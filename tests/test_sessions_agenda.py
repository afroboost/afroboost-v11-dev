# -*- coding: utf-8 -*-
"""L'agenda public rend les MEMES horaires que les cartes d'offres.

Le vrai `sessions_agenda` est extrait de `api/server.py` par AST et execute
sur un faux MongoDB, avec les documents REELS de production (les identifiants
et les drapeaux sont ceux observes le 17/08/2026).

Aucun reseau. Aucune base. Aucune ecriture.

Lancement :  python3 tests/test_sessions_agenda.py
"""

import ast
import asyncio
import io
import os
import sys
from datetime import datetime, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("introuvable : %s" % nom)


def extraire(nom):
    n = noeud(nom)
    return "".join(LIGNES[n.lineno - 1:n.end_lineno])


def code_nu(nom):
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps)


# ------------------------------------------------------- faux client MongoDB
MANQUANT = object()


def _val(doc, chemin):
    cur = doc
    for p in chemin.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return MANQUANT
        cur = cur[p]
    return cur


def _match(doc, q):
    for cle, attendu in (q or {}).items():
        if cle == "$or":
            if not any(_match(doc, sous) for sous in attendu):
                return False
            continue
        obtenu = _val(doc, cle)
        if isinstance(attendu, dict):
            for op, v in attendu.items():
                if op == "$ne":
                    if obtenu is not MANQUANT and obtenu == v:
                        return False
                elif op == "$in":
                    if obtenu is MANQUANT or obtenu not in v:
                        return False
                elif op == "$exists":
                    if bool(obtenu is not MANQUANT) != bool(v):
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        else:
            if obtenu is MANQUANT or obtenu != attendu:
                return False
    return True


class _Curseur(object):
    def __init__(self, d):
        self.d = d

    async def to_list(self, n):
        await asyncio.sleep(0)
        import copy
        return [copy.deepcopy(x) for x in self.d[:n]]


class _Coll(object):
    def __init__(self, docs):
        self.docs = docs

    def find(self, q=None, p=None):
        return _Curseur([d for d in self.docs if _match(d, q or {})])


class _Base(object):
    def __init__(self, offres, cours):
        self.offers = _Coll(offres)
        self.courses = _Coll(cours)


# ------------------------------------------------------------------ le bac
CONSTANTES = """
_V184_WEEKDAY_LABELS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
"""

A_EXTRAIRE = ["_v184_parse_time_hhmm", "_v184_next_occurrences", "sessions_agenda",
              "rv3_cours_configurables",
              # E1B : la regle « ce cours sert-il encore ? » est desormais
              # ecrite une seule fois et partagee avec le moteur de rappels.
              "e1b_cours_encore_servi"]

APPELANT = ["coach@exemple.com"]


class _HTTP(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code
        self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))


async def _appelant(request):
    await asyncio.sleep(0)
    return APPELANT[0]


def bac(offres, cours):
    base = _Base(offres, cours)
    b = {
        "db": base,
        "datetime": datetime, "timedelta": timedelta,
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
        "api_router": type("r", (), {"get": staticmethod(lambda *a, **k: (lambda f: f))}),
        "HTTPException": _HTTP,
        "Request": object,
        "is_super_admin": lambda e: (e or "").lower() == "admin@exemple.com",
        "_n1b3b2_coach_appelant": _appelant,
    }
    exec(compile("\n\n".join([CONSTANTES] + [extraire(f) for f in A_EXTRAIRE]),
                 "<agenda>", "exec"), b)
    return b, base


# --------------------------------------------------- documents REELS observes
MERCREDI = {"id": "64b4c975", "name": "Afroboost Silent – Session Cardio",
            "weekday": 3, "time": "18:30", "locationName": "Neuchâtel",
            "visible": True, "archived": True, "agenda_abonne": True}
DIMANCHE = {"id": "23534f7c", "name": "Afroboost Silent – Sunday Vibes",
            "weekday": 0, "time": "18:30", "locationName": "Neuchâtel",
            "visible": True, "archived": True, "agenda_abonne": True}
EVENEMENT = {"id": "laff21", "name": "Laff Festival", "weekday": 5, "date": "2026-08-21",
             "time": "18:30", "locationName": "Lausanne", "visible": True, "archived": False}
RETIRE = {"id": "vieux", "name": "Cours retire", "weekday": 2, "time": "20:00",
          "visible": True, "archived": True}          # archive SANS agenda_abonne
MASQUE = {"id": "brouillon", "name": "Nouveau cours", "weekday": 4, "time": "18:30",
          "visible": False, "archived": False}

PULSE = {"id": "pulse", "name": "PULSE x10 cours", "visible": True,
         "linked_course_ids": ["64b4c975", "23534f7c"]}
MEMBRES = {"id": "membres", "name": "Membres", "visible": True,
           "linked_course_ids": ["64b4c975", "23534f7c"]}
OFFRE_EVT = {"id": "off-evt", "name": "Afroboost Silent", "visible": True,
             "linked_course_ids": ["laff21"]}
OFFRE_RETIREE = {"id": "off-vieux", "name": "Ancienne offre", "visible": True,
                 "linked_course_ids": ["vieux"]}


async def agenda(offres, cours, jours=60):
    b, _ = bac(offres, cours)
    return await b["sessions_agenda"](days=jours)


def jours_de(sortie):
    return sorted({o["datetime"][:10] for o in sortie["occurrences"]})


async def scenarios():
    # --- A. le cas reel : PULSE et Membres, mercredi + dimanche --------------
    s = await agenda([PULSE, MEMBRES, OFFRE_EVT], [MERCREDI, DIMANCHE, EVENEMENT], jours=30)
    occ = s["occurrences"]
    verifier("A1. les seances recurrentes du mercredi et du dimanche SORTENT",
             len(occ) > 0, "%d occurrence(s)" % len(occ))

    _mercredis = [o for o in occ if o["course_id"] == "64b4c975"]
    _dimanches = [o for o in occ if o["course_id"] == "23534f7c"]
    verifier("A2. les deux cours archives mais `agenda_abonne` sont presents",
             len(_mercredis) > 0 and len(_dimanches) > 0,
             "mercredi %d / dimanche %d" % (len(_mercredis), len(_dimanches)))

    verifier("A3. tous les mercredis tombent bien un mercredi",
             all(datetime.fromisoformat(o["datetime"]).weekday() == 2 for o in _mercredis))
    verifier("A4. tous les dimanches tombent bien un dimanche",
             all(datetime.fromisoformat(o["datetime"]).weekday() == 6 for o in _dimanches))
    verifier("A5. l'heure annoncee est 18:30 partout",
             all(o["datetime"][11:16] == "18:30" for o in _mercredis + _dimanches),
             str(sorted({o["datetime"][11:16] for o in _mercredis + _dimanches})))

    # --- B. ANTI-DOUBLON : deux offres, un seul cours -----------------------
    _cles = [(o["course_id"], o["datetime"]) for o in occ]
    verifier("B1. PULSE et Membres pointent le meme cours -> UNE occurrence",
             len(_cles) == len(set(_cles)),
             "%d occurrences pour %d cles distinctes" % (len(_cles), len(set(_cles))))
    verifier("B2. mais les DEUX offres sont listees a cote de la seance",
             _mercredis and sorted(x["id"] for x in _mercredis[0]["offers"]) == ["membres", "pulse"],
             str(_mercredis[0]["offers"] if _mercredis else None))

    # --- C. la regle exacte : archive SEUL ne suffit pas --------------------
    s2 = await agenda([PULSE, MEMBRES, OFFRE_RETIREE], [MERCREDI, DIMANCHE, RETIRE], jours=30)
    verifier("C1. un cours archive SANS `agenda_abonne` reste dehors, meme lie a une offre",
             not any(o["course_id"] == "vieux" for o in s2["occurrences"]))
    s3 = await agenda([], [MASQUE], jours=30)
    verifier("C2. un cours `visible: false` non lie reste dehors",
             len(s3["occurrences"]) == 0, str(s3["occurrences"][:1]))
    s4 = await agenda([], [EVENEMENT], jours=60)
    verifier("C3. un cours publie SANS offre publique ne sort pas — pas de chemin d'acces",
             len(s4["occurrences"]) == 0, str(s4["occurrences"][:1]))
    s5 = await agenda([OFFRE_EVT], [EVENEMENT], jours=60)
    verifier("C3b. le meme cours sort des qu'une offre publique y mene",
             len(s5["occurrences"]) == 1)

    # --- D. FLEXIBILITE : aucun jour n'est fige -----------------------------
    JEUDI = dict(MERCREDI, id="jeu", name="Atelier", weekday=4, time="19:00")
    OFF_J = {"id": "oj", "name": "Offre jeudi", "visible": True, "linked_course_ids": ["jeu"]}
    sj = await agenda([OFF_J], [JEUDI], jours=30)
    verifier("D1. un cours du jeudi apparait le JEUDI, sans une ligne de code en plus",
             sj["occurrences"] and all(
                 datetime.fromisoformat(o["datetime"]).weekday() == 3 for o in sj["occurrences"]),
             str(jours_de(sj)[:3]))
    verifier("D2. et a 19:00",
             all(o["datetime"][11:16] == "19:00" for o in sj["occurrences"]))

    # le coach deplace le cours : jeudi -> samedi, 19:00 -> 10:30
    SAMEDI = dict(JEUDI, weekday=6, time="10:30")
    ss = await agenda([OFF_J], [SAMEDI], jours=30)
    verifier("D3. deplace au samedi, les futures occurrences suivent",
             ss["occurrences"] and all(
                 datetime.fromisoformat(o["datetime"]).weekday() == 5 for o in ss["occurrences"]),
             str(jours_de(ss)[:3]))
    verifier("D4. et la nouvelle heure suit aussi",
             all(o["datetime"][11:16] == "10:30" for o in ss["occurrences"]))
    verifier("D5. l'identifiant du cours n'a pas bouge — la config tient au cours",
             all(o["course_id"] == "jeu" for o in ss["occurrences"]))

    # les sept jours, sans distinction
    for _j in range(7):
        _c = dict(MERCREDI, id="j%d" % _j, weekday=_j)
        _o = {"id": "o%d" % _j, "name": "o", "visible": True, "linked_course_ids": ["j%d" % _j]}
        _s = await agenda([_o], [_c], jours=14)
        if not _s["occurrences"]:
            verifier("D6. les sept jours de la semaine sont couverts", False, "weekday=%d vide" % _j)
            break
    else:
        verifier("D6. les sept jours de la semaine sont couverts", True)

    # --- E. contenu d'une occurrence ---------------------------------------
    o = _mercredis[0]
    verifier("E1. l'occurrence porte tout ce qu'il faut a l'ecran",
             all(k in o for k in ("course_id", "name", "date", "time", "datetime",
                                  "locationName", "offers", "recurrent")),
             str(sorted(o.keys())))
    verifier("E2. un cours recurrent est marque comme tel",
             o.get("recurrent") is True)
    _evt = [x for x in occ if x["course_id"] == "laff21"]
    verifier("E3. un evenement date est marque comme NON recurrent",
             _evt and _evt[0].get("recurrent") is False, str(_evt[:1]))
    verifier("E4. les occurrences sortent triees",
             [x["datetime"] for x in occ] == sorted(x["datetime"] for x in occ))

    # --- F. bornes ----------------------------------------------------------
    verifier("F1. l'horizon demande est respecte",
             all(datetime.fromisoformat(x["datetime"]) <= datetime.now() + timedelta(days=31)
                 for x in occ))
    _s = await agenda([PULSE], [MERCREDI], jours=10000)
    verifier("F2. un horizon aberrant est borne, pas honore", _s["jours"] == 180, str(_s["jours"]))


# ============================================================================
#        LE LIEU — canonique sur le COURS, jamais emprunte a une offre
# ============================================================================
async def scenarios_lieu():
    """Une seance a UN lieu, et il vit sur le cours.

    Une offre est un moyen d'acces commercial : trois offres peuvent mener a la
    meme seance, il serait absurde que le lieu depende de celle par laquelle on
    arrive. `_v184_next_occurrences` lit donc `locationName` sur le cours, et
    l'agenda le transmet sans le toucher.
    """
    AUVERNIER = "Bord du Lac, Auvernier, Neuchatel"
    LAUSANNE = "ESPLANADE & CASINO DE MONTBENON, LAUSANNE"

    _merc = dict(MERCREDI, locationName=AUVERNIER)
    _dim = dict(DIMANCHE, locationName=AUVERNIER)
    _o1 = {"id": "pulse", "name": "PULSE x10 cours", "visible": True,
           "linked_course_ids": ["64b4c975", "23534f7c"]}
    _o2 = {"id": "membres", "name": "Membres", "visible": True,
           "linked_course_ids": ["64b4c975", "23534f7c"]}
    _o3 = {"id": "unite", "name": "Cours a l'unite", "visible": True,
           "linked_course_ids": ["64b4c975", "23534f7c"]}

    # --- A. trois offres, un seul cours -> une occurrence, un seul lieu ------
    s = await agenda([_o1, _o2, _o3], [_merc, _dim], jours=10)
    _m = [o for o in s["occurrences"] if o["course_id"] == "64b4c975"]
    _d = [o for o in s["occurrences"] if o["course_id"] == "23534f7c"]
    _cles = [(o["course_id"], o["datetime"]) for o in s["occurrences"]]
    verifier("L-A. trois offres sur le meme cours -> aucune occurrence en double",
             len(_cles) == len(set(_cles)) and len(_m) >= 1,
             "%d occurrences / %d cles" % (len(_cles), len(set(_cles))))

    # --- B. le lieu canonique est celui du COURS ----------------------------
    verifier("L-B. Sessions rend le lieu enregistre sur le cours",
             all(o["locationName"] == AUVERNIER for o in _m + _d),
             str({o["locationName"] for o in _m + _d}))
    verifier("L-B2. et il est IDENTIQUE quelle que soit l'offre d'acces",
             len({o["locationName"] for o in _m}) == 1)
    verifier("L-B3. les trois offres sont bien listees a cote, sans influer sur le lieu",
             _m and sorted(x["id"] for x in _m[0]["offers"]) == ["membres", "pulse", "unite"],
             str(_m[0]["offers"] if _m else None))

    # --- C. aucune valeur parasite ne fuit ----------------------------------
    # Le document porte un alias `location` divergent : c'est exactement le cas
    # reel. `locationName` doit primer, sans jamais laisser passer l'alias.
    _divergent = dict(_merc, locationName=AUVERNIER, location="Jeunes-Rives, terrain de basket")
    s = await agenda([_o1], [_divergent], jours=10)
    verifier("L-C. un alias `location` divergent ne fuit JAMAIS quand `locationName` existe",
             all(o["locationName"] == AUVERNIER for o in s["occurrences"])
             and not any("Jeunes-Rives" in json_texte(o) for o in s["occurrences"]),
             str({o["locationName"] for o in s["occurrences"]}))

    # --- C2. le repli sur `location` reste, mais seulement si besoin ---------
    _sans_nom = dict(_merc, locationName="", location=AUVERNIER)
    s = await agenda([_o1], [_sans_nom], jours=10)
    verifier("L-C2. `locationName` vide -> repli documente sur `location`",
             all(o["locationName"] == AUVERNIER for o in s["occurrences"]),
             str({o["locationName"] for o in s["occurrences"]}))

    # --- D. changer le lieu du cours suffit ---------------------------------
    _deplace = dict(_merc, locationName=LAUSANNE)
    s = await agenda([_o1], [_deplace], jours=10)
    verifier("L-D. changer le lieu du cours change Sessions, sans une ligne de code",
             s["occurrences"] and all(o["locationName"] == LAUSANNE for o in s["occurrences"]),
             str({o["locationName"] for o in s["occurrences"]}))

    # --- E. jour, heure et lieu bougent ensemble ----------------------------
    _tout = dict(_merc, weekday=4, time="19:00", locationName=LAUSANNE)
    s = await agenda([_o1], [_tout], jours=14)
    _ok = s["occurrences"] and all(
        datetime.fromisoformat(o["datetime"]).weekday() == 3
        and o["datetime"][11:16] == "19:00"
        and o["locationName"] == LAUSANNE for o in s["occurrences"])
    verifier("L-E. mercredi/Auvernier -> jeudi 19:00/Lausanne suit entierement", _ok,
             str([(o["datetime"], o["locationName"]) for o in s["occurrences"][:2]]))

    # --- F. Sunday Vibes suit exactement la meme logique --------------------
    _dim2 = dict(_dim, locationName=LAUSANNE, weekday=6, time="10:30")
    s = await agenda([_o1], [_dim2], jours=14)
    _ok = s["occurrences"] and all(
        datetime.fromisoformat(o["datetime"]).weekday() == 5
        and o["locationName"] == LAUSANNE for o in s["occurrences"])
    verifier("L-F. le cours du dimanche obeit aux memes regles, sans cas particulier", _ok,
             str([(o["datetime"], o["locationName"]) for o in s["occurrences"][:2]]))

    # --- H. QUATRE cours, QUATRE villes, aucune contamination ---------------
    # Aucune ville n'est un cas particulier : le lieu est une donnee du cours,
    # au meme titre que son heure. On en prend quatre a la fois, on en deplace
    # UN seul, et on verifie que les trois autres n'ont pas bouge d'un caractere.
    _villes = [("cA", 1, "Auvernier"), ("cB", 2, "Lausanne"),
               ("cC", 4, "Geneve"), ("cD", 5, "Neuchatel")]
    _quatre = [dict(MERCREDI, id=_i, name="Cours " + _i, weekday=_w, locationName=_v)
               for _i, _w, _v in _villes]
    _offre4 = {"id": "o4", "name": "Passe partout", "visible": True,
               "linked_course_ids": [i for i, _, _ in _villes]}

    s = await agenda([_offre4], _quatre, jours=14)
    _lieu_de = {}
    for o in s["occurrences"]:
        _lieu_de.setdefault(o["course_id"], set()).add(o["locationName"])
    verifier("L-H1. quatre cours simultanes -> quatre villes distinctes, chacune chez soi",
             {c: sorted(v) for c, v in _lieu_de.items()}
             == {i: [v] for i, _, v in _villes},
             str({c: sorted(v) for c, v in _lieu_de.items()}))
    verifier("L-H2. et chacun tombe bien son jour",
             all(datetime.fromisoformat(o["datetime"]).weekday() == (w - 1) % 7
                 for o in s["occurrences"]
                 for i, w, _ in _villes if o["course_id"] == i))

    # on deplace UN seul cours : Lausanne -> Bienne
    _bouge = [dict(c, locationName="Bienne") if c["id"] == "cB" else c for c in _quatre]
    s2 = await agenda([_offre4], _bouge, jours=14)
    _apres = {}
    for o in s2["occurrences"]:
        _apres.setdefault(o["course_id"], set()).add(o["locationName"])
    verifier("L-H3. deplacer UN cours ne touche a AUCUN autre",
             {c: sorted(v) for c, v in _apres.items()}
             == {"cA": ["Auvernier"], "cB": ["Bienne"], "cC": ["Geneve"], "cD": ["Neuchatel"]},
             str({c: sorted(v) for c, v in _apres.items()}))

    # et on peut tous les deplacer, dans n'importe quel ordre
    _tous = [dict(c, locationName="Ville-" + c["id"]) for c in _quatre]
    s3 = await agenda([_offre4], _tous, jours=14)
    verifier("L-H4. les quatre suivent independamment, sans ordre privilegie",
             all(o["locationName"] == "Ville-" + o["course_id"] for o in s3["occurrences"]),
             str(sorted({(o["course_id"], o["locationName"]) for o in s3["occurrences"]})))

    # --- G. le lieu d'une OFFRE n'entre jamais dans l'occurrence -------------
    _offre_ailleurs = dict(_o1, location="Un tout autre endroit")
    s = await agenda([_offre_ailleurs], [_merc], jours=10)
    verifier("L-G. le lieu de l'offre n'est jamais recopie sur la seance",
             not any("tout autre endroit" in json_texte(o) for o in s["occurrences"]))


# ============================================================================
#     VISITEUR — une offre masquee n'apparait JAMAIS, ni en direct ni par ricochet
# ============================================================================
MASQUEE = {"id": "off-masq", "name": "SILENT LAKESIDE", "visible": False,
           "linked_course_ids": ["cache", "mixte"]}
PUBLIQUE_MIXTE = {"id": "off-pub", "name": "Membres", "visible": True,
                  "linked_course_ids": ["mixte"]}
CACHE = {"id": "cache", "name": "Seance confidentielle", "weekday": 1, "time": "20:00",
         "visible": True, "archived": True, "agenda_abonne": True}
MIXTE = {"id": "mixte", "name": "Seance mixte", "weekday": 2, "time": "19:00",
         "visible": True, "archived": True, "agenda_abonne": True}


async def scenarios_visiteur():
    # --- CAS A : lie UNIQUEMENT a une offre masquee -------------------------
    s = await agenda([MASQUEE], [CACHE], jours=30)
    verifier("V-A. cours archive lie SEULEMENT a une offre masquee -> jamais public",
             len(s["occurrences"]) == 0, str(s["occurrences"][:1]))

    # --- CAS B : offre publique + offre masquee -----------------------------
    s = await agenda([MASQUEE, PUBLIQUE_MIXTE], [MIXTE], jours=30)
    _occ = s["occurrences"]
    verifier("V-B1. lie a une offre publique ET a une masquee -> le cours sort",
             len(_occ) > 0, "%d" % len(_occ))
    _noms = {x["name"] for o in _occ for x in o["offers"]}
    verifier("V-B2. seule l'offre PUBLIQUE est exposee",
             _noms == {"Membres"}, str(sorted(_noms)))
    verifier("V-B3. le nom de l'offre masquee n'apparait nulle part",
             "SILENT LAKESIDE" not in json_texte(s), "")

    # --- CAS C : deux offres publiques, une seule occurrence ----------------
    _p2 = dict(PUBLIQUE_MIXTE, id="off-pub2", name="PULSE x10 cours")
    s = await agenda([PUBLIQUE_MIXTE, _p2], [MIXTE], jours=14)
    _cles = [(o["course_id"], o["datetime"]) for o in s["occurrences"]]
    verifier("V-C. deux offres publiques sur le meme cours -> UNE occurrence",
             len(_cles) == len(set(_cles)) and len(_cles) > 0,
             "%d occurrences / %d cles" % (len(_cles), len(set(_cles))))
    verifier("V-C2. mais les deux offres sont proposees comme acces",
             s["occurrences"] and len(s["occurrences"][0]["offers"]) == 2,
             str(s["occurrences"][0]["offers"] if s["occurrences"] else None))

    # --- CAS D : une offre masquee n'est jamais un moyen d'acces ------------
    s = await agenda([MASQUEE, PUBLIQUE_MIXTE], [MIXTE, CACHE], jours=14)
    verifier("V-D. aucune offre masquee ne figure comme option d'acces",
             all(all(x["id"] != "off-masq" for x in o["offers"]) for o in s["occurrences"]))

    # --- CAS E : l'offre masquee devient publique ---------------------------
    _devenue = dict(MASQUEE, visible=True)
    s = await agenda([_devenue], [CACHE], jours=30)
    verifier("V-E. offre rendue publique -> son cours devient eligible, sans code en plus",
             len(s["occurrences"]) > 0, "%d" % len(s["occurrences"]))

    # --- CAS F : l'offre publique devient masquee ---------------------------
    _retiree = dict(PUBLIQUE_MIXTE, visible=False)
    s = await agenda([_retiree, MASQUEE], [MIXTE], jours=30)
    verifier("V-F. offre rendue masquee -> le cours quitte le parcours visiteur",
             len(s["occurrences"]) == 0, "%d" % len(s["occurrences"]))

    # --- le coeur de la regle : PAS de chemin public, PAS de seance ---------
    # Un cours parfaitement publie mais rattache a la seule offre masquee est
    # une impasse : le visiteur le verrait sans pouvoir le reserver. Sessions
    # decrit ce qui est ACCESSIBLE, pas ce qui existe.
    _publie_impasse = {"id": "impasse", "name": "Silent Dance & Fitness",
                       "weekday": 0, "time": "18:30", "visible": True, "archived": False}
    _off_m2 = {"id": "off-m2", "name": "Silent Dance", "visible": False,
               "linked_course_ids": ["impasse"]}
    s = await agenda([_off_m2], [_publie_impasse], jours=14)
    verifier("V-G. cours PUBLIE mais sans offre publique -> absent de Sessions",
             len(s["occurrences"]) == 0, str(s["occurrences"][:1]))

    _off_p2 = dict(_off_m2, id="off-p2", visible=True)
    s = await agenda([_off_p2], [_publie_impasse], jours=14)
    verifier("V-G2. la meme seance revient des que son offre est publiee",
             len(s["occurrences"]) > 0)

    # --- aucun cours du tout n'est rattache a une offre publique -----------
    s = await agenda([MASQUEE], [CACHE, MIXTE, _publie_impasse], jours=14)
    verifier("V-H. aucune offre publique -> agenda vide, jamais une impasse",
             s["occurrences"] == [], str(s["occurrences"][:1]))


def json_texte(x):
    import json as _j
    return _j.dumps(x, ensure_ascii=False)


# ============================================================================
#        COACH — administrer n'est pas publier
# ============================================================================
VRAI_MERC = {"id": "merc", "name": "Afroboost Silent – Session Cardio", "weekday": 3,
             "time": "18:30", "visible": True, "archived": True, "agenda_abonne": True,
             "coach_id": "coach@exemple.com"}
VRAI_DIM = {"id": "dim", "name": "Afroboost Silent – Sunday Vibes", "weekday": 0,
            "time": "18:30", "visible": True, "archived": True, "agenda_abonne": True,
            "coach_id": "coach@exemple.com"}
BROUILLON = {"id": "brouillon", "name": "Nouveau cours", "weekday": 3, "time": "18:30",
             "visible": False, "archived": False, "coach_id": "coach@exemple.com"}
OUBLIE = {"id": "oublie", "name": "SUNSET × SILENT DISCO", "weekday": 3, "time": "18:30",
          "visible": True, "archived": True, "coach_id": "coach@exemple.com"}
OFF_VEND = {"id": "pulse", "name": "PULSE x10 cours", "visible": True,
            "linked_course_ids": ["merc", "dim"]}


async def liste_coach(offres, cours):
    b, _ = bac(offres, cours)
    return await b["rv3_cours_configurables"](object())


async def scenarios_coach():
    APPELANT[0] = "coach@exemple.com"
    s = await liste_coach([OFF_VEND], [VRAI_MERC, VRAI_DIM, BROUILLON, OUBLIE])
    _ids = [c["id"] for c in s]

    verifier("C-1. le VRAI cours du mercredi, archive mais vendu, est configurable",
             "merc" in _ids, str(_ids))
    verifier("C-2. le VRAI cours du dimanche aussi",
             "dim" in _ids, str(_ids))
    verifier("C-3. un brouillon `visible: false` reste administrable — publier n'est pas administrer",
             "brouillon" in _ids, str(_ids))
    verifier("C-4. un cours archive SANS offre et SANS agenda_abonne sort de la liste",
             "oublie" not in _ids, str(_ids))
    verifier("C-5. la liste dit par quelles offres le cours est vendu",
             [c for c in s if c["id"] == "merc"][0]["offres"][0]["name"] == "PULSE x10 cours")
    verifier("C-6. et si ces offres sont publiques",
             [c for c in s if c["id"] == "merc"][0]["offres"][0]["publique"] is True)
    verifier("C-7. un brouillon sans offre le dit franchement",
             [c for c in s if c["id"] == "brouillon"][0]["offres"] == [])

    # une offre MASQUEE suffit a prouver qu'un cours sert — mais elle est marquee
    _off_m = {"id": "m", "name": "Offre masquee", "visible": False,
              "linked_course_ids": ["oublie"]}
    s2 = await liste_coach([_off_m], [OUBLIE])
    verifier("C-8. un cours archive rattache a une offre MASQUEE reste administrable",
             [c["id"] for c in s2] == ["oublie"], str([c["id"] for c in s2]))
    verifier("C-9. et l'ecran sait que cette offre n'est pas publique",
             s2[0]["offres"][0]["publique"] is False)

    # generique : un jeudi cree demain
    _jeu = {"id": "jeu", "name": "Atelier du jeudi", "weekday": 4, "time": "19:00",
            "visible": False, "archived": True, "agenda_abonne": True,
            "coach_id": "coach@exemple.com"}
    _off_j = {"id": "oj", "name": "Offre jeudi", "visible": True, "linked_course_ids": ["jeu"]}
    s3 = await liste_coach([_off_j], [_jeu])
    verifier("C-10. un cours du jeudi cree demain devient configurable sans code en plus",
             [c["id"] for c in s3] == ["jeu"])

    # cloisonnement par coach
    _autre = dict(BROUILLON, id="autre", coach_id="ailleurs@exemple.com")
    s4 = await liste_coach([], [BROUILLON, _autre])
    verifier("C-11. un coach ne voit que SES cours",
             [c["id"] for c in s4] == ["brouillon"], str([c["id"] for c in s4]))
    APPELANT[0] = "admin@exemple.com"
    s5 = await liste_coach([], [BROUILLON, _autre])
    verifier("C-12. le super-admin les voit tous",
             sorted(c["id"] for c in s5) == ["autre", "brouillon"])
    APPELANT[0] = "coach@exemple.com"

    verifier("C-13. la selection se fait par course_id, jamais par titre",
             all("id" in c for c in s) and len({c["id"] for c in s}) == len(s))

    # --- la liste sert AUSSI l'ecran de gestion : le document part ENTIER ---
    _riche = dict(VRAI_MERC, mapsUrl="https://maps.example/x",
                  playlist=["a"], audio_tracks=[{"u": "b"}], locationName="Auvernier")
    s6 = await liste_coach([OFF_VEND], [_riche])
    verifier("C-14. le document repart entier — `mapsUrl` et le reste ne sont pas rabotes",
             all(k in s6[0] for k in ("mapsUrl", "playlist", "audio_tracks",
                                      "locationName", "visible", "archived")),
             str(sorted(s6[0].keys())))
    verifier("C-15. l'alias `location` est recalcule, jamais servi perime",
             s6[0].get("location") == "Auvernier", repr(s6[0].get("location")))

    _perime = dict(_riche, locationName="Jeunes-Rives", location="Auvernier")
    s7 = await liste_coach([OFF_VEND], [_perime])
    verifier("C-16. un alias perime en base ne ressort pas de la route",
             s7[0].get("location") == "Jeunes-Rives", repr(s7[0].get("location")))

    # --- administrer n'a JAMAIS publie quoi que ce soit --------------------
    _avant = (VRAI_MERC.get("visible"), VRAI_MERC.get("archived"))
    s8 = await liste_coach([OFF_VEND], [VRAI_MERC])
    verifier("C-17. la route ne modifie ni `visible` ni `archived`",
             (VRAI_MERC.get("visible"), VRAI_MERC.get("archived")) == _avant
             and s8[0]["archived"] is True and s8[0]["visible"] is True,
             str(s8[0].get("archived")))

    # le meme cours reste hors du parcours visiteur tant qu'aucune offre
    # publique n'y mene — administrer ne publie pas.
    _off_masq = {"id": "m2", "name": "Masquee", "visible": False,
                 "linked_course_ids": ["merc"]}
    _vis = await agenda([_off_masq], [VRAI_MERC], jours=14)
    verifier("C-18. administrable cote coach n'implique JAMAIS visible cote visiteur",
             _vis["occurrences"] == [], str(_vis["occurrences"][:1]))


def structure():
    nu = code_nu("sessions_agenda")
    verifier("S1. la route reutilise le calcul d'occurrences existant",
             "_v184_next_occurrences" in nu)
    verifier("S2. elle applique la regle V426 `agenda_abonne`",
             "agenda_abonne" in nu)
    verifier("S3. elle dedoublonne par (cours, instant), jamais par offre",
             "course_id" in nu and "datetime" in nu)
    verifier("S4. elle ne code AUCUN jour de la semaine",
             not any(j in nu.lower() for j in
                     ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")))
    verifier("S5. elle n'ecrit rien en base",
             not any(m in nu for m in ("update_one", "insert_one", "delete_one", "$set")))
    verifier("S6. elle ne lit pas les offres masquees",
             "'visible'" in nu.replace('"', "'"))

    nu_coach = code_nu("rv3_cours_configurables")
    # `visible` figure dans la route — projection du document, lecture de l'etat
    # des offres. Ce qui compte est qu'il n'entre PAS dans la decision. On lit
    # donc la garde elle-meme, pas le texte de la fonction.
    _gardes = []
    for _n in ast.walk(noeud("rv3_cours_configurables")):
        if (isinstance(_n, ast.If) and len(_n.body) == 1
                and isinstance(_n.body[0], ast.Continue)):
            _gardes.append(ast.unparse(_n.test))
    verifier("S8. AUCUNE garde de la regle COACH ne decide sur `visible`",
             _gardes and all("visible" not in g for g in _gardes), str(_gardes))
    # E1B : la garde ne recopie plus la regle, elle l'APPELLE. Ce deplacement est
    # le fond du lot : le moteur de rappels appelle exactement la meme fonction,
    # et deux ecritures de la meme regle ne peuvent plus diverger. On verifie
    # donc que la garde delegue, puis que la fonction appelee decide bien sur
    # l'archivage, les offres et `agenda_abonne`.
    verifier("S8b. sa garde d'eligibilite delegue a la regle partagee",
             any("e1b_cours_encore_servi" in g for g in _gardes), str(_gardes))
    nu_regle = code_nu("e1b_cours_encore_servi")
    verifier("S9. la regle partagee s'appuie sur l'archivage et `agenda_abonne`",
             all(m in nu_regle for m in ("archived", "agenda_abonne"))
             and "linked_course_ids" in nu_coach)
    verifier("S9b. le moteur de rappels appelle LA MEME regle",
             "e1b_cours_encore_servi" in SOURCE[SOURCE.find(
                 "async def cron_reservation_reminders"):])
    verifier("S10. elle expose l'etat de publication de chaque offre",
             "publique" in nu_coach)
    verifier("S11. elle n'ecrit rien en base",
             not any(m in nu_coach for m in ("update_one", "insert_one", "$set")))

    nu_occ = code_nu("_v184_next_occurrences")
    verifier("S12. le lieu d'une occurrence vient du COURS, jamais d'une offre",
             "locationName" in nu_occ and "offer" not in nu_occ.lower())
    nu_ag = code_nu("sessions_agenda")
    verifier("S13. l'agenda ne reecrit aucun lieu",
             "locationName" not in nu_ag, "")

    # Aucune ville n'est un cas particulier. `Europe/Zurich` est un FUSEAU
    # horaire, pas une adresse : on l'ecarte explicitement du controle plutot
    # que de laisser le test croire a une infraction.
    _villes = ("auvernier", "lausanne", "geneve", "genève", "neuchatel",
               "neuchâtel", "vallangines", "jeunes-rives", "montbenon",
               "vidy", "st-blaise", "bienne")
    for _f in ("sessions_agenda", "_v184_next_occurrences",
               "rv3_cours_configurables", "_enrich_offers_with_next_date"):
        _nu = code_nu(_f).lower().replace("europe/zurich", "")
        _trouves = [v for v in _villes if v in _nu]
        verifier("S14. `%s` ne code AUCUN lieu en dur" % _f, not _trouves, str(_trouves))

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S7. ce test n'importe que la bibliotheque standard hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "datetime", "copy", "json"},
             str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(scenarios())
        b.run_until_complete(scenarios_visiteur())
        b.run_until_complete(scenarios_coach())
        b.run_until_complete(scenarios_lieu())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Requetes MongoDB reelles : 0 — la base est un double en memoire")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

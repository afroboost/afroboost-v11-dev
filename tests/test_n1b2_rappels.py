# -*- coding: utf-8 -*-
"""N1B-2 — tests hors ligne. Aucune base, aucun reseau.

Les fonctions testees sont EXTRAITES du vrai `api/server.py` (via AST), pas
recopiees : si le code change, le test suit.
"""
import ast, asyncio, os, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "server.py")
A_EXTRAIRE = {"n1b2_cle", "n1b2_titre", "n1b2_corps", "n1b2_cible",
              "n1b2_valider_regles", "n1b_deja_envoye",
              "n1b3b2_plan", "n1b3b2_regles_trop_proches", "n1b3b2_collisions",
              # N1B-3B2 : les DEUX routes sont extraites comme le reste. Le
              # cloisonnement entre coachs ne se demontre pas sur une copie du
              # code — il se demontre sur le code REELLEMENT servi. Et c'est
              # possible ici : `get_source_segment` part du `def`, donc le
              # decorateur `@api_router` ne suit pas et la route redevient une
              # coroutine ordinaire, appelable sans FastAPI.
              "_n1b3b2_coach_appelant", "_n1b3b2_occurrences_du_coach",
              "n1b3b2_lire_regles", "n1b3b2_ecrire_regles"}
CONSTANTES = {"N1B_CLE_HERITEE", "N1B2_MAX_REGLES", "N1B2_DELAIS_AUTORISES",
              "N1B2_REGLES_DEFAUT", "N1B2_DEMI_FENETRE_MIN", "N1B2_HORIZON_MIN",
              "N1B2_MINUTES_AUTORISEES", "N1B3B2_ECART_MIN",
              "N1B3B2_HORIZON_JOURS"}

src = open(SRC, encoding="utf-8").read()
arbre = ast.parse(src)
morceaux = []
for n in arbre.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in A_EXTRAIRE:
        morceaux.append(ast.get_source_segment(src, n))
    elif isinstance(n, ast.Assign):
        for c in n.targets:
            if isinstance(c, ast.Name) and c.id in CONSTANTES:
                morceaux.append(ast.get_source_segment(src, n))

# === N1B-3B2 : de quoi appeler les routes hors FastAPI, sans base ni reseau ==
#
# Les routes s'appuient sur quatre choses seulement : l'identite de l'appelant,
# la base, `HTTPException`, et le journal. On les remplace par des doubles qui
# ENREGISTRENT chaque appel. C'est ce journal qui fait la preuve : il ne suffit
# pas que le coach A recoive les bonnes regles — il faut que la requete partie
# vers Mongo n'ait JAMAIS pu en designer une autre. Un test qui se contenterait
# de comparer la reponse passerait alors meme que le filtre serait ouvert.

class FauxHTTPException(Exception):
    """Meme surface que celle de FastAPI : un code et un detail."""
    def __init__(self, status_code=500, detail=""):
        self.status_code, self.detail = status_code, detail
        Exception.__init__(self, "%s %s" % (status_code, detail))


class FausseRequete:
    """Porte un corps JSON. `Request` ne sert que d'annotation de signature."""
    def __init__(self, corps=None, illisible=False):
        self._corps, self._illisible = corps, illisible

    async def json(self):
        if self._illisible:
            raise ValueError("corps illisible")
        return self._corps


class FausseCollection:
    """Documents en memoire, et journal des filtres REELLEMENT envoyes."""
    def __init__(self):
        self.docs, self.filtres = [], []

    @staticmethod
    def _colle(doc, filtre):
        # Les conditions a operateur (`{"$ne": True}`) ne servent pas au
        # cloisonnement : on ne les rejoue pas, mais le filtre reste journalise.
        return all(doc.get(c) == v for c, v in filtre.items()
                   if not isinstance(v, dict))

    async def find_one(self, filtre, projection=None):
        self.filtres.append(("find_one", dict(filtre)))
        for _d in self.docs:
            if self._colle(_d, filtre):
                return dict(_d)
        return None

    async def update_one(self, filtre, maj, upsert=False):
        self.filtres.append(("update_one", dict(filtre)))
        for _d in self.docs:
            if self._colle(_d, filtre):
                _d.update(maj.get("$set", {}))
                return
        if upsert:
            self.docs.append(dict(maj.get("$set", {})))

    def find(self, filtre, projection=None):
        self.filtres.append(("find", dict(filtre)))
        _trouves = [dict(_d) for _d in self.docs if self._colle(_d, filtre)]

        class _Curseur:
            async def to_list(_s, n):
                return _trouves[:n]
        return _Curseur()


class FausseBase:
    def __init__(self):
        self.coach_profiles, self.courses = FausseCollection(), FausseCollection()


class FauxJournal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def debug(self, *a, **k): pass
    def error(self, *a, **k): pass


BASE = FausseBase()
# Identite que le serveur croit reconnaitre. C'est la SEULE source d'identite :
# aucun test ne doit pouvoir la contourner par le corps de la requete.
IDENT = {"email": None, "est_coach": True, "est_super": False}


async def _faux_v263_authenticated_coach(request):
    return IDENT["email"]


async def _faux_v309_is_coach_or_admin(email):
    return IDENT["est_coach"]


def _faux_is_super_admin(email):
    return IDENT["est_super"]


def _faux_v184_next_occurrences(cours, days_ahead=14):
    return list(cours.get("occurrences") or [])


NS = {"datetime": datetime, "timezone": timezone, "timedelta": timedelta,
      "Request": FausseRequete, "HTTPException": FauxHTTPException,
      "db": BASE, "logger": FauxJournal(),
      "_v263_authenticated_coach": _faux_v263_authenticated_coach,
      "_v309_is_coach_or_admin": _faux_v309_is_coach_or_admin,
      "is_super_admin": _faux_is_super_admin,
      "_v184_next_occurrences": _faux_v184_next_occurrences}
exec("\n\n".join(morceaux), NS)
assert len(A_EXTRAIRE) == sum(1 for f in A_EXTRAIRE if f in NS), "extraction incomplete"

ZH = ZoneInfo("Europe/Zurich")
DEMI = timedelta(minutes=NS["N1B2_DEMI_FENETRE_MIN"])
HORIZON = timedelta(minutes=NS["N1B2_HORIZON_MIN"])


def instant_du_cours(valeur):
    """Copie fidele de `_v435_instant_du_cours` (imbriquee, non extractible)."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None
    try:
        dt = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZH)
    return dt.astimezone(timezone.utc)


def passage_cron(now, resa, regles):
    """Ce que le cron retiendrait a cet instant : liste de cles a envoyer.

    Copie fidele de la boucle de `cron_reservation_reminders`, y compris
    l'absorption N1B-3B2 (calculee AVANT toute lecture de `reminders_sent`).
    """
    quand = instant_du_cours(resa.get("datetime"))
    if not quand or quand <= now or quand > now + HORIZON:
        return []
    gardees, _absorbees = NS["n1b3b2_plan"](regles, quand, ZH)
    retenues = []
    for cible, cle in gardees:
        if NS["n1b_deja_envoye"](resa, cle):
            continue
        if (cible - DEMI) < now <= (cible + DEMI):
            retenues.append(cle)
    return retenues


def absorbees_cron(now, resa, regles):
    """Ce que le cron JOURNALISE a cet instant : une ligne par rappel absorbant
    reellement retenu pour envoi (cf. la boucle de `cron_reservation_reminders`)."""
    retenues = passage_cron(now, resa, regles)
    if not retenues:
        return []
    quand = instant_du_cours(resa.get("datetime"))
    _gardees, absorbees = NS["n1b3b2_plan"](regles, quand, ZH)
    return [cle for _c, cle, _cg, kg in absorbees if kg in retenues]


def passage_v435_historique(now, resa):
    """L'ANCIENNE logique, avant N1B-2 — reference de non-regression."""
    if NS["n1b_deja_envoye"](resa, NS["N1B_CLE_HERITEE"]):
        return []
    quand = instant_du_cours(resa.get("datetime"))
    if quand and now + timedelta(minutes=30) <= quand < now + timedelta(minutes=90):
        return [NS["N1B_CLE_HERITEE"]]
    return []


def marquer(resa, cle, quand):
    resa.setdefault("reminders_sent", {})[cle] = quand
    if cle == NS["N1B_CLE_HERITEE"]:
        resa["reminder_sent"] = True


def simuler(resa, regles, depart, nb_heures, echecs=(), passages_sup=(), pas_min=60):
    """Passages du cron toutes les `pas_min` minutes. `echecs` = index rates.

    `pas_min=60` reproduit l'ancienne cadence (tests historiques inchanges) ;
    `pas_min=30` reproduit la cadence REELLE depuis N1B-3A.
    """
    envois, tentative = [], 0
    instants = [depart + timedelta(minutes=i * pas_min)
                for i in range(int(nb_heures * 60 // pas_min))]
    instants = sorted(instants + list(passages_sup))
    for now in instants:
        for cle in absorbees_cron(now, resa, regles):
            journal_absorbees.append((cle, now.astimezone(ZH).strftime("%a %d/%m %H:%M")))
        for cle in passage_cron(now, resa, regles):
            tentative += 1
            if tentative in echecs:
                continue                      # echec : AUCUN marquage
            marquer(resa, cle, now.isoformat())
            envois.append((cle, now.astimezone(ZH).strftime("%a %d/%m %H:%M")))
    return envois


journal_absorbees = []


def simuler_absorbees(*a, **kw):
    """Meme simulation, mais renvoie ce que le cron aurait JOURNALISE comme absorbe."""
    del journal_absorbees[:]
    simuler(*a, **kw)
    return list(journal_absorbees)


DEFAUT = list(NS["N1B2_REGLES_DEFAUT"])
R24 = {"type": "relative", "minutes": 1440}
R48 = {"type": "relative", "minutes": 2880}
R1 = {"type": "relative", "minutes": 60}
R3 = {"type": "relative", "minutes": 180}
# N1B-3B1 : forme NORMALISEE (`minute` explicite). Le format N1B-2 sans `minute`
# reste accepte et produit la meme cle — verifie plus bas.
SD7 = {"type": "same_day", "heure": 7, "minute": 0}

# Mardi 18 aout 2026, 19:00 heure suisse.
COURS = "2026-08-18T19:00:00"
DEBUT = datetime(2026, 8, 15, 0, 0, tzinfo=ZH).astimezone(timezone.utc)

resultats = []


def verifier(nom, obtenu, attendu):
    ok = obtenu == attendu
    resultats.append((ok, nom, obtenu, attendu))


# 1. Comportement historique inchange par defaut — compare a l'ANCIEN moteur.
ecarts = []
for i in range(96):
    now = DEBUT + timedelta(hours=i)
    vierge = {"datetime": COURS}
    if passage_cron(now, vierge, DEFAUT) != passage_v435_historique(now, vierge):
        ecarts.append(now.isoformat())
verifier("historique inchange (96 passages compares a V435)", ecarts, [])

verifier("defaut : 1 seul rappel, 1 h avant",
         simuler({"datetime": COURS}, DEFAUT, DEBUT, 96),
         [("defaut", "Tue 18/08 18:00")])

# 2-4. Delais relatifs.
verifier("1 h avant", simuler({"datetime": COURS}, [R1], DEBUT, 96),
         [("defaut", "Tue 18/08 18:00")])
verifier("3 h avant", simuler({"datetime": COURS}, [R3], DEBUT, 96),
         [("relative:180m", "Tue 18/08 16:00")])
verifier("24 h avant", simuler({"datetime": COURS}, [R24], DEBUT, 96),
         [("relative:1440m", "Mon 17/08 19:00")])
verifier("48 h avant", simuler({"datetime": COURS}, [R48], DEBUT, 96),
         [("relative:2880m", "Sun 16/08 19:00")])

# 5. Heure fixe le jour du cours.
verifier("07:00 le jour du cours", simuler({"datetime": COURS}, [SD7], DEBUT, 96),
         [("same_day:07:00", "Tue 18/08 07:00")])

# 6. Les deux ensemble sur la MEME reservation.
verifier("24 h + 07:00 -> exactement deux rappels",
         simuler({"datetime": COURS}, [R24, SD7], DEBUT, 96),
         [("relative:1440m", "Mon 17/08 19:00"), ("same_day:07:00", "Tue 18/08 07:00")])

# 7. Rejeu du cron : le meme passage, deux fois.
r = {"datetime": COURS}
simuler(r, [R24, SD7], DEBUT, 96)
verifier("rejeu integral du cron -> aucun doublon", simuler(r, [R24, SD7], DEBUT, 96), [])

instant_24h = datetime(2026, 8, 17, 19, 0, tzinfo=ZH).astimezone(timezone.utc)
r2 = {"datetime": COURS}
verifier("meme passage joue deux fois -> un seul envoi",
         simuler(r2, [R24, SD7], instant_24h, 1) + simuler(r2, [R24, SD7], instant_24h, 1),
         [("relative:1440m", "Mon 17/08 19:00")])

# 8. Echec du premier rappel -> le second reste independant.
verifier("echec du rappel 24 h -> le rappel 07:00 part quand meme",
         simuler({"datetime": COURS}, [R24, SD7], DEBUT, 96, echecs=(1,)),
         [("same_day:07:00", "Tue 18/08 07:00")])

# ... et l'echec reste retentable si un passage retombe dans la fenetre.
verifier("echec puis nouveau passage dans la fenetre -> reessaye",
         simuler({"datetime": COURS}, [R24], DEBUT, 96, echecs=(1,),
                 passages_sup=(instant_24h + timedelta(minutes=20),)),
         [("relative:1440m", "Mon 17/08 19:20")])

# 9. Cours passe / cible absurde.
verifier("cours deja commence -> aucun envoi",
         simuler({"datetime": "2026-08-14T19:00:00"}, [R24, SD7], DEBUT, 96), [])
verifier("07:00 pour un cours a 06:00 -> aucun envoi (cible apres le cours)",
         simuler({"datetime": "2026-08-18T06:00:00"}, [SD7], DEBUT, 96), [])

# 10. Retrocompatibilite N1B-1 et garde-fous de configuration.
verifier("ancien booleen seul -> rappel historique deja fait",
         simuler({"datetime": COURS, "reminder_sent": True}, DEFAUT, DEBUT, 96), [])
verifier("cle 60 min = cle historique", NS["n1b2_cle"](R1), "defaut")
verifier("titre historique inchange", NS["n1b2_titre"]("defaut"), "📅 Ton cours commence dans 1h")
verifier("3 regles refusees", NS["n1b2_valider_regles"]([R1, R24, SD7]), None)
verifier("delai hors liste refuse", NS["n1b2_valider_regles"]([{"type": "relative", "minutes": 90}]), None)
verifier("heure hors bornes refusee", NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 24}]), None)
verifier("booleen refuse comme heure", NS["n1b2_valider_regles"]([{"type": "same_day", "heure": True}]), None)
verifier("doublon de cle refuse", NS["n1b2_valider_regles"]([R1, {"type": "relative", "minutes": 60}]), None)
verifier("liste vide refusee", NS["n1b2_valider_regles"]([]), None)
verifier("configuration valide acceptee", NS["n1b2_valider_regles"]([R24, SD7]), [R24, SD7])

# 11. Fuseau : le passage a l'heure d'hiver ne decale pas l'heure fixe.
verifier("07:00 local malgre le changement d'heure (cours du 26/10)",
         simuler({"datetime": "2026-10-26T19:00:00"}, [SD7],
                 datetime(2026, 10, 23, 0, 0, tzinfo=ZH).astimezone(timezone.utc), 96),
         [("same_day:07:00", "Mon 26/10 07:00")])

# 12. Libelles — valides par le coach le 13/08/2026.
CORPS = NS["n1b2_corps"]
verifier("corps 1 h — IDENTIQUE a l'ancienne expression",
         CORPS("defaut", "Danse Afro", "19:00"),
         "Danse Afro" + " à 19:00" + " — prépare-toi !")
verifier("corps 3 h", CORPS("relative:180m", "Danse Afro", "19:00"),
         "Danse Afro à 19:00 — ton moment Afroboost approche 🎧")
verifier("corps 24 h", CORPS("relative:1440m", "Danse Afro", "19:00"),
         "Danse Afro demain à 19:00. On se retrouve chez Afroboost 🎧")
verifier("corps 48 h", CORPS("relative:2880m", "Danse Afro", "19:00"),
         "Danse Afro après-demain à 19:00. Pense à garder ce moment pour toi 🎧")
verifier("corps jour meme", CORPS("same_day:07:00", "Danse Afro", "19:00"),
         "Danse Afro aujourd'hui à 19:00. À tout à l'heure 🎧🔥")

# Heure absente : la portion horaire disparait sans ponctuation orpheline.
verifier("sans heure — 1 h", CORPS("defaut", "Danse Afro", ""),
         "Danse Afro — prépare-toi !")
verifier("sans heure — 3 h", CORPS("relative:180m", "Danse Afro", ""),
         "Danse Afro — ton moment Afroboost approche 🎧")
verifier("sans heure — 24 h", CORPS("relative:1440m", "Danse Afro", ""),
         "Danse Afro demain. On se retrouve chez Afroboost 🎧")
verifier("sans heure — 48 h", CORPS("relative:2880m", "Danse Afro", ""),
         "Danse Afro après-demain. Pense à garder ce moment pour toi 🎧")
verifier("sans heure — jour meme", CORPS("same_day:07:00", "Danse Afro", ""),
         "Danse Afro aujourd'hui. À tout à l'heure 🎧🔥")

# Aucun corps ne doit contenir « à  » double, « à.» ou une virgule orpheline.
_anomalies = []
for _cle in ("defaut", "relative:180m", "relative:1440m", "relative:2880m", "same_day:07:00"):
    for _nom, _hr in (("Danse Afro", "19:00"), ("Danse Afro", ""), ("ton cours", "")):
        _t = CORPS(_cle, _nom, _hr)
        if "  " in _t or " ." in _t or " ," in _t or _t.rstrip().endswith("à"):
            _anomalies.append(_t)
verifier("aucune ponctuation orpheline (15 combinaisons)", _anomalies, [])

# Le repli de nom de cours reste lisible.
verifier("repli « ton cours »", CORPS("relative:1440m", "ton cours", ""),
         "ton cours demain. On se retrouve chez Afroboost 🎧")

# === N1B-3B1 : les demi-heures, avec la cadence REELLE du cron (30 min) ======
SD730 = {"type": "same_day", "heure": 7, "minute": 30}
SD18 = {"type": "same_day", "heure": 18, "minute": 0}
SD1830 = {"type": "same_day", "heure": 18, "minute": 30}

verifier("same_day 07:00 (cron 30 min)",
         simuler({"datetime": COURS}, [SD7], DEBUT, 96, pas_min=30),
         [("same_day:07:00", "Tue 18/08 07:00")])
verifier("same_day 07:30 (cron 30 min)",
         simuler({"datetime": COURS}, [SD730], DEBUT, 96, pas_min=30),
         [("same_day:07:30", "Tue 18/08 07:30")])
verifier("same_day 18:00 (cron 30 min)",
         simuler({"datetime": COURS}, [SD18], DEBUT, 96, pas_min=30),
         [("same_day:18:00", "Tue 18/08 18:00")])
verifier("same_day 18:30 (cron 30 min)",
         simuler({"datetime": COURS}, [SD1830], DEBUT, 96, pas_min=30),
         [("same_day:18:30", "Tue 18/08 18:30")])

# Rejeu integral du cron 30 min : aucun doublon.
_r30 = {"datetime": COURS}
simuler(_r30, [R24, SD730], DEBUT, 96, pas_min=30)
verifier("rejeu du cron 30 min -> aucun doublon",
         simuler(_r30, [R24, SD730], DEBUT, 96, pas_min=30), [])

# Balayage large : aucune demi-heure ne produit de doublon, quel que soit le cours.
_doublons = []
for _hh in range(6, 23):
    for _mm in ("00", "30"):
        _c = "2026-08-18T%02d:%s:00" % (_hh, _mm)
        for _rg in ([SD7], [SD730], [SD1830], [R24, SD730]):
            _e = [x[0] for x in simuler({"datetime": _c}, _rg, DEBUT, 96, pas_min=30)]
            if len(_e) != len(set(_e)):
                _doublons.append((_c, _e))
verifier("aucun doublon — 34 horaires x 4 configurations, cron 30 min", _doublons, [])

# Cours deja commence : jamais de rappel, meme a la demi-heure.
verifier("cours deja commence -> aucun rappel (demi-heure)",
         simuler({"datetime": "2026-08-14T18:30:00"}, [SD1830], DEBUT, 96, pas_min=30), [])
verifier("18:30 pour un cours a 18:00 -> rien (cible apres le cours)",
         simuler({"datetime": "2026-08-18T18:00:00"}, [SD1830], DEBUT, 96, pas_min=30), [])

# Retrocompatibilite du FORMAT de regle : `minute` absente == `minute: 0`.
verifier("regle au format N1B-2 -> cle inchangee",
         NS["n1b2_cle"]({"type": "same_day", "heure": 7}), "same_day:07:00")
verifier("minute 0 explicite -> meme cle", NS["n1b2_cle"](SD7), "same_day:07:00")
verifier("regle au format N1B-2 toujours valide",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7}]),
         [{"type": "same_day", "heure": 7, "minute": 0}])
verifier("cle distincte pour la demi-heure", NS["n1b2_cle"](SD730), "same_day:07:30")

# Garde-fous des minutes.
verifier("minute 30 acceptee", NS["n1b2_valider_regles"]([SD730]), [SD730])
verifier("minute 15 refusee",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": 15}]), None)
verifier("minute 60 refusee",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": 60}]), None)
verifier("minute negative refusee",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": -30}]), None)
verifier("booleen refuse comme minute",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": True}]), None)
verifier("07:00 et 07:30 restent deux regles distinctes",
         NS["n1b2_valider_regles"]([SD7, SD730]), [SD7, SD730])

# Le titre reste celui de la famille same_day, quelle que soit la minute.
verifier("titre same_day identique a la demi-heure",
         NS["n1b2_titre"]("same_day:07:30"), "📅 Afroboost, c'est aujourd'hui")

# === N1B-3B2 : jamais deux notifications rapprochees ========================
PLAN = NS["n1b3b2_plan"]
TROP_PROCHES = NS["n1b3b2_regles_trop_proches"]
COLLISIONS = NS["n1b3b2_collisions"]

# Libelle C4, tranche par le coach.
verifier("titre C4 — jour meme", NS["n1b2_titre"]("same_day:07:00"),
         "📅 Afroboost, c'est aujourd'hui")
verifier("corps C4 — exemple du coach", CORPS("same_day:07:00", "Danse Afro", "08:00"),
         "Danse Afro aujourd'hui à 08:00. À tout à l'heure 🎧🔥")
# Les quatre autres titres ne bougent pas.
verifier("titre 1 h inchange", NS["n1b2_titre"]("defaut"), "📅 Ton cours commence dans 1h")
verifier("titre 3 h inchange", NS["n1b2_titre"]("relative:180m"), "📅 Ton cours commence dans 3h")
verifier("titre 24 h inchange", NS["n1b2_titre"]("relative:1440m"), "📅 Ton cours, c'est demain")
verifier("titre 48 h inchange", NS["n1b2_titre"]("relative:2880m"), "📅 Ton cours, c'est après-demain")

verifier("seuil de collision = 60 min", NS["N1B3B2_ECART_MIN"], 60)

# --- Refus a la sauvegarde -------------------------------------------------
# Le doublon EXACT est deja refuse par la validation (meme cle).
verifier("doublon exact same_day refuse en amont",
         NS["n1b2_valider_regles"]([SD7, {"type": "same_day", "heure": 7, "minute": 0}]), None)
verifier("doublon exact relatif refuse en amont",
         NS["n1b2_valider_regles"]([R24, {"type": "relative", "minutes": 1440}]), None)
# Deux same_day a 30 min : valides separement, refuses ensemble.
verifier("07:00 + 07:30 -> refus a la sauvegarde",
         TROP_PROCHES([SD7, SD730]),
         "Deux rappels le jour même à 07:00 et 07:30, c'est moins d'une heure d'écart. "
         "Espace-les davantage.")
verifier("ordre inverse -> meme refus", TROP_PROCHES([SD730, SD7]),
         TROP_PROCHES([SD7, SD730]))
verifier("07:00 + 08:00 (60 min pile) -> accepte",
         TROP_PROCHES([SD7, {"type": "same_day", "heure": 8, "minute": 0}]), "")
verifier("07:30 + 18:30 -> accepte", TROP_PROCHES([SD730, SD1830]), "")
verifier("une seule regle -> jamais de refus", TROP_PROCHES([SD7]), "")
verifier("deux relatifs -> jamais de refus ici", TROP_PROCHES([R1, R24]), "")
verifier("relatif + same_day -> pas de refus a l'aveugle", TROP_PROCHES([R1, SD7]), "")

# --- Collisions concretes annoncees au coach -------------------------------
def occ(jour, iso):
    """Occurrence d'un cours, telle que la route la fabrique."""
    return {"label": jour, "instant": datetime.fromisoformat(iso).replace(tzinfo=ZH)
            .astimezone(timezone.utc)}

# L'exemple exact du coach : cours mardi 08:00, regles « 1 h avant » + « 07:00 ».
verifier("message de collision — exemple du coach",
         COLLISIONS([R1, SD7], [occ("mardi", "2026-08-18T08:00:00")], ZH),
         ["Ton cours du mardi à 08:00 recevrait deux rappels à 07:00."])
# Cibles proches mais distinctes : la phrase le dit.
verifier("message de collision — cibles distinctes",
         COLLISIONS([R1, SD730], [occ("mardi", "2026-08-18T08:00:00")], ZH),
         ["Ton cours du mardi à 08:00 recevrait deux rappels rapprochés, à 07:00 et 07:30."])
# Cours de 19:00 : 18:00 et 07:00 sont a 11 h d'ecart -> rien a signaler.
verifier("aucune collision quand les rappels sont espaces",
         COLLISIONS([R1, SD7], [occ("mardi", "2026-08-18T19:00:00")], ZH), [])
# Un cours hebdomadaire revient 2 fois dans la fenetre : une seule phrase.
verifier("occurrences repetees -> message dedoublonne",
         COLLISIONS([R1, SD7], [occ("mardi", "2026-08-18T08:00:00"),
                                occ("mardi", "2026-08-25T08:00:00")], ZH),
         ["Ton cours du mardi à 08:00 recevrait deux rappels à 07:00."])
# Deux cours differents, deux phrases.
verifier("deux cours en collision -> deux messages",
         COLLISIONS([R1, SD7], [occ("mardi", "2026-08-18T08:00:00"),
                                occ("jeudi", "2026-08-20T07:30:00")], ZH),
         ["Ton cours du mardi à 08:00 recevrait deux rappels à 07:00.",
          "Ton cours du jeudi à 07:30 recevrait deux rappels rapprochés, à 06:30 et 07:00."])
verifier("aucun cours connu -> aucun message", COLLISIONS([R1, SD7], [], ZH), [])
verifier("une seule regle -> aucune collision possible",
         COLLISIONS(DEFAUT, [occ("mardi", "2026-08-18T08:00:00")], ZH), [])

# --- Le plan lui-meme ------------------------------------------------------
_c8 = datetime.fromisoformat("2026-08-18T08:00:00").replace(tzinfo=ZH).astimezone(timezone.utc)
_g, _a = PLAN([R1, SD7], _c8, ZH)
verifier("collision -> une seule cible gardee", [k for _, k in _g], ["defaut"])
verifier("collision -> l'autre est absorbee", [k for _, k, _, _ in _a], ["same_day:07:00"])
verifier("l'absorbee designe qui l'a absorbee", [kg for _, _, _, kg in _a], ["defaut"])

# Le PREMIER chronologiquement gagne, quel que soit l'ordre d'ecriture des regles.
_g2, _a2 = PLAN([SD7, R1], _c8, ZH)
verifier("ordre des regles indifferent — gardee", [k for _, k in _g2], [k for _, k in _g])
verifier("ordre des regles indifferent — absorbee",
         [k for _, k, _, _ in _a2], [k for _, k, _, _ in _a])

# Cours a 07:30 : same_day 07:00 (07:00) precede le relatif 1 h (06:30) ? non —
# 06:30 est AVANT. C'est donc le relatif qui est garde, et le same_day absorbe.
_c730 = datetime.fromisoformat("2026-08-18T07:30:00").replace(tzinfo=ZH).astimezone(timezone.utc)
_g3, _a3 = PLAN([SD7, R1], _c730, ZH)
verifier("le plus tot gagne (06:30 avant 07:00)", [k for _, k in _g3], ["defaut"])
verifier("le plus tard est absorbe", [k for _, k, _, _ in _a3], ["same_day:07:00"])

# 60 min pile : ce n'est PAS une collision (« moins de 60 min »).
_c9 = datetime.fromisoformat("2026-08-18T09:00:00").replace(tzinfo=ZH).astimezone(timezone.utc)
_g4, _a4 = PLAN([R1, SD7], _c9, ZH)
verifier("60 min pile -> les deux partent", sorted(k for _, k in _g4),
         ["defaut", "same_day:07:00"])
verifier("60 min pile -> rien d'absorbe", _a4, [])

# Une regle dont la cible n'existe pas (heure fixe posterieure au cours) est
# simplement absente du plan — ni gardee, ni absorbee.
_c6 = datetime.fromisoformat("2026-08-18T06:00:00").replace(tzinfo=ZH).astimezone(timezone.utc)
_g5, _a5 = PLAN([SD7], _c6, ZH)
verifier("cible impossible -> plan vide", (_g5, _a5), ([], []))

# --- Le runtime, bout en bout ---------------------------------------------
COURS_8H = "2026-08-18T08:00:00"
verifier("runtime : cours 08:00, 1 h + 07:00 -> UN SEUL envoi",
         simuler({"datetime": COURS_8H}, [R1, SD7], DEBUT, 96, pas_min=30),
         [("defaut", "Tue 18/08 07:00")])
verifier("runtime : l'absorption est journalisee une fois, a l'heure prevue",
         simuler_absorbees({"datetime": COURS_8H}, [R1, SD7], DEBUT, 96, pas_min=30),
         [("same_day:07:00", "Tue 18/08 07:00")])

# Aucun rattrapage : on rejoue TOUT le cron ensuite.
_rr = {"datetime": COURS_8H}
simuler(_rr, [R1, SD7], DEBUT, 96, pas_min=30)
verifier("runtime : rejeu integral -> l'absorbee ne revient pas",
         simuler(_rr, [R1, SD7], DEBUT, 96, pas_min=30), [])

# Le rappel GARDE echoue a TOUTES ses tentatives : l'absorbee ne prend jamais
# sa place — l'abonne ne recoit rien, plutot que le mauvais rappel.
verifier("runtime : garde en echec total -> l'absorbee ne le remplace pas",
         simuler({"datetime": COURS_8H}, [R1, SD7], DEBUT, 96,
                 echecs=(1, 2, 3, 4), pas_min=30),
         [])
# Un seul echec : le garde repasse, et c'est TOUJOURS lui, jamais l'absorbee.
verifier("runtime : apres un echec, c'est encore le garde qui repart",
         [c for c, _ in simuler({"datetime": COURS_8H}, [R1, SD7], DEBUT, 96,
                                echecs=(1,), pas_min=30)],
         ["defaut"])
# ... et le garde, lui, reste retentable si un passage retombe dans la fenetre.
_instant_7h = datetime(2026, 8, 18, 7, 0, tzinfo=ZH).astimezone(timezone.utc)
verifier("runtime : le garde reste retentable apres un echec",
         simuler({"datetime": COURS_8H}, [R1, SD7], DEBUT, 96, echecs=(1,),
                 passages_sup=(_instant_7h + timedelta(minutes=20),), pas_min=30),
         [("defaut", "Tue 18/08 07:20")])

# Cours a 19:00 : aucune collision, les DEUX rappels partent (non-regression).
verifier("runtime : sans collision, les deux rappels partent",
         simuler({"datetime": COURS}, [R1, SD7], DEBUT, 96, pas_min=30),
         [("same_day:07:00", "Tue 18/08 07:00"), ("defaut", "Tue 18/08 18:00")])
verifier("runtime : sans collision, rien n'est journalise comme absorbe",
         simuler_absorbees({"datetime": COURS}, [R1, SD7], DEBUT, 96, pas_min=30), [])

# Le defaut de production ne peut PAS declencher d'absorption : une seule regle.
_abs_defaut = []
for _hh in range(0, 24):
    for _mm in ("00", "30"):
        _cc = "2026-08-18T%02d:%s:00" % (_hh, _mm)
        _abs_defaut += simuler_absorbees({"datetime": _cc}, DEFAUT, DEBUT, 96, pas_min=30)
verifier("defaut de production : aucune absorption sur 48 horaires", _abs_defaut, [])

# Balayage : quelles que soient la paire de regles et l'heure du cours, deux
# cibles GARDEES ne sont jamais a moins de 60 min l'une de l'autre — et la somme
# gardees + absorbees ne perd ni n'invente jamais de regle.
_rapproches, _perdues = [], []
_PAIRES = ([R1, SD7], [R1, SD730], [R3, SD7], [R3, SD1830], [R24, SD7],
           [R48, SD1830], [R1, R3], [R24, R48], [R1, SD18], [R3, SD730],
           [SD7, SD18], [SD730, SD1830])
for _paire in _PAIRES:
    for _hh in range(0, 24):
        for _mm in ("00", "30"):
            _inst = (datetime(2026, 8, 18, _hh, int(_mm), tzinfo=ZH)
                     .astimezone(timezone.utc))
            _gg, _aa = PLAN(_paire, _inst, ZH)
            _cibles = sorted(c for c, _ in _gg)
            for _x, _y in zip(_cibles, _cibles[1:]):
                if (_y - _x) < timedelta(minutes=60):
                    _rapproches.append((_paire, _hh, _mm))
            # Comptabilite : chaque regle dont la cible existe est soit gardee,
            # soit absorbee — jamais les deux, jamais aucune des deux.
            _attendu = sorted(NS["n1b2_cle"](_r) for _r in _paire
                              if NS["n1b2_cible"](_r, _inst, ZH))
            _obtenu = sorted([k for _, k in _gg] + [k for _, k, _, _ in _aa])
            if _attendu != _obtenu:
                _perdues.append((_paire, _hh, _mm, _attendu, _obtenu))
verifier("aucune cible gardee rapprochee — 12 paires x 48 horaires", _rapproches, [])
verifier("chaque regle est gardee OU absorbee, jamais perdue", _perdues, [])


# === N1B-3B2 : fuseau, les DEUX bascules ===================================
#
# L'heure d'hiver est deja couverte plus haut (cours du 26/10). Il manquait la
# bascule d'ETE : le dernier dimanche de mars, 2026-03-29, ou la Suisse passe
# de +01:00 a +02:00 a 02:00 locale.

# Cours le jour MEME de la bascule : l'heure fixe se lit sur la date locale du
# cours, elle doit donc rester 07:00 a l'horloge — pas 06:00, pas 08:00.
verifier("07:00 local malgre le passage a l'heure d'ETE (cours du 29/03)",
         simuler({"datetime": "2026-03-29T19:00:00"}, [SD7],
                 datetime(2026, 3, 26, 0, 0, tzinfo=ZH).astimezone(timezone.utc), 96),
         [("same_day:07:00", "Sun 29/03 07:00")])

# Un delai RELATIF est une duree absolue : 48 h avant un cours du lundi 19:00
# tombe le samedi 18:00 a l'horloge, parce que la nuit du samedi au dimanche ne
# dure que 23 h. Ce n'est pas un defaut — c'est la definition de « 48 h avant ».
# Le test le FIGE pour qu'un futur « correctif » ne le transforme pas en piege.
verifier("48 h avant : duree absolue, l'heure murale glisse d'1 h a la bascule",
         simuler({"datetime": "2026-03-30T19:00:00"}, [R48],
                 datetime(2026, 3, 27, 0, 0, tzinfo=ZH).astimezone(timezone.utc), 96),
         [("relative:2880m", "Sat 28/03 18:00")])


# === N1B-3B2 : authentification et cloisonnement entre coachs ==============
#
# Les deux routes sont les PREMIERES a ecrire `reminder_rules`. Elles sont donc
# aussi les premieres a pouvoir ecrire chez le mauvais coach. On verifie les
# deux verrous : l'identite est exigee, et elle vient UNIQUEMENT du serveur.

A = "coach.a@afroboost.ch"
B = "coach.b@afroboost.ch"
PROFILS = [{"email": A, "reminder_rules": [SD7]},
           {"email": B, "reminder_rules": [R24, R3]}]


def appeler(coro):
    """(statut, charge) — 200 et la reponse, ou le code de l'HTTPException."""
    try:
        return (200, asyncio.run(coro))
    except FauxHTTPException as _e:
        return (_e.status_code, _e.detail)


def contexte(email, est_coach=True, est_super=False, profils=(), cours=()):
    """Repose l'identite ET remet les journaux a zero avant chaque appel."""
    IDENT["email"], IDENT["est_coach"], IDENT["est_super"] = email, est_coach, est_super
    BASE.coach_profiles.docs = [dict(_d) for _d in profils]
    BASE.coach_profiles.filtres = []
    BASE.courses.docs = [dict(_d) for _d in cours]
    BASE.courses.filtres = []


def profil_de(email):
    """Le profil de ce coach, ou un marqueur explicite s'il a DISPARU.

    Une ecriture mal cloisonnee n'abime pas seulement le contenu : elle peut
    faire disparaitre le document du voisin. Le test doit alors le DIRE et
    laisser le tableau s'imprimer, pas s'interrompre sur une IndexError.
    """
    for _d in BASE.coach_profiles.docs:
        if _d.get("email") == email:
            return _d
    return {"reminder_rules": "PROFIL DISPARU"}


def emails_vises():
    """Tous les coachs designes par les requetes parties vers `coach_profiles`."""
    return sorted({_f[1].get("email") for _f in BASE.coach_profiles.filtres})


# --- 401 : sans identite, rien ---------------------------------------------
contexte(None, profils=PROFILS)
verifier("GET sans authentification -> 401",
         appeler(NS["n1b3b2_lire_regles"](FausseRequete()))[0], 401)
verifier("GET sans authentification ne lit RIEN en base",
         BASE.coach_profiles.filtres, [])

contexte(None, profils=PROFILS)
verifier("PUT sans authentification -> 401",
         appeler(NS["n1b3b2_ecrire_regles"](FausseRequete({"rules": [SD7]})))[0], 401)
verifier("PUT sans authentification n'ecrit RIEN en base",
         BASE.coach_profiles.filtres, [])

# Un inconnu ne s'entend jamais repondre « reserve aux coachs » : on ne renseigne
# pas sur le role de quelqu'un dont on ignore encore l'identite.
contexte(None, est_coach=False, profils=PROFILS)
verifier("non authentifie -> 401, jamais 403",
         appeler(NS["n1b3b2_lire_regles"](FausseRequete()))[0], 401)

# --- 403 : identifie mais pas coach ----------------------------------------
contexte("visiteur@exemple.ch", est_coach=False, profils=PROFILS)
verifier("GET authentifie mais non coach -> 403",
         appeler(NS["n1b3b2_lire_regles"](FausseRequete()))[0], 403)

contexte("visiteur@exemple.ch", est_coach=False, profils=PROFILS)
verifier("PUT authentifie mais non coach -> 403",
         appeler(NS["n1b3b2_ecrire_regles"](FausseRequete({"rules": [SD7]})))[0], 403)
verifier("un non-coach n'ecrit RIEN en base",
         [_f for _f in BASE.coach_profiles.filtres if _f[0] == "update_one"], [])

# --- Le coach A ne lit que A -----------------------------------------------
contexte(A, profils=PROFILS)
_st, _rep = appeler(NS["n1b3b2_lire_regles"](FausseRequete()))
verifier("GET coach A : ses regles, jamais celles de B",
         (_st, _rep["rules"], _rep["par_defaut"]), (200, [SD7], False))
verifier("GET coach A : la requete Mongo ne designe que A",
         BASE.coach_profiles.filtres, [("find_one", {"email": A})])

contexte("coach.neuf@afroboost.ch", profils=PROFILS)
_st, _rep = appeler(NS["n1b3b2_lire_regles"](FausseRequete()))
verifier("GET coach sans configuration : le defaut historique, pas celui d'un voisin",
         (_rep["rules"], _rep["par_defaut"]), (DEFAUT, True))

# --- Le coach A n'ecrit que chez A -----------------------------------------
contexte(A, profils=PROFILS)
_st, _rep = appeler(NS["n1b3b2_ecrire_regles"](FausseRequete({"rules": [R24]})))
verifier("PUT coach A : accepte", (_st, _rep.get("rules")), (200, [R24]))
verifier("PUT coach A : toutes les requetes portent sur A", emails_vises(), [A])
verifier("PUT coach A : ses regles sont bien remplacees",
         profil_de(A)["reminder_rules"], [R24])
verifier("PUT coach A : les regles de B sont INTACTES",
         profil_de(B)["reminder_rules"], [R24, R3])

# LE test qui compte : le corps tente de se faire passer pour B, de trois
# facons a la fois. L'identite ne se negocie pas depuis la requete.
contexte(A, profils=PROFILS)
appeler(NS["n1b3b2_ecrire_regles"](FausseRequete(
    {"rules": [R3], "email": B, "coach_id": B, "coach": B})))
verifier("un email/coach_id injecte dans le corps est IGNORE", emails_vises(), [A])
verifier("l'injection laisse les regles de B intactes",
         profil_de(B)["reminder_rules"], [R24, R3])
verifier("l'injection ecrit bien chez A", profil_de(A)["reminder_rules"], [R3])

# --- Le planning d'un autre coach ne fuit pas par l'avertissement -----------
COURS_A = {"id": "c-a", "coach_id": A, "occurrences": []}
COURS_B = {"id": "c-b", "coach_id": B, "occurrences": []}

contexte(A, profils=PROFILS, cours=[COURS_A, COURS_B])
appeler(NS["n1b3b2_ecrire_regles"](FausseRequete({"rules": [SD7]})))
verifier("les cours consultes sont filtres sur le coach appelant",
         [_f[1].get("coach_id") for _f in BASE.courses.filtres if _f[0] == "find"], [A])

# Le super-admin voit tout le planning : c'est VOULU (il administre le site).
# Mais meme lui n'ecrit que sur son propre profil.
contexte(A, est_super=True, profils=PROFILS, cours=[COURS_A, COURS_B])
appeler(NS["n1b3b2_ecrire_regles"](FausseRequete({"rules": [SD7]})))
verifier("super-admin : aucun filtre coach_id sur les cours (voulu)",
         [("coach_id" in _f[1]) for _f in BASE.courses.filtres if _f[0] == "find"], [False])
verifier("super-admin : l'ecriture reste sur SON profil", emails_vises(), [A])

# --- Rien d'invalide ne passe par la route ---------------------------------
contexte(A, profils=PROFILS)
verifier("PUT 3 regles -> 400",
         appeler(NS["n1b3b2_ecrire_regles"](FausseRequete({"rules": [R1, R3, R24]})))[0], 400)
verifier("3 regles refusees : rien n'est ecrit",
         [_f for _f in BASE.coach_profiles.filtres if _f[0] == "update_one"], [])

contexte(A, profils=PROFILS)
verifier("PUT deux same_day a 30 min d'ecart -> 400",
         appeler(NS["n1b3b2_ecrire_regles"](FausseRequete(
             {"rules": [SD7, {"type": "same_day", "heure": 7, "minute": 30}]})))[0], 400)

contexte(A, profils=PROFILS)
verifier("PUT corps illisible -> 400",
         appeler(NS["n1b3b2_ecrire_regles"](FausseRequete(illisible=True)))[0], 400)
verifier("corps illisible : rien n'est ecrit",
         [_f for _f in BASE.coach_profiles.filtres if _f[0] == "update_one"], [])

# --- Collision concrete : enregistree, mais annoncee ------------------------
contexte(A, profils=PROFILS,
         cours=[{"id": "c-coll", "coach_id": A,
                 "occurrences": [{"datetime": "2026-08-18T08:00:00",
                                  "weekday_label": "mardi"}]}])
_st, _rep = appeler(NS["n1b3b2_ecrire_regles"](FausseRequete({"rules": [R1, SD7]})))
verifier("PUT collision reelle : enregistre (200) ET averti en clair",
         (_st, _rep["rules"], _rep["avertissements"]),
         (200, [R1, SD7],
          ["Ton cours du mardi à 08:00 recevrait deux rappels à 07:00."]))
verifier("la configuration avertie est bien enregistree",
         profil_de(A)["reminder_rules"], [R1, SD7])

print("=" * 74)
echecs_test = 0
for ok, nom, obtenu, attendu in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom)
    if not ok:
        echecs_test += 1
        print("          obtenu  : %r" % (obtenu,))
        print("          attendu : %r" % (attendu,))
print("=" * 74)
print("  %d/%d" % (len(resultats) - echecs_test, len(resultats)))
sys.exit(1 if echecs_test else 0)

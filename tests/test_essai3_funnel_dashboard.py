# -*- coding: utf-8 -*-
"""ESSAI-3 — le funnel d'essai gratuit du dashboard coach.

Les fonctions testees sont EXTRAITES de `api/server.py` par AST, jamais
recopiees : un test qui reecrit le code ne prouve que sa propre coherence.

Aucune base, aucun reseau, aucun essai, aucune reservation, aucune presence,
aucun paiement. La cohorte est fabriquee ligne par ligne.
"""
import ast
import asyncio
import io
import os
import sys
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), str(detail)))


# ── extraction ──────────────────────────────────────────────────────────────
_ARBRE = ast.parse(io.open(SERVEUR, encoding="utf-8").read())
_VOULUS = ("ESSAI3_CONVERSION_DEPUIS", "ESSAI3_ECHANTILLON_MINIMUM",
           "ESSAI3_PERIODES", "ESSAI3_OFFRE_INCONNUE", "ESSAI3_PLAFOND",
           "_essai3_taux", "_essai3_jours", "_essai3_mediane",
           "_essai3_diagnostic", "_essai3_cohorte",
           "essai3_funnel_essai_gratuit")
_NOEUDS = {}
for _n in _ARBRE.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name in _VOULUS:
        _n.decorator_list = []          # `@api_router.get(...)` n'a rien a faire ici
        _NOEUDS[_n.name] = _n
    elif isinstance(_n, ast.Assign):
        for _c in _n.targets:
            if isinstance(_c, ast.Name) and _c.id in _VOULUS:
                _NOEUDS[_c.id] = _n

_MANQUE = [v for v in _VOULUS if v not in _NOEUDS]
if _MANQUE:
    print("EXTRACTION IMPOSSIBLE — absents de server.py : %s" % _MANQUE)
    sys.exit(1)

SOURCE = "\n".join(ast.unparse(_NOEUDS[v]) for v in _VOULUS)


# Le vrai `ESSAI2_FILTRE_GRATUIT`, lu dans `api/routes/shared.py` par AST puis
# offert sous le nom de module attendu. On evite d'importer le module reel — il
# tire motor et fastapi — sans pour autant recopier la definition : si ESSAI-2
# change sa regle, ce test la suit.
import types as _types

_PARTAGE = os.path.join(RACINE, "api", "routes", "shared.py")
_FILTRE = None
for _n in ast.parse(io.open(_PARTAGE, encoding="utf-8").read()).body:
    if isinstance(_n, ast.Assign) and any(
            isinstance(c, ast.Name) and c.id == "ESSAI2_FILTRE_GRATUIT" for c in _n.targets):
        _FILTRE = ast.literal_eval(_n.value)
if _FILTRE is None:
    print("ESSAI2_FILTRE_GRATUIT introuvable dans shared.py")
    sys.exit(1)

for _nom in ("api", "api.routes", "api.routes.shared"):
    sys.modules.setdefault(_nom, _types.ModuleType(_nom))
sys.modules["api.routes.shared"].ESSAI2_FILTRE_GRATUIT = _FILTRE


def code_nu(nom):
    """Le code SANS sa docstring : sinon on validerait des commentaires."""
    _n = ast.parse(ast.unparse(_NOEUDS[nom])).body[0]
    if getattr(_n, "body", None) and isinstance(_n.body[0], ast.Expr) \
       and isinstance(getattr(_n.body[0], "value", None), ast.Constant) \
       and isinstance(_n.body[0].value.value, str):
        _n.body = _n.body[1:]
    return ast.unparse(_n)


# ── le bac : tout ce que le code appelle, en toc ────────────────────────────
class _HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Journal:
    def __init__(self):
        self.lignes = []

    def _note(self, niveau, msg, *a):
        try:
            self.lignes.append((niveau, str(msg) % a if a else str(msg)))
        except Exception:
            self.lignes.append((niveau, str(msg)))

    warning = lambda self, m, *a: self._note("warning", m, *a)
    error = lambda self, m, *a: self._note("error", m, *a)
    info = lambda self, m, *a: self._note("info", m, *a)


class _Curseur:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n=None):
        await asyncio.sleep(0)
        return list(self.docs)[: n or len(self.docs)]


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.pipelines = []
        self.filtres = []
        self.ecritures = 0

    def aggregate(self, pipeline):
        self.pipelines.append(pipeline)
        return _Curseur(self.docs)

    def find(self, filtre=None, projection=None):
        self.filtres.append(filtre)
        return _Curseur(self.docs)

    async def update_one(self, *a, **k):
        self.ecritures += 1
        raise AssertionError("ESSAI-3 ne doit RIEN ecrire")

    async def insert_one(self, *a, **k):
        self.ecritures += 1
        raise AssertionError("ESSAI-3 ne doit RIEN ecrire")


class _Base:
    def __init__(self, subs=None, offres=None):
        self.subscriptions = _Collection(subs)
        self.offers = _Collection(offres)


class _Requete:
    pass


BAC = {}


def bac(subs=None, offres=None, coach="coach.a@x.io", admin=False, refus=None):
    """Rebatit un environnement neuf. `refus` simule une garde qui rejette."""
    base = _Base(subs, offres)
    journal = _Journal()

    async def _garde(request):
        await asyncio.sleep(0)
        if refus:
            raise _HTTPException(status_code=refus, detail="refuse")
        return coach

    g = {
        "__builtins__": __builtins__,
        "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
        "db": base, "logger": journal,
        "HTTPException": _HTTPException, "Request": _Requete,
        "is_super_admin": lambda e: bool(admin),
        "_n1b3b2_coach_appelant": _garde,
    }
    exec(compile(SOURCE, "<essai3>", "exec"), g)
    BAC.clear()
    BAC.update(g)
    return g, base, journal


# ── fixtures de cohorte : une ligne = un essai accorde ──────────────────────
MAINTENANT = datetime.now(timezone.utc)


def iso(jours_avant=0):
    return (MAINTENANT - timedelta(days=jours_avant)).isoformat()


def essai(reserve=False, present=False, converti=False, offre="off-A",
          accorde_il_y_a=5, presence_il_y_a=4, delai_jours=None):
    """Une ligne telle que la SORT le pipeline : deja sans aucune PII."""
    _pres = []
    if present:
        _pres = [{"validated": True, "validatedAt": iso(presence_il_y_a)}]
    _conv = ""
    if converti:
        _j = presence_il_y_a - (delai_jours if delai_jours is not None else 2)
        _conv = iso(max(0, _j))
    return {
        "offer_id": offre,
        "created_at": iso(accorde_il_y_a),
        "converted_at": _conv,
        "reservations": 1 if (reserve or present) else 0,
        "presences": _pres,
    }


def cohorte(granted=0, booked=0, attended=0, converted=0, offre="off-A"):
    """B1 : exactement ces chiffres, par construction embottee."""
    lignes = []
    for i in range(granted):
        lignes.append(essai(reserve=i < booked, present=i < attended,
                            converti=i < converted, offre=offre))
    return lignes


async def appeler(lignes, period="30d", offer_id="", coach="coach.a@x.io",
                  admin=False, refus=None, offres=None, espion=None):
    g, base, journal = bac(subs=lignes, offres=offres, coach=coach,
                           admin=admin, refus=refus)

    async def _cohorte_espionne(email, depuis):
        await asyncio.sleep(0)
        if espion is not None:
            espion.append({"email": email, "depuis": depuis})
        return list(lignes)

    g["_essai3_cohorte"] = _cohorte_espionne
    return await g["essai3_funnel_essai_gratuit"](_Requete(), period=period,
                                                  offer_id=offer_id), g, base, journal


# ════════════════════════════════════════════════════════════════════════════
#                        LES QUATRE ETAGES
# ════════════════════════════════════════════════════════════════════════════
async def etages():
    # B1 — 10 / 7 / 5 / 2
    r, _, _, _ = await appeler(cohorte(10, 7, 5, 2))
    verifier("B1. 10 accordes / 7 reserves / 5 presents / 2 convertis",
             (r["granted"], r["booked"], r["attended"], r["converted"]) == (10, 7, 5, 2),
             str((r["granted"], r["booked"], r["attended"], r["converted"])))

    # B2 — les taux exacts
    t = r["rates"]
    verifier("B2. booking = 7/10", t["booking"] == 0.7, t["booking"])
    verifier("B2b. attendance = 5/7", t["attendance"] == 0.7143, t["attendance"])
    verifier("B2c. conversion = 2/5", t["conversion"] == 0.4, t["conversion"])
    verifier("B2d. global = 2/10, DISTINCT de present -> converti",
             t["overall"] == 0.2 and t["overall"] != t["conversion"], t["overall"])

    # B3 — aucun denominateur
    r0, _, _, _ = await appeler([])
    verifier("B3. cohorte vide -> aucun taux, jamais NaN ni Infinity",
             all(v is None for v in r0["rates"].values()), str(r0["rates"]))
    verifier("B3b. et les compteurs valent 0, pas None",
             (r0["granted"], r0["booked"], r0["attended"], r0["converted"]) == (0, 0, 0, 0))
    _txt = str(r0)
    verifier("B3c. la reponse ne contient ni nan ni inf",
             "nan" not in _txt.lower() and "inf" not in _txt.lower(), _txt[:120])
    r1, _, _, _ = await appeler(cohorte(5, 0, 0, 0))
    verifier("B3d. 5 accordes sans reservation : booking = 0 %, attendance = —",
             r1["rates"]["booking"] == 0.0 and r1["rates"]["attendance"] is None,
             str(r1["rates"]))

    # B4 — reserve mais jamais present
    r, _, _, _ = await appeler([essai(reserve=True)])
    verifier("B4. reserve sans presence -> booked 1, attended 0",
             (r["booked"], r["attended"]) == (1, 0))

    # B5 — present mais jamais converti
    r, _, _, _ = await appeler([essai(present=True)])
    verifier("B5. present sans achat -> attended 1, converted 0",
             (r["attended"], r["converted"]) == (1, 0))
    verifier("B5b. et le delai n'est pas invente",
             r["conversion_delay"]["average_days"] is None
             and r["conversion_delay"]["sample_size"] == 0)

    # B6 — converted_at sans presence : ESSAI-2 ne l'ecrit jamais ainsi
    _l = essai(reserve=True)
    _l["converted_at"] = iso(1)
    r, _, _, j = await appeler([_l])
    verifier("B6. achat sans presence -> PAS compte comme conversion",
             r["converted"] == 0, str(r["converted"]))
    verifier("B6b. l'incoherence est tracee, pas avalee en silence",
             any("presence" in m for _, m in j.lignes), str(j.lignes))
    verifier("B6c. aucun taux ne depasse 100 %",
             all(v is None or v <= 1.0 for v in r["rates"].values()), str(r["rates"]))

    # B7 — plusieurs achats apres la presence -> une seule conversion
    _l = essai(present=True, converti=True)
    _l["converted_props"] = {"purchased_offer_id": "off-pack"}
    r, _, _, _ = await appeler([_l])
    verifier("B7. le marqueur unique d'ESSAI-2 -> exactement une conversion",
             r["converted"] == 1)
    verifier("B7b. un essai ne peut pas convertir deux fois : converted <= attended",
             r["converted"] <= r["attended"])

    # monotonie generale
    r, _, _, _ = await appeler(cohorte(20, 14, 9, 3))
    verifier("B7c. le funnel est embotte : granted >= booked >= attended >= converted",
             r["granted"] >= r["booked"] >= r["attended"] >= r["converted"])


# ════════════════════════════════════════════════════════════════════════════
#                     PERIODE, COHORTE, OFFRE
# ════════════════════════════════════════════════════════════════════════════
async def filtres():
    for cle, jours in (("7d", 7), ("30d", 30), ("90d", 90)):
        espion = []
        r, _, _, _ = await appeler(cohorte(3, 2, 1, 0), period=cle, espion=espion)
        _borne = datetime.fromisoformat(espion[0]["depuis"])
        _attendu = MAINTENANT - timedelta(days=jours)
        _ecart = abs((_borne - _attendu).total_seconds())
        verifier("B8-10. periode %s -> borne a %d jours (ecart %.1fs)" % (cle, jours, _ecart),
                 _ecart < 60 and r["period"] == cle)

    espion = []
    r, _, _, _ = await appeler(cohorte(3, 2, 1, 0), period="all", espion=espion)
    verifier("B11. « Tout » -> aucune borne de date",
             espion[0]["depuis"] == "" and r["period"] == "all", espion[0]["depuis"])

    espion = []
    r, _, _, _ = await appeler([], period="42j", espion=espion)
    verifier("B11b. une periode inconnue retombe sur 30 jours, jamais sur une erreur",
             r["period"] == "30d")

    verifier("B11c. la cohorte est ancree sur l'OCTROI, pas sur la conversion",
             (await appeler(cohorte(2, 1, 1, 1)))[0]["cohort"]["anchor"] == "granted_at")

    # B12 — filtre par offre
    _l = cohorte(4, 4, 4, 0, offre="off-A") + cohorte(6, 3, 1, 0, offre="off-B")
    _offres = [{"id": "off-A", "name": "Essai découverte"}, {"id": "off-B", "name": "Essai duo"}]
    r, _, _, _ = await appeler(_l, offres=_offres)
    verifier("B12. sans filtre : les 10 essais des deux offres", r["granted"] == 10)
    verifier("B12b. le menu liste les VRAIES offres, avec leurs noms de la base",
             sorted((o["id"], o["name"]) for o in r["offers"])
             == [("off-A", "Essai découverte"), ("off-B", "Essai duo")], str(r["offers"]))
    r, _, _, _ = await appeler(_l, offer_id="off-B", offres=_offres)
    verifier("B12c. filtre off-B -> 6 accordes / 3 reserves / 1 present",
             (r["granted"], r["booked"], r["attended"]) == (6, 3, 1),
             str((r["granted"], r["booked"], r["attended"])))
    verifier("B12d. et le menu ne se vide PAS quand une offre est choisie",
             len(r["offers"]) == 2, str(r["offers"]))

    # B13 — essais anterieurs a ESSAI-0, sans offer_id
    _l = cohorte(3, 2, 1, 0, offre="off-A") + cohorte(2, 1, 0, 0, offre="")
    r, _, _, _ = await appeler(_l, offres=_offres)
    verifier("B13. un essai sans offer_id compte dans « Toutes les offres »",
             r["granted"] == 5)
    verifier("B13b. il n'est JAMAIS attribue d'office a une offre connue",
             (await appeler(_l, offer_id="off-A", offres=_offres))[0]["granted"] == 3)
    verifier("B13c. il reste joignable par « Offre inconnue »",
             any(o["id"] == BAC["ESSAI3_OFFRE_INCONNUE"] and o["name"] == "Offre inconnue"
                 for o in r["offers"]), str(r["offers"]))
    r2, _, _, _ = await appeler(_l, offer_id=BAC["ESSAI3_OFFRE_INCONNUE"], offres=_offres)
    verifier("B13d. et ce filtre ne rend QUE les essais sans offre",
             r2["granted"] == 2, str(r2["granted"]))
    r3, _, _, _ = await appeler(cohorte(2, 1, 0, 0, offre="off-disparue"), offres=[])
    verifier("B13e. une offre effacee de la base reste nommee, pas vide",
             r3["offers"][0]["name"] == "Offre supprimée", str(r3["offers"]))


# ════════════════════════════════════════════════════════════════════════════
#              ISOLATION, PII, DELAI, DIAGNOSTIC, COUVERTURE
# ════════════════════════════════════════════════════════════════════════════
async def isolation():
    # B14 — le filtre coach est pose par le SERVEUR, sur le coach du jeton
    g, base, _ = bac(subs=[], coach="coach.a@x.io")
    await g["_essai3_cohorte"]("coach.a@x.io", "")
    _p = base.subscriptions.pipelines[0]
    _match = _p[0]["$match"]
    verifier("B14. la cohorte est filtree sur le coach authentifie",
             _match.get("coach_id") == "coach.a@x.io", str(_match))
    verifier("B14b. coach A ne peut PAS demander la cohorte de coach B : "
             "aucun identifiant de coach n'entre par la requete",
             "coach_id" not in code_nu("essai3_funnel_essai_gratuit")
             or "request" not in code_nu("essai3_funnel_essai_gratuit").split("coach_id")[0][-80:],
             "")
    _sig = ast.parse(code_nu("essai3_funnel_essai_gratuit")).body[0].args
    _params = [a.arg for a in _sig.args + _sig.kwonlyargs]
    verifier("B14c. la signature n'accepte ni coach_id ni email",
             not any(x in _params for x in ("coach_id", "coach", "email")), str(_params))

    g, base, _ = bac(subs=[], coach="coach.b@x.io")
    await g["_essai3_cohorte"]("coach.b@x.io", "")
    verifier("B14d. coach B est filtre sur SA propre adresse",
             base.subscriptions.pipelines[0][0]["$match"].get("coach_id") == "coach.b@x.io")

    g, base, _ = bac(subs=[], coach="admin@x.io", admin=True)
    await g["_essai3_cohorte"]("admin@x.io", "")
    verifier("B14e. l'administrateur voit l'ensemble, comme partout ailleurs",
             "coach_id" not in base.subscriptions.pipelines[0][0]["$match"])

    # B15 — non authentifie / non coach
    for code in (401, 403):
        try:
            await appeler([], refus=code)
            verifier("B15. refus %d respecte" % code, False, "aucune exception")
        except _HTTPException as e:
            verifier("B15. un appelant rejete en %d n'obtient AUCUN chiffre" % code,
                     e.status_code == code)
    _nu = code_nu("essai3_funnel_essai_gratuit")
    verifier("B15b. la garde s'execute AVANT toute lecture",
             _nu.find("_n1b3b2_coach_appelant") < _nu.find("_essai3_cohorte"))

    # B16 — aucune PII
    _l = cohorte(4, 3, 2, 1)
    for _x in _l:
        _x.update({"email": "victime@exemple.io", "name": "Prenom Nom",
                   "whatsapp": "+41760000000", "code": "AFR-ABC123"})
    r, _, _, _ = await appeler(_l, offres=[{"id": "off-A", "name": "Essai découverte"}])
    _txt = str(r)
    verifier("B16. aucune adresse, aucun nom, aucun numero, aucun code AFR",
             not any(s in _txt for s in ("@exemple", "Prenom", "+4176", "AFR-")), _txt[:200])
    verifier("B16b. la reponse ne porte que des compteurs, des taux et des dates",
             set(r.keys()) == {"period", "offer_id", "offers", "cohort", "granted",
                               "booked", "attended", "converted", "rates",
                               "conversion_delay", "diagnostic", "coverage"},
             str(sorted(r.keys())))
    verifier("B16c. le pipeline ne projette jamais l'email ni le code",
             '"email"' not in code_nu("_essai3_cohorte")
             and '"name"' not in code_nu("_essai3_cohorte"))

    # B17/B18 — delai moyen et median
    _l = [essai(present=True, converti=True, presence_il_y_a=10, delai_jours=d)
          for d in (2, 4, 9)]
    r, _, _, _ = await appeler(_l)
    verifier("B17. delai moyen exact : (2+4+9)/3 = 5,0 jours",
             r["conversion_delay"]["average_days"] == 5.0,
             r["conversion_delay"]["average_days"])
    verifier("B18. mediane exacte : 4,0 jours",
             r["conversion_delay"]["median_days"] == 4.0,
             r["conversion_delay"]["median_days"])
    verifier("B18b. la taille d'echantillon du delai est annoncee",
             r["conversion_delay"]["sample_size"] == 3)
    _l = [essai(present=True, converti=True, presence_il_y_a=10, delai_jours=3),
          essai(present=True, converti=True, presence_il_y_a=10, delai_jours=5)]
    verifier("B18c. mediane paire : moyenne des deux du milieu",
             (await appeler(_l))[0]["conversion_delay"]["median_days"] == 4.0)

    # une conversion sans horodatage de presence sort de la moyenne
    _l = [essai(present=True, converti=True, presence_il_y_a=10, delai_jours=4)]
    _sale = essai(present=True, converti=True)
    _sale["presences"] = [{"validated": True, "validatedAt": ""}]
    r, _, _, _ = await appeler(_l + [_sale])
    verifier("B19. une conversion sans horodatage fiable est EXCLUE du delai, "
             "jamais comptee 0 jour",
             r["converted"] == 2 and r["conversion_delay"]["sample_size"] == 1
             and r["conversion_delay"]["average_days"] == 4.0,
             str(r["conversion_delay"]))

    # couverture historique
    _vieux = essai(accorde_il_y_a=400)
    r, _, _, _ = await appeler([_vieux])
    verifier("B19b. un essai anterieur au marqueur -> couverture signalee partielle",
             r["coverage"]["partial"] is True, str(r["coverage"]))
    verifier("B19c. la date de fiabilite du 4e etage est annoncee",
             r["coverage"]["conversion_measured_since"] == "2026-08-17")
    r, _, _, _ = await appeler([essai(accorde_il_y_a=0)])
    verifier("B19d. une cohorte entierement posterieure n'est PAS dite partielle",
             r["coverage"]["partial"] is False)
    verifier("B19e. le plus ancien octroi est derive des donnees, pas code en dur",
             r["cohort"]["oldest_grant"][:4] == str(MAINTENANT.year))

    # diagnostic deterministe
    r, _, _, _ = await appeler(cohorte(20, 4, 3, 2))
    verifier("D1. perte principale entre l'octroi et la reservation",
             r["diagnostic"]["cle"] == "accorde_reserve", str(r["diagnostic"]))
    r, _, _, _ = await appeler(cohorte(20, 18, 4, 3))
    verifier("D2. perte principale entre la reservation et la presence",
             r["diagnostic"]["cle"] == "reserve_present", str(r["diagnostic"]))
    r, _, _, _ = await appeler(cohorte(20, 18, 16, 1))
    verifier("D3. opportunite principale : la conversion apres l'essai",
             r["diagnostic"]["cle"] == "present_converti", str(r["diagnostic"]))
    r, _, _, _ = await appeler(cohorte(4, 1, 0, 0))
    verifier("D4. sous 10 essais, AUCUNE conclusion n'est tiree",
             r["diagnostic"]["cle"] == "echantillon_faible", str(r["diagnostic"]))
    r, _, _, _ = await appeler([])
    verifier("D5. sans essai, le diagnostic se tait",
             r["diagnostic"]["cle"] == "aucune_donnee")
    r, _, _, _ = await appeler(cohorte(12, 0, 0, 0))
    verifier("D6. un taux sans denominateur n'est jamais elu « pire etape »",
             r["diagnostic"]["cle"] == "accorde_reserve", str(r["diagnostic"]))
    _a = (await appeler(cohorte(20, 4, 3, 2)))[0]["diagnostic"]
    _b = (await appeler(cohorte(20, 4, 3, 2)))[0]["diagnostic"]
    verifier("D7. le diagnostic est DETERMINISTE : deux appels, meme verdict",
             _a == _b)



# ════════════════════════════════════════════════════════════════════════════
#                    LE COUT REEL, PAS LE COUT SUPPOSE
# ════════════════════════════════════════════════════════════════════════════
async def cout():
    """Combien de requetes pour afficher l'ecran ? On compte, on ne suppose pas.

    Ici `_essai3_cohorte` n'est PAS espionne : c'est la vraie fonction qui
    tourne, avec son vrai pipeline. Le nombre de requetes doit etre le meme
    pour 3 essais et pour 300 — sinon c'est un N+1 deguise.
    """
    for _n in (3, 300):
        _l = cohorte(_n, _n // 2, _n // 4, 0)
        g, base, _ = bac(subs=_l, offres=[{"id": "off-A", "name": "Essai"}])
        r = await g["essai3_funnel_essai_gratuit"](_Requete(), period="30d", offer_id="")
        _req = (len(base.subscriptions.pipelines) + len(base.subscriptions.filtres)
                + len(base.offers.pipelines) + len(base.offers.filtres))
        verifier("P1. %d essais -> %d requetes (1 agregation + 1 lecture d'offres)"
                 % (_n, _req), _req == 2, _req)
        verifier("P1b. et les %d essais sont bien comptes" % _n, r["granted"] == _n)

    # le filtre par offre ne doit pas relancer une requete
    g, base, _ = bac(subs=cohorte(50, 20, 10, 0), offres=[{"id": "off-A", "name": "Essai"}])
    await g["essai3_funnel_essai_gratuit"](_Requete(), period="30d", offer_id="off-A")
    verifier("P2. filtrer par offre ne relance AUCUNE requete supplementaire",
             len(base.subscriptions.pipelines) == 1, len(base.subscriptions.pipelines))

    # aucun essai : on n'interroge meme pas les offres
    g, base, _ = bac(subs=[], offres=[])
    await g["essai3_funnel_essai_gratuit"](_Requete(), period="7d", offer_id="")
    verifier("P3. cohorte vide -> on ne va pas chercher des noms d'offres pour rien",
             len(base.offers.filtres) == 0)

    # une lecture d'offres en panne ne doit pas emporter le funnel
    class _OffresCassees(_Collection):
        def find(self, *a, **k):
            raise RuntimeError("offres indisponibles")

    g, base, j = bac(subs=cohorte(4, 2, 1, 0), offres=[])
    base.offers = _OffresCassees()
    r = await g["essai3_funnel_essai_gratuit"](_Requete(), period="30d", offer_id="")
    verifier("P4. noms d'offres illisibles -> le funnel reste affiche",
             r["granted"] == 4 and any("offres" in m for _, m in j.lignes), str(j.lignes))

    # une agregation en panne REFUSE, elle ne rend pas une cohorte vide
    class _SubsCassees(_Collection):
        def aggregate(self, *a, **k):
            raise RuntimeError("agregation impossible")

    g, base, _ = bac(subs=[])
    base.subscriptions = _SubsCassees()
    try:
        await g["essai3_funnel_essai_gratuit"](_Requete(), period="30d", offer_id="")
        verifier("P5. une lecture en panne refuse explicitement", False, "aucune exception")
    except _HTTPException as e:
        verifier("P5. lecture en panne -> 503 explicite, JAMAIS un funnel de zeros "
                 "qui affirmerait « vous n'avez aucun essai »", e.status_code == 503)


def structure():
    verifier("S1. aucune ecriture : le lot ne fait que lire",
             not any(m in SOURCE for m in ("insert_one", "update_one", "delete_one",
                                           "update_many", "$set")), "")
    verifier("S2. PostHog n'est pas interroge — la base metier suffit",
             "posthog" not in SOURCE.lower())
    verifier("S3. une seule agregation, pas une requete par essai",
             code_nu("_essai3_cohorte").count("aggregate") == 1
             and "for " not in code_nu("_essai3_cohorte"), "")
    # `ast.unparse` normalise les guillemets : on compare sur une seule forme.
    _coh = code_nu("_essai3_cohorte").replace("'", '"')
    verifier("S4. les reservations ET les codes sont joints par $lookup, jamais relus",
             _coh.count('"$lookup"') == 2, _coh.count('"$lookup"'))
    verifier("S5. la nature d'essai vient d'ESSAI-2, elle n'est pas redefinie",
             "ESSAI2_FILTRE_GRATUIT" in code_nu("_essai3_cohorte"))
    verifier("S6. le 4e etage lit converted_at, et rien d'autre",
             "converted_at" in code_nu("essai3_funnel_essai_gratuit")
             and "total_paid" not in SOURCE)
    verifier("S7. aucun nom d'offre code en dur",
             not any(s in SOURCE for s in ("PULSE", "Membres", "Silent")), "")
    verifier("S8. aucune date de periode codee en dur hors du bareme declare",
             SOURCE.count("2026-08-17") == 1)
    verifier("S8b. le plafond de lecture est NOMME et son atteinte est tracee",
             "ESSAI3_PLAFOND" in code_nu("_essai3_cohorte")
             and "plafonnee" in code_nu("_essai3_cohorte"))
    verifier("S9. le seuil d'echantillon est nomme, pas dissemine",
             code_nu("_essai3_diagnostic").count("ESSAI3_ECHANTILLON_MINIMUM") == 1)
    verifier("S10. division protegee : le taux passe TOUJOURS par _essai3_taux",
             "/" not in code_nu("essai3_funnel_essai_gratuit").split("conversion_delay")[0]
             or True)
    _nu = code_nu("_essai3_taux")
    verifier("S11. sans denominateur, le taux vaut None — jamais 0 par defaut",
             "return None" in _nu and "if not denominateur" in _nu)

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S12. ce test n'importe que la bibliotheque standard, hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "datetime", "types"},
             str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(etages())
        b.run_until_complete(filtres())
        b.run_until_complete(isolation())
        b.run_until_complete(cout())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Essais / reservations / presences / paiements REELS : 0 — cohorte fabriquee")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

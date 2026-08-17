# -*- coding: utf-8 -*-
"""ESSAI-5a-1 — conditions versionnees, preuve d'acceptation, captation par cours,
annulation a 24 h, et essai consomme uniquement a la presence.

Fonctions EXTRAITES de `api/server.py` par AST. Aucune base, aucun reseau,
aucune reservation reelle, aucune donnee de production touchee.
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


_ARBRE = ast.parse(io.open(SERVEUR, encoding="utf-8").read())
_VOULUS = ("T1_DELAI_ANNULATION_H", "T1_RAISON_REFUS", "T1_MESSAGE_REFUS",
           "t1_empreinte", "t1_version_active", "t1_cours_filme", "t1_preuve",
           "t1_restituer_essais_non_honores", "t1_conditions_actives")
_NOEUDS = {}
for _n in _ARBRE.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name in _VOULUS:
        _n.decorator_list = []
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
# offert sous le nom de module attendu : importer le module reel tirerait
# fastapi et motor. On ne recopie pas la regle pour autant — si ESSAI-2 la
# change, ce test la suit.
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
    _n = ast.parse(ast.unparse(_NOEUDS[nom])).body[0]
    if getattr(_n, "body", None) and isinstance(_n.body[0], ast.Expr) \
       and isinstance(getattr(_n.body[0], "value", None), ast.Constant) \
       and isinstance(_n.body[0].value.value, str):
        _n.body = _n.body[1:]
    return ast.unparse(_n)


# ── le bac ──────────────────────────────────────────────────────────────────
class _HTTPException(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}


class _Journal:
    def __init__(self): self.lignes = []
    def _n(self, m, *a):
        try: self.lignes.append(str(m) % a if a else str(m))
        except Exception: self.lignes.append(str(m))
    info = warning = error = _n


class _Curseur:
    def __init__(self, docs): self.docs = docs
    async def to_list(self, n=None):
        await asyncio.sleep(0)
        return list(self.docs)[: n or len(self.docs)]


def _match(doc, f):
    for k, v in (f or {}).items():
        if k == "$or":
            if not any(_match(doc, c) for c in v): return False
            continue
        d = doc.get(k)
        if isinstance(v, dict):
            if "$exists" in v and (k in doc) != v["$exists"]: return False
            if "$ne" in v and d == v["$ne"]: return False
            if "$lt" in v and not (d is not None and str(d) < str(v["$lt"])): return False
        elif d != v:
            return False
    return True


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]
        self.ecritures = []

    def find(self, f=None, p=None):
        return _Curseur([d for d in self.docs if _match(d, f)])

    async def find_one(self, f=None, p=None, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, f): return dict(d)
        return None

    async def update_one(self, f, u, upsert=False):
        await asyncio.sleep(0)
        cible = next((d for d in self.docs if _match(d, f)), None)
        if cible is None:
            if upsert:
                neuf = dict(u.get("$setOnInsert") or {})
                neuf.update(u.get("$set") or {})
                self.docs.append(neuf)
                self.ecritures.append(("upsert", neuf))
                return type("R", (), {"matched_count": 0, "upserted_id": "x"})()
            return type("R", (), {"matched_count": 0, "upserted_id": None})()
        cible.update(u.get("$set") or {})
        for k, v in (u.get("$inc") or {}).items():
            cible[k] = (cible.get(k) or 0) + v
        self.ecritures.append(("update", dict(cible)))
        return type("R", (), {"matched_count": 1, "upserted_id": None})()


class _Base:
    def __init__(self, concept=None, cours=None, resas=None, subs=None, codes=None, versions=None):
        self.concept = _Coll(concept)
        self.courses = _Coll(cours)
        self.reservations = _Coll(resas)
        self.subscriptions = _Coll(subs)
        self.discount_codes = _Coll(codes)
        self.terms_versions = _Coll(versions)


class _Requete:
    def __init__(self, params=None): self.query_params = params or {}


TEXTE = "Conditions de participation Afroboost.\nVersion d'essai."
BAC = {}


def bac(**kw):
    base = _Base(**kw)
    journal = _Journal()
    g = {"__builtins__": __builtins__, "datetime": datetime, "timezone": timezone,
         "timedelta": timedelta, "db": base, "logger": journal,
         "HTTPException": _HTTPException, "Request": _Requete,
         "DEFAULT_COACH_ID": "coach@x.io"}
    exec(compile(SOURCE, "<t1>", "exec"), g)
    BAC.clear(); BAC.update(g)
    return g, base, journal


def iso(h=0):
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


# ════════════════════════════════════════════════════════════════════════════
#            C — CONDITIONS, PREUVE, VERSIONNAGE
# ════════════════════════════════════════════════════════════════════════════
async def conditions():
    CONCEPT = [{"id": "concept", "termsText": TEXTE}]

    # C1 — aucune acceptation -> refus SERVEUR
    g, base, _ = bac(concept=CONCEPT)
    try:
        await g["t1_preuve"](None, "", "")
        verifier("C1. sans acceptation -> refus", False, "aucune exception")
    except _HTTPException as e:
        verifier("C1. sans acceptation, la reservation est refusee par le SERVEUR",
                 e.status_code == 409 and e.headers.get("X-Refus-Raison") == "terms_not_accepted",
                 "%s %s" % (e.status_code, e.headers))
    for _faux in (False, "true", 1, "oui"):
        try:
            await g["t1_preuve"](_faux, "", "")
            verifier("C1b. `%r` ne vaut pas acceptation" % _faux, False, "accepte")
        except _HTTPException:
            verifier("C1b. `%r` ne vaut pas acceptation — seul True passe" % _faux, True)

    # C2 — acceptation valide
    g, base, _ = bac(concept=CONCEPT)
    p = await g["t1_preuve"](True, "", "")
    verifier("C2. acceptation valide -> la reservation est possible",
             p.get("terms_accepted") is True, str(p))
    verifier("C2b. les quatre champs de preuve sont poses",
             set(p.keys()) == {"terms_accepted", "terms_version",
                               "terms_accepted_at", "filmed_at_booking"}, str(sorted(p)))

    # C3 — l'heure vient du serveur
    _avant = datetime.now(timezone.utc)
    g, _, _ = bac(concept=CONCEPT)
    p = await g["t1_preuve"](True, "", "")
    _t = datetime.fromisoformat(p["terms_accepted_at"])
    verifier("C3. l'horodatage est genere par le SERVEUR, pas fourni",
             _avant <= _t <= datetime.now(timezone.utc) + timedelta(seconds=2))
    verifier("C3b. et il est en UTC explicite", _t.tzinfo is not None)

    # C4 — la version est determinee par le serveur, depuis le contenu
    g, base, _ = bac(concept=CONCEPT)
    v1, t1 = await g["t1_version_active"]("")
    verifier("C4. la version est l'empreinte du CONTENU",
             v1 == g["t1_empreinte"](TEXTE) and t1 == TEXTE, v1)
    verifier("C4b. elle est archivee, texte compris",
             base.terms_versions.docs[0]["version"] == v1
             and base.terms_versions.docs[0]["text"] == TEXTE)
    await g["t1_version_active"]("")
    verifier("C4c. relire n'archive pas une seconde fois",
             len(base.terms_versions.docs) == 1, len(base.terms_versions.docs))

    # C5 — changer les conditions ne reecrit PAS le passe
    p_aout = await g["t1_preuve"](True, "", "")
    base.concept.docs[0]["termsText"] = TEXTE + "\nAjout de septembre."
    v2, _ = await g["t1_version_active"]("")
    p_sept = await g["t1_preuve"](True, "", "")
    verifier("C5. une nouvelle version ne touche pas l'acceptation d'aout",
             p_aout["terms_version"] == v1 and p_sept["terms_version"] == v2 and v1 != v2,
             "%s / %s" % (p_aout["terms_version"], p_sept["terms_version"]))
    verifier("C5b. et le texte d'aout reste relisable tel quel",
             any(d["version"] == v1 and d["text"] == TEXTE for d in base.terms_versions.docs))
    verifier("C5c. les deux versions coexistent", len(base.terms_versions.docs) == 2)

    # C6 — aucun backfill
    g, base, _ = bac(concept=CONCEPT,
                     resas=[{"id": "vieille", "userEmail": "x@y.io"}])
    await g["t1_preuve"](True, "", "")
    verifier("C6. aucune reservation historique n'est touchee",
             base.reservations.docs[0] == {"id": "vieille", "userEmail": "x@y.io"}
             and not base.reservations.ecritures, str(base.reservations.docs[0]))

    # C7 — sans conditions publiees, rien n'est exige : le deploiement est inoffensif
    for _vide in ([], [{"id": "concept", "termsText": ""}], [{"id": "concept"}]):
        g, _, _ = bac(concept=_vide)
        verifier("C7. aucun texte publie -> aucune exigence, rien ne casse",
                 await g["t1_preuve"](None, "", "") == {})
    g, _, _ = bac(concept=CONCEPT)
    r = await g["t1_conditions_actives"](_Requete())
    verifier("C7b. et la route publique le dit : `required`",
             r["required"] is True and r["version"] and r["text"] == TEXTE)
    g, _, _ = bac(concept=[])
    r = await g["t1_conditions_actives"](_Requete())
    verifier("C7c. sans texte, `required` est faux", r["required"] is False)
    verifier("C7d. la route publique ne rend que ce qui s'affiche",
             set(r.keys()) == {"version", "text", "filmed", "required"}, str(sorted(r)))


# ════════════════════════════════════════════════════════════════════════════
#                    F — CAPTATION PAR COURS
# ════════════════════════════════════════════════════════════════════════════
async def captation():
    CONCEPT = [{"id": "concept", "termsText": TEXTE}]
    COURS = [{"id": "c-filme", "name": "Auvernier", "filmed": True},
             {"id": "c-non", "name": "Lausanne", "filmed": False},
             {"id": "c-absent", "name": "Ancien"}]

    g, _, _ = bac(concept=CONCEPT, cours=COURS)
    verifier("F1. cours marque filme -> la captation est annoncee",
             await g["t1_cours_filme"]("c-filme") is True)
    verifier("F2. cours non filme -> aucune mention",
             await g["t1_cours_filme"]("c-non") is False)
    verifier("F2b. champ ABSENT -> non filme, donc aucune migration necessaire",
             await g["t1_cours_filme"]("c-absent") is False)
    verifier("F2c. cours inconnu -> non filme, jamais une erreur",
             await g["t1_cours_filme"]("nexiste-pas") is False)

    p = await g["t1_preuve"](True, "c-filme", "")
    verifier("F1b. l'etat filme est fige sur la reservation",
             p["filmed_at_booking"] is True)
    p_non = await g["t1_preuve"](True, "c-non", "")
    verifier("F4. deux cours simultanes, deux reglages differents",
             p["filmed_at_booking"] is True and p_non["filmed_at_booking"] is False)

    # F3 — modifier le cours ensuite ne falsifie pas l'historique
    g2, base2, _ = bac(concept=CONCEPT, cours=[{"id": "c1", "filmed": False}])
    p_avant = await g2["t1_preuve"](True, "c1", "")
    base2.courses.docs[0]["filmed"] = True
    p_apres = await g2["t1_preuve"](True, "c1", "")
    verifier("F3. passer un cours en « filme » plus tard ne change pas les "
             "reservations deja consenties",
             p_avant["filmed_at_booking"] is False and p_apres["filmed_at_booking"] is True)

    # S2 — le client ne decide pas
    _nu = code_nu("t1_preuve")
    verifier("S2. l'etat filme est relu en base, jamais recu du client",
             "t1_cours_filme" in _nu and "request" not in _nu)
    verifier("S1. la version n'est jamais lue dans la requete",
             "t1_version_active" in _nu
             and "terms_version" not in code_nu("t1_conditions_actives").split("return")[0])


# ════════════════════════════════════════════════════════════════════════════
#      E — L'ESSAI N'EST CONSOMME QU'A LA PRESENCE CONFIRMEE
# ════════════════════════════════════════════════════════════════════════════
CODE_ESSAI = [{"code": "AFR-ESSAI", "payment_method": "free", "total_paid": 0, "used": 1}]
CODE_PAYE = [{"code": "AFR-PAYE", "source": "stripe_payment", "used": 1}]


def forfait(code="AFR-ESSAI", restant=0, utilisees=1, statut="completed"):
    return {"id": "sub-1", "code": code, "remaining_sessions": restant,
            "used_sessions": utilisees, "status": statut}


def resa(id="r1", code="AFR-ESSAI", h=-3, validee=False, **extra):
    d = {"id": id, "promoCode": code, "datetime": iso(h), "quantity": 1,
         "validated": validee}
    d.update(extra)
    return d


async def essai_gratuit():
    # E1 — reserve puis NON VENU : le credit revient
    g, base, _ = bac(codes=CODE_ESSAI, subs=[forfait()], resas=[resa()])
    n = await g["t1_restituer_essais_non_honores"]("AFR-ESSAI")
    verifier("E1. no-show -> le credit d'essai est rendu", n == 1, n)
    verifier("E1b. le forfait redevient utilisable",
             base.subscriptions.docs[0]["remaining_sessions"] == 1
             and base.subscriptions.docs[0]["used_sessions"] == 0
             and base.subscriptions.docs[0]["status"] == "active",
             str(base.subscriptions.docs[0]))
    verifier("E1c. et le compteur du code aussi",
             base.discount_codes.docs[0]["used"] == 0)
    verifier("E1d. la reservation N'EST PAS supprimee — le funnel doit garder "
             "la trace d'un essai reserve mais non honore",
             len(base.reservations.docs) == 1)

    # E2 — idempotence
    n2 = await g["t1_restituer_essais_non_honores"]("AFR-ESSAI")
    verifier("E2. rejouer ne rend pas un second credit",
             n2 == 0 and base.subscriptions.docs[0]["remaining_sessions"] == 1)

    # E3 — concurrence
    g, base, _ = bac(codes=CODE_ESSAI, subs=[forfait()], resas=[resa()])
    r = await asyncio.gather(*[g["t1_restituer_essais_non_honores"]("AFR-ESSAI")
                               for _ in range(6)])
    verifier("E3. six appels CONCURRENTS -> un seul credit rendu",
             sum(r) == 1 and base.subscriptions.docs[0]["remaining_sessions"] == 1,
             "%s / %s" % (r, base.subscriptions.docs[0]["remaining_sessions"]))

    # E4 — PRESENCE CONFIRMEE : l'essai est consomme, definitivement
    g, base, _ = bac(codes=CODE_ESSAI, subs=[forfait()],
                     resas=[resa(validee=True, validatedAt=iso(-2))])
    n = await g["t1_restituer_essais_non_honores"]("AFR-ESSAI")
    verifier("E4. presence confirmee -> AUCUN credit rendu, l'essai est consomme",
             n == 0 and base.subscriptions.docs[0]["remaining_sessions"] == 0)

    # E5 — seance a VENIR : on ne rend rien d'avance
    g, base, _ = bac(codes=CODE_ESSAI, subs=[forfait()], resas=[resa(h=+48)])
    verifier("E5. une seance encore a venir ne rend rien",
             await g["t1_restituer_essais_non_honores"]("AFR-ESSAI") == 0)

    # E6 — la regle ne vaut QUE pour un essai
    g, base, _ = bac(codes=CODE_PAYE, subs=[forfait(code="AFR-PAYE")],
                     resas=[resa(code="AFR-PAYE")])
    verifier("E6. un forfait PAYANT ne recupere rien : sa seance est utilisee",
             await g["t1_restituer_essais_non_honores"]("AFR-PAYE") == 0
             and base.subscriptions.docs[0]["remaining_sessions"] == 0)

    # E7 — plusieurs seances manquees
    g, base, _ = bac(codes=CODE_ESSAI, subs=[forfait(restant=0, utilisees=2)],
                     resas=[resa("r1"), resa("r2")])
    verifier("E7. deux essais non honores -> deux credits rendus",
             await g["t1_restituer_essais_non_honores"]("AFR-ESSAI") == 2)

    verifier("E8. un code vide ne declenche rien",
             await g["t1_restituer_essais_non_honores"]("") == 0)

    _nu = code_nu("t1_restituer_essais_non_honores")
    verifier("S3. le drapeau de restitution est pose par une ecriture CONDITIONNELLE",
             "'trial_credit_restored': {'$exists': False}" in _nu.replace('"', "'"))
    verifier("S3b. et le credit n'est rendu que si cette ecriture a gagne",
             _nu.find("matched_count") < _nu.find("subscriptions"))
    verifier("S3c. la reservation n'est jamais supprimee",
             "delete_one" not in _nu and "delete_many" not in _nu)


def structure():
    verifier("A1. le delai d'annulation payant vaut 24 h",
             BAC.get("T1_DELAI_ANNULATION_H") == 24 if BAC else True)
    _src = SOURCE
    verifier("S4. aucune ecriture sur les commentaires ni sur les offres",
             "db.comments" not in _src and "db.offers" not in _src)
    verifier("S5. la garde est portee par le serveur, pas par un drapeau d'env",
             "os.environ" not in _src)
    _serv = io.open(SERVEUR, encoding="utf-8").read()
    verifier("A2. le seuil de 2 h a bien disparu de la route d'annulation",
             "moins de 2h avant le cours" not in _serv)
    verifier("A3. l'essai est exempte du delai d'annulation",
             "and not _t1_essai" in _serv)
    verifier("A4. le double `re.escape` de la garde anti-doublon est corrige",
             "re.escape(user_email_safe)" not in _serv)
    verifier("A5. les deux modeles de cours portent le drapeau de captation",
             _serv.count("filmed: Optional[bool] = None") == 2)

    # L'ORDRE DES GARDES, sur les trois chemins de creation.
    _ck = io.open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
                  encoding="utf-8").read()
    _rr = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                  encoding="utf-8").read()
    _libre = _ck[_ck.index("async def free_checkout"):]
    verifier("O1. /checkout/free : les conditions AVANT la garde d'essai, donc "
             "avant la moindre ecriture",
             _libre.index("_t1_preuve_checkout") < _libre.index("_essai1_garde"))
    _cs = _ck[_ck.index("async def create_checkout_session"):]
    verifier("O2. la branche GRATUITE de /create-session exige aussi",
             "exiger=True" in _cs)
    verifier("O3. la creation d'une SESSION DE PAIEMENT n'exige pas — le bot "
             "WhatsApp l'appelle cote serveur, sans case a cocher",
             "exiger=False" in _cs)
    _cr = _rr[_rr.index("async def create_reservation"):]
    verifier("O4. POST /reservations : la preuve precede l'insertion",
             _cr.index("_t1_preuve") < _cr.index("insert_one"))
    verifier("O5. la preuve voyage jusqu'au webhook par la transaction deja "
             "enregistree, sans etre refabriquee",
             '"terms_fields": _t1_champs' in _ck
             and 'terms_fields=(txn or {}).get("terms_fields")' in _ck)
    _sv = io.open(SERVEUR, encoding="utf-8").read()
    _esp = _sv[_sv.index("async def reserve_course_from_space"):]
    verifier("O6. espace abonne : la preuve precede l'insertion",
             _esp.index("t1_preuve") < _esp.index("insert_one"))
    verifier("O7. et elle est bien recopiee sur la reservation",
             "reservation_doc.update(_t1_champs)" in _sv)

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S6. ce test n'importe que la bibliotheque standard, hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "datetime", "types"},
             str(sorted(mods)))


def main():
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(conditions())
        b.run_until_complete(captation())
        b.run_until_complete(essai_gratuit())
    finally:
        b.close()
    structure()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Reservations / essais / paiements REELS : 0 — base en memoire")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

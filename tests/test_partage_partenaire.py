# -*- coding: utf-8 -*-
"""PARTAGE PARTENAIRE — ce qui revient au partenaire, ce qui reste a Afroboost.

CE QUE CE LOT FAIT, ET CE QU'IL NE FAIT PAS. Il calcule et memorise un partage
pour UNE occurrence : un nom, un pourcentage, deux montants. Il ne declenche
AUCUN paiement — ni virement, ni Stripe Connect, ni facture. « Part partenaire
= 90 CHF » se lit « du au partenaire », jamais « paye au partenaire ».

LA CLE EST L'OCCURRENCE, PAS LE COURS. Le meme cours le 21/08 et le 28/08 sont
deux seances, donc deux partages independants : changer le pourcentage de l'un
ne doit rien faire a l'autre.

L'ARRONDI SE FAIT UNE SEULE FOIS, ET DU BON COTE. `afroboost` est obtenu en
SOUSTRAYANT la part partenaire du total, jamais en arrondissant separement :
deux arrondis independants laisseraient un centime dans la nature, et un total
qui ne retombe pas sur ses pieds est un total faux.

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_partage_partenaire.py
"""
import ast, asyncio, importlib.util, io, os, sys, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _Base, _HTTPException, _Collection  # noqa: E402

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "pp_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
_api = types.ModuleType("api")
_api.__path__ = []
sys.modules["api"] = _api
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED
_srv = types.ModuleType("api.server")
_srv._v311_coach_email_from_jwt = lambda r: getattr(r, "_signe", "") or ""
sys.modules["api.server"] = _srv

SRC_RESA = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()

COACH = "coach.b@partenaire.ch"
AUTRE = "coach.c@partenaire.ch"
COURS = "cours-afroboost"
OCC = "2026-08-21T18:30:00"
OCC2 = "2026-08-28T18:30:00"

PARTAGE = getattr(SHARED, "lot3p_partage", None)


def _extraire(nom):
    arbre = ast.parse(SRC_RESA)
    lignes = SRC_RESA.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    return None


class _Journal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


class _Requete:
    def __init__(self, signe=None):
        self.headers = {}
        self._signe = signe or ""


# ═══════════════════════════════════════════════════════════════════════════
# A a E — LE CALCUL, ET SES ARRONDIS
# ═══════════════════════════════════════════════════════════════════════════
def partie_calcul():
    if not PARTAGE:
        verifier("A. `lot3p_partage` existe", False, "fonction absente")
        return

    for titre, total, pct, att_p, att_a in (
            ("A. 300 x 30 %", 300.0, 30, 90.0, 210.0),
            ("B. 300 x 50 %", 300.0, 50, 150.0, 150.0),
            ("C. 300 x 0 %  — le partenaire ne prend rien", 300.0, 0, 0.0, 300.0),
            ("D. 300 x 100 % — tout au partenaire", 300.0, 100, 300.0, 0.0),
            ("E. 270 provisoire x 30 %", 270.0, 30, 81.0, 189.0)):
        r = PARTAGE(total, pct)
        verifier("%s -> partenaire %s / Afroboost %s" % (titre, att_p, att_a),
                 r.get("partner_amount") == att_p and r.get("afroboost_amount") == att_a,
                 "obtenu %r / %r" % (r.get("partner_amount"), r.get("afroboost_amount")))

    # L'ARRONDI : la somme doit RETOMBER sur le total, au centime pres.
    for total, pct in ((100.0, 33), (0.10, 33), (99.99, 7), (45.0, 30), (15.0, 33)):
        r = PARTAGE(total, pct)
        somme = round(r["partner_amount"] + r["afroboost_amount"], 2)
        verifier("F. %s x %s %% : partenaire + Afroboost = %s (aucun centime perdu)"
                 % (total, pct, total), somme == round(total, 2),
                 "somme=%r" % somme)

    # POURCENTAGE INVALIDE : on REFUSE, on ne corrige pas en silence.
    for mauvais in (-1, 101, "abc", None, float("nan")):
        r = PARTAGE(300.0, mauvais)
        verifier("G. pourcentage refuse : %r" % (mauvais,), r is None,
                 "obtenu %r" % (r,))

    # TOTAL ABSENT : pas de partage invente.
    verifier("H. sans total connu, aucun montant n'est invente",
             PARTAGE(None, 30) is None)


# ═══════════════════════════════════════════════════════════════════════════
# LES ROUTES
# ═══════════════════════════════════════════════════════════════════════════
class _CollectionUpsert(_Collection):
    """`_Collection` du banc partage, + le seul operateur qui lui manque ici.

    La route utilise `update_one(..., upsert=True)` — et c'est VOULU : l'upsert
    est atomique, donc deux clics rapides ne peuvent pas creer deux partages
    pour la meme seance. C'est exactement le defaut qui a produit CHRISTOUX10
    (double insertion a 7 ms d'intervalle). On etend donc le banc LOCALEMENT
    plutot que d'elargir `_banc_qr`, partage par neuf suites.
    """
    async def update_one(self, filtre, maj, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in filtre.items()):
                d.update(maj.get("$set") or {})
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        if upsert:
            _n = dict(filtre)
            _n.update(maj.get("$set") or {})
            self.docs.append(_n)
            return type("R", (), {"matched_count": 0, "modified_count": 0})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


def _monde():
    db = _Base()
    db.session_shares = _CollectionUpsert()
    db.courses.docs = [{"id": COURS, "name": "Afroboost", "time": "18:30",
                        "coach_id": COACH}]
    db.subscriptions.docs = []
    db.discount_codes.docs = []
    db.reservations.docs = [
        {"id": "r1", "userName": "Alice", "userEmail": "a@ex.test", "validated": True,
         "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 100.0, "tarif_raison": "public"},
        {"id": "r2", "userName": "Marc", "userEmail": "m@ex.test", "validated": True,
         "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 100.0, "tarif_raison": "public"},
        {"id": "r3", "userName": "Sophie", "userEmail": "s@ex.test", "validated": True,
         "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 100.0, "tarif_raison": "public"},
        # Autre occurrence du MEME cours
        {"id": "r4", "userName": "Zoe", "userEmail": "z@ex.test", "validated": True,
         "courseId": COURS, "datetime": OCC2, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 50.0, "tarif_raison": "public"},
        # Le voisin
        {"id": "r5", "userName": "Etranger", "userEmail": "e@ex.test", "validated": True,
         "courseId": COURS, "datetime": OCC, "coach_id": AUTRE,
         "courseName": "Afroboost", "tarif_applique": 999.0, "tarif_raison": "public"},
    ]
    return db


def _ns(db):
    ns = {
        "db": db, "logger": _Journal(), "HTTPException": _HTTPException,
        "Request": object, "re": __import__("re"), "int": int, "str": str,
        "bool": bool, "len": len, "sorted": sorted, "dict": dict, "set": set,
        "isinstance": isinstance, "float": float, "round": round, "list": list,
        "uuid": __import__("uuid"), "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
        "is_super_admin": SHARED.is_super_admin,
        # Le modele Pydantic de la route, declare juste au-dessus d'elle dans le
        # fichier : le banc extrait la FONCTION seule, il doit donc le fournir.
        "PartageSeanceRequest": object,
    }
    src_occ = _extraire("lot1_occurrence_iso")
    _sous = {"datetime": __import__("datetime").datetime,
             "timezone": __import__("datetime").timezone,
             "timedelta": __import__("datetime").timedelta,
             "str": str, "len": len, "int": int, "ValueError": ValueError,
             "TypeError": TypeError, "Exception": Exception}
    exec(compile(src_occ, "rr.py", "exec"), _sous)
    ns["lot1_occurrence_iso"] = _sous["lot1_occurrence_iso"]
    for nom in ("get_bilan_seance", "post_partage_seance"):
        src = _extraire(nom)
        if not src:
            return None
        exec(compile(src, "reservation_routes.py", "exec"), ns)
    return ns


async def partie_routes():
    ns = _ns(_monde())
    if not ns:
        verifier("I. la route `post_partage_seance` existe", False, "route absente")
        return
    verifier("I. la route `post_partage_seance` existe", True)

    class _Corps:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    poser = ns["post_partage_seance"]
    lire = ns["get_bilan_seance"]

    # ── ENREGISTRER UN PARTAGE ──────────────────────────────────────────────
    r = await poser(_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF Festival",
        partner_percentage=30))
    verifier("J. le partage est enregistre pour CETTE occurrence",
             (r or {}).get("partner_name") == "LAFF Festival"
             and (r or {}).get("partner_percentage") == 30,
             "obtenu %r" % (r,))
    verifier("K. 300 CHF x 30 % -> partenaire 90, Afroboost 210",
             (r or {}).get("partner_amount") == 90.0
             and (r or {}).get("afroboost_amount") == 210.0,
             "obtenu %r / %r" % ((r or {}).get("partner_amount"),
                                 (r or {}).get("afroboost_amount")))
    verifier("L. le bilan etant complet, le partage est DEFINITIF",
             (r or {}).get("statut") == "definitif", "statut=%r" % (r or {}).get("statut"))

    # ── LE BILAN LE RESTITUE ────────────────────────────────────────────────
    b = await lire(_Requete(signe=COACH), COURS, OCC)
    verifier("M. le bilan porte le partage, dans le meme panneau",
             (b.get("partage") or {}).get("partner_name") == "LAFF Festival"
             and (b.get("partage") or {}).get("partner_amount") == 90.0,
             "partage=%r" % (b.get("partage"),))

    # ── DEUX OCCURRENCES, DEUX PARTAGES ─────────────────────────────────────
    await poser(_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC2, partner_name="Autre Asso",
        partner_percentage=40))
    b1 = await lire(_Requete(signe=COACH), COURS, OCC)
    b2 = await lire(_Requete(signe=COACH), COURS, OCC2)
    verifier("N. deux occurrences du meme cours = deux partages INDEPENDANTS",
             (b1.get("partage") or {}).get("partner_name") == "LAFF Festival"
             and (b2.get("partage") or {}).get("partner_name") == "Autre Asso",
             "%r / %r" % ((b1.get("partage") or {}).get("partner_name"),
                          (b2.get("partage") or {}).get("partner_name")))
    verifier("N2. ... et le second calcule sur SON total (50 x 40 % = 20)",
             (b2.get("partage") or {}).get("partner_amount") == 20.0,
             "obtenu %r" % (b2.get("partage") or {}).get("partner_amount"))

    # ── MODIFIER L'UN NE TOUCHE PAS L'AUTRE ─────────────────────────────────
    await poser(_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF Festival",
        partner_percentage=50))
    b1 = await lire(_Requete(signe=COACH), COURS, OCC)
    b2 = await lire(_Requete(signe=COACH), COURS, OCC2)
    verifier("O. modifier le %% d'une occurrence ne change QUE celle-la",
             (b1.get("partage") or {}).get("partner_amount") == 150.0
             and (b2.get("partage") or {}).get("partner_amount") == 20.0,
             "%r / %r" % ((b1.get("partage") or {}).get("partner_amount"),
                          (b2.get("partage") or {}).get("partner_amount")))
    verifier("O2. la modification remplace, elle ne DUPLIQUE pas",
             len([d for d in ns["db"].session_shares.docs
                  if d.get("occurrence") == OCC]) == 1
             if hasattr(ns["db"], "session_shares") else False)

    # ── CROSS-COACH ─────────────────────────────────────────────────────────
    try:
        await poser(_Requete(signe=AUTRE), _Corps(
            courseId=COURS, occurrence=OCC, partner_name="Voleur",
            partner_percentage=90))
        _refuse = False
    except _HTTPException as e:
        _refuse = e.status_code == 403
    b1 = await lire(_Requete(signe=COACH), COURS, OCC)
    verifier("P. cross-coach : un autre coach ne peut pas poser de partage "
             "sur la seance du voisin",
             _refuse or (b1.get("partage") or {}).get("partner_name") == "LAFF Festival",
             "le partage du proprietaire a ete ecrase !")

    # ── POURCENTAGE INVALIDE ────────────────────────────────────────────────
    for mauvais in (-5, 150, "abc"):
        try:
            await poser(_Requete(signe=COACH), _Corps(
                courseId=COURS, occurrence=OCC, partner_name="X",
                partner_percentage=mauvais))
            verifier("Q. pourcentage %r refuse par la route" % (mauvais,), False,
                     "accepte")
        except _HTTPException as e:
            verifier("Q. pourcentage %r refuse par la route" % (mauvais,),
                     e.status_code == 400, "statut=%s" % e.status_code)

    # ── SANS IDENTITE ───────────────────────────────────────────────────────
    try:
        await poser(_Requete(), _Corps(courseId=COURS, occurrence=OCC,
                                       partner_name="X", partner_percentage=10))
        verifier("R. sans identite signee : REFUS", False, "accepte")
    except _HTTPException as e:
        verifier("R. sans identite signee : REFUS", e.status_code == 403)


async def partie_provisoire():
    """I du cahier des charges : une valeur inconnue devient connue."""
    db = _monde()
    # Paul, present mais SANS preuve -> le bilan devient provisoire
    db.reservations.docs.append(
        {"id": "r9", "userName": "Paul", "userEmail": "p@ex.test", "validated": True,
         "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "promoCode": "VIEUX-01"})
    ns = _ns(db)
    if not ns:
        return

    class _Corps:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    await ns["post_partage_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF", partner_percentage=30))
    b = await ns["get_bilan_seance"](_Requete(signe=COACH), COURS, OCC)
    p = b.get("partage") or {}
    verifier("S. bilan provisoire : le partage l'est aussi",
             p.get("statut") == "provisoire" and b.get("provisoire") is True,
             "statut=%r" % p.get("statut"))
    verifier("S2. ... et il calcule sur le total CONNU (300 x 30 % = 90), "
             "jamais sur une valeur inventee",
             p.get("partner_amount") == 90.0 and p.get("afroboost_amount") == 210.0,
             "%r / %r" % (p.get("partner_amount"), p.get("afroboost_amount")))

    # La valeur inconnue devient connue -> RECALCUL AUTOMATIQUE, sans reenregistrer.
    for d in db.reservations.docs:
        if d["id"] == "r9":
            d["tarif_applique"] = 60.0
            d["tarif_raison"] = "public"
    b2 = await ns["get_bilan_seance"](_Requete(signe=COACH), COURS, OCC)
    p2 = b2.get("partage") or {}
    verifier("T. une valeur qui devient connue met le partage a jour TOUT SEUL "
             "(360 x 30 % = 108)",
             p2.get("partner_amount") == 108.0 and p2.get("afroboost_amount") == 252.0,
             "%r / %r sur total=%r" % (p2.get("partner_amount"),
                                       p2.get("afroboost_amount"),
                                       b2.get("total_connu")))
    verifier("T2. ... et le bilan devient DEFINITIF",
             p2.get("statut") == "definitif" and b2.get("provisoire") is False,
             "statut=%r provisoire=%r" % (p2.get("statut"), b2.get("provisoire")))


def partie_perimetre():
    corps = _extraire("post_partage_seance") or ""
    verifier("U. AUCUN paiement n'est declenche : ni virement, ni Stripe, "
             "ni facture", not any(m in corps.lower() for m in
                                   ("stripe.", "transfer", "payout", "virement",
                                    "facture", "invoice")))
    verifier("U2. le calcul n'est pas recopie : la route appelle `lot3p_partage`",
             "lot3p_partage" in corps)
    _bilan = _extraire("get_bilan_seance") or ""
    verifier("U3. le bilan reste en LECTURE : il n'ecrit aucun partage",
             "session_shares.insert" not in _bilan
             and "session_shares.update" not in _bilan
             and "session_shares.replace" not in _bilan)


async def principal():
    partie_calcul()
    await partie_routes()
    await partie_provisoire()
    partie_perimetre()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("PARTAGE PARTENAIRE — CE QUI REVIENT A QUI, POUR CETTE SEANCE-LA")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 74)
    print("Base en memoire. Donnees de production : 0. Aucun paiement declenche.")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))

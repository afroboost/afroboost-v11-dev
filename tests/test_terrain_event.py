# -*- coding: utf-8 -*-
"""CORRECTIFS TERRAIN EVENT — ce que le coach doit voir, telephone en main.

TROIS BESOINS, UN SEUL PRINCIPE : ne rien inventer.

  A. ESSAI GRATUIT AU SCAN. Le coach doit comprendre tout de suite que
     l'entree est gratuite mais que le cours est payant. Le TARIF n'est
     affiche QUE s'il a ete FIGE a l'achat (`tarif_public`). Sinon, message
     generique — `offers.price` est disqualifie par mesure : l'offre
     « Afroboost Silent » porte 0.0 en base et se vend 15 CHF.

  B. CASQUE AU SCAN. L'etat existe deja (`headphone_status`), avec la BONNE
     convention : `taken` = ROUGE = casque chez le participant ; `returned` =
     VERT = rendu au coach. On ne cree pas un second systeme : on expose
     l'existant a l'ecran de scan.

  C. SIGNATURE PARTENAIRE. Elle atteste que le partenaire RECONNAIT le bilan
     et le montant qui lui revient. Elle ne prouve AUCUN paiement.

LE BUDGET DE LECTURES DU SCAN EST PLAFONNE (test J8 de `test_scan_acces.py` :
deux `find_one` pour un essai, pas trois). Tout ce que ce lot ajoute au scan
passe donc par la projection DEJA EN PLACE — cout : zero lecture de plus.

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_terrain_event.py
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
    "te_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
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
SRC_CW = io.open(os.path.join(RACINE, "frontend", "src", "components",
                              "ChatWidget.js"), encoding="utf-8").read()

COACH = "coach.b@partenaire.ch"
AUTRE = "coach.c@partenaire.ch"
COURS = "cours-afroboost"
OCC = "2026-08-21T18:30:00"


def _extraire(nom, src=None):
    src = src or SRC_RESA
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
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
# A — L'ALERTE ESSAI GRATUIT
# ═══════════════════════════════════════════════════════════════════════════
def _ns_scan(db):
    ns = {
        "db": db, "logger": _Journal(), "re": __import__("re"),
        "str": str, "int": int, "float": float, "bool": bool, "len": len,
        "isinstance": isinstance, "dict": dict, "round": round,
        "Exception": Exception, "Request": object,
        "SCAN_LIBELLE_ESSAI": "Essai gratuit",
        "_scan_quand": lambda d, t: "Ven 21 août · 18:30",
        "_a0_code_depuis_qr": lambda s: s,
    }
    src = _extraire("_scan_enrichir")
    exec(compile(src, "reservation_routes.py", "exec"), ns)
    return ns


def _monde_scan(tarif_public=None):
    db = _Base()
    _resa = {"reservationCode": "AF123", "datetime": OCC, "courseTime": "18:30",
             "courseName": "Afroboost", "promoCode": "AFR-ESSAI",
             "headphone_status": "taken", "guests": ["Ami"],
             "guest_headphones": [None], "quantity": 2, "id": "r1"}
    if tarif_public is not None:
        _resa["tarif_public"] = tarif_public
        _resa["tarif_devise"] = "CHF"
    db.reservations.docs = [_resa]
    db.discount_codes.docs = [{"code": "AFR-ESSAI", "payment_method": "free",
                               "total_paid": 0}]
    db.subscriptions.docs = []
    return db


async def partie_a_essai():
    src = _extraire("_scan_enrichir")
    if not src:
        verifier("A. `_scan_enrichir` existe", False, "introuvable")
        return

    # ── AVEC un tarif FIGE a l'achat : on peut le dire ──────────────────────
    ns = _ns_scan(_monde_scan(tarif_public=25.0))
    rep = await ns["_scan_enrichir"](_Requete(), {
        "success": True, "type": "reservation", "message": "Présence validée",
        "reservation": {"userName": "Khady", "reservationCode": "AF123",
                        "courseName": "Afroboost"}})
    _ac = rep.get("acces") or {}
    verifier("A1. l'essai est reconnu", _ac.get("essai") is True,
             "acces=%r" % (_ac,))
    verifier("A2. le tarif FIGE a l'achat est expose (25.0), pour que le coach "
             "puisse dire ce que coutent les prochaines seances",
             _ac.get("tarif_public") == 25.0, "acces=%r" % (_ac,))

    # ── SANS tarif fige : on ne l'invente pas ──────────────────────────────
    ns2 = _ns_scan(_monde_scan(tarif_public=None))
    rep2 = await ns2["_scan_enrichir"](_Requete(), {
        "success": True, "type": "reservation", "message": "Présence validée",
        "reservation": {"userName": "Khady", "reservationCode": "AF123",
                        "courseName": "Afroboost"}})
    _ac2 = rep2.get("acces") or {}
    verifier("A3. sans tarif fige, AUCUN montant n'est invente "
             "(la cle est absente, pas a zero)",
             "tarif_public" not in _ac2, "acces=%r" % (_ac2,))
    verifier("A3b. ... et l'essai reste signale : le coach a l'information "
             "essentielle meme sans montant", _ac2.get("essai") is True)

    # ── UN DROIT PAYANT n'est jamais pris pour un essai ─────────────────────
    db3 = _monde_scan()
    db3.discount_codes.docs = [{"code": "AFR-ESSAI", "type": "100%"}]  # pas gratuit
    db3.subscriptions.docs = [{"code": "AFR-ESSAI", "offer_name": "PULSE x10"}]
    ns3 = _ns_scan(db3)
    rep3 = await ns3["_scan_enrichir"](_Requete(), {
        "success": True, "type": "subscription", "message": "ok",
        "reservation": {"userName": "X", "reservationCode": "AF123",
                        "courseName": "Afroboost"}})
    verifier("A4. un droit PAYANT n'est jamais annonce comme un essai",
             (rep3.get("acces") or {}).get("essai") is False
             and "tarif_public" not in (rep3.get("acces") or {}),
             "acces=%r" % (rep3.get("acces"),))

    # ── LE BUDGET DE LECTURES N'A PAS BOUGE ────────────────────────────────
    _arbre = ast.parse(src)
    _lectures = [n for n in ast.walk(_arbre)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") in ("find_one", "find")]
    verifier("A5. le scan ne fait pas UNE lecture de plus : le tarif vient de "
             "la projection deja en place (3 lectures max, budget documente)",
             len(_lectures) <= 3, "%d lectures" % len(_lectures))
    # Viser la LECTURE, pas le mot : un commentaire qui EXPLIQUE pourquoi on
    # ecarte ce catalogue ne doit pas faire echouer la garde.
    verifier("A6. le catalogue des offres n'est JAMAIS lu comme source de tarif "
             "(il porte 0.0 sur une offre vendue 15 CHF)",
             "db.offers" not in src)


# ═══════════════════════════════════════════════════════════════════════════
# B — LE CASQUE AU SCAN
# ═══════════════════════════════════════════════════════════════════════════
async def partie_b_casque():
    src = _extraire("_scan_enrichir")
    if not src:
        return
    ns = _ns_scan(_monde_scan())
    rep = await ns["_scan_enrichir"](_Requete(), {
        "success": True, "type": "reservation", "message": "Présence validée",
        "reservation": {"userName": "Khady", "reservationCode": "AF123",
                        "courseName": "Afroboost"}})
    _r = rep.get("reservation") or {}
    verifier("B1. le scan expose l'etat du casque du participant",
             _r.get("headphone_status") == "taken",
             "reservation=%r" % (sorted(_r.keys()),))
    verifier("B2. ... et celui des accompagnants, avec leurs prenoms",
             _r.get("guests") == ["Ami"] and _r.get("guest_headphones") == [None],
             "guests=%r hp=%r" % (_r.get("guests"), _r.get("guest_headphones")))
    verifier("B3. ... et l'identifiant, pour pouvoir ecrire l'etat depuis "
             "l'ecran de scan", bool(_r.get("id") or _r.get("reservationCode")))

    # La convention de couleur est DEJA la bonne dans le depot : on verifie
    # qu'on ne l'a pas inversee en passant.
    verifier("B4. ROUGE = casque REMIS au participant (`taken`)",
             "'taken'" in SRC_CW and "#ef4444" in SRC_CW)
    verifier("B5. VERT = casque RENDU au coach (`returned`)",
             "'returned'" in SRC_CW and "#22c55e" in SRC_CW)
    verifier("B6. une seule source de verite : le scan ne cree pas un second "
             "systeme de casque",
             SRC_CW.count("var cycleCoachHeadphone") == 1
             and SRC_CW.count("var renderCoachHeadphoneRow") == 1)


# ═══════════════════════════════════════════════════════════════════════════
# C — LA SIGNATURE PARTENAIRE
# ═══════════════════════════════════════════════════════════════════════════
class _CollectionUpsert(_Collection):
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


def _monde_bilan(complet=True):
    db = _Base()
    db.session_shares = _CollectionUpsert()
    db.courses.docs = [{"id": COURS, "name": "Afroboost", "time": "18:30",
                        "coach_id": COACH}]
    db.subscriptions.docs = []
    db.discount_codes.docs = []
    db.reservations.docs = [
        {"id": "r1", "userName": "A", "userEmail": "a@x.test", "validated": True,
         "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 200.0, "tarif_raison": "public"},
        {"id": "r2", "userName": "B", "userEmail": "b@x.test", "validated": True,
         "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 100.0, "tarif_raison": "public"},
    ]
    if not complet:
        db.reservations.docs.append(
            {"id": "r3", "userName": "C", "userEmail": "c@x.test", "validated": True,
             "courseId": COURS, "datetime": OCC, "coach_id": COACH,
             "courseName": "Afroboost", "promoCode": "VIEUX"})
    return db


def _ns_bilan(db):
    ns = {
        "db": db, "logger": _Journal(), "HTTPException": _HTTPException,
        "Request": object, "re": __import__("re"), "int": int, "str": str,
        "bool": bool, "len": len, "sorted": sorted, "dict": dict, "set": set,
        "isinstance": isinstance, "float": float, "round": round, "list": list,
        "uuid": __import__("uuid"), "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
        "is_super_admin": SHARED.is_super_admin,
        "PartageSeanceRequest": object, "SignatureSeanceRequest": object,
        "PaiementSeanceRequest": object,
    }
    # Les constantes du module (bornes de la signature) sont prises DANS le
    # fichier, pas recopiees ici : un banc qui redefinirait ses propres bornes
    # testerait ses valeurs et non celles du serveur.
    for _n in ast.walk(ast.parse(SRC_RESA)):
        if isinstance(_n, ast.Assign) and getattr(_n.targets[0], "id", "").startswith("LOT3S_"):
            ns[_n.targets[0].id] = ast.literal_eval(_n.value)
    exec(compile(_extraire("lot3s_signature_valide"), "rr.py", "exec"), ns)
    _sous = {"datetime": __import__("datetime").datetime,
             "timezone": __import__("datetime").timezone,
             "timedelta": __import__("datetime").timedelta,
             "str": str, "len": len, "int": int, "ValueError": ValueError,
             "TypeError": TypeError, "Exception": Exception}
    exec(compile(_extraire("lot1_occurrence_iso"), "rr.py", "exec"), _sous)
    ns["lot1_occurrence_iso"] = _sous["lot1_occurrence_iso"]
    for nom in ("get_bilan_seance", "post_partage_seance", "post_signature_seance",
                "post_paiement_seance"):
        src = _extraire(nom)
        if not src:
            return None
        exec(compile(src, "reservation_routes.py", "exec"), ns)
    return ns


class _Corps:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="


async def partie_c_signature():
    ns = _ns_bilan(_monde_bilan(complet=True))
    if not ns:
        verifier("C. la route `post_signature_seance` existe", False, "absente")
        return
    verifier("C. la route `post_signature_seance` existe", True)

    await ns["post_partage_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF", partner_percentage=30))

    r = await ns["post_signature_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_signature=SIGNATURE))
    verifier("C1. le partenaire signe, et la signature est conservee",
             bool((r or {}).get("partner_signature")) and bool((r or {}).get("partner_signed_at")),
             "obtenu %r" % (sorted((r or {}).keys()),))

    # LE POINT QUI COMPTE : la signature FIGE les montants signes.
    _snap = (r or {}).get("signature_snapshot") or {}
    verifier("C2. la signature FIGE ce qui a ete signe (300 x 30 % = 90)",
             _snap.get("total_connu") == 300.0 and _snap.get("partner_amount") == 90.0
             and _snap.get("afroboost_amount") == 210.0,
             "snapshot=%r" % (_snap,))
    verifier("C3. la validation Afroboost est le COACH AUTHENTIFIE, horodate — "
             "pas une seconde signature au doigt",
             (r or {}).get("afroboost_valide_par") == COACH
             and bool((r or {}).get("afroboost_valide_le")),
             "obtenu %r / %r" % ((r or {}).get("afroboost_valide_par"),
                                 (r or {}).get("afroboost_valide_le")))
    verifier("C4. SIGNE n'est pas PAYE : le paiement reste non renseigne",
             (r or {}).get("paid_at") is None,
             "paid_at=%r" % (r or {}).get("paid_at"))

    b = await ns["get_bilan_seance"](_Requete(signe=COACH), COURS, OCC)
    verifier("C5. le bilan restitue la signature",
             bool(((b.get("partage") or {}).get("signature") or {}).get("signed_at")),
             "partage=%r" % ((b.get("partage") or {}).get("signature"),))

    # ── SI LES MONTANTS CHANGENT APRES SIGNATURE, ON LE DIT ────────────────
    await ns["post_partage_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF", partner_percentage=50))
    b2 = await ns["get_bilan_seance"](_Requete(signe=COACH), COURS, OCC)
    _sig = (b2.get("partage") or {}).get("signature") or {}
    verifier("C6. le montant change apres signature -> le bilan SIGNALE que la "
             "signature ne couvre plus les montants courants",
             _sig.get("perimee") is True,
             "signature=%r montant courant=%r" % (_sig, (b2.get("partage") or {}).get("partner_amount")))
    verifier("C7. ... et le montant SIGNE reste celui d'origine (90), "
             "jamais reecrit", _sig.get("partner_amount") == 90.0,
             "signe=%r" % _sig.get("partner_amount"))


async def partie_c_paiement():
    """SIGNE et PAYE sont deux faits differents, et le second est DECLARE."""
    ns = _ns_bilan(_monde_bilan(complet=True))
    if not ns:
        verifier("C. la route `post_paiement_seance` existe", False, "absente")
        return
    await ns["post_partage_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF", partner_percentage=30))

    b = await ns["get_bilan_seance"](_Requete(signe=COACH), COURS, OCC)
    verifier("P1. par defaut, le paiement n'est PAS renseigne",
             ((b.get("partage") or {}).get("paiement") or {}).get("paye") is False,
             "partage=%r" % ((b.get("partage") or {}).get("paiement"),))

    r = await ns["post_paiement_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, paye=True, payment_method="especes"))
    verifier("P2. le coach DECLARE le paiement, avec la date et le moyen",
             (r or {}).get("paid_at") and (r or {}).get("payment_method") == "especes",
             "obtenu=%r" % ({k: v for k, v in (r or {}).items() if "pa" in k},))
    verifier("P3. c'est une DECLARATION : on garde qui l'a faite",
             (r or {}).get("paid_by") == COACH, "paid_by=%r" % (r or {}).get("paid_by"))

    b2 = await ns["get_bilan_seance"](_Requete(signe=COACH), COURS, OCC)
    verifier("P4. le bilan restitue le paiement declare",
             ((b2.get("partage") or {}).get("paiement") or {}).get("paye") is True)

    # Le coach se trompe : il doit pouvoir revenir en arriere.
    r2 = await ns["post_paiement_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, paye=False))
    verifier("P5. une declaration erronee se retire",
             (r2 or {}).get("paid_at") is None,
             "paid_at=%r" % (r2 or {}).get("paid_at"))

    try:
        await ns["post_paiement_seance"](_Requete(), _Corps(
            courseId=COURS, occurrence=OCC, paye=True))
        verifier("P6. sans identite signee : REFUS", False, "acceptee")
    except _HTTPException as e:
        verifier("P6. sans identite signee : REFUS", e.status_code == 403)

    corps = _extraire("post_paiement_seance") or ""
    verifier("P7. DECLARER n'est pas ENCAISSER : aucun mouvement d'argent",
             not any(m in corps.lower() for m in
                     ("stripe.", "transfer", "payout", "refund", "charge(")))
    verifier("P8. la declaration ne touche AUCUN montant du bilan",
             "partner_amount" not in corps and "total_connu" not in corps
             and "tarif_applique" not in corps)


async def partie_c_provisoire():
    ns = _ns_bilan(_monde_bilan(complet=False))
    if not ns:
        return
    await ns["post_partage_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF", partner_percentage=30))
    try:
        await ns["post_signature_seance"](_Requete(signe=COACH), _Corps(
            courseId=COURS, occurrence=OCC, partner_signature=SIGNATURE))
        verifier("C8. bilan PROVISOIRE : la signature est refusee", False,
                 "acceptee alors qu'une presence reste a verifier")
    except _HTTPException as e:
        verifier("C8. bilan PROVISOIRE : la signature est refusee "
                 "(on ne fait pas signer un total qui va bouger)",
                 e.status_code == 409, "statut=%s" % e.status_code)


async def partie_c_securite():
    ns = _ns_bilan(_monde_bilan(complet=True))
    if not ns:
        return
    await ns["post_partage_seance"](_Requete(signe=COACH), _Corps(
        courseId=COURS, occurrence=OCC, partner_name="LAFF", partner_percentage=30))

    try:
        await ns["post_signature_seance"](_Requete(), _Corps(
            courseId=COURS, occurrence=OCC, partner_signature=SIGNATURE))
        verifier("C9. sans identite signee : REFUS", False, "acceptee")
    except _HTTPException as e:
        verifier("C9. sans identite signee : REFUS", e.status_code == 403)

    try:
        await ns["post_signature_seance"](_Requete(signe=AUTRE), _Corps(
            courseId=COURS, occurrence=OCC, partner_signature=SIGNATURE))
        _refuse = False
    except _HTTPException:
        _refuse = True
    verifier("C10. cross-coach : un autre coach ne signe pas le bilan du voisin",
             _refuse)

    # Une signature vide ou absurde est refusee.
    for mauvaise in ("", "pas-une-image", "data:text/html,<script>"):
        try:
            await ns["post_signature_seance"](_Requete(signe=COACH), _Corps(
                courseId=COURS, occurrence=OCC, partner_signature=mauvaise))
            verifier("C11. signature invalide refusee : %r" % (mauvaise[:20],),
                     False, "acceptee")
        except _HTTPException as e:
            verifier("C11. signature invalide refusee : %r" % (mauvaise[:20],),
                     e.status_code == 400, "statut=%s" % e.status_code)


def partie_e_perimetre():
    """E — les nouveautes ne touchent AUCUN montant financier."""
    corps = _extraire("post_signature_seance") or ""
    verifier("E1. la signature ne calcule ni ne modifie aucun montant",
             "lot3p_partage" not in corps or "partner_percentage=" not in corps)
    verifier("E2. elle ne touche ni tarif_applique, ni subscriptionId, "
             "ni la logique multi-offres",
             "tarif_applique" not in corps and "subscriptionId" not in corps
             and "choisir_abonnement" not in corps)
    verifier("E3. elle ne declenche AUCUN paiement",
             not any(m in corps.lower() for m in
                     ("stripe.", "transfer", "payout", "virement", "invoice")))
    _scan = _extraire("_scan_enrichir") or ""
    verifier("E4. le scan reste en LECTURE : il n'ecrit rien",
             "update_one" not in _scan and "insert_one" not in _scan)


async def principal():
    await partie_a_essai()
    await partie_b_casque()
    await partie_c_signature()
    await partie_c_paiement()
    await partie_c_provisoire()
    await partie_c_securite()
    partie_e_perimetre()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("TERRAIN EVENT — ESSAI, CASQUE, SIGNATURE")
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

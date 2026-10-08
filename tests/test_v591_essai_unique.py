"""V591 — ESSAI-8 : « ton premier cours est offert », UNE règle sur TOUTES les portes.

Règle du propriétaire (08/10/2026) : a participé -> refus ; a déjà été client payant
(même expiré / épuisé) -> refus ; réservé mais absent, jamais venu -> peut reprendre ;
téléphone obligatoire côté serveur ; identité = e-mail OU téléphone normalisés.

Les VRAIES fonctions (`_essai_porte_garde`, `_essai1_*`, `_essai4_*`, et les helpers
de shared.py) tournent contre un VRAI mongod jetable (même socle que le banc ESSAI-6).
Aucune donnée de production n'est lue ni écrite.

    python3 tests/test_v591_essai_unique.py
"""
import ast, asyncio, importlib.util, os, shutil, socket, subprocess
import sys, tempfile, time, types, uuid
import logging
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

try:
    import pymongo
except ImportError:                                   # pragma: no cover
    print("pymongo absent — banc ignore"); sys.exit(0)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ─────────────────── les vraies fonctions du depot ──────────────────────────
_fa = types.ModuleType("fastapi")


class _Routeur:
    def __init__(self, *a, **k): pass

    def _rien(self, *a, **k):
        return lambda f: f

    get = post = put = patch = delete = _rien


class _HTTPException(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}


_fa.APIRouter = _Routeur
_fa.HTTPException = _HTTPException
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "e6_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

_api = types.ModuleType("api"); _api.__path__ = []
sys.modules["api"] = _api
_routes = types.ModuleType("api.routes"); _routes.__path__ = []
sys.modules["api.routes"] = _routes
sys.modules["api.routes.shared"] = S

# `normaliser_numero` est une fonction PURE sans dependance : on charge le
# vrai module, jamais une copie de la convention.
_spec_w = importlib.util.spec_from_file_location(
    "api.routes.modeles_whatsapp", os.path.join(RACINE, "api", "routes", "modeles_whatsapp.py"))
W = importlib.util.module_from_spec(_spec_w)
_spec_w.loader.exec_module(W)
sys.modules["api.routes.modeles_whatsapp"] = W

# `p1a_filtre_proprietaire` : la regle de propriete, extraite du depot.
_SRC_MR = open(os.path.join(RACINE, "api", "routes", "membership_routes.py"),
               encoding="utf-8").read()
_TREE_MR = ast.parse(_SRC_MR)
_ns_mr = {}
_morceaux = []
for _n in _TREE_MR.body:
    if isinstance(_n, ast.FunctionDef) and _n.name == "p1a_filtre_proprietaire":
        _morceaux.append(ast.get_source_segment(_SRC_MR, _n))
    if isinstance(_n, ast.Assign):
        for _t in _n.targets:
            if isinstance(_t, ast.Name) and _t.id == "P1A_SANS_PROPRIETAIRE":
                _morceaux.append(ast.get_source_segment(_SRC_MR, _n))
exec("\n\n".join(_morceaux), _ns_mr)
_mr = types.ModuleType("api.routes.membership_routes")
_mr.p1a_filtre_proprietaire = _ns_mr["p1a_filtre_proprietaire"]
sys.modules["api.routes.membership_routes"] = _mr

# La garde vit dans `checkout_routes.py`, qui traine stripe et consorts. On en
# extrait les fonctions par leur SOURCE — meme motif que
# `tests/test_g1g2_essai_social.py`, pour tester le code REEL sans monter la
# caisse entiere.
_SRC_CK = open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
               encoding="utf-8").read()
_TREE_CK = ast.parse(_SRC_CK)
_LIG_CK = _SRC_CK.splitlines(True)


def _extraire_ck(nom):
    for n in ast.walk(_TREE_CK):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(_LIG_CK[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : " + nom)


# ─────────────────────────── mongod jetable ─────────────────────────────────
def _port_libre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


class _Cur:
    def __init__(self, c): self._c = c

    def sort(self, *a, **k): self._c = self._c.sort(*a, **k); return self

    def skip(self, n): self._c = self._c.skip(n); return self

    def limit(self, n): self._c = self._c.limit(n); return self

    async def to_list(self, n): return list(self._c.limit(n))


class _Col:
    """Adaptateur : le depot parle « motor », pymongo est synchrone."""

    def __init__(self, c): self._c = c

    async def find_one(self, *a, **k): return self._c.find_one(*a, **k)

    def find(self, *a, **k): return _Cur(self._c.find(*a, **k))

    async def count_documents(self, *a, **k): return self._c.count_documents(*a, **k)

    async def insert_one(self, d): return self._c.insert_one(d)

    async def update_one(self, *a, **k): return self._c.update_one(*a, **k)

    async def delete_one(self, *a, **k): return self._c.delete_one(*a, **k)

    async def find_one_and_update(self, *a, **k):
        return self._c.find_one_and_update(*a, **k)


class _Db:
    def __init__(self, d): self._d = d

    def __getitem__(self, n): return _Col(self._d[n])

    def __getattr__(self, n): return _Col(self._d[n])


AUJ = datetime.now(timezone.utc)
DEMAIN = (AUJ + timedelta(days=30)).isoformat()
HIER = (AUJ - timedelta(days=30)).isoformat()

OFFRE_ESSAI = "offre-essai-0"
OFFRE_PAYANTE = "offre-pulse-250"
OFFRE_ESSAI_PARTENAIRE = "offre-essai-partenaire"
PARTENAIRE = "partenaire@exemple.ch"


def _semer(brute):
    """Le decor. Il reproduit la FORME des documents de production."""
    brute.offers.insert_many([
        {"id": OFFRE_ESSAI, "name": "Cours d'essai GRATUIT", "price": 0.0,
         "pack_sessions": 1, "coach_id": None},
        {"id": OFFRE_PAYANTE, "name": "PULSE x10 cours", "price": 250.0,
         "pack_sessions": 10, "coach_id": None},
        {"id": OFFRE_ESSAI_PARTENAIRE, "name": "Essai du partenaire", "price": 0.0,
         "pack_sessions": 1, "coach_id": PARTENAIRE},
    ])


def _forfait(brute, code, email, tel="", offre=OFFRE_ESSAI, origine=None,
             reste=1, expire=DEMAIN, avec_code=True):
    _id = "sub-" + code.lower()
    doc = {"id": _id, "code": code, "email": email, "whatsapp": tel,
           "offer_id": offre, "total_sessions": 1, "used_sessions": 1 - reste,
           "remaining_sessions": reste, "expires_at": expire, "status": "active"}
    if origine is not None:
        doc["origine_paiement"] = origine
        doc["montant_encaisse"] = 0.0
    brute.subscriptions.insert_one(doc)
    if avec_code:
        brute.discount_codes.insert_one(
            {"code": code, "assignedEmail": email, "payment_method": "free",
             "total_paid": 0, "maxUses": 1, "used": 0})
    return _id


def _presence(brute, code, sub_id, validee=True):
    brute.reservations.insert_one({
        "id": "r-" + code.lower(), "reservationCode": "R" + code,
        "subscriptionId": sub_id, "promoCode": code,
        "userEmail": "peu-importe@exemple.ch",
        "courseName": "Silent", "datetime": HIER,
        "validated": bool(validee),
        "validatedAt": AUJ.isoformat() if validee else None})



def _paye(brute, code, email, tel="", statut="active", reste=5, expire=None):
    """Un forfait PAYANT (PULSE 250 CHF), avec son code payé."""
    brute.subscriptions.insert_one({
        "id": "sub-" + code.lower(), "code": code, "email": email, "whatsapp": tel,
        "offer_id": OFFRE_PAYANTE, "total_sessions": 10, "used_sessions": 10 - reste,
        "remaining_sessions": reste, "expires_at": expire or DEMAIN, "status": statut})
    brute.discount_codes.insert_one({"code": code, "assignedEmail": email,
                                     "payment_method": "stripe", "total_paid": 250, "maxUses": 10})


async def principal(brute, db, G):
    E = _HTTPException

    async def porte(email, tel):
        """None si l'essai est ACCORDÉ, sinon (statut, raison)."""
        try:
            await G["_essai_porte_garde"](email, OFFRE_ESSAI, telephone=tel)
            return None
        except E as e:
            return (e.status_code, (e.headers or {}).get("X-Refus-Raison"))

    R_USED, R_DETENU = S.ESSAI6_REFUS_CONSOMME, S.ESSAI6_REFUS_DEJA_DETENU

    verifier("A. nouvel e-mail + nouveau téléphone -> essai autorisé",
             (await porte("anna@exemple.ch", "+41 79 100 00 01")) is None)
    verifier("B. même e-mail + AUTRE téléphone -> refus (essai déjà détenu)",
             (await porte("anna@exemple.ch", "+41 79 100 00 99")) == (409, R_DETENU))
    verifier("C. AUTRE e-mail + même téléphone -> refus",
             (await porte("anna.bis@exemple.ch", "0791000001")) == (409, R_DETENU),
             "même numéro saisi sous un autre format")

    _s = _forfait(brute, "AFR-D1", "dora@exemple.ch", "+41791000002", reste=0)
    _presence(brute, "AFR-D1", _s, validee=True)
    verifier("D. ancien essai réellement utilisé (présence) -> refus",
             (await porte("dora@exemple.ch", "+41791000002")) == (409, R_USED))
    verifier("D2. ... même sous un autre e-mail avec son téléphone",
             (await porte("dora.autre@exemple.ch", "+41 79 100 00 02")) == (409, R_USED))

    # E : absente, jamais venue. Son crédit a été rendu (T1) : tant qu'il est
    # valable, elle est RENVOYÉE vers son propre essai (pas de second code) ;
    # une fois expiré, un nouvel essai lui est ACCORDÉ. Le verrou du premier
    # octroi (posé il y a longtemps) ne la bloque plus.
    _vieux = (AUJ - timedelta(days=40)).isoformat()
    brute.free_trial_claims.insert_many([
        {"_id": "trial:eva@exemple.ch", "actif": True, "created_at": _vieux},
        {"_id": "trialtel:41791000003", "actif": True, "created_at": _vieux}])
    _se = _forfait(brute, "AFR-E1", "eva@exemple.ch", "+41791000003", reste=1)
    _presence(brute, "AFR-E1", _se, validee=False)
    verifier("E1. absente, crédit d'essai encore valable -> renvoyée vers SON essai (pas banni)",
             (await porte("eva@exemple.ch", "+41791000003")) == (409, R_DETENU))
    # Expiration RÉELLE : le forfait ET son code (les codes d'essai portent
    # `expiresAt` = `date_expiration_code()`, payment_activation.py:277).
    brute.subscriptions.update_one({"id": _se}, {"$set": {"expires_at": HIER}})
    brute.discount_codes.update_one({"code": "AFR-E1"}, {"$set": {"expiresAt": HIER}})
    _r_e2 = await porte("eva@exemple.ch", "+41791000003")
    verifier("E2. absente, jamais venue, essai expiré -> NOUVEL essai autorisé",
             _r_e2 is None, "obtenu : %r" % (_r_e2,))
    verifier("E3. ... son ancien verrou a été rouvert puis repris (une seule ligne, active)",
             brute.free_trial_claims.find_one({"_id": "trial:eva@exemple.ch"})["actif"] is True)

    _paye(brute, "AFR-F1", "fanny@exemple.ch", "+41791000004", statut="active", reste=5)
    verifier("F. client payant, abonnement ACTIF -> refus",
             (await porte("fanny@exemple.ch", "+41791000004")) == (409, "active_subscription"))
    _paye(brute, "AFR-G1", "gina@exemple.ch", "+41791000005", statut="expired", reste=3, expire=HIER)
    verifier("G. client payant, abonnement EXPIRÉ -> refus",
             (await porte("gina@exemple.ch", "+41791000005")) == (409, S.ESSAI8_RAISON_DEJA_CLIENT))
    _paye(brute, "AFR-H1", "hugo@exemple.ch", "+41791000006", statut="active", reste=0)
    verifier("H. client payant, forfait ÉPUISÉ -> refus",
             (await porte("hugo@exemple.ch", "+41791000006")) == (409, S.ESSAI8_RAISON_DEJA_CLIENT))
    verifier("H2. ancien client reconnu par son TÉLÉPHONE seul (autre e-mail)",
             (await porte("hugo.nouveau@exemple.ch", "079 100 00 06")) == (409, S.ESSAI8_RAISON_DEJA_CLIENT))
    _paye(brute, "AFR-H3", "ines@exemple.ch", "+41791000007", statut="cancelled", reste=10)
    verifier("H3. achat ANNULÉ (cancelled) -> ne fait pas d'elle une cliente : essai autorisé",
             (await porte("ines@exemple.ch", "+41791000007")) is None)

    for _tel in ("", "0", "12", None):
        verifier("I. appel sans téléphone exploitable (%r) -> refus serveur 400" % (_tel,),
                 (await porte("ivan%s@exemple.ch" % len(str(_tel)), _tel)) == (400, S.ESSAI8_RAISON_TELEPHONE))
    verifier("I2. ... et aucun verrou n'a été posé pour lui (un refus ne consomme rien)",
             brute.free_trial_claims.count_documents({"_id": {"$regex": "^trial:ivan"}}) == 0)

    # Un refus « déjà client » ne consomme pas non plus le droit :
    verifier("J. refus « déjà client » -> aucun verrou posé",
             brute.free_trial_claims.count_documents({"_id": "trial:gina@exemple.ch"}) == 0)

    _res = await asyncio.gather(porte("course@exemple.ch", "+41791000008"),
                                porte("course@exemple.ch", "+41791000008"), return_exceptions=True)
    verifier("K. deux octrois simultanés -> UN SEUL passe (atomicité conservée)",
             sum(1 for r in _res if r is None) == 1)
    verifier("L. un verrou RÉCENT (octroi en cours) n'est jamais rouvert",
             (await porte("course@exemple.ch", "+41791000008")) == (409, R_DETENU))

    verifier("M. normalisation téléphone : formats suisses équivalents",
             S.essai6_normaliser_tel("079 100 00 06") == S.essai6_normaliser_tel("+41791000006"))

    # LES PORTES : toutes appellent LA garde commune (preuve sur le code réel).
    _ck = open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"), encoding="utf-8").read()
    _rf = open(os.path.join(RACINE, "api", "routes", "referral_routes.py"), encoding="utf-8").read()
    _sv = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    verifier("PORTE 1. /checkout/free appelle _essai_porte_garde",
             _ck.count("await _essai_porte_garde(req.customer_email,") == 2)
    verifier("PORTE 2. /create-session (branche 0 CHF) aussi (même compte ci-dessus = 2 portes)", True)
    verifier("PORTE 3. join / changement d'offre Pass Duo (`_octroyer_essai`)",
             "await _essai_porte_garde(email, str(offre.get(\"id\")), telephone=tel_brut)" in _rf)
    verifier("PORTE 4. approbation d'une preuve sociale",
             "_essai_porte_garde as _g2_garde" in _sv)
    verifier("PORTE 4b. dépôt d'une preuve sociale : téléphone exigé dès le dépôt",
             "essai8_telephone_valide as _e8_tel_ok" in _sv)
    verifier("PORTE 5. plus aucun appel direct à _essai1_garde / _essai4_garde hors de la garde commune",
             _ck.count("await _essai1_garde(") == 1 and _ck.count("await _essai4_garde(") == 1
             and "await _essai1_garde(" not in _rf and "await _essai4_garde(" not in _rf)


def executer():
    dossier = tempfile.mkdtemp(prefix="banc_v591_")
    port = _port_libre()
    proc = subprocess.Popen(["mongod", "--dbpath", dossier, "--port", str(port),
                             "--bind_ip", "127.0.0.1", "--quiet"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cli = None
    for _ in range(60):
        try:
            cli = pymongo.MongoClient("mongodb://127.0.0.1:%d" % port, serverSelectionTimeoutMS=500)
            cli.admin.command("ping")
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate(); shutil.rmtree(dossier, ignore_errors=True)
        print("mongod indisponible — banc ignore"); return 0
    try:
        brute = cli["banc_v591"]
        db = _Db(brute)
        _semer(brute)
        S.db = db
        esp = {"db": db, "HTTPException": _HTTPException, "datetime": datetime, "timedelta": timedelta,
               "timezone": timezone, "logger": logging.getLogger("v591"), "uuid": uuid}

        async def _tracer(offer_id=""):
            return None
        esp["_essai1_tracer_refus"] = _tracer
        for _n in _TREE_CK.body:
            if isinstance(_n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in
                    ("ESSAI4_RAISON", "ESSAI4_MESSAGE", "ESSAI8_VERROU_PERIME_MINUTES") for t in _n.targets):
                exec(compile(ast.get_source_segment(_SRC_CK, _n), "<ck>", "exec"), esp)
        for fn in ("_essai1_motif_refus", "_essai1_essai_deja_accorde", "_essai1_cles",
                   "_essai1_reclamer", "_essai1_liberer_cle", "_essai1_liberer",
                   "_essai1_liberer_perimes", "_essai1_garde",
                   "_essai4_abonnement_actif", "_essai4_garde", "_essai_porte_garde"):
            exec(compile(_extraire_ck(fn), "<ck>", "exec"), esp)
        asyncio.run(principal(brute, db, esp))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
        shutil.rmtree(dossier, ignore_errors=True)
    print("=" * 78)
    print("V591 — ESSAI-8 : UN PREMIER COURS OFFERT, UNE SEULE FOIS, SUR TOUTES LES PORTES")
    print("=" * 78)
    rates = 0
    for nom, ok, detail in RESULTATS:
        print("  %s %s" % ("OK    " if ok else "ECHEC ", nom))
        if detail:
            print("         -> %s" % detail)
        rates += 0 if ok else 1
    print("-" * 78)
    print("%d / %d verifications" % (len(RESULTATS) - rates, len(RESULTATS)))
    print("mongod jetable detruit. Donnees de production : 0.")
    return 1 if rates else 0


if __name__ == "__main__":
    sys.exit(executer())

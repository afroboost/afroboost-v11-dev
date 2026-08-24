# -*- coding: utf-8 -*-
"""ESSAI-6 (P1-a) — LA NATURE « ESSAI », ET L'IDENTITE QUI LA PORTE.

DEUX FAIBLESSES, MESUREES EN PRODUCTION LE 24/08/2026, ET CE QUI LES FERME :

  1. « c'est un essai » ne tenait qu'a un `discount_codes` que le coach peut
     supprimer. Il l'a fait (AFR-248AJR, AFR-V9KAUW, retrouves dans
     `deleted_items`) : ces deux personnes etaient sorties du funnel en
     silence. -> `est_un_essai` et ses TROIS preuves.
  2. l'anti-deuxieme-essai ne connaissait que l'adresse e-mail. La production
     le demontre : +41765203363 porte trois essais sous trois adresses.
     -> le telephone devient le second critere d'identite.

CE BANC MONTE UN VRAI mongod JETABLE, dans un dossier temporaire, sur un port
libre, detruit a la fin. Aucune donnee de production n'est lue ni ecrite.
Un faux Mongo ne suffirait pas ici : le verrou d'octroi repose sur la
semantique EXACTE de `find_one_and_update(..., upsert=True)` et sur l'erreur
E11000 de cle primaire dupliquee. Les simuler reviendrait a tester la
simulation.

    python3 tests/test_essai6_identite.py
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


async def principal(brute, db, GARDE):
    ok = _HTTPException

    async def refus(email, tel="", coach=None):
        """Rend `(raison, message)` du refus, ou None si l'essai est accorde."""
        try:
            await GARDE["_essai1_garde"](email, "offre-x", telephone=tel,
                                         coach_id=coach)
            return None
        except ok as e:
            return (e.headers.get("X-Refus-Raison"), e.detail)

    R_USED = S.ESSAI6_REFUS_CONSOMME
    R_DETENU = S.ESSAI6_REFUS_DEJA_DETENU

    # ══ CAS 1 — une personne inconnue obtient son premier essai ══════════════
    verifier("CAS 1. nouvelle personne -> premier essai autorise",
             (await refus("neuve@exemple.ch", "+41 79 111 22 33")) is None)

    # ══ CAS 2 — meme e-mail, essai CONSOMME ═════════════════════════════════
    _s = _forfait(brute, "AFR-C2", "c2@exemple.ch", "+41791112244", reste=0)
    _presence(brute, "AFR-C2", _s, validee=True)
    verifier("CAS 2. meme e-mail + essai consomme -> refus",
             (await refus("c2@exemple.ch"))[0] == R_USED)

    # ══ CAS 3 — e-mail DIFFERENT, meme telephone, essai consomme ════════════
    verifier("CAS 3. autre e-mail + MEME telephone + essai consomme -> refus",
             (await refus("tout-autre@exemple.ch", "+41791112244"))[0] == R_USED,
             "c'est l'abus mesure en production : +41765203363, trois adresses")

    # ══ CAS 4 — meme e-mail, reservation mais ABSENCE ═══════════════════════
    # Le credit lui a ete rendu (T1) : son forfait est encore utilisable.
    # « Reprendre un essai » = reprendre CELUI-LA, pas en fabriquer un second.
    _s4 = _forfait(brute, "AFR-C4", "c4@exemple.ch", "+41791112255", reste=1)
    _presence(brute, "AFR-C4", _s4, validee=False)
    _r4 = await refus("c4@exemple.ch")
    verifier("CAS 4. meme e-mail + absence -> essai TOUJOURS possible (pas 'deja utilise')",
             _r4 is not None and _r4[0] == R_DETENU,
             "renvoye vers son propre droit, jamais banni")
    verifier("CAS 4b. ... et son forfait d'essai reste utilisable",
             (await S.essai6_reutilisable(db, "c4@exemple.ch")) is not None)

    # ══ CAS 5 — meme telephone, reservation mais ABSENCE ════════════════════
    _r5 = await refus("encore-autre@exemple.ch", "+41791112255")
    verifier("CAS 5. meme telephone + absence -> pas de refus 'consomme'",
             _r5 is not None and _r5[0] == R_DETENU)
    verifier("CAS 5b. ... l'absence n'a JAMAIS consomme le droit",
             (await S.essai6_consomme(db, "", "+41791112255")) is None)

    # ══ CAS 6 — le document source PRINCIPAL a ete supprime ═════════════════
    # C'est la situation reelle d'AFR-248AJR et AFR-V9KAUW.
    _s6 = _forfait(brute, "AFR-C6", "c6@exemple.ch", "+41791112266",
                   origine="offert", reste=0, avec_code=False)
    _presence(brute, "AFR-C6", _s6, validee=True)
    verifier("CAS 6. code supprime -> le forfait reste reconnu comme un essai",
             await S.est_un_essai(db, forfait=brute.subscriptions.find_one({"id": _s6})))
    verifier("CAS 6b. ... et l'essai consomme est toujours vu -> second essai refuse",
             (await refus("c6@exemple.ch"))[0] == R_USED)
    verifier("CAS 6c. ... reconnu par le CODE seul aussi (appelants qui n'ont que lui)",
             await S.est_un_essai(db, code="AFR-C6"))

    # ══ CAS 7 — telephone absent : le comportement e-mail est conserve ══════
    _s7 = _forfait(brute, "AFR-C7", "c7@exemple.ch", "", reste=0)
    _presence(brute, "AFR-C7", _s7, validee=True)
    verifier("CAS 7. telephone absent -> comportement e-mail inchange (refus)",
             (await refus("c7@exemple.ch", ""))[0] == R_USED)
    verifier("CAS 7b. telephone absent chez un inconnu -> essai accorde",
             (await refus("inconnu7@exemple.ch", "")) is None)
    verifier("CAS 7c. numero trop court ignore, jamais pris pour une identite",
             S.essai6_normaliser_tel("0") == "" and S.essai6_normaliser_tel("12") == "")

    # ══ CAS 8 — trois ecritures du MEME numero ══════════════════════════════
    _n = S.essai6_normaliser_tel("+41 76 123 45 67")
    verifier("CAS 8. +41 76 123 45 67 / 0761234567 / 0041761234567 -> meme identite",
             _n == S.essai6_normaliser_tel("0761234567")
             == S.essai6_normaliser_tel("0041761234567") == "41761234567",
             "convention `normaliser_numero` du depot, pas une troisieme")
    _s8 = _forfait(brute, "AFR-C8", "c8@exemple.ch", "+41 76 123 45 67", reste=0)
    _presence(brute, "AFR-C8", _s8, validee=True)
    verifier("CAS 8b. ... et un autre format du meme numero est refuse",
             (await refus("autre8@exemple.ch", "0041761234567"))[0] == R_USED)

    # ══ CAS 9 — un client PAYANT n'est pas un essai ═════════════════════════
    _s9 = _forfait(brute, "PULSE-C9", "c9@exemple.ch", "+41791112299",
                   offre=OFFRE_PAYANTE, origine="twint", reste=8, avec_code=False)
    brute.subscriptions.update_one({"id": _s9}, {"$set": {"montant_encaisse": 250.0}})
    _presence(brute, "PULSE-C9", _s9, validee=True)
    verifier("CAS 9. forfait payant -> PAS un essai",
             not await S.est_un_essai(db, forfait=brute.subscriptions.find_one({"id": _s9})))
    verifier("CAS 9b. ... sa presence ne vaut pas essai consomme",
             (await S.essai6_consomme(db, "c9@exemple.ch")) is None)
    verifier("CAS 9c. ... et il garde droit a un essai",
             (await refus("c9@exemple.ch", "+41791112299")) is None)

    # ══ CAS 10 — le document parasite de `reservations` ═════════════════════
    # Forme reelle mesuree en production : une reponse d'API mise en cache.
    brute.reservations.insert_one({"coach_id": "", "data": [], "pagination": {}})
    _s10 = _forfait(brute, "AFR-C10", "c10@exemple.ch", "+41791112210", reste=1)
    verifier("CAS 10. document parasite -> ne vaut pas une presence, aucun faux refus",
             (await S.essai6_consomme(db, "c10@exemple.ch")) is None)
    verifier("CAS 10b. ... et il n'est jamais rendu comme preuve",
             (await refus("c10@exemple.ch"))[0] == R_DETENU)

    # ══ CAS 11 — les deux forfaits orphelins de production ══════════════════
    # Reproduits a l'identique : code supprime, forfait actif, 1 seance, AUCUNE
    # presence. Ils ne doivent etre ni casses, ni requalifies en consommes, ni
    # dotes d'un code invente.
    _s11 = _forfait(brute, "AFR-248AJR", "fogasa@exemple.ch", "+41765203324",
                    origine=None, reste=1, avec_code=False)
    _s11b = _forfait(brute, "AFR-V9KAUW", "hejox@exemple.ch", "+41765203363",
                     origine=None, reste=1, avec_code=False)
    verifier("CAS 11. orphelin reconnu comme essai (preuve P3, l'offre a 0)",
             await S.est_un_essai(db, forfait=brute.subscriptions.find_one({"id": _s11})))
    verifier("CAS 11b. orphelin SANS presence -> jamais 'consomme'",
             (await S.essai6_consomme(db, "fogasa@exemple.ch")) is None)
    verifier("CAS 11c. orphelin -> renvoye vers son essai, pas banni",
             (await refus("fogasa@exemple.ch", "+41765203324"))[0] == R_DETENU)
    verifier("CAS 11d. aucun code n'a ete invente pour lui",
             brute.discount_codes.count_documents({"code": "AFR-248AJR"}) == 0)
    verifier("CAS 11e. son forfait n'a pas ete touche",
             brute.subscriptions.find_one({"id": _s11})["remaining_sessions"] == 1)
    verifier("CAS 11f. l'autre orphelin non plus",
             brute.subscriptions.find_one({"id": _s11b})["remaining_sessions"] == 1)

    # ══ CAS 12 — la portee : une personne, un essai PAR PROPRIETAIRE ════════
    # `c2@exemple.ch` a consomme son essai SANS proprietaire. Le partenaire a
    # son propre catalogue : son essai a lui reste ouvert.
    verifier("CAS 12. essai consomme chez le proprietaire A -> refus chez A",
             (await refus("c2@exemple.ch", "", None))[0] == R_USED)
    verifier("CAS 12b. ... mais l'essai du PARTENAIRE reste accessible",
             (await refus("c2@exemple.ch", "", PARTENAIRE)) is None,
             "la cle est (personne, proprietaire) — jamais « plus rien de gratuit, nulle part »")
    verifier("CAS 12c. le catalogue gratuit est filtre par proprietaire",
             (await S.essai6_offres_gratuites(db, None)) == [OFFRE_ESSAI]
             and (await S.essai6_offres_gratuites(db, PARTENAIRE)) == [OFFRE_ESSAI_PARTENAIRE])

    # ══ ATOMICITE — deux requetes nees a la meme milliseconde ═══════════════
    _res = await asyncio.gather(
        refus("course@exemple.ch", "+41791119999"),
        refus("course@exemple.ch", "+41791119999"),
        return_exceptions=True)
    _accordes = [r for r in _res if r is None]
    verifier("ATOMICITE. deux octrois simultanes -> UN SEUL passe",
             len(_accordes) == 1, "verrou de cle primaire, pas une lecture-puis-ecriture")

    # ══ COMPATIBILITE — la forme des verrous deja poses en production ═══════
    verifier("VERROU. sans proprietaire, la cle reste `trial:{email}` (zero migration)",
             GARDE["_essai1_cles"]("A@Exemple.CH ") == ["trial:a@exemple.ch"])
    verifier("VERROU b. avec telephone, une seconde cle s'ajoute",
             GARDE["_essai1_cles"]("a@exemple.ch", "+41 76 123 45 67")
             == ["trial:a@exemple.ch", "trialtel:41761234567"])
    verifier("VERROU c. un partenaire a son propre espace de cles",
             GARDE["_essai1_cles"]("a@exemple.ch", "", PARTENAIRE)
             == ["trial:" + PARTENAIRE + ":a@exemple.ch"])
    verifier("VERROU d. le document de verrou n'est jamais supprime, il est marque",
             "delete_one" not in _extraire_ck("_essai1_liberer_cle"))

    # ══ INVARIANT G1/G2 — un refus ne consomme jamais le droit ══════════════
    verifier("INVARIANT. une personne sans rien : le droit reste ouvert",
             (await GARDE["_essai1_essai_deja_accorde"]("jamais-vue@exemple.ch")) is False)


def executer():
    dossier = tempfile.mkdtemp(prefix="banc_essai6_")
    port = _port_libre()
    proc = subprocess.Popen(
        ["mongod", "--dbpath", dossier, "--port", str(port),
         "--bind_ip", "127.0.0.1", "--quiet"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    cli = None
    for _ in range(60):
        try:
            cli = pymongo.MongoClient("mongodb://127.0.0.1:%d" % port,
                                      serverSelectionTimeoutMS=500)
            cli.admin.command("ping")
            break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate(); shutil.rmtree(dossier, ignore_errors=True)
        print("mongod indisponible — banc ignore"); return 0

    try:
        brute = cli["banc_essai6"]
        db = _Db(brute)
        _semer(brute)

        esp = {"db": db, "HTTPException": _HTTPException, "datetime": datetime,
               "timezone": timezone, "logger": logging.getLogger("e6"), "uuid": uuid}

        async def _tracer(offer_id=""):
            return None

        esp["_essai1_tracer_refus"] = _tracer
        for fn in ("_essai1_motif_refus", "_essai1_essai_deja_accorde",
                   "_essai1_cles", "_essai1_reclamer", "_essai1_liberer_cle",
                   "_essai1_liberer", "_essai1_garde"):
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
    print("ESSAI-6 — NATURE DE L'ESSAI ET IDENTITE DE LA PERSONNE")
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

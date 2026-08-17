# -*- coding: utf-8 -*-
"""V446 — le chemin de prelevement n'est plus ouvert a Internet.

Les deux handlers sont EXTRAITS de api/server.py par analyse AST et executes tels
quels. Stripe n'est jamais importe ni appele : le moteur de renouvellement est
remplace par un mouchard. AUCUN prelevement, AUCUN reseau, AUCUNE base reelle.

Lancement :  python3 tests/test_v446_cron_paiement.py
"""
import ast, asyncio, io, os, subprocess, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

SECRET = "secret-de-cron-de-test-v446-jamais-en-production"
CODES_CONNUS = {"NADIABOOST-26"}
ADMIN = "contact.artboost@gmail.com"

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
    """Le code EXECUTE, sans docstring ni commentaires — les commentaires V446
    citent `PaymentIntent` et `off_session` pour expliquer le risque ; une
    recherche de texte brute les prendrait pour du code."""
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps)


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code; self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))

class FausseRequete:
    def __init__(self, headers=None, corps=None):
        self._h = {k.lower(): v for k, v in (headers or {}).items()}
        self.headers = self
        self._corps = corps if corps is not None else {}
    def get(self, k, d=""): return self._h.get(k.lower(), d)
    async def json(self): return self._corps


# ------------------------------------------------ base factice, LECTURE SEULE
class _Curseur:
    def __init__(self, d): self.d = d
    def sort(self, *a, **k): return self
    async def to_list(self, n): return [dict(x) for x in self.d[:n]]

class _Coll:
    def __init__(self, docs=None): self.docs = docs or []; self.ecritures = []
    def find(self, q=None, p=None): return _Curseur(self.docs)
    async def find_one(self, q, p=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()): return dict(d)
        return None
    async def update_one(self, q, m, **k): self.ecritures.append((q, m))
    async def count_documents(self, q): return len(self.docs)

class _Base:
    def __init__(self, subs=None): self.subscriptions = _Coll(subs)


APPELS_STRIPE = []          # doit rester VIDE
AUTORISATIONS = []          # arguments passes a _v334_autoriser


def bac_commun(subs=None):
    from datetime import datetime as _dt, timezone as _tz
    base = _Base(subs)
    async def _faux_auto_renew(sub):
        APPELS_STRIPE.append(sub)          # le mouchard : jamais Stripe
        return False
    # LA VRAIE `_v334_autoriser`, extraite de server.py et executee telle quelle.
    # Une revue a justement releve qu'un bouchon aurait valide le bouchon, pas la
    # garde : `R2 PASSE` serait passe pour une mauvaise raison. On ne stubbe donc
    # que ses trois dependances d'entree/sortie, jamais sa logique de decision.
    _autoriser_bac = {
        "HTTPException": HTTPException, "Request": FausseRequete, "logger": None,
        "_v261_resolve_subscriber": None, "_v263_authenticated_coach": None,
        "_v309_is_coach_or_admin": None, "is_super_admin": lambda e: e == ADMIN,
    }
    async def _resoudre(code):
        code = (code or "").strip().upper()
        return (True, "Abonne", None) if code in CODES_CONNUS else (False, "", None)
    async def _coach_auth(request):
        return ADMIN if request.get("X-Admin-Test") == "oui" else ""
    async def _est_coach(email): return email == ADMIN
    _autoriser_bac.update({
        "_v261_resolve_subscriber": _resoudre,
        "_v263_authenticated_coach": _coach_auth,
        "_v309_is_coach_or_admin": _est_coach,
        "logger": type("l", (), {"warning": staticmethod(lambda *a, **k: None),
                                 "info": staticmethod(lambda *a, **k: None)}),
    })
    exec(compile(extraire("_v334_autoriser"), "<v446-garde>", "exec"), _autoriser_bac)
    _vraie = _autoriser_bac["_v334_autoriser"]
    async def _faux_autoriser(request, code_cible, code_fourni=""):
        AUTORISATIONS.append((code_cible, code_fourni))
        return await _vraie(request, code_cible, code_fourni)
    return {
        "db": base, "HTTPException": HTTPException, "Request": FausseRequete,
        "datetime": _dt, "timezone": _tz,
        "os": type("os", (), {"environ": {}}),
        "logger": type("l", (), {"warning": staticmethod(lambda *a, **k: None),
                                 "info": staticmethod(lambda *a, **k: None),
                                 "error": staticmethod(lambda *a, **k: None),
                                 "debug": staticmethod(lambda *a, **k: None)}),
        "is_super_admin": lambda e: (e or "").lower().strip() == ADMIN,
        "_v311_coach_email_from_jwt": lambda r: r.get("X-Faux-JWT", ""),
        "_v195_auto_renew": _faux_auto_renew,
        "_v195_send_renewal_notification": lambda *a, **k: None,
        "_v334_autoriser": _faux_autoriser,
        "api_router": type("r", (), {"get": staticmethod(lambda *a, **k: (lambda f: f)),
                                     "put": staticmethod(lambda *a, **k: (lambda f: f))}),
    }, base


def construire_cron(secret=""):
    bac, base = bac_commun([])
    bac["os"].environ["CRON_SECRET"] = secret
    exec(compile(extraire("cron_check_subscription_renewal"), "<v446>", "exec"), bac)
    return bac, base

def construire_toggle(subs):
    bac, base = bac_commun(subs)
    exec(compile(extraire("toggle_subscription_auto_renew"), "<v446>", "exec"), bac)
    return bac, base


async def scenario():
    B = lambda t: {"Authorization": "Bearer " + t}

    # ═══ ROUTE 1 — le cron de renouvellement ═══
    for nom, secret, headers in (
        ("anonyme, secret absent",          "",      {}),
        ("anonyme, secret pose",            SECRET,  {}),
        ("secret FAUX",                     SECRET,  B("mauvais-secret")),
        ("secret alors qu'aucun n'est pose", "",     B(SECRET)),
        ("X-User-Email forge d'un admin",   SECRET,  {"X-User-Email": ADMIN}),
        ("JWT d'un non-admin",              SECRET,  {"X-Faux-JWT": "quidam@example.com"}),
        ("Bearer vide",                     SECRET,  B("")),
        # Le cas que `bool(cron_secret)` existe PRECISEMENT pour empecher :
        # sans lui, `auth == f"Bearer {''}"` laisserait passer un Bearer vide
        # quand aucun secret n'est pose. Signale par la revue, il manquait.
        ("secret ABSENT + Bearer vide",     "",      B("")),
        ("secret ABSENT + Bearer nu",       "",      {"Authorization": "Bearer"}),
    ):
        bac, base = construire_cron(secret)
        avant = len(APPELS_STRIPE)
        try:
            await bac["cron_check_subscription_renewal"](FausseRequete(headers))
            verifier("R1 REFUS  %s" % nom, False, "aucun refus")
        except HTTPException as e:
            verifier("R1 REFUS  %s" % nom, e.status_code == 401, str(e.status_code))
        verifier("R1        ^ base non interrogee", base.subscriptions.docs == [], "")
        verifier("R1        ^ AUCUN appel au moteur de paiement",
                 len(APPELS_STRIPE) == avant, "%d appel(s)" % (len(APPELS_STRIPE) - avant))

    for nom, secret, headers in (
        ("secret de cron VALIDE", SECRET, B(SECRET)),
        ("super-admin JWT signe", SECRET, {"X-Faux-JWT": ADMIN}),
        ("super-admin sans secret pose", "", {"X-Faux-JWT": ADMIN}),
    ):
        bac, base = construire_cron(secret)
        try:
            r = await bac["cron_check_subscription_renewal"](FausseRequete(headers))
            verifier("R1 PASSE  %s" % nom, isinstance(r, dict) and r.get("scanned") == 0, str(r))
        except HTTPException as e:
            verifier("R1 PASSE  %s" % nom, False, "refuse en %s" % e.status_code)

    # ═══ ROUTE 2 — la bascule auto_renew ═══
    SUBS = [{"id": "sub-1", "code": "NADIABOOST-26", "stripe_customer_id": "cus_x",
             "stripe_payment_method": "pm_x", "auto_renew": False}]

    for nom, corps, headers, attendu in (
        ("anonyme, sans code",            {"auto_renew": True},                          {}, 403),
        ("code FAUX",                     {"auto_renew": True, "code": "PAS-LE-BON"},    {}, 403),
        ("code vide",                     {"auto_renew": True, "code": ""},              {}, 403),
    ):
        bac, base = construire_toggle(list(SUBS))
        try:
            await bac["toggle_subscription_auto_renew"]("sub-1", FausseRequete(headers, corps))
            verifier("R2 REFUS  %s" % nom, False, "aucun refus")
        except HTTPException as e:
            verifier("R2 REFUS  %s" % nom, e.status_code == attendu, str(e.status_code))
        verifier("R2        ^ aucune ecriture sur l'abonnement",
                 base.subscriptions.ecritures == [], str(base.subscriptions.ecritures))

    # le chemin LEGITIME de l'abonne : il presente le code de son espace
    bac, base = construire_toggle(list(SUBS))
    r = await bac["toggle_subscription_auto_renew"](
        "sub-1", FausseRequete({}, {"auto_renew": True, "code": "NADIABOOST-26"}))
    verifier("R2 PASSE  abonne avec SON code (regle V310c)",
             r.get("success") is True and r.get("auto_renew") is True, str(r))
    verifier("R2        ^ l'ecriture a bien eu lieu", len(base.subscriptions.ecritures) == 1, "")

    # le coach/admin authentifie garde son acces
    bac, base = construire_toggle(list(SUBS))
    r = await bac["toggle_subscription_auto_renew"](
        "sub-1", FausseRequete({"X-Admin-Test": "oui"}, {"auto_renew": False}))
    verifier("R2 PASSE  coach/admin authentifie", r.get("success") is True, str(r))

    # abonnement sans code : on refuse plutot que d'ouvrir
    bac, base = construire_toggle([{"id": "sub-2", "code": "", "auto_renew": False}])
    try:
        await bac["toggle_subscription_auto_renew"]("sub-2", FausseRequete({}, {"auto_renew": True}))
        verifier("R2 REFUS  abonnement sans code", False, "aucun refus")
    except HTTPException as e:
        verifier("R2 REFUS  abonnement sans code", e.status_code == 403, str(e.status_code))

    # abonnement inexistant : 404 avant toute autorisation (comportement historique)
    bac, base = construire_toggle([])
    try:
        await bac["toggle_subscription_auto_renew"]("inconnu", FausseRequete({}, {"auto_renew": True}))
        verifier("R2 404 sur abonnement inexistant", False, "")
    except HTTPException as e:
        verifier("R2 404 sur abonnement inexistant", e.status_code == 404, str(e.status_code))


def tests_structurels():
    # --- la garde precede TOUT dans le cron ---
    nu = code_nu("cron_check_subscription_renewal")
    verifier("S1. le refus precede la requete Mongo",
             nu.index("raise HTTPException") < nu.index("db.subscriptions.find"), "")
    verifier("S2. le handler recoit un objet Request",
             "request" in [a.arg for a in noeud("cron_check_subscription_renewal").args.args], "")
    verifier("S3. fail-closed : le secret vide n'ouvre pas",
             "bool(cron_secret)" in nu, nu[:120])
    verifier("S4. l'identite admin vient d'un JWT signe, pas d'un en-tete",
             "_v311_coach_email_from_jwt" in nu and "X-User-Email" not in nu, "")

    # --- la garde precede l'ecriture dans la bascule ---
    nu2 = code_nu("toggle_subscription_auto_renew")
    verifier("S5. l'autorisation precede l'ecriture",
             nu2.index("_v334_autoriser") < nu2.index("db.subscriptions.update_one"), "")
    verifier("S6. la garde abonne reutilisee est celle du depot (_v334_autoriser)",
             "_v334_autoriser" in nu2, "")
    verifier("S7. le garde-fou moyen de paiement d'origine est CONSERVE",
             "stripe_customer_id" in nu2 and "stripe_payment_method" in nu2, "")

    # --- LE MOTEUR DE PAIEMENT N'A PAS BOUGE (consigne du proprietaire) ---
    # Ce que V446 doit prouver, c'est que SON commit n'a pas touche au moteur —
    # pas que personne ne le touchera jamais. Une sonde bornee a l'arbre de
    # travail tombe des le lot suivant : V447 ajoute une cle d'idempotence, tout
    # a fait legitimement, et cette sonde n'a rien a en dire. QUATRIEME occurrence
    # de ce defaut dans le depot (S9b de V442, F1 de V443, H1-H4 de V445). On
    # compare donc le commit V446 a SON PROPRE PARENT.
    V446 = "1f063c9"
    def _src_au(rev, nom):
        txt = subprocess.check_output(["git", "show", "%s:api/server.py" % rev],
                                      cwd=RACINE).decode(errors="replace")
        lg = txt.splitlines(True)
        for x in ast.walk(ast.parse(txt)):
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == nom:
                return "".join(lg[x.lineno - 1:x.end_lineno])
        return None
    for f in ("_v195_auto_renew", "_v195_send_renewal_notification"):
        verifier("S8. le commit V446 n'a pas touche a %s" % f,
                 _src_au(V446 + "^", f) == _src_au(V446, f), "")
    verifier("S9. V446 n'a ajoute aucune idempotency_key (elle viendra de V447)",
             "idempotency_key" not in (_src_au(V446, "_v195_auto_renew") or ""), "")

    # --- perimetre ---
    # Le perimetre se juge sur le LOT, pas sur l'arbre de travail. Une sonde
    # bornee a un hachage fige tombe des qu'un lot ULTERIEUR touche le meme
    # fichier — c'est arrive deja deux fois dans ce depot (S9b de V442, F1 de
    # V443). On regarde donc la plage de commits si elle existe, et l'arbre
    # seulement tant que le lot n'est pas commite.
    _plage = subprocess.check_output(["git", "rev-list", "--count", "ff5846d..HEAD"],
                                     cwd=RACINE).decode().strip()
    _ref = ["git", "diff", "--name-only", "ff5846d..HEAD"] if _plage != "0" \
        else ["git", "diff", "--name-only", "ff5846d"]
    touches = sorted(f for f in subprocess.check_output(_ref, cwd=RACINE).decode().split()
                     if f and not f.startswith("tests/"))
    ATTENDUS = ["api/server.py", "docker-compose.yml",
                "frontend/src/components/SubscriberSpace.js"]
    verifier("S10. perimetre applicatif conforme au lot declare",
             touches == ATTENDUS, "%s (attendu %s)" % (touches, ATTENDUS))
    verifier("S10b. aucun AUTRE cron touche que celui du renouvellement",
             all(f not in touches for f in
                 ("api/routes/reservation_routes.py", "api/routes/stripe_routes.py",
                  "api/routes/checkout_routes.py")), str(touches))

    # --- AUCUNE trace de Stripe dans ce test ---
    moi = io.open(__file__, encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import): mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module: mods.add(n.module.split(".")[0])
    verifier("S11. ce test n'importe ni stripe, ni requests, ni pymongo",
             not (mods & {"stripe", "requests", "pymongo", "httpx", "urllib", "socket"}),
             str(sorted(mods)))
    verifier("S12. il n'importe que la bibliotheque standard",
             mods <= {"ast", "asyncio", "io", "os", "subprocess", "sys", "datetime"}, str(sorted(mods)))


def main():
    tests_structurels()
    asyncio.get_event_loop().run_until_complete(scenario())
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Appels au moteur de paiement pendant cette suite : %d (attendu : 0)" % len(APPELS_STRIPE))
    print("PaymentIntent REELLEMENT crees : 0 — le module stripe n'est jamais importe")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if (ok == len(RESULTATS) and not APPELS_STRIPE) else 1


if __name__ == "__main__":
    sys.exit(main())

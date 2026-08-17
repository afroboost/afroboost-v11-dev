# -*- coding: utf-8 -*-
"""V447 — deux appels concurrents ne peuvent plus produire deux prelevements.

Le handler du cron ET `_v195_auto_renew` sont EXTRAITS de api/server.py par AST et
executes tels quels. Le module `stripe` est remplace par un faux qui ENREGISTRE
l'appel : aucune connexion, aucun prelevement, aucune cle d'API lue.

La base factice reproduit la semantique de Mongo qui compte ici :
`find_one_and_update` filtre et ecrit SANS point de suspension interne — c'est
exactement ce qui rend l'operation atomique, et c'est sur cette propriete que
repose tout le lot.

Lancement :  python3 tests/test_v447_verrou_renouvellement.py
"""
import ast, asyncio, io, os, subprocess, sys
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

ADMIN = "contact.artboost@gmail.com"
SECRET = "secret-de-test-v447"

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


# ══════════════════ Mongo factice : l'atomicite est la propriete testee ══════
def _match(doc, f):
    for cle, cond in f.items():
        if cle == "$or":
            if not any(_match(doc, c) for c in cond): return False
            continue
        val = doc.get(cle, KeyError)
        if isinstance(cond, dict):
            for op, ref in cond.items():
                if op == "$exists":
                    if (val is not KeyError) != ref: return False
                elif op == "$ne":
                    # semantique Mongo : sur un TABLEAU, `$ne: v` est vrai si
                    # aucun element ne vaut v.
                    if isinstance(val, list):
                        if ref in val: return False
                    elif val == ref: return False
                elif op in ("$lt", "$lte", "$gte"):
                    # CLOISONNEMENT PAR TYPE — c'est le comportement de MongoDB, et
                    # il compte ici : `$lt: "<chaine>"` face a un nombre ou a une
                    # Date ne matche PAS, et ne leve pas. Comparer directement en
                    # Python leverait un TypeError et masquerait le vrai
                    # comportement (c'est ce qui est arrive a la premiere version
                    # de ce simulateur).
                    if val is KeyError or val is None: return False
                    if isinstance(val, str) != isinstance(ref, str): return False
                    if isinstance(val, bool) or isinstance(ref, bool): return False
                    try:
                        _ok = (val < ref) if op == "$lt" else \
                              (val <= ref) if op == "$lte" else (val >= ref)
                    except TypeError:
                        return False
                    if not _ok: return False
                elif op == "$nin":
                    if val is not KeyError and val in ref: return False
                elif op == "$type":
                    # MongoDB compare par TYPE. On ne simule que "string", seul
                    # type utilise par le filtre du verrou.
                    _est = isinstance(val, str)
                    if ref != "string":
                        raise AssertionError("type non simule : %s" % ref)
                    if not _est: return False
                elif op == "$not":
                    # `{champ: {$not: <expr>}}` matche quand <expr> ne matche PAS —
                    # y compris quand le champ est ABSENT. C'est la semantique qui
                    # rattrape un `renewal_lock_at` d'un type inattendu.
                    if _match(doc, {cle: ref}): return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        else:
            if val is KeyError or val != cond: return False
    return True

def _appliquer(doc, maj):
    for op, champs in maj.items():
        if op == "$set": doc.update(champs)
        elif op == "$unset":
            for k in champs: doc.pop(k, None)
        elif op == "$push":
            for k, v in champs.items(): doc.setdefault(k, []).append(v)
        elif op == "$inc":
            for k, v in champs.items(): doc[k] = (doc.get(k) or 0) + v
        else: raise AssertionError("op non simule : %s" % op)

class _Curseur:
    def __init__(self, d, coll=None): self.d = d; self.coll = coll
    def sort(self, *a, **k): return self
    async def to_list(self, n):
        await asyncio.sleep(0)          # le `find` rend la main lui aussi
        return [dict(x) for x in self.d[:n]]

class _Coll:
    """Chaque methode REND LA MAIN a la boucle avant d'agir.

    C'est le trajet reseau vers MongoDB, et c'est indispensable : sans ce point de
    suspension, `asyncio.gather` deroule la premiere tache entierement avant de
    demarrer la seconde, aucun entrelacement ne se produit, et un test de
    concurrence passe meme sans verrou. Une revue l'a demontre sur la premiere
    version de ce fichier — les tests 1 et 2 passaient sur le code d'avant V447.

    L'atomicite, elle, est modelisee par l'ABSENCE de `await` entre le filtre et
    l'ecriture DANS `find_one_and_update`. Rendre la main avant : oui. Pendant :
    jamais. C'est exactement le contrat de MongoDB au niveau du document.
    """
    def __init__(self, docs=None): self.docs = docs or []
    def find(self, q=None, p=None):
        return _Curseur([d for d in self.docs if _match(d, q or {})], self)
    async def find_one(self, q, p=None):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q): return dict(d)
        return None
    async def update_one(self, q, m, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q): _appliquer(d, m); return
    async def find_one_and_update(self, q, m, **k):
        await asyncio.sleep(0)          # le trajet reseau — AVANT la section atomique
        # --- section atomique : aucun `await` du filtre a l'ecriture ---
        for d in self.docs:
            if _match(d, q):
                avant = dict(d); _appliquer(d, m); return avant
        return None

class _Base:
    def __init__(self, subs): self.subscriptions = _Coll(subs)


# ══════════════════ faux Stripe — il n'envoie rien, il enregistre ════════════
APPELS_PI = []

class _FauxStripeError(Exception):
    def __init__(self, msg="", user_message=""):
        Exception.__init__(self, msg); self.user_message = user_message

class _PI:
    @staticmethod
    def create(**kw):
        APPELS_PI.append(kw)
        if _PI.comportement == "carte_refusee":
            raise _FauxStripe.error.CardError("refus", user_message="Carte refusee")
        if _PI.comportement == "timeout":
            raise _FauxStripeError("timeout reseau")
        return type("pi", (), {"status": "succeeded", "id": "pi_faux"})()
    comportement = "succes"

class _FauxStripe:
    PaymentIntent = _PI
    class error:
        CardError = type("CardError", (_FauxStripeError,), {})


def bac(subs, secret=SECRET, mongo_ko_apres_stripe=False):
    from datetime import datetime as _dt
    base = _Base(subs)
    if mongo_ko_apres_stripe:
        async def _ko(q, m, **k): raise RuntimeError("Mongo indisponible")
        base.subscriptions.update_one = _ko
    b = {
        "db": base, "HTTPException": type("H", (Exception,), {}),
        "Request": object, "datetime": _dt, "timezone": timezone, "timedelta": timedelta,
        "stripe": _FauxStripe,
        "os": type("os", (), {"environ": {"CRON_SECRET": secret}}),
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
        "is_super_admin": lambda e: e == ADMIN,
        "_v311_coach_email_from_jwt": lambda r: r.get("jwt", ""),
        "_v195_send_renewal_notification": lambda *a, **k: asyncio.sleep(0),
        "api_router": type("r", (), {"get": staticmethod(lambda *a, **k: (lambda f: f))}),
    }
    exec(compile(extraire("_v195_auto_renew"), "<v447>", "exec"), b)
    src_cron = extraire("cron_check_subscription_renewal")
    src_cst = "V447_VERROU_TTL_S = 900\n"
    exec(compile(src_cst + src_cron, "<v447>", "exec"), b)
    return b, base


class Req(dict):
    def __init__(self, h=None): dict.__init__(self, h or {}); self.headers = self
    def get(self, k, d=""): return dict.get(self, k, d)

def REQ_CRON(): return Req({"Authorization": "Bearer " + SECRET})

def abonne(**kw):
    d = {"id": "sub-1", "email": "a@example.com", "name": "Ana", "status": "active",
         "auto_renew": True, "remaining_sessions": 0, "renewal_price": 60.0,
         "renewal_sessions": 10, "stripe_customer_id": "cus_1",
         "stripe_payment_method": "pm_1", "renewal_warnings_sent": []}
    d.update(kw); return d


async def scenario():
    JOUR = datetime.now(timezone.utc).strftime("%Y%m%d")

    # ── 1. DEUX appels simultanes → UN SEUL PaymentIntent ──
    APPELS_PI.clear(); _PI.comportement = "succes"
    b, base = bac([abonne()])
    r = await asyncio.gather(*[b["cron_check_subscription_renewal"](REQ_CRON()) for _ in range(2)])
    verifier("1. 2 appels simultanes -> UN SEUL PaymentIntent", len(APPELS_PI) == 1,
             "%d appels" % len(APPELS_PI))
    verifier("1b. un seul `renewed` compte au total",
             sum(x["renewed"] for x in r) == 1, str([x["renewed"] for x in r]))

    # ── 2. DIX appels simultanes → UN SEUL PaymentIntent ──
    APPELS_PI.clear()
    b, base = bac([abonne()])
    r = await asyncio.gather(*[b["cron_check_subscription_renewal"](REQ_CRON()) for _ in range(10)])
    verifier("2. 10 appels simultanes -> UN SEUL PaymentIntent", len(APPELS_PI) == 1,
             "%d appels" % len(APPELS_PI))
    verifier("2b. les 9 autres sortent proprement, sans erreur",
             sum(x["errors"] for x in r) == 0, str([x["errors"] for x in r]))

    # ── 3. Succes → aucun second debit, meme en rejouant ──
    APPELS_PI.clear()
    b, base = bac([abonne()])
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("3. succes -> 1 debit", len(APPELS_PI) == 1, str(len(APPELS_PI)))
    doc = base.subscriptions.docs[0]
    verifier("3b. le marqueur du jour est pose", ("renewed_%s" % JOUR) in doc["renewal_warnings_sent"],
             str(doc.get("renewal_warnings_sent")))
    verifier("3c. le verrou est relache", "renewal_lock_at" not in doc, str(doc.get("renewal_lock_at")))
    verifier("3d. les seances sont rechargees", doc["remaining_sessions"] == 10, str(doc["remaining_sessions"]))
    for _ in range(5):
        await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("3e. 5 rejeux apres succes -> AUCUN second debit", len(APPELS_PI) == 1,
             "%d appels" % len(APPELS_PI))

    # ── 4. Echec Stripe (carte refusee) → retry possible selon la strategie ──
    APPELS_PI.clear(); _PI.comportement = "carte_refusee"
    b, base = bac([abonne()])
    await b["cron_check_subscription_renewal"](REQ_CRON())
    doc = base.subscriptions.docs[0]
    verifier("4. carte refusee -> le verrou est relache", "renewal_lock_at" not in doc, "")
    verifier("4b. comportement metier historique conserve (auto_renew coupe)",
             doc.get("auto_renew") is False, str(doc.get("auto_renew")))
    verifier("4c. aucun marqueur de renouvellement pose",
             ("renewed_%s" % JOUR) not in (doc.get("renewal_warnings_sent") or []), "")

    # ── 5. Timeout reseau → verrou relache, reprise possible ──
    APPELS_PI.clear(); _PI.comportement = "timeout"
    b, base = bac([abonne()])
    await b["cron_check_subscription_renewal"](REQ_CRON())
    doc = base.subscriptions.docs[0]
    verifier("5. timeout -> verrou relache", "renewal_lock_at" not in doc, str(doc.get("renewal_lock_at")))
    verifier("5b. timeout -> l'abonnement reste eligible (retry au passage suivant)",
             doc.get("auto_renew") is True and doc.get("remaining_sessions") == 0, "")
    _PI.comportement = "succes"
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("5c. le retry aboutit", len(APPELS_PI) == 2, "%d appels" % len(APPELS_PI))

    # ── 6. Crash apres le verrou → recuperation apres peremption ──
    APPELS_PI.clear(); _PI.comportement = "succes"
    _vieux = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
    b, base = bac([abonne(renewal_lock_at=_vieux)])
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("6. verrou PERIME (crash) -> reprise possible", len(APPELS_PI) == 1,
             "%d appels" % len(APPELS_PI))
    APPELS_PI.clear()
    _frais = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    b, base = bac([abonne(renewal_lock_at=_frais)])
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("6b. verrou FRAIS -> on ne double pas", len(APPELS_PI) == 0,
             "%d appels" % len(APPELS_PI))

    # ── 6c. Un verrou d'un TYPE inattendu ne gele plus l'abonne a vie ──
    APPELS_PI.clear()
    b, base = bac([abonne(renewal_lock_at=12345)])       # un nombre, pas une chaine
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("6c. verrou d'un type inattendu -> l'abonne n'est PAS gele",
             len(APPELS_PI) == 1, "%d appel(s)" % len(APPELS_PI))
    APPELS_PI.clear()
    b, base = bac([abonne(renewal_lock_at=None)])
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("6d. verrou a null -> traite comme libre", len(APPELS_PI) == 1,
             "%d appel(s)" % len(APPELS_PI))

    # ── 7. Stripe OK mais Mongo KO → la cle d'idempotence protege le rejeu ──
    APPELS_PI.clear()
    b, base = bac([abonne()], mongo_ko_apres_stripe=True)
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("7. Stripe OK + Mongo KO -> 1 appel, et une cle d'idempotence",
             len(APPELS_PI) == 1 and "idempotency_key" in APPELS_PI[0], str(APPELS_PI[:1]))
    _cle1 = APPELS_PI[0]["idempotency_key"]
    b2, base2 = bac([abonne()])
    await b2["cron_check_subscription_renewal"](REQ_CRON())
    verifier("7b. le rejeu porte la MEME cle -> Stripe ne debite pas deux fois",
             APPELS_PI[-1]["idempotency_key"] == _cle1,
             "%s vs %s" % (_cle1, APPELS_PI[-1]["idempotency_key"]))
    verifier("7c. la cle est stable par (abonnement, jour)",
             _cle1 == "afb-renew-sub-1-%s" % JOUR, _cle1)

    # ── 8. Le montant n'a pas bouge ──
    verifier("8. montant inchange : 60.00 CHF -> 6000 centimes",
             APPELS_PI[0]["amount"] == 6000 and APPELS_PI[0]["currency"] == "chf",
             str({k: APPELS_PI[0].get(k) for k in ("amount", "currency")}))
    for champ, attendu in (("customer", "cus_1"), ("payment_method", "pm_1"),
                           ("off_session", True), ("confirm", True)):
        verifier("8b. %s inchange" % champ, APPELS_PI[0].get(champ) == attendu,
                 str(APPELS_PI[0].get(champ)))

    # ── 9. Un abonnement non eligible n'est jamais verrouille ──
    APPELS_PI.clear()
    b, base = bac([abonne(remaining_sessions=3, renewal_warnings_sent=["warning_3"])])
    await b["cron_check_subscription_renewal"](REQ_CRON())
    verifier("9. abonne a 3 seances -> aucun debit, aucun verrou",
             len(APPELS_PI) == 0 and "renewal_lock_at" not in base.subscriptions.docs[0], "")


async def test_discriminant():
    """Le harnais detecte-t-il l'absence de verrou ?

    Une suite de concurrence qui passe aussi sur le code casse ne prouve rien.
    On rejoue donc les MEMES 10 appels simultanes contre le handler d'AVANT
    V447 — celui du commit V446, qui a la garde d'authentification mais aucun
    verrou — et on EXIGE qu'il produise plusieurs prelevements. S'il n'en produit
    qu'un, c'est le harnais qui est defaillant, pas le code.
    """
    avant_txt = subprocess.check_output(["git", "show", "1f063c9:api/server.py"],
                                        cwd=RACINE).decode(errors="replace")
    arbre_av = ast.parse(avant_txt); lg_av = avant_txt.splitlines(True)
    src_cron_av = None
    for n in ast.walk(arbre_av):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and n.name == "cron_check_subscription_renewal":
            src_cron_av = "".join(lg_av[n.lineno - 1:n.end_lineno])
    if src_cron_av is None:
        verifier("0. le handler d'avant V447 est retrouvable", False, "introuvable a 1f063c9")
        return
    verifier("0. le handler d'avant V447 n'a AUCUN verrou",
             "find_one_and_update" not in src_cron_av, "")

    APPELS_PI.clear(); _PI.comportement = "succes"
    b, base = bac([abonne()])
    exec(compile(src_cron_av, "<v446>", "exec"), b)      # ecrase par la version SANS verrou
    await asyncio.gather(*[b["cron_check_subscription_renewal"](REQ_CRON()) for _ in range(10)])
    verifier("0b. SANS verrou, le harnais voit BIEN plusieurs prelevements",
             len(APPELS_PI) > 1,
             "%d appel(s) — le harnais n'entrelace pas, les tests 1 et 2 ne prouvent rien"
             % len(APPELS_PI))
    APPELS_PI.clear()


def tests_structurels():
    nu_moteur = extraire("_v195_auto_renew")
    verifier("S1. la cle d'idempotence est passee a Stripe",
             "idempotency_key=_v447_cle" in nu_moteur, "")
    verifier("S2. le montant n'est pas touche",
             "amount=int(round(price * 100))" in nu_moteur, "")
    def _code_nu(nom):
        """Le code EXECUTE, sans docstring : celle du cron cite `_v195_auto_renew()`
        AVANT le verrou, ce qui ferait echouer S4 sur une simple recherche de texte."""
        n = noeud(nom); corps = list(n.body)
        if (corps and isinstance(corps[0], ast.Expr)
                and isinstance(getattr(corps[0], "value", None), ast.Constant)
                and isinstance(corps[0].value.value, str)):
            corps = corps[1:]
        return "\n".join(ast.unparse(x) for x in corps)
    nu_cron = _code_nu("cron_check_subscription_renewal")
    verifier("S3. la prise de droit est atomique (find_one_and_update)",
             "find_one_and_update" in nu_cron, "")
    verifier("S4. le verrou precede l'appel au moteur",
             nu_cron.index("find_one_and_update") < nu_cron.index("_v195_auto_renew("), "")
    verifier("S5. le verrou est TOUJOURS relache (finally)",
             "finally:" in nu_cron and "$unset" in nu_cron, "")
    verifier("S6. le verrou est date, donc recuperable",
             "V447_VERROU_TTL_S" in nu_cron and "renewal_lock_at" in nu_cron, "")
    verifier("S7. l'ancienne lecture non atomique a disparu",
             "already_renewed_today" not in nu_cron, "")

    # le reste du moteur est intact
    avant = subprocess.check_output(["git", "show", "ff5846d:api/server.py"],
                                    cwd=RACINE).decode(errors="replace")
    a = ast.parse(avant); lg = avant.splitlines(True)
    def src_avant(nom):
        for x in ast.walk(a):
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == nom:
                return "".join(lg[x.lineno - 1:x.end_lineno])
    verifier("S8. _v195_send_renewal_notification INCHANGE",
             src_avant("_v195_send_renewal_notification") == extraire("_v195_send_renewal_notification"), "")
    # Le moteur ne differe QUE par la cle d'idempotence — compare par AST, pas
    # par expression reguliere : `ast.unparse` supprime commentaires et docstring,
    # et on retire chirurgicalement les deux seuls ajouts avant de comparer.
    def _corps_ast(src):
        n = ast.parse(src).body[0]
        corps = list(n.body)
        if (corps and isinstance(corps[0], ast.Expr)
                and isinstance(getattr(corps[0], "value", None), ast.Constant)
                and isinstance(corps[0].value.value, str)):
            corps = corps[1:]
        return corps

    _reconstruit = ast.Module(body=_corps_ast(nu_moteur), type_ignores=[])
    # 1. retirer l'affectation `_v447_cle = ...` OU QU'ELLE SOIT — elle est
    #    imbriquee dans le `try:`, un filtre de premier niveau la manquerait.
    _retire = False
    for _p in ast.walk(_reconstruit):
        for _attr in ("body", "orelse", "finalbody"):
            _bloc = getattr(_p, _attr, None)
            if isinstance(_bloc, list):
                _neuf = [x for x in _bloc
                         if not (isinstance(x, ast.Assign)
                                 and getattr(x.targets[0], "id", "") == "_v447_cle")]
                if len(_neuf) != len(_bloc):
                    _retire = True
                setattr(_p, _attr, _neuf)
    verifier("S9b. l'affectation de la cle a bien ete isolee", _retire, "")
    # 2. retirer le kwarg `idempotency_key` de l'appel a Stripe
    _trouve = False
    for x in ast.walk(_reconstruit):
        if isinstance(x, ast.Call) and "PaymentIntent.create" in ast.unparse(x.func):
            avant_n = len(x.keywords)
            x.keywords = [k for k in x.keywords if k.arg != "idempotency_key"]
            _trouve = avant_n != len(x.keywords)
    verifier("S9a. le kwarg idempotency_key est bien present dans l'appel", _trouve, "")
    _txt_apres = "\n".join(ast.unparse(x) for x in _reconstruit.body)
    _txt_avant = "\n".join(ast.unparse(x) for x in _corps_ast(src_avant("_v195_auto_renew")))
    verifier("S9. le moteur ne differe QUE par la cle d'idempotence",
             _txt_avant == _txt_apres, "ecart de %d caracteres" % abs(len(_txt_avant) - len(_txt_apres)))

    moi = io.open(__file__, encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import): mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module: mods.add(n.module.split(".")[0])
    verifier("S10. ce test n'importe NI stripe, NI reseau, NI base",
             not (mods & {"stripe", "requests", "pymongo", "httpx", "socket", "urllib"}),
             str(sorted(mods)))


def main():
    tests_structurels()
    asyncio.get_event_loop().run_until_complete(test_discriminant())
    asyncio.get_event_loop().run_until_complete(scenario())
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("PaymentIntent REELLEMENT crees : 0 — le module stripe n'est jamais importe")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

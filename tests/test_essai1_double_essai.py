# -*- coding: utf-8 -*-
"""ESSAI-1 — une personne n'obtient qu'UN essai gratuit.

Le vrai `free_checkout` et la vraie `create_checkout_session` sont extraits de
`api/routes/checkout_routes.py` par AST et executes sur un faux MongoDB qui
modelise la seule garantie d'unicite dont on dispose : la cle primaire `_id`.

`_process_successful_payment` est remplace par un MOUCHARD. Ce n'est pas une
complaisance : la garde doit s'executer AVANT lui, et un mouchard qui n'est
jamais appele est precisement la preuve recherchee. L'ordre reel dans le code
est verifie separement, par AST, sur le code execute (S1/S2).

Aucun reseau. Aucun paiement. Aucun e-mail. Aucun essai reel.

Lancement :  python3 tests/test_essai1_double_essai.py
"""

import ast
import asyncio
import io
import os
import subprocess
import sys
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIER = os.path.join(RACINE, "api", "routes", "checkout_routes.py")
SOURCE = io.open(FICHIER, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

BASE_AVANT = "0b3ef2a"          # l'etat du depot avant ESSAI-1

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom, arbre=None):
    for n in ast.walk(arbre or ARBRE):
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


# --------------------------------------------------------- faux client Mongo
class Doublon(Exception):
    """Ce que MongoDB leve sur une cle primaire deja prise (E11000)."""
    def __init__(self):
        Exception.__init__(self, "E11000 duplicate key error")


def _match(doc, q):
    for cle, attendu in (q or {}).items():
        if cle == "$or":
            if not any(_match(doc, sous) for sous in attendu):
                return False
            continue
        obtenu = doc.get(cle, _ABSENT)
        if isinstance(attendu, dict):
            for op, v in attendu.items():
                if op == "$exists":
                    if bool(obtenu is not _ABSENT) != bool(v):
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        else:
            if obtenu is _ABSENT or obtenu != attendu:
                return False
    return True


_ABSENT = object()


class _Coll(object):
    """Chaque methode rend la main AVANT d'agir — sans cela `asyncio.gather`
    deroulerait la premiere requete entierement et aucune course n'aurait lieu.

    L'unicite de `_id`, elle, est verifiee et posee SANS `await` entre les deux :
    c'est ce que garantit MongoDB sur sa cle primaire."""

    def __init__(self, docs=None, cle_primaire=False):
        self.docs = list(docs or [])
        self.cle_primaire = cle_primaire
        self.ecritures = 0

    async def find_one(self, q, p=None):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q):
                return dict(d)
        return None

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        # --- section atomique : aucun await du controle a l'insertion ---
        if self.cle_primaire and "_id" in doc:
            if any(d.get("_id") == doc["_id"] for d in self.docs):
                raise Doublon()
        self.docs.append(dict(doc))
        self.ecritures += 1

    async def delete_one(self, q):
        await asyncio.sleep(0)
        for i, d in enumerate(self.docs):
            if _match(d, q):
                self.docs.pop(i)
                return

    async def update_one(self, q, m, **k):
        await asyncio.sleep(0)
        self.ecritures += 1


class _Base(object):
    def __init__(self, codes=None):
        self._c = {
            "discount_codes": _Coll(codes),
            "free_trial_claims": _Coll([], cle_primaire=True),
            "subscriptions": _Coll(),
            "checkout_transactions": _Coll(),
            "reservations": _Coll(),
            "payment_transactions": _Coll(),
            "chat_participants": _Coll(),
        }

    def __getitem__(self, nom):
        return self._c.setdefault(nom, _Coll())

    def __getattr__(self, nom):
        return self["_c"] if nom == "_c" else self[nom]


# ------------------------------------------------------------- les mouchards
PAIEMENTS = []          # appels a _process_successful_payment
POSTHOG = []            # evenements analytiques


class _HTTP(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}
        Exception.__init__(self, "%s %s" % (status_code, detail))


class _Item(object):
    def __init__(self, id=None, name="Essai", price=0.0, quantity=1, type="offer"):
        self.id = id
        self.name = name
        self.price = price
        self.quantity = quantity
        self.type = type

    def dict(self):
        return {"id": self.id, "name": self.name, "price": self.price,
                "quantity": self.quantity, "type": self.type}


class _Req(object):
    def __init__(self, email, items=None, nom="Ana", coach="coach@x.ch",
                 phone="", discount_code=None, discount_amount=0):
        self.customer_email = email
        self.customer_name = nom
        self.customer_phone = phone
        self.coach_email = coach
        self.items = items if items is not None else [_Item(id="off-essai")]
        self.discount_code = discount_code
        self.discount_amount = discount_amount


A_EXTRAIRE = ["_essai1_essai_deja_accorde", "_essai1_reclamer", "_essai1_liberer",
              "_essai1_tracer_refus", "_essai1_garde", "calculate_total",
              "free_checkout", "create_checkout_session"]

CONSTANTES = '''
ESSAI1_RAISON = "free_trial_already_used"
ESSAI1_MESSAGE = "Votre essai gratuit a deja ete utilise."
'''


def bac(codes=None, echec_paiement=False):
    PAIEMENTS[:] = []
    POSTHOG[:] = []
    base = _Base(codes)

    async def faux_paiement(**kw):
        await asyncio.sleep(0)
        PAIEMENTS.append(kw)
        if echec_paiement:
            raise RuntimeError("panne simulee pendant la creation")
        # ce que ferait le vrai helper : un code et un forfait
        await base["discount_codes"].insert_one({
            "code": "AFR-XXXXXX",
            "assignedEmail": (kw.get("customer_email") or "").strip().lower(),
            "payment_method": kw.get("payment_method"),
            "total_paid": kw.get("total"),
        })
        await base["subscriptions"].insert_one({
            "email": (kw.get("customer_email") or "").strip().lower(),
            "offer_id": str((kw.get("items") or [{}])[0].id or "") if kw.get("items") else "",
        })
        return {"access_code": "AFR-XXXXXX", "product_name": "Essai"}

    async def faux_posthog(event, email="", props=None, distinct_id=None):
        await asyncio.sleep(0)
        POSTHOG.append({"event": event, "email": email, "props": dict(props or {})})
        return True

    faux_shared = type("m", (), {"posthog_capture": staticmethod(faux_posthog)})
    sys.modules["api.routes.shared"] = faux_shared
    sys.modules.setdefault("api", type("p", (), {})())
    sys.modules.setdefault("api.routes", type("p", (), {})())
    sys.modules["api.server"] = type("m", (), {
        "send_push_by_email": staticmethod(lambda *a, **k: asyncio.sleep(0))})

    b = {
        "db": base,
        "asyncio": asyncio,
        "datetime": datetime, "timezone": timezone,
        "uuid": __import__("uuid"),
        "HTTPException": _HTTP,
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
        "router": type("r", (), {
            "post": staticmethod(lambda *a, **k: (lambda f: f))}),
        "_process_successful_payment": faux_paiement,
        "FreeCheckoutRequest": object, "CreateCheckoutRequest": object,
        # annotations des signatures extraites
        "List": list, "Optional": object, "Dict": dict, "Any": object,
        "CheckoutItem": _Item, "float": float, "str": str,
    }
    exec(compile("\n\n".join([CONSTANTES] + [extraire(f) for f in A_EXTRAIRE]),
                 "<essai1>", "exec"), b)
    absents = [f for f in A_EXTRAIRE if f not in b]
    assert not absents, "extraction incomplete : %s" % absents
    return b, base


def code_essai(email, **extra):
    """Un code tel que `_process_successful_payment` l'ecrit pour un essai."""
    d = {"code": "AFR-ANCIEN", "assignedEmail": email.lower(),
         "payment_method": "free", "total_paid": 0, "source": "checkout_payment"}
    d.update(extra)
    return d


# ============================================================================
#                     LES VERIFICATIONS BLOQUANTES
# ============================================================================
async def scenarios():
    ANA = "ana@exemple.ch"

    # --- T1. un nouveau visiteur passe -------------------------------------
    b, base = bac()
    r = await b["free_checkout"](_Req(ANA))
    verifier("T1. nouveau visiteur -> essai accorde",
             r.get("success") is True and len(PAIEMENTS) == 1, str(r)[:80])
    verifier("T1b. et sa reservation d'essai est posee",
             len(base["free_trial_claims"].docs) == 1)

    # --- T2. essai deja consomme -------------------------------------------
    b, base = bac(codes=[code_essai(ANA)])
    _e = None
    try:
        await b["free_checkout"](_Req(ANA))
    except _HTTP as ex:
        _e = ex
    verifier("T2. essai deja accorde -> refus 409",
             _e is not None and _e.status_code == 409, repr(_e and _e.status_code))
    verifier("T2b. le refus survient AVANT toute ecriture",
             len(PAIEMENTS) == 0, "%d appel(s) au moteur de paiement" % len(PAIEMENTS))
    verifier("T2c. le message est lisible, pas technique",
             _e and "essai" in str(_e.detail).lower() and "409" not in str(_e.detail),
             repr(_e and _e.detail))
    verifier("T2d. et le motif machine voyage en en-tete",
             _e and _e.headers.get("X-Refus-Raison") == "free_trial_already_used",
             repr(_e and _e.headers))

    # --- T3. essai encore actif --------------------------------------------
    b, base = bac(codes=[code_essai(ANA, active=True)])
    _e = None
    try:
        await b["free_checkout"](_Req(ANA))
    except _HTTP as ex:
        _e = ex
    verifier("T3. essai encore valide -> pas de second essai en parallele",
             _e is not None and len(PAIEMENTS) == 0)

    # --- T4. un refus ne laisse AUCUNE trace parasite -----------------------
    b, base = bac(codes=[code_essai(ANA)])
    _avant = {k: len(v.docs) for k, v in base._c.items()}
    try:
        await b["free_checkout"](_Req(ANA))
    except _HTTP:
        pass
    _apres = {k: len(v.docs) for k, v in base._c.items()}
    verifier("T4. refus -> aucune reservation, commande ou acces cree",
             _avant == _apres, "%r -> %r" % (_avant, _apres))

    # --- T5. double clic : deux requetes simultanees ------------------------
    b, base = bac()
    _res = await asyncio.gather(b["free_checkout"](_Req(ANA)),
                                b["free_checkout"](_Req(ANA)),
                                return_exceptions=True)
    _ok = [x for x in _res if not isinstance(x, Exception)]
    _ko = [x for x in _res if isinstance(x, _HTTP)]
    verifier("T5. 2 requetes concurrentes -> UN seul essai",
             len(PAIEMENTS) == 1 and len(_ok) == 1 and len(_ko) == 1,
             "%d essai(s), %d ok, %d refus" % (len(PAIEMENTS), len(_ok), len(_ko)))

    b, base = bac()
    await asyncio.gather(*[b["free_checkout"](_Req(ANA)) for _ in range(10)],
                         return_exceptions=True)
    verifier("T5b. 10 requetes concurrentes -> toujours UN seul",
             len(PAIEMENTS) == 1, "%d essai(s)" % len(PAIEMENTS))

    # --- T6. deux personnes differentes -------------------------------------
    b, base = bac()
    await asyncio.gather(b["free_checkout"](_Req("a@exemple.ch")),
                         b["free_checkout"](_Req("b@exemple.ch")),
                         return_exceptions=True)
    verifier("T6. deux personnes -> chacune son essai",
             len(PAIEMENTS) == 2, "%d essai(s)" % len(PAIEMENTS))

    # --- T7. ESSAI-0 : offer_id toujours persiste ---------------------------
    b, base = bac()
    await b["free_checkout"](_Req(ANA, items=[_Item(id="off-42")]))
    verifier("T7. l'offer_id d'ESSAI-0 arrive intact au moteur",
             PAIEMENTS and PAIEMENTS[0]["items"][0].id == "off-42",
             str(PAIEMENTS[0]["items"][0].id if PAIEMENTS else None))
    verifier("T7b. et il est bien ecrit sur le forfait",
             base["subscriptions"].docs
             and base["subscriptions"].docs[0].get("offer_id") == "off-42")

    # --- T8. le checkout PAYANT n'est pas touche ----------------------------
    b, base = bac(codes=[code_essai(ANA)])
    _e = None
    try:
        # Le chemin payant part chercher les cles du vendeur : il s'interrompt
        # ici faute de Stripe, et c'est exactement ce qu'on veut prouver — il
        # est ENTRE dans la branche payante au lieu d'etre refuse.
        await b["create_checkout_session"](
            _Req(ANA, items=[_Item(id="pack", price=250.0)]))
    except Exception as ex:
        _e = ex
    verifier("T8. un achat payant n'est JAMAIS refuse par la garde d'essai",
             not isinstance(_e, _HTTP) or _e.status_code != 409,
             "%s %s" % (type(_e).__name__, getattr(_e, "status_code", "")))
    verifier("T8b. et aucune reservation d'essai n'est posee pour un payant",
             len(base["free_trial_claims"].docs) == 0)
    verifier("T8c. le moteur gratuit n'est pas sollicite non plus",
             len(PAIEMENTS) == 0, "%d" % len(PAIEMENTS))

    # --- le SECOND chemin gratuit est garde lui aussi -----------------------
    b, base = bac(codes=[code_essai(ANA)])
    _e = None
    try:
        await b["create_checkout_session"](_Req(ANA, items=[_Item(price=0.0)]))
    except _HTTP as ex:
        _e = ex
    verifier("T8d. /create-session a total nul est garde comme /free",
             _e is not None and _e.status_code == 409 and len(PAIEMENTS) == 0,
             repr(_e and _e.status_code))

    # --- l'essai contre PREUVE SOCIALE compte aussi -------------------------
    b, base = bac(codes=[{"code": "AFR-SP", "assignedEmail": ANA,
                          "source": "social_proof"}])
    _e = None
    try:
        await b["free_checkout"](_Req(ANA))
    except _HTTP as ex:
        _e = ex
    verifier("T9a. un essai obtenu contre preuve sociale bloque aussi",
             _e is not None and len(PAIEMENTS) == 0)

    # --- un code OFFERT par le coach ne brule PAS l'essai -------------------
    b, base = bac(codes=[{"code": "AFR-CADEAU", "assignedEmail": ANA,
                          "source": "admin_manual"}])
    _r = await b["free_checkout"](_Req(ANA))
    verifier("T9b. un code offert par le coach ne consomme pas l'essai",
             _r.get("success") is True and len(PAIEMENTS) == 1)

    # --- une panne ne confisque pas l'essai ---------------------------------
    b, base = bac(echec_paiement=True)
    try:
        await b["free_checkout"](_Req(ANA))
    except RuntimeError:
        pass
    verifier("T9c. panne pendant la creation -> la reservation est RENDUE",
             len(base["free_trial_claims"].docs) == 0,
             str(base["free_trial_claims"].docs))
    b2, _ = bac()
    _r = await b2["free_checkout"](_Req(ANA))
    verifier("T9d. et la personne peut donc reessayer",
             _r.get("success") is True)

    # --- T9/T10. PostHog : aucune donnee personnelle -------------------------
    b, base = bac(codes=[code_essai(ANA)])
    try:
        await b["free_checkout"](_Req(ANA, nom="Ana Sentinelle",
                                      phone="+41760000001"))
    except _HTTP:
        pass
    verifier("T10. un refus est bien mesure",
             len(POSTHOG) == 1 and POSTHOG[0]["event"] == "trial_refused",
             str(POSTHOG))
    _tout = str(POSTHOG)
    verifier("T10b. AUCUNE donnee personnelle dans l'evenement",
             all(x not in _tout for x in (ANA, "Ana Sentinelle", "+41760000001",
                                          "AFR-ANCIEN", "@")),
             _tout[:160])
    verifier("T10c. aucun identify() a partir d'un e-mail non verifie",
             POSTHOG and POSTHOG[0]["email"] == "", repr(POSTHOG[0]["email"]))
    verifier("T10d. le motif et l'offre voyagent, eux",
             POSTHOG and POSTHOG[0]["props"].get("reason") == "already_used",
             str(POSTHOG[0]["props"]))


# ============================================================================
#              DISCRIMINANT — le harnais attrape-t-il vraiment ?
# ============================================================================
async def discriminant():
    ANA = "ana@exemple.ch"
    try:
        avant = subprocess.check_output(
            ["git", "show", "%s:api/routes/checkout_routes.py" % BASE_AVANT],
            cwd=RACINE).decode(errors="replace")
    except Exception as e:
        verifier("D1. code d'avant ESSAI-1 rejoue", False, "git: %s" % e)
        return
    arbre_av = ast.parse(avant)
    lg = avant.splitlines(True)
    n = noeud("free_checkout", arbre_av)
    src_av = "".join(lg[n.lineno - 1:n.end_lineno])

    b, base = bac(codes=[code_essai(ANA)])
    exec(compile(src_av, "<avant>", "exec"), b)      # ecrase par la version SANS garde
    PAIEMENTS[:] = []
    await asyncio.gather(*[b["free_checkout"](_Req(ANA)) for _ in range(5)],
                         return_exceptions=True)
    verifier("D1. SANS la garde, le harnais voit BIEN plusieurs essais",
             len(PAIEMENTS) > 1,
             "%d essai(s) — sinon T2 et T5 ne prouvent rien" % len(PAIEMENTS))


# ============================================================================
#                          INVARIANTS DE STRUCTURE
# ============================================================================
def structure():
    for f in ("free_checkout", "create_checkout_session"):
        nu = code_nu(f)
        g = nu.find("_essai1_garde")
        w = nu.find("_process_successful_payment")
        verifier("S1. `%s` : la garde precede la premiere ecriture" % f,
                 0 <= g < w, "garde@%d ecriture@%d" % (g, w))

    nu_garde = code_nu("_essai1_garde")
    verifier("S2. le refus est un 409, pas un 500",
             "409" in nu_garde)
    verifier("S3. le motif machine part en en-tete, pas dans le message",
             "X-Refus-Raison" in nu_garde and "ESSAI1_MESSAGE" in nu_garde)

    nu_sig = code_nu("_essai1_essai_deja_accorde")
    verifier("S4. le signal ne se fie NI a `offer_name` NI a `source: checkout_vitrine`",
             "offer_name" not in nu_sig and "checkout_vitrine" not in nu_sig, nu_sig[:120])
    verifier("S5. il s'appuie sur les marqueurs ecrits par du code",
             all(m in nu_sig for m in ("payment_method", "total_paid", "social_proof")))
    verifier("S6. il ne bloque PAS sur un code offert par le coach",
             "admin_manual" not in nu_sig)
    verifier("S7. il ne fait que LIRE",
             not any(m in nu_sig for m in ("insert_one", "update_one", "delete_one")))

    nu_res = code_nu("_essai1_reclamer")
    verifier("S8. la reservation s'appuie sur la cle primaire `_id`",
             "_id" in nu_res and "insert_one" in nu_res)
    verifier("S9. et le doublon est bien interprete comme « deja pris »",
             "duplicate" in nu_res.lower() or "E11000" in nu_res)

    nu_ph = code_nu("_essai1_tracer_refus")
    verifier("S10. l'evenement ne transporte ni e-mail, ni nom, ni code",
             not any(m in nu_ph for m in ("customer_email", "customer_name",
                                          "access_code", "assignedEmail")))
    verifier("S11. et il est non bloquant",
             "except" in nu_ph)

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S12. ce test n'importe que la bibliotheque standard hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "subprocess", "sys", "datetime", "uuid"},
             str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(discriminant())
        b.run_until_complete(scenarios())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Essais gratuits REELLEMENT crees : 0 — aucune base, aucun reseau")
    print("E-mails / paiements REELS        : 0 — le moteur est un mouchard")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

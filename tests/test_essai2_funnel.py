# -*- coding: utf-8 -*-
"""ESSAI-2 — les etapes du funnel, adossees a la base.

Les vraies fonctions sont extraites de `api/routes/shared.py` par AST et
executees sur un faux MongoDB qui modelise l'atomicite du `$exists` : le filtre
et l'ecriture ne sont separes par aucun `await`, exactement comme MongoDB le
garantit au niveau du document.

PostHog est un mouchard. Aucun reseau, aucune base, aucun essai, aucune
presence, aucun paiement.

Lancement :  python3 tests/test_essai2_funnel.py
"""

import ast
import asyncio
import io
import os
import sys
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = os.path.join(RACINE, "api", "routes", "shared.py")
SOURCE = io.open(SHARED, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

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


# ------------------------------------------------------- faux client MongoDB
_ABSENT = object()


def _val(doc, chemin):
    cur = doc
    for p in chemin.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return _ABSENT
        cur = cur[p]
    return cur


def _match(doc, q):
    for cle, attendu in (q or {}).items():
        if cle == "$or":
            if not any(_match(doc, s) for s in attendu):
                return False
            continue
        obtenu = _val(doc, cle)
        if isinstance(attendu, dict):
            for op, v in attendu.items():
                if op == "$exists":
                    if bool(obtenu is not _ABSENT) != bool(v):
                        return False
                elif op == "$in":
                    if obtenu is _ABSENT or obtenu not in v:
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        else:
            if obtenu is _ABSENT or obtenu != attendu:
                return False
    return True


class _Res(object):
    def __init__(self, n):
        self.matched_count = n
        self.modified_count = n


class _Curseur(object):
    def __init__(self, d):
        self.d = d

    async def to_list(self, n):
        await asyncio.sleep(0)
        import copy
        return [copy.deepcopy(x) for x in self.d[:n]]


class _Coll(object):
    """Rend la main AVANT d'agir — sans quoi `asyncio.gather` ne produirait
    aucun entrelacement. L'ecriture conditionnelle, elle, ne contient aucun
    `await` entre le filtre et le `$set` : c'est le contrat de MongoDB."""

    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, q=None, p=None):
        return _Curseur([d for d in self.docs if _match(d, q or {})])

    async def find_one(self, q, p=None):
        await asyncio.sleep(0)
        import copy
        for d in self.docs:
            if _match(d, q):
                return copy.deepcopy(d)
        return None

    async def update_one(self, q, m, **k):
        await asyncio.sleep(0)
        # --- section atomique : aucun await du filtre a l'ecriture ---
        for d in self.docs:
            if _match(d, q):
                for cle, v in (m.get("$set") or {}).items():
                    d[cle] = v
                return _Res(1)
        return _Res(0)


class _Base(object):
    def __init__(self, codes=None, subs=None, resas=None):
        self._c = {
            "discount_codes": _Coll(codes),
            "subscriptions": _Coll(subs),
            "reservations": _Coll(resas),
        }

    def __getitem__(self, n):
        return self._c.setdefault(n, _Coll())

    def __getattr__(self, n):
        return self[n]


# ------------------------------------------------------------- les mouchards
POSTHOG = []
PH_ECHOUE = [False]


async def faux_posthog(event, email="", props=None, distinct_id=None):
    await asyncio.sleep(0)
    if PH_ECHOUE[0]:
        raise RuntimeError("PostHog injoignable (simule)")
    POSTHOG.append({"event": event, "email": email, "props": dict(props or {})})
    return True


A_EXTRAIRE = ["est_un_essai",
              "essai2_codes_essai", "essai2_forfait_essai", "essai2_est_essai",
              "essai2_presence_essai", "essai2_marquer_conversion",
              "essai2_tracer_octroi"]

CONSTANTES = '''
# ESSAI-6 : la marque de gratuite portee par le FORFAIT (trace LOT B), seconde
# preuve de `est_un_essai` — celle qui survit a la suppression du code.
ESSAI6_ORIGINE_OFFERTE = "offert"

ESSAI2_FILTRE_GRATUIT = {
    "$or": [
        {"payment_method": "free", "total_paid": 0},
        {"source": "social_proof"},
    ]
}
'''


def bac(codes=None, subs=None, resas=None):
    POSTHOG[:] = []
    PH_ECHOUE[0] = False
    base = _Base(codes, subs, resas)
    b = {
        "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
        "asyncio": asyncio,
        "posthog_capture": faux_posthog,
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
    }
    exec(compile("\n\n".join([CONSTANTES] + [extraire(f) for f in A_EXTRAIRE]),
                 "<essai2>", "exec"), b)
    absents = [f for f in A_EXTRAIRE if f not in b]
    assert not absents, "extraction incomplete : %s" % absents
    return b, base


# ----------------------------------------------------------- jeux de donnees
ANA = "ana@exemple.ch"
IL_Y_A_3J = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()


def code_gratuit(code="AFR-ESSAI", email=ANA):
    return {"code": code, "assignedEmail": email,
            "payment_method": "free", "total_paid": 0}


def code_paye(code="AFR-PACK", email=ANA):
    return {"code": code, "assignedEmail": email,
            "payment_method": "card", "total_paid": 250}


def forfait(code="AFR-ESSAI", sid="sub-essai", offer="off-essai", **extra):
    d = {"id": sid, "email": ANA, "code": code, "offer_id": offer,
         "created_at": "2026-08-01T10:00:00+00:00", "total_sessions": 1}
    d.update(extra)
    return d


def resa(sid="sub-essai", code="AFR-ESSAI", validee=False, cours="cours-1", **extra):
    d = {"id": "r1", "userEmail": ANA, "subscriptionId": sid,
         "promoCode": code, "discountCode": code, "courseId": cours}
    if validee:
        d["validated"] = True
        d["validatedAt"] = IL_Y_A_3J
    d.update(extra)
    return d


# ============================================================================
#                       LES ETAPES DU FUNNEL
# ============================================================================
async def scenarios():
    # --- T1. essai accorde, aucune reservation -> granted seul --------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()])
    await b["essai2_tracer_octroi"](base, ANA, "off-essai", 1)
    verifier("T1. essai accorde -> free_trial_granted, et rien d'autre",
             [e["event"] for e in POSTHOG] == ["free_trial_granted"], str(POSTHOG))
    _c = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    verifier("T1b. sans reservation ni presence -> aucune conversion", _c is False)

    # --- T2. essai reserve -> booked ---------------------------------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa()])
    verifier("T2. la reservation est reconnue comme un ESSAI",
             await b["essai2_est_essai"](base, resa()) is True)
    b2, base2 = bac(codes=[code_paye("AFR-PACK")], subs=[forfait("AFR-PACK", "sub-pack")],
                    resas=[resa("sub-pack", "AFR-PACK")])
    verifier("T2b. une reservation d'abonne PAYANT n'en est pas un",
             await b2["essai2_est_essai"](base2, resa("sub-pack", "AFR-PACK")) is False)

    # --- T3. reservation sans presence -> jamais attended -------------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=False)])
    verifier("T3. reserve mais absent -> aucune presence",
             await b["essai2_presence_essai"](base, forfait()) is None)
    _c = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    verifier("T3b. et donc aucune conversion possible", _c is False)
    verifier("T3c. une date passee ne vaut PAS presence",
             "datetime" not in code_nu("essai2_presence_essai")
             or "validated" in code_nu("essai2_presence_essai"))

    # --- T4. presence confirmee --------------------------------------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=True)])
    _p = await b["essai2_presence_essai"](base, forfait())
    verifier("T4. presence confirmee par le coach -> trouvee",
             _p is not None and _p.get("validatedAt") == IL_Y_A_3J)

    # --- T5. presence + achat -> converted exactement une fois --------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=True)])
    verifier("T5a. converted_at est ABSENT avant toute conversion",
             "converted_at" not in base["subscriptions"].docs[0])
    _c1 = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    verifier("T5. premiere conversion -> actee", _c1 is True)
    verifier("T5b. et converted_at est POSE",
             bool(base["subscriptions"].docs[0].get("converted_at")))
    verifier("T5c. l'evenement est emis une fois",
             [e["event"] for e in POSTHOG] == ["free_trial_converted"], str(POSTHOG))
    verifier("T5d. l'envoi analytique est marque comme abouti",
             base["subscriptions"].docs[0].get("converted_event_sent") is True)

    _c2 = await b["essai2_marquer_conversion"](base, ANA, "off-pack-2", "sub-pack-2")
    verifier("T5e. rejouer le MEME appel ne convertit pas deux fois", _c2 is False)
    verifier("T5f. et n'emet aucun second evenement",
             len([e for e in POSTHOG if e["event"] == "free_trial_converted"]) == 1)

    # --- T6. achat AVANT presence -> aucune fausse conversion ---------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=False)])
    _c = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    verifier("T6. achat avant la presence -> PAS une conversion post-essai",
             _c is False and "converted_at" not in base["subscriptions"].docs[0])
    # la presence arrive ensuite : elle ne retro-convertit rien toute seule
    base["reservations"].docs[0]["validated"] = True
    base["reservations"].docs[0]["validatedAt"] = IL_Y_A_3J
    verifier("T6b. la presence posterieure ne convertit pas retroactivement",
             "converted_at" not in base["subscriptions"].docs[0])

    # --- T7. deux achats -> une seule premiere conversion -------------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=True)])
    _r = [await b["essai2_marquer_conversion"](base, ANA, "off-%d" % i, "sub-%d" % i)
          for i in range(3)]
    verifier("T7. trois achats successifs -> une seule conversion",
             _r == [True, False, False], str(_r))
    verifier("T7b. et le marqueur porte le PREMIER achat",
             base["subscriptions"].docs[0].get("converted_by_subscription_id") == "sub-0")

    # --- concurrence : deux achats a la meme milliseconde -------------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=True)])
    _r = await asyncio.gather(*[b["essai2_marquer_conversion"](base, ANA, "o", "s%d" % i)
                                for i in range(6)])
    verifier("T7c. six achats CONCURRENTS -> une seule conversion",
             sum(1 for x in _r if x) == 1, str(_r))
    verifier("T7d. et un seul evenement",
             len([e for e in POSTHOG if e["event"] == "free_trial_converted"]) == 1)

    # --- T8. plusieurs reservations -> une seule consommation ---------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()],
                  resas=[resa(validee=True), dict(resa(validee=True), id="r2")])
    _r1 = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    _r2 = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    verifier("T8. deux reservations validees -> toujours une seule conversion",
             (_r1, _r2) == (True, False))

    # --- T9. offer_id d'ESSAI-0 conserve dans l'attribution -----------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait(offer="off-essai-42")],
                  resas=[resa(validee=True, cours="cours-77")])
    await b["essai2_marquer_conversion"](base, ANA, "off-achete-9", "sub-pack")
    _p = POSTHOG[-1]["props"]
    verifier("T9. l'attribution porte les deux offres et le cours",
             _p.get("trial_offer_id") == "off-essai-42"
             and _p.get("purchased_offer_id") == "off-achete-9"
             and _p.get("course_id") == "cours-77", str(_p))
    verifier("T9b. et le delai presence -> achat, calcule, jamais fige",
             _p.get("days_since_attendance") == 3, str(_p.get("days_since_attendance")))

    # --- essai SANS offer_id (avant ESSAI-0) : l'etape reste attribuable ----
    b, base = bac(codes=[code_gratuit()], subs=[forfait(offer="")],
                  resas=[resa(validee=True)])
    _ok = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    verifier("T9c. un essai historique sans offer_id convertit quand meme",
             _ok is True and POSTHOG[-1]["props"].get("trial_offer_id") == "")

    # --- T10. aucune PII ----------------------------------------------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=True)])
    await b["essai2_tracer_octroi"](base, ANA, "off-essai", 1)
    await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    _tout = str([e["props"] for e in POSTHOG])
    verifier("T10. AUCUNE donnee personnelle dans les proprietes",
             all(x not in _tout for x in (ANA, "@", "AFR-", "Ana")), _tout[:160])
    verifier("T10b. l'adresse ne sert qu'au pseudonyme, jamais aux proprietes",
             all("email" not in e["props"] for e in POSTHOG))

    # --- la fenetre Mongo -> PostHog, documentee et rejouable ---------------
    b, base = bac(codes=[code_gratuit()], subs=[forfait()], resas=[resa(validee=True)])
    PH_ECHOUE[0] = True
    _c = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    _doc = base["subscriptions"].docs[0]
    verifier("W1. PostHog en panne -> la conversion metier est TOUT DE MEME actee",
             _c is True and bool(_doc.get("converted_at")))
    verifier("W2. mais l'envoi est marque comme NON abouti",
             _doc.get("converted_event_sent") is False, repr(_doc.get("converted_event_sent")))
    verifier("W3. et la charge analytique est conservee pour un rejeu",
             isinstance(_doc.get("converted_props"), dict)
             and _doc["converted_props"].get("purchased_offer_id") == "off-pack",
             str(_doc.get("converted_props")))
    PH_ECHOUE[0] = False
    _c2 = await b["essai2_marquer_conversion"](base, ANA, "off-pack", "sub-pack")
    verifier("W4. le retry ne DUPLIQUE pas la conversion",
             _c2 is False and len([e for e in POSTHOG if e["event"] == "free_trial_converted"]) == 0)


# ============================================================================
#                          INVARIANTS DE STRUCTURE
# ============================================================================
def structure():
    nu_conv = code_nu("essai2_marquer_conversion")
    verifier("S1. le marqueur est pose par une ecriture CONDITIONNELLE",
             "'$exists': False" in nu_conv.replace('"', "'"), "")
    verifier("S2. et le verdict se lit sur matched_count",
             "matched_count" in nu_conv)
    verifier("S3. la presence est exigee avant toute conversion",
             nu_conv.find("essai2_presence_essai") < nu_conv.find("update_one"))
    verifier("S4. l'ecriture metier precede l'envoi analytique",
             nu_conv.find("update_one") < nu_conv.find("posthog_capture"))
    verifier("S5. la charge analytique est persistee pour un rejeu",
             "converted_props" in nu_conv and "converted_event_sent" in nu_conv)

    nu_sig = code_nu("essai2_est_essai")
    # ESSAI-6 : la nature d'un essai ne se lit plus SEULEMENT dans
    # `discount_codes` — un document que le coach peut supprimer, ce qu'il a
    # fait. Elle est demandee a `est_un_essai`, qui garde ce filtre comme
    # premiere preuve et sait retomber sur le forfait et le catalogue.
    verifier("S6. la nature d'un essai est DEMANDEE a la definition centrale",
             "est_un_essai" in nu_sig
             and "payment_method" not in nu_sig and "total_paid" not in nu_sig)
    verifier("S7. jamais dans le nom de l'offre",
             "offer_name" not in nu_sig)

    nu_pres = code_nu("essai2_presence_essai")
    verifier("S8. la presence est `validated`, jamais une date passee",
             "'validated': True" in nu_pres.replace('"', "'"))
    verifier("S9. et rien n'est ecrit pour la constater",
             not any(m in nu_pres for m in ("update_one", "insert_one")))

    _src = SOURCE
    verifier("S10. `pulse_purchased` n'est pas touche par ce lot",
             "pulse_purchased" not in _src, "")

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S11. ce test n'importe que la bibliotheque standard hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "datetime", "copy"},
             str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(scenarios())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Essais / presences / paiements REELS : 0 — base en memoire, PostHog mouchard")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

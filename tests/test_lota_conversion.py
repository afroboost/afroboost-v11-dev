# -*- coding: utf-8 -*-
"""LOT A — L'APRES-ESSAI : CE QU'ON PROPOSE, ET CE QU'ON REFUSE.

Les VRAIES fonctions sont extraites par AST de `api/routes/shared.py` et de
`api/server.py`, puis executees sur un faux MongoDB qui modelise l'atomicite du
`$exists` : le filtre et l'ecriture ne sont separes par aucun `await`, exactement
comme MongoDB le garantit au niveau du document.

La garde A1/A1b n'est PAS simulee : `_a1b_occurrences_reelles` est extraite du
vrai `api/routes/reservation_routes.py` et branchee sur la meme fausse base. Un
cours historique est donc ecarte ici par le code qui l'ecarte en production.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE DE PRODUCTION, AUCUN PAIEMENT.

Lancement :  python3 tests/test_lota_conversion.py
"""

import ast
import asyncio
import copy
import io
import os
import re
import sys
import types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TZ_CH = timezone(timedelta(hours=2))
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


class _Source(object):
    def __init__(self, chemin):
        self.chemin = chemin
        self.texte = io.open(chemin, encoding="utf-8").read()
        self.arbre = ast.parse(self.texte)
        self.lignes = self.texte.splitlines(True)

    def extraire(self, nom):
        for n in ast.walk(self.arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
                return "".join(self.lignes[n.lineno - 1:n.end_lineno])
        raise AssertionError("fonction introuvable dans %s : %s" % (self.chemin, nom))

    def constante(self, nom):
        for n in ast.walk(self.arbre):
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == nom:
                return "".join(self.lignes[n.lineno - 1:n.end_lineno])
        raise AssertionError("constante introuvable dans %s : %s" % (self.chemin, nom))


SHARED = _Source(os.path.join(RACINE, "api", "routes", "shared.py"))
RESA = _Source(os.path.join(RACINE, "api", "routes", "reservation_routes.py"))
SERVEUR = _Source(os.path.join(RACINE, "api", "server.py"))
CAISSE_SRC = _Source(os.path.join(RACINE, "api", "routes", "checkout_routes.py"))


# ═════════════════════════════════ Mongo factice ════════════════════════════
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
                elif op == "$ne":
                    if obtenu is not _ABSENT and obtenu == v:
                        return False
                elif op == "$regex":
                    if not isinstance(obtenu, str):
                        return False
                    _f = re.I if "i" in (attendu.get("$options") or "") else 0
                    if not re.search(v, obtenu, _f):
                        return False
                elif op == "$options":
                    continue
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

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        await asyncio.sleep(0)
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
    def __init__(self, **collections):
        self._c = {n: _Coll(v) for n, v in collections.items()}

    def __getitem__(self, n):
        return self._c.setdefault(n, _Coll())

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return self[n]


# ═══════════════════════════════ les mouchards ══════════════════════════════
POSTHOG = []
CAISSE = []
CONVERSIONS = []
CONV_ERREUR = [False]


async def faux_posthog(event, email="", props=None, distinct_id=None):
    await asyncio.sleep(0)
    POSTHOG.append({"event": event, "email": email, "props": dict(props or {})})
    return True


class _HTTPException(Exception):
    def __init__(self, status_code=400, detail=""):
        self.status_code = status_code
        self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))


class _Journal(object):
    def __getattr__(self, _):
        return lambda *a, **k: None


class _Requete(object):
    def __init__(self, corps):
        self._corps = corps

    async def json(self):
        await asyncio.sleep(0)
        if self._corps is None:
            raise ValueError("corps illisible")
        return self._corps


# ═══════════════════════ construction des namespaces ════════════════════════
# ESSAI-6 (P1-a) : `conv_etat` ne relit plus le code lui-meme — elle demande a
# `est_un_essai`, la definition centrale, qui sait aussi reconnaitre un essai
# dont le `discount_codes` a ete supprime. On charge donc la VRAIE fonction ;
# la recopier ici rendrait ce banc aveugle a ses evolutions.
# P1-c : `conv_offres_premier_achat` delegue desormais deux decisions a des
# aides dediees — retirer ce que la caisse refuserait, et designer LA
# recommandation. Ce sont des DEPENDANCES REELLES : sans elles dans cet espace,
# la fonction leve un NameError et tout le banc tombe sur une panne de banc.
# Elles arrivent avec leurs propres dependances LOT R / LOT 3b, chargees ici
# pour la meme raison : ce banc doit executer le VRAI code, pas une copie.
CONV = ["normaliser_email", "est_un_essai", "conv_presence_reelle",
        "lotr_etat_adhesion", "lotr_verdict_recharge",
        "lotr_seances_encore_utilisables", "lot3b_adhesions",
        "p1c_retirer_inachetables", "p1c_index_recommande",
        "conv_offres_premier_achat",
        "conv_offre_autorisee", "conv_etat", "conv_marquer_vue"]

A1B = ["_a0_maintenant_ch", "_a0_horodatage", "_a1_jour_js",
       "_a1_a_lieu_aujourdhui", "_a1b_occurrences_reelles"]

ROUTES = ["_conv_contexte", "get_conversion_apres_essai", "post_conversion_checkout"]


def _module(nom, **attrs):
    m = types.ModuleType(nom)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[nom] = m
    return m


def bac(codes=None, subs=None, resas=None, offers=None, courses=None,
        caisse_erreur=None):
    """Monte une base factice et rend (namespace shared, namespace routes, base)."""
    POSTHOG[:] = []
    CAISSE[:] = []
    CONVERSIONS[:] = []
    CONV_ERREUR[0] = False
    base = _Base(discount_codes=codes or [], subscriptions=subs or [],
                 reservations=resas or [], offers=offers or [],
                 courses=courses or [])

    # --- la VRAIE garde A1b, sur la meme base -------------------------------
    ns_a1b = {"db": base, "re": re, "datetime": datetime, "timezone": timezone,
              "timedelta": timedelta, "logger": _Journal(), "asyncio": asyncio}
    exec(compile(RESA.constante("A1_JOURS_JS"), "<a1>", "exec"), ns_a1b)
    for f in A1B:
        exec(compile(RESA.extraire(f), "<a1b>", "exec"), ns_a1b)
    _module("api")
    _module("api.routes")
    _module("api.routes.reservation_routes",
            _a1b_occurrences_reelles=ns_a1b["_a1b_occurrences_reelles"])

    # --- le VRAI moteur LOT A ----------------------------------------------
    ns = {"datetime": datetime, "timezone": timezone, "timedelta": timedelta,
          "asyncio": asyncio, "posthog_capture": faux_posthog,
          "logger": _Journal()}
    exec(compile(SHARED.constante("ESSAI2_FILTRE_GRATUIT"), "<lota>", "exec"), ns)
    exec(compile(SHARED.constante("B_DEVISE_DEFAUT"), "<lota>", "exec"), ns)
    # P1-c : les constantes dont dependent les aides LOT R / LOT 3b chargees
    # ci-dessous. Sans elles, le banc tombe sur un NameError — une panne de
    # banc, pas une regression du code.
    for _c in ("LOT3B_PREFIXE", "LOTR_PREFIXE", "LOTR_CHAMP_PROTECTION",
               "LOTR_REFUS_SEANCES", "LOTR_REFUS_SANS_ADHESION",
               "LOTR_REFUS_ADHESION_EXPIREE", "LOTR_REFUS_INDETERMINE"):
        exec(compile(SHARED.constante(_c), "<lota>", "exec"), ns)
    for c in ("CONV_INELIGIBLE", "CONV_OUVERTE", "CONV_TERMINEE",
              "ESSAI6_ORIGINE_OFFERTE"):
        exec(compile(SHARED.constante(c), "<lota>", "exec"), ns)
    for f in CONV:
        exec(compile(SHARED.extraire(f), "<lota>", "exec"), ns)
    absents = [f for f in CONV if f not in ns]
    assert not absents, "extraction incomplete : %s" % absents

    async def _lire(db, code, email=None, filtre_supplementaire=None):
        return await base.subscriptions.find_one(
            {"code": {"$regex": "^%s$" % re.escape((code or "").strip().upper()),
                      "$options": "i"}})

    async def _marquer(db_, email, purchased_offer_id="", purchased_sub_id=""):
        await asyncio.sleep(0)
        CONVERSIONS.append({"email": email, "offer_id": purchased_offer_id,
                            "sub_id": purchased_sub_id})
        if CONV_ERREUR[0]:
            raise RuntimeError("moteur indisponible (simule)")
        return True

    _module("api.routes.shared", lire_abonnement_par_code=_lire,
            posthog_capture=faux_posthog, essai2_marquer_conversion=_marquer,
            **{f: ns[f] for f in CONV},
            CONV_INELIGIBLE=ns["CONV_INELIGIBLE"], CONV_OUVERTE=ns["CONV_OUVERTE"],
            CONV_TERMINEE=ns["CONV_TERMINEE"])

    # --- le moteur de caisse EXISTANT, remplace par un mouchard -------------
    class _Item(object):
        def __init__(self, **kw):
            self.__dict__.update(kw)

    class _Req(object):
        def __init__(self, **kw):
            self.__dict__.update(kw)

    async def _caisse(req):
        await asyncio.sleep(0)
        CAISSE.append(req)
        if caisse_erreur:
            raise caisse_erreur
        return {"success": True, "payment_url": "https://stripe.test/session",
                "transaction_id": "txn_test"}

    _module("api.routes.checkout_routes", create_checkout_session=_caisse,
            CreateCheckoutRequest=_Req, CheckoutItem=_Item)

    # --- les VRAIES routes --------------------------------------------------
    ns_r = {"db": base, "re": re, "datetime": datetime, "timezone": timezone,
            "logger": _Journal(), "HTTPException": _HTTPException,
            "SUPER_ADMIN_EMAILS": ["admin@test"], "Request": object,
            "_v184_public_origin": lambda: "https://afroboost.test",
            "api_router": type("R", (), {
                "get": staticmethod(lambda *a, **k: (lambda f: f)),
                "post": staticmethod(lambda *a, **k: (lambda f: f))})()}
    for f in ROUTES:
        exec(compile(SERVEUR.extraire(f), "<routes>", "exec"), ns_r)
    return ns, ns_r, base


# ═════════════════════════════ jeux de donnees ══════════════════════════════
ANA = "ana@exemple.ch"
COACH = "admin@test"


def _jour(decalage=0):
    return (datetime.now(TZ_CH) + timedelta(days=decalage)).strftime("%Y-%m-%d")


def _js(decalage=0):
    """Jour de la semaine en convention JAVASCRIPT (Dim=0), comme en base."""
    return (datetime.now(TZ_CH) + timedelta(days=decalage)).isoweekday() % 7


def code_gratuit(code="AFR-ESSAI", email=ANA, coach_id=COACH):
    return {"code": code, "assignedEmail": email, "coach_id": coach_id,
            "payment_method": "free", "total_paid": 0}


def code_paye(code="AFR-PACK", email=ANA):
    return {"code": code, "assignedEmail": email, "coach_id": COACH,
            "payment_method": "card", "total_paid": 250}


def forfait(code="AFR-ESSAI", sid="sub-essai", **extra):
    d = {"id": sid, "email": ANA, "name": "Ana", "whatsapp": "+41760000000",
         "code": code, "offer_id": "off-essai", "coach_id": COACH,
         "created_at": "2026-08-01T10:00:00+00:00", "total_sessions": 1}
    d.update(extra)
    return d


def resa(validee=False, jour=0, cours="cours-1", sid="sub-essai",
         code="AFR-ESSAI", **extra):
    d = {"id": "r1", "reservationCode": "AFRO-TEST", "userEmail": ANA,
         "subscriptionId": sid, "promoCode": code, "discountCode": code,
         "courseId": cours, "courseName": "Silent Mercredi",
         "datetime": _jour(jour) + "T18:30:00"}
    if validee:
        d["validated"] = True
        d["validatedAt"] = (datetime.now(timezone.utc) + timedelta(days=jour)).isoformat()
    d.update(extra)
    return d


def cours_recurrent(cid="cours-1", jour=0, **extra):
    """Un cours hebdomadaire qui a lieu le jour vise. `weekday` en convention
    JAVASCRIPT (Dim=0), comme en base."""
    d = {"id": cid, "name": "Silent Mercredi", "weekday": _js(jour),
         "time": "18:30", "visible": True, "archived": False, "coach_id": COACH}
    d.update(extra)
    return d


def offre(oid, nom, prix, autorisee=True, **extra):
    d = {"id": oid, "name": nom, "price": prix, "coach_id": COACH,
         "visible": True, "first_purchase_eligible": autorisee}
    d.update(extra)
    return d


PULSE = lambda **k: offre("off-pulse", "PULSE x10", 250, pack_sessions=10, position=1, **k)
UNITE = lambda **k: offre("off-unite", "Cours à l'unité", 30, pack_sessions=1, position=2, **k)
def MEMBRES(autorisee=False, **k):
    return offre("off-membres", "Membres / renouvellement", 150,
                 autorisee=autorisee, pack_sessions=10, position=0, **k)


def catalogue_complet():
    """Le catalogue vise au lancement : deux offres declarees, l'adhesion non."""
    return [PULSE(), UNITE(), MEMBRES()]


def base_essai_effectue(**kw):
    """Le cas nominal : essai gratuit, seance d'aujourd'hui, presence validee."""
    d = dict(codes=[code_gratuit()], subs=[forfait()],
             resas=[resa(validee=True)], courses=[cours_recurrent()],
             offers=catalogue_complet())
    d.update(kw)
    return bac(**d)


# ════════════════════════════════ scenarios ═════════════════════════════════
async def scenarios():
    # ─────────────────── 1. ELIGIBILITE : CE QUI OUVRE, CE QUI N'OUVRE PAS ──
    # T1. Essai RESERVE mais non effectue -> refus.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=False, jour=1)],
                        courses=[cours_recurrent(jour=1)], offers=catalogue_complet())
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T1. essai reserve mais non effectue -> conversion refusee",
             e["state"] == "not_eligible" and e["reason"] == "not_attended"
             and e["offers"] == [], str(e))

    # T2. Essai EFFECTUE -> conversion ouverte.
    ns, nsr, base = base_essai_effectue()
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T2. essai effectue -> conversion autorisee",
             e["state"] == "open" and e["eligible"] is True and len(e["offers"]) == 2,
             str(e))

    # T13. Ancien client PAYANT : ce n'est pas un essai, rien ne s'ouvre.
    ns, nsr, base = bac(codes=[code_paye()], subs=[forfait(code="AFR-PACK")],
                        resas=[resa(validee=True, code="AFR-PACK")],
                        courses=[cours_recurrent()], offers=catalogue_complet())
    e = await ns["conv_etat"](base, forfait(code="AFR-PACK"), COACH)
    verifier("T13. ancien client payant -> aucune conversion (pas un essai)",
             e["state"] == "not_eligible" and e["reason"] == "not_a_trial", str(e))

    # T14. Cours HISTORIQUE : la reservation est validee, mais le cours n'a plus
    #      lieu ce jour-la. C'est le residu « Diner canadien » du 19/08/2026.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)],
                        courses=[{"id": "cours-1", "name": "Dîner canadien",
                                  "date": "2026-08-09", "time": "18:30",
                                  "archived": False, "coach_id": COACH}],
                        offers=catalogue_complet())
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T14. cours historique (ponctuel passe) -> aucune conversion",
             e["state"] == "not_eligible" and e["reason"] == "not_attended", str(e))

    # T14b. Cours ARCHIVE -> idem.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)],
                        courses=[cours_recurrent(archived=True)],
                        offers=catalogue_complet())
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T14b. cours archive -> aucune conversion",
             e["state"] == "not_eligible", str(e))

    # T14c. Cours SUPPRIME de la collection -> idem.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)], courses=[],
                        offers=catalogue_complet())
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T14c. cours supprime -> aucune conversion", e["state"] == "not_eligible",
             str(e))

    # T15. Occurrence RECURRENTE reelle : le cours a bien lieu ce jour-la.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True, jour=-7)],
                        courses=[cours_recurrent(jour=-7)], offers=catalogue_complet())
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T15. occurrence recurrente reelle (il y a 7 jours) -> conversion ouverte",
             e["state"] == "open", str(e))

    # T1b. Ce qui NE declenche RIEN : une reservation seule, sans presence.
    ns, nsr, base = bac(codes=[code_gratuit()],
                        subs=[forfait(remaining_sessions=0, used_sessions=1)],
                        resas=[resa(validee=False, jour=-2)],
                        courses=[cours_recurrent(jour=-2)], offers=catalogue_complet())
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T1b. compteur a zero + date passee sans presence -> aucune conversion",
             e["state"] == "not_eligible" and e["reason"] == "not_attended", str(e))

    # ─────────────────────────────── 2. LES OFFRES PROPOSEES ────────────────
    ns, nsr, base = base_essai_effectue()
    offres = await ns["conv_offres_premier_achat"](base, COACH)
    ids = [o["id"] for o in offres]
    verifier("T5. PULSE x10 configure -> visible, en premier, recommandee",
             ids[0] == "off-pulse" and offres[0]["price"] == 250.0
             and offres[0]["sessions"] == 10 and offres[0]["recommended"] is True,
             str(offres))
    verifier("T6. cours a l'unite configure -> visible",
             "off-unite" in ids and offres[1]["price"] == 30.0
             and offres[1]["recommended"] is False, str(offres))
    verifier("T7. offre Membres/renouvellement 150 non declaree -> INVISIBLE",
             "off-membres" not in ids, str(ids))
    verifier("T7b. l'ordre suit `position`, pas l'ordre d'insertion",
             ids == ["off-pulse", "off-unite"], str(ids))
    verifier("T7c. aucune donnee personnelle dans la projection des offres",
             all(not (set(o) & {"email", "whatsapp", "phone", "assignedEmail"})
                 for o in offres), str(offres))

    # T7d. L'exclusion ne tient PAS au prix : la meme offre a 150 devient
    #      visible des que le coach la declare, et PULSE disparait s'il la
    #      retire. C'est bien le champ explicite qui decide.
    ns2, _, base2 = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)], courses=[cours_recurrent()],
                        offers=[PULSE(autorisee=False), MEMBRES(autorisee=True)])
    ids2 = [o["id"] for o in await ns2["conv_offres_premier_achat"](base2, COACH)]
    verifier("T7d. l'exclusion vient du champ explicite, jamais du montant",
             ids2 == ["off-membres"], str(ids2))

    # T9. Le prix vient du serveur, a chaque lecture.
    ns, nsr, base = base_essai_effectue()
    base.offers.docs[0]["price"] = 275
    offres = await ns["conv_offres_premier_achat"](base, COACH)
    verifier("T9. prix modifie en base -> le serveur rend la nouvelle valeur",
             [o["price"] for o in offres if o["id"] == "off-pulse"] == [275.0],
             str(offres))

    # T10. Aucune offre configuree -> etat propre, aucune exception.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)], courses=[cours_recurrent()],
                        offers=[MEMBRES(), offre("x", "Autre", 90, autorisee=False)])
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T10. aucune offre declaree -> ouverte, liste vide, aucun crash",
             e["state"] == "open" and e["offers"] == [], str(e))

    # T10b. Collection d'offres totalement vide.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)], courses=[cours_recurrent()],
                        offers=[])
    e = await ns["conv_etat"](base, forfait(), COACH)
    verifier("T10b. catalogue vide -> liste vide, aucun crash",
             e["state"] == "open" and e["offers"] == [], str(e))

    # T10c. Une offre a 0 CHF declaree ne se propose pas : un ecran de
    #       conversion vend, il ne redistribue pas un second essai gratuit.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)], courses=[cours_recurrent()],
                        offers=[offre("off-gratuit", "Séance découverte", 0)])
    verifier("T10c. offre a 0 CHF declaree -> non proposee (ce serait un 2e essai)",
             await ns["conv_offres_premier_achat"](base, COACH) == [], "")

    # T10d. Le catalogue d'un AUTRE coach n'est jamais propose.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)], courses=[cours_recurrent()],
                        offers=[PULSE(coach_id="autre@coach.ch")])
    verifier("T10e. offre d'un autre coach -> non proposee",
             await ns["conv_offres_premier_achat"](base, COACH) == [], "")

    # ──────────────────── 3. IDEMPOTENCE DE `conversion_viewed` ─────────────
    # T3. Dix rafraichissements -> un seul evenement metier.
    ns, nsr, base = base_essai_effectue()
    for _ in range(10):
        f = await base.subscriptions.find_one({"id": "sub-essai"})
        await nsr["get_conversion_apres_essai"]("AFR-ESSAI")
    vues = [x for x in POSTHOG if x["event"] == "conversion_viewed"]
    verifier("T3. 10 rafraichissements -> conversion_viewed emis UNE fois",
             len(vues) == 1, str([x["event"] for x in POSTHOG]))
    doc = await base.subscriptions.find_one({"id": "sub-essai"})
    verifier("T3b. les deux dates sont posees ensemble",
             bool(doc.get("conversion_first_viewed_at"))
             and doc.get("conversion_eligible_at") == doc.get("conversion_first_viewed_at"),
             str(doc.get("conversion_first_viewed_at")))

    # T3c. Une fois la date posee, le GET n'ecrit PLUS RIEN.
    ecritures = []
    _vrai_update = base.subscriptions.update_one

    async def _espion(q, m, **k):
        ecritures.append(q)
        return await _vrai_update(q, m, **k)

    base.subscriptions.update_one = _espion
    for _ in range(5):
        await nsr["get_conversion_apres_essai"]("AFR-ESSAI")
    verifier("T3c. apres la premiere vue, le GET ne tente AUCUNE ecriture",
             ecritures == [], str(ecritures))

    # T4. Deux onglets / deux scans SIMULTANES -> un seul evenement.
    ns, nsr, base = base_essai_effectue()
    f = await base.subscriptions.find_one({"id": "sub-essai"})
    r = await asyncio.gather(ns["conv_marquer_vue"](base, f, 2),
                             ns["conv_marquer_vue"](base, f, 2),
                             ns["conv_marquer_vue"](base, f, 2))
    vues = [x for x in POSTHOG if x["event"] == "conversion_viewed"]
    verifier("T4. trois appels simultanes -> une seule prise de droit",
             sum(1 for x in r if x) == 1 and len(vues) == 1,
             "%s / %s" % (r, len(vues)))

    # T4b. Un essai NON eligible ne marque rien du tout.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=False)], courses=[cours_recurrent()],
                        offers=catalogue_complet())
    await nsr["get_conversion_apres_essai"]("AFR-ESSAI")
    doc = await base.subscriptions.find_one({"id": "sub-essai"})
    verifier("T4b. non eligible -> aucune date posee, aucun evenement",
             not doc.get("conversion_first_viewed_at") and POSTHOG == [],
             str(POSTHOG))

    # ───────────────── 4. LA GARDE DE NIVEAU 2 (falsification) ──────────────
    # T8. L'identifiant de l'offre a 150 poste directement au serveur.
    ns, nsr, base = base_essai_effectue()
    try:
        await nsr["post_conversion_checkout"](
            "AFR-ESSAI", _Requete({"offer_id": "off-membres"}))
        verifier("T8. offer_id de l'offre 150 falsifie -> REFUS serveur", False,
                 "aucune exception levee")
    except _HTTPException as ex:
        verifier("T8. offer_id de l'offre 150 falsifie -> REFUS serveur",
                 ex.status_code == 403 and not CAISSE,
                 "%s / caisse=%s" % (ex.status_code, len(CAISSE)))

    # T8b. Un identifiant inexistant, une chaine vide : meme refus.
    for _mauvais in ("", "off-inconnue", "../off-membres"):
        ns, nsr, base = base_essai_effectue()
        try:
            await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": _mauvais}))
            verifier("T8b. offer_id « %s » -> refus" % _mauvais, False, "accepte")
        except _HTTPException as ex:
            verifier("T8b. offer_id « %s » -> refus" % _mauvais,
                     ex.status_code == 403 and not CAISSE, str(ex.status_code))

    # T8c. Essai non effectue : meme une offre AUTORISEE est refusee.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=False)], courses=[cours_recurrent()],
                        offers=catalogue_complet())
    try:
        await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "off-pulse"}))
        verifier("T8c. essai non effectue -> achat refuse meme sur une offre autorisee",
                 False, "accepte")
    except _HTTPException as ex:
        verifier("T8c. essai non effectue -> achat refuse meme sur une offre autorisee",
                 ex.status_code == 403 and not CAISSE, str(ex.status_code))

    # T8d. Cours historique : meme refus a la caisse, pas seulement a l'ecran.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait()],
                        resas=[resa(validee=True)],
                        courses=[{"id": "cours-1", "name": "Dîner canadien",
                                  "date": "2026-08-09", "time": "18:30",
                                  "archived": False, "coach_id": COACH}],
                        offers=catalogue_complet())
    try:
        await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "off-pulse"}))
        verifier("T8d. cours historique -> achat refuse a la caisse", False, "accepte")
    except _HTTPException as ex:
        verifier("T8d. cours historique -> achat refuse a la caisse",
                 ex.status_code == 403 and not CAISSE, str(ex.status_code))

    # ─────────────────── 5. LE CHEMIN LEGITIME, ET SA CAISSE ────────────────
    # T11a. PULSE x10 : la caisse existante recoit le bon panier.
    ns, nsr, base = base_essai_effectue()
    rep = await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "off-pulse"}))
    req = CAISSE[0] if CAISSE else None
    verifier("T11. PULSE x10 -> session creee par le moteur de caisse existant",
             rep.get("checkout_url") == "https://stripe.test/session"
             and req is not None and req.payment_method == "card"
             and req.items[0].id == "off-pulse" and req.items[0].price == 250.0,
             str(rep))
    verifier("T11b. l'identite de l'acheteur vient du FORFAIT, pas du corps recu",
             req.customer_email == ANA and req.customer_name == "Ana"
             and req.coach_email == COACH, str(getattr(req, "customer_email", None)))
    evs = [x["event"] for x in POSTHOG]
    verifier("T11c. analytics : clic puis demarrage de caisse, dans cet ordre",
             evs == ["conversion_viewed", "conversion_offer_clicked", "checkout_started"]
             or evs == ["conversion_offer_clicked", "checkout_started"], str(evs))

    # T12a. Cours a l'unite : meme chemin, prix du serveur.
    ns, nsr, base = base_essai_effectue()
    await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "off-unite"}))
    verifier("T12. cours a l'unite -> meme caisse, 30 CHF du catalogue",
             CAISSE[0].items[0].price == 30.0 and CAISSE[0].items[0].id == "off-unite",
             str(CAISSE[0].items[0].price))

    # ───────────────────── 6. APRES L'ACHAT, ET APRES L'ECHEC ───────────────
    # T11d. `converted_at` pose par ESSAI-2 -> la conversion est TERMINEE.
    ns, nsr, base = base_essai_effectue(
        subs=[forfait(converted_at="2026-08-19T12:00:00+00:00")])
    e = await ns["conv_etat"](base, await base.subscriptions.find_one({"id": "sub-essai"}), COACH)
    verifier("T11d. achat reussi -> conversion terminee, plus aucune offre poussee",
             e["state"] == "purchased" and e["offers"] == [], str(e))
    try:
        await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "off-pulse"}))
        verifier("T11e. deja converti -> second achat refuse (409)", False, "accepte")
    except _HTTPException as ex:
        verifier("T11e. deja converti -> second achat refuse (409)",
                 ex.status_code == 409 and not CAISSE, str(ex.status_code))

    # T12b. Paiement ECHOUE : rien n'a ete pose, la conversion reste ouverte.
    ns, nsr, base = base_essai_effectue(caisse_erreur=_HTTPException(500, "Stripe HS"))
    try:
        await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "off-pulse"}))
    except _HTTPException:
        pass
    doc = await base.subscriptions.find_one({"id": "sub-essai"})
    e = await ns["conv_etat"](base, doc, COACH)
    verifier("T12b. paiement echoue -> conversion toujours accessible",
             e["state"] == "open" and len(e["offers"]) == 2
             and not doc.get("converted_at"), str(e))

    # T9b. ETAT PERSISTANT : le meme code, relu a froid, redonne le meme etat.
    ns, nsr, base = base_essai_effectue()
    e1 = await nsr["get_conversion_apres_essai"]("AFR-ESSAI")
    e2 = await nsr["get_conversion_apres_essai"]("afr-essai")   # casse differente
    verifier("T9c. etat persistant, insensible a la casse et au rechargement",
             e1["conversion"]["state"] == e2["conversion"]["state"] == "open"
             and e1["conversion"]["offers"] == e2["conversion"]["offers"], "")

    # T-sec. Le corps de la requete ne peut RIEN injecter d'identitaire.
    ns, nsr, base = base_essai_effectue()
    await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete(
        {"offer_id": "off-pulse", "customer_email": "pirate@mail.ch",
         "price": 1, "coach_email": "pirate@mail.ch",
         "originUrl": "https://pirate.example"}))
    verifier("T-sec1. l'URL de retour fournie par le client est IGNOREE",
             CAISSE[0].success_url.startswith("https://afroboost.test/")
             and CAISSE[0].cancel_url.startswith("https://afroboost.test/"),
             str(CAISSE[0].success_url))
    verifier("T-sec. e-mail, prix et vendeur fournis par le client sont IGNORES",
             CAISSE[0].customer_email == ANA and CAISSE[0].items[0].price == 250.0
             and CAISSE[0].coach_email == COACH, str(CAISSE[0].customer_email))

    # T-sec2. Le GET ne rend aucune donnee personnelle.
    ns, nsr, base = base_essai_effectue()
    rep = await nsr["get_conversion_apres_essai"]("AFR-ESSAI")
    _plat = repr(rep)
    verifier("T-sec2. le GET ne rend ni e-mail, ni WhatsApp, ni nom",
             ANA not in _plat and "+4176" not in _plat and "Ana" not in _plat, _plat[:200])

    # ────────── 7. LE CHAINON QUI POSE `converted_at` A L'ENCAISSEMENT ──────
    # Le webhook reellement declare chez Stripe traite LUI-MEME les achats
    # vitrine et ne deleguait jamais la conversion : sans ce chainon, l'ecran
    # continuerait a vendre a quelqu'un qui vient d'acheter.
    ns, nsr, base = base_essai_effectue()
    nsc = {"db": base, "logger": _Journal(), "asyncio": asyncio}
    exec(compile(CAISSE_SRC.extraire("_essai2_convertir_si_paye"), "<caisse>", "exec"), nsc)
    _si_paye = nsc["_essai2_convertir_si_paye"]

    verifier("T16. achat PAYANT -> la conversion est jugee par ESSAI-2",
             await _si_paye(ANA, 250, "card", "off-pulse", "sub-pulse") is True
             and CONVERSIONS == [{"email": ANA, "offer_id": "off-pulse",
                                  "sub_id": "sub-pulse"}], str(CONVERSIONS))

    CONVERSIONS[:] = []
    verifier("T16b. acces GRATUIT apres un essai -> AUCUNE conversion comptee",
             await _si_paye(ANA, 0, "free", "off-essai", "sub-2") is False
             and CONVERSIONS == [], str(CONVERSIONS))

    CONVERSIONS[:] = []
    verifier("T16c. montant nul, meme par carte -> aucune conversion",
             await _si_paye(ANA, 0, "card", "x", "y") is False and CONVERSIONS == [],
             str(CONVERSIONS))

    CONVERSIONS[:] = []
    verifier("T16d. montant recu en chaine (« 250 ») -> compte quand meme",
             await _si_paye(ANA, "250", "card", "x", "y") is True, str(CONVERSIONS))

    CONVERSIONS[:] = []
    verifier("T16e. montant illisible -> refus, aucune exception",
             await _si_paye(ANA, "abc", "card", "x", "y") is False and CONVERSIONS == [],
             str(CONVERSIONS))

    CONVERSIONS[:] = []
    CONV_ERREUR[0] = True
    verifier("T16f. moteur en panne -> non bloquant, le paiement reste encaisse",
             await _si_paye(ANA, 250, "card", "x", "y") is False, "")
    CONV_ERREUR[0] = False

    # T16g. Le chainon est bien BRANCHE dans le traitement du paiement.
    _corps = CAISSE_SRC.extraire("_process_successful_payment")
    verifier("T16g. `_process_successful_payment` appelle bien ce chainon",
             "_essai2_convertir_si_paye(customer_email, total, payment_method," in _corps
             and "subscription_id)" in _corps, "")

    # ───────── 8. LE FILTRE COACH : SYMETRIQUE, ET SANS FUITE ──────────────
    # Cause racine mesuree le 19/08/2026 : les 8 offres de production portent
    # `coach_id` nul et le forfait d'essai comme son code portent la chaine
    # vide. Le repli « proprietaire de la plateforme » cherchait donc un
    # `coach_id` que RIEN ne porte : zero offre, quoi que le coach coche.
    PARTENAIRE = "partenaire@coach.ch"

    def _sans_proprio(oid, nom, prix, forme, **extra):
        """La MEME offre, dans les trois formes reelles de « sans proprietaire »."""
        d = {"id": oid, "name": nom, "price": prix, "visible": True,
             "first_purchase_eligible": True, "position": 1}
        if forme == "nul":
            d["coach_id"] = None
        elif forme == "vide":
            d["coach_id"] = ""
        # forme == "absent" : la cle n'existe pas du tout
        d.update(extra)
        return d

    def _bac_orphelin(offres):
        """Essai sans proprietaire — l'etat reel de la production."""
        # Le CODE aussi porte la chaine vide : c'est l'etat reel releve en
        # production, et c'est ce qui fait tomber les deux replis de
        # `_conv_contexte` l'un apres l'autre.
        return bac(codes=[code_gratuit(coach_id="")], subs=[forfait(coach_id="")],
                   resas=[resa(validee=True)], courses=[cours_recurrent()],
                   offers=offres)

    for _forme in ("nul", "vide", "absent"):
        ns, nsr, base = _bac_orphelin([_sans_proprio("o1", "Pack", 250, _forme)])
        _r = await ns["conv_offres_premier_achat"](base, "")
        verifier("T17-%s. essai sans proprietaire + offre coach_id %s -> remonte"
                 % (_forme, _forme), [o["id"] for o in _r] == ["o1"], str(_r))

    # T18. LA GARDE ANTI-FUITE : une offre explicitement possedee par un
    #      partenaire n'est JAMAIS projetee pour un essai sans proprietaire.
    ns, nsr, base = _bac_orphelin([
        _sans_proprio("o-lib", "Pack maison", 250, "nul"),
        offre("o-part", "Pack du partenaire", 250, coach_id=PARTENAIRE),
    ])
    _r = await ns["conv_offres_premier_achat"](base, "")
    verifier("T18. essai sans proprietaire -> l'offre d'un partenaire est EXCLUE",
             [o["id"] for o in _r] == ["o-lib"], str([o["id"] for o in _r]))

    # T19. SYMETRIE INVERSE : un essai qui declare un partenaire ne voit que ses
    #      offres a lui — jamais le catalogue historique sans proprietaire.
    ns, nsr, base = bac(
        codes=[code_gratuit(email=ANA)], subs=[forfait(coach_id=PARTENAIRE)],
        resas=[resa(validee=True)], courses=[cours_recurrent()],
        offers=[_sans_proprio("o-lib", "Pack maison", 250, "nul"),
                offre("o-part", "Pack du partenaire", 250, coach_id=PARTENAIRE)])
    _r = await ns["conv_offres_premier_achat"](base, PARTENAIRE)
    verifier("T19. essai d'un partenaire -> uniquement SES offres",
             [o["id"] for o in _r] == ["o-part"], str([o["id"] for o in _r]))

    # T20. LE SUPER-ADMIN N'EST JAMAIS INJECTE COMME PROPRIETAIRE. C'est le
    #      defaut exact qui vidait l'ecran : `_conv_contexte` doit rendre la
    #      chaine vide, pas `SUPER_ADMIN_EMAILS[0]`.
    ns, nsr, base = _bac_orphelin(catalogue_complet())
    _code, _forf, _coach = await nsr["_conv_contexte"]("AFR-ESSAI")
    verifier("T20. proprietaire inconnu -> chaine vide, jamais le super-admin",
             _coach == "" and _coach != "admin@test", repr(_coach))

    # T20b. ... et le coach REEL, quand il existe, reste retenu tel quel.
    ns, nsr, base = bac(codes=[code_gratuit()], subs=[forfait(coach_id=PARTENAIRE)],
                        resas=[resa(validee=True)], courses=[cours_recurrent()],
                        offers=catalogue_complet())
    _c, _f, _coach2 = await nsr["_conv_contexte"]("AFR-ESSAI")
    verifier("T20b. proprietaire declare -> retenu tel quel",
             _coach2 == PARTENAIRE, repr(_coach2))

    # T20c. Repli sur le CODE quand le forfait ne declare rien.
    ns, nsr, base = bac(codes=[code_gratuit(coach_id=PARTENAIRE)],
                        subs=[forfait(coach_id="")],
                        resas=[resa(validee=True)], courses=[cours_recurrent()],
                        offers=catalogue_complet())
    _c, _f, _coach3 = await nsr["_conv_contexte"]("AFR-ESSAI")
    verifier("T20c. forfait muet, code declarant -> le code fait autorite",
             _coach3 == PARTENAIRE, repr(_coach3))

    # ───────── 9. LE CATALOGUE REEL DE PRODUCTION, A L'IDENTIQUE ────────────
    # Formes exactes relevees le 19/08/2026 : `coach_id` nul partout, PULSE en
    # position 2, « Cours a l'unite » en 3, « Membres » en 2 et non cochee.
    PROD = [
        {"id": "a687ce86", "name": "PULSE x10 cours", "price": 250.0, "position": 2,
         "pack_sessions": 10, "coach_id": None, "first_purchase_eligible": True},
        {"id": "fea0ab6a", "name": "Cours à l'unité", "price": 30.0, "position": 3,
         "pack_sessions": None, "coach_id": None, "first_purchase_eligible": True},
        {"id": "484c4519", "name": "Membres", "price": 150.0, "position": 2,
         "pack_sessions": 10, "coach_id": None, "first_purchase_eligible": False},
        {"id": "tshirt", "name": "T-shirt + 1 cours offert!", "price": 59.99,
         "position": 4, "coach_id": None},
        {"id": "vidy", "name": "Silent Dance & Fitness au bord du Lac de Vidy",
         "price": 25.0, "position": None, "coach_id": None},
        {"id": "lakeside", "name": "SILENT LAKESIDE", "price": 0.0, "position": 0,
         "coach_id": None, "first_purchase_eligible": True},
        {"id": "billet", "name": " Afroboost Silent avec Bassi", "price": 0.0,
         "position": 1, "coach_id": None},
        {"id": "essai", "name": "Cours d'essai GRATUIT", "price": 0.0, "position": 3,
         "coach_id": None},
    ]
    ns, nsr, base = _bac_orphelin(PROD)
    _rep = await nsr["get_conversion_apres_essai"]("AFR-ESSAI")
    _conv = _rep["conversion"]
    _off = _conv["offers"]
    verifier("T21. catalogue de production -> EXACTEMENT 2 offres projetees",
             len(_off) == 2, str([o["id"] for o in _off]))
    verifier("T21a. PULSE x10 : 250 CHF, 10 seances, recommandee, en premier",
             _off[0] == {"id": "a687ce86", "name": "PULSE x10 cours", "price": 250.0,
                         "currency": "CHF", "sessions": 10, "description": "",
                         "thumbnail": "", "recommended": True}, str(_off[0]))
    verifier("T21b. Cours a l'unite : 30 CHF, non recommandee, en second",
             _off[1]["id"] == "fea0ab6a" and _off[1]["price"] == 30.0
             and _off[1]["recommended"] is False, str(_off[1]))
    verifier("T21c. Membres 150 ABSENTE de la projection",
             not any(o["id"] == "484c4519" for o in _off), str(_off))
    verifier("T21d. aucune autre offre : ni t-shirt, ni event, ni gratuite cochee",
             {o["id"] for o in _off} == {"a687ce86", "fea0ab6a"}, str(_off))
    verifier("T21e. l'offre gratuite COCHEE reste ecartee (ce serait un 2e essai)",
             not any(o["id"] == "lakeside" for o in _off), str(_off))

    # T22. La garde de niveau 2 n'a pas bouge : l'offre 150 reste refusee a la
    #      caisse, apres correction du filtre coach comme avant.
    ns, nsr, base = _bac_orphelin(PROD)
    try:
        await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "484c4519"}))
        verifier("T22. offre 150 falsifiee -> toujours refusee apres correctif",
                 False, "acceptee")
    except _HTTPException as ex:
        verifier("T22. offre 150 falsifiee -> toujours refusee apres correctif",
                 ex.status_code == 403 and not CAISSE, str(ex.status_code))

    # T22b. ... et l'achat legitime passe, lui.
    ns, nsr, base = _bac_orphelin(PROD)
    _rep = await nsr["post_conversion_checkout"]("AFR-ESSAI", _Requete({"offer_id": "a687ce86"}))
    verifier("T22b. PULSE x10 -> caisse existante, 250 CHF du catalogue",
             _rep.get("checkout_url") and CAISSE[0].items[0].price == 250.0, str(_rep))

    # T23. FAIL CLOSED CONSERVE : aucune offre cochee -> ecran vide, aucun crash.
    ns, nsr, base = _bac_orphelin([dict(o, first_purchase_eligible=False) for o in PROD])
    _rep = await nsr["get_conversion_apres_essai"]("AFR-ESSAI")
    verifier("T23. aucune offre cochee -> ouverte mais vide, aucun crash",
             _rep["conversion"]["state"] == "open"
             and _rep["conversion"]["offers"] == [], str(_rep))

    # T-code. Un code inconnu ne fabrique pas d'eligibilite.
    ns, nsr, base = base_essai_effectue()
    rep = await nsr["get_conversion_apres_essai"]("AFR-INEXISTANT")
    verifier("T-code. code inconnu -> non eligible, aucun crash",
             rep["conversion"]["state"] == "not_eligible", str(rep))


# ═══════════════════════════════════ sortie ═════════════════════════════════
def main():
    asyncio.get_event_loop().run_until_complete(scenarios()) if sys.version_info < (3, 7) \
        else asyncio.run(scenarios())
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 78)
    print("LOT A — CONVERSION APRES ESSAI")
    print("=" * 78)
    for nom, cond, detail in RESULTATS:
        print(("  OK   " if cond else "  ECHEC") + "  " + nom + (
            "" if cond else "\n           -> " + str(detail)[:300]))
    print("-" * 78)
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

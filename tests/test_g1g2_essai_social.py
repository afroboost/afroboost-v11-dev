# -*- coding: utf-8 -*-
"""
G1 + G2 — l'anti-double du parcours « essai gratuit contre preuve sociale ».

Les DEUX gardes sont jouees POUR DE VRAI, contre une base simulee en memoire :
  G1  une seule demande EN ATTENTE par personne  (submit_social_proof)
  G2  la garde ESSAI-1 atomique a l'approbation  (review_social_proof)

L'INVARIANT LE PLUS IMPORTANT : deposer une demande, ou se la faire REFUSER,
ne consomme JAMAIS le droit au premier essai. `free_trial_claims` doit rester
vide tant qu'aucun essai n'est reellement accorde.

HORS LIGNE. Aucune connexion, aucune ecriture, aucune donnee de production.

    python3 tests/test_g1g2_essai_social.py
"""
import asyncio
import io
import os
import re
import sys
import uuid

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
CHECKOUT = io.open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"), encoding="utf-8").read()

resultats = []
def verifier(nom, cond, detail=""):
    resultats.append((nom, bool(cond), str(detail)))


# ---------------------------------------------------------------------------
# Une base en memoire, juste ce qu'il faut
# ---------------------------------------------------------------------------
class FausseCollection:
    def __init__(self, unique_id=False):
        self.docs = []
        self.unique_id = unique_id

    def _match(self, doc, filtre):
        for k, v in (filtre or {}).items():
            if isinstance(v, dict) and "$or" in v:
                return False
            if k == "$or":
                if not any(self._match(doc, sf) for sf in v):
                    return False
            elif isinstance(v, dict) and "$ne" in v:
                if doc.get(k) == v["$ne"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    async def find_one(self, filtre=None, proj=None):
        for d in self.docs:
            if self._match(d, filtre or {}):
                return dict(d)
        return None

    async def insert_one(self, doc):
        if self.unique_id and any(d.get("_id") == doc.get("_id") for d in self.docs):
            raise Exception("E11000 duplicate key error")
        self.docs.append(dict(doc))

    async def update_one(self, filtre, maj):
        for d in self.docs:
            if self._match(d, filtre):
                d.update(maj.get("$set", {}))
                return
    async def delete_one(self, filtre):
        self.docs = [d for d in self.docs if not self._match(d, filtre)]
    async def to_list(self, n=None):
        return [dict(d) for d in self.docs]
    def find(self, filtre=None, proj=None):
        parent = self
        class _C:
            async def to_list(self, n=None):
                return [dict(d) for d in parent.docs if parent._match(d, filtre or {})]
        return _C()
    async def count_documents(self, filtre=None):
        return len([d for d in self.docs if self._match(d, filtre or {})])


class FausseBase:
    def __init__(self):
        self.social_proofs = FausseCollection()
        self.offers = FausseCollection()
        self.discount_codes = FausseCollection()
        self.subscriptions = FausseCollection()
        self.chat_participants = FausseCollection()
        self.free_trial_claims = FausseCollection(unique_id=True)
        self.users = FausseCollection()
    def __getitem__(self, nom):
        return getattr(self, nom)


class HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, headers=None):
        self.status_code, self.detail, self.headers = status_code, detail, headers or {}


def extraire(src, nom):
    m = re.search(r"^async def %s\(.*?(?=^(?:async def |def |@)|\Z)" % nom, src, re.S | re.M)
    if not m:
        m = re.search(r"^def %s\(.*?(?=^(?:async def |def |@)|\Z)" % nom, src, re.S | re.M)
    return m.group(0) if m else None


def construire(base):
    """Charge les VRAIES fonctions des deux fichiers, avec la fausse base."""
    import datetime, logging, types

    esp_ck = {"db": base, "HTTPException": HTTPException, "datetime": datetime.datetime,
              "timezone": datetime.timezone, "logger": logging.getLogger("t"), "uuid": uuid}
    exec(compile("ESSAI1_RAISON = 'free_trial_already_used'\n"
                 "ESSAI1_MESSAGE = \"Votre essai gratuit a déjà été utilisé.\"", "<c>", "exec"), esp_ck)
    async def _tracer(offer_id=""):
        return None
    esp_ck["_essai1_tracer_refus"] = _tracer
    for fn in ("_essai1_essai_deja_accorde", "_essai1_reclamer", "_essai1_liberer", "_essai1_garde"):
        exec(compile(extraire(CHECKOUT, fn), "<ck>", "exec"), esp_ck)

    faux_ck = types.ModuleType("api.routes.checkout_routes")
    for k, v in esp_ck.items():
        setattr(faux_ck, k, v)
    sys.modules["api"] = types.ModuleType("api")
    sys.modules["api.routes"] = types.ModuleType("api.routes")
    sys.modules["api.routes.checkout_routes"] = faux_ck

    class SocialProof:
        """Reproduit le modele Pydantic reel : `id` par defaut, comme en base."""
        def __init__(self, **kw):
            self.id = str(uuid.uuid4())
            self.status = "pending"
            self.__dict__.update(kw)
        def model_dump(self): return dict(self.__dict__)
        def get(self, k, d=None): return self.__dict__.get(k, d)

    esp = {"db": base, "HTTPException": HTTPException, "SocialProof": SocialProof,
           "datetime": datetime.datetime, "timezone": datetime.timezone,
           "logger": logging.getLogger("t"), "uuid": uuid,
           "DEFAULT_COACH_ID": "bassi_default", "Request": object,
           "require_auth": lambda r: "coach@test.ch",
           "is_super_admin": lambda e: True,
           "send_push_by_email": None,
           # dependances d'envoi : neutralisees, ce lot ne teste pas les emails
           "RESEND_AVAILABLE": False, "resend": None, "asyncio": asyncio,
           "COACH_EMAIL": "coach@test.ch",
           "SUPER_ADMIN_EMAILS": ["coach@test.ch"],
           "FRONTEND_URL": "https://exemple.test",
           "os": os, "re": re}
    for fn in ("submit_social_proof", "review_social_proof"):
        exec(compile(extraire(SERVEUR, fn), "<s>", "exec"), esp)
    return esp, esp_ck


class Req:
    def __init__(self, corps): self._c = corps
    async def json(self): return self._c
    headers = {}


OFFRE = {"id": "off-1", "name": "🎁 Cours d'essai GRATUIT", "price": 0,
         "social_proof_price": 30, "coach_id": "coach@test.ch", "pack_sessions": 1}

def demande(email="ana@exemple.ch"):
    return {"offer_id": "off-1", "client_name": "Ana", "client_email": email,
            "video_link": "https://instagram.com/p/x", "instagram_username": "@ana",
            "motivation": "Je veux essayer"}


async def scenario():
    base = FausseBase()
    await base.offers.insert_one(dict(OFFRE))
    esp, esp_ck = construire(base)
    submit, review = esp["submit_social_proof"], esp["review_social_proof"]

    # --- 1. premiere demande : acceptee -------------------------------------
    try:
        await submit(Req(demande()))
        verifier("1. demande #1 acceptee", True)
    except HTTPException as e:
        verifier("1. demande #1 acceptee", False, f"{e.status_code} {e.detail}")

    # --- 3. AUCUN claim pose par une simple demande -------------------------
    verifier("3. free_trial_claims VIDE apres une demande en attente",
             len(base.free_trial_claims.docs) == 0,
             f"{len(base.free_trial_claims.docs)} claim(s)")

    # --- 2. deuxieme demande, meme email : 409 pending ----------------------
    try:
        await submit(Req(demande()))
        verifier("2. demande #2 refusee (409 pending)", False, "acceptee a tort")
    except HTTPException as e:
        verifier("2. demande #2 refusee (409 pending)",
                 e.status_code == 409 and "cours de validation" in (e.detail or ""),
                 f"{e.status_code} {e.detail}")
        verifier("2b. le message ne dit PAS « deja utilise »",
                 "utilisé" not in (e.detail or ""), e.detail)
        verifier("2c. motif machine expose",
                 (e.headers or {}).get("X-Refus-Raison") == "social_proof_pending", e.headers)

    # --- 4. demande refusee -> on peut recommencer --------------------------
    pid = base.social_proofs.docs[0]["id"]
    class R2:
        def __init__(self, c): self._c = c
        async def json(self): return self._c
        headers = {}
    await review(pid, R2({"action": "reject"}))
    verifier("4a. la demande est refusee",
             base.social_proofs.docs[0]["status"] == "rejected",
             base.social_proofs.docs[0]["status"])
    verifier("4b. AUCUN claim pose par un refus",
             len(base.free_trial_claims.docs) == 0,
             f"{len(base.free_trial_claims.docs)} claim(s)")
    try:
        await submit(Req(demande()))
        verifier("4c. apres refus, une NOUVELLE demande est acceptee", True)
    except HTTPException as e:
        verifier("4c. apres refus, une NOUVELLE demande est acceptee", False,
                 f"{e.status_code} {e.detail}")

    # --- 5. approbation : code + claim --------------------------------------
    pid2 = [d for d in base.social_proofs.docs if d["status"] == "pending"][0]["id"]
    await review(pid2, R2({"action": "approve"}))
    verifier("5a. un code AFR- est cree",
             len(base.discount_codes.docs) == 1 and base.discount_codes.docs[0]["code"].startswith("AFR-"),
             [d.get("code") for d in base.discount_codes.docs])
    verifier("5b. un abonnement est cree", len(base.subscriptions.docs) == 1)
    verifier("5c. le claim est MAINTENANT pose",
             len(base.free_trial_claims.docs) == 1,
             base.free_trial_claims.docs)

    # --- 6. seconde approbation, meme identite : 409 ------------------------
    await submit(Req(demande()))          # nouvelle demande (aucune en attente)
    pid3 = [d for d in base.social_proofs.docs if d["status"] == "pending"][0]["id"]
    try:
        await review(pid3, R2({"action": "approve"}))
        verifier("6. seconde approbation refusee", False, "acceptee a tort")
    except HTTPException as e:
        verifier("6. seconde approbation refusee (409)", e.status_code == 409,
                 f"{e.status_code} {e.detail}")
    verifier("6b. AUCUN second code emis",
             len(base.discount_codes.docs) == 1,
             f"{len(base.discount_codes.docs)} code(s)")

    # --- 7. /checkout/free PUIS preuve sociale : 409 ------------------------
    base2 = FausseBase()
    await base2.offers.insert_one(dict(OFFRE))
    esp2, esp_ck2 = construire(base2)
    # essai deja pris par le checkout gratuit
    await base2.discount_codes.insert_one({"code": "AFR-OLD", "assignedEmail": "bob@exemple.ch",
                                           "payment_method": "free", "total_paid": 0})
    await esp2["submit_social_proof"](Req(demande("bob@exemple.ch")))
    pidb = base2.social_proofs.docs[0]["id"]
    try:
        await esp2["review_social_proof"](pidb, R2({"action": "approve"}))
        verifier("7. checkout/free puis preuve sociale -> refuse", False, "accepte a tort")
    except HTTPException as e:
        verifier("7. checkout/free puis preuve sociale -> refuse (409)", e.status_code == 409,
                 f"{e.status_code} {e.detail}")

    # --- 8. deux approbations SIMULTANEES : un seul code --------------------
    base3 = FausseBase()
    await base3.offers.insert_one(dict(OFFRE))
    esp3, _ = construire(base3)
    await esp3["submit_social_proof"](Req(demande("cle@exemple.ch")))
    d1 = base3.social_proofs.docs[0]["id"]
    base3.social_proofs.docs.append(dict(base3.social_proofs.docs[0], id="dup", status="pending"))
    res = await asyncio.gather(
        esp3["review_social_proof"](d1, R2({"action": "approve"})),
        esp3["review_social_proof"]("dup", R2({"action": "approve"})),
        return_exceptions=True,
    )
    refus = [r for r in res if isinstance(r, HTTPException)]
    verifier("8a. deux approbations simultanees -> UN SEUL code",
             len(base3.discount_codes.docs) == 1,
             f"{len(base3.discount_codes.docs)} code(s)")
    verifier("8b. la seconde est refusee en 409", len(refus) == 1 and refus[0].status_code == 409,
             [getattr(r, 'status_code', r) for r in res])
    verifier("8c. UN SEUL claim", len(base3.free_trial_claims.docs) == 1)

    # --- 10. aucun code AFR expose publiquement -----------------------------
    verifier("10. la reponse publique de soumission n'expose aucun code",
             "granted_code" not in extraire(SERVEUR, "submit_social_proof"))


# ---------------------------------------------------------------------------
# Garde-fous de perimetre
# ---------------------------------------------------------------------------
def code_seul(src):
    """Retire commentaires et docstrings : on raisonne sur du CODE, pas sur des
    explications qui citent justement les noms qu'on cherche."""
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"^\s*#.*$", "", src, flags=re.M)


def perimetre():
    _sub = code_seul(extraire(SERVEUR, "submit_social_proof"))
    _rev = code_seul(extraire(SERVEUR, "review_social_proof"))
    verifier("P1. G1 n'appelle JAMAIS _essai1_garde (ne consomme pas l'essai)",
             "_essai1_garde" not in _sub and "free_trial_claims" not in _sub)
    verifier("P2. G1 ne retient que les demandes EN ATTENTE",
             '"status": "pending"' in _sub)
    verifier("P3. G2 appelle la garde atomique", "_essai1_garde as _g2_garde" in _rev)
    verifier("P4. G2 libere le claim si la creation echoue", "_g2_liberer" in _rev)
    verifier("P5. les Conditions restent HORS de ce lot",
             "t1_preuve" not in _sub and "t1_preuve" not in _rev)
    verifier("P6. aucun index cree par ce lot", SERVEUR.count("create_index") == 7,
             SERVEUR.count("create_index"))
    verifier("P7. maxPoolSize inchange", "maxPoolSize=3" in SERVEUR)


asyncio.run(scenario())
perimetre()

print("=" * 78)
echecs = 0
for nom, ok, detail in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom + ("" if ok else "   -> " + detail[:110]))
    if not ok:
        echecs += 1
print("=" * 78)
print("Donnees de production touchees : 0 — base simulee en memoire")
print("%d/%d verifications" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)

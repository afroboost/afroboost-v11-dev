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

    async def update_one(self, filtre, maj, upsert=False):
        """Rend un resultat porteur de `matched_count`, comme le vrai pilote.

        C'est indispensable : G4 decide QUI a gagne la course d'approbation en
        lisant `matched_count`. Un faux qui rend `None` ferait passer le test
        alors que la vraie base dirait l'inverse — ou l'echouerait a tort.
        `$unset` est gere parce que le retour en attente efface les marques de
        revue ; `upsert` parce que `t1_version_active` archive la version.
        """
        class _Res:
            def __init__(self, n, up=None):
                self.matched_count = n
                self.modified_count = n
                self.upserted_id = up
        for d in self.docs:
            if self._match(d, filtre):
                d.update(maj.get("$set", {}))
                for k in (maj.get("$unset") or {}):
                    d.pop(k, None)
                for k, v in (maj.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                return _Res(1)
        if upsert:
            neuf = dict(maj.get("$setOnInsert", {}))
            neuf.update(maj.get("$set", {}))
            for k, v in (filtre or {}).items():
                if not isinstance(v, dict):
                    neuf.setdefault(k, v)
            self.docs.append(neuf)
            return _Res(0, up=neuf.get("_id"))
        return _Res(0)
    async def find_one_and_update(self, filtre, maj, upsert=False, **_k):
        """Le primitif sur lequel repose le verrou d'octroi (ESSAI-6).

        IL FAUT LE MODELISER FIDELEMENT, sinon ce banc validerait une garde qui
        ne tient pas en vraie base. Deux comportements comptent, et un seul les
        distingue :
          * un document EXISTE et correspond au filtre -> mise a jour, on rend
            le document AVANT modification ;
          * aucun ne correspond ET `upsert` -> insertion ; si la cle primaire
            est deja prise par un document que le filtre a ECARTE, MongoDB rend
            un doublon E11000. C'est exactement ce cas-la qui ferme la course
            entre deux octrois simultanes.
        """
        for d in self.docs:
            if self._match(d, filtre):
                avant = dict(d)
                d.update(maj.get("$set", {}))
                for k in (maj.get("$unset") or {}):
                    d.pop(k, None)
                return avant
        if not upsert:
            return None
        neuf = dict(maj.get("$setOnInsert", {}))
        neuf.update(maj.get("$set", {}))
        for k, v in (filtre or {}).items():
            if not isinstance(v, dict):
                neuf.setdefault(k, v)
        if self.unique_id and any(d.get("_id") == neuf.get("_id") for d in self.docs):
            raise Exception("E11000 duplicate key error")
        self.docs.append(neuf)
        return None

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
        # Conditions : le texte publie, et l'archive des versions acceptees.
        self.concept = FausseCollection()
        self.terms_versions = FausseCollection()
        self.comments = FausseCollection()
        # ESSAI-6 : « consomme » se lit dans les presences. Vide par defaut —
        # aucune demande de preuve sociale n'en cree, et c'est precisement ce
        # que l'invariant de ce banc affirme.
        self.reservations = FausseCollection()
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


def _charger_shared_reel():
    """Le VRAI `api/routes/shared.py`, avec ses dependances pures.

    POURQUOI PAS UN BOUCHON. Depuis ESSAI-6, la garde d'essai demande a ce
    module « cet essai a-t-il ete consomme ? » et « en detient-elle deja un ? ».
    Reecrire ces deux reponses ici en ferait une SECONDE definition, qui
    divergerait du serveur sans que rien ne le dise — le defaut que ce banc
    passe justement son temps a debusquer ailleurs.

    Les semantiques d'ESSAI-6 sont prouvees a part, sur un vrai mongod
    (`tests/test_essai6_identite.py`). Ici, on veut seulement que ce soit LE
    code du depot qui reponde.
    """
    import ast as _ast, importlib.util as _iu, types as _t
    if "fastapi" not in sys.modules:
        _fa = _t.ModuleType("fastapi")
        class _Routeur:
            def __init__(self, *a, **k): pass
            def _rien(self, *a, **k): return lambda f: f
            get = post = put = patch = delete = _rien
        _fa.APIRouter = _Routeur
        _fa.HTTPException = HTTPException
        _fa.Request = object
        sys.modules["fastapi"] = _fa

    # `p1a_filtre_proprietaire` : la regle de propriete, prise a la source.
    _src = io.open(os.path.join(RACINE, "api", "routes", "membership_routes.py"),
                   encoding="utf-8").read()
    _bouts, _ns = [], {}
    for _n in _ast.parse(_src).body:
        if isinstance(_n, _ast.FunctionDef) and _n.name == "p1a_filtre_proprietaire":
            _bouts.append(_ast.get_source_segment(_src, _n))
        if isinstance(_n, _ast.Assign):
            for _t2 in _n.targets:
                if isinstance(_t2, _ast.Name) and _t2.id == "P1A_SANS_PROPRIETAIRE":
                    _bouts.append(_ast.get_source_segment(_src, _n))
    exec("\n\n".join(_bouts), _ns)
    _mr = _t.ModuleType("api.routes.membership_routes")
    _mr.p1a_filtre_proprietaire = _ns["p1a_filtre_proprietaire"]
    sys.modules["api.routes.membership_routes"] = _mr

    _spec_w = _iu.spec_from_file_location(
        "api.routes.modeles_whatsapp",
        os.path.join(RACINE, "api", "routes", "modeles_whatsapp.py"))
    _w = _iu.module_from_spec(_spec_w); _spec_w.loader.exec_module(_w)
    sys.modules["api.routes.modeles_whatsapp"] = _w

    _spec = _iu.spec_from_file_location(
        "api.routes.shared", os.path.join(RACINE, "api", "routes", "shared.py"))
    _m = _iu.module_from_spec(_spec); _spec.loader.exec_module(_m)
    return _m


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
    # ESSAI-6 (P1-a) : la garde s'appuie sur deux helpers de plus — le motif de
    # refus, et les cles de verrou (l'adresse, et le numero quand il existe).
    # On charge les VRAIES fonctions, comme les quatre autres.
    for fn in ("_essai1_motif_refus", "_essai1_essai_deja_accorde", "_essai1_cles",
               "_essai1_reclamer", "_essai1_liberer_cle", "_essai1_liberer",
               "_essai1_garde"):
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
    # ESSAI CONDITIONS — on charge les VRAIES fonctions du socle T1, pas des
    # imitations : c'est `t1_preuve` qui decide du refus, et `t1_version_active`
    # qui calcule l'empreinte figee sur la demande. Un doublon de test aurait
    # pu diverger du serveur sans que rien ne le dise.
    for fn in ("t1_empreinte", "t1_bloc_captation", "t1_cours_filme",
               "t1_captation_applicable", "t1_version_active", "t1_preuve"):
        exec(compile(extraire(SERVEUR, fn), "<t1>", "exec"), esp)
    exec(compile("T1_MESSAGE_REFUS = \"Merci d'accepter les conditions de participation.\"\n"
                 "T1_RAISON_REFUS = 'terms_not_accepted'", "<t1c>", "exec"), esp)
    for fn in ("submit_social_proof", "review_social_proof"):
        exec(compile(extraire(SERVEUR, fn), "<s>", "exec"), esp)
    # `essai2_tracer_octroi` (G6) est importe depuis api.routes.shared : on pose
    # un module espion pour verifier qu'il est bien appele, sans reseau.
    import types as _t
    faux_shared = _charger_shared_reel()
    appels_octroi = []
    async def _octroi(db_, email="", offer_id="", sessions=0):
        appels_octroi.append({"email": email, "offer_id": offer_id, "sessions": sessions})
    faux_shared.essai2_tracer_octroi = _octroi
    sys.modules["api.routes.shared"] = faux_shared
    esp["_appels_octroi"] = appels_octroi
    return esp, esp_ck


class Req:
    def __init__(self, corps): self._c = corps
    async def json(self): return self._c
    headers = {}


class R2(Req):
    """La requete du coach : meme forme, nom distinct pour la lisibilite."""
    pass


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

    # --- 8d. deux approbations de LA MEME demande : la barriere d'etat -------
    #
    # Le cas 8 ci-dessus fait courir DEUX demandes ; c'est le verrou d'essai qui
    # tranche. Ici les deux appels visent LE MEME document : c'est la transition
    # d'etat conditionnelle (G4) qui doit designer un seul gagnant, avant meme
    # que le verrou n'entre en jeu.
    base8 = FausseBase()
    await base8.offers.insert_one(dict(OFFRE))
    esp8, _ = construire(base8)
    await esp8["submit_social_proof"](Req(demande("ivan@exemple.ch")))
    d8 = base8.social_proofs.docs[0]["id"]
    res8 = await asyncio.gather(
        esp8["review_social_proof"](d8, R2({"action": "approve"})),
        esp8["review_social_proof"](d8, R2({"action": "approve"})),
        return_exceptions=True,
    )
    refus8 = [r for r in res8 if isinstance(r, HTTPException)]
    verifier("8d. meme demande approuvee deux fois -> UN SEUL code",
             len(base8.discount_codes.docs) == 1,
             f"{len(base8.discount_codes.docs)} code(s)")
    verifier("8e. le perdant recoit 409 « deja traitee »",
             len(refus8) == 1 and refus8[0].status_code == 409
             and "traitée" in (refus8[0].detail or ""),
             [getattr(r, "detail", r) for r in res8])
    verifier("8f. UN SEUL abonnement", len(base8.subscriptions.docs) == 1)

    # --- 10. aucun code AFR expose publiquement -----------------------------
    verifier("10. la reponse publique de soumission n'expose aucun code",
             "granted_code" not in extraire(SERVEUR, "submit_social_proof"))

    # --- 9. un refus laisse le DROIT a l'essai intact ------------------------
    #
    # Verification directe sur la fonction qui decide, pas sur un effet de bord :
    # apres un refus, `_essai1_essai_deja_accorde` doit repondre NON, sinon la
    # personne serait privee d'un essai qu'elle n'a jamais recu.
    base9 = FausseBase()
    await base9.offers.insert_one(dict(OFFRE))
    esp9, esp_ck9 = construire(base9)
    await esp9["submit_social_proof"](Req(demande("dora@exemple.ch")))
    p9 = base9.social_proofs.docs[0]["id"]
    await esp9["review_social_proof"](p9, R2({"action": "reject"}))
    verifier("9a. apres refus, AUCUN claim",
             len(base9.free_trial_claims.docs) == 0, base9.free_trial_claims.docs)
    verifier("9b. apres refus, le droit a l'essai est INTACT",
             (await esp_ck9["_essai1_essai_deja_accorde"]("dora@exemple.ch")) is False)

    # --- 11. panne APRES la pose du claim : le claim est rendu ---------------
    #
    # On casse volontairement la seconde ecriture (l'abonnement). Le claim a
    # deja ete pose par la garde : s'il n'etait pas rendu, cette personne
    # perdrait son essai sans jamais l'avoir recu. L'etat de la demande doit
    # aussi revenir en attente, sinon plus personne ne pourrait rejouer.
    base11 = FausseBase()
    await base11.offers.insert_one(dict(OFFRE))
    esp11, _ = construire(base11)
    await esp11["submit_social_proof"](Req(demande("eve@exemple.ch")))
    p11 = base11.social_proofs.docs[0]["id"]
    async def _casse(doc):
        raise Exception("panne simulee a l'ecriture de l'abonnement")
    base11.subscriptions.insert_one = _casse
    try:
        await esp11["review_social_proof"](p11, R2({"action": "approve"}))
        verifier("11. panne apres claim -> l'erreur remonte", False, "aucune erreur")
    except Exception as e:
        verifier("11. panne apres claim -> l'erreur remonte", not isinstance(e, HTTPException)
                 or e.status_code != 409, type(e).__name__)
    # ESSAI-6 : le verrou n'est plus SUPPRIME, il est marque `actif: False`.
    # L'invariant teste ici est inchange — « une panne au milieu du tunnel ne
    # prive personne de son essai » — mais il se lit desormais sur le drapeau.
    # La ligne survit a dessein : c'est la seule trace de qui a demande un
    # essai, et quand, le jour ou il faudra arbitrer un litige.
    _c11 = base11.free_trial_claims.docs
    verifier("11a. le claim a ete RENDU (verrou libere, trace conservee)",
             len(_c11) == 1 and _c11[0].get("actif") is False
             and _c11[0].get("libere_motif") == "octroi_echoue", _c11)
    verifier("11b. la demande est revenue EN ATTENTE",
             base11.social_proofs.docs[0]["status"] == "pending",
             base11.social_proofs.docs[0]["status"])
    verifier("11c. les marques de revue ont ete effacees",
             "reviewed_by" not in base11.social_proofs.docs[0],
             sorted(base11.social_proofs.docs[0].keys()))
    verifier("11d. AUCUN code orphelin ne subsiste",
             len(base11.discount_codes.docs) == 0,
             [d.get("code") for d in base11.discount_codes.docs])
    # ET LA PREUVE QUE CA COMPTE : la personne doit pouvoir etre approuvee
    # a la reprise. Un code orphelin l'aurait bannie definitivement.
    base11.subscriptions.insert_one = FausseCollection().insert_one.__get__(
        base11.subscriptions, FausseCollection)
    p11b = base11.social_proofs.docs[0]["id"]
    try:
        await esp11["review_social_proof"](p11b, R2({"action": "approve"}))
        verifier("11e. la reprise apres panne aboutit", len(base11.discount_codes.docs) == 1,
                 base11.discount_codes.docs)
    except HTTPException as e:
        verifier("11e. la reprise apres panne aboutit", False, f"{e.status_code} {e.detail}")

    # --- 13. le funnel voit l'octroi social ---------------------------------
    #
    # DEUX lectures, parce qu'il y a deux funnels :
    #   - ESSAI-3 lit la BASE : le code doit porter `source: social_proof`, seul
    #     marqueur reconnu par ESSAI2_FILTRE_GRATUIT ;
    #   - PostHog lit l'evenement : `free_trial_granted` doit etre emis, comme
    #     sur /checkout/free.
    base13 = FausseBase()
    await base13.offers.insert_one(dict(OFFRE))
    esp13, _ = construire(base13)
    await esp13["submit_social_proof"](Req(demande("flo@exemple.ch")))
    p13 = base13.social_proofs.docs[0]["id"]
    await esp13["review_social_proof"](p13, R2({"action": "approve"}))
    verifier("13a. le code porte le marqueur reconnu par ESSAI-3",
             base13.discount_codes.docs[0].get("source") == "social_proof",
             base13.discount_codes.docs[0].get("source"))
    verifier("13b. l'abonnement porte le marqueur",
             base13.subscriptions.docs[0].get("source") == "social_proof")
    verifier("13c. free_trial_granted est emis (G6)",
             len(esp13["_appels_octroi"]) == 1, esp13["_appels_octroi"])
    if esp13["_appels_octroi"]:
        _a = esp13["_appels_octroi"][0]
        verifier("13d. la mesure ne porte que l'offre et le nombre de seances",
                 _a["offer_id"] == "off-1" and _a["sessions"] == 1, _a)


TEXTE_CONDITIONS = "CONDITIONS DE PARTICIPATION\n\n1. Vous reservez une place."


async def scenario_conditions():
    """ESSAI CONDITIONS — le parcours preuve sociale recueille l'acceptation."""
    base = FausseBase()
    await base.offers.insert_one(dict(OFFRE))
    await base.concept.insert_one({"id": "concept", "termsText": TEXTE_CONDITIONS})
    esp, _ = construire(base)
    submit, review = esp["submit_social_proof"], esp["review_social_proof"]

    version_attendue = esp["t1_empreinte"](TEXTE_CONDITIONS)

    # --- 6. conditions publiees, case NON cochee : refus ---------------------
    try:
        await submit(Req(demande("gaia@exemple.ch")))
        verifier("6. demande SANS acceptation -> refusee", False, "acceptee a tort")
    except HTTPException as e:
        verifier("6. demande SANS acceptation -> refusee (409)", e.status_code == 409,
                 f"{e.status_code} {e.detail}")
    verifier("6a. aucune demande enregistree",
             len(base.social_proofs.docs) == 0, len(base.social_proofs.docs))
    verifier("6b. aucun claim pose par un refus de conditions",
             len(base.free_trial_claims.docs) == 0)

    # --- 6c. `terms_accepted` falsifie (chaine, pas True) : refuse aussi -----
    for valeur in ("true", 1, "oui"):
        try:
            d = demande("gaia@exemple.ch"); d["terms_accepted"] = valeur
            await submit(Req(d))
            verifier("6c. acceptation non booleenne refusee (%r)" % valeur, False, "acceptee")
        except HTTPException as e:
            verifier("6c. acceptation non booleenne refusee (%r)" % valeur,
                     e.status_code == 409, e.status_code)

    # --- 7. case cochee : demande creee, version FIGEE -----------------------
    d = demande("gaia@exemple.ch"); d["terms_accepted"] = True
    await submit(Req(d))
    doc = base.social_proofs.docs[0]
    verifier("7a. la demande est enregistree", len(base.social_proofs.docs) == 1)
    verifier("7b. terms_accepted fige a True", doc.get("terms_accepted") is True)
    verifier("7c. terms_version = empreinte du texte publie",
             doc.get("terms_version") == version_attendue,
             f"{doc.get('terms_version')} vs {version_attendue}")
    verifier("7d. terms_accepted_at horodate par le SERVEUR",
             bool(doc.get("terms_accepted_at")))
    verifier("7e. filmed_at_booking False — une demande ne vise aucune seance",
             doc.get("filmed_at_booking") is False, doc.get("filmed_at_booking"))
    verifier("7f. la version est archivee dans terms_versions",
             any(v.get("version") == version_attendue for v in base.terms_versions.docs))
    verifier("7g. la reponse ne renvoie AUCUN code",
             len(base.discount_codes.docs) == 0)

    # --- 7h. approbation d'une demande qui PORTE la preuve : ca passe --------
    await review(doc["id"], R2({"action": "approve"}))
    verifier("7h. demande avec preuve -> approuvee et code emis",
             len(base.discount_codes.docs) == 1, base.discount_codes.docs)

    # --- 6d. demande ANCIENNE, sans preuve : approbation REFUSEE -------------
    #
    # Le cas des demandes deposees avant ce correctif. Le coach ne doit pas
    # pouvoir accorder un essai sur un consentement qui n'existe pas — et la
    # demande doit RESTER exploitable (en attente), pas rester bloquee.
    base2 = FausseBase()
    await base2.offers.insert_one(dict(OFFRE))
    await base2.concept.insert_one({"id": "concept", "termsText": TEXTE_CONDITIONS})
    esp2, _ = construire(base2)
    await base2.social_proofs.insert_one({
        "id": "vieille", "offer_id": "off-1", "client_email": "hugo@exemple.ch",
        "client_name": "Hugo", "coach_id": "coach@test.ch", "status": "pending",
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    try:
        await esp2["review_social_proof"]("vieille", R2({"action": "approve"}))
        verifier("6d. ancienne demande sans preuve -> refusee", False, "approuvee a tort")
    except HTTPException as e:
        verifier("6d. ancienne demande sans preuve -> refusee (409)",
                 e.status_code == 409
                 and (e.headers or {}).get("X-Refus-Raison") == "social_proof_sans_conditions",
                 f"{e.status_code} {e.headers}")
    verifier("6e. aucun code emis pour une demande sans preuve",
             len(base2.discount_codes.docs) == 0)
    verifier("6f. aucun claim pose", len(base2.free_trial_claims.docs) == 0)
    verifier("6g. la demande RESTE en attente (rejouable)",
             base2.social_proofs.docs[0]["status"] == "pending",
             base2.social_proofs.docs[0]["status"])

    # --- 6h. un REFUS reste possible sur une ancienne demande ----------------
    await esp2["review_social_proof"]("vieille", R2({"action": "reject"}))
    verifier("6h. le coach peut toujours REFUSER une ancienne demande",
             base2.social_proofs.docs[0]["status"] == "rejected")


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
    verifier("P5. les Conditions sont recueillies AU DEPOT, par t1_preuve",
             "t1_preuve(" in _sub, "absent de submit_social_proof")
    verifier("P5b. le DEPOT ne pose toujours aucun claim (invariant du lot)",
             "_essai1_garde" not in _sub and "free_trial_claims" not in _sub)
    verifier("P5c. l'approbation RELIT la preuve, elle n'en fabrique pas",
             "t1_preuve(" not in _rev and "terms_version" in _rev)
    verifier("P5d. la transition d'etat est CONDITIONNELLE (concurrence)",
             '"id": proof_id, "status": "pending"' in _rev)
    verifier("P5e. l'echec d'octroi rend la demande en attente",
             _rev.count("_g4_rendre_en_attente()") >= 3,
             _rev.count("_g4_rendre_en_attente()"))
    verifier("P5f. l'octroi social alimente le meme funnel",
             "essai2_tracer_octroi" in _rev)
    verifier("P5g. un octroi echoue ne laisse aucun code derriere lui",
             "discount_codes.delete_one" in _rev)
    verifier("P6. aucun index cree par ce lot", SERVEUR.count("create_index") == 7,
             SERVEUR.count("create_index"))
    verifier("P7. maxPoolSize inchange", "maxPoolSize=3" in SERVEUR)

    # --- 14/15/16 : ce que ce lot NE DOIT PAS avoir touche ------------------
    #
    # Verifications STRUCTURELLES, sur le code lui-meme : elles tiennent hors
    # ligne et disent quelque chose de vrai, contrairement a un « je n'y ai pas
    # touche » sur parole.
    _free = code_seul(extraire(CHECKOUT, "free_checkout") or "")
    verifier("14a. /checkout/free exige toujours les Conditions",
             "_t1_preuve_checkout(" in _free)
    verifier("14b. /checkout/free garde son anti-double et son filet",
             "_essai1_garde(" in _free and "_essai1_liberer(" in _free)
    verifier("14c. /checkout/free mesure toujours l'octroi",
             "essai2_tracer_octroi" in _free)
    verifier("14d. les quatre fonctions ESSAI-1 sont intactes",
             all(extraire(CHECKOUT, f) for f in
                 ("_essai1_essai_deja_accorde", "_essai1_reclamer",
                  "_essai1_liberer", "_essai1_garde")))

    _t3 = code_seul(extraire(SERVEUR, "t3_eligibilite") or "")
    _t3s = code_seul(extraire(SERVEUR, "t3_soumettre") or "")
    verifier("15a. les temoignages restent un systeme separe",
             "social_proof" not in _t3 and "social_proof" not in _t3s)
    verifier("15b. l'eligibilite au temoignage vient toujours du coach",
             "contact_type" in _t3)
    verifier("15c. accepter les Conditions n'accorde AUCUN temoignage",
             "consent" not in _sub and "temoignage" not in _sub.lower())

    _t1p = extraire(SERVEUR, "t1_preuve") or ""
    verifier("16a. t1_preuve garde sa signature",
             "async def t1_preuve(accepte, course_id: str = \"\", coach_id: str = \"\")" in _t1p)
    verifier("16b. les Conditions restent facultatives tant que rien n'est publie",
             "if not _version:" in _t1p and "return {}" in _t1p)
    verifier("16c. la version reste l'empreinte du contenu",
             "hashlib.sha256" in (extraire(SERVEUR, "t1_empreinte") or ""))
    verifier("16d. la reservation reste le mur final",
             "t1_preuve" in io.open(os.path.join(RACINE, "api", "routes",
                                                 "reservation_routes.py"),
                                    encoding="utf-8").read())


asyncio.run(scenario())
asyncio.run(scenario_conditions())
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

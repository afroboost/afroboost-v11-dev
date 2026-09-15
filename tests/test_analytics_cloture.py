# -*- coding: utf-8 -*-
"""ANALYTICS PHASE 4 — clôture mensuelle : snapshot officiel, idempotence, immutabilité.

Ce que ces bancs tiennent :
  * seule écriture autorisée = `insert_one` dans `analytics_monthly_reports` ;
    toute écriture sur une collection métier fait ÉCHOUER le banc ;
  * clôture = mois civil complet ET terminé, sans filtre cours ; refus du mois
    en cours, d'une période personnalisée, d'un filtre cours ;
  * super-admin seulement (401 sans jeton, 403 coach) ;
  * snapshot = projection phase 3 (valeur pour valeur), anonymisé, empreinte
    SHA-256 déterministe (ordre des clés, champs volatils) ;
  * double clic / retry / deux appels simultanés -> UN snapshot, 409 ensuite,
    jamais d'écrasement ;
  * IMMUTABILITÉ : après clôture, une donnée source modifiée change le bilan
    DYNAMIQUE mais pas le bilan OFFICIEL, ni ses exports (CSV / XLSX / PDF
    générés depuis le snapshot) ;
  * archives et lecture d'un snapshot : périmètre coach imposé.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_analytics_cloture.py
"""
import asyncio, copy, csv, io, os, sys, types
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from api.routes import analytics_shared as A
from api.routes import analytics_association as AS
from api.routes import analytics_cloture as C

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


# ═══ données (celles de la phase 3, août 2026) ═══
COACH = "coach@exemple.invalid"
AUTRE = "autre@exemple.invalid"
ADMIN = "admin@exemple.invalid"
MAINTENANT_FIXE = datetime(2026, 9, 15, 12, 0, 0)


def resa(id_, email, occ, cree, course_id="c-mer", course_name="Silent", coach=COACH, **kw):
    d = {"id": id_, "userEmail": email, "userName": "Prénom Nom " + id_, "courseId": course_id, "courseName": course_name,
         "datetime": occ, "createdAt": cree, "coach_id": coach, "validated": False, "isProduct": False, "price": 0}
    d.update(kw)
    return d


def sub(code, email, cree, offer_name="PULSE x10 cours", coach=COACH, **kw):
    d = {"id": "sub-" + code.lower(), "code": code, "email": email, "name": "Prénom Nom", "offer_name": offer_name,
         "status": "active", "created_at": cree + "T10:00:00+00:00", "expires_at": "2027-03-01T23:59:59+00:00",
         "total_sessions": 10, "used_sessions": 0, "remaining_sessions": 10, "coach_id": coach, "renewal_warnings_sent": []}
    d.update(kw)
    return d


def fiche(code, email, **kw):
    d = {"code": code, "assignedEmail": email, "maxUses": 10, "used": 0, "active": True, "id": "dc-" + code.lower()}
    d.update(kw)
    return d


RESAS = [
    resa("j1", "anna@mail.ch", "2026-07-08T18:30:00", "2026-07-01T10:00:00+00:00"),
    resa("a1", "anna@mail.ch", "2026-08-05T18:30:00", "2026-08-01T10:00:00+00:00", validated=True, tarif_applique=25.0),
    resa("a2", "carl@mail.ch", "2026-08-05T18:30:00", "2026-08-01T10:00:00+00:00"),
    resa("a3", "dora@mail.ch", "2026-08-09T18:30:00", "2026-08-02T10:00:00+00:00", "c-dim", "Sunday", discountCode="AFR-ESSAI1", validated=True),
    resa("a4", "eve@mail.ch", "2026-08-12T18:30:00", "2026-08-10T10:00:00+00:00"),
    resa("s1", "anna@mail.ch", "2026-09-09T18:30:00", "2026-09-01T10:00:00+00:00"),
]
SUBS = [
    sub("PULSE-A", "anna@mail.ch", "2026-08-03", montant_encaisse=250, origine_paiement="twint"),
    sub("AFR-ESSAI1", "dora@mail.ch", "2026-08-02", "🎁 Cours d'essai GRATUIT ", montant_encaisse=0, origine_paiement="offert", coach=""),
    sub("DECL-1", "kim@mail.ch", "2026-08-11", offer_price=250),
    sub("JUIL-1", "bob@mail.ch", "2026-07-03", montant_encaisse=100, origine_paiement="especes"),
]
FICHES = [fiche("PULSE-A", "anna@mail.ch"), fiche("AFR-ESSAI1", "dora@mail.ch", payment_method="free", total_paid=0),
          fiche("DECL-1", "kim@mail.ch"), fiche("JUIL-1", "bob@mail.ch")]
PAIEMENTS = [{"id": "p1", "session_id": "cs_live_abc123", "customer_email": "carl@mail.ch", "created_at": "2026-08-06T10:00:00+00:00",
              "amount": 30.0, "amount_total": 3000, "quantity": 1, "currency": "chf", "product_name": "Cours", "payment_status": "paid",
              "coach_id": COACH, "metadata": {"customer_email": "carl@mail.ch"}}]
CARTES = [{"email": "anna@mail.ch", "date_debut": "2026-08-03", "date_fin": "2027-08-02", "source": "achat", "coach_id": COACH}]
COURS = [{"id": "c-mer", "name": "Silent", "weekday": 3}, {"id": "c-dim", "name": "Sunday", "weekday": 0}]
CONCEPT = [{"coach_id": COACH, "appName": "Studio Test"}]

# ═══ 1. règles pures ═══
verifier("clé canonique : 2026-08:tous / 2026-08:coach:<id> (minuscules)", C.cle_cloture(2026, 8) == "2026-08:tous" and C.cle_cloture(2026, 8, " Coach@X.CH ") == "2026-08:coach:coach@x.ch")
d, f = A.bornes_periode("mois", MAINTENANT_FIXE, "", "", "2026-08")
verifier("août 2026 (terminé) : clôturable", C.est_cloturable(d, f, MAINTENANT_FIXE) == (True, ""))
d, f = A.bornes_periode("mois", MAINTENANT_FIXE, "", "", "2026-09")
verifier("septembre 2026 (en cours) : refusé, raison « mois en cours »", C.est_cloturable(d, f, MAINTENANT_FIXE) == (False, C.RAISON_MOIS_EN_COURS))
d, f = A.bornes_periode("perso", MAINTENANT_FIXE, "2026-08-01", "2026-08-15")
verifier("B'. période personnalisée 1–15 août : refusée (« période personnalisée »)", C.est_cloturable(d, f, MAINTENANT_FIXE, "", "perso") == (False, C.RAISON_PERIODE_PERSO))
d, f = A.bornes_periode("perso", MAINTENANT_FIXE, "2026-08-01", "2026-08-31")
verifier("B. perso couvrant EXACTEMENT août (mêmes bornes qu'un mois civil) : REFUSÉE — une vue personnalisée n'est jamais officielle",
         C.est_cloturable(d, f, MAINTENANT_FIXE, "", "perso") == (False, C.RAISON_PERIODE_PERSO))
d, f = A.bornes_periode("perso", MAINTENANT_FIXE, "2026-08-01", "2026-09-01")
verifier("C. perso 1 août → 1er septembre : refusée", C.est_cloturable(d, f, MAINTENANT_FIXE, "", "perso") == (False, C.RAISON_PERIODE_PERSO))
verifier("periode=annee / semaine / aujourdhui : jamais clôturables", all(C.est_cloturable(d, f, MAINTENANT_FIXE, "", p) == (False, C.RAISON_PERIODE_PERSO) for p in ("annee", "semaine", "aujourdhui", "")))
d, f = A.bornes_periode("mois", MAINTENANT_FIXE, "", "", "2026-07")
verifier("F. mois passé (juillet) : accepté", C.est_cloturable(d, f, MAINTENANT_FIXE, "", "mois") == (True, ""))
d, f = A.bornes_periode("mois", MAINTENANT_FIXE, "", "", "2026-08")
verifier("filtre cours : refusé", C.est_cloturable(d, f, MAINTENANT_FIXE, "c-dim") == (False, C.RAISON_FILTRE_COURS))
verifier("bornes nulles : refusé", C.est_cloturable(None, None, MAINTENANT_FIXE)[0] is False)

# hash déterministe
b1 = {"a": 1, "b": {"y": 2, "x": [1, 2]}, "genere_le": "2026-09-15 12:00"}
b2 = {"genere_le": "2027-01-01 00:00", "b": {"x": [1, 2], "y": 2}, "a": 1}
verifier("hash : indépendant de l'ordre des clés et de genere_le", C.hash_bilan(b1) == C.hash_bilan(b2) and len(C.hash_bilan(b1)) == 64)
verifier("hash : sensible au contenu", C.hash_bilan({"a": 1}) != C.hash_bilan({"a": 2}))
verifier("hash : identique à deux appels (déterministe)", C.hash_bilan(b1) == C.hash_bilan(copy.deepcopy(b1)))

# ═══ 2. faux Mongo : écritures interdites partout sauf la collection des clôtures ═══
class _Cur:
    def __init__(self, docs): self.d = docs
    async def to_list(self, n): return [dict(x) for x in self.d]


def _match(doc, f):
    for k, v in f.items():
        if k == "$or":
            if not any(_match(doc, alt) for alt in v): return False
        elif isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]: return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]: return False
        elif doc.get(k) != v:
            return False
    return True


def _proj(d, p):
    if p and any(v == 0 for k, v in p.items() if k != "_id"):
        return {k: v for k, v in d.items() if p.get(k, 1) != 0}
    return dict(d)


ECRITURES_METIER = []


class _Metier:
    def __init__(self, docs, base): self.docs, self.base = docs, base
    def find(self, f, p=None):
        self.base.requetes += 1
        return _Cur([d for d in self.docs if _match(d, f)])
    async def find_one(self, f, p=None):
        self.base.requetes += 1
        for d in self.docs:
            if _match(d, f): return _proj(d, p)
        return None
    def __getattr__(self, name):
        if name in ("update_one", "insert_one", "delete_one", "update_many", "find_one_and_update", "replace_one", "insert_many", "delete_many", "create_index", "bulk_write"):
            ECRITURES_METIER.append(name)
            raise AssertionError("ÉCRITURE MÉTIER INTERDITE : " + name)
        raise AttributeError(name)


class _Clotures:
    """La seule collection inscriptible : index unique sur `cle` et `id` simulé."""
    def __init__(self, base): self.docs, self.base, self.index, self.inserts = [], base, [], 0
    async def create_index(self, champ, unique=False):
        self.index.append((champ, unique))
    async def insert_one(self, doc):
        from pymongo.errors import DuplicateKeyError
        self.inserts += 1
        for d in self.docs:
            if d["cle"] == doc["cle"] or d["id"] == doc["id"]:
                raise DuplicateKeyError("E11000 duplicate key")
        self.docs.append(copy.deepcopy(doc))
        return types.SimpleNamespace(inserted_id=doc["id"])
    def find(self, f, p=None):
        self.base.requetes += 1
        return _Cur([_proj(d, p) for d in self.docs if _match(d, f)])
    async def find_one(self, f, p=None):
        self.base.requetes += 1
        for d in self.docs:
            if _match(d, f): return _proj(d, p)
        return None
    def __getattr__(self, name):
        if name in ("update_one", "update_many", "find_one_and_update", "replace_one", "delete_one", "delete_many"):
            raise AssertionError("ÉCRASEMENT INTERDIT : " + name)
        raise AttributeError(name)


class _Base:
    def __init__(self, resas, subs, fiches, pays, cartes, clotures=None):
        self.requetes = 0
        self.reservations = _Metier(resas, self)
        self.courses = _Metier(COURS, self)
        self.subscriptions = _Metier(subs, self)
        self.discount_codes = _Metier(fiches, self)
        self.offers = _Metier([], self)
        self.memberships = _Metier(cartes, self)
        self.payment_transactions = _Metier(pays, self)
        self.concept = _Metier(CONCEPT, self)
        self.seance_mouvements = _Metier([], self)
        self.analytics_monthly_reports = clotures or _Clotures(self)
        self._coll = {"analytics_monthly_reports": self.analytics_monthly_reports}
    def __getitem__(self, nom):
        if nom in self._coll: return self._coll[nom]
        return getattr(self, nom)


def _serveur(base, jwt_email):
    m = types.ModuleType("api.server")
    m.db = base
    m._v311_coach_email_from_jwt = lambda request: jwt_email
    async def _est_coach(email): return email in (COACH, AUTRE, ADMIN)
    m._v309_is_coach_or_admin = _est_coach
    sys.modules["api.server"] = m
    rr = types.ModuleType("api.routes.reservation_routes")
    rr.lot1_occurrence_iso = lambda v: (A.parser_local(v).strftime("%Y-%m-%dT%H:%M:%S") if A.parser_local(v) else "")
    sys.modules["api.routes.reservation_routes"] = rr


import api.routes.shared as _shared
_shared.is_super_admin = lambda e: (e or "").lower() == ADMIN

try:
    import fastapi  # noqa: F401
    from fastapi import HTTPException
    import api.routes.analytics_routes as R
    _shared_vers_local = R.vers_local
    # On fige « maintenant » au 15/09/2026 pour que le banc ne dépende pas du jour réel.
    R.vers_local = lambda dt: MAINTENANT_FIXE

    class _Req:
        headers = {}

    def _appel(fn, base, jwt, **params):
        _serveur(base, jwt)
        try:
            r = run(fn(_Req(), **params))
            return 200, r, base.requetes
        except HTTPException as e:
            return e.status_code, e.detail, base.requetes

    CLOTURES = _Clotures(None)
    def base():
        b = _Base(copy.deepcopy(RESAS), copy.deepcopy(SUBS), copy.deepcopy(FICHES), copy.deepcopy(PAIEMENTS), copy.deepcopy(CARTES), CLOTURES)
        CLOTURES.base = b
        return b

    # ── permissions ──
    s, d, _ = _appel(R.analytics_cloturer, base(), "", mois="2026-08")
    verifier("clôture sans jeton -> 401", s == 401, s)
    s, d, _ = _appel(R.analytics_cloturer, base(), COACH, mois="2026-08")
    verifier("clôture par un coach -> 403", s == 403, s)
    verifier("aucun snapshot créé par ces refus", len(CLOTURES.docs) == 0)

    # ── refus mois en cours / perso / cours ──
    s, d, _ = _appel(R.analytics_cloturer, base(), ADMIN, mois="2026-09")
    verifier("clôture du mois en cours -> 409 « mois en cours »", s == 409 and d == C.RAISON_MOIS_EN_COURS, (s, d))
    s, d, _ = _appel(R.analytics_cloturer, base(), ADMIN, mois="2026-8")
    verifier("mois mal formé -> 400", s == 400, s)
    s, r, _ = _appel(R.analytics_cockpit, base(), ADMIN, periode="perso", du="2026-08-01", au="2026-08-15", vue="association")
    verifier("vue association sur une période perso 1–15 août : non clôturable, raison « période personnalisée »", r["cloture"]["cloturable"] is False and r["cloture"]["raison"] == C.RAISON_PERIODE_PERSO, r["cloture"])
    s, r, n = _appel(R.analytics_cockpit, base(), ADMIN, periode="perso", du="2026-08-01", au="2026-08-31", vue="association")
    verifier("B. vue perso 1–31 août (mois exact) : NON clôturable, aucune lecture de clôture (7 requêtes), aucune bannière",
             r["cloture"]["cloturable"] is False and r["cloture"]["raison"] == C.RAISON_PERIODE_PERSO and r["cloture"]["existante"] is None and n == 7, (r["cloture"], n))
    s, r, _ = _appel(R.analytics_cockpit, base(), ADMIN, periode="perso", du="2026-08-01", au="2026-09-01", vue="association")
    verifier("C. vue perso 1 août → 1er sept : NON clôturable", r["cloture"]["cloturable"] is False and r["cloture"]["raison"] == C.RAISON_PERIODE_PERSO)
    s, r, _ = _appel(R.analytics_cockpit, base(), ADMIN, periode="annee", mois="2026-08", vue="association")
    verifier("vue année : NON clôturable", r["cloture"]["cloturable"] is False and r["cloture"]["raison"] == C.RAISON_PERIODE_PERSO)
    s, r, _ = _appel(R.analytics_cockpit, base(), ADMIN, periode="mois", mois="2026-08", course_id="c-dim", vue="association")
    verifier("vue association avec filtre cours : non clôturable, raison « filtre cours »", r["cloture"]["cloturable"] is False and r["cloture"]["raison"] == C.RAISON_FILTRE_COURS)
    s, r, _ = _appel(R.analytics_cockpit, base(), ADMIN, periode="mois", mois="2026-09", vue="association")
    verifier("vue association septembre : non clôturable (« mois en cours »)", r["cloture"]["cloturable"] is False and r["cloture"]["raison"] == C.RAISON_MOIS_EN_COURS)
    s, r, n = _appel(R.analytics_cockpit, base(), ADMIN, periode="mois", mois="2026-08", vue="association")
    verifier("vue association août (admin) : clôturable, aucune clôture existante, 8 requêtes (+1 lecture clôture)", r["cloture"] == {"existante": None, "cloturable": True, "raison": "", "super_admin": True} and n == 8, (r["cloture"], n))
    s, r, _ = _appel(R.analytics_cockpit, base(), COACH, periode="mois", mois="2026-08", vue="association")
    verifier("vue association août (coach) : jamais clôturable (super_admin False)", r["cloture"]["cloturable"] is False and r["cloture"]["super_admin"] is False)
    ASSOC_AOUT = r and _appel(R.analytics_cockpit, base(), ADMIN, periode="mois", mois="2026-08", vue="association")[1]["association"]

    # ── D. contournement serveur : le POST ne lit ni periode, ni du/au, ni course_id ──
    import inspect as _inspect
    _sig = _inspect.signature(R.analytics_cloturer).parameters
    verifier("D. la route POST /cloture n'accepte que `mois` et `coach_id` (ni periode, ni du, ni au, ni course_id)",
             set(_sig) == {"request", "mois", "coach_id"}, list(_sig))
    s, d, _ = _appel(R.analytics_cloturer, base(), ADMIN, mois="")
    verifier("D. POST sans `mois` (tentative depuis une vue perso) -> 400, aucun snapshot", s == 400 and len(CLOTURES.docs) == 0, (s, d))
    s, d, _ = _appel(R.analytics_cloturer, base(), ADMIN, mois="2026-08-01")
    verifier("D. POST avec une date (du/au déguisé) -> 400, aucun snapshot", s == 400 and len(CLOTURES.docs) == 0, (s, d))

    # ── A / F. clôture réussie (mois passé, mode mois reconstruit par le serveur) ──
    s, d, n = _appel(R.analytics_cloturer, base(), ADMIN, mois="2026-08")
    verifier("clôture août par le super-admin -> 200, snapshot officiel v1", s == 200 and d["cloture"]["statut"] == "officiel" and d["cloture"]["version"] == 1 and d["cloture"]["cle"] == "2026-08:tous", (s, d))
    verifier("index uniques posés AVANT l'insertion (cle, id)", CLOTURES.index[:2] == [("cle", True), ("id", True)], CLOTURES.index)
    SNAP = CLOTURES.docs[0]
    verifier("snapshot = projection phase 3, valeur pour valeur (hors genere_le)", SNAP["bilan"] == C.bilan_figeable(ASSOC_AOUT) and "genere_le" not in SNAP["bilan"], list(SNAP["bilan"]))
    verifier("snapshot : métadonnées complètes (période, périmètre, dates, auteur, versions, empreinte)",
             SNAP["annee"] == 2026 and SNAP["mois"] == 8 and SNAP["periode"]["libelle"] == "Août 2026" and SNAP["perimetre"]["coach_id"] is None
             and SNAP["created_by"] == ADMIN and SNAP["created_at"].startswith("2026-09-15") and SNAP["schema_version"] == 1
             and SNAP["analytics_version"] == C.CLOTURE_ANALYTICS_VERSION and len(SNAP["hash"]) == 64 and "jwt" not in str(SNAP).lower())
    verifier("snapshot : empreinte = hash du bilan stocké (intégrité)", C.verifier_integrite(SNAP) and SNAP["hash"] == C.hash_bilan(ASSOC_AOUT))
    verifier("snapshot anonymisé (aucun e-mail, tél, code, Stripe, jeton dans le bilan)", AS.verifier_anonymat(SNAP["bilan"]) == [], AS.verifier_anonymat(SNAP["bilan"]))
    verifier("snapshot : CA officiel août = 280 (250 + 30 ; JUIL-1 est de juillet), 4 réservations", SNAP["bilan"]["finances"]["ca_prouve"] == 280.0 and SNAP["bilan"]["activite"]["reservations"] == 4)
    verifier("AUCUNE écriture sur une collection métier pendant la clôture", ECRITURES_METIER == [], ECRITURES_METIER)
    verifier("une seule insertion, dans la seule collection autorisée", CLOTURES.inserts == 1 and len(CLOTURES.docs) == 1)

    # ── idempotence : double clic, retry, simultanéité ──
    s, d, _ = _appel(R.analytics_cloturer, base(), ADMIN, mois="2026-08")
    verifier("second clic -> 409 « déjà clôturé », aucun second snapshot", s == 409 and d == C.RAISON_DEJA_CLOTURE and len(CLOTURES.docs) == 1, (s, d))
    s, d, _ = _appel(R.analytics_cloturer, base(), ADMIN, mois="2026-08")
    verifier("retry -> 409, toujours un seul snapshot, hash inchangé", s == 409 and len(CLOTURES.docs) == 1 and CLOTURES.docs[0]["hash"] == SNAP["hash"])
    # deux appels simultanés sur un mois vierge (juillet) : on contourne la pré-lecture en
    # faisant partir les deux coroutines ensemble ; l'index unique tranche.
    CL2 = _Clotures(None)
    b2 = _Base(copy.deepcopy(RESAS), copy.deepcopy(SUBS), copy.deepcopy(FICHES), copy.deepcopy(PAIEMENTS), copy.deepcopy(CARTES), CL2)
    CL2.base = b2
    _serveur(b2, ADMIN)
    async def _deux():
        async def _un():
            try:
                return 200, await R.analytics_cloturer(_Req(), mois="2026-07")
            except HTTPException as e:
                return e.status_code, e.detail
        return await asyncio.gather(_un(), _un())
    res = run(_deux())
    verifier("deux appels simultanés -> un seul snapshot officiel (un 200, un 409)", sorted(x[0] for x in res) == [200, 409] and len(CL2.docs) == 1, (res, len(CL2.docs)))

    # ── vue après clôture ──
    s, r, n = _appel(R.analytics_cockpit, base(), ADMIN, periode="mois", mois="2026-08", vue="association")
    verifier("vue association août après clôture : existante = méta du snapshot, plus clôturable, raison « déjà clôturé »",
             r["cloture"]["existante"]["id"] == SNAP["id"] and r["cloture"]["cloturable"] is False and r["cloture"]["raison"] == C.RAISON_DEJA_CLOTURE and "bilan" not in r["cloture"]["existante"])

    # ── archives et lecture ──
    s, r, _ = _appel(R.analytics_clotures, base(), ADMIN)
    verifier("archives (admin) : la clôture d'août, sans le bilan complet", s == 200 and [c["cle"] for c in r["clotures"]] == ["2026-08:tous"] and "bilan" not in r["clotures"][0])
    s, r, _ = _appel(R.analytics_clotures, base(), COACH)
    verifier("archives (coach) : uniquement son périmètre (aucune clôture « tous »)", s == 200 and r["clotures"] == [] and r["perimetre"] == COACH)
    s, r, _ = _appel(R.analytics_clotures, base(), "")
    verifier("archives sans jeton -> 401", s == 401)
    s, r, _ = _appel(R.analytics_cloture_lire, base(), ADMIN, id=SNAP["id"])
    verifier("lecture du snapshot (admin) : bilan figé + mention de clôture officielle", s == 200 and r["bilan"]["finances"]["ca_prouve"] == 280.0 and r["bilan"]["cloture"]["officiel"] is True and r["bilan"]["cloture"]["version"] == 1)
    s, r, _ = _appel(R.analytics_cloture_lire, base(), COACH, id=SNAP["id"])
    verifier("lecture d'un snapshot « tous » par un coach -> 403", s == 403, s)
    s, r, _ = _appel(R.analytics_cloture_lire, base(), ADMIN, id="inconnu")
    verifier("snapshot inconnu -> 404", s == 404, s)

    # ── exports officiels depuis le snapshot ──
    s, resp, _ = _appel(R.analytics_cloture_export, base(), ADMIN, id=SNAP["id"], format="csv")
    csv_txt = resp.body.decode("utf-8-sig")
    lignes = list(csv.reader(io.StringIO(csv_txt), delimiter=";"))
    verifier("export CSV officiel : BOM, ligne « Statut : BILAN OFFICIEL », CA 280,00, nom de fichier officiel",
             resp.body.startswith(b"\xef\xbb\xbf") and lignes[0][0] == "Statut" and lignes[0][1].startswith("BILAN OFFICIEL") and dict(zip(lignes[1], lignes[2]))["CA prouvé (CHF)"] == "280,00"
             and "bilan-officiel-afroboost-2026-08-v1.csv" in resp.headers["content-disposition"], (lignes[:1], resp.headers))
    s, resp, _ = _appel(R.analytics_cloture_export, base(), ADMIN, id=SNAP["id"], format="xlsx")
    feuilles = AS.lire_xlsx(resp.body)
    verifier("export XLSX officiel : 7 feuilles, Résumé porte « Statut BILAN OFFICIEL », CA 280", list(feuilles) == list(AS.NOMS_FEUILLES)
             and any(l[:1] == ["Statut"] and str(l[1]).startswith("BILAN OFFICIEL") for l in feuilles["Résumé"]) and {l[0]: l[1] for l in feuilles["Résumé"] if len(l) >= 2}["CA prouvé (CHF)"] == 280.0)
    s, resp, _ = _appel(R.analytics_cloture_export, base(), ADMIN, id=SNAP["id"], format="pdf")
    verifier("export PDF officiel : %PDF, généré depuis le snapshot", s == 200 and resp.body.startswith(b"%PDF"))
    try:
        from pypdf import PdfReader
        texte = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(io.BytesIO(resp.body)).pages)
        verifier("PDF officiel : mention « BILAN OFFICIEL — clôturé le … (v1) — empreinte … », CA 280,00 CHF, pied", "BILAN OFFICIEL" in texte and "empreinte " + SNAP["hash"][:12] in texte and "280,00 CHF" in texte and "ne sont pas incluses" in texte, texte[:300])
    except ImportError:
        verifier("pypdf absent", False, "pip install pypdf")
    s, resp, _ = _appel(R.analytics_cloture_export, base(), COACH, id=SNAP["id"], format="pdf")
    verifier("export officiel par un coach hors périmètre -> 403", s == 403)
    s, resp, _ = _appel(R.analytics_cloture_export, base(), "", id=SNAP["id"], format="pdf")
    verifier("export officiel sans jeton -> 401", s == 401)
    s, resp, _ = _appel(R.analytics_export, base(), ADMIN, format="csv", mois="2026-08")
    verifier("export DYNAMIQUE : pas de ligne « BILAN OFFICIEL » (les deux ne se confondent pas)", list(csv.reader(io.StringIO(resp.body.decode("utf-8-sig")), delimiter=";"))[0][0] != "Statut")

    # ═══ 3. TEST CRITIQUE D'IMMUTABILITÉ ═══
    # Une donnée historique d'août est « corrigée » : DECL-1 (tarif à la création, non prouvé)
    # reçoit un encaissement déclaré de 250 CHF -> le moteur dynamique doit monter à 530.
    SUBS_MODIF = copy.deepcopy(SUBS)
    for x in SUBS_MODIF:
        if x["code"] == "DECL-1":
            x["montant_encaisse"] = 250; x["origine_paiement"] = "twint"
    b3 = _Base(copy.deepcopy(RESAS), SUBS_MODIF, copy.deepcopy(FICHES), copy.deepcopy(PAIEMENTS), copy.deepcopy(CARTES), CLOTURES)
    CLOTURES.base = b3
    s, r, _ = _appel(R.analytics_cockpit, b3, ADMIN, periode="mois", mois="2026-08", vue="association")
    verifier("IMMUTABILITÉ 1 — le bilan DYNAMIQUE change : CA actuel 530", r["association"]["finances"]["ca_prouve"] == 530.0, r["association"]["finances"]["ca_prouve"])
    verifier("IMMUTABILITÉ 2 — la vue signale toujours la clôture existante (officiel ≠ dynamique)", r["cloture"]["existante"]["hash"] == SNAP["hash"])
    s, r2, _ = _appel(R.analytics_cloture_lire, b3, ADMIN, id=SNAP["id"])
    verifier("IMMUTABILITÉ 3 — le bilan OFFICIEL reste à 280", r2["bilan"]["finances"]["ca_prouve"] == 280.0)
    s, resp, _ = _appel(R.analytics_cloture_export, b3, ADMIN, id=SNAP["id"], format="csv")
    verifier("IMMUTABILITÉ 4 — le CSV officiel reste à 280,00", dict(zip(*list(csv.reader(io.StringIO(resp.body.decode("utf-8-sig")), delimiter=";"))[1:3]))["CA prouvé (CHF)"] == "280,00")
    s, resp, _ = _appel(R.analytics_export, b3, ADMIN, format="csv", mois="2026-08")
    verifier("IMMUTABILITÉ 5 — le CSV dynamique dit 530,00", dict(zip(*list(csv.reader(io.StringIO(resp.body.decode("utf-8-sig")), delimiter=";"))[:2]))["CA prouvé (CHF)"] == "530,00")
    s, d, _ = _appel(R.analytics_cloturer, b3, ADMIN, mois="2026-08")
    verifier("IMMUTABILITÉ 6 — re-clôturer avec les données corrigées -> 409, le snapshot n'est PAS écrasé", s == 409 and CLOTURES.docs[0]["hash"] == SNAP["hash"] and CLOTURES.docs[0]["bilan"]["finances"]["ca_prouve"] == 280.0)
    verifier("IMMUTABILITÉ 7 — intégrité du snapshot stocké vérifiable", C.verifier_integrite(CLOTURES.docs[0]))
    verifier("toujours AUCUNE écriture métier, une seule insertion (les 409 sont tranchés AVANT insert_one)", ECRITURES_METIER == [] and CLOTURES.inserts == 1, (ECRITURES_METIER, CLOTURES.inserts))
    R.vers_local = _shared_vers_local
except ImportError:
    verifier("fastapi absent : la route n'a pas pu être exercée", False, "installer fastapi")

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

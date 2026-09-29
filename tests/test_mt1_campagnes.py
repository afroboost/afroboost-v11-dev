#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MT-1 — CAMPAGNES MULTI-COACH : identité signée + périmètre propriétaire.

Ce banc exécute les VRAIES routes de campagne (`api/routes/campaign_routes.py`
et `api/server.py`) et le VRAI moteur de résolution des destinataires
(`_campagne_resoudre_contacts`, `launch_campaign` canal interne) sur le MongoDB
EN MÉMOIRE du banc `test_referral_pass_duo` (importé, jamais recopié), avec de
VRAIS JWT signés par le secret du banc.

Couvert :
  A. lectures (GET /campaigns, /campaigns/{id}, /campaigns-list, /campaign-debug) :
     A lit A 200 / A lit B 404 / B lit A 404 / anonyme 403 / X-User-Email seul 403 /
     JWT B + X-User-Email admin -> reste B / les DEUX super-admins : global ;
  B. mark-sent (route active server.py ET copie masquée) : anonyme bloqué, B sur A
     bloqué, `all([])` ne complète jamais, témoin positif ;
  C. destinataires : « tous » d'un coach = son portefeuille ; targetIds / groupes /
     selectedContacts / segments d'un autre coach retirés ; pas de repli sur
     « tous » ; super-admin et campagne historique : global INCHANGÉ ;
     canal interne de `launch_campaign` (moteur programmé compris) ;
  D. send-email : débit sur l'identité SIGNÉE (jamais l'en-tête), destinataire hors
     portefeuille refusé sans débit, super-admin exempté.

AUCUN réseau, AUCUN e-mail réel (Resend remplacé par un espion), AUCUNE base réelle.

Lancement :  python3 tests/test_mt1_campagnes.py
"""
import asyncio
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

S = H.S
import api.routes.campaign_routes as CR  # noqa: E402
import api.routes.contact_segments_routes as SEG  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


ADMIN = "contact.artboost@gmail.com"
# SA-1 : UN SEUL super-admin. L'ancien second compte est vérifié NON super-admin.
ADMIN2 = "afroboost.bassi@gmail.com"
A = "coach.a@exemple.test"
B = "coach.b@exemple.test"
MSG_403 = "Authentification coach requise — reconnectez-vous"


def req(jeton_de=None, entete=None, corps=None):
    e = {}
    if jeton_de:
        e["Authorization"] = "Bearer " + H.jeton_admin(jeton_de)
    if entete:
        e["X-User-Email"] = entete
    return H.Requete(corps if corps is not None else {}, e)


async def appel(coro):
    try:
        return 200, await coro
    except HTTPException as e:
        return e.status_code, e.detail


# ─────────────────────────────────────────────────────────────────────────────
# Base de départ
# ─────────────────────────────────────────────────────────────────────────────
ENVOIS = []


class ResendEspion:
    class Emails:
        @staticmethod
        def send(params):
            ENVOIS.append(dict(params))
            return {"id": "espion-%d" % len(ENVOIS)}


class _CollCampagnes(H._Coll):
    """Ajoute au faux Mongo l'opérateur POSITIONNEL `results.$.champ` (mark-sent)."""

    async def update_one(self, q, maj, upsert=False, **k):
        _pos = {c: v for c, v in (maj.get("$set") or {}).items() if ".$." in c}
        if not _pos:
            return await H._Coll.update_one(self, q, maj, upsert=upsert, **k)
        _sous = {c.split(".", 1)[1]: v for c, v in q.items() if c.startswith("results.")}
        for d in self.docs:
            if H._match(d, {c: v for c, v in q.items() if not c.startswith("results.")}):
                for r in d.get("results") or []:
                    if all(r.get(c) == v for c, v in _sous.items()):
                        for c, v in _pos.items():
                            r[c.split(".$.", 1)[1]] = v
                        return type("R", (), {"matched_count": 1, "modified_count": 1})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


class _CollSessions(H._Coll):
    """Ajoute au faux Mongo l'appartenance à un TABLEAU (`{"participant_ids": x}`),
    comme MongoDB — utilisée par les recherches de conversation des campagnes."""

    @staticmethod
    def _vue(d, q):
        v = dict(d)
        for c, attendu in (q or {}).items():
            if (not str(c).startswith("$") and not isinstance(attendu, (dict, list))
                    and isinstance(d.get(c), list) and attendu in d[c]):
                v[c] = attendu
        for sous in (q or {}).get("$or") or []:
            v = _CollSessions._vue(v, sous) if isinstance(sous, dict) else v
        return v

    async def find_one(self, q=None, proj=None, **k):
        for d in self.docs:
            if H._match(self._vue(d, q), q):
                return H._projeter(d, proj)
        return None


def base_de_depart():
    base = H._Base()
    base._c["campaigns"] = _CollCampagnes("campaigns")
    base._c["chat_sessions"] = _CollSessions("chat_sessions")
    base["coaches"].docs += [{"email": A, "credits": 5}, {"email": B, "credits": 5}]
    base["users"].docs += [
        {"id": "uA1", "name": "Alice A", "email": "a1@exemple.test", "coach_id": A},
        {"id": "uA2", "name": "Alain A", "email": "a2@exemple.test"},          # rattaché par chat_participants de A
        {"id": "uB1", "name": "Bruno B", "email": "b1@exemple.test", "coach_id": B},
        {"id": "uX", "name": "Xavier X", "email": "x@exemple.test"},           # sans propriétaire
    ]
    base["chat_participants"].docs += [
        {"id": "pA2", "name": "Alain A", "email": "a2@exemple.test", "coach_id": A},
        {"id": "pA3", "name": "Anne A", "email": "a3@exemple.test", "coach_id": A},
        {"id": "pB2", "name": "Berthe B", "email": "b2@exemple.test", "coach_id": B},
    ]
    base["chat_sessions"].docs += [
        {"id": "grp_A", "coach_id": A, "mode": "group", "title": "Groupe A",
         "participant_ids": ["uA1", "uB1"]},
        {"id": "grp_B", "coach_id": B, "mode": "group", "title": "Groupe B",
         "participant_ids": ["uB1"]},
    ]
    base["campaigns"].docs += [
        {"id": "cA", "name": "Camp A", "coach_id": A, "status": "draft", "results": [],
         "createdAt": "2026-09-01"},
        {"id": "cB", "name": "Camp B", "coach_id": B, "status": "scheduled",
         "scheduledAt": "2099-01-01T10:00:00+00:00", "results": [], "createdAt": "2026-09-02"},
        {"id": "cB2", "name": "Camp B2", "coach_id": B, "status": "sending",
         "results": [{"contactId": "k1", "channel": "email", "status": "pending"}],
         "createdAt": "2026-09-03"},
        {"id": "cAdm", "name": "Camp Admin", "coach_id": ADMIN, "status": "draft", "results": [],
         "createdAt": "2026-09-04"},
        {"id": "cHist", "name": "Camp Historique", "status": "draft", "results": [],
         "createdAt": "2026-09-05"},
    ]
    S.db = base
    CR.init_campaign_db(base)
    SEG.db = base
    S.resend = ResendEspion
    S.RESEND_AVAILABLE = True
    S.RESEND_API_KEY = "cle-fictive-banc-mt1"
    ENVOIS[:] = []
    return base


def camp(base, cid):
    return next(d for d in base["campaigns"].docs if d.get("id") == cid)


def emails(contacts):
    return sorted({(c.get("email") or "").lower() for c in contacts if c.get("email")})


# ─────────────────────────────────────────────────────────────────────────────
# A. Lectures
# ─────────────────────────────────────────────────────────────────────────────
async def partie_lectures():
    base_de_depart()
    c, r = await appel(CR.get_campaign("cA", req(A)))
    verifier("A1. A lit SA campagne -> 200", c == 200 and r.get("id") == "cA", (c, r))
    c, r = await appel(CR.get_campaign("cB", req(A)))
    verifier("A2. A lit la campagne de B -> 404 (existence non révélée)", c == 404, (c, r))
    c, r = await appel(CR.get_campaign("cA", req(B)))
    verifier("A3. B lit la campagne de A -> 404", c == 404, (c, r))
    c, r = await appel(CR.get_campaign("cA", req()))
    verifier("A4. anonyme -> 403 + message « reconnectez-vous »", c == 403 and r == MSG_403, (c, r))
    c, r = await appel(CR.get_campaign("cA", req(entete=A)))
    verifier("A5. X-User-Email de A SANS jeton -> 403", c == 403, (c, r))
    c, r = await appel(CR.get_campaign("cB", req(entete=ADMIN)))
    verifier("A6. X-User-Email super-admin SANS jeton -> 403", c == 403, (c, r))
    c, r = await appel(CR.get_campaign("cB", req(ADMIN)))
    verifier("A7. super-admin signé lit la campagne de B -> 200", c == 200 and r.get("id") == "cB", (c, r))
    c, r = await appel(CR.get_campaign("cB", req(ADMIN2)))
    verifier("A8. SA-1 : ancien 2e super-admin (afroboost.bassi) signé -> refus", c in (403, 404), (c, r))

    # GET /campaigns
    c, r = await appel(CR.get_campaigns(req(A)))
    verifier("A9. liste A = uniquement ses campagnes", c == 200 and [x["id"] for x in r] == ["cA"], (c, r))
    c, r = await appel(CR.get_campaigns(req(B, entete=ADMIN)))
    verifier("A10. JWT B + X-User-Email super-admin -> reste B (2 campagnes de B)",
             c == 200 and sorted(x["id"] for x in r) == ["cB", "cB2"], (c, r))
    c, r = await appel(CR.get_campaigns(req(entete=ADMIN)))
    verifier("A11. X-User-Email super-admin anonyme -> 403 (fin du passe-partout)", c == 403, (c, r))
    c, r = await appel(CR.get_campaigns(req()))
    verifier("A12. anonyme -> 403", c == 403, (c, r))
    for adm, n in ((ADMIN, "A13"),):
        c, r = await appel(CR.get_campaigns(req(adm)))
        verifier("%s. super-admin %s -> TOUTES les campagnes (5)" % (n, adm), c == 200 and len(r) == 5, (c, len(r) if c == 200 else r))
    c, r = await appel(CR.get_campaigns(req(ADMIN2)))
    verifier("A14. SA-1 : ancien 2e super-admin -> aucune vue globale (refus)", c == 403, (c, r))
    c, r = await appel(CR.get_campaigns(req("inconnu@exemple.test")))
    verifier("A15. jeton valide d'un non-coach -> 403", c == 403, (c, r))

    # GET /campaigns-list (server.py)
    c, r = await appel(S.get_campaigns_list(req(A)))
    verifier("A16. /campaigns-list A = ses campagnes", c == 200 and [x["id"] for x in r] == ["cA"], (c, r))
    c, r = await appel(S.get_campaigns_list(req(entete=ADMIN)))
    verifier("A17. /campaigns-list X-User-Email admin sans jeton -> 403", c == 403, (c, r))
    c, r = await appel(S.get_campaigns_list(req(B, entete=ADMIN)))
    verifier("A18. /campaigns-list JWT B + en-tête admin -> reste B",
             c == 200 and sorted(x["id"] for x in r) == ["cB", "cB2"], (c, r))
    c, r = await appel(S.get_campaigns_list(req(ADMIN2)))
    verifier("A19. SA-1 : /campaigns-list ancien 2e super-admin -> refus", c == 403, (c, r))

    # GET /campaign-debug (server.py)
    c, r = await appel(S.get_campaign_debug("cA", req()))
    verifier("A20. /campaign-debug anonyme -> 403", c == 403, (c, r))
    c, r = await appel(S.get_campaign_debug("cA", req(A)))
    verifier("A21. /campaign-debug coach (même sur SA campagne) -> 403", c == 403, (c, r))
    c, r = await appel(S.get_campaign_debug("cB", req(entete=ADMIN)))
    verifier("A22. /campaign-debug en-tête admin sans jeton -> 403", c == 403, (c, r))
    c, r = await appel(S.get_campaign_debug("cB", req(ADMIN)))
    verifier("A23. /campaign-debug super-admin signé -> 200", c == 200 and r.get("id") == "cB", (c, r))


# ─────────────────────────────────────────────────────────────────────────────
# B. mark-sent
# ─────────────────────────────────────────────────────────────────────────────
async def partie_mark_sent():
    for nom_route, route in (("server.py (active)", S.mark_campaign_sent),
                             ("campaign_routes (masquée)", CR.mark_campaign_sent)):
        base = base_de_depart()
        corps = {"contactId": "k1", "channel": "email"}
        c, r = await appel(route("cB", req(corps=corps)))
        verifier("B1. %s : anonyme -> 403, programmée intacte" % nom_route,
                 c == 403 and camp(base, "cB")["status"] == "scheduled", (c, r))
        c, r = await appel(route("cB", req(entete=B, corps=corps)))
        verifier("B2. %s : X-User-Email du propriétaire sans jeton -> 403" % nom_route,
                 c == 403 and camp(base, "cB")["status"] == "scheduled", (c, r))
        c, r = await appel(route("cB", req(A, corps=corps)))
        verifier("B3. %s : A sur la campagne de B -> refusé, intacte" % nom_route,
                 c in (403, 404) and camp(base, "cB")["status"] == "scheduled", (c, r))
        c, r = await appel(route("cB", req(B, corps=corps)))
        verifier("B4. %s : propriétaire, campagne SANS résultat -> jamais `completed` (all([]))" % nom_route,
                 c == 200 and camp(base, "cB")["status"] == "scheduled", (c, camp(base, "cB")["status"]))
        c, r = await appel(route("cB2", req(B, corps=corps)))
        verifier("B5. %s : témoin — dernier résultat marqué -> `completed`" % nom_route,
                 c == 200 and camp(base, "cB2")["status"] == "completed", (c, camp(base, "cB2")["status"]))
        c, r = await appel(route("cB", req(B, corps={"contactId": {"$ne": None}, "channel": "email"})))
        verifier("B6. %s : opérateur Mongo dans le corps -> 400" % nom_route, c == 400, (c, r))
        c, r = await appel(route("cB", req(ADMIN2, corps=corps)))
        verifier("B7. %s : SA-1 — ancien 2e super-admin signé -> refusé" % nom_route, c in (403, 404), (c, r))
        c, r = await appel(route("cB", req(ADMIN, corps=corps)))
        verifier("B7b. %s : super-admin signé -> autorisé" % nom_route, c == 200, (c, r))


# ─────────────────────────────────────────────────────────────────────────────
# C. Destinataires
# ─────────────────────────────────────────────────────────────────────────────
async def resoudre(base, **champs):
    doc = {"id": "tmp", "name": "tmp", "targetType": "selected", "targetIds": [],
           "selectedContacts": [], "channels": {"email": True}}
    doc.update(champs)
    ids = [t for t in (doc.get("targetIds") or []) if t and str(t).strip()]
    return await S._campagne_resoudre_contacts(doc, ids)


async def partie_destinataires():
    base = base_de_depart()
    PORTEFEUILLE_A = ["a1@exemple.test", "a2@exemple.test", "a3@exemple.test"]

    r = await resoudre(base, coach_id=A, targetType="all")
    verifier("C1. campagne de A « tous » -> uniquement le portefeuille de A",
             emails(r) == PORTEFEUILLE_A, emails(r))
    r = await resoudre(base, coach_id=A, targetIds=["uA1", "uB1", "pB2", "uX"])
    verifier("C2. targetIds avec contacts de B / sans propriétaire -> retirés", emails(r) == ["a1@exemple.test"], emails(r))
    r = await resoudre(base, coach_id=A, targetType="all", targetIds=["uB1"])
    verifier("C3. cible 100 % hors portefeuille -> AUCUN destinataire (pas de repli « tous »)", r == [], emails(r))
    r = await resoudre(base, coach_id=A, targetIds=["grp_A"])
    verifier("C4. groupe de A déplié : le membre de B est écarté", emails(r) == ["a1@exemple.test"], emails(r))
    r = await resoudre(base, coach_id=A, targetIds=["grp_B"])
    verifier("C5. groupe de B dans une campagne de A -> retiré", r == [], emails(r))
    r = await resoudre(base, coach_id=A, selectedContacts=["pA3", "pB2"])
    verifier("C6. selectedContacts : contact de B retiré", emails(r) == ["a3@exemple.test"], emails(r))

    _orig = SEG._calcule_personnes

    async def faux_calcule_personnes(*a, **k):
        return ([{"id": i, "etiquettes": ["email"]} for i in ("uA1", "uB1", "pB2", "uX", "pA3")], {})
    SEG._calcule_personnes = faux_calcule_personnes
    try:
        r = await resoudre(base, coach_id=A, targetCategories=["email"])
        verifier("C7. segment global intersecté avec le portefeuille de A",
                 emails(r) == ["a1@exemple.test", "a3@exemple.test"], emails(r))
        r = await resoudre(base, coach_id=ADMIN, targetCategories=["email"])
        verifier("C8. segment d'une campagne super-admin -> global inchangé (5)", len(r) == 5, emails(r))
    finally:
        SEG._calcule_personnes = _orig

    TOUS = ["a1@exemple.test", "a2@exemple.test", "b1@exemple.test", "x@exemple.test"]
    r = await resoudre(base, targetType="all", coach_id=ADMIN2)
    verifier("C9. SA-1 : « tous » d'une campagne de l'ancien 2e super-admin -> PAS le global",
             emails(r) != TOUS, emails(r))
    for nom, cid in (("super-admin", ADMIN), ("historique sans coach_id", None),
                     ("historique « bassi_default »", "bassi_default"), ("historique vide", "")):
        champs = {"targetType": "all"}
        if cid is not None:
            champs["coach_id"] = cid
        r = await resoudre(base, **champs)
        verifier("C9. « tous » %s -> db.users global INCHANGÉ" % nom, emails(r) == TOUS, emails(r))
    r = await resoudre(base, coach_id=ADMIN, targetIds=["uB1", "grp_B"])
    verifier("C10. super-admin : cibles de B conservées (non-régression admin)",
             emails(r) == ["b1@exemple.test"], emails(r))

    # Canal INTERNE via le VRAI launch_campaign (même chemin que le moteur programmé).
    base["campaigns"].docs.append({"id": "cInt", "name": "Interne A", "coach_id": A, "status": "draft",
                                   "results": [], "channels": {"internal": True},
                                   "targetIds": ["uA1", "grp_B", "uB1"], "message": "Bonjour {prénom}"})
    res = await S.launch_campaign("cInt")
    cibles = sorted(x.get("targetId") for x in (res.get("results") or []) if x.get("channel") == "internal")
    msgs_grp_b = [m for m in base["chat_messages"].docs if m.get("session_id") == "grp_B"]
    verifier("C11. launch_campaign (interne) d'un coach : seule la cible de A est servie",
             cibles == ["uA1"] and not msgs_grp_b, (cibles, len(msgs_grp_b)))

    # Moteur programmé : aucun appelant, le propriétaire décide.
    base["campaigns"].docs.append({"id": "cProg", "name": "Prog A", "coach_id": A, "status": "scheduled",
                                   "scheduledAt": "2020-01-01T00:00:00+00:00", "results": [],
                                   "channels": {"internal": True}, "targetIds": ["grp_B"], "message": "x"})
    await S._v328_run_due_campaigns(origine="BANC")
    verifier("C12. moteur programmé : campagne de A visant le groupe de B -> rien posté dans grp_B",
             not [m for m in base["chat_messages"].docs if m.get("session_id") == "grp_B"])


# ─────────────────────────────────────────────────────────────────────────────
# C-bis. Conversations (audit P1) + filtrage groupé (audit P2)
# ─────────────────────────────────────────────────────────────────────────────
async def partie_conversations():
    base = base_de_depart()
    next(d for d in base["coaches"].docs if d["email"] == A)["name"] = "Studio A"
    # Contact PARTAGÉ : dans le portefeuille de A, mais sa conversation existante est chez B.
    base["users"].docs.append({"id": "uS", "name": "Sam Partage", "email": "sam.partage@mail-client.ch", "coach_id": A})
    base["chat_sessions"].docs.append({"id": "sB", "coach_id": B, "mode": "user",
                                       "participantEmail": "sam.partage@mail-client.ch", "participant_ids": ["uS"]})

    base["campaigns"].docs.append({"id": "cIntS", "name": "Interne A", "coach_id": A, "status": "draft",
                                   "results": [], "channels": {"internal": True},
                                   "targetIds": ["uS"], "message": "Bonjour"})
    await S.launch_campaign("cIntS")
    dans_sb = [m for m in base["chat_messages"].docs if m.get("session_id") == "sB"]
    msgs = list(base["chat_messages"].docs)
    sess_a = [d for d in base["chat_sessions"].docs if d.get("coach_id") == A and "uS" in (d.get("participant_ids") or [])]
    verifier("P1a. canal interne : le message de A n'atterrit JAMAIS dans la conversation du contact avec B",
             not dans_sb, len(dans_sb))
    verifier("P1b. ... une session appartenant à A (coach_id=A) est créée et reçoit le message",
             len(sess_a) == 1 and any(m.get("session_id") == sess_a[0]["id"] for m in msgs),
             [d.get("id") for d in sess_a])
    _m = next((m for m in msgs if sess_a and m.get("session_id") == sess_a[0]["id"]), {})
    verifier("P1c. ... expéditeur = nom du coach propriétaire (pas « Coach Bassi »)",
             _m.get("sender_name") == "Studio A", _m.get("sender_name"))

    # Relance : la session de A est RÉUTILISÉE (pas de nouvelle session).
    base["campaigns"].docs.append({"id": "cIntS2", "name": "Interne A 2", "coach_id": A, "status": "draft",
                                   "results": [], "channels": {"internal": True},
                                   "targetIds": ["uS"], "message": "Re"})
    await S.launch_campaign("cIntS2")
    sess_a2 = [d for d in base["chat_sessions"].docs if d.get("coach_id") == A and "uS" in (d.get("participant_ids") or [])]
    verifier("P1d. 2e campagne de A : réutilise SA session, toujours rien chez B",
             len(sess_a2) == 1 and not [m for m in base["chat_messages"].docs if m.get("session_id") == "sB"])

    # Copie omnicanale (e-mail / WhatsApp) — même règle.
    avant = len(base["chat_sessions"].docs)
    await S._save_campaign_chat_message(contact_id="uS", content="omni", channel="email",
                                        campaign_id="cX", campaign_name="X", proprietaire=A,
                                        sender_name="Studio A")
    omni = [m for m in base["chat_messages"].docs if m.get("content") == "omni"]
    verifier("P1e. copie omnicanale d'une campagne de A : jamais dans sB, session de A",
             omni and omni[0]["session_id"] != "sB"
             and next(d for d in base["chat_sessions"].docs if d["id"] == omni[0]["session_id"]).get("coach_id") == A
             and len(base["chat_sessions"].docs) == avant, (omni[0]["session_id"] if omni else None))

    # Super-admin / historique : comportement INCHANGÉ (retrouve la conversation existante).
    base["campaigns"].docs.append({"id": "cIntAdm", "name": "Interne admin", "coach_id": ADMIN, "status": "draft",
                                   "results": [], "channels": {"internal": True},
                                   "targetIds": ["uS"], "message": "Admin"})
    await S.launch_campaign("cIntAdm")
    adm = [m for m in base["chat_messages"].docs if m.get("content") == "Admin"]
    verifier("P1f. campagne super-admin : session existante utilisée, expéditeur « Coach Bassi » (inchangé)",
             adm and adm[0]["session_id"] == "sB" and adm[0]["sender_name"] == "Coach Bassi",
             adm and (adm[0]["session_id"], adm[0]["sender_name"]))
    await S._save_campaign_chat_message(contact_id="uS", content="omni-adm", channel="email")
    oa = [m for m in base["chat_messages"].docs if m.get("content") == "omni-adm"]
    verifier("P1g. copie omnicanale sans propriétaire : recherche historique inchangée",
             oa and oa[0]["session_id"] == "sB" and oa[0]["sender_name"] == "Coach Bassi")

    # Audit P2 : filtrage GROUPÉ ($in) — aucun find_one par cible.
    coll = base["chat_sessions"]
    compteur = {"find_one": 0, "find": 0}
    _fo, _f = coll.find_one, coll.find

    async def fo(*a, **k):
        compteur["find_one"] += 1
        return await _fo(*a, **k)

    def f(*a, **k):
        compteur["find"] += 1
        return _f(*a, **k)
    coll.find_one, coll.find = fo, f
    try:
        pf = await CR.mt1_portefeuille(base, A)
        ids = ["etranger-%d" % i for i in range(900)] + ["uA1", "grp_A", "grp_B", "x$y"]
        garde = await CR.mt1_filtrer_cibles(base, pf, ids)
    finally:
        coll.find_one, coll.find = _fo, _f
    verifier("P2a. 904 cibles filtrées en UNE requête groupée (0 find_one)",
             compteur == {"find_one": 0, "find": 1}, compteur)
    verifier("P2b. ... résultat identique à la règle : uA1 + grp_A gardés, le reste retiré",
             garde == ["uA1", "grp_A"], garde[:5])


# ─────────────────────────────────────────────────────────────────────────────
# D. send-email
# ─────────────────────────────────────────────────────────────────────────────
def credits(base, email):
    return next(d for d in base["coaches"].docs if d["email"] == email)["credits"]


async def partie_send_email():
    corps = lambda dest: {"to_email": dest, "to_name": "X", "subject": "S", "message": "M"}  # noqa: E731
    base = base_de_depart()
    c, r = await appel(S.send_campaign_email(req(corps=corps("a1@exemple.test"))))
    verifier("D1. anonyme -> 403, aucun envoi", c == 403 and not ENVOIS, (c, r))
    c, r = await appel(S.send_campaign_email(req(entete=A, corps=corps("a1@exemple.test"))))
    verifier("D2. X-User-Email seul -> 403, aucun envoi", c == 403 and not ENVOIS, (c, r))

    c, r = await appel(S.send_campaign_email(req(A, entete=B, corps=corps("a1@exemple.test"))))
    verifier("D3. JWT A + en-tête B : envoi à un contact de A -> 200",
             c == 200 and len(ENVOIS) == 1 and ENVOIS[0]["to"] == ["a1@exemple.test"], (c, r))
    verifier("D4. ... débit sur l'identité SIGNÉE (A -1), B intact",
             credits(base, A) == 4 and credits(base, B) == 5, (credits(base, A), credits(base, B)))

    ENVOIS[:] = []
    c, r = await appel(S.send_campaign_email(req(A, corps=corps("b1@exemple.test"))))
    verifier("D5. A écrit à un contact de B -> 403, aucun envoi, aucun débit",
             c == 403 and not ENVOIS and credits(base, A) == 4, (c, r, credits(base, A)))
    c, r = await appel(S.send_campaign_email(req(A, corps=corps("inconnu.total@exemple.test"))))
    verifier("D6. A écrit à une adresse libre -> 403 (plus de relais)", c == 403 and not ENVOIS, (c, r))
    c, r = await appel(S.send_campaign_email(req(A, corps=corps(A))))
    verifier("D7. A s'écrit à lui-même (e-mail de test) -> 200", c == 200 and len(ENVOIS) == 1, (c, r))

    ENVOIS[:] = []
    c, r = await appel(S.send_campaign_email(req(ADMIN2, corps=corps("b1@exemple.test"))))
    verifier("D8. SA-1 : ancien 2e super-admin -> destinataire libre REFUSÉ, aucun envoi",
             c in (403, 404) and not ENVOIS, (c, r))
    for adm in (ADMIN,):
        c, r = await appel(S.send_campaign_email(req(adm, corps=corps("b1@exemple.test"))))
        verifier("D8. super-admin %s : destinataire libre autorisé" % adm, c == 200, (c, r))
    verifier("D9. ... et aucun débit de coach pour le super-admin",
             credits(base, A) == 3 and credits(base, B) == 5, (credits(base, A), credits(base, B)))


# ─────────────────────────────────────────────────────────────────────────────
# E. Routes déjà sûres : gardées (preuve)
# ─────────────────────────────────────────────────────────────────────────────
async def partie_routes_existantes():
    base = base_de_depart()
    c, r = await appel(S.update_campaign("cB", req(A, corps={"name": "pirate"})))
    verifier("E1. PUT : A sur la campagne de B -> 403, intacte", c == 403 and camp(base, "cB")["name"] == "Camp B", (c, r))
    c, r = await appel(S.update_campaign("cB", req(ADMIN2, corps={"name": "pirate SA-1"})))
    verifier("E2. PUT : SA-1 — ancien 2e super-admin signé -> 403, intacte",
             c == 403 and camp(base, "cB")["name"] == "Camp B", (c, r))
    c, r = await appel(S.update_campaign("cB", req(ADMIN, corps={"name": "Camp B"})))
    verifier("E2b. PUT : super-admin signé -> 200 (ne dépend plus de `_autorise`)", c == 200, (c, r))
    c, r = await appel(CR.delete_campaign("cB", req(entete=ADMIN)))
    verifier("E3. DELETE : en-tête admin sans jeton -> 403", c == 403 and any(d["id"] == "cB" for d in base["campaigns"].docs), (c, r))
    c, r = await appel(CR.delete_campaign("cB", req(A)))
    verifier("E4. DELETE : A sur B -> 403", c == 403, (c, r))
    c, r = await appel(CR.purge_all_campaigns(req()))
    verifier("E5. purge : anonyme -> 403", c == 403, (c, r))
    c, r = await appel(S.v451_lancer_campagne_http("cB", req(A)))
    verifier("E6. launch : A sur B -> 403", c == 403, (c, r))
    c, r = await appel(S.v451_lancer_campagne_http("cB", req()))
    verifier("E7. launch : anonyme -> 403", c == 403, (c, r))
    c, r = await appel(S.r3_previsualiser_campagne("cB", req(A)))
    verifier("E8. preview : A sur B -> 403", c == 403, (c, r))
    c, r = await appel(S.r3_previsualiser_campagne("cB", req()))
    verifier("E9. preview : anonyme -> 403", c == 403, (c, r))
    c, r = await appel(CR.get_campaigns_error_logs(req()))
    verifier("E10. logs : anonyme -> 403", c == 403, (c, r))


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_lectures, partie_mark_sent, partie_destinataires, partie_conversations,
                   partie_send_email, partie_routes_existantes):
        try:
            boucle.run_until_complete(partie())
        except Exception as e:  # une partie qui plante est un échec, pas un arrêt du banc
            import traceback
            traceback.print_exc()
            verifier("%s s'exécute sans exception" % partie.__name__, False, repr(e))
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("=" * 78)
    print("MT-1 — CAMPAGNES MULTI-COACH : %d vérifications" % len(RESULTATS))
    print("=" * 78)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:400])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

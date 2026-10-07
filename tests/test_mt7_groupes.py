#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MT-7 — GROUPES DU CHAT MULTI-COACH : identité signée + propriétaire.

Ce banc exécute les VRAIES routes des groupes (`/chat/groups*`, `/groups/join`,
`/chat/group-message`, `/chat/links*` sur une session de groupe, routes
d'amorçage `/create-*-group`) et la VRAIE résolution des destinataires de
campagne (`_campagne_resoudre_contacts`) sur le MongoDB EN MÉMOIRE du banc
`test_referral_pass_duo` (importé, jamais recopié), avec de VRAIS JWT signés.

Couvert :
  L. liste : A voit A, B voit B, anonyme 403, X-User-Email seul 403, JWT B +
     en-tête A -> reste B, les DEUX super-admins : global (historique compris),
     e-mail d'un membre hors portefeuille masqué ;
  M. modification / suppression / visibilité : autre coach 404, anonyme 403,
     en-tête seul 403, JWT B + en-tête A 404, historique sans coach_id : 404
     pour un coach, 200 pour le super-admin ; liste blanche (coach_id, link_token
     jamais modifiables) ;
  N. membres : création et modification n'ajoutent QUE des contacts du
     portefeuille du propriétaire ; un membre déjà présent n'est pas éjecté ;
  J. adhésion : propriétaire (portefeuille), invité muni du jeton, membre déjà
     inscrit ; refus sinon ; `/groups/join` sans regex ni session privée ;
  P. vue membre `/chat/groups/public` : jamais member_ids / link_token / prompt ;
  X. routes voisines : `/chat/links*` ne touchent plus un groupe, diffusion
     globale et amorçage réservés au super-admin signé ;
  C. campagnes : groupe de B refusé pour A, groupe de A = membres du
     portefeuille A seulement, repli `chat_groups` d'un autre coach ignoré.

AUCUN réseau, AUCUNE base réelle.
Lancement :  python3 tests/test_mt7_groupes.py
"""
import asyncio
import json
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

S = H.S
import api.routes.campaign_routes as CR  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


ADMIN = "contact.artboost@gmail.com"
# SA-1 : UN SEUL super-admin. L'ancien second compte est vérifié NON super-admin.
ADMIN2 = "afroboost.bassi@gmail.com"
A = "coach.a@exemple.test"
B = "coach.b@exemple.test"

GA, GB, GH = "aaaa1111-0000-0000-0000-000000000001", "bbbb2222-0000-0000-0000-000000000002", \
    "hhhh3333-0000-0000-0000-000000000003"
SA, SB, SH = "grp_aaaa1111", "grp_bbbb2222", "grp_hhhh3333"


def req(jeton_de=None, entete=None, corps=None, params=None):
    e = {}
    if jeton_de:
        e["Authorization"] = "Bearer " + H.jeton_admin(jeton_de)
    if entete:
        e["X-User-Email"] = entete
    return H.Requete(corps if corps is not None else {}, e, params)


async def appel(coro):
    try:
        return 200, await coro
    except HTTPException as e:
        return e.status_code, e.detail


class _CollTableaux(H._Coll):
    """Faux Mongo + appartenance à un TABLEAU (`{"participant_ids": x}`) et
    `$addToSet`, comme MongoDB."""

    @staticmethod
    def _vue(d, q):
        v = dict(d)
        for c, attendu in (q or {}).items():
            if (not str(c).startswith("$") and not isinstance(attendu, (dict, list))
                    and isinstance(d.get(c), list) and attendu in d[c]):
                v[c] = attendu
        for sous in (q or {}).get("$or") or []:
            v = _CollTableaux._vue(v, sous) if isinstance(sous, dict) else v
        return v

    def find(self, q=None, proj=None, **k):
        return H._Curseur([H._projeter(d, proj) for d in self.docs if H._match(self._vue(d, q), q)])

    async def find_one(self, q=None, proj=None, **k):
        for d in self.docs:
            if H._match(self._vue(d, q), q):
                return H._projeter(d, proj)
        return None

    def _appliquer(self, d, maj):
        H._Coll._appliquer(self, d, maj)
        for cle, v in (maj.get("$addToSet") or {}).items():
            lst = list(d.get(cle) or [])
            if v not in lst:
                lst.append(v)
            d[cle] = lst

    async def update_one(self, q, maj, upsert=False, **k):
        for d in self.docs:
            if H._match(self._vue(d, q), q):
                self._appliquer(d, maj)
                return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
        return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()


def base_de_depart(strict=False):
    base = H._Base()
    for nom in ("chat_sessions", "chat_groups", "users", "chat_participants"):
        base._c[nom] = _CollTableaux(nom)
    base["coaches"].docs += [{"email": A, "credits": 5}, {"email": B, "credits": 5}]
    if strict:
        base["feature_flags"].docs.append({"id": "feature_flags", S.V349_FLAG: True})
    base["chat_participants"].docs += [
        {"id": "pA1", "name": "Alice A", "email": "a1@exemple.test", "coach_id": A},
        {"id": "pA2", "name": "Alain A", "email": "a2@exemple.test", "coach_id": A},
        {"id": "pB1", "name": "Bruno B", "email": "b1@exemple.test", "coach_id": B},
        {"id": "pB2", "name": "Berthe B", "email": "b2@exemple.test", "coach_id": B},
        {"id": "pX", "name": "Xavier X", "email": "x@exemple.test"},
    ]
    base["users"].docs += [
        {"id": "uA3", "name": "Anne A", "email": "a3@exemple.test", "coach_id": A},
        {"id": "uB3", "name": "Basile B", "email": "b3@exemple.test", "coach_id": B},
    ]
    base["chat_groups"].docs += [
        {"id": GA, "name": "Groupe A", "coach_id": A, "member_ids": ["pA1", "pB1"],
         "system_prompt": "prompt A", "is_ai_active": True, "link_token": "tokA",
         "created_at": "2026-09-01", "is_deleted": False},
        {"id": GB, "name": "Groupe B", "coach_id": B, "member_ids": ["pB1"],
         "system_prompt": "prompt B", "is_ai_active": True, "link_token": "tokB",
         "created_at": "2026-09-02", "is_deleted": False},
        {"id": GH, "name": "Groupe historique", "member_ids": ["pX"],
         "system_prompt": "", "is_ai_active": False, "link_token": "tokH",
         "created_at": "2026-01-01", "is_deleted": False},
    ]
    base["chat_sessions"].docs += [
        {"id": SA, "title": "Groupe A", "mode": "group", "coach_id": A, "group_id": GA,
         "participant_ids": ["pA1", "pB1"], "link_token": "tokA"},
        {"id": SB, "title": "Groupe B", "mode": "group", "coach_id": B, "group_id": GB,
         "participant_ids": ["pB1"], "link_token": "tokB"},
        {"id": SH, "title": "Groupe historique", "mode": "group", "group_id": GH,
         "participant_ids": ["pX"], "link_token": "tokH"},
        {"id": "sess-priv", "title": "", "mode": "human", "coach_id": B,
         "participant_ids": ["pB2"], "link_token": "privtok"},
        # Session de A SANS participant_ids qui pointe vers le groupe de B (repli chat_groups)
        {"id": "grp_piege000", "title": "Piège", "mode": "group", "coach_id": A, "group_id": GB,
         "participant_ids": []},
    ]
    S.db = base
    CR.init_campaign_db(base)
    return base


def groupe(base, gid):
    return next(d for d in base["chat_groups"].docs if d.get("id") == gid)


def session(base, sid):
    return next(d for d in base["chat_sessions"].docs if d.get("id") == sid)


def instantane(base):
    return json.dumps([base["chat_groups"].docs, base["chat_sessions"].docs], sort_keys=True, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# L. Liste
# ─────────────────────────────────────────────────────────────────────────────
async def partie_liste():
    for strict in (False, True):
        t = " [drapeau %s]" % ("ON" if strict else "OFF")
        base_de_depart(strict)
        c, r = await appel(S.get_chat_groups(req(A)))
        verifier("L1. A liste -> uniquement ses groupes" + t, c == 200 and [g["id"] for g in r] == [GA], (c, r))
        c, r = await appel(S.get_chat_groups(req(B)))
        verifier("L2. B liste -> uniquement ses groupes" + t, c == 200 and [g["id"] for g in r] == [GB], (c, r))
        c, r = await appel(S.get_chat_groups(req()))
        verifier("L3. anonyme -> 403" + t, c == 403, (c, r))
        c, r = await appel(S.get_chat_groups(req(entete=A)))
        verifier("L4. X-User-Email de A seul -> 403" + t, c == 403, (c, r))
        c, r = await appel(S.get_chat_groups(req(entete=ADMIN)))
        verifier("L5. X-User-Email super-admin seul -> 403" + t, c == 403, (c, r))
        c, r = await appel(S.get_chat_groups(req(B, entete=A)))
        verifier("L6. JWT B + en-tête A -> reste B" + t, c == 200 and [g["id"] for g in r] == [GB], (c, r))
        c, r = await appel(S.get_chat_groups(req(ADMIN)))
        verifier("L7. super-admin -> global (historique compris)" + t,
                 c == 200 and sorted(g["id"] for g in r) == sorted([GA, GB, GH]), (c, r))
        c, r = await appel(S.get_chat_groups(req(ADMIN2)))
        verifier("L8. SA-1 : ancien 2e super-admin -> AUCUNE vue globale" + t,
                 c in (403, 404) or (c == 200 and not r), (c, r))
    base_de_depart()
    c, r = await appel(S.get_chat_groups(req(A)))
    info = {m["id"]: m for m in (r[0].get("members_info") if c == 200 and r else [])}
    verifier("L9. A : e-mail du membre de B (hors portefeuille) masqué, le sien visible",
             info.get("pA1", {}).get("email") == "a1@exemple.test" and info.get("pB1", {}).get("email") == "",
             info)
    c, r = await appel(S.get_chat_groups(req(ADMIN)))
    info = {m["id"]: m for g in (r if c == 200 else []) for m in g.get("members_info", [])}
    verifier("L10. super-admin : e-mails visibles", info.get("pB1", {}).get("email") == "b1@exemple.test", info)


# ─────────────────────────────────────────────────────────────────────────────
# M. Mutations
# ─────────────────────────────────────────────────────────────────────────────
MUTATIONS = {
    "modifier": lambda gid, r: S.update_chat_group(gid, r),
    "supprimer": lambda gid, r: S.delete_chat_group(gid, r),
    "visibilité": lambda gid, r: S.v198_toggle_group_visibility(gid, r),
}
CORPS = {"modifier": {"name": "piraté", "system_prompt": "x"}, "supprimer": {},
         "visibilité": {"visible_to_subscribers": False}}


async def partie_mutations():
    for nom, f in MUTATIONS.items():
        for strict in (False, True):
            t = " [%s, drapeau %s]" % (nom, "ON" if strict else "OFF")
            base = base_de_depart(strict)
            avant = instantane(base)
            c, r = await appel(f(GB, req(A, corps=CORPS[nom])))
            verifier("M1. A sur le groupe de B -> 404, rien modifié" + t, c == 404 and instantane(base) == avant, (c, r))
            c, r = await appel(f(GA, req(B, corps=CORPS[nom])))
            verifier("M2. B sur le groupe de A -> 404, rien modifié" + t, c == 404 and instantane(base) == avant, (c, r))
            c, r = await appel(f(GA, req(corps=CORPS[nom])))
            verifier("M3. anonyme -> 403" + t, c == 403 and instantane(base) == avant, (c, r))
            c, r = await appel(f(GA, req(entete=A, corps=CORPS[nom])))
            verifier("M4. X-User-Email du propriétaire SANS jeton -> 403" + t, c == 403 and instantane(base) == avant, (c, r))
            c, r = await appel(f(GA, req(B, entete=A, corps=CORPS[nom])))
            verifier("M5. JWT B + en-tête A sur le groupe de A -> 404" + t, c == 404 and instantane(base) == avant, (c, r))
            c, r = await appel(f(GH, req(A, corps=CORPS[nom])))
            verifier("M6. historique sans coach_id : coach -> 404" + t, c == 404 and instantane(base) == avant, (c, r))
            c, r = await appel(f("inexistant", req(A, corps=CORPS[nom])))
            verifier("M7. groupe inexistant -> 404" + t, c == 404, (c, r))
            c, r = await appel(f(GA, req(A, corps=CORPS[nom])))
            verifier("M8. A sur SON groupe -> 200" + t, c == 200, (c, r))
            c, r = await appel(f(GH, req(ADMIN, corps=CORPS[nom])))
            verifier("M9. super-admin sur l'historique -> 200" + t, c == 200, (c, r))
            _avant10 = instantane(base)
            c, r = await appel(f(GB, req(ADMIN2, corps=CORPS[nom])))
            verifier("M10. SA-1 : ancien 2e super-admin sur le groupe de B -> refus, intact" + t,
                     c in (403, 404) and instantane(base) == _avant10, (c, r))
            c, r = await appel(f(GB, req(ADMIN, corps=CORPS[nom])))
            verifier("M10b. super-admin sur le groupe de B -> 200" + t, c == 200, (c, r))

    base = base_de_depart()
    c, r = await appel(S.update_chat_group(GA, req(A, corps={
        "name": "Nouveau", "coach_id": B, "link_token": "vole", "is_deleted": True, "mode": "x"})))
    g = groupe(base, GA)
    verifier("M11. liste blanche : coach_id / link_token / is_deleted jamais modifiables",
             c == 200 and g["coach_id"] == A and g["link_token"] == "tokA" and g["is_deleted"] is False
             and g["name"] == "Nouveau" and "mode" not in g, (c, g))
    verifier("M12. réponse sans _id et sans fuite d'un autre groupe", c == 200 and r.get("id") == GA, r)


# ─────────────────────────────────────────────────────────────────────────────
# N. Membres
# ─────────────────────────────────────────────────────────────────────────────
async def partie_membres():
    base = base_de_depart()
    c, r = await appel(S.update_chat_group(GA, req(A, corps={
        "member_ids": ["pA1", "pB1", "pA2", "pB2", "uA3", "uB3", "pX", "x$y"]})))
    g = groupe(base, GA)
    verifier("N1. A ajoute des contacts de B / sans propriétaire -> refusés ; les siens ajoutés ; "
             "un membre déjà présent (pB1) n'est pas éjecté",
             c == 200 and g["member_ids"] == ["pA1", "pB1", "pA2", "uA3"], (c, g.get("member_ids")))
    verifier("N2. session liée synchronisée sur la liste FILTRÉE",
             session(base, SA)["participant_ids"] == ["pA1", "pB1", "pA2", "uA3"], session(base, SA))
    c, r = await appel(S.update_chat_group(GA, req(A, corps={"member_ids": ["pA1"]})))
    verifier("N3. retirer un membre reste possible", c == 200 and groupe(base, GA)["member_ids"] == ["pA1"],
             groupe(base, GA))
    c, r = await appel(S.update_chat_group(GA, req(ADMIN, corps={"member_ids": ["pA1", "pB2"]})))
    verifier("N3b. super-admin : ajout global (contact de B dans le groupe de A)",
             c == 200 and groupe(base, GA)["member_ids"] == ["pA1", "pB2"], groupe(base, GA))
    c, r = await appel(S.update_chat_group(GA, req(A, corps={"member_ids": ["pA1"]})))
    c, r = await appel(S.update_chat_group(GA, req(A, corps={"member_ids": "pB1"})))
    verifier("N4. member_ids non-liste -> 400", c == 400 and groupe(base, GA)["member_ids"] == ["pA1"], (c, r))

    base = base_de_depart()
    c, r = await appel(S.create_chat_group(req(A, entete=B, corps={
        "name": "Nouveau A", "members": ["pA1", "pB1", "uB3", "uA3"], "coach_id": B})))
    cree = next((d for d in base["chat_groups"].docs if d.get("name") == "Nouveau A"), {})
    sess = next((d for d in base["chat_sessions"].docs if d.get("group_id") == cree.get("id")), {})
    verifier("N5. création : coach_id = identité SIGNÉE (jamais l'en-tête / le corps)",
             c == 200 and cree.get("coach_id") == A and sess.get("coach_id") == A, (c, cree))
    verifier("N6. création : seuls les contacts du portefeuille A deviennent membres",
             cree.get("member_ids") == ["pA1", "uA3"] and sess.get("participant_ids") == ["pA1", "uA3"], cree)
    n = len(base["chat_groups"].docs)
    c, r = await appel(S.create_chat_group(req(corps={"name": "anon", "members": []})))
    verifier("N7. création anonyme -> 403, rien créé", c == 403 and len(base["chat_groups"].docs) == n, (c, r))
    c, r = await appel(S.create_chat_group(req(entete=A, corps={"name": "hdr", "members": []})))
    verifier("N8. création par X-User-Email seul -> 403", c == 403 and len(base["chat_groups"].docs) == n, (c, r))
    c, r = await appel(S.create_chat_group(req(ADMIN, corps={"name": "Admin", "members": ["pB1", "pX"]})))
    cree = next((d for d in base["chat_groups"].docs if d.get("name") == "Admin"), {})
    verifier("N9. super-admin : membres globaux", c == 200 and cree.get("member_ids") == ["pB1", "pX"], cree)


# ─────────────────────────────────────────────────────────────────────────────
# J. Adhésion
# ─────────────────────────────────────────────────────────────────────────────
async def partie_adhesion():
    for strict in (False, True):
        t = " [drapeau %s]" % ("ON" if strict else "OFF")
        base = base_de_depart(strict)
        c, r = await appel(S.join_chat_group(GA, req(A, corps={"participant_id": "pA2"})))
        verifier("J1. propriétaire ajoute un contact de SON portefeuille -> 200" + t,
                 c == 200 and "pA2" in groupe(base, GA)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GA, req(A, corps={"participant_id": "pB2"})))
        verifier("J2. propriétaire ajoute un contact de B -> refusé" + t,
                 c in (403, 404) and "pB2" not in groupe(base, GA)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GA, req(A, corps={"participant_id": "inconnu-123"})))
        verifier("J2b. propriétaire ajoute un id qui n'est PAS un contact de son portefeuille -> refusé" + t,
                 c in (403, 404) and "inconnu-123" not in groupe(base, GA)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GB, req(ADMIN2, corps={"participant_id": "pA2"})))
        verifier("J2c. SA-1 : ancien 2e super-admin : ajout global -> refusé" + t,
                 c in (403, 404) and "pA2" not in groupe(base, GB)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GB, req(ADMIN, corps={"participant_id": "pA2"})))
        verifier("J2d. super-admin : ajout global -> 200" + t,
                 c == 200 and "pA2" in groupe(base, GB)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GB, req(A, corps={"participant_id": "pA1"})))
        verifier("J3. A inscrit quelqu'un dans le groupe de B sans jeton -> refusé" + t,
                 c in (403, 404) and "pA1" not in groupe(base, GB)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GA, req(corps={"participant_id": "pX"})))
        verifier("J4. anonyme sans jeton d'invitation -> refusé" + t,
                 c in (403, 404) and "pX" not in groupe(base, GA)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GA, req(entete=A, corps={"participant_id": "pX"})))
        verifier("J5. X-User-Email du propriétaire seul -> refusé" + t,
                 c in (403, 404) and "pX" not in groupe(base, GA)["member_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GA, req(corps={"participant_id": "pX", "link_token": "tokA"})))
        verifier("J6. invité muni du jeton -> 200 (usage visiteur légitime)" + t,
                 c == 200 and "pX" in groupe(base, GA)["member_ids"]
                 and "pX" in session(base, SA)["participant_ids"], (c, r))
        c, r = await appel(S.join_chat_group(GA, req(corps={"participant_id": "pA1"})))
        verifier("J7. membre déjà inscrit (re-sélection du groupe) -> 200, rien ne change" + t, c == 200, (c, r))
        c, r = await appel(S.join_chat_group(GA, req(corps={"participant_id": "uB3", "link_token": "tokA"})))
        verifier("J8. jeton d'invitation : aucune fiche `users` d'un autre coach copiée dans le portefeuille" + t,
                 not any(p.get("id") == "uB3" and p.get("coach_id") == A for p in base["chat_participants"].docs),
                 base["chat_participants"].docs[-1])

    base = base_de_depart()
    S_join = S.join_group_automatically
    c, r = await appel(S_join(S.GroupJoinRequest(group_id="tokA", email="x@exemple.test", user_id="pX")))
    verifier("J9. /groups/join par lien d'invitation (?group=<jeton>) -> 200",
             c == 200 and r.get("conversation_id") == SA and "pX" in session(base, SA)["participant_ids"], (c, r))
    avant = instantane(base)
    for gid, nom in ((SB, "id brut d'un groupe"), ("sess-priv", "session privée"), (".*", "regex"),
                     ("Groupe", "titre partiel"), ("privtok", "jeton d'une session privée")):
        c, r = await appel(S_join(S.GroupJoinRequest(group_id=gid, email="x@exemple.test", user_id="pX")))
        verifier("J10. /groups/join par %s -> 404, rien modifié" % nom,
                 c == 404 and instantane(base) == avant, (c, r))


# ─────────────────────────────────────────────────────────────────────────────
# P. Vue membre
# ─────────────────────────────────────────────────────────────────────────────
async def partie_publique():
    base_de_depart(strict=True)
    c, r = await appel(S.get_public_groups(req(params={"participant_id": "pA1"})))
    verifier("P1. membre légitime (drapeau ON) -> voit SON groupe", c == 200 and [g["id"] for g in r] == [GA], (c, r))
    verifier("P2. ... sans member_ids / link_token / system_prompt, avec session_id et compteur",
             c == 200 and all("member_ids" not in g and "link_token" not in g and "system_prompt" not in g
                              and g.get("session_id") == SA and g.get("member_count") == 2 for g in r), r)
    c, r = await appel(S.get_public_groups(req()))
    verifier("P3. anonyme (drapeau ON) -> 403", c == 403, (c, r))
    base_de_depart(strict=False)
    c, r = await appel(S.get_public_groups(req()))
    verifier("P4. drapeau OFF : anonyme -> 403 (aucune dépendance au drapeau)", c == 403, (c, r))
    for qui, nom in ((None, "X-User-Email A seul"),):
        c, r = await appel(S.get_public_groups(req(entete=A)))
        verifier("P5. drapeau OFF : %s -> 403" % nom, c == 403, (c, r))
    c, r = await appel(S.get_public_groups(req(A)))
    verifier("P6. drapeau OFF : coach A signé -> ses groupes seulement, sans PII",
             c == 200 and [g["id"] for g in r] == [GA]
             and all("member_ids" not in g and "link_token" not in g and "system_prompt" not in g for g in r), (c, r))
    c, r = await appel(S.get_public_groups(req(B, entete=A)))
    verifier("P7. drapeau OFF : JWT B + en-tête A -> reste B", c == 200 and [g["id"] for g in r] == [GB], (c, r))
    c, r = await appel(S.get_public_groups(req(params={"participant_id": "pA1"})))
    verifier("P8. drapeau OFF : membre légitime -> son groupe", c == 200 and [g["id"] for g in r] == [GA], (c, r))


# ─────────────────────────────────────────────────────────────────────────────
# X. Routes voisines
# ─────────────────────────────────────────────────────────────────────────────
async def partie_voisines():
    base = base_de_depart()
    avant = instantane(base)
    # V585 : la route exige désormais un JWT. Sans identité -> refus ; même le SUPER-ADMIN
    #   signé n'atteint jamais un groupe par cette route (404), le groupe reste intact.
    c, r = await appel(S.delete_chat_link(SB, req()))
    verifier("X1. DELETE /chat/links/<groupe> sans jeton -> refusé, groupe intact", c in (401, 403) and instantane(base) == avant, (c, r))
    c, r = await appel(S.delete_chat_link(SB, req(jeton_de=ADMIN)))
    verifier("X1b. DELETE /chat/links/<groupe> super-admin -> 404, groupe intact", c == 404 and instantane(base) == avant, (c, r))
    c, r = await appel(S.update_chat_link(SA, req(corps={"custom_prompt": "piraté", "title": "x"})))
    verifier("X2. PUT /chat/links/<groupe> sans jeton -> refusé, prompt intact", c in (401, 403) and instantane(base) == avant, (c, r))
    c, r = await appel(S.update_chat_link(SA, req(jeton_de=ADMIN, corps={"custom_prompt": "piraté", "title": "x"})))
    verifier("X2b. PUT /chat/links/<groupe> super-admin -> 404, prompt intact", c == 404 and instantane(base) == avant, (c, r))
    c, r = await appel(S.get_chat_link_by_token(SA))
    verifier("X3. GET /chat/links/<id de groupe> -> 404 (jeton d'invitation non exposé)", c == 404, (c, r))
    c, r = await appel(S.get_chat_link_by_token("tokA"))
    verifier("X4. GET /chat/links/<jeton de groupe> -> 404", c == 404, (c, r))

    n = len(base["chat_messages"].docs)
    for qui, nom in ((None, "anonyme"), (A, "coach A signé")):
        c, r = await appel(S.send_group_message(req(qui, corps={"message": "à tous"})))
        verifier("X5. /chat/group-message (diffusion à TOUS les contacts) par %s -> 403" % nom,
                 c == 403 and len(base["chat_messages"].docs) == n, (c, r))
    c, r = await appel(S.send_group_message(req(entete=ADMIN, corps={"message": "à tous"})))
    verifier("X6. /chat/group-message par X-User-Email super-admin seul -> 403", c == 403, (c, r))

    for f, nom in ((S.create_sunset_group, "sunset"), (S.create_whatsapp_group, "whatsapp")):
        n = len(base["chat_groups"].docs)
        c, r = await appel(f(req()))
        verifier("X7. /create-%s-group anonyme -> 403, rien créé" % nom,
                 c == 403 and len(base["chat_groups"].docs) == n, (c, r))
        c, r = await appel(f(req(A)))
        verifier("X8. /create-%s-group par un coach -> 403" % nom,
                 c == 403 and len(base["chat_groups"].docs) == n, (c, r))


# ─────────────────────────────────────────────────────────────────────────────
# C. Campagnes -> groupes
# ─────────────────────────────────────────────────────────────────────────────
async def resoudre(**champs):
    doc = {"id": "tmp", "name": "tmp", "targetType": "selected", "targetIds": [],
           "selectedContacts": [], "channels": {"email": True}}
    doc.update(champs)
    ids = [t for t in (doc.get("targetIds") or []) if t and str(t).strip()]
    return await S._campagne_resoudre_contacts(doc, ids)


def emails(contacts):
    return sorted({(c.get("email") or "").lower() for c in contacts if c.get("email")})


async def partie_campagnes():
    base_de_depart()
    r = await resoudre(coach_id=A, targetIds=[SB])
    verifier("C1. campagne de A -> groupe de B : aucun destinataire", r == [], emails(r))
    r = await resoudre(coach_id=A, targetIds=[SA])
    verifier("C2. campagne de A -> groupe de A : seulement les membres du portefeuille A",
             emails(r) == ["a1@exemple.test"], emails(r))
    r = await resoudre(coach_id=A, targetIds=[SH])
    verifier("C3. campagne de A -> groupe historique sans coach_id : refusé (fail-closed)", r == [], emails(r))
    r = await resoudre(coach_id=A, targetIds=["grp_piege000"])
    verifier("C4. session de A pointant vers le groupe de B : jamais dépliée sur les membres de B",
             r == [], emails(r))
    _lus = []
    _orig = S.db.chat_groups.find_one

    async def _espion(q=None, proj=None, **k):
        _lus.append(dict(q or {}))
        return await _orig(q, proj, **k)
    S.db.chat_groups.find_one = _espion
    await resoudre(coach_id=A, targetIds=["grp_piege000"])
    S.db.chat_groups.find_one = _orig
    verifier("C4b. ... le repli `chat_groups` est lui-même borné au propriétaire (défense en profondeur)",
             _lus and all(q.get("coach_id") == A for q in _lus), _lus)
    r = await resoudre(coach_id=A, targetIds=[GB])
    verifier("C5. id brut chat_groups de B -> rien", r == [], emails(r))
    r = await resoudre(coach_id=A, selectedContacts=[SB])
    verifier("C6. groupe de B via selectedContacts -> rien", r == [], emails(r))
    r = await resoudre(coach_id=ADMIN, targetIds=[SB, SH])
    verifier("C7. super-admin : groupes de B et historique dépliés (inchangé)",
             emails(r) == ["b1@exemple.test", "x@exemple.test"], emails(r))
    r = await resoudre(targetIds=[SB])
    verifier("C8. campagne historique sans propriétaire : inchangé (global)", emails(r) == ["b1@exemple.test"], emails(r))


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_liste, partie_mutations, partie_membres, partie_adhesion, partie_publique,
                   partie_voisines, partie_campagnes):
        try:
            boucle.run_until_complete(partie())
        except Exception as e:
            import traceback
            traceback.print_exc()
            verifier("%s s'exécute sans exception" % partie.__name__, False, repr(e))
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("=" * 78)
    print("MT-7 — GROUPES DU CHAT MULTI-COACH : %d vérifications" % len(RESULTATS))
    print("=" * 78)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:400])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

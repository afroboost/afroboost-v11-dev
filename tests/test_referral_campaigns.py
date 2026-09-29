#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INV-1 — « Invitation » de la page Campagnes du coach : le banc.

Une invitation est un LIEN partageable (carte OG), jamais une campagne d'envoi :
collection `referral_campaigns`, jamais `campaigns`. Ce banc exécute les VRAIES
routes (`referral_campaigns_routes.py`), le VRAI moteur pur
(`referral_campaigns_engine.py`) et la VRAIE création de Pass Duo, sur le
MongoDB en mémoire de `test_referral_pass_duo.py` (importé, jamais recopié).
AUCUN réseau, AUCUN e-mail, AUCUNE donnée réelle.

Lancement :  python3 tests/test_referral_campaigns.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_v3 as V3  # noqa: E402  (pose l'environnement du banc)

H = V3.H
E, R = H.E, H.R
verifier, appel, Requete = H.verifier, H.appel, H.Requete

import api.routes.referral_campaigns_engine as IC  # noqa: E402
import api.routes.referral_campaigns_routes as RC  # noqa: E402

COACH_A = "coach.a.inv@exemple.test"
COACH_B = "coach.b.inv@exemple.test"
NON_COACH = "simple.visiteur@exemple.test"
PHOTO_A = "https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/coach-a.jpg"
COURS_A, COURS_A_SANS_DUO, COURS_B = "cours-inv-a", "cours-inv-a-sans-duo", "cours-inv-b"
OFFRE_A_ESSAI, OFFRE_A_PAYANTE, OFFRE_A_PROG = "offre-inv-a-essai", "offre-inv-a-25", "offre-inv-a-prog"
OFFRE_B_ESSAI = "offre-inv-b-essai"
INTERDITS = ("scheduled", "sending", "recipients", "channel", "send_at", "scheduledAt", "targetType")


def jeton(email):
    return {"Authorization": "Bearer " + H.jeton_admin(email)}


def rq(email=None, corps=None, params=None, entetes=None):
    _e = dict(jeton(email)) if email else {}
    _e.update(entetes or {})
    return Requete(corps if corps is not None else {}, _e, params or {})


def depart():
    base, occ = H.base_de_depart()
    base._c["referral_campaigns"] = H._Coll("referral_campaigns", uniques=[(("id",), None),
                                                                          (("share_token",), None)])
    RC.init_db(base)
    base["coaches"].docs += [{"id": "ca", "email": COACH_A, "name": "Mariam Coach"},
                             {"id": "cb", "email": COACH_B, "name": "Brice Coach"}]
    base["coach_profiles"].docs.append({"email": COACH_A, "display_name": "Mariam Diallo", "photo_url": PHOTO_A})
    _wd = [c for c in base["courses"].docs if c["id"] == H.COURS_DUO][0]["weekday"]
    base["courses"].docs += [
        {"id": COURS_A, "name": "Afro A", "weekday": _wd, "time": "18:30", "locationName": "Salle A",
         "visible": True, "archived": False, "duo_enabled": True, "coach_id": COACH_A},
        {"id": COURS_A_SANS_DUO, "name": "Afro A2", "weekday": _wd, "time": "18:30", "locationName": "Salle A2",
         "visible": True, "archived": False, "coach_id": COACH_A},
        {"id": COURS_B, "name": "Afro B", "weekday": _wd, "time": "19:00", "locationName": "Salle B",
         "visible": True, "archived": False, "duo_enabled": True, "coach_id": COACH_B},
    ]
    base["offers"].docs += [
        {"id": OFFRE_A_ESSAI, "name": "Essai A", "price": 0.0, "visible": True, "coach_id": COACH_A},
        {"id": OFFRE_A_PAYANTE, "name": "Soirée A", "price": 25.0, "visible": True, "coach_id": COACH_A,
         "location": "Salle Événement"},
        {"id": OFFRE_A_PROG, "name": "Festival A", "price": 0.0, "visible": True, "coach_id": COACH_A,
         "progressive_pricing": True, "price_early_bird": 10.0, "price_standard": 15.0, "price_last_minute": 20.0},
        {"id": OFFRE_B_ESSAI, "name": "Essai B", "price": 0.0, "visible": True, "coach_id": COACH_B},
    ]
    return base, occ


async def creer(email, corps):
    return await appel(RC.invitations_creer(rq(email, corps)))


async def modifier(email, inv_id, corps):
    return await appel(RC.invitations_modifier(inv_id, rq(email, corps)))


def doc(base, inv_id):
    for d in base["referral_campaigns"].docs:
        if d.get("id") == inv_id:
            return d
    return None


def fuite(objet, base):
    _t = V3.fuite(objet, base, extra=(COACH_A, COACH_B, "coach_id", H.ADMIN))
    for d in base["referral_campaigns"].docs:
        if d.get("id") and d["id"] in json.dumps(objet, default=str):
            _t.append("id_invitation:" + d["id"][:8])
    return _t


# ═══════════════════════════════════════════════════════════════════════════
async def partie_moteur_pur():
    verifier("INV-M1 TYPES / STATUTS du contrat", IC.TYPES == ("trial", "pass_duo", "event_free", "event_paid")
             and IC.STATUTS == ("draft", "active", "archived"))
    verifier("INV-M2 CHAMPS_VISUELS exacts", set(IC.CHAMPS_VISUELS) == {
        "title", "subtitle", "message", "cta_label", "image_url", "image_source", "course_id",
        "occurrence", "offer_id", "type"})
    d = {"type": "trial", "offer_id": "o 1/é", "share_token": "t"}
    verifier("INV-M3 cible trial", IC.cible_front(d) == "/?offre=o%201%2F%C3%A9&reserver=1", IC.cible_front(d))
    verifier("INV-M3b cible event_free", IC.cible_front(dict(d, type="event_free")).endswith("&reserver=1"))
    verifier("INV-M3c cible event_paid SANS reserver",
             IC.cible_front(dict(d, type="event_paid")) == "/?offre=o%201%2F%C3%A9")
    verifier("INV-M3d cible pass_duo", IC.cible_front({"type": "pass_duo", "share_token": "ab-C_"})
             == "/parrainage?campagne=ab-C_")
    e = IC.valider_entree({"type": "trial", "title": "<b>Viens</b>  danser", "coach_id": "x@y",
                           "scheduled": True, "recipients": ["a"], "channel": "email", "send_at": "x"})
    verifier("INV-M4 liste blanche + HTML retiré", e["title"] == "Viens danser" and not any(
        k in e for k in INTERDITS + ("coach_id",)), e)
    for mauvais in ({"type": "spam"}, {"type": "trial", "status": "scheduled"},
                    {"type": "trial", "status": "archived"}, {"type": "trial", "title": "x" * 81},
                    {"type": "trial", "subtitle": "x" * 121}, {"type": "trial", "message": "x" * 281},
                    {"type": "trial", "cta_label": "x" * 31}, {"type": "trial", "occurrence": "2026-10-01"},
                    {"type": "trial", "image_url": "http://res.cloudinary.com/x.jpg"},
                    {"type": "trial", "image_url": "https://evil.example/x.jpg"},
                    {"type": "trial", "image_source": "upload"}):
        try:
            IC.valider_entree(mauvais)
            ok = False
        except IC.InvitationCampagneInvalide:
            ok = True
        verifier("INV-M5 refusé : %s" % str(mauvais)[:60], ok)
    e = IC.valider_entree({"type": "trial", "image_url": "/api/files/abc/x.jpg"})
    verifier("INV-M6 /api/files admis -> upload", e["image_source"] == "upload" and e["image_url"] == "/api/files/abc/x.jpg")
    e = IC.valider_entree({"type": "trial", "image_source": "default", "image_url": PHOTO_A})
    verifier("INV-M6b default => image_url None", e["image_url"] is None and e["image_source"] == "default")
    e = IC.valider_entree({"type": "pass_duo", "occurrence": "2026-10-01T16:30:00Z"})
    verifier("INV-M7 occurrence convertie à Zurich", e["occurrence"] == "2026-10-01T18:30:00", e["occurrence"])
    verifier("INV-M8 libellés FR", IC.date_label("2026-10-01T18:30:00") == "jeudi 1 octobre"
             and IC.time_label("2026-10-01T18:30:00") == "18:30", IC.date_label("2026-10-01T18:30:00"))
    a = {"type": "trial", "title": "A", "subtitle": None}
    verifier("INV-M9 version : identique -> non ; \"\" == None", not IC.version_incrementee(a, dict(a, subtitle="")))
    verifier("INV-M9b version : titre changé -> oui", IC.version_incrementee(a, dict(a, title="B")))
    verifier("INV-M9c status seul -> non", not IC.version_incrementee(dict(a, status="draft"), dict(a, status="active")))
    verifier("INV-M10 prix progressif (price=0 sentinelle) n'est PAS gratuit",
             not IC.offre_gratuite({"price": 0, "progressive_pricing": True, "price_standard": 15})
             and IC.offre_payante({"price": 0, "progressive_pricing": True, "price_standard": 15}))
    verifier("INV-M10b 0 CHF simple gratuit", IC.offre_gratuite({"price": 0.0}) and not IC.offre_payante({"price": 0}))
    verifier("INV-M10c active_price prime", not IC.offre_gratuite({"price": 0, "active_price": 12}))
    i = IC.identite_coach({"email": "mariam@x.test", "name": "mariam", "photo_url": "javascript:x"})
    verifier("INV-M11 identite_coach : partie locale refusée, photo invalide -> None",
             i == {"prenom": "", "photo_url": None, "source": "coach"}, i)
    i = IC.identite_coach({"email": COACH_A, "display_name": "Mariam Diallo", "photo_url": PHOTO_A})
    verifier("INV-M11b identite_coach", i == {"prenom": "Mariam", "photo_url": PHOTO_A, "source": "coach"}, i)
    dp = IC.dto_public({"type": "event_paid", "offer_id": "o", "share_token": "t", "coach_id": COACH_A,
                        "id": "interne-1", "version": 3, "occurrence": "2026-10-01T18:30:00",
                        "inviter_display": {"prenom": "Mariam", "photo_url": PHOTO_A, "source": "coach",
                                            "email": COACH_A}},
                       {"locationName": "Salle A", "coach_id": COACH_A},
                       {"progressive_pricing": True, "price_early_bird": 10, "price_standard": 15,
                        "price_last_minute": 20, "coach_id": COACH_A})
    _s = json.dumps(dp)
    verifier("INV-M12 dto_public sans PII ni id interne", COACH_A not in _s and "interne-1" not in _s
             and "coach_id" not in _s and not E.contient_pii(dp), dp)
    verifier("INV-M12b dto_public : paliers event_paid", dp["prix"] == {"early_bird": 10.0, "standard": 15.0,
                                                                         "last_minute": 20.0}, dp["prix"])
    verifier("INV-M12c dto_public : clés exactes", set(dp) == {
        "type", "title", "subtitle", "message", "cta_label", "image_url", "version", "share_token",
        "occurrence", "date_label", "time_label", "lieu", "inviter_display", "target_url", "prix"}, sorted(dp))
    dc = IC.dto_coach({"type": "trial", "share_token": "tok", "version": 2, "id": "i1"}, base_url="https://x.test/")
    verifier("INV-M13 dto_coach : share_url / card_url versionnées",
             dc["share_url"] == "https://x.test/api/share/invite/tok?v=2"
             and dc["card_url"] == "https://x.test/api/share/invite/tok/carte.jpg?v=2" and "coach_id" not in dc, dc)


async def partie_auth():
    base, occ = depart()
    for nom, coro in (("liste", RC.invitations_lister), ("options", RC.invitations_options),
                      ("création", RC.invitations_creer)):
        c, _ = await appel(coro(rq(None, {"type": "trial"})))
        verifier("INV-A1 %s sans jeton -> 401" % nom, c == 401, c)
        c, _ = await appel(coro(rq(None, {"type": "trial"}, entetes={"X-User-Email": COACH_A})))
        verifier("INV-A2 %s avec X-User-Email seul -> 401 (jamais lu)" % nom, c == 401, c)
        c, _ = await appel(coro(rq(NON_COACH, {"type": "trial"})))
        verifier("INV-A3 %s jeton non coach -> 403" % nom, c == 403, c)
    c, _ = await appel(RC.invitations_lire("x", rq(None)))
    verifier("INV-A4 lecture sans jeton -> 401", c == 401, c)
    c, _ = await appel(RC.invitations_modifier("x", rq(NON_COACH, {"title": "x"})))
    verifier("INV-A4b modification jeton non coach -> 403", c == 403, c)
    c, _ = await appel(RC.invitations_archiver("x", rq(None)))
    verifier("INV-A4c archivage sans jeton -> 401", c == 401, c)
    verifier("INV-A5 rien n'a été écrit", not base["referral_campaigns"].docs)


async def partie_types():
    base, occ = depart()
    # D — trial : draft incomplet, puis active
    c, d = await creer(COACH_A, {"type": "trial", "title": "Premier cours offert"})
    verifier("INV-D1 trial draft incomplet -> 201", c == 201 and d.get("status") == "draft" and d.get("version") == 1, (c, d))
    c, r = await modifier(COACH_A, d["id"], {"status": "active"})
    verifier("INV-D2 trial active sans cours/occurrence/offre -> 422", c == 422, (c, r))
    c, r = await modifier(COACH_A, d["id"], {"status": "active", "course_id": COURS_A, "occurrence": occ,
                                             "offer_id": OFFRE_A_PAYANTE})
    verifier("INV-D3 trial avec offre payante -> 422", c == 422, (c, r))
    c, r = await modifier(COACH_A, d["id"], {"status": "active", "course_id": COURS_A, "occurrence": occ,
                                             "offer_id": OFFRE_A_PROG})
    verifier("INV-D3b trial avec prix progressif (price=0 sentinelle) -> 422", c == 422, (c, r))
    c, r = await modifier(COACH_A, d["id"], {"status": "active", "course_id": COURS_A, "occurrence": occ,
                                             "offer_id": OFFRE_A_ESSAI})
    verifier("INV-D4 trial active -> 200", c == 200 and r.get("status") == "active"
             and r.get("target_url") == "/?offre=%s&reserver=1" % OFFRE_A_ESSAI
             and r.get("lieu") == "Salle A" and r.get("time_label") == "18:30" and r.get("date_label"), (c, r))
    verifier("INV-D5 inviter_display figé (coach)", doc(base, d["id"])["inviter_display"] ==
             {"prenom": "Mariam", "photo_url": PHOTO_A, "source": "coach"}, doc(base, d["id"]).get("inviter_display"))
    c, r = await creer(COACH_A, {"type": "trial", "status": "active", "course_id": COURS_A, "occurrence": occ,
                                 "offer_id": OFFRE_A_ESSAI})
    verifier("INV-D6 trial créé directement actif -> 201", c == 201 and r.get("status") == "active", (c, r))
    c, r = await creer(COACH_A, {"type": "trial", "status": "active", "course_id": COURS_A,
                                 "occurrence": "2020-01-01T18:30:00", "offer_id": OFFRE_A_ESSAI})
    verifier("INV-D7 trial sur séance passée -> 422", c == 422, (c, r))

    # E — pass_duo
    c, r = await creer(COACH_A, {"type": "pass_duo", "status": "active", "course_id": COURS_A})
    verifier("INV-E1 pass_duo sans occurrence -> 422", c == 422, (c, r))
    c, r = await creer(COACH_A, {"type": "pass_duo", "status": "active", "course_id": COURS_A_SANS_DUO,
                                 "occurrence": occ})
    verifier("INV-E2 pass_duo sur cours sans Pass Duo -> 422", c == 422, (c, r))
    c, r = await creer(COACH_A, {"type": "pass_duo", "status": "active", "course_id": COURS_A, "occurrence": occ,
                                 "message": "Viens avec moi"})
    verifier("INV-E3 pass_duo actif -> 201 + cible /parrainage?campagne=<jeton>",
             c == 201 and r.get("target_url") == "/parrainage?campagne=" + r.get("share_token"), (c, r))

    # F — event_free
    c, r = await creer(COACH_A, {"type": "event_free", "status": "active", "offer_id": OFFRE_A_PAYANTE})
    verifier("INV-F1 event_free sur offre payante -> 422", c == 422, (c, r))
    c, r = await creer(COACH_A, {"type": "event_free", "status": "active", "offer_id": OFFRE_A_ESSAI})
    verifier("INV-F2 event_free actif sans cours ni occurrence -> 201", c == 201 and r.get("occurrence") is None
             and r.get("target_url").endswith("&reserver=1") and r.get("prix") is None, (c, r))

    # G — event_paid : draft OK, activation 409 (drapeau absent), puis drapeau false explicite
    c, g = await creer(COACH_A, {"type": "event_paid", "offer_id": OFFRE_A_PROG, "title": "Festival"})
    verifier("INV-G1 event_paid draft -> 201", c == 201 and g.get("status") == "draft"
             and g.get("target_url") == "/?offre=" + OFFRE_A_PROG
             and g.get("prix") == {"early_bird": 10.0, "standard": 15.0, "last_minute": 20.0}, (c, g))
    c, r = await modifier(COACH_A, g["id"], {"status": "active"})
    verifier("INV-G2 event_paid activation -> 409 (drapeau absent)", c == 409
             and r.get("detail") == IC.MESSAGE_EVENT_PAYANT_BLOQUE, (c, r))
    c, r = await creer(COACH_A, {"type": "event_paid", "status": "active", "offer_id": OFFRE_A_PAYANTE})
    verifier("INV-G3 event_paid créé actif -> 409, rien écrit", c == 409 and len(
        [x for x in base["referral_campaigns"].docs if x.get("type") == "event_paid"]) == 1, (c, r))
    base["feature_flags"].docs[0]["invitation_event_paid_enabled"] = "true"
    c, r = await modifier(COACH_A, g["id"], {"status": "active"})
    verifier("INV-G4 drapeau non booléen (\"true\") -> toujours 409", c == 409, (c, r))
    verifier("INV-G5 event_paid toujours draft en base", doc(base, g["id"])["status"] == "draft")
    base["feature_flags"].docs[0]["invitation_event_paid_enabled"] = True
    c, r = await modifier(COACH_A, g["id"], {"status": "active"})
    verifier("INV-G6 drapeau true -> activation possible", c == 200 and r.get("status") == "active", (c, r))
    base["feature_flags"].docs[0].pop("invitation_event_paid_enabled", None)

    # Jamais dans `campaigns`
    verifier("INV-G7 aucune écriture dans `campaigns`", not base["campaigns"].docs)


async def partie_proprietaire():
    base, occ = depart()
    c, a = await creer(COACH_A, {"type": "event_free", "offer_id": OFFRE_A_ESSAI, "title": "A"})
    c2, b = await creer(COACH_B, {"type": "event_free", "offer_id": OFFRE_B_ESSAI, "title": "B"})
    verifier("INV-H0 deux invitations créées", c == 201 and c2 == 201, (c, c2))
    verifier("INV-H0b coach_id = clé serveur", doc(base, a["id"])["coach_id"] == COACH_A
             and doc(base, b["id"])["coach_id"] == COACH_B)
    c, l = await appel(RC.invitations_lister(rq(COACH_A)))
    verifier("INV-H1 A ne liste que les siennes", c == 200 and [i["id"] for i in l["items"]] == [a["id"]]
             and l["total"] == 1, l)
    c, _ = await appel(RC.invitations_lire(b["id"], rq(COACH_A)))
    verifier("INV-H2 A lit celle de B -> 404", c == 404, c)
    c, _ = await modifier(COACH_A, b["id"], {"title": "piraté"})
    verifier("INV-H3 A modifie celle de B -> 404, intacte", c == 404 and doc(base, b["id"])["title"] == "B", c)
    c, _ = await appel(RC.invitations_archiver(b["id"], rq(COACH_A)))
    verifier("INV-H4 A archive celle de B -> 404, intacte", c == 404 and doc(base, b["id"])["status"] == "draft", c)
    c, r = await creer(COACH_A, {"type": "event_free", "offer_id": OFFRE_B_ESSAI})
    verifier("INV-H5 offre de B dans une invitation de A -> 422", c == 422, (c, r))
    c, r = await creer(COACH_A, {"type": "pass_duo", "course_id": COURS_B})
    verifier("INV-H6 cours de B -> 422 (même en draft)", c == 422, (c, r))
    c, r = await creer(COACH_A, {"type": "event_free", "offer_id": OFFRE_A_ESSAI, "coach_id": COACH_B})
    verifier("INV-H7 coach_id du corps ignoré", c == 201 and doc(base, r["id"])["coach_id"] == COACH_A, (c, r))
    c, o = await appel(RC.invitations_options(rq(COACH_A)))
    _cids = {x["id"] for x in o.get("courses", [])}
    _oids = {x["id"] for x in o.get("offers", [])}
    verifier("INV-H8 options : uniquement les objets de A", c == 200 and _cids == {COURS_A, COURS_A_SANS_DUO}
             and _oids == {OFFRE_A_ESSAI, OFFRE_A_PAYANTE, OFFRE_A_PROG}, (c, _cids, _oids))
    _prog = [x for x in o["offers"] if x["id"] == OFFRE_A_PROG][0]
    verifier("INV-H8b options : prix progressif exposé, pas gratuit", _prog["has_progressive_pricing"] is True
             and _prog["is_free"] is False and _prog["price_standard"] == 15.0, _prog)
    verifier("INV-H8c options : occurrences et aucune PII", all(x.get("occurrences") for x in o["courses"])
             and COACH_A not in json.dumps(o) and not E.contient_pii(o), o)
    c, _ = await appel(RC.invitations_archiver(a["id"], rq(COACH_A)))
    c2, l = await appel(RC.invitations_lister(rq(COACH_A)))
    c3, l2 = await appel(RC.invitations_lister(rq(COACH_A, params={"include_archived": "1"})))
    verifier("INV-H9 archivée exclue de la liste, sauf include_archived", c == 200 and a["id"] not in
             [i["id"] for i in l["items"]] and a["id"] in [i["id"] for i in l2["items"]], (l, l2))
    c, r = await modifier(COACH_A, a["id"], {"title": "après archive"})
    verifier("INV-H10 archivée non modifiable -> 409", c == 409, (c, r))
    c, l = await appel(RC.invitations_lister(rq(COACH_A, params={"limit": "500"})))
    verifier("INV-H11 limit borné à 50", c == 200 and len(l["items"]) <= 50)


async def partie_jeton_version_pii():
    base, occ = depart()
    c, d = await creer(COACH_A, {"type": "trial", "title": "Titre", "course_id": COURS_A, "occurrence": occ,
                                 "offer_id": OFFRE_A_ESSAI, "share_token": "force", "version": 99,
                                 "id": "force-id", "inviter_display": {"prenom": "X"},
                                 "scheduled": True, "sending": True, "recipients": ["a@b.c"], "channel": "whatsapp",
                                 "send_at": "2026-10-01", "scheduledAt": "x", "targetType": "all"})
    stocke = doc(base, d["id"])
    verifier("INV-L1 champs interdits JAMAIS stockés", c == 201 and not any(k in stocke for k in INTERDITS)
             and set(stocke) <= set(IC.CHAMPS_DOCUMENT), sorted(stocke))
    verifier("INV-L1b share_token / version / id / inviter_display décidés par le serveur",
             stocke["share_token"] != "force" and stocke["version"] == 1 and stocke["id"] != "force-id"
             and stocke["inviter_display"]["source"] == "coach", stocke)
    tok = stocke["share_token"]
    c, d2 = await creer(COACH_A, {"type": "trial"})
    verifier("INV-I1 share_token unique", c == 201 and doc(base, d2["id"])["share_token"] != tok)

    # Collision forcée : le premier jeton tiré existe déjà -> nouvel essai.
    _orig = RC.secrets.token_urlsafe
    _seq = iter([tok, "jeton-neuf-inv-1"])
    RC.secrets.token_urlsafe = lambda n=24: next(_seq, _orig(n))
    try:
        c, d3 = await creer(COACH_A, {"type": "trial"})
    finally:
        RC.secrets.token_urlsafe = _orig
    verifier("INV-I2 collision de jeton -> nouvel essai", c == 201 and doc(base, d3["id"])["share_token"]
             == "jeton-neuf-inv-1", (c, d3))

    c, r = await modifier(COACH_A, d["id"], {"title": "Titre", "course_id": COURS_A, "offer_id": OFFRE_A_ESSAI,
                                             "occurrence": occ, "share_token": "autre"})
    verifier("INV-K1 PUT identique -> version inchangée, jeton inchangé", c == 200 and r["version"] == 1
             and doc(base, d["id"])["share_token"] == tok, (c, r))
    c, r = await modifier(COACH_A, d["id"], {"status": "active"})
    verifier("INV-K2 statut seul -> version inchangée", c == 200 and r["version"] == 1 and r["status"] == "active", (c, r))
    c, r = await modifier(COACH_A, d["id"], {"title": "Nouveau titre"})
    verifier("INV-K3 changement visuel -> version 2, même jeton", c == 200 and r["version"] == 2
             and r["share_token"] == tok and r["share_url"].endswith("/api/share/invite/%s?v=2" % tok), (c, r))
    c, r = await modifier(COACH_A, d["id"], {"image_url": PHOTO_A})
    verifier("INV-K4 image -> version 3, source upload", c == 200 and r["version"] == 3
             and r["image_source"] == "upload", (c, r))
    c, r = await modifier(COACH_A, d["id"], {"image_url": "http://res.cloudinary.com/x.jpg"})
    verifier("INV-K5 image http:// -> 422, rien changé", c == 422 and doc(base, d["id"])["version"] == 3, (c, r))
    c, r = await modifier(COACH_A, d["id"], {"image_url": "https://evil.example/x.jpg"})
    verifier("INV-K5b hôte inconnu -> 422", c == 422, (c, r))
    c, r = await creer(COACH_A, {"type": "trial", "image_url": "https://evil.example/x.jpg"})
    verifier("INV-K5c création avec hôte inconnu -> 422", c == 422, (c, r))
    c, r = await modifier(COACH_A, d["id"], {"image_source": "default"})
    verifier("INV-K6 retour à l'image par défaut -> url None, version 4", c == 200 and r["image_url"] is None
             and r["version"] == 4, (c, r))
    verifier("INV-K7 jeton toujours inchangé", doc(base, d["id"])["share_token"] == tok)

    pub = IC.dto_public(doc(base, d["id"]), {"locationName": "Salle A", "coach_id": COACH_A},
                        {"coach_id": COACH_A, "price": 0})
    verifier("INV-L2 dto_public sans PII", not fuite(pub, base), fuite(pub, base))
    c, r = await appel(RC.invitations_lire(d["id"], rq(COACH_A)))
    _sans_id = dict(r)
    _sans_id.pop("id", None)
    verifier("INV-L3 dto_coach sans PII (hors son propre id)", c == 200 and not fuite(_sans_id, base)
             and "coach_id" not in r, fuite(_sans_id, base))


async def partie_pass_duo():
    base, occ = depart()
    # Une invitation pass_duo ACTIVE de l'espace plateforme (super-admin) sur le cours Duo du banc.
    c, inv = await creer(H.ADMIN, {"type": "pass_duo", "status": "active", "course_id": H.COURS_DUO,
                                   "occurrence": occ, "message": "Viens danser avec moi ce jeudi"})
    verifier("INV-P0 invitation pass_duo plateforme active", c == 201 and doc(base, inv["id"])["coach_id"] == "", (c, inv))

    c, p = await H.creer_pass(base, occ, referral_campaign=inv["share_token"])
    pd = V3.doc_par_tok(base, p.get("share_token"))
    verifier("INV-P1 pass créé avec referral_campaign -> referral_campaign_id stocké",
             c == 201 and pd.get("referral_campaign_id") == inv["id"], (c, pd and pd.get("referral_campaign_id")))
    verifier("INV-P1b message prérempli depuis l'invitation",
             (pd.get("invitation") or {}).get("message") == "Viens danser avec moi ce jeudi", pd.get("invitation"))
    verifier("INV-P1c l'id de l'invitation ne sort pas dans le DTO public", inv["id"] not in json.dumps(
        (await H.appel(R.referral_pass_public(p["share_token"])))[1], default=str))

    # Sans : pass identique à avant (aucune clé nouvelle)
    base2, occ2 = depart()
    c, p2 = await H.creer_pass(base2, occ2)
    pd2 = V3.doc_par_tok(base2, p2.get("share_token"))
    verifier("INV-P2 sans referral_campaign -> ni referral_campaign_id ni invitation",
             c == 201 and "referral_campaign_id" not in pd2 and "invitation" not in pd2, sorted(pd2 or {}))

    # Jeton inconnu / invitation draft / autre type / valeur non texte : ignorés, 201
    base3, occ3 = depart()
    c, brouillon = await creer(H.ADMIN, {"type": "pass_duo", "course_id": H.COURS_DUO, "occurrence": occ3})
    c, essai = await creer(H.ADMIN, {"type": "event_free", "status": "active", "offer_id": H.OFFRE_A})
    for n, (nom, val) in enumerate((("inconnu", "jeton-inconnu"), ("draft", brouillon["share_token"]),
                                    ("autre type", essai["share_token"]), ("objet", {"$ne": None}))):
        tok = H.jeton_espace(base3)
        base3["referral_passes"].docs[:] = []
        c, p3 = await H.creer_pass(base3, occ3, tok=tok, referral_campaign=val)
        pd3 = V3.doc_par_tok(base3, p3.get("share_token")) or {}
        verifier("INV-P3 %s -> ignoré silencieusement" % nom, c == 201 and "referral_campaign_id" not in pd3
                 and "invitation" not in pd3, (c, sorted(pd3)))

    # Le message du membre prime
    base4, occ4 = depart()
    c, inv4 = await creer(H.ADMIN, {"type": "pass_duo", "status": "active", "course_id": H.COURS_DUO,
                                    "occurrence": occ4, "message": "Message coach"})
    c, p4 = await H.creer_pass(base4, occ4, referral_campaign=inv4["share_token"],
                               invitation={"message": "Mon message à moi"})
    pd4 = V3.doc_par_tok(base4, p4.get("share_token"))
    verifier("INV-P4 message du membre prioritaire", c == 201 and pd4["invitation"]["message"] == "Mon message à moi"
             and pd4.get("referral_campaign_id") == inv4["id"], pd4.get("invitation"))


async def partie_audit_p2():
    # 1 — PUT concurrent d'un archivage : jamais désarchivée, 409.
    base, occ = depart()
    c, d = await creer(COACH_A, {"type": "event_free", "offer_id": OFFRE_A_ESSAI, "title": "A"})
    _orig = RC._invitation
    _appels = [0]

    async def _lu_puis_archive(coach, inv_id):
        _r = await _orig(coach, inv_id)
        _appels[0] += 1
        if _appels[0] == 1:          # archivé ENTRE la lecture et l'écriture du PUT
            doc(base, d["id"])["status"] = "archived"
        return _r
    RC._invitation = _lu_puis_archive
    try:
        c, r = await modifier(COACH_A, d["id"], {"title": "course", "status": "draft"})
    finally:
        RC._invitation = _orig
    verifier("INV-AUD1 PUT pendant un archivage -> 409, reste archivée, titre intact",
             c == 409 and doc(base, d["id"])["status"] == "archived" and doc(base, d["id"])["title"] == "A", (c, r))

    # 2 — invitation pass_duo d'un AUTRE cours : ignorée à la création du pass.
    base, occ = depart()
    c, inv = await creer(COACH_A, {"type": "pass_duo", "status": "active", "course_id": COURS_A,
                                   "occurrence": occ, "message": "Autre cours"})
    c, p = await H.creer_pass(base, occ, referral_campaign=inv["share_token"])
    pd = V3.doc_par_tok(base, p.get("share_token")) or {}
    verifier("INV-AUD2 invitation d'un autre cours -> ignorée", c == 201 and "referral_campaign_id" not in pd
             and "invitation" not in pd, (c, sorted(pd)))

    # 3 — plafond : 200 non archivées par coach.
    base, occ = depart()
    _plafond = getattr(RC, "PLAFOND_PAR_COACH", 200)
    base["referral_campaigns"].docs += [{"id": "plein-%d" % i, "coach_id": COACH_A, "status": "draft",
                                         "share_token": "plein-tok-%d" % i, "type": "trial", "version": 1}
                                        for i in range(_plafond)]
    c, r = await creer(COACH_A, {"type": "trial"})
    verifier("INV-AUD3 201e invitation -> 409 clair, rien écrit", c == 409 and "200" in str(r.get("detail"))
             and len(base["referral_campaigns"].docs) == _plafond, (c, r))
    c, r = await creer(COACH_B, {"type": "trial"})
    verifier("INV-AUD3b plafond par coach (B non concerné)", c == 201, (c, r))
    base["referral_campaigns"].docs[0]["status"] = "archived"
    c, r = await creer(COACH_A, {"type": "trial"})
    verifier("INV-AUD3c une archivée libère une place", c == 201, (c, r))


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:  # noqa: BLE001
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_moteur_pur, partie_auth, partie_types, partie_proprietaire,
                   partie_jeton_version_pii, partie_pass_duo, partie_audit_p2):
        try:
            boucle.run_until_complete(partie())
        except Exception as err:  # noqa: BLE001
            import traceback
            verifier("PARTIE %s sans exception" % partie.__name__, False,
                     "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1500:]))
    res = [r for r in H.RESULTATS if str(r[0]).startswith(("INV", "PARTIE"))]
    ok = sum(1 for _, c, _ in res if c)
    for nom, cond, detail in res:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom, ("" if cond or not detail else "\n         -> " + str(detail)[:600])))
    print("%d / %d verifications INV-1 au vert" % (ok, len(res)))
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())

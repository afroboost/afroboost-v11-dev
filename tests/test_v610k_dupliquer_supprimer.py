#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610k — « Mes invitations » : DUPLIQUER (nouveau brouillon indépendant) et SUPPRIMER
(toujours logique : archivée, restaurable ; rien d'historique n'est effacé).

Banc sur les VRAIES routes (`referral_campaigns_routes.py`) et le MongoDB en mémoire du
banc Pass Duo. Aucun réseau, aucune donnée réelle.

Lancement : python3 tests/test_v610k_dupliquer_supprimer.py
"""
import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_v610h_publication_dediee as VH  # noqa: E402  (pose l'environnement du banc)

T, H, IC, RC = VH.T, VH.H, VH.IC, VH.RC
verifier = H.verifier
obj, brouillon, etat, JOUR, HEURE, REG_A = VH.obj, VH.brouillon, VH.etat, VH.JOUR, VH.HEURE, VH.REG_A
MEDIAS = {"video_url": "/api/files/v1/v.mp4", "audio_url": "/api/files/a0/mot.mp3", "audio_partage_url": "/api/files/a1/a.mp3",
          "image_url": "/api/files/i1/i.jpg", "image_source": "upload", "description": "Casque fourni."}
JAMAIS = ("share_token", "id", "status", "version", "created_at")


async def route(fn, inv_id, email):
    return await H.appel(fn(inv_id, T.rq(email, {})))


def liste_ids(base, coach):
    return [d["id"] for d in base["referral_campaigns"].docs if d.get("coach_id") == coach and d.get("status") != "archived"]


async def principal():
    verifier("K-0 titre de la copie", RC.titre_copie("AFROBOOST SILENT — ÉDITION SPÉCIALE") == "AFROBOOST SILENT — ÉDITION SPÉCIALE — Copie"
             and len(RC.titre_copie("x" * 80)) == 80 and RC.titre_copie("A — Copie") == "A — Copie")

    # ── A / B / C : essai gratuit, Pass Duo, événement gratuit ─────────────
    base, occ = VH.depart()
    cas = {
        "trial": {"type": "trial", "status": "draft", "title": "Essai A", "offer_id": T.OFFRE_A_ESSAI, "course_id": T.COURS_A},
        "pass_duo": {"type": "pass_duo", "status": "draft", "title": "Duo A", "course_id": T.COURS_A},
        "event_free": {"type": "event_free", "status": "draft", "title": "Soirée gratuite A", "offer_id": T.OFFRE_A_ESSAI,
                       "lieu": "Salle A"},
    }
    for typ, corps in cas.items():
        s, d = await T.creer(T.COACH_A, dict(corps, **MEDIAS))
        src = copy.deepcopy(T.doc(base, d["id"]))
        base["invitation_relais"].docs.append({"id": "rel-" + typ, "jeton": "J-" + typ, "campagne_id": src["id"], "generation": 1})
        s, c = await route(RC.invitations_dupliquer, src["id"], T.COACH_A)
        cp = T.doc(base, (c or {}).get("id"))
        verifier("K-%s1 dupliquer -> 201, brouillon" % typ, s == 201 and cp and cp["status"] == "draft", (s, c))
        verifier("K-%s2 nouvel id, nouveau jeton, version 1" % typ,
                 cp["id"] != src["id"] and cp["share_token"] != src["share_token"] and cp["version"] == 1 and cp.get("copie_de") == src["id"])
        verifier("K-%s3 même type, textes « — Copie », médias RÉFÉRENCÉS (mêmes fichiers)" % typ,
                 cp["type"] == typ and cp["title"] == corps["title"] + " — Copie"
                 and all(cp.get(k) == MEDIAS[k] for k in MEDIAS))
        verifier("K-%s4 mêmes références catalogue (offre / cours partagés)" % typ,
                 cp.get("offer_id") == src.get("offer_id") and cp.get("course_id") == src.get("course_id"))
        verifier("K-%s5 aucun lien personnel copié" % typ,
                 not any(r.get("campagne_id") == cp["id"] for r in base["invitation_relais"].docs))
        verifier("K-%s6 original intact" % typ, T.doc(base, src["id"]) == src)

    # ── D : événement payant à paire DÉDIÉE ────────────────────────────────
    base, occ = VH.depart()
    s, d = await T.creer(T.COACH_A, dict(brouillon("a"), **MEDIAS))
    inv = d["id"]
    await T.modifier(T.COACH_A, inv, {"status": "active"})
    base["reservations"].docs.append({"id": "resa-evt", "courseId": "cours-evt-a", "datetime": JOUR + "T18:45:00", "status": "confirmed", "source": "paid_event_auto"})
    base["payment_transactions"].docs.append({"id": "pay-evt", "offer_id": "offre-evt-a", "amount": 25.0, "status": "paid"})
    base["invitation_relais"].docs.append({"id": "rel-evt", "jeton": "JETON-SOPHIE", "campagne_id": inv, "generation": 1})
    src = copy.deepcopy(T.doc(base, inv))
    o0, c0 = copy.deepcopy(obj(base, "offers", "offre-evt-a")), copy.deepcopy(obj(base, "courses", "cours-evt-a"))
    reg0 = copy.deepcopy(obj(base, "courses", REG_A))
    s, c = await route(RC.invitations_dupliquer, inv, T.COACH_A)
    cp = T.doc(base, c["id"])
    no, nc = obj(base, "offers", cp["offer_id"]), obj(base, "courses", cp["course_id"])
    verifier("K-D1 copie en brouillon, nouvel id + jeton", s == 201 and cp["status"] == "draft" and cp["share_token"] != src["share_token"])
    verifier("K-D2 NOUVELLE offre + NOUVEAU cours (jamais ceux de l'événement réel)",
             cp["offer_id"] != "offre-evt-a" and cp["course_id"] != "cours-evt-a" and no and nc)
    verifier("K-D3 la nouvelle paire est masquée (rien de vendable avant publication)", no["visible"] is False and nc["visible"] is False)
    verifier("K-D4 la nouvelle paire est DÉDIÉE (publiable par le workflow existant)",
             IC.paire_evenement_dediee(no, nc, T.COACH_A) and no[IC.MARQUE_EVENEMENT] != o0[IC.MARQUE_EVENEMENT])
    verifier("K-D5 tarifs / date / lieu repris", all(no.get(k) == o0.get(k) for k in ("price_early_bird", "price_standard", "price_last_minute",
                                                                                      "countdown_date", "countdown_time", "location", "stock"))
             and nc.get("date") == c0.get("date") and nc.get("remplace_cours_id") == REG_A)
    verifier("K-D6 aucun jour exclu copié, aucune réservation / paiement / lien copié",
             not nc.get("dates_annulees") and not any(r.get("courseId") == nc["id"] for r in base["reservations"].docs)
             and not any(p.get("offer_id") == no["id"] for p in base["payment_transactions"].docs)
             and not any(r.get("campagne_id") == cp["id"] for r in base["invitation_relais"].docs))
    verifier("K-D7 événement d'origine INTACT (invitation, offre, cours, cours régulier)",
             T.doc(base, inv) == src and obj(base, "offers", "offre-evt-a") == o0 and obj(base, "courses", "cours-evt-a") == c0
             and obj(base, "courses", REG_A) == reg0)
    s, d = await T.modifier(T.COACH_A, cp["id"], {"status": "active"})
    verifier("K-D8 la copie se publie par le workflow V610h, sans toucher à l'original",
             s == 200 and obj(base, "offers", cp["offer_id"])["visible"] is True and obj(base, "offers", "offre-evt-a") == o0, (s, d))
    # événement payant NON dédié : simple référence au billet du catalogue
    s, d = await T.creer(T.COACH_A, {"type": "event_paid", "status": "draft", "title": "Soirée A", "offer_id": T.OFFRE_A_PAYANTE})
    s, c = await route(RC.invitations_dupliquer, d["id"], T.COACH_A)
    verifier("K-D9 billet NON dédié : référence conservée, aucune offre créée",
             s == 201 and T.doc(base, c["id"])["offer_id"] == T.OFFRE_A_PAYANTE
             and sum(1 for o in base["offers"].docs if o.get("copie_de") == T.OFFRE_A_PAYANTE) == 0)

    # ── IDOR ────────────────────────────────────────────────────────────────
    for nom, fn in (("dupliquer", RC.invitations_dupliquer), ("supprimer", RC.invitations_supprimer),
                    ("restaurer", RC.invitations_restaurer), ("donnees", RC.invitations_donnees_liees)):
        s, _ = await route(fn, inv, T.COACH_B)
        verifier("K-I %s par un autre coach -> 404" % nom, s == 404, s)
    s, _ = await H.appel(RC.invitations_supprimer(inv, T.rq(None, {})))
    verifier("K-I supprimer sans jeton -> 401/403", s in (401, 403), s)
    verifier("K-I rien n'a bougé", T.doc(base, inv)["status"] == "active")

    # ── E : supprimer un brouillon sans historique ──────────────────────────
    base, occ = VH.depart()
    s, d = await T.creer(T.COACH_A, dict(cas["trial"]))
    b = d["id"]
    s, dl = await route(RC.invitations_donnees_liees, b, T.COACH_A)
    verifier("K-E1 brouillon neuf : aucune donnée liée", s == 200 and dl["a_des_donnees"] is False, dl)
    s, r = await route(RC.invitations_supprimer, b, T.COACH_A)
    verifier("K-E2 suppression LOGIQUE (jamais définitive)", s == 200 and r["definitive"] is False
             and T.doc(base, b)["status"] == "archived" and T.doc(base, b).get("supprimee_le"), (s, r))
    s, l = await H.appel(RC.invitations_lister(T.rq(T.COACH_A, {})))
    verifier("K-E3 disparaît de Mes invitations", b not in [x["id"] for x in l["items"]])
    s, l = await H.appel(RC.invitations_lister(T.rq(T.COACH_A, {}, params={"include_archived": "1"})))
    verifier("K-E4 présente dans la corbeille", b in [x["id"] for x in l["items"]])
    s, r = await route(RC.invitations_restaurer, b, T.COACH_A)
    verifier("K-E5 restaurer -> BROUILLON (jamais republiée)", s == 200 and T.doc(base, b)["status"] == "draft"
             and "supprimee_le" not in T.doc(base, b), (s, r))

    # ── F / G / H : supprimer une invitation ACTIVE avec historique ─────────
    base, occ = VH.depart()
    s, d = await T.creer(T.COACH_A, dict(brouillon("a"), **MEDIAS))
    inv = d["id"]
    await T.modifier(T.COACH_A, inv, {"status": "active"})
    base["reservations"].docs.append({"id": "resa-evt", "courseId": "cours-evt-a", "datetime": JOUR + "T18:45:00", "status": "confirmed", "source": "paid_event_auto"})
    base["payment_transactions"].docs.append({"id": "pay-evt", "offer_id": "offre-evt-a", "amount": 25.0, "status": "paid"})
    base["invitation_relais"].docs.append({"id": "rel-evt", "jeton": "JETON-SOPHIE", "campagne_id": inv, "generation": 1})
    base["invitation_events"].docs.append({"id": "ev-1", "campagne_id": inv, "evenement": "partage_whatsapp_declenche"})
    avant = {k: copy.deepcopy(base[k].docs) for k in ("reservations", "payment_transactions", "invitation_relais", "invitation_events")}
    s, dl = await route(RC.invitations_donnees_liees, inv, T.COACH_A)
    verifier("K-F1 données liées détectées (lien perso, statistiques, réservation)",
             dl["a_des_donnees"] and dl["liens_personnels"] == 1 and dl["statistiques"] >= 1 and dl["reservations"] == 1, dl)
    s, r = await route(RC.invitations_supprimer, inv, T.COACH_A)
    verifier("K-F2 archivée, jamais effacée", s == 200 and T.doc(base, inv) is not None and T.doc(base, inv)["status"] == "archived")
    verifier("K-F3 offre + cours dédiés masqués (plus de vente)", etat(base, "a", REG_A)[:2] == (False, False))
    verifier("K-G1 ancien lien : plus public (statut non actif)", not IC.est_active(T.doc(base, inv)) if hasattr(IC, "est_active")
             else T.doc(base, inv)["status"] != "active")
    verifier("K-H1 réservations, paiements, liens personnels, statistiques INTACTS",
             all(base[k].docs[:len(avant[k])] == avant[k] for k in avant))
    verifier("K-H2 jour exclu du cours régulier conservé (pas de réactivation implicite)", JOUR in etat(base, "a", REG_A)[2])
    import api.routes.share_invite_routes as SH
    _p1, _p2 = SH._page_indisponible(), SH._page_indisponible()
    _txt = _p1.body.decode("utf-8")
    verifier("K-G2 ancien lien : page propre 404 (HTML, jamais du texte brut ni une 500), corps identique pour tous",
             _p1.status_code == 404 and _p1.media_type == "text/html" and _p1.body == _p2.body
             and ("n'est plus disponible" in _txt or '<div id="root">' in _txt), (_p1.status_code, _txt[:80]))
    s, r = await route(RC.invitations_restaurer, inv, T.COACH_A)
    verifier("K-H3 restaurée en brouillon, paire toujours masquée, jeton inchangé",
             T.doc(base, inv)["status"] == "draft" and etat(base, "a", REG_A)[:2] == (False, False)
             and T.doc(base, inv)["share_token"] == d.get("share_token", T.doc(base, inv)["share_token"]))


if __name__ == "__main__":
    asyncio.run(principal())
    _res = getattr(H, "RESULTATS", None) or getattr(H, "RES", None)
    if _res is not None:
        _ok = sum(1 for r in _res if (r[0] if isinstance(r, tuple) else r))
        print("\n%d / %d vérifications V610k" % (_ok, len(_res)))
        sys.exit(0 if _ok == len(_res) else 1)

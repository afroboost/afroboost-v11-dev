#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610h — « Publier » un événement créé avec son offre + son cours DÉDIÉS (masqués).

Banc sur les VRAIES routes (`referral_campaigns_routes.py`) et le MongoDB en mémoire
du banc Pass Duo (aucun réseau, aucune donnée réelle) :

  * brouillon -> actif publie ENSEMBLE offre, cours, exclusion du jour sur le cours
    régulier remplacé, invitation ; les autres jours restent intacts ;
  * « offre masquée » reste un refus pour toute offre NON dédiée ;
  * IDOR : la paire d'un autre coach (même pour le super-admin) est refusée ;
  * réservation existante sur le cours régulier ce jour-là -> 409, rien n'est publié ;
  * échec de l'écriture de l'invitation -> retour arrière complet.

Lancement : python3 tests/test_v610h_publication_dediee.py
"""
import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_campaigns as T  # noqa: E402  (pose l'environnement du banc)

H, IC, RC = T.H, T.IC, T.RC
verifier = H.verifier

JOUR, HEURE = "2030-10-30", "18:45"          # un mercredi, loin dans le futur
REG_A, REG_B = "cours-reg-mercredi-a", "cours-reg-mercredi-b"
MARQUE = "evt-test-v610h"


def paire(coach, suffixe, regulier, marque=MARQUE, visible=False):
    cours = {"id": "cours-evt-" + suffixe, "name": "Soirée " + suffixe, "date": JOUR, "time": HEURE, "weekday": None,
             "locationName": "Salle Événement", "visible": visible, "archived": False, "coach_id": coach,
             "v610_evenement": marque, "remplace_cours_id": regulier}
    offre = {"id": "offre-evt-" + suffixe, "name": "Billet " + suffixe, "price": 25.0, "offer_type": "event",
             "billing_mode": "unique", "visible": visible, "archived": False, "coach_id": coach,
             "progressive_pricing": True, "price_early_bird": 25.0, "price_standard": 30.0, "price_last_minute": 40.0,
             "early_bird_days_before": 7, "standard_hours_before": 24, "countdown_enabled": True,
             "countdown_date": JOUR, "countdown_time": HEURE, "stock": -1, "linked_course_ids": [cours["id"]],
             "location": "Salle Événement", "v610_evenement": marque}
    return cours, offre


def depart():
    base, occ = T.depart()
    base["courses"].docs += [
        {"id": REG_A, "name": "Cours à l'unité A", "weekday": 3, "time": HEURE, "locationName": "Salle A",
         "visible": True, "archived": False, "coach_id": T.COACH_A, "dates_annulees": ["2030-11-06"]},
        {"id": REG_B, "name": "Cours à l'unité B", "weekday": 3, "time": HEURE, "locationName": "Salle B",
         "visible": True, "archived": False, "coach_id": T.COACH_B},
    ]
    for coach, suf, reg in ((T.COACH_A, "a", REG_A), (T.COACH_B, "b", REG_B)):
        c, o = paire(coach, suf, reg)
        base["courses"].docs.append(c)
        base["offers"].docs.append(o)
    # Une offre masquée NON dédiée (sans marque) du coach A.
    c, o = paire(T.COACH_A, "a-libre", REG_A, marque=None)
    o.pop("v610_evenement"); c.pop("v610_evenement")
    base["courses"].docs.append(c)
    base["offers"].docs.append(o)
    return base, occ


def obj(base, coll, oid):
    return next((d for d in base[coll].docs if d.get("id") == oid), None)


def brouillon(suffixe):
    return {"type": "event_paid", "status": "draft", "title": "Soirée spéciale",
            "offer_id": "offre-evt-" + suffixe, "course_id": "cours-evt-" + suffixe,
            "occurrence": "%sT%s:00" % (JOUR, HEURE)}


def etat(base, suffixe, reg):
    return (obj(base, "offers", "offre-evt-" + suffixe)["visible"], obj(base, "courses", "cours-evt-" + suffixe)["visible"],
            list(obj(base, "courses", reg).get("dates_annulees") or []))


async def principal():
    # ── moteur pur ──────────────────────────────────────────────────────────
    c, o = paire(T.COACH_A, "x", REG_A)
    verifier("H-M1 paire dédiée du coach reconnue", IC.paire_evenement_dediee(o, c, T.COACH_A.upper()))
    verifier("H-M2 autre coach connecté -> non", not IC.paire_evenement_dediee(o, c, T.COACH_B))
    verifier("H-M3 super-admin sur la paire d'un coach -> non", not IC.paire_evenement_dediee(o, c, H.ADMIN))
    verifier("H-M4 marques différentes -> non", not IC.paire_evenement_dediee(o, dict(c, v610_evenement="autre"), T.COACH_A))
    verifier("H-M5 cours non rattaché -> non", not IC.paire_evenement_dediee(dict(o, linked_course_ids=[]), c, T.COACH_A))
    verifier("H-M6 offre archivée -> non", not IC.paire_evenement_dediee(dict(o, archived=True), c, T.COACH_A))
    verifier("H-M7 sans marque -> non", not IC.paire_evenement_dediee(dict(o, v610_evenement=""), dict(c, v610_evenement=""), T.COACH_A))
    verifier("H-M8 la règle générale reste : masquée = refus", IC.raison_offre_non_billet(o) == "offre masquée")

    # ── A : publication réussie ────────────────────────────────────────────
    base, _ = depart()
    s, d = await T.creer(T.COACH_A, brouillon("a"))
    verifier("H-A1 brouillon créé avec la paire masquée", s == 201 and d.get("status") == "draft", (s, d))
    inv = d["id"]
    jeton = T.doc(base, inv)["share_token"]
    s, d = await T.modifier(T.COACH_A, inv, {"status": "active"})
    verifier("H-A2 Publier -> 200, invitation active", s == 200 and T.doc(base, inv)["status"] == "active", (s, d))
    vo, vc, ann = etat(base, "a", REG_A)
    verifier("H-A3 offre dédiée publiée", vo is True)
    verifier("H-A4 cours dédié publié", vc is True)
    verifier("H-A5 jour exclu sur le cours régulier remplacé", JOUR in ann, ann)
    verifier("H-A6 autres jours intacts (exclusion antérieure gardée, rien d'autre)", sorted(ann) == sorted(["2030-11-06", JOUR]), ann)
    verifier("H-A7 cours régulier toujours visible (seul ce jour est exclu)", obj(base, "courses", REG_A)["visible"] is True)
    verifier("H-A8 jeton de partage inchangé", T.doc(base, inv)["share_token"] == jeton)
    verifier("H-A9 cours régulier d'un autre coach intact", not obj(base, "courses", REG_B).get("dates_annulees"))
    verifier("H-A10 paire de l'autre coach toujours masquée", etat(base, "b", REG_B)[:2] == (False, False))

    # ── B : offre masquée NON dédiée -> refus, rien n'est écrit ─────────────
    base, _ = depart()
    s, d = await T.creer(T.COACH_A, brouillon("a-libre"))
    inv = d["id"]
    s, d = await T.modifier(T.COACH_A, inv, {"status": "active"})
    verifier("H-B1 offre masquée quelconque -> 422 « offre masquée »", s == 422 and "offre masquée" in str(d), (s, d))
    verifier("H-B2 rien publié", etat(base, "a-libre", REG_A) == (False, False, ["2030-11-06"]) and T.doc(base, inv)["status"] == "draft")

    # ── C : IDOR ────────────────────────────────────────────────────────────
    base, _ = depart()
    s, d = await T.creer(T.COACH_A, dict(brouillon("b")))
    verifier("H-C1 coach A ne peut pas viser la paire du coach B", s == 422 and "n'appartient pas" in str(d), (s, d))
    s, d = await T.creer(H.ADMIN, brouillon("a"))
    inv_admin = (d or {}).get("id")
    s, d = await T.modifier(H.ADMIN, inv_admin, {"status": "active"}) if inv_admin else (s, d)
    verifier("H-C2 super-admin : la paire masquée d'un coach n'est pas publiable", s == 422 and "offre masquée" in str(d), (s, d))
    verifier("H-C3 rien publié chez le coach A", etat(base, "a", REG_A) == (False, False, ["2030-11-06"]))
    s, d = await T.creer(T.COACH_A, brouillon("a"))
    inv = d["id"]
    s, d = await T.modifier(T.COACH_B, inv, {"status": "active"})
    verifier("H-C4 coach B ne peut pas publier l'invitation du coach A (404)", s == 404, (s, d))
    verifier("H-C5 toujours rien publié", etat(base, "a", REG_A) == (False, False, ["2030-11-06"]))

    # ── D : réservation existante sur le cours régulier ce jour-là ─────────
    base, _ = depart()
    base["reservations"].docs.append({"id": "resa-1", "courseId": REG_A, "datetime": JOUR + "T18:45:00", "status": "confirmed"})
    base["reservations"].docs.append({"id": "resa-2", "courseId": REG_A, "datetime": "2030-11-13T18:45:00", "status": "confirmed"})
    s, d = await T.creer(T.COACH_A, brouillon("a"))
    inv = d["id"]
    s, d = await T.modifier(T.COACH_A, inv, {"status": "active"})
    verifier("H-D1 réservation ce jour-là -> 409 explicite", s == 409 and "1 réservation" in str(d), (s, d))
    verifier("H-D2 rien publié", etat(base, "a", REG_A) == (False, False, ["2030-11-06"]) and T.doc(base, inv)["status"] == "draft")
    base["reservations"].docs[0]["status"] = "cancelled"
    s, d = await T.modifier(T.COACH_A, inv, {"status": "active"})
    verifier("H-D3 réservation annulée ne bloque pas", s == 200 and T.doc(base, inv)["status"] == "active", (s, d))

    # ── E : échec de l'écriture de l'invitation -> retour arrière ──────────
    base, _ = depart()
    s, d = await T.creer(T.COACH_A, brouillon("a"))
    inv = d["id"]
    coll = base["referral_campaigns"]
    orig = coll.update_one

    async def panne(q, maj, **k):
        raise RuntimeError("panne simulée")
    coll.update_one = panne
    try:
        s, d = await T.modifier(T.COACH_A, inv, {"status": "active"})
    except RuntimeError:
        s = "exception"
    coll.update_one = orig
    verifier("H-E1 panne à l'écriture de l'invitation -> erreur", s != 200, s)
    verifier("H-E2 retour arrière : offre + cours de nouveau masqués, jour non exclu",
             etat(base, "a", REG_A) == (False, False, ["2030-11-06"]), etat(base, "a", REG_A))
    verifier("H-E3 invitation toujours brouillon", T.doc(base, inv)["status"] == "draft")

    # ── F : publier une seconde fois / jour déjà exclu ─────────────────────
    base, _ = depart()
    obj(base, "courses", REG_A)["dates_annulees"] = ["2030-11-06", JOUR]
    s, d = await T.creer(T.COACH_A, brouillon("a"))
    inv = d["id"]
    s, d = await T.modifier(T.COACH_A, inv, {"status": "active"})
    verifier("H-F1 jour déjà exclu : publié sans doublon", s == 200 and etat(base, "a", REG_A)[2] == ["2030-11-06", JOUR], (s, etat(base, "a", REG_A)))
    s, d = await T.modifier(T.COACH_A, inv, {"title": "Soirée spéciale !"})
    verifier("H-F2 modification après publication : 200, rien ne se re-masque", s == 200 and etat(base, "a", REG_A)[:2] == (True, True), (s, d))

    # ── G : MASQUER / RÉACTIVER (complément du 12/10) ───────────────────────
    base, _ = depart()
    s, d = await T.creer(T.COACH_A, brouillon("a"))
    inv = d["id"]
    await T.modifier(T.COACH_A, inv, {"status": "active", "video_url": "/api/files/v1/v.mp4",
                                      "audio_partage_url": "/api/files/a1/a.mp3", "image_url": "/api/files/i1/i.jpg",
                                      "image_source": "upload"})
    avant = copy.deepcopy(T.doc(base, inv))
    base["reservations"].docs.append({"id": "resa-evt", "courseId": "cours-evt-a", "datetime": JOUR + "T18:45:00", "status": "confirmed"})
    base["payment_transactions"].docs.append({"id": "pay-evt", "offer_id": "offre-evt-a", "amount": 25.0, "status": "paid"})
    base["invitation_relais"].docs.append({"id": "rel-1", "jeton": "JETON-SOPHIE", "campagne_id": inv, "generation": 1})
    s, d = await appel_route(RC.invitations_masquer, inv, T.COACH_A)
    verifier("H-G1 Masquer -> 200, statut masquée", s == 200 and T.doc(base, inv)["status"] == "hidden", (s, d))
    verifier("H-G2 offre + cours dédiés masqués (plus de vente)", etat(base, "a", REG_A)[:2] == (False, False))
    verifier("H-G3 cours régulier : jour TOUJOURS exclu (pas de réactivation implicite)", JOUR in etat(base, "a", REG_A)[2])
    verifier("H-G4 réservation conservée", obj(base, "reservations", "resa-evt") is not None)
    verifier("H-G5 paiement conservé", obj(base, "payment_transactions", "pay-evt") is not None)
    verifier("H-G6 lien personnel conservé", obj(base, "invitation_relais", "rel-1") is not None)
    apres = T.doc(base, inv)
    verifier("H-G7 médias, textes, jeton, ids conservés",
             all(apres.get(k) == avant.get(k) for k in ("id", "share_token", "video_url", "audio_partage_url", "image_url",
                                                        "title", "offer_id", "course_id", "occurrence")))
    s, d = await appel_route(RC.invitations_masquer, inv, T.COACH_B)
    verifier("H-G8 autre coach ne peut pas masquer (404)", s == 404, s)
    s, d = await appel_route(RC.invitations_reactiver, inv, T.COACH_B)
    verifier("H-G9 autre coach ne peut pas réactiver (404)", s == 404 and T.doc(base, inv)["status"] == "hidden", s)
    s, d = await appel_route(RC.invitations_reactiver, inv, T.COACH_A)
    apres = T.doc(base, inv)
    verifier("H-G10 Réactiver -> 200, active", s == 200 and apres["status"] == "active", (s, d))
    verifier("H-G11 mêmes ids / même jeton / médias intacts",
             all(apres.get(k) == avant.get(k) for k in ("id", "share_token", "video_url", "audio_partage_url", "image_url", "offer_id", "course_id")))
    verifier("H-G12 offre + cours de nouveau publiés", etat(base, "a", REG_A)[:2] == (True, True))
    verifier("H-G13 aucun doublon (1 invitation, 1 offre, 1 cours, jour exclu une fois)",
             sum(1 for x in base["referral_campaigns"].docs if x.get("offer_id") == "offre-evt-a") == 1
             and sum(1 for x in base["offers"].docs if x.get("id") == "offre-evt-a") == 1
             and etat(base, "a", REG_A)[2].count(JOUR) == 1)
    s, d = await appel_route(RC.invitations_masquer, inv, T.COACH_A)
    s2, _ = await appel_route(RC.invitations_masquer, inv, T.COACH_A)
    verifier("H-G14 masquer deux fois : sans effet de bord", s == 200 and s2 == 200 and T.doc(base, inv)["status"] == "hidden")
    T.doc(base, inv)["occurrence"] = "2020-10-28T18:45:00"
    s, d = await appel_route(RC.invitations_reactiver, inv, T.COACH_A)
    verifier("H-G15 événement passé : réactivation refusée avec conseil", s == 409 and "déjà passé" in str(d), (s, d))
    verifier("H-G16 rien republié", etat(base, "a", REG_A)[:2] == (False, False) and T.doc(base, inv)["status"] == "hidden")
    T.doc(base, inv)["occurrence"] = "%sT%s:00" % (JOUR, HEURE)
    s, d = await appel_route(RC.invitations_masquer, "inexistante", T.COACH_A)
    verifier("H-G17 brouillon / inconnue : masquer refusé proprement", s == 404, s)
    s, d = await T.creer(T.COACH_A, brouillon("a-libre"))
    s, d = await appel_route(RC.invitations_masquer, d["id"], T.COACH_A)
    verifier("H-G18 un brouillon ne se « masque » pas (409)", s == 409, s)

    # ── I : archiver = hors ligne, la paire dédiée ne reste pas en vente ───
    base, _ = depart()
    s, d = await T.creer(T.COACH_A, brouillon("a"))
    inv = d["id"]
    await T.modifier(T.COACH_A, inv, {"status": "active"})
    s, d = await appel_route(RC.invitations_archiver, inv, T.COACH_A)
    verifier("H-I1 archivée : offre + cours dédiés masqués, rien supprimé",
             s == 200 and T.doc(base, inv)["status"] == "archived" and etat(base, "a", REG_A)[:2] == (False, False), (s, d))

    ok = sum(1 for r in H.RES if r) if hasattr(H, "RES") else None
    return ok


async def appel_route(route, inv_id, email):
    return await H.appel(route(inv_id, T.rq(email, {})))


if __name__ == "__main__":
    asyncio.run(principal())
    _res = getattr(T.H, "RESULTATS", None) or getattr(T.H, "RES", None)
    if _res is not None:
        _ok = sum(1 for r in _res if (r[0] if isinstance(r, tuple) else r))
        print("\n%d / %d vérifications V610h" % (_ok, len(_res)))
        sys.exit(0 if _ok == len(_res) else 1)

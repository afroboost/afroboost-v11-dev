#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610 — Préparer / publier l'événement AFROBOOST SILENT — ÉDITION SPÉCIALE (28/10/2026).

PAR DÉFAUT : ESSAI À BLANC (rien n'est écrit). `--appliquer` pour écrire.

  python3 scripts/v610_evenement_silent.py --mongo-url … --db … preparer [--appliquer]
  python3 scripts/v610_evenement_silent.py --mongo-url … --db … publier  [--appliquer]

PRÉPARER (brouillon, invisible) — idempotent (marque `v610_evenement`) :
  * le COURS de l'événement : mercredi 28/10/2026 18:45, AU LIEU EXACT du cours
    régulier du mercredi (lu en base, jamais saisi ici), `visible: false` ;
  * l'OFFRE billet : 3 paliers 25 / 30 / 40 CHF (bascules 21/10 18:45 et 27/10
    18:45, Europe/Zurich), fin des ventes au début de l'événement (compte à
    rebours), réservation AUTOMATIQUE au paiement, place OFFERTE aux abonnements
    8 mois actifs. AUCUNE capacité (stock -1, pas de participants max).
    `visible: false` ;
  * l'INVITATION (boule de neige) en BROUILLON : titre, accroche, offre, cours,
    date — emplacements vidéo / voix-off / miniature VIDES (médias Cowork à venir).

PUBLIER (seulement quand les médias sont validés) :
  * offre + cours visibles ;
  * le cours régulier du mercredi n'a pas lieu le 28/10 (`dates_annulees`) —
    refusé s'il porte déjà des réservations ce jour-là ;
  * l'invitation passe ACTIVE par les règles du serveur (mêmes contrôles que l'écran).

Aucun paiement, aucun e-mail, aucun WhatsApp n'est déclenché par ce script.
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

MARQUE = "silent-2026-10-28"
COACH = "contact.artboost@gmail.com"
COURS_MERCREDI = "62fcac27-75ad-4429-bfb1-aee613858bdc"
DATE, HEURE = "2026-10-28", "18:45"
TITRE = "AFROBOOST SILENT — ÉDITION SPÉCIALE"
ACCROCHE = "1 heure de cardio-danse afro au casque, accessible à tous les niveaux."
# Les abonnements « 8 mois » de la saison hiver (identifiés en production le 12/10/2026
# par leur ID, leur `duree_mois` / `billing_mode` — jamais par leur titre seul) :
OFFRES_8_MOIS = [
    "9fa5ac00-9ba2-4e54-b40e-54827f16f072",   # Saison hiver — 8 mois (549 CHF, paiement unique, duree_mois 8)
    "7b96a431-26ce-4a98-bd66-ebffffd7c35c",   # Saison hiver — 2 paiements (2 × 299 CHF, saison_2x)
    "ba530ae4-934c-46b1-8bc5-4999448f1e86",   # Membres — 8 mois (2 × 199.99 CHF, saison_2x, duree_mois 8)
]
VIDEO_URL = None
AUDIO_PARTAGE_URL = None   # V610d : « Deviens Afroboosteur », écouté APRÈS la réservation
DESCRIPTION = """Afroboost Silent 🔥🎧

1 heure de cardio-danse afro, accessible à tous les niveaux, avec ton propre casque audio.

Tu suis le coach, tu bouges à ton rythme et tu profites de l'énergie du groupe dans ta bulle.

🎧 Casque fourni
🔥 Tous niveaux
💜 Une expérience Afroboost spéciale

Plus tu réserves tôt, moins c'est cher :

25 CHF prévente
30 CHF standard
40 CHF dernière minute

💜 Événement offert aux membres Afroboost avec abonnement 8 mois actif."""


def _iso():
    return datetime.now(timezone.utc).isoformat()


async def preparer(db, appliquer):
    reg = await db.courses.find_one({"id": COURS_MERCREDI}, {"_id": 0})
    if not reg or not (reg.get("locationName") or reg.get("location")):
        raise SystemExit("STOP : cours régulier du mercredi introuvable ou sans lieu — rien n'est inventé.")
    lieu = reg.get("locationName") or reg.get("location")
    print("Lieu (lu sur le cours du mercredi) :", lieu)
    for oid in OFFRES_8_MOIS:
        o = await db.offers.find_one({"id": oid}, {"_id": 0, "name": 1, "duree_mois": 1, "billing_mode": 1})
        print("  offre 8 mois", oid[:8], "->", (o or {}).get("name"), (o or {}).get("billing_mode"), (o or {}).get("duree_mois"))
        if not o:
            raise SystemExit("STOP : offre 8 mois %s introuvable." % oid)

    cours = await db.courses.find_one({"v610_evenement": MARQUE}, {"_id": 0})
    if not cours:
        cours = {"id": str(uuid.uuid4()), "name": TITRE, "date": DATE, "weekday": None, "time": HEURE,
                 "location": lieu, "locationName": lieu, "mapsUrl": reg.get("mapsUrl") or "",
                 "duration_minutes": 60, "coach_id": COACH, "visible": False, "archived": False,
                 "v610_evenement": MARQUE, "created_at": _iso()}
        print("COURS à créer :", cours["id"], cours["date"], cours["time"], "visible=False")
        if appliquer:
            await db.courses.insert_one(dict(cours))
    else:
        print("COURS déjà présent :", cours["id"])

    offre = await db.offers.find_one({"v610_evenement": MARQUE}, {"_id": 0})
    if not offre:
        offre = {
            "id": str(uuid.uuid4()), "name": TITRE, "description": DESCRIPTION, "price": 25.0,
            "offer_type": "event", "category": "service", "isProduct": False, "billing_mode": "unique",
            "season": "toutes", "audience": "all", "owner_type": "admin", "coach_id": COACH,
            "visible": False, "archived": False, "link_only": False,
            "stock": -1, "max_participants": None,                       # AUCUNE limite de places
            "pack_sessions": 1, "linked_course_ids": [cours["id"]], "location": lieu,
            "duration_minutes": 60, "thumbnail": "", "videoUrl": "", "images": [],
            "progressive_pricing": True, "price_early_bird": 25.0, "price_standard": 30.0,
            "price_last_minute": 40.0, "early_bird_days_before": 7, "standard_hours_before": 24,
            "label_early_bird": "Prévente", "label_standard": "Standard", "label_last_minute": "Dernière minute",
            "countdown_enabled": True, "countdown_date": DATE, "countdown_time": HEURE,
            "countdown_text": TITRE,
            "evenement_reservation_auto": True, "gratuit_abonnements_offer_ids": list(OFFRES_8_MOIS),
            "v610_evenement": MARQUE, "created_at": _iso(),
        }
        print("OFFRE à créer :", offre["id"], "25/30/40 CHF, visible=False, réservation auto, 8 mois offerts")
        if appliquer:
            await db.offers.insert_one(dict(offre))
    else:
        print("OFFRE déjà présente :", offre["id"])

    from api.routes import referral_campaigns_engine as IC
    camp = await db.referral_campaigns.find_one({"offer_id": offre["id"], "status": {"$ne": "archived"}}, {"_id": 0})
    if camp:
        print("INVITATION déjà présente :", camp["id"], camp.get("status"), "| vidéo :", camp.get("video_url") or "VIDE")
        print("  audio après réservation :", camp.get("audio_partage_url") or "VIDE")
        _maj = {}
        if VIDEO_URL and camp.get("video_url") != VIDEO_URL:
            _maj["video_url"] = VIDEO_URL
        if AUDIO_PARTAGE_URL and camp.get("audio_partage_url") != AUDIO_PARTAGE_URL:
            _maj["audio_partage_url"] = AUDIO_PARTAGE_URL
        if _maj:
            print("  -> à rattacher :", _maj)
            if appliquer:
                _maj["updated_at"] = _iso()
                await db.referral_campaigns.update_one({"id": camp["id"]}, {"$set": _maj, "$inc": {"version": 1}})
        return
    champs = IC.valider_entree({"type": "event_paid", "status": "draft", "title": TITRE, "subtitle": ACCROCHE,
                                "cta_label": "Je réserve ma place", "offer_id": offre["id"], "course_id": cours["id"],
                                "occurrence": "%sT%s" % (DATE, HEURE)}, None)
    profil = await db.coaches.find_one({"email": COACH}, {"_id": 0}) or {}
    import secrets
    doc = dict(champs)
    # Une invitation du super-admin est rangée sous la clé PLATEFORME "" (`_coach_strict`) :
    # c'est sous elle que l'écran « Mes invitations » la retrouve.
    doc.update({"id": str(uuid.uuid4()), "coach_id": "", "version": 1, "share_token": secrets.token_urlsafe(24),
                "inviter_display": IC.identite_coach(profil), "created_at": _iso(), "updated_at": _iso(),
                "video_url": None, "audio_url": None, "image_url": None})
    doc = {k: doc.get(k) for k in IC.CHAMPS_DOCUMENT}
    if VIDEO_URL:
        doc["video_url"] = IC.valider_media_url(VIDEO_URL, "video_url")
    if AUDIO_PARTAGE_URL:
        doc["audio_partage_url"] = IC.valider_media_url(AUDIO_PARTAGE_URL, "audio_partage_url")
    print("INVITATION brouillon à créer :", doc["id"], "| vidéo :", doc.get("video_url") or "VIDE",
          "| audio après réservation :", doc.get("audio_partage_url") or "VIDE", "| miniature : VIDE")
    if appliquer:
        await db.referral_campaigns.insert_one(dict(doc))


async def publier(db, appliquer):
    cours = await db.courses.find_one({"v610_evenement": MARQUE}, {"_id": 0})
    offre = await db.offers.find_one({"v610_evenement": MARQUE}, {"_id": 0})
    if not cours or not offre:
        raise SystemExit("STOP : préparer d'abord.")
    camp = await db.referral_campaigns.find_one({"offer_id": offre["id"], "status": {"$ne": "archived"}}, {"_id": 0})
    # Vidéo finale OBLIGATOIRE (elle porte son propre son). Voix-off séparée : facultative
    # (décision du 12/10). Miniature : facultative — sans elle, la carte générée sert d'aperçu.
    if not camp or not camp.get("video_url"):
        raise SystemExit("STOP : vidéo finale non rattachée à l'invitation — pas de publication.")
    if not camp.get("image_url"):
        print("ATTENTION : aucune miniature finale — l'aperçu WhatsApp utilisera la carte générée.")
    deja = await db.reservations.count_documents({"courseId": COURS_MERCREDI, "datetime": {"$regex": "^%s" % DATE}})
    if deja:
        raise SystemExit("STOP : %d réservation(s) existent sur le cours régulier du %s — à traiter avant." % (deja, DATE))
    print("Publier : offre + cours visibles, %s annulé pour le cours régulier, invitation active." % DATE)
    if not appliquer:
        return
    await db.offers.update_one({"id": offre["id"]}, {"$set": {"visible": True}})
    await db.courses.update_one({"id": cours["id"]}, {"$set": {"visible": True}})
    await db.courses.update_one({"id": COURS_MERCREDI}, {"$addToSet": {"dates_annulees": DATE}})
    print("Activer l'invitation depuis l'écran « Mes invitations » (mêmes contrôles serveur).")


async def principal():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo-url", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("etape", choices=("preparer", "publier"))
    ap.add_argument("--appliquer", action="store_true")
    ap.add_argument("--video-url", default=None, help="/api/files/... de la vidéo finale (préparer)")
    ap.add_argument("--audio-partage-url", default=None, help="/api/files/... de l'audio « Deviens Afroboosteur » (préparer)")
    a = ap.parse_args()
    global VIDEO_URL, AUDIO_PARTAGE_URL
    VIDEO_URL = a.video_url if (a.video_url or "").startswith("/api/files/") else None
    AUDIO_PARTAGE_URL = a.audio_partage_url if (a.audio_partage_url or "").startswith("/api/files/") else None
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(a.mongo_url, serverSelectionTimeoutMS=15000)[a.db]
    print("== V610 %s — %s" % (a.etape, "ÉCRITURE" if a.appliquer else "ESSAI À BLANC (rien n'est écrit)"))
    await (preparer if a.etape == "preparer" else publier)(db, a.appliquer)


if __name__ == "__main__":
    asyncio.run(principal())

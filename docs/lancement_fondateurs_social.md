# AFROBOOST — FONDATEURS SEPTEMBRE 2026 — campagne social (1 Reel maître) — préparé le 16/09/2026

> **RIEN N'EST PUBLIÉ.** Fichiers vidéo dans `Claude outputs/fondateurs_reel/` (non versionnés). Aucun compte social modifié.

## Reel maître
- `MASTER_CLEAN.mp4` — 1080×1920, 30 fps, **32,2 s**, H.264 (crf 17) + AAC : **sans musique** (ambiance naturelle des rushes à −9 dB) → à publier tel quel puis ajouter le son **dans chaque plateforme** (Instagram / Facebook / TikTok / YouTube Shorts). Aucun watermark plateforme.
- `MASTER_SOCIAL_mak.mp4` — même image + piste `(8)mak-saute-Bassi.mp3` (à partir de 96 s, fondu de sortie). ⚠️ **Licence non prouvée dans le fichier** (aucun tag) : les 5 reels de juillet l'appelaient « ta musique » — **à confirmer par Bassi** que c'est sa production avant toute utilisation publique/publicitaire. En cas de doute : `MASTER_CLEAN` + son de la plateforme.
- `MASTER_COVER.jpg` — vignette (hook, 1,3 s). `check_final.jpg` — 6 vignettes de contrôle (une par section).
- Rushes : session Afroboost réelle en extérieur (30 clips 4K 25 fps, `~/Claude/Projects/SporDate Studio IA/RUSHS_BRUTS`), recadrés 9:16 et étalonnés (contraste/saturation, teinte homogène) : C1158 (gros plan sourire, bras levés — hook), C1117 (Bassi mène le groupe), C1131 (casque, gros plan punchy), C1124 (danse à deux), C1133 (grand groupe), C1143 ×2 (contre-plongée sous l'arche, sauts), C1128 (Bassi + groupe + lac), C1133 (CTA, assombri).
- Structure : 0–3 s « Tu cherches un entraînement différent à Neuchâtel ? » · 3–9 s « Cardio + danse afrobeat + casque audio » · 9–15 s « Pas besoin de savoir danser » · 15–22 s « OFFRE FONDATEURS / 59 CHF / mois / 8 séances / mois » · 22–27 s « 50 places maximum / Jusqu'au 30 septembre » · 27–32 s logo, « Découvre Afroboost » → « Réserve ton offre Fondateurs », afroboost.com.
- Style : noir #000000 / fuchsia #D91CD2 / blanc #FFFFFF, police Anton (OFL, reprise de Studiio) + Arial Bold, logo discret en haut à gauche, textes centrés dans les zones sûres (aucun texte sous 70 % de la hauteur ni dans la colonne droite), fondus courts, cuts toutes les 3–5 s.

## Campagne
- **Nom** : AFROBOOST — FONDATEURS SEPTEMBRE 2026 · **Période** : 16/09 → 30/09/2026 · **Objectif** : trafic → offre Fondateurs → achat · **CTA** : Découvrir l'offre Fondateurs.
- **URL centrale** : `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437` (fiche Fondateurs, vérifiée 200 pour les 4 UTM ci-dessous).
- **UTM par réseau** (tracking M2-A existant, sources `instagram`, `facebook`, `tiktok`, `youtube` toutes dans `M2A_SOURCES` — shared.py:5699 / `utils/attribution.js:45`) :
  - Instagram : `…&utm_source=instagram&utm_medium=social&utm_campaign=fondateurs2026`
  - Facebook : `…&utm_source=facebook&utm_medium=social&utm_campaign=fondateurs2026`
  - TikTok : `…&utm_source=tiktok&utm_medium=social&utm_campaign=fondateurs2026`
  - YouTube : `…&utm_source=youtube&utm_medium=social&utm_campaign=fondateurs2026`
  - Story : `utm_source=instagram&utm_content=story` (« story » n'est pas une source de la liste fermée).

## Légendes (le Reel reste identique)
**Base (Instagram / Facebook)** :
🔥 La saison Afroboost reprend à Neuchâtel.
Découvre l'offre Fondateurs :
59 CHF/mois · 8 séances/mois · 50 places maximum · jusqu'au 30 septembre.
Cardio + danse afrobeat + casque audio. Pas besoin de savoir danser.
👉 Découvre l'offre : [lien tracké du réseau] (Instagram : « lien en bio »)
#Afroboost #Neuchatel #Afrobeat #CardioDanse #FitnessNeuchatel

**TikTok** (court) : Entraînement différent à Neuchâtel : cardio + danse afrobeat + casque audio 🎧 Offre Fondateurs 59 CHF/mois, 8 séances, 50 places jusqu'au 30 septembre → lien en bio. #Afroboost #Neuchatel #Afrobeat #CardioDanse
**YouTube Shorts** (titre + description) : « Afroboost Neuchâtel — Offre Fondateurs 59 CHF/mois » · description = base + lien YouTube tracké.

## Calendrier (même Reel, accroches différentes, sans marteler la même audience : alterner Reel / Story, matin / soir)
| Jour | Date | Format | Accroche de légende |
|---|---|---|---|
| J1 | 16/09 | Reel IG + FB + TikTok + Shorts | Lancement : « La saison reprend à Neuchâtel — offre Fondateurs ouverte » |
| J3 | 18/09 | Reel IG (soir) + Story | Expérience : « Cardio, afrobeat, casque audio : l'entraînement qu'on ne voit nulle part ailleurs » |
| J5 | 20/09 | Reel FB + TikTok (matin) | Offre : « 59 CHF/mois, 8 séances, 50 places — pourquoi Fondateurs » |
| J8 | 23/09 | Reel IG + Story | Rappel deadline : « Plus que 7 jours — jusqu'au 30 septembre » |
| J11+ | 26–30/09 | Story + Reel (selon résultats) | Final : « Dernières places / dernières heures » **seulement si le stock réel le justifie** (le site affiche les places restantes) |

## Studiio.pro — état réel (lecture seule de `origin/main` `623019f`, 16/09)
- **Calendrier IA** : `src/app/dashboard/calendar/page.tsx` — lit/écrit `scheduled_posts` via `GET/POST/PUT/DELETE /api/posts` (`src/app/api/posts/route.ts:11-248`), brouillons `status: draft`, `platforms TEXT[]`, `scheduled_date/time`, `media_url`. Agent IA (`AgentIAModal`) pour générer le contenu.
- **Médias / Bibliothèque** : `POST /api/upload/media` (Supabase Storage, buckets `media`/`audio`, `src/app/api/upload/media/route.ts:31`), `GET /api/media/list`, `signed-url` + `PUT /api/storage/upload`.
- **Réseaux sociaux** : deux mécanismes — `social_accounts` (Meta Graph/TikTok/YouTube détenus par Studiio, `002_complete_schema.sql:85`, **UNIQUE(user_id, platform)**) et **Zernio** (fournisseur de publication, `migrations/2026-08-08-zernio.sql:21`, `zernio_accounts(user_id, platform, profile_id)`, `publishing_enabled` par utilisateur, webhook `/api/social/zernio/webhook`).
- **Planification / publication** : cron `GET /api/cron/publish` (`Bearer CRON_SECRET`, route.ts:64) ne prend que `status = 'scheduled'` (route.ts:209) → `publishViaZernio` sinon `social_accounts` ; publication immédiate `POST /api/social/publish` (session).
- **Rattachement d'un post à un compte** : uniquement **`post.user_id`** (`cron/publish/route.ts:49`, `social/publish/route.ts:63-65`). **Aucune notion de marque / projet / workspace** dans le schéma (grep `brand_id|workspace|organization` = 0).
- **⚠️ Protection Spordateur** : Instagram/Facebook sont liés à l'utilisateur Studiio de Bassi. Tout post créé sous **ce même utilisateur** avec `platforms` instagram/facebook partirait **sur les comptes Spordateur**. Garde-fous possibles avec l'existant : (1) laisser les posts Afroboost en `draft` (le cron ignore les brouillons) ; (2) publier Afroboost depuis un **utilisateur Studiio distinct** dont les comptes connectés sont ceux d'Afroboost (un compte par plateforme et par utilisateur = la seule cloison qui existe) ; (3) `publishing_enabled=false` coupe toute publication Zernio d'un utilisateur.
- **API** : toutes les routes posts/médias sont protégées par la **session NextAuth** (`auth()`), aucune clé API ni jeton machine ; seul le cron a un `Bearer CRON_SECRET`. **Aucun webhook entrant** pour créer un post. Aucun modèle « Campaign » (la campagne = un ensemble de `scheduled_posts`).

## Connexion Afroboost → Studiio (audit, rien développé)
- **Existe** : `POST /api/posts` (brouillon dans le Calendrier IA à partir de `title, caption, media_url, media_type, platforms, scheduled_date, scheduled_time, status, metadata`) ; `media_url` peut être une URL externe (Cloudinary Afroboost) ; `metadata` JSON libre (UTM, campagne) ; import média par upload ; publication différée par le cron.
- **Manque** : une **authentification machine** (clé API ou jeton de service lié à un `user_id`) sur `POST /api/posts` — aujourd'hui session navigateur uniquement ; une notion de **marque/workspace** (cloison Afroboost / Spordateur) ; un endpoint d'import multi-posts (campagne).
- **Plus petite intégration** : côté Studiio, accepter sur `POST /api/posts` un `Authorization: Bearer <STUDIIO_API_TOKEN_AFROBOOST>` résolu vers un `user_id` dédié « Afroboost » (~20 lignes, même pattern que le `CRON_SECRET`) ; côté Afroboost, un appel sortant à la création d'une campagne marketing : `{title, caption (+UTM), media_url: <Cloudinary>, media_type: 'video', platforms: [...], scheduled_date/time, status: 'draft', metadata: {source:'afroboost', campaign:'fondateurs2026'}}` → brouillon visible dans le Calendrier IA, planification/publication laissée à Studiio. Zéro nouvelle table, zéro nouveau système analytics.

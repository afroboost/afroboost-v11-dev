# TRD — Afroboost (technique, plateforme complète)

> Document technique global d'**afroboost.com**, établi le 19/10/2026 à partir du code (`main` = `0a575c9b`) et de la
> production (lecture seule). Aucun secret n'est reproduit : seuls des **noms** de variables apparaissent.
> Détail du module Live : [`modules/live/LIVE_AUDIT.md`](modules/live/LIVE_AUDIT.md). Schéma de données :
> [`BACKEND_SCHEMA.md`](BACKEND_SCHEMA.md) et [`annexes/SCHEMA_MONGO_REEL.md`](annexes/SCHEMA_MONGO_REEL.md).

## 1. Architecture actuelle

```
Navigateur / PWA (React 19, service worker)
        │ HTTPS
        ▼
Cloudflare (proxy, cache, TLS)  ──►  VPS Hetzner 178.105.201.62  ──►  Traefik (Coolify)
                                                                       │
            ┌──────────────────────────────────────────────────────────┼─────────────────────────────┐
            ▼                                                          ▼                             ▼
  App Coolify afroboost-v11-dev (Docker)                  afroboost-live (/live, iframe)     spordate-rencontre (/rencontre)
  uvicorn 1 worker : FastAPI api/server.py                + backend api-live.afroboost.com     (app Next/Firebase séparée)
  + build React servi par le même conteneur               + LiveKit SFU/Egress/Redis
            │                                              + Supabase (supabase-live)
            ▼
  MongoDB Atlas (base promo-credits-lab, 109 collections)   Disque MEDIA_DIR (/app/media) — fichiers /api/files
            │
            ├─ Stripe (Checkout, TWINT, abonnements, Connect)       ├─ Resend (e-mails sortants + entrants, webhooks Svix)
            ├─ Meta WhatsApp Cloud API (modèles, webhook)            ├─ OpenAI (chat, IA prospection gpt-4.1, traduction)
            ├─ Web Push (VAPID)                                      ├─ Google (OAuth, Contacts, Calendar)
            ├─ OSM Nominatim + OSRM (trajets)                         ├─ PostHog (analytics)
            └─ PawaPay / CinetPay / PayPal (dormants/partiels)       └─ api.qrserver.com (QR), Studiio, Spordate
```

## 2. Frontend
| Élément | Réalité |
|---|---|
| Framework | React 19 (CRA 5 + CRACO), Tailwind 3, quelques composants shadcn/Radix (presque inutilisés), axios |
| Routage | **aucun routeur** : `App.js` lit `pathname`/`hash`/`search` et rend par retours anticipés (13 cas prioritaires) ; `react-router-dom` installé mais inutilisé |
| Taille | 168 938 lignes ; `ChatWidget.js` 13 673, `App.js` 11 140, `CoachDashboard.js` 9 706 ; 2 sauvegardes mortes de CoachDashboard (~15,6 k lignes) |
| État | `useState`/`useEffect`, `localStorage` (identité, thème, session), hook `useChargement` (états de section) |
| Auth côté client | intercepteur axios global : ajoute `Authorization: Bearer afroboost_jwt` **et** `X-User-Email` ; gère la session expirée (`terminerSession`) |
| PWA | `public/sw.js` (ES5), `CACHE_NAME` à incrémenter à chaque livraison front (`afroboost-v619` au 19/10) ; navigations network-first, `/static/` cache-first, `/api/` non intercepté |
| i18n | FR/EN/DE (vitrine et réservation) ; le reste est en français en dur |
| Analytics | PostHog (snippet `index.html`, autocapture désactivé) |
| Tests | Jest (143 suites, 2 462 tests au 15/10) |

## 3. Backend
| Élément | Réalité |
|---|---|
| Framework | FastAPI 0.110, Python 3.11 (image `python:3.11-slim`), Motor 3.3 / PyMongo 4.5 |
| Processus | **uvicorn 1 worker** (`Dockerfile:77`) — les limites de débit et caches en mémoire ne sont valables que parce qu'il n'y a qu'un processus |
| Code | `api/server.py` ≈ 57 000 lignes (441 routes) + `api/routes/*.py` (220 routes) = **661 routes** ; `api/resend_central.py` (point d'envoi e-mail unique), `api/routes/shared.py` (règles communes) |
| Code mort | `admin_routes.py`, `scheduler_engine.py`, routes de migration `v2xx/v30x`, webhook Twilio, 3 routes masquées par des doublons |
| Démarrage | création d'index, ~11 boucles de fond (voir §Schedulers), résolution de `JWT_SECRET` (env → fichier → `app_secrets`) |
| Santé | `/healthz` (vivacité sans Mongo, `boot_id`, `uptime_s`) = HEALTHCHECK Docker ; `/health` (ping Atlas) ; `/api/debug/config` (présence des clés, booléens) |

## 4. Base de données
- **MongoDB Atlas**, base `promo-credits-lab`, **109 collections** (relevé du 19/10, annexe). `maxPoolSize=3`.
- Schéma souple, aucune validation Mongo ; validation applicative (Pydantic partiel, fonctions « pures »).
- **Aucun index** sur des collections centrales : `reservations`, `subscriptions`, `discount_codes`, `offers`, `courses`, `users`, `chat_participants`, `payment_transactions` (seules quelques collections récentes en ont : `referral_passes`, `partners`, `creators`, `invitation_events`, `boosttribe_usage` TTL 7 j…).
- Live : Supabase Postgres séparé (voir LIVE_AUDIT).

## 5. Hébergement
- Coolify v4 sur VPS Hetzner **unique** `178.105.201.62` (7,7 Go RAM, swap utilisé), partagé avec : afroboosteur.com, formation, afroboost-live (front+back), spordate, spordate-rencontre, LiveKit+Egress+Redis, Supabase (×2), Studiio.
- Build : `Dockerfile` multi-étapes (Node 18 → build React ; Python 3.11 → API + statique). ~9 min. **Builds parfois tués** (mémoire) → « Failed » sans erreur de code ; redéploiement manuel nécessaire (vu le 15/10).
- Cloudflare devant (DNS, proxy, cache) ; preuve de déploiement = `sw.js`/`boot_id`, jamais le DNS.
- `vercel.json` = résidu (crons non exécutés).

## 6. Stockage
- Fichiers sur disque `MEDIA_DIR` (`/app/media`) servis par `/api/files/{id}/{nom}` (Range 206, cache 1 an), métadonnées `uploaded_files`, repli historique dans Mongo.
- Purge des orphelins après 48 h (balayage de toutes les collections) ; médias éphémères du chat (5 min de cycle).
- Cloudinary : héritage (lecture/purge seulement).
- ⚠️ La persistance du volume `MEDIA_DIR` entre redéploiements est à vérifier dans Coolify (volume monté ?).

## 7. Authentification
| Population | Mécanisme |
|---|---|
| Coach / partenaire / super-admin | `/api/auth/login` (bcrypt) → **JWT HS256 7 jours** (`JWT_SECRET`) en `Authorization: Bearer` ; Google OAuth historique retiré (410) |
| Membre | pas de compte : **code d'accès** + session d'espace (OTP e-mail 6 chiffres, 10 min, 5 essais ; jeton 30 j, `subscriber_sessions`) ou lien magique (`espace_liens_acces`) ; jeton `X-Subscriber-Token` (V296) |
| Invité Live | cookie `afb_live_guest` + jetons courts (`boosttribe-live-guest`) |
| Machines | webhooks signés (Stripe, Resend/Svix, Meta HMAC sous drapeau), `CRON_SECRET`, `AFRO_BT_SHARED_SECRET`, `AFRO_SPORDATE_SHARED_SECRET`, `STUDIIO_SERVICE_TOKEN`, `AFROBOOST_LIST_API_KEY` |

**Dette critique** : `require_auth()` (42 routes) et `_v263_authenticated_coach()` retombent **toujours** sur l'en-tête `X-User-Email` (repli « transitoire » V265 jamais retiré, non gouverné par `REQUIRE_COACH_JWT`). Les fonctions strictes existent (`_v309_require_coach_or_admin`, `_v311_coach_email_from_jwt`, `super_admin_signe`) et sont déjà utilisées par les modules récents.

## 8. Rôles
- **Super-admin** : liste en dur `SUPER_ADMIN_EMAILS = ["contact.artboost@gmail.com"]` (server.py:271, shared.py, copie l.21495, App.js:353). Règle SA-1 : un seul.
- **Coach** : présence dans `coaches` / `coach_auth`.
- **Partenaire** : coach avec `coach_id` propre (cloisonnement `get_coach_filter`, « mono-coach assumé » à plusieurs endroits).
- **Membre** : porteur d'un code / d'une session d'espace.
- **Staff** : `/staff/login` (scan).
- Constantes `super_admin/coach/user/partner` déclarées mais `get_user_role` ne renvoie que `super_admin` ou `user`.

## 9. Autorisations
- Modèle cible déjà présent dans le code récent : JWT signé + rôle relu en base + propriété (`coach_id`) + session d'espace pour le membre.
- Drapeaux de durcissement (`feature_flags`, document global) : `REQUIRE_COACH_JWT`, `SUPERADMIN_JWT_STRICT` (réputés ON en production d'après le code), `CHAT_READ_STRICT`, `UPLOADS_IDENTITE_STRICTE`, `META_WEBHOOK_SIGNATURE_ENABLED`, `RESERVATIONS_JWT_STRICT` (inerte). **États réels à relire en base.**
- Il n'existe **aucun droit par utilisateur et par fonctionnalité** (cf. Live).

## 10. Paiements
- Stripe Checkout (carte + TWINT), prix **recalculé serveur** (V428c/V429), abonnements récurrents (`invoice.*`, `customer.subscription.*`), Stripe Connect (partenaires), Boost payant.
- Webhooks : `/api/checkout/webhook/stripe` (refus sans secret ✅), **`/api/webhook/stripe` et `/api/stripe/webhook` acceptent un événement non signé si le secret n'est pas posé** ; branche `credit_purchase` sans idempotence. Présence réelle de `STRIPE_WEBHOOK_SECRET_CHECKOUT` / `STRIPE_WEBHOOK_SECRET` : **à vérifier dans Coolify**.
- Paiement manuel : `discount_codes`/`subscriptions` avec `montant_encaisse`, `origine_paiement`, `suivi_paiement`, échéances.
- PawaPay (drapeau OFF), CinetPay, PayPal (re-vérification serveur).

## 11. E-mails
- Resend, **point d'envoi unique** `api/resend_central.py` (journal `resend_envois`, quota quotidien et garde-fou `RESEND_DAILY_LIMIT`/`RESEND_DAILY_SAFETY_LIMIT`, réconciliation 10 min), webhooks de remise (`resend_evenements`), e-mails entrants (prospection).
- Désinscription RFC 8058, registre STOP (`subscribers`).
- EmailJS : héritage (`/emailjs-config` public).

## 12. WhatsApp
- Meta WhatsApp Cloud API : modèles approuvés, envoi campagne, webhook (`/webhook/whatsapp-meta`, signature HMAC sous drapeau), statuts (`whatsapp_statuts`), bot à menu (dormant), messagerie privée, vente assistée IA.
- Twilio : héritage, webhook non signé.

## 13. Vidéo / média
Upload morceaux 4 Mo (contourne les limites Cloudflare/origine), éditeur vidéo **dans le navigateur** (découpe, 16:9/9:16/1:1, miniature), aucun transcodage serveur.

## 14. Live / WebRTC
Module BoostTribe en iframe : LiveKit (vidéo), PeerJS (audio), Supabase Realtime, OpenAI ; jeton HS256 15 min émis par `/api/boosttribe/access`, débit `/api/boosttribe/consume`. Voir LIVE_AUDIT.

## 15. IA
| Usage | Modèle | Où |
|---|---|---|
| Générateur de réponses partenaires + relecture (AI_REPLY_CHECK) | **gpt-4.1** (`V621_MODELE`) | prospection |
| Chat widget, IA WhatsApp, suggestions campagnes, amélioration de texte | `ai_config.model` (défaut gpt-4o-mini) | chat, campagnes |
| Traduction | gpt-4o-mini ; gpt-4o pour langues peu dotées ; **`/translate` public** | chat, prospection |
| Vente WhatsApp | gpt-4o-mini | messagerie |
| Live (transcription, souffleur) | gpt-4o-transcribe / gpt-4o-mini(-transcribe) | BoostTribe |
Journal `ai_logs`. Pas de plafond de dépense global ; `/ai-test` public.

## 16. Schedulers (boucles dans le processus API)
| Boucle | Période | Rôle | Drapeau |
|---|---|---|---|
| Purge publications + orphelins | 1 h | disque, Cloudinary | — |
| Purge médias éphémères chat | 5 min | — | — |
| Planificateur de campagnes | 60 s | campagnes programmées | — |
| Échéances de tâches | 60 s | notifications | — |
| Synchronisation Google Calendar | 90 s | — | par événement |
| Rappels avant cours (RV3-B) | 1 h | rappels | `REMINDERS_SUBSCRIBERS_*` (DRY_RUN par défaut) |
| Relance essai J+3 | 1 h | e-mails | `P1_TRIAL_J3_*` |
| Essai non réservé | variable | e-mails | `P1E_*` |
| Auto-présence | 1 h | présences | `AUTO_PRESENCE_*` |
| Relances prospection J+3/J+7/J+14 | 1 h (8h-18h Zurich, semaine) | e-mails | `P3_RELANCE_*` |
| Réconciliation quota Resend | 10 min | quota | `RESEND_API_KEY` |
**Crons HTTP inactifs sur Coolify** (déclarés seulement dans `vercel.json`) : `/cron/check-subscription-renewal`, `/cron/post-course-feedback`, `/cron/rappel-renouvellement`, `/admin/check-expirations`. Risque : tâches attendues qui ne tournent pas.

## 17. Webhooks
Stripe (×4 routes), Resend (Svix ✅ fail-closed), Meta (HMAC sous drapeau), CinetPay/PawaPay/PayPal (re-vérification par API), Twilio (non signé, héritage), BoostTribe → `/boosttribe/consume` (JWT).

## 18. Services externes (noms de variables seulement)
Stripe (`STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_WEBHOOK_SECRET_CHECKOUT`) · Resend (`RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET`, `RESEND_DAILY_*`, `AFROBOOST_REPLY_TO*`, `P3_REPLY_DOMAIN`, `AFROBOOST_UNSUB_SECRET`) · Meta (`META_WHATSAPP_TOKEN`, `_PHONE_ID`, `_WABA_ID`, `_API_VERSION`, `_VERIFY_TOKEN`, `META_APP_SECRET`) · OpenAI (`OPENAI_API_KEY`) · Google (`GOOGLE_CONTACTS_CLIENT_ID/SECRET`, `GOOGLE_TOKEN_KEY`) · VAPID (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_CLAIMS_EMAIL`) · PostHog (`POSTHOG_*`) · PawaPay/CinetPay/PayPal · BoostTribe (`AFRO_BT_SHARED_SECRET`, `BOOSTTRIBE_EMBED_URL`) · Spordate (`AFRO_SPORDATE_SHARED_SECRET`, `SPORDATE_INTERNAL_URL`) · Studiio (`STUDIIO_URL`, `STUDIIO_SERVICE_TOKEN`) · interne (`MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `CRON_SECRET`, `MEDIA_DIR`, `FRONTEND_URL`, `CORS_ORIGINS`, `AFROBOOST_LIST_API_KEY`). Tiers sans clé : OSM Nominatim/OSRM, api.qrserver.com, dicebear, YouTube images. Au 19/10, `/api/debug/config` confirme la présence de : Stripe, OpenAI, Resend, JWT, Meta app secret.

## 19. APIs
661 routes, préfixe `/api`. Principaux préfixes : `/admin` (69), `/chat` (44), `/coach` (33), `/subscriber` (20), `/reservations` (15), `/campaigns` (15), `/pass` (15), `/prospect-inbound` (14), `/referral`, `/discount-codes`, `/offers`, `/courses`, `/calendar-events`, `/boosttribe`, `/live-guest`, `/spordate`, `/analytics`, `/stripe`, `/checkout`, `/pawapay`, `/cinetpay`. Pas de versionnement d'API ; contrat implicite avec le front.

## 20. Sécurité — état au 19/10 (vérifié dans le code, **non testé contre la production**)
| # | Constat | Gravité |
|---|---|---|
| S1 | Repli `X-User-Email` inconditionnel dans `require_auth` / `_v263` → usurpation du super-admin (adresse publique dans le bundle) sur 42 routes : `/platform-settings`, `/concept`, `/admin/reconcile-*`, `/admin/fix-*`, `/boosttribe/access` (Live gratuit + reprise de la session hôte), `/boosttribe/live-status`… | **P0** |
| S2 | `POST /api/custom-emojis/upload` : **aucune authentification**, nom de fichier pris dans la requête sans filtrage (`../`) → écriture de fichier arbitraire dans le conteneur | **P0** |
| S3 | `POST /api/admin/create-code` : le contrôle super-admin porte sur `body.admin_email` → n'importe qui crée des codes avec N séances (+ e-mail envoyé) | **P0** |
| S4 | `PUT /api/payment-links` et `PUT /api/payment-config` sur simple en-tête → détournement des liens de paiement (TWINT/Stripe/PayPal) ; `GET /api/payment-config/raw/{email}` public renverrait les clés (aujourd'hui **vides** en base, vérifié) | **P0** |
| S5 | Routes sans authentification : `PUT /config`, `PUT /coach-subscription`, `PUT /emailjs-config`, `POST /ai-test`, `DELETE /chat/emojis/{id}`, migrations publiques, `/admin/delete-history` et `/admin/change-identity` (confiance au corps) | P0/P1 |
| S6 | CRUD `/courses` et `/offers` : en-tête + aucun contrôle de propriété sur les cours (les offres sans `coach_id` sont modifiables par tous) | P1 |
| S7 | Webhooks Stripe non signés si secret absent ; `credit_purchase` sans idempotence | P1 (à vérifier) |
| S8 | `GET /api/subscriber/{code}` public (e-mail, nom, séances, présences) ; `/progress/*` (santé) sur le seul code ; pas de limite de débit | P1 |
| S9 | `/translate`, `/chat` publics consomment OpenAI sans plafond global ; `/auth/login` sans limitation | P1 |
| S10 | `/cron/reservation-reminders` public ; `CRON_SECRET` réputé absent sur Coolify | P2 |
| S11 | Pas de CSP ; QR codes générés chez un tiers avec le code d'accès dans l'URL | P2 |
| Live | L1 (secret LiveKit Cloud dans un dépôt public), L2 (= S1), L3/L4 (RLS Supabase, à vérifier) — voir LIVE_AUDIT | **P0** |
Points solides : espace membre B3, OTP, réservations MT-5, discount-codes, adhésions, invitations, ambassadeurs, analytics, webhook vitrine, Resend (Svix), CORS restreint, en-têtes de sécurité (HSTS, nosniff, DENY).

## 21. Confidentialité / données sensibles
Données personnelles : nom, e-mail, WhatsApp/téléphone, date de naissance, adresse (boutique), progression (données de santé), présences, paiements, photos, messages, transcriptions Live. Exigences (règle CLAUDE.md) : JWT + propriété pour toute route renvoyant ces données, pagination ≤ 50, aucune entrée utilisateur dans une regex Mongo. Écarts : S8. Pas de politique de rétention automatique (sauf médias éphémères, `boosttribe_usage` 7 j).

## 22. Performance
1 worker uvicorn, pool Mongo 3, collections centrales sans index, `/contacts/all` ≈ 3 s (optimisé), polling du chat (Socket.IO retiré), front lourd (bundle unique). Les relevés de performance existants sont ponctuels (aucun monitoring continu).

## 23. Disponibilité / fiabilité
VPS unique sans redondance ; ~1-2 % de 404 Traefik observés historiquement (conteneur absent) ; HEALTHCHECK `/healthz` ; mémoire serrée (builds tués). Aucun SLA externe.

## 24. Sauvegardes
Sauvegardes ponctuelles manuelles avant opérations sensibles (`~/afroboost-sauvegardes`). **Politique de sauvegarde Atlas (snapshots) et du disque `MEDIA_DIR` : à vérifier** — aucune trace dans le code.

## 25. Logs / monitoring
Logs texte (`logger`), journaux métiers en base (`resend_envois`, `ai_logs`, `campaign_errors`, `boosttribe_live_journal`, `seance_mouvements`, `whatsapp_statuts`), `boot_id`. **Pas** d'APM, d'alerting, ni de journal d'audit des actions admin. PostHog côté produit.

## 26. Cache / CDN
Cloudflare (purge manuelle après livraison), service worker (`CACHE_NAME`), `Cache-Control` 1 an sur `/api/files`, caches mémoire applicatifs (preuves V619, trajets).

## 27. Environnements
| Env | Réalité |
|---|---|
| Développement | local (`.env.local` pointe vers la base de **production** ⚠️) |
| Tests | bancs Python (≈ 314 fichiers `tests/`), Jest, Playwright local sur base séparée `afroboost_pw_test` (`tests/parcours/pile_locale.py`, Stripe/Resend factices) |
| Staging | **aucun** |
| Production | afroboost.com (Coolify) |

## 28. CI/CD
Aucune CI. `git push origin main` → webhook Coolify → build Docker (~9 min). Contrôles après livraison : `boot_id`, `sw.js`, `tests/nonregression.py` (exige un `ADMIN_JWT` du propriétaire ; sans lui, la suite salit la production).

## 29. Déploiement Coolify
App `afroboost-v11-dev:main-ae8xfe89eru6bpsxgsyukp4t` (projet afroboost.com). Variables d'environnement dans Coolify (pas Vercel). `REACT_APP_*` inlinées au build. Rollback : `git revert` + push. Builds simultanés sur le VPS = risque d'échec.

## 30. Décisions techniques
| Choix | Raison | Alternatives | Compromis |
|---|---|---|---|
| Monolithe FastAPI (`server.py`) + modules `routes/` | vitesse de livraison historique | microservices | fichier géant, revue difficile ; extraire progressivement par module |
| MongoDB Atlas sans schéma strict | souplesse | Postgres | doublons et incohérences ; compenser par index uniques et fonctions « canoniques » |
| Coolify sur un seul VPS | coût faible, maîtrise | Vercel/Render/k8s | point unique de défaillance, mémoire partagée |
| Membres sans compte (code + OTP) | friction minimale | comptes classiques | le code est une capacité : à protéger (sessions, limites de débit) |
| Live en service séparé (iframe) | isolation, réutilisation BoostTribe | intégration complète | deux bases, deux crédits ; cible : Afroboost autoritaire (option D) |
| Fichiers sur disque + `/api/files` | fin des limites Cloudinary | S3/R2 | dépend de la persistance du volume et des sauvegardes |
| Drapeaux en base (`feature_flags`) | activer/désactiver sans redéployer | variables d'env | état invisible dans le code ; à documenter et nettoyer |
| Point d'envoi e-mail unique (`resend_central`) | quotas, journal, idempotence | appels directs | à généraliser à WhatsApp |
| Pas de CI | rapidité | GitHub Actions | régressions découvertes en production ; ajouter une CI légère (tests rapides) |
| 1 worker uvicorn | simplicité, caches mémoire cohérents | plusieurs workers | débit limité ; à revoir avec un stockage partagé des limites |

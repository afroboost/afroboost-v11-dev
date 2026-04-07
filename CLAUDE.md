# CLAUDE.md — Guide de Contexte Permanent Afroboost

> Dernière mise à jour : 7 avril 2026 — v162m
> Ce fichier sert de référence exhaustive pour toute intervention sur le projet.

---

## 1. Vue d'ensemble du projet

**Afroboost** est une plateforme SaaS de fitness immersif (cardio + danse afrobeat + casques audio) opérant en Suisse. Elle combine :
- Un site vitrine public avec réservation de cours et achat d'abonnements
- Un chat IA conversationnel (onboarding, réservation via chat, support)
- Un dashboard coach complet (CRM, conversations, campagnes, codes promo, réservations)
- Un panel Super Admin
- Une PWA installable (Android/iOS)
- Des tunnels de vente intelligents (Liens Intelligents)

**URL production** : https://afroboost.com
**Hébergement** : Vercel (serverless)
**Base de données** : MongoDB Atlas (cluster M0, base `afroboost_db`)

---

## 2. Stack Technique

### Backend (API serverless)
| Composant | Version | Rôle |
|-----------|---------|------|
| Python | 3.11+ | Runtime Vercel |
| FastAPI | 0.110.1 | Framework API REST |
| Motor | 3.3.1 | Driver MongoDB async |
| PyMongo | 4.5.0 | Driver MongoDB sync (sous Motor) |
| Pydantic | 2.12.5 | Validation des modèles |
| Stripe | 14.1.0 | Paiements (CHF, TWINT, carte) |
| OpenAI | 1.99.9 | Chat IA, suggestions, génération |
| Resend | 2.19.0 | Emails transactionnels |
| PyWebPush | 2.2.0 | Notifications push web |
| PyJWT | 2.10.1 | Authentification JWT |
| Pillow | 12.1.0 | Traitement images profil |

### Frontend
| Composant | Version | Rôle |
|-----------|---------|------|
| React | 19.0.0 | UI framework |
| Create React App | 5.0.1 | Build tool (via CRACO) |
| CRACO | 7.1.0 | Override CRA config |
| TailwindCSS | 3.4.17 | Styling utilitaire |
| Radix UI | dernière | Composants UI accessibles |
| Axios | 1.8.4 | HTTP client |
| Socket.IO Client | 4.8.3 | WebSocket (conversations temps réel) |
| Recharts | 3.6.0 | Graphiques dashboard |
| html5-qrcode | 2.3.8 | Scanner QR caméra |
| qrcode.react | 4.2.0 | Génération QR codes |

### Infrastructure
| Service | Usage |
|---------|-------|
| Vercel | Hébergement + serverless functions + crons |
| MongoDB Atlas | Base de données (cluster M0, max 500 connexions) |
| GitHub | Code source (`afroboost/afroboost-v11-dev`) |
| Resend | Envoi emails (@afroboosteur.com) |
| Stripe | Paiements CHF (carte + TWINT) |
| OpenAI API | Chat IA, suggestions coach, génération tunnel |
| Twilio | SMS (non actif, regulatory bundle en cours) |
| Meta WhatsApp Business API | Campagnes WhatsApp (en cours de setup) |
| PostHog | Analytics |

---

## 3. Architecture des Dossiers

```
afroboost-v11-dev/
├── api/                          # Backend Python (Vercel serverless)
│   ├── index.py                  # Point d'entrée Vercel → importe fastapi_app
│   ├── server.py                 # Fichier principal (~11000 lignes) : modèles, ~198 endpoints, logique métier
│   ├── scheduler_engine.py       # Moteur de campagnes programmées
│   ├── requirements.txt          # Dépendances Python
│   └── routes/                   # Routes modulaires extraites
│       ├── auth_routes.py        # JWT auth, login, register, password reset
│       ├── reservation_routes.py # CRUD réservations, QR scan, validation
│       ├── coach_routes.py       # Gestion coachs/partenaires
│       ├── promo_routes.py       # Codes promo, discount codes
│       ├── stripe_routes.py      # Webhook Stripe, checkout
│       ├── checkout_routes.py    # Sessions de paiement
│       ├── cinetpay_routes.py    # Paiement CinetPay (Afrique)
│       ├── campaign_routes.py    # Campagnes marketing
│       ├── payment_config_routes.py # Config paiement multi-vendeurs
│       ├── contact_categories_routes.py # Catégories CRM
│       └── shared.py             # Helpers partagés
├── frontend/                     # React CRA + CRACO
│   ├── package.json
│   ├── craco.config.js           # Override webpack, ESLint, aliases
│   ├── public/
│   │   ├── index.html            # HTML avec SW registration, PWA capture, PostHog
│   │   ├── manifest.json         # PWA manifest
│   │   ├── sw.js                 # Service Worker v162m (ES5 pur)
│   │   ├── logo192.png           # Icône PWA 192x192
│   │   ├── logo512.png           # Icône PWA 512x512
│   │   ├── logo192-maskable.png  # Icône maskable (Android)
│   │   └── logo512-maskable.png  # Icône maskable 512
│   └── src/
│       ├── App.js                # Composant racine (~5900 lignes) : routing, PWA install, vitrine
│       ├── App.css               # Styles globaux
│       ├── components/
│       │   ├── ChatWidget.js     # Widget chat IA + mini-dashboard coach (~7700 lignes)
│       │   ├── CoachDashboard.js # Dashboard complet coach (~6900 lignes)
│       │   ├── CoachLoginModal.js # Modal connexion coach
│       │   ├── SuperAdminPanel.js # Panel super admin
│       │   ├── PartnersCarousel.js # Carrousel partenaires vitrine
│       │   ├── CoachVitrine.js   # Page vitrine coach
│       │   ├── VitrineCheckout.js # Checkout vitrine
│       │   ├── AudioPlayer.js    # Lecteur audio
│       │   ├── EmojiPicker.js    # Sélecteur emoji custom
│       │   ├── chat/             # Sous-composants chat
│       │   │   ├── OnboardingTunnel.js  # Tunnel d'onboarding (Liens Intelligents)
│       │   │   ├── SubscriberForm.js    # Formulaire abonné
│       │   │   ├── BookingPanel.js      # Panel de réservation
│       │   │   ├── ChatBubbles.js       # Bulles de conversation
│       │   │   └── PrivateChatView.js   # Vue conversation privée
│       │   ├── coach/            # Sous-composants coach dashboard
│       │   │   ├── SmartLinksSection.js  # Section Liens Intelligents
│       │   │   ├── SmartLinkCard.js      # Carte de lien
│       │   │   ├── CampaignManager.js    # Gestion campagnes
│       │   │   ├── ReservationTab.js     # Onglet réservations
│       │   │   └── CRMSection.js         # Section CRM contacts
│       │   ├── dashboard/        # Sous-composants dashboard
│       │   │   ├── ContactsManager.js    # Gestion contacts
│       │   │   ├── OffersManager.js      # Gestion offres
│       │   │   ├── CoursesManager.js     # Gestion cours
│       │   │   ├── PromoCodesTab.js      # Codes promo
│       │   │   ├── PaymentConfigTab.js   # Config paiement
│       │   │   └── ConceptEditor.js      # Éditeur concept/branding
│       │   └── ui/               # Composants Radix UI / shadcn
│       ├── config/               # Configuration
│       │   ├── constants.js      # Constantes globales
│       │   └── index.js
│       ├── services/             # Services métier
│       │   ├── whatsappService.js    # API WhatsApp
│       │   ├── aiResponseService.js  # Gestion réponses IA
│       │   ├── emailService.js       # Email (EmailJS legacy)
│       │   ├── notificationService.js # Notifications
│       │   ├── pushNotificationService.js # Push web
│       │   └── twilioService.js      # Twilio SMS
│       ├── hooks/                # Hooks React custom
│       │   ├── useDataCache.js   # Cache invalidation
│       │   └── use-toast.js      # Notifications toast
│       ├── utils/                # Utilitaires
│       │   ├── i18n.js           # Internationalisation
│       │   ├── contactParser.js  # Parsing contacts
│       │   └── clipboard.js      # Copie presse-papiers
│       └── lib/                  # Libs partagées (shadcn utils)
├── vercel.json                   # Config Vercel : build, rewrites, crons, headers
├── memory/                       # Notes de développement
└── tests/                        # Tests backend
```

---

## 4. Architecture Technique

### Pattern de déploiement Vercel
```
Requête → Vercel Edge → vercel.json rewrites
  ├── /api/*  → api/index.py → FastAPI (server.py)
  └── /*      → frontend/build/index.html (SPA React)
```

- **Serverless function unique** : `api/index.py` (max 60s, 1024MB RAM)
- **Build** : `cd frontend && npm install --legacy-peer-deps && CI=false npx craco build`
- **Output** : `frontend/build/`

### Crons Vercel
| Schedule | Endpoint | Rôle |
|----------|----------|------|
| `0 7 * * *` | `/api/cron/check-campaigns` | Vérifier campagnes programmées |
| `0 8 * * *` | `/api/admin/check-expirations` | Vérifier expirations abonnements |
| `0 10 * * *` | `/api/cron/post-course-feedback` | Demander avis post-séance |

### Authentification (double système)
1. **JWT signé** (prioritaire) : `Authorization: Bearer <token>` — stocké dans `localStorage('afroboost_jwt')`
2. **Header email** (fallback legacy) : `X-User-Email: <email>` — injecté par intercepteur Axios global

### Base de données MongoDB

**57 collections** identifiées. Les principales :

| Collection | Rôle |
|------------|------|
| `users` | Contacts / CRM |
| `chat_participants` | Participants chat (avec source, coach_id) |
| `chat_sessions` | Sessions de conversation (liens intelligents inclus) |
| `chat_messages` | Messages de conversation |
| `courses` | Cours planifiés |
| `offers` | Offres commerciales |
| `reservations` | Réservations de cours/produits |
| `subscriptions` | Abonnements auto-créés après paiement Stripe |
| `discount_codes` | Codes promo / codes d'accès (AFR-XXXXXX) |
| `coaches` | Comptes coachs/partenaires |
| `coach_auth` | Auth coach (email/password) |
| `coach_profiles` | Profils coach (photo, date de naissance) |
| `coach_subscriptions` | Abonnements coach à la plateforme |
| `campaigns` | Campagnes marketing (email, WhatsApp, push) |
| `payment_transactions` | Transactions Stripe |
| `payment_links` | Config liens de paiement |
| `platform_settings` | Paramètres plateforme (staff code, etc.) |
| `concept` | Branding/concept du site |
| `uploaded_files` | Fichiers uploadés (images, audio) |
| `leads` | Leads collectés via tunnels |
| `push_subscriptions` | Souscriptions push web |
| `ai_config` | Configuration IA (prompt système, etc.) |

### Isolation multi-tenant (coach_id)
- Chaque enregistrement porte un `coach_id` pour isoler les données par coach
- Les Super Admins voient tout (`is_super_admin()` → filtre vide `{}`)
- Les coachs ne voient que leurs données (`{"coach_id": email}`)
- Fallback : `DEFAULT_COACH_ID = "bassi_default"` pour les données pré-existantes

---

## 5. Variables d'Environnement

### Backend (Vercel Environment Variables)

| Variable | Obligatoire | Description |
|----------|:-----------:|-------------|
| `MONGO_URL` | ✅ | URI MongoDB Atlas |
| `DB_NAME` | ❌ | Nom de la base (défaut: `afroboost_db`) |
| `STRIPE_SECRET_KEY` | ✅ | Clé secrète Stripe |
| `OPENAI_API_KEY` | ✅ | Clé API OpenAI (chat IA) |
| `RESEND_API_KEY` | ✅ | Clé API Resend (emails) |
| `VAPID_PUBLIC_KEY` | ❌ | Clé publique VAPID (push) |
| `VAPID_PRIVATE_KEY` | ❌ | Clé privée VAPID (push) |
| `VAPID_CLAIMS_EMAIL` | ❌ | Email VAPID (défaut: contact@afroboost.ch) |
| `TWILIO_ACCOUNT_SID` | ❌ | SID Twilio (SMS, non actif) |
| `TWILIO_AUTH_TOKEN` | ❌ | Token Twilio |
| `TWILIO_FROM_NUMBER` | ❌ | Numéro Twilio |
| `FRONTEND_URL` | ❌ | URL frontend (défaut: https://afroboost.com) |
| `CORS_ORIGINS` | ❌ | Origines CORS autorisées |
| `GOOGLE_CONTACTS_CLIENT_ID` | ❌ | OAuth Google Contacts |
| `GOOGLE_CONTACTS_CLIENT_SECRET` | ❌ | Secret OAuth Google |
| `AUTHORIZED_COACH_EMAIL` | ❌ | Email coach autorisé (défaut: contact.artboost@gmail.com) |
| `VERCEL_URL` | ❌ | URL Vercel auto-injectée |

### Frontend (Build-time)

| Variable | Description |
|----------|-------------|
| `REACT_APP_BACKEND_URL` | URL backend (vide en prod = même domaine) |
| `REACT_APP_API_URL` | Alternative API URL (certains composants) |

### Constantes hardcodées critiques

```python
COACH_EMAIL = "contact.artboost@gmail.com"
SUPER_ADMIN_EMAILS = ["contact.artboost@gmail.com", "afroboost.bassi@gmail.com"]
DEFAULT_COACH_ID = "bassi_default"
```

---

## 6. Intégrations API tierces

| Service | Usage | Endpoint/Config |
|---------|-------|-----------------|
| **Stripe** | Paiements (carte + TWINT CHF) | Webhook: `POST /api/webhook/stripe` |
| **OpenAI** | Chat IA, suggestions, tunnels | GPT-4o-mini, streaming |
| **Resend** | Emails transactionnels | From: `notifications@afroboosteur.com` |
| **Twilio** | SMS (en setup) | Webhook status: `POST /api/webhooks/twilio/status` |
| **Meta WhatsApp Business** | Campagnes WhatsApp (en setup) | Phone ID: `1026143103920031` |
| **CinetPay** | Paiements Afrique | Routes dédiées |
| **Google People API** | Import contacts Google | OAuth2 flow |
| **PostHog** | Analytics | Script dans index.html |
| **QR Server API** | Génération QR codes | `api.qrserver.com` |

---

## 7. Commandes de Workflow

### Installation locale
```bash
# Frontend
cd frontend
npm install --legacy-peer-deps

# Backend (pour tests locaux)
pip install -r api/requirements.txt
```

### Développement
```bash
cd frontend
npm start              # ou: npx craco start
```

### Build production
```bash
cd frontend
CI=false npx craco build
```
> `CI=false` est obligatoire : désactive le traitement des warnings comme erreurs.

### Tests
```bash
cd frontend && npx craco test     # Tests React
python backend_test.py            # Tests backend (racine)
```

### Déploiement
```bash
git add <fichiers>
git commit -m "vXXX: description"
git push origin main              # Vercel auto-deploy sur push main
```
> Vercel build automatique : ~1min. Vérifier sur le dashboard Vercel.

### Git (depuis VM Claude)
```bash
# Push via PAT (depuis environnement sans git config)
git push https://<PAT>@github.com/afroboost/afroboost-v11-dev.git main
```

---

## 8. Conventions de Code

### Règles CRITIQUES — Ne jamais enfreindre

1. **ES5 obligatoire dans ChatWidget.js** : `var`, `function()`, `React.createElement()` — PAS de `const`, `let`, arrow functions, template literals. Raison : compatibilité Samsung Internet / anciens Android.

2. **Ne jamais supprimer de données** : Le site est en production avec des abonnés actifs. Toute modification doit préserver les données existantes.

3. **Ne pas toucher** :
   - Les 53 routes JWT auth existantes
   - Le Service Worker V140 (sauf bumps de version)
   - Le système de paiement Stripe (webhook critique)
   - Les fonctionnalités qui marchent déjà

4. **Ne pas casser le paiement, les réservations, ni les conversations.**

### Style Python (Backend)
- Type hints partout (Pydantic models)
- Async/await pour toutes les opérations DB
- Logging structuré : `logger.info(f"[PREFIXE] message")`
- Gestion d'erreurs : try/except avec logging, jamais de crash silencieux
- Emails envoyés via `asyncio.to_thread(resend.Emails.send, ...)` (non-bloquant)

### Style JavaScript (Frontend)
- **ChatWidget.js** : ES5 strict (`var`, `function()`, `React.createElement`)
- **Autres composants** : ES6+ autorisé (hooks, JSX, arrow functions)
- Axios avec intercepteur global pour auth (JWT + X-User-Email)
- État géré via `useState`/`useEffect` (pas de Redux/Zustand)
- Composants UI : Radix UI + TailwindCSS

### Conventions de commit
```
vXXX: Description courte

- Détail 1
- Détail 2

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

### Conventions de nommage
- Collections MongoDB : `snake_case` (ex: `chat_sessions`, `discount_codes`)
- Endpoints API : `kebab-case` (ex: `/dashboard/all-transactions`)
- Composants React : `PascalCase` (ex: `ChatWidget`, `CoachDashboard`)
- Fichiers routes : `snake_case_routes.py`

---

## 9. Fonctionnalités Clés

### Visiteur / Abonné
- Parcourir les offres et cours sur la vitrine
- Réserver un cours (via formulaire ou via chat)
- Payer par Stripe (carte + TWINT)
- Recevoir un code d'accès (AFR-XXXXXX) + QR code par email
- Consulter ses séances restantes via code
- Chatter avec l'IA Afroboost (onboarding, réservation, questions)
- Installer l'app en PWA
- Scanner son QR code à l'entrée du cours

### Coach / Partenaire
- Dashboard complet : Conversations, Transactions, Scanner QR, Gestion
- Créer/gérer des Liens Intelligents (tunnels de vente avec questions personnalisées)
- Gérer les offres, cours, codes promo
- Envoyer des campagnes (email, push, WhatsApp)
- Voir et répondre aux conversations (mode IA ou mode humain)
- Exporter les contacts (CSV)
- Gérer le branding/concept du site
- Uploader photo de profil, audio tracks
- Accès staff limité (Réservations + Scanner uniquement) avec code `STAFF2026`

### Super Admin
- Vue globale de toutes les données (tous coachs)
- Panel admin dédié
- Gestion des paramètres plateforme
- Notifications email sur chaque transaction

---

## 10. Points d'Attention et Pièges Connus

### MongoDB Atlas M0
- **Max 500 connexions** : Pool limité à `maxPoolSize=3` dans le driver
- Les serverless functions Vercel créent une connexion par cold start

### Fichiers volumineux
- `server.py` : ~11000 lignes — le cœur du backend
- `ChatWidget.js` : ~7700 lignes (ES5 !) — le chat + mini-dashboard
- `CoachDashboard.js` : ~6900 lignes — dashboard complet
- `App.js` : ~5900 lignes — vitrine + routing

### Service Worker
- Version actuelle : `v162m` (CACHE_NAME: `afroboost-v162m`)
- ES5 pur (pas de const/let/arrow)
- `manifest.json` et icônes PWA ne sont PAS interceptés par le SW
- Push notifications désactivées dans le SW (cassaient WebAPK)

### Encodage UTF-8
- Les fichiers Python peuvent contenir des caractères UTF-8 mal encodés (double-encoding historique)
- Utiliser `open(file, 'r', encoding='utf-8')` systématiquement
- Le `ContactsManager.js` avait un bug de double-encoding corrigé en v162

### Vercel Specific
- Timeout serverless : 60 secondes max
- Pas de filesystem persistant (les uploads vont dans MongoDB)
- Les rewrites `/api/(.*)` → `api/index.py` catchent toutes les requêtes API
- Les crons Vercel nécessitent un plan Pro pour fonctionner

---

## 11. Questions Ouvertes / Ambiguïtés

1. **Socket.IO** : Le client est importé dans le frontend (`socket.io-client`) mais le backend Vercel serverless ne supporte pas les WebSockets persistants. Le chat fonctionne en mode polling HTTP.

2. **Backend dossier `/backend/`** : Un dossier `backend/` existe à la racine avec son propre `requirements.txt` — c'est l'ancien backend standalone (avant migration Vercel). Il n'est PAS utilisé en production. Seul `/api/` est actif.

3. **EmailJS** : Présent dans les dépendances (`@emailjs/browser`) — service legacy, remplacé par Resend côté backend. Peut être retiré.

4. **Twilio** : Compte configuré mais regulatory bundle suisse incomplet. SMS non fonctionnel en production.

5. **WhatsApp Business API** : En cours de setup. Numéro vérifié (+41 76 763 99 28) mais token permanent non créé (bloqué par rate limit Meta). Mode sandbox uniquement.

6. **next-themes** : Présent dans package.json mais le projet n'utilise PAS Next.js (c'est CRA+CRACO). Dépendance probablement inutile.

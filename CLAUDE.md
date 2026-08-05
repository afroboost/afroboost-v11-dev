# CLAUDE.md — Instructions for AI Assistants

## Project Overview
Afroboost is a SaaS fitness platform built on FastAPI + React, deployed on Coolify (Hetzner VPS) — NOT Vercel, see the « Déploiement » section. Coach Bassi (owner) is based in Switzerland and is NOT a developer — explain things simply, step by step.

## Tech Stack
- Backend: FastAPI (Python 3.11), Motor (async MongoDB), single file `api/server.py` (16,700+ lines)
- Frontend: React 19, TailwindCSS, Radix UI/shadcn, CRACO
- Database: MongoDB Atlas (49 collections)
- Deploy: Coolify sur VPS Hetzner (conteneur Docker, uvicorn). `vercel.json` est un résidu.
- Payments: Stripe Connect + CinetPay
- Messaging: WhatsApp Business API (Meta Cloud API)
- Notifications: WebPush + Resend email
- AI: OpenAI GPT

## Critical Files
- `api/server.py` — Main backend (16,700 lines). Be careful with edits, always search for the right line numbers.
- `frontend/src/components/CoachDashboard.js` — Main dashboard (7,200 lines)
- `frontend/src/components/ChatWidget.js` — Chat + mini-dashboard (9,400 lines, ES5 only)
- `frontend/src/App.js` — Vitrine + routing (8,100 lines)
- `vercel.json` — Deployment config + cron jobs
- `api/routes/` — Modular route files (13 files)

## Key Conventions
- Version comments: changes are marked with `# V{number}: description` (e.g., `# V171.1: Fix template cleaning`)
- Coach Bassi speaks French — respond in French
- The brand color is #D91CD2 (magenta/pink)
- Backend and frontend are in the same repo (monorepo)
- All API routes start with `/api/` or are under router prefixes
- **ALL icons must be SVG inline** — never use emoji Unicode characters (🕐, 📍, 👥, ⏱, etc.) as icons in the UI. Use inline `<svg>` elements with `stroke="currentColor"` instead. This applies to ALL components (App.js, CoachVitrine.js, OfferCard.js, CoachDashboard.js, OfferWizard.js, etc.).

## 🎨 RÈGLE ABSOLUE — COULEURS PERSONNALISÉES DU COACH (erreur récurrente, signalée plusieurs fois)

> **Quand le coach/admin personnalise ses couleurs (page « Ma Vitrine »), ces couleurs doivent s'appliquer PARTOUT sur sa vitrine — sans exception.**

C'est l'erreur la plus répétée du projet. À vérifier SYSTÉMATIQUEMENT avant chaque commit touchant l'UI :

1. **JAMAIS de couleur codée en dur** dans un composant. Interdit : `#a855f7`, `#8B5CF6`, `#9333ea`, `#D91CD2` écrits directement dans un `style` ou un `className`.
   **Toujours** : `var(--primary-color, #D91CD2)`, `var(--secondary-color, …)`, `rgba(var(--primary-rgb, 217, 28, 210), …)`.
   Le `#D91CD2` n'est qu'une VALEUR DE SECOURS dans le `var()`, jamais une valeur directe.

2. **Portée = TOUTE la vitrine**, y compris les zones souvent oubliées :
   - ChatWidget dans ses TROIS espaces : visiteur, abonné, coach partenaire / coach-admin
   - Tous les boutons ronds de la barre de saisie (emoji, calendrier, « ? », globe) — **même couleur, même taille, même opacité dans les trois espaces**
   - Modales (publication, réservation, profil, staff), panneaux, badges, compteurs
   - Publications, offres, boutique, page « Devenir partenaire », sélecteurs de langue
   - États : survol, focus, actif, désactivé, chargement

3. **Cohérence inter-espaces** : un même composant (ex. le bouton calendrier) doit être VISUELLEMENT IDENTIQUE côté abonné et côté coach. Pas de variante isolée.

4. **Pas de FOUC** : au chargement, la couleur personnalisée doit être appliquée dès la première milliseconde (lecture depuis le localStorage dans un script inline en `<head>`), jamais après un flash de la couleur par défaut.

5. **Avant chaque commit UI** : rechercher les hex codés en dur (`#[0-9a-fA-F]{6}`) dans les fichiers modifiés et vérifier que chacun est bien une valeur de secours dans un `var()`, et non une couleur imposée.

## 🛡️ RÈGLE ABSOLUE — TESTS DE NON-RÉGRESSION AVANT TOUTE LIVRAISON

Le site est en PRODUCTION avec de vrais clients. Depuis V291, chaque version a cassé
quelque chose. Pour que cela n'arrive plus :

1. Après CHAQUE déploiement, lancer `python tests/nonregression.py` contre la
   production et COLLER le tableau de résultats dans le bilan.
2. Aucune version n'est « terminée » tant que tous les tests ne sont pas au vert.
3. Interdit de dire « à vérifier de ton côté » pour un parcours couvert par la suite.
4. Tout nouveau correctif ajoute son test — la couverture ne recule jamais.
5. Un échec sur un parcours non lié au correctif = RÉGRESSION : corriger avant de livrer.

## 🚦 RÈGLE ABSOLUE — « ÉCRIT » NE VEUT PAS DIRE « LIVRÉ »

Aucun correctif n'est annoncé comme livré tant que : (1) le déploiement Coolify
affiche `Finished` (le build peut échouer — OOM Terser, cf. V309b — sans que le code
soit en faute), (2) le cache Cloudflare est purgé, (3) la réponse RÉELLE de la
production déployée est collée dans le rapport. Un `git push` réussi ne prouve RIEN.
Toujours re-tester l'endpoint déployé (curl) avant d'annoncer un résultat.

## 🔑 RÈGLE ABSOLUE — NE JAMAIS DURCIR UNE AUTH SANS PROUVER QUE LE CHEMIN LÉGITIME MARCHE (V310c)

Avant d'exiger un jeton (JWT) sur une route, PROUVER par un appel réel que le
propriétaire garde l'accès. Sa parole « je me suis reconnecté » NE SUFFIT PAS.
Preuve obligatoire, sur LA MÊME route, AVANT de livrer :
- `200` **avec** le jeton légitime, ET `403` **sans**.

Contexte de l'incident (V310 FIX 1, revert `0e12578`) : le dashboard du
propriétaire s'authentifie via le **repli super-admin X-User-Email** du ChatWidget
(`afroboost_identity` / `afroboost_admin_persist`) — ce chemin **n'appelle jamais
`/auth/login`, donc n'émet AUCUN JWT**. Passer les routes de lecture en JWT-strict a
renvoyé 403 → tableau de bord VIDE. Tests #15/#32 étaient en SKIP faute de jeton :
un SKIP sur le parcours légitime d'un durcissement = interdiction de livrer.
Corollaire : pour sécuriser vraiment ces routes, il faut D'ABORD garantir que
l'entrée coach du dashboard émet un JWT (via `/auth/login`), le vérifier, PUIS durcir.

## 🔐 RÈGLE ABSOLUE — AUCUNE DONNÉE PERSONNELLE SANS AUTHENTIFICATION

Toute route renvoyant `email`, `whatsapp`, `phone`, `birthday`, un code d'abonnement,
des notes ou un historique doit vérifier une identité serveur (JWT) et renvoyer 403
sinon. Le rôle coach/admin ne se décide JAMAIS côté navigateur. Toute liste est
paginée (50 max) et limitée en débit. Aucune entrée utilisateur n'entre dans une
regex MongoDB (utiliser `re.escape` ou une égalité stricte). Toute nouvelle route est
testée SANS authentification avant livraison (parcours 21-24 de tests/nonregression.py).

## ⚡ RÈGLE ABSOLUE — JAMAIS DE BOUCLE D'APPELS API

Un `setState` avec un objet NEUF alors que les données sont identiques relance tous
les effets qui en dépendent -> boucle d'appels -> serveur saturé -> 502 en production
(arrivé en V305). Avant tout `setState` d'objet : comparer et renvoyer `prev` si rien
n'a changé. Faire dépendre les `useEffect` de valeurs primitives, jamais d'un objet.

## Known Gotchas
1. WhatsApp template variables CANNOT contain: emojis, full URLs (https://...), Unicode bold chars. Domain names without protocol are OK.
2. MongoDB queries on large groups (800+ members) must use batch `$in` queries, NOT individual `find_one()` calls
3. Historiquement contraint par le timeout 60s de Vercel — le code en garde les optimisations (utile de toute façon)
4. Frontend uses `--legacy-peer-deps` for npm install
5. `re_tpl` is a pre-compiled regex module used in template cleaning — search for its definition before modifying regex patterns

## Environment Variables
Required: MONGO_URL, STRIPE_SECRET_KEY, RESEND_API_KEY, META_WHATSAPP_TOKEN, META_WHATSAPP_PHONE_ID, META_WHATSAPP_VERIFY_TOKEN, OPENAI_API_KEY, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, JWT_SECRET

## Deployment
- Frontend + API : auto-deploy sur `git push origin main` (voir « Déploiement » ci-dessous pour l'hébergeur RÉEL)
- Build : `Dockerfile` à la racine (multi-étapes React + FastAPI)
- API entry: `api/index.py` → imports `api/server.py`

## Déploiement — les TROIS sites (V264b)

> Trois sites distincts coexistent. **Les trois sont sur le MÊME serveur
> Hetzner/Coolify** (`178.105.201.62`).
> Vérifications faites le 24 juillet 2026 (`dig`, `curl` avec en-tête `Host`,
> comparaison des hachages de bundle).

### ⚠️ Ne PAS se fier au DNS ni aux traces Vercel
afroboost.com est derrière le **proxy Cloudflare**. Trois pièges, tous
rencontrés :
1. `dig afroboost.com` renvoie des IP **Cloudflare** (104.21.x / 172.67.x) —
   jamais l'origine. On ne peut RIEN en déduire sur l'hébergeur.
2. Cloudflare réécrit l'en-tête `server:` en `cloudflare`, masquant le
   `Server: uvicorn` de l'origine.
3. Le dépôt contient un `vercel.json` et le DNS des TXT `_vercel`
   (`vc-domain-verify`) : ce sont des **RÉSIDUS d'une ancienne installation
   Vercel**, plus utilisés. `afroboost-v11-dev-pm7l.vercel.app` existe encore
   mais sert un bundle PÉRIMÉ, différent de la production.

**Le seul test fiable** — interroger l'origine directement en forçant l'hôte,
puis comparer au bundle servi en production :
```bash
curl -sI -H "Host: afroboost.com" http://178.105.201.62/api/debug/config
#   -> Server: uvicorn   (= FastAPI dans un conteneur, pas Vercel)
curl -s -H "Host: afroboost.com" http://178.105.201.62/ | grep -o 'static/js/main\.[0-9a-f]*\.js'
curl -s https://afroboost.com/ | grep -o 'static/js/main\.[0-9a-f]*\.js'
#   -> hachages IDENTIQUES = c'est bien cette machine qui sert le site
```
(En HTTPS direct sur l'IP, `curl` échoue avec l'erreur 60 : le certificat ne
couvre pas ce nom, Cloudflare parlant à l'origine en HTTP.)

### afroboost.com — plateforme fitness / ChatWidget (CE DÉPÔT)
- **Hébergement** : **Coolify sur VPS Hetzner `178.105.201.62`**, conteneur
  Docker servi par **uvicorn**. PAS Vercel — voir l'encadré ci-dessus.
- **Dépôt** : `afroboost/afroboost-v11-dev`, branche `main`
- **Build** : le `Dockerfile` à la racine (multi-étapes : build React puis
  service FastAPI). C'est LUI qui construit, pas `vercel.json`.
- **Stack** : React (Craco) + FastAPI
- **Base** : MongoDB Atlas, DB `promo-credits-lab`
- **Médias** : Cloudinary (cloud `dtm0r7hwq`, preset unsigned `afroboost`)
- **DNS** : Cloudflare (compte bassicustomshoes@gmail.com), proxy actif
- **Déployer** : `git push origin main` → Coolify rebuild automatique (webhook),
  **~4 min** (build du Dockerfile, pas un simple upload). Attendre la fin avant
  de conclure « pas déployé » : le build prend du temps.
- **Cache navigateur / PWA** : le Service Worker (`frontend/public/sw.js`,
  `CACHE_NAME`) peut servir un ancien bundle même après un déploiement réussi.
  Si un changement front n'apparaît pas alors que le bundle en ligne le contient
  (`curl -s https://afroboost.com/ | grep -o 'static/js/main.[0-9a-f]*\.js'`),
  BUMPER `CACHE_NAME` dans sw.js force tous les clients à se rafraîchir.
- **Rollback** : `git revert <hash> && git push origin main`
- **Variables d'env** : **Coolify** → application afroboost → Environment
  Variables. PAS Vercel : y ajouter une variable n'a AUCUN effet.
- **Vérifier ce qui est en ligne** : `curl -s https://afroboost.com/api/debug/config`

### ⚠️ « 404 page not found » intermittent sur afroboost.com (V320)

Symptôme : le site renvoie quelques secondes un **404 dont le corps est
`404 page not found`**. Ce corps est la page d'erreur par défaut de **Traefik**
(le proxy de Coolify) : la réponse ne vient PAS de l'application. Preuve
structurelle : le catch-all SPA (`api/server.py`, `_serve_spa`) renvoie
`index.html` **inconditionnellement** — il lui est impossible de produire un 404
sur `/`. Un 404 sur `/` signifie donc : **aucun conteneur sain pour cette app**.

**Le test qui tranche** (à refaire tel quel, il élimine 3 suspects d'un coup) —
au moment d'un échec, interroger l'origine EN DIRECT et les autres sites :
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://afroboost.com/                      # via Cloudflare
curl -s -H "Host: afroboost.com" -o /dev/null -w "%{http_code}\n" http://178.105.201.62/   # origine directe
curl -s -o /dev/null -w "%{http_code}\n" https://afroboosteur.com/                   # autre app, même serveur
```
Mesure réelle du 27 juillet 2026 : `viaCF=404 | origine=404 | afroboosteur=200`.
-> Cloudflare, le réseau et Traefik sont INNOCENTÉS ; seul le conteneur afroboost
est absent à cet instant. Fréquence observée : ~1 à 2 % des requêtes, **y compris
hors déploiement** (donc : redémarrages du conteneur, piste OOM).

**Sondes disponibles** :
- `/healthz` — vivacité PURE, **sans Mongo** (V320). Cible du `HEALTHCHECK`.
  Renvoie `boot_id` (change à chaque démarrage -> détecte les redémarrages)
  et `uptime_s` (V320b).
- `/health` — **ping MongoDB Atlas**, renvoie 503 si la base tarde.
  **NE JAMAIS s'en servir comme healthcheck** : un hoquet d'Atlas ferait
  redémarrer en boucle une application saine.

**Deux correctifs, deux pannes différentes — il faut les DEUX** :
1. *Coupure pendant les déploiements* -> `HEALTHCHECK` (fait : `Dockerfile` +
   `docker-compose.yml`) **+ réglage Coolify** : activer le Health Check
   (`/healthz`, port 8080) et l'attente « healthy » avant retrait de l'ancien
   conteneur. **Le commit seul ne suffit pas** : sans ce réglage d'interface, la
   sonde existe mais n'est pas la condition de bascule.
2. *Coupure hors déploiement* -> mémoire. Vérifier `swapon --show` puis, si vide,
   ajouter 4 Go de swap (`fallocate` / `mkswap` / `swapon` / `/etc/fstab`).
   Preuve d'OOM à réclamer : `docker inspect ... OOMKilled`, `dmesg -T | grep -i
   "killed process"`, `RestartCount`.

Mesure de référence avant réglage Coolify (déploiement V320, sonde 1/s) :
`297 × 200, 0 × 404, 3 × 000` — soit ~13 s d'indisponibilité au remplacement
du conteneur.

### afroboosteur.com — site de l'association
- **Hébergement** : Coolify sur VPS Hetzner — `178.105.201.62` (confirmé par `dig`)
- **Dépôt** : `sambassi/afroboosteur-site`, branche `main`
- **Stack** : Next.js + Supabase + Firebase — Build Pack Nixpacks, port 3000
- **Coolify** : http://178.105.201.62:8000
- **Même serveur qu'afroboost.com**, mais application Coolify DIFFÉRENTE.
  C'est sur CE site qu'on tombe en cherchant « afroboost » dans Coolify —
  d'où la confusion.

### formation.afroboosteur.com — plateforme de formation
- **Hébergement** : Coolify, même serveur Hetzner
- **Conteneurs** : `formation-backend` (port 8000) + `formation-frontend` (port 80)
- **Troisième site, distinct des deux autres.**

### Variables d'environnement à ne pas oublier (afroboost.com / **Coolify**)
| Variable | Effet si absente |
|----------|------------------|
| `JWT_SECRET` | Auth retombe sur `X-User-Email` (falsifiable). `/api/debug/config` → `jwt_secret_set: false` |
| `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | La purge 48 h (V261) retire les publications de la base mais laisse les fichiers chez Cloudinary |
| `REACT_APP_*` | Inlinées **au build** par CRA : une variable posée seulement à l'exécution n'atteint jamais le bundle |
| `PAWAPAY_API_TOKEN` / `PAWAPAY_BASE_URL` | Mobile Money inerte. **Le mode se lit dans l'URL** : `https://api.pawapay.io` = production, `https://api.sandbox.pawapay.io` = bac à sable. Un jeton de prod sur l'URL sandbox renvoie 401 |
| `PAWAPAY_DEFAULT_COUNTRY` | **V381 — chaque paiement échoue en 400** « Mobile Money indisponible pour ce pays ». Le compte a 12 pays ouverts, ni le frontend ni `resoudre_pays()` ne peuvent trancher tout seuls. ⚠️ Cette variable est prioritaire sur le pays demandé : elle FORCE le pays pour tout le monde. À retirer le jour où le frontend proposera un sélecteur de pays |

### ⚠️ Activer `JWT_SECRET` — procédure (V265)
Poser `JWT_SECRET` bascule l'authentification en mode signé. **Ne l'activer
qu'avec le mode transitoire V265 déployé** (`require_auth` +
`_v263_authenticated_coach`, server.py). Sans lui, l'activation avait cassé
uploads et publications pour toute session ouverte avant — c'est ce qui s'est
produit une première fois.

Ce que fait le mode transitoire, secret posé :
1. requête avec JWT valide → acceptée (chemin sûr, cible finale) ;
2. requête sans JWT mais avec `X-User-Email` → acceptée AUSSI, avec un WARNING
   `[V265] repli X-User-Email` dans les logs (les anciennes sessions survivent) ;
3. rien → 401.

Procédure :
1. Vérifier que V265 est en ligne : `curl -s https://afroboost.com/api/debug/config`.
2. Poser `JWT_SECRET` dans Coolify, redéployer (~4 min).
3. Se déconnecter / reconnecter une fois (pour obtenir un vrai jeton signé).
4. Surveiller les logs : tant que `[V265] repli X-User-Email` apparaît, des
   sessions n'ont pas encore migré — NE PAS retirer le repli.
5. Quand ces warnings ont cessé (tout le monde a un jeton), une version dédiée
   pourra RETIRER l'étape 2 pour revenir au JWT strict, non falsifiable.

⚠️ Tant que l'étape 2 existe, `X-User-Email` reste falsifiable : le mode
transitoire est un pont, pas l'état final.

## Testing
- Test files: `backend_test.py`, `backend_regression_test.py`, `tests/`
- Run: `python -m pytest tests/`

## When Making Changes
1. Always add a version comment (V{next_number})
2. Test locally before deploying
3. Be careful with the WhatsApp template cleaning code (~line 6572) — it went through 6 iterations
4. When modifying CoachDashboard.js, check that you're not breaking other tabs/sections
5. MongoDB collection names are lowercase with underscores

---

# LEGACY DOCUMENTATION (Archived)

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

3. **Icônes en SVG uniquement** : Ne jamais utiliser d'emoji Unicode comme icônes dans l'interface. Toujours utiliser des `<svg>` inline avec `stroke="currentColor"`.

4. **Ne pas toucher** :
   - Les 53 routes JWT auth existantes
   - Le Service Worker V140 (sauf bumps de version)
   - Le système de paiement Stripe (webhook critique)
   - Les fonctionnalités qui marchent déjà

5. **Ne pas casser le paiement, les réservations, ni les conversations.**

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

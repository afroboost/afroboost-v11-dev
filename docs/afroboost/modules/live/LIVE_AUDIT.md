# Module Afroboost Live / BoostTribe — Audit détaillé

> Audit **en lecture seule** du 19/10/2026. Aucune modification, aucun déploiement, aucun Live lancé, aucun crédit touché.
> Code audité : BoostTribe `origin/main` = **`215c18b`** (06/10/2026), exporté hors dépôt (`git archive`) — c'est le code servi
> en production (bundle `boosttribe.pro` = `index-D9ow6lkt.js`, dernière modification 06/10 12:07 UTC ; `afroboost.com/live`
> = `index-DpM68cLP.js`, branche `deploy/afroboost-live` = `2e7503d`). Côté Afroboost : `afroboost-v11-dev` `main` = `0a575c9b` (V621).
>
> ⚠️ « boosttrube.pro » n'existe pas (aucune résolution DNS) : le domaine réel est **boosttribe.pro**.
>
> Légende des preuves : `BT/…` = dépôt BoostTribe, `AF/…` = dépôt Afroboost. Les numéros de ligne renvoient au code audité.
> Les points marqués **« à vérifier en base »** dépendent de scripts SQL Supabase dont on ne sait pas lesquels ont été appliqués
> en production (plusieurs fichiers se contredisent) : ils n'ont **pas** été testés contre la production — les tester serait
> les exploiter.

---

## 1. Architecture réelle

```
Coach / abonné Afroboost                         Utilisateur direct BoostTribe
        │ (bouton « Live » de la barre,                     │
        │  modale Publier → Sessions live)                  │
        ▼                                                   ▼
afroboost.com (React)                            boosttribe.pro (Vite/React/TS, nginx)
        │ POST /api/boosttribe/access                       │
        ▼                                                   │
API Afroboost (FastAPI, Mongo)  ── JWT HS256 15 min ──►  iframe afroboost.com/live/embed?bt_token=…[&bt_session=CODE]
  (décide admin / abonné,                                   │ (même code BoostTribe, habillage REACT_APP_BRAND=afroboost)
   lit séances restantes)                                   ▼
        ▲                                        Backend BoostTribe (FastAPI, main.py 6000 l.)
        │ POST /api/boosttribe/consume ◄──────── POST /api/embed/session-started (déclenché par le NAVIGATEUR)
        │ (débit 1 séance, idempotent jti)       │ /api/embed/verify → crée/retrouve le compte Supabase,
        │                                        │   accorde comp_access « pro » 12 h, magic-link
        │                                        ▼
        │                                  Supabase auto-hébergé (auth GoTrue, Postgres, Storage, Realtime)
        │                                  LiveKit SFU auto-hébergé (vidéo) + Egress + Redis (Coolify)
        │                                  PeerJS (audio : serveur auto-hébergé ; visio mesh = cloud public, code mort)
        │                                  OpenAI (transcription, souffleur), Stripe/PawaPay/Flutterwave (crédits, billets)
```

| Élément | Réalité constatée |
|---|---|
| Dépôt | `github.com/afroboost/Boosttribe-v8` (**PUBLIC**), branche `main`. Copie locale `~/Boosttribe-v8` (main local **en retard de 92 commits** sur origin). |
| Déploiement Afroboost | dépôt `afroboost/afroboost-live` = `Boosttribe-v8` `main` + 1 commit `.env.production` (`REACT_APP_BRAND=afroboost`), webhook Coolify actif. |
| Frontend | Vite + React 18 + TypeScript, Tailwind, shadcn minimal, lucide ; `SessionPage.tsx` ≈ 6 760 lignes ; admin `pages/admin/Dashboard.tsx` 2 735 l. |
| Backend | FastAPI `backend/main.py` (6 000 l.) + `multistream.py` + `social_destinations.py` ; Nixpacks/Procfile ; domaines `api-live.afroboost.com` (habillage Afroboost) et backend BT. |
| Base | Supabase **auto-hébergé** (Postgres + GoTrue + Storage + Realtime) : `api.boosttribe.pro` et `supabase-live.afroboost.com` (pile Afroboost). |
| Vidéo | **LiveKit SFU** auto-hébergé (`livekit.boosttribe.pro` = `livekit.afroboost.com`, même conteneur), + Egress v1.14.1 + Redis (déployés 21/09). |
| Audio | **PeerJS** (serveur auto-hébergé `peerjs.<ip>.sslip.io`), STUN Google, TURN coturn optionnel (identifiants injectés au build → visibles dans le bundle). |
| Temps réel applicatif | Supabase Realtime (broadcast + presence) : chat, réactions, commandes hôte. |
| Hébergement | Coolify sur le **même VPS Hetzner** `178.105.201.62` qu'afroboost.com (7,7 Go RAM, swap déjà chargé). |
| CI | **aucune** (pas de `.github/workflows`). Tests manuels : 19 fichiers pytest + `yarn test` + `yarn test:live-contract` (`docs/LIVE_CONTRACT.md`). |
| État production (19/10, lecture) | boosttribe.pro 200, afroboost.com/live 200, api-live `/health` `{"ok":true}`, livekit 200, Supabase 401 (normal sans clé). |

---

## 2. Inventaire fonctionnel (≈ 70 fonctionnalités)

Statuts : ✅ fonctionnelle · 🟡 partielle · ❌ absente · 💀 code mort. Réutilisation pour afroboost.com : F/M/Fa = forte / moyenne / faible.

### 2.1 Salle / session
| Fonctionnalité | Statut | Qui | Frontend | Backend / données | Problèmes | Réutil. |
|---|---|---|---|---|---|---|
| Créer une salle | ✅ | utilisateur connecté | `SessionPage.tsx:4330-4360` (id généré côté client) | `/session/claim-host` (main.py:3309) ; table `playlists` ; débit `cost_host` via `/credits/spend` | **premier arrivé = hôte** (3319) ; photo obligatoire ; limite de sessions côté client | F |
| Rejoindre | ✅ | tous (`/session/:id` public) | `SessionPage.tsx:2025-2058` | `/credits/spend join` (mode open), `checkTicket` (payant), salle d'attente (privé) | `/livekit/token` viewer accordé **sans vérifier crédit ni billet** | F |
| Code + lien + QR | ✅ | hôte | `qrcode.react`, `lib/publicUrl.ts` | page `/promo/:id` | — | F |
| Page promo / lien d'invitation | ✅ | hôte | `PromoEditor.tsx`, `PromoPage.tsx` | `/session/promo*` | — | M |
| Modes d'accès open / paid / private, guest/account | ✅ | hôte | `AccessModeSelector.tsx`, `lib/accesSession.ts` | `/session/configure`, `playlists.access_mode` | invité = écoute seule | F |
| Salle privée / salle d'attente | 🟡 | hôte | `WaitingRoomScreen.tsx` | admission par broadcast `ADMIT` | admission vérifiée **côté client seulement** | M |
| Mot de passe / verrouillage | ❌ | — | — | — | — | — |
| Max participants | 🟡 | — | `capacity` en mode payant ; scène vidéo max 10 | `MAX_LIVEKIT_STAGE=10` | pas de plafond d'audience | Fa |
| Planification / calendrier / rappels | ❌ | — | — | — | Afroboost a déjà calendrier + rappels (à réutiliser) | — |
| Terminer le Live | ✅ | hôte | `lib/finDuLive.ts` | `/session/{id}/terminer`, `/etat-live` | — | F |
| « Live en cours » côté Afroboost | ✅ | coach hôte → public | `BoostTribeLive.js` | `AF` `/boosttribe/live-status` + collection `boosttribe_live` (heartbeat 15 s, garde 3 h) | annonce pilotée par le navigateur | F |

### 2.2 Audio / vidéo
| Fonctionnalité | Statut | Frontend | Transport | Problèmes | Réutil. |
|---|---|---|---|---|---|
| Vidéo hôte / co-hôtes | ✅ | `useLiveKitStage.ts`, `LiveVisioPanel.tsx` | LiveKit (`/livekit/token`, rôle stage décidé serveur) | `useVideoMesh` (PeerJS) = 💀 | F |
| Voix / musique | ✅ | `usePeerAudio.ts` (1 638 l.), `useMicrophone.ts` | PeerJS | LiveKit ne porte que la vidéo | M |
| Mute participant, donner/couper la parole | ✅ | `ParticipantControls.tsx` | broadcast `CMD_MUTE_USER` | commande non authentifiée | M |
| Caméra on/off, changer de caméra | ✅ | `useLiveKitStage.ts:537-575` | LiveKit | — | F |
| Caméra externe (UVC, OBS, Insta360 UVC) | 🟡 | `useSecondaryCameras.ts`, `SourcesDrawer.tsx` | composée dans le programme | Chromium desktop seulement | M |
| Micro secondaire | ✅ | `useSecondaryMic.ts` | mixeur | — | M |
| Studio scènes Preview/Programme | ✅ | `useStudio.ts`, `programCompositor.ts` | canvas → `publishProgram` | — | F |
| Partage d'écran | ✅ | `getDisplayMedia` | LiveKit | `ScreenShareView.tsx` 💀 | F |
| Partage média (vidéo/image/YouTube) | ✅ | `SharedMediaPlayer.tsx` | bucket public `session-media` (TTL 24 h) | — | M |
| Beauté / looks | ✅ | `useBeauteVisage.ts` | GPU local | — | M |
| Plein écran / mobile (cibles 44 px) | ✅ | `useFullscreen.ts`, `liveControls.ts` | — | — | M |

### 2.3 Interaction
| Fonctionnalité | Statut | Détail | Réutil. |
|---|---|---|---|
| Liste des participants | ✅ | Supabase Presence | F |
| Co-hôte | ✅ | `/session/cohosts`, `playlists.cohosts` | F |
| Lever la main / monter sur scène | ✅ | demande en broadcast, promotion **vérifiée serveur** (`/livekit/promote`) | F |
| Chat de groupe et privé | ✅ | broadcast éphémère (rien stocké) ; droit `droitChatLive` | M |
| Réactions (6 types) | ✅ | broadcast agrégé | F |
| Likes / commentaires persistants | ✅ | `session_likes`, `session_comments` | M |
| Exclusion | 🟡 | broadcast `CMD_EJECT_USER` → l'exclu peut revenir | Fa |
| Modération | 🟡 | mute/exclusion/suppression message côté client | Fa |

### 2.4 Enregistrement / IA
| Fonctionnalité | Statut | Détail | Coût | Réutil. |
|---|---|---|---|---|
| Enregistrement local du programme vidéo | ✅ | `useProgramRecorder.ts` (OPFS, téléchargement ; rien n'est envoyé au serveur) | 0 | F |
| Enregistrement audio + transcription | ✅ | `/session/record/start|stop|upload` (300 Mo max), bucket privé `session-recordings` | `cost_record_transcribe` = 4 crédits ; **`/upload` non plafonné** | M |
| Résumé IA | 💀 | désactivé (main.py:570) | — | — |
| Replay | 🟡 | liste dans `/wallet` : transcription seulement, pas de lecteur vidéo ni miniature ; **aucune conservation automatique** | — | Fa |
| Transcription temps réel (voix participant) | ✅ | jeton éphémère OpenAI Realtime, hôte Espace Coach/admin | `gpt-4o-mini-transcribe` | M |
| Souffleur IA (suggestions hôte) | ✅ | `/live/assistant/suggestions`, quotas en mémoire | `gpt-4o-mini` | F |
| Prompteur | ✅ | localStorage, `/studio` | 0 | F |
| Sous-titres / traduction / clips / miniatures | ❌ | — | — | — |
| Assistant support (ChatBot) | ✅ | mots-clés, réponses fixes (pas d'IA) | 0 | Fa |

### 2.5 Diffusion / réseaux
| Fonctionnalité | Statut | Détail | Réutil. |
|---|---|---|---|
| Multistream YouTube / Facebook / Instagram / TikTok | 🟡 | Egress RTMPS ; **simulé** tant que le verrou `verrou_direct_reel` (3 variables dont `SOCIAL_LIVE_GO=GO_BASSI_TEST_LIVE_SOCIAL`) n'est pas levé ; comptes restreints à la Page et la chaîne Afroboost | M |
| RTMP en clair | refusé | seul `rtmps://` accepté | — |

### 2.6 Musique / séance (cœur Afroboost)
| Fonctionnalité | Statut | Détail | Réutil. |
|---|---|---|---|
| Playlist, upload, glisser-déposer | ✅ | bucket `audio-tracks`, `playlists.tracks` | F |
| Synchronisation de lecture | ✅ | `useAudioSync.ts` (Realtime) | F |
| Mixeur + ducking | ✅ | `useAudioMixer.ts` (≈ −20 %) | F |
| Interval timer (HIIT) | ✅ | `IntervalTimer.tsx` | F |

### 2.7 Monétisation
| Fonctionnalité | Statut | Détail |
|---|---|---|
| Crédits (solde, dépense join/host) | ✅ | `/credits/me`, `/credits/spend` ; coût décidé serveur (402) ; **appel déclenché par le client** |
| Bonus d'inscription | ✅ | `/credits/signup-bonus` (idempotent) |
| Achat de crédits | ✅ | Stripe `/stripe/buy-credits` ; masqué sur Afroboost (`vendCredits:false`) |
| Historique crédits (UI) | ❌ | `/credits/me` renvoie 50 lignes du ledger, **aucun écran ne l'affiche** |
| Plans Pro / Enterprise | ✅ | Stripe, PawaPay, Flutterwave |
| Coach Illimité (99,99 CHF/mois) | 🟡 | `/coach/plan` ; `subscribeCoach` 💀 |
| Billetterie (session payante) | ✅ | Stripe/PawaPay/Flutterwave, commission 15 % |
| Portefeuille coach / virements | ✅ | `coach_wallet`, `wallet_ledger`, `payout_requests` |
| Promo Live par un participant | ✅ | `live_promos` |
| Essai 5 min | 🟡 | minuteur **client** |
| Quotas (titres, sessions) | 🟡 | **client uniquement** |

### 2.8 Admin BoostTribe (`/admin`)
Onglets : Identité, Couleurs, Boutons & Stats, Clés Stripe/IA/PawaPay, Crédits & Tarifs, Billetterie & Virements, Crédits offerts, Utilisateurs (**lecture seule** + CSV). Onglet « plans » rendu mais inatteignable.
Ce qu'un admin peut faire **par utilisateur** : offrir / ajuster / supprimer un octroi de crédits, régler le type de paiement d'un coach. **Il ne peut pas** activer/désactiver une fonctionnalité, rendre illimité (routes `grant-access`/`revoke-access` existent mais ne sont pas branchées), ni voir l'usage.

### 2.9 Autres
Embed Afroboost ✅ (F) · marques `brands.json` ✅ · notifications/e-mails ❌ (seuls e-mails d'auth Supabase) · statistiques / durée de présence / historique de sessions ❌ · logs : `console.log` / `logger` texte · mobile : PWA + Capacitor Android 🟡 · `/studio` ✅.

**Nombre de fonctionnalités auditées : 70** (dont 49 fonctionnelles, 13 partielles, 8 absentes ; 9 fichiers/fonctions de code mort relevés).

---

## 3. Système de crédits actuel

**SYSTÈME DE CRÉDITS EXISTANT = OUI côté BoostTribe ; NON (au sens « crédits Live ») côté Afroboost.**

### 3.1 BoostTribe (Supabase)
| Élément | Réalité (`BT/infra/credits/schema.sql`) |
|---|---|
| Solde | `profiles.credits integer` = **cache** recalculé par trigger `trg_credit_ledger_change` = `sum(delta)` |
| Journal | `credit_ledger(id, user_id, delta, reason, ref, note, expires_at, created_at)` ; `reason` ∈ purchase, spend_join, spend_host, spend_record, offered, signup_bonus, referral, launch_bonus, refund, gift ; index unique `(reason, ref)` = idempotence |
| Manque | **pas de `created_by`**, pas de `session_id` dédiée (encodée dans `ref`), pas de `feature` |
| Octroi | achat Stripe (webhook `ref=stripe:{event}`), factures plan, mobile money, admin « offered », bonus inscription, launch bonus 5 |
| Consommation | `/credits/spend` (`join`, `host` = 1 crédit par défaut, réglables `pricing_settings.cost_join/cost_host`), enregistrement 4 crédits ; RPC `spend_credits` SECURITY DEFINER + `FOR UPDATE` |
| Remboursement | ❌ (seuls les billets) |
| Expiration | `expires_at` stocké, **jamais appliqué** |
| Admin | PATCH / DELETE des lignes du ledger → **journal réécrit sans trace** |
| Affichage | solde partout ; historique non affiché |
| Packs | 1 cr = 9 CHF, 5 = 40, 10 = 70 (`credit_packs`) |

### 3.2 Afroboost (Mongo) — ce que « crédit » veut dire aujourd'hui pour le Live
- **1 crédit Live = 1 séance du forfait de l'abonné** : `subscriptions.remaining_sessions` (sinon `discount_codes.maxUses − used`), débité par `POST /api/boosttribe/consume` (idempotent sur `jti`, collection `boosttribe_usage`, TTL 7 j) via la règle unique `seances_consommer` (`seance_mouvements`).
- Le super-admin ne paie jamais ; l'hôte n'est pas facturé côté Afroboost.
- `coaches.credits` (`/coach/add-credits`, collection `credit_transactions`) = portefeuille **séparé** des partenaires (IA/campagnes), **non utilisé par le Live**.
- Via l'embed, BoostTribe accorde `comp_access_plan="pro"` **12 h** → crédits BT ignorés (illimité) pour ces utilisateurs.

### 3.3 Journal des mouvements — existe-t-il ?
| Exigence (exemple demandé) | BoostTribe `credit_ledger` | Afroboost `seance_mouvements` |
|---|---|---|
| transaction_id | ✅ `id` | 🟡 pas d'id propre (clé = réservation) |
| user_id | ✅ | 🟡 `code` / `fiche_id` |
| amount | ✅ `delta` | ✅ `quantite` |
| type / reason | ✅ `reason` | ✅ `type` + `source` |
| feature | ❌ | ❌ |
| session_id | 🟡 dans `ref` | 🟡 `reservation_id` |
| created_at | ✅ | ✅ `at` |
| created_by | ❌ | ❌ |
| immuable | ❌ (PATCH/DELETE admin) | 🟡 (pas d'écriture admin directe) |

**JOURNAL CRÉDITS EXISTANT = OUI mais incomplet et mutable** (pas d'auteur, pas de fonctionnalité, modifiable).

---

## 4. Permissions / fonctionnalités actuelles

| Mode de décision | Existe ? | Où |
|---|---|---|
| Codé en dur | ✅ | `ADMIN_EMAILS` (backend + 3 fichiers front + RLS SQL) |
| Lié au rôle | ✅ | hôte / co-hôte (`playlists.host_id`, `cohosts`) ; admin |
| Lié au plan | ✅ | `comp_access_plan` pro/enterprise, `coach_payment_type` (commission ⇒ billetterie, promo Live), abonnement coach |
| Lié au crédit | ✅ | `/credits/spend` pour join/host/enregistrement |
| Feature flags | 🟡 | `pricing_settings.services_shown`, `trial_days`, `site_settings.plan_*_visible` (globaux, affichage) |
| Configurable utilisateur par utilisateur | ❌ | **aucune table de droits** ; seul levier par utilisateur = crédits offerts |
| « Espace Coach » | ✅ | `_est_espace_coach` = commission OU enterprise OU abonnement coach OU admin → enregistrement, transcription, souffleur voix |

**PERMISSIONS PAR UTILISATEUR = PARTIEL** (dérivées du plan/rôle, jamais réglables individuellement par fonctionnalité).
**FONCTIONNALITÉS CONFIGURABLES PAR ADMIN = NON** (globalement seulement : coûts, visibilité des plans).
**COÛT PAR FONCTIONNALITÉ = PARTIEL** : 3 coûts (rejoindre, animer, enregistrement+transcription) ; aucun coût par minute, IA, partage d'écran, multistream.

### 4.1 Le backend est-il autoritaire ? (exigence « start_recording »)
| Contrôle | Respecté ? |
|---|---|
| Identité (JWT Supabase vérifié par `/auth/v1/user`) | ✅ |
| Droit de publier la vidéo (stage) | ✅ serveur |
| Enregistrement / transcription / souffleur | ✅ serveur (Espace Coach + hôte) |
| Coût prélevé | 🟡 serveur, **mais l'appel `/credits/spend` est déclenché par le client** et `/livekit/token` (viewer) ne vérifie ni crédit ni billet → on peut regarder sans payer |
| Solde | ❌ **falsifiable si la RLS `profiles_update` des scripts est celle appliquée** (UPDATE de toute sa ligne : `credits`, `comp_access_*`, `coach_payment_type`, `role`) — **à vérifier en base** |
| Modération (mute, exclusion, admission) | ❌ client (broadcast non authentifié) |
| Quotas (sessions, titres, essai 5 min) | ❌ client |

---

## 5. Sécurité — constats Live (par gravité)

| # | Constat | Preuve | Gravité |
|---|---|---|---|
| L1 | **Identifiants LiveKit Cloud (clé + secret) écrits en clair dans le dépôt PUBLIC** depuis le 29/06/2026 (section « Rollback ») | `BT/infra/livekit/README.md:94-95` ; commits 473a7bc, 86cd8ed | **P0** — révoquer côté LiveKit Cloud, purger l'historique |
| L2 | `POST /api/boosttribe/access` décide « super-admin » via `X-User-Email` non signé quand aucun JWT n'est fourni → Live gratuit illimité **et reprise de la session hôte en cours** ; idem `POST /boosttribe/live-status` | `AF/api/server.py:12001-12035, 14772-14812, 141-205` (déduit du code, non testé) | **P0** |
| L3 | RLS `profiles_update` sans restriction de colonnes : un utilisateur peut s'écrire crédits / illimité / commission / `role=admin` | `BT/frontend/SUPABASE_INIT.sql:137` etc., `AuthContext.tsx:207-211` | **P0 si appliqué — à vérifier en base** |
| L4 | RPC `wallet_add` SECURITY DEFINER **sans REVOKE** → solde de portefeuille forgeable puis demande de virement | `BT/infra/billetterie/schema.sql:94-131` | **P0 si appliqué — à vérifier** |
| L5 | `/livekit/token` viewer accordé à tous pour toute session, payante comprise | `main.py:1266-1322` | P1 |
| L6 | Appropriation d'une session sans hôte (`claim-host`, `configure`, RLS `host_id IS NULL`) | `main.py:3319, 3093` | P1 |
| L7 | `/api/embed/verify` ouvre une session (magic-link) pour **tout email** d'un JWT signé par Afroboost, admin compris, sans anti-rejeu du `jti` | `main.py:5031-5078` | P1 (le secret partagé = clé maîtresse) |
| L8 | Débit Afroboost déclenché par le navigateur, accès 12 h accordé **avant** ; si Afroboost injoignable → gratuit | `main.py:5014-5028`, `embedApi.ts:103-139` | P1 |
| L9 | `/session/record/upload` sans plafond ni vérification du débit → coût OpenAI illimité | `main.py:665+` | P1 |
| L10 | Commandes hôte (mute/éjecter/admettre) par broadcast non authentifié | `SocketContext.tsx:155-171` | P2 |
| L11 | Journal crédits mutable, pas d'auteur ; aucune table d'audit ; journal promo public | §3 | P2 |
| L12 | `/admin/stripe-keys?reveal=true` renvoie la clé secrète Stripe en clair | `main.py:459` | P2 |
| L13 | Identifiants TURN injectés au build (visibles) ; quotas IA en mémoire (réinitialisés au redéploiement) | `usePeerAudio.ts` | P2 |
| L14 | Abonnés Afroboost **sans e-mail** refusés par BT (401 « Jeton sans email ») | `main.py:5040` | P2 (fonctionnel) |

---

## 6. Coûts réels (fournisseurs)

Aucun prix n'est écrit dans le code BoostTribe. Prix publics fournisseurs : **à confirmer sur les factures/console** (non visibles d'ici).

| Fournisseur | Fonctionnalité | Unité facturée | Configuration actuelle | Limites | Risque de dépassement |
|---|---|---|---|---|---|
| LiveKit (auto-hébergé, VPS Hetzner) | vidéo Live, partage d'écran | CPU/RAM/bande passante du VPS (forfait) | SFU 1.13.2, scène 10 max | aucune limite d'audience | **saturation du VPS partagé avec afroboost.com** (7,7 Go) |
| LiveKit Egress | multistream, test fichier | CPU (encodage) | déployé, simulé tant que verrou fermé | `mem_limit` 1,5 Go | élevé si activé |
| OpenAI `gpt-4o-transcribe` | transcription d'enregistrement | minute d'audio | clé chiffrée `ai_secrets` | **upload non plafonné** | élevé (faille L9) |
| OpenAI `gpt-4o-mini-transcribe` | transcription temps réel | minute d'audio | jeton éphémère | 10/Live/10 min, 20/compte/h (mémoire) | moyen |
| OpenAI `gpt-4o-mini` | souffleur | tokens | — | 20 appels / 5 min (mémoire) | faible |
| Supabase auto-hébergé | auth, base, stockage | disque VPS | `session-recordings` sans TTL ; `session-media` 24 h ; `promo/`, `invites/` sans nettoyage | — | moyen (disque) |
| PeerJS / STUN / TURN | audio | bande passante (TURN) | auto-hébergé | — | faible |
| Stripe / PawaPay / Flutterwave | crédits, billets, plans | commission par transaction | — | — | faible |
| LiveKit Cloud (repli documenté) | vidéo | minute participant | identifiants **exposés** (L1) | — | **inconnu : dépend de l'état du compte Cloud** |

### 6.1 Matrice fonctionnalité → coût → unité de crédit proposée (sans montant)
| Fonctionnalité | Coût fournisseur réel | Unité naturelle | Proposition d'unité de crédit | Marge |
|---|---|---|---|---|
| Rejoindre un Live (audio + vidéo regardée) | VPS (fixe) | session | forfait par participation | élevée (coût marginal ≈ 0 tant que le VPS tient) |
| Animer un Live | VPS (fixe) | session ou minute | forfait par Live ou par tranche de minutes | élevée |
| Partage d'écran / caméra externe | VPS (CPU/bande passante) | minute | inclus ou supplément | élevée |
| Enregistrement local | 0 | — | droit (oui/non), pas de crédit | — |
| Enregistrement + transcription | OpenAI à la minute | minute d'audio | crédits par tranche de minutes | dépend du prix décidé |
| Transcription temps réel | OpenAI à la minute | minute | crédits par minute | idem |
| Souffleur IA | OpenAI tokens | appel | crédits par appel ou forfait | élevée |
| Multistream | CPU Egress | minute | crédits par minute | moyenne |
| Stockage replay | disque | Go × durée | crédits par Go/mois ou durée de conservation | — |

**Aucun montant n'est fixé : décision commerciale de Bassi.**

---

## 7. Réutilisation dans afroboost.com

| Fonctionnalité | Telle quelle | Avec adaptation | À réécrire | Risque régression afroboost.com | Dépendances |
|---|---|---|---|---|---|
| Embed + jeton `/boosttribe/access` | OUI | sécuriser L2 | NON | moyen | `AFRO_BT_SHARED_SECRET` |
| « Live en cours » + bouton barre | OUI | — | NON | faible | `boosttribe_live` |
| Vidéo LiveKit (scène, co-hôte, main levée) | OUI (dans l'iframe) | — | NON | faible | SFU partagé |
| Musique synchronisée + mixeur + timer | OUI | — | NON | faible | PeerJS, Supabase |
| Partage d'écran / studio / caméras externes | OUI | — | NON | faible | navigateur |
| Chat Live | OUI | stocker si besoin | NON | faible | Realtime |
| Enregistrement local | OUI | — | NON | nul | — |
| Transcription / souffleur | OUI | plafonds persistants | NON | faible | OpenAI |
| Crédits BT (`credit_ledger`) | NON | **oui comme modèle** | partiel | élevé si fusion brutale | Supabase |
| Admin BT (crédits offerts) | NON | modèle d'écran | — | — | — |
| Multistream | NON (verrou) | oui | NON | faible | Egress |
| Replay | NON | stockage + lecteur | OUI | faible | stockage |
| Modération (exclusion, admission) | NON | contrôle serveur | OUI | faible | — |

### 7.1 Options d'architecture
| Critère | **A** — Live reste un service séparé, connecté (état actuel) | **B** — tout intégrer dans afroboost.com | **C** — backend partagé / frontend intégré | **D** — A renforcé : Afroboost = source unique des comptes, crédits et droits ; BoostTribe = moteur Live qui consulte une API d'autorisation |
|---|---|---|---|---|
| Complexité | faible (existe) | très élevée (réécrire 6 760 l. TS + PeerJS + Supabase dans un front React 19 JS de 11 000 l.) | élevée (deux bases à fusionner) | moyenne |
| Coût | nul | élevé | élevé | moyen |
| Performance | bonne (iframe isolée) | risque sur App.js déjà lourd | moyenne | bonne |
| Sécurité | faibles actuelles (L1-L9) | — | — | **meilleure** : une seule autorité, décisions serveur à serveur |
| Maintenance | deux systèmes de crédits divergents | un seul code mais énorme | deux bases couplées | un seul registre de droits et crédits |
| Mise en production | immédiate | des mois | des mois | **par petits lots** |

**Recommandation : D.** Garder le moteur Live BoostTribe (il fonctionne, il est isolé dans une iframe, il ne casse pas afroboost.com), mais rendre **Afroboost autoritaire** pour : l'identité, le solde de crédits, les droits par fonctionnalité et les limites. BoostTribe demande à Afroboost (serveur à serveur, signé) « cet utilisateur peut-il faire X, pour combien ? » au moment de l'action (démarrer, enregistrer, partager, IA), et Afroboost débite son propre journal. Les crédits BoostTribe restent pour les clients directs de boosttribe.pro (marque séparée) tant que Bassi ne décide pas autre chose.

---

## 8. Écran admin cible (documentation, NON construit)

```
ADMIN → UTILISATEURS → [Paul Exemple]
┌────────────────────────────────────────────────┐
│ Paul Exemple · paul@… · Coach · Actif          │
├─ CRÉDITS ──────────────────────────────────────┤
│ Solde : 850 crédits    [ + Ajouter ] [ − Retirer ]  (motif obligatoire)
│ Historique (immuable)                           │
│ +500  15/10 manual_credit  Admin · « pack test »│
│  −60  16/10 live_usage     Live « HIIT » 60 min │
│ +200  17/10 promo          Code AUTOMNE         │
│ (correction = nouvelle ligne inverse, jamais une modification)
├─ FONCTIONNALITÉS AUTORISÉES ───────────────────┤
│ [✓] Live  [✓] Caméra  [✓] Micro  [✓] Chat  [✓] Replay
│ [ ] Enregistrement  [ ] Partage écran  [ ] IA  │
│ (case grisée + mention si le plan ne l'inclut pas)
├─ LIMITES (optionnel) ──────────────────────────┤
│ Durée max Live [ 90 ] min · Participants max [ 30 ]
│ Stockage [ 2 ] Go · Replays conservés [ 30 ] j │
├─ UTILISATION ──────────────────────────────────┤
│ 12 Lives · 640 min · 3 enregistrements (30 j)  │
└────────────────────────────────────────────────┘
          [ Annuler ]        [ Enregistrer ]
```
Règle : l'écran n'envoie que des **intentions** (ajouter 500, motif X ; activer recording) ; le serveur vérifie le super-admin signé, écrit une ligne de journal et un audit log, puis renvoie l'état recalculé.

---

## 9. Questions pour Bassi (Live)
1. Les clients directs de boosttribe.pro et ceux d'afroboost.com doivent-ils partager le **même solde** de crédits ?
2. Un « crédit » Live doit-il rester **une séance du forfait** (aujourd'hui) ou devenir une **unité distincte** ?
3. Qui paie le Live : seulement les participants, aussi l'hôte (coach), ou personne (inclus dans l'abonnement) ?
4. Prix réels : quelles fonctionnalités deviennent payantes (enregistrement, IA, multistream, replay) et combien ?
5. Le replay vidéo (stockage serveur) est-il souhaité ? Durée de conservation ?
6. Les coachs partenaires peuvent-ils animer des Lives (aujourd'hui seul le super-admin anime via l'embed) ?
7. Faut-il révoquer immédiatement le compte LiveKit Cloud exposé (recommandé) — qui a accès à ce compte ?
8. Faut-il garder boosttribe.pro comme marque commerciale séparée ?

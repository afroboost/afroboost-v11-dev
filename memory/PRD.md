# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### ✅ Mission v13.2 (March 2026) - COMPLETED
**Validation Sécurité & Nettoyage du Code (Refactoring)**
1. **Verrouillage Crédits Validé** - Partenaires avec 0 crédits voient écran "Crédits insuffisants"
2. **Super Admin Bypass** - Bassi peut tout ouvrir sans restriction
3. **Refactoring CoachDashboard.js** - Réduit de 6759 → 6537 lignes (-222 lignes)
4. **Composants Extraits** :
   - `CreditsGate.js` - Écran de blocage réutilisable
   - `CreditBoutique.js` - Section achat de packs
   - `StripeConnectTab.js` - Section Stripe & personnalisation
5. **Anti-régression** - 22 réservations intactes, vidéo full-width confirmée

**Nouveaux fichiers v13.2:**
- `/app/frontend/src/components/dashboard/CreditsGate.js` (45 lignes)
- `/app/frontend/src/components/dashboard/CreditBoutique.js` (112 lignes)
- `/app/frontend/src/components/dashboard/StripeConnectTab.js` (128 lignes)
- `/app/frontend/src/components/dashboard/index.js`

### ✅ Mission v13.1 (March 2026) - COMPLETED
**Verrouillage Services & Sécurité Crédits**
- Blocage accès services si crédits insuffisants
- Redirection vers Boutique pour recharger

### ✅ Mission v13.0 (March 2026) - COMPLETED
**Stripe Connect & Vente de Packs Crédits**
- Paiement par carte via Stripe
- Crédits automatiques via webhook
- Boutique premium dans dashboard partenaire

### ✅ Missions v11.2-v12.1 - COMPLETED
- Prix services dynamiques (Super Admin)
- Design sans cadre "Zéro Frame"
- Vidéo Full-Width sans bordures
- Système codes & crédits
- PWA installable

## Architecture

```
/app/
├── backend/
│   ├── server.py              # Backend principal (~7000 lignes - à continuer refactoring)
│   └── routes/
│       ├── auth_routes.py
│       ├── campaign_routes.py
│       ├── coach_routes.py
│       ├── promo_routes.py
│       └── reservation_routes.py
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   └── components/
│   │       ├── CoachDashboard.js  # v13.2: Optimisé (6537 lignes)
│   │       ├── dashboard/         # v13.2: NOUVEAU - Composants extraits
│   │       │   ├── CreditsGate.js
│   │       │   ├── CreditBoutique.js
│   │       │   ├── StripeConnectTab.js
│   │       │   └── index.js
│   │       ├── coach/
│   │       │   ├── CampaignManager.js
│   │       │   ├── CRMSection.js
│   │       │   └── ReservationTab.js
│   │       └── SuperAdminPanel.js
│   └── public/
│       ├── manifest.json
│       └── sw.js
└── memory/PRD.md
```

## Service Prices (Configurable by Super Admin)
- Campagnes: **2 crédits**
- Conversation IA: **1 crédit**
- Code Promo: **3 crédits**

## Key Flow - Credit Lock v13.1/v13.2

```
1. Partenaire accède à un onglet (Codes/Campagnes/Conversations)
2. Frontend: hasCreditsFor(serviceType) vérifie:
   - isSuperAdmin → true (bypass)
   - credits === -1 → true (illimité)
   - credits >= servicePrices[serviceType] → true
3. Si false: Affiche CreditsGate avec:
   - Message "Crédits insuffisants"
   - Prix requis en violet
   - Solde actuel en rouge
   - Bouton "Recharger mes crédits" → Boutique
```

## Data Status
- ✅ 22 réservations
- ✅ 7 contacts
- ✅ 4 packs crédits (Starter 49 CHF, Pro 99 CHF...)
- ✅ Video: full-width
- ✅ Service prices: campaign=2, ai_conversation=1, promo_code=3

## Pending Tasks (P0/P1)
1. **P0**: Implémenter Stripe Connect pour paiements partenaires
2. **P1**: Continuer refactoring server.py (extraire routes restantes)
3. **P1**: Continuer refactoring CoachDashboard.js (encore ~6500 lignes)
4. **P1**: Production deployment (backend actuellement preview seulement)
5. **P2**: Déduction crédits pour Chat actions (v9.5.8 incomplet)

## Super Admin Access
- Emails: `contact.artboost@gmail.com`, `afroboost.bassi@gmail.com`
- Crédits: -1 (illimité)
- Triple-click sur "© Afroboost 2026" pour login admin

## Testing Status
- Mission v13.2: 100% (12/12 backend tests, frontend validé)
- Report: `/app/test_reports/iteration_142.json`

---
Last Updated: March 2026 - Mission v13.2 VALIDATED

# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### Mission v13.8 (March 2026) - COMPLETED - RESTAURATION CHIRURGICALE
**Restauration complète des fonctionnalités Codes Promos et Conversations**

#### Corrections effectuées:
1. **editCode function** (CoachDashboard.js lignes 1194-1211): Permet d'éditer un code promo existant en chargeant ses données dans le formulaire
2. **duplicateCode function** (CoachDashboard.js lignes 1214-1231): Permet de dupliquer un code avec suffixe "_COPY"
3. **Props PromoCodesTab** (lignes 4565-4607): Toutes les props manquantes ajoutées:
   - `toggleCode`, `editCode`, `duplicateCode`
   - `uniqueCustomers`, `selectedBeneficiaries`, `toggleBeneficiarySelection`
   - `courses`, `toggleCourseSelection`, `removeAllowedArticle`
   - `batchLoading`

#### Fonctionnalités restaurées dans PromoCodesTab:
- Boutons "Éditer" et "Dupliquer" visibles sur chaque code
- Champ "Date d'expiration" (expiresAt)
- Champ "Nombre max utilisations" (maxUses)
- Sélection multiple de bénéficiaires
- Toggle Actif/Inactif fonctionnel

#### Corrections Chat (CRMSection.js):
- Fallback message: `msg.content || msg.text || msg.message || '[Message vide]'`
- Validation date: `isNaN(d.getTime()) ? '—' : d.toLocaleDateString('fr-FR')`

### Mission v13.7 (March 2026) - COMPLETED
- Fix toggleCodeActive renamed to toggleCode
- Fix code.isActive changed to code.active
- Fix empty message bubbles with fallback
- Fix Invalid Date with try/catch

### Mission v13.6 (March 2026) - COMPLETED
- Design "Zéro Cadre" appliqué
- DashboardHeader.js créé

### Missions v13.0-v13.5 - COMPLETED
- Stripe integration for credits
- Credit locking system
- Component refactoring

## Data Status (Anti-Régression Audit)
- 2 réservations
- 8 contacts
- 2 codes promos
- Video: Full-Width
- Design: "Zéro Cadre"

## Testing Status
- Mission v13.8: **100%** (11/11 tests)
- Report: `/app/test_reports/iteration_147.json`

## Pending Tasks

### P0 (Critical)
- Déploiement backend en production

### P1 (High Priority)
- Intégration Stripe Connect pour paiements partenaires
- Continuer modularisation CoachDashboard.js (4835 lignes -> objectif <3000)
- Continuer modularisation server.py

### P2 (Medium Priority)
- Déduction crédits pour actions Chat
- Investigation hook useDebounce pour personnalisation couleurs

## Super Admin Access
- Emails: `contact.artboost@gmail.com`, `afroboost.bassi@gmail.com`
- Triple-click sur "© Afroboost 2026" pour login admin

## Architecture

### Frontend Components
```
/app/frontend/src/components/
├── CoachDashboard.js         # Main dashboard (~4835 lines)
├── dashboard/
│   ├── index.js              # Exports
│   ├── PromoCodesTab.js      # v13.8: RESTORED
│   ├── CreditsGate.js
│   ├── CreditBoutique.js
│   ├── StripeConnectTab.js
│   ├── CoursesManager.js
│   ├── OffersManager.js
│   ├── ConceptEditor.js
│   ├── PageVenteTab.js
│   └── DashboardHeader.js
└── coach/
    └── CRMSection.js         # v13.8: Fixed dates/messages
```

### Backend Routes
```
/app/backend/
├── server.py                 # Main server (~3000 lines)
└── routes/
    ├── promo_routes.py
    ├── reservation_routes.py
    ├── stripe_routes.py
    ├── auth_routes.py
    ├── coach_routes.py
    └── campaign_routes.py
```

---
Last Updated: March 2026 - Mission v13.8 RESTAURATION VALIDATED

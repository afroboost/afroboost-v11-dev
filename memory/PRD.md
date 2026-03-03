# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### Mission v14.0 (March 2026) - COMPLETED - IDENTITÉ VISITEURS & BOUTONS PROMO
**Restauration de l'identité des visiteurs dans le CRM et bouton Copier**

#### Corrections effectuées:
1. **Activation IA** - `ai_config.enabled` mis à `true` via PUT `/api/ai-config`
2. **Enrichissement sessions** - Endpoints `/chat/sessions` et `/chat/conversations` enrichis avec:
   - `participantName` (nom du premier participant ou fallback sur `title`)
   - `participantEmail`
   - `lastMessage`, `messageCount`
3. **Bouton Copier** - Ajouté dans `PromoCodesTab.js`:
   - `CopyIcon` et `CheckIcon` composants SVG
   - `copyCodeToClipboard()` avec `navigator.clipboard.writeText()` + fallback
   - `data-testid="copy-code-{code.id}"` pour tests
4. **Nom du lien dans Chat** - `ChatWidget.js` affiche `sessionData.title` dans le header

#### Tests validés (100%):
- Backend: 10/10 tests passés
- Frontend: Aucune erreur console

### Mission v13.8 (March 2026) - COMPLETED
- Restauration `editCode` et `duplicateCode` fonctions
- Props complètes passées à `PromoCodesTab`
- Fonctionnalités: Édition, Duplication, Date expiration, Max uses, Sélection contacts

### Missions v13.0-v13.7 - COMPLETED
- Design "Zéro Cadre", Stripe integration, Credit system, Refactoring

## Data Status (Anti-Régression Audit v14.0)
- 2 réservations
- 8 contacts
- 2 codes promos
- 6 chat links
- AI Config: enabled=true

## Testing Status
- Mission v14.0: **100%** (10/10 tests)
- Report: `/app/test_reports/iteration_148.json`

## Pending Tasks

### P0 (Critical)
- Déploiement backend en production (risque: environnement preview)

### P1 (High Priority)
- Intégration Stripe Connect pour paiements partenaires
- Continuer modularisation CoachDashboard.js (4853 lignes -> objectif <3000)
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
├── CoachDashboard.js         # Main dashboard (~4853 lines)
├── ChatWidget.js             # Chat widget (~5311 lines)
├── dashboard/
│   ├── index.js              # Exports
│   ├── PromoCodesTab.js      # v14.0: Bouton Copier ajouté
│   ├── CreditsGate.js
│   ├── CreditBoutique.js
│   ├── StripeConnectTab.js
│   ├── CoursesManager.js
│   ├── OffersManager.js
│   ├── ConceptEditor.js
│   ├── PageVenteTab.js
│   └── DashboardHeader.js
└── coach/
    └── CRMSection.js         # v14.0: participantName enrichi
```

### Backend Routes
```
/app/backend/
├── server.py                 # Main server (~7036 lines)
│   ├── GET /api/chat/sessions   # v14.0: enrichi participantName
│   ├── GET /api/conversations   # v14.0: enrichi participantName
│   └── PUT /api/ai-config       # v14.0: enabled=true
└── routes/
    ├── promo_routes.py
    ├── reservation_routes.py
    ├── stripe_routes.py
    ├── auth_routes.py
    ├── coach_routes.py
    └── campaign_routes.py
```

### Key API Endpoints v14.0
- `GET /api/chat/sessions` - Sessions enrichies avec participantName
- `GET /api/conversations` - Conversations enrichies avec participantName
- `PUT /api/ai-config` - Activer/désactiver l'IA
- `GET /api/ai-config` - Vérifier le statut de l'IA

---
Last Updated: March 2026 - Mission v14.0 VALIDATED

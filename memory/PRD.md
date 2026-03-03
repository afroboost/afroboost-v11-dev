# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### Mission v14.3 (March 2026) - COMPLETED - LIAISON CLIENT-LIEN & CHAT PRO
**Interface chat professionnelle avec couleurs différenciées et assistant rédaction**

#### Corrections effectuées:
1. **Bulles Chat Côté Coach** (CRMSection.js):
   - Messages CLIENT: Gris foncé (`bg-gray-700/80`), aligné à GAUCHE (`justify-start`)
   - Messages COACH/IA: Violet Afroboost (`#D91CD2`), aligné à DROITE (`justify-end`)
   - Nom de l'expéditeur affiché dans chaque bulle

2. **Source du Lien** (CRMSection.js):
   - Affichage "🔗 Source : [Nom du Lien]" dans l'en-tête de conversation
   - Affichage dans la liste des conversations

3. **ChatWidget Header** (ChatWidget.js):
   - Affiche "🤖 Assistant Afroboost : **[Nom du Lien]**" quand un lien est actif
   - Ouverture automatique du chat si `linkToken` présent dans l'URL

4. **Assistant Rédaction Prompt** (CRMSection.js + server.py):
   - Bouton ✨ pour améliorer le prompt avec l'IA
   - Endpoint POST `/api/chat/enhance-prompt`
   - Fallback intelligent si IA désactivée

5. **Fix "Visiteur"** → "Client" partout

6. **Format Date**: `fr-CH` (ex: "04.03.2026, 18:30")

### Mission v14.0 (March 2026) - COMPLETED
- Activation IA (`ai_config.enabled = true`)
- Enrichissement sessions avec `participantName`
- Bouton "Copier" codes promo

### Missions v13.x - COMPLETED
- Restauration codes promos et chat
- Design "Zéro Cadre"
- Stripe credits integration

## Data Status (Anti-Régression v14.3)
- 2 réservations ✅
- 8 contacts ✅
- 2 codes promos ✅
- 8+ chat links ✅

## Testing Status
- Mission v14.3: **100% backend** (11/11), **90% frontend**
- Report: `/app/test_reports/iteration_149.json`

## Pending Tasks

### P0 (Critical)
- Déploiement backend en production

### P1 (High Priority)
- Intégration Stripe Connect pour paiements partenaires
- Ajouter titre par défaut aux liens créés sans titre
- Continuer modularisation CoachDashboard.js

### P2 (Medium Priority)
- Déduction crédits pour actions Chat
- Investigation hook useDebounce

## Super Admin Access
- Emails: `contact.artboost@gmail.com`, `afroboost.bassi@gmail.com`
- Triple-click "© Afroboost 2026" pour login admin

## Architecture

### Frontend Components
```
/app/frontend/src/components/
├── CoachDashboard.js         # Main dashboard (~4867 lines)
├── ChatWidget.js             # Chat widget (~5320 lines)
├── dashboard/
│   └── PromoCodesTab.js      # v14.0: Bouton Copier
└── coach/
    └── CRMSection.js         # v14.3: Bulles colorées, Source lien, Assistant IA
```

### Backend Routes
```
/app/backend/server.py
├── GET /api/chat/sessions       # Sessions enrichies
├── GET /api/conversations       # Conversations enrichies  
├── POST /api/chat/enhance-prompt # v14.3: Assistant IA rédaction
├── PUT /api/ai-config           # Activer/désactiver IA
└── routes/...
```

### Key CSS v14.3
```css
/* Client bubble */
bg-gray-700/80 text-white justify-start

/* Coach/IA bubble */
backgroundColor: #D91CD2 text-white justify-end
```

---
Last Updated: March 2026 - Mission v14.3 VALIDATED

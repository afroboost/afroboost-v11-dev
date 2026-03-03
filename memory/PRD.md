# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### Mission v14.5 (March 2026) - COMPLETED - VÉRIFICATION TOTALE & FIX MULTIMÉDIA
**Vérification complète du repo et corrections multimédia**

#### Corrections effectuées:
1. **Document Title Dynamique** (ChatWidget.js):
   - `document.title = "Afroboost | Chat ${sessionData.title}"` quand session active
   - Cleanup à la fermeture du chat

2. **Badge "Session Active"** (ChatWidget.js):
   - Affichage: `🤖 [Nom du Lien]` + `✓ Session Active` en dessous
   - Visible uniquement si `sessionData.title` existe

3. **Dates Uniformisées fr-CH** (CRMSection.js):
   - Toutes les dates utilisent `Intl.DateTimeFormat('fr-CH')`
   - Format: `dd.mm.yyyy, hh:mm`

4. **Campagnes Multimédia Vérifiées**:
   - `mediaUrl` stocké dans Campaign model (server.py ligne 1721)
   - `scheduler_engine.py` traite `mediaUrl` pour campagnes programmées
   - Fonctionne pour envois immédiats ET programmés

### Mission v14.3 (March 2026) - COMPLETED
- Bulles Chat: Client=Gris GAUCHE, Coach/IA=Violet DROITE
- Source du lien dans l'en-tête
- Assistant rédaction prompt (bouton ✨)
- Fix "Visiteur" -> "Client"

### Mission v14.0 (March 2026) - COMPLETED
- Activation IA, enrichissement sessions, bouton Copier

### Missions v13.x - COMPLETED
- Restauration codes promos et chat, Design "Zéro Cadre", Stripe credits

## Data Status (Anti-Régression v14.5)
- 2 réservations ✅
- 8 contacts ✅
- 2 codes promos ✅
- 8+ chat links ✅

## Testing Status
- Mission v14.5: **100% backend** (15/15), **95% frontend**
- Report: `/app/test_reports/iteration_150.json`

## Pending Tasks

### P0 (Critical)
- Déploiement backend en production

### P1 (High Priority)
- Intégration Stripe Connect pour paiements partenaires
- Ajouter titre par défaut aux liens sans titre
- Continuer modularisation CoachDashboard.js

### P2 (Medium Priority)
- Déduction crédits pour actions Chat
- Investigation hook useDebounce

## Super Admin Access
- Emails: `contact.artboost@gmail.com`, `afroboost.bassi@gmail.com`
- Triple-click "© Afroboost 2026" pour login admin

## Architecture

### Key Frontend Files
```
/app/frontend/src/components/
├── ChatWidget.js             # v14.5: document.title, badge Session Active
├── CoachDashboard.js         # Main dashboard (~4867 lines)
├── dashboard/
│   └── PromoCodesTab.js      # v14.0: Bouton Copier avec feedback
└── coach/
    └── CRMSection.js         # v14.3-14.5: Bulles colorées, dates fr-CH
```

### Key Backend Files
```
/app/backend/
├── server.py                 # Campaign mediaUrl ligne 1721
├── scheduler_engine.py       # mediaUrl pour campagnes programmées
└── routes/...
```

### Key Features Summary
| Feature | File | Lines | Status |
|---------|------|-------|--------|
| Document title | ChatWidget.js | 2849-2862 | ✅ |
| Badge Session Active | ChatWidget.js | 3689-3699 | ✅ |
| Bulles colorées | CRMSection.js | 670-685 | ✅ |
| Dates fr-CH | CRMSection.js | 310, 432, 703 | ✅ |
| Bouton Copier | PromoCodesTab.js | 459-470 | ✅ |
| Campaign mediaUrl | server.py | 1721 | ✅ |
| Scheduled mediaUrl | scheduler_engine.py | 406, 431 | ✅ |

---
Last Updated: March 2026 - Mission v14.5 VALIDATED

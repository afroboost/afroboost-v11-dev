# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### Mission v14.6 (March 2026) - COMPLETED - RECHERCHE & MOTS-CLÉS
**Recherche par mots-clés côté client et stabilité campagnes**

#### Nouvelles fonctionnalités:
1. **Recherche Offres Côté Client** (CoachVitrine.js):
   - Champ de recherche avec loupe (🔍) visible si > 1 offre
   - Filtrage instantané par nom, description ou keywords
   - Message "Aucune offre ne correspond" si pas de résultat
   - Bouton ✕ pour effacer la recherche

2. **Mots-clés Offres** (OffersManager.js):
   - Champ "Mots-clés (pour la recherche)" dans le formulaire
   - Séparés par virgules: "fitness, musculation, perte de poids"

3. **Campagnes Multimédia Vérifiées**:
   - mediaUrl stocké et traité pour envois directs ET programmés
   - scheduler_engine.py lignes 406, 431, 480

### Mission v14.5 (March 2026) - COMPLETED
- Document title dynamique, badge Session Active
- Dates fr-CH uniformisées

### Mission v14.3 (March 2026) - COMPLETED
- Bulles Chat: Client=Gris GAUCHE, Coach/IA=Violet DROITE
- Source du lien, Assistant rédaction prompt

### Missions v14.0-v13.x - COMPLETED
- Activation IA, bouton Copier, design Zéro Cadre, Stripe credits

## Data Status (Anti-Régression v14.6)
- 2 réservations ✅
- 8 contacts ✅
- 3 offres ✅
- 2 codes promos ✅
- 8+ chat links ✅

## Testing Status
- Mission v14.6: **100% backend** (16/16), **100% frontend**
- Report: `/app/test_reports/iteration_151.json`

## Pending Tasks

### P0 (Critical)
- Déploiement backend en production

### P1 (High Priority)
- Intégration Stripe Connect pour paiements partenaires
- Titre par défaut pour liens sans titre
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
├── CoachVitrine.js           # v14.6: Recherche offres par keywords
├── ChatWidget.js             # v14.5: document.title, badge Session Active
├── CoachDashboard.js         # Main dashboard
├── dashboard/
│   ├── OffersManager.js      # v14.6: Champ keywords
│   └── PromoCodesTab.js      # v14.0: Bouton Copier
└── coach/
    └── CRMSection.js         # v14.3-14.5: Bulles colorées, dates fr-CH
```

### Key Backend Files
```
/app/backend/
├── server.py                 # Offer model keywords ligne 430
├── scheduler_engine.py       # mediaUrl lignes 406, 431, 480
└── routes/...
```

### v14.6 Search Feature
```javascript
// CoachVitrine.js
const filteredOffers = searchTerm 
  ? offers.filter(offer => {
      const nameMatch = offer.name?.toLowerCase().includes(searchTerm);
      const descMatch = offer.description?.toLowerCase().includes(searchTerm);
      const keywordsMatch = offer.keywords?.toLowerCase().includes(searchTerm);
      return nameMatch || descMatch || keywordsMatch;
    })
  : offers;
```

---
Last Updated: March 2026 - Mission v14.6 VALIDATED

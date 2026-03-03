# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### Mission v14.7 (March 2026) - COMPLETED - ÉTANCHÉITÉ CONTACTS
**Étanchéité des données multi-partenaires + validation recherche**

#### Nouvelles fonctionnalités:
1. **Filtrage coach_id sur tous les endpoints** (server.py):
   - GET /chat/sessions : Filtré par coach_id (ligne 4350)
   - GET /conversations : Filtré par coach_id (ligne 4440)
   - GET /chat/participants : Filtré par coach_id (ligne 3968)
   - POST /chat/generate-link : coach_id tatoué sur la session (ligne 5190)

2. **Règles d'étanchéité**:
   - Super Admin (`is_super_admin`) : Voit TOUT
   - Partenaires : Voient uniquement leurs données (`coach_id == email`)

3. **Recherche validée** (CoachVitrine.js):
   - Case-insensitive avec `toLowerCase()` (lignes 864-869)
   - Bouton ✕ réinitialise la liste

4. **Campagnes multimédia**:
   - Scheduler persiste en MongoDB (`status: scheduled`)
   - `object-fit: cover` pour images Samsung

### Mission v14.6 (March 2026) - COMPLETED
- Recherche offres par mots-clés côté client

### Missions v14.0-14.5 - COMPLETED
- Activation IA, bouton Copier, document.title, badge Session Active
- Bulles colorées, dates fr-CH, Source du lien

## Data Status (Anti-Régression v14.7)
- 2 réservations ✅
- 8 contacts ✅
- 3 offres ✅
- 8+ chat links ✅

## Testing Status
- Mission v14.7: **100% backend** (19/19), **100% frontend**
- Report: `/app/test_reports/iteration_152.json`

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

### Étanchéité Multi-Partenaires (v14.7)
```python
# server.py - Règle d'étanchéité
if is_super_admin(caller_email):
    # Super Admin voit TOUT
    query = {}
else:
    # Partenaire voit uniquement ses données
    query["coach_id"] = caller_email
```

### Endpoints avec coach_id
| Endpoint | Méthode | Filtrage |
|----------|---------|----------|
| /chat/sessions | GET | ✅ coach_id |
| /conversations | GET | ✅ coach_id |
| /chat/participants | GET | ✅ coach_id |
| /chat/generate-link | POST | ✅ coach_id ajouté |

### Key Frontend Files
```
/app/frontend/src/components/
├── CoachVitrine.js           # v14.6-14.7: Recherche case-insensitive
├── ChatWidget.js             # v14.5: document.title, badge
├── CoachDashboard.js         # Main dashboard
└── coach/
    └── CRMSection.js         # v14.3: Bulles colorées, dates fr-CH
```

---
Last Updated: March 2026 - Mission v14.7 VALIDATED

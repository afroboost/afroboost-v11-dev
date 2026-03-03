# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### ✅ Mission v11.7 (March 2026) - COMPLETED
**Logique Multi-Partenaires & Flux Intelligent**
1. **Identification par Email** - Chaque vitrine partenaire liée à un email unique
2. **Flux Reels Dynamique** - Scroll vertical seulement si >1 partenaire actif
3. **Protection Super Admin** - Double-clic désactivé sur vidéos SA (play/pause uniquement)
4. **Scroll vers Offres** - Bouton Réserver scrolle vers section offres sans redirection

### ✅ Mission v11.5 (March 2026) - COMPLETED
**Date/Heure Réservation & Sécurité**
- Affichage date/heure dans confirmation (format français avec année)
- Bouton X ferme le bloc de confirmation
- Protection données intacte

### ✅ Mission v11.4 (March 2026) - COMPLETED
**Système de Codes & Crédits Chat**
- Validation code crée abonnement avec séances
- Bloc info abonnement (offre + solde + validité)
- Déduction automatique à la réservation

### ✅ Mission v11.2 (March 2026) - COMPLETED
**Prompts Indépendants & PWA**
- Isolation totale des custom_prompts par lien
- PWA installable (manifest + service worker)

## Architecture

```
/app/
├── backend/
│   ├── server.py
│   ├── routes/
│   │   ├── promo_routes.py      # Subscription system
│   │   ├── reservation_routes.py # Auto-deduct sessions
│   │   ├── auth_routes.py
│   │   ├── coach_routes.py
│   │   └── campaign_routes.py
│   └── shared.py
├── frontend/
│   ├── src/
│   │   ├── App.js
│   │   ├── components/
│   │   │   ├── CoachVitrine.js     # Partner storefront
│   │   │   ├── CoachDashboard.js   # Partner management
│   │   │   ├── PartnersCarousel.js # Main Reels feed (v11.7)
│   │   │   └── ChatWidget.js       # Chat + subscription info
│   │   └── services/
│   │       └── SoundManager.js
│   └── public/
│       ├── manifest.json
│       └── sw.js
└── memory/PRD.md
```

## Key Logic (v11.7)

### Super Admin Protection
```javascript
const SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
const isSuperAdminVideo = SUPER_ADMIN_EMAILS.some(email => email.toLowerCase() === partnerEmail);
// Double-clic sur SA -> play/pause uniquement, pas de navigation
```

### Conditional Scroll
```javascript
// Scroll activé UNIQUEMENT si >1 partenaire
className={`${filteredPartners.length > 1 ? 'overflow-y-auto' : 'overflow-hidden'}`}
```

## Pending Tasks (P0/P1)
1. **P0**: Stripe Connect for partner payouts
2. **P1**: Production deployment
3. **P1**: Continue modularizing server.py

## Super Admin Access
- Emails: `contact.artboost@gmail.com`, `afroboost.bassi@gmail.com`
- Login: Triple-click footer "© Afroboost 2026"

## Testing Status
- Mission v11.7: 10/10 pytest tests PASS
- Data: 21 réservations, 14 contacts intacts
- Report: `/app/test_reports/iteration_136.json`

---
Last Updated: March 2026 - Mission v11.7 VALIDATED

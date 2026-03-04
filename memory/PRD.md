# Afroboost - Product Requirements Document

## Original Problem Statement
Multi-partner SaaS platform for fitness coaching with a mobile-first, "Instagram Reels" style vertical video feed. Super Admin (Bassi) manages partners who can customize their own storefronts.

## Core Features Implemented

### Mission v15.1 (March 2026) - COMPLETED - VALIDATION COMPLÈTE
**Pont lien-chat et campagnes omnicanal - VALIDATION 100%**

#### Validations effectuées:
1. **Pont Lien → Chat** (server.py lignes 3596-3616):
   - `link_token` charge le `custom_prompt` spécifique
   - Mode STRICT activé → ISOLATION TOTALE du contexte
   - Aucune donnée de vente si custom_prompt présent

2. **Campagnes → Chat** (server.py lignes 1717-1727):
   - Messages insérés dans `chat_messages`
   - `sender_type='coach'`, `sender_name='Coach Bassi'`
   - Client voit le message dans son chat

3. **Source Affichée** (CRMSection.js lignes 420-423, 649-652):
   - "🔗 Source : [Nom du Lien]" visible dans Dashboard Coach
   - Via `session.title`

4. **Calendrier** (fix v14.8):
   - `daysUntilCourse < 0` (pas `<= 0`)
   - ChatWidget.js ligne 1807 ✅
   - BookingPanel.js ligne 23 ✅

5. **Couleurs Chat** (CRMSection.js lignes 680-685):
   - Client: `bg-gray-700/80` GAUCHE ✅
   - Coach/IA: `#D91CD2` DROITE ✅

6. **Bouton Copier** (PromoCodesTab.js ligne 79):
   - `navigator.clipboard.writeText()` + fallback `execCommand('copy')`

7. **Recherche Mots-clés** (CoachVitrine.js lignes 864-869):
   - Filtrage par nom, description, ET keywords

8. **Super Admin** (server.py lignes 290-298):
   - `is_super_admin()` → Pas de filtre `coach_id`

### Missions précédentes - COMPLETED
- v15.0: Système connecté, participantName mis à jour
- v14.8: Calendrier réaligné
- v14.7: Étanchéité contacts
- v14.6: Recherche mots-clés
- v14.3-14.5: Bulles colorées, Source lien, document.title

## Data Status (Anti-Régression v15.1)
- 20+ réservations ✅
- 8+ contacts ✅
- 17+ sessions chat ✅
- 17+ chat links ✅

## Testing Status
- Mission v15.1: **100% backend** (18/18), **100% frontend**
- Report: `/app/test_reports/iteration_155.json`

## Pending Tasks

### P0 (Critical)
- Déploiement backend en production

### P1 (High Priority)
- Intégration Stripe Connect pour paiements partenaires

### P2 (Medium Priority)
- Déduction crédits pour actions Chat
- Modularisation CoachDashboard.js

## Super Admin Access
- Emails: `contact.artboost@gmail.com`, `afroboost.bassi@gmail.com`
- Triple-click "© Afroboost 2026" pour login admin

## Architecture - Pont Lien → Chat

### Flux complet
```
CLIENT                          BACKEND                         DASHBOARD
   |                               |                               |
   | Clique ?link=bavard           |                               |
   |------------------------------>|                               |
   |                               | Récupère session bavard       |
   |                               | avec custom_prompt            |
   |                               |                               |
   | Saisit Nom/Email              |                               |
   |------------------------------>|                               |
   |                               | POST /chat/smart-entry        |
   |                               | Met à jour participantName    |
   |                               |                               |
   | Envoie message                |                               |
   |------------------------------>|                               |
   |                               | Mode STRICT activé            |
   |                               | ISOLATION TOTALE              |
   |                               | Répond avec custom_prompt     |
   |<------------------------------|                               |
   |                               |                               |
   |                               |            Source: bavard     |
   |                               |------------------------------>|
```

---
Last Updated: March 2026 - Mission v15.1 VALIDATION COMPLÈTE

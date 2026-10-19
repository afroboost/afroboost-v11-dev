# Documentation maîtresse Afroboost

Établie le 19/10/2026 à partir du code réel (`afroboost-v11-dev` `0a575c9b`, BoostTribe `215c18b`) et de la production en
lecture seule. **Aucune modification du produit, de la base ou de la production n'a été faite pour la produire.**

| Document | Contenu |
|---|---|
| [PRD.md](PRD.md) | vision, utilisateurs, 22 modules, user stories, critères d'acceptation, questions produit |
| [TRD.md](TRD.md) | architecture, stack, auth, paiements, e-mails, WhatsApp, IA, schedulers, sécurité, environnements, décisions |
| [APP_FLOW.md](APP_FLOW.md) | tous les parcours (visiteur, essai, membre, événement, coach, partenaire, prospection, Live) et leurs états |
| [UI_UX_DESIGN_BRIEF.md](UI_UX_DESIGN_BRIEF.md) | audit du design actuel et référence UI de tout le site |
| [BACKEND_SCHEMA.md](BACKEND_SCHEMA.md) | schéma réel (109 collections) et schéma cible recommandé (crédits, droits, audit) |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | lots priorisés P0 → P3, chacun avec risque, rollback et critère GO/NO-GO |
| [modules/live/LIVE_AUDIT.md](modules/live/LIVE_AUDIT.md) | audit détaillé d'Afroboost Live / BoostTribe (crédits, permissions, coûts, réutilisation) |
| [annexes/SCHEMA_MONGO_REEL.md](annexes/SCHEMA_MONGO_REEL.md) | relevé brut des collections, champs, types et index de production (aucune valeur) |

Règle de mise à jour : la source de vérité reste le produit en production ; ces documents doivent être corrigés à chaque
lot livré (section concernée + date).

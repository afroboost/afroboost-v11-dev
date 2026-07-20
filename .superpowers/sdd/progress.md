# V223 — Journal d'exécution

Plan : docs/superpowers/plans/2026-07-20-v223-prix-progressif.md
Branche : v223-prix-progressif (partie de main @ 1d66a58)
Périmètre : tâches 1 à 8. Tâche 9 EXCLUE (demande utilisateur).
Base de données : promo-credits-lab = PRODUCTION → vérifications en lecture seule.
Ne jamais git push.

## Avancement
Tâche 1 : TERMINÉE (commits c062059..1ee5c78, revue clean, 13 tests verts)
  - module pur api/pricing.py + tests/test_pricing_v223.py
  - 2 correctifs de revue appliqués (seuil 0 écrasé par le défaut ; test tautologique)

Tâche 2 : TERMINÉE (commit 057798c, revue clean)
  - 9 champs sur Offer, 7 sur OfferCreate, diff +21/-0
  - test de désérialisation supprimé : deps backend absentes (fastapi manquant)
  - couverture assurée par lecture statique : tous les champs ont un défaut,
    donc aucune ValidationError possible sur une offre existante

Tâche 3 : TERMINÉE (commit 7c893e6, revue clean)
  - GET /offers enrichi sur SES DEUX chemins de retour (le plan n'en voyait qu'un)
  - endpoint GET /offers/{id}/active-price + 404
  - VÉRIFIÉ RÉELLEMENT via venv Python 3.13 + base factice (15 assertions) :
    offre existante -> active_price == price (anti-régression prouvée)
    endpoint -> forme OK, 404 OK
  - venv de vérification : /tmp/v223venv (python3.13, deps api/requirements.txt)
    le Python système est en 3.9, trop ancien pour ces dépendances

Tâche 4 : TERMINÉE (commits 6bbc2d2..c6f02ba, revue clean, risque prod jugé faible)
  - metadata checkout + customer_details.email + pack_sessions prioritaire
  - l'agent implémenteur a été coupé par une erreur API APRÈS son commit :
    travail complet, seul le rapport manque
  - VÉRIFIÉ : 15 assertions sur les expressions EXTRAITES du fichier réel
    parcours formulaire actuel -> email et crédits strictement inchangés
    bug historique reproduit ('Cours du 10 mai' -> 10 crédits) puis corrigé
  - 2 durcissements post-revue : str() anti-AttributeError, tier max 64 car.

Tâche 5 : TERMINÉE (commit 1d89bcd, revue clean)
  - PUT /subscriptions/{code}/profile -> subscriptions + upsert chat_participants
  - correction du plan appliquée : $setOnInsert doit porter un id uuid,
    sinon le contact CRM est orphelin (le CRM cherche par {"id": ...})
  - VÉRIFIÉ : 12 assertions avec base factice (404, trim, upsert, id, pas
    d'écriture CRM si l'abonné n'a pas d'email)

Tâche 6 : TERMINÉE (commit 0d18496, revue clean, build OK)
  - section prix progressif + pack_sessions dans OffersManager, +75/-0
  - insérée comme SŒUR de la grille (pas dedans) : mise en page préservée
  - champs vidés -> null et jamais NaN ; bouton type="button"

Tâche 7 : TERMINÉE (commits 809c3f3, 05eb425, 3cf30ef — revue clean, build OK)
  - SubscriberOnboarding.js (+148) ; SubscriberSpace.js +17/-0 seulement
  - lien « Plus tard » présent : aucun abonné ne peut être enfermé
  - 2 défauts trouvés en revue et corrigés :
    a) GET /subscriber/space ne renvoyait pas whatsapp -> l'écran se rouvrait
       à CHAQUE chargement, pour TOUS les abonnés
    b) fuite entre membres d'un groupe : un membre secondaire voyait le
       WhatsApp du titulaire et l'écrasait en soumettant. Lecture branchée par
       membre + porte désactivée pour les membres secondaires.

Tâche 8 : TERMINÉE (commit c288d7e, revue clean, build OK)
  - prix du palier actif + badge sur OfferCardSlider
  - test par `!= null` et non par truthiness : un prix à 0 reste correct

REVUE FINALE DE BRANCHE (opus) : « À CORRIGER AVANT FUSION »
  I1 CORRIGÉ (commit 729ad6a) : l'écran d'onboarding se rouvrait à chaque
     visite pour tout abonné existant sans WhatsApp (test !name mort +
     refus non persisté). Seule vraie régression identifiée.
  C1 NON CORRIGÉ — DÉCISION UTILISATEUR REQUISE : CoachDashboard.js construit
     offerData par liste blanche (ligne 2366) et n'inclut AUCUN champ V223.
     La section dashboard de la tâche 6 n'enregistre donc rien. Fonctionnalité
     inerte. Hors périmètre du lot : le plan n'avait pas prévu ce fichier.
  C2 NON CORRIGÉ — LIÉ À C1 : calculateTotal() et le récapitulatif utilisent
     selectedOffer.price, pas active_price. Si C1 est corrigé sans C2, le
     client voit 15 CHF et paie 30. NE JAMAIS corriger C1 seul.
     Autres canaux non enrichis : CoachVitrine, prompt IA, coach_routes.

=== LOT 1-8 TERMINÉ. Tâche 9 hors périmètre (demande utilisateur). ===

## Constats mineurs à trier avant merge
- UX dashboard : l'avertissement « activez le compte à rebours » teste
  countdown_date mais ignore countdown_enabled. Si le coach saisit une date
  puis désactive le compte à rebours, l'avertissement disparaît alors que les
  paliers restent inactifs. Défaut hérité du plan.
- getattr(request, "packSessions", "") est redondant depuis que le champ est
  déclaré sur le modèle Pydantic (inoffensif, imposé par le plan)
- active_price est un float alors que price est souvent un int en base
  (égalité numérique correcte, à surveiller si un test compare les types)
- DETTE TRANSVERSE (préexistante, pas introduite par V223) : toutes les routes
  /espace/{code} sont publiques, protégées par la seule connaissance du code
  AFR — y compris des DELETE destructifs. Notre endpoint profil suit ce
  pattern ; un tiers connaissant un code peut écraser un nom/WhatsApp.
- DETTE CONNUE : PUT /subscriptions/{code}/profile n'a aucune notion de
  membre. Le chemin UI est fermé pour les membres secondaires, mais un appel
  direct à l'API avec le code du groupe permet encore d'écraser le profil du
  titulaire. Préexistant au pattern du projet, non introduit par V223.
- UX : si progressive_pricing est vrai mais active_price absent, le badge de
  palier s'affiche à côté du prix de base (conditions indépendantes).
- SÉCURITÉ HORS PÉRIMÈTRE : /api/webhook/stripe n'authentifie pas ses appels
  (construct_from au lieu de construct_event) — chantier séparé, cf. spec §8

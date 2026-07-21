# V225 — Journal d'exécution

Plan : docs/superpowers/plans/2026-07-21-v225-cartes-completes.md
Spec : docs/superpowers/specs/2026-07-21-v225-cartes-completes-design.md
Branche : v225-cartes-completes (depuis main @ 31cdeb7, V224 fusionné)
Périmètre : tâches 1 à 7.
Règle absolue utilisateur : NE SUPPRIMER AUCUN CODE EXISTANT (tout est additif).
Ne pas pousser sans demande explicite de l'utilisateur.

## Avancement
(en cours)

## Constats mineurs à trier avant merge
- DETTE SÉCURITÉ (préexistante, AGGRAVÉE en exposition par la tâche 7) :
  PUT /courses/{id}, PUT /courses/{id}/archive et DELETE /courses/{id} n'ont
  aucun contrôle de propriétaire ; POST /courses accepte un coach_id arbitraire ;
  require_auth ne lit qu'un en-tête déclaratif sans jeton. Mettre l'édition de
  cours dans le wizard rend la faille bien plus atteignable. Chantier dédié.
- DETTE héritée V224 : PUT /offers/{id} sans contrôle de propriétaire.
- GET /courses n'a aucun filtre par coach (limite 100) ; l'endpoint vitrine
  limite à 20 et ne filtre ni archived ni visible.

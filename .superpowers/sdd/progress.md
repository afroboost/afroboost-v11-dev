# V226 — Journal d'exécution

Plan : docs/superpowers/plans/2026-07-21-v226-correctifs.md
Spec : docs/superpowers/specs/2026-07-21-v226-correctifs-design.md
Branche : v226-correctifs (depuis main @ 01e710a, V225 fusionné)
Règle absolue : NE SUPPRIMER AUCUN CODE EXISTANT. Ne pas pousser sans demande.

## Décisions prises avec le propriétaire avant exécution
- BUG 4 : le DnD n'était PAS câblé sur les nouvelles cartes (handlers sur
  l'ancien rendu, sous {false && ...}). Décision : câbler d'abord, masquer
  les flèches ensuite.
- BUG 5 : le wizard ne sait ni supprimer ni archiver un horaire, et les
  horaires laissés en visible:false par une session abandonnée (correction
  V225) n'avaient CoursesManager que comme recours. Décision : rendre le
  wizard autonome AVANT de masquer la section.
- Frais de port et TVA : jamais ajoutés à calculateTotal, donc pas facturés
  aujourd'hui. Hors périmètre, l'achat direct n'aggrave rien.
- isAudio n'est consommé nulle part : les achats audio peuvent passer en direct.

## Avancement
(en cours)

## Constats mineurs à trier avant merge
(aucun pour l'instant)

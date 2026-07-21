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

## Décision ajoutée en cours de lot (après revue de la tâche 4)
TÂCHE 7 AJOUTÉE : le passage des produits en achat direct supprimait leur
document `reservations`. Vérifié en revue : shipping_details n'est lu par AUCUN
code backend, les variant_* par AUCUN composant frontend, et ReservationTab
identifie une commande produit par selectedVariants/trackingNumber/shippingStatus
— tous issus de ce document. Un coach vendant des t-shirts n'aurait plus pu
traiter ses commandes depuis Afroboost. Décision : recopier la commande depuis
le webhook. Vaut aussi pour audio/vidéo.

## Avancement
Tâches 1+2 : TERMINÉES (commits 6e7eb0b, 40351a2 — revue clean, builds OK)
  - bouton « Réserver » seul en quantité 1 ; total + (Nx) au-delà
  - 6 icônes SVG (horloge, pin, personnes) sur carte publique et dashboard
  - relecteur a confirmé intacts : stopPropagation du lien Maps, repli
    startsWith('http'), != null sur max_participants, garde checkoutBusy

Tâche 3 : TERMINÉE (commit 2ba2805, revue clean sans réserve, 21/21 tests)
  - collectShipping + variants sur CreateCheckoutRequest
  - **v226_shipping construit UNE fois avant le try, passé aux DEUX
    Session.create : la divergence par duplication (mode de défaillance
    rattrapé en V224) est rendue impossible par construction
  - préfixe variant_ : une variante ne peut PAS écraser pack_sessions,
    tier ni quantity — la règle V223 tient
  - pire cas metadata calculé : 19 clés / 28 car. de clé / 100 car. de valeur,
    contre 50 / 40 / 500 autorisés

(en cours)

## Constats mineurs à trier avant merge
- OfferCard.js:124,134 — icône tracée en #aaa alors que le texte porteur est
  en #ccc. Invisible avec les emoji colorés, visible en SVG monochrome.
- les SVG n'ont ni shrink-0 ni aria-hidden (hygiène, pas de défaut actuel)
- ClockIcon extraite mais non utilisée dans dashboard/OfferCard.js (no-unused-vars
  n'est pas activé dans ce projet, donc aucun avertissement)

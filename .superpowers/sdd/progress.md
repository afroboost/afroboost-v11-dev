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

TÂCHE 8 AJOUTÉE (décision propriétaire après revue tâche 6) : masquer la
section Cours faisait perdre 3 fonctions sans équivalent — dupliquer un cours,
« Demander un avis » et le toggle d'avis automatique. La 2e est le SEUL appelant
de POST /api/reviews/request dans tout le frontend : l'endpoint devenait
injoignable. Décision : les reporter dans le wizard.
CORRECTION D'UNE PRÉMISSE FAUSSE DE MA PART : CoursesManager n'a JAMAIS eu de
suppression, seulement archivage et visibilité. La suppression ajoutée au wizard
est un ajout net, pas un rattrapage.

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

Tâche 4 : TERMINÉE (commits c14fa46, 3126415, + commentaire — re-revue clean)
  - v225IsDirectCheckout élargi à tout ce qui est payant ; 0 CHF garde le formulaire
  - sélecteur de variantes, bouton bloqué tant qu'une dimension manque
  - défauts trouvés en revue et corrigés :
    (1) l'implémenteur a fermé de lui-même un trou hors brief : la RACINE de la
        carte partait chez Stripe SANS variantes, contournant le bouton désactivé
    (2) MEDIUM le nettoyage cours/dates du slider produits sautait pour les
        offres à variantes -> une réservation gratuite ultérieure pouvait
        hériter d'un courseId et d'une date périmés. Resets déplacés dans
        startProgressiveCheckout, donc sur TOUS les chemins d'entrée.
    (3) clic racine silencieux quand une variante manque -> scrollIntoView + flash
    (4) commentaire faux : il affirmait que tous les appelants sont des achats
        produit/audio/video sans cours, or le slider SERVICES passe par là

Tâche 5 : TERMINÉE (commit 33674ce, revue clean, build OK)
  - DnD câblé sur OfferCard (il ne l'était PAS : les handlers vivaient sur
    l'ancien rendu sous {false && ...})
  - reorderGridOffers opère sur orderedOffers (l'ordre AFFICHÉ) et jamais sur
    l'état brut — le piège identifié en revue V224
  - glisser désactivé sous recherche active (grille partielle = positions fausses)
  - isOwnOffer appliqué à DEUX niveaux : attribut draggable + revérification
  - handleDrop v159 conservé, rattaché à l'ancien rendu

GATE NON FRANCHI : le masquage des flèches ▲▼ attend la vérification manuelle
du DnD (souris + session coach), impossible depuis cet environnement. Tâche 6
faite SANS masquer les flèches.

Tâche 6 : correctifs appliqués (commits 79e15df, 20a910a), re-revue en cours
  - wizard : suppression, republication d'un horaire masqué, badge « masqué »
  - section Cours masquée par la constante SHOW_COURSES_SECTION
  - revue avait rendu NON APPROUVÉ, défauts corrigés :
    (H-1) BLOQUANT un horaire supprimé restait proposé au rattachement ->
          PUT 404 -> l'OFFRE ENTIÈRE ne s'enregistrait plus, sans indice.
          Prop onCoursesChanged câblée jusqu'à CoachDashboard.setCourses.
    (M-1) supprimer un horaire partagé rend d'autres offres silencieusement
          non réservables -> avertissement ajouté au confirm
    (M-2) 4 commentaires renvoyaient vers CoursesManager, voie disparue
    (B-1) bouton Archiver retiré du rendu : GET /courses filtre archived,
          donc un archivé disparaissait sans retour à la fermeture du wizard
  - DÉVIATION VALIDÉE de l'implémenteur sur B-2 : ma consigne littérale aurait
    rendu non restaurable un horaire créé puis archivé dans la même session
    (archiveCourse purge sessionOwnedCourseIds)

Tâche 6 : TERMINÉE (re-revue clean)
Tâche 7 : TERMINÉE (commits 0808099 + 537936d)
  - webhook recopie shipping_details + variantes dans reservations, upsert
    $setOnInsert sur stripe_session_id (Stripe rejoue ses webhooks)
  - AUCUN Session.retrieve ajouté : le piège de la clé partenaire est contourné
    en lisant l'objet session de l'événement, pas résolu
  - revue a rendu NON CONFORME : le webhook écrivait une donnée que RIEN ne
    pouvait lire. Complété : projection GET /reservations, affichage dans
    ReservationTab, recâblage du suivi d'expédition.
  - 2 prises importantes du complément :
    (a) isProduct valait VRAI pour d'anciennes réservations de cours
        (shippingStatus absent -> undefined !== 'pending'). Y accrocher le bloc
        aurait affiché un formulaire de colis sur des réservations de cours.
        -> hasShippingData() exige une preuve positive.
    (b) updateTracking était INCOMPATIBLE : setReservations(res.data) alors que
        l'API renvoie {data, pagination} -> la page aurait planté au premier
        changement de statut. Doublé par updateTrackingV226.
Tâche 8 : TERMINÉE (commit 1e4124f, revue clean)
  - duplication, demande d'avis et toggle d'avis auto reportés dans le wizard
  - duplication respecte la règle V225 : visible:false, publié à l'enregistrement
  - CONSTAT : le toggle d'avis automatique n'émet AUCUNE requête, il n'écrit
    que dans localStorage. Aucun code backend ne le lit, le cron ne peut pas
    lire un localStorage. Réglage sans effet réel, AVANT comme APRÈS. Préexistant.

=== LOT V226 : 8 TÂCHES TERMINÉES. Revue finale de branche à suivre. ===
GATE EN ATTENTE : masquage des flèches ▲▼, subordonné à la vérification
manuelle du glisser-déposer par le propriétaire.

## Constats mineurs à trier avant merge
- OfferCard.js:124,134 — icône tracée en #aaa alors que le texte porteur est
  en #ccc. Invisible avec les emoji colorés, visible en SVG monochrome.
- les SVG n'ont ni shrink-0 ni aria-hidden (hygiène, pas de défaut actuel)
- ClockIcon extraite mais non utilisée dans dashboard/OfferCard.js (no-unused-vars
  n'est pas activé dans ce projet, donc aucun avertissement)

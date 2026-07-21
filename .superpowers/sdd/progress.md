# V225 — Journal d'exécution

Plan : docs/superpowers/plans/2026-07-21-v225-cartes-completes.md
Spec : docs/superpowers/specs/2026-07-21-v225-cartes-completes-design.md
Branche : v225-cartes-completes (depuis main @ 31cdeb7, V224 fusionné)
Périmètre : tâches 1 à 7.
Règle absolue utilisateur : NE SUPPRIMER AUCUN CODE EXISTANT (tout est additif).
Ne pas pousser sans demande explicite de l'utilisateur.

## Avancement
Tâche 1 : TERMINÉE (commit 4f20892, revue clean, 21/21 tests verts)
  - 3 champs label_* symétriques sur Offer et OfferCreate
  - tests/test_offer_labels_v225.py, analyse AST (FastAPI absent en local)
  - relecteur a vérifié que le test n'est pas tautologique : il échoue bien si
    un champ manque d'un seul côté ou est mal orthographié

Tâche 2 : TERMINÉE (commits 5b4f8d7, 08a74f8 — re-revue clean, 21/21 tests)
  - quantity 1..5 bornée serveur, appliquée aux DEUX Session.create
  - crédits = pack_sessions × quantité
  - défaut MAJEUR trouvé en revue et corrigé : la quantité était relue via
    list_line_items avec la clé Stripe GLOBALE, alors que le checkout lit
    partner_payment_config EN PRIORITÉ. Chemin nominal, pas cas limite : dès
    qu'une clé dashboard diffère de l'env, tout acheteur de N recevait les
    crédits de 1. Basculé sur metadata — mécanisme déjà établi par V223 pour
    pack_sessions — posé serveur, relu ET re-borné au webhook.
  - PIÈGE DOCUMENTÉ : `amount` doit être UNITAIRE dès que quantity > 1. Deux
    appelants envoient un TOTAL (App.js:4438 et 4488) ; seul le parcours
    d'achat direct envoie un unitaire. À NE PAS oublier en tâche 4.

Tâche 3 : TERMINÉE (commit f62393a, revue clean, 21/21 tests)
  - bouton « Réserver ma séance » vers /espace/{code} dans l'email post-paiement
  - enrichissement active_price/active_tier sur l'endpoint vitrine
  - import retenu : coach_routes -> api.pricing (PAS api.server, qui importe
    déjà coach_routes ligne 35 : l'inverse aurait créé un cycle)
  - try/except PAR OFFRE : une offre corrompue n'en emporte pas 19 autres
  - relecteur a vérifié que le bloc email est HORS du try existant, donc la
    sûreté vient de ce que l'ajout est du texte pur, sans await ni accès payload

Tâche 4 : TERMINÉE (commits 28cc250, cb6fe56, ab76328, + dedup — re-revue clean)
  - achat direct pour les offres de service payantes, showSessions = false
    (calcul d'origine conservé sous showSessionsLegacy)
  - 2 BLOQUANTS trouvés en revue et corrigés :
    (1) CRITIQUE tous les produits physiques devenaient INACHETABLES. Le modèle
        Offer (server.py:366) ne déclare AUCUN champ `type` et OfferCreate est
        en extra="ignore" : le test `offer.type === 'product'` valait TOUJOURS
        faux pour une offre de la base. Défaut préexistant mais franchissable ;
        showSessions=false a supprimé l'échappatoire. Formulaire jamais ouvert,
        adresse de livraison inatteignable.
    (2) offres de service à 0 CHF dans la même impasse, double verrou.
  - helper v225IsDirectCheckout extrait en portée module = point de décision
    UNIQUE, appelé par handleSelectOffer ET (tâche 5) par le bouton de la carte
  - courseName : une offre de service gratuite était libellée « Produit
    physique » dans le ticket, l'email client et la vue coach

Tâche 5 : TERMINÉE (commits e99d8bc, 66354d5 — re-revue clean, build OK)
  - OfferCardSlider : lieu GPS cliquable, horaires, 3 paliers, quantité, gap 16px
  - sélecteur de quantité CONDITIONNÉ à v225IsDirectCheckout : sinon le bouton
    annoncerait un total que le parcours ne facturerait pas (produit/gratuit)
  - défauts trouvés en revue et corrigés :
    (1) href={mapsUrl || '#'} + target=_blank ouvrait un ONGLET VIDE quand
        mapsUrl est absent — or il vaut "" par défaut et les cours seedés
        l'ont vide : c'était le cas le plus fréquent. URL de recherche Maps.
    (2) deux formats de prix dans la même carte (CHF 20.- vs 20.00 CHF)
    (3) CARD_WIDTH sur-comptait 12px (box-sizing: border-box via preflight)
    (4) lieu affiché 2x si offer.location ET cours lié
    (5) mapsUrl injecté brut dans href -> garde startsWith('http')
  - parité EXACTE avec le pré-V225 confirmée pour tout prix entier

Tâche 6 : TERMINÉE (commits 1b80fed + correctifs — revue clean, build OK)
  - PROGRESSIVE_TIERS étendue (labelKey + placeholder), pas dupliquée
  - les QUATRE zones vérifiées par le relecteur sur le code : état initial,
    offerData, startEditOffer, cancelEditOffer ET reset post-création
  - relecteur a aussi confirmé qu'aucune autre voie d'écriture n'efface les
    libellés : handleToggleVisible passe par updateOffer (objet complet)
  - 2 correctifs : badge de palier figé sur V223_TIERS alors que la grille
    juste en dessous affichait le libellé personnalisé ; .trim() manquant

Tâche 7 : TERMINÉE (commits d0f6201, 0d67564, feca138 — revue clean, build OK)
  - horaires éditables dans l'étape 2 : nom, jour, heure, lieu, Maps
  - écart assumé et validé en revue : ajout d'un sélecteur « rattacher un cours
    existant », sans quoi un horaire délié par erreur devenait inatteignable
  - défauts trouvés en revue et corrigés :
    (1) MOYEN un horaire créé puis abandonné restait PUBLIC sur la vitrine
        (POST au clic avec visible: true). Créé masqué, publié à l'enregistrement.
    (2) linkedCourses construit depuis la prop brute, pas filtrée par coach ->
        cours d'un autre coach pleinement éditable. Lecture seule hors périmètre.
    (3) clic rapide Ajouter puis Enregistrer -> cours orphelin
  - ERREUR DE MA CONSIGNE, rattrapée : forcer visible:true sur TOUS les cours
    persistés republiait un horaire délibérément masqué par le coach. Corrigé :
    seuls les cours créés dans la session sont publiés ; pour les autres la clé
    `visible` n'est pas envoyée du tout ($set partiel = valeur en base intacte).

=== LOT V225 : 7 TÂCHES TERMINÉES ===

REVUE FINALE DE BRANCHE (opus) : « À CORRIGER AVANT FUSION » — 3 bloquants nés
ENTRE les tâches. Tous corrigés :
  B1 (3182571) « + Ajouter un horaire » TOTALEMENT INOPÉRANT. Jonction de deux
     de mes propres consignes : créer l'horaire masqué (pour qu'un abandon ne
     soit pas public) + lecture seule hors visibleCourses. Le cours créé n'étant
     pas dans la prop `courses` du parent, il s'affichait « 🔒 lecture seule »,
     n'entrait pas dans toPersist, et restait donc invisible À JAMAIS — tout en
     apparaissant sur la carte publique via linked_course_ids.
     L'implémenteur a ajouté sessionOwnedCourseIds car sessionCreatedCourseIds
     est vidé après le PUT : si l'offre échouait ensuite, le bug revenait.
  B2 (83959f2) la carte publique exposait les horaires MASQUÉS et ARCHIVÉS
     (jour, heure, adresse). linkedCourses lisait `courses` brut au lieu de
     baseCourses. GET /courses ne filtre pas `visible`, l'endpoint vitrine ne
     filtre ni visible ni archived. Régression de confidentialité.
  B3 (1ff88c5) la confirmation affichait le PRIX UNITAIRE après un débit :
     3 × 20 CHF prélevés, « Paiement confirmé — CHF 20.- » affiché.
  C4 (fc243f0) v225FormatAmount appliqué au grand prix, aux paliers, et au
     montant de confirmation devenu total donc potentiellement fractionnaire.

CHAÎNE D'ACHAT VALIDÉE DE BOUT EN BOUT par le relecteur final : montant affiché
= montant facturé = crédits accordés = ce que le client peut consommer.

## Constats mineurs à trier avant merge
- DETTE SÉCURITÉ (préexistante, AGGRAVÉE en exposition par la tâche 7) :
  PUT /courses/{id}, PUT /courses/{id}/archive et DELETE /courses/{id} n'ont
  aucun contrôle de propriétaire ; POST /courses accepte un coach_id arbitraire ;
  require_auth ne lit qu'un en-tête déclaratif sans jeton. Mettre l'édition de
  cours dans le wizard rend la faille bien plus atteignable. Chantier dédié.
- email du flux ADMIN MANUEL (server.py:4222) toujours sans lien /espace/ :
  le client reçoit un email sans bouton de réservation. Ticket séparé.
- coach_routes.py:479 duplique _enrich_offers_with_active_price (server.py:1152).
  Déplacer le helper dans api/pricing.py dans un lot ultérieur.
- v225FormatAmount non appliqué au grand prix ni aux paliers : un prix
  fractionnaire donne « CHF 19.5.- » au-dessus de « 19.50 CHF ». Sans effet
  sur les offres actuelles (toutes à prix entier).
- CARD_WIDTH n'est pas recalculé au resize/rotation (préexistant).
- PRÉEXISTANT, hors périmètre : une offre vidéo (type 'video', price > 0) ouvre
  le formulaire mais handleSubmit la rejette en silence — ni produit physique,
  ni audio, ni gratuite, donc elle exige un cours et des dates. Jamais réparé
  par l'achat direct puisque la vidéo est classée « produit ».
- list_line_items résiduel (server.py:3873, PRÉEXISTANT) : même fragilité de
  clé Stripe pour le repli sur product_name. Gravité faible (atteint seulement
  si product_name vide, or il est obligatoire sur le modèle). Ticket séparé.
- DETTE héritée V224 : PUT /offers/{id} sans contrôle de propriétaire.
- GET /courses n'a aucun filtre par coach (limite 100) ; l'endpoint vitrine
  limite à 20 et ne filtre ni archived ni visible.

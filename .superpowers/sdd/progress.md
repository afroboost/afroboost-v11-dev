# V224 — Journal d'exécution

Plan : docs/superpowers/plans/2026-07-21-v224-refonte-ui.md
Spec : docs/superpowers/specs/2026-07-21-v224-refonte-ui-design.md
Branche : v224-refonte-ui (partie de origin/main @ 4d04985, V223 fusionné)
Périmètre : tâches 1 à 6.
Base de données : PRODUCTION → vérifications en lecture seule. Ne jamais git push.
Règle absolue utilisateur : NE SUPPRIMER AUCUN CODE EXISTANT (tout est additif).

## Avancement
Tâche 1 : TERMINÉE (commit 27ddc1e, revue clean, 17/17 tests verts)
  - 3 champs symétriques sur Offer et OfferCreate, test AST tests/test_offer_fields_v224.py
  - invariant $set/extra="ignore" confirmé fermé par le relecteur

Tâche 2 : TERMINÉE (commit 412976f, revue clean, build OK)
  - 5 champs dans les 4 zones : état initial, offerData, startEditOffer, 2 resets
  - ?? et non || sur les 2 entiers ; v223Int(val, null) laisse passer un 0 légitime
  - bug linked_course_ids confirmé réel par le relecteur (case cochée -> jamais envoyée)

Tâche 3 : TERMINÉE (commits 34ddb15, e83cdcb, 3ce5443 — re-revue clean, build OK)
  - OfferWizard.js : modal 3 étapes, 27 champs, state local, onSave unique
  - 5 défauts trouvés en revue et corrigés :
    (1) IMPORTANT inputs variants contrôlés sur valeur normalisée -> la virgule
        était détruite à la frappe, une seule variante saisissable. State brut.
    (2) IMPORTANT overlay onClick -> une sélection de texte relâchée hors panneau
        fermait le modal et perdait 20 champs. Passé en onMouseDown + test cible.
    (3) IMPORTANT bouton « Aide IA » sans équivalent -> fonctionnalité inatteignable
        une fois l'ancien formulaire masqué. Prop optionnelle onEnhanceDescription.
    (6) focus invisible ; .neon-input inutilisable (border !important au repos)
        -> nouvelle classe .v224-input dans App.css, purement additive, focus seul
    (7) preview vidéo : ajout youtu.be, Vimeo, URL YouTube avec paramètres
  - DETTE : youtube.com/shorts/ID non reconnu par la preview (cosmétique)

À CÂBLER IMPÉRATIVEMENT EN TÂCHE 4 (sinon régressions silencieuses) :
  - isSuperAdmin + coachEmail : sans eux, un coach non-admin voit les cours des AUTRES coachs
  - onEnhanceDescription : sans elle, le bouton Aide IA reste inerte
  - initialOffer={newOffer} (référence stable, jamais {{...newOffer}})

Tâche 4 : TERMINÉE (commits 79aa5db, dda6e8e, 3af7049 — re-revue clean, build OK)
  - OfferCard.js + grille 2 colonnes + montage du wizard dans OffersManager
  - addOffer refactorisé : accepte des valeurs en argument, renvoie un booléen.
    Chemin onSubmit de l'ancien formulaire vérifié intact (3 return seulement).
  - 3 props critiques câblées : isSuperAdmin/coachEmail (sinon fuite entre
    locataires), onEnhanceDescription (sinon Aide IA inatteignable)
  - défauts trouvés en revue et corrigés :
    (1) IMPORTANT le wizard se fermait avant de savoir si le POST/PUT avait
        réussi -> 3 étapes de saisie irrécupérables en cas d'échec réseau
    (2) IMPORTANT glisser-déposer de réorganisation (position) inatteignable
        -> boutons ▲/▼ sur les cartes, persistOfferOrder partagé avec handleDrop
    (3,4,5) nom affiché 2x, « undefined CHF », affordance « 🔒 Protégée » perdue
    (6) le wizard sautait à l'étape 1 pendant l'enregistrement (setNewOffer
        changeait la référence de initialOffer) -> ligne retirée

Tâche 5 : TERMINÉE (commits 2e0d3a8, 7ebad16 — re-revue clean, build OK)
  - startProgressiveCheckout + gardes sur handleSelectOffer et showSessions
  - NON-RÉGRESSION DÉMONTRÉE par le relecteur : membre gauche de showSessions
    strictement booléen, activeOffer null -> garde neutre. Offre classique ->
    chute sur le « v56: Toggle » d'origine, inchangé ligne pour ligne.
  - chaîne de livraison du code AFR remontée et validée de bout en bout :
    customer_details.email (3767) + pack_sessions relu en base depuis offerId
  - défauts trouvés en revue et corrigés :
    (1) IMPORTANT réservation FANTÔME : pendingReservation survit à un abandon
        de checkout ; un client qui abandonne un parcours classique puis achète
        une offre progressive voyait le ticket de l'ancienne offre ET créait une
        réservation parasite avec notification au coach. removeItem ajouté.
    (2) IMPORTANT aucun retour visuel + double-clic -> N sessions Stripe.
        Garde de ré-entrance if (loading) return.

Tâche 6 : TERMINÉE (commits a632c3c, de731bc, e3d7e1e — re-revue clean, build OK)
  - OfferCardSlider INLINE d'App.js (le bon des 3 composants homonymes)
  - getNextOccurrences retourne des Date natives, PAS des {label} : le code du
    plan aurait affiché « Mon Jul 27 2026 00:00:00 GMT+0200 ». Formaté via formatDate.
  - défauts trouvés en revue et corrigés :
    (1) IMPORTANT le lock d'orientation ne pouvait JAMAIS marcher : branché sur
        loadedmetadata avec preload="metadata", donc au chargement de page, hors
        plein écran où l'API rejette toujours. Ratio mémorisé en ref, lock APRÈS
        résolution du plein écran, unlock sur fullscreenchange + au démontage.
    (2) IMPORTANT parseMediaUrl détectait par SOUS-CHAÎNE : une image dont l'URL
        contient « .mov » devenait un <video> noir sans repli. Extension exigée
        en fin de chemin, avant ? et #.
    (3) routage dupliqué -> divergence réelle sur le slider produits (le bouton
        court-circuitait setSelectedCourse(null)). Un seul point de vérité.
    (4) le bloc prix réimplémentait v223UnitPrice -> appel de la fonction
    (5) pas de repli si la vidéo échoue -> onError vers la branche image

=== LOT V224 : 6 TÂCHES TERMINÉES ===

REVUE FINALE DE BRANCHE (opus) : « À CORRIGER AVANT FUSION » — 4 bloquants, tous
nés ENTRE les tâches, donc invisibles aux revues individuelles. Tous corrigés :
  B1 (06eeb07) CRITIQUE : le client qui payait une offre progressive atterrissait
     sur l'écran de connexion PARTENAIRE. L'heuristique isPartnerPayment
     distinguait coach/client par la PRÉSENCE de pendingReservation ; le
     correctif anti-réservation-fantôme de la tâche 5 efface cette clé. L'effet
     partenaire s'exécutant en premier supprimait status et session_id de l'URL,
     si bien qu'AUCUN ticket n'était affiché. Marqueur dédié + confirmation client.
  B2 (e5f32ac) `position` remis à null à chaque enregistrement depuis le wizard
     (absent des 2 listes blanches). V224 en faisait le cœur de la boucle d'usage :
     le coach rangeait ses offres, en modifiait une, elle sautait en fin de
     grille ET de vitrine publique.
  B3 (06eeb07) le loading GLOBAL désactivait toutes les cartes après un retour
     bfcache depuis Stripe -> boutique entière morte. État checkoutBusy dédié
     + écouteur pageshow.
  B4 (06eeb07, 67073ff) participants_count n'existe dans AUCUN modèle : un cours
     complet affichait « 0/50 ». Remplacé par une capacité « 50 places ».
  A  (f9000ba) la vente progressive s'affichait « Client — — 0 CHF » au dashboard.
     Webhook enrichit payment_transactions (email réel + montant).
  B  (56466db) flèches ▲▼ actives sur les offres d'autres coachs -> isOwnOffer.

RE-REVUE DES CORRECTIFS : 1 NOUVEAU bloquant, né de la JONCTION de B1 et B3.
  (e9662a5) Le marqueur progressif n'était effacé sur aucun chemin d'abandon
     (onglet fermé, retour navigateur). Il survivait, et l'achat CLASSIQUE
     suivant était pris pour un progressif : finalizeReservation jamais appelé,
     le client payait sans réservation créée, sans ticket, coach non notifié.
     La réservation en attente prime désormais ; retour classique purge le marqueur.

## Constats mineurs à trier avant merge
- SÉCURITÉ (préexistante, hors périmètre) : PUT /offers/{id} ne vérifie que
  require_auth, sans contrôle de propriétaire — contrairement à DELETE. La
  grille affiche les offres des autres coachs, et un clic sur ▲ déclenche un
  $set sur toutes celles dont la position change. Comportement identique au
  DnD v159, mais désormais atteignable d'un simple tap. Tâche backend dédiée.
- bfcache (PRÉEXISTANT, touche AUSSI le parcours classique) : setLoading(true)
  puis window.location.href sans reset ; un retour navigateur depuis Stripe
  restauré depuis le bfcache laisse loading=true et le bouton inerte pour la
  session. Aucun listener pageshow/persisted dans App.js. Ticket séparé.
- parcours progressif : aucun code promo applicable (pas de formulaire) — à
  valider comme choix produit
- retour de paiement progressif : ticket générique « Réservation Afroboost »,
  totalPrice '-', sans mention du code AFR ni du lien /espace/<code>
- OfferCardSlider : prop startProgressiveCheckout relayée mais non consommée
  (aiguillage centralisé dans handleSelectOffer) — commentaire ajouté, prop
  conservée pour ne rien retirer hors périmètre
- une offre EXISTANTE portant linked_course_ids affichera désormais la ligne
  « Prochaine séance » : seul changement visible sur des offres déjà en prod
- OfferCard : libellés en dur (« Masquer », « Active ») non internationalisés,
  alors que l'ancienne liste utilisait t('visible')
- attributs data-testid (edit-offer-*, delete-offer-*, offer-keywords) sortis
  du DOM rendu ; test_reports/ y fait référence
- conteneur scrollable maxHeight 500px de l'ancienne liste non repris
- accordéon horaires par offre non repris (lien cours↔offre reste éditable
  dans l'étape 2 du wizard)
- preview vidéo du wizard : youtube.com/shorts/ID non reconnu (cosmétique)
- handleDrop calcule depuis `offers` brut alors que la grille affiche
  `orderedOffers` : inoffensif tant que l'ancien rendu est sous {false && …}
- la grille du dashboard trie tout ensemble, la vitrine trie produits et
  services séparément : un coach mêlant les deux ne voit pas un miroir exact

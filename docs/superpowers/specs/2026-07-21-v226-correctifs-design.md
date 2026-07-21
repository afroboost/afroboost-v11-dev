# V226 — Correctifs UI et paiement unifié

Date : 2026-07-21
Branche : `v226-correctifs` (depuis `main` @ `01e710a`, V225 fusionné)
Statut : design validé

## Objectif

Corriger cinq problèmes remontés après la mise en production de la V225 :
prix affiché deux fois, produits physiques hors du parcours Stripe, emoji au lieu
d'icônes SVG, réorganisation des offres, et gestion des horaires dispersée.

## Règle absolue

Tout est additif, marqueur `// V226` (JS) ou `# V226` (Python). Aucune suppression.
Aucune écriture en base hors des chemins existants. Chat, codes AFR, codes promo,
espace client et paiements doivent continuer à fonctionner.

## État des lieux (vérifié dans le code)

Quatre vérifications ont corrigé le cahier des charges initial :

- **Le drag & drop n'est PAS câblé sur les nouvelles cartes.**
  `components/dashboard/OfferCard.js` ne porte aucun handler. Ceux de
  `OffersManager.js` (l.483, l.598) sont sur l'ancien rendu en liste, placé sous
  `{false && (…)}` par la V224 : c'est du code mort. Masquer les flèches sans câbler
  le DnD priverait le coach de tout moyen de réordonner, or l'ordre pilote
  l'affichage public.
- **Le wizard ne sait ni supprimer ni archiver un horaire.** `deleteCourse` et
  `archiveCourse` vivent dans `CoursesManager`. De plus, la correction V225 laisse un
  horaire créé puis abandonné en `visible: false` **définitivement** ; le seul recours
  documenté était précisément `CoursesManager`. Masquer la section sans combler ces
  manques rendrait ces horaires irrécupérables.
- **Les frais de port ne sont pas perdus** : `calculateTotal` ne les a jamais ajoutés
  (`shippingCost` n'entre dans aucun calcul de total). Ils ne sont pas facturés
  aujourd'hui ; l'achat direct n'aggrave rien. Hors périmètre.
- **`isAudio` n'est consommé nulle part** — ni backend, ni dashboard. Faire passer les
  achats audio en direct ne perd aucune donnée exploitée.

## Chantier 1 — Prix affiché une seule fois

`OfferCardSlider` (`App.js` ~l.1874). Le bouton affiche `Réserver` seul quand la
quantité vaut 1, et `Réserver — {total} CHF ({n}x)` au-delà. Le prix du corps de carte
est conservé : c'est lui qui porte l'information tarifaire.

## Chantier 2 — Paiement unifié

`v225IsDirectCheckout` devient : toute offre de prix strictement positif part en
checkout Stripe. Seules les offres à 0 CHF conservent le formulaire — Stripe refuse un
montant nul, c'est une limite de plateforme.

Conséquences assumées, validées par l'état des lieux :
- les produits physiques y passent, avec `shipping_address_collection` côté Stripe
  (pays : CH, FR, DE, IT, AT, BE) ;
- les achats audio et vidéo y passent également ; `isAudio` n'étant lu nulle part,
  aucune donnée exploitée n'est perdue.

### Variantes

Si une offre porte des variantes (`variants.sizes` / `colors` / `weights`), un sélecteur
apparaît sur la carte **avant** le bouton. La sélection est transmise au backend et
recopiée dans les `metadata` Stripe (`variant_size`, `variant_color`…), afin que le
coach sache quoi expédier.

### Backend

`CreateCheckoutRequest` reçoit `collectShipping: bool = False` et
`variants: Optional[dict] = None`. `create_checkout_session` construit ses paramètres de
session dans un dictionnaire, y ajoute `shipping_address_collection` si demandé, et
recopie les variantes dans les metadata.

**Contrainte impérative** : les DEUX appels `stripe.checkout.Session.create` (chemin
nominal et fallback carte-seule) doivent recevoir le même traitement. Le fallback se
déclenche pour tout compte sans TWINT actif ; l'oublier ferait perdre l'adresse de
livraison sur ces comptes.

## Chantier 3 — Icônes SVG

Remplacer les emoji `⏱`, `📍`, `👥` par des SVG inline, sur la carte publique
(`OfferCardSlider`) et sur la carte du dashboard (`components/dashboard/OfferCard.js`).
Le pin GPS reste cliquable vers Google Maps, avec son `stopPropagation` — sans lui, le
clic déclencherait l'achat.

## Chantier 4 — Réorganisation par glisser-déposer

Câbler le glisser-déposer sur `components/dashboard/OfferCard.js` : `draggable`,
`onDragStart`, `onDragOver`, `onDrop`, `onDragEnd`, curseur `grab` / `grabbing` et
retour visuel pendant le déplacement. Réutiliser `persistOfferOrder` déjà en place, qui
n'écrit que les offres dont la position change réellement.

L'ordre de référence est `orderedOffers` (tri par `position`), celui qui est affiché —
et non l'état `offers` brut, sur lequel l'ancien `handleDrop` calculait.

Les flèches ▲▼ ne sont masquées **qu'une fois le glisser-déposer vérifié fonctionnel**.

Limite connue et acceptée : le glisser-déposer HTML5 ne répond pas au doigt sur mobile.
La réorganisation se fera depuis un ordinateur.

## Chantier 5 — Wizard autonome sur les horaires

Avant de masquer la section « Cours », combler les manques du wizard :

- **Supprimer / archiver** un horaire, en réutilisant les endpoints existants.
  Distinguer clairement cette action du simple délien, qui ne touche pas la base.
- **Badge « masqué » et republication** pour les horaires en `visible: false` — ce sont
  ceux qu'une session de wizard abandonnée a laissés derrière elle. Sans ce recours,
  ils sont irrécupérables une fois la section masquée.

La section « Cours » du dashboard n'est masquée qu'ensuite. `CoursesManager.js` reste
intact dans le code.

## Risques et parades

| Risque | Parade |
|---|---|
| Réorganisation impossible | DnD câblé et vérifié AVANT de masquer les flèches |
| Horaires masqués irrécupérables | Republication ajoutée au wizard AVANT de masquer la section |
| Adresse de livraison perdue sur un compte sans TWINT | `shipping_address_collection` sur les DEUX `Session.create` |
| Coach ne sait pas quoi expédier | Variantes recopiées dans les metadata Stripe |
| Clic sur le pin GPS déclenchant l'achat | `stopPropagation` conservé |
| Offre à 0 CHF cassée | Exclue de l'achat direct, formulaire conservé |

## Hors périmètre

- `shippingCost` et `tva`, qui n'entrent dans aucun calcul de total aujourd'hui.
  Les facturer serait un changement de comportement, pas un correctif.
- Le montant du checkout calculé côté client : faiblesse préexistante documentée
  depuis V223.
- Le contrôle de propriétaire sur `PUT /offers/{id}`, `PUT /courses/{id}` et
  `DELETE /courses/{id}` : dette connue, chantier backend dédié.
- Le glisser-déposer tactile sur mobile.
- L'audit `pack_sessions` en base, à mener par le propriétaire.

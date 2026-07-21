# V225 — Cartes d'offres complètes, achat direct et cours dans le wizard

Date : 2026-07-21
Branche : `v225-cartes-completes` (depuis `main`, V224 fusionné en `31cdeb7`)
Statut : design validé

## Objectif

1. Chaque carte d'offre publique affiche tout : lieu géolocalisé, horaires, compte à
   rebours, les 3 paliers de prix, un sélecteur de quantité.
2. La section « Horaires pour… » disparaît. Toutes les offres éligibles partent
   directement en paiement Stripe ; le client réserve ensuite depuis `/espace/<code>`,
   via un lien reçu par email.
3. Le coach gère les horaires depuis le wizard de l'offre, sans passer par une autre
   section du dashboard.
4. Le coach peut renommer les 3 paliers de prix.

## Règle absolue — non-régression

Tout est additif, marqueur `// V225` (JS) ou `# V225` (Python). Aucune suppression.
Codes AFR-XXXXXX, chat, Stripe/TWINT/PayPal inchangés.

## État des lieux (vérifié dans le code)

Constats qui conditionnent le design et corrigent le cahier des charges initial :

- **`frontend/src/components/CoachVitrine.js` est du code mort.** Son import est
  commenté (`App.js:55-56`), aucun fichier ne le monte. Les pages partenaires sont
  rendues par `App.js` lui-même (mode vitrine, `App.js:3194-3246`). « Même design
  partout » est donc acquis sans travail : c'est le même composant.
- **`OfferCard` (`App.js:1127-1223`) est du code mort** : jamais rendu. Seul
  `OfferCardSlider` (`App.js:1255-1678`) porte le rendu réel, monté deux fois —
  offres (`:5617`) et shop (`:5866`).
- **L'endpoint vitrine n'enrichit pas les offres.** `coach_routes.py:475-476` lit
  `db.offers.find(...)` sans passer par `_enrich_offers_with_active_price`
  (`server.py:1138-1156`, appliqué au seul `GET /offers`). Sur une page partenaire,
  `active_price` et `active_tier` sont absents et `v223UnitPrice` retombe sur
  `offer.price` : **les paliers ne s'afficheraient jamais correctement**.
- **La sélection de dates n'existe qu'à `App.js:4573-4576`**, dans `renderDates`,
  rendu sous `showSessions` (`:5554-5558`, seul consommateur `:5561`). C'est pourquoi
  masquer cette section impose de basculer l'achat en direct.
- **`App.js:4166`** bloque toute offre non-produit sans date sélectionnée.
- **L'email post-paiement** (`server.py:3919-3921`) pointe vers `?qr={code}` (le chat).
  Aucun lien `/espace/{code}` n'y figure.
- **`PUT /courses/{id}`** (`server.py:1020-1035`) accepte un dictionnaire libre, n'a
  **aucun contrôle de propriétaire**, et ignore les valeurs `None` — donc un champ ne
  peut pas être vidé. `require_auth` (`:115-128`) ne lit qu'un en-tête déclaratif.
- **`POST /courses`** (`:1007-1018`) n'assigne `coach_id` depuis l'en-tête que si le
  corps n'en fournit pas : un client peut en poster un arbitraire.
- Le webhook accorde les crédits depuis `pack_sessions` (`server.py:3792-3800`),
  **sans notion de quantité**.

## Périmètre de l'achat direct

| Type d'offre | Parcours |
|---|---|
| Service / cours, prix > 0 | **Achat direct Stripe** (nouveau) |
| Produit physique (`isProduct` / `isPhysicalProduct`) | **Inchangé** — formulaire + adresse de livraison |
| Offre à 0 CHF | **Inchangé** — Stripe refuse un montant nul |

Les deux exclusions sont des contraintes de plateforme, pas des choix esthétiques.

## Sélecteur de quantité

Sur la carte, un sélecteur 1 à 5. Prix affiché = quantité × prix du palier actif.

La quantité est transmise à Stripe via le champ `quantity` de la ligne de commande —
`unit_amount` reste le prix unitaire. Le récapitulatif Stripe montre donc « 3 × 15 CHF ».

### Les crédits doivent suivre la quantité

C'est le point critique de cette version. Le webhook accorde aujourd'hui
`pack_sessions` crédits, quelle que soit la quantité. Un client achetant 3 packs de 10
paierait 3 fois et recevrait 10 crédits.

`sessions_count` devient donc `pack_sessions × quantité`.

**La quantité est relue côté serveur**, jamais acceptée du client au moment du webhook :
elle est lue sur la session Stripe via `stripe.checkout.Session.list_line_items`, comme
le fait déjà le repli sur `product_name` (`server.py:3785-3793`). C'est la continuité
directe de la règle posée en V223 : le serveur fait autorité sur les crédits.

À l'entrée de `create-checkout-session`, la quantité reçue est **bornée à 1..5** côté
serveur. Un client peut poster ce qu'il veut ; le plafond n'est pas côté interface.

## Chantier 1 — Carte publique complète

Fichier unique : `OfferCardSlider` (`App.js:1255-1678`).

Ajouts, chacun **masqué si sa donnée est absente** — les offres existantes ne portent
aucun de ces champs et ne doivent afficher ni ligne vide ni « undefined » :

- **Lieu** : icône GPS SVG inline (pas d'image externe), lieu cliquable ouvrant
  `mapsUrl` dans un nouvel onglet, avec `stopPropagation` pour ne pas déclencher la
  sélection de l'offre.
- **Horaires** : un par cours lié, `Jour · Heure`.
- **Compte à rebours** : `OfferCountdown` est déjà rendu (`:1640`) ; vérifier sa
  présence, ne pas le recréer.
- **3 paliers** : boîtes côte à côte, palier actif mis en évidence et coché, inactifs
  estompés. Libellés personnalisés avec repli sur « Prévente » / « Standard » /
  « Dernière min. ».
- **Quantité** : sélecteur 1-5.
- **Espacement** : `gap: 16px`, largeur minimale 280px mobile / 320px desktop.

Les offres sont enrichies de `linkedCourses` aux deux points de montage
(`App.js:5617` et `:5866`) en croisant `linked_course_ids` avec `courses`.

## Chantier 2 — Suppression de la section horaires

- `showSessions` (`App.js:5554-5558`) forcé à `false`. Le bloc `sessionsBlock`
  (`:5561-5602`) reste dans le fichier, non rendu.
- `handleSelectOffer` route vers le checkout direct toute offre **non produit et de
  prix strictement positif**. Les deux autres cas conservent leur chemin actuel, y
  compris le blocage `:4166` qui les renvoie vers le formulaire.

## Chantier 3 — Email avec lien de réservation

Dans l'email post-paiement (`server.py:3919+`), ajouter un bouton « Réserver ma
séance » vers `https://afroboost.com/espace/{code}`. Le QR et le lien chat existants
sont conservés : l'ajout est additif.

## Chantier 4 — Cours dans le wizard

L'étape 2 remplace les cases à cocher (`OfferWizard.js:449-492`) par des blocs
éditables : nom, jour, heure, lieu, lien Maps. Ajout via `POST /courses`, retrait par
délien (le cours n'est jamais supprimé de la base), modifications appliquées par
`PUT /courses/{id}` à l'enregistrement du wizard.

Contrainte connue : `PUT /courses/{id}` ignore les valeurs `None`. Un champ vidé par le
coach doit donc être envoyé en chaîne vide, pas en `null`, sinon la modification est
silencieusement ignorée.

`CoursesManager.js` n'est pas touché et reste accessible.

## Chantier 5 — Libellés de paliers personnalisables

Trois champs sur `Offer` **et** `OfferCreate`, symétriquement :

```python
label_early_bird: Optional[str] = None    # V225
label_standard: Optional[str] = None      # V225
label_last_minute: Optional[str] = None   # V225
```

La symétrie est imposée par `PUT /offers` qui fait `$set: offer.model_dump()` sur un
modèle en `extra="ignore"` : un champ absent d'`OfferCreate` est effacé en base à
chaque sauvegarde. Même invariant qu'en V224.

Ajoutés au wizard (étape 1), à la liste blanche `offerData` de `CoachDashboard.js`, et
lus par la carte.

## Chantier 6 — Enrichissement de l'endpoint vitrine

`coach_routes.py:475` passe les offres par `_enrich_offers_with_active_price`, sans
quoi les paliers restent inertes sur les pages partenaires.

## Risques et parades

| Risque | Parade |
|---|---|
| Crédits non multipliés par la quantité | `sessions_count = pack_sessions × quantité`, quantité relue sur la session Stripe |
| Quantité forgée par le client | Bornée 1..5 côté serveur |
| Champs `label_*` effacés au `$set` | Déclarés sur `Offer` **et** `OfferCreate` |
| Produits physiques sans adresse | Exclus de l'achat direct, parcours inchangé |
| Offres gratuites cassées | Exclues de l'achat direct, parcours inchangé |
| Codes promo inatteignables | `allowPromotionCodes` activé sur les achats directs |
| Paliers morts chez les partenaires | Enrichissement de l'endpoint vitrine |
| Lignes vides sur les offres existantes | Chaque ligne masquée quand sa donnée est absente |

## Hors périmètre

- `CoachVitrine.js` et `OfferCard` (`App.js:1127`) : code mort, non modifiés.
- **Dette de sécurité signalée, non traitée ici** : `PUT /courses/{id}`,
  `PUT /courses/{id}/archive` et `DELETE /courses/{id}` n'ont aucun contrôle de
  propriétaire, et `POST /courses` accepte un `coach_id` arbitraire. Préexistant, mais
  mettre l'édition de cours en avant dans le wizard rend la faille nettement plus
  atteignable. Chantier backend dédié recommandé, même famille que la dette
  `PUT /offers` héritée de V224.
- Le montant du checkout reste calculé côté client : faiblesse préexistante documentée
  en V223, volontairement non aggravée.
- Les codes promo du dashboard coach (`discount_codes`) restent distincts des codes du
  Dashboard Stripe.

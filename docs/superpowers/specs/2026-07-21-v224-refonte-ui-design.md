# V224 — Refonte UI : dashboard des offres + page d'accueil

Date : 2026-07-21
Branche : `v224-refonte-ui` (depuis `main`, V223 fusionné via PR #1 `4d04985`)
Statut : design validé

## Objectif

Rapprocher l'interface d'Afroboost de celle de spordateur.com sur deux fronts :

1. **Dashboard coach** — remplacer le long formulaire vertical de création/modification
   d'offre par un modal en 3 étapes, et présenter les offres en cartes visuelles.
2. **Page d'accueil** — pour les offres à prix progressif (V223), supprimer la grille
   d'horaires et envoyer directement le client vers Stripe ; refondre les cartes
   publiques (média, métadonnées, bouton Réserver).

## Règle absolue — non-régression

Tout est additif. Aucun code existant n'est supprimé. Chaque ajout porte le marqueur
`// V224`.

Une offre **sans** `progressive_pricing` ne rencontre aucune des nouvelles gardes :
son parcours d'achat reste bit-pour-bit celui d'aujourd'hui (grille d'horaires,
formulaire client, `handleSubmit`, choix carte/TWINT). Les codes AFR-XXXXXX, le chat,
et les intégrations Stripe/TWINT/PayPal sont inchangés.

`frontend/src/components/SubscriberSpace.js` n'est pas touché.

## État des lieux (vérifié dans le code)

Constats établis avant rédaction, qui conditionnent le design :

- `api/server.py` porte tout V223 : `progressive_pricing`, `price_early_bird`,
  `price_standard`, `price_last_minute` (l.405-412, 439-445), `pack_sessions`, et
  l'enrichissement serveur `active_price` / `active_tier` (l.1127-1145).
  Le dossier `/backend/` est du code mort (non déployé) et ne les a pas.
- **`videoUrl` existe déjà** dans `Offer` (l.371) et `OfferCreate` (l.423), mais n'est
  jamais rempli par l'UI. Réutilisable sans migration.
- **`PUT /offers/{offer_id}` (l.1199-1242) fait `$set: offer.model_dump()`** — un
  remplacement complet. Tout champ absent de `OfferCreate` est **effacé à chaque
  sauvegarde**. C'est la raison pour laquelle V223 avait dû déclarer ses champs, et
  la contrainte centrale de cette spec.
- **Bug existant** : `linked_course_ids` est coché dans le formulaire mais absent de la
  liste blanche `offerData` (`CoachDashboard.js` l.2391-2426) — donc jamais envoyé par
  `addOffer`. Les cours associés à la création sont silencieusement perdus.
- `frontend/src/components/OfferCard.js` (racine) existe mais est **du code mort**
  (0 consommateur). Non touché ; le nouveau composant vit sous `dashboard/`.
- La page d'accueil ne l'utilise pas : elle rend `OffersSliderAutoPlay` →
  `OfferCardSlider`, **définis inline dans `App.js`** (l.1230-1458).
- Les 3 inputs `variants` de `OffersManager.js` (l.891-917) n'ont pas de `value=` :
  non contrôlés, jamais pré-remplis en édition.
- Le webhook Stripe a déjà le repli V223 (l.3755) :
  `customer_details.email` → `customer_email` → `metadata`, avec un commentaire visant
  explicitement « le parcours sans formulaire ».
- `CheckoutRequest.customerEmail` est `Optional[str] = None` (l.3323) et est passé tel
  quel à Stripe (l.3438, et l.3487 dans le fallback carte-seule).

## Architecture

| Fichier | Statut | Rôle |
|---|---|---|
| `frontend/src/components/dashboard/OfferWizard.js` | **neuf** | Modal 3 étapes (ES6+) |
| `frontend/src/components/dashboard/OfferCard.js` | **neuf** | Carte d'offre dashboard (ES6+) |
| `frontend/src/components/dashboard/OffersManager.js` | modifié | Rend la grille de cartes, monte le wizard |
| `frontend/src/components/CoachDashboard.js` | modifié | Liste blanche `offerData`, état d'ouverture du wizard |
| `frontend/src/App.js` | modifié | Chantiers 3 et 4 |
| `api/server.py` | modifié | 3 champs sur `Offer` **et** `OfferCreate` |

`ChatWidget.js` n'est pas concerné : la contrainte ES5 stricte ne s'applique donc pas.
Les nouveaux composants suivent le style ES6+ du dossier `dashboard/`.

## Chantier 0 — Migration backend

Sur `Offer` (~l.371) **et** `OfferCreate` (~l.423), **symétriquement** :

```python
duration_minutes: Optional[int] = None    # V224
location: Optional[str] = ""              # V224
max_participants: Optional[int] = None    # V224
```

La symétrie n'est pas cosmétique : un champ déclaré sur `Offer` mais pas sur
`OfferCreate` serait effacé au premier `PUT` — c'est-à-dire au premier toggle
actif/inactif depuis une carte (Chantier 2).

`videoUrl` est déjà déclaré des deux côtés : rien à ajouter.

Aucune migration de données. Les offres existantes lisent `None` / `""`, et chaque
ligne d'affichage se masque quand sa donnée est absente.

## Chantier 1 — Wizard 3 étapes

Nouveau composant `OfferWizard.js`, utilisé pour la **création** et la **modification**.

### Modèle d'état

Le wizard tient un state local unique, initialisé depuis l'offre en édition (ou vide
en création). Il ne remonte au parent **qu'une seule fois**, à l'enregistrement — donc
une seule requête POST/PUT, exactement comme aujourd'hui.

### Répartition des champs

**Étape 1 — Bases**
`name` (requis), `price`, toggle `progressive_pricing` + les 3 paliers
(`price_early_bird`, `price_standard`, `price_last_minute`, avec le bouton
« Réinitialiser aux valeurs suggérées » et l'avertissement `countdown_date` — repris
tels quels de V223), `pack_sessions`, `description` (`maxLength` porté de 2000 à 3000),
`keywords`.

**Étape 2 — Logistique**
`countdown_enabled`, `countdown_text`, `countdown_date`, `countdown_time` ;
`duration_value`, `duration_unit`, `is_auto_prolong` ; `linked_course_ids` ;
**`duration_minutes`, `location`, `max_participants`** (nouveaux) ;
`category`, `isProduct`, `visible`.

Champs produit (`tva`, `shippingCost`, `stock`, `variants.sizes/colors/weights`) :
également en étape 2, affichés seulement si `isProduct`. Les 3 inputs `variants`
deviennent contrôlés (ajout de `value=`), ce qui corrige leur non-pré-remplissage en
édition.

**Étape 3 — Médias**
`images[0..4]` (5 inputs URL) ; **`videoUrl`** avec prévisualisation.

### Navigation

- Onglets numérotés (1) (2) (3), **librement cliquables** : on ne bloque pas la
  navigation entre étapes.
- Bas de modal : « Annuler » + « Suivant → » ; à l'étape 3 : « ← Précédent » +
  « Enregistrer ».
- Seule contrainte : l'enregistrement est refusé si `name` est vide, avec retour
  automatique sur l'étape 1 et focus sur le champ.

### Coexistence avec l'ancien formulaire

L'ancien formulaire plat de `OffersManager.js` **reste dans le fichier** mais n'est plus
rendu. Il n'est pas supprimé (règle de non-régression) et pourra l'être dans une version
ultérieure, une fois le wizard éprouvé en production.

## Chantier 1bis — Liste blanche `offerData`

Dans `CoachDashboard.js` (l.2391-2426), ajouter au payload :

`videoUrl`, `linked_course_ids`, `duration_minutes`, `location`, `max_participants`.

L'ajout de `linked_course_ids` corrige le bug décrit plus haut : les cours associés
lors de la création étaient perdus. Le wizard, qui envoie tout d'un coup, en dépend.

## Chantier 2 — Cartes d'offres dashboard

Nouveau composant `dashboard/OfferCard.js`. Grille responsive : 2 colonnes desktop,
1 colonne mobile.

Contenu d'une carte : média en haut (ratio 16:9, image ou vignette vidéo), nom, badge
« Active » (vert si `visible`, gris sinon), toggle actif/inactif, description tronquée,
ligne méta (`duration_minutes`, `price`), `location`, compteur de participants, et les
actions Modifier / Dupliquer / Supprimer.

- « Modifier » ouvre le wizard pré-rempli.
- « + NOUVELLE OFFRE » (en-tête) ouvre le wizard vide.
- Le toggle appelle `updateOffer` (comportement existant, inchangé).

Le rendu actuel en liste (mobile l.285-397, desktop l.400-498) est conservé dans le
fichier mais n'est plus rendu.

## Chantier 3 — Parcours progressif sans horaires

Deux points de branchement dans `App.js`, tous deux sous garde
`if (offer.progressive_pricing)` :

1. **`handleSelectOffer`** (l.3773) — sortie immédiate vers
   `startProgressiveCheckout(offer)` : pas de `pendingOffer`, pas de scroll vers les
   horaires, pas de passage par le formulaire client.
2. **`showSessions`** (l.5129-5131) — ajout de `&& !activeOffer?.progressive_pricing`,
   ce qui masque le bloc « Horaires pour "…" ».

### `startProgressiveCheckout(offer)`

Poste sur `create-checkout-session` :

```js
{
  productName: offer.name,
  amount: v223UnitPrice(offer),
  originUrl: window.location.origin,
  offerId: offer.id
}
```

Puis redirige vers `response.data.url`.

**Contraintes impératives :**

- **La clé `customerEmail` est omise** — jamais envoyée à `""`. Stripe rejette une
  chaîne vide comme adresse invalide ; le fallback carte-seule (l.3487) la relaierait
  telle quelle, faisant échouer les deux tentatives et laissant le client sans
  paiement possible. Omise, `customerEmail` vaut `None` et Stripe Checkout collecte
  lui-même l'email.
- **`reservationData` est omis** — aucune réservation n'est créée à l'achat. Le client
  réserve ensuite depuis `/espace/<code>`.

Le reste est déjà en place et n'est pas modifié : le webhook récupère l'email via
`customer_details`, lit les crédits en base depuis `offerId` (l.3377-3398, jamais reçus
du client), et émet le code AFR-XXXXXX.

Aucune modification du backend de paiement n'est nécessaire pour ce chantier.

## Chantier 4 — Cartes publiques

Modification de `OfferCardSlider` **inline dans `App.js`** (l.1230-1458) — c'est le
composant réellement rendu par `OffersSliderAutoPlay` (l.1568), lui-même monté dans le
bloc offres (l.5190-5195).

### Contenu

Média, titre, description tronquée, puis les lignes méta — **chacune masquée si sa
donnée est absente** :

- `duration_minutes` → « 105 min »
- `location` → « 📍 Lausanne — Plage de Vidy »
- participants → « 👥 0/50 », dérivé des réservations et de `max_participants`
- « Prochaine séance » → dérivée des `linked_course_ids` via `getNextOccurrences`
  (déjà présent, l.4187)

Prix et bouton « Réserver — X CHF ». Le prix reste lu via **`v223UnitPrice`**
(l.1216) : c'est le point de vérité unique côté client et il n'est pas modifié.

### Médias

Détection du type via **`parseMediaUrl`** (l.645), qui gère déjà YouTube, Vimeo et les
extensions vidéo.

- Image : clic sur 🔍 → agrandissement en overlay.
- Vidéo : bouton ▶ sur la vignette ; au clic, `requestFullscreen()`.

**Orientation.** Le ratio est mesuré sur l'évènement `loadedmetadata`
(`videoWidth / videoHeight`), jamais deviné depuis l'URL. Pour une vidéo 16:9 sur
mobile, `screen.orientation.lock('landscape')` est tenté **dans un `try/catch` avec
repli silencieux** : l'API est absente ou refusée sur iOS Safari, et elle rejette sa
promesse si elle est appelée hors plein écran. Un échec de rotation ne doit jamais
empêcher la lecture. Une vidéo 9:16 est laissée en portrait.

## Risques et parades

| Risque | Parade |
|---|---|
| `PUT /offers` efface les champs non déclarés | Les 3 champs sont ajoutés à `Offer` **et** `OfferCreate` |
| `customerEmail: ""` casse le paiement (2 tentatives) | La clé est omise du payload, jamais vidée |
| Rotation d'écran refusée sur iOS | `try/catch`, repli silencieux, lecture préservée |
| Régression sur les offres non progressives | Toutes les nouvelles branches sont sous garde `progressive_pricing` |
| Perte de `linked_course_ids` | Ajout à la liste blanche `offerData` |

## Design visuel

Fond `#0A0A0F` ; primaire `#D91CD2` ; secondaire `#FF2DAA` ; texte `#FFFFFF`.
Modal `#1a1a2e`, bordures `rgba(217,28,210,0.2)`, coins 12px.
Inputs fond `#0a0a0f`, bordure `#333`, focus `#D91CD2`.
Onglet actif rose, inactifs gris. Cartes : hover en légère élévation (ombre violette).

Le projet mélange déjà Tailwind (layout, espacements, typo) et `style={{}}` inline
(couleurs de marque, états dynamiques). Les nouveaux composants suivent cette
convention plutôt que d'en introduire une troisième.

## Hors périmètre

- Upload de fichier vidéo (URL uniquement — Vercel plafonne à 60 s par requête).
- Suppression de l'ancien formulaire plat et de l'ancien rendu en liste.
- Suppression du code mort `components/OfferCard.js` (racine).
- Toute modification de `SubscriberSpace.js`.
- Le montant du checkout reste calculé côté client : faiblesse préexistante,
  documentée dans V223 (`api/server.py` l.3370-3376), volontairement non aggravée
  et non traitée ici.

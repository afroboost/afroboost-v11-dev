# V225 — Cartes complètes et achat direct : plan d'implémentation

> **Pour les agents :** SOUS-SKILL REQUISE — utiliser `superpowers:subagent-driven-development`
> pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe `- [ ]`.

**Objectif :** Afficher toutes les informations d'une offre sur sa carte (lieu
géolocalisé, horaires, paliers de prix, compte à rebours, quantité), faire passer les
offres de service en achat direct Stripe, et permettre au coach de gérer ses horaires
depuis le wizard de l'offre.

**Architecture :** Aucun composant neuf. Les modifications portent sur
`OfferCardSlider` (seul rendu réellement monté), `OfferWizard`, la liste blanche
`offerData`, et trois zones backend (modèles, checkout, webhook). Les cas produit
physique et offre gratuite sont exclus de l'achat direct par des gardes explicites.

**Stack :** React 19 (CRA + CRACO), FastAPI + Pydantic 2, MongoDB Atlas, Stripe.

**Spec de référence :** `docs/superpowers/specs/2026-07-21-v225-cartes-completes-design.md`

## Contraintes globales

- **Aucune suppression de code existant.** Site en production avec abonnés actifs.
- **Marqueur `// V225`** (JS) ou `# V225` (Python) sur chaque ajout.
- **Ne pas toucher** : `SubscriberSpace.js`, `CoursesManager.js`, `ChatWidget.js`,
  `CoachVitrine.js` (code mort), `OfferCard` d'`App.js:1127` (code mort), le Service
  Worker, les routes JWT.
- **Palette** : fond `#0A0A0F`, primaire `#D91CD2`, secondaire `#FF2DAA`, texte
  `#FFFFFF` / `#AAAAAA`, inputs fond `#0a0a0f` bordure `#333`, coins `12px`,
  gap cartes `16px` minimum.
- **Convention** : Tailwind pour layout/espacement/typo, `style={{}}` inline pour les
  couleurs de marque et états dynamiques.
- **Build** : `cd frontend && CI=false npx craco build`. Après le build, exécuter
  `git checkout -- frontend/build/` depuis la racine — le build modifie des artefacts
  versionnés qui ne doivent pas entrer dans les commits.
- **Tests backend** : `python3 -m pytest tests/test_offer_fields_v224.py tests/test_pricing_v223.py -v`
  (17 tests) doivent rester verts.
- **Commits en français**, préfixés `V225:`, avec
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## Stratégie de test

Identique à V224, et pour les mêmes raisons :

- **Backend** — pytest fonctionne. FastAPI n'étant pas installé localement,
  `from api.server import Offer` échoue : les modèles se testent par **analyse AST**,
  sur le modèle de `tests/test_offer_fields_v224.py`.
- **Frontend** — **aucune infrastructure de test n'existe** (0 `.test.js`, pas de
  `setupTests.js`, `@testing-library` absent). Ne pas en créer. Validation par build
  réel + vérification manuelle scriptée.

## Structure des fichiers

| Fichier | Statut | Responsabilité |
|---|---|---|
| `api/server.py` | modifié | 3 champs `label_*`, `quantity` au checkout, crédits × quantité, email `/espace/` |
| `api/routes/coach_routes.py` | modifié (`:475`) | Enrichissement `active_price` sur la vitrine |
| `tests/test_offer_labels_v225.py` | **créé** | Garde-fou symétrie des modèles |
| `frontend/src/components/CoachDashboard.js` | modifié | Liste blanche `offerData` : 3 `label_*` |
| `frontend/src/components/dashboard/OfferWizard.js` | modifié | Libellés de paliers (étape 1), cours éditables (étape 2) |
| `frontend/src/App.js` | modifié | Carte complète, quantité, achat direct, `showSessions` |

---

### Tâche 1 : Champs `label_*` et garde-fou de symétrie

**Fichiers :**
- Créer : `tests/test_offer_labels_v225.py`
- Modifier : `api/server.py` (classes `Offer` et `OfferCreate`)

**Interfaces :**
- Produit : `label_early_bird`, `label_standard`, `label_last_minute`, tous
  `Optional[str] = None`, sur les deux modèles. Les tâches 2, 3 et 5 les consomment.

- [ ] **Étape 1 : Écrire le test qui échoue**

Créer `tests/test_offer_labels_v225.py`, sur le modèle de
`tests/test_offer_fields_v224.py` (le lire d'abord) :

```python
"""V225 — Garde-fou sur les libellés de paliers.

Module pur : analyse le source de api/server.py par AST. Aucune dépendance
FastAPI ni MongoDB — ces paquets ne sont pas installés en local.

Invariant protégé : PUT /offers/{id} fait `$set: offer.model_dump()` sur un
OfferCreate en `extra="ignore"`. Tout champ persisté absent d'OfferCreate est
donc effacé en base à chaque sauvegarde d'offre.
"""
import ast
import pathlib

import pytest

SERVER = pathlib.Path(__file__).resolve().parents[1] / "api" / "server.py"

V225_LABELS = {"label_early_bird", "label_standard", "label_last_minute"}


def _class_fields(class_name):
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            }
    raise AssertionError(f"classe {class_name} introuvable dans {SERVER}")


@pytest.mark.parametrize("model", ["Offer", "OfferCreate"])
def test_les_libelles_v225_sont_declares(model):
    manquants = V225_LABELS - _class_fields(model)
    assert not manquants, f"{model} ne declare pas {sorted(manquants)}"


def test_symetrie_offer_offercreate_sur_les_libelles():
    """Un champ sur Offer mais pas sur OfferCreate est efface au premier PUT."""
    assert V225_LABELS <= _class_fields("Offer") & _class_fields("OfferCreate")


def test_les_prix_des_paliers_restent_declares():
    """Non-regression V223 : les libelles accompagnent les prix, ne les remplacent pas."""
    prix = {"price_early_bird", "price_standard", "price_last_minute"}
    assert prix <= _class_fields("Offer")
    assert prix <= _class_fields("OfferCreate")
```

- [ ] **Étape 2 : Lancer le test et vérifier qu'il échoue**

```bash
python3 -m pytest tests/test_offer_labels_v225.py -v
```

Attendu : les 3 premiers tests ÉCHOUENT (`Offer ne declare pas [...]`).
`test_les_prix_des_paliers_restent_declares` PASSE déjà.

- [ ] **Étape 3 : Ajouter les champs aux deux modèles**

Dans `api/server.py`, repérer le bloc V223 `pack_sessions` de la classe `Offer`, puis
celui de `OfferCreate`. Ajouter dans **chacune** :

```python
    # V225: libelles personnalises des paliers. Obligatoirement symetrique entre
    # Offer et OfferCreate : PUT /offers fait `$set: offer.model_dump()` sur
    # OfferCreate en extra="ignore", donc un champ absent ici serait efface en
    # base a chaque sauvegarde d'offre.
    label_early_bird: Optional[str] = None
    label_standard: Optional[str] = None
    label_last_minute: Optional[str] = None
```

- [ ] **Étape 4 : Vérifier que tout passe**

```bash
python3 -m pytest tests/test_offer_labels_v225.py tests/test_offer_fields_v224.py tests/test_pricing_v223.py -v
```

Attendu : 4 tests V225 + 4 tests V224 + 13 tests V223 = 21 PASSENT.

- [ ] **Étape 5 : Commit**

```bash
git add api/server.py tests/test_offer_labels_v225.py
git commit -m "V225: libelles personnalisables des paliers de prix

Declares symetriquement sur Offer et OfferCreate : la symetrie est imposee par
PUT /offers qui fait un \$set complet.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Tâche 2 : Quantité au checkout et crédits proportionnels

C'est la tâche la plus sensible : elle touche le paiement **et** l'attribution des
crédits. Une erreur ici fait payer un client sans lui donner ce qu'il a acheté.

**Fichiers :**
- Modifier : `api/server.py` — `CreateCheckoutRequest`, les deux `stripe.checkout.Session.create`, et le webhook

**Interfaces :**
- Produit : `quantity: int = 1` sur `CreateCheckoutRequest`. La tâche 4 l'envoie.

- [ ] **Étape 1 : Ajouter le champ au modèle**

Dans `CreateCheckoutRequest`, après `allowPromotionCodes` :

```python
    # V225: nombre d'unites achetees (ex: 2 places pour un couple).
    # Borne cote serveur : cet endpoint est public, la limite de l'interface
    # ne protege rien.
    quantity: int = 1
```

- [ ] **Étape 2 : Borner la quantité et l'appliquer aux deux sessions**

Juste avant la construction des `metadata`, ajouter :

```python
    # V225: 1..5. Un client peut poster ce qu'il veut ; le plafond est ici.
    safe_quantity = max(1, min(5, int(request.quantity or 1)))
```

Puis, dans les **deux** appels `stripe.checkout.Session.create` (chemin nominal et
fallback carte-seule), remplacer `'quantity': 1` par `'quantity': safe_quantity`.

`unit_amount` reste le prix **unitaire** : Stripe multiplie lui-même. Ne pas envoyer
un montant déjà multiplié, sinon le récapitulatif Stripe afficherait « 3 × 45 CHF »
pour un article à 15 CHF.

- [ ] **Étape 3 : Faire suivre les crédits**

Dans le webhook, repérer le bloc V223 qui calcule `sessions_count` depuis
`metadata["pack_sessions"]` (`api/server.py` ~l.3792-3800). Après ce calcul, appliquer
le multiplicateur :

```python
                # V225: la quantite est relue sur la session Stripe, jamais
                # acceptee du client au moment du webhook — meme regle que V223
                # pour les credits. Sans ce multiplicateur, un client achetant
                # 3 packs de 10 paierait 3 fois et recevrait 10 credits.
                purchased_qty = 1
                try:
                    _li = stripe.checkout.Session.list_line_items(session.id, limit=1)
                    if _li and _li.data:
                        purchased_qty = max(1, min(5, int(_li.data[0].quantity or 1)))
                except Exception as _qty_err:
                    logger.warning(f"[V225] Quantite illisible sur {session.id}: {_qty_err} — repli sur 1")
                if purchased_qty > 1:
                    sessions_count = sessions_count * purchased_qty
                    logger.info(f"[V225] {purchased_qty} unites achetees -> {sessions_count} credits")
```

Le repli sur 1 en cas d'erreur est délibéré : mieux vaut accorder trop peu de crédits
et corriger à la main que d'en accorder trop sur une lecture douteuse.

- [ ] **Étape 4 : Vérifier**

```bash
python3 -c "import ast;ast.parse(open('api/server.py',encoding='utf-8').read());print('syntaxe OK')"
python3 -m pytest tests/test_offer_labels_v225.py tests/test_offer_fields_v224.py tests/test_pricing_v223.py -q
```

Attendu : syntaxe OK, 21 tests verts.

Relire ensuite soi-même les deux `Session.create` pour confirmer que `unit_amount` n'a
pas été touché et que `safe_quantity` est bien appliqué **aux deux**.

- [ ] **Étape 5 : Commit**

```bash
git add api/server.py
git commit -m "V225: quantite au checkout et credits proportionnels

La quantite est bornee 1..5 a l'entree et relue sur la session Stripe au
webhook, jamais acceptee du client — meme regle que V223 pour les credits.
Sans le multiplicateur, un client achetant 3 packs de 10 payait 3 fois et
recevait 10 credits.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Tâche 3 : Email de réservation et enrichissement de la vitrine

**Fichiers :**
- Modifier : `api/server.py` (email post-paiement ~l.3919)
- Modifier : `api/routes/coach_routes.py` (~l.475)

- [ ] **Étape 1 : Ajouter le lien `/espace/` à l'email**

Dans le bloc email du webhook, à côté de `chat_url` (~l.3921), ajouter :

```python
                    espace_url = f"https://afroboost.com/espace/{new_code}"  # V225
```

Puis insérer dans le HTML, en évidence, un bouton « 🗓️ Réserver ma séance » pointant
vers `espace_url`. Le QR et le lien chat existants sont **conservés** : l'ajout est
additif. Respecter le style de l'email (fond sombre, accent `#d91cd2`).

- [ ] **Étape 2 : Enrichir les offres de la vitrine**

Dans `api/routes/coach_routes.py`, repérer `offers = await db.offers.find(coach_filter, {"_id": 0}).to_list(20)` (~l.475).

Sans cet enrichissement, `active_price` et `active_tier` sont absents sur les pages
partenaires, et les paliers de prix y restent inertes.

Importer et appliquer `_enrich_offers_with_active_price` depuis `api.server` — vérifier
d'abord le sens d'import déjà en place dans ce fichier pour ne pas créer d'import
circulaire. Si l'import depuis `api.server` est impossible, appeler directement
`compute_active_price` de `api.pricing` (module pur, aucune dépendance) et poser
`active_price` / `active_tier` sur chaque offre — c'est exactement ce que fait
`_enrich_offers_with_active_price` (`server.py:1138-1156`), à relire avant d'écrire.

- [ ] **Étape 3 : Vérifier**

```bash
python3 -c "import ast;ast.parse(open('api/server.py',encoding='utf-8').read());print('server OK')"
python3 -c "import ast;ast.parse(open('api/routes/coach_routes.py',encoding='utf-8').read());print('coach_routes OK')"
python3 -m pytest tests/test_offer_labels_v225.py tests/test_offer_fields_v224.py tests/test_pricing_v223.py -q
```

- [ ] **Étape 4 : Commit**

```bash
git add api/server.py api/routes/coach_routes.py
git commit -m "V225: lien de reservation dans l'email et paliers sur les pages partenaires

L'email post-paiement pointait vers le chat (?qr=), jamais vers /espace/ :
le client payait sans recevoir de lien pour reserver.

L'endpoint vitrine ne passait pas les offres par _enrich_offers_with_active_price,
donc active_tier etait absent et les paliers restaient inertes chez les partenaires.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Tâche 4 : Achat direct et suppression de la section horaires

**Fichiers :**
- Modifier : `frontend/src/App.js` — `handleSelectOffer` (~l.4141), `showSessions`
  (~l.5554), `startProgressiveCheckout` (~l.4085)

**Interfaces :**
- Consomme : `quantity` de la tâche 2.
- Produit : `startProgressiveCheckout(offer, quantity)` — la tâche 5 l'appelle avec la
  quantité choisie sur la carte.

- [ ] **Étape 1 : Étendre `startProgressiveCheckout` à la quantité**

La fonction existe (V224). Lui ajouter un second paramètre `quantity = 1` et l'inclure
dans le payload :

```js
        quantity: Math.max(1, Math.min(5, parseInt(quantity, 10) || 1)), // V225
```

Ne pas toucher au reste du payload : l'absence de `customerEmail` et de
`reservationData` est délibérée et documentée (V224).

- [ ] **Étape 2 : Élargir la garde de `handleSelectOffer`**

La garde V224 ne visait que `progressive_pricing`. Elle vise désormais toute offre de
service payante. Repérer le bloc V224 en tête de `handleSelectOffer` et le remplacer
par :

```js
    // V225: toutes les offres de service payantes partent en achat direct.
    // Deux exclusions, imposees par la plateforme et non par le design :
    //  - produit physique : l'adresse de livraison se saisit dans le formulaire
    //    (App.js ~l.6193) et serait perdue ;
    //  - offre a 0 CHF : Stripe refuse un montant nul.
    // Ces deux cas gardent le parcours actuel, formulaire compris.
    const v225IsProduct = offer && (offer.isProduct || offer.isPhysicalProduct
      || offer.type === 'product' || offer.type === 'audio' || offer.type === 'video');
    const v225UnitPrice = offer ? v223UnitPrice(offer) : 0;
    if (offer && !v225IsProduct && v225UnitPrice > 0) {
      startProgressiveCheckout(offer, 1);
      return;
    }
```

Le `return` est impératif : sans lui, le flux continue et pose un `pendingOffer`.

- [ ] **Étape 3 : Désactiver la section horaires**

Repérer la définition de `showSessions` (~l.5554-5558). **Ne pas supprimer le calcul
existant** : le conserver et neutraliser le résultat, pour que le code reste lisible et
réactivable.

```js
    // V225: les horaires sont desormais affiches sur chaque carte, et toutes les
    // offres de service partent en achat direct. La grille de dates n'a plus de
    // role. Le calcul d'origine est conserve juste au-dessus, non consomme.
    const showSessions = false;
```

Renommer le calcul d'origine en `showSessionsLegacy` pour éviter une redéclaration, et
laisser un commentaire indiquant qu'il est conservé volontairement.

- [ ] **Étape 4 : Vérifier le build**

```bash
cd frontend && CI=false npx craco build 2>&1 | tail -20
cd .. && git checkout -- frontend/build/
```

Attendu : compilation réussie.

- [ ] **Étape 5 : Vérification manuelle**

1. Offre de service payante → clic → **aucune** grille d'horaires, redirection Stripe.
2. **Produit physique** → parcours inchangé : formulaire, adresse de livraison, paiement.
3. **Offre à 0 CHF** → parcours inchangé : formulaire, réservation créée sans Stripe.

Les points 2 et 3 sont le critère d'acceptation principal : ce sont les seuls parcours
qui doivent survivre intacts.

- [ ] **Étape 6 : Commit**

```bash
git add frontend/src/App.js
git commit -m "V225: achat direct pour les offres de service, section horaires retiree

showSessions force a false, calcul d'origine conserve sous showSessionsLegacy.
Produits physiques et offres gratuites gardent le parcours actuel : le premier
a besoin de l'adresse de livraison du formulaire, le second ne peut pas passer
par Stripe qui refuse un montant nul.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Tâche 5 : Carte publique complète

**Fichiers :**
- Modifier : `frontend/src/App.js` — `OfferCardSlider` (~l.1255-1678),
  `OffersSliderAutoPlay` (~l.1683), les deux points de montage (~l.5617, ~l.5866)

Viser `OfferCardSlider` : c'est le seul composant réellement rendu.
`OfferCard` (`App.js:1127`) et `components/CoachVitrine.js` sont du code mort et ne
doivent pas être touchés.

- [ ] **Étape 1 : Enrichir les offres de leurs cours**

Aux **deux** points de montage d'`OffersSliderAutoPlay`, croiser les offres avec les
cours :

```jsx
{/* V225: enrichir chaque offre de ses cours complets */}
const v225Enriched = offers.map(o => ({
  ...o,
  linkedCourses: (o.linked_course_ids || [])
    .map(id => courses.find(c => c.id === id))
    .filter(Boolean)
}));
```

Faire l'enrichissement une seule fois, dans `OffersSliderAutoPlay`, plutôt que de le
dupliquer aux deux montages.

- [ ] **Étape 2 : Lieu géolocalisé**

Dans `OfferCardSlider`, sous la description. `stopPropagation` est impératif : sans lui,
le clic sur le lieu déclencherait aussi la sélection de l'offre, donc le checkout.

```jsx
{/* V225: lieu cliquable vers Google Maps */}
{(() => {
  const loc = (offer.linkedCourses || []).find(c => c && c.locationName);
  if (!loc) return null;
  return (
    <a href={loc.mapsUrl || '#'} target="_blank" rel="noopener noreferrer"
       onClick={e => e.stopPropagation()}
       style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#D91CD2', textDecoration: 'none', marginBottom: '6px' }}>
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#D91CD2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>
      <span>{loc.locationName}</span>
    </a>
  );
})()}
```

- [ ] **Étape 3 : Horaires**

```jsx
{/* V225: horaires des cours lies */}
{(offer.linkedCourses || []).map(course => {
  const days = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'];
  return (
    <div key={course.id} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '2px', color: '#aaa', fontSize: '12px' }}>
      <span>🕐</span>
      <span>{days[course.weekday]} · {course.time}</span>
    </div>
  );
})}
```

- [ ] **Étape 4 : Les 3 paliers**

```jsx
{/* V225: 3 paliers de prix, libelles personnalisables */}
{offer.progressive_pricing && (
  <div style={{ display: 'flex', gap: '6px', margin: '8px 0' }}>
    {[
      { key: 'early_bird', price: offer.price_early_bird, label: offer.label_early_bird || 'Prévente', color: '#22c55e' },
      { key: 'standard', price: offer.price_standard, label: offer.label_standard || 'Standard', color: '#eab308' },
      { key: 'last_minute', price: offer.price_last_minute, label: offer.label_last_minute || 'Dernière min.', color: '#ef4444' },
    ].filter(t => t.price != null).map(tier => {
      const isActive = offer.active_tier === tier.key;
      return (
        <div key={tier.key} style={{
          flex: 1, padding: '6px 4px', borderRadius: '8px', textAlign: 'center',
          background: isActive ? `${tier.color}15` : '#1a1a2e',
          border: `1px solid ${isActive ? tier.color : '#333'}`,
          opacity: isActive ? 1 : 0.5,
        }}>
          <div style={{ fontSize: '10px', color: isActive ? tier.color : '#888', fontWeight: 600 }}>
            {tier.label} {isActive && '✓'}
          </div>
          <div style={{ fontSize: '14px', fontWeight: 700, color: isActive ? '#fff' : '#666' }}>
            {tier.price} CHF
          </div>
        </div>
      );
    })}
  </div>
)}
```

Le `.filter(t => t.price != null)` est nécessaire : un palier non renseigné afficherait
« null CHF ». Utiliser `!= null` et non la véracité — un palier à 0 est légitime.

- [ ] **Étape 5 : Sélecteur de quantité**

État local au composant, réinitialisé quand l'offre change :

```jsx
const [v225Qty, setV225Qty] = useState(1); // V225
```

Rendu, au-dessus du bouton :

```jsx
{/* V225: quantite 1..5 */}
<div style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '8px 0' }}>
  <span style={{ fontSize: '12px', color: '#aaa' }}>Quantité</span>
  <select
    value={v225Qty}
    onClick={e => e.stopPropagation()}
    onChange={e => { e.stopPropagation(); setV225Qty(parseInt(e.target.value, 10) || 1); }}
    className="v224-input"
    style={{ background: '#0a0a0f', border: '1px solid #333', borderRadius: '8px', color: '#fff', padding: '4px 8px' }}
  >
    {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{n}</option>)}
  </select>
</div>
```

Le `stopPropagation` sur `onClick` **et** `onChange` est impératif : sans lui, ouvrir le
sélecteur déclencherait la sélection de l'offre, donc un départ en checkout.

- [ ] **Étape 6 : Bouton et prix total**

Le bouton affiche le total et transmet la quantité. Attention : la garde V224 impose
que le bouton appelle `onClick(offer)` et non directement le checkout — cette règle
avait été posée pour supprimer une divergence sur le slider produits. Ici, la quantité
doit néanmoins atteindre `startProgressiveCheckout`.

Solution retenue : le bouton appelle `startProgressiveCheckout(offer, v225Qty)`
**uniquement** quand l'offre est éligible à l'achat direct (service payant), et
`onClick(offer)` sinon. Reproduire exactement la même condition d'éligibilité que la
tâche 4, sans quoi les deux chemins divergeraient :

```jsx
{/* V225 */}
<button
  type="button"
  disabled={checkoutBusy}
  onClick={(e) => {
    e.stopPropagation();
    const isProd = offer.isProduct || offer.isPhysicalProduct
      || offer.type === 'product' || offer.type === 'audio' || offer.type === 'video';
    const unit = v223UnitPrice(offer);
    if (!isProd && unit > 0 && typeof startProgressiveCheckout === 'function') {
      startProgressiveCheckout(offer, v225Qty);
    } else {
      onClick(offer);
    }
  }}
  ...
>
  {checkoutBusy ? 'Un instant…' : `Réserver — ${(v223UnitPrice(offer) * v225Qty).toFixed(2)} CHF`}
</button>
```

- [ ] **Étape 7 : Espacement et largeur des cartes**

Dans `OffersSliderAutoPlay`, appliquer `gap: '16px'` au conteneur défilant et une
largeur minimale de 280px (mobile) / 320px (desktop) à chaque carte.

- [ ] **Étape 8 : Compte à rebours**

`OfferCountdown` est déjà rendu (`App.js:1640`). Vérifier sa présence dans le nouveau
rendu et **ne pas le recréer**.

- [ ] **Étape 9 : Vérifier le build**

```bash
cd frontend && CI=false npx craco build 2>&1 | tail -20
cd .. && git checkout -- frontend/build/
```

- [ ] **Étape 10 : Vérification manuelle**

1. Une offre **existante**, sans cours liés ni paliers, s'affiche **exactement comme
   avant** : aucune ligne vide, aucun « undefined », aucun « null CHF ».
2. Une offre avec cours liés affiche lieu et horaires ; le clic sur le lieu ouvre Maps
   **sans** déclencher le checkout.
3. Les 3 paliers s'affichent, l'actif est coché.
4. Le sélecteur de quantité s'ouvre **sans** déclencher le checkout ; le prix du bouton
   suit la quantité.
5. Les cartes sont visiblement séparées dans le carrousel.

Le point 1 et les `stopPropagation` des points 2 et 4 sont les critères d'acceptation
les plus importants.

- [ ] **Étape 11 : Commit**

```bash
git add frontend/src/App.js
git commit -m "V225: carte d'offre complete

Lieu geolocalise, horaires des cours lies, 3 paliers avec libelles
personnalisables, selecteur de quantite, espacement des cartes.

Chaque ligne est masquee quand sa donnee est absente : les offres existantes
restent visuellement inchangees. stopPropagation sur le lieu et le selecteur,
sans quoi un clic dessus partirait en checkout.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Tâche 6 : Libellés de paliers dans le wizard

**Fichiers :**
- Modifier : `frontend/src/components/dashboard/OfferWizard.js` (étape 1, ~l.191-256)
- Modifier : `frontend/src/components/CoachDashboard.js` (liste blanche `offerData`)

- [ ] **Étape 1 : Ajouter les libellés à l'étape 1**

Dans l'encadré des paliers, associer à chaque prix un champ de libellé. La constante
`PROGRESSIVE_TIERS` (`OfferWizard.js:67-71`) porte déjà les clés de prix : l'étendre
d'une clé `labelKey` et d'un `placeholder`, plutôt que d'écrire trois blocs séparés.

Placeholders : « Prévente », « Standard », « Dernière min. ».

- [ ] **Étape 2 : Étendre la liste blanche `offerData`**

Dans `CoachDashboard.js`, ajouter au payload :

```js
        // V225: libelles des paliers. Sans ces lignes, les champs saisis dans le
        // wizard ne sont pas envoyes et le PUT les remettrait a zero en base.
        label_early_bird: src.label_early_bird || null,
        label_standard: src.label_standard || null,
        label_last_minute: src.label_last_minute || null,
```

Ajouter également les trois clés à `startEditOffer`, à l'état initial `newOffer`, et
aux deux resets — sinon l'édition ne les pré-remplit pas et un reset incomplet laisse
la valeur de l'offre précédente.

- [ ] **Étape 3 : Vérifier le build**

```bash
cd frontend && CI=false npx craco build 2>&1 | tail -20
cd .. && git checkout -- frontend/build/
```

- [ ] **Étape 4 : Vérification manuelle**

Créer une offre avec des libellés personnalisés, enregistrer, recharger, rouvrir en
modification : les libellés sont pré-remplis. Basculer l'offre en masquée depuis sa
carte, recharger : les libellés **n'ont pas été effacés** — c'est le test grandeur
nature de la symétrie de la tâche 1.

- [ ] **Étape 5 : Commit**

```bash
git add frontend/src/components/dashboard/OfferWizard.js frontend/src/components/CoachDashboard.js
git commit -m "V225: libelles de paliers editables dans le wizard

Ajoutes a l'etape 1, a la liste blanche offerData, a l'edition et aux resets.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Tâche 7 : Cours éditables dans le wizard

**Fichiers :**
- Modifier : `frontend/src/components/dashboard/OfferWizard.js` (étape 2, ~l.449-492)

- [ ] **Étape 1 : État local des cours liés**

Remplacer les cases à cocher par un état `linkedCourses` : un tableau d'objets cours
complets, initialisé dans le **même `useEffect`** que `form` (celui sur
`[open, initialOffer]`), en croisant `initialOffer.linked_course_ids` avec la prop
`courses`.

- [ ] **Étape 2 : Bloc éditable par horaire**

Pour chaque cours : nom, jour (`select` 0-6), heure (`type="time"`), lieu, lien Maps,
et une croix de délien. Style conforme à la palette du wizard (fond `#0a0a0f`, bordure
`#333`, classe `v224-input`).

Le délien retire l'entrée de `linkedCourses` et l'id de `form.linked_course_ids`. Il ne
supprime **jamais** le cours en base.

- [ ] **Étape 3 : Ajout d'un horaire**

Bouton « + Ajouter un horaire » en pointillés. Il appelle `POST /courses` avec :

```js
{ name: 'Nouveau cours', weekday: 3, time: '18:30', locationName: '', mapsUrl: '', visible: true }
```

`locationName` est **requis** par `CourseCreate` (`api/server.py:353-363`) : l'envoyer,
même vide, sinon la requête est rejetée. Ne **pas** envoyer de `coach_id` : le serveur
l'assigne depuis l'en-tête `X-User-Email` quand le corps n'en fournit pas
(`server.py:1013-1014`), ce qui est le comportement voulu.

À la réponse, ajouter l'objet complet à `linkedCourses` et son id à
`form.linked_course_ids` pour un affichage immédiat.

- [ ] **Étape 4 : Persistance à l'enregistrement**

Avant d'appeler `onSave(form)`, envoyer un `PUT /courses/{id}` pour chaque cours
**modifié**. Suivre les modifications plutôt que de tout réécrire, pour ne pas émettre
N requêtes inutiles.

Piège documenté : `PUT /courses/{id}` ignore les valeurs `None`
(`server.py:1031` — `{k: v for k, v in course_update.items() if v is not None}`). Un
champ vidé par le coach doit donc être envoyé en **chaîne vide**, jamais en `null`,
sinon l'effacement est silencieusement ignoré.

Si un `PUT` échoue, ne pas fermer le wizard silencieusement : signaler l'échec et
laisser la saisie en place, comme le fait déjà `handleWizardSave` pour l'offre.

- [ ] **Étape 5 : Vérifier le build**

```bash
cd frontend && CI=false npx craco build 2>&1 | tail -20
cd .. && git checkout -- frontend/build/
```

- [ ] **Étape 6 : Vérification manuelle**

1. Ouvrir une offre existante ayant des cours liés : ils apparaissent, pré-remplis.
2. Modifier un horaire, enregistrer, recharger : la modification a persisté.
3. Ajouter un horaire : il apparaît immédiatement et existe après rechargement.
4. Délier un cours, enregistrer : il disparaît de l'offre mais **existe toujours** dans
   `CoursesManager`.
5. Vider un lien Maps, enregistrer, recharger : le champ est bien vide (piège `None`).
6. En tant que coach non super-admin : seuls ses propres cours sont listés.

- [ ] **Étape 7 : Commit**

```bash
git add frontend/src/components/dashboard/OfferWizard.js
git commit -m "V225: horaires editables directement dans le wizard

Creation via POST /courses, modifications via PUT /courses/{id} a
l'enregistrement, delien sans suppression en base.

Les champs vides sont envoyes en chaine vide et non en null : PUT /courses
ignore les valeurs None, un effacement en null serait silencieusement perdu.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Auto-revue du plan

**Couverture de la spec**

| Exigence | Tâche |
|---|---|
| Champs `label_*` symétriques | 1 |
| Quantité au checkout | 2 |
| Crédits × quantité, serveur autoritatif | 2 |
| Email avec lien `/espace/` | 3 |
| Paliers actifs sur les pages partenaires | 3 |
| Achat direct des offres de service | 4 |
| Produits physiques et offres gratuites préservés | 4, étape 5 (bloquante) |
| Section horaires retirée | 4 |
| Lieu + GPS, horaires, paliers, countdown | 5 |
| Sélecteur de quantité | 5 |
| Espacement des cartes | 5 |
| Libellés éditables dans le wizard | 6 |
| Cours éditables dans le wizard | 7 |

**Cohérence des types** — `label_*` sont `Optional[str]`, envoyés en `null` quand vides
(`|| null`), ce qui est correct pour des chaînes optionnelles. La quantité est un `int`
borné 1..5 des deux côtés. Les prix de paliers sont testés par `!= null` et non par
véracité, pour ne pas masquer un palier à 0.

**Duplication signalée aux exécutants** — la condition d'éligibilité à l'achat direct
apparaît en tâche 4 (`handleSelectOffer`) et en tâche 5 (bouton de la carte). Les deux
doivent rester strictement identiques. Si l'exécutant de la tâche 5 peut l'extraire
dans un helper partagé sans déplacer de code existant, c'est préférable — à signaler
dans son rapport.

**Point de vigilance** — la tâche 3 dépend du sens d'import entre `coach_routes.py` et
`api.server`, non vérifié à l'écriture du plan. L'étape indique explicitement de le
contrôler et donne un repli via `api.pricing`.

## Ordre d'exécution

1 → 2 → 3 (backend, séquentiel : 2 et 3 touchent le même fichier).
4 → 5 (frontend, la 5 consomme la signature produite par la 4).
6 → 7 (wizard, même fichier).

Ordre recommandé : 1, 2, 3, 4, 5, 6, 7.

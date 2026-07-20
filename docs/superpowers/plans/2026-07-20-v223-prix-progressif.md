# Plan d'implémentation — V223 Prix progressif

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE — utiliser `superpowers:subagent-driven-development` (recommandé) ou `superpowers:executing-plans` pour exécuter ce plan tâche par tâche. Les étapes utilisent la syntaxe case à cocher (`- [ ]`).

**Objectif :** Permettre à une offre d'afficher 3 paliers de prix (Early Bird / Standard / Last Minute) et de vendre en « paiement d'abord, choix des dates ensuite », sans modifier le comportement d'aucune offre existante.

**Architecture :** Le calcul de prix est isolé dans un nouveau module pur `api/pricing.py` (aucune dépendance MongoDB), ce qui le rend testable unitairement — `api/server.py` ouvre une connexion Mongo dès l'import et n'est donc pas testable unitairement. Tout le reste est branché derrière `if offer.progressive_pricing`, de sorte que les offres actuelles empruntent le chemin de code existant, octet pour octet.

**Stack :** Python 3.11 / FastAPI / Pydantic v2 / Motor · React 19 / CRACO / Tailwind · Stripe · pytest

**Spec de référence :** `docs/superpowers/specs/2026-07-20-v223-design.md`

## Contraintes globales

Ces règles s'appliquent implicitement à **toutes** les tâches.

- **Interdiction absolue de supprimer ou modifier le comportement du code existant.** Tout est additif.
- Marquer chaque ajout : `# V223` (backend), `// V223` (frontend).
- **ES5 strict dans `ChatWidget.js`** (`var`, `function()`, `React.createElement`). Aucune tâche de ce plan ne touche ce fichier.
- Ne pas toucher : les 53 routes JWT, le Service Worker, le webhook vitrine, le webhook crédits.
- Devise : `CHF` en minuscules côté Stripe, `"CHF"` en majuscules dans les réponses API.
- Palette dashboard : fond noir, bordures `rgba(217,28,210,0.2)`, accent `#D91CD2`, texte blanc.
- Ne **jamais** `git push` — le push sur `main` déclenche un déploiement en production. Commits locaux uniquement.
- 🔴 **`DB_NAME=promo-credits-lab` EST LA BASE DE PRODUCTION.** Un serveur lancé en local avec le `.env` du projet écrit chez de vrais abonnés payants.
  - Vérifications autorisées : **lecture seule** (`GET`, `curl`, ouverture d'une page).
  - **Interdit sans accord explicite de l'utilisateur** : tout `POST`/`PUT`/`DELETE` de vérification, toute création de code `AFR-`, toute soumission du formulaire d'onboarding, tout achat de test.
  - En cas de doute sur l'effet d'écriture d'une vérification : ne pas l'exécuter, la signaler dans le compte rendu de tâche.
- Ne jamais mettre `frontend/build/` dans un commit (des modifications non liées y sont déjà présentes dans l'arbre de travail).

## Points de vigilance identifiés à l'exploration

1. `GET /offers` déclare `response_model=List[Offer]` (`api/server.py:1102`). FastAPI **filtre** tout champ absent du modèle : `active_price` et `active_tier` **doivent** être déclarés sur `Offer`, sinon ils disparaissent silencieusement de la réponse.
2. `api/server.py:92` instancie le client Mongo à l'import → `server.py` n'est pas importable dans un test unitaire. D'où `api/pricing.py`.
3. 24 des 26 fichiers de `tests/` sont des tests d'intégration (`requests` + `BASE_URL`) nécessitant un serveur lancé. Seule la tâche 1 fait du vrai TDD ; les autres se vérifient par tests d'intégration et contrôle manuel.

---

## Tâche 1 : Module de calcul de prix `api/pricing.py`

C'est la seule logique métier réellement testable unitairement, et celle qui porte le risque financier. Elle est traitée en TDD strict.

**Fichiers :**
- Créer : `api/pricing.py`
- Créer : `tests/test_pricing_v223.py`

**Interfaces :**
- Consomme : rien.
- Produit : `compute_active_price(offer: dict, now: datetime | None = None) -> dict` renvoyant `{"price": float, "tier": str, "original_price": float, "currency": "CHF"}`. `tier` ∈ `{"regular", "early_bird", "standard", "last_minute"}`. Le paramètre `now` est injectable pour rendre les tests déterministes.

- [ ] **Étape 1 : Installer pytest**

```bash
pip3 install pytest
```

Attendu : `Successfully installed pytest-...`

- [ ] **Étape 2 : Écrire les tests qui échouent**

Créer `tests/test_pricing_v223.py` :

```python
"""V223 — Tests unitaires du calcul de prix progressif.

Module pur : aucune connexion MongoDB, aucun serveur requis.
"""
from datetime import datetime, timezone, timedelta
import pytest

from api.pricing import compute_active_price

REF = datetime(2026, 9, 1, 19, 0, tzinfo=timezone.utc)


def _offer(**kw):
    base = {
        "price": 30.0,
        "progressive_pricing": True,
        "countdown_date": "2026-09-01",
        "countdown_time": "19:00",
        "price_early_bird": 15.0,
        "price_standard": 20.0,
        "price_last_minute": 30.0,
        "early_bird_days_before": 7,
        "standard_hours_before": 24,
    }
    base.update(kw)
    return base


def test_offre_non_progressive_retourne_prix_normal():
    res = compute_active_price({"price": 42.0}, now=REF)
    assert res == {"price": 42.0, "tier": "regular",
                   "original_price": 42.0, "currency": "CHF"}


def test_progressif_sans_countdown_date_retombe_sur_regular():
    """Garde-fou anti-perte de revenu : jamais Early Bird par défaut."""
    res = compute_active_price(_offer(countdown_date=None), now=REF)
    assert res["tier"] == "regular"
    assert res["price"] == 30.0


def test_plus_de_7_jours_avant_early_bird():
    res = compute_active_price(_offer(), now=REF - timedelta(days=10))
    assert res["tier"] == "early_bird"
    assert res["price"] == 15.0
    assert res["original_price"] == 30.0


def test_entre_24h_et_7_jours_standard():
    res = compute_active_price(_offer(), now=REF - timedelta(days=3))
    assert res["tier"] == "standard"
    assert res["price"] == 20.0


def test_moins_de_24h_last_minute():
    res = compute_active_price(_offer(), now=REF - timedelta(hours=2))
    assert res["tier"] == "last_minute"
    assert res["price"] == 30.0


def test_date_depassee_reste_last_minute():
    res = compute_active_price(_offer(), now=REF + timedelta(days=5))
    assert res["tier"] == "last_minute"


def test_frontiere_exactement_7_jours_bascule_en_standard():
    """À exactement 7 jours on n'est plus « plus de 7 jours avant »."""
    res = compute_active_price(_offer(), now=REF - timedelta(days=7))
    assert res["tier"] == "standard"


def test_palier_non_defini_retombe_sur_prix_de_base():
    """Une config partielle ne doit jamais produire un prix nul."""
    res = compute_active_price(_offer(price_early_bird=None),
                               now=REF - timedelta(days=10))
    assert res["tier"] == "early_bird"
    assert res["price"] == 30.0


def test_countdown_time_absent_utilise_minuit():
    res = compute_active_price(_offer(countdown_time=None),
                               now=datetime(2026, 8, 20, tzinfo=timezone.utc))
    assert res["tier"] == "early_bird"


def test_countdown_date_malformee_retombe_sur_regular():
    """Une saisie dashboard invalide ne doit pas faire planter la vitrine."""
    res = compute_active_price(_offer(countdown_date="pas-une-date"), now=REF)
    assert res["tier"] == "regular"
    assert res["price"] == 30.0


def test_prix_absent_vaut_zero_sans_planter():
    res = compute_active_price({}, now=REF)
    assert res["price"] == 0.0
    assert res["tier"] == "regular"
```

- [ ] **Étape 3 : Lancer les tests pour vérifier qu'ils échouent**

```bash
cd /Users/afroboost/afroboost-v11-dev && python3 -m pytest tests/test_pricing_v223.py -v
```

Attendu : `ModuleNotFoundError: No module named 'api.pricing'` (11 erreurs de collecte).

- [ ] **Étape 4 : Écrire l'implémentation minimale**

Créer `api/pricing.py` :

```python
"""V223 — Calcul du prix progressif à 3 paliers.

Module volontairement pur : aucun accès base de données, aucun import de
server.py (qui ouvre une connexion MongoDB dès l'import). C'est ce qui rend
cette logique — la seule à porter un risque financier direct — testable
unitairement.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)

CURRENCY = "CHF"


def _reference_datetime(offer: dict) -> Optional[datetime]:
    """Date de référence = countdown_date + countdown_time (v132).

    Renvoie None si la date est absente ou malformée : l'appelant retombe
    alors sur le prix normal.
    """
    raw_date = offer.get("countdown_date")
    if not raw_date:
        return None
    raw_time = offer.get("countdown_time") or "00:00"
    try:
        parsed = datetime.strptime(f"{raw_date} {raw_time}", "%Y-%m-%d %H:%M")
        return parsed.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logger.warning(f"[V223] countdown_date invalide: {raw_date!r} {raw_time!r}")
        return None


def compute_active_price(offer: dict, now: Optional[datetime] = None) -> dict:
    """Renvoie le prix et le palier actifs d'une offre.

    `now` est injectable pour rendre les tests déterministes.
    """
    base_price = float(offer.get("price") or 0)

    def regular():
        return {"price": base_price, "tier": "regular",
                "original_price": base_price, "currency": CURRENCY}

    if not offer.get("progressive_pricing"):
        return regular()

    reference = _reference_datetime(offer)
    if reference is None:
        # Aucune date de référence : on ne peut pas situer l'acheteur dans le
        # temps. On retombe sur le prix normal — surtout pas sur Early Bird,
        # qui ferait vendre au tarif le plus bas toute offre mal configurée.
        return regular()

    now = now or datetime.now(timezone.utc)
    remaining = reference - now

    days_before = int(offer.get("early_bird_days_before") or 7)
    hours_before = int(offer.get("standard_hours_before") or 24)

    if remaining > timedelta(days=days_before):
        tier, tier_price = "early_bird", offer.get("price_early_bird")
    elif remaining > timedelta(hours=hours_before):
        tier, tier_price = "standard", offer.get("price_standard")
    else:
        # Inclut le cas « date dépassée » (remaining négatif).
        tier, tier_price = "last_minute", offer.get("price_last_minute")

    # Un palier non renseigné retombe sur le prix de base : une configuration
    # partielle ne doit jamais produire un prix nul.
    price = float(tier_price) if tier_price is not None else base_price

    return {"price": price, "tier": tier,
            "original_price": base_price, "currency": CURRENCY}
```

- [ ] **Étape 5 : Lancer les tests pour vérifier qu'ils passent**

```bash
cd /Users/afroboost/afroboost-v11-dev && python3 -m pytest tests/test_pricing_v223.py -v
```

Attendu : `11 passed`.

- [ ] **Étape 6 : Commit**

```bash
git add api/pricing.py tests/test_pricing_v223.py
git commit -m "V223: Module pur de calcul du prix progressif + tests unitaires

Isolé de server.py (qui ouvre une connexion Mongo à l'import) pour être
testable sans base ni serveur. Sans countdown_date, on retombe sur le prix
normal et jamais sur Early Bird, pour qu'une offre mal configurée ne se vende
pas au tarif le plus bas.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 2 : Champs V223 sur le modèle `Offer`

**Fichiers :**
- Modifier : `api/server.py:363-401` (classe `Offer`) et la classe `OfferCreate` qui suit.

**Interfaces :**
- Consomme : rien.
- Produit : les champs `progressive_pricing`, `price_early_bird`, `price_standard`, `price_last_minute`, `early_bird_days_before`, `standard_hours_before`, `pack_sessions`, `active_price`, `active_tier` sur `Offer`.

- [ ] **Étape 1 : Ajouter les champs à `Offer`**

Dans `api/server.py`, juste après le bloc `# v132: Compte à rebours` de la classe `Offer` (après `countdown_text: Optional[str] = None`), insérer :

```python
    # V223: Prix progressif 3 paliers — référence temporelle = countdown_date
    progressive_pricing: bool = False
    price_early_bird: Optional[float] = None
    price_standard: Optional[float] = None
    price_last_minute: Optional[float] = None
    early_bird_days_before: int = 7
    standard_hours_before: int = 24
    # V223: Pack de crédits (remplace la déduction par regex sur le nom produit)
    pack_sessions: Optional[int] = None
    # V223: Calculés à la lecture. DOIVENT être déclarés ici, sinon le
    # response_model=List[Offer] de GET /offers les filtrerait silencieusement.
    active_price: Optional[float] = None
    active_tier: Optional[str] = None
```

- [ ] **Étape 2 : Ajouter les mêmes champs d'écriture à `OfferCreate`**

Dans la classe `OfferCreate`, après les champs e-commerce, insérer (sans `active_price` ni `active_tier`, qui sont calculés et non écrits) :

```python
    # V223: Prix progressif 3 paliers
    progressive_pricing: bool = False
    price_early_bird: Optional[float] = None
    price_standard: Optional[float] = None
    price_last_minute: Optional[float] = None
    early_bird_days_before: int = 7
    standard_hours_before: int = 24
    pack_sessions: Optional[int] = None
```

- [ ] **Étape 3 : Vérifier que les offres existantes se désérialisent à l'identique**

Créer `tests/test_offer_model_v223.py` :

```python
"""V223 — Une offre au format actuel doit rester valide et inchangée."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_offre_legacy_reste_valide(monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017")
    from api.server import Offer

    legacy = Offer(id="abc", name="Pack 10 séances", price=250.0)

    assert legacy.price == 250.0
    assert legacy.progressive_pricing is False
    assert legacy.pack_sessions is None
    assert legacy.active_tier is None
    assert legacy.early_bird_days_before == 7
```

- [ ] **Étape 4 : Lancer le test**

```bash
cd /Users/afroboost/afroboost-v11-dev && python3 -m pytest tests/test_offer_model_v223.py -v
```

Attendu : `1 passed`.

Si l'import de `api.server` échoue malgré `MONGO_URL` (le client Motor est instancié à l'import), noter l'échec, **supprimer ce fichier de test** et vérifier la désérialisation manuellement via `GET /api/offers` à la tâche 3. Ne pas contourner en modifiant `server.py:92`.

- [ ] **Étape 5 : Commit**

```bash
git add api/server.py tests/test_offer_model_v223.py
git commit -m "V223: Champs prix progressif + pack_sessions sur le modele Offer

active_price/active_tier sont declares sur le modele car GET /offers utilise
response_model=List[Offer], qui filtrerait tout champ non declare.
Tous les defauts reproduisent le comportement actuel.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 3 : Exposer le prix actif dans l'API

**Fichiers :**
- Modifier : `api/server.py:1102-1114` (`GET /offers`)
- Modifier : `api/server.py` (ajouter `GET /offers/{offer_id}/active-price`)

**Interfaces :**
- Consomme : `compute_active_price` (tâche 1), champs `Offer` (tâche 2).
- Produit : chaque offre renvoyée porte `active_price` et `active_tier` ; endpoint `GET /api/offers/{offer_id}/active-price` → `{price, tier, original_price, currency}`.

- [ ] **Étape 1 : Importer le module de prix**

En haut de `api/server.py`, dans le bloc d'imports :

```python
from api.pricing import compute_active_price  # V223
```

Si l'import relatif échoue au démarrage (`api` non traité comme package selon le point d'entrée), utiliser `from .pricing import compute_active_price`. Vérifier avec `python3 -c "import api.server"` après avoir positionné `MONGO_URL`.

- [ ] **Étape 2 : Enrichir `GET /offers`**

Dans le corps de la fonction, juste avant le `return`, enrichir chaque offre. Ne **rien** retirer de l'existant :

```python
        # V223: prix actif calculé à la lecture (évite une requête par carte)
        for _o in offers:
            _p = compute_active_price(_o)
            _o["active_price"] = _p["price"]
            _o["active_tier"] = _p["tier"]
```

Adapter le nom de la variable de liste à celui réellement utilisé dans la fonction.

- [ ] **Étape 3 : Ajouter l'endpoint dédié**

Juste après la fonction `GET /offers` :

```python
# V223: Prix actif d'une offre — utilisé par la page activité
@api_router.get("/offers/{offer_id}/active-price")
async def get_offer_active_price(offer_id: str):
    offer = await db.offers.find_one({"id": offer_id}, {"_id": 0})
    if not offer:
        raise HTTPException(status_code=404, detail="Offre introuvable")
    return compute_active_price(offer)
```

- [ ] **Étape 4 : Vérifier manuellement**

Lancer le serveur puis :

```bash
curl -s http://localhost:8080/api/offers | head -c 600
```

Attendu : chaque offre porte `active_price` et `active_tier`. Pour une offre existante (non progressive), `active_tier` vaut `"regular"` et `active_price` est **égal** à `price`.

**Point de contrôle anti-régression :** si `active_price` diffère de `price` sur une offre existante, arrêter et corriger avant de continuer.

- [ ] **Étape 5 : Commit**

```bash
git add api/server.py
git commit -m "V223: Exposer active_price/active_tier sur GET /offers + endpoint dedie

Le calcul se fait a la lecture pour que la page d'accueil affiche les paliers
sans une requete supplementaire par carte.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 4 : Correctifs du webhook Stripe

Tâche la plus sensible du plan : ce code est traversé par **tous** les paiements, y compris ceux des abonnés actuels.

**Fichiers :**
- Modifier : `api/server.py:3316-3320` (metadata checkout)
- Modifier : `api/server.py:3634` (`customer_email`)
- Modifier : `api/server.py:3649-3659` (`sessions_count`)

**Interfaces :**
- Consomme : `pack_sessions` (tâche 2).
- Produit : metadata Stripe enrichie de `pack_sessions` et `tier` ; `sessions_count` fiable.

- [ ] **Étape 1 : Enrichir la metadata du checkout**

`api/server.py:3316`, ajouter deux clés **sans toucher** aux existantes :

```python
    metadata = {
        "product_name": request.productName,
        "customer_email": request.customerEmail or "",
        "source": "afroboost_checkout",
        # V223: crédits explicites + palier tarifaire
        "pack_sessions": str(getattr(request, "packSessions", "") or ""),
        "tier": getattr(request, "tier", "") or "",
    }
```

`getattr` avec défaut est utilisé parce que les appelants existants n'envoient pas ces champs : leur absence doit rester silencieuse.

- [ ] **Étape 2 : Ajouter les champs optionnels au modèle de requête checkout**

Localiser le modèle Pydantic de `request` (celui portant `productName` / `customerEmail`) et y ajouter :

```python
    packSessions: Optional[int] = None  # V223
    tier: Optional[str] = None          # V223
```

- [ ] **Étape 3 : Corriger `customer_email` (correctif bloquant)**

`api/server.py:3634`. Ligne actuelle :

```python
customer_email = session.get("customer_email") or metadata.get("customer_email", "")
```

La remplacer par :

```python
                # V223: quand Stripe collecte lui-même l'email (parcours sans
                # formulaire), il le place dans customer_details.email et NON
                # dans customer_email. Sans ce repli, l'acheteur paie et ne
                # reçoit ni code ni accès à son espace.
                customer_email = (session.get("customer_details") or {}).get("email") \
                    or session.get("customer_email") \
                    or metadata.get("customer_email", "")
```

**L'ordre des deux termes d'origine est préservé** : c'est un élargissement de repli, pas un changement de priorité.

- [ ] **Étape 4 : Fiabiliser `sessions_count`**

`api/server.py:3647-3656`. Remplacer le bloc existant :

```python
                # V204: Calcul intelligent du nombre de séances depuis le nom du produit
                import re as _re_webhook
                sessions_count = 1  # défaut
                # Chercher "x10", "x5", "x20", "x40" etc. dans le nom
                x_match = _re_webhook.search(r'x\s*(\d+)', product_name, _re_webhook.IGNORECASE)
                if x_match:
                    sessions_count = int(x_match.group(1))
                elif "10" in product_name:
                    sessions_count = 10
                elif "5" in product_name:
                    sessions_count = 5
```

par :

```python
                # V223: si l'offre déclare ses crédits, on les utilise.
                # La regex V204 devient le repli des offres historiques : elle
                # accorde 10 crédits à un produit nommé « Cours du 10 mai ».
                import re as _re_webhook
                sessions_count = 1  # défaut
                _pack = metadata.get("pack_sessions") or ""
                if _pack.isdigit() and int(_pack) > 0:
                    sessions_count = int(_pack)
                else:
                    # V204 — logique d'origine, strictement inchangée
                    x_match = _re_webhook.search(r'x\s*(\d+)', product_name, _re_webhook.IGNORECASE)
                    if x_match:
                        sessions_count = int(x_match.group(1))
                    elif "10" in product_name:
                        sessions_count = 10
                    elif "5" in product_name:
                        sessions_count = 5
```

La ligne `new_code = f"AFR-..."` qui suit immédiatement ne doit pas être modifiée ni ré-indentée.

- [ ] **Étape 5 : Vérifier le non-régression du parcours actuel**

Sans serveur Stripe, vérifier par lecture que pour un paiement du **formulaire actuel** :
- `metadata["pack_sessions"]` vaut `""` → `.isdigit()` est `False` → la regex s'applique comme avant ;
- `metadata["customer_email"]` est renseigné → `customer_email` est identique à avant.

Puis vérifier que le serveur démarre :

```bash
cd /Users/afroboost/afroboost-v11-dev && python3 -c "import ast; ast.parse(open('api/server.py').read()); print('syntaxe OK')"
```

Attendu : `syntaxe OK`.

- [ ] **Étape 6 : Commit**

```bash
git add api/server.py
git commit -m "V223: Webhook — email Stripe et credits explicites

- customer_details.email en premier repli : sans formulaire, Stripe collecte
  lui-meme l'email et ne renseigne pas customer_email. L'ordre des replis
  existants est preserve, le parcours formulaire est inchange.
- pack_sessions prioritaire sur la regex du nom de produit, qui accorde
  aujourd'hui 10 credits a un produit nomme « Cours du 10 mai ».

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 5 : Endpoint de profil abonné

**Fichiers :**
- Modifier : `api/server.py` (ajouter la route près des routes `/subscriptions` existantes)

**Interfaces :**
- Consomme : rien.
- Produit : `PUT /api/subscriptions/{code}/profile`, corps `{"name": str, "whatsapp": str}` → `{"success": true}`.

- [ ] **Étape 1 : Ajouter le modèle et la route**

```python
# V223: Complément de profil depuis l'espace abonné
class SubscriberProfileUpdate(BaseModel):
    name: Optional[str] = None
    whatsapp: Optional[str] = None


@api_router.put("/subscriptions/{code}/profile")
async def update_subscriber_profile(code: str, payload: SubscriberProfileUpdate):
    code_upper = (code or "").strip().upper()
    subscription = await db.subscriptions.find_one({"code": code_upper}, {"_id": 0})
    if not subscription:
        raise HTTPException(status_code=404, detail="Code introuvable")

    now_iso = datetime.now(timezone.utc).isoformat()
    updates = {"updated_at": now_iso}
    if payload.name:
        updates["name"] = payload.name.strip()
    if payload.whatsapp:
        updates["whatsapp"] = payload.whatsapp.strip()

    await db.subscriptions.update_one({"code": code_upper}, {"$set": updates})

    # V223: le CRM lit chat_participants — la collection « contacts » n'existe
    # pas ; y écrire rendrait ces données invisibles au dashboard.
    email = subscription.get("email") or ""
    if email:
        await db.chat_participants.update_one(
            {"email": email},
            {"$set": {**updates, "email": email, "source": "espace_onboarding",
                      "code": code_upper},
             "$setOnInsert": {"created_at": now_iso}},
            upsert=True,
        )

    return {"success": True}
```

- [ ] **Étape 2 : Vérifier la syntaxe**

```bash
cd /Users/afroboost/afroboost-v11-dev && python3 -c "import ast; ast.parse(open('api/server.py').read()); print('syntaxe OK')"
```

Attendu : `syntaxe OK`.

- [ ] **Étape 3 : Commit**

```bash
git add api/server.py
git commit -m "V223: Endpoint PUT /subscriptions/{code}/profile

Ecrit dans subscriptions puis upsert dans chat_participants, qui est la
collection reellement lue par le CRM.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 6 : Section prix progressif dans le dashboard

**Fichiers :**
- Modifier : `frontend/src/components/dashboard/OffersManager.js:520` (après le champ prix)

Le formulaire est partagé création/édition (`newOffer` + `editingOfferId`) : **un seul point d'insertion**.

**Interfaces :**
- Consomme : champs `OfferCreate` (tâche 2).
- Produit : `newOffer.progressive_pricing`, `.price_early_bird`, `.price_standard`, `.price_last_minute`, `.pack_sessions`.

- [ ] **Étape 1 : Insérer la section après le champ prix**

Juste après le `<input>` de la ligne 520 :

```jsx
{/* V223: Prix progressif 3 paliers */}
<div className="mt-4 p-4 rounded-lg" style={{ background: '#000', border: '1px solid rgba(217,28,210,0.2)' }}>
  <label className="flex items-center gap-3 cursor-pointer">
    <input
      type="checkbox"
      checked={!!newOffer.progressive_pricing}
      onChange={e => setNewOffer({ ...newOffer, progressive_pricing: e.target.checked })}
      className="accent-[#D91CD2] w-4 h-4"
    />
    <span className="text-white text-sm font-medium">📊 Activer les 3 paliers de prix</span>
  </label>
  <p className="text-xs mt-1 ml-7" style={{ color: 'rgba(255,255,255,0.5)' }}>
    Récompense les réservations en avance et capture les réservations de dernière minute.
  </p>

  {newOffer.progressive_pricing && (
    <div className="mt-4 space-y-3">
      {!newOffer.countdown_date && (
        <p className="text-xs p-2 rounded" style={{ background: 'rgba(217,28,210,0.1)', color: '#D91CD2' }}>
          ⚠️ Activez le compte à rebours ci-dessous : sans date de référence, les
          paliers ne s'appliquent pas et le prix normal reste affiché.
        </p>
      )}
      {[
        { key: 'price_early_bird', label: '✨ Early Bird (plus de 7 jours avant)' },
        { key: 'price_standard', label: '⏱ Standard (plus de 24h avant)' },
        { key: 'price_last_minute', label: '⚡ Last Minute (moins de 24h)' },
      ].map(f => (
        <div key={f.key}>
          <label className="block text-xs mb-1" style={{ color: 'rgba(255,255,255,0.7)' }}>{f.label}</label>
          <input
            type="number"
            value={newOffer[f.key] ?? ''}
            onChange={e => setNewOffer({ ...newOffer, [f.key]: e.target.value === '' ? null : parseFloat(e.target.value) })}
            className="w-full px-3 py-2 rounded-lg neon-input text-sm"
            placeholder="CHF"
          />
        </div>
      ))}
      <button
        type="button"
        onClick={() => {
          const base = parseFloat(newOffer.price) || 0;
          setNewOffer({
            ...newOffer,
            price_early_bird: base,
            price_standard: Math.round(base * 1.33),
            price_last_minute: base * 2,
          });
        }}
        className="text-xs underline"
        style={{ color: '#D91CD2' }}
      >
        Réinitialiser aux valeurs suggérées
      </button>
    </div>
  )}

  <div className="mt-4">
    <label className="block text-xs mb-1" style={{ color: 'rgba(255,255,255,0.7)' }}>
      Nombre de séances incluses (pack)
    </label>
    <input
      type="number"
      value={newOffer.pack_sessions ?? ''}
      onChange={e => setNewOffer({ ...newOffer, pack_sessions: e.target.value === '' ? null : parseInt(e.target.value, 10) })}
      className="w-full px-3 py-2 rounded-lg neon-input text-sm"
      placeholder="ex: 10"
    />
    <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.5)' }}>
      Si rempli, l'acheteur reçoit un espace personnel avec ce nombre de crédits.
    </p>
  </div>
</div>
```

- [ ] **Étape 2 : Vérifier que le build passe**

```bash
cd /Users/afroboost/afroboost-v11-dev/frontend && CI=false npx craco build 2>&1 | tail -20
```

Attendu : `Compiled successfully` ou `Compiled with warnings`. Aucune erreur.

- [ ] **Étape 3 : Vérifier manuellement**

Ouvrir le dashboard → Gestion → Offres. Contrôler : le toggle est éteint sur toutes les offres existantes ; l'activer révèle les 3 champs ; « valeurs suggérées » sur un prix de 15 donne 15 / 20 / 30.

- [ ] **Étape 4 : Commit**

```bash
git add frontend/src/components/dashboard/OffersManager.js
git commit -m "V223: Section prix progressif + pack_sessions dans OffersManager

Formulaire partage creation/edition : un seul point d'insertion.
Avertissement affiche si le compte a rebours n'est pas configure, car sans
date de reference les paliers ne s'appliquent pas.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 7 : Onboarding de l'espace abonné

**Fichiers :**
- Créer : `frontend/src/components/SubscriberOnboarding.js`
- Modifier : `frontend/src/components/SubscriberSpace.js` (import + une condition, **rien d'autre**)

**Interfaces :**
- Consomme : `PUT /api/subscriptions/{code}/profile` (tâche 5).
- Produit : composant `<SubscriberOnboarding code subscription onDone />`.

- [ ] **Étape 1 : Créer le composant**

```jsx
// V223: Écran de complément de profil, affiché une seule fois à l'ouverture
// de l'espace abonné. Isolé dans son propre fichier : SubscriberSpace.js fait
// 57 Ko et sert tous les abonnés payants actuels.
import React, { useState } from 'react';
import axios from 'axios';

export default function SubscriberOnboarding({ code, subscription, onDone }) {
  const [name, setName] = useState(subscription?.name || '');
  const [whatsapp, setWhatsapp] = useState(subscription?.whatsapp || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    if (!name.trim()) { setError('Merci d\'indiquer ton nom.'); return; }
    setSaving(true);
    setError('');
    try {
      await axios.put(`/api/subscriptions/${code}/profile`, {
        name: name.trim(),
        whatsapp: whatsapp.trim(),
      });
      onDone();
    } catch (e) {
      // L'échec réseau ne doit jamais bloquer l'accès à des crédits payés.
      setError('Enregistrement impossible. Tu peux continuer et réessayer plus tard.');
      setSaving(false);
    }
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0A0A0F', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ maxWidth: 420, width: '100%', background: '#000', border: '1px solid rgba(217,28,210,0.2)', borderRadius: 16, padding: 28 }}>
        <h2 style={{ color: '#fff', fontSize: 22, margin: '0 0 8px', textAlign: 'center' }}>
          Bienvenue chez Afroboost ! 🎉
        </h2>
        <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14, textAlign: 'center', margin: '0 0 24px' }}>
          Complète ton profil pour réserver tes séances.
        </p>

        <label style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, display: 'block', marginBottom: 6 }}>Nom complet</label>
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          style={{ width: '100%', padding: '12px', borderRadius: 10, background: '#0A0A0F', border: '1px solid rgba(217,28,210,0.3)', color: '#fff', marginBottom: 16 }}
        />

        <label style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, display: 'block', marginBottom: 6 }}>WhatsApp</label>
        <input
          value={whatsapp}
          onChange={e => setWhatsapp(e.target.value)}
          placeholder="+41 76 000 00 00"
          style={{ width: '100%', padding: '12px', borderRadius: 10, background: '#0A0A0F', border: '1px solid rgba(217,28,210,0.3)', color: '#fff', marginBottom: 20 }}
        />

        {error && <p style={{ color: '#ff6b6b', fontSize: 13, marginBottom: 12 }}>{error}</p>}

        <button
          onClick={submit}
          disabled={saving}
          style={{ width: '100%', padding: '14px', borderRadius: 10, background: '#D91CD2', color: '#fff', fontWeight: 'bold', border: 'none', cursor: 'pointer', opacity: saving ? 0.6 : 1 }}
        >
          {saving ? 'Enregistrement…' : "C'est parti →"}
        </button>

        {/* Échappatoire obligatoire : sans elle, tout abonné existant sans
            name/whatsapp serait enfermé hors de crédits déjà payés. */}
        <button
          onClick={onDone}
          style={{ width: '100%', marginTop: 12, background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', fontSize: 13, cursor: 'pointer' }}
        >
          Plus tard
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Étape 2 : Brancher la porte dans `SubscriberSpace.js`**

Ajouter l'import en haut :

```jsx
import SubscriberOnboarding from './SubscriberOnboarding'; // V223
```

Ajouter un state près des autres `useState` :

```jsx
const [onboardingDone, setOnboardingDone] = useState(false); // V223
```

Puis, **juste avant le `return` principal** du composant, insérer la porte :

```jsx
  // V223: profil incomplet → écran de bienvenue, une seule fois
  const needsOnboarding = !onboardingDone && subscription &&
    (!subscription.name || !subscription.whatsapp);
  if (needsOnboarding) {
    return (
      <SubscriberOnboarding
        code={code}
        subscription={subscription}
        onDone={() => setOnboardingDone(true)}
      />
    );
  }
```

Adapter `subscription` et `code` aux noms de variables réellement présents dans le composant. **Ne modifier aucune autre ligne du fichier.**

- [ ] **Étape 3 : Vérifier le build**

```bash
cd /Users/afroboost/afroboost-v11-dev/frontend && CI=false npx craco build 2>&1 | tail -20
```

Attendu : compilation réussie.

- [ ] **Étape 4 : Vérifier manuellement**

Ouvrir `/espace/<un code existant>`. Si la fiche a déjà `name` et `whatsapp`, l'espace s'affiche directement. Sinon le formulaire apparaît, et « Plus tard » donne accès à l'espace.

**Point de contrôle anti-régression :** vérifier qu'un abonné existant peut toujours atteindre ses crédits, avec ou sans profil complet.

- [ ] **Étape 5 : Commit**

```bash
git add frontend/src/components/SubscriberOnboarding.js frontend/src/components/SubscriberSpace.js
git commit -m "V223: Ecran de complement de profil a la premiere visite de /espace/

Isole dans son propre composant : SubscriberSpace.js n'est touche que par un
import et une condition. Lien « Plus tard » obligatoire, sinon un abonne
existant sans name/whatsapp serait enferme hors de credits deja payes.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 8 : Affichage des paliers sur les cartes d'offres

**Fichiers :**
- Modifier : `frontend/src/App.js` (composant `OfferCardSlider`)

**Interfaces :**
- Consomme : `active_price` / `active_tier` (tâche 3).
- Produit : badge et prix de palier sur les cartes.

Le composant est défini à `frontend/src/App.js:1211` et affiche le prix à la **ligne 1411** :

```jsx
                CHF {offer.price}.-
```

- [ ] **Étape 2 : Ajouter le helper de badge**

Au-dessus du composant `OfferCardSlider` :

```jsx
// V223: libellé et couleur du palier tarifaire actif
const V223_TIERS = {
  early_bird:  { label: '🎯 Early Bird', color: '#22c55e' },
  standard:    { label: 'Standard',      color: '#eab308' },
  last_minute: { label: '🔥 Last Minute', color: '#ef4444' },
};
```

- [ ] **Étape 3 : Afficher le badge et le prix actif**

À la ligne 1411, remplacer :

```jsx
                CHF {offer.price}.-
```

par :

```jsx
                {/* V223: prix du palier actif, sinon rendu d'origine */}
                CHF {offer.progressive_pricing && offer.active_price != null
                       ? offer.active_price
                       : offer.price}.-
```

Puis, juste après le `</span>` fermant (ligne 1412) et **avant** le bloc `{offer.tva > 0 && ...}`, insérer le badge :

```jsx
              {/* V223: badge du palier tarifaire */}
              {offer.progressive_pricing && V223_TIERS[offer.active_tier] && (
                <span style={{
                  fontSize: 11, padding: '2px 8px', borderRadius: 999,
                  background: `${V223_TIERS[offer.active_tier].color}22`,
                  color: V223_TIERS[offer.active_tier].color,
                }}>
                  {V223_TIERS[offer.active_tier].label}
                </span>
              )}
```

Le `style` du `<span>` du prix (couleur, `textShadow`, `className`) n'est pas modifié : une offre sans `progressive_pricing` rend exactement `CHF {offer.price}.-` comme aujourd'hui.

- [ ] **Étape 4 : Vérifier le build puis commit**

```bash
cd /Users/afroboost/afroboost-v11-dev/frontend && CI=false npx craco build 2>&1 | tail -20
git add frontend/src/App.js
git commit -m "V223: Prix du palier actif et badge sur les cartes d'offres

Branche conditionnee a progressive_pricing : les cartes actuelles conservent
leur rendu exact.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Tâche 9 : Page activité et parcours paiement direct

Dernière tâche : elle assemble tout le reste. À n'entamer qu'une fois les tâches 1 à 8 vérifiées.

**Fichiers :**
- Modifier : `frontend/src/App.js` (vue détail d'une offre)

**Interfaces :**
- Consomme : `GET /api/offers/{id}/active-price` (tâche 3), metadata checkout (tâche 4).
- Produit : page activité à 3 paliers avec redirection directe vers Stripe.

- [ ] **Étape 1 : Afficher les 3 cartes de paliers**

Dans la vue détail, à l'intérieur d'une garde `{offer.progressive_pricing && (...)}` :

```jsx
{/* V223: Grille des 3 paliers */}
<div style={{ marginTop: 24 }}>
  <h3 style={{ color: '#fff', margin: 0 }}>Prix progressif</h3>
  <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: 14, marginTop: 4 }}>
    Plus tu réserves tôt, moins c'est cher.
  </p>
  <div style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
    {[
      { key: 'early_bird',  icon: '✨', title: 'EARLY BIRD',  price: offer.price_early_bird },
      { key: 'standard',    icon: '⏱', title: 'STANDARD',    price: offer.price_standard },
      { key: 'last_minute', icon: '⚡', title: 'LAST MINUTE', price: offer.price_last_minute },
    ].map(t => (
      <div key={t.key} style={{
        flex: '1 1 140px', padding: 16, borderRadius: 12, background: '#000',
        border: offer.active_tier === t.key
          ? '2px solid #D91CD2'
          : '1px solid rgba(217,28,210,0.2)',
      }}>
        <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.6)' }}>{t.icon} {t.title}</div>
        <div style={{ fontSize: 22, color: '#fff', fontWeight: 'bold', marginTop: 6 }}>
          {t.price ?? offer.price} CHF
        </div>
      </div>
    ))}
  </div>
</div>
```

- [ ] **Étape 2 : Bouton de réservation vers Stripe**

```jsx
{/* V223: paiement direct — Stripe collecte lui-même l'email */}
<button
  onClick={async () => {
    const res = await axios.post('/api/create-checkout-session', {
      productName: offer.name,
      amount: offer.active_price ?? offer.price,
      customerEmail: '',
      packSessions: offer.pack_sessions || null,
      tier: offer.active_tier || null,
      originUrl: window.location.origin,
    });
    window.location.href = res.data.url;
  }}
  style={{ width: '100%', padding: '16px', borderRadius: 12, background: '#D91CD2', color: '#fff', fontWeight: 'bold', fontSize: 16, border: 'none', cursor: 'pointer', marginTop: 20 }}
>
  Réserver — {offer.active_price ?? offer.price} CHF →
</button>
<p style={{ textAlign: 'center', color: 'rgba(255,255,255,0.5)', fontSize: 12, marginTop: 8 }}>
  Palier {V223_TIERS[offer.active_tier]?.label || 'Standard'}
</p>
```

Avant d'écrire ce code, ouvrir l'appel existant à `/api/create-checkout-session` dans `App.js` et **reprendre exactement** ses noms de champs et sa lecture de réponse (`res.data.url` ou `res.data.checkout_url`).

- [ ] **Étape 3 : Conserver le formulaire pour les offres non progressives**

Vérifier que le formulaire actuel reste rendu à l'identique quand `progressive_pricing` est faux — il ne doit être ni déplacé ni ré-indenté.

- [ ] **Étape 4 : Vérifier le build**

```bash
cd /Users/afroboost/afroboost-v11-dev/frontend && CI=false npx craco build 2>&1 | tail -20
```

- [ ] **Étape 5 : Test de bout en bout en mode test Stripe**

Avec une clé Stripe de test, acheter une offre progressive et vérifier dans l'ordre :
1. redirection vers Stripe sans formulaire préalable ;
2. Stripe demande bien l'email ;
3. après paiement, un document `subscriptions` existe avec un `email` **non vide** (c'est le correctif de la tâche 4 — s'il est vide, arrêter) ;
4. `total_sessions` est égal au `pack_sessions` de l'offre ;
5. l'email de confirmation arrive avec le code ;
6. `/espace/<code>` affiche l'écran d'onboarding.

- [ ] **Étape 6 : Commit**

```bash
git add frontend/src/App.js
git commit -m "V223: Page activite a 3 paliers et paiement direct Stripe

Le formulaire actuel reste le chemin par defaut de toute offre sans
progressive_pricing.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Hors périmètre de ce plan

**`PaymentSuccessPage.jsx` (§5.5 de la spec) n'est volontairement pas réactivée ici.** Elle a été désactivée délibérément en v158.7 (`App.js:4812`) et la raison n'est pas documentée. Les tâches 1 à 9 délivrent un parcours complet sans elle : après paiement, l'acheteur reçoit son code par email, ce qui est précisément le comportement que la v158.7 avait choisi. À traiter en tâche séparée une fois la raison de la désactivation retrouvée.

**Vérification de signature du webhook** (`server.py:3469`) — faille réelle, à corriger dans un commit dédié comme indiqué en §8 de la spec.

## Questions tranchées (20 juillet 2026)

1. **`DB_NAME` = `promo-credits-lab`, et c'est la PRODUCTION.** Voir la contrainte de sécurité en tête de plan.
2. **`PaymentSuccessPage`** — raison de la désactivation v158.7 perdue. Décision : **on ne la réactive pas**. Le parcours par email suffit. La section « Hors périmètre » est définitive.
3. **Webhook confirmé** : la branche `else` de `server.py:3624-3849` traite bien les achats d'offres. L'abandon des chantiers 2C et 2E est validé.

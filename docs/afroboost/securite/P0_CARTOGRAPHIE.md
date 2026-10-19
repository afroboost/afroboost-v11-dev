# P0 — Cartographie pré-correction (19/10/2026)

> Établie **avant toute modification**, à partir de `IMPLEMENTATION_PLAN.md`, `LIVE_AUDIT.md` et d'une relecture du code
> (`main` = `0a575c9b`). État réel vérifié en lecture seule : drapeaux `REQUIRE_COACH_JWT`, `SUPERADMIN_JWT_STRICT`,
> `CHAT_READ_STRICT`, `SUBSCRIBER_STRICT_ENTRY`, `META_WEBHOOK_SIGNATURE_ENABLED` = **true** ; `UPLOADS_IDENTITE_STRICTE`
> = false. Journaux de production (≈ 10 h, 5 000 lignes) : **0** usage du repli `X-User-Email` (`[V265]`).
> Inventaire statique : **228 routes** accordent un privilège super-admin ; **67** tirent l'identité d'une source falsifiable
> (en-tête direct, `require_auth`, `_v263`, `_v319`, champ du corps).

## Lot P0-A — Authentification admin

| RISQUE | FICHIER | ROUTE | PROTECTION ACTUELLE | PROBLÈME | CORRECTION MINIMALE | RISQUE DE RÉGRESSION | TEST | ROLLBACK |
|---|---|---|---|---|---|---|---|---|
| A1 | `server.py:141` (`require_auth`), `:12001` (`_v263`), `:12080` (`_v319`), 26 fonctions lisant directement `X-User-Email` | 42 routes `require_auth`/`_v263` + 19 en-tête direct (ex. `/platform-settings`, `/concept`, `/admin/reconcile-*`, `/admin/fix-*`, `/admin/faqs*`, `/boosttribe/access`, `/boosttribe/live-status`, `/payment-links` PUT, `/send-bulk-email`, `/check-expirations`, `/v199` factures, `/admin/generate-social-proof`…) | JWT si présent, **sinon en-tête accepté** | l'adresse du super-admin est publique → `X-User-Email: <super-admin>` suffit | **un seul point** : intergiciel qui retire l'en-tête `X-User-Email` quand il désigne le super-admin **sans** JWT coach signé du même e-mail (les autres coachs : inchangés, lot P0-4) | owner sans JWT valide (session expirée, repli V305) → traité comme anonyme → reconnexion | 403 sans jeton, 200 avec jeton, aucun privilège avec l'e-mail seul ; suites existantes | drapeau `P0A_REPLI_ENTETE_SUPERADMIN=true` (≤ 30 s) ou `git revert` |
| A2 | `server.py:10644` | `POST /admin/create-code` | `body.admin_email` ∈ super-admins | n'importe qui crée des codes gratuits (+ e-mail) | `super_admin_signe(request)` | aucun appelant front | 403 sans jeton / passage avec jeton | revert |
| A3 | `server.py:41227`, `:41266` | `POST /admin/delete-history`, `POST /admin/change-identity` | `body.email == COACH_EMAIL` | suppression d'historique / changement d'identité par n'importe qui | `super_admin_signe(request)` | ChatWidget (mode coach, qui exige déjà un JWT) | idem | revert |
| A4 | `coach_routes.py:478` | `GET /auth/role` | en-tête seul | « super_admin » renvoyé sur simple en-tête | couvert par A1 (l'en-tête non prouvé disparaît) | dashboard ouvert sans JWT → déconnexion propre (comportement déjà prévu) | rôle avec/sans jeton | idem A1 |
| A5 | `auth_routes.py:337` | `POST /auth/register` | déjà protégé (409 sur adresse réservée, statut admin par JWT) | — | aucune | — | — | — |

## Lot P0-B — Routes publiques dangereuses (préparé, NON modifié)

| RISQUE | FICHIER | ROUTE | PROTECTION | PROBLÈME | CORRECTION MINIMALE | RÉGRESSION | TEST | ROLLBACK |
|---|---|---|---|---|---|---|---|---|
| B1 | `server.py:42181` | `POST /custom-emojis/upload` | aucune | écriture de fichier, nom non filtré (`../`) | JWT coach strict + nom = slug `[a-z0-9_-]` + extension ∈ {png,jpg,webp,gif} + taille max, ou retrait (aucun appelant front) | nulle | 401 / traversée refusée | revert |
| B2 | `server.py:23206` | `PUT /config` | aucune | réglages du site par n'importe qui | super-admin signé | à vérifier (appelant ancien) | 403/200 | revert |
| B3 | `server.py:23413` | `PUT /coach-subscription` | aucune (TODO) | — | super-admin signé | idem | idem | revert |
| B4 | `server.py:23521` | `PUT /emailjs-config` | aucune | — | super-admin signé | idem | idem | revert |
| B5 | `server.py:26074` | `POST /ai-test` | aucune | coût OpenAI | super-admin signé | nulle | idem | revert |
| B6 | `server.py:44432` | `DELETE /chat/emojis/{id}` | aucune | suppression | coach signé + propriété | à vérifier | idem | revert |
| B7 | `server.py` | `POST /v290-…`, `/v299-…`, `/v305-…` (migrations publiques) | aucune | réécritures en base | super-admin signé (ou retrait) | nulle | idem | revert |
| B8 | `server.py:583` | `GET /debug/network` | aucune | topologie Mongo | super-admin signé | nulle | idem | revert |
| B9 | `server.py:2391-2520`, `:3062-3295`, `:21427/21458` | CRUD `/courses`, `/offers`, `/coach/update-branding|seo` | en-tête | propriété non vérifiée | JWT coach + propriété | dashboard Gestion (JWT déjà envoyé) | parcours Gestion | revert |

## Lot P0-C — Paiements (préparé, NON modifié)

| RISQUE | FICHIER | ROUTE | PROTECTION | PROBLÈME | CORRECTION MINIMALE | RÉGRESSION | TEST | ROLLBACK |
|---|---|---|---|---|---|---|---|---|
| C1 | `server.py:7864` | `PUT /payment-links` | en-tête (super-admin couvert par P0-A ; coach non) | détournement des liens TWINT/Stripe/PayPal | JWT coach strict + propriété | écran paiements (JWT) | 403/200 | revert |
| C2 | `payment_config_routes.py:137` | `PUT /payment-config` | en-tête | remplacement des clés d'un partenaire | JWT coach strict | idem | idem | revert |
| C3 | `payment_config_routes.py:250` | `GET /payment-config/raw/{email}` | aucune | clés en clair (vides au 19/10) | suppression de la route (lecture interne directe) | aucun appelant HTTP | 404/405 | revert |
| C4 | `server.py:9378`, `stripe_routes.py:362` | webhooks Stripe | signature **seulement si** le secret est posé | événements forgeables si secret absent | fail-closed (refus sans secret) — **après** vérification des variables Coolify | webhook refusé si secret manquant | événement de test Stripe signé | revert |
| C5 | `server.py:9466`, `stripe_routes.py` | branche `credit_purchase` | aucune idempotence | double crédit au rejeu | marqueur unique `stripe_event_id` | nulle | rejeu = 1 effet | revert |
| C6 | `payment_config_routes.py:263` | `POST /payment-config/test/{method}` | en-tête | test de clés d'autrui | JWT coach strict | idem | idem | revert |

## Lot P0-D — Données membres (préparé, NON modifié)

| RISQUE | FICHIER | ROUTE | PROTECTION | PROBLÈME | CORRECTION MINIMALE | RÉGRESSION | TEST | ROLLBACK |
|---|---|---|---|---|---|---|---|---|
| D1 | `server.py:15808` | `GET /subscriber/{code}` | aucune | e-mail, nom, séances, présences | réponse minimale sans session d'espace ; complète avec session | écrans qui l'utilisent (à identifier) | parcours espace / QR | revert |
| D2 | `server.py:12968-13723` | `/progress/*` | le code suffit | données de santé | session d'espace exigée | cockpit membre | parcours progression | revert |
| D3 | `promo_routes.py:1151` | `POST /discount-codes/validate` | aucune | document complet du code | vue minimale | formulaire de réservation | réservation avec code | revert |
| D4 | `server.py:18389/18423` | `/space/{code}/member/{slug}/block`, `/join` | le code suffit | blocage/ajout par un tiers | session d'espace du payeur | espace groupe | idem | revert |
| D5 | global | `/auth/login`, OTP, routes par code | limites partielles | force brute | limite de débit persistante (Mongo + TTL) | faux positifs | 429 après N essais | drapeau |

## Lot P0-E — BoostTribe / Live (préparé, NON modifié)

| RISQUE | FICHIER | ROUTE | PROTECTION | PROBLÈME | CORRECTION MINIMALE | RÉGRESSION | TEST | ROLLBACK |
|---|---|---|---|---|---|---|---|---|
| E1 | `AF server.py:14735` | `/boosttribe/access` | `_v263` (repli en-tête) | Live gratuit + reprise de session hôte | **couvert par P0-A** (super-admin prouvé) | owner sans JWT → traité comme abonné | 200 avec jeton / pas d'accès admin sans | drapeau P0-A |
| E2 | BT `main.py:1266` | `/livekit/token` (viewer) | aucune vérification d'accès | sessions payantes regardables sans billet | contrôle billet / crédit côté serveur pour `mode=paid|open` | spectateurs légitimes refusés si bug | contrat Live | revert |
| E3 | BT SQL `profiles` | RLS `profiles_update` | **à vérifier en base** | crédits / illimité / rôle falsifiables | policy limitée aux colonnes non sensibles | profil (nom, photo) | contrat Live + test RLS | SQL inverse |
| E4 | BT SQL billetterie | RPC `wallet_add` | **à vérifier en base** | solde forgeable puis virement | `REVOKE EXECUTE` anon/authenticated | nulle | appel refusé | SQL inverse |
| E5 | BT `main.py:3309`, `:3093` | `claim-host`, `configure` | premier arrivé | appropriation d'une session | hôte = créateur prouvé | création de session | contrat Live | revert |
| E6 | BT `main.py:665` | `/session/record/upload` | JWT + hôte | pas de plafond ni contrôle du débit | plafond + débit vérifié | enregistrement | pytest | revert |
| E7 | BT `main.py:5031` | `/api/embed/verify` | JWT HS256 partagé | pas d'anti-rejeu `jti` | `jti` à usage unique | ré-ouverture d'iframe | contrat Live | revert |

### Clé LiveKit Cloud exposée
| Question | Réponse | Preuve |
|---|---|---|
| CLÉ UTILISÉE EN PRODUCTION | **NON** | l'API Live de production renvoie `url = wss://livekit.afroboost.com` (SFU auto-hébergé) ; les bundles ne contiennent aucune URL `*.livekit.cloud` (seule la fonction de détection de la librairie) |
| ANCIENNE CLÉ EXPOSÉE | **OUI** | `infra/livekit/README.md` (section « Rollback LiveKit Cloud ») du dépôt **public** `afroboost/Boosttribe-v8`, commits du 29/06 et du 03/08 ; le projet Cloud correspondant répond encore (HTTP 200) |
| ACTION MANUELLE REQUISE | **OUI** | révocation dans la console LiveKit Cloud (voir étapes dans le rapport) |

# IMPLEMENTATION PLAN — Afroboost (plateforme complète)

> **PLAN UNIQUEMENT — aucune implémentation n'est lancée.** Établi le 19/10/2026 après audit du code et de la production
> (lecture seule). Chaque lot attend un GO explicite de Bassi. Règles permanentes (CLAUDE.md) : tests de non-régression
> après chaque livraison, « écrit ≠ livré » (Coolify Finished + preuve production), jamais durcir une authentification
> sans prouver « 200 avec jeton / 403 sans » sur la même route, aucune donnée client modifiée sans sauvegarde, contrat
> Live (`yarn test:live-contract`) avant/après toute modification du Live.

## 1. Ce qui est stable et doit être préservé
Réservations et règle unique des séances (consommer/restituer), annulation transactionnelle, espace membre (OTP, sessions),
codes et abonnements (résolveur « abonnement actuel »), checkout Stripe à prix serveur + webhook vitrine, invitations /
Pass Duo / chaîne / ambassadeurs, événements (paliers, capacité, avantages membres), prospection (fil V619, médias V620,
générateur V621), point d'envoi e-mail unique Resend + quota + STOP, analytics + clôture mensuelle, Live (moteur
BoostTribe en iframe, débit d'une séance idempotent).

## 2. Dette technique et incohérences relevées
- Sécurité : repli `X-User-Email` (42 routes), routes sans authentification (dont une écriture de fichier), routes de paiement sur en-tête, webhooks Stripe non signés si secret absent, données personnelles publiques, BoostTribe (secret exposé dans un dépôt public, RLS à vérifier, paywall vidéo non appliqué).
- Données : collections centrales sans index ni unicité ; deux modèles de contact et de droits ; collections de tentatives sans purge.
- Opérations : crons hérités de Vercel inactifs ; pas de CI ; pas de staging ; sauvegardes non documentées ; VPS unique saturé en mémoire (builds tués).
- Front : fichiers géants, 158 `alert()`, design system double, code mort (~20 k lignes), emojis, `#8B5CF6`/classes purple en dur.
- Produit : drapeaux dormants à trancher ; Live sans crédits/droits par utilisateur ; règle ES5 du ChatWidget non respectée dans les faits.

## 3. Lots

Légende complexité : S (≤ ½ jour) · M (1-2 jours) · L (3-5 jours) · XL (> 1 semaine, à redécouper).

---

## PRIORITÉ 0 — Sécurité, données, paiements

### LOT P0-0 — Préparation (sauvegarde, état réel, outillage)
- **OBJECTIF** : connaître l'état réel avant de toucher quoi que ce soit.
- **POURQUOI** : plusieurs risques dépendent de valeurs invisibles dans le code (drapeaux en base, variables Coolify, RLS Supabase).
- **MODULES** : transverse.
- **FRONTEND** : — · **BACKEND** : — · **DB** : lecture seule (export `feature_flags`, `platform_settings`).
- **MIGRATION** : aucune. **SERVICES EXTERNES** : Coolify (lecture des noms de variables), Atlas (snapshots), Supabase (lecture des policies).
- **TESTS** : —
- **RISQUE** : FAIBLE · **ROLLBACK** : sans objet · **DÉPENDANCES** : accès Coolify/Atlas de Bassi ; un `ADMIN_JWT` frais pour `tests/nonregression.py`.
- **COMPLEXITÉ** : S
- **GO/NO-GO** : liste écrite de l'état réel (drapeaux, présence de `STRIPE_WEBHOOK_SECRET*`, `CRON_SECRET`, snapshots Atlas actifs, persistance de `MEDIA_DIR`, policies `profiles`/`wallet_add` Supabase) + sauvegarde datée.

### LOT P0-1 — Secret LiveKit Cloud exposé
- **OBJECTIF** : neutraliser les identifiants LiveKit Cloud publiés dans le dépôt public BoostTribe (`infra/livekit/README.md`).
- **POURQUOI** : utilisables par n'importe qui depuis le 29/06/2026 (facturation, abus).
- **MODULES** : Live. **FRONTEND/BACKEND** : — · **DB** : — · **MIGRATION** : —
- **SERVICES EXTERNES** : console LiveKit Cloud (révocation de la clé **par Bassi**), GitHub (retrait du fichier ; purge de l'historique optionnelle).
- **TESTS** : Live en production intact (le SFU auto-hébergé n'utilise pas ces identifiants) ; contrat Live `--prod`.
- **RISQUE** : FAIBLE · **ROLLBACK** : aucun nécessaire (le repli Cloud documenté devient inutilisable — accepté).
- **COMPLEXITÉ** : S · **GO/NO-GO** : clé révoquée côté LiveKit Cloud, fichier nettoyé, Live 200.

### LOT P0-2 — Fermer les routes ouvertes
- **OBJECTIF** : authentification signée sur `POST /custom-emojis/upload` (ou suppression : inutilisée), `POST /admin/create-code` (super-admin signé au lieu de `body.admin_email`), `PUT /config`, `PUT /coach-subscription`, `PUT /emailjs-config`, `POST /ai-test`, `DELETE /chat/emojis/{id}`, `POST /admin/delete-history`, `POST /admin/change-identity`, routes de migration publiques (`/v290-…`, `/v299-…`, `/v305-…`), `GET /debug/network`.
- **POURQUOI** : écriture de fichier arbitraire, création de codes gratuits, modifications de configuration par n'importe qui.
- **MODULES** : plateforme, codes, chat. **FRONTEND** : vérifier les appelants (la plupart n'en ont aucun). **BACKEND** : `super_admin_signe` / `_v309_require_coach_or_admin`.
- **DB** : — · **MIGRATION** : — · **SERVICES** : —
- **TESTS** : pour chaque route : 403 sans jeton, 200 avec jeton super-admin réel (règle V310c) ; ajout aux parcours 21-24 de `nonregression.py`.
- **RISQUE** : FAIBLE (routes sans usage légitime ou usage super-admin seul) · **ROLLBACK** : `git revert`.
- **COMPLEXITÉ** : S-M · **GO/NO-GO** : tableau 403/200 collé, aucune régression dashboard.

### LOT P0-3 — Paiements : liens, configuration partenaire, webhooks
- **OBJECTIF** : `PUT /payment-links`, `PUT /payment-config` en JWT strict + propriété ; suppression de `GET /payment-config/raw/{email}` (lecture interne directe en base) ; webhooks `/api/webhook/stripe` et `/api/stripe/webhook` **fail-closed** sans secret ; idempotence de `credit_purchase`.
- **POURQUOI** : détournement possible des liens TWINT/Stripe/PayPal ; événements Stripe forgeables si le secret manque ; double crédit au rejeu.
- **MODULES** : paiements, partenaires. **FRONTEND** : dashboard paiements (le JWT est déjà envoyé). **BACKEND** : 4 routes + webhook.
- **DB** : — · **MIGRATION** : — · **SERVICES** : Stripe (vérifier que les secrets de webhook sont posés AVANT la bascule fail-closed).
- **TESTS** : checkout réel en mode test sur la pile locale, rejeu de webhook (1 seul effet), 403/200.
- **RISQUE** : MOYEN (un secret manquant = webhooks refusés → accès non délivrés) · **ROLLBACK** : revert ; garder le webhook vitrine (déjà strict) comme filet.
- **DÉPENDANCES** : P0-0. **COMPLEXITÉ** : M
- **GO/NO-GO** : secrets présents dans Coolify, test de webhook signé OK en production (événement de test Stripe), aucun paiement réel touché.

### LOT P0-4 — Fin du repli `X-User-Email`
- **OBJECTIF** : `require_auth()` et `_v263_authenticated_coach()` respectent `REQUIRE_COACH_JWT` (déjà réputé ON), puis passent en JWT strict ; `/boosttribe/access` et `/boosttribe/live-status` décident le super-admin sur JWT signé uniquement ; CRUD `/courses`, `/offers`, `/concept`, `/platform-settings`, `/admin/*` sur JWT + propriété.
- **POURQUOI** : l'adresse du super-admin est publique : un en-tête suffit aujourd'hui à agir à sa place sur 42 routes (dont le Live gratuit avec reprise de la session hôte).
- **MODULES** : tous ceux du dashboard, Live. **FRONTEND** : vérifier que chaque écran envoie le JWT (l'intercepteur le fait déjà) ; ChatWidget coach (JWT exigé). **BACKEND** : 2 fonctions + routes listées.
- **DB** : — · **MIGRATION** : — · **SERVICES** : —
- **TESTS** : **règle V310c** sur chaque route touchée (200 avec jeton réel du propriétaire, 403 sans) ; parcours dashboard complet (Playwright local) ; journal `[V265] repli X-User-Email` vide pendant 7 jours **avant** la bascule stricte.
- **RISQUE** : ÉLEVÉ (un écran qui n'envoie pas de JWT = dashboard vide, incident V310) · **ROLLBACK** : drapeau (repli rétabli en une seconde) + revert.
- **DÉPENDANCES** : P0-0. **COMPLEXITÉ** : L (à découper par famille de routes)
- **GO/NO-GO** : 0 occurrence du repli dans les logs sur 7 jours ; tableau 200/403 complet ; aucune session coach cassée.

### LOT P0-5 — Données personnelles exposées et limites de débit
- **OBJECTIF** : `GET /subscriber/{code}` réduit ou derrière session d'espace ; `/progress/*` derrière session d'espace ; `/discount-codes/validate` renvoie une vue minimale ; limites de débit persistantes sur `/auth/login`, OTP, recherche par code, `/translate`, `/chat` (coût IA) ; QR générés localement (plus d'appel à api.qrserver.com avec le code).
- **POURQUOI** : code de 6 caractères hexadécimaux devinable, données de santé, coûts OpenAI publics.
- **MODULES** : membres, chat, IA. **FRONTEND** : espace membre, réservation (vérifier les champs utilisés). **BACKEND** : 6-8 routes.
- **DB** : collection de compteurs (TTL) · **MIGRATION** : aucune donnée. **SERVICES** : OpenAI (plafond).
- **TESTS** : parcours membre complet ; essais de force brute limités (429).
- **RISQUE** : MOYEN (casser l'affichage d'un ancien écran) · **ROLLBACK** : revert.
- **COMPLEXITÉ** : M · **GO/NO-GO** : parcours réservation/espace/essai verts en local et en production.

### LOT P0-6 — Sécurité BoostTribe (Live) — dépôt BoostTribe
- **OBJECTIF** : selon P0-0 : restreindre la RLS `profiles` (colonnes sensibles non modifiables par l'utilisateur), `REVOKE` sur `wallet_add`, vérification crédit/billet avant `/livekit/token` des sessions payantes, anti-rejeu `jti` sur `/api/embed/verify`, plafond et débit vérifié sur `/session/record/upload`, contrôle serveur de `claim-host`.
- **POURQUOI** : soldes, accès illimité, virements et coûts OpenAI potentiellement falsifiables.
- **MODULES** : Live. **FRONTEND** : `AuthContext` (ne plus écrire `role`), session. **BACKEND** : `main.py`. **DB** : policies Supabase.
- **MIGRATION** : SQL de policies (réversible). **SERVICES** : Supabase, LiveKit.
- **TESTS** : `yarn test:live-contract` avant/après ; pytest ; Live réel à deux navigateurs (avec GO).
- **RISQUE** : ÉLEVÉ (le Live est utilisé en cours réels) · **ROLLBACK** : SQL inverse prêt avant application ; revert.
- **DÉPENDANCES** : P0-0, P0-4 (pour `/boosttribe/access`). **COMPLEXITÉ** : L
- **GO/NO-GO** : contrat Live vert en local et `--prod` ; aucun Live programmé pendant la bascule.

---

## PRIORITÉ 1 — Fiabilité des fonctions principales

### LOT P1-1 — Index et unicité des collections centrales
- **OBJECTIF** : index de performance + index uniques (voir BACKEND_SCHEMA §B.1) sur `discount_codes`, `subscriptions` (actif unique par code), `reservations`, `payment_transactions`, `seance_mouvements`, contacts.
- **POURQUOI** : les doublons de codes/abonnements ont déjà coûté des corrections manuelles ; les listes ralentissent avec le volume.
- **BACKEND** : création d'index au démarrage (idempotente). **DB** : audit des doublons **à blanc**, puis correction avec GO (sauvegarde). **MIGRATION** : seulement les doublons listés et validés.
- **TESTS** : rapport avant/après ; temps de réponse des listes.
- **RISQUE** : MOYEN (un index unique échoue s'il reste un doublon → l'app démarre quand même si la création est tolérante) · **ROLLBACK** : `dropIndex`.
- **COMPLEXITÉ** : M · **GO/NO-GO** : 0 doublon restant, index créés, démarrage OK.

### LOT P1-2 — Tâches planifiées réellement actives
- **OBJECTIF** : décider pour chaque cron hérité (`check-subscription-renewal`, `post-course-feedback`, `rappel-renouvellement`, `check-expirations`) : boucle interne (comme RV3-B) ou suppression ; protéger `/cron/reservation-reminders`.
- **POURQUOI** : des tâches attendues ne tournent pas depuis la migration Vercel → Coolify.
- **BACKEND** : 1 boucle générique sous drapeau + `CRON_SECRET`. **DB** : — · **TESTS** : mode « à blanc » qui liste ce qui serait envoyé.
- **RISQUE** : MOYEN (envois réels) · **ROLLBACK** : drapeau OFF. **COMPLEXITÉ** : M
- **GO/NO-GO** : liste à blanc validée par Bassi avant tout envoi réel.

### LOT P1-3 — CI légère et environnement de test
- **OBJECTIF** : GitHub Actions sur chaque push : bancs Python rapides (sans réseau), Jest, build front ; documenter la pile locale `afroboost_pw_test` comme « staging » ; `.env.local` ne pointe plus vers la production par défaut.
- **POURQUOI** : les régressions sont découvertes en production ; développer contre la base de production est risqué.
- **RISQUE** : FAIBLE · **ROLLBACK** : désactiver le workflow. **COMPLEXITÉ** : M
- **GO/NO-GO** : CI verte sur `main` ; un push rouge est visible avant le déploiement Coolify.

### LOT P1-4 — Sauvegardes, supervision, capacité
- **OBJECTIF** : snapshots Atlas vérifiés + test de restauration ; sauvegarde du volume `MEDIA_DIR` ; alerte sur `/healthz` (redémarrages via `boot_id`) ; suivi mémoire du VPS ; une seule construction à la fois.
- **POURQUOI** : VPS unique partagé, builds tués, aucun signal d'alerte.
- **SERVICES** : Atlas, Coolify, un service de surveillance (au choix de Bassi). **RISQUE** : FAIBLE · **COMPLEXITÉ** : S-M
- **GO/NO-GO** : restauration testée sur une base séparée ; alerte reçue lors d'un test.

### LOT P1-5 — Inventaire et nettoyage des drapeaux
- **OBJECTIF** : tableau état réel / intention pour les ~35 drapeaux ; décision de Bassi : activer, garder dormant, supprimer le code.
- **RISQUE** : FAIBLE (documentation) puis variable par drapeau · **COMPLEXITÉ** : S
- **GO/NO-GO** : tableau validé.

### LOT P1-6 — Journal d'audit des actions admin
- **OBJECTIF** : collection `audit_logs` append-only écrite par les routes admin (codes, abonnements, offres, réglages, drapeaux, crédits) ; lecture super-admin.
- **POURQUOI** : aujourd'hui personne ne peut savoir qui a modifié quoi.
- **DB** : nouvelle collection (aucune migration). **RISQUE** : FAIBLE · **ROLLBACK** : revert (la collection reste). **COMPLEXITÉ** : M
- **GO/NO-GO** : chaque action admin testée laisse une ligne avec l'auteur JWT.

---

## PRIORITÉ 2 — UX et simplification

### LOT P2-1 — Retours intégrés au lieu des `alert()`
Composants partagés `Bouton`, `Modale`, `Retour` (bandeau + toast), `Onglets` en réutilisant les styles existants ; remplacement des `alert()` du dashboard (90) puis du chat et de la vitrine. RISQUE FAIBLE · COMPLEXITÉ L (par écran) · GO : aucun `alert()` dans l'écran traité, Jest + parcours verts.

### LOT P2-2 — Couleurs du coach partout
`#8B5CF6` → `var(--secondary-color, #8B5CF6)`, classes Tailwind purple/pink/violet → variables, `rgba(217,28,210,…)` → `rgba(var(--primary-rgb), …)` ; habillage Live branché sur les mêmes variables. RISQUE FAIBLE · COMPLEXITÉ M · GO : recherche d'hex en dur = 0 hors repli `var()` sur les fichiers touchés.

### LOT P2-3 — Code mort
Supprimer les 2 sauvegardes de CoachDashboard, CoachVitrine/VitrineCheckout, `components/index.js` + `ui/index.jsx`, 45 composants shadcn inutilisés, `EmojiPicker.js`, `admin_routes.py`, `scheduler_engine.py`, routes de migration, webhook Twilio. RISQUE FAIBLE (vérifier les imports) · COMPLEXITÉ S · GO : build + Jest verts, bundle plus léger.

### LOT P2-4 — Navigation et états
Bouton retour dans les modales de réservation (entrée d'historique), écran hors ligne léger, `BanniereSession` monté. RISQUE MOYEN (parcours de paiement) · COMPLEXITÉ M · GO : parcours visiteur/membre verts sur 390 px et desktop.

### LOT P2-5 — Espace membre : historique
Historique unifié réservations / présences / paiements / séances (lecture de `seance_mouvements`, `reservations`, `payment_transactions`). RISQUE FAIBLE · COMPLEXITÉ M.

---

## PRIORITÉ 3 — Nouvelles fonctionnalités

### LOT P3-1 — Live : crédits et droits par utilisateur (architecture D)
Découpage (chaque sous-lot = un GO) :

| Sous-lot | OBJECTIF | FRONTEND | BACKEND | DB | TESTS | RISQUE | ROLLBACK | COMPLEXITÉ | GO/NO-GO |
|---|---|---|---|---|---|---|---|---|---|
| **3-1a** Référentiel | `features` + `user_entitlements` en **lecture seule**, défauts = comportement actuel | — | `/me/entitlements` (JWT) | 2 collections neuves | 403 sans jeton | FAIBLE | revert | M | aucune différence visible |
| **3-1b** Journal de crédits | `credit_wallets` + `credit_transactions` immuables, écran admin « Créditer / Retirer » avec motif, historique | dashboard super-admin (fiche utilisateur) | routes super-admin signé + transaction Mongo + `audit_logs` | 2 collections | idempotence, solde = somme, aucun UPDATE/DELETE | MOYEN | revert (journal conservé) | L | 3 opérations réelles de test sur un compte de test, soldes justes |
| **3-1c** Écran droits | cases à cocher par fonctionnalité + limites | fiche utilisateur | PUT entitlements (super-admin signé, audit) | — | 200/403 | FAIBLE | revert | M | GO Bassi sur l'écran |
| **3-1d** Autorisation serveur à serveur | BoostTribe demande à Afroboost « peut-il faire X ? coût ? » avant start/record/share/IA ; Afroboost débite | — | `/api/live/authorize` (signé, anti-rejeu) + appels côté `main.py` BT | `usage_events` | contrat Live + pytest des deux côtés | **ÉLEVÉ** | drapeau : retour au débit « 1 séance » actuel | L | Live réel test (2 navigateurs, compte de test) |
| **3-1e** UI utilisateur | solde, droits visibles, coût affiché avant action, « crédits insuffisants » | espace membre + overlay Live | lecture | — | Playwright 390/desktop | FAIBLE | revert | M | parcours vert |
| **3-1f** QA / monitoring | tableau d'usage (minutes, débits), alertes de coût OpenAI | super-admin | agrégats | — | — | FAIBLE | — | M | chiffres cohérents avec le journal |
**Dépendances** : P0-4, P0-6, P1-6 ; décisions de Bassi (prix, unité de crédit, solde commun avec boosttribe.pro). **Montants : à décider par Bassi — aucun n'est fixé par ce plan.**

### LOT P3-2 — Replay vidéo serveur (si décidé)
Egress fichier → stockage → lecteur + miniature + rétention obligatoire + droit `replay`. RISQUE MOYEN (disque, coût CPU) · COMPLEXITÉ L.

### LOT P3-3 — Multi-coach partenaires (si décidé)
Cloisonnement `coach_id` complet, dashboard partenaire, Stripe Connect, suppression des hypothèses « mono-coach ». RISQUE ÉLEVÉ · COMPLEXITÉ XL (à redécouper).

### LOT P3-4 — Traduction de l'espace membre et du dashboard (si décidé)
Extension de `t()` au-delà de la vitrine. RISQUE FAIBLE · COMPLEXITÉ L.

### LOT P3-5 — Activation des fonctions dormantes (au cas par cas)
Relances essai, auto-présence, tarif membre, bot WhatsApp, PawaPay : chacune avec mode à blanc, liste validée, puis activation. RISQUE variable · COMPLEXITÉ S par fonction.

## 4. Ordre recommandé
P0-0 → P0-1 → P0-2 → P0-3 → P0-5 → P0-4 (par familles) → P0-6 → P1-4 → P1-3 → P1-1 → P1-6 → P1-2 → P1-5 → P2-* → P3-1 (a→f) → autres P3 selon décisions.
Les lots P0-1 et P0-2 sont rapides, à faible risque et suppriment les failles les plus graves : ils sont les premiers candidats au GO.

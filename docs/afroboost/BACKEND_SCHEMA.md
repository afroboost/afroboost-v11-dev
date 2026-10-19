# BACKEND SCHEMA — Afroboost

> Partie A = **schéma RÉEL** relevé en lecture seule le 19/10/2026 (production, base `promo-credits-lab`, 109 collections ;
> liste exhaustive des champs et index dans [`annexes/SCHEMA_MONGO_REEL.md`](annexes/SCHEMA_MONGO_REEL.md)) + Supabase du
> module Live (d'après les scripts SQL du dépôt). Partie B = **schéma CIBLE recommandé**, purement documentaire :
> **rien n'a été créé**.
>
> Conventions réelles : identifiant applicatif `id` (UUID chaîne) en plus du `_id` Mongo ; dates en **chaînes ISO**
> (sauf quelques `Date` BSON pour les TTL) ; propriété par **`coach_id` = e-mail du coach** ; pas de validation de schéma
> Mongo (validation applicative). « Autorisation » = garde réelle des routes principales.

---

# A. SCHÉMA ACTUEL RÉEL

## A.1 Personnes et accès
| Collection (docs) | Rôle | Champs clés (types) | Index | Relations | Propriété / autorisation | Rétention |
|---|---|---|---|---|---|---|
| `users` (140) | contacts CRM « historiques » | id, name, email, whatsapp/phone, birthday, coach_id, accessCode, role, source, language, photo_url (str) | **aucun** | → `subscriptions` par e-mail | coach (JWT + `_mt2_user_du_coach`) | illimitée |
| `chat_participants` (1 249) | contacts réels (chat, leads, abonnés) | id, name, email, whatsapp, coach_id, source, link_token, isSubscriber, subscriptionCode, contact_type | **aucun** | → `chat_sessions`, `subscriptions` | coach | illimitée |
| `coaches` (1) | profil coach/partenaire (branding, SEO, crédits) | email, accent_color, logo_url, meta_*, credits… | aucun | `coach_id` = email | super-admin / coach (**routes branding sur en-tête**) | — |
| `coach_auth` / `users_auth` (11) | identifiants de connexion | email, hash bcrypt, rôle | — | coaches | `/auth/login` | — |
| `coach_profiles`, `coach_packs` (3), `coach_sessions` | profils, packs partenaires, sessions | — | aucun | — | super-admin | — |
| `subscriber_sessions` (64) | sessions d'espace membre | jti, code, email, coach_id, slug, expires_at, revoked | **aucun** | → code | membre (B3) | expiration logique 30 j |
| `subscriber_otp` (83) | codes OTP | code, email, otp_empreinte (haché), expires_at, essais, used | aucun | — | membre | 10 min (logique) |
| `espace_liens_acces` (6) | liens magiques d'espace | code, email, expires_at (24 h), ouvertures | aucun | — | membre | logique |
| `subscriber_infos` (9) | infos complémentaires du membre | code, … | aucun | — | jeton MT-6 | — |
| `password_resets`, `recovery_attempts` (21), `smart_entry_attempts` (1 720) | sécurité / limites de débit | — | aucun | — | — | **sans purge** |
| `google_users`, `google_tokens` | OAuth Google | jetons chiffrés | — | coach | coach | — |
| `app_secrets` (1) | secret JWT de repli | id, secret | aucun | — | serveur | — |

## A.2 Offres, droits, réservations
| Collection (docs) | Rôle | Champs clés | Index | Relations | Autorisation | Notes |
|---|---|---|---|---|---|---|
| `offers` (17) | catalogue (unité, pack, abonnement, saison, produit, événement) | id, name, price (num), offer_type, billing_mode, season, visible, stock, pack_sessions, linked_course_ids, coach_id (souvent **nul**), paliers (price_early_bird/standard/last_minute), link_only, creates_membership, duree_mois… | **aucun** | → courses, discount_codes, subscriptions | lecture publique filtrée ; **écriture sur en-tête** | prix relu serveur au checkout |
| `courses` (24) | cours récurrents et occurrences | id, name, weekday, time, location, coach_id, visible, archived, saison, dates_annulees, reminder_rules, duo_*, duration_minutes | **aucun** | → reservations, offers | lecture publique ; **écriture sur en-tête sans propriété** | — |
| `discount_codes` (67) | **codes d'accès** AFR-xxxx (droits historiques) | id, code, type, value, maxUses, used, active, expiresAt, assignedEmail, coach_id, montant_encaisse, origine_paiement, canonical… | **aucun** | ↔ subscriptions (code) | JWT strict | `discount_codes` fait foi pour les droits (LOT A) |
| `subscriptions` (100) | **abonnements / forfaits** | id, code, email, name, offer_id, total/used/**remaining_sessions** (int), expires_at, status, auto_renew, stripe_*, montant_encaisse, suivi_paiement, deleted_* | **aucun** | → offers, discount_codes | JWT / session d'espace | « abonnement actuel » = résolveur unique |
| `memberships` (6) | adhésions association | id, email, coach_id, date_debut, date_fin, subscription_id, offer_id | aucun | → subscriptions | JWT strict | — |
| `code_members` (20) | membres d'un code partagé | code, slug, name, email, whatsapp | aucun | → discount_codes | **le code suffit** (block/join) | — |
| `reservations` (191) | réservations et présences | id, reservationCode, userEmail, courseId, offerId, datetime, selectedDates, quantity, totalPrice, discountCode, subscriptionId, validated/validatedAt, tarif_*, source, attribution, headphone_*, reminder_sent… | **aucun** | → courses, offers, subscriptions | création publique ; lecture JWT + propriété (MT-5) | — |
| `seance_mouvements` (57) | **journal des séances** (consommer / restituer) | type, reservation_id, code, fiche_id, quantite, source, statut, at, used_apres | aucun | → reservations, codes | serveur | règle unique (clé = réservation) |
| `reservation_cancellations` (5), `session_adjustments` (7), `qr_validations` (3) | annulations, ajustements, scans | — | aucun | — | coach | — |
| `free_trial_claims` (61) | essais accordés | created_at, actif (+ empreintes) | aucun | — | serveur | — |
| `evenement_places` (2) | capacité réelle d'événement | offer_id, statut, reservation_id | aucun | → offers | serveur | — |
| `progress_entries` (0), `coaching_notes` (0) | progression (santé) | — | aucun | → code | **le code suffit** | — |

## A.3 Invitation, parrainage, événements
| Collection | Rôle | Index | Autorisation |
|---|---|---|---|
| `referral_campaigns` (12) | invitations du coach (essai, Pass Duo, événement gratuit/payant), statuts draft/active/hidden/archived, médias | id U, share_token U, (coach_id, status, updated_at) | JWT strict |
| `referral_passes` (30) | Pass Duo / chaîne (parrain, filleul, séance, statut, chaîne) | 8 index dont unicités filleul/séance/rang | jetons + session |
| `referral_invitations` (30), `referral_share_settings`, `invitation_relais` (2), `invitation_events` (59, clé U) | liens personnels, suivi du funnel | partiels | public limité / JWT |
| `ambassadeur_boosts` (0), `referral_commissions` (0), `creators` (1), `payout_requests` (0) | ambassadeurs, créateurs, commissions | `creators` : id/email/share_token U | JWT |

## A.4 Paiements
| Collection | Rôle | Index | Notes |
|---|---|---|---|
| `payment_transactions` (293) | transactions Stripe (montant serveur, tarif figé, statut, réconciliation) | **aucun** | idempotence via `session_id` dans les codes |
| `checkout_transactions` (68) | transactions du checkout vitrine | aucun | historique |
| `payment_links` (15) | liens Stripe/PayPal/TWINT par coach | aucun | **PUT sur en-tête** |
| `partner_payment_config` (2) | clés de paiement partenaire | aucun | **toutes vides au 19/10** ; route `/raw` publique |
| `pawapay_transactions` (0), `invoices` (1), `analytics_monthly_reports` (1) | — | — | — |

## A.5 Prospection
| Collection | Rôle | Index |
|---|---|---|
| `partner_prospects` (435) | fiches prospects (niche, statut, coordonnées publiques) | index au démarrage (coach_id…) |
| `prospection_niches` (8), `prospection_medias` (28), `prospection_liens` | niches, médias, liens | — |
| `prospect_campaigns` (10), `prospect_campaign_actions` (844) | campagnes P3, actions J0→J+14 (textes approuvés, statuts de remise, jetons de réponse) | 8 index dont 4 uniques |
| `prospect_inbound_messages` (69) | réponses reçues (corps, citation, lu, traité, nature) | 5 index dont dédoublonnage U |
| `prospect_reply_drafts` (53), `prospect_reply_sends` (52), `prospect_notes` (104) | brouillons IA (+ analyse, contrôle V621), envois (instantané texte + média), notes | `prospect_reply_sends` : id U |
| `calendar_events` (3) | tâches, RDV (créneaux uniques) | 8 index |
| `trajets_cache` (5), `leads` (170), `partners` (1) | — | `leads.submission_id` U ; `partners` 3 U |

## A.6 Communication
| Collection | Rôle | Index |
|---|---|---|
| `campaigns` (13), `campaign_errors` (94) | campagnes clients | aucun |
| `resend_envois` (490), `resend_evenements` (1 023), `resend_quota` (2) | journal d'envoi e-mail, événements de remise (idempotents), quota | — |
| `subscribers` (43) | registre opt-in / STOP | (channel, value) U |
| `whatsapp_config`, `whatsapp_statuts` (1 322), `bot_whatsapp_etat`, `bot_quick_replies` | WhatsApp | — |
| `chat_sessions` (563), `chat_messages` (2 965), `chat_groups` (14), `private_conversations` (12), `private_messages` (148) | chat | aucun |
| `notifications` (244), `notification_preferences`, `push_subscriptions` (346, endpoint U) | notifications et push | — |
| `reminder_sends` (498) | rappels envoyés | — |
| `ai_config`, `ai_logs` (663) | IA | — |

## A.7 Contenu, médias, plateforme
`concept` (20), `config`, `platform_settings` (3 : maintenance, accès partenaires, saison, prix de service, code staff), `feature_flags` (2 : drapeaux globaux), `publications` (4), `comments` (754), `page_likes`, `social_proofs`, `faqs`, `terms_versions`, `categories`, `contact_categories`, `contact_segments_config`, `uploaded_files` (113 : métadonnées des fichiers disque), `upload_chunks`, `audio_tracks`, `media_links`, `deleted_items` (65 : corbeille avec `payload`), `emailjs_config`.

## A.8 Live (côté Afroboost)
| Collection | Rôle | Champs | Index |
|---|---|---|---|
| `boosttribe_live` (1) | Live en cours (document unique `actuel`) | session_code, host, started_at, ended, owner, surfaces | — |
| `boosttribe_live_journal` (310) | journal append-only des événements Live | event, outcome, session_code, at, by, source, reason | — |
| `boosttribe_usage` (5) | jetons émis / débits (idempotence `jti`) | status, kind, code, email, remaining, debited_at, created_dt | `created_dt` (TTL 7 j) |
| `invites_live` (2) | identités d'invités Live | pseudo, email, whatsapp, appareils | id U, appareils.h U |
| `spordate_bridge_usage` (1 122) | pont Spordateur | — | — |

## A.9 Live (Supabase BoostTribe — d'après les scripts du dépôt ; application réelle à vérifier)
`profiles` (credits, role, comp_access_plan/until, coach_payment_type, stripe_*), `playlists` (= sessions : host_id, cohosts, mode, price_chf, capacity, access_mode, is_private, record_enabled, live_promo_*), `credit_ledger`, `credit_packs`, `pricing_settings`, `credit_codes` (inutilisée), `tickets`, `coach_wallet`, `wallet_ledger`, `payout_requests`, `coach_bank`, `commission_settings`, `coach_subscriptions`, `access_requests`, `session_recordings`, `live_promos`, `social_destinations`, `session_media/likes/comments`, `site_settings`, tables de secrets chiffrés et d'idempotence. Détail : LIVE_AUDIT §3 et §5.

## A.10 Constats sur le schéma actuel
1. **Collections centrales sans aucun index** (`reservations`, `subscriptions`, `discount_codes`, `offers`, `courses`, `users`, `chat_participants`, `payment_transactions`, `notifications`) : ni performance garantie, ni **unicité** (cause historique des doublons de codes/abonnements).
2. Deux notions de « contact » (`users` et `chat_participants`) et deux de « droit » (`discount_codes` et `subscriptions`), réconciliées par des fonctions canoniques.
3. Dates en chaînes : tri correct en ISO UTC mais fragile si les fuseaux sont mélangés (fonction `pf_instant` dédiée).
4. Journaux existants (bons modèles) : `seance_mouvements`, `resend_envois`, `boosttribe_live_journal`, `deleted_items`. **Absent** : journal d'audit des actions admin.
5. Collections sans purge : `smart_entry_attempts`, `recovery_attempts`, `subscriber_otp`, `ai_logs`, `whatsapp_statuts`.
6. Crédits : `coaches.credits` + `credit_transactions` (partenaires) ≠ séances (`subscriptions`) ≠ crédits BoostTribe (`credit_ledger`).

---

# B. SCHÉMA CIBLE RECOMMANDÉ (documentaire — rien n'est créé)

Principe : **ajouter peu, contraindre beaucoup**. On ne réécrit pas le modèle existant ; on ajoute des **index uniques** là
où les doublons ont coûté cher, un **journal d'audit**, et — pour le besoin Live — deux couches séparées **crédits** et
**droits**, détenues par Afroboost.

## B.1 Contraintes à ajouter sur l'existant (après nettoyage des doublons, en mode « à blanc » d'abord)
| Collection | Index recommandé | But |
|---|---|---|
| `discount_codes` | `code` unique ; `(coach_id, assignedEmail)` | un code = une fiche |
| `subscriptions` | `id` unique ; `code` (non unique : historique) + index partiel unique `(code)` où `status="active"` | un seul abonnement actuel par code |
| `reservations` | `id` unique ; `(courseId, datetime)` ; `(userEmail, datetime)` ; `reservationCode` | listes rapides, anti-double réservation |
| `offers`, `courses` | `id` unique ; `coach_id` | propriété |
| `payment_transactions` | `session_id` unique | idempotence webhook |
| `chat_participants`, `users` | `id` unique ; `(coach_id, email)` ; `(coach_id, whatsapp)` | anti-doublon contacts |
| `seance_mouvements` | `(reservation_id, type)` unique | une seule consommation / restitution par réservation |
| `notifications` | `(coach_id, created_at)` | dashboard |
| Collections de tentatives | TTL (ex. 30 j) | hygiène / RGPD |

## B.2 Nouvelles entités (pour crédits + droits, module Live et au-delà)

### `credit_wallets` — solde (cache, jamais écrit à la main)
| Champ | Type | Oblig. | Défaut | Index | Validation |
|---|---|---|---|---|---|
| user_key | str (e-mail normalisé ou id de compte) | ✅ | — | **U** | — |
| balance | int | ✅ | 0 | — | **= somme des transactions** (recalcul serveur) |
| currency_unit | str | ✅ | "credit" | — | — |
| updated_at | ISO | ✅ | now | — | — |
Propriété : l'utilisateur lit son solde ; **seul le serveur écrit**. Rétention : vie du compte.

### `credit_transactions` — journal IMMUABLE (append-only)
| Champ | Type | Oblig. | Défaut | Index | Validation |
|---|---|---|---|---|---|
| transaction_id | uuid | ✅ | — | **U** | — |
| user_key | str | ✅ | — | (user_key, created_at) | — |
| amount | int (±) | ✅ | — | — | ≠ 0 |
| type | enum : manual_credit, manual_debit, purchase, promo, live_usage, feature_usage, refund, expiry, correction | ✅ | — | — | liste fermée |
| reason | str | ✅ si manuel | — | — | 3–200 car. |
| feature | str (clé de `features`) | si usage | null | — | clé existante |
| session_id / ref | str | si usage | null | **(type, ref) U** = idempotence | — |
| balance_after | int | ✅ | — | — | ≥ 0 sauf correction autorisée |
| created_at | ISO | ✅ | now | — | — |
| created_by | str (e-mail admin ou « system ») | ✅ | — | — | — |
| corrects | transaction_id | si correction | null | — | — |
Règles : **jamais d'UPDATE ni de DELETE** ; une erreur se corrige par une transaction inverse (`correction`, `corrects`). Écriture + solde dans **une transaction Mongo** (déjà utilisée par l'annulation B3). Rétention : 10 ans (pièces comptables) ou selon décision.

Exemple :
```
+500  manual_credit  reason="pack test"   created_by=contact.artboost@gmail.com
 -60  live_usage     feature=live_minute  ref=live:ABCD:session-2026-10-16  created_by=system
```

### `features` — catalogue des fonctionnalités (référentiel)
| Champ | Type | Exemple |
|---|---|---|
| key (U) | str | live_video, live_audio, chat, replay, recording, screen_share, ai_transcription, ai_assistant, multistream |
| label, description | str | « Enregistrement » |
| category | enum | live, ia, contenu |
| default_enabled | bool | false |
| active | bool | true |

### `user_entitlements` — droits par utilisateur (séparés des crédits)
| Champ | Type | Oblig. | Index | Notes |
|---|---|---|---|---|
| user_key | str | ✅ | **(user_key, feature) U** | — |
| feature | str | ✅ | — | clé de `features` |
| enabled | bool | ✅ | — | — |
| limits | objet {max_duration_min, max_participants, storage_gb, max_replays, retention_days} | non | — | null = pas de limite propre |
| source | enum : manual, plan, promo | ✅ | — | — |
| valid_until | ISO | non | — | droit temporaire |
| updated_at / updated_by | ISO / str | ✅ | — | — |
Résolution serveur : `droit = entitlement explicite ?? droit du plan ?? features.default_enabled`.

### `feature_costs` — tarification (montants décidés par Bassi)
| Champ | Type | Exemple (structure seulement) |
|---|---|---|
| feature (U avec unit) | str | live_session_start |
| unit | enum : action, minute, gb_month | minute |
| credits | int | **à décider** |
| active_from / active_until | ISO | versionnage (le coût appliqué est figé dans la transaction) |

### `usage_events` — mesure (non monétaire)
user_key, feature, session_id, started_at, ended_at, quantity (minutes, Go), outcome, source (live, ia…). Index (user_key, started_at). Sert l'écran « Utilisation » et les contrôles de limites. Rétention : 13 mois.

### `live_sessions` (côté Afroboost, optionnel si BoostTribe reste moteur)
session_code, host_user_key, started_at, ended_at, participants_max, minutes_total, recording (bool), credits_debited. Alimenté par le journal existant `boosttribe_live_journal`.

### `recordings` / `replays` (seulement si le replay serveur est décidé)
id, session_code, owner, storage_path, size_bytes, duration_s, thumbnail_url, visibility (owner/participants/public), expires_at (**rétention obligatoire**), created_at.

### `audit_logs` — qui a fait quoi (toutes actions admin)
| Champ | Type |
|---|---|
| id (U) | uuid |
| at | ISO |
| actor | e-mail (JWT signé) |
| action | str (ex. credits.add, entitlement.set, offer.update, platform_settings.update, flag.set) |
| target | {collection, id} |
| before / after | objets réduits (sans secret) |
| request_id, ip_hash | str |
Append-only, index (target.id, at) et (actor, at). Rétention 24 mois.

## B.3 Règle d'autorisation unique (cible)
```
client demande start_recording(session)
serveur : JWT signé valide ?               sinon 401
          rôle / propriété de la session ?  sinon 403
          user_entitlements[recording] ?     sinon 403 feature_not_allowed
          limites (durée, stockage) OK ?     sinon 409 limit_reached
          coût = feature_costs[recording]; solde ≥ coût ?  sinon 402 insufficient_credits
          → transaction (débit + usage_event + audit) puis autorisation
```
Le frontend n'affiche que ce que le serveur renvoie (`/me/entitlements`, `/me/credits`) ; il ne décide jamais d'un solde, d'un coût, d'un droit ou d'une gratuité.

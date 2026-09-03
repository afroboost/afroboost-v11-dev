# AFROBOOST — ÉTAT PROJET (mémoire opérationnelle persistante)

> Source de vérité opérationnelle. **Documentation uniquement — aucun code, aucun secret.**
> Ne stocke que `présent = oui/non`, `configuré = oui/non`, des noms de variables, des SHA et des compteurs.
> Pour tout sujet **production**, la **preuve runtime** prime sur toute vue UI / onglet / rapport ancien.

Dernière réconciliation runtime vérifiée : **2026-09-03, 05:47 UTC**.

---

## RÈGLE DE RÉCONCILIATION (ordre de confiance)

1. runtime production fonctionnel (le conteneur qui répond maintenant)
2. base de données actuelle
3. git HEAD / origin/main / déploiement Coolify
4. ce fichier (`docs/AFROBOOST_PROJECT_STATE.md`)
5. ancienne conversation / ancien onglet Chrome / modal resté ouvert / vue Coolify périmée

En cas de contradiction : **RÉCONCILIER AVANT D'AGIR.** Ne jamais contredire un état déjà prouvé
en production sur la seule foi d'un ancien onglet, d'un modal ou d'une liste UI.

Avant chaque lot / diagnostic / déploiement : (1) lire ce fichier ; (2) vérifier HEAD / origin/main ;
(3) si le sujet touche la production, vérifier le runtime réel.

### Pièges de méthode déjà payés (à ne pas repayer)

- **Page Coolify lue avant son rendu.** L'onglet « Environment Variables » est rendu par Livewire :
  une lecture trop tôt renvoie **zéro variable**, ce qui ressemble exactement à « la variable est absente ».
  C'est l'origine des affirmations fausses « `GOOGLE_CONTACTS_CLIENT_SECRET` absent ».
  **Toujours** recharger l'URL de l'onglet, attendre le rendu, puis compter les variables :
  si le compte est 0, la page n'est pas chargée — ce n'est pas un constat.
- **Un GET inconnu sous `/api/` renvoie 200**, car le catch-all SPA sert `index.html`.
  Pour prouver qu'une route existe : comparer avec une route de contrôle inexistante.
  **403 = la route existe et est protégée ; 405 = la route n'existe pas.**
- **Un `git push` ne prouve rien.** Vérifier le déploiement Coolify (`Success`) ET sonder la prod.

---

# ÉTAT ACTUEL

## A. ARCHITECTURE

- Application principale : **afroboost-v11-dev**
- Domaine : **https://afroboost.com**
- Repo : **afroboost/afroboost-v11-dev** — branche **main**
- Hébergement : Coolify sur VPS Hetzner `178.105.201.62`, conteneur Docker (uvicorn), Build Pack **Dockerfile**
- Base : MongoDB Atlas, DB **promo-credits-lab**

## I. COOLIFY — la bonne application

- Projet **afroboost.com** > application **`afroboost-v11-dev:main-ae8xfe89eru6bpsxgsyukp4t`** > sert **afroboost.com**
- **NE PAS CONFONDRE avec `afroboosteur-site`** (projet « Afroboost ») qui sert **afroboosteur.com**.
  C'est une application DIFFÉRENTE sur le MÊME serveur : y poser une variable n'a aucun effet sur afroboost.com.
- Dans le même environnement se trouvent aussi `afroboost-live`, `sportdate`, `sportdate-rencontre` : ce ne sont pas la bonne app.

## Git / déploiement (vérifié 2026-09-03 05:47 UTC)

- `origin/main` = `HEAD` local = **a20c93ad** — « P3-R1 : l'adresse de réponse porte l'identité de l'action »
- **Preuve runtime que la prod EXÉCUTE bien P3-R1** — deux faits indépendants, aucun ne repose sur Coolify :
  1. l'index **`reply_token_1`**, unique et partiel, **existe en base** — il n'est créé qu'au démarrage
     par le code de P3-R1 ;
  2. un e-mail réel envoyé à `r-<jeton>@reply.afroboosteur.com` est ressorti en base avec
     `matching_method = A0_REPLY_TOKEN`, confiance **100** — méthode qui n'existe que dans P3-R1.
- `GET /healthz` → 200 ; 15 sondes consécutives sur `/` → **15 × 200**, aucun 404 Traefik.
- Antérieurement : GOOGLE-2 (`9972d48a`) déployé le 02/09, Coolify Success 09:13:25 → 09:18:04 UTC.

## Variables d'environnement (présence uniquement, aucune valeur)

Relevées sur la bonne app, liste rechargée et rendue (38 variables) :

| Variable | Présente |
|---|---|
| `GOOGLE_CONTACTS_CLIENT_ID` | **oui** |
| `GOOGLE_CONTACTS_CLIENT_SECRET` | **oui** |
| `JWT_SECRET` | oui |
| `MONGO_URL`, `DB_NAME` | oui |
| `RESEND_API_KEY`, `RESEND_WEBHOOK_SECRET` | oui |
| `META_APP_SECRET`, `META_WHATSAPP_TOKEN`, `META_WHATSAPP_PHONE_ID` | oui |
| `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | oui |
| `PAWAPAY_API_TOKEN` | oui |

Confirmé côté runtime par `GET /api/debug/config` : `jwt_secret_set`, `resend_key_set`,
`openai_key_set`, `stripe_key_set`, `meta_app_secret_set` = **true**.

## F. GOOGLE-1 — VALIDÉ EN PRODUCTION

- OAuth Google **fonctionnel** ; lecture Google Calendar **réelle et prouvée**
- Événement Google (ex. « MENAGE ») affiché dans Afroboost ; suppression côté Google reflétée dans Afroboost
- Événements Google lus **à la volée**, non persistés inutilement
- Google Contacts : lecture active
- Preuve runtime du jour : `GET /api/google/calendars` → **HTTP 200, 2 calendriers Google réellement retournés**
  (appel vivant à l'API Google : prouve que le Client Secret fonctionne et que le refresh de jeton marche)
- `GET /api/google/status` → `configured: true`, `connected: true`, `revoked: false`, `calendar_granted: true`

### `google_tokens` (base, aucune valeur affichée)

| Fait | Valeur |
|---|---|
| Nombre de documents | **1** |
| Compte Afroboost associé (`coach_email`) | `contact.artboost@gmail.com` |
| `access_token` / `refresh_token` présents | **oui / oui** |
| Chiffrés (préfixe `enc:v1:`) | **oui** — aucune fuite en clair |
| Révoqué | non |
| Scopes actuels | `calendar.readonly` + `contacts.readonly` — **LECTURE SEULE** |
| Créé / rafraîchi | 2026-09-02 08:21:13 UTC / 10:13:47 UTC |

## G. GOOGLE-2 — **VALIDÉ EN PRODUCTION** (test réel du 2026-09-02)

- Code = commit **9972d48a**, déployé (Coolify Success 09:13→09:18 UTC le 02/09)
- Droits d'écriture **acquis** le 02/09 11:49 UTC : consentement OAuth avec `calendar.events`
- `calendar_write_granted = true`, `reconnect_required_for_sync = false`
- Scopes du jeton : `calendar.events` + `calendar.readonly` + `contacts.readonly`
  (les deux lectures ont été **conservées** — `include_granted_scopes` fait son travail)

### Test contrôlé de bout en bout — 13 points, tous verts

Événement `[TEST GOOGLE-2] À SUPPRIMER`, 2026-09-06, aucun prospect, aucune campagne,
aucune donnée métier touchée. Séquence réellement exécutée en production :

| # | Vérification | Résultat |
|---|---|---|
| 1 | Création dans Afroboost | OK — `836d9246`, HTTP 200 |
| 2 | Sync Google demandée et effectuée | OK — `google_sync_status = synced` |
| 3 | `google_event_id` réellement enregistré | OK — + `google_etag` présent (Google a répondu) |
| 4 | Exactement 1 événement chez Google | OK — suppression confirmée par Google, 0 orphelin ensuite |
| 5 | Aucun doublon dans Afroboost après refresh | OK — moisson Google = 0, inchangée |
| 6 | Modification du titre ET de l'heure | OK — HTTP 200 |
| 7 | Même `google_event_id` après modification | OK — identifiant identique |
| 8 | Retry contrôlé (sans `force`) | OK — `synced`, même identifiant, `attempts = 0` |
| 9 | Toujours exactement 1 événement Google | OK — aucun doublon après retry |
| 10 | Suppression explicite des deux côtés (`?google=delete`) | OK — `demande: true` |
| 11 | Disparition chez Google | OK — `supprime: true`, **confirmé par Google** |
| 12 | Nettoyage dans Afroboost | OK — suppression douce puis retrait du document de test |
| 13 | Aucune donnée de test restante | OK — 0 résidu en base, 0 résidu chez Google |

**Preuve d'unicité (la plus forte du lot)** : après la suppression douce, le document
n'est plus dans le filtre anti-doublon — toute la fenêtre Google redevient visible.
Le balayage a rendu **0 événement**. Un second exemplaire poussé par erreur serait
apparu ici en orphelin : il n'y en avait aucun.

**Intégrité vérifiée après le test** : le cours métier du 06/09 est intact ;
P3 inchangé (142 prospects, 137 actions, 0 contacté, 0 envoyé, 0 inbound,
drapeaux d'envoi toujours absents) ; Resend et DNS non touchés.

- Rappel de conception : la synchronisation est **explicite**, événement par événement
  (`google_sync` dans le corps). Rien ne part automatiquement.
- Rappel : **Afroboost écrit d'abord, Google ensuite.** Une panne Google n'annule jamais
  une création Afroboost.
- **NE JAMAIS conclure « secret absent »** sans avoir vérifié le runtime réel (cf. pièges de méthode).

## E. CALENDRIER

- **CAL-1 = VERT ; CAL-2 = VERT ; CAL-3 = VERT**
- Un seul calendrier Afroboost ; `calendar_events` = **collection centrale**
- Tâches natives + rendez-vous prospects dans le même calendrier et le même moteur
- Bouton « Planifier » (depuis une fiche prospect) fonctionnel
- **Afroboost = source de vérité** ; Google est une destination, jamais l'inverse

## D. RESEND

- **Receiving configuré** ; `email.sent` **actif** ; `email.received` **actif** (webhook signé Svix — lot P3-U3)
- **Reply-To commercial : `contact@afroboosteur.com`** — canonique pour tout ce qui n'est PAS P3
  (`AFROBOOST_REPLY_TO` et `AFROBOOST_REPLY_TO_RAPPELS` convergent dessus)
- **Reply-To des actions P3 : `r-<jeton>@reply.afroboosteur.com`, UN PAR ACTION** (P3-R1, `a20c93ad`).
  Le générique reste le repli quand l'action n'a pas de jeton (simulation) et pour tout e-mail hors P3.
  Domaine de réception réglable par `P3_REPLY_DOMAIN` ; **absent en production**, donc le défaut
  `reply.afroboosteur.com` s'applique — et il est prouvé fonctionnel (test réel du 03/09).
- ⚠️ **Resend NE TRANSMET PAS `In-Reply-To` ni `References`** dans `email.received`. Deux vraies
  réponses Gmail sont arrivées avec les deux champs vides, dont une APRÈS le correctif de lecture
  `fa3485ce` (les en-têtes Resend sont une LISTE, pas un dictionnaire — ce correctif était juste,
  mais insuffisant). **Ne pas rouvrir ce sujet** : les méthodes A et B sont indisponibles en pratique,
  c'est ce qui a rendu P3-R1 nécessaire.
- ✅ **Resend transmet le local-part COMPLET du destinataire** dans `to_email` (jeton compris).
  Prouvé deux fois en production : sonde du 02/09 19:22 UTC, puis test P3-R1 du 03/09 05:45 UTC.
- Expéditeur (FROM) : `Afroboost <notifications@afroboost.com>`
- ⚠️ `contact@afroboost.ch` est une **adresse morte** (domaine sans MX) : refusée par le code, ne pas la reposer
- **DNS déjà configuré — NE PAS recommencer la configuration DNS**

## C. P3 — PROSPECTION PARTENAIRES (re-vérifié en base 2026-09-03, après nettoyage de la fixture P3-R1)

| Fait | Valeur vérifiée |
|---|---|
| Campagne | **P3-LAUNCH-137** (`idempotency_key = P3-LAUNCH-137-INITIAL-2026-09`) |
| État | `approuvee` |
| `snapshot_hash` courant | `cd84f795ea66dc26fc288131559b016308be38eac9e86100c08fde6b3640bdb9` |
| Prospects (`partner_prospects`) | **142** |
| Actions (`prospect_campaign_actions`) | **137** |
| Contacté (`first_contact_claimed_at`) | **0** |
| Envoyé (`first_contact_sent_at`) | **0** |
| Inbound (`prospect_inbound_messages`) | **0** |
| Répartition par canal | email 56, instagram 51, formulaire 16, aucun 9, visite 3, whatsapp 1, téléphone 1 |
| Répartition par exécution | AUTO 56, MANUEL 53, ASSISTÉ 19, BLOQUÉ 9 |

### P3-R1 — CORRÉLATION FORTE : **VERT, PROUVÉE EN PRODUCTION (03/09/2026)**

Le rattachement d'une réponse ne passe plus par un en-tête que le fournisseur ne rend pas,
mais par **l'adresse à laquelle on demande de répondre** : chaque action porte son
`r-<jeton>@reply.afroboosteur.com`. Jeton = 128 bits d'aléatoire cryptographique, opaque,
**aucun identifiant métier** (ni `_id`, ni `action_id`, ni `recipient_key`, ni l'adresse du
prospect). Index unique **partiel** sur `reply_token` — présent en base, vérifié.

Ordre de corrélation : **A0 jeton (100)** > A `In-Reply-To` (100) > B `References` (95) >
`B_PROVIDER` (90) > C `from_email` (60) > revue manuelle. Les anciennes méthodes sont
**conservées**, elles reprendront du service le jour où les en-têtes arriveront.

Test réel contrôlé, fixture isolée (`FIXTURE-R1-*`), **aucun prospect réel touché** :

| # | Vérification | Résultat |
|---|---|---|
| 1 | Resend expose le local-part complet du destinataire | OK — jeton lu dans `to_email` |
| 2 | Réponse envoyée depuis une **AUTRE adresse** que celle démarchée | OK — `notifications@afroboost.com` ≠ `info@club-fictif-p3r1.exemple` |
| 3 | Méthodes A/B mécaniquement impossibles | OK — `in_reply_to: []`, `references: []` |
| 4 | Méthode C mécaniquement impossible | OK — l'expéditeur ne correspond à aucune `target` |
| 5 | Rattachement | OK — `matching_method = A0_REPLY_TOKEN` |
| 6 | Confiance | OK — **100**, `statut = rattache` |
| 7 | Action retrouvée | OK — `action_id`, `campaign_id`, `recipient_key` renseignés |
| 8 | `replied_at` écrit | OK — `2026-09-03T05:44:59.915Z` |
| 9 | Relances J+3 / J+7 annulées | OK — `j3_annule_le` + `j7_annule_le`, motif « reponse recue » |
| 10 | Deuxième réponse du même fil | OK — stockée, rattachée, **`replied_at` INCHANGÉ** |
| 11 | Aucun doublon d'action, aucun rejeu | OK — 2 messages, 1 seule pose de date |
| 12 | Jeton inconnu | OK — sonde `r-test-91f0…` → `AUCUNE`, revue manuelle, rien rattaché |
| 13 | `/prospect-inbound` protégé | OK — **403 sans jeton** (contrôle : route inexistante = 200, POST = 405) |
| 14 | Nettoyage de la fixture | OK — **0 résidu**, compteurs revenus à l'identique |

**Ce que le jeton n'ouvre pas** : aucune route ne l'accepte en entrée, il n'apparaît nulle part
dans le frontend, il n'est lu que depuis un message entrant **déjà authentifié par la signature
Svix**. Le **domaine est vérifié** en plus du préfixe — sans quoi `r-<jeton>@ailleurs.example`,
adresse qu'un tiers contrôle, serait lue comme une des nôtres.

**Multi-fiches** (5 destinataires portent plusieurs organisations) : couvert par le banc U2
(`11d. fiches_marquees == 2`), pas par le test réel — la fixture n'avait aucune fiche rattachée.

- **31 e-mails prêts mais NON envoyés** (chiffre déclaré par le coach ; en base, 56 destinataires
  de canal e-mail en exécution AUTO — à re-confirmer avant tout envoi).
- **Porte d'envoi FERMÉE et prouvée fermée** : les deux drapeaux `P3_LAUNCH_ENABLED` et
  `P3_LAUNCH_ENVOI_REEL` sont **absents** de `feature_flags` → l'envoi réel est impossible.
  L'absence est le cas sûr, par conception.
- **NE JAMAIS LANCER SANS GO EXPLICITE DU COACH.**

## B. P2 — PARTENAIRES

- **P2 terminé.** Ne pas modifier sauf blocage réel.
- Données de test supprimées (P2-CLEANUP, 31/08) ; sauvegardes dans `~/afroboost-sauvegardes/`.

## H. GOOGLE CLOUD

- Projet dédié : **Afroboost Production**
- Client OAuth dédié : **Afroboost Production**
- Redirect URIs (ne pas toucher) :
  `https://afroboost.com/api/google/callback` et `https://afroboost.com/api/google-contacts/callback`
- **NE PAS TOUCHER** : projet *Studiio Pro*, client *Firebase*
- Compte Google de test autorisé : **bassicustomshoes@gmail.com**
  (à distinguer du compte Afroboost propriétaire des jetons : `contact.artboost@gmail.com`)

---

# HISTORIQUE DES LOTS (SHA vérifiés dans git)

| LOT | COMMIT | PROD | VERDICT |
|---|---|---|---|
| P3-S1 | `863aeb82` | déployé | VERT — socle prospects |
| P3-S2 → S2F | `99d5d4d3` → `3e867ec2` | déployé | VERT — écran Prospection, 142 fiches |
| P3-S3-A → D4 | `64fa6aa9` → `118a805c` | déployé | VERT — campagne préparée, personne contacté |
| P3 Reply-To | `aeeecfe5` | déployé | VERT — `contact@afroboosteur.com` canonique |
| P3-U1 / U2 / U3 | `556a99ee` / `4bd1af5f` / `e7b69c79` | déployé | VERT — désabonnement, corrélation, Resend Receiving signé |
| CAL-1 | `f6c24435` | déployé | VERT |
| CAL-2 | `1b9f3492` | déployé | VERT |
| CAL-3 | `de0f8997` | déployé | VERT |
| GOOGLE-1 | `521cfe19` | déployé | VERT — lecture Google Calendar prouvée en production |
| GOOGLE-2 | `9972d48a` | déployé | **VERT** — écriture Google prouvée de bout en bout le 02/09 (13 points) |
| Hotfix espace abonné | `aad0fa7a` | **déployé (prod actuelle)** | **VERT** — une liste vide dit enfin pourquoi elle est vide |
| Lecture en-têtes Resend | `fa3485ce` | déployé | VERT — les en-têtes sont une liste ; correctif juste mais insuffisant (Resend ne les envoie pas) |
| P3-R1 | `a20c93ad` | **déployé (prod actuelle)** | **VERT** — corrélation par jeton prouvée en production le 03/09 (14 points) |

---

# DETTES / PROCHAINES ÉTAPES

- **GOOGLE-2 : terminé.** Plus rien à faire sur ce lot.
  ⚠️ Le `state` OAuth expire en **900 s** : si une reconnexion Google devient nécessaire un jour,
  générer le lien et cliquer **immédiatement**. C'est ce délai — et rien d'autre — qui avait fait
  échouer la première tentative.
- **P3-LAUNCH-137** : campagne prête, envoi bloqué par les deux drapeaux absents.
  N'ouvrir qu'après GO explicite écrit du coach.
- **P3-R1 : terminé et prouvé.** Le verrou technique qui empêchait de lancer sereinement
  — « une réponse envoyée depuis une autre adresse partait en revue manuelle et les relances
  continuaient » — est levé. Reste, avant tout envoi : re-confirmer le nombre réel de
  destinataires e-mail en exécution AUTO (**56 en base**, « 31 » annoncé par le coach).
- Dettes antérieures (non bloquantes) : cf. `CLAUDE.md` et l'historique des lots.

---

## Réservation & forfaits — DEUX FONCTIONS MANQUANTES (constaté 02/09/2026)

Les deux ont bloqué le coach une après-midi entière, sur un cours du soir.
Ce ne sont pas des bugs : ce sont des fonctions qui **n'existent pas**.

### Dette 1 — prolonger un forfait depuis le dashboard
**Aucune route ne modifie la date d'expiration d'un forfait existant.**
`PUT /subscriptions/{id}/sessions` ajuste les séances, `/profile` le profil,
mais la validité n'est modifiable nulle part. Le champ « expiration » de
l'onglet Codes promo ne sert qu'à la **création** (`POST /admin/create-code`) ;
`PromoCodesTab.js` ne fait que des lectures.
Conséquence vécue : le coach a cru prolonger, rien ne s'est écrit, et il a fallu
poser la date **directement en base**. À noter : la date vit à **deux endroits**
(`subscriptions.expires_at` ET `discount_codes.expiresAt`) — c'est la première
que lisent les gardes V393/LOT B2, mais les deux doivent rester cohérentes.

### Dette 2 — réservation administrateur explicite et tracée
**Il n'existe qu'UNE seule route de création de réservation** :
`POST /subscriber/space/{code}/reserve/{course_id}`, appelée uniquement par
`SubscriberSpace.js`. Le coach qui « réserve depuis l'administration » emprunte
donc exactement le chemin d'une participante, avec exactement les mêmes gardes.
Aucune dérogation admin n'est prévue. Un lot futur devra l'ajouter :
explicite, tracée, non destructive, sans falsifier l'abonnement.

### Corrigé au passage — `aad0fa7a` (déployé 02/09)
Le serveur envoyait déjà `forfait_bloque` / `forfait_message` pour expliquer une
liste de créneaux vide (V393) ; `SubscriberSpace.js` les ignorait et affichait
« Aucun cours disponible pour le moment » — la phrase d'un planning vide. Une
abonnée au forfait expiré en concluait qu'il n'y avait pas de cours, et le coach
avec elle. L'écran affiche désormais le motif du serveur.

---

## Bancs de test au ROUGE — état connu, à traiter dans un lot séparé

Les trois étaient **déjà rouges avant** les lots inbound (vérifié en retirant
les changements : `git stash`, relance, même échec). Aucun n'est causé par
P3-U3, la lecture des en-têtes, ni P3-R1. **Aucun n'est corrigé ici** — les
consigner évite qu'on les redécouvre en croyant à une régression.

| Banc | État | Cause connue |
|---|---|---|
| `test_p3s2_import_prospection` | ROUGE | Assertion « l'écran n'appelle que partner-prospects, prospect-campaigns, prospect-inbound et prospect-agenda ». **GOOGLE-2 a ajouté un appel `google/status`** dans `ProspectsSection.js` (case à cocher de synchronisation). L'écran est correct ; c'est l'assertion qui doit accueillir le nouvel appel. |
| `test_lot1_rattachement` | ROUGE | `IndexError` : le banc découpe `ChatWidget.js` sur l'ancre `=== LOT 1 — CHARGER DES OCCURRENCES`, **qui n'existe plus** dans le fichier (0 occurrence). Banc à ré-ancrer sur une propriété, pas sur un commentaire. |
| `test_lot3b_avantage_membre` | ROUGE | 218/219. Une seule vérification : `9K5. checkout_routes.py aussi`. |

**Re-vérifiés le 2026-09-03 05:43 UTC**, sur `a20c93ad`, sortie exacte :

| Banc | Sortie | Lot séparé à prévoir |
|---|---|---|
| `test_p3s2_import_prospection` | `164/165` — échec `8a.` ; l'appel constaté en trop est `google` | **LOT ROUGE-1** : accueillir `google/status` dans l'assertion `8a.` |
| `test_lot1_rattachement` | `IndexError` ligne 507, l'ancre commentaire n'existe plus | **LOT ROUGE-2** : ré-ancrer le banc sur une propriété du code, pas sur un commentaire |
| `test_lot3b_avantage_membre` | `218/219` — échec `9K5. checkout_routes.py aussi` | **LOT ROUGE-3** : trancher si `checkout_routes.py` doit porter la règle |

Les trois bancs verts du chantier inbound, aux mêmes date et commit :
`test_p3u3_resend_inbound` **133/133**, `test_p3u2_inbound` **102/102**,
`test_p3s3d1_moteur_factice` **226/226**.

**Règle de méthode** : avant d'incriminer un lot en cours, retirer ses
changements et relancer le banc. Un banc rouge n'est pas une régression tant
qu'on n'a pas prouvé qu'il était vert avant.

---

# MISE À JOUR DE CE FICHIER

À la fin de chaque lot réellement validé, mettre à jour **uniquement les faits qui changent** :
commit, état production, fonctionnalités prouvées, compteurs critiques, dettes restantes, prochain lot autorisé.
Ne pas réécrire l'ensemble. **Toujours distinguer ÉTAT ACTUEL et HISTORIQUE** : une situation passée
ne doit jamais être présentée comme l'état courant.

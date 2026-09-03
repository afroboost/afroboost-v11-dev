# AFROBOOST — ÉTAT PROJET (mémoire opérationnelle persistante)

> Source de vérité opérationnelle. **Documentation uniquement — aucun code, aucun secret.**
> Ne stocke que `présent = oui/non`, `configuré = oui/non`, des noms de variables, des SHA et des compteurs.
> Pour tout sujet **production**, la **preuve runtime** prime sur toute vue UI / onglet / rapport ancien.

Dernière réconciliation runtime vérifiée : **2026-09-03, 17:20 UTC**.

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

## Git / déploiement (vérifié 2026-09-03 13:12 UTC) — ✅ LIVRÉ, BLOCAGE RÉSORBÉ

- `origin/main` = `HEAD` local = **`e40f99b9`**, qui contient **`cccd739f` (P3-R3)** et
  **`96642164` (P3-R2)**. La production **exécute le nouveau code**.
- **Preuve runtime** : `boot_id` **`bd3d1c0b…`** (l'ancien `dda30969…` a disparu),
  démarrage du conteneur à **13:02:54 UTC**, soit **6 min 39 s APRÈS** le dernier push
  (`e40f99b9`, 12:56:15 UTC). Un démarrage postérieur au push, sur une app que Coolify
  reconstruit depuis `HEAD` : la bascule a bien eu lieu.
- **Limite honnête de cette preuve** : P3-R3 ne modifie que des fonctions internes
  (`p3s3_empreinte`), **sans aucune surface HTTP** — aucune route ne permet de lire
  l'algorithme depuis l'extérieur. La preuve est le démarrage postérieur au push, pas une
  signature du code. Elle ne bloque rien : le moteur de relance **n'a aucune route HTTP**
  et s'exécute depuis le dépôt, donc depuis le code poussé.
- Stabilité au même instant : **20/20 × 200** sur `/` via Cloudflare, **200** sur l'origine
  directe (`Host: afroboost.com` → `178.105.201.62`), aucun 404 Traefik, `boot_id` stable
  pendant toute la mesure.

## Git / déploiement — historique (vérifié 2026-09-03 05:47 UTC)

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
| État | **`approuvee`** — **CAMPAGNE J0 TERMINÉE le 03/09 10:57 UTC** ; **réapprobation courante 2026-09-03 12:02:35 UTC** par `contact.artboost@gmail.com` (P3-R3 : couvre les textes J+3/J+7). Réapprobation précédente 09:15:03 UTC archivée |
| `snapshot_hash` courant | **`de05fdeee289807574856e5aa7c24f83ca3e06b6ccdc1c520767c70b0b3f294b`** (P3-R3, 03/09 12:01) — couvre désormais **les trois messages et les trois objets**. Anciennes `cd84f795…` et `bfdba290…` archivées |
| Prospects (`partner_prospects`) | **142** |
| Actions (`prospect_campaign_actions`) | **137** |
| Contacté (fiches `first_contact_sent_at`) | **59 fiches** pour **55 destinataires** (4 destinataires portent 2 fiches) |
| Envoyé (actions `sent_at`) | **55 / 55** — le J0 est **terminé**, plus aucune action autorisée |
| Inbound (`prospect_inbound_messages`) | **2** — `ZRH-D5` SalsaRica (03/09 11:37 UTC) et `LSN-A3` ACD (03/09 13:35 UTC). **Les deux ont leur `body_text` réel depuis P3-R4** |
| Répartition par canal | email 56, instagram 51, formulaire 16, aucun 9, visite 3, whatsapp 1, téléphone 1 |
| Répartition par exécution | AUTO 56, MANUEL 53, ASSISTÉ 19, BLOQUÉ 9 |
| Approbations archivées | **3** (01/09 09:12, 01/09 11:17, 03/09 09:15 — rouvertes, historique intact) + l'approbation **courante** du 03/09 12:02:35 |
| `nb_destinataires` (campagne, tous canaux) | **136** — 137 actions moins `BAR-05` exclue |
| **AUTO e-mail encore autorisés** | **0** — tout est parti (3 le 03/09 10:00, puis 52 le 03/09 10:57) |
| Textes de relance écrits | **52 `message_j3`** et **52 `message_j7`** (P3-R3) ; `subject_j3` = `subject_j7` = `Re: Proposition de collaboration avec Afroboost` |
| Relances RÉELLEMENT envoyées | **0 `j3_sent_at`, 0 `j7_sent_at`** |

### 🟢 ÉTAT OPÉRATIONNEL AU 2026-09-03 16:03 UTC — **ATTENTE GO J+3**

- **P3-LAUNCH-137 reste la campagne UNIQUE** (`prospect_campaigns` = 1,
  `id = 6a1fddf8-8fdb-41e6-bd77-a8f43732b740`). Aucune seconde campagne n'a jamais été créée.
- **J0 terminé** : **55 premiers e-mails envoyés**, 55 actions `sent_at`, 59 fiches
  `first_contact_sent_at`. Historique **intact**.
- **Moteur J+3/J+7 (P3-R2) construit et validé** ; **contenus J+3/J+7 (P3-R3) réapprouvés**
  sur la même campagne, empreinte `de05fdee…` **conforme** (recalcul = base).
- **Production sur le nouveau code** (cf. « Git / déploiement » ci-dessus).
- **Contenu des réponses entrantes (P3-R4) : TERMINÉ.** Cf. section dédiée.
- **50 J+3 potentiellement éligibles au 06/09**, **selon l'état actuel** — simulation sans
  écriture : `SIMULATION` 50 · `JAMAIS_ENVOYE` 82 (les non-J0) · `REFUS_EXPRIME` 3 ·
  `A_REPONDU` **2** = 137 actions.
- **50 J+7 potentiellement éligibles au 10/09**, selon l'état actuel, **à recalculer par la
  garde le jour J** (même répartition).
- ⚠️ **CE NOMBRE SERA RECALCULÉ PAR LA GARDE LE JOUR J.** Chaque réponse, refus ou rebond
  arrivé d'ici là le fera baisser. Le 50 est une photo, pas un engagement — il valait
  **51** trois heures plus tôt, avant la réponse d'ACD.
- **Aucune relance J+3/J+7 n'a encore été envoyée** : `j3_sent_at` = 0, `j7_sent_at` = 0.
- **3 adresses en `REFUS_EXPRIME`** — les 3 rebonds **permanents**, déjà au registre STOP :
  `GVA-E1` (`fesstra@gmail.com`), `ORG-02` (`contact@case-a-chocs.ch`),
  `ORG-04` (`info@danse-neuchatel.ch`). Bar King (`BAR-02`, rebond **transitoire**) garde ses relances.
- **2 prospects ont répondu** (`A_REPONDU` = 2), tous deux corrélés en réel par
  **`A0_REPLY_TOKEN`, confiance 100**, J+3 **et** J+7 annulés automatiquement :
  **`ZRH-D5` / SalsaRica** (REFUS) et **`LSN-A3` / ACD Lausanne** (POSITIVE).
- **Aucune relance réelle envoyée. Portes d'envoi FERMÉES** : `P3_LAUNCH_ENABLED` et
  `P3_LAUNCH_ENVOI_REEL` à `false`, `P3_RELANCE_ENABLED` et `P3_RELANCE_ENVOI_REEL`
  **absents** → `p3r2_envoi_autorise()` = **False**.
- **Statut : ATTENTE GO J+3. NE RIEN ENVOYER SANS GO EXPLICITE DU COACH.**

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

### LOT P3-J0-25 — les 25 messages manquants sont écrits (03/09/2026)

**`MESSAGE_VIDE` restant : 0.** Les 25 actions AUTO+e-mail sans `message_j0` en ont désormais un.
Aucune n'a été jugée `DONNEES_INSUFFISANTES` : **chaque fiche portait déjà, dans ses `notes`,
un « Pourquoi Afroboost » et une « Idée de collaboration » rédigés par le coach**. C'est cette
matière-là qui a servi — aucune recherche web, aucun fait inventé sur une organisation réelle.

| Avant | Après |
|---|---|
| AUTO+e-mail avec `message_j0` : 31 | **56** |
| `MESSAGE_VIDE` : 25 | **0** |
| `message_j0_origine` | 31 `fiche` + **25 `edite`** |

Trois consignes de rédaction respectées et vérifiées par relecture automatique :
aucun **QR**, aucune statistique, aucune commission, aucune exclusivité — les trois fiches
dont l'idée mentionnait un QR (`COM-07`, `RES-04`, `RES-09`) ont été reformulées en
« invitation découverte » / « offre membres ». Format tenu : 1 idée + 1 raison personnalisée
+ 1 CTA court, 263 à 383 caractères (les 31 existants sont dans la même plage).

**Langue** : les 25 avaient `language` vide (non précisée) — **aucune traduction automatique**,
tout est en français, y compris Bienne (`ECO-10`). Les versions allemandes de Zurich n'ont pas
été touchées.

**Déduplication** : `FES-08` porte deux fiches (LAFF + CIPINA) — **un seul J0**, sur la seule
action de ce `recipient_key`. Aucun doublon créé.

⚠️ **La campagne a été ROUVERTE, et c'est le mécanisme prévu, pas un contournement.**
`POST /prospect-campaigns/{id}/rouvrir` : l'approbation précédente est **archivée** dans
`approbations` (avec sa date, son auteur, son empreinte et la date de réouverture), l'état
redevient `preparee`, `snapshot_hash` est effacé. **Aucune seconde campagne n'a été créée.**
Trois raisons indépendantes empêchent aujourd'hui tout envoi : état non approuvé, empreinte
absente, drapeaux absents.

### Arbitrage du coach — deux adresses, une seule maison (03/09)

Deux actions visaient le **même domaine `case-a-chocs.ch`** : `ORG-02` (Case à Chocs,
`contact@`) et `BAR-05` (L'Interlope, `interlope@`). Ce n'était pas un doublon technique —
deux fiches, deux adresses — mais la fiche de L'Interlope désigne elle-même comme contact
**« Programmation Case à Chocs »** : les deux boîtes aboutissent au même bureau.

**Décision du coach : `ORG-02` part, `BAR-05` attend.** `BAR-05` passe en `statut = "exclu"`
(chemin `excluded: true` de la route de modification). **Rien n'est supprimé** : l'action, son
message et la fiche `partner_prospects` (toujours `a_contacter`) restent intacts et
réintégrables en un appel. Une action `exclu` sort de l'empreinte ET du décompte.

**AUTO destinés au premier lancement : 56 → 55.**

**Aucun autre doublon organisationnel**, vérifié sur quatre critères parmi les 55 partants :
adresse e-mail exacte (55 distinctes), domaine d'entreprise hors messagerie gratuite (aucun
en double), site web (aucun partagé), adresse postale (aucune partagée). Les **8 adresses
`gmail.com`** appartiennent à **8 entités réellement indépendantes** (noms, villes et
catégories différents) : un domaine gratuit partagé n'est pas un doublon. `GVA-D2` porte deux
sites « Dancefloor Studio » **dans la même action** — un seul message, pas un doublon.

### ✅ PREMIERS ENVOIS RÉELS — 3 J0 PARTIS (03/09 10:00 UTC)

Après libération des 3 verrous (`p3s3d_liberer`, mécanisme prévu) et installation du SDK,
le même passage a été rejoué, plafond 3. **3 SUCCESS, 3 identifiants Resend réels.**

| Destinataire | Identifiant Resend | Reply-To individuel | État Resend |
|---|---|---|---|
| `BAR-01` Waves — Rooftop (Beaulac) | `01a066b6-0515…` | `r-5c04a040…@reply.afroboosteur.com` | **delivered** |
| `BAR-02` Bar King | `01a066b6-08ef…` | `r-dcac8e46…@reply.afroboosteur.com` | ⚠️ **bounced** |
| `BAR-03` Café du Cerf | `01a066b6-0c26…` | `r-64b1d6ef…@reply.afroboosteur.com` | **delivered** |

Tout est conservé de la tentative avortée : **même jeton, même clé d'idempotence, même
message, même destinataire** — c'est ce qui rend une réponse au premier envoi rattachable.
Chez Resend : **3 e-mails portant l'objet de campagne, 0 doublon de destinataire.**

**P3-U3 a fonctionné pour de vrai** : le webhook `email.sent` a rendu le `Message-ID` RFC,
enregistré sur les 3 actions. La méthode A redevient donc disponible **pour ces trois-là**,
en plus de A0.

📌 **Où lire le compteur « envoyé »** : `first_contact_sent_at` vit sur les **fiches
`partner_prospects`** (3), **pas** sur les actions — sur l'action c'est `sent_at` (3).
Ne pas compter le mauvais champ.
📌 `verrou_actif` **reste posé après un succès**, volontairement : l'envoi est définitif,
le verrou empêche tout second premier contact. Ce n'est pas un blocage à nettoyer.

### 🚀 ENVOI DES 52 — LE J0 EST TERMINÉ (03/09 10:57:09 → 10:57:56 UTC, 47 s)

**52 tentatives, 52 SUCCESS, 0 échec.** Aucun `PERMANENT`, aucun `RETRYABLE`, aucun
`INDETERMINE`. Porte ouverte 47 secondes, **refermée dans le `finally`** et vérifiée close.
Plafond 52 respecté : **aucun 53ᵉ envoi**.

| Fait | Valeur vérifiée |
|---|---|
| Total envoyé sur la campagne | **55 / 55** (3 + 52) |
| `provider_message_id` | **55**, tous **distincts** |
| Jetons de réponse P3-R1 | **55**, tous **distincts** |
| Destinataires | **55 distincts** — **0 doublon** |
| `rfc_message_id` (webhook `email.sent`) | **55** — la méthode A est disponible partout |
| Fiches `contacte` | **59** (4 destinataires portent 2 fiches) |
| Actions encore autorisées | **0** |
| Empreinte | conforme |

**Contrôle croisé chez Resend, les 55 interrogés un par un** :
**49 `delivered` · 4 `bounced` · 2 `sent`** (encore en vol au moment du contrôle).
**55 destinataires distincts, 55 Reply-To individuels distincts, 0 non conforme au
format `r-<32 hex>@reply.afroboosteur.com`.**

### ⚠️ P3-B1 A FONCTIONNÉ EN PRODUCTION, SUR DE VRAIES DONNÉES — 4 rebonds

Déployé depuis quelques minutes, le lot a traité **4 rebonds réels sans intervention** :

| Destinataire | Type | Adresse | Effet |
|---|---|---|---|
| `GVA-E1` FESTTRAA | **Permanent** | `fesstra@gmail.com` | J+3/J+7 annulés, **registre STOP** |
| `ORG-02` **Case à Chocs** | **Permanent** | `contact@case-a-chocs.ch` | J+3/J+7 annulés, **registre STOP** |
| `ORG-04` ADN — Assoc. Danse NE | **Permanent** | `info@danse-neuchatel.ch` | J+3/J+7 annulés, **registre STOP** |
| `BAR-02` Bar King | `Transient` | `caveauduking@gmail.com` | enregistré, **rien bloqué** |

La garde le confirme : **`REFUS_EXPRIME` = 3**. Les trois adresses sont désormais refusées
par le système lui-même, sans qu'aucune règle ait été posée à la main. Les fiches restent
`contacte`, ne sont pas supprimées, et une nouvelle adresse les rendrait joignables.

🔴 **À TRANCHER PAR LE COACH — `contact@case-a-chocs.ch` est une adresse morte.**
C'est **exactement l'adresse retenue lors de l'arbitrage du 03/09**, au détriment de
`interlope@case-a-chocs.ch` (`BAR-05`, mise en attente, jamais contactée). La maison n'a
donc **rien reçu**. `BAR-05` est toujours `exclu` et intacte : la réintégrer est un appel,
et c'est la seule voie e-mail restante vers la Case à Chocs.

### ✅ INCIDENT REFERMÉ — LE DÉPLOIEMENT ÉTAIT EN RETARD, PAS EN PANNE (12:35 → 13:12 UTC)

**Ce qui avait été constaté à 12:35 UTC** : deux pushes — `cccd739f` (P3-R3) puis
`5803f8df` (re-déclenchement via `trigger.txt`) — sans aucune bascule de conteneur,
`boot_id` figé sur `dda30969…` pendant plus de **88 minutes**. Le site répondait
parfaitement (25/25 × 200) : ce n'était pas une panne de service.

**Résolution constatée à 13:12 UTC, sans aucune intervention sur le code** : le conteneur
a redémarré à **13:02:54 UTC** avec un nouveau `boot_id` (`bd3d1c0b…`), soit **après** le
dernier push. Le build est passé ; le code de P3-R3 est en ligne.

**Ce que l'épisode confirme, et qu'il faut garder** : pendant tout le retard,
**aucun risque d'envoi n'a existé**. Les deux drapeaux étaient fermés, 0 action J0 encore
autorisée, aucune route HTTP ne déclenche d'envoi, et une empreinte jugée non conforme
**arrête** le moteur. L'écart penchait **du côté sûr** — et il s'est résorbé seul, comme
prévu, dès le passage du build.

📌 **Leçon de méthode** : un `boot_id` figé plus d'une heure après un push est un signal de
retard de livraison, pas une preuve de panne définitive. Avant d'ouvrir Coolify, **re-sonder
`/healthz`** : un `uptime_s` faible et un `boot_id` neuf suffisent à clore le sujet.

### 📥 P3-R4 — LE CORPS DES REPONSES EST ENFIN LU (03/09)

**Le trou** : le webhook `email.received` de Resend **ne porte pas le corps du message**,
par conception. On savait **qu'**un prospect avait répondu, jamais **quoi** : `body_text`
était vide sur la première vraie réponse de la campagne.

**Le correctif** : après la corrélation — jamais avant, jamais à sa place — le corps est lu
en **lecture seule** chez le fournisseur (`GET /emails/receiving/{email_id}`), puis conservé
avec le message. Le nouveau texte et **l'historique cité sont SÉPARÉS** (`body_text` /
`body_quoted`) : sans cette coupe, notre propre J0 revenait en base comme s'il venait du
prospect.

**La règle qui domine le lot** : *la perte du corps n'entraîne jamais la perte de la
corrélation.* Fournisseur muet, clé absente, exception inattendue → le message est stocké,
`replied_at` est écrit, les relances sont annulées, et **seul le contenu** porte un état
d'échec (`contenu_recupere: false` + motif). Une panne de lecture n'est pas une réponse
inexistante. Un rejeu du même webhook **complète** un corps manquant sans rien dupliquer.

⚠️ **DEUX PIÈGES DÉJÀ PAYÉS, à ne pas repayer** :
1. l'`email_id` est un **UUID**. L'identifiant d'**événement** (`msg_…`), le seul que la base
   conservait, est refusé en **422** « must be a valid UUID ». Le lot le VALIDE désormais.
2. `urllib` reçoit un **403 Cloudflare « error code: 1010 »** sur `api.resend.com` — ce
   n'est **pas** un refus de clé. Passer par le SDK (`resend.Emails.Receiving`) ou `curl`.

**Anti-confusion, prouvée par banc** : aucun champ rédigé par Afroboost (`message_j0`,
`message_j3`, `message_j7`, `interested_message`) ne peut devenir un corps entrant. Le seul
repli autorisé est le texte livré par le FOURNISSEUR. Le banc échoue si quelqu'un
réintroduit un repli commercial.

**Bancs** : `test_p3r4_contenu_entrant` **121/121** (A→J du cahier des charges). Non-régression
au vert : U1 64 · U2 102 · U3 134 · B1 84 · R2 69 · D1 226 · D2 116 · D3 112 · D4 100 ·
S3-A 159 · préparation 149 · réouverture 110 · S1 82 · reply-to 44 · boot 21 · opt-out 50.
**0 e-mail, 0 socket.** Le rattrapage **n'a AUCUNE route HTTP** et simule par défaut.

### 🎉 DEUX RÉPONSES RÉELLES — dont une POSITIVE (03/09)

`prospect_inbound_messages` = **2**, toutes deux rattachées par jeton
(`A0_REPLY_TOKEN`, confiance **100**), `replied_at` écrit, J+3 **et** J+7 annulés
automatiquement, fiches passées à `repondu`. Aucune intervention humaine.

| Réf | Organisation | Reçu (UTC) | Intention |
|---|---|---|---|
| `ZRH-D5` | SalsaRica Dance School, Zürich | 03/09 11:37:15 | **REFUS** net, en allemand |
| `LSN-A3` | Association Art et Culture pour le Développement (ACD), Lausanne | 03/09 13:35:35 | **POSITIVE** — un contact et un numéro donnés |

> ⚠️ **ÉTAT DÉPASSÉ, conservé pour l'historique** : au moment de la livraison de P3-R4, le
> rattrapage n'était PAS exécuté — la simulation attendait 1 candidat et en avait trouvé 2,
> la seconde réponse étant arrivée pendant le lot. **Il a été exécuté depuis** (03/09 16:03
> UTC, sur GO), et la section ci-dessous fait foi.

### ✅ RATTRAPAGE P3-R4 EXÉCUTÉ — 2/2 (03/09 16:03 UTC, sur GO du coach)

| Fait | Valeur |
|---|---|
| Messages candidats | **2** |
| Messages complétés | **2 / 2** (verdict `COMPLETE` sur chacun) |
| `ZRH-D5` SalsaRica | **COMPLETE** — `provider_email_id` `88268b21-13be-4b73-9ee6-437fe86396e4` |
| `LSN-A3` ACD | **COMPLETE** — `provider_email_id` `71ce4a20-921a-44dd-b8cb-5cbf558bffb5` |
| Contenu réel récupéré depuis Resend | **OUI** |
| Source | **`text`** pour les deux (`contenu_source`), `contenu_erreur` vide |
| Corrélation | **INCHANGÉE** — `A0_REPLY_TOKEN` / confiance **100** sur les deux |
| `replied_at` | **INCHANGÉS** — `ZRH-D5` 11:37:15.440Z, `LSN-A3` 13:35:35.233Z |
| Annulations J+3/J+7 | **INCHANGÉES**, au caractère près |
| Nouvel inbound créé | **0** — les 2 documents existants ont été complétés, rien d'autre |
| E-mails envoyés / relances envoyées | **0 / 0** |
| Portes d'envoi | **FERMÉES** (`P3_LAUNCH_*` à `false`, `P3_RELANCE_*` absents) |
| Campagne P3 unique / actions / prospects | **1 / 137 / 142** |
| Registre STOP | **11 entrées, inchangé** |

**SalsaRica et ACD disposent désormais de leur vrai `body_text` entrant.** Avant P3-R4, ces
deux champs étaient vides : on savait qu'un prospect avait répondu, jamais quoi.

⚠️ **AUCUN champ Afroboost n'a servi de corps entrant** — ni `j0_message`, ni
`message_j3`, ni `message_j7`, ni `interested_message`. Vérifié champ par champ sur les
deux documents.

📌 **PIÈGE DE CONTRÔLE, à ne pas repayer.** Chercher un texte Afroboost dans **tout** le
document donne un **faux positif** : notre J0 s'y trouve légitimement, dans `body_quoted` —
c'est l'historique que le logiciel de messagerie du prospect recopie sous sa réponse. **Le
seul contrôle qui compte porte sur `body_text` SEUL**, et il est propre sur les deux.

**P3-R4 ENRICHIT, IL NE CORRÈLE PAS.** Le lot n'a pas touché une ligne de P3-R1 : il vient
APRÈS la corrélation, jamais à sa place. Et la règle qui gouverne le reste :
**une panne future de récupération du corps ne doit JAMAIS faire perdre la corrélation** —
message stocké, `replied_at` écrit, relances annulées, seul le contenu porte l'échec
(`contenu_recupere: false` + motif).

### ✍️ P3-R3 — LES RELANCES ONT UN TEXTE (03/09 12:01 UTC)

**52 J+3 et 52 J+7 écrits**, tous **distincts**, tous **plus courts que leur propre J0**
(175 à 264 caractères contre 243 à 383). Aucune donnée inventée : chaque phrase
personnalisée est **tirée du J0 déjà approuvé** de la même action — donc de la matière que
le coach avait lui-même écrite dans les `notes` de la fiche.

**3 destinataires écartés — les 3 rebonds PERMANENTS** : `GVA-E1` FESTTRAA, `ORG-02` Case à
Chocs, `ORG-04` ADN. Aucun texte ne leur est préparé ; leur adresse est de toute façon au
registre STOP. `BAR-02` Bar King (rebond **transitoire**) **garde** ses relances : il n'est
pas bloqué, et rien n'est renvoyé maintenant.

**Langues** : celle du J0 réellement parti, jamais retraduite. **46 en français**,
**6 en allemand** (`ZRH-D1`, `ZRH-D3`, `ZRH-D5`, `ZRH-E1`, `ZRH-F1`, `ZRH-F4` — leur J0
était en allemand, y compris ceux marqués « anglais » ou « les trois » dans la fiche : c'est
le message ENVOYÉ qui fait foi, pas le champ `language`).

**Objet des deux relances : `Re: Proposition de collaboration avec Afroboost`.** Le moteur
EXIGE `subject_j3` / `subject_j7` (sinon `OBJET_ABSENT`) — ils ne peuvent donc pas être
omis. Reprendre l'objet du premier message **préfixé de `Re:`** est la solution minimale
cohérente : les clients de messagerie regroupent sur l'objet, la relance reste **dans le
même fil**, et le `Re:` dit honnêtement que c'est un suivi.

### 🔒 L'EMPREINTE COUVRE ENFIN LES RELANCES — un trou qui aurait pu coûter cher

En préparant ce lot, un contrôle a montré que **l'empreinte ne changeait PAS** quand on
ajoutait `message_j3` / `message_j7` : elle ne couvrait que `message_j0` et `subject_j0`.
Autrement dit, un texte de relance pouvait être remplacé **après** l'approbation sans que
le moteur ne voie rien passer — exactement le défaut « approuver A, envoyer B » que cette
empreinte existe pour empêcher, simplement **décalé d'une étape**.

`p3s3_empreinte` couvre désormais **les trois messages et les trois objets**. C'est ce qui
fait passer l'empreinte de `bfdba290…` à `de05fdee…`. Banc D3 enrichi de 5 vérifications
(107 → **112**) : modifier `message_j3`, `message_j7`, `subject_j3` ou `subject_j7` change
maintenant l'empreinte.

**Réapprobation faite sur LA MÊME campagne** (`prospect_campaigns` = 1), empreinte
**recalculée au moment de l'approbation**, **3 approbations archivées**, historique intact.

⚠️ **APPROUVER N'EST PAS ENVOYER.** Les drapeaux `P3_RELANCE_ENABLED` /
`P3_RELANCE_ENVOI_REEL` restent **absents**. Aucune relance n'est partie.

**Simulation sur la production** (aucune écriture, vérifiée) :

| Échéance | Partiraient | Bloqués |
|---|---|---|
| **J+3 au 06/09** | **51** | 3 `REFUS_EXPRIME` (rebonds durs) · **1 `A_REPONDU`** · 82 `JAMAIS_ENVOYE` |
| **J+7 au 10/09** | **51** | idem |

> ⚠️ **Mesure du 03/09 12:01 UTC, DÉPASSÉE.** Depuis la réponse d'ACD, c'est **50** au
> 06/09 et **50** au 10/09 (`A_REPONDU` = 2). Chiffre à jour : section « ÉTAT
> OPÉRATIONNEL » en tête de la partie C.

### 🎉 UNE PREMIÈRE RÉPONSE EST ARRIVÉE — ET P3-R1 L'A RATTACHÉE SEUL

> Une **seconde** est arrivée depuis (`LSN-A3` / ACD, 03/09 13:35 UTC) : voir la section
> « DEUX RÉPONSES RÉELLES ». Les deux ont leur corps réel depuis le rattrapage P3-R4.

`SalsaRica Dance School` (Zurich, `ZRH-D5`) a répondu le **03/09 à 11:37 UTC**, depuis
`info@salsarica.ch` sur `r-6e7e104e…@reply.afroboosteur.com`.
**`matching_method = A0_REPLY_TOKEN`, confiance 100, `statut = rattache`.**
`replied_at` écrit, **J+3 et J+7 annulés automatiquement** (motif « reponse recue »), fiche
passée à `repondu`. La chaîne complète — jeton, corrélation, arrêt des relances — est donc
prouvée **sur un vrai prospect**, pas sur une fixture.

### ⏸️ P3-R2 — LE MOTEUR DE RELANCE EXISTE, ET IL N'A RIEN À DIRE (03/09)

> ⚠️ **SECTION HISTORIQUE — DÉPASSÉE PAR P3-R3.** Ce qui suit décrit l'état du moteur
> **avant** que les textes de relance soient écrits. Depuis P3-R3 (03/09 12:01 UTC), les
> 52 `message_j3` / 52 `message_j7` et les deux objets existent : `MESSAGE_VIDE` et
> `OBJET_ABSENT` ne s'appliquent plus. **Chiffres à jour : section « ÉTAT OPÉRATIONNEL »
> en tête de la partie C.** Le moteur lui-même n'a pas changé.

`p3u2_relance_autorisee` existait depuis U2, testée, correcte — et **n'avait aucun
appelant**. Aucune relance ne partait, non parce qu'une garde l'interdisait, mais parce que
**rien ne les exécutait**. Le jour où un cron aurait été branché à la va-vite, il aurait
relancé sans consulter cette garde. C'est ce vide qui est comblé.

Le moteur est le **jumeau** de celui du J0 : même ordre d'écritures (garde → réservation →
trace d'intention → fournisseur → verdict), mêmes verrous conditionnels, même isolement des
erreurs, même plafond. Il **ne recopie pas** la garde de U2, **il l'appelle**.

⛔ **IL NE PEUT RIEN ENVOYER AUJOURD'HUI, ET CE N'EST PAS UN DRAPEAU.**
Les actions ne portent **aucun `message_j3` ni `message_j7`** (0 sur 137) et la campagne
n'a **ni `subject_j3` ni `subject_j7`**. Il n'y a pas de texte de relance. Le moteur refuse
donc sur `MESSAGE_VIDE` — exactement comme le J0 refusait les 25 sans texte avant qu'on les
rédige.

📌 **On ne va PAS chercher le texte dans la fiche.** 72 fiches portent un `j3_message`,
mais l'instantané approuvé ne couvre que `message_j0`. Envoyer un texte que le coach n'a
jamais approuvé à cette étape est exactement ce que l'empreinte existe pour empêcher.
**Rédiger les relances est un lot à part, avec sa réapprobation**, comme P3-J0-25 l'a été.

**Simulation sur la production réelle** (aucune écriture, vérifié champ par champ) :

| Échéance | Partiraient (mesure du 03/09 **avant** P3-R3) | Détail |
|---|---|---|
| **J+3 au 06/09** | **0** | 52 `MESSAGE_VIDE` · 3 `REFUS_EXPRIME` (rebonds durs) · 82 `JAMAIS_ENVOYE` |
| **J+7 au 10/09** | **0** | idem |

> Mesure **remplacée** depuis P3-R3, puis à nouveau depuis la réponse d'ACD : **50** au
> 06/09 et **50** au 10/09, selon l'état actuel — 50 `SIMULATION` · 82 `JAMAIS_ENVOYE` ·
> 3 `REFUS_EXPRIME` · **2 `A_REPONDU`**.

Les 3 rebonds permanents sont **déjà écartés** par le registre STOP, sans règle ajoutée.
Bar King (transitoire) reste dans les 52 : il n'est pas bloqué, il n'a simplement pas de texte.

**Drapeaux dédiés** : `P3_RELANCE_ENABLED` / `P3_RELANCE_ENVOI_REEL`, **absents** donc
fermés. Réutiliser ceux du J0 aurait rouvert la porte du **premier** contact en même temps.
Deux étapes, deux portes.

📌 Le **jeton de réponse P3-R1 de la relance est celui du J0** : une réponse à une relance
doit se rattacher à la même action — c'est la même conversation. Un second jeton aurait
créé deux fils pour un seul prospect.
📌 **Aucun cron n'a été créé.** L'exécuteur est appelable de façon contrôlée, avec plafond.

Banc **P3-R2 : 69/69**. Non-régression : U1 64 · U2 102 · U3 134 · B1 84 · D1 226 · D2 116 ·
D3 107 · D4 100 · préparation 149 · opt-out 50 · boot 21. **0 e-mail, 0 socket.**

### ✅ P3-B1 — LES REBONDS SONT TRACÉS (livré et déployé le 03/09, `ea73c2e8`)

**L'abonnement Resend a été corrigé en premier** — c'était là qu'était la cause :
`events: ["email.sent", "email.received", "email.bounced"]`, même webhook, même endpoint,
même secret de signature. **P3-R1 et `email.received` intacts** (webhook toujours 401 sans
signature Svix).

Ce que fait le lot, action par action, sur `email.bounced` :

| Cas | Effet |
|---|---|
| **Tout rebond** | `provider_status = bounced`, `bounced_at`, `bounce_type`, `bounce_subtype`, `bounce_message` — **write-once** |
| **`Permanent` SEULEMENT** | annule J+3 et J+7 (champs **existants**, motif « rebond permanent ») **et** inscrit l'adresse au registre STOP → la garde `REFUS_EXPRIME` refuse ensuite tout envoi |
| **`Transient` / `Undetermined` / inconnu** | enregistré, **rien de bloqué** — se tromper en bloquant coûte un prospect, se tromper en ne bloquant pas coûte un e-mail |

📌 **`contacte` n'est PAS redéfini** : le contrat reste « accepté par le fournisseur », qui
reste vrai. La nuance de livraison se lit dans `provider_status` / `bounce_type`, à côté.
📌 **L'adresse bloquée est le `target` de NOTRE action**, jamais celle annoncée par la
charge utile — seule valeur dont nous soyons la source.
📌 Corrélation par `provider_message_id` en **égalité stricte**, aucune regex.
📌 Une annulation de relance déjà posée par une **réponse** n'est jamais écrasée.

**Bar King régularisé à partir de la réponse RÉELLE de l'API Resend** (aucun champ inventé) :
`bounce_type = Transient`, `subType = General` → **SOFT**. Donc enregistré, **J+3/J+7 non
annulés, aucun registre STOP** — l'adresse reste joignable, ce que dit Resend lui-même
(« un envoi ultérieur peut passer »). Rejeu du même événement : `doublon: true`, aucun effet.

Bancs : **P3-B1 84/84**, U3 **134/134**, U2 102, U1 63, D1 226, D2 116, D3 107, D4 100,
préparation 149, opt-out 50, boot 21 — **0 e-mail, 0 socket**.

### Historique — comment la dette avait été constatée (03/09, lecture seule)

Ce n'est pas seulement que le code ne traite pas les rebonds : **l'abonnement Resend ne les
demande même pas.** Relevé sur l'API Resend, webhook `f486bc06…`, `status: enabled`,
endpoint `https://afroboost.com/api/webhooks/resend` :
**`events: ["email.sent", "email.received"]`** — ni `email.bounced`, ni `email.delivered`.
Resend **ne nous enverra donc jamais** l'information, et le handler acquitte de toute façon
en 200 tout type inconnu sans rien écrire. **Aucune trace de rebond n'est possible en base.**

État réel de `BAR-02` (Bar King, `caveauduking@gmail.com`) : `statut = envoye`,
`provider_status = accepted`, fiche `contacte`, **aucun champ `bounce`, `bounced_at` ni
erreur**. Chez Resend : `last_event = bounced`, `type = Transient`, `subType = General`
(« le fournisseur du destinataire a renvoyé un rebond général ; un envoi ultérieur peut
passer ») — donc un **SOFT bounce**, pas une adresse morte.

Ce qui se passerait aujourd'hui pour Bar King, mesuré avec les gardes réelles :

| Question | Réponse | Pourquoi |
|---|---|---|
| Un nouveau J0 partirait-il ? | **NON** | `DEJA_CONTACTE` — mais parce qu'il est « contacté », **pas** à cause du rebond |
| La garde de relance l'autorise-t-elle ? | **OUI** (`autorise: true`) | elle ignore tout du rebond |
| Un J+3 / J+7 partirait-il ? | **NON, aujourd'hui** | uniquement parce qu'**aucun moteur de relance n'existe** (`p3u2_relance_autorisee` n'a **aucun appelant**) |
| L'adresse est-elle bloquée après un rebond dur ? | **NON** | aucun mécanisme ; registre STOP vide pour cette adresse |

⚠️ **Le jour où un moteur J+3 sera écrit, il relancera une adresse qui a rebondi sans le
savoir.** C'est ce couple — rebond invisible + relance aveugle — qu'il faut fermer.

**Correctif minimal alors proposé — LIVRÉ depuis, cf. ci-dessus :**
1. **Abonner `email.bounced`** sur le webhook Resend (réglage, pas de code).
2. **Prouver la charge utile AVANT de coder** — comme pour P3-R1 : recevoir un vrai
   `email.bounced` et vérifier qu'il porte bien un identifiant corrélable
   (`provider_message_id`) et le couple `type`/`subType`. Sans cette preuve, ne rien écrire.
3. Une branche dans le handler : corrélation **par `provider_message_id`** (déjà indexé et
   déjà stocké sur l'action), écriture **write-once** de `bounced_at`, `bounce_type`,
   `bounce_subtype`, `bounce_message`, `provider_status = "bounced"`.
4. **Rebond PERMANENT uniquement** : poser `j3_annule_le` / `j7_annule_le` (champs
   **existants**, motif « rebond permanent ») **et** inscrire l'adresse au registre STOP via
   `p3u1_enregistrer_refus("email", …)` — la garde `REFUS_EXPRIME` bloque alors tout envoi
   futur, sans nouveau mécanisme. Rebond **transitoire** : on enregistre, on ne bloque rien.
5. **Ne pas toucher au sens de `contacte`.** Le contrat actuel est « accepté par le
   fournisseur » ; le remettre en cause dépasse ce correctif. La distinction se lit dans le
   nouveau champ `provider_status`, pas dans `status`.

L'historique du premier envoi est conservé dans tous les cas, le prospect n'est jamais
supprimé, et une nouvelle adresse trouvée plus tard restera contactable.

### ⛔ INCIDENT — PREMIER ENVOI x3 AVORTÉ, 0 E-MAIL PARTI (03/09 09:51 UTC)

Un premier passage réel plafonné à 3 a été lancé sur GO écrit du coach. **Aucun e-mail
n'est parti** : le moteur a été exécuté **depuis le poste local**, où le paquet `resend`
n'était **pas installé**. `import resend` a levé `ModuleNotFoundError` **avant** le moindre
appel réseau.

**LA LEÇON, ET ELLE EST STRUCTURELLE** : `p3s3d_executer_campagne` n'est exposée par
**aucune route HTTP** — la lancer suppose donc de l'appeler à la main, et **l'endroit d'où
on l'appelle décide si le SDK existe**. `resend==2.19.0` est dans `api/requirements.txt`,
donc présent dans le conteneur ; il ne l'était pas sur le poste. Avant tout envoi réel :
**vérifier `import resend` là où le moteur va tourner.**

**Ce que le système a bien fait** — la conception a tenu exactement comme prévue :
l'échec est classé `INDETERMINE` (le SDK ne permet pas de distinguer « jamais parti » de
« parti, réponse perdue »), donc **le verrou reste posé** et rien n'est rejoué tout seul.
Aucun faux `sent`.

| Fait | Valeur vérifiée |
|---|---|
| E-mails réellement envoyés | **0** — confirmé côté **Resend** : 0 envoi vers les 3 adresses, 0 e-mail portant l'objet de campagne |
| `sent_at` / `provider_message_id` / `first_contact_sent_at` | **0 / 0 / 0** |
| Fiches `partner_prospects` | **142 × `a_contacter`** — aucune passée à `contacte` |
| Actions touchées | **3** : `BAR-01`, `BAR-02`, `BAR-03` |
| Leur état | `statut = echec_indetermine`, `verrou_actif = true`, `attempt_count = 1`, `reply_token` posé |
| 4ᵉ destinataire | **aucun** — les 52 suivants en `REPORTE / PLAFOND` |
| Drapeaux d'envoi | **refermés** (`$unset`, donc absents) — porte close, vérifiée `envoi_autorise() = False` |

⚠️ **ÉTAT À RÉGULARISER AVANT LE PROCHAIN ENVOI** : les 3 actions sont **verrouillées** et
sortent donc des exécutables (55 → 52 tant qu'elles le restent). La libération
(`p3s3d_liberer` → `statut = echec`, verrou retiré) est **une décision humaine par
conception** — le code réserve ce cas à un humain, et la preuve d'innocuité est acquise
(0 envoi côté Resend). **Ne pas libérer sans GO.**
💡 Leur `reply_token` est **conservé et réutilisable** : c'est voulu, un jeton qui changerait
entre deux tentatives rendrait orpheline toute réponse au premier envoi.

Correctif de terrain appliqué : `resend==2.19.0` **installé sur le poste**, `import resend`
vérifié, et la porte fermée refuse toujours avant tout appel (`ENVOI_NON_AUTORISE`, 0 appel).

### RÉAPPROBATION FAITE — 2026-09-03 09:15:03 UTC

Le coach a validé les 25 messages et l'arbitrage, puis la campagne a été **réapprouvée**.
**MÊME campagne, aucune seconde créée** (`prospect_campaigns` = 1). L'empreinte a été
**recalculée au moment de l'approbation** sur l'état réel, jamais recopiée d'un calcul
antérieur ; elle est ensuite vérifiée **conforme** par `p3s3d_empreinte_conforme`.

Garde réelle rejouée après approbation, sur les 137 actions :

| Verdict | Nombre |
|---|---|
| **AUTORISE** | **55** |
| `PAS_AUTO` | 81 (MANUEL 53, ASSISTÉ 19, BLOQUÉ 9) |
| `ACTION_EXCLUE` | 1 (`BAR-05`, L'Interlope) |
| `MESSAGE_VIDE`, `DEJA_CONTACTE`, `REFUS_EXPRIME`, `CIBLE_INVALIDE`, `DEJA_RESERVE`, `OBJET_ABSENT`, `STATUT_INCOMPATIBLE`, `TENTATIVES_EPUISEES` | **0 chacun** |

Vérifié en plus : aucune action exclue ne figure parmi les 55 ; `ORG-02` y est, `BAR-05` n'y est
pas ; les 55 sont toutes `AUTO` + `email` et portent toutes un `message_j0`.

**P3-R1 — les 55 sont rattachables** : pour chacune, un Reply-To individuel
`r-<jeton>@reply.afroboosteur.com` est généré, relu et redonne le même jeton (**55/55**,
en simulation pure — **aucun jeton n'a été écrit**). Confiance `A0_REPLY_TOKEN` = **100**.
⚠️ **`reply_token` est posé À L'EXÉCUTION, pas à l'approbation** : en compter 0 en base
aujourd'hui est le comportement attendu, pas un manque.

⚠️ **APPROUVER N'EST PAS ENVOYER.** Les deux drapeaux `P3_LAUNCH_ENABLED` et
`P3_LAUNCH_ENVOI_REEL` restent **absents**, `p3s3_envoi_autorise()` rend **False**.
Aucun `claim`, aucun `verrou_actif`, aucun `sent_at`, aucun e-mail. **La porte d'envoi reste
fermée et n'a pas été touchée.**

Sauvegardes d'avant chaque opération, dans `~/afroboost-sauvegardes/` :
`p3-j0-25-avant-20260903-083541.json`, `p3-arbitrage-interlope-avant-20260903-090614.json`,
`p3-avant-reapprobation-20260903-091503.json`.

### Le compte des destinataires — historique de la réconciliation du 2026-09-03

**Le chiffre du coach était juste.** Réconciliation faite en appelant la garde RÉELLE du serveur
(`p3s3d_garde_action`, fonction pure) sur les 137 actions réelles — aucune écriture, aucune
réservation, aucun envoi.

| Étape | Nombre | Ce qui filtre |
|---|---|---|
| Actions de la campagne | 137 | — |
| `execution_type == AUTO` | **56** | les 81 autres → `PAS_AUTO` (MANUEL 53, ASSISTÉ 19, BLOQUÉ 9) |
| … et `channel == email` | **56** | aucune perte : **toutes** les AUTO sont e-mail |
| … et `message_j0` non vide | **31** | les 25 autres → `MESSAGE_VIDE` |
| **Verdict de la garde : AUTORISE** | **31** | plus aucun filtre ne retire personne |
| *(après P3-J0-25, sur campagne réapprouvée)* | **56** | les 25 `MESSAGE_VIDE` ont reçu leur J0 |
| *(après l'arbitrage Case à Chocs)* | **55** | `BAR-05` mise en attente : `ACTION_EXCLUE` |

⚠️ **Le « 56 » n'a jamais été un nombre d'envois** : c'est le total AUTO+e-mail, AVANT la garde.
Le seul chiffre qui compte est celui que rend la garde : **31**.

Les **25 écartées** le sont pour une raison unique et non technique — `message_j0` vide.
Ce n'est pas un échec d'envoi, c'est l'absence de contenu : personne n'a encore écrit leur
message. Elles redeviendront envoyables le jour où leur J0 sera rédigé, sans aucune
modification de code. Catégories concernées : bar 7, ecole_danse 7, organisateur 4,
restaurant 3, commerce 2, festival 2.

Les autres portes de la garde ont toutes été vérifiées vides au même moment :
`REFUS_EXPRIME` 0 (registre STOP interrogé par canal, 0 refus applicable), `DEJA_CONTACTE` 0,
`ACTION_EXCLUE` 0, `CIBLE_INVALIDE` 0, `OBJET_ABSENT` 0 (objet de campagne présent),
`DEJA_RESERVE` 0, `STATUT_INCOMPATIBLE` 0, `TENTATIVES_EPUISEES` 0.
Empreinte de campagne **conforme**, `envoi_autorise = False`.

- **55 e-mails prêts** (31 avant P3-J0-25 ; 56 avant l'arbitrage Case à Chocs). ⚠️ **État de l'époque : non envoyés.** Ils sont **tous partis depuis** — 3 le 03/09 10:00 UTC, 52 le 03/09 10:57 UTC.
- **Porte d'envoi du J0** : à l'époque, les deux drapeaux `P3_LAUNCH_ENABLED` et
  `P3_LAUNCH_ENVOI_REEL` étaient **absents** de `feature_flags` → envoi réel impossible.
  L'absence est le cas sûr, par conception. **Aujourd'hui ils sont présents à `false`**, et
  ce sont `P3_RELANCE_ENABLED` / `P3_RELANCE_ENVOI_REEL` qui sont **absents**, donc fermés.
- **NE JAMAIS LANCER SANS GO EXPLICITE DU COACH.**

## J. ESSAI GRATUIT & RAPPELS AVANT COURS (vérifié en base 2026-09-03, 17:20 UTC)

### ✅ AUTO-PRÉSENCE DES ESSAIS — ACTIVE EN PRODUCTION (03/09, décision du coach)

**Règle métier retenue par le propriétaire : le scan QR n'est plus obligatoire.**
Un essai gratuit réservé, non annulé, non déclaré absent devient une présence
**2 h après la FIN du cours** (`AP_GRACE_MINUTES = 120` ; fin = début + `duration_minutes`,
60 min par défaut). Le scan reste possible et prioritaire.

**AUCUN CODE ÉCRIT POUR CELA.** Le moteur (phase 1) existait déjà, déployé et testé
(`test_autopresence_essai` **91/91**). L'activation a consisté à basculer **un seul champ** :

| Drapeau | Avant | Après |
|---|---|---|
| `AUTO_PRESENCE_TRIAL_ENABLED` | true | true (inchangé) |
| `AUTO_PRESENCE_TRIAL_ECRITURE_REELLE` | *(absent = false)* | **true** |

Repli : remettre ce champ à `false`. Sauvegarde des 18 drapeaux prise avant l'écriture.

⚠️ **PHASE 1 = ESSAIS SEULEMENT.** Les forfaits payants sont exclus (`pas_un_essai`) —
auto-valider consommerait une séance vendue. **La phase payante n'est PAS ouverte.**
⚠️ **L'ABSENCE EST DÉSORMAIS UNE DÉCLARATION.** Ne rien faire vaut « venu ». La route
`POST /reservations/{id}/absence` existe et n'a jamais servi.
⚠️ `AP_BORNE_ACTIVATION` reste au **26/08** : 122 réservations historiques protégées.
**Ne jamais la reculer.**

### ✅ LE FUNNEL D'ESSAI EST ALLÉ AU BOUT — pour la première fois (03/09 17:08 UTC)

Passe automatique du moteur en production, **non forcée**. Deux essais du cours du 02/09
18:30 auto-validés :

| Personne | `validation_source` | `auto_presence_at` | Écran après-essai | J+0 |
|---|---|---|---|---|
| Hélène Bourgouin (`AFR-3J5JKA`) | **`auto`** | 17:08:41 | **ouvert, 2 offres** | **delivered** — `01a0683e-845a-720b-a6c8-0d45a60e5046` |
| Yann (`AFR-R4HS8Q`) | **`auto`** | 17:08:42 | **ouvert, 2 offres** | **delivered** — `01a0683e-863e-705a-a6c1-444b12697e3b` |

Chaîne complète prouvée : **accordé → réservé → présent → écran ouvert → J+0 livré.**
Offres proposées : *PULSE x10 cours* et *Cours à l'unité*. Aucune offre interdite ne fuite
(« Membres », le T-shirt et l'essai lui-même sont écartés).

Non-débordement vérifié : **0** réservation payante auto-validée, **0** annulée, **0**
antérieure au 26/08. Exactement **2** documents portent `validation_source: "auto"` dans
toute la base. Présences validées : 15 → **17**.

📌 **PIÈGE DE CONTRÔLE.** `conv_etat` doit être appelée avec le coach résolu par
`_conv_contexte`, PAS avec l'e-mail admin : ces forfaits portent `coach_id = ""` et le
filtre est symétrique. Passer le mauvais propriétaire affiche « 0 offre » et fait croire à
une régression qui n'existe pas.

J+3 : Hélène et Yann deviendront candidats le **06/09** s'ils n'ont pas converti.
`P1_TRIAL_J3_ENVOI_REEL` reste à **false** — le moteur simulera, rien ne partira.

### ✅ RAPPELS AVANT COURS — LE DÉCLENCHEUR COOLIFY EXISTE ENFIN (RV3-B, `43b8fa57`)

**La cause était le silence, pas le refus.** `/api/cron/reservation-reminders` n'avait qu'un
seul planificateur : `vercel.json`. **Les crons de ce fichier ne s'exécutent PAS sur
Coolify.** Mesure du 03/09 : **0 réservation sur 152** ne porte `reminders_sent`, et les
deux seules traces de l'ancien champ datent du **12/08** — plus un rappel depuis 3 semaines.

RV3-B ajoute **une horloge, et rien d'autre** : `_rv3b_boucle_rappels`, tâche asyncio native
enregistrée au démarrage comme les cinq autres, qui appelle le moteur EXISTANT. Elle ne lit
aucune réservation, ne décide d'aucun envoi, ne connaît ni règles ni canaux.

- **Période = 3600 s**, soit **exactement** la largeur de la fenêtre du moteur
  (2 × `N1B2_DEMI_FENETRE_MIN`). Chaque instant appartient à une fenêtre et une seule,
  quelle que soit l'heure de démarrage du conteneur. Premier passage à **+90 s**.
- **Aucun rattrapage** : un rappel dont l'heure est passée de plus de 30 min tombe hors de
  la fenêtre `(cible − 30) < maintenant ≤ (cible + 30)`. Cette garde vit dans le moteur.
- Banc `test_rv3b_boucle_rappels` **44/44** (horloge gelée pour éprouver le rappel de 07:00
  hors de 07:00). Non-régression : RV2 96/96 · E2 73/73 · E1B 50/50 · boot 21/21.
- Déployé : `boot_id b94b4526…`, démarrage **17:14:33 UTC**, postérieur au push. 15/15 × 200.

⚠️ **Les 4 AUTRES crons de `vercel.json` sont dans le même cas** (`check-campaigns`,
`post-course-feedback`, `check-subscription-renewal`, `admin/check-expirations`) et méritent
le même examen. Certains ont déjà leur boucle, d'autres non — à vérifier un par un.

### ⛔ SECOND VERROU TOUJOURS FERMÉ — le cours réservé n'a pas ses rappels

**Vérifié en base le 03/09 à 17:20 UTC : `reminders_enabled` est TOUJOURS ABSENT sur le
cours que les gens réservent réellement.**

| Cours | id | `reminders_enabled` | Règles | Réservations |
|---|---|---|---|---|
| **Cours à l'unité** — mercredi 18:30, Bord du Lac Auvernier | `62fcac27` | **absent** | aucune | **6** |
| Afroboost Silent – Session Cardio | `64b4c975` | true | 24 h + 07:00 | 46 (**archivé**) |
| Nouveau cours | `285fadd6` | true | 24 h + 07:00 | **0** |

Le moteur exige `reminders_enabled is True`, **sans aucun repli** sur la configuration du
coach. Les règles 24 h + 07:00 existent bien dans `coach_profiles.reminder_rules`, mais
elles ne sont JAMAIS lues à l'exécution : seule la configuration **du cours** compte.

**Aucune écriture n'a eu lieu ce jour-là** : la route `PUT /coach/courses/{id}/reminders`
pose `reminders_updated_at` à chaque succès, et la trace la plus récente du parc entier
date du **17/08**. Un enregistrement réussi serait visible ; il n'y en a aucun.

👉 **À FAIRE CÔTÉ COACH** : rouvrir « Cours à l'unité » (`62fcac27`, celui qui porte les
6 réservations, PAS l'homonyme `01f3b303` ni celui qui est archivé), activer les rappels et
**vérifier que l'écran confirme l'enregistrement**. Tant que ce champ est absent, l'horloge
tourne à vide sur ce cours.

📌 **« Rappel configuré » ≠ « rappel envoyé ».** Deux verrous indépendants : le déclencheur
(désormais ouvert) et l'activation par cours (toujours fermée sur le bon cours).

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
  continuaient » — est levé.
- **Nombre de destinataires : 55** — 56 après P3-J0-25, moins `BAR-05` mise en attente par arbitrage du coach.
- ✅ **P3-LAUNCH-137 — LE J0 EST TERMINÉ** : 55/55 partis le 03/09, 0 action encore autorisée.
  Les drapeaux d'envoi sont **refermés** (absents). **NE JAMAIS LES ROUVRIR SANS GO ÉCRIT.**
- 🔴 **À trancher : `contact@case-a-chocs.ch` a rebondi en PERMANENT.** L'arbitrage avait
  retenu cette adresse contre `interlope@case-a-chocs.ch` (`BAR-05`, `exclu`, jamais
  contactée). La Case à Chocs n'a rien reçu ; `BAR-05` est la seule voie e-mail restante.
- ✅ **J+3 / J+7 : moteur (P3-R2) + textes (P3-R3) prêts et approuvés.** Simulation :
  **50 relances** partiraient au 06/09 (état du 03/09 16:03 UTC). **Les drapeaux restent
  fermés** — aucune relance n'est partie, et les ouvrir demande un GO écrit distinct.
- 📬 **Deux réponses reçues**, rattachées par jeton à confiance 100, relances annulées
  automatiquement : SalsaRica (`ZRH-D5`, REFUS) et ACD Lausanne (`LSN-A3`, **POSITIVE** —
  un contact et un numéro transmis).
- ✅ **P3-R4 terminé** : les deux réponses ont leur corps réel, récupéré chez Resend.
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

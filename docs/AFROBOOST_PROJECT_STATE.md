# AFROBOOST — ÉTAT PROJET (mémoire opérationnelle persistante)

> Source de vérité opérationnelle. **Documentation uniquement — aucun code, aucun secret.**
> Ne stocke que `présent = oui/non`, `configuré = oui/non`, des noms de variables, des SHA et des compteurs.
> Pour tout sujet **production**, la **preuve runtime** prime sur toute vue UI / onglet / rapport ancien.

Dernière réconciliation runtime vérifiée : **2026-09-02, 11:15 UTC**.

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

## Git / déploiement (vérifié 2026-09-02 11:15 UTC)

- `origin/main` = **9972d48a** — « GOOGLE-2 : un rendez-vous convenu part enfin dans l'agenda du coach »
- Dernier déploiement Coolify = **Success**, commit **9972d48**, 09:13:25 → 09:18:04 UTC
- Uptime conteneur cohérent avec ce démarrage — **la prod EXÉCUTE bien GOOGLE-2**

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

## G. GOOGLE-2 — DÉPLOYÉ EN PRODUCTION, ÉCRITURE EN ATTENTE DE SCOPE

- Code GOOGLE-2 = commit **9972d48a**, **déployé** (Coolify Success 09:13→09:18 UTC le 02/09)
- **Preuve runtime** (403 = route existe et protégée ; 405 = route inexistante) :

  | Route | Réponse sans jeton |
  |---|---|
  | `POST /api/calendar-events/{id}/google-sync` | **403** |
  | `POST /api/calendar-events/{id}/google-retry` | **403** |
  | `DELETE /api/calendar-events/{id}/google-sync` | **403** |
  | `POST /api/calendar-events/{id}/controle-inexistant` (contrôle) | 405 |

- État des droits d'écriture : **`calendar_write_granted = false`**, **`reconnect_required_for_sync = true`**
- **Seul point manquant** : les jetons stockés ne portent pas `calendar.events`.
  Ce n'est ni un bug, ni une régression, ni un problème de secret.
- Cause identifiée : le consentement du 02/09 09:19 UTC accordait bien `calendar.events`, mais le `state`
  OAuth avait expiré (fenêtre 900 s dépassée) avant le traitement du callback ; l'échange du code a donc
  été refusé et les jetons de lecture d'origine sont restés inchangés.
- **Action nécessaire** : un nouveau consentement OAuth avec `calendar.events`, cliqué **dans les 15 minutes**
  suivant la génération du lien. Rien d'autre.
- **NE JAMAIS conclure « secret absent »** sans avoir vérifié le runtime réel (cf. pièges de méthode).

## E. CALENDRIER

- **CAL-1 = VERT ; CAL-2 = VERT ; CAL-3 = VERT**
- Un seul calendrier Afroboost ; `calendar_events` = **collection centrale**
- Tâches natives + rendez-vous prospects dans le même calendrier et le même moteur
- Bouton « Planifier » (depuis une fiche prospect) fonctionnel
- **Afroboost = source de vérité** ; Google est une destination, jamais l'inverse

## D. RESEND

- **Receiving configuré** ; `email.sent` **actif** ; `email.received` **actif** (webhook signé Svix — lot P3-U3)
- **Reply-To commercial actuel : `contact@afroboosteur.com`** — seule source canonique
  (`AFROBOOST_REPLY_TO` et `AFROBOOST_REPLY_TO_RAPPELS` convergent dessus)
- Expéditeur (FROM) : `Afroboost <notifications@afroboost.com>`
- ⚠️ `contact@afroboost.ch` est une **adresse morte** (domaine sans MX) : refusée par le code, ne pas la reposer
- **DNS déjà configuré — NE PAS recommencer la configuration DNS**

## C. P3 — PROSPECTION PARTENAIRES (vérifié en base 2026-09-02)

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
| GOOGLE-2 | `9972d48a` | **déployé (prod actuelle)** | Routes actives ; écriture en attente du scope `calendar.events` |

---

# DETTES / PROCHAINES ÉTAPES

- **GOOGLE-2** : un seul geste manquant — nouveau consentement OAuth avec `calendar.events`,
  cliqué dans les 15 min. Puis vérifier `calendar_write_granted = true`, tester la sync d'un événement,
  le `google_event_id` et l'anti-doublon.
- **P3-LAUNCH-137** : campagne prête, envoi bloqué par les deux drapeaux absents.
  N'ouvrir qu'après GO explicite écrit du coach.
- Dettes antérieures (non bloquantes) : cf. `CLAUDE.md` et l'historique des lots.

---

# MISE À JOUR DE CE FICHIER

À la fin de chaque lot réellement validé, mettre à jour **uniquement les faits qui changent** :
commit, état production, fonctionnalités prouvées, compteurs critiques, dettes restantes, prochain lot autorisé.
Ne pas réécrire l'ensemble. **Toujours distinguer ÉTAT ACTUEL et HISTORIQUE** : une situation passée
ne doit jamais être présentée comme l'état courant.

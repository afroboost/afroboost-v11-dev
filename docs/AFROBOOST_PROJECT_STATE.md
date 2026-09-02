# AFROBOOST — ÉTAT PROJET (mémoire opérationnelle persistante)

> Source de vérité opérationnelle. **Documentation uniquement — aucun code, aucun secret.**
> Ne stocke que `présent = oui/non`, `configuré = oui/non`, des noms de variables, des SHA et des compteurs.
> Pour tout sujet **production**, la **preuve runtime** prime sur toute vue UI/onglet/rapport ancien.

Dernière réconciliation runtime vérifiée : **2026-09-02**.

---

## RÈGLE DE RÉCONCILIATION (ordre de confiance)
1. runtime production fonctionnel (conteneur en cours)
2. base de données actuelle
3. git HEAD / origin/main / commit déployé
4. ce fichier (AFROBOOST_PROJECT_STATE.md)
5. ancienne conversation / ancien onglet Chrome / modal resté ouvert / vue Coolify périmée

En cas de contradiction : **RÉCONCILIER AVANT D'AGIR**. Ne jamais contredire un état déjà prouvé
en production sur la seule foi d'un ancien onglet, d'un modal, ou d'une liste UI Coolify (variables
Shared/héritées n'apparaissent PAS comme lignes éditables mais SONT injectées au runtime).

Avant chaque lot / diagnostic / déploiement : (1) lire ce fichier ; (2) vérifier HEAD/origin/main ;
(3) si sujet production, vérifier le runtime réel du conteneur.

---

# ÉTAT ACTUEL

## A. ARCHITECTURE
- Application principale : **afroboost-v11-dev**
- Domaine : **https://afroboost.com**
- Repo : **afroboost/afroboost-v11-dev** — branche **main**
- Base de données : Mongo, DB name = **promo-credits-lab** (collection centrale calendrier = `calendar_events`)
- Coolify : projet **afroboost.com** > app **afroboost-v11-dev** (Build Pack Dockerfile, code sous `/app/api`)
- NE PAS CONFONDRE avec **afroboosteur-site** (projet « Afroboost ») qui sert **afroboosteur.com** (≠ afroboost.com)

## Git / déploiement (vérifié 2026-09-02)
- HEAD local = origin/main = **9972d48a** (GOOGLE-2)
- Commit **déployé en production** = **521cfe19** (GOOGLE-1)
- => **main est en avance sur la prod d'un commit (GOOGLE-2 non déployé).**

## Runtime container (vérifié, présence uniquement, aucune valeur)
- `GOOGLE_CONTACTS_CLIENT_ID` present = **oui**
- `GOOGLE_CONTACTS_CLIENT_SECRET` present = **oui**
- `META_APP_SECRET`, `RESEND_*`, `STRIPE_*`, `TWILIO_*`, `MONGO_URL`, `DB_NAME` = présents
- configured = **true** ; connected = **true**

## F. GOOGLE-1 — VALIDÉ EN PRODUCTION
- OAuth Google fonctionnel ; Google Calendar **lecture réelle** prouvée
- Événement Google (ex. MENAGE) affiché dans Afroboost ; suppression Google reflétée dans Afroboost
- Événements Google lus à la volée (non persistés inutilement)
- Google Contacts lecture active
- `google_tokens` : count = **1**, tokens **chiffrés = oui**, refresh_token **présent = oui**
- Scopes actuels du token : `calendar.readonly` + `contacts.readonly` (LECTURE seule)

## G. GOOGLE-2 — CODE PRÊT, NON DÉPLOYÉ
- Code GOOGLE-2 = commit **9972d48a** sur main + poussé, **NON déployé** (prod = 521cfe19)
- Code déployé (521cfe19) demande déjà le scope `calendar.events` et gère les drapeaux
  `calendar_write_granted` / `reconnect_required_for_sync` (dans `/app/api/server.py`)
- État actuel : **calendar_write_granted = false**, **reconnect_required_for_sync = true**
- Pour activer l'écriture Google réelle il faut LES DEUX :
  1. redéployer la prod sur 9972d48a (logique d'écriture « rendez-vous -> agenda coach »)
  2. nouveau consentement OAuth accordant `calendar.events` (le token courant n'a que la lecture)
- Écriture Google nécessite `calendar.events`. Vérifier les tokens avant chaque reconnexion.
- NE JAMAIS conclure « secret absent » sans vérifier le runtime réel du conteneur.

## E. CALENDRIER
- CAL-1 = VERT ; CAL-2 = VERT ; CAL-3 = VERT
- Un seul calendrier Afroboost ; `calendar_events` = collection centrale
- Tâches natives + rendez-vous prospects ; bouton « Planifier » fonctionnel
- Afroboost = source de vérité

## D. RESEND
- Receiving configuré ; `email.sent` actif ; `email.received` actif
- Reply-To commercial actuel en place ; DNS **déjà configuré** — NE PAS recommencer la config DNS
- Réf. lot : P3-U3 (e7b69c79)

## C. P3 (déclaré, à re-confirmer runtime avant toute action d'envoi)
- Campagne **P3-LAUNCH-137** : actions = 137 ; prospects = 142 ; contacte = 0 ; sent = 0
- 31 emails prêts mais **NON envoyés** — ne JAMAIS lancer sans GO explicite
- inbound / snapshot_hash : selon dernier état vérifié (non re-vérifié ce jour)

## B. P2
- P2 terminé — ne pas modifier sauf blocage réel

## H. GOOGLE CLOUD
- Projet dédié : **Afroboost Production** ; client OAuth dédié : **Afroboost Production**
  (ID public commence par `1087423218147-9e10…`)
- Redirect URIs (ne pas toucher) : `https://afroboost.com/api/google/callback`,
  `https://afroboost.com/api/google-contacts/callback`
- NE PAS toucher : Studiio Pro, client Firebase
- Compte test : **bassicustomshoes@gmail.com**

## I. COOLIFY
- Bonne app : **afroboost-v11-dev** (sert afroboost.com)
- Piège : **afroboosteur-site** sert afroboosteur.com — ne pas y écrire les variables Google

---

# HISTORIQUE DES LOTS (SHA vérifiés dans git)

| LOT | COMMIT | PROD | VERDICT |
|------|----------|------|---------|
| CAL-1 | f6c24435 | déployé | VERT |
| CAL-2 | 1b9f3492 | déployé | VERT |
| CAL-3 | de0f8997 | déployé | VERT |
| GOOGLE-1 | 521cfe19 | **DÉPLOYÉ (prod actuel)** | VERT (lecture prouvée) |
| GOOGLE-2 | 9972d48a | **NON déployé (main seulement)** | code prêt ; redeploy + consentement `calendar.events` requis |

---

# DETTES / PROCHAINES ÉTAPES
- GOOGLE-2 : (1) redéployer prod -> 9972d48a ; (2) nouveau consentement OAuth avec `calendar.events`
  pour bassicustomshoes@gmail.com ; puis test sync 1 événement / `google_event_id` / anti-doublon.
- P3-LAUNCH-137 : 31 emails prêts, envoi bloqué jusqu'à GO explicite.

# MISE À JOUR
À la fin de chaque lot réellement validé : mettre à jour uniquement les faits qui changent
(commit, état prod, fonctionnalités prouvées, compteurs, dettes, prochain lot autorisé).
Distinguer toujours ÉTAT ACTUEL vs HISTORIQUE.

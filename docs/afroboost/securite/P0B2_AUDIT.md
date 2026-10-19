# P0-B2 — Audit d'usage des 6 routes reportées (19/10/2026, avant modification)

Lecture seule : code `82b5d46e`, base de production (comptes, sans valeurs personnelles).

| # | ROUTE | MÉTHODE | APPELANT | QUI | DONNÉES MODIFIÉES | IDENTITÉ DISPONIBLE À L'APPEL | PROTECTION ACTUELLE | RISQUE RÉEL | POURQUOI PUBLIQUE | CORRECTION SÛRE | RISQUE DE CASSER |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `/chat/messages/{id}/delete` | PUT | `ChatWidget.js:7439` (bulle de message, visiteur ET mode coach) ; `CRMSection.js:1440` (dashboard) | visiteur anonyme, abonné, coach | `chat_messages.is_deleted` | coach : JWT (intercepteur) ; visiteur : `participantId` (UUID, localStorage) — **non envoyé aujourd'hui** ; abonné : jeton d'appareil V296 | **aucune** | n'importe qui supprime n'importe quel message par son id (y compris ceux du coach) | historique (v153) | coach : JWT + propriété de la conversation ; visiteur : son `participant_id` = `sender_id` du message ET membre de la conversation 1-à-1 (mécanisme V349 déjà utilisé pour LIRE) ; en **groupe/communauté** les `sender_id` sont visibles de tous → preuve exigée = jeton abonné V296 (ou coach) | faible : le widget doit envoyer `participant_id` (1 ligne) ; un visiteur ne pourra plus supprimer un message qui n'est pas le sien (voulu) |
| 2 | `/chat/sessions` | POST | `CoachDashboard.js:4472` (chat communauté), `CRMSection.js:1403` | coach | crée une `chat_sessions` (sans `coach_id`) | JWT coach | **aucune** | création massive de conversations par n'importe qui | historique | JWT coach + `coach_id` = appelant | nul (aucun appelant visiteur ; les visiteurs créent leur conversation par `/chat/smart-entry`, non touché) |
| 3 | `/chat/sessions/{id}/add-participant` | POST | **aucun** | — | `chat_sessions.participant_ids` | — | **aucune** | ajouter n'importe qui dans une conversation étrangère (puis lire ses messages, V349) | historique | JWT coach + propriété de la conversation | nul |
| 4 | `/notifications/mark-read` | PUT | `CoachDashboard.js:5329` (polling des notifications) | coach | `chat_messages.notified` (y compris « tous les messages » via `all_for_target`) | JWT coach | **aucune** | effacer les notifications de n'importe quel coach / de toute la plateforme | historique | JWT coach + seulement les messages de SES conversations (super-admin : tous) | nul (seul appelant : le dashboard, déjà authentifié) |
| 5 | `/cron/reservation-reminders` | GET | **aucun appel HTTP réel** : `vercel.json` (cron Vercel, ne tourne plus) ; la boucle interne **RV3-B** (`_rv3b_boucle_rappels`) appelle la **fonction Python directement**, toutes les heures | tâche interne | `reservations.reminders_sent` + **envoi d'e-mails / push de rappel** | aucune (interne) | **aucune** | n'importe qui peut déclencher une passe d'envoi de rappels (anti-doublon limite les dégâts) | ancien cron Vercel | la boucle garde l'appel direct (intacte) ; la route HTTP exige `Bearer CRON_SECRET` ou un JWT super-admin (même règle que `/cron/check-campaigns`, V329/V330) | nul pour la boucle ; l'HTTP n'a pas d'appelant |
| 6 | `/webhooks/twilio/status` | POST | Twilio (externe) | webhook | `campaigns.results.$` (statuts de remise) | aucune | **aucune signature vérifiée** | statuts de campagne falsifiables | ancien canal | **inutilisé** : envois WhatsApp via Meta (`META_*`, priorité 1), identifiants Twilio en base **vides**, 5 campagnes récentes = identifiants Meta `wamid`, aucun `StatusCallback` dans le code → **410 Gone**, sauf si `TWILIO_AUTH_TOKEN` est posé : alors signature `X-Twilio-Signature` exigée (403 sinon) | nul |

## Corrections appliquées (P0-B2)

| Route | Après P0-B2 |
|---|---|
| PUT `/chat/messages/{id}/delete` | auteur visiteur (`participant_id` = `sender_id`, membre, conversation 1-à-1) ; en groupe : jeton abonné de l'auteur ; coach propriétaire / super-admin signés. Sinon 404. Front : `ChatWidget` envoie `participant_id`. |
| POST `/chat/sessions` | coach signé ; `coach_id` = appelant. |
| POST `/chat/sessions/{id}/add-participant` | coach signé propriétaire (super-admin : toutes), 404 sinon. |
| PUT `/notifications/mark-read` | coach signé ; seulement les messages de SES conversations ; 500 ids max. |
| GET `/cron/reservation-reminders` | `Bearer CRON_SECRET` ou super-admin signé (401 sinon). La boucle RV3-B appelle toujours le moteur directement. |
| POST `/webhooks/twilio/status` | 410 Gone (désactivé, inutilisé). |

Tests : `tests/test_p0b2_routes_reportees.py` 58/58 (43 échecs sur l'ancien code).

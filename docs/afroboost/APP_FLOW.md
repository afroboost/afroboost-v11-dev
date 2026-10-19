# APP FLOW — Parcours Afroboost (site complet)

> Parcours réels d'**afroboost.com** au 19/10/2026 (code `0a575c9b`), établis depuis le code ; les éléments « cible »
> sont signalés comme tels. Afroboost n'a **pas de routeur** : `App.js` choisit l'écran selon le chemin, le hash et les
> paramètres (ordre de priorité ci-dessous).

## 0. Règles transverses

### 0.1 Résolution de l'écran (premier qui correspond)
1. Modale de connexion coach · 2. `#become-coach` (devenir partenaire) · 3. média partagé `/v/<slug>` · 4. `/rdv/<jeton>`
(rendez-vous partenaire) · 5. `/parrainage` · 6. `/i/<jeton>` (invitation) · 7. `/duo/c/<jeton>` puis `/duo/<jeton>` (Pass Duo)
· 8. `/espace/<CODE>` (espace membre) · 9. panneau Super Admin · 10. maintenance (sauf super-admin) · 11. dashboard coach
· 12. vitrine. Liens profonds : `?offre=<id>[&reserver=1]`, `?qr=AFR-…` (redirigé vers `/espace` avant React),
`?visitor=true`, `/partner/<slug>`, `?prospection=1&inbound=<id>`, retours de paiement (`?status=success|canceled`, `session_id`).

### 0.2 États communs
| Situation | Comportement réel |
|---|---|
| Session coach expirée | intercepteur axios (401 marqué ou JWT expiré) → `terminerSession()` → message « Votre session a expiré » + formulaire de connexion, sans recharger |
| Session membre expirée | identification e-mail → code OTP 6 chiffres ; lien magique expiré → état « lien expiré » avec renvoi |
| Bouton retour | géré (`popstate`) pour `/espace`, `/parrainage`, `/i`, `/duo`, `/partner` ; les modales ne créent pas d'entrée d'historique → retour = quitter la page (dette) |
| Hors ligne | pas d'écran dédié ; le polling se suspend ; le service worker sert `index.html` en cache |
| Erreur de section | `SectionErreur` (« Réessayer ») sur 5 écrans ; ailleurs `alert()` (158 occurrences) |
| Démarrage bloqué | après 5 s sans rendu React : purge SW/caches automatique + lien `/reset.html` |
| Permissions refusées (serveur) | 401/403 → message ; côté Live, refus `subscription_required` / `no_credit` |
| État vide | messages dédiés dans la plupart des listes (ex. « Aucune réponse n'a encore été préparée ») |

---

## 1. VISITEUR — accueil → cours → réservation → paiement → confirmation
| Étape | Déclencheur | Validation | Chargement | Succès | Erreur | Écran suivant |
|---|---|---|---|---|---|---|
| Accueil | URL `/` | — | rendu immédiat (couleurs sans flash) | hero, publications, offres « aimants », événements | API indisponible → sections vides | choix d'une offre / d'un cours |
| Choix du cours / date | clic sur un cours, une date (`SessionsModal`) | date future, occurrence non annulée | — | date sélectionnée | — | choix de l'offre |
| Choix de l'offre | clic carte offre (ou `?offre=`) | offre visible, en saison, en stock, non expirée (serveur) | — | formulaire | offre introuvable → retour aux offres | formulaire |
| Formulaire | saisie nom, e-mail, WhatsApp, date de naissance (+ adresse/variantes si produit, code promo, quantité) | champs requis, code promo vérifié côté serveur (vert/rouge) | « Vérification… » | total recalculé (avantage membre éventuel) | code invalide → message rouge | conditions de participation |
| Conditions | case à cocher | obligatoire | — | bouton « Réserver » actif | — | paiement ou gratuit |
| Paiement | « Réserver » → e-mail confirmé → `POST /create-checkout-session` ; choix intégral / 2 fois si proposé | prix **recalculé serveur** | redirection Stripe | retour `?status=success` → ticket + nettoyage URL | `?status=canceled` → message, panier conservé | confirmation |
| Gratuit (0 CHF) | `POST /checkout/free` | éligibilité serveur (essai unique, invitation) | — | confirmation | refus neutre `not_eligible` | confirmation |
| Confirmation | webhook Stripe → code + séances + e-mail | idempotence | overlay « paiement en cours » | `SuccessOverlay` : code, QR, lien espace | webhook en retard → message d'attente | espace membre / partage |

## 2. ESSAI GRATUIT — invitation → séance → coordonnées → inviter un ami → confirmation
| Étape | Déclencheur | Validation | Succès | Erreur | Suivant |
|---|---|---|---|---|---|
| Ouvrir l'invitation | lien `/i/<jeton>` ou `/duo/<jeton>` | jeton valide, campagne active | page courte : vidéo/audio, séance, prix 0 | jeton inconnu/expiré → « Invitation introuvable » + accès vitrine | choix de séance |
| Choisir la séance | clic séance (changeable) | séance future, places | séance retenue | complet → autre date | coordonnées |
| Coordonnées | prénom, e-mail, téléphone | téléphone obligatoire ; garde essai unique (téléphone, déjà client, essai déjà pris) | essai accordé | refus neutre | inviter un ami |
| Inviter un ami (Pass Duo) | « Viens avec un ami » → partage WhatsApp / lien | lien personnel signé | invitation créée | — | confirmation |
| Confirmation | — | — | « Ta place est réservée », audio d'accueil, accès espace | — | espace membre (`AccesEspaceMembre`) |
| Relances | J0 / J+3 / essai non réservé (si drapeaux actifs) | registre STOP, quota | e-mail | — | — |
Cas : réouverture sur un autre appareil avant confirmation → continue avec la clé de l'appareil ; après confirmation → « Ta place est déjà réservée ».

## 3. MEMBRE — lien sécurisé → espace → choisir une séance → réserver → QR
| Étape | Déclencheur | Validation | Chargement | Succès | Erreur | Suivant |
|---|---|---|---|---|---|---|
| Entrer | lien `/espace/<CODE>`, `?qr=`, e-mail « accès » (lien magique 24 h), PWA (retour auto) | session d'espace vivante (`subscriber_sessions`) sinon OTP | « Chargement… » | tableau de bord membre | lien expiré → renvoi OTP | menu rapide |
| Identification | e-mail → code 6 chiffres | 10 min, 5 essais, 3 demandes / 10 min | envoi | session 30 j (renouvelée à J-7) | code faux → message ; trop d'essais → 429 | espace |
| Voir ses droits | ouverture | abonnement actuel (résolveur unique) | — | séances restantes, expiration, échéances | aucun abonnement actif → offres de recharge | réserver / recharger |
| Réserver | clic séance (agenda) | séances > 0, éligibilité, conditions | « Réservation… » | séance débitée, carte événement conservée | plus de séance → « Recharger » | QR / inviter |
| Annuler | « Annuler » | délai, propriétaire | — | séance restituée (une fois) | — | espace |
| QR | « Mon QR » | — | plein écran | — | — | scan au cours |
| Recharger | « Recharger » | catalogue serveur | Stripe | nouvelle séance(s) | annulation Stripe → message | espace |
| Inviter | « Inviter » → `/parrainage` | — | — | lien personnel | — | partage |
| Progression, créateur, notifications, profil Spordateur | menu rapide | — | — | — | — | — |

## 4. ÉVÉNEMENT — invitation → tarif → avantage membre → paiement/réservation → confirmation → partage
| Étape | Déclencheur | Validation | Succès | Erreur | Suivant |
|---|---|---|---|---|---|
| Page événement | lien d'invitation (`event_paid`/`event_free`), `?offre=` | événement publié (pas brouillon/masqué) | vidéo, promesse, date, **prix du palier actuel**, places restantes (si capacité réelle) | archivé → message | « Je réserve ma place — <prix> » |
| Membre ? | « Je suis membre » | lien d'accès membre (une étape) | avantage appliqué (gratuit / % / prix fixe réglé par le coach) | non éligible → tarif normal | paiement / place offerte |
| Paiement | Stripe | prix serveur, palier figé à la création du checkout | billet + réservation automatique | complet → refus | confirmation |
| Confirmation + partage | — | — | « Viens avec tes amis », partage, « Plus tard » | — | espace / vitrine |

## 5. COACH (super-admin) — connexion → clients → abonnement → réservation → événements → invitation → prospection
| Étape | Déclencheur | Validation | Succès | Erreur | Suivant |
|---|---|---|---|---|---|
| Connexion | `#coach-dashboard` / modale | `/auth/login` (bcrypt) → JWT 7 j | dashboard (onglet Réservations par défaut) | identifiants faux → message | onglets |
| Réservations | onglet | JWT + propriété | liste paginée, rappels par cours, scanner QR | — | scan / détail |
| Codes / clients | onglets Codes, Contacts | JWT strict | créer/modifier/remplacer un abonnement (anti-doublon, avertissement si déjà actif), suivi de paiement, rappels | doublon → choix Modifier / Remplacer | fiche contact |
| Gestion | onglet Gestion → sous-cartes | — | offres (wizard), cours, vitrine (couleurs), hero, paiements, adhésions, WhatsApp, funnel essai | — | — |
| Événements / invitations | Campagnes → Invitation & Parrainage | — | créer, modifier (409 « confirmation requise » si impact), publier, masquer, dupliquer | — | partage |
| Campagnes clients | Campagnes → Clients | quota, STOP | campagne e-mail / WhatsApp / push programmée | erreurs → `campaign_errors` | suivi |
| Prospection | Campagnes → Prospection | — | 7 sous-vues (voir §7) | — | — |
| Super Admin | menu « Actions du compte » | super-admin signé | partenaires, packs, cockpit, analytics, maintenance, saison, drapeaux | — | — |

## 6. PARTENAIRE — lien → espace partenaire → activité
| Étape | Déclencheur | Validation | Succès | Erreur | Suivant |
|---|---|---|---|---|---|
| Devenir partenaire | `#become-coach` | choix d'un pack, paiement Stripe ou inscription gratuite | compte en attente de validation | — | validation super-admin |
| Connexion | `#partner-dashboard` | JWT | dashboard (onglets communs + Boutique, Mon Stripe, Créateur) | — | — |
| Vitrine | `/partner/<slug>` | slug actif | vitrine du partenaire | slug du super-admin → redirigé vers `/?visitor=true` | réservation |
| Prospect → partenaire | candidature `/partner-applications/<jeton>` | décision du coach | fiche `partners` | — | — |

## 7. PROSPECTION — prospect → J0 → relance → réponse → IA → réponse coach → traité
| Étape | Déclencheur | Validation | Chargement | Succès | Erreur | Suivant |
|---|---|---|---|---|---|---|
| Fiche prospect | import / création | anti-doublon (nom normalisé, e-mail, téléphone, domaine, Instagram) | — | fiche + niche | doublon signalé | campagne |
| Préparer J0 | « Préparer » (simulation puis réel) | ciblage, langue, canal | aperçu 137 destinataires | actions `prepared` | — | approbation |
| Approuver | « Approuver » | empreinte figée | — | campagne approuvée | texte modifié après approbation → refus | envoi (drapeaux) |
| J+3 / J+7 / J+14 | boucle horaire (semaine 8h-18h) | J0 remis, pas de réponse, pas de STOP, relances validées | — | e-mail suivi (remis/rebond) | rebond → arrêt | réponse |
| Réponse reçue | e-mail entrant (Resend) | rattachement par jeton de réponse | — | conversation « À répondre », notification push | non rattachée → revue manuelle | ouvrir |
| Ouvrir la conversation | clic | — | — | **fil complet** (J0→J+14, réponses, reçus), marqué lu | — | générer / écrire |
| Générer avec l'IA | « Générer » / « Régénérer » | fil + faits du code + garde-fous ; **AI_REPLY_CHECK** avant affichage | « Analyse en cours… » (≈ 10 s) | brouillon court + motifs de validation éventuels | modèle indisponible → message, composer manuel disponible | modifier / valider |
| Modifier + média | « Modifier », « Ajouter un média » | référence de média résolue serveur | — | carte « VIDÉO JOINTE » | fichier refusé → message | valider |
| Valider et envoyer | « Valider et envoyer » | aperçu **serveur** (destinataire, objet, texte, média, e-mail exact) | — | écran de confirmation | contexte changé / champ « [À COMPLÉTER] » → 409 | « Confirmer l'envoi » |
| Confirmer | « Confirmer l'envoi » | empreinte, drapeaux, STOP, idempotence | « Envoi… » | « soumise à Resend » → remise suivie | échec → « Réessayer » si rien n'est parti | conversation suivante |
| Traité | « Marquer comme traité » | réversible | — | sort de la file | — | — |

## 8. LIVE — accès → salle → permissions → session → crédits → sortie
(Détail : `modules/live/LIVE_AUDIT.md`.)
| Étape | Déclencheur | Validation (réelle) | Chargement | Succès | Erreur | Suivant |
|---|---|---|---|---|---|---|
| Accès | bouton « Live » (barre) ou modale Publier | `POST /boosttribe/access` : super-admin, sinon code abonné avec séances > 0 | overlay plein écran | jeton 15 min + iframe `/live/embed` (+ `bt_session` si Live en cours) | `subscription_required` / `no_credit` → message ; pas d'identité → ouverture du chat | salle |
| Vérification BT | chargement de l'iframe | `/api/embed/verify` (jeton signé) → compte + accès 12 h | « Connexion… » | connecté | jeton expiré / sans e-mail → refus | hub ou session |
| Rejoindre | code de session / lien | mode d'accès (open, payant, privé), pseudo | — | dans la salle | salle d'attente (privé) | permissions |
| Permissions navigateur | caméra / micro | autorisation du navigateur | — | flux actifs | **refus caméra/micro → le participant reste en écoute** ; navigateur incompatible (pas de WebRTC) → message | session |
| Session | Live | rôles : hôte, co-hôte, scène (serveur), spectateur | — | vidéo, musique synchro, chat, réactions, main levée | connexion perdue → reconnexion LiveKit/PeerJS automatique | fin |
| Crédits | démarrage réel | `session-started` (navigateur) → `/boosttribe/consume` (1 séance, idempotent `jti`) | — | `afroboost:credit-refresh` | Afroboost injoignable → **non débité** (faille) | — |
| Sortie | « Quitter » / fermeture overlay (hôte : « Terminer ») | — | — | `bt:session-ended` → « Live » redevient disponible | — | vitrine / espace |

### 8.1 Cible (non construite) — crédits et fonctionnalités par utilisateur
**Admin** : Dashboard → Utilisateurs → ouvrir → Créditer (+/− avec motif) → cocher les fonctionnalités → Enregistrer.
| Action | Validation serveur | Succès | Erreur |
|---|---|---|---|
| Créditer / retirer | super-admin signé, montant entier ≠ 0, motif requis | nouvelle ligne de journal + audit, solde recalculé | solde négatif interdit → 409 |
| Cocher une fonctionnalité | super-admin signé, fonctionnalité connue | droit enregistré + audit | — |
| Enregistrer | — | toast « Enregistré » | session expirée → reconnexion |
**Utilisateur** : connexion → dashboard → voir crédits → voir fonctionnalités disponibles (grisées sinon) → lancer Live → consommation → fin → historique.
| Cas | Comportement attendu |
|---|---|
| Crédits insuffisants | refus **serveur** avant toute ressource (« Il te reste 0 crédit », lien recharger) |
| Fonctionnalité non autorisée | bouton masqué ou grisé + refus serveur 403 si appel forcé |
| Session expirée en plein Live | le Live continue jusqu'à expiration du jeton LiveKit ; nouvelle action payante → reconnexion |
| Connexion perdue | reprise automatique ; aucun double débit (idempotence) |

**Participant** : lien → rejoindre → permissions caméra/micro → Live → quitter (aucun crédit si invité gratuit, selon décision).

## 9. MEMBRE / VISITEUR — chat
Bulle → visiteur : prénom + WhatsApp (lead), réponses rapides, FAQ IA multilingue ; abonné reconnu : réservations, QR, groupes, messages privés ; coach : sessions, transactions, éditeur de bot (JWT exigé). Erreur réseau → nouvelle tentative ; session expirée → message dans la conversation.

## 10. Parcours manquants ou fragiles (à traiter)
1. Retour arrière dans les modales de réservation (quitte la page).
2. Pas d'écran hors ligne.
3. Abonné sans e-mail : ne peut pas entrer dans le Live.
4. Partenaire : parcours d'activité incomplet (mono-coach assumé).
5. Erreurs signalées par `alert()` au lieu d'un retour intégré.

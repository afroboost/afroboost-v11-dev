# PRD — Afroboost (produit complet)

> Document produit global d'**afroboost.com**, établi le 19/10/2026 à partir du **code et de la base de production réels**
> (lecture seule). Afroboost Live / BoostTribe y figure comme **module** ; son détail est dans
> [`modules/live/LIVE_AUDIT.md`](modules/live/LIVE_AUDIT.md). Les priorités P0/P1/P2 décrivent l'importance produit d'une
> fonctionnalité **existante ou souhaitée** ; elles ne sont pas un planning (voir `IMPLEMENTATION_PLAN.md`).
> Aucun KPI chiffré n'est inventé : les cibles chiffrées sont à fixer par Bassi.

---

## 1. Afroboost — Vision produit

**Afroboost est une plateforme de cardio-danse afro (en salle, en extérieur, en version Silent avec casques et en Live
vidéo) qui permet à Coach Bassi et à ses partenaires de remplir leurs cours, de fidéliser leurs membres et de développer
leur communauté par l'invitation, en gérant réservations, abonnements, paiements, prospection et Live au même endroit.**

Le problème résolu : un coach indépendant jongle aujourd'hui entre WhatsApp, Excel, Stripe, Instagram, des liens de
paiement et des feuilles de présence. Afroboost réunit l'expérience du participant (découvrir, essayer, réserver,
payer, venir, inviter) et l'outil du coach (cours, offres, membres, présences, campagnes, partenaires, analytics).

## 2. Utilisateurs cibles

| Utilisateur | Besoins | Problèmes | Objectifs |
|---|---|---|---|
| **Visiteur** | comprendre le concept, voir horaires/lieux/prix, essayer | ne sait pas si c'est pour lui (niveau, ambiance, casque) | réserver un essai ou un cours en quelques gestes |
| **Participant** (invité, essai) | arriver au bon endroit, au bon moment, avec son ami | lien d'invitation, date, conditions | vivre la 1re séance et revenir |
| **Membre** (abonné, carte, adhésion) | réserver, voir ses séances restantes, son QR, inviter | code à retrouver, expiration, paiement fractionné | s'entraîner régulièrement sans friction |
| **Coach** (Bassi, super-admin) | remplir les cours, encaisser, suivre les membres, prospecter | outils dispersés, saisie manuelle, erreurs de données | développer l'activité sans perdre de temps |
| **Partenaire / coach partenaire** | vendre ses propres cours/offres sous Afroboost | autonomie, paiements, visibilité | une vitrine et un dashboard à lui, données cloisonnées |
| **Organisateur** (festival, école, entreprise, association) | une animation clé en main | comprendre l'offre, prix, logistique | réserver une intervention ou un événement |
| **Admin** | modérer, configurer | — | (aujourd'hui confondu avec le super-admin) |
| **Super-admin** (UNIQUE : `contact.artboost@gmail.com`) | tout voir, tout régler, droits plateforme | sécurité, cohérence des données | piloter la plateforme et les partenaires |

## 3. Problèmes actuels (constatés dans le produit)
1. **Sécurité** : une partie des routes fait encore confiance à l'en-tête `X-User-Email` non signé (usurpation possible du super-admin), plusieurs routes de configuration/paiement sont sans authentification (voir TRD §Sécurité).
2. **Cohérence des données** : historique de doublons (codes, abonnements), aucune contrainte d'unicité sur les collections centrales (`reservations`, `subscriptions`, `discount_codes`, `offers`).
3. **Complexité de l'interface** : fichiers géants (App.js 11 k lignes, ChatWidget 13,7 k, CoachDashboard 9,7 k), 158 `alert()`, design system double.
4. **Fonctions dormantes** : nombreux drapeaux désactivés (relances, auto-présence, tarif membre, bot WhatsApp…) dont l'état réel n'est visible qu'en base.
5. **Live** : deux systèmes de crédits (séances Afroboost / crédits BoostTribe), aucun droit par fonctionnalité, failles d'autorisation.
6. **Opérations** : crons hérités de Vercel inactifs sur Coolify, aucune CI, déploiement manuel à surveiller.

## 4. Solution Afroboost
Un seul site, trois espaces : **vitrine publique** (découvrir, essayer, réserver, payer), **espace membre** (séances, QR,
réservation, invitation, progression), **dashboard coach** (cours, offres, codes, réservations, contacts, campagnes,
prospection, invitation, Live, analytics), plus le **Live** intégré par iframe et des ponts vers Spordateur et Studiio.

## 5. Proposition de valeur
- Pour le participant : « Je découvre, j'essaie gratuitement avec un ami, je réserve et je viens — tout depuis mon téléphone. »
- Pour le membre : « Mes séances, mon QR, mes réservations et mes invitations au même endroit. »
- Pour le coach : « Je remplis mes cours et j'encaisse sans tableur ni WhatsApp manuel. »
- Pour le partenaire : « Ma propre vitrine et mes paiements, avec la marque Afroboost. »

## 6. Objectifs business (qualitatifs — chiffres à fixer par Bassi)
1. Augmenter le nombre de **membres actifs** et leur **rétention**.
2. Convertir les **essais gratuits** en abonnements.
3. Faire croître la communauté par **l'invitation** (Pass Duo, chaîne, ambassadeurs).
4. Développer les **partenariats** (écoles, festivals, entreprises, associations) via la prospection.
5. Ouvrir un revenu **Live** (en ligne) sans dégrader l'expérience en salle.
6. Fiabiliser l'encaissement (aucun paiement perdu, aucun accès donné sans paiement).

## 7. Indicateurs de réussite (définitions ; cibles à fixer)
| Indicateur | Définition | Source existante |
|---|---|---|
| Réservations | nombre de réservations par semaine / par cours | `reservations` (cockpit analytics) |
| Taux de présence | présences validées / réservations | `reservations.validated` |
| Membres actifs | abonnements `active` avec ≥ 1 présence sur 30 j | `subscriptions`, `reservations` |
| Rétention | membres actifs au mois M encore actifs à M+1 | à calculer |
| Essai → abonnement | essais accordés convertis en achat sous N jours | `free_trial_claims`, `subscriptions.converted_*` |
| Invitations | invitations envoyées / ouvertes / converties | `invitation_events`, `referral_passes` |
| Partenaires | prospects contactés → réponses → partenaires | `prospect_campaign_actions`, `prospect_inbound_messages`, `partners` |
| Événements | places vendues / capacité | `evenement_places`, `reservations` |
| Revenus | encaissements par mois et par source | `payment_transactions`, cockpit finance, clôture mensuelle |
| Utilisation Live | Lives, participants, minutes, séances débitées | `boosttribe_live_journal`, `boosttribe_usage` |

## 8. Modules produit

Statut réel : ✅ en production · 🟡 partiel/dormant · ❌ absent. Priorité = importance produit.

### M1 — Site public / vitrine
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Accueil (hero éditable, carrousel publications, offres « aimants ») | comprendre et donner envie | visiteur | ✅ | P0 |
| Cours, horaires, lieux, saison été/hiver | savoir où et quand | visiteur | ✅ | P0 |
| Offres et tarifs (filtrées : visibles, saison, stock, privées par lien) | choisir son offre | visiteur | ✅ | P0 |
| Liens profonds `?offre=`, `&reserver=1` | campagnes ciblées | visiteur | ✅ | P1 |
| Événements à la une, compte à rebours | urgence, remplissage | visiteur | ✅ | P1 |
| Partenaires (carrousel, vitrines `/partner/<slug>`) | crédibilité, réseau | visiteur | ✅ | P2 |
| SEO (sitemap, OG dynamiques, page « cours d'essai gratuit Neuchâtel », noindex des pages privées) | acquisition | robots | ✅ | P1 |
| FAQ, témoignages modérés, preuves sociales | confiance | visiteur | ✅ | P2 |
| Recherche par mots-clés des offres | trouver vite | visiteur | ✅ (front) | P2 |
| Multilingue FR/EN/DE (vitrine seulement) | visiteurs non francophones | visiteur | 🟡 | P2 |
| Mode maintenance | intervenir sans casser | super-admin | ✅ | P2 |

### M2 — Clients / membres
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Fiche contact (CRM `users`, `chat_participants`, tags, catégories, segments) | connaître ses membres | coach | ✅ | P0 |
| Code d'accès AFR-xxxxxx (QR) | entrer au cours, réserver | membre | ✅ | P0 |
| Espace membre `/espace/<CODE>` (OTP e-mail, lien magique, session 30 j) | autonomie | membre | ✅ | P0 |
| Séances restantes, expiration, « abonnement actuel » (résolveur unique) | clarté | membre, coach | ✅ | P0 |
| Progression (cockpit, mesures) | motivation | membre | ✅ | P2 |
| Historique (réservations, présences, paiements) | confiance | membre | 🟡 | P1 |
| Corbeille (restauration) | erreur réversible | coach | ✅ | P1 |

### M3 — Offres / abonnements
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Types : unité, carte/pack, abonnement, saison, étudiants, produit | flexibilité commerciale | coach | ✅ | P0 |
| Abonnement récurrent Stripe (mensuel), saison 1×/2× | revenu récurrent | membre | ✅ | P0 |
| Échéancier / paiement fractionné, suivi des échéances | accessibilité | membre, coach | ✅ | P1 |
| Adhésions (membership association) | statut membre | coach | ✅ | P1 |
| Offres manuelles (abonnements saisis par le coach) | encaissement hors ligne | coach | ✅ | P1 |
| Offres masquées / privées par lien | offres ciblées | coach | ✅ | P1 |
| Tarifs dynamiques (early bird, standard, last minute, paliers) | remplissage | coach | ✅ | P2 |
| Tarif membre / avantages membres (gratuit, %, prix fixe) | fidélisation | membre | 🟡 (dormant global, réglable par offre) | P2 |

### M4 — Réservations et présence
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Réserver un cours récurrent / une occurrence / un événement | venir | visiteur, membre | ✅ | P0 |
| Règle unique de consommation/restitution des séances | aucune séance perdue ou doublée | système | ✅ | P0 |
| Annulation transactionnelle (restitution) | confiance | membre, coach | ✅ | P0 |
| Scan QR, présence, absence, casque | contrôle d'accès | coach, staff | ✅ | P0 |
| Auto-présence de l'essai | moins de saisie | système | 🟡 dormant | P2 |
| Inscrits par session (+ WhatsApp) | préparer le cours | coach | ✅ | P1 |
| Rappels avant cours (par cours, push/e-mail) | moins d'absences | membre | 🟡 (boucle horaire ; mode test par défaut) | P1 |
| Export des présences, bilan de séance | gestion, finance | coach | ✅ | P2 |

### M5 — Essai gratuit
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Essai unique (anti-double : téléphone, déjà client, absent ≠ nouvel essai) | protéger l'offre | système | ✅ | P0 |
| Invitation obligatoire (par un membre / une campagne) | croissance par recommandation | invité | ✅ | P1 |
| Checkout gratuit 0 CHF, confirmation, audio d'accueil | expérience fluide | invité | ✅ | P0 |
| Relances essai J0 / J+3 / « essai non réservé » | conversion | système | 🟡 (drapeaux — états réels à confirmer en base) | P1 |
| Funnel essai (coach) | piloter la conversion | coach | ✅ | P1 |

### M6 — Invitation & parrainage
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Pass Duo (inviter un ami sur une séance précise, choix de séance) | venir à deux | membre, invité | ✅ | P0 |
| Invitations du coach : essai gratuit, événement gratuit, événement payant (brouillon/actif/masqué/archivé) | campagnes d'invitation | coach | ✅ | P0 |
| Liens personnels après achat/inscription (« inviter encore », chaîne) | effet boule de neige | membre | ✅ | P1 |
| Ambassadeurs (Boosts, paliers, récompenses) | récompenser les meilleurs | membre, coach | ✅ | P2 |
| Suivi du funnel d'invitation | mesurer | coach | ✅ | P1 |
| Médias d'invitation (vidéo, audio) | convaincre | coach | ✅ | P2 |

### M7 — Événements
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Création / brouillon / publication / masquer (ex. Afroboost Silent) | vendre un événement | coach | ✅ | P0 |
| Page événement courte (vidéo, promesse, date, prix, « Je réserve ») | conversion | visiteur | ✅ | P0 |
| Paliers datés, capacité réelle, urgence | remplissage | visiteur | ✅ | P1 |
| Avantages membres réglés par le coach | fidélisation | membre | ✅ | P1 |
| Billet / place offerte / partage | viralité | membre | ✅ | P1 |

### M8 — Partenaires
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Devenir partenaire (packs, inscription, validation) | recruter des coachs | partenaire | ✅ | P2 |
| Vitrine partenaire `/partner/<slug>`, dashboard partenaire (onglets boutique, Stripe, créateur) | autonomie | partenaire | 🟡 (mono-coach assumé dans le code) | P2 |
| Cloisonnement des données par `coach_id` | confidentialité | partenaire | 🟡 | P0 (si partenaires réels) |
| Stripe Connect, crédits partenaire | encaissement direct | partenaire | 🟡 | P2 |
| Statistiques partenaire | suivi | partenaire | ✅ | P2 |

### M9 — Prospection
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Fiches prospects (import, niches, enrichissement, anti-doublon, statuts) | cibler | coach | ✅ | P1 |
| Campagnes J0 → J+3 → J+7 → J+14 (approbation, empreinte, quota) | contacter à l'échelle | coach | ✅ (drapeaux d'envoi) | P1 |
| Réponses entrantes (Resend inbound), conversations partenaires, fil complet | ne rien rater | coach | ✅ | P0 |
| Générateur IA de réponses (répondre avant de vendre, contrôle avant affichage) | gagner du temps | coach | ✅ | P1 |
| Réponse manuelle + média (vidéo/image) + envoi suivi (remis/rebond) | suivi commercial | coach | ✅ | P1 |
| Agenda / RDV public, notes, traduction | conclure | coach, partenaire | ✅ | P2 |
| Médias et liens de prospection, résultats/KPI | outillage | coach | ✅ | P2 |

### M10 — Campagnes clients
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Campagnes e-mail (Resend), WhatsApp (modèles Meta), push | réactiver, annoncer | coach | ✅ | P1 |
| Planificateur (boucle 60 s), quota quotidien Resend | fiabilité | système | ✅ | P1 |
| Registre STOP / désinscription en 1 clic | conformité | destinataire | ✅ | P0 |
| Segments, réactivation | ciblage | coach | ✅ | P2 |
| Diffusion vers Studiio | multi-canal | coach | ✅ | P2 |

### M11 — Médias
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Upload (simple et par morceaux, 200 Mo), service par plages (vidéo) | médias fiables | coach, membre | ✅ | P0 |
| Bibliothèques (prospection, invitation), éditeur vidéo navigateur (découpe, formats, miniature) | contenus pro | coach | ✅ | P1 |
| Purge des orphelins (48 h de grâce), médias éphémères du chat | maîtrise du disque | système | ✅ | P1 |

### M12 — Paiements
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Checkout Stripe (carte, TWINT), prix calculé serveur | encaisser | visiteur, membre | ✅ | P0 |
| Webhooks + idempotence, activation automatique (code, séances) | accès immédiat | système | ✅ (voir risques) | P0 |
| Abonnements Stripe récurrents (résilier/réactiver) | récurrence | membre | ✅ | P0 |
| Paiements manuels + suivi des échéances + rappels | encaissement hors ligne | coach | ✅ | P1 |
| Mobile money (PawaPay), CinetPay, PayPal | international | visiteur | 🟡 (dormant / partiel) | P2 |
| Transactions, bilan de séance, partage, clôture mensuelle | finance | coach | ✅ | P1 |

### M13 — Dashboard coach / super-admin
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Onglets Réservations, Gestion (offres/cours/vitrine/hero/paiements…), Codes, Contacts, Campagnes, Prospection, Invitation, Conversations, Corbeille | piloter | coach | ✅ | P0 |
| Super Admin : partenaires, packs, cockpit, analytics, association, créateurs, maintenance, saison, drapeaux | gouverner | super-admin | ✅ | P0 |
| Personnalisation des couleurs de la vitrine (sans flash) | marque | coach | ✅ | P1 |

### M14 — Analytics
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Cockpit (réservations, revenus, sources, essais, abonnements), exports CSV/XLSX/PDF | décider | super-admin | ✅ | P1 |
| Vue association anonymisée, clôture mensuelle figée | gouvernance | association | ✅ | P2 |
| Attribution (source de réservation, metadata Stripe) | mesurer le marketing | coach | 🟡 | P2 |
| PostHog (événements funnel) | parcours | super-admin | 🟡 | P2 |

### M15 — Afroboost Live (BoostTribe) — détail : `modules/live/LIVE_AUDIT.md`
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| Live vidéo (scène, co-hôte, main levée), musique synchronisée, timer, studio, partage d'écran | cours en ligne Afroboost | coach, membre | ✅ | P1 |
| Accès depuis afroboost.com (bouton Live, « Live en cours », 1 séance débitée) | continuité | membre | ✅ | P1 |
| Invités Live (identité légère, contact) | acquisition | invité | ✅ | P2 |
| Crédits par utilisateur + droits par fonctionnalité réglables par l'admin | monétiser finement | super-admin | ❌ | P1 (souhait Bassi) |
| Enregistrement local / transcription / souffleur IA | contenu, aide | coach | ✅ | P2 |
| Replay vidéo serveur | rattrapage | membre | ❌ | P2 |
| Multistream réseaux sociaux | audience | coach | 🟡 (verrou) | P2 |

### M16 — Chat / messagerie
| Fonctionnalité | Bénéfice | Utilisateur | Statut | Prio |
|---|---|---|---|---|
| ChatWidget (visiteur : capture lead, FAQ IA ; abonné : réservations, QR, groupes ; coach : sessions, bot) | contact immédiat | tous | ✅ | P1 |
| Chat IA, traduction multilingue | répondre 24/7 | visiteur | ✅ | P2 |
| Messagerie privée, groupes, WhatsApp (webhook Meta, vente assistée) | relation | coach | ✅ | P1 |
| Bot WhatsApp à menu | automatiser | système | 🟡 dormant | P2 |
| Notifications push (abonnements, préférences, silence) | réengagement | membre | ✅ | P1 |

### M17 — Calendrier & tâches
Agenda des campagnes, tâches à échéance, rendez-vous, synchronisation Google Calendar — ✅ — coach — P2.

### M18 — Programme Créateur / affiliation
Candidature créateur, lien de partage, commissions, demandes de paiement — ✅ (peu utilisé : 1 créateur) — P2.

### M19 — Publications / social boost / témoignages
Publications (photo/vidéo), Boost payant, commentaires, likes, témoignages modérés, preuves sociales — ✅ — P2.

### M20 — Ponts externes
Spordateur / rencontre (profil unifié, accès signé) ✅ P2 · Studiio (diffusion de campagnes) ✅ P2.

### M21 — Boutique
Produits physiques (variantes, adresse, suivi d'expédition) — ✅ — P2.

### M22 — Authentification & sécurité (transverse)
Connexion coach (mot de passe + JWT 7 j), espace membre (OTP), super-admin unique, drapeaux de durcissement — 🟡 (repli `X-User-Email` encore actif) — **P0**.

## 9. Hors périmètre actuel
- Application mobile native (seule la PWA est en production ; Capacitor Android existe pour BoostTribe, non publié côté Afroboost).
- Multi-coach complet « SaaS » (le code assume encore un mono-coach à plusieurs endroits).
- Comptabilité/facturation légale complète (seule une génération de factures simple existe).
- Replay vidéo serveur, sous-titres, clips (Live).
- Marketplace de coachs.
- Toute refonte complète du design ou réécriture du backend.

## 10. User stories (sélection par module)
- **M1** — En tant que visiteur, je veux voir les prochains cours avec lieu et heure, afin de choisir une séance qui me convient.
- **M1** — En tant que visiteur arrivant par un lien `?offre=X`, je veux voir directement cette offre, afin de réserver sans chercher.
- **M2** — En tant que membre, je veux me reconnecter à mon espace avec un code reçu par e-mail, afin de ne pas retenir de mot de passe.
- **M2** — En tant que coach, je veux voir pour chaque membre son abonnement actuel et ses séances restantes, afin de répondre sans calcul.
- **M3** — En tant que membre, je veux payer ma saison en deux fois, afin d'étaler la dépense.
- **M4** — En tant que membre, je veux annuler une réservation et récupérer ma séance, afin de ne pas la perdre.
- **M4** — En tant que coach, je veux scanner le QR d'un participant, afin de valider sa présence en une seconde.
- **M5** — En tant qu'invité, je veux réserver mon essai gratuit avec mon ami, afin de venir accompagné.
- **M6** — En tant que membre, je veux partager un lien personnel vers une séance précise, afin que mon ami s'inscrive facilement.
- **M7** — En tant que visiteur, je veux voir le prix actuel d'un événement et la date du prochain palier, afin de décider vite.
- **M8** — En tant que partenaire, je veux ne voir que mes propres clients, afin de respecter leur confidentialité.
- **M9** — En tant que coach, je veux une réponse IA courte qui répond au dernier message du partenaire, afin de gagner du temps sans paraître générique.
- **M10** — En tant que destinataire, je veux me désinscrire en un clic, afin de ne plus recevoir de messages.
- **M12** — En tant que membre, je veux recevoir mon code et mes séances immédiatement après paiement, afin de réserver tout de suite.
- **M13** — En tant que super-admin, je veux être le seul à pouvoir modifier les réglages de la plateforme, afin d'éviter toute usurpation.
- **M15** — En tant que super-admin, je veux attribuer à un utilisateur des crédits et choisir les fonctionnalités Live autorisées, afin de vendre des formules différentes.
- **M15** — En tant que membre, je veux voir combien de crédits il me reste avant de rejoindre un Live, afin de ne pas être bloqué en cours.
- **M16** — En tant que visiteur, je veux poser une question dans ma langue, afin de comprendre l'offre.

## 11. Critères d'acceptation (sélection)
- Étant donné un abonnement actif avec 3 séances, quand le membre réserve une séance, alors il en reste 2, une ligne `seance_mouvements` est écrite, et une seconde soumission identique ne débite rien.
- Étant donné une réservation confirmée, quand le membre l'annule dans les délais, alors la séance est restituée une seule fois et la réservation passe « annulée ».
- Étant donné un paiement Stripe réussi, quand le webhook est reçu deux fois, alors un seul code/abonnement est créé.
- Étant donné un visiteur ayant déjà bénéficié d'un essai, quand il tente un nouvel essai, alors la réponse est un refus neutre sans révéler la raison.
- Étant donné une requête sans JWT signé et un en-tête `X-User-Email` du super-admin, quand elle appelle une route réservée au super-admin, alors la réponse est 401/403 (**non respecté aujourd'hui sur une partie des routes**).
- Étant donné un brouillon de réponse contenant « [À COMPLÉTER : … ] », quand le coach confirme l'envoi, alors l'envoi est refusé (409) tant que le champ n'est pas rempli.
- Étant donné un membre sans crédit Live, quand il ouvre le Live, alors l'accès est refusé avec le message « plus de séance disponible » et aucun débit n'a lieu.
- Étant donné un utilisateur dont la fonctionnalité « Enregistrement » est désactivée, quand il demande à enregistrer, alors le **serveur** refuse, même si l'interface a été modifiée (cible, non existant).

## 12. Questions produit ouvertes (décision de Bassi)
1. **Sécurité d'abord** : accepter un lot P0 de fermeture des routes falsifiables, quitte à demander une reconnexion à tous les coachs ?
2. Partenaires : la plateforme doit-elle vraiment devenir multi-coach (plusieurs partenaires actifs), ou rester centrée sur Coach Bassi ? (conditionne le cloisonnement et le dashboard partenaire)
3. Live : un crédit Live = une séance du forfait, ou une unité distincte ? Solde commun avec boosttribe.pro ? Qui paie (participant, hôte) ?
4. Live : quelles fonctionnalités payantes et à quel prix (enregistrement, IA, replay, multistream) ?
5. Drapeaux dormants : lesquels activer, lesquels supprimer (tarif membre, bot WhatsApp, auto-présence, relances P1, PawaPay) ?
6. Paiements alternatifs (PawaPay, CinetPay, PayPal) : à garder ou à retirer ?
7. Langues : faut-il traduire l'espace membre et le dashboard (aujourd'hui français en dur) ?
8. KPI : quelles cibles chiffrées pour réservations, rétention, conversion essai, invitations, revenus, Live ?
9. Données de santé (progression) : doivent-elles rester accessibles avec le seul code d'accès ?
10. Faut-il un rôle « admin » distinct du super-admin (ex. staff de salle), avec des droits limités ?

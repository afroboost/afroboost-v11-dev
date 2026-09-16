# Lancement Fondateurs — VAGUE 1 (APERÇU, RIEN N'EST ENVOYÉ) — préparé le 16/09/2026

> Lecture seule de la production. Mêmes règles que l'aperçu de campagne 3B : segments `classer_personne`,
> fusion par téléphone/e-mail, décisions e-mail/WhatsApp (`r3_preparer_*`), registre STOP (`c3_refus_exprimes`),
> données de test écartées. Aucune donnée personnelle en clair : prénom + initiale, numéro et e-mail masqués.
> Offre vérifiée au moment du calcul : **Fondateurs 59 CHF/mois · `mensuel_auto` · 8 séances · deadline 30/09/2026 23:59 (Zurich) · stock 0/50.**

## Résumé

| | |
|---|---|
| Base réactivation (union sans doublon, hors actifs et tests) | 35 personnes (identique au calcul E1) |
| **VAGUE 1 (signal fort)** | **13 personnes** |
| WhatsApp | 12 |
| E-mail | 1 |
| Exclus de la vague 1 (gardés pour une vague 2) | 22 |
| Clients actifs (droit en cours) — public séparé, hors réactivation | 12 détectés par cette passe (66 selon l'aperçu 3B complet, qui lit aussi les codes d'accès) |

**Pourquoi 13 et pas 20** : après retrait des essais **à venir** (2, le 20/09 — la relance après essai existante prend le relais),
des essais **jamais réservés** (7, signal faible), du public **événement** Laff Festival (5, pas des habitués des cours de
Neuchâtel), d'une donnée de test non détectée par la regex (1) et des anciens participants de plus de 90 jours (7), il reste
exactement 13 signaux forts : 7 anciens abonnés/packs, 3 essais présents non convertis, 3 anciens participants récents (≤ 3 semaines).

## Critères (ordre lisible, données existantes uniquement)

1. **Ancien abonné / pack** (a déjà payé un abonnement, aujourd'hui inactif) — récence en 2ᵉ clé.
2. **Essai présent non converti** (présence scannée, aucun achat ensuite).
3. **Ancien participant récent** (≥ 1 réservation de cours hors essai, dernière ≤ 90 j).

Canal : **un seul par personne**. WhatsApp si numéro légitime (E.164 ou mobile suisse), autorisé par la garde
(consentement OU relation client : réservation/abonnement/conversation), pas STOP ; sinon e-mail valide non rebondi.

## Tableau Vague 1

| # | Prénom | Segment | Dernière interaction | Canal | Coordonnée (masquée) | Motif de sélection | Lien tracké | Statut |
|---|---|---|---|---|---|---|---|---|
| 1 | Amanda R. | Ancien abonné / pack | 09/09/2026 · réservation | WhatsApp | +4176 ** *** ** 05 | ancienne abonnée, encore active en réservation | WA | PRÊT |
| 2 | Carel A. | Ancien abonné / pack | 30/08/2026 · réservation | WhatsApp | +4178 ** *** ** 65 | ancien abonné, réservation récente | WA | PRÊT |
| 3 | Caroline B. | Ancien abonné / pack | 01/07/2026 · réservation | WhatsApp | +4179 ** *** ** 97 | ancienne abonnée | WA | PRÊT |
| 4 | A. S. (pseudo) | Ancien abonné / pack | 07/06/2026 · réservation | WhatsApp | +4179 ** *** ** 80 | ancienne abonnée — ⚠ prénom incertain (pseudo) | WA | PRÊT (sans prénom) |
| 5 | Veldaes B. | Ancien abonné / pack | 03/05/2026 · réservation | WhatsApp | +3376 ** *** ** 46 | ancien abonné — numéro français (WhatsApp OK) | WA | PRÊT |
| 6 | Diana D. | Ancien abonné / pack | 12/04/2026 · présence scannée | WhatsApp | +4176 ** *** ** 62 | ancienne abonnée | WA | PRÊT |
| 7 | Patricia A. | Ancien abonné / pack | 15/03/2026 · achat pack | WhatsApp | +4177 ** *** ** 65 | ancienne abonnée | WA | PRÊT |
| 8 | Chloé H. | Essai présent non converti | 09/09/2026 · présence scannée | WhatsApp | +4179 ** *** ** 61 | a essayé il y a 7 jours, pas encore convertie | WA | PRÊT |
| 9 | Mme B. | Essai présent non converti | 02/09/2026 · présence scannée | WhatsApp | +4179 ** *** ** 63 | a essayé il y a 2 semaines — ⚠ prénom incertain (« Mme ») | WA | PRÊT (sans prénom) |
| 10 | Yann | Essai présent non converti | 02/09/2026 · présence scannée | WhatsApp | +4177 ** *** ** 45 | a essayé il y a 2 semaines | WA | PRÊT |
| 11 | Kim2 | Ancien participant | 02/09/2026 · réservation (cours à l'unité) | WhatsApp | +4178 ** *** ** 45 | 3 réservations de cours (mai, juin, sept.) — ⚠ prénom incertain (pseudo) | WA | PRÊT (sans prénom) |
| 12 | Khady | Ancien participant | 26/08/2026 · réservation | WhatsApp | +4176 ** *** ** 89 | réservation il y a 3 semaines | WA | PRÊT |
| 13 | Ozgul | Ancien participant | 26/08/2026 · réservation | **E-mail** | os…@p***.net | réservation il y a 3 semaines ; pas de numéro exploitable | EMAIL | PRÊT |

Liens : **WA** = `afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=whatsapp&utm_medium=messaging&utm_campaign=fondateurs2026`
(sans protocole : le moteur le retire lui-même pour Meta) · **EMAIL** = `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=email&utm_medium=email&utm_campaign=fondateurs2026`.
Vérifié le 16/09 (Playwright, lecture seule) : HTTP 200, fiche Fondateurs ouverte (nom, 59, 8 séances), attribution `af_attribution` first/last écrite.

## Non retenus pour la vague 1 (vague 2 potentielle) — 22

| Groupe | Nb | Motif | Canal possible |
|---|---|---|---|
| Essai réservé pour le **20/09** (Garance H., Camille B.) | 2 | essai à venir : laisser la relance après essai (P1-b/P1-d) faire son travail ; recontacter après le 20/09 | WhatsApp |
| Anciens participants > 90 j (Ceylan, Laura B., Nadia O., Elsa G. — 17-21/06 ; Oswald C. 17/05 ; Sandra C. 26/04 ; Enock A. 22/04 ; Léa P. 12/04) | 8 | signal réel mais plus ancien → vague 2 | 7 WhatsApp, 1 e-mail |
| Essais **jamais réservés** (Andreia M. 12/09, Rose, Margotine H. 02/09, G., Y. 25/08, M. 24/08) | 6 | essai octroyé mais jamais réservé : → corrigé 16/09 : message Fondateurs (connaissent déjà Afroboost) | WhatsApp |
| Public **Laff Festival** 21-22/08 (C. L., B. L., A. M., L. C., T. (pseudos)) | 5 | présence à un événement, pas aux cours de Neuchâtel ; 2 numéros français | 3 WhatsApp, 2 e-mail |
| Testfunel2 | 1 | **donnée de test** (« Testfunel2 » échappe à la regex `\btest\b` de `est_donnee_test`) — à exclure de toute campagne ; petite dette : élargir la regex | — |

## Sécurité avant GO (vérifié le 16/09, lecture seule)

- STOP : registre = 3 refus e-mail, 0 refus WhatsApp — **aucun des 13 n'y figure**.
- Tests : 57 fiches de test écartées par la règle ; **+ Testfunel2 écarté à la main** (voir dette ci-dessus). Aucun `@example.com` dans les 13.
- Doublons : fusion téléphone + e-mail (union-find) → **0 doublon** dans les 13 ; **0 personne sur deux canaux**.
- Abonnement Fondateurs déjà actif : **0** (stock 0/50).
- Deadline : 30/09/2026 23:59 heure de Zurich — valide.
- Liens : 3/3 en 200, fiche ouverte, attribution posée.
- Monitoring premier client : `python3 tests/monitoring_premier_fondateur.py [email]` — prêt (syntaxe OK, sortie « aucun abonné » propre), **ne pas lancer avant le premier achat réel**.

## Messages FINAUX (correction du 16/09 — AUCUN essai gratuit : les 13 connaissent déjà Afroboost)

Brouillons créés en base (statut `draft`, aperçu serveur 12 WA `ok` + 1 e-mail `ok`, Patricia sur sa fiche `chat_login`) :
`123b7bb9…` « Fondateurs V1 FINAL — WhatsApp (prénom) » (8) · `bf9a0c39…` « Fondateurs V1 FINAL — WhatsApp (sans prénom) » (4 : Carel,
avitanshannon, Bourgouin, Kim) · `0aa0ad1c…` « Nouvelles offres Afroboost — Offre Fondateurs à 59 CHF/mois » (1, e-mail).
⚠️ Les 3 premiers brouillons (`33531e64…`, `e6f44e66…`, `ccd0026c…`, textes avec essai) sont OBSOLÈTES : ne jamais les lancer.

### A. WhatsApp — gabarit Meta `afroboost_campagne`
> Bonjour {prenom}, c'est Bassi d'Afroboost.
> La saison reprend à Neuchâtel et les nouvelles offres Afroboost sont disponibles.
> L'offre Fondateurs est à 59 CHF/mois pour 8 séances/mois.
> 50 places maximum, disponible jusqu'au 30 septembre.
> Découvrir les nouvelles offres :
> afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=whatsapp&utm_medium=messaging&utm_campaign=fondateurs2026
> Réponds STOP si tu ne souhaites plus recevoir de messages Afroboost

Variante sans prénom : « Bonjour, c'est Bassi d'Afroboost. »
Rendu reçu : « Afroboost vous informe: Bonjour Amanda, c'est Bassi d'Afroboost. La saison reprend à Neuchâtel et les nouvelles offres Afroboost sont disponibles. L'offre Fondateurs est à 59 CHF/mois pour 8 séances/mois. 50 places maximum, disponible jusqu'au 30 septembre. Découvrir les nouvelles offres : afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=whatsapp&utm_medium=messaging&utm_campaign=fondateurs2026. Réponds STOP si tu ne souhaites plus recevoir de messages Afroboost. Rendez-vous sur afroboost.com »

### B. E-mail (Ozgul)
Objet : Nouvelles offres Afroboost — Offre Fondateurs à 59 CHF/mois (le moteur préfixe « 📢 »)
> Bonjour Ozgul,
> La saison reprend à Neuchâtel et les nouvelles offres Afroboost sont maintenant disponibles.
> L'offre Fondateurs est proposée à 59 CHF/mois pour 8 séances/mois.
> 50 places maximum, disponible jusqu'au 30 septembre.
> [Découvrir les nouvelles offres] → https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=email&utm_medium=email&utm_campaign=fondateurs2026
> À très vite,
> Bassi — Afroboost
> (désinscription un-clic 3B ajoutée par le moteur)

**STOP automatique — prouvé le 16/09** : `POST /webhook/whatsapp-meta` → `_v332_stop_whatsapp` (casse/accents/ponctuation) → `subscribers.opted_out`
→ `c3_refus_exprimes` → campagne suivante `opt_out`/`skipped`. Mock 7/7 ; bancs 95/95 et 42/42.
## Après GO — comment ça s'envoie (rappel, rien n'est fait ici)
Campagne 3B existante : sélection des 13 contacts (`selectedContacts`), canal WhatsApp pour 12 / e-mail pour 1 (deux campagnes ou une
campagne par canal), **aperçu serveur** (`GET …/apercu` : compteurs `ok / opt_out / test / actif / doublon / sans_relation`) → les 13 doivent
sortir en `ok` → confirmation. Idempotence : une personne + une campagne + un canal = un envoi (`cle_idempotence`). Exiger `delivered`, jamais `sent`.

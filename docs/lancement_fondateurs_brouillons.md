# Lancement Offre Fondateurs — BROUILLONS (rien n'est envoyé) — préparé le 16/09/2026

> Offre en production (vérifiée en base + vitrine + landing le 16/09) : **Fondateurs — 59 CHF / mois — 8 séances par mois
> (valables le mois en cours, non reportées) — 50 places maximum — jusqu'au 30 septembre 2026, 23:59 (heure suisse) —
> prélèvement mensuel par carte, résiliable à tout moment depuis l'espace abonné (accès jusqu'à la fin du mois payé).**
> Le nombre de places restantes est TOUJOURS la valeur calculée par le site (`places_restantes`), jamais un chiffre écrit à la main.
> Aucun témoignage, aucun compteur inventé. L'essai gratuit reste l'alternative pour les hésitants.

## Liens avec attribution (modèle M2-A existant, `?offre=` + UTM ou `?ref=`)

| Canal | Lien |
|---|---|
| E-mail | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=email&utm_medium=email&utm_campaign=fondateurs2026` |
| WhatsApp | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=whatsapp&utm_medium=messaging&utm_campaign=fondateurs2026` |
| Instagram | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=instagram&utm_medium=social&utm_campaign=fondateurs2026` |
| Facebook | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=facebook&utm_medium=social&utm_campaign=fondateurs2026` |
| TikTok | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=tiktok&utm_medium=social&utm_campaign=fondateurs2026` |
| QR (affiche, flyer) | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=qr&utm_medium=print&utm_campaign=fondateurs2026` |
| Partenaire | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&ref=<slug-du-partenaire>` (→ source `partenaire`, medium `referral`, content = slug) |
| Story (lien « swipe up » / sticker) | `https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=instagram&utm_medium=story&utm_campaign=fondateurs2026` |

Essai gratuit (alternative) : `https://afroboost.com/cours-essai-gratuit-neuchatel?utm_source=<canal>&utm_medium=<medium>&utm_campaign=fondateurs2026`.
Le lien ouvre directement la fiche Fondateurs ; l'attribution first/last voyage jusqu'aux métadonnées Stripe et au cockpit « par source » (prouvé P6/P6b).

## A. WhatsApp — ancien client (gabarit Meta : PAS d'emoji, PAS d'URL complète dans les variables ; domaine sans protocole autorisé)

Bonjour {{1}}, c'est Bassi d'Afroboost.
La saison reprend a Neuchatel et j'ouvre une offre Fondateurs : 59 CHF par mois, 8 seances par mois, reservee aux 50 premiers inscrits, jusqu'au 30 septembre.
Sans engagement : tu peux resilier a tout moment depuis ton espace.
Decouvrir l'offre et reserver ma place : afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437&utm_source=whatsapp&utm_medium=messaging&utm_campaign=fondateurs2026
Tu hesites ? Ton premier cours est offert : afroboost.com/cours-essai-gratuit-neuchatel
Reponds STOP pour ne plus recevoir de messages.

(Variables : {{1}} = prénom. Garde consentement OU relation client, registre STOP et exclusions déjà appliqués par le moteur de campagne.)

## B. E-mail — ancien client

Objet : Offre Fondateurs — 59 CHF/mois, 50 places, jusqu'au 30 septembre
Pré-en-tête : La saison Afroboost reprend à Neuchâtel. Tarif de lancement réservé aux 50 premiers inscrits.

Bonjour {{prénom}},

La saison reprend et je voulais te prévenir en premier : j'ouvre une **offre Fondateurs** pour celles et ceux qui ont déjà dansé avec nous.

- **59 CHF / mois**, prélevé chaque mois par carte
- **8 séances par mois** (valables le mois en cours)
- **50 places maximum** — le site affiche les places restantes en temps réel
- **Jusqu'au 30 septembre 2026** (23:59, heure suisse)
- **Sans engagement** : résiliable à tout moment depuis ton espace abonné, accès jusqu'à la fin du mois payé

[Découvrir l'offre / Réserver ma place] → lien E-mail ci-dessus

Tu hésites ? **Ton premier cours est offert** : [Réserver mon cours d'essai] → lien essai gratuit.

À très vite au bord du lac,
Bassi — Afroboost

Se désinscrire : {{lien_desinscription_un_clic}} (mécanisme 3B existant)

## C. Instagram / Facebook (post)

OFFRE FONDATEURS — la saison reprend à Neuchâtel.
59 CHF/mois · 8 séances/mois · 50 places maximum · jusqu'au 30 septembre.
Cardio-danse africaine au casque, en groupe, au bord du lac. Pas besoin de savoir danser.
Sans engagement — résiliable à tout moment depuis ton espace.
Lien en bio → Découvrir l'offre / Réserver ma place. Premier cours offert si tu veux d'abord essayer.
#afroboost #neuchatel #danse #cardio #silentfitness

(Lien en bio : lien Instagram/Facebook ci-dessus. Aucun chiffre de places dans le visuel : le site l'affiche en direct.)

## D. Story (3 écrans)

1. « La saison reprend. » — visuel cours au bord du lac.
2. « Offre Fondateurs : 59 CHF/mois, 8 séances/mois, 50 places, jusqu'au 30 septembre. »
3. « Réserver ma place » (sticker lien Story) — « Ou teste d'abord : 1er cours offert » (sticker lien essai).

## E. SMS

Pas de canal : Twilio n'est pas actif en production (bundle réglementaire suisse incomplet). Aucun brouillon SMS.

## Segments disponibles (calcul du 16/09, mêmes règles que l'aperçu de campagne 3B, lecture seule)

| Segment (réactivation) | Personnes | E-mail éligibles | WhatsApp éligibles |
|---|---|---|---|
| Essais présents non convertis | 3 | 2 | 3 |
| Essais réservés, présence inconnue | 2 | 2 | 2 |
| Essais jamais réservés | 7 | 7 | 7 |
| Anciens participants | 17 | 15 | 15 |
| Anciens abonnés / packs | 7 | 6 | 7 |
| Récents non abonnés (≤ 60 j) | 22 | 20 | 19 |
| **Union (sans doublon)** | **35** | **32** | **31** |
| Clients ACTIFS (droit en cours — exclus des campagnes de réactivation, mais public légitime pour une info « nouvelle formule ») | 66 | 66 | 65 |

Exclus automatiquement : 14 « sans relation » (comptes app sans historique client — jamais sollicités), 6 données de test, 9 doublons, adresses/numéros manquants. Refus (STOP / désinscription) honorés par `c3_refus_exprimes`. 8 numéros WhatsApp avec consentement explicite ; les autres passent par la règle « relation client ».

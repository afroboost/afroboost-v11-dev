# Parcours client Playwright — pile LOCALE (aucun paiement, aucun e-mail réel)

- `pile_locale.py` : la VRAIE application (code de l'arbre) sur une base de test séparée
  (`afroboost_pw_test`, jamais la prod), Stripe et Resend remplacés par des faux
  (page « Paiement TEST » → événement `checkout.session.completed` posté au VRAI webhook ;
  e-mails écrits dans `pw_emails.jsonl`). Épingle `stripe==14.1.0` (version de prod) dans `pw_lib/`.
- `semer_base_test.py` : copie LECTURE SEULE des collections de configuration (offres, cours,
  concept, réglages, médias) — jamais de données personnelles.
- `parcours_fondateurs.cjs` : P1 desktop, P4 mobile, P5 double clic / refresh / rejeu webhook, P6 UTM → metadata Stripe.
- `parcours_essai_espace.cjs` : P2 essai (lien profond du tunnel → formulaire → octroi → OTP lu dans
  le faux Resend → réservation), P3 reconnexion (autre appareil, session d'appareil), P3b acheteur
  Fondateurs (onboarding → espace 8/8), P5b double inscription refusée.

```
cd <scratchpad>; python3 -m pip install --target pw_lib stripe==14.1.0
cd frontend && REACT_APP_BACKEND_URL=http://127.0.0.1:8001 BUILD_PATH=<scratchpad>/pw_build npx craco build
python3 semer_base_test.py ; python3 pile_locale.py &
NODE_PATH=$HOME/.claude/skills/gstack/node_modules node parcours_fondateurs.cjs
NODE_PATH=$HOME/.claude/skills/gstack/node_modules node parcours_essai_espace.cjs
```
Règle du moteur à respecter dans les enchaînements : 120 s entre deux demandes d'OTP pour un même code, 3 par 10 min.

## V534 — Centre Parrainage / Pass Duo (`parcours_parrainage.cjs`, `fixtures_duo.py`)
- `fixtures_duo.py activer` : drapeau `parrainage_duo_enabled` + `duo_enabled` sur les deux cours récurrents,
  **dans la base de test uniquement** ; `fixtures_duo.py parrain <email@example.com> [séances]` : parrain fictif
  (abonnement + code) ; `fixtures_duo.py nettoyer` : retire ces fixtures.
- `parcours_parrainage.cjs` : scénarios A→P (centre, WhatsApp, copie, QR, partage natif, création, invitation
  publique, ami inscrit, attente, déblocage, billets, espace abonné, chat widget, après réservation, historique,
  responsive) + anti-abus par l'API + KPI admin (JWT local `pw-local-secret`). Un parrain « sans séance » est
  créé en cours de route (scénario I). Captures dans `captures/`.
- L'entrée « Parrainage » du menu ⋮ du chat n'est pas atteignable en headless (en-tête hors viewport) : à vérifier
  dans un vrai Chrome (fait le 21/09/2026).
- V534b : `fixtures_duo.py activer` pose aussi le catalogue d'offres (`duo_offer_ids` = essai gratuit + deux offres de TEST
  à 0 CHF « Pass découverte » / « Offre étudiant », recommandée sur le mercredi) ; le banc couvre le choix d'offre à la
  création, « Changer d'offre » (sheet, version, 409 conflit), « Voir les autres offres » côté ami, le changement après
  déblocage sans présence (ancienne réservation supprimée, séance restituée, un seul code actif), le refus après présence
  validée (texte exact) et les KPI d'offres.

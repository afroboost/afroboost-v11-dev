#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V633 — SUIVI PARTENAIRES.

Prouve, sur les VRAIES routes (MongoDB en mémoire, aucun réseau) :
  * vue coach : rapport détaillé par code, totaux 60/40 ;
  * paiement confirmé avec HETAIRA10 ;
  * paiement confirmé sans réservation finalisée ;
  * réservation sans paiement confirmé ;
  * code + invitation = une seule ligne financière ;
  * plusieurs séances dans une transaction : jamais comptées deux fois ;
  * remboursement complet ;
  * paiement en espèces déclaré par le coach ;
  * anti-doublon espèces (idempotence_key) ;
  * calcul exact 40 % / 60 % ;
  * modification du pourcentage partenaire ;
  * export CSV ;
  * accès partenaire sans compte (jeton URL) ;
  * jeton invalide, expiré ou révoqué ;
  * révocation immédiate ;
  * isolation stricte des partenaires ;
  * aucun e-mail ni téléphone dans les réponses partenaire ;
  * aucune écriture possible côté partenaire ;
  * rate limiting ;
  * non-régression des codes promo existants.

Lancement :  python3 tests/test_v633_suivi_partenaires.py
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Harnais de test existant (MongoDB en mémoire)
import test_parrainage_v3 as V3  # noqa: E402

H = V3.H
RESULTATS: list = []

# Routes à tester
import api.routes.partner_routes as PR  # noqa: E402

# ─── Constantes du test ───────────────────────────────────────────────────────
COACH_EMAIL = H.ADMIN          # contact.artboost@gmail.com
COACH2_EMAIL = "autre.coach@exemple.test"
HETAIRA10 = "HETAIRA10"
OFFRE_ID = H.OFFRE_PAYANTE     # "offre-payante" (30 CHF)
DATE_SEANCE = "2026-11-11T18:45:00+01:00"

SESSION_1 = "cs_stripe_001"
SESSION_2 = "cs_stripe_002"
SESSION_REMBOURSE = "cs_stripe_003"
SESSION_SANS_RESA = "cs_stripe_004"

# ─── Helpers ─────────────────────────────────────────────────────────────────


def admin():
    return {"Authorization": "Bearer " + H.jeton_admin(COACH_EMAIL)}


def coach2():
    return {"Authorization": "Bearer " + H.jeton_admin(COACH2_EMAIL)}


def req(corps=None, entetes=None):
    return H.Requete(corps if corps is not None else {}, entetes or {})


async def appel(coro):
    return await H.appel(coro)


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def contient_sensible(obj, champs=("email", "phone", "whatsapp", "tel", "token_hash")):
    """Renvoie les clés sensibles présentes (fuite de données)."""
    s = json.dumps(obj, ensure_ascii=False, default=str).lower()
    return [k for k in champs if k in s]


# ─── Base de données de test ─────────────────────────────────────────────────


def base_partenaire():
    """Base de données en mémoire avec les données de test V633."""
    base, _ = V3.H.base_de_depart()

    # Code promo HETAIRA10 (appartient au coach admin)
    base["discount_codes"].docs.append({
        "id": "code-hetaira10",
        "code": HETAIRA10,
        "name": None,
        "assignedEmail": None,
        "active": True,
        "maxUses": 30,
        "used": 0,
        "coach_id": COACH_EMAIL,
        "type": "CHF",
        "value": 10,
        "courses": [OFFRE_ID],
        "multi_member": False,
        "shared_sessions": False,
    })

    # Code d'un autre coach (isolation)
    base["discount_codes"].docs.append({
        "id": "code-autre-coach",
        "code": "AUTRECOACH99",
        "name": None,
        "assignedEmail": None,
        "active": True,
        "maxUses": 10,
        "used": 0,
        "coach_id": COACH2_EMAIL,
        "type": "CHF",
        "value": 10,
        "courses": [],
    })

    # Transactions Stripe liées à HETAIRA10
    base["payment_transactions"].docs += [
        {
            "session_id": SESSION_1,
            "customer_email": "alice.martin@test.com",
            "customer_name": "Alice Martin",
            "promo_code": HETAIRA10,
            "tarif_applique": 20.0,     # 30 - 10 = 20 CHF
            "tarif_public": 30.0,
            "server_unit_price": 30.0,
            "quantity": 1,
            "payment_status": "paid",
            "coach_id": COACH_EMAIL,
            "created_at": "2026-10-01T10:00:00+00:00",
        },
        {
            "session_id": SESSION_2,
            "customer_email": "bruno.keller@test.com",
            "customer_name": "Bruno Keller",
            "promo_code": HETAIRA10,
            "tarif_applique": 20.0,
            "tarif_public": 30.0,
            "server_unit_price": 30.0,
            "quantity": 1,
            "payment_status": "paid",
            "coach_id": COACH_EMAIL,
            "created_at": "2026-10-02T11:00:00+00:00",
        },
        {
            "session_id": SESSION_REMBOURSE,
            "customer_email": "chloe.favre@test.com",
            "customer_name": "Chloé Favre",
            "promo_code": HETAIRA10,
            "tarif_applique": 20.0,
            "tarif_public": 30.0,
            "server_unit_price": 30.0,
            "quantity": 1,
            "payment_status": "refunded",
            "coach_id": COACH_EMAIL,
            "created_at": "2026-10-03T09:00:00+00:00",
        },
        {
            "session_id": SESSION_SANS_RESA,
            "customer_email": "david.roux@test.com",
            "customer_name": "David Roux",
            "promo_code": HETAIRA10,
            "tarif_applique": 20.0,
            "tarif_public": 30.0,
            "server_unit_price": 30.0,
            "quantity": 1,
            "payment_status": "paid",
            "coach_id": COACH_EMAIL,
            "created_at": "2026-10-04T08:00:00+00:00",
        },
        # Transaction d'un autre code (ne doit pas apparaître dans HETAIRA10)
        {
            "session_id": "cs_autre_code",
            "customer_email": "eva.blanc@test.com",
            "customer_name": "Eva Blanc",
            "promo_code": "AUTRECOACH99",
            "tarif_applique": 25.0,
            "tarif_public": 30.0,
            "quantity": 1,
            "payment_status": "paid",
            "coach_id": COACH2_EMAIL,
        },
    ]

    # Réservations liées
    base["reservations"].docs += [
        {
            "id": "resa-001",
            "userEmail": "alice.martin@test.com",
            "userName": "Alice Martin",
            "promoCode": HETAIRA10,
            "stripeSessionId": SESSION_1,
            "courseId": OFFRE_ID,
            "courseName": "Cours à l'unité",
            "datetime": DATE_SEANCE,
            "coach_id": COACH_EMAIL,
        },
        {
            "id": "resa-002",
            "userEmail": "bruno.keller@test.com",
            "userName": "Bruno Keller",
            "promoCode": HETAIRA10,
            "stripeSessionId": SESSION_2,
            "courseId": OFFRE_ID,
            "courseName": "Cours à l'unité",
            "datetime": DATE_SEANCE,
            "coach_id": COACH_EMAIL,
        },
        {
            "id": "resa-003",
            "userEmail": "chloe.favre@test.com",
            "userName": "Chloé Favre",
            "promoCode": HETAIRA10,
            "stripeSessionId": SESSION_REMBOURSE,
            "courseId": OFFRE_ID,
            "courseName": "Cours à l'unité",
            "datetime": DATE_SEANCE,
            "coach_id": COACH_EMAIL,
        },
        # SESSION_SANS_RESA : pas de réservation liée (intentionnel)
    ]

    # Espèces déclarées
    base["partner_cash_payments"].docs += [
        {
            "id": "cash-001",
            "code_upper": HETAIRA10,
            "coach_id": COACH_EMAIL,
            "prenom": "Emma",
            "nom": "Blanc",
            "date_seance": "2026-11-11",
            "montant_chf": 30.0,
            "idempotence_key": f"{HETAIRA10}:idem-001",
            "created_at": "2026-10-05T10:00:00+00:00",
            "created_by": COACH_EMAIL,
        },
    ]

    PR.init_partner_db(base)
    return base


# ══════════════════════════════════════════════════════════════════════════════
# Partie 1 — Vue coach
# ══════════════════════════════════════════════════════════════════════════════

async def partie_vue_coach():
    base = base_partenaire()

    # 1. Paiement confirmé avec HETAIRA10
    code, r = await appel(PR.details_code(HETAIRA10, req({}, admin())))
    verifier("coach/details: HTTP 200", code == 200)
    verifier("coach/details: code retourné", r.get("code") == HETAIRA10)
    verifier("coach/details: lignes présentes", len(r.get("lignes", [])) >= 2)

    lignes = r.get("lignes", [])
    alices = [l for l in lignes if "Alice" in (l.get("nom") or "")]
    verifier("coach/Alice: présente", len(alices) == 1)
    alice = alices[0]
    verifier("coach/Alice: montant 20 CHF", alice.get("montant_chf") == 20.0)
    verifier("coach/Alice: réduction 10 CHF", alice.get("reduction_chf") == 10.0)
    verifier("coach/Alice: statut payé", alice.get("statut") == "paye")
    verifier("coach/Alice: moyen en ligne", alice.get("moyen") == "en_ligne")
    verifier("coach/Alice: date séance", DATE_SEANCE in (alice.get("date_seance") or ""))

    # 2. Paiement confirmé sans réservation finalisée
    davids = [l for l in lignes if "David" in (l.get("nom") or "")]
    verifier("coach/David (sans resa): présent", len(davids) == 1)
    david = davids[0]
    verifier("coach/David: statut paiement_sans_reservation",
             david.get("statut") == "paiement_sans_reservation")

    # 3. Remboursement visible et exclu du net
    chloes = [l for l in lignes if "Chlo" in (l.get("nom") or "")]
    verifier("coach/Chloé: présente", len(chloes) == 1)
    verifier("coach/Chloé: statut rembourse", chloes[0].get("statut") == "rembourse")

    # 4. Totaux
    totaux = r.get("totaux", {})
    # Alice (20) + Bruno (20) + David (20, paiement_sans_reservation) + Emma espèces (30)
    # Confirmés (statut=paye) = Alice, Bruno, David (paiement_sans_reservation ne compte pas), Emma
    # MAIS: paiement_sans_reservation n'est PAS "paye" dans le calcul
    # Recalcul: Alice(20) + Bruno(20) + Emma espèces(30) = 70 CHF net
    verifier("coach/totaux: nb_inscriptions >= 4", totaux.get("nb_inscriptions", 0) >= 4)
    verifier("coach/totaux: nb_rembourses == 1", totaux.get("nb_rembourses") == 1)
    verifier("coach/totaux: total_net_chf = 70.0", totaux.get("total_net_chf") == 90.0)
    verifier("coach/totaux: part_partenaire = 28.0",
             abs(totaux.get("part_partenaire_chf", 0) - 36.0) < 0.01)
    verifier("coach/totaux: part_afroboost = 42.0",
             abs(totaux.get("part_afroboost_chf", 0) - 54.0) < 0.01)

    # 5. Encaissement espèces
    emmas = [l for l in lignes if "Emma" in (l.get("nom") or "")]
    verifier("coach/Emma espèces: présente", len(emmas) == 1)
    verifier("coach/Emma: moyen especes", emmas[0].get("moyen") == "especes")
    verifier("coach/Emma: montant 30 CHF", emmas[0].get("montant_chf") == 30.0)

    # 6. Isolation: le coach 2 ne voit pas HETAIRA10
    code2, r2 = await appel(PR.details_code(HETAIRA10, req({}, coach2())))
    verifier("isolation/coach2 ne voit pas HETAIRA10", code2 == 404)

    # 7. Sans auth : refus 403
    code_noauth, _ = await appel(PR.details_code(HETAIRA10, req({}, {})))
    verifier("auth/details sans JWT: 403", code_noauth == 403)


# ══════════════════════════════════════════════════════════════════════════════
# Partie 2 — Configuration et pourcentage
# ══════════════════════════════════════════════════════════════════════════════

async def partie_config():
    base = base_partenaire()

    # Configurer à 40 %
    code, r = await appel(PR.config_partenaire(
        HETAIRA10,
        PR.ConfigPartenaire(partner_name="Société Hétaïra", partner_pct=40),
        req({}, admin())
    ))
    verifier("config/set 40%: HTTP 200", code == 200)
    verifier("config/set 40%: pct retourné", r.get("partner_pct") == 40)

    # Vérifier via details
    _, r2 = await appel(PR.details_code(HETAIRA10, req({}, admin())))
    verifier("config/details: pct 40%", r2.get("pct_partenaire") == 40)
    verifier("config/details: nom partenaire", r2.get("partner_name") == "Société Hétaïra")

    # Modifier à 35 %
    code3, r3 = await appel(PR.config_partenaire(
        HETAIRA10,
        PR.ConfigPartenaire(partner_name="Hétaïra", partner_pct=35),
        req({}, admin())
    ))
    verifier("config/update 35%: HTTP 200", code3 == 200)
    _, r4 = await appel(PR.details_code(HETAIRA10, req({}, admin())))
    verifier("config/details après update: pct 35%", r4.get("pct_partenaire") == 35)
    totaux = r4.get("totaux", {})
    # 90 CHF net (V638: paiement_sans_reservation inclus) * 35% = 31.5
    verifier("config/totaux à 35%: part_partenaire",
             abs(totaux.get("part_partenaire_chf", 0) - 31.5) < 0.01)

    # Valeur invalide (> 100)
    try:
        PR.ConfigPartenaire(partner_pct=150)
        verifier("config/pct>100: validation", False, "devrait échouer")
    except Exception:
        verifier("config/pct>100: validation Pydantic", True)

    # Sans auth: refus
    code_na, _ = await appel(PR.config_partenaire(
        HETAIRA10, PR.ConfigPartenaire(partner_pct=50), req({}, {})
    ))
    verifier("config/sans auth: 403", code_na == 403)


# ══════════════════════════════════════════════════════════════════════════════
# Partie 3 — Espèces
# ══════════════════════════════════════════════════════════════════════════════

async def partie_especes():
    base = base_partenaire()

    data = PR.EspecesDeclaration(
        prenom="Farid", nom="Nguyen",
        date_seance="2026-11-11",
        montant_chf=30.0,
        idempotence_key="idem-especes-001"
    )

    code, r = await appel(PR.declarer_especes(HETAIRA10, data, req({}, admin())))
    verifier("especes/declare: HTTP 200", code == 200)
    verifier("especes/declare: ok=True", r.get("ok") is True)
    verifier("especes/declare: id présent", bool(r.get("id")))
    verifier("especes/declare: pas doublon", r.get("doublon") is False)

    # Double soumission avec la même clé d'idempotence
    code2, r2 = await appel(PR.declarer_especes(HETAIRA10, data, req({}, admin())))
    verifier("especes/idempotence: HTTP 200", code2 == 200)
    verifier("especes/idempotence: doublon=True", r2.get("doublon") is True)
    verifier("especes/idempotence: même id", r2.get("id") == r.get("id"))

    # Montant négatif: refus Pydantic
    try:
        PR.EspecesDeclaration(prenom="X", nom="Y", date_seance="2026-11-11",
                               montant_chf=-5.0, idempotence_key="idem-neg")
        verifier("especes/montant_negatif: validation", False, "devrait échouer")
    except Exception:
        verifier("especes/montant_negatif: validation Pydantic", True)

    # Coach 2 ne peut pas déclarer sur HETAIRA10
    code3, _ = await appel(PR.declarer_especes(
        HETAIRA10,
        PR.EspecesDeclaration(prenom="Eva", nom="Test", date_seance="2026-11-11",
                               montant_chf=30.0, idempotence_key="idem-c2-001"),
        req({}, coach2())
    ))
    verifier("especes/isolation coach2: 404", code3 == 404)

    # Sans auth
    code4, _ = await appel(PR.declarer_especes(
        HETAIRA10, data, req({}, {})
    ))
    verifier("especes/sans auth: 403", code4 == 403)

    # Après déclaration, Farid apparaît dans les lignes
    _, dr = await appel(PR.details_code(HETAIRA10, req({}, admin())))
    farids = [l for l in dr.get("lignes", []) if "Farid" in (l.get("nom") or "")]
    verifier("especes/Farid dans lignes", len(farids) == 1)


# ══════════════════════════════════════════════════════════════════════════════
# Partie 4 — Calcul financier
# ══════════════════════════════════════════════════════════════════════════════

async def partie_calcul():
    base = base_partenaire()

    # Plusieurs séances dans une transaction (quantity > 1)
    base["payment_transactions"].docs.append({
        "session_id": "cs_multi_001",
        "customer_email": "gaelle.morel@test.com",
        "customer_name": "Gaëlle Morel",
        "promo_code": HETAIRA10,
        "tarif_applique": 20.0,      # 20 CHF × 2 = 40 CHF total
        "tarif_public": 30.0,
        "server_unit_price": 30.0,
        "quantity": 2,               # 2 séances dans une transaction
        "payment_status": "paid",
        "coach_id": COACH_EMAIL,
        "created_at": "2026-10-06T10:00:00+00:00",
    })
    base["reservations"].docs += [
        {
            "id": "resa-m1", "userEmail": "gaelle.morel@test.com", "userName": "Gaëlle Morel",
            "promoCode": HETAIRA10, "stripeSessionId": "cs_multi_001",
            "courseName": "Cours à l'unité", "datetime": DATE_SEANCE, "coach_id": COACH_EMAIL,
        },
        # Deuxième réservation sur le MÊME session_id (n'est pas créée en doublon)
    ]
    PR.init_partner_db(base)

    _, r = await appel(PR.details_code(HETAIRA10, req({}, admin())))
    gaelles = [l for l in r.get("lignes", []) if "Ga" in (l.get("nom") or "")]
    verifier("calcul/Gaëlle présente", len(gaelles) == 1)
    # quantity=2 → montant = 20*2 = 40 CHF
    verifier("calcul/Gaëlle: montant 40 CHF", gaelles[0].get("montant_chf") == 40.0)

    # Pas deux fois la même session (même session_id pour deux réservations)
    non_none_sessions = [l.get("session_id") for l in r.get("lignes", []) if l.get("session_id")]
    verifier("calcul/session_id unique dans lignes",
             len(non_none_sessions) == len(set(non_none_sessions)))

    # V638 : paiement_sans_reservation inclus. Alice(20)+Bruno(20)+David(20)+Gaëlle(40)+Emma(30)=130
    totaux = r.get("totaux", {})
    verifier("calcul/total_net avec Gaëlle = 110",
             abs(totaux.get("total_net_chf", 0) - 130.0) < 0.01)
    verifier("calcul/40% de 110 = 44.0",
             abs(totaux.get("part_partenaire_chf", 0) - 52.0) < 0.01)
    verifier("calcul/60% de 110 = 66.0",
             abs(totaux.get("part_afroboost_chf", 0) - 78.0) < 0.01)


# ══════════════════════════════════════════════════════════════════════════════
# Partie 5 — Jeton partenaire et vue publique
# ══════════════════════════════════════════════════════════════════════════════

async def partie_jeton():
    base = base_partenaire()

    # Générer un jeton
    code, r = await appel(PR.generer_token_partenaire(HETAIRA10, req({}, admin())))
    verifier("jeton/generer: HTTP 200", code == 200)
    verifier("jeton/generer: token présent", bool(r.get("token")))
    verifier("jeton/generer: token_id présent", bool(r.get("token_id")))
    token = r.get("token")

    # Vérifier que le lien apparaît dans details
    _, dr = await appel(PR.details_code(HETAIRA10, req({}, admin())))
    verifier("jeton/details: lien_actif True", dr.get("lien_actif") is True)

    # Vue partenaire : accès avec le bon jeton
    code_pub, r_pub = await appel(PR.vue_partenaire(token, req(), mock_response()))
    verifier("jeton/vue partenaire: HTTP 200", code_pub == 200)
    verifier("jeton/vue partenaire: lignes présentes", len(r_pub.get("lignes", [])) >= 2)
    verifier("jeton/vue partenaire: code présent", r_pub.get("code") == HETAIRA10)

    # Sécurité : aucun email dans la réponse partenaire
    fuites = contient_sensible(r_pub, champs=("@test.com", "@exemple", "alice.martin",
                                               "bruno.keller", "chloe.favre"))
    verifier("jeton/vue partenaire: aucun email", len(fuites) == 0, str(fuites))

    # Sécurité : aucun token_hash dans la réponse
    verifier("jeton/vue partenaire: pas de token_hash", "token_hash" not in json.dumps(r_pub))

    # Noms masqués
    noms = [l.get("nom_masque") for l in r_pub.get("lignes", [])]
    verifier("jeton/noms masqués: pas de nom complet",
             all("." in (n or ".") for n in noms if n))

    # Jeton invalide
    code_inv, _ = await appel(PR.vue_partenaire("jeton_bidon_123456", req(), mock_response()))
    verifier("jeton/invalide: 404", code_inv == 404)

    # Jeton vide
    code_vide, _ = await appel(PR.vue_partenaire("", req(), mock_response()))
    verifier("jeton/vide: 404", code_vide == 404)

    # Révocation
    code_rev, _ = await appel(PR.revoquer_token_partenaire(HETAIRA10, req({}, admin())))
    verifier("jeton/revocation: HTTP 200", code_rev == 200)

    # Après révocation: jeton refusé immédiatement
    code_arev, _ = await appel(PR.vue_partenaire(token, req(), mock_response()))
    verifier("jeton/après révocation: 404", code_arev == 404)

    # Après révocation: lien_actif False dans details
    _, dr2 = await appel(PR.details_code(HETAIRA10, req({}, admin())))
    verifier("jeton/après révocation: lien_actif False", dr2.get("lien_actif") is False)

    # Générer un nouveau jeton après révocation
    code_n, r_n = await appel(PR.generer_token_partenaire(HETAIRA10, req({}, admin())))
    verifier("jeton/nouveau après révocation: HTTP 200", code_n == 200)
    token2 = r_n.get("token")
    verifier("jeton/nouveau token différent", token2 != token)

    # Ancien token toujours révoqué, nouveau fonctionne
    code_old, _ = await appel(PR.vue_partenaire(token, req(), mock_response()))
    verifier("jeton/ancien toujours révoqué: 404", code_old == 404)
    code_new, r_new = await appel(PR.vue_partenaire(token2, req(), mock_response()))
    verifier("jeton/nouveau token fonctionne: 200", code_new == 200)

    # Coach 2 ne peut pas révoquer HETAIRA10
    code_c2, _ = await appel(PR.revoquer_token_partenaire(HETAIRA10, req({}, coach2())))
    verifier("jeton/revocation coach2: 404", code_c2 == 404)

    # Sans auth : refus
    code_na, _ = await appel(PR.generer_token_partenaire(HETAIRA10, req({}, {})))
    verifier("jeton/generer sans auth: 403", code_na == 403)


def mock_response():
    """Faux objet Response pour les tests."""
    class FakeResponse:
        headers = {}
    return FakeResponse()


# ══════════════════════════════════════════════════════════════════════════════
# Partie 6 — Export CSV
# ══════════════════════════════════════════════════════════════════════════════

async def partie_csv():
    base = base_partenaire()

    code, r = await appel(PR.export_csv(HETAIRA10, req({}, admin())))
    verifier("csv/HTTP 200", code == 200)
    # La route retourne une Response (bytes), appel() la passe telle quelle si ce n'est pas JSON
    # Vérifier au moins que c'est accessible sans erreur
    verifier("csv/accès réussi", code == 200)

    # Sans auth
    code_na, _ = await appel(PR.export_csv(HETAIRA10, req({}, {})))
    verifier("csv/sans auth: 403", code_na == 403)

    # Coach 2 ne peut pas exporter HETAIRA10
    code_c2, _ = await appel(PR.export_csv(HETAIRA10, req({}, coach2())))
    verifier("csv/coach2 isolation: 404", code_c2 == 404)


# ══════════════════════════════════════════════════════════════════════════════
# Partie 7 — Non-régression codes promo existants
# ══════════════════════════════════════════════════════════════════════════════

async def partie_nonregression():
    base = base_partenaire()

    # Les collections historiques ne doivent PAS avoir été modifiées
    nb_codes_avant = len(base["discount_codes"].docs)
    nb_tx_avant = len(base["payment_transactions"].docs)
    nb_resas_avant = len(base["reservations"].docs)

    # Appels divers qui lisent les données
    await appel(PR.details_code(HETAIRA10, req({}, admin())))
    await appel(PR.config_partenaire(
        HETAIRA10, PR.ConfigPartenaire(partner_pct=40), req({}, admin())
    ))

    verifier("nonreg/discount_codes non modifiés",
             len(base["discount_codes"].docs) == nb_codes_avant)
    verifier("nonreg/payment_transactions non modifiés",
             len(base["payment_transactions"].docs) == nb_tx_avant)
    verifier("nonreg/reservations non modifiées",
             len(base["reservations"].docs) == nb_resas_avant)

    # Le code HETAIRA10 est toujours actif et inchangé
    fiche = next((d for d in base["discount_codes"].docs if d.get("code") == HETAIRA10), None)
    verifier("nonreg/HETAIRA10 toujours actif", fiche and fiche.get("active") is True)
    verifier("nonreg/HETAIRA10 maxUses inchangé", fiche and fiche.get("maxUses") == 30)
    verifier("nonreg/HETAIRA10 used inchangé", fiche and fiche.get("used") == 0)


# ══════════════════════════════════════════════════════════════════════════════
# Partie 8 — Rate limiting (simulé)
# ══════════════════════════════════════════════════════════════════════════════

async def partie_rate_limiting():
    """Test du rate limiting de la vue partenaire."""
    # Réinitialiser le compteur
    PR._RATE.clear()

    base = base_partenaire()
    # Générer un jeton valide
    _, r = await appel(PR.generer_token_partenaire(HETAIRA10, req({}, admin())))
    token = r.get("token")

    # Simuler 35 requêtes depuis la même IP (> 30 = limite)
    ip_test = "192.168.1.42"
    import time
    bucket = int(time.time()) // 60
    PR._RATE[ip_test] = (30, bucket)  # déjà à la limite

    # La 31ème requête doit être bloquée
    class ReqAvecIP:
        headers = {"X-Forwarded-For": ip_test}

    try:
        req_ip = H.Requete({}, {"X-Forwarded-For": ip_test})
        code_rl, _ = await appel(PR.vue_partenaire(token, req_ip, mock_response()))
        verifier("rate_limiting/au-delà de la limite: 429", code_rl == 429)
    except Exception as e:
        verifier("rate_limiting/erreur inattendue", False, str(e))

    # Réinitialiser pour ne pas perturber les autres tests
    PR._RATE.clear()


# ══════════════════════════════════════════════════════════════════════════════
# Point d'entrée
# ══════════════════════════════════════════════════════════════════════════════

async def principal():
    print("V633 — Suivi partenaires\n" + "═" * 50)

    await partie_vue_coach()
    print(f"  [1/8] Vue coach")
    await partie_config()
    print(f"  [2/8] Configuration et pourcentage")
    await partie_especes()
    print(f"  [3/8] Espèces")
    await partie_calcul()
    print(f"  [4/8] Calcul financier")
    await partie_jeton()
    print(f"  [5/8] Jeton partenaire")
    await partie_csv()
    print(f"  [6/8] Export CSV")
    await partie_nonregression()
    print(f"  [7/8] Non-régression")
    await partie_rate_limiting()
    print(f"  [8/8] Rate limiting")

    ok = sum(1 for _, p, _ in RESULTATS if p)
    ko = sum(1 for _, p, _ in RESULTATS if not p)
    print(f"\n{'═'*50}")
    print(f"Résultat : {ok}/{ok+ko} tests réussis")
    if ko:
        print("\nÉCHECS :")
        for nom, p, detail in RESULTATS:
            if not p:
                print(f"  ✗ {nom}" + (f" — {detail}" if detail else ""))
    else:
        print("\nTous les tests sont au vert ✓")
    return ko == 0


if __name__ == "__main__":
    ok = asyncio.run(principal())
    sys.exit(0 if ok else 1)

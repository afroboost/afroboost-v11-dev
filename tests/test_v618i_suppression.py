#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618i — SUPPRESSION FIABLE D'UN ABONNEMENT + ANTI-DOUBLON + ANTI-FUITE.

Banc permanent, sans réseau, données SYNTHÉTIQUES : vraies routes (promo_routes, abonnement_actuel,
server), vrais jetons signés, base en mémoire. Scénarios A à P de la demande + gardes de réactivation.

Lancement : python3 tests/test_v618i_suppression.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement : JWT_SECRET de banc, api.server)

import pymongo.errors  # noqa: E402
pymongo.errors.DuplicateKeyError = H.DuplicateKeyError      # le faux Mongo lève SA classe

S = H.S
import api.routes.abonnement_actuel as AA  # noqa: E402
import api.routes.promo_routes as PR  # noqa: E402
import api.routes.evenement_special as EVS  # noqa: E402
import api.routes.hiver as HIV  # noqa: E402
from api.routes import shared as SH  # noqa: E402

RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


ADMIN = SH.SUPER_ADMIN_EMAILS[0]
COACH_P = "coach.p@partenaire.example"
C1, C2, C3, C4 = "client.un@t.example", "client.deux@t.example", "client.trois@t.example", "client.quatre@t.example"
FUTUR = "2027-05-05T23:59:59+00:00"
DEMAIN = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT18:30:00")
HIER = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT18:30:00")


def sub(i, code, email, status="active", exp=FUTUR, total=10, used=2, coach="", **extra):
    d = {"id": i, "code": code, "email": email, "status": status, "expires_at": exp, "total_sessions": total,
         "used_sessions": used, "remaining_sessions": total - used, "created_at": "2026-05-01", "coach_id": coach,
         "offer_name": "PULSE x10"}
    d.update(extra)
    return d


def fiche(i, code, titulaire, coach=None, exp="2027-05-05", **extra):
    d = {"id": i, "code": code, "assignedEmail": titulaire, "active": True, "expiresAt": exp, "maxUses": 10, "used": 2,
         "type": "CHF", "value": 30, "coach_id": coach}
    d.update(extra)
    return d


def req(email=ADMIN, corps=None):
    return H.Requete(corps or {}, {"Authorization": "Bearer " + H.jeton_admin(email)})


def le(base, coll, cle, val):
    return next((d for d in base[coll].docs if d.get(cle) == val), None)


def monde():
    base = H._Base()
    base["coaches"].docs += [{"id": "cp", "email": COACH_P, "name": "Coach P"}]
    base["discount_codes"].docs += [
        fiche("f1", "AFR-C1", C1, montant_encaisse=100.0, origine_paiement="twint"),
        fiche("f2a", "AFR-C2A", C2), fiche("f2b", "AFR-C2B", C2),
        fiche("fp", "AFR-PART", C4, coach=COACH_P),
    ]
    base["subscriptions"].docs += [
        sub("s1", "AFR-C1", C1, montant_encaisse=100.0, offer_id="OFF-8M"),
        sub("s2a", "AFR-C2A", C2), sub("s2b", "AFR-C2B", C2, exp="2026-12-31T23:59:59+00:00"),
        sub("sp", "AFR-PART", C4, coach=COACH_P),
        sub("so", "AFR-ORPHELIN", C3),                              # fiche supprimée AVANT V618i
    ]
    base["reservations"].docs += [
        {"id": "r-passe", "userEmail": C1, "discountCode": "AFR-C1", "datetime": HIER, "subscriptionId": "s1"},
        {"id": "r-futur", "userEmail": C1, "discountCode": "AFR-C1", "datetime": DEMAIN, "subscriptionId": "s1"},
    ]
    base["seance_mouvements"].docs.append({"_id": "debit:r-passe", "code": "AFR-C1", "statut": "applique"})
    _j, _jti = SH.lotb3s1_make_token("AFR-C1", C1, S.DEFAULT_COACH_ID, None)
    base[S._B3S1_COLL_SESSIONS].docs.append({"jti": _jti, "code": "AFR-C1", "email": C1, "coach_id": S.DEFAULT_COACH_ID,
                                             "slug": "", "revoked": False,
                                             "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()})
    for m in (S, PR, AA):
        pass
    S.db = base
    PR._db = base
    AA.init_db(base)
    return base, _j


async def principal():
    base, ancien_jeton = monde()

    EVT = {"id": "EVT", "gratuit_abonnements_offer_ids": ["OFF-8M"]}
    DEBUT = datetime(2026, 10, 28, 16, 0, tzinfo=timezone.utc)
    g0 = await EVS.abonnement_gratuit(base, C1, EVT, DEBUT)
    verifier("H0 témoin : AVANT suppression, l'abonnement donne bien la place offerte", g0 and g0.get("id") == "s1", g0)

    # ── aperçu + suppression (A, M, N) ──────────────────────────────────────────────
    c, ap = await H.appel(PR.apercu_suppression_code("f1", req()))
    verifier("A0 aperçu : client, abonnement, séances restantes, expiration, historique (paiement + réservations)",
             c == 200 and ap["client"] == C1 and ap["seances_restantes"] == 8 and ap["expiration"] == "2027-05-05"
             and ap["abonnements_supprimes"] == 1 and ap["historique"]["conserve"] is True
             and ap["historique"]["reservations_passees"] == 1 and ap["historique"]["reservations_futures"] == 1, ap)
    c, r = await H.appel(PR.delete_discount_code("f1", req()))
    s1 = le(base, "subscriptions", "id", "s1")
    verifier("A supprimer -> abonnement en pierre tombale `deleted`, AUCUN abonnement actuel ensuite",
             c == 200 and s1["status"] == "deleted" and r["etat_apres"] == "aucun" and r["abonnement_actuel_apres"] is None, r)
    verifier("M paiements conservés (montant encaissé intact sur l'abonnement)", s1.get("montant_encaisse") == 100.0
             and s1["used_sessions"] == 2 and s1["total_sessions"] == 10)
    verifier("N réservations et mouvements conservés (historique)",
             le(base, "reservations", "id", "r-passe") and le(base, "reservations", "id", "r-futur")
             and base["seance_mouvements"].docs)
    verifier("A2 fiche à la corbeille avec la liste des abonnements supprimés (restauration possible)",
             not le(base, "discount_codes", "id", "f1")
             and any((x.get("related") or {}).get("abonnements_supprimes") == ["s1"] for x in base["deleted_items"].docs))

    # ── ne revient JAMAIS (B à H) ─────────────────────────────────────────────────────
    r1 = await AA.resoudre_abonnement_actuel(base, C1, notifier=False)
    verifier("B refresh : le résolveur ne le voit plus (ni actuel, ni historique)", r1["etat"] == "aucun" and r1["dernier"] is None)
    sess = le(base, S._B3S1_COLL_SESSIONS, "code", "AFR-C1")
    charge, motif = await S._b3s13_porteur_autorise(H.Requete({}, {"x-espace-token": ancien_jeton}), "AFR-C1", "")
    verifier("C déconnexion/reconnexion : la session d'espace ouverte est révoquée, l'ancien jeton refusé",
             sess["revoked"] is True and charge is None, motif)
    acc = await AA.fiches_pour_acces(base, C1)
    verifier("D ancien e-mail d'accès : aucune fiche, aucun code proposé", acc["fiches"] == [])
    verifier("E ancien QR / F ancien code : aucune lecture de l'abonnement supprimé (espace, scan, recharge)",
             await SH.lire_abonnement_par_code(base, "AFR-C1") is None)
    v = await PR.validate_discount_code({"code": "AFR-C1", "email": C1})
    verifier("F2 ancien code saisi dans le chat / la vitrine : refusé", v.get("valid") is False)
    st = await PR.get_subscription_status(H.Requete(), email=C1)
    verifier("G ChatWidget (/subscriptions/status) : plus d'abonnement", st.get("success") is False
             and not st.get("current_subscription"))
    g = await EVS.abonnement_gratuit(base, C1, EVT, DEBUT)
    verifier("H événement : l'abonnement supprimé ne donne aucune place offerte", g is None)
    verifier("H2 OTP : jamais l'adresse d'un abonnement supprimé",
             AA.contact_otp([], [s1], C1) == (None, None))

    # ── un autre abonnement actif légitime reste l'actuel ─────────────────────────────
    c, r = await H.appel(PR.delete_discount_code("f2b", req()))
    verifier("A3 client avec deux abonnements : supprimer l'un -> l'AUTRE devient l'actuel (vérification serveur)",
             c == 200 and r["abonnement_actuel_apres"] == "AFR-C2A", r)

    # ── jamais réactivé ──────────────────────────────────────────────────────────────
    c, _ = await H.appel(PR.update_subscription("s1", {"status": "active"}, req()))
    verifier("R1 PUT /subscriptions : un abonnement supprimé ne se remet pas « active » (409)", c == 409
             and le(base, "subscriptions", "id", "s1")["status"] == "deleted")
    verifier("R2 annulation / restitution : jamais réactivé", AA.statut_apres_restitution(s1) is None)
    base["subscriptions"].docs.append(sub("sh-strip", "HIV-1", "h@t.example", status="deleted", stripe_subscription_id="sub_x"))
    rh = await HIV.traiter_facture_payee(base, {"subscription": "sub_x", "id": "in_1", "billing_reason": "subscription_cycle"})
    verifier("R3 facture Stripe : aucun crédit, aucune réactivation", rh["motif"] == "abonnement_supprime"
             and le(base, "subscriptions", "id", "sh-strip")["status"] == "deleted", rh)
    _cid = next(x["id"] for x in base["deleted_items"].docs if (x.get("related") or {}).get("abonnements_supprimes") == ["s1"])
    c, _ = await H.appel(S.restore_trash(_cid, req(COACH_P)))
    verifier("14 restauration par un coach : refusée (403)", c == 403)
    c, d = await H.appel(S.restore_trash(_cid, req()))
    verifier("14b super-admin sans confirmation explicite : refusée (409)", c == 409 and le(base, "subscriptions", "id", "s1")["status"] == "deleted")

    # ── création : anti-doublon, remplacement, idempotence, concurrence (I à L) ─────
    corps = {"code": "AFR-C2N", "type": "CHF", "value": 30, "assignedEmail": C2, "maxUses": 10,
             "expiresAt": "2027-06-30", "montant_encaisse": 150, "origine_paiement": "twint", "idempotency_key": "k-i"}
    c, d = await H.appel(PR.create_discount_code(PR.DiscountCodeCreate(**corps), req()))
    verifier("I client avec un abonnement actif : JAMAIS un second en silence (409 « déjà un abonnement actif »)",
             c == 409 and d["detail"]["type"] == "droits_existants" and "déjà un abonnement actif" in d["detail"]["message"], d)
    c, d = await H.appel(PR.create_discount_code(PR.DiscountCodeCreate(**dict(corps, remplacer_abonnement_actuel=True)), req()))
    r2 = await AA.resoudre_abonnement_actuel(base, C2, notifier=False)
    actuels = [x for x in base["subscriptions"].docs if x.get("email") == C2 and AA.est_courant(x)]
    verifier("L renouvellement : ancien en historique (superseded), nouveau actuel, UN SEUL actuel",
             c == 200 and le(base, "subscriptions", "id", "s2a")["status"] == "superseded"
             and r2["etat"] == "courant" and r2["abonnement"]["code"] == "AFR-C2N" and len(actuels) == 1, (c, d, r2["etat"]))
    verifier("L2 l'ancien garde ses compteurs et sa trace de remplacement",
             le(base, "subscriptions", "id", "s2a")["used_sessions"] == 2
             and le(base, "subscriptions", "id", "s2a")["superseded_reason"] == "remplacement_coach")
    n0 = len(base["subscriptions"].docs)
    c, d = await H.appel(PR.create_discount_code(PR.DiscountCodeCreate(**dict(corps, remplacer_abonnement_actuel=True)), req()))
    verifier("J double clic (même clé) : le code déjà créé est renvoyé, aucun second abonnement",
             c == 200 and len(base["subscriptions"].docs) == n0, (c, len(base["subscriptions"].docs), n0))
    corps_k = {"code": "AFR-K1", "type": "CHF", "value": 30, "assignedEmail": "nouveau@t.example", "maxUses": 10,
               "expiresAt": "2027-06-30", "montant_encaisse": 150, "origine_paiement": "twint"}
    res = await asyncio.gather(
        H.appel(PR.create_discount_code(PR.DiscountCodeCreate(**dict(corps_k, idempotency_key="ka")), req())),
        H.appel(PR.create_discount_code(PR.DiscountCodeCreate(**dict(corps_k, code="AFR-K2", idempotency_key="kb")), req())))
    nouv = [x for x in base["subscriptions"].docs if x.get("email") == "nouveau@t.example"]
    verifier("K deux requêtes simultanées (clés différentes) pour le même client : UN seul abonnement",
             len(nouv) == 1 and sorted(c for c, _ in res) == [200, 409], [c for c, _ in res])
    verifier("K2 aucun verrou ne reste posé après coup", not [x for x in base["abonnement_verrous"].docs
                                                              if str(x.get("_id")).startswith("personne:")])

    # ── anti-fuite coach A -> coach B (O) ─────────────────────────────────────────────
    c, _ = await H.appel(PR.delete_discount_code("f2a", req(COACH_P)))
    verifier("O coach partenaire supprime l'abonnement de la plateforme : 403", c == 403 and le(base, "discount_codes", "id", "f2a"))
    c, _ = await H.appel(PR.apercu_suppression_code("f2a", req(COACH_P)))
    verifier("O2 … ni même l'aperçu (client, séances) : 403", c == 403)
    c, _ = await H.appel(PR.update_subscription("s2a", {"remaining_sessions": 99}, req(COACH_P)))
    verifier("O3 … ni la modification d'un abonnement de la plateforme (sans coach_id) : 403", c == 403)
    c, liste = await H.appel(PR.get_discount_codes(req(COACH_P)))
    verifier("O4 liste des codes du partenaire : SES codes seulement (plus les fiches de la plateforme)",
             c == 200 and {x.get("code") for x in liste} == {"AFR-PART"}, [x.get("code") for x in liste] if c == 200 else liste)
    c, _ = await H.appel(AA.supprimer_abonnement_orphelin("so", req(COACH_P)))
    verifier("O5 abonnement orphelin de la plateforme : le partenaire ne peut pas le supprimer (403)", c == 403)
    c, d = await H.appel(AA.abonnements_orphelins(req(COACH_P)))
    verifier("O6 … ni le voir dans sa liste", c == 200 and d["orphelins"] == [], d)

    # ── abonnements orphelins (supprimés avant V618i) ─────────────────────────────────
    c, d = await H.appel(AA.abonnements_orphelins(req()))
    verifier("Q1 super-admin : l'abonnement resté actif sans code est listé (actuel)",
             c == 200 and [x["code"] for x in d["orphelins"]] == ["AFR-ORPHELIN"] and d["orphelins"][0]["courant"], d)
    c, d = await H.appel(AA.supprimer_abonnement_orphelin("so", req()))
    r3 = await AA.resoudre_abonnement_actuel(base, C3, notifier=False)
    verifier("Q2 suppression par le coach : pierre tombale, plus d'abonnement actuel", c == 200
             and le(base, "subscriptions", "id", "so")["status"] == "deleted" and r3["etat"] == "aucun", d)
    c, _ = await H.appel(AA.supprimer_abonnement_orphelin("s2a", req()))
    verifier("Q3 un abonnement dont le code existe se supprime depuis sa carte (409)", c in (404, 409))

    # ── restauration administrative explicite (super-admin + confirmation) ────────────
    c, d = await H.appel(S.restore_trash(_cid, req(ADMIN, {"confirmer_restauration_abonnement": True})))
    verifier("14c super-admin + confirmation : fiche et abonnement reviennent EXACTEMENT au statut d'avant",
             c == 200 and le(base, "subscriptions", "id", "s1")["status"] == "active"
             and le(base, "discount_codes", "id", "f1") is not None
             and "statut_avant_suppression" not in le(base, "subscriptions", "id", "s1"), (c, d))

    # ── anti-fuite client A -> client B (P) ───────────────────────────────────────────
    st = await PR.get_subscription_status(H.Requete(), email=C2)
    verifier("P sans preuve d'identité : ni nom, ni adresse, ni historique d'un client",
             all("name" not in x and "email" not in x for x in (st.get("subscriptions") or []))
             and st.get("history") == [], st)


def main():
    asyncio.run(principal())
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:700])
        _ok += ok
    print("%d / %d verifications V618i au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

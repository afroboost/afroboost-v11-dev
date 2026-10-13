#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618k — finitions : (1) aucun faux partage quand l'essai est refusé ; (3/4) l'offre réelle d'un
abonnement manuel « 8 mois » (offer_id) à la création ET quand ses articles sont modifiés.

Banc permanent, vraies routes, base en mémoire, données synthétiques.
Lancement : python3 tests/test_v618k_finitions.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_essai_moi_dabord as M  # noqa: E402  (pose le banc V3 + campagnes)

V3, H = M.V3, M.H
R, E = H.R, H.E
appel, req = H.appel, V3.req
import api.routes.promo_routes as PR  # noqa: E402
import api.routes.abonnement_actuel as AA  # noqa: E402
import api.routes.evenement_special as EVS  # noqa: E402

RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


async def creer(tok, cle=None):
    return await appel(R.referral_chaine_creer(tok, req({}, {"X-Chain-Key": cle} if cle else {})))


async def join(tok, cle, email, tel, nom="Jade", canal=None):
    corps = H.corps_ami(email, tel, nom)
    if canal:
        corps["partage_canal"] = canal
    return await appel(R.referral_join(tok, req(corps, {"X-Chain-Key": cle} if cle else {})))


def enfant(base, parent):
    """L'invitation de l'ami ENCORE liée au parent (une invitation libérée n'en fait plus partie)."""
    return next((d for d in base["referral_passes"].docs
                 if (d.get("chain") or {}).get("parent_pass_id") == parent["id"] and d.get("status") != "cancelled"), {})


def partages(base, parent_id):
    return [d for d in base["referral_invitations"].docs if d.get("chain_parent_pass_id") == parent_id] \
        if "referral_invitations" in base._c else []


async def partie_partage():
    base, _ = M.depart()
    # Un membre ACTIF : abonnement courant + fiche (l'essai lui est refusé par la garde commune).
    base["subscriptions"].docs.append({"id": "s-mem", "code": "MEM-1", "email": "membre@exemple.test", "status": "active",
                                       "expires_at": "2027-05-05T23:59:59+00:00", "total_sessions": 64, "used_sessions": 3,
                                       "remaining_sessions": 61, "created_at": "2026-09-01", "coach_id": ""})
    base["discount_codes"].docs.append({"id": "dc-mem", "code": "MEM-1", "assignedEmail": "membre@exemple.test",
                                        "active": True, "expiresAt": "2027-05-05", "maxUses": 64, "used": 3})
    _, r = await M.entree(base)
    t0 = r["share_token"]
    p0 = V3.doc_par_tok(base, t0)
    c, a = await creer(t0)
    cle = a.get("edit_key")
    coll_inv = R.COLL_INVITATIONS
    n_inv = len(base[coll_inv].docs)
    c, j = await join(t0, cle, "membre@exemple.test", "+41791112233", canal="whatsapp")
    p0 = V3.doc_par_tok(base, t0)
    enf = enfant(base, p0)
    verifier("1 membre actif : essai REFUSÉ", c in (403, 409), (c, j))
    verifier("1b … AUCUN partage enregistré (ni compteur, ni « partagée », ni invitation_sent)",
             len(base[coll_inv].docs) == n_inv and not E.chaine_partagee(p0)
             and not any(ev.get("type") == "invitation_sent" for ev in (enf.get("events") or [])),
             (len(base[coll_inv].docs), n_inv, E.chaine_partagee(p0)))
    # Le refus LIBÈRE l'invitation de l'ami (règle existante) : la page en prépare une nouvelle.
    c, a = await creer(t0)
    cle = a.get("edit_key")
    c, j = await join(t0, cle, "nouveau@exemple.test", "+41794445566", nom="Nina", canal="whatsapp")
    p0 = V3.doc_par_tok(base, t0)
    enf = enfant(base, p0)
    verifier("2 non-membre, même invitation : essai accordé", c in (200, 201), (c, j))
    verifier("2b … partage enregistré UNE fois, APRÈS l'octroi (compteur + « partagée » + invitation_sent)",
             len(base[coll_inv].docs) == n_inv + 1 and E.chaine_partagee(p0)
             and any(ev.get("type") == "invitation_sent" for ev in (enf.get("events") or [])))
    c, j = await join(t0, cle, "nouveau@exemple.test", "+41794445566", nom="Nina", canal="whatsapp")
    verifier("2c double clic : idempotent, aucun second partage", len(base[coll_inv].docs) == n_inv + 1, (c, len(base[coll_inv].docs)))
    # Sans canal et sans partage préalable : la règle « boule de neige » d'avant est intacte.
    _, r2 = await M.entree(base)
    t1 = r2["share_token"]
    c, a2 = await creer(t1)
    c, j = await join(t1, a2.get("edit_key"), "autre@exemple.test", "+41797778899")
    verifier("3 sans partage ni canal : 409 invitation_requise (inchangé)", c == 409, (c, j))
    c, j = await join(t1, None, "autre@exemple.test", "+41797778899", canal="whatsapp")
    verifier("4 canal SANS la clé de l'appareil : refusé (pas de partage différé pour un tiers)", c in (403, 409), (c, j))


async def partie_offre():
    base = H._Base()
    H.S.db = base
    PR._db = base
    AA.init_db(base)
    OFF8 = {"id": "OFF-8M", "name": "Membres — 8 mois", "price": 199.99, "offer_type": "subscription", "visible": True}
    COURS = {"id": "c-unite", "name": "Cours à l'unité", "visible": True}
    base["offers"].docs.append(OFF8)
    base["courses"].docs.append(COURS)
    adm = H.Requete({}, {"Authorization": "Bearer " + H.jeton_admin()})
    # Création manuelle avec la VRAIE offre 8 mois dans les articles autorisés.
    corps = {"code": "M8-NEUF", "type": "100%", "value": 100, "assignedEmail": "client8@exemple.test", "maxUses": 64,
             "expiresAt": "2027-06-30", "courses": ["c-unite", "OFF-8M"], "montant_encaisse": 200, "origine_paiement": "especes"}
    c, d = await appel(PR.create_discount_code(PR.DiscountCodeCreate(**corps), adm))
    s = next((x for x in base["subscriptions"].docs if x.get("code") == "M8-NEUF"), {})
    verifier("5 création manuelle « 8 mois » : la subscription enregistre le VRAI offer_id (pas le titre)",
             c == 200 and s.get("offer_id") == "OFF-8M", (c, s.get("offer_id")))
    # Cas BASSBOOSTX-11 (synthétique) : abonnement actuel SANS offre, fiche modifiée vers l'offre 8 mois.
    base["discount_codes"].docs.append({"_id": "oid-dc-x", "id": "dc-x", "code": "X-11", "assignedEmail": "x@exemple.test", "active": True,
                                        "expiresAt": "2027-05-05", "maxUses": 64, "used": 15, "courses": []})
    base["subscriptions"].docs.append({"id": "s-x", "code": "X-11", "email": "x@exemple.test", "status": "active",
                                       "offer_id": None, "offer_name": "X-11", "expires_at": "2027-05-05T23:59:59+00:00",
                                       "total_sessions": 64, "used_sessions": 15, "remaining_sessions": 49,
                                       "montant_encaisse": 200.0, "created_at": "2026-05-17", "coach_id": ""})
    EVT = {"id": "EVT", "gratuit_abonnements_offer_ids": ["OFF-8M"]}
    DEBUT = datetime(2026, 10, 28, 16, 45, tzinfo=timezone.utc)
    verifier("6 AVANT : abonnement sans offre -> non éligible à la place offerte", await EVS.abonnement_gratuit(base, "x@exemple.test", EVT, DEBUT) is None)
    c, d = await appel(PR.update_discount_code("dc-x", {"courses": ["OFF-8M"]}, adm))
    sx = next(x for x in base["subscriptions"].docs if x["id"] == "s-x")
    verifier("7 modification des articles -> offer_id COMPLÉTÉ ; séances, fin, paiement INTACTS",
             c == 200 and sx["offer_id"] == "OFF-8M" and sx["used_sessions"] == 15 and sx["total_sessions"] == 64
             and sx["expires_at"].startswith("2027-05-05") and sx["montant_encaisse"] == 200.0, (c, sx))
    g = await EVS.abonnement_gratuit(base, "x@exemple.test", EVT, DEBUT)
    verifier("8 APRÈS : mêmes droits qu'un abonnement acheté -> éligible à la place offerte", g and g["id"] == "s-x", g)
    # Une offre DÉJÀ présente et différente n'est jamais remplacée.
    base["offers"].docs.append({"id": "OFF-AUTRE", "name": "Autre", "visible": True})
    base["discount_codes"].docs.append({"_id": "oid-dc-y", "id": "dc-y", "code": "Y-1", "assignedEmail": "y@exemple.test", "active": True,
                                        "expiresAt": "2027-05-05", "maxUses": 10, "used": 1, "courses": []})
    base["subscriptions"].docs.append({"id": "s-y", "code": "Y-1", "email": "y@exemple.test", "status": "active",
                                       "offer_id": "OFF-AUTRE", "expires_at": "2027-05-05T23:59:59+00:00",
                                       "total_sessions": 10, "used_sessions": 1, "remaining_sessions": 9, "coach_id": ""})
    c, d = await appel(PR.update_discount_code("dc-y", {"courses": ["OFF-8M"]}, adm))
    verifier("9 offre existante différente : JAMAIS remplacée (ce serait un nouvel abonnement)",
             next(x for x in base["subscriptions"].docs if x["id"] == "s-y")["offer_id"] == "OFF-AUTRE", d)
    # Code sans abonnement actuel (ancien) : modifier ses articles ne déclenche aucun refus V617.
    base["discount_codes"].docs.append({"_id": "oid-dc-z", "id": "dc-z", "code": "Z-1", "assignedEmail": "z@exemple.test", "active": True,
                                        "expiresAt": "2027-05-05", "maxUses": 10, "used": 1, "courses": []})
    base["subscriptions"].docs.append({"id": "s-z", "code": "Z-1", "email": "z@exemple.test", "status": "superseded",
                                       "offer_id": None, "total_sessions": 10, "used_sessions": 1, "coach_id": ""})
    c, d = await appel(PR.update_discount_code("dc-z", {"courses": ["OFF-8M"]}, adm))
    verifier("10 ancien code (aucun abonnement actuel) : articles modifiés, historique JAMAIS touché",
             c == 200 and next(x for x in base["subscriptions"].docs if x["id"] == "s-z")["offer_id"] is None, (c, d))


def main():
    asyncio.run(partie_partage())
    asyncio.run(partie_offre())
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:700])
        _ok += ok
    print("%d / %d verifications V618k au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

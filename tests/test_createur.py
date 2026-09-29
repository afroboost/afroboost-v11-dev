#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V559 — PROGRAMME CRÉATEUR / AFFILIATION.

Prouve, sur les VRAIES routes (MongoDB en mémoire, aucun réseau) :
  * « Devenir créateur » : demande `pending`, validations, jamais d'auto-approbation ;
  * seule la super-admin approuve / refuse / suspend ; le tableau de bord n'existe
    qu'une fois approuvé ; un coach partenaire utilise la MÊME fiche / le MÊME écran ;
  * programmes d'affiliation (montant fixe / pourcentage) par offre ;
  * conversion = paiement confirmé (webhook `paid`) ; commission DIRECTE
    uniquement (lien créateur, sinon parrain DIRECT de l'invitation) ; jamais
    l'acheteur lui-même ; jamais le parrain du parrain ;
  * un paiement = une commission (webhook rejoué) ;
  * délai de confirmation, solde, demande de retrait, paiement manuel ;
  * remboursement : pending/confirmed -> refunded, payée -> régularisation ;
  * filleuls et conversions sans donnée personnelle ; page de partage + carte.

Lancement :  python3 tests/test_createur.py
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_campagne_chaine as CC  # noqa: E402  (pose le banc V3 + campagnes)

V3, H = CC.V3, CC.H
R, E, S = H.R, H.E, H.S
verifier, appel = H.verifier, H.appel
import api.routes.creator_routes as CR  # noqa: E402
import api.routes.creator_engine as C  # noqa: E402

LEA = H.PARRAIN_EMAIL                     # abonnée (jeton d'espace)
PARTENAIRE = CC.PARTENAIRE                # coach partenaire (JWT)
OFFRE_PULSE = "offre-pulse-x10"
OFFRE_EVENT = "offre-event-40"
SOPHIE, MARC, FABIEN = "sophie.v559@exemple.test", "marc.v559@exemple.test", "fabien.v559@exemple.test"


def req(corps=None, entetes=None, params=None):
    return H.Requete(corps if corps is not None else {}, entetes or {}, params)


def lea(base):
    return {"x-espace-token": H.jeton_espace(base)}


def admin():
    return {"Authorization": "Bearer " + H.jeton_admin()}


def coach():
    return {"Authorization": "Bearer " + H.jeton_admin(PARTENAIRE)}


def demande(**extra):
    d = {"prenom": "Léa", "nom": "Parrain", "telephone": "079 200 30 40", "reseaux": "@lea.danse",
         "motivation": "Je donne des cours de danse et j'ai un grand réseau.", "payout_method": "twint",
         "reglement_accepte": True}
    d.update(extra)
    return d


def session(sid, email, montant_chf, offre, jeton=None, statut="paid", pi=None, nom="Sophie Martin"):
    meta = {"offer_id": offre, "customer_name": nom, "customer_email": email}
    if jeton:
        meta["creator_token"] = jeton
    return {"id": sid, "payment_status": statut, "amount_total": int(round(montant_chf * 100)), "currency": "chf",
            "customer_details": {"email": email}, "payment_intent": pi or ("pi_" + sid), "metadata": meta}


def commissions(base):
    return base["referral_commissions"].docs


def depart():
    base, occ = CC.depart()
    base["offers"].docs += [
        {"id": OFFRE_PULSE, "name": "Pulse X10", "price": 150.0, "visible": True, "coach_id": None},
        {"id": OFFRE_EVENT, "name": "Soirée Afro", "price": 40.0, "visible": True, "coach_id": None},
    ]
    CR.init_db(base)
    return base, occ


def fuite(objet, *interdits):
    _s = json.dumps(objet, ensure_ascii=False, default=str)
    return [m for m in interdits if m and m in _s]


async def moi(base, entetes):
    return await appel(CR.createur_moi(req({}, entetes)))


# ═══════════════════════════════════════════════════════════════════════════
async def partie_demande_et_approbation(base):
    c, x = await appel(CR.createur_moi(req({}, {})))
    verifier("A0. /createur/me sans identité -> 401", c == 401, (c, x))
    c, m = await moi(base, lea(base))
    verifier("A1. abonnée sans demande : statut none, pas de tableau de bord",
             c == 200 and m["statut"] == "none" and "dashboard" not in m, (c, m))
    for bad, attendu in (({"payout_method": "iban", "payout_detail": "CH00 0000 0000 0000 0000 0"}, "IBAN"),
                         ({"telephone": "12"}, "téléphone"), ({"reglement_accepte": False}, "règlement"),
                         ({"motivation": ""}, "Motivation")):
        c, x = await appel(CR.createur_demande(req(demande(**bad), lea(base))))
        verifier("A2. demande invalide (%s) -> 422, rien écrit" % attendu,
                 c == 422 and attendu.lower() in str(x.get("detail")).lower() and not base["creators"].docs, (c, x))
    c, m = await appel(CR.createur_demande(req(demande(), lea(base))))
    fiche = base["creators"].docs[0] if base["creators"].docs else {}
    verifier("A3. « Envoyer ma demande » -> pending ; e-mail = identité serveur ; aucun lien avant approbation",
             c == 200 and m["statut"] == "pending" and "dashboard" not in m and fiche.get("email") == LEA
             and fiche.get("share_token") is None and fiche.get("payout_detail") == "+41792003040", (c, m, fiche))
    verifier("A3b. le moyen de paiement est MASQUÉ dans la réponse",
             m.get("demande", {}).get("methode_detail") == "•••• 3040" and not fuite(m, "792003040"), m.get("demande"))
    c, x = await appel(CR.createur_demande(req(demande(), lea(base))))
    verifier("A4. seconde demande pendant l'examen -> 409", c == 409, (c, x))
    c, x = await appel(CR.createur_demande(req(demande(), admin())))
    verifier("A5. la super-admin ne peut pas être créatrice rémunérée -> 409", c == 409, (c, x))

    fid = fiche["id"]
    for ent, nom in ((lea(base), "abonnée"), (coach(), "coach partenaire"), ({}, "anonyme")):
        c, x = await appel(CR.admin_decision(fid, req({"decision": "approve"}, ent)))
        verifier("B1. approuver par %s -> 401/403, rien ne change" % nom,
                 c in (401, 403) and base["creators"].docs[0]["status"] == "pending", (c, x))
    c, x = await appel(CR.admin_decision(fid, req({"decision": "approve"}, admin())))
    fiche = base["creators"].docs[0]
    verifier("B2. super-admin approuve -> approved + jeton de lien", c == 200 and fiche["status"] == "approved"
             and C.jeton_valide(fiche.get("share_token")), (c, x))
    c, m = await moi(base, lea(base))
    d = m.get("dashboard") or {}
    verifier("B3. après approbation : Dashboard Créateur actif IMMÉDIATEMENT (lien sécurisé + partage + carte)",
             c == 200 and m["statut"] == "approved" and d.get("lien", "").endswith("/?createur=" + fiche["share_token"])
             and "/api/createur/partage/" in d.get("lien_partage", "") and d.get("carte_url", "").endswith("/carte.jpg")
             and d.get("kpis") == {"gains_totaux": 0.0, "en_attente": 0.0, "solde": 0.0, "achats": 0, "filleuls": 0},
             (c, d))
    c, x = await appel(CR.admin_decision(fid, req({"decision": "reject"}, admin())))
    verifier("B4. refuser un créateur déjà approuvé -> 409 (transition interdite)", c == 409, (c, x))
    return fiche


async def partie_programmes(base):
    c, x = await appel(CR.admin_programme_creer(req({"name": "Créateurs Afroboost", "offer_id": OFFRE_PULSE,
                                                     "reward_type": "fixed_amount", "reward_value": 15}, coach())))
    verifier("C0. un coach ne crée pas de programme -> 403", c == 403, (c, x))
    c, p1 = await appel(CR.admin_programme_creer(req({"name": "Créateurs Afroboost", "offer_id": OFFRE_PULSE,
                                                      "reward_type": "fixed_amount", "reward_value": 15}, admin())))
    c2, p2 = await appel(CR.admin_programme_creer(req({"name": "Événements", "offer_id": OFFRE_EVENT,
                                                       "reward_type": "percentage", "reward_value": 10}, admin())))
    verifier("C1. programmes Pulse X10 -> 15 CHF et Événement -> 10 % (type affiliation, plateforme)",
             c == 200 and c2 == 200 and p1["type"] == "affiliation" and p1["coach_id"] == ""
             and p1["offer_name"] == "Pulse X10" and p2["reward_type"] == "percentage", (c, p1, c2, p2))
    c, x = await appel(CR.admin_programme_creer(req({"name": "X", "offer_id": OFFRE_PULSE,
                                                     "reward_type": "percentage", "reward_value": 150}, admin())))
    verifier("C2. pourcentage > 100 -> 422", c == 422, (c, x))
    c, m = await moi(base, lea(base))
    verifier("C3. le créateur voit le barème : « Pulse X10 : 15.00 CHF », « Soirée Afro : 10 % »",
             m["dashboard"]["commissions"] == ["Pulse X10 : 15.00 CHF", "Soirée Afro : 10 %"], m["dashboard"]["commissions"])
    return p1, p2


async def partie_conversions(base, fiche):
    jeton = fiche["share_token"]
    r = await CR.creator_conversion_stripe(base, session("cs_1", SOPHIE, 150, OFFRE_PULSE, jeton))
    verifier("D1. Sophie achète Pulse X10 (150 CHF) via le lien de Léa -> commission 15 CHF pending",
             r and r["commission_amount"] == 15.0 and r["status"] == "pending" and r["creator_email"] == LEA
             and r["origine"] == "lien" and r["gross_amount"] == 150.0, r)
    r2 = await CR.creator_conversion_stripe(base, session("cs_1", SOPHIE, 150, OFFRE_PULSE, jeton))
    verifier("D2. webhook rejoué (même session) -> AUCUNE seconde commission",
             len(commissions(base)) == 1 and r2 and r2["id"] == r["id"], len(commissions(base)))
    await CR.creator_conversion_stripe(base, session("cs_2", SOPHIE, 40, OFFRE_EVENT, jeton, statut="unpaid"))
    await CR.creator_conversion_stripe(base, session("cs_3", SOPHIE, 0, OFFRE_PULSE, jeton))
    await CR.creator_conversion_stripe(base, session("cs_4", SOPHIE, 30, H.OFFRE_PAYANTE, jeton))
    await CR.creator_conversion_stripe(base, session("cs_5", LEA, 150, OFFRE_PULSE, jeton, nom="Léa"))
    verifier("D3. rien pour : paiement non confirmé, montant 0 (essai), offre sans programme, auto-achat",
             len(commissions(base)) == 1, [c.get("cle_paiement") for c in commissions(base)])
    r = await CR.creator_conversion_stripe(base, session("cs_6", SOPHIE, 40, OFFRE_EVENT, jeton))
    verifier("D4. Soirée 40 CHF -> 10 % = 4.00 CHF", r and r["commission_amount"] == 4.0, r)
    c, m = await moi(base, lea(base))
    d = m["dashboard"]
    verifier("D5. KPIs : gains 0 (rien de confirmé), en attente 19, achats 2, filleuls 1 (Sophie)",
             d["kpis"] == {"gains_totaux": 0.0, "en_attente": 19.0, "solde": 0.0, "achats": 2, "filleuls": 1}, d["kpis"])
    conv = d["conversions"][0]
    verifier("D6. « Mes conversions » : date, offre, montant, commission, statut — sans l'acheteur",
             set(conv) >= {"date", "offre", "montant", "commission", "statut"} and conv["offre"] == "Soirée Afro"
             and not fuite(d["conversions"], SOPHIE, "Sophie"), d["conversions"])
    verifier("D7. « Mes filleuls » : prénom, date, origine, statut — jamais l'e-mail",
             d["filleuls"] == [{"prenom": "Sophie", "date": d["filleuls"][0]["date"], "origine": "Lien créateur",
                                "statut": "Client"}] and not fuite(m, SOPHIE), d["filleuls"])


async def partie_directe_uniquement(base):
    """Fabien (créateur) -> Sophie2 (créatrice) -> Marc : Marc achète sans lien."""
    for email, prenom in ((FABIEN, "Fabien"), ("sophie2.v559@exemple.test", "Sophie")):
        base["creators"].docs.append({"id": "cr-" + prenom, "email": email, "prenom": prenom, "nom": "T",
                                      "status": "approved", "share_token": "jeton" + prenom + "xyz",
                                      "created_at": C.iso()})
    base["referral_passes"].docs += [
        {"id": "px-1", "sponsor": {"email_norm": FABIEN, "pending": False},
         "invitee": {"email_norm": "sophie2.v559@exemple.test", "name": "Sophie"}, "created_at": C.iso()},
        {"id": "px-2", "sponsor": {"email_norm": "sophie2.v559@exemple.test", "pending": False},
         "invitee": {"email_norm": MARC, "name": "Marc Dupont"}, "created_at": C.iso()},
    ]
    r = await CR.creator_conversion_stripe(base, session("cs_m1", MARC, 150, OFFRE_PULSE, nom="Marc Dupont"))
    verifier("E1. Marc (invité de Sophie, créatrice) achète -> commission à SOPHIE (parrain direct)",
             r and r["creator_email"] == "sophie2.v559@exemple.test" and r["origine"] == "invitation"
             and r["referral_id"] == "px-2", r)
    fab = [c for c in commissions(base) if c.get("creator_email") == FABIEN]
    verifier("E2. Fabien (parrain de Sophie) ne touche RIEN sur l'achat de Marc : pas de pyramide", fab == [], fab)
    base["creators"].docs[-1]["status"] = "suspended"
    r = await CR.creator_conversion_stripe(base, session("cs_m2", MARC, 150, OFFRE_PULSE, nom="Marc Dupont"))
    fab = [c for c in commissions(base) if c.get("creator_email") == FABIEN]
    verifier("E3. Sophie non créatrice (suspendue) -> AUCUNE commission, et toujours rien pour Fabien",
             r is None and fab == [], (r, fab))
    r = await CR.creator_conversion_stripe(base, session("cs_m3", MARC, 150, OFFRE_PULSE, "jetonFabienxyz",
                                                         nom="Marc Dupont"))
    verifier("E4. le lien créateur explicite (Fabien) l'emporte : commission DIRECTE à Fabien",
             r and r["creator_email"] == FABIEN and r["origine"] == "lien", r)


async def partie_confirmation_retrait_remboursement(base, fiche):
    lea_comms = [c for c in commissions(base) if c["creator_email"] == LEA]
    for c in lea_comms:
        c["confirmable_at"] = "2020-01-01T00:00:00+00:00"
    c, m = await moi(base, lea(base))
    k = m["dashboard"]["kpis"]
    verifier("F1. délai écoulé -> confirmées : gains 19, en attente 0, solde 19, retrait possible",
             k["gains_totaux"] == 19.0 and k["en_attente"] == 0.0 and k["solde"] == 19.0
             and m["dashboard"]["retrait_possible"] is True
             and all(c["status"] == "confirmed" for c in lea_comms), k)
    c, x = await appel(CR.createur_retrait(req({}, lea(base))))
    rq = base["payout_requests"].docs[0] if base["payout_requests"].docs else {}
    verifier("F2. « Demander un retrait » -> payout_request pending de 19 CHF (TWINT), solde réservé",
             c == 200 and rq.get("status") == "pending" and rq.get("amount") == 19.0 and rq.get("payment_method") == "twint"
             and x["dashboard"]["kpis"]["solde"] == 0.0 and x["dashboard"]["retrait_en_cours"] is True, (c, rq))
    c, x = await appel(CR.createur_retrait(req({}, lea(base))))
    verifier("F3. seconde demande pendant la première -> 409", c == 409, (c, x))
    # remboursement de la soirée (4 CHF) PENDANT la demande : le retrait baisse
    n = await CR.creator_remboursement(base, "pi_cs_6", True)
    soiree = [c for c in commissions(base) if c.get("order_id") == "cs_6"][0]
    verifier("G1. remboursement d'une commission confirmée réservée -> refunded, retrait ramené à 15 CHF",
             n == 1 and soiree["status"] == "refunded" and base["payout_requests"].docs[0]["amount"] == 15.0
             and any(h.get("status") == "refunded" for h in soiree["history"]), (n, soiree["status"],
                                                                                 base["payout_requests"].docs[0]["amount"]))
    c, x = await appel(CR.admin_retraits(req({}, admin())))
    verifier("F4. la super-admin voit la demande avec le moyen de paiement complet (paiement manuel)",
             c == 200 and x["retraits"][0]["payout_detail"] == "+41792003040", (c, x))
    c, x = await appel(CR.admin_retrait_decision(rq["id"], req({"decision": "pay"}, admin())))
    pulse = [c for c in commissions(base) if c.get("order_id") == "cs_1"][0]
    verifier("F5. « payé » -> retrait paid (date de traitement), commission Pulse -> paid",
             c == 200 and x["statut"] == "paid" and x["traite_le"] and pulse["status"] == "paid", (c, x, pulse["status"]))
    n = await CR.creator_remboursement(base, "pi_cs_1", True)
    pulse = [c for c in commissions(base) if c.get("order_id") == "cs_1"][0]
    verifier("G2. remboursement APRÈS paiement -> reste « paid » + régularisation -15 CHF tracée, rien supprimé",
             n == 1 and pulse["status"] == "paid" and pulse["regularisation"]["montant"] == -15.0
             and len(commissions(base)) == 4, (n, pulse.get("regularisation"), len(commissions(base))))
    n2 = await CR.creator_remboursement(base, "pi_cs_1", True)
    verifier("G3. remboursement rejoué -> aucune seconde régularisation", n2 == 0, n2)


async def partie_coach_et_partage(base, fiche):
    c, m = await appel(CR.createur_demande(req(demande(prenom="Mariam", nom="Coach", payout_method="iban",
                                                       payout_detail="CH93 0076 2011 6238 5295 7"), coach())))
    verifier("H1. un coach partenaire devient créateur avec la MÊME route (demande pending, IBAN masqué)",
             c == 200 and m["statut"] == "pending" and m["role"] == "coach"
             and m["demande"]["methode_detail"] == "CH93 •••• 2957", (c, m))
    c, x = await appel(CR.createur_partage(fiche["share_token"], req()))
    page = bytes(getattr(x, "body", b"") or b"").decode("utf-8") if c == 200 else ""
    verifier("I1. page de partage : og:title « Léa t'invite… », carte, redirection vers ?createur=",
             c == 200 and "Léa t'invite à découvrir Afroboost" in page and "/carte.jpg" in page
             and "?createur=" + fiche["share_token"] in page and LEA not in page, (c, page[:300]))
    try:
        cx = await CR.createur_carte(fiche["share_token"], req())
        ok = cx.media_type == "image/jpeg" and len(cx.body) > 1000
    except Exception as err:  # noqa: BLE001
        ok = False
        cx = err
    verifier("I2. carte 1200×630 JPEG servie", ok, str(cx)[:200])
    c, x = await appel(CR.createur_partage("jetonInconnu123", req()))
    verifier("I3. jeton inconnu -> 404", c == 404, (c, x))
    c, x = await appel(CR.admin_decision(fiche["id"], req({"decision": "suspend"}, admin())))
    c2, m = await moi(base, lea(base))
    c3, x3 = await appel(CR.createur_partage(fiche["share_token"], req()))
    verifier("I4. suspendu -> plus de tableau de bord, lien de partage 404",
             c == 200 and m["statut"] == "suspended" and "dashboard" not in m and c3 == 404, (c, m, c3))
    c, x = await appel(CR.admin_createurs(req({}, lea(base))))
    verifier("I5. la liste admin est refusée à une abonnée", c in (401, 403), (c, x))


def partie_pure():
    verifier("P1. IBAN : clé mod-97 vérifiée", C.iban_valide("CH93 0076 2011 6238 5295 7") == "CH9300762011623852957"
             and C.iban_valide("CH94 0076 2011 6238 5295 7") == "")
    verifier("P2. commission fixe plafonnée au prix payé ; % arrondi au centime",
             C.commission_pour([{"type": "affiliation", "status": "active", "offer_id": "o", "reward_type": "fixed_amount",
                                 "reward_value": 15}], "o", 10)[0] == 10.0
             and C.commission_pour([{"type": "affiliation", "status": "active", "offer_id": "o", "reward_type": "percentage",
                                     "reward_value": 7.5}], "o", 33.33)[0] == 2.5)
    verifier("P3. choisir_createur : lien > invitation ; jamais soi-même ; jamais non approuvé",
             C.choisir_createur({"id": "a", "status": "approved", "email": "a@x"}, {"id": "b", "status": "approved",
                                                                                   "email": "b@x"}, "c@x")["id"] == "a"
             and C.choisir_createur({"id": "a", "status": "approved", "email": "c@x"}, {"id": "b", "status": "approved",
                                                                                   "email": "b@x"}, "c@x")["id"] == "b"
             and C.choisir_createur({"id": "a", "status": "pending", "email": "a@x"}, None, "c@x") is None)


async def principal():
    partie_pure()
    base, occ = depart()
    fiche = await partie_demande_et_approbation(base)
    await partie_programmes(base)
    await partie_conversions(base, fiche)
    await partie_directe_uniquement(base)
    await partie_confirmation_retrait_remboursement(base, fiche)
    await partie_coach_et_partage(base, fiche)


def main():
    _tmp = tempfile.mkdtemp(prefix="banc_v559_")
    _orig = S._V413_MEDIA_DIR
    S._V413_MEDIA_DIR = _tmp
    try:
        asyncio.run(principal())
    finally:
        S._V413_MEDIA_DIR = _orig
        shutil.rmtree(_tmp, ignore_errors=True)
    ok = sum(1 for r in H.RESULTATS if r[1])
    for nom, bon, detail in H.RESULTATS:
        if not bon:
            print("ECHEC ", nom, "\n       ", str(detail)[:700])
    print("%d / %d verifications V559 au vert" % (ok, len(H.RESULTATS)))
    sys.exit(0 if ok == len(H.RESULTATS) else 1)


if __name__ == "__main__":
    main()

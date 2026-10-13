#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618 — L'ABONNEMENT ACTUEL D'UNE PERSONNE : une seule règle, partout.

Matrice permanente (A à J), création manuelle, renouvellement, et le cas réel
« bassicustomshoes » reproduit sur des données SYNTHÉTIQUES (même forme qu'en base,
aucune donnée réelle lue ni écrite). Banc sans réseau.

Lancement : python3 tests/test_v618_abonnement_actuel.py
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_v607_invitation_evenement as V7  # noqa: E402  (pose l'environnement du banc)

T, H = V7.T, V7.H
verifier = H.verifier
import api.routes.abonnement_actuel as AA  # noqa: E402
import api.routes.evenement_special as EVS  # noqa: E402
from api.routes.shared import cloturer_anciens_forfaits  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
PROMO = open(os.path.join(RACINE, "api", "routes", "promo_routes.py"), encoding="utf-8").read()
MAINTENANT = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
M = "client.x@test.example"


def sub(i, code, status="active", exp="2027-05-05T23:59:59+00:00", offer="OFF-8M", total=10, used=0, email=M, cree="2026-01-01"):
    return {"id": i, "code": code, "email": email, "status": status, "expires_at": exp, "offer_id": offer,
            "total_sessions": total, "used_sessions": used, "remaining_sessions": total - used, "created_at": cree}


def etat(subs):
    return AA.choisir(subs, MAINTENANT)


async def principal():
    # ── matrice pure ─────────────────────────────────────────────────────────
    r = etat([sub("old", "AFR-OLD", exp="2026-09-23T23:59:59+00:00"), sub("new", "NEW-11")])
    verifier("A ancien expiré (statut resté « active ») + nouveau actif -> NOUVEAU", r["etat"] == "courant" and r["abonnement"]["id"] == "new")
    r = etat([sub("h1", "H1", status="superseded"), sub("h2", "H2", status="completed"), sub("cur", "CUR")])
    verifier("D 2 historiques + 1 actif -> l'actif", r["etat"] == "courant" and r["abonnement"]["id"] == "cur")
    r = etat([sub("a", "A-1"), sub("b", "B-1", exp="2026-12-03T23:59:59+00:00")])
    verifier("E 2 actifs RÉELS -> conflit, aucun choisi", r["etat"] == "conflit" and r["abonnement"] is None and len(r["candidats"]) == 2)
    r = etat([sub("x", "X-1", exp="2026-09-01T23:59:59+00:00")])
    verifier("F expiré seulement -> aucun (le dernier sert l'historique seulement)", r["etat"] == "aucun" and r["dernier"]["id"] == "x")
    r = etat([sub("old", "OLD", total=60, used=0, exp="2026-09-01T23:59:59+00:00", offer="OFF-AUTRE"), sub("new", "NEW", total=4, used=3)])
    verifier("H ancien avec PLUS de séances restantes -> aucune influence", r["abonnement"]["id"] == "new")
    verifier("I ancien d'une AUTRE offre -> aucune influence (offre = celle du nouveau)", r["abonnement"]["offer_id"] == "OFF-8M")
    verifier("C ancien code + nouvel offer_id -> aucun mélange de compteurs (lecture seule, sub intacte)",
             r["abonnement"]["total_sessions"] == 4 and r["abonnement"]["used_sessions"] == 3)
    r = etat([sub("d", "D-1", exp="2026-10-13")])
    verifier("règle de date V617 : « 2026-10-13 » encore valable le 13/10 (fin de journée suisse)", r["etat"] == "courant")
    r = etat([sub("c", "C-1", status="cancelled"), sub("ar", "AR", status="archived"), sub("ex", "EX", status="expired")])
    verifier("statuts historiques jamais courants", r["etat"] == "aucun")

    # ── base synthétique : le cas « bassicustomshoes » (même forme qu'en base) ──
    base, _ = T.depart()
    for nom in ("subscriptions", "discount_codes", "notifications"):
        if nom not in base._c:
            base._c[nom] = H._Coll(nom, uniques=[])
    for m in (AA,):
        m.init_db(base)
    B = "membre.b@test.example"
    base["subscriptions"].docs += [
        sub("s-bass", "BASS", status="completed", exp="2026-12-23T23:59:59+00:00", email=B, total=10, used=10),
        sub("s-bbx-old", "BBX-11", status="superseded", exp="2026-07-13T23:59:59+00:00", email=B),
        sub("s-test", "BTEST", status="active", exp="2026-07-13T23:59:59+00:00", email=B, total=4, used=3),     # statut périmé
        sub("s-bbx", "BBX-11", status="active", exp="2027-05-05T23:59:59+00:00", email=B, total=64, used=15, offer="OFF-8M"),
        sub("s-mq", "AFR-MQ", status="active", exp="2026-09-24T23:59:59+00:00", email=B, total=1, offer="OFF-UNITE"),  # statut périmé
    ]
    base["discount_codes"].docs += [
        {"code": "BBX-11", "assignedEmail": B, "active": True, "expiresAt": "2027-05-05", "maxUses": 64, "used": 15},
        {"code": "AFR-OLD9", "assignedEmail": B, "active": True, "expiresAt": "2026-09-23", "maxUses": 1, "used": 0},
    ]
    r = await AA.resoudre_abonnement_actuel(base, "MEMBRE.B@test.example", MAINTENANT)
    verifier("B1 cas réel : abonnement ACTUEL = BBX-11 (15/64, 49 restantes, 05/05/2027), e-mail sans casse",
             r["etat"] == "courant" and r["abonnement"]["code"] == "BBX-11" and r["abonnement"]["remaining_sessions"] == 49)
    acc = await AA.fiches_pour_acces(base, B, MAINTENANT)
    verifier("B2 e-mail d'accès : SON code actuel BBX-11 (jamais l'ancien AFR-OLD9 expiré)",
             acc["etat"] == "courant" and [f["code"] for f in acc["fiches"]] == ["BBX-11"])
    cible = await AA.code_cible_espace(base, B, "AFR-OLD9")
    verifier("B CAS B ancien code dans l'adresse + nouveau actif -> espace ACTUEL (après preuve de la session)",
             cible == {"code": "BBX-11", "coach_id": ""}, cible)
    verifier("B3 adresse = code actuel -> pas de redirection", await AA.code_cible_espace(base, B, "BBX-11") is None)
    verifier("B4 autre adresse e-mail (session d'un tiers) -> jamais l'espace de B",
             await AA.code_cible_espace(base, "autre@test.example", "AFR-OLD9") is None)

    # ── J : événement (place offerte) -> l'abonnement ACTUEL uniquement ─────────
    offre = {"id": "EVT", "gratuit_abonnements_offer_ids": ["OFF-8M"]}
    debut = datetime(2026, 10, 28, 16, 45, tzinfo=timezone.utc)
    g = await EVS.abonnement_gratuit(base, B, offre, debut)
    verifier("J événement : droits calculés depuis l'abonnement ACTUEL (BBX-11, offre 8 mois)", g and g["id"] == "s-bbx")
    offre_unite = {"id": "EVT2", "gratuit_abonnements_offer_ids": ["OFF-UNITE"]}
    verifier("J2 un ANCIEN abonnement d'une autre offre (statut resté « active ») ne donne plus droit",
             await EVS.abonnement_gratuit(base, B, offre_unite, debut) is None)
    C = "conflit@test.example"
    base["subscriptions"].docs += [sub("c1", "AMB-26", email=C, offer="OFF-8M"),
                                   sub("c2", "AFR-Y8", email=C, offer="OFF-UNITE", exp="2026-12-03T23:59:59+00:00")]
    verifier("E2 conflit -> aucune gratuité (fail closed), rien de modifié",
             await EVS.abonnement_gratuit(base, C, offre, debut) is None
             and {s["status"] for s in base["subscriptions"].docs if s["email"] == C} == {"active"})
    notes = [n for n in base["notifications"].docs if n.get("type") == "abonnement_integrite"]
    verifier("E3 conflit -> notification coach INTERNE, codes seuls (aucun e-mail)",
             len(notes) == 1 and "AMB-26" in notes[0]["message"] and "@" not in notes[0]["message"])
    await AA.resoudre_abonnement_actuel(base, C, MAINTENANT)
    verifier("E4 notification idempotente (pas de doublon)", len([n for n in base["notifications"].docs if n.get("type") == "abonnement_integrite"]) == 1)
    acc = await AA.fiches_pour_acces(base, C, MAINTENANT)
    verifier("E5 e-mail d'accès en conflit : rien choisi à sa place (aucune fiche de code -> repli neutre)", acc["etat"] == "conflit")

    # ── G / renouvellement : création manuelle -> le nouveau devient l'actuel ──
    N = "renouv@test.example"
    base["subscriptions"].docs += [sub("ancien", "AFR-A1", email=N, exp="2026-10-01T23:59:59+00:00")]
    nouveau = sub("neuf", "AFR-N2", email=N, cree="2026-10-13")
    base["subscriptions"].docs.append(nouveau)
    fermes = await cloturer_anciens_forfaits(base, N, "neuf", log_prefix="V618")
    anc = [s for s in base["subscriptions"].docs if s["id"] == "ancien"][0]
    verifier("G création manuelle : l'ancien expiré passe en HISTORIQUE (superseded), compteurs intacts",
             fermes == ["ancien"] and anc["status"] == "superseded" and anc["superseded_by"] == "neuf" and anc["total_sessions"] == 10)
    r = await AA.resoudre_abonnement_actuel(base, N)
    verifier("G2 dès la création, le NOUVEAU est l'abonnement actuel", r["etat"] == "courant" and r["abonnement"]["id"] == "neuf")
    verifier("G3 la création manuelle (POST /discount-codes) appelle cette clôture",
             "_v618_cloturer(_db, assigned_email, sub_data.get(\"id\"), log_prefix=\"V618\")" in PROMO)

    # ── simulation (lecture seule) ─────────────────────────────────────────────
    sim = AA.simuler(base["subscriptions"].docs, base["discount_codes"].docs, MAINTENANT)
    verifier("S-1 simulation : conflits, statuts périmés, codes actifs expirés comptés, sans e-mail en clair",
             sim["clients_conflit_multi_actifs"] == 1 and sim["subscriptions_statut_active_mais_expirees"] >= 2
             and sim["codes_active_mais_expires"] == 1 and "@" not in str(sim["conflits"]), sim)

    # ── câblage : toutes les portes passent par le résolveur ──────────────────
    rec = SERVEUR[SERVEUR.index('@api_router.post("/subscriber/recover")'):]
    rec = rec[:rec.index("@api_router", 10)]
    verifier("W-1 e-mail d'accès : résolveur, plus de find_one({assignedEmail, active}) sans tri",
             "_v618.fiches_pour_acces(db, found_email)" in rec and '{"assignedEmail": email, "active": True}' not in rec)
    esp = SERVEUR[SERVEUR.index("async def get_subscriber_space("):]
    esp = esp[:esp.index("V201: Log pour diagnostic")]
    verifier("W-2 espace : APRÈS la preuve de session, un ancien code renvoie vers l'espace actuel",
             esp.index("_b3s13_porteur_autorise") < esp.index("code_cible_espace") and '"redirection_espace"' in esp)
    verifier("W-3 lien d'espace coach + rappel Stripe : résolveur ; conflit -> aucun choix",
             SERVEUR.count("resoudre_abonnement_actuel(db, email_clean)") == 1 and SERVEUR.count("resoudre_abonnement_actuel(db, _email)") == 1
             and "Plusieurs abonnements actifs pour ce client — à vérifier." in SERVEUR)
    verifier("W-4 notification coach visible (type ajouté aux notifications du tableau de bord)", '"abonnement_integrite")' in SERVEUR)


def main():
    asyncio.run(principal())
    _res = [r for r in H.RESULTATS if re.match(r"^([A-J]\d?|[BEGSW]-?\d|règle|statuts|B\d)", r[0])]
    _ok = 0
    for nom, ok, detail in _res:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:500])
        _ok += ok
    print("%d / %d verifications V618 au vert" % (_ok, len(_res)))
    sys.exit(0 if _ok == len(_res) else 1)


if __name__ == "__main__":
    main()

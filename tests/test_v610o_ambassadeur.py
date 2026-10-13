#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610o — PROGRAMME AMBASSADEUR : Boosts, paliers, récompenses, révocations.

Banc sur les VRAIES routes (`invitation_relais.py`, `ambassadeur_routes.py`,
`evenement_special.py`) et le MongoDB en mémoire du banc V607. Aucun réseau, aucune
donnée réelle, aucun paiement : les sessions Stripe sont simulées.

Lancement : python3 tests/test_v610o_ambassadeur.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_v607_invitation_evenement as V7  # noqa: E402  (pose l'environnement du banc)

T, H, RL, SI, SV = V7.T, V7.H, V7.RL, V7.SI, V7.SV
verifier, appel = H.verifier, H.appel
import api.routes.ambassadeur_routes as AMB  # noqa: E402
import api.routes.ambassadeur_engine as A  # noqa: E402
import api.routes.evenement_special as EVS  # noqa: E402


class _RqEspace:
    def __init__(self, corps, jeton=""):
        self._c = corps
        self.headers = V7._Ent({"x-espace-token": jeton, "user-agent": ""})
        self.client = type("C", (), {"host": "10.6.6.6"})()

    async def json(self):
        return self._c


def compte(base, empreinte, statut=A.STATUT_ACCORDE):
    return sum(1 for b in base[AMB.COLL_BOOSTS].docs if b.get("parrain_empreinte") == empreinte and b.get("statut") == statut)


async def payer(base, cs, jeton, email, nom, montant=3000, statut="paid"):
    s = V7.session(cs, jeton, email, nom, montant)
    s["payment_status"] = statut
    return await RL.relais_depuis_paiement_stripe(base, s)


async def principal():
    base, occ = T.depart()
    for nom, uniques in (("invitation_relais", [(("jeton",), None), (("preuve_cle",), None)]),
                         ("invitation_events", [(("cle",), None)]), (AMB.COLL_BOOSTS, []),
                         (AMB.COLL_RECOMPENSES, []), ("notifications", []), ("referral_programs", []),
                         ("evenement_places", [])):
        if nom not in base._c:
            base._c[nom] = H._Coll(nom, uniques=uniques)
    for m in (SI, RL, SV, AMB):
        m.init_db(base)
    c, ev = await T.creer(T.COACH_A, {"type": "event_paid", "status": "active", "offer_id": T.OFFRE_A_PAYANTE,
                                      "occurrence": occ, "title": "AFROBOOST SILENT"})
    verifier("O-0 événement payant actif", c == 201, (c, ev))
    racine = ev["share_token"]
    emp = RL.empreinte_email

    # ── Bassi : membre 8 mois, place offerte via l'invitation du coach (génération 1) ──
    base["reservations"].docs.append({"id": "R-BASSI", "userName": "Bassi Test", "userEmail": "bassi@test.example",
                                      "userWhatsapp": "+41790000001", "coach_id": T.COACH_A})
    bassi = await RL.creer_relais(base, jeton_parent=racine, email="bassi@test.example", nom="Bassi Test",
                                  preuve_nature="membre", preuve_cle="R-BASSI", reservation_id="R-BASSI")
    verifier("O-1 Bassi : génération 1 (racine = invitation du coach), AUCUN Boost pour le coach",
             bassi["generation"] == 1 and not base[AMB.COLL_BOOSTS].docs, bassi)
    verifier("O-2 lien de Bassi : nature « membre » (message « ma place est offerte »)",
             RL.dto_relais(bassi)["nature"] == "membre")

    # ── G / H : clic seul, paiement échoué -> 0 Boost ──────────────────────────
    await appel(SI.invitation_publique(bassi["jeton"]))          # Sophie ouvre la page de Bassi
    verifier("G-1 simple ouverture du lien de Bassi -> 0 Boost", compte(base, emp("bassi@test.example")) == 0)
    rate = await payer(base, "cs_test_ECHEC1", bassi["jeton"], "sophie@test.example", "Sophie Test", statut="unpaid")
    verifier("H-1 paiement NON payé -> aucun relais, 0 Boost", rate is None and compte(base, emp("bassi@test.example")) == 0)

    # ── F / I : Sophie paie via Bassi -> Bassi +1 ; webhook rejoué -> toujours 1 ──
    sophie = await payer(base, "cs_test_SOPHIE1", bassi["jeton"], "sophie@test.example", "Sophie Test")
    verifier("F-1 Sophie paie via le lien de Bassi -> Bassi +1 Boost", compte(base, emp("bassi@test.example")) == 1)
    verifier("F-2 Sophie obtient SON lien (génération 2, inviteur direct Bassi)",
             sophie["generation"] == 2 and sophie["parent_relais_id"] == bassi["id"] and sophie["jeton"] != bassi["jeton"])
    await payer(base, "cs_test_SOPHIE1", bassi["jeton"], "sophie@test.example", "Sophie Test")
    await payer(base, "cs_test_SOPHIE2", bassi["jeton"], "sophie@test.example", "Sophie Test")   # autre appareil, même personne
    verifier("I-1 double webhook / second achat de la même personne -> 1 Boost maximum",
             compte(base, emp("bassi@test.example")) == 1 and len([b for b in base[AMB.COLL_BOOSTS].docs]) == 1)
    b0 = base[AMB.COLL_BOOSTS].docs[0]
    verifier("I-2 historique BOOST_GRANTED, clé boost:<relais de Sophie>",
             b0["_id"] == "boost:%s" % sophie["id"] and b0["historique"][0]["evenement"] == "BOOST_GRANTED")

    # ── auto-parrainage : Bassi achète via SON propre lien -> rien ─────────────
    await payer(base, "cs_test_BASSI01", bassi["jeton"], "bassi@test.example", "Bassi Test")
    verifier("O-3 auto-parrainage -> aucun Boost", compte(base, emp("bassi@test.example")) == 1)

    # ── N : Nadine via Sophie, Julie via Nadine -> chaque Boost au parrain DIRECT ──
    nadine = await payer(base, "cs_test_NADINE1", sophie["jeton"], "nadine@test.example", "Nadine Test")
    julie = await payer(base, "cs_test_JULIE01", nadine["jeton"], "julie@test.example", "Julie Test")
    verifier("N-1 Nadine réserve -> Sophie +1 ; Bassi reste à 1 (pas de Boost ascendant)",
             compte(base, emp("sophie@test.example")) == 1 and compte(base, emp("bassi@test.example")) == 1)
    verifier("N-2 Julie réserve -> Nadine +1", compte(base, emp("nadine@test.example")) == 1)
    verifier("N-3 générations 1 / 2 / 3 / 4, même racine",
             [bassi["generation"], sophie["generation"], nadine["generation"], julie["generation"]] == [1, 2, 3, 4]
             and {x["racine_jeton"] for x in (bassi, sophie, nadine, julie)} == {racine})

    # ── J : remboursement de Sophie -> Boost de Bassi retiré UNE fois ─────────
    n1 = await AMB.revoquer_par_paiement(base, "pi_cs_test_SOPHIE1", True)
    n2 = await AMB.revoquer_par_paiement(base, "pi_cs_test_SOPHIE1", True)
    verifier("J-1 remboursement -> Boost révoqué une seule fois", n1 == 1 and n2 == 0 and compte(base, emp("bassi@test.example")) == 0)
    verifier("J-2 historique conservé : GRANTED puis REVOKED (remboursement_stripe), rien d'effacé",
             [h["evenement"] for h in b0["historique"]] == ["BOOST_GRANTED", "BOOST_REVOKED"]
             and b0["raison_revocation"] == "remboursement_stripe" and len(base[AMB.COLL_BOOSTS].docs) == 3)

    # ── annulation : la réservation de Nadine supprimée -> Boost de Sophie révoqué à la lecture ──
    base["evenement_places"].docs.append({"_id": "stripe:cs_test_NADINE1", "reservation_id": "R-NADINE-SUPPRIMEE"})
    imp = await AMB.impact(base, "", emp("sophie@test.example")) if False else await AMB.impact(base, T.COACH_A, emp("sophie@test.example"))
    verifier("J-3 réservation annulée -> Boost de Sophie révoqué (reservation_annulee)",
             compte(base, emp("sophie@test.example")) == 0 and imp["progression"]["boosts"] == 0
             and any(b.get("raison_revocation") == "reservation_annulee" for b in base[AMB.COLL_BOOSTS].docs))

    # ── K / L / M : paliers 3 / 5 / 10 pour une ambassadrice (Mia) ─────────────
    base["reservations"].docs.append({"id": "R-MIA", "userName": "Mia Test", "userEmail": "mia@test.example", "coach_id": T.COACH_A})
    mia = await RL.creer_relais(base, jeton_parent=racine, email="mia@test.example", nom="Mia Test",
                                preuve_nature="membre", preuve_cle="R-MIA", reservation_id="R-MIA")
    pi_amis = []
    for i in range(1, 11):
        await payer(base, "cs_test_AMI%03d" % i, mia["jeton"], "ami%d@test.example" % i, "Ami%d Test" % i)
        pi_amis.append("pi_cs_test_AMI%03d" % i)
        n = compte(base, emp("mia@test.example"))
        rec = {r["palier"]: r for r in base[AMB.COLL_RECOMPENSES].docs if r.get("ambassadeur_empreinte") == emp("mia@test.example")}
        if i == 2:
            verifier("K-0 2 Boosts : aucun palier", not rec)
        if i == 3:
            verifier("K-1 3 Boosts -> Pass Ami débloqué (disponible)", rec.get("pass_ami", {}).get("etat") == "disponible", rec)
        if i == 5:
            verifier("L-1 5 Boosts -> Récompense Afroboost (à remettre)", rec.get("recompense", {}).get("etat") == "a_remettre", rec)
        if i == 10:
            verifier("M-1 10 Boosts -> Ambassadeur VIP", rec.get("vip", {}).get("etat") == "actif" and n == 10, rec)
    p = A.progression(10)
    verifier("M-2 compteur CUMULÉ (jamais remis à zéro) : 10 Boosts, VIP, aucun palier suivant",
             p["boosts"] == 10 and p["vip"] and p["prochain"] is None and p["debloques"] == ["pass_ami", "recompense", "vip"])
    notifs = [x for x in base["notifications"].docs if x.get("type") == "ambassadeur_palier"]
    verifier("K-2 notification coach INTERNE à chaque palier (3), prénom seul",
             len(notifs) == 3 and all("@" not in x["message"] for x in notifs), [x["message"] for x in notifs])

    # ── Récompense remise puis repassage sous le seuil -> jamais effacée, « à vérifier » ──
    rid = "%s|%s|recompense" % (T.COACH_A, emp("mia@test.example"))
    c, r = await appel(AMB.ambassadeur_coach_recompense(T.rq(T.COACH_A, {"id": rid, "etat": "remise"})))
    verifier("R-1 coach : Récompense marquée « Remise »", c == 200 and r["etat"] == "remise", (c, r))
    c, _ = await appel(AMB.ambassadeur_coach_recompense(T.rq(T.COACH_B, {"id": rid, "etat": "a_remettre"})))
    verifier("R-2 un AUTRE coach ne touche pas cette récompense -> 404", c == 404, c)
    for pi in pi_amis[:6]:
        await AMB.revoquer_par_paiement(base, pi, True)
    rr = [x for x in base[AMB.COLL_RECOMPENSES].docs if x["_id"] == rid][0]
    verifier("R-3 4 Boosts après 6 remboursements : la Récompense REMISE reste, signalée « à vérifier »",
             compte(base, emp("mia@test.example")) == 4 and rr["etat"] == "remise" and rr.get("a_verifier") is True)
    verifier("R-4 notification coach « cas à vérifier »",
             any("cas à vérifier" in x["title"] for x in base["notifications"].docs))

    # ── O : 51e réservation autorisée (aucune capacité technique) ─────────────
    offre = {"id": "OFF-51", "name": "Silent", "coach_id": T.COACH_A}
    cours = {"id": "C-51", "name": "Silent", "time": "18:45", "coach_id": T.COACH_A}
    crees = 0
    for i in range(51):
        resa, creee = await EVS.reserver(base, cle="test51:%d" % i, offre=offre, cours=cours, occ=occ,
                                         email="p%d@test.example" % i, nom="P%d" % i, prix=30, source="test")
        crees += int(bool(resa and creee))
    verifier("O-4 51 réservations distinctes -> 51 créées (aucun plafond de 50)", crees == 51, crees)

    # ── routes membre : 403 sans session, impact avec session ────────────────
    ancien = RL._porteur_espace
    sessions = {"tok-mia": {"email": "mia@test.example", "code": "AFR-MIA"}}

    async def faux(request, code, slug):
        _c = sessions.get(request.headers.get("x-espace-token"))
        return _c if _c and _c["code"] == code else None
    RL._porteur_espace = faux
    try:
        c, _ = await appel(AMB.ambassadeur_mon_impact(_RqEspace({"code": "AFR-MIA"}, "")))
        verifier("S-1 mon impact sans session d'espace -> 403", c == 403, c)
        c, r = await appel(AMB.ambassadeur_mon_impact(_RqEspace({"code": "AFR-MIA"}, "tok-mia")))
        verifier("S-2 mon impact : 4 Boosts, prochain palier Récompense (5), lien perso, aucun e-mail",
                 c == 200 and r["ambassadeur"] and r["progression"]["boosts"] == 4
                 and r["progression"]["prochain"]["cle"] == "recompense" and r["lien"]["jeton"] == mia["jeton"]
                 and "@" not in str(r), (c, r))
    finally:
        RL._porteur_espace = ancien
    c, r = await appel(AMB.ambassadeur_impact_session("cs_test_AMI010"))
    verifier("S-3 impact par session Stripe payée (l'acheteur Ami10) : compteurs seuls", c == 200
             and r["progression"]["boosts"] == 0 and "recents" not in r, (c, r))
    c, _ = await appel(AMB.ambassadeur_impact_session("cs_inconnu_000000"))
    verifier("S-4 session inconnue -> 404", c == 404, c)

    # ── coach : liste, détail, config ─────────────────────────────────────────
    c, r = await appel(AMB.ambassadeur_coach_liste(T.rq(T.COACH_A)))
    lignes = {l["prenom"]: l for l in (r or {}).get("ambassadeurs", [])}
    verifier("C-1 liste coach : Mia (4 convertis, 6 révoqués), contact de SA réservation",
             c == 200 and lignes.get("Mia", {}).get("convertis") == 4 and lignes["Mia"]["revoques"] == 6
             and lignes["Mia"]["contact"].get("email") == "mia@test.example", (c, lignes.get("Mia")))
    c, rq = await appel(AMB.ambassadeur_coach_liste(T.rq(T.COACH_A), q="bassi"))
    verifier("C-2 recherche « bassi »", c == 200 and [l["prenom"] for l in rq["ambassadeurs"]] == ["Bassi"], rq)
    c, rb = await appel(AMB.ambassadeur_coach_liste(T.rq(T.COACH_B)))
    verifier("C-3 un autre coach ne voit AUCUN ambassadeur de A", c == 200 and rb["ambassadeurs"] == [], rb)
    c, _ = await appel(AMB.ambassadeur_coach_liste(T.rq(None)))
    verifier("C-4 sans jeton -> 401", c == 401, c)
    c, d = await appel(AMB.ambassadeur_coach_detail(lignes["Bassi"]["id"], T.rq(T.COACH_A)))
    f = (d or {}).get("filleuls") or []
    verifier("C-5 détail Bassi : Sophie, Boost non (remboursé), montant 30",
             c == 200 and len(f) == 1 and f[0]["prenom"] == "Sophie" and f[0]["boost"] is False
             and f[0]["annule_ou_rembourse"] is True and f[0]["montant"] == 30.0, (c, d))
    c, _ = await appel(AMB.ambassadeur_config_ecrire(T.rq(T.COACH_A, {"paliers": [
        {"cle": "pass_ami", "seuil": 5}, {"cle": "recompense", "seuil": 3}, {"cle": "vip", "seuil": 10}]})))
    verifier("C-6 config : seuils non croissants -> 400", c == 400, c)
    c, cfg = await appel(AMB.ambassadeur_config_ecrire(T.rq(T.COACH_A, {
        "paliers": [{"cle": "pass_ami", "seuil": 3, "libelle": "Pass Ami"}, {"cle": "recompense", "seuil": 5, "libelle": "Chaussettes"},
                    {"cle": "vip", "seuil": 10}], "pass_ami": {"activites": ["OFF-1"], "expire_le": "2026-12-31"},
        "avantage_filleul": {"actif": True, "type": "pourcentage", "valeur": 10}})))
    verifier("C-7 config enregistrée ; l'avantage filleul reste DÉSACTIVÉ", c == 200
             and cfg["paliers"][1]["libelle"] == "Chaussettes" and cfg["avantage_filleul"]["actif"] is False
             and cfg["pass_ami"]["expire_le"] == "2026-12-31", (c, cfg))
    verifier("C-8 valeurs initiales : 3 / 5 / 10, « 50 PLACES »",
             [p["seuil"] for p in A.config_defaut()["paliers"]] == [3, 5, 10] and A.config_defaut()["message_places"] == "50 PLACES")
    verifier("C-9 ville du lieu : « Chemin des Valangines 97, 2000 Neuchâtel » -> « Neuchâtel »",
             A.ville("Chemin des Valangines 97, 2000 Neuchâtel") == "Neuchâtel")


def main():
    asyncio.run(principal())
    _res = [r for r in H.RESULTATS if r[0][:2] in ("O-", "G-", "H-", "F-", "I-", "N-", "J-", "K-", "L-", "M-", "R-", "S-", "C-")]
    _ok = 0
    for nom, ok, detail in _res:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:600])
        _ok += ok
    print("%d / %d verifications V610o au vert" % (_ok, len(_res)))
    sys.exit(0 if _ok == len(_res) else 1)


if __name__ == "__main__":
    main()

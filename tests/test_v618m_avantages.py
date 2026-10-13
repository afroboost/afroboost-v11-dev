#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618M — AVANTAGES MEMBRES PAR OFFRE (réglés par le coach) + URGENCE / CAPACITÉ SÉPARÉES.

Plus aucune règle « 8 mois » codée en dur : pour chaque événement payant, le coach choisit,
offre par offre (identifiant réel), Gratuit / Réduction % / Prix fixe / Aucun avantage. Le
serveur décide du prix depuis l'abonnement ACTUEL (résolveur canonique) de la personne prouvée.
« 50 PLACES » n'est qu'un texte ; seule une capacité ACTIVÉE limite les réservations.

Banc permanent, base en mémoire, données synthétiques.
Lancement : python3 tests/test_v618m_avantages.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_essai_moi_dabord as M  # noqa: E402  (pose l'environnement du banc)

H = M.H
import api.routes.abonnement_actuel as AA  # noqa: E402
import api.routes.evenement_special as EVS  # noqa: E402
import api.routes.invitation_edition as IE  # noqa: E402
from fastapi import HTTPException  # noqa: E402

RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


DEBUT = datetime.now(timezone.utc) + timedelta(days=15)
JOUR = (DEBUT.astimezone(EVS._ZURICH)).strftime("%Y-%m-%d")


def sub(i, email, offre):
    return {"_id": "oid-" + i, "id": i, "code": i.upper(), "email": email, "status": "active", "offer_id": offre,
            "expires_at": (DEBUT + timedelta(days=200)).isoformat(), "total_sessions": 64, "used_sessions": 1,
            "remaining_sessions": 63, "created_at": "2026-09-01", "coach_id": ""}


def fiche(i, email):
    return {"_id": "oid-dc-" + i, "id": "dc-" + i, "code": i.upper(), "assignedEmail": email, "active": True,
            "expiresAt": (DEBUT + timedelta(days=200)).strftime("%Y-%m-%d"), "maxUses": 64, "used": 1}


def base_evenement(avantages=None, legacy=None, **extra):
    b = H._Base()
    AA.init_db(b)
    evt = {"id": "EVT", "name": "AFROBOOST SILENT", "offer_type": "event", "price": 30.0, "visible": True,
           "linked_course_ids": ["C-EVT"], "evenement_reservation_auto": True, "coach_id": ""}
    if avantages is not None:
        evt["avantages_membres"] = avantages
    if legacy is not None:
        evt["gratuit_abonnements_offer_ids"] = legacy
    evt.update(extra)
    b["offers"].docs.append(evt)
    b["courses"].docs.append({"id": "C-EVT", "name": "AFROBOOST SILENT", "date": JOUR, "time": "18:45", "coach_id": ""})
    for i, email, offre in (("a", "a@exemple.test", "OFF-A"), ("b", "b@exemple.test", "OFF-B"),
                            ("c", "c@exemple.test", "OFF-C"), ("d", "d@exemple.test", "OFF-D"),
                            ("amie", "amie@exemple.test", "OFF-A")):
        b["subscriptions"].docs.append(sub(i, email, offre))
        b["discount_codes"].docs.append(fiche(i, email))
    return b, evt


REGLES = [{"offer_id": "OFF-A", "type": "gratuit"}, {"offer_id": "OFF-B", "type": "reduction", "valeur": 20},
          {"offer_id": "OFF-C", "type": "prix_fixe", "valeur": 20}, {"offer_id": "OFF-D", "type": "aucun"}]


async def principal():
    b, evt = base_evenement(REGLES)
    t = {k: await EVS.tarif_membre(b, k + "@exemple.test", evt, 30.0) for k in ("a", "b", "c", "d")}
    verifier("A offre A = Gratuit -> membre A : 0 CHF", t["a"]["prix"] == 0.0 and t["a"]["regle"]["type"] == "gratuit", t["a"])
    verifier("B offre B = -20 % -> 30 CHF devient 24 CHF", t["b"]["prix"] == 24.0, t["b"])
    verifier("C offre C = prix fixe 20 CHF -> 20 CHF", t["c"]["prix"] == 20.0, t["c"])
    verifier("D offre D = aucun avantage -> tarif public 30 CHF", t["d"]["prix"] == 30.0 and t["d"]["regle"] is None, t["d"])
    e = await EVS.tarif_membre(b, "ami.sans.abonnement@exemple.test", evt, 30.0)
    verifier("E ami d'un membre gratuit, sans abonnement : tarif public (aucun héritage)", e["prix"] == 30.0 and e["regle"] is None, e)
    f = await EVS.tarif_membre(b, "amie@exemple.test", evt, 30.0)
    verifier("F ami LUI-MÊME membre de l'offre A : gratuit selon SON abonnement", f["prix"] == 0.0, f)
    # Prix public d'un autre palier : la réduction suit, le prix fixe reste.
    verifier("B2 -20 % sur 40 CHF (dernière minute) = 32 CHF ; prix fixe reste 20 CHF",
             (await EVS.tarif_membre(b, "b@exemple.test", evt, 40.0))["prix"] == 32.0
             and (await EVS.tarif_membre(b, "c@exemple.test", evt, 40.0))["prix"] == 20.0)
    verifier("B3 arrondi au centime (-15 % de 25 CHF = 21.25 CHF) ; 100 % = gratuit ; jamais au-dessus du public",
             EVS.prix_membre({"type": "reduction", "valeur": 15}, 25) == 21.25
             and EVS._regle_valide({"type": "reduction", "valeur": 100}) == {"type": "gratuit", "valeur": None}
             and EVS.prix_membre({"type": "prix_fixe", "valeur": 50}, 30) == 30.0)
    verifier("B4 réduction hors 1..100 % refusée", EVS._regle_valide({"type": "reduction", "valeur": 0}) is None
             and EVS._regle_valide({"type": "reduction", "valeur": 120}) is None)
    # Un abonnement ancien (non actuel) ne donne rien.
    b["subscriptions"].docs[1]["status"] = "superseded"
    verifier("B5 abonnement non actuel (remplacé) : aucun avantage", (await EVS.tarif_membre(b, "b@exemple.test", evt, 30.0))["regle"] is None)
    # Avantages suspendus par le coach.
    evt2 = dict(evt, gratuit_membres_actif=False)
    verifier("B6 avantages suspendus par le coach : tarif public pour tous", (await EVS.tarif_membre(b, "a@exemple.test", evt2, 30.0))["regle"] is None)

    # Migration : ancienne forme (liste « gratuit ») lue À L'IDENTIQUE.
    b2, evt_l = base_evenement(None, legacy=["OFF-A", "OFF-C"])
    verifier("M1 ancienne règle (gratuit_abonnements_offer_ids) -> mêmes membres éligibles, gratuit",
             EVS.regles_avantages(evt_l) == {"OFF-A": {"type": "gratuit", "valeur": None}, "OFF-C": {"type": "gratuit", "valeur": None}}
             and (await EVS.tarif_membre(b2, "c@exemple.test", evt_l, 30.0))["prix"] == 0.0
             and (await EVS.tarif_membre(b2, "b@exemple.test", evt_l, 30.0))["regle"] is None)
    verifier("M2 la nouvelle forme PRIME sur l'ancienne", EVS.regles_avantages(dict(evt_l, avantages_membres=[{"offer_id": "OFF-B", "type": "reduction", "valeur": 10}]))
             == {"OFF-B": {"type": "reduction", "valeur": 10}})

    # G — sélecteur coach : actives seulement ; masquées / expirées à part ; archivées jamais.
    passe = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    offres = [{"id": "1", "name": "Membres — 8 mois", "offer_type": "subscription", "created_at": "2026-09-02"},
              {"id": "2", "name": "Membres — 8 mois", "offer_type": "subscription", "created_at": "2026-01-01"},
              {"id": "3", "name": "Ancienne", "offer_type": "subscription", "archived": True},
              {"id": "4", "name": "Pulse", "offer_type": "pack", "expiration_date": passe},
              {"id": "5", "name": "Cachée", "offer_type": "pack", "visible": False},
              {"id": "6", "name": "Un événement", "offer_type": "event"},
              {"id": "7", "name": "T-shirt", "offer_type": "product", "isProduct": True},
              {"id": "8", "name": "Étudiant", "offer_type": "subscription"}]
    act, aut = IE.offres_choisissables(offres)
    verifier("G offre archivée / événement / produit : jamais proposés ; doublon de nom : une seule fois",
             [o["id"] for o in act] == ["8", "1"] and not any(o["id"] in ("3", "6", "7") for o in act + aut), (act, aut))
    verifier("G2 offres masquées ou expirées : à part (jamais dans la liste principale)", sorted(o["id"] for o in aut) == ["4", "5"], aut)
    try:
        IE.valider_avantages([{"offer_id": "3", "type": "gratuit"}], offres)
        ok = False
    except HTTPException as x:
        ok = x.status_code == 422
    verifier("G3 offre archivée envoyée quand même : refusée par le serveur", ok)
    try:
        IE.valider_avantages([{"offer_id": "inconnue", "type": "gratuit"}], offres)
        ok = False
    except HTTPException as x:
        ok = x.status_code == 422
    verifier("G4 identifiant inventé (ou d'un autre coach) : refusé — jamais un titre", ok)
    verifier("G5 « aucun » n'est pas stocké ; prix fixe 0 = gratuit",
             IE.valider_avantages([{"offer_id": "8", "type": "aucun"}, {"offer_id": "1", "type": "prix_fixe", "valeur": 0}], offres)
             == [{"offer_id": "1", "type": "gratuit", "valeur": None}])

    # H — historique : une réservation payée garde son prix quand la règle change.
    b3, evt3 = base_evenement([{"offer_id": "OFF-A", "type": "reduction", "valeur": 10}])
    cours = b3["courses"].docs[0]
    occ = EVS.occurrence(cours)
    resa, creee = await EVS.reserver(b3, cle="stripe:cs_test_hist", offre=evt3, cours=cours, occ=occ, email="a@exemple.test",
                                     nom="Sophie", prix=25.0, source=EVS.SOURCE_PAYANT)
    evt3["avantages_membres"] = [{"offer_id": "OFF-A", "type": "gratuit"}]
    r = next(x for x in b3["reservations"].docs if x["id"] == resa["id"])
    verifier("H paiement passé (25 CHF) : INCHANGÉ après passage de la règle à « Gratuit »",
             creee and r["price"] == 25.0 and r["totalPrice"] == 25.0
             and (await EVS.tarif_membre(b3, "a@exemple.test", evt3, 30.0))["prix"] == 0.0)

    # L — double clic sur la réservation gratuite : une seule place.
    b4, evt4 = base_evenement(REGLES)
    c4 = b4["courses"].docs[0]
    r1 = await EVS.reserver(b4, cle="membre:EVT:a@exemple.test", offre=evt4, cours=c4, occ=EVS.occurrence(c4),
                            email="a@exemple.test", nom="A", prix=0, source=EVS.SOURCE_MEMBRE)
    r2 = await EVS.reserver(b4, cle="membre:EVT:a@exemple.test", offre=evt4, cours=c4, occ=EVS.occurrence(c4),
                            email="a@exemple.test", nom="A", prix=0, source=EVS.SOURCE_MEMBRE)
    verifier("L double clic réservation gratuite -> UNE seule réservation", r1[1] and not r2[1] and r1[0]["id"] == r2[0]["id"]
             and len([x for x in b4["reservations"].docs if x.get("userEmail") == "a@exemple.test"]) == 1)

    # I / J / K — urgence et capacité.
    b5, evt5 = base_evenement(REGLES, texte_urgence="50 PLACES", texte_urgence_visible=True)
    c5 = b5["courses"].docs[0]
    for n in range(51):
        await EVS.reserver(b5, cle="stripe:cs_%d" % n, offre=evt5, cours=c5, occ=EVS.occurrence(c5), email="p%d@exemple.test" % n,
                           nom="P", prix=30, source=EVS.SOURCE_PAYANT)
    verifier("I texte « 50 PLACES » + aucune capacité : 51 places prises, jamais « complet »",
             await EVS.places_prises(b5, evt5) == 51 and EVS.capacite(evt5) is None and not await EVS.complet(b5, evt5))
    evt5.update(capacite_limitee=True, capacite_max=50)
    verifier("J capacité réelle 50 activée : complet -> la 51e est refusée", await EVS.complet(b5, evt5))
    verifier("J2 capacité saisie mais NON activée : aucune limite", EVS.capacite(dict(evt5, capacite_limitee=False)) is None)
    verifier("J3 le texte ne crée jamais de capacité (« 50 PLACES » sans case)",
             EVS.capacite({"texte_urgence": "50 PLACES", "texte_urgence_visible": True}) is None)

    # Espace : l'avantage réel est rendu par le serveur (prix public du moment + prix membre).
    b6, evt6 = base_evenement(REGLES)
    liste = await EVS.evenements_offerts(b6, "b@exemple.test")
    verifier("ESP espace du membre B : « 24 CHF au lieu de 30 CHF » calculé par le serveur",
             len(liste) == 1 and liste[0]["avantage"] == {"type": "reduction", "valeur": 20, "prix_public": 30.0, "prix_membre": 24.0}, liste)
    verifier("ESP2 membre D (aucun avantage) : rien d'offert", await EVS.evenements_offerts(b6, "d@exemple.test") == [])


def main():
    asyncio.run(principal())
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:700])
        _ok += ok
    print("%d / %d verifications V618M au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V576 — UN NOUVEAU CYCLE SUR LE MÊME CODE s'ouvre directement dans l'espace.

LE BESOIN (05/10/2026). Un membre renouvelle son forfait SANS changer de code :
l'ancien cycle (9/9, terminé) doit rester dans l'historique, le nouveau (0/63)
doit s'afficher tout de suite. Le modèle sait déjà porter deux fiches pour un
même code (une `canonical: true` vivante, l'ancienne `superseded_by`), mais la
simulation sur une copie des données réelles a montré DEUX défauts :

  1. `lota_etat_du_code` lisait TOUS les abonnements du code : l'ancien
     (`used_sessions: 9`, clos) contredisait la fiche neuve (`used: 0`) ->
     AMBIGU `consommation_contradictoire` -> l'écran affichait « Plusieurs
     forfaits sont enregistrés à ton nom » au lieu du compteur.
     Correctif : un abonnement CLOS PAR UN SUCCESSEUR (`superseded_by`) est de
     l'historique, pas un témoin du cycle en cours.
  2. L'espace prenait la fiche au `stripe_amount` le plus élevé, et le plafond
     V394 recalculait le solde sur cette fiche : l'ancienne (9/9) gagnait ->
     « 0 restante ». Correctif : une fiche `canonical: true` encore vivante fait
     foi, comme partout ailleurs (`lota_resoudre_code`).

Mesuré en lecture seule sur les 59 codes de production le 05/10 : aucun autre
code ne change d'état avec ces deux règles.

Garde-fous conservés (prouvés ici) : un abonnement clos SANS successeur
continue de déclencher `consommation_contradictoire` (on ne rend pas un essai
gratuit deux fois) ; sans fiche canonique, le choix historique est inchangé.

Données SYNTHÉTIQUES, base en mémoire, vraies routes, aucun réseau.
    python3 tests/test_v576_cycle_meme_code.py
"""
import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

S, SH = H.S, H.SH
verifier, appel, Requete = H.verifier, H.appel, H.Requete

COACH = "coach.v576@exemple.test"
CODE = "LEABOOST-26"
EMAIL = "lea.v576@exemple.test"
OFFRE = "offre-v576-8mois"
COURS = "cours-v576-soir"
OLD_DC, NEW_DC = "dc-v576-ancien", "dc-v576-neuf"
OLD_SUB, NEW_SUB = "sub-v576-ancien", "sub-v576-neuf"


def depart(cycle=True, canonical=True, successeur=True, prix_neuf=None):
    base = H._Base()
    base["feature_flags"].docs.append({"id": "feature_flags"})
    base["coaches"].docs.append({"id": "c-v576", "email": COACH, "name": "Coach V576"})
    _, wd = H._prochaine_occurrence(2, "18:30")
    base["courses"].docs.append({"id": COURS, "name": "Afro Soir V576", "weekday": wd, "time": "18:30",
                                 "locationName": "Salle", "visible": True, "archived": False, "coach_id": COACH})
    base["offers"].docs.append({"id": OFFRE, "name": "Membres 8 mois V576", "price": 199.99,
                                "visible": True, "coach_id": COACH, "linked_course_ids": [COURS]})
    # Ancien cycle : 9/9, terminé, payé 150 (prix le plus élevé des deux fiches).
    base["discount_codes"].docs.append({
        "id": OLD_DC, "code": CODE, "assignedEmail": EMAIL, "maxUses": 9, "used": 9, "coach_id": COACH,
        "active": not cycle, "expiresAt": "2026-10-05", "stripe_amount": 150.0, "courses": [COURS]})
    base["subscriptions"].docs.append({
        "id": OLD_SUB, "code": CODE, "email": EMAIL, "name": "Léa V576", "offer_id": OFFRE,
        "offer_name": "PULSE x10", "total_sessions": 9, "used_sessions": 9, "remaining_sessions": 0,
        "expires_at": "2026-10-05T23:59:59+00:00", "status": "completed", "coach_id": COACH})
    if cycle:
        _old_dc, _old_sub = base["discount_codes"].docs[0], base["subscriptions"].docs[0]
        _old_dc.update({"canonical": False, "superseded_by": NEW_DC})
        if successeur:
            _old_sub["superseded_by"] = NEW_SUB
        neuf = {"id": NEW_DC, "code": CODE, "assignedEmail": EMAIL, "maxUses": 63, "used": 0,
                "coach_id": COACH, "active": True, "expiresAt": "2027-06-04", "courses": [COURS]}
        if canonical:
            neuf["canonical"] = True
        if prix_neuf is not None:
            neuf["stripe_amount"] = prix_neuf
        base["discount_codes"].docs.append(neuf)
        base["subscriptions"].docs.append({
            "id": NEW_SUB, "code": CODE, "email": EMAIL, "name": "Léa V576", "offer_id": OFFRE,
            "offer_name": "Membres 8 mois V576", "total_sessions": 63, "used_sessions": 0,
            "remaining_sessions": 63, "expires_at": "2027-06-04T23:59:59+00:00", "status": "active",
            "coach_id": COACH})
    for module in (S, H.C, H.RR):
        module.db = base
    H.R.init_db(base)
    tok = H.jeton_espace(base, code=CODE, email=EMAIL, coach_id=COACH)
    return base, tok


async def espace(tok):
    return await appel(S.get_subscriber_space(CODE, Requete({}, {"x-espace-token": tok}), None))


def compteur(r):
    s = (r or {}).get("subscription") or {}
    return (s.get("total_sessions"), s.get("used_sessions"), s.get("remaining_sessions"),
            s.get("droits_etat"), s.get("droits_total"), s.get("droits_utilise"), s.get("droits_restant"))


async def main():
    print("\n1. Règle pure — lota_etat_du_code")
    base, _ = depart()
    docs = base["discount_codes"].docs
    subs = base["subscriptions"].docs
    e = SH.lota_etat_du_code(copy.deepcopy(docs), copy.deepcopy(subs))
    verifier("1a. nouveau cycle : OK 63 / 0 / 63 (plus de consommation_contradictoire)",
             (e["etat"], e["total"], e["utilise"], e["restant"]) == ("OK", 63, 0, 63), e)
    base, _ = depart(successeur=False)
    e = SH.lota_etat_du_code(copy.deepcopy(base["discount_codes"].docs), copy.deepcopy(base["subscriptions"].docs))
    verifier("1b. garde-fou : abonnement clos SANS successeur -> toujours AMBIGU consommation_contradictoire",
             (e["etat"], e["motif"]) == ("AMBIGU", "consommation_contradictoire"), e)
    e = SH.lota_etat_du_code([{"code": "ESSAI-1", "active": True, "maxUses": 1, "used": 0}],
                             [{"id": "s-essai", "status": "superseded", "used_sessions": 1,
                               "superseded_by": "s-pack-autre-code"}])
    verifier("1b2. fail-open fermé : essai clos par V397 au profit d'un AUTRE code -> toujours AMBIGU",
             (e["etat"], e["motif"]) == ("AMBIGU", "consommation_contradictoire"), e)
    e = SH.lota_etat_du_code([{"code": "ESSAI-1", "active": True, "maxUses": 1, "used": 0}],
                             [{"status": "completed", "used_sessions": 1}])
    verifier("1c. garde-fou historique (AFR-0C60A3) intact", (e["etat"], e["motif"]) == ("AMBIGU", "consommation_contradictoire"), e)
    e = await SH.lota_droits_du_code(depart()[0], CODE)
    verifier("1d. lota_droits_du_code (lecture en base) : OK 63 restantes", (e["etat"], e["restant"]) == ("OK", 63), e)

    print("\n2. Espace abonné — la vraie route")
    base, tok = depart()
    c, r = await espace(tok)
    verifier("2a. 200 + compteur 63 / 0 / 63 et droits OK 63 / 0 / 63 (fiche neuve SANS prix)",
             c == 200 and compteur(r) == (63, 0, 63, "OK", 63, 0, 63), (c, compteur(r) if c == 200 else r))
    verifier("2b. expiration du nouveau cycle", c == 200 and str((r["subscription"] or {}).get("expires_at", "")).startswith("2027-06-04"),
             (r.get("subscription") or {}).get("expires_at") if c == 200 else r)
    verifier("2c. une séance au moins proposée et incluse",
             c == 200 and any(o.get("inclus_abonnement") for o in r.get("upcoming_courses") or []))
    base, tok = depart(canonical=False)
    c, r = await espace(tok)
    verifier("2d. sans marque canonique, ancienne fiche INACTIVE : la seule fiche vivante fait foi (63 / 0 / 63)",
             c == 200 and compteur(r) == (63, 0, 63, "OK", 63, 0, 63), (c, compteur(r) if c == 200 else r))
    base, tok = depart(canonical=False)
    base["discount_codes"].docs[0]["active"] = True
    base["discount_codes"].docs[0]["expiresAt"] = "2027-01-01"
    base["discount_codes"].docs[0]["used"] = 5                    # 4 séances encore dues
    c, r = await espace(tok)
    verifier("2f. deux fiches VIVANTES sans canonique : AMBIGU, aucun chiffre deviné (inchangé)",
             c == 200 and compteur(r)[3] == "AMBIGU", (c, compteur(r) if c == 200 else r))
    base, tok = depart(cycle=False)
    c, r = await espace(tok)
    verifier("2e. sans nouveau cycle : 9 / 9 / 0, aucun droit (inchangé)",
             c == 200 and compteur(r)[:4] == (9, 9, 0, "AUCUN_DROIT"), (c, compteur(r) if c == 200 else r))

    print("\n3. Réservation — la vraie route, débit sur le NOUVEAU cycle")
    base, tok = depart()
    c, r = await espace(tok)
    occ = next((o for o in r.get("upcoming_courses") or [] if o.get("inclus_abonnement")), None)
    rq = Requete({"datetime": occ["datetime"] if occ else "", "quantity": 1, "terms_accepted": True},
                 {"x-espace-token": tok})
    cr, rr = await appel(S.reserve_course_from_space(CODE, COURS, rq))
    dc = {d["id"]: d for d in base["discount_codes"].docs}
    sb = {d["id"]: d for d in base["subscriptions"].docs}
    verifier("3a. réservation acceptée", cr == 200, (cr, rr))
    verifier("3b. fiche neuve débitée 1/63, ancienne intacte 9/9",
             dc[NEW_DC]["used"] == 1 and dc[OLD_DC]["used"] == 9, (dc[NEW_DC]["used"], dc[OLD_DC]["used"]))
    verifier("3c. abonnement neuf 1/62, ancien intact 9/9 completed",
             (sb[NEW_SUB]["used_sessions"], sb[NEW_SUB]["remaining_sessions"]) == (1, 62)
             and (sb[OLD_SUB]["used_sessions"], sb[OLD_SUB]["status"]) == (9, "completed"),
             (sb[NEW_SUB], sb[OLD_SUB]))
    c, r = await espace(tok)
    verifier("3d. espace relu : 63 / 1 / 62, droits OK", c == 200 and compteur(r) == (63, 1, 62, "OK", 63, 1, 62),
             compteur(r) if c == 200 else r)

    ok = sum(1 for x in H.RESULTATS if x[1]) if hasattr(H, "RESULTATS") else None
    return ok


asyncio.run(main())
_res = getattr(H, "RESULTATS", None) or getattr(H, "_RESULTATS", None)
if _res is not None:
    for _n, _b, _d in _res:
        print("  %-6s %s%s" % ("OK" if _b else "ECHEC", _n, "" if _b or not _d else "\n           -> %s" % (_d,)))
    _ok = sum(1 for x in _res if x[1])
    print("\n%d / %d vérifications V576 au vert" % (_ok, len(_res)))
    sys.exit(0 if _ok == len(_res) else 1)

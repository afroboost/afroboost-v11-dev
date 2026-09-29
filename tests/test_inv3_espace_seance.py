#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INV-3 — la séance d'une invitation reste choisissable dans l'espace abonné.

LE DÉFAUT. Le coach choisit la séance d'une invitation « Essai gratuit » /
« Événement gratuit » jusqu'à 30 jours (`referral_routes._occurrences`,
JOURS_AVANT=30). L'espace abonné (`GET /api/subscriber/space/{code}`) ne
calcule que 14 jours (`_v184_next_occurrences(course, days_ahead=14)`) et
l'écran n'en montre que 12. Une séance à J+15..J+30 (ou au-delà du 12e rang)
affichait donc un faux « n'est plus disponible ».

LA CORRECTION, MINIMALE. `?course=&occurrence=` (déjà transportés par INV-2)
ajoutent CETTE séance-là, et elle seule, si et seulement si : cours déjà dans
les cours filtrés de l'abonné (coach, visible, archivage, offre), couvert par
l'offre, vraie occurrence (`_v184_next_occurrences(course, 30)`), future,
≤ 30 jours. Sinon : réponse STRICTEMENT identique à aujourd'hui.

Ce banc exécute la VRAIE route (`get_subscriber_space`) et la VRAIE réservation
(`reserve_course_from_space`) sur le MongoDB en mémoire de
`test_referral_pass_duo.py` (importé, jamais recopié). AUCUN réseau, AUCUN
e-mail, AUCUNE donnée réelle.

Lancement :  python3 tests/test_inv3_espace_seance.py
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

S = H.S
verifier, appel, Requete = H.verifier, H.appel, H.Requete

COACH = "coach.inv3@exemple.test"
AUTRE_COACH = "autre.inv3@exemple.test"
CODE = "AFR-INV3AA"
EMAIL = "invitee.inv3@exemple.test"
OFFRE = "offre-inv3-essai"
C_SOIR = "cours-inv3-soir"            # lié à l'offre, 18:30, jour de J+21
C_HORS_OFFRE = "cours-inv3-hors"      # du coach, visible, NON lié à l'offre
C_AUTRE_COACH = "cours-inv3-autre"    # lié à l'offre mais d'un AUTRE coach
C_CACHE = "cours-inv3-cache"          # lié, du coach, mais invisible
C_MATIN = ["cours-inv3-matin-%d" % i for i in range(7)]   # un par jour : > 12 séances


def occ(jours, heure):
    """(« AAAA-MM-JJTHH:MM », weekday JS) de « dans N jours à HH:MM » (heure suisse)."""
    iso, wd = H._prochaine_occurrence(jours, heure)
    return iso[:16], wd


def depart():
    base = H._Base()
    base["feature_flags"].docs.append({"id": "feature_flags"})
    base["coaches"].docs += [{"id": "c-inv3", "email": COACH, "name": "Coach Inv3"},
                             {"id": "c-autre", "email": AUTRE_COACH, "name": "Autre"}]
    _, wd21 = occ(21, "18:30")
    cours = [
        {"id": C_SOIR, "name": "Afro Soir", "weekday": wd21, "time": "18:30", "locationName": "Salle S",
         "visible": True, "archived": False, "coach_id": COACH},
        {"id": C_HORS_OFFRE, "name": "Hors offre", "weekday": wd21, "time": "19:30", "locationName": "Salle H",
         "visible": True, "archived": False, "coach_id": COACH},
        {"id": C_AUTRE_COACH, "name": "Autre coach", "weekday": wd21, "time": "20:30", "locationName": "Salle A",
         "visible": True, "archived": False, "coach_id": AUTRE_COACH},
        {"id": C_CACHE, "name": "Caché", "weekday": wd21, "time": "21:30", "locationName": "Salle C",
         "visible": False, "archived": False, "coach_id": COACH},
    ]
    for i, cid in enumerate(C_MATIN):
        cours.append({"id": cid, "name": "Matin %d" % i, "weekday": i, "time": "07:00",
                      "locationName": "Salle M", "visible": True, "archived": False, "coach_id": COACH})
    base["courses"].docs += cours
    base["offers"].docs.append({
        "id": OFFRE, "name": "Essai Inv3", "price": 0.0, "visible": True, "coach_id": COACH,
        "linked_course_ids": [C_SOIR, C_AUTRE_COACH, C_CACHE] + C_MATIN})
    dans_2_mois = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    base["subscriptions"].docs.append({
        "id": "sub-inv3", "code": CODE, "email": EMAIL, "name": "Awa Invitée",
        "offer_name": "Essai Inv3", "offer_id": OFFRE, "total_sessions": 1, "used_sessions": 0,
        "remaining_sessions": 1, "expires_at": dans_2_mois, "status": "active", "coach_id": COACH})
    base["discount_codes"].docs.append({
        "id": "code-inv3", "code": CODE, "name": "Awa Invitée", "assignedEmail": EMAIL,
        "active": True, "maxUses": 1, "used": 0, "coach_id": COACH, "expiresAt": dans_2_mois})
    for module in (S, H.C, H.RR):
        module.db = base
    H.R.init_db(base)
    H.poser_mouchards()
    tok = H.jeton_espace(base, code=CODE, email=EMAIL, coach_id=COACH)
    return base, tok


async def espace(tok, **params):
    return await appel(S.get_subscriber_space(CODE, Requete({}, {"x-espace-token": tok}), None, **params))


def cles(r):
    return [(o.get("course_id"), str(o.get("datetime") or "")[:16]) for o in (r or {}).get("upcoming_courses") or []]


def canon(r):
    return json.dumps(r, sort_keys=True, default=str)


# ═══════════════════════════════════════════════════════════════════════════
async def partie_inclusion():
    base, tok = depart()
    c0, r0 = await espace(tok)
    verifier("INV3-0 espace de référence 200 (banc réel)", c0 == 200 and isinstance(r0.get("upcoming_courses"), list),
             (c0, r0 if c0 != 200 else ""))
    liste0 = cles(r0)
    verifier("INV3-0b la liste de référence dépasse 12 séances (13e rang existe)", len(liste0) > 12, len(liste0))

    j21, _ = occ(21, "18:30")
    c, r = await espace(tok, course=C_SOIR, occurrence=j21)
    verifier("INV3-1 J+21 absente sans paramètres (fenêtre 14 j)", (C_SOIR, j21) not in liste0)
    verifier("INV3-1b J+21 présente dans upcoming_courses avec ?course=&occurrence=",
             c == 200 and (C_SOIR, j21) in cles(r), cles(r)[-3:])
    ajout = [o for o in (r.get("upcoming_courses") or []) if (o.get("course_id"), str(o.get("datetime"))[:16]) == (C_SOIR, j21)]
    verifier("INV3-1c une seule fois, réservable (inclus_abonnement, INCLUDED)",
             len(ajout) == 1 and ajout[0].get("inclus_abonnement") is True and ajout[0].get("type_acces") == "INCLUDED",
             ajout)
    verifier("INV3-1d UNE séance ajoutée, pas toute la fenêtre de 30 jours",
             len(cles(r)) == len(liste0) + 1 and [k for k in cles(r) if k != (C_SOIR, j21)] == liste0,
             (len(cles(r)), len(liste0)))
    verifier("INV3-1e liste toujours triée par date", cles(r) == sorted(cles(r), key=lambda k: k[1]))
    _cles_occ = set(ajout[0].keys()) if ajout else set()
    _cles_ref = set((r0.get("upcoming_courses") or [{}])[0].keys())
    verifier("INV3-1f mêmes champs que les autres séances (aucune donnée supplémentaire)",
             _cles_occ == _cles_ref, _cles_occ ^ _cles_ref)
    _hors = {k: v for k, v in r.items() if k != "upcoming_courses"}
    _hors0 = {k: v for k, v in r0.items() if k != "upcoming_courses"}
    verifier("INV3-1g le reste de la réponse est identique", canon(_hors) == canon(_hors0))

    # La réservation de cette séance, sur la vraie route.
    rq = Requete({"datetime": ajout[0]["datetime"] if ajout else j21 + ":00", "quantity": 1,
                  "terms_accepted": True}, {"x-espace-token": tok})
    cr, rr = await appel(S.reserve_course_from_space(CODE, C_SOIR, rq))
    resas = [x for x in base["reservations"].docs if x.get("courseId") == C_SOIR]
    verifier("INV3-2 la séance J+21 se réserve (route réelle)",
             cr == 200 and len(resas) == 1 and str(resas[0].get("datetime"))[:16] == j21,
             (cr, rr, [str(x.get("datetime")) for x in resas]))

    # 13e rang (index 12) : déjà servie par le serveur, la présélection est côté écran.
    base, tok = depart()
    c0, r0 = await espace(tok)
    liste0 = cles(r0)
    rang13 = liste0[12] if len(liste0) > 12 else (None, None)
    c, r = await espace(tok, course=rang13[0], occurrence=rang13[1])
    verifier("INV3-3 séance au 13e rang : présente, jamais dupliquée, réponse identique",
             c == 200 and rang13[0] and cles(r).count(rang13) == 1 and canon(r) == canon(r0), rang13)


async def partie_refus():
    base, tok = depart()
    c0, r0 = await espace(tok)
    ref = canon(r0)
    j21_soir, _ = occ(21, "18:30")
    j21_hors, _ = occ(21, "19:30")
    j21_autre, _ = occ(21, "20:30")
    j21_cache, _ = occ(21, "21:30")
    j21_faux, _ = occ(21, "19:00")
    j20, _ = occ(20, "18:30")
    j_passe, _ = occ(-7, "18:30")
    j31, wd31 = occ(31, "07:00")
    j28, wd28 = occ(28, "07:00")
    cas = [
        ("INV3-4 cours hors offre -> aucun ajout", C_HORS_OFFRE, j21_hors),
        ("INV3-4b cours d'un autre coach (même lié à l'offre) -> aucun ajout", C_AUTRE_COACH, j21_autre),
        ("INV3-4c cours invisible -> aucun ajout", C_CACHE, j21_cache),
        ("INV3-4d cours inexistant -> aucun ajout", "cours-inconnu", j21_soir),
        ("INV3-5 heure absente du planning -> aucun ajout", C_SOIR, j21_faux),
        ("INV3-5b mauvais jour de semaine -> aucun ajout", C_SOIR, j20),
        ("INV3-5c occurrence passée -> aucun ajout", C_SOIR, j_passe),
        ("INV3-6 J+31 -> aucun ajout", C_MATIN[wd31], j31),
    ]
    for nom, cid, oc in cas:
        c, r = await espace(tok, course=cid, occurrence=oc)
        verifier(nom, c == 200 and canon(r) == ref, (cid, oc, cles(r)[-2:]))
    c, r = await espace(tok, course=C_MATIN[wd28], occurrence=j28)
    verifier("INV3-6b témoin : J+28 du même planning -> ajoutée", c == 200 and (C_MATIN[wd28], j28) in cles(r))

    # Sans paramètres : identique à la référence (deux lectures successives).
    c1, r1 = await espace(tok)
    verifier("INV3-7 sans paramètres -> réponse identique", c1 == 200 and canon(r1) == ref)
    malformes = [
        {"course": "../etc", "occurrence": j21_soir},
        {"course": C_SOIR, "occurrence": j21_soir.replace("T", " ")},
        {"course": C_SOIR, "occurrence": j21_soir + ":00"},
        {"course": C_SOIR, "occurrence": "2026-13-45T25:99"},
        {"course": "x" * 65, "occurrence": j21_soir},
        {"course": {"$ne": ""}, "occurrence": j21_soir},
        {"course": C_SOIR, "occurrence": None},
        {"course": None, "occurrence": j21_soir},
        {"course": "", "occurrence": ""},
    ]
    ok = True
    for p in malformes:
        c, r = await espace(tok, **p)
        if c != 200 or canon(r) != ref:
            ok = False
    verifier("INV3-8 paramètres malformés -> ignorés (réponse identique)", ok)

    # Aucun nouveau droit : sans jeton, la route reste fermée même avec les paramètres.
    c, r = await appel(S.get_subscriber_space(CODE, Requete({}, {}), None, course=C_SOIR, occurrence=j21_soir))
    verifier("INV3-9 sans jeton -> refus inchangé (404 neutre), aucune séance servie",
             c == 404 and "upcoming_courses" not in (r or {}), (c, r))


async def partie_structure():
    import inspect
    sig = inspect.signature(S.get_subscriber_space)
    verifier("INV3-10 la route accepte `course` et `occurrence` optionnels",
             "course" in sig.parameters and "occurrence" in sig.parameters
             and sig.parameters["course"].default is None and sig.parameters["occurrence"].default is None)
    src = inspect.getsource(S.get_subscriber_space)
    verifier("INV3-10b la fenêtre générale reste à 14 jours (pas d'élargissement à 30)",
             src.count("_v184_next_occurrences(course, days_ahead=14)") == 2
             and "days_ahead=30" not in src.replace("_inv3_seance_invitee", ""))
    verifier("INV3-10c l'ajout passe par la règle pure `_inv3_seance_invitee`",
             "_inv3_seance_invitee(" in src)


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:  # noqa: BLE001
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_inclusion, partie_refus, partie_structure):
        try:
            boucle.run_until_complete(partie())
        except Exception as err:  # noqa: BLE001
            import traceback
            verifier("PARTIE %s sans exception" % partie.__name__, False,
                     "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1500:]))
    res = [r for r in H.RESULTATS if str(r[0]).startswith(("INV3", "PARTIE"))]
    ok = sum(1 for _, c, _ in res if c)
    for nom, cond, detail in res:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom, ("" if cond or not detail else "\n         -> " + str(detail)[:600])))
    print("%d / %d verifications INV-3 au vert" % (ok, len(res)))
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())

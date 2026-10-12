#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V607 — ESSAI GRATUIT « MOI D'ABORD → PUIS MON AMI » + cause du « dimanche ».

Ce banc prouve, sur les VRAIES routes (MongoDB en mémoire, aucun réseau) :
  * DIMANCHE — la cause exacte : une campagne du super-admin a la clé de
    propriétaire "" (plateforme) alors que ses cours portent son e-mail ;
    `_cours_offrables` comparait les clés BRUTES et ne gardait que le cours
    du pass (le mercredi). Après correction : le cours du dimanche (weekday 0)
    est proposé ; le cours d'un partenaire ne l'est toujours pas ;
  * l'invité d'une chaîne d'essai choisit SA séance (PATCH /occurrence avec
    course_id) parmi la liste du serveur, avec version, refus clairs ;
  * l'invitation de son ami hérite de cette séance par défaut ;
  * l'obligation d'inviter reste celle du SERVEUR (409 invitation_requise) ;
  * après partage, le changement de séance qui trahirait l'invitation envoyée
    est refusé (409 invitation_deja_partagee) ;
  * l'ami (maillon suivant) peut changer SA séance ; la place de son parrain
    reste celle qu'il a déjà (aucun second débit) ;
  * le Pass Duo (hors campagne) ne change pas : un maillon y reste lié ;
  * le funnel V607 (`invitation_events`) reçoit essai_debloque /
    reservation_confirmee / nouvelle_invitation_generee, sans donnée personnelle.

Lancement :  python3 tests/test_parrainage_essai_moi_dabord.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_campagne_chaine as CC  # noqa: E402  (pose le banc V3 + campagnes)

V3, H = CC.V3, CC.H
R, E = H.R, H.E
verifier, appel, req, raison = H.verifier, H.appel, V3.req, V3.raison
doc_par_tok, chaine, partager, rejoindre, pub = V3.doc_par_tok, V3.chaine, V3.partager, V3.rejoindre, V3.pub
ident, resas_de, codes_de = V3.ident, V3.resas_de, V3.codes_de

ADMIN = H.ADMIN
COURS_DIM = "cours-dimanche-auvernier"
COURS_PART = "cours-du-partenaire"


async def options(tok):
    return await appel(R.referral_chaine_options(tok, req()))


async def ma_seance(tok, corps):
    return await appel(R.referral_changer_seance(tok, req(corps)))


def seances(rep):
    return {s["course_id"]: s["occurrences"] for s in (rep or {}).get("seances") or []}


def depart():
    """La situation de PRODUCTION (sauvegarde du 22/09) : campagne du super-admin
    (clé ""), cours mercredi + dimanche portant l'e-mail du super-admin, offre
    d'essai liée aux deux (+ un cours partenaire lié par erreur)."""
    base, occ = CC.depart(coach_id="")
    for c in base["courses"].docs:
        if c.get("id") == H.COURS_DUO:
            c["coach_id"] = ADMIN
    base["courses"].docs += [
        {"id": COURS_DIM, "name": "Cours à l'unité", "weekday": 0, "time": "18:00",
         "locationName": "Bord du Lac, Auvernier", "visible": True, "archived": False, "coach_id": ADMIN},
        {"id": COURS_PART, "name": "Cours partenaire", "weekday": 0, "time": "20:00",
         "locationName": "Studio P", "visible": True, "archived": False, "coach_id": CC.PARTENAIRE},
    ]
    for o in base["offers"].docs:
        if o.get("id") == CC.OFFRE_CAMP:
            o["coach_id"] = ADMIN
            o["linked_course_ids"] = [H.COURS_DUO, COURS_DIM, COURS_PART]
    return base, occ


def evenements(base, ev=None):
    return [d for d in base["invitation_events"].docs if ev is None or d.get("evenement") == ev]


async def partie_dimanche():
    # Le moteur pur : la règle qui excluait le dimanche, puis la correction.
    verifier("D0. AVANT : clé brute du cours du super-admin != clé de la campagne plateforme (\"\")",
             E._proprietaire(ADMIN) != E._proprietaire(""), E._proprietaire(ADMIN))
    verifier("D0b. APRÈS : clé canonique — super-admin, sans propriétaire, sentinelle = plateforme",
             E.proprietaire_canonique(ADMIN, [ADMIN]) == "" and E.proprietaire_canonique(None, [ADMIN]) == ""
             and E.proprietaire_canonique("bassi_default", [ADMIN]) == ""
             and E.proprietaire_canonique(" Contact.Artboost@Gmail.com ", [ADMIN]) == "")
    verifier("D0c. un partenaire reste lui-même (cloisonnement intact)",
             E.proprietaire_canonique(CC.PARTENAIRE, [ADMIN]) == CC.PARTENAIRE)
    base, occ = depart()
    dim = next(c for c in base["courses"].docs if c["id"] == COURS_DIM)
    occ_dim = R._occurrences(dim)
    verifier("D1. weekday 0 (dimanche) n'est PAS traité comme vide : occurrences du dimanche calculées",
             len(occ_dim) >= 4 and all(H.datetime.fromisoformat(o).weekday() == 6 for o in occ_dim), occ_dim)
    c, r = await entree(base)
    t0 = r["share_token"]
    c, op = await options(t0)
    s = seances(op)
    verifier("D2. options de la chaîne d'une campagne plateforme : mercredi ET dimanche proposés",
             c == 200 and H.COURS_DUO in s and COURS_DIM in s and s[COURS_DIM] == occ_dim, list(s))
    verifier("D3. le cours d'un partenaire (lié à l'offre) n'est JAMAIS proposé à une campagne plateforme",
             COURS_PART not in s, list(s))


async def entree(base, cle=None):
    return await CC.entree(cle=cle)


async def partie_moi_dabord():
    base, occ = depart()
    c, r = await entree(base)
    t0 = r["share_token"]
    c, g = await pub(t0)
    verifier("M0. la page reçue est un Essai gratuit (jamais « Pass Duo »), chaîne requise",
             c == 200 and g.get("invitation_type") == "trial" and g.get("chain_required") is True, g.get("invitation_type"))
    dim = next(x for x in base["courses"].docs if x["id"] == COURS_DIM)
    o_dim, o_dim2 = R._occurrences(dim)[0], R._occurrences(dim)[1]

    c, x = await ma_seance(t0, {"course_id": COURS_DIM, "occurrence": o_dim, "version": 99})
    verifier("M1. version périmée -> 409 conflit_version, rien n'est écrit",
             c == 409 and raison(x) == "conflit_version" and doc_par_tok(base, t0)["occurrence"] == occ, (c, x))
    c, x = await ma_seance(t0, {"course_id": COURS_DIM, "occurrence": o_dim[:10] + "T03:00:00", "version": g["version"]})
    verifier("M2. date hors de la liste du serveur -> 400 seance_indisponible", c == 400 and raison(x) == "seance_indisponible", (c, x))
    c, x = await ma_seance(t0, {"course_id": COURS_PART, "occurrence": R._occurrences(
        next(y for y in base["courses"].docs if y["id"] == COURS_PART))[0], "version": g["version"]})
    verifier("M3. cours d'un partenaire -> 400 seance_non_autorisee", c == 400 and raison(x) == "seance_non_autorisee", (c, x))
    c, x = await ma_seance(t0, {"course_id": COURS_DIM, "occurrence": o_dim, "version": g["version"]})
    d0 = doc_par_tok(base, t0)
    verifier("M4. l'invité choisit SA séance (dimanche) -> 200 ; le pass porte cours, date, expiration, instantané",
             c == 200 and d0["course_id"] == COURS_DIM and d0["occurrence"] == o_dim and d0["expires_at"] == o_dim
             and d0["course_snapshot"]["locationName"] == "Bord du Lac, Auvernier"
             and x.get("occurrence") == o_dim and x.get("invitation_type") == "trial"
             and x.get("chain_required") is True, (c, str(x)[:300]))
    verifier("M4b. réponse publique : aucune donnée personnelle", not CC.fuite(x, base), str(x)[:300])
    c, x2 = await ma_seance(t0, {"course_id": COURS_DIM, "occurrence": o_dim, "version": x["version"]})
    verifier("M5. même séance renvoyée -> 200 idempotent, aucune écriture (version inchangée)",
             c == 200 and x2["version"] == x["version"], (c, x2.get("version")))

    c, x = await rejoindre(t0, 1, nom="Alice")
    verifier("M6. OBLIGATION SERVEUR conservée : join avant partage -> 409 invitation_requise",
             c == 409 and raison(x) == "invitation_requise", (c, x))

    c, rc = await chaine(t0)       # le front ne transmet PAS de séance : l'ami hérite de la mienne
    t1 = rc["child"]["share_token"] if c == 201 else None
    d1 = doc_par_tok(base, t1) if t1 else {}
    verifier("M7. l'invitation de l'ami hérite de MA séance (même cours, même date), type Essai gratuit",
             c == 201 and d1.get("course_id") == COURS_DIM and d1.get("occurrence") == o_dim
             and rc["child"]["kind"] == "trial" and E.seance_choisie(d1) is False, (c, d1.get("course_id")))
    ng = evenements(base, "nouvelle_invitation_generee")
    verifier("M8. funnel : nouvelle_invitation_generee (trial, génération 2, jeton en empreinte)",
             len(ng) == 1 and ng[0]["type_invitation"] == "trial" and ng[0]["generation"] == 2
             and ng[0]["jeton"] != t1 and ng[0]["campagne_id"] == CC.CAMP_ID, ng)

    # Avant partage, je peux encore changer : l'enfant (qui me suit) suit.
    c, g = await pub(t0)
    c, x = await ma_seance(t0, {"course_id": COURS_DIM, "occurrence": o_dim2, "version": g["version"]})
    verifier("M9. avant partage : je change ma séance -> l'invitation de mon ami suit (non envoyée)",
             c == 200 and doc_par_tok(base, t1)["occurrence"] == o_dim2, (c, doc_par_tok(base, t1).get("occurrence")))
    c, x = await partager(t0)
    verifier("M10. partage DÉCLENCHÉ -> enregistré", c == 200 and x.get("shared") is True, (c, x))
    c, g = await pub(t0)
    c, x = await ma_seance(t0, {"course_id": COURS_DIM, "occurrence": o_dim, "version": g["version"]})
    verifier("M11. après partage : changer ma séance -> 409 invitation_deja_partagee (rien de silencieux)",
             c == 409 and raison(x) == "invitation_deja_partagee" and doc_par_tok(base, t0)["occurrence"] == o_dim2, (c, x))

    c, x = await rejoindre(t0, 1, nom="Alice")
    e1 = ident(1)[0]
    r1 = resas_de(base, e1)
    verifier("M12. join après partage -> 200 ; la réservation est sur MA séance (dimanche)",
             c == 200 and len(r1) == 1 and r1[0].get("courseId") == COURS_DIM, (c, [(r.get("courseId"), r.get("datetime")) for r in r1]))
    eb, rc_ = evenements(base, "essai_debloque"), evenements(base, "reservation_confirmee")
    verifier("M13. funnel : essai_debloque + reservation_confirmee (trial, génération 1)",
             len(eb) == 1 and len(rc_) == 1 and eb[0]["type_invitation"] == "trial" and eb[0]["generation"] == 1, (eb, rc_))
    c, x = await rejoindre(t0, 1, nom="Alice")
    verifier("M14. rejeu du join -> idempotent, aucune ligne de funnel en double",
             c == 200 and len(evenements(base, "essai_debloque")) == 1, (c, len(evenements(base, "essai_debloque"))))
    verifier("M15. funnel sans donnée personnelle (ni e-mail, ni téléphone, ni jeton en clair)",
             not any(e1 in str(d) or t0 in str(d) or ident(1)[1] in str(d) for d in evenements(base)),
             evenements(base))

    # L'AMI (maillon suivant) choisit SA séance de son côté.
    c, g1 = await pub(t1)
    verifier("M16. l'ami voit aussi un Essai gratuit", c == 200 and g1.get("invitation_type") == "trial", g1.get("invitation_type"))
    duo = next(x for x in base["courses"].docs if x["id"] == H.COURS_DUO)
    o_mer = R._occurrences(duo)[0]
    c, x = await ma_seance(t1, {"course_id": H.COURS_DUO, "occurrence": o_mer, "version": g1["version"]})
    d1 = doc_par_tok(base, t1)
    verifier("M17. l'ami change SA séance -> 200, marquée seance_choisie (ma séance à moi ne bouge pas)",
             c == 200 and d1["course_id"] == H.COURS_DUO and d1["occurrence"] == o_mer and E.seance_choisie(d1)
             and doc_par_tok(base, t0)["occurrence"] == o_dim2, (c, x))
    await chaine(t1)
    await partager(t1)
    c, x = await rejoindre(t1, 2, nom="Bruno")
    d1 = doc_par_tok(base, t1)
    verifier("M18. l'ami s'inscrit sur SA séance ; ma place reste la mienne (aucune 2e réservation pour moi)",
             c == 200 and len(resas_de(base, ident(2)[0])) == 1 and resas_de(base, ident(2)[0])[0].get("courseId") == H.COURS_DUO
             and len(resas_de(base, e1)) == 1 and d1.get("status") == "unlocked", (c, d1.get("status"), d1.get("blocked_reason")))


async def partie_pass_duo_inchange():
    base, occ = H.base_de_depart(chaine=True)
    c, p = await H.creer_pass(base, occ)
    tp = p["share_token"]
    c, g = await pub(tp)
    verifier("P1. Pass Duo : type pass_duo (jamais « Essai gratuit »)", g.get("invitation_type") == "pass_duo", g.get("invitation_type"))
    verifier("P1b. parcours_essai faux pour un Pass Duo", E.parcours_essai(doc_par_tok(base, tp)) is False)
    c, rc = await chaine(tp)
    tk = rc["child"]["share_token"]
    c, gk = await pub(tk)
    c, x = await ma_seance(tk, {"course_id": H.COURS_DUO, "occurrence": occ, "version": gk["version"]})
    verifier("P2. Pass Duo : un maillon reste lié à la séance de son parrain (409 pass_non_modifiable)",
             c == 409 and raison(x) == "pass_non_modifiable", (c, x))
    verifier("P3. aucune ligne de funnel « essai » pour un Pass Duo sans partage",
             not evenements(base, "essai_debloque"))


async def principal():
    await partie_dimanche()
    await partie_moi_dabord()
    await partie_pass_duo_inchange()


def main():
    _tmp = tempfile.mkdtemp(prefix="banc_v607_")
    _orig = H.S._V413_MEDIA_DIR
    H.S._V413_MEDIA_DIR = _tmp
    try:
        asyncio.run(principal())
    except Exception as err:  # noqa: BLE001
        import traceback
        verifier("banc exécuté sans exception", False, "%s\n%s" % (err, traceback.format_exc()[-1500:]))
    finally:
        H.S._V413_MEDIA_DIR = _orig
        shutil.rmtree(_tmp, ignore_errors=True)
    ok = sum(1 for r in H.RESULTATS if r[1])
    total = len(H.RESULTATS)
    for nom, bon, detail in H.RESULTATS:
        print("  %s  %s%s" % ("OK   " if bon else "ECHEC", nom, "" if bon else "\n         -> " + str(detail)[:900]))
    print("%d / %d verifications V607 au vert" % (ok, total))
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()

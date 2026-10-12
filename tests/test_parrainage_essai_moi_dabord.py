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


async def suivante(tok, cle=V3._DEF):
    return await appel(R.referral_chaine_suivante(tok, req({}, V3._entete_cle(tok, cle))))


async def partager_enfant(tok_parent, tok_enfant, canal="whatsapp"):
    return await appel(R.referral_chaine_partager(
        tok_parent, req({"channel": canal, "child_token": tok_enfant}, V3._entete_cle(tok_parent, V3._DEF))))


def enfants(base, parent_id):
    return [d for d in base["referral_passes"].docs if (d.get("chain") or {}).get("parent_pass_id") == parent_id]


async def partie_inviter_encore():
    """V607g — Sophie (P0, génération 1, invitée par la campagne) -> Nadine (A),
    puis « Inviter encore » -> Julie (B), puis C… ; Nadine -> génération 3."""
    base, occ = depart()
    c, r = await entree(base)
    t0 = r["share_token"]
    p0 = doc_par_tok(base, t0)
    c, x = await suivante(t0)
    verifier("E0. « Inviter encore » AVANT tout (rien de partagé, pas inscrite) -> 409, rien créé",
             c == 409 and not enfants(base, p0["id"]), (c, x))
    c, ra = await chaine(t0)
    tA = ra["child"]["share_token"]
    await partager(t0)
    c, x = await suivante(t0)
    verifier("E1. partagé mais Sophie PAS encore inscrite -> 409 essai_non_confirme (preuve serveur exigée)",
             c == 409 and raison(x) == "essai_non_confirme" and len(enfants(base, p0["id"])) == 1, (c, x))
    c, x = await rejoindre(t0, 1, nom="Sophie")
    verifier("E2. Sophie rejoint son essai (1re invitation obligatoire, inchangée)", c == 200, (c, str(x)[:200]))
    c, x = await suivante(t0, cle="cle-d-un-autre-appareil")
    verifier("E3. « Inviter encore » depuis un AUTRE appareil -> 403, rien créé",
             c == 403 and len(enfants(base, p0["id"])) == 1, (c, x))
    c, rb = await suivante(t0)
    tB = rb.get("child", {}).get("share_token")
    dA, dB = doc_par_tok(base, tA), doc_par_tok(base, tB) or {}
    verifier("E4. « Inviter encore » -> 201, NOUVEAU lien (jeton distinct de celui de Nadine)",
             c == 201 and tB and tB != tA and tB != t0, (c, str(rb)[:300]))
    verifier("E5. même parent, même racine, même profondeur (même génération), même campagne, rang 2",
             dB.get("chain", {}).get("parent_pass_id") == p0["id"]
             and dB["chain"].get("root_pass_id") == dA["chain"].get("root_pass_id")
             and dB["chain"].get("depth") == dA["chain"].get("depth") == 1
             and (dB.get("origin") or {}).get("campaign_id") == CC.CAMP_ID and dB["chain"].get("rang") == 2,
             dB.get("chain"))
    verifier("E6. son parrain est Sophie, déjà LIÉE (jamais « en attente »), même séance que la sienne",
             dB["sponsor"]["email_norm"] == ident(1)[0] and dB["sponsor"]["pending"] is False
             and dB["occurrence"] == doc_par_tok(base, t0)["occurrence"], dB.get("sponsor"))
    verifier("E6b. réponse sans donnée personnelle", not CC.fuite(rb, base), str(rb)[:300])
    c, rb2 = await suivante(t0)
    verifier("E7. double clic : la même invitation est rendue (200), jamais deux",
             c == 200 and rb2["child"]["share_token"] == tB and len(enfants(base, p0["id"])) == 2, (c, len(enfants(base, p0["id"]))))
    gen = [d for d in evenements(base, "nouvelle_invitation_generee")]
    verifier("E8. funnel : nouvelle_invitation_generee pour A et B (génération 2), une ligne par invitation",
             len(gen) == 2 and all(g["generation"] == 2 and g["type_invitation"] == "trial" for g in gen), gen)

    # Nadine (A) : son essai, puis SA propre invitation obligatoire -> génération 3.
    c, rn = await chaine(tA)
    tA1 = rn["child"]["share_token"]
    await partager(tA)
    c, x = await rejoindre(tA, 2, nom="Nadine")
    verifier("E9. Nadine réserve sur le lien A", c == 200 and len(resas_de(base, ident(2)[0])) == 1, (c, str(x)[:200]))
    await chaine(tA1)
    await partager(tA1)
    c, x = await rejoindre(tA1, 4, nom="David")
    g3 = [g for g in evenements(base, "nouvelle_invitation_generee") if g["generation"] == 3]
    verifier("E10. Nadine -> personne suivante : inscrite (génération 3 au funnel)",
             c == 200 and len(resas_de(base, ident(4)[0])) == 1 and len(g3) >= 1, (c, g3))

    # Julie (B) : partage déclenché par Sophie, puis Julie réserve indépendamment.
    c, x = await partager_enfant(t0, tB)
    verifier("E11. partage de l'invitation B (même appareil) enregistré sur B", c == 200
             and x["child"]["share_token"] == tB and E.partage_chaine(doc_par_tok(base, tB))["shared"], (c, x))
    await chaine(tB)
    await partager(tB)
    c, x = await rejoindre(tB, 3, nom="Julie")
    dB = doc_par_tok(base, tB)
    verifier("E12. Julie réserve sur le lien B ; B débloqué ; Sophie garde UNE seule place (aucun 2e débit)",
             c == 200 and len(resas_de(base, ident(3)[0])) == 1 and dB.get("status") == "unlocked"
             and len(resas_de(base, ident(1)[0])) == 1, (c, dB.get("status"), dB.get("blocked_reason")))
    c, x = await rejoindre(tB, 5, nom="Emma")
    verifier("E13. jeton fermé (B rejoint) : jamais réutilisé -> 409 pass_ferme", c == 409 and raison(x) == "pass_ferme", (c, x))

    c, rc = await suivante(t0)
    tC = rc.get("child", {}).get("share_token")
    verifier("E14. « Inviter encore » -> C, rang 3, jeton jamais vu",
             c == 201 and tC not in (t0, tA, tB, tA1) and doc_par_tok(base, tC)["chain"]["rang"] == 3
             and len({d["share_token"] for d in base["referral_passes"].docs}) == len(base["referral_passes"].docs), (c, tC))
    await partager_enfant(t0, tC)
    await chaine(tC)
    await partager(tC)
    c, x = await rejoindre(tC, 3, email="julie.autre@exemple.test", nom="Julie")
    verifier("E15. essai unique : Julie (déjà essai, même numéro) sur C -> refus habituel 409",
             c == 409 and raison(x) in E.REFUS_IDENTITE_DEFINITIFS, (c, x))

    # Plafond : invitations ouvertes non rejointes.
    _orig = E.ENFANTS_OUVERTS_MAX
    try:
        E.ENFANTS_OUVERTS_MAX = len([d for d in enfants(base, p0["id"]) if not d.get("invitee")])
        c, x = await suivante(t0)
        verifier("E16. plafond d'invitations ouvertes atteint -> 409 invitations_ouvertes_max, rien créé",
                 c == 409 and raison(x) == "invitations_ouvertes_max", (c, x))
    finally:
        E.ENFANTS_OUVERTS_MAX = _orig
    verifier("E17. l'obligatoire reste LA référence (porte du join, A1) : _enfant_de rend A",
             (await R._enfant_de(doc_par_tok(base, t0)))["share_token"] == tA)

    # Pass Duo : aucun changement.
    base2, occ2 = H.base_de_depart(chaine=True)
    c, p = await H.creer_pass(base2, occ2)
    tp = p["share_token"]
    await chaine(tp)
    await partager(tp)
    await rejoindre(tp, 6, nom="Farid")
    n_avant = len(base2["referral_passes"].docs)
    c, x = await suivante(tp)
    verifier("E18. Pass Duo : « Inviter encore » -> 409, aucune invitation créée (comportement inchangé)",
             c == 409 and len(base2["referral_passes"].docs) == n_avant, (c, x))

    # Production sans migration d'index : refus propre, rien d'écrit.
    base3, occ3 = depart()
    base3["referral_passes"].uniques = [u for u in base3["referral_passes"].uniques
                                        if u[0] != ("chain.parent_pass_id", "chain.rang?")] + [
        (("chain.parent_pass_id",), {"chain.parent_pass_id": {"$type": "string"}})]
    c, r = await entree(base3)
    t3 = r["share_token"]
    await chaine(t3)
    await partager(t3)
    await rejoindre(t3, 7, nom="Gaelle")
    n_avant = len(base3["referral_passes"].docs)
    c, x = await suivante(t3)
    verifier("E19. index historique non migré -> 409 invitation_suivante_indisponible, rien d'écrit",
             c == 409 and raison(x) == "invitation_suivante_indisponible" and len(base3["referral_passes"].docs) == n_avant, (c, x))


async def principal():
    await partie_dimanche()
    await partie_moi_dabord()
    await partie_pass_duo_inchange()
    await partie_inviter_encore()


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

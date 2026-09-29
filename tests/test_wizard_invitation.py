#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V558 — WIZARD « INVITATION & PARRAINAGE » + ESSAI GRATUIT UNIQUE.

Ce banc prouve, sur les VRAIES routes et les VRAIES gardes ESSAI-1 / ESSAI-4
(MongoDB en mémoire, aucun réseau) :
  * étape « Offre » : le type choisi est conservé (`chain.kind`), Parrainage /
    Affiliation n'existent QUE si un programme réel est configuré ;
  * étape « Séance » : chaque maillon choisit la séance qu'il offre au suivant —
    l'enfant la porte, le parent garde la sienne ; séance d'un autre coach,
    passée ou hors liste refusée ; pas de changement silencieux après envoi ;
  * l'identité réelle de l'invitant sur la page / l'aperçu ;
  * l'essai gratuit : UNE fois par personne, à vie — ni une nouvelle invitation,
    ni une nouvelle campagne, ni un autre coach ne le rouvrent ; inviter ne
    rend JAMAIS un essai à l'invitant ; la récompense de parrainage n'est pas un
    essai ; « déjà client » ne casse pas la chaîne de son ami.

Lancement :  python3 tests/test_wizard_invitation.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_campagne_chaine as CC  # noqa: E402  (pose le banc V3 + campagnes)

V3, H = CC.V3, CC.H
R, E = H.R, H.E
verifier, appel, req, raison = H.verifier, H.appel, V3.req, V3.raison
doc_par_tok, chaine, chaine_patch = V3.doc_par_tok, V3.chaine, V3.chaine_patch
partager, rejoindre, pub = V3.partager, V3.rejoindre, V3.pub
preparer_et_partager, resas_de, codes_de, debits, ident = (
    V3.preparer_et_partager, V3.resas_de, V3.codes_de, V3.debits, V3.ident)
CLES = V3.CLES

COURS2 = "cours-duo-2-cardio"          # même propriétaire (plateforme), offre A autorisée
COURS_AUTRE = "cours-autre-coach"      # coach B : jamais proposé
COURS_PART = "cours-partenaire"        # cours du partenaire de la campagne
AUTRE_COACH = "autre@coach.test"
FABIEN, SOPHIE, MARC, HUGO = 1, 2, 3, 5


async def options(tok):
    return await appel(R.referral_chaine_options(tok, req()))


def depart():
    base, occ = CC.depart()
    _o2, wd2 = H._prochaine_occurrence(2, "18:45")
    base["courses"].docs += [
        {"id": COURS2, "name": "Afroboost Silent – Session Cardio", "weekday": wd2, "time": "18:45",
         "locationName": "Ch. des Valangines 97, 2000 Neuchâtel", "visible": True, "archived": False,
         "duo_enabled": True, "coach_id": None, "duo_offer_ids": [H.OFFRE_A]},
        {"id": COURS_AUTRE, "name": "Cours du coach B", "weekday": wd2, "time": "19:00",
         "locationName": "Ailleurs", "visible": True, "archived": False, "duo_enabled": True,
         "coach_id": AUTRE_COACH, "duo_offer_ids": [H.OFFRE_A]},
        {"id": COURS_PART, "name": "Cours partenaire", "weekday": wd2, "time": "20:00",
         "locationName": "Studio P", "visible": True, "archived": False, "coach_id": CC.PARTENAIRE},
    ]
    for o in base["offers"].docs:
        if o.get("id") == CC.OFFRE_CAMP:
            o["linked_course_ids"] = [H.COURS_DUO, COURS_PART, COURS_AUTRE]
    return base, occ


def seances(rep):
    return {s["course_id"]: s["occurrences"] for s in (rep or {}).get("seances") or []}


# ═══════════════════════════════════════════════════════════════════════════
async def partie_wizard():
    base, occ = depart()
    c, p0 = await H.creer_pass(base, occ)
    t0 = p0["share_token"]
    c, op = await options(t0)
    s = seances(op)
    verifier("0. options : types = [pass_duo] seul (aucun programme) ; séances du même propriétaire",
             c == 200 and [t["id"] for t in op["types"]] == ["pass_duo"]
             and H.COURS_DUO in s and COURS2 in s and COURS_AUTRE not in s and H.COURS_CACHE not in s
             and not V3.fuite(op, base), (c, op.get("types"), list(s)))
    o2, o2b = s[COURS2][0], s[COURS2][1]
    o_autre = R._occurrences(next(x for x in base["courses"].docs if x["id"] == COURS_AUTRE))[0]

    c, x = await chaine(t0, {"course_id": COURS_AUTRE, "occurrence": o_autre})
    verifier("5. séance d'un AUTRE coach -> 400 seance_non_autorisee, aucun enfant créé",
             c == 400 and raison(x) == "seance_non_autorisee" and not await R._enfant_de(doc_par_tok(base, t0)), (c, x))
    c, x = await chaine(t0, {"course_id": COURS2, "occurrence": "2020-01-01T18:45:00"})
    verifier("6. séance PASSÉE -> 400 seance_indisponible", c == 400 and raison(x) == "seance_indisponible", (c, x))
    c, x = await chaine(t0, {"course_id": COURS2, "occurrence": o2[:10] + "T03:00:00"})
    verifier("6b. date tapée à la main (hors liste du serveur) -> 400 seance_indisponible",
             c == 400 and raison(x) == "seance_indisponible", (c, x))
    c, x = await chaine(t0, {"kind": "parrainage"})
    verifier("1a. « Parrainage » sans programme configuré -> 400 type_non_autorise",
             c == 400 and raison(x) == "type_non_autorise", (c, x))

    c, r = await chaine(t0, {"kind": "pass_duo", "course_id": COURS2, "occurrence": o2})
    t1 = r["child"]["share_token"] if c == 201 else None
    d0, d1 = doc_par_tok(base, t0), doc_par_tok(base, t1) if t1 else {}
    verifier("1. l'offre sélectionnée est conservée (chain.kind = pass_duo, rendue au créateur)",
             c == 201 and d1["chain"].get("kind") == "pass_duo" and r["child"]["kind"] == "pass_duo", (c, str(r)[:200]))
    verifier("2. la séance choisie est enregistrée SUR L'ENFANT (cours, date, expiration, instantané)",
             d1.get("course_id") == COURS2 and d1.get("occurrence") == o2 and d1.get("expires_at") == o2
             and d1["course_snapshot"]["name"] == "Afroboost Silent – Session Cardio"
             and d1["chain"].get("seance_choisie") is True, {k: d1.get(k) for k in ("course_id", "occurrence")})
    verifier("3. le parent garde SA séance (cours et date inchangés)",
             d0["course_id"] == H.COURS_DUO and d0["occurrence"] == occ, (d0["course_id"], d0["occurrence"]))

    c, x = await chaine_patch(t0, {"course_id": COURS2, "occurrence": o2b}, CLES[t0])
    verifier("2b. « Changer de séance » AVANT envoi (PATCH, même appareil) -> 200, l'enfant suit, le parent non",
             c == 200 and doc_par_tok(base, t1)["occurrence"] == o2b and doc_par_tok(base, t0)["occurrence"] == occ, (c, x))
    c, x = await chaine_patch(t0, {"course_id": COURS2, "occurrence": o2}, "cle-d-un-autre-appareil")
    verifier("2c. changer la séance depuis un AUTRE appareil -> 403, rien ne bouge",
             c == 403 and doc_par_tok(base, t1)["occurrence"] == o2b, (c, x))
    c, x = await chaine(t0, {"course_id": COURS2, "occurrence": o2})
    verifier("2d. re-POST SANS la clé de l'appareil : l'enfant est relu, sa séance ne change pas",
             c == 200 and doc_par_tok(base, t1)["occurrence"] == o2b, (c, doc_par_tok(base, t1)["occurrence"]))
    c, x = await appel(R.referral_chaine_creer(t0, req({"course_id": COURS2, "occurrence": o2},
                                                       {"X-Chain-Key": CLES[t0]})))
    verifier("2e. re-POST idempotent AVEC la clé : la séance choisie est reprise (o2)",
             c == 200 and doc_par_tok(base, t1)["occurrence"] == o2, (c, doc_par_tok(base, t1)["occurrence"]))

    # 7. identité réelle
    c, x = await chaine_patch(t0, {"display_name": "Fabien"}, CLES[t0])
    c, g1 = await pub(t1)
    verifier("7. inviter_display réel : « Fabien » sur la page de son ami, titre « Fabien t'invite à Afroboost »",
             c == 200 and (g1.get("inviter_display") or {}).get("prenom") == "Fabien"
             and g1.get("sponsor_first_name") == "Fabien"
             and E.og_titre_invitation(E.nom_parrain_affichable(doc_par_tok(base, t1))) == "Fabien t'invite à Afroboost"
             and "Un membre" not in str(g1), (g1.get("inviter_display"), g1.get("sponsor_first_name")))
    verifier("4. l'enfant reçoit SA séance (page publique de l'ami : cours 2, date o2) ; badge pass_duo",
             g1.get("occurrence") == o2 and (g1.get("course") or {}).get("name") == "Afroboost Silent – Session Cardio"
             and g1.get("invitation_type") == "pass_duo", (g1.get("occurrence"), g1.get("course"), g1.get("invitation_type")))

    # le parent change de séance : l'enfant qui a CHOISI la sienne ne suit pas
    occs0 = [o for o in s[H.COURS_DUO] if o != occ]
    c, x = await appel(R.referral_changer_seance(t0, req({"occurrence": occs0[0], "version": E.version_pass(doc_par_tok(base, t0))})))
    verifier("3b. le parent change SA séance : l'enfant garde celle choisie pour son ami",
             c == 200 and doc_par_tok(base, t0)["occurrence"] == occs0[0] and doc_par_tok(base, t1)["occurrence"] == o2,
             (c, doc_par_tok(base, t1)["occurrence"]))

    c, _ = await partager(t0)
    c, x = await chaine_patch(t0, {"course_id": COURS2, "occurrence": o2b}, CLES[t0])
    verifier("19. APRÈS envoi : changer la séance -> 409 invitation_deja_partagee (jamais silencieux)",
             c == 409 and raison(x) == "invitation_deja_partagee" and doc_par_tok(base, t1)["occurrence"] == o2, (c, x))

    ef, tf, _ = ident(FABIEN)
    c, jf = await rejoindre(t0, FABIEN, nom="Fabien")
    verifier("8. Fabien n'a jamais essayé -> SON essai (200, un code d'essai, une place)",
             c == 200 and len(codes_de(base, ef)) == 1 and len(resas_de(base, ef)) == 1, (c, str(jf)[:200]))
    code_f = codes_de(base, ef)[0]["code"]
    avant_f = (len(codes_de(base, ef)), len(resas_de(base, ef)), debits(base, code_f),
               len([s_ for s_ in base["subscriptions"].docs if (s_.get("email") or "").lower() == ef]),
               len([v for v in base["free_trial_claims"].docs if ef in str(v.get("_id"))]))

    es, _, _ = ident(SOPHIE)
    t2, _ = await preparer_et_partager(t1)
    c, js = await rejoindre(t1, SOPHIE, nom="Sophie")
    d1 = doc_par_tok(base, t1)
    resa_s = resas_de(base, es)
    verifier("12. Sophie n'a jamais essayé -> SON essai, sur la séance que Fabien lui a offerte",
             c == 200 and len(codes_de(base, es)) == 1 and len(resa_s) == 1
             and str(resa_s[0].get("datetime") or "")[:16] == o2[:16], (c, [r_.get("datetime") for r_ in resa_s], o2))
    apres_f = (len(codes_de(base, ef)), len(resas_de(base, ef)), debits(base, code_f),
               len([s_ for s_ in base["subscriptions"].docs if (s_.get("email") or "").lower() == ef]),
               len([v for v in base["free_trial_claims"].docs if ef in str(v.get("_id"))]))
    verifier("11. Fabien invite Sophie -> AUCUN nouvel essai pour Fabien (codes, places, débits, forfaits, verrous identiques)",
             avant_f == apres_f and d1["status"] == "unlocked" and d1["reservations"]["sponsor_id"] == resas_de(base, ef)[0]["id"],
             {"avant": avant_f, "apres": apres_f, "P1": (d1["status"], d1.get("blocked_reason"))})
    verifier("3c. le parent (P0) a toujours sa séance après l'inscription de Sophie",
             doc_par_tok(base, t0)["occurrence"] == occs0[0] and doc_par_tok(base, t0)["course_id"] == H.COURS_DUO)
    return base, occ, t2


async def partie_essai_unique(base, occ, t2):
    ef, tf, _ = ident(FABIEN)
    # 10 + 14 : une nouvelle invitation, d'un AUTRE coach (campagne du partenaire)
    c, r = await CC.entree()
    tc = r["share_token"]
    tcf, _ = await preparer_et_partager(tc)
    c, x = await rejoindre(tc, FABIEN, nom="Fabien")
    verifier("10/14. Fabien reçoit une nouvelle invitation d'un AUTRE coach -> 409 free_trial_already_granted, aucun 2e essai",
             c == 409 and raison(x) == "free_trial_already_granted" and len(codes_de(base, ef)) == 1, (c, x))
    verifier("30. « déjà client » : l'invitation que Fabien a DÉJÀ envoyée reste valable (non annulée)",
             doc_par_tok(base, tcf)["status"] not in ("cancelled",) and doc_par_tok(base, tcf)["chain"].get("parent_pass_id"),
             doc_par_tok(base, tcf).get("status"))
    eh, _, _ = ident(HUGO)
    await preparer_et_partager(tcf)
    c, jh = await rejoindre(tcf, HUGO, nom="Hugo")
    verifier("30b. …et l'ami de Fabien (Hugo) obtient SON propre essai : la chaîne ne casse pas",
             c == 200 and len(codes_de(base, eh)) == 1, (c, str(jh)[:200]))

    # 9 : Fabien UTILISE son essai (présence validée) -> définitivement fermé
    for r_ in resas_de(base, ef):
        r_["validated"] = True
        r_["validatedAt"] = "2026-09-30T19:00:00"
    c, r = await CC.entree()
    td = r["share_token"]
    await preparer_et_partager(td)
    c, x = await rejoindre(td, FABIEN, nom="Fabien")
    verifier("9. Fabien a UTILISÉ son essai -> 409 free_trial_already_used (définitif)",
             c == 409 and raison(x) == "free_trial_already_used" and len(codes_de(base, ef)) == 1, (c, x))

    # 13 : une NOUVELLE campagne (plateforme) ne contourne pas l'essai unique
    base["referral_campaigns"].docs.append(CC.campagne(occ, id="camp-0002", share_token="campTokB9z8Y7x6",
                                                        coach_id="", offer_id=H.OFFRE_A))
    c, r = await CC.entree(tok="campTokB9z8Y7x6")
    tn = r["share_token"]
    await preparer_et_partager(tn)
    c, x = await rejoindre(tn, FABIEN, nom="Fabien")
    verifier("13. nouvelle campagne -> 409 free_trial_already_used, aucun 2e essai",
             c == 409 and raison(x) == "free_trial_already_used" and len(codes_de(base, ef)) == 1, (c, x))
    c, x = await rejoindre(tn, FABIEN, email="fabien.nouvelle@exemple.test", nom="Fabien")
    verifier("13b. nouvelle adresse, MÊME numéro -> 409 (le numéro est une clé d'identité)",
             c == 409 and raison(x) in ("free_trial_already_used", "free_trial_already_granted"), (c, x))
    c, x = await appel(R.referral_join(tn, req(H.corps_ami("fabien.troisieme@exemple.test", "", "Fabien"),
                                               V3._entete_cle(tn, V3._DEF))))
    verifier("13c. nouvelle adresse SANS numéro -> 400 whatsapp_requis (l'e-mail seul ne rouvre rien)",
             c == 400 and raison(x) == "whatsapp_requis", (c, x))
    c, x = await rejoindre(tn, MARC, nom="Marc")
    verifier("12b. Marc (jamais essayé) sur la même campagne -> SON essai", c == 200, (c, str(x)[:200]))

    # 5b : la campagne du partenaire propose ses cours, jamais ceux d'un autre coach
    c, op = await options(tc)
    s = seances(op)
    verifier("5b. campagne du partenaire : séances = son cours + le cours de la campagne, jamais le coach B",
             c == 200 and COURS_PART in s and H.COURS_DUO in s and COURS_AUTRE not in s, list(s))


async def partie_recompense(base):
    prog = {"coach_id": "", "type": "parrainage", "status": "active", "reward_type": "free_session", "reward_value": 1}
    aff = {"coach_id": "", "type": "affiliation", "status": "active", "reward_type": "fixed_amount",
           "reward_value": 15, "offer_name": "Pulse X10"}
    verifier("15. récompense de parrainage ≠ essai gratuit (nature, libellé)",
             E.nature_avantage(E.programme_valide(prog)) == "recompense_parrainage"
             and E.nature_avantage("trial") == "premier_essai"
             and E.libelle_recompense(E.programme_valide(prog)) == "Tu gagnes 1 séance offerte de parrainage quand les conditions sont remplies."
             and "essai" not in E.libelle_recompense(E.programme_valide(prog)).lower())
    verifier("15b. affiliation : montant fixé par le programme ; masquée à un abonné, visible pour un partenaire",
             [t["id"] for t in E.types_offrables({}, [prog, aff])] == ["pass_duo", "parrainage"]
             and [t["id"] for t in E.types_offrables({}, [prog, aff], role="partner")] == ["pass_duo", "parrainage", "affiliation"]
             and E.libelle_recompense(E.programme_valide(aff)) == "Tu gagnes 15 CHF si ton client achète Pulse X10."
             and E.programme_valide(dict(aff, reward_type="free_session")) is None
             and E.programme_valide(dict(prog, status="draft")) is None)
    base["referral_programs"].docs.append(prog)
    occ3 = [o for o in R._occurrences(next(x for x in base["courses"].docs if x["id"] == H.COURS_DUO))][-1]
    c, p = await H.creer_pass(base, occ3)
    tp = p["share_token"]
    c, op = await options(tp)
    carte = next((t for t in op.get("types") or [] if t["id"] == "parrainage"), None)
    verifier("15c. programme configuré -> carte « Parrainage » avec SA récompense (pas un essai)",
             carte is not None and carte["nature"] == "recompense_parrainage" and "séance offerte" in carte["recompense"],
             op.get("types"))
    c, r = await chaine(tp, {"kind": "parrainage"})
    tk = r["child"]["share_token"] if c == 201 else None
    c2, g = await pub(tk) if tk else (0, {})
    verifier("15d. « Parrainage » choisi -> conservé ; badge de l'ami = parrainage",
             c == 201 and doc_par_tok(base, tk)["chain"]["kind"] == "parrainage" and g.get("invitation_type") == "parrainage",
             (c, g.get("invitation_type")))
    subs_avant = len(base["subscriptions"].docs)
    await partager(tp)
    c, x = await rejoindre(tp, 6, nom="Farid")
    ajoutes = base["subscriptions"].docs[subs_avant:]
    verifier("15e. l'ami s'inscrit : UN seul forfait créé (le sien) — rien n'est octroyé en « essai » à l'invitant",
             c == 200 and len(ajoutes) == 1 and (ajoutes[0].get("email") or "").lower() == ident(6)[0], (c, len(ajoutes)))


async def principal():
    base, occ, t2 = await partie_wizard()
    await partie_essai_unique(base, occ, t2)
    await partie_recompense(base)


def main():
    import shutil
    import tempfile
    _tmp = tempfile.mkdtemp(prefix="banc_v558_")
    _orig = H.S._V413_MEDIA_DIR
    H.S._V413_MEDIA_DIR = _tmp
    try:
        asyncio.run(principal())
    finally:
        H.S._V413_MEDIA_DIR = _orig
        shutil.rmtree(_tmp, ignore_errors=True)
    ok = sum(1 for r in H.RESULTATS if r[1])
    total = len(H.RESULTATS)
    for nom, bon, detail in H.RESULTATS:
        if not bon:
            print("ECHEC ", nom, "\n       ", str(detail)[:600])
    print("%d / %d verifications V558 au vert" % (ok, total))
    sys.exit(0 if ok == total else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PAR-1 — LOT 1 « Invitation & parrainage » : la campagne d'un coach devient la
RACINE d'une chaîne V556 (pass racine P0 ordinaire, un par visiteur).

Ce banc prouve :
  * le lien de la campagne `trial` (page OG) mène à `/duo/c/<jeton>` quand les
    drapeaux sont allumés, et au lien d'avant sinon ;
  * POST /api/referral/campaign/{token}/entry crée UN P0 (idempotent par
    X-Entry-Key), sans PII, avec ses refus (404 neutre, 410, 409, drapeau) ;
  * la chaîne 5 niveaux : partenaire -> P0 -> A -> B -> C -> D -> E
    (profondeur 0..5, racine P0, campagne héritée, P0 débloqué SANS place de
    parrain, chaque maillon reprend la place de son parent sans second débit),
    et les gardes V556 (invitation requise, autre appareil, anti-boucle,
    essai unique, le coach ne s'inscrit pas lui-même).

Même harnais que `test_parrainage_v3.py` (importé, jamais recopié) : MongoDB
en mémoire, VRAIES routes, VRAIES gardes ESSAI-1/ESSAI-4. AUCUN réseau.

Lancement :  python3 tests/test_parrainage_campagne_chaine.py
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_parrainage_v3 as V3  # noqa: E402  (pose l'environnement du banc)

H = V3.H
S, R, E = H.S, H.R, H.E
verifier, appel = H.verifier, H.appel
req, ident, raison, doc_par_tok = V3.req, V3.ident, V3.raison, V3.doc_par_tok
rejoindre, preparer_et_partager, pub = V3.rejoindre, V3.preparer_et_partager, V3.pub
resas_de, codes_de, debits = V3.resas_de, V3.codes_de, V3.debits

import api.routes.referral_campaigns_engine as IC  # noqa: E402
import api.routes.referral_campaigns_routes as RCR  # noqa: E402
import api.routes.share_invite_routes as SI  # noqa: E402

FRONT = "https://afroboost.com"
PARTENAIRE = "coach.partenaire@exemple.test"
OFFRE_CAMP = "offre-campagne-essai"
TOK_CAMP = "campTokA1b2C3d4e5"
CAMP_ID = "camp-0001"
UA_NAV = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Safari/604.1"
UA_ROBOT = "WhatsApp/2.23.20.0 A"


def campagne(occ, **extra):
    d = {"id": CAMP_ID, "coach_id": PARTENAIRE, "type": "trial", "status": "active",
         "share_token": TOK_CAMP, "version": 2, "title": "Cours découverte", "subtitle": None,
         "message": "Viens essayer avec moi", "cta_label": "Je viens", "image_url": None,
         "image_source": "default", "course_id": H.COURS_DUO, "occurrence": occ, "offer_id": OFFRE_CAMP,
         "inviter_display": {"prenom": "Mariam", "photo_url": None, "source": "coach"},
         "created_at": "2026-09-29T10:00:00+00:00", "updated_at": "2026-09-29T10:00:00+00:00"}
    d.update(extra)
    return d


def depart(drapeau_campagne=True, chaine=True, **extra_camp):
    base, occ = H.base_de_depart(chaine=chaine)
    base["feature_flags"].docs[0]["invitation_chaine_campagne_enabled"] = drapeau_campagne
    base._c["referral_campaigns"] = H._Coll("referral_campaigns", uniques=[(("id",), None),
                                                                          (("share_token",), None)])
    base["offers"].docs.append({"id": OFFRE_CAMP, "name": "Essai partenaire", "price": 0.0, "visible": True,
                                "coach_id": PARTENAIRE})
    base["concept"].docs.append({"id": "concept", "primaryColor": "#D91CD2"})
    base["coaches"].docs.append({"id": "cp", "email": PARTENAIRE, "name": "Mariam Coach"})
    base["referral_campaigns"].docs.append(campagne(occ, **extra_camp))
    RCR.init_db(base)
    SI.init_db(base)
    return base, occ


async def entree(tok=TOK_CAMP, cle=None, corps=None):
    _e = {"X-Entry-Key": cle} if cle else {}
    return await appel(R.referral_campagne_entree(tok, req(corps or {}, _e)))


def p0s(base):
    return [d for d in base["referral_passes"].docs if (d.get("origin") or {}).get("source_type")]


def fuite(objet, base):
    return V3.fuite(objet, base, extra=(PARTENAIRE, "campagne:", CAMP_ID, "entry_key_hash", "coach_id"))


# ═══════════════════════════════════════════════════════════════════════════
# 1. La cible du lien (moteur pur) — ROUGE avant l'implémentation
# ═══════════════════════════════════════════════════════════════════════════
def partie_cible():
    s = {"type": "trial", "offer_id": "offre-1", "share_token": "tokA-b_1",
         "course_id": "cours-A_1", "occurrence": "2026-10-01T18:30:00"}
    verifier("C1. cible_front(trial complet, chaine=True) = /duo/c/<share_token>, sans reserver=1",
             IC.cible_front(s, chaine=True) == "/duo/c/tokA-b_1", IC.cible_front(s, chaine=True))
    verifier("C1b. cible_front(trial complet) drapeau éteint : lien d'avant inchangé",
             IC.cible_front(s) == "/?offre=offre-1&reserver=1&course=cours-A_1&occurrence=2026-10-01T18%3A30"
             and IC.cible_front(s, chaine=False) == IC.cible_front(s), IC.cible_front(s))
    verifier("C1c. trial SANS séance complète + chaine=True : lien d'avant (pas de P0 possible)",
             IC.cible_front(dict(s, occurrence=None), chaine=True) == "/?offre=offre-1&reserver=1",
             IC.cible_front(dict(s, occurrence=None), chaine=True))
    verifier("C1d. event_free / event_paid / pass_duo : inchangés même chaine=True",
             IC.cible_front(dict(s, type="event_free"), chaine=True).startswith("/?offre=offre-1&reserver=1")
             and IC.cible_front(dict(s, type="event_paid"), chaine=True) == "/?offre=offre-1"
             and IC.cible_front(dict(s, type="pass_duo"), chaine=True) == "/parrainage?campagne=tokA-b_1")
    verifier("C1e. jeton hors motif + chaine=True : lien d'avant (jamais un chemin fabriqué)",
             IC.cible_front(dict(s, share_token="a/b c"), chaine=True).startswith("/?offre="),
             IC.cible_front(dict(s, share_token="a/b c"), chaine=True))
    verifier("C1f. dto_public(chaine=True).target_url = /duo/c/<jeton> ; défaut inchangé",
             IC.dto_public(s, chaine=True)["target_url"] == "/duo/c/tokA-b_1"
             and IC.dto_public(s)["target_url"].startswith("/?offre="))
    # PAR-3 (A4) : l'historique du parrain ne montre plus les types bruts de la chaîne.
    _h = E.historique([{"id": "p1", "events": [
        {"type": "chain_child_created", "at": "2026-10-01T10:00:00"},
        {"type": "chain_shared", "at": "2026-10-01T10:05:00"}]}])
    verifier("C1g. historique : chain_shared / chain_child_created traduits",
             [x["label"] for x in _h] == ["Invitation partagée", "Invitation de ton ami préparée"], _h)


async def partie_page_og():
    base, occ = depart()
    r = await SI.share_invite_page(TOK_CAMP, H.Requete({}, {"user-agent": UA_NAV}), "")
    h = bytes(r.body or b"").decode("utf-8")
    _cible = "%s/duo/c/%s" % (FRONT, TOK_CAMP)
    verifier("C2. GET /api/share/invite/<tok> navigateur + drapeaux -> redirige vers FRONT/duo/c/<tok>",
             r.status_code == 200 and 'content="0;url=%s"' % _cible in h and 'href="%s"' % _cible in h
             and "reserver=1" not in h, h[-600:])
    r = await SI.share_invite_page(TOK_CAMP, H.Requete({}, {"user-agent": UA_ROBOT}), "")
    h = bytes(r.body or b"").decode("utf-8")
    verifier("C2b. robot : toujours pas de meta refresh, og:image inchangée",
             'http-equiv="refresh"' not in h and "/api/share/invite/%s/carte.jpg?v=2" % TOK_CAMP in h)
    base["feature_flags"].docs[0]["invitation_chaine_campagne_enabled"] = False
    r = await SI.share_invite_page(TOK_CAMP, H.Requete({}, {"user-agent": UA_NAV}), "")
    h = bytes(r.body or b"").decode("utf-8")
    verifier("C2c. drapeau campagne ÉTEINT : lien d'avant (/?offre=…&reserver=1&course=…)",
             "/duo/c/" not in h and "reserver=1" in h, h[-500:])
    base["feature_flags"].docs[0]["invitation_chaine_campagne_enabled"] = True
    base["feature_flags"].docs[0]["parrainage_chaine_enabled"] = False
    r = await SI.share_invite_page(TOK_CAMP, H.Requete({}, {"user-agent": UA_NAV}), "")
    h = bytes(r.body or b"").decode("utf-8")
    verifier("C2d. chaîne V556 ÉTEINTE : lien d'avant", "/duo/c/" not in h and "reserver=1" in h)
    base["feature_flags"].docs[0]["parrainage_chaine_enabled"] = True
    # DTO coach (écran Campagnes) : la même cible
    c, d = await appel(RCR.invitations_lire(CAMP_ID, H.Requete({}, {"Authorization": "Bearer " + H.jeton_admin(PARTENAIRE)})))
    verifier("C3. DTO coach : target_url = /duo/c/<jeton> drapeaux allumés",
             c == 200 and d.get("target_url") == "/duo/c/%s" % TOK_CAMP, (c, d))


# ═══════════════════════════════════════════════════════════════════════════
# 2. L'entrée (création de P0)
# ═══════════════════════════════════════════════════════════════════════════
async def partie_entree():
    base, occ = depart()
    c, r = await entree(corps={"attribution": {"first": {"source": "whatsapp"}}})
    verifier("N1. POST entry -> 201 {share_token, entry_key, target:/duo/<tok>}",
             c == 201 and r.get("share_token") and r.get("entry_key")
             and r.get("target") == "/duo/%s" % r.get("share_token") and set(r) == {"share_token", "entry_key", "target"},
             (c, r))
    verifier("N1b. réponse sans PII (contient_pii vide, ni e-mail coach, ni id, ni « campagne: »)",
             not E.contient_pii(r) and not fuite(r, base), fuite(r, base))
    p0 = doc_par_tok(base, r["share_token"])
    o = (p0 or {}).get("origin") or {}
    verifier("N2. P0 : origin {source_type partner, source_id, campaign_id, entry_key_hash}, jamais la clé en clair",
             o.get("source_type") == "partner" and o.get("source_id") == PARTENAIRE and o.get("campaign_id") == CAMP_ID
             and o.get("entry_key_hash") and r["entry_key"] not in json.dumps(base["referral_passes"].docs), o)
    verifier("N2b. P0 : séance/offre de la campagne, chain {root:soi, depth 0}, parrain « campagne: » non en attente",
             p0["course_id"] == H.COURS_DUO and p0["occurrence"] == occ and p0["offer_id"] == OFFRE_CAMP
             and p0["chain"].get("root_pass_id") == p0["id"] and p0["chain"].get("depth") == 0
             and not p0["chain"].get("parent_pass_id")
             and p0["sponsor"]["email_norm"].startswith("campagne:") and p0["sponsor"].get("pending") is False
             and not E.parrain_en_attente(p0) and E.sans_place_parrain(p0), p0)
    verifier("N2c. P0 : inviter_display source coach, invitation au prénom du coach",
             p0["inviter_display"].get("source") == "coach" and p0["inviter_display"].get("prenom") == "Mariam"
             and p0["invitation"].get("display_name") == "Mariam", p0.get("inviter_display"))
    n = len(base["referral_passes"].docs)
    c2, r2 = await entree(cle=r["entry_key"])
    verifier("N3. même X-Entry-Key -> 200 même P0, sans entry_key, aucun pass en plus",
             c2 == 200 and r2.get("share_token") == r["share_token"] and "entry_key" not in r2
             and len(base["referral_passes"].docs) == n, (c2, r2))
    c3, r3 = await entree(cle="cle-inconnue")
    verifier("N3b. X-Entry-Key inconnue -> 201 nouveau P0", c3 == 201 and r3["share_token"] != r["share_token"], (c3, r3))
    # GET /pass du P0 : le contrat
    c, g = await pub(r["share_token"])
    verifier("N4. GET /pass P0 : inviter_display.source coach, occurrences [], UNE offre, chain_required true",
             c == 200 and g["inviter_display"]["source"] == "coach" and g.get("occurrences") == []
             and len(g.get("offers") or []) == 1 and g["offers"][0]["id"] == OFFRE_CAMP
             and g.get("chain_required") is True and g["sponsor_display_name"] == "Mariam", g)
    verifier("N4b. GET /pass P0 : aucune PII, aucun champ origin/campaign", not fuite(g, base)
             and "origin" not in g and "lignage" not in g, fuite(g, base))
    # PATCH offre / séance : figés sur la campagne
    c, x = await appel(R.referral_changer_offre(r["share_token"], req({"offer_id": H.OFFRE_B, "version": g["version"]})))
    verifier("N5. PATCH /offer public sur P0 -> 409 pass_non_modifiable", c == 409 and raison(x) == "pass_non_modifiable", (c, x))
    c, x = await appel(R.referral_changer_seance(r["share_token"], req({"occurrence": occ, "version": g["version"]})))
    verifier("N5b. PATCH /occurrence public sur P0 -> 409 pass_non_modifiable", c == 409 and raison(x) == "pass_non_modifiable", (c, x))

    # refus
    base, occ = depart()
    base["referral_campaigns"].docs[0]["status"] = "draft"
    c, x = await entree()
    verifier("N6. campagne draft -> 404 neutre, rien créé", c == 404 and not base["referral_passes"].docs, (c, x))
    base["referral_campaigns"].docs[0]["status"] = "archived"
    c, x2 = await entree()
    verifier("N6b. campagne archivée -> 404 neutre (même corps)", c == 404 and x2 == x, (c, x2))
    base["referral_campaigns"].docs[0].update(status="active", type="pass_duo")
    c, x3 = await entree()
    verifier("N6c. campagne pass_duo -> 404 neutre", c == 404 and x3 == x, (c, x3))
    c, x4 = await entree(tok="jeton-inconnu")
    verifier("N6d. jeton inconnu -> 404 neutre", c == 404 and x4 == x, (c, x4))
    base["referral_campaigns"].docs[0].update(type="trial", occurrence="2020-01-01T18:30:00")
    c, x = await entree()
    verifier("N7. séance de la campagne passée -> 410, rien créé", c == 410 and not base["referral_passes"].docs, (c, x))
    base, occ = depart(drapeau_campagne=False)
    c, x = await entree()
    verifier("N8. drapeau invitation_chaine_campagne_enabled éteint -> 404 parrainage_chaine_desactive",
             c == 404 and x.get("detail") == "parrainage_chaine_desactive" and not base["referral_passes"].docs, (c, x))
    base, occ = depart(chaine=False)
    c, x = await entree()
    verifier("N8b. chaîne V556 éteinte -> 404 parrainage_chaine_desactive", c == 404
             and x.get("detail") == "parrainage_chaine_desactive", (c, x))
    base, occ = depart()
    base["feature_flags"].docs[0].pop("invitation_chaine_campagne_enabled")
    c, x = await entree()
    verifier("N8c. drapeau ABSENT = éteint", c == 404, (c, x))
    # plafond
    base, occ = depart()
    _orig = R.CAMPAGNE_ENTREES_OUVERTES_MAX
    R.CAMPAGNE_ENTREES_OUVERTES_MAX = 2
    try:
        a = [await entree() for _ in range(3)]
    finally:
        R.CAMPAGNE_ENTREES_OUVERTES_MAX = _orig
    verifier("N9. plafond de P0 ouverts atteint -> 409 X-Refus-Raison: campagne_complete",
             [x[0] for x in a] == [201, 201, 409] and raison(a[2][1]) == "campagne_complete"
             and len(p0s(base)) == 2, [(x[0], raison(x[1])) for x in a])
    verifier("N9b. constante de plafond = 500", _orig == 500, _orig)
    # drapeau exposé et pilotable (défaut éteint)
    try:
        S.FeatureFlagsUpdate(invitation_chaine_campagne_enabled=True)
        _modele = True
    except Exception:  # noqa: BLE001
        _modele = False
    base, occ = depart()
    base["feature_flags"].docs[0].pop("invitation_chaine_campagne_enabled")
    g = await S.get_feature_flags()
    verifier("N11. modèle PUT /feature-flags accepte le drapeau ; GET le rend (défaut false)",
             _modele and g.get("invitation_chaine_campagne_enabled") is False, g.get("invitation_chaine_campagne_enabled"))
    # super-admin (clé "")
    base, occ = depart(coach_id="")
    base["offers"].docs[-1]["coach_id"] = None
    c, r = await entree()
    verifier("N10. campagne plateforme (clé \"\") -> P0 source_type super_admin",
             c == 201 and doc_par_tok(base, r["share_token"])["origin"]["source_type"] == "super_admin", (c, r))


# ═══════════════════════════════════════════════════════════════════════════
# 3. La chaîne 5 niveaux : partenaire -> P0 -> A -> B -> C -> D -> E
# ═══════════════════════════════════════════════════════════════════════════
async def partie_chaine_5():
    base, occ = depart()
    c, r = await entree()
    t0 = r["share_token"]
    await pub(t0)
    # le coach ne s'inscrit pas lui-même
    c, x = await appel(R.referral_join(t0, req(H.corps_ami(PARTENAIRE, "+41 78 999 00 11", "Mariam Coach"))))
    verifier("K0. le coach propriétaire s'inscrit sur son P0 -> 409 auto_parrainage, rien écrit",
             c == 409 and raison(x) == "auto_parrainage" and doc_par_tok(base, t0)["invitee"] is None, (c, x))
    c, x = await rejoindre(t0, 1)
    verifier("K1. A sans partage -> 409 invitation_requise", c == 409 and raison(x) == "invitation_requise", (c, x))
    toks = [t0]
    for niveau in range(1, 6):                     # A..E : chacun partage son enfant puis rejoint
        tp = toks[-1]
        tn, _ = await preparer_et_partager(tp)
        if niveau == 2:
            c, x = await rejoindre(tp, niveau, cle="mauvaise-cle")
            verifier("K2. B avec une mauvaise clé d'appareil -> 403 invitation_autre_appareil",
                     c == 403 and raison(x) == "invitation_autre_appareil", (c, x))
            c, x = await rejoindre(tp, 1, cle=None)     # A, depuis SON appareil (pas celui qui a partagé P2)
            verifier("K3. anti-boucle : A sur P1 -> 409 auto_parrainage", c == 409 and raison(x) == "auto_parrainage", (c, x))
        c, j = await rejoindre(tp, niveau)
        verifier("K4.%d personne %d s'inscrit sur P%d -> unlocked" % (niveau, niveau, niveau - 1),
                 c == 200 and j.get("status") == "unlocked", (c, str(j)[:300]))
        if niveau == 1:
            verifier("K4b. /join P0 : billet de l'invité SEUL (aucune place parrain)",
                     len(j.get("tickets") or []) == 1 and j["tickets"][0]["role"] == "invitee"
                     and not fuite(j, base), (j.get("tickets"), fuite(j, base)))
        toks.append(tn)
    docs = [doc_par_tok(base, t) for t in toks]
    verifier("K5. profondeur 0..5, racine = P0 pour tous",
             [d["chain"]["depth"] for d in docs] == [0, 1, 2, 3, 4, 5]
             and all(d["chain"]["root_pass_id"] == docs[0]["id"] for d in docs), [d["chain"] for d in docs])
    verifier("K5b. parent de P(n) = P(n-1)",
             all(docs[i]["chain"]["parent_pass_id"] == docs[i - 1]["id"] for i in range(1, 6)))
    verifier("K6. campaign_id hérité par toute la chaîne ; lignage partner sur P0 / subscriber ailleurs",
             all((d.get("origin") or {}).get("campaign_id") == CAMP_ID for d in docs)
             and E.lignage(docs[0])["source_type"] == "partner"
             and all(E.lignage(d)["source_type"] == "subscriber" for d in docs[1:])
             and all(E.lignage(d)["campaign_id"] == CAMP_ID and E.lignage(d)["root_referral_id"] == docs[0]["id"]
                     for d in docs) and [E.lignage(d)["depth"] for d in docs] == [0, 1, 2, 3, 4, 5]
             and E.lignage(docs[3])["parent_referral_id"] == docs[2]["id"]
             and E.lignage(docs[0])["parent_referral_id"] is None, [E.lignage(d) for d in docs])
    verifier("K6b. enfants : root_source_type/root_source_id hérités, jamais source_type propre",
             all(d["origin"].get("root_source_type") == "partner" and d["origin"].get("root_source_id") == PARTENAIRE
                 and "source_type" not in d["origin"] and "entry_key_hash" not in d["origin"] for d in docs[1:]))
    verifier("K7. P0 unlocked SANS place de parrain (sponsor_id None), un seul billet",
             docs[0]["status"] == "unlocked" and not docs[0]["reservations"].get("sponsor_id"))
    verifier("K8. P1..P4 unlocked : place du parrain = réservation de filleul du parent",
             all(docs[i]["status"] == "unlocked"
                 and docs[i]["reservations"]["sponsor_id"] == docs[i - 1]["reservations"]["invitee_id"]
                 for i in range(1, 5)), [d["reservations"] for d in docs])
    verifier("K8b. P5 (invitation de E) attend son ami, parrain lié à E",
             docs[5]["status"] in ("locked", "waiting") and docs[5]["sponsor"]["email_norm"] == ident(5)[0])
    verifier("K9. chacun (A..E) : 1 code d'essai, 1 réservation, 1 débit (aucun second débit)",
             all(len(codes_de(base, ident(n)[0])) == 1 and len(resas_de(base, ident(n)[0])) == 1
                 and debits(base, codes_de(base, ident(n)[0])[0]["code"]) == 1 for n in range(1, 6)),
             [(len(codes_de(base, ident(n)[0])), len(resas_de(base, ident(n)[0]))) for n in range(1, 6)])
    verifier("K9b. la campagne n'a AUCUNE réservation ni débit (le parrain racine n'a pas de place)",
             not [x for x in base["reservations"].docs if "campagne:" in str(x.get("userEmail"))]
             and len(base["reservations"].docs) == 5, len(base["reservations"].docs))
    verifier("K10. aucun push / e-mail vers « campagne: » ni vers une adresse en attente",
             not [m for m in H.MOUCHARDS["push"] if "@" not in str(m["email"])]
             and docs[0]["id"] not in H.MOUCHARDS["email_parrain"], H.MOUCHARDS["push"])
    c, x = await rejoindre(toks[3], 1)
    verifier("K11. anti-boucle plus loin : A sur P3 (déjà pourvu) refusé", c == 409, (c, x))
    # admin : lignage, jamais l'adresse « campagne: »
    c, lst = await appel(R.referral_admin_passes(H.Requete({}, H.entetes_admin())))
    _p0 = [i for i in (lst or {}).get("items", []) if i.get("id") == docs[0]["id"]]
    verifier("K12. vue admin P0 : lignage partner, e-mail parrain vide (jamais « campagne: »)",
             c == 200 and _p0 and _p0[0].get("lignage", {}).get("source_type") == "partner"
             and _p0[0]["sponsor"]["email"] == "" and "campagne:" not in json.dumps(lst), (c, str(_p0)[:400]))
    # statut `used` : la présence de l'invité suffit sur P0
    _rid = docs[0]["reservations"]["invitee_id"]
    _resa = [x for x in base["reservations"].docs if x["id"] == _rid][0]
    verifier("K13. statut_derive P0 : used dès que la présence de l'invité est validée",
             E.statut_derive(docs[0], None, [dict(_resa, validated=True)])[0] == "used"
             and E.statut_derive(docs[0], None, [_resa])[0] == "unlocked")

    # /me de A : son invitation enfant P1 porte « partagée » (booléen + canal, sans PII)
    _ea = ident(1)[0]
    _tok_a = H.jeton_espace(base, code=codes_de(base, _ea)[0]["code"], email=_ea)
    c, me = await appel(R.referral_me(H.Requete({}, {"x-espace-token": _tok_a})))
    _p1 = [x for x in (me or {}).get("passes", []) if x.get("share_token") == toks[1]]
    verifier("K14a. GET /me de A : P1 chain_shared true, chain_share_channel whatsapp, aucune PII",
             c == 200 and _p1 and _p1[0].get("chain_shared") is True
             and _p1[0].get("chain_share_channel") == "whatsapp" and not E.contient_pii(_p1[0]),
             (c, str(_p1)[:400]))
    verifier("K14a-bis. /chain/share journalise dans referral_invitations (pass P1, rattaché à A après liaison)",
             any(i.get("pass_id") == docs[1]["id"] and i.get("sponsor_email_norm") == _ea
                 and i.get("channel") == "whatsapp" for i in base["referral_invitations"].docs)
             and any(i.get("pass_id") == docs[1]["id"] for i in (me or {}).get("invitations", [])))
    verifier("K14a-ter. pass hors chaîne : chain_shared false, canal None",
             E.partage_chaine(docs[0]) == {"shared": False, "channel": None})

    # 409 essai déjà reçu (autre séance, autre chaîne)
    base, occ = depart()
    _course = [x for x in base["courses"].docs if x["id"] == H.COURS_DUO][0]
    occ2 = R._occurrences(_course)[1]
    c, pstd = await H.creer_pass(base, occ2)
    t_std, _ = await preparer_et_partager(pstd["share_token"])
    c, j = await rejoindre(pstd["share_token"], 7)
    assert c == 200, (c, j)
    c, r = await entree()
    t0 = r["share_token"]
    await preparer_et_partager(t0)
    avant = V3.etat(base)
    c, x = await rejoindre(t0, 7)
    verifier("K14. une personne qui a déjà un essai -> 409 free_trial_already_*, P0 rouvert",
             c == 409 and str(raison(x)).startswith("free_trial_already")
             and doc_par_tok(base, t0)["invitee"] is None and V3.etat(base)["resas"] == avant["resas"], (c, x))
    # coupe-circuit : archiver la campagne ferme le P0 et ses enfants
    base, occ = depart()
    c, r = await entree()
    t0 = r["share_token"]
    t1, _ = await preparer_et_partager(t0)
    base["referral_campaigns"].docs[0]["status"] = "archived"
    c, x = await rejoindre(t0, 1)
    verifier("K15. campagne archivée : join sur P0 -> 410, rien octroyé",
             c == 410 and doc_par_tok(base, t0)["invitee"] is None and not base["free_trial_claims"].docs, (c, x))
    base["referral_campaigns"].docs[0]["status"] = "active"
    c, j = await rejoindre(t0, 1)
    t2, _ = await preparer_et_partager(t1)
    base["referral_campaigns"].docs[0]["status"] = "archived"
    c, x = await rejoindre(t1, 2)
    verifier("K15b. campagne archivée : join sur l'enfant P1 -> 410", c == 410, (c, x))


# ═══════════════════════════════════════════════════════════════════════════
# 4. Audit sécurité (P1-A, P1-B, P2)
# ═══════════════════════════════════════════════════════════════════════════
def _faux_p0(i, created_at, invitee=None):
    return {"id": "faux-p0-%d-%s" % (i, created_at[:10]), "share_token": "faux-tok-%d-%s" % (i, created_at[:10]),
            "status": "waiting" if not invitee else "unlocked", "invitee": invitee,
            "course_id": H.COURS_DUO, "occurrence": "x-%d" % i, "created_at": created_at,
            "sponsor": {"email_norm": "campagne:%s:faux-%d-%s" % (CAMP_ID, i, created_at[:10])},
            "origin": {"source_type": "partner", "source_id": PARTENAIRE, "campaign_id": CAMP_ID,
                       "entry_key_hash": "h%d" % i}}


async def partie_audit():
    from datetime import datetime, timedelta, timezone
    _vieux = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    _recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    # P1-A (1) : 500 P0 abandonnés de plus de 24 h ne bloquent plus
    base, occ = depart()
    base["referral_passes"].docs += [_faux_p0(i, _vieux) for i in range(500)]
    c, r = await entree()
    verifier("A1. 500 P0 ouverts VIEUX (> 24 h) : ignorés du plafond -> 201", c == 201, (c, r))
    base["referral_passes"].docs += [_faux_p0(i, _recent) for i in range(499)]
    c, r = await entree()
    verifier("A1b. 500 P0 ouverts RÉCENTS -> 409 campagne_complete", c == 409 and raison(r) == "campagne_complete", (c, r))
    # P1-A (2) : débit par IP ET par campagne (5 P0 / heure) ; une clé connue ne le consomme pas
    base, occ = depart()
    R._DEBIT_ENTREE_CAMPAGNE.clear()
    _ip = {"CF-Connecting-IP": "203.0.113.77"}

    async def _e(cle=None):
        _h = dict(_ip)
        if cle:
            _h["X-Entry-Key"] = cle
        return await appel(R.referral_campagne_entree(TOK_CAMP, H.Requete({}, _h)))
    res = [await _e() for _ in range(5)]
    c6, r6 = await _e()
    verifier("A2. même IP, même campagne : 5 P0 créés puis 429 au 6e, rien écrit",
             [x[0] for x in res] == [201] * 5 and c6 == 429 and len(p0s(base)) == 5, ([x[0] for x in res], c6))
    c7, r7 = await _e(cle=res[0][1]["entry_key"])
    verifier("A2b. clé X-Entry-Key connue : 200 même P0 malgré le débit épuisé", c7 == 200
             and r7.get("share_token") == res[0][1]["share_token"], (c7, r7))
    verifier("A2c. débit par campagne : constante 5 / heure", R.CAMPAGNE_ENTREES_PAR_IP_HEURE == 5)
    # P1-B : plafond d'ESSAIS par campagne (défaut 30)
    verifier("B0. CAMPAGNE_ESSAIS_MAX = 30 par défaut", R.CAMPAGNE_ESSAIS_MAX == 30, R.CAMPAGNE_ESSAIS_MAX)
    base, occ = depart()
    c, r = await entree()
    t0 = r["share_token"]
    await preparer_et_partager(t0)
    base["referral_passes"].docs += [_faux_p0(i, _recent, invitee={"email_norm": "deja%d@exemple.test" % i})
                                     for i in range(30)]
    avant = V3.etat(base)
    n_psp = len(H.MOUCHARDS["paiements"])
    c, x = await rejoindre(t0, 1)
    verifier("B1. 31e essai de la campagne -> 409 campagne_complete, RIEN consommé (ni invité, verrou, code, résa)",
             c == 409 and raison(x) == "campagne_complete" and doc_par_tok(base, t0)["invitee"] is None
             and V3.etat(base) == avant and len(H.MOUCHARDS["paiements"]) == n_psp
             and not base["free_trial_claims"].docs, (c, x, V3.etat(base), avant))
    c, x = await entree()
    verifier("B2. /entry quand le plafond d'essais est atteint -> 409 campagne_complete",
             c == 409 and raison(x) == "campagne_complete", (c, x))
    base["referral_passes"].docs = [d for d in base["referral_passes"].docs if not d["id"].startswith("faux-p0-29")]
    c, j = await rejoindre(t0, 1)
    verifier("B3. sous le plafond (29 essais) : le 30e s'inscrit", c == 200 and j.get("status") == "unlocked", (c, str(j)[:200]))
    # P2 : campagne archivée -> la chaîne ne s'étend plus
    base, occ = depart()
    c, r = await entree()
    t0 = r["share_token"]
    c, x = await V3.chaine(t0)
    k_ok = c == 201
    base["referral_campaigns"].docs[0]["status"] = "archived"
    c, x = await V3.partager(t0)
    verifier("P2a. campagne archivée : /chain/share -> 410, parent non marqué partagé",
             k_ok and c == 410 and not (doc_par_tok(base, t0).get("chain") or {}).get("shared_at"), (c, x))
    base, occ = depart()
    c, r = await entree()
    base["referral_campaigns"].docs[0]["status"] = "archived"
    n = len(base["referral_passes"].docs)
    c, x = await V3.chaine(r["share_token"])
    verifier("P2b. campagne archivée : POST /chain -> 410, aucun enfant créé",
             c == 410 and len(base["referral_passes"].docs) == n, (c, x))
    # pass d'avant : /chain inchangé (aucune lecture de campagne)
    base, occ, p0 = await V3.depart()
    c, x = await V3.chaine(p0["share_token"])
    verifier("P2c. pass Duo classique : POST /chain inchangé (201)", c == 201, (c, x))


# ═══════════════════════════════════════════════════════════════════════════
# 5. A1 : un refus d'IDENTITÉ libère la place d'enfant de CET appareil
#    A3 : le parrain d'une chaîne ne voit pas les données de son filleul
# ═══════════════════════════════════════════════════════════════════════════
def _enfants_vivants(base, parent_id):
    return [d for d in base["referral_passes"].docs
            if (d.get("chain") or {}).get("parent_pass_id") == parent_id]


async def _cas_liberation(base, t_parent, libelle):
    """Sur le pass `t_parent` (sans invité) : A (déjà inscrit plus haut) prépare
    et partage un enfant puis se fait refuser (identité) -> l'enfant est libéré ;
    ensuite un ami légitime (personne 6) recrée l'enfant et s'inscrit."""
    d_par = doc_par_tok(base, t_parent)
    t_enf, _ = await preparer_et_partager(t_parent)
    d_enf = doc_par_tok(base, t_enf)
    c, x = await rejoindre(t_parent, 1)
    d_par, d_enf = doc_par_tok(base, t_parent), doc_par_tok(base, t_enf)
    verifier("L1%s. A refusé (identité, 409 auto_parrainage) : son enfant passe cancelled, jamais supprimé" % libelle,
             c == 409 and raison(x) == "auto_parrainage" and d_enf is not None and d_enf["status"] == "cancelled"
             and any(e.get("type") == "cancelled" and "auto_parrainage" in str(e.get("detail"))
                     for e in d_enf.get("events", [])), (c, x, d_enf and d_enf.get("status")))
    verifier("L1%sb. le parent est rouvert : plus de child_pass_id / shared_at / share_channel, aucun enfant vivant" % libelle,
             not any(k in (d_par.get("chain") or {}) for k in ("child_pass_id", "child_created_at", "shared_at", "share_channel"))
             and not _enfants_vivants(base, d_par["id"]) and d_par["invitee"] is None, d_par.get("chain"))
    c, g = await pub(t_parent)
    verifier("L1%sc. le prochain visiteur repart de l'étape 1-2 : chain {exists:false, shared:false}" % libelle,
             g.get("chain") == {"exists": False, "shared": False} and g.get("chain_required") is True, g.get("chain"))
    t_enf2, _ = await preparer_et_partager(t_parent)
    c, j = await rejoindre(t_parent, 6)
    verifier("L1%sd. un ami légitime recrée l'enfant (nouveau jeton) et s'inscrit" % libelle,
             t_enf2 != t_enf and c == 200 and j.get("status") == "unlocked", (c, str(j)[:200]))


async def partie_liberation_et_filleul():
    # V556 classique : Léa -> P0 ; A inscrit sur P0 ; A refusé sur P1
    base, occ, p0 = await V3.depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    c, _ = await rejoindre(t0, 1)
    await _cas_liberation(base, t1, "")
    # chaîne de campagne : P0 -> A inscrit ; A refusé sur P1
    base, occ = depart()
    c, r = await entree()
    t0 = r["share_token"]
    t1, _ = await preparer_et_partager(t0)
    c, _ = await rejoindre(t0, 1)
    await _cas_liberation(base, t1, "-camp")

    # jamais de libération : refus transitoire, mauvaise clé, enfant qui a un invité
    base, occ, p0 = await V3.depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    c, _ = await rejoindre(t0, 1)                       # A inscrit sur P0
    c, x = await V3.chaine(t1)                          # enfant P2 préparé, NON partagé
    c2, x2 = await rejoindre(t1, 6)                     # un vrai inconnu, pas encore partagé
    d1 = doc_par_tok(base, t1)
    verifier("L2. refus TRANSITOIRE (invitation_requise) : l'enfant reste (non libéré)",
             c2 == 409 and raison(x2) == "invitation_requise" and _enfants_vivants(base, d1["id"])
             and (d1.get("chain") or {}).get("child_pass_id"), (c2, x2))
    await V3.partager(t1)
    c3, x3 = await rejoindre(t1, 1, cle="cle-d-un-autre-appareil")
    verifier("L3. refus avec une AUTRE clé d'appareil : rien n'est libéré",
             c3 in (403, 409) and _enfants_vivants(base, d1["id"])
             and (doc_par_tok(base, t1).get("chain") or {}).get("shared_at"), (c3, x3))
    # enfant qui a DÉJÀ un invité : B prépare P2, C s'y inscrit (ordre inverse), puis A refusé avec la clé de B
    base, occ, p0 = await V3.depart()
    t0 = p0["share_token"]
    t1, _ = await preparer_et_partager(t0)
    c, _ = await rejoindre(t0, 1)
    t2, _ = await preparer_et_partager(t1)              # clé de P2 = CLES[t1]
    t3, _ = await preparer_et_partager(t2)
    c, jc = await rejoindre(t2, 3)                      # C inscrit sur P2 (B pas encore)
    c4, x4 = await rejoindre(t1, 1)                     # A refusé sur P1 avec la clé de P2
    d2 = doc_par_tok(base, t2)
    verifier("L4. enfant qui a déjà un invité : JAMAIS libéré", c4 == 409 and d2["status"] != "cancelled"
             and d2["invitee"] and (doc_par_tok(base, t1)["chain"] or {}).get("child_pass_id") == d2["id"], (c4, d2["status"]))

    # A3 : le parrain d'une chaîne ne voit ni le prénom, ni le billet, ni le QR de son filleul
    base, occ = depart()
    c, r = await entree()
    t0 = r["share_token"]
    t1, _ = await preparer_et_partager(t0)
    c, _ = await rejoindre(t0, 1)
    t2, _ = await preparer_et_partager(t1)
    c, jb = await rejoindre(t1, 2)
    _ea, _eb = ident(1)[0], ident(2)[0]
    _code_b = doc_par_tok(base, t1)["reservations"]["invitee_code"]
    _tok_a = H.jeton_espace(base, code=codes_de(base, _ea)[0]["code"], email=_ea)
    c, me = await appel(R.referral_me(H.Requete({}, {"x-espace-token": _tok_a})))
    _p1 = [x for x in (me or {}).get("passes", []) if x.get("share_token") == t1]
    _txt = json.dumps(_p1, ensure_ascii=False)
    verifier("F1. /me de A (chaîne) : ami_rejoint true, invitee null, AUCUN billet/QR/code/prénom de B",
             c == 200 and _p1 and _p1[0].get("ami_rejoint") is True and _p1[0].get("invitee") is None
             and all(t.get("role") != "invitee" for t in _p1[0].get("tickets", []))
             and _code_b not in _txt and "Bruno" not in _txt and not E.contient_pii(_p1[0]), _txt[:500])
    verifier("F1b. A garde SON billet (place de parrain = sa réservation de filleul du parent)",
             len(_p1[0].get("tickets", [])) == 1 and _p1[0]["tickets"][0]["role"] == "sponsor")
    _dp0 = doc_par_tok(base, t0)
    _d = E.dto_pass(_dp0, "unlocked", E.tickets_du_pass(_dp0, [], FRONT), FRONT)
    verifier("F2. pass d'origine campagne : dto_pass masque aussi l'invité (ami_rejoint seul)",
             _d.get("invitee") is None and _d.get("ami_rejoint") is True)
    _adm = E.dto_admin(doc_par_tok(base, t1), "unlocked", [], FRONT)
    verifier("F3. la vue ADMIN garde l'invité (prénom + e-mail)", (_adm.get("invitee") or {}).get("email") == _eb)
    # Pass Duo classique : inchangé
    base, occ, p0 = await V3.depart(chaine_active=False)
    c, j = await rejoindre(p0["share_token"], 2)
    c, me = await appel(R.referral_me(H.req_parrain(base)))
    _pc = me["passes"][0]
    verifier("F4. Pass Duo classique : /me inchangé (prénom de l'ami, 2 billets) + ami_rejoint true",
             _pc["invitee"] == {"first_name": "Bruno"} and len(_pc["tickets"]) == 2
             and {t["role"] for t in _pc["tickets"]} == {"sponsor", "invitee"} and _pc.get("ami_rejoint") is True,
             (_pc.get("invitee"), len(_pc.get("tickets", []))))


def main():
    _tmp = tempfile.mkdtemp(prefix="banc_par1_")
    _orig = S._V413_MEDIA_DIR
    S._V413_MEDIA_DIR = _tmp
    try:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:  # noqa: BLE001
            pass
        boucle = asyncio.get_event_loop()
        for partie in (partie_cible, partie_page_og, partie_entree, partie_chaine_5, partie_audit,
                       partie_liberation_et_filleul):
            try:
                _r = partie()
                if asyncio.iscoroutine(_r):
                    boucle.run_until_complete(_r)
            except Exception as err:  # noqa: BLE001  (banc ROUGE : on le dit, on ne plante pas)
                import traceback
                verifier("PARTIE %s exécutée sans exception" % partie.__name__, False,
                         "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1500:]))
    finally:
        S._V413_MEDIA_DIR = _orig
        shutil.rmtree(_tmp, ignore_errors=True)
    ok = sum(1 for _, c, _ in H.RESULTATS if c)
    print("=" * 78)
    print("PAR-1 — CAMPAGNE RACINE DE CHAÎNE : %d vérifications" % len(H.RESULTATS))
    print("=" * 78)
    for nom, cond, detail in H.RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:900])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(H.RESULTATS)))
    return 0 if ok == len(H.RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

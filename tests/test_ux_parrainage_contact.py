#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UX-P1 (29/09) — Invitation & parrainage : étape 2 de WizardFilleul.

Ce que ce banc prouve (MongoDB en mémoire, VRAIES routes, VRAI moteur pur —
harnais de `test_parrainage_v3.py` importé, jamais recopié) :
  - PATCH /pass/{tok}/chain accepte `photo_url`, `whatsapp`, `consent_contact` ;
    prénom / photo re-figent `inviter_display`, la share_url et la carte changent ;
  - sans photo : photo de profil si une identité abonné est présentée, sinon
    avatar Afroboost (jamais la photo du coach) ; `photo_suggeree` exposée ;
  - le numéro est normalisé E.164 (3 écritures -> 1), invalide -> 422, jamais
    renvoyé en clair (`whatsapp_renseigne` seulement) ;
  - le contact naît chez le COACH PROPRIÉTAIRE (pass / campagne / plateforme),
    dédoublonné par (coach, téléphone), jamais chez un autre coach ;
  - consent_contact = false -> refus inscrit au registre `subscribers` EXISTANT,
    donc exclu des campagnes par `c3_refus_exprimes` / `c3_verdict` (C3) ;
  - POST /pass/{tok}/chain/photo : X-Chain-Key, type, signature, taille.
AUCUN réseau, AUCUN e-mail, AUCUNE donnée réelle. Disque : dossier temporaire.

Lancement :  python3 tests/test_ux_parrainage_contact.py
"""
import asyncio
import io
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

import api.routes.tenant_contacts as TC  # noqa: E402

PHOTO_PROFIL = "https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/profil-lea.jpg"
PHOTO_CHOISIE = "https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/invitation-b.jpg"
PHOTO_COACH = "https://res.cloudinary.com/dtm0r7hwq/image/upload/v1/coach-bassi.jpg"
COACH_A = "coach.a@exemple.test"
COACH_B = "coach.b@exemple.test"
COACH_C = "coach.c@exemple.test"
NUM_E164 = "+41791234567"

PNG_MIN = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
           b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
           b"\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")
JPEG_MIN = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64 + b"\xff\xd9"


class FauxFichier:
    def __init__(self, nom, type_mime, contenu):
        self.filename = nom
        self.content_type = type_mime
        self._b = io.BytesIO(contenu)

    async def read(self, n=-1):
        return self._b.read(n)


def _doc(base, tok):
    return V3.doc_par_tok(base, tok)


def _contacts(base, coach_id=None):
    return [d for d in base["chat_participants"].docs
            if coach_id is None or d.get("coach_id") == coach_id]


def _registre(base, valeur):
    return [d for d in base["subscribers"].docs
            if d.get("channel") == "whatsapp" and d.get("value") == valeur]


async def patch(tok, corps, cle=V3._DEF, entetes=None):
    _e = dict(V3._entete_cle(tok, cle))
    _e.update(entetes or {})
    return await appel(R.referral_chaine_modifier(tok, V3.req(corps, _e)))


async def photo(tok, fichier, cle=V3._DEF):
    return await appel(R.referral_chaine_photo(tok, V3.req({}, V3._entete_cle(tok, cle)), fichier))


async def enfant_neuf(coach_id=None, corps=None, entetes=None):
    """Un pass P0 (coach éventuel) + son invitation enfant ; rend (base, t0, enfant_doc, réponse)."""
    base, occ, p0 = await V3.depart()
    t0 = p0["share_token"]
    if coach_id is not None:
        _doc(base, t0)["coach_id"] = coach_id
    c, r = await appel(R.referral_chaine_creer(t0, V3.req(corps or {"display_name": "Henri"}, entetes)))
    assert c == 201, (c, r)
    V3.CLES[t0] = r["edit_key"]
    return base, t0, _doc(base, r["child"]["share_token"]), r


# ═══════════════════════════════════════════════════════════════════════════
async def partie_identite_photo():
    base, t0, enf, r0 = await enfant_neuf()
    base["coaches"].docs.append({"email": "", "photo_url": PHOTO_COACH})
    v0 = r0["child"]["preview_version"]
    carte0 = r0["child"]["card_url"]

    c, r = await patch(t0, {"display_name": "Bruno"})
    ch = r.get("child") or {}
    verifier("UX1. PATCH prénom -> 200, inviter_display.prenom = Bruno",
             c == 200 and ch.get("inviter_display", {}).get("prenom") == "Bruno", (c, ch.get("inviter_display")))
    verifier("UX1b. ?v incrémenté (preview_version et share_url)",
             ch.get("preview_version") == v0 + 1 and ch.get("share_url", "").endswith("?v=%d" % (v0 + 1)),
             (v0, ch.get("preview_version"), ch.get("share_url")))
    verifier("UX1c. card_url change avec le prénom", ch.get("card_url") and ch["card_url"] != carte0, ch.get("card_url"))
    verifier("UX1d. figé en base (inviter_display.prenom)",
             (_doc(base, ch["share_token"]).get("inviter_display") or {}).get("prenom") == "Bruno")

    carte1 = ch["card_url"]
    c, r = await patch(t0, {"photo_url": PHOTO_CHOISIE})
    ch = r.get("child") or {}
    d = _doc(base, ch.get("share_token"))
    verifier("UX2. photo membre -> inviter_display.photo_url = photo choisie",
             c == 200 and ch.get("inviter_display", {}).get("photo_url") == PHOTO_CHOISIE
             and ch.get("photo_url") == PHOTO_CHOISIE, (c, ch.get("inviter_display")))
    verifier("UX2b. la carte de l'enfant utilise cette photo (inviter_display_du_pass) et change d'URL",
             E.inviter_display_du_pass(d)["photo_url"] == PHOTO_CHOISIE and ch.get("card_url") != carte1,
             ch.get("card_url"))
    verifier("UX2c. prénom conservé quand seule la photo change", ch["inviter_display"]["prenom"] == "Bruno")

    c, r = await patch(t0, {"photo_url": "https://evil.example/x.jpg"})
    verifier("UX2d. photo d'un hôte non admis -> 422", c == 422, (c, r))
    c, r = await patch(t0, {"photo_url": None})
    ch = r.get("child") or {}
    verifier("UX3. photo retirée, aucune identité -> avatar Afroboost (None), jamais la photo du coach",
             c == 200 and ch["inviter_display"]["photo_url"] is None and ch["inviter_display"]["source"] == "member"
             and PHOTO_COACH not in json.dumps(r) and ch.get("photo_suggeree") is None, ch.get("inviter_display"))

    # identité abonné présentée : la photo de profil est proposée et sert de repli
    base, occ, p0 = await V3.depart()
    base["users"].docs.append({"id": "u-lea", "email": H.PARRAIN_EMAIL, "photo_url": PHOTO_PROFIL})
    t0 = p0["share_token"]
    ident = {"x-espace-token": H.jeton_espace(base)}
    c, r = await appel(R.referral_chaine_creer(t0, V3.req({"display_name": "Léa"}, ident)))
    V3.CLES[t0] = (r or {}).get("edit_key")
    ch = r.get("child") or {}
    verifier("UX4. création avec identité abonné -> photo_suggeree = photo de profil",
             c == 201 and ch.get("photo_suggeree") == PHOTO_PROFIL, (c, ch.get("photo_suggeree")))
    verifier("UX4b. sans photo choisie -> la carte prend la photo de profil",
             ch.get("inviter_display", {}).get("photo_url") == PHOTO_PROFIL and ch.get("photo_url") is None,
             ch.get("inviter_display"))
    c, r = await patch(t0, {"photo_url": PHOTO_CHOISIE})
    verifier("UX4c. photo choisie prime sur la photo de profil",
             r["child"]["inviter_display"]["photo_url"] == PHOTO_CHOISIE, r["child"]["inviter_display"])
    c, r = await patch(t0, {"photo_url": None})
    verifier("UX4d. photo retirée -> retour à la photo de profil (jamais le coach)",
             r["child"]["inviter_display"]["photo_url"] == PHOTO_PROFIL, r["child"]["inviter_display"])
    c, r = await appel(R.referral_chaine_apercu(t0, V3.req({}, ident)))
    verifier("UX4e. lecture (GET preview) expose aussi photo_suggeree",
             c == 200 and r["child"].get("photo_suggeree") == PHOTO_PROFIL, r.get("child", {}).get("photo_suggeree"))
    verifier("UX4f. aucune donnée personnelle dans les réponses", not V3.fuite(r, base), V3.fuite(r, base))
    # identité invalide : ignorée, la route reste publique
    c, r = await appel(R.referral_chaine_apercu(t0, V3.req({}, {"x-espace-token": "faux.jeton"})))
    verifier("UX4g. jeton abonné invalide ignoré sur la lecture (200)", c == 200, c)


async def partie_cle():
    base, t0, enf, _ = await enfant_neuf()
    avant = json.dumps(_doc(base, enf["share_token"]), sort_keys=True)
    c, _r = await patch(t0, {"whatsapp": NUM_E164, "display_name": "Pirate"}, cle="mauvaise-cle")
    verifier("UX5. mauvaise X-Chain-Key -> 403", c == 403, c)
    c, _r = await patch(t0, {"whatsapp": NUM_E164}, cle=None)
    verifier("UX5b. sans X-Chain-Key -> 403", c == 403, c)
    verifier("UX5c. rien écrit (ni pass, ni contact, ni registre)",
             json.dumps(_doc(base, enf["share_token"]), sort_keys=True) == avant
             and not _contacts(base) and not _registre(base, NUM_E164))


async def partie_numero_contact():
    # normalisation pure : trois écritures -> une E.164
    formes = ("079 123 45 67", "+41791234567", "0041 79 123 45 67", "+41 79 123 45 67")
    verifier("UX6. normalisation : 079 / +41 / 0041 -> même E.164",
             {TC.telephone_e164(f) for f in formes} == {NUM_E164}, [TC.telephone_e164(f) for f in formes])
    for mauvais in ("abc", "12", "079 12x 45 67", "+41 79+123", "0" * 20, ""):
        verifier("UX6b. invalide rejeté : %r" % mauvais, TC.telephone_e164(mauvais) == "")

    base, t0, enf, r0 = await enfant_neuf(coach_id=COACH_A)
    v0 = r0["child"]["preview_version"]
    c, r = await patch(t0, {"whatsapp": "079 12x", "consent_contact": True})
    verifier("UX7. numéro invalide -> 422 avec message clair",
             c == 422 and "indicatif" in str(r.get("detail", "")), (c, r))
    verifier("UX7b. 422 : rien écrit (ni numéro, ni contact)",
             not E.contact_invitant(_doc(base, enf["share_token"])) and not _contacts(base))
    c, r = await patch(t0, {"consent_contact": "oui"})
    verifier("UX7c. consent_contact non booléen -> 422", c == 422, (c, r))

    c, r = await patch(t0, {"whatsapp": "079 123 45 67", "consent_contact": True})
    ch = r.get("child") or {}
    d = _doc(base, enf["share_token"])
    verifier("UX8. PATCH numéro -> 200, stocké en E.164 côté serveur",
             c == 200 and E.contact_invitant(d).get("whatsapp_e164") == NUM_E164, (c, E.contact_invitant(d)))
    verifier("UX8b. DTO : whatsapp_renseigne true, consent_contact true, numéro JAMAIS en clair",
             ch.get("whatsapp_renseigne") is True and ch.get("consent_contact") is True
             and "791234567" not in json.dumps(r) and not E.contient_pii(r), ch)
    verifier("UX8c. numéro seul : pas de nouvelle version d'aperçu (non visuel)",
             ch.get("preview_version") == v0, (v0, ch.get("preview_version")))
    lst = _contacts(base)
    verifier("UX9. contact créé chez le coach PROPRIÉTAIRE du pass (coach A), un seul",
             len(lst) == 1 and lst[0]["coach_id"] == COACH_A and lst[0]["whatsapp"] == NUM_E164
             and lst[0]["name"] == "Henri", lst)
    k = lst[0]
    ref = k.get("referral") or {}
    verifier("UX9b. provenance : source referral + bloc referral complet",
             k.get("source") == "referral" and "referral" in (k.get("sources") or [])
             and ref.get("pass_id") == d["id"] and ref.get("inviter_pass_id") == _doc(base, t0)["id"]
             and ref.get("parent_referral_id") == _doc(base, t0)["id"]
             and ref.get("root_referral_id") == _doc(base, t0)["id"]
             and ref.get("type") == "pass_duo" and "campaign_id" in ref and ref.get("created_at"), k)
    verifier("UX9c. consentement marketing porté par le contact", k.get("marketing_consent") is True, k)
    verifier("UX9d. isolation : le contact appartient à A, pas à B",
             await TC.contact_appartient(base, COACH_A, "chat_participants", k["id"])
             and not await TC.contact_appartient(base, COACH_B, "chat_participants", k["id"]))

    # même numéro, même pass, autre écriture -> pas de doublon, pas de 2e provenance
    c, r = await patch(t0, {"whatsapp": "0041 79 123 45 67"})
    verifier("UX10. même numéro (autre écriture) même pass -> toujours 1 contact, 1 provenance",
             c == 200 and len(_contacts(base)) == 1 and len(_contacts(base)[0].get("referrals") or []) == 1,
             _contacts(base))

    # 2e saisie du même numéro chez le même coach, depuis une autre invitation
    base["chat_participants"].docs[0]["name"] = ""
    t_autre = await _second_enfant_meme_base(base, COACH_A)
    c, r = await patch(t_autre, {"whatsapp": "+41 79 123 45 67", "consent_contact": True})
    lst = _contacts(base, COACH_A)
    verifier("UX11. 2e saisie même numéro même coach -> pas de doublon (mise à jour + source ajoutée)",
             c == 200 and len(lst) == 1 and len(lst[0].get("referrals") or []) == 2
             and lst[0]["sources"].count("referral") == 1, lst)
    verifier("UX11b. prénom vide complété (champ autorisé)", lst[0]["name"] == "Henri", lst[0].get("name"))

    # fiche saisie par le coach avant : jamais écrasée
    base2, t2, enf2, _ = await enfant_neuf(coach_id=COACH_A)
    base2["chat_participants"].docs.append({"id": "fiche-coach", "name": "Client Connu", "whatsapp": "079 123 45 67",
                                            "email": "client@exemple.test", "source": "manual", "coach_id": COACH_A})
    c, r = await patch(t2, {"whatsapp": NUM_E164, "consent_contact": True})
    f = _contacts(base2, COACH_A)
    verifier("UX12. fiche existante du coach : retrouvée (variantes), nom / e-mail / source / numéro intacts",
             len(f) == 1 and f[0]["name"] == "Client Connu" and f[0]["email"] == "client@exemple.test"
             and f[0]["source"] == "manual" and f[0]["whatsapp"] == "079 123 45 67"
             and set(f[0]["sources"]) == {"manual", "referral"} and f[0]["referral"]["pass_id"] == enf2["id"], f)

    # même numéro chez un AUTRE coach -> contact distinct chez lui, rien chez A
    base3, t3, enf3, _ = await enfant_neuf(coach_id=COACH_B)
    base3["chat_participants"].docs.append({"id": "fiche-a", "name": "Chez A", "whatsapp": NUM_E164,
                                            "source": "manual", "coach_id": COACH_A})
    c, r = await patch(t3, {"whatsapp": NUM_E164, "consent_contact": True})
    fa, fb = _contacts(base3, COACH_A), _contacts(base3, COACH_B)
    verifier("UX13. même numéro chez un autre coach -> contact DISTINCT chez B, fiche de A intacte",
             c == 200 and len(fb) == 1 and fb[0]["id"] != "fiche-a" and len(fa) == 1
             and fa[0]["name"] == "Chez A" and "referral" not in fa[0] and "sources" not in fa[0], (fa, fb))

    # pass de la plateforme (coach_id vide) -> espace plateforme
    base4, t4, enf4, _ = await enfant_neuf(coach_id="")
    await patch(t4, {"whatsapp": NUM_E164, "consent_contact": True})
    from api.routes.shared import DEFAULT_COACH_ID
    verifier("UX14. pass plateforme -> contact dans l'espace plateforme (super-admin global)",
             [k["coach_id"] for k in _contacts(base4)] == [DEFAULT_COACH_ID]
             and await TC.contact_appartient(base4, H.ADMIN, "chat_participants", _contacts(base4)[0]["id"])
             and not await TC.contact_appartient(base4, COACH_A, "chat_participants", _contacts(base4)[0]["id"]))

    # campagne : propriétaire = celui de la campagne
    base5, t5, enf5, _ = await enfant_neuf(coach_id="")
    base5["referral_campaigns"].docs.append({"id": "camp-ux", "coach_id": COACH_C, "type": "trial",
                                             "status": "active", "share_token": "tok-camp-ux"})
    _doc(base5, enf5["share_token"])["origin"] = {"campaign_id": "camp-ux", "root_source_type": "partner",
                                                  "root_source_id": COACH_C}
    await patch(t5, {"whatsapp": NUM_E164, "consent_contact": True})
    k5 = _contacts(base5)
    verifier("UX15. invitation de campagne -> contact chez le propriétaire de la campagne, type trial",
             len(k5) == 1 and k5[0]["coach_id"] == COACH_C and k5[0]["referral"]["campaign_id"] == "camp-ux"
             and k5[0]["referral"]["type"] == "trial", k5)


async def _second_enfant_meme_base(base, coach_id):
    """Un 2e pass P0 (autre parrain) dans la MÊME base + son enfant ; rend le jeton du parent."""
    tok_marc = H.jeton_espace(base, code="BASS-DUO-02", email="marc.parrain@exemple.test")
    base["subscriptions"].docs.append(dict(base["subscriptions"].docs[0], id="sub-marc", code="BASS-DUO-02",
                                           email="marc.parrain@exemple.test"))
    base["discount_codes"].docs.append(dict(base["discount_codes"].docs[0], id="code-marc", code="BASS-DUO-02",
                                            assignedEmail="marc.parrain@exemple.test"))
    occ = _doc(base, [d for d in base["referral_passes"].docs][0]["share_token"])["occurrence"]
    c, p = await H.creer_pass(base, occ, tok=tok_marc)
    assert c == 201, (c, p)
    _doc(base, p["share_token"])["coach_id"] = coach_id
    c, r = await appel(R.referral_chaine_creer(p["share_token"], V3.req({"display_name": "Henri"})))
    assert c == 201, (c, r)
    V3.CLES[p["share_token"]] = r["edit_key"]
    return p["share_token"]


async def partie_consentement():
    base, t0, enf, _ = await enfant_neuf(coach_id=COACH_A)
    c, r = await patch(t0, {"whatsapp": "079 123 45 67", "consent_contact": False})
    k = _contacts(base)
    verifier("UX16. consent false : le contact existe pour le suivi du coach, marketing_consent false",
             c == 200 and len(k) == 1 and k[0]["marketing_consent"] is False and k[0]["coach_id"] == COACH_A, k)
    reg = _registre(base, NUM_E164)
    verifier("UX16b. refus inscrit au registre EXISTANT `subscribers` (whatsapp, E.164, opted_out)",
             len(reg) == 1 and reg[0]["status"] == "opted_out" and reg[0].get("opted_out_at"), reg)
    refus = await S.c3_refus_exprimes("whatsapp", [k[0]["whatsapp"]])
    verifier("UX16c. C3 : c3_refus_exprimes le retient -> campagne l'écarte (c3_verdict = refus)",
             NUM_E164 in refus and S.c3_verdict("whatsapp", k[0]["whatsapp"], refus, set()) == "refus", refus)
    # un « oui » public ultérieur ne ressuscite pas le refus (règle DETTE 3 du registre)
    c, r = await patch(t0, {"consent_contact": True})
    verifier("UX16d. consent true après un refus : le refus reste (aucun accord fabriqué)",
             _registre(base, NUM_E164)[0]["status"] == "opted_out"
             and NUM_E164 in await S.c3_refus_exprimes("whatsapp", [NUM_E164]), _registre(base, NUM_E164))

    base, t0, enf, _ = await enfant_neuf(coach_id=COACH_A)
    base["subscribers"].docs.append({"id": "s1", "channel": "whatsapp", "value": NUM_E164, "status": "targeted",
                                     "source": "campaign_target"})
    await patch(t0, {"whatsapp": NUM_E164, "consent_contact": False})
    verifier("UX17. consent false sur une ligne `targeted` existante -> opted_out (une seule ligne)",
             [d["status"] for d in _registre(base, NUM_E164)] == ["opted_out"], _registre(base, NUM_E164))

    base, t0, enf, _ = await enfant_neuf(coach_id=COACH_A)
    await patch(t0, {"whatsapp": NUM_E164, "consent_contact": True})
    reg = _registre(base, NUM_E164)
    verifier("UX18. consent true : ligne neutre `targeted` (STOP exprimable), JAMAIS confirmed ni refus",
             len(reg) == 1 and reg[0]["status"] == "targeted" and not reg[0].get("consent_at")
             and NUM_E164 not in await S.c3_refus_exprimes("whatsapp", [NUM_E164]), reg)

    # registre illisible avec consent false : AUCUN contact créé (jamais joignable sans refus inscrit)
    base, t0, enf, _ = await enfant_neuf(coach_id=COACH_A)
    vrai = base._c["subscribers"] = H._Coll("subscribers")

    async def _panne(*a, **k):
        raise RuntimeError("registre en panne")
    vrai.update_one = _panne
    vrai.find_one = _panne
    c, r = await patch(t0, {"whatsapp": NUM_E164, "consent_contact": False})
    verifier("UX19. registre en panne + consent false -> 200 mais AUCUN contact marketing créé",
             c == 200 and not _contacts(base), (c, _contacts(base)))


async def partie_upload():
    media = tempfile.mkdtemp(prefix="banc-uxp1-")
    ancien = S._V413_MEDIA_DIR
    S._V413_MEDIA_DIR = media
    try:
        base, t0, enf, _ = await enfant_neuf()
        c, _r = await photo(t0, FauxFichier("a.png", "image/png", PNG_MIN), cle=None)
        verifier("UX20. upload sans X-Chain-Key -> 403", c == 403, c)
        c, _r = await photo(t0, FauxFichier("a.png", "image/png", PNG_MIN), cle="mauvaise")
        verifier("UX20b. upload mauvaise X-Chain-Key -> 403", c == 403, c)
        for nom, f, attendu in (
                ("GIF", FauxFichier("a.gif", "image/gif", b"GIF89a" + b"\x00" * 20), 415),
                ("faux PNG (signature)", FauxFichier("a.png", "image/png", b"<html>pas une image</html>"), 415),
                ("PNG déclaré, JPEG réel", FauxFichier("a.png", "image/png", JPEG_MIN), 415),
                ("extension .svg", FauxFichier("a.svg", "image/png", PNG_MIN), 415),
                ("> 5 Mo", FauxFichier("a.jpg", "image/jpeg", JPEG_MIN + b"\x00" * (5 * 1024 * 1024)), 413)):
            c, _r = await photo(t0, f)
            verifier("UX21. upload refusé : %s -> %d" % (nom, attendu), c == attendu, (c, _r))
        verifier("UX21b. aucun fichier enregistré par les refus", not base["uploaded_files"].docs)
        c, r = await photo(t0, FauxFichier("moi.webp", "image/webp", b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 30))
        c2, r2 = await photo(t0, FauxFichier("moi.jpg", "image/jpeg", JPEG_MIN))
        url = (r2 or {}).get("photo_url", "")
        verifier("UX22. upload valide -> 201 {photo_url: /api/files/...}",
                 c == 201 and c2 == 201 and url.startswith("/api/files/") and E.url_image_partage_valide(url), (c2, r2))
        f = base["uploaded_files"].docs[-1]
        verifier("UX22b. stockage V413, aucune donnée personnelle dans la fiche du fichier",
                 f.get("asset_type") == "referral_chain_photo" and not E.contient_pii(f)
                 and "coach_email" not in f and set(r2.keys()) == {"photo_url"}, f)
        c, r = await patch(t0, {"photo_url": url})
        verifier("UX22c. la photo envoyée s'applique via PATCH (carte de l'enfant)",
                 c == 200 and r["child"]["inviter_display"]["photo_url"] == url, (c, r.get("child", {}).get("inviter_display")))
    finally:
        S._V413_MEDIA_DIR = ancien
        shutil.rmtree(media, ignore_errors=True)


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:  # noqa: BLE001
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_identite_photo, partie_cle, partie_numero_contact, partie_consentement, partie_upload):
        try:
            boucle.run_until_complete(partie())
        except Exception as err:  # noqa: BLE001
            import traceback
            verifier("PARTIE %s sans exception" % partie.__name__, False,
                     "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1500:]))
    res = [r for r in H.RESULTATS if str(r[0]).startswith(("UX", "PARTIE"))]
    ok = sum(1 for _, c, _ in res if c)
    for nom, cond, detail in res:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              ("" if cond or not detail else "\n         -> " + str(detail)[:600])))
    print("%d / %d verifications UX-P1 au vert" % (ok, len(res)))
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())

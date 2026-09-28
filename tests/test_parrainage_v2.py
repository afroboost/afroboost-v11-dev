#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V551 — PARRAINAGE V2 : le banc autonome (réglages de partage du coach,
invitation personnalisée du membre, page d'aperçu, filtre « nom affichable »).

Même harnais que `test_referral_pass_duo.py` (MongoDB en mémoire, VRAIES
routes, VRAI moteur pur) — importé tel quel, pas recopié. AUCUN réseau, AUCUN
e-mail, AUCUNE donnée réelle. Le seul disque touché est un dossier temporaire
(stockage V413 des images), supprimé à la fin.

Lancement :  python3 tests/test_parrainage_v2.py
"""
import asyncio
import io
import json
import os
import shutil
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

S, R, E = H.S, H.R, H.E
verifier, appel, Requete = H.verifier, H.appel, H.Requete

COACH_A = "coach.a@exemple.test"
COACH_B = "coach.b@exemple.test"
ADMIN = H.ADMIN

PNG_MIN = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
           b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
           b"\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")
JPEG_MIN = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64 + b"\xff\xd9"


class FauxFichier:
    """Ce que `UploadFile` expose aux routes : nom, type, lecture."""

    def __init__(self, nom, type_mime, contenu):
        self.filename = nom
        self.content_type = type_mime
        self._b = io.BytesIO(contenu)

    async def read(self, n=-1):
        return self._b.read(n)


def bearer(email):
    return {"Authorization": "Bearer " + H.jeton_admin(email)}


def req_coach(email, corps=None, extra=None):
    ent = bearer(email)
    ent.update(extra or {})
    return Requete(corps if corps is not None else {}, ent)


def base_v2(**k):
    base, occ = H.base_de_depart(**k)
    base["coaches"].docs += [{"email": COACH_A, "name": "Coach A"},
                             {"email": COACH_B, "name": "Coach B"}]
    return base, occ


async def partie_coach():
    base, _ = base_v2()

    # ── 1. authentification ──────────────────────────────────────────────
    c, _ = await appel(R.referral_share_settings_put(Requete({"default_message": "x"}, {})))
    verifier("1. PUT share-settings sans jeton -> 401", c == 401, c)
    c, _ = await appel(R.referral_share_settings_get(Requete({}, {})))
    verifier("1b. GET share-settings sans jeton -> 401", c == 401, c)
    tok_esp = H.jeton_espace(base)
    c, _ = await appel(R.referral_share_settings_put(
        Requete({"default_message": "x"}, {"x-espace-token": tok_esp, "Authorization": "Bearer " + tok_esp})))
    verifier("1c. PUT share-settings avec un jeton ABONNÉ -> 403", c == 403, c)
    c, _ = await appel(R.referral_share_settings_put(
        Requete({"default_message": "x"}, bearer("inconnu@exemple.test"))))
    verifier("1d. PUT share-settings avec un JWT d'une adresse non coach -> 403", c == 403, c)
    c, _ = await appel(R.referral_share_settings_put(
        Requete({"default_message": "x"}, {"X-User-Email": COACH_A})))
    verifier("2c. X-User-Email falsifié seul -> aucun droit (401/403)", c in (401, 403), c)
    verifier("2c-bis. rien n'a été écrit par les appels refusés",
             not base["referral_share_settings"].docs, base["referral_share_settings"].docs)

    # ── 2. cloisonnement ────────────────────────────────────────────────
    c, g = await appel(R.referral_share_settings_get(req_coach(COACH_A)))
    verifier("2. GET vierge : message/image null, effective = message intégré, defaults.message",
             c == 200 and g["default_message"] is None and g["share_image_url"] is None
             and g["effective"]["message"] == E.MESSAGE_INVITATION_DEFAUT
             and g["defaults"]["message"] == E.MESSAGE_INVITATION_DEFAUT
             and isinstance(g["effective"]["image_url"], str) and "updated_at" in g, g)
    c, a = await appel(R.referral_share_settings_put(req_coach(
        COACH_A, {"default_message": "  Viens danser avec moi !  ", "email": COACH_B, "coach_id": COACH_B,
                  "user_id": "u-b"})))
    verifier("2a. coach A écrit : trim, clé = identité serveur (email/coach_id du corps IGNORÉS)",
             c == 200 and a["default_message"] == "Viens danser avec moi !"
             and [d["_id"] for d in base["referral_share_settings"].docs] == [COACH_A]
             and "user_id" not in base["referral_share_settings"].docs[0]
             and base["referral_share_settings"].docs[0].get("updated_by") == COACH_A, (a, base["referral_share_settings"].docs))
    c, b = await appel(R.referral_share_settings_get(req_coach(COACH_B)))
    verifier("2b. coach B ne voit PAS le réglage de A", c == 200 and b["default_message"] is None, b)
    c, _ = await appel(R.referral_share_settings_put(req_coach(COACH_B, {"default_message": "Message B"})))
    c, a2 = await appel(R.referral_share_settings_get(req_coach(COACH_A)))
    verifier("2d. le PUT de B n'a pas touché A",
             a2["default_message"] == "Viens danser avec moi !" and len(base["referral_share_settings"].docs) == 2, a2)
    c, _ = await appel(R.referral_share_settings_put(req_coach(COACH_A, {"default_message": "x" * 281})))
    verifier("2e. message > 280 -> 422", c == 422, c)
    c, _ = await appel(R.referral_share_settings_put(req_coach(ADMIN, {"default_message": "Message plateforme"})))
    verifier("2f. super-admin -> clé \"\" (plateforme)",
             any(d["_id"] == "" and d["default_message"] == "Message plateforme"
                 for d in base["referral_share_settings"].docs), base["referral_share_settings"].docs)
    base["coaches"].docs.append({"email": "coach.c@exemple.test"})
    c, g3 = await appel(R.referral_share_settings_get(req_coach("coach.c@exemple.test")))
    verifier("2g. coach sans réglage : effective.message = message plateforme",
             g3["default_message"] is None and g3["effective"]["message"] == "Message plateforme", g3)
    c, a3 = await appel(R.referral_share_settings_put(req_coach(COACH_A, {"default_message": ""})))
    verifier("2h. \"\" -> retour au message par défaut (null, effective = plateforme)",
             c == 200 and a3["default_message"] is None and a3["effective"]["message"] == "Message plateforme", a3)

    # ── 4. share_image_url arbitraire ───────────────────────────────────
    for mauvaise in ("http://evil.example/x.png", "https://evil.example/api/files/a/b.png",
                     "/api/files/../../etc/passwd", "/api/files/abc/..", "../api/files/a/b.png",
                     "/api/files/a/b.png?x=1", "javascript:alert(1)", "/api/files/a b/c.png", 12):
        c, _ = await appel(R.referral_share_settings_put(req_coach(COACH_A, {"share_image_url": mauvaise})))
        verifier("4. share_image_url refusée -> 400 : %r" % (mauvaise,), c == 400, c)
    c, ok = await appel(R.referral_share_settings_put(req_coach(COACH_A, {"share_image_url": "/api/files/abc123/share_x.png"})))
    verifier("4b. share_image_url /api/files/<id>/<nom> acceptée",
             c == 200 and ok["share_image_url"] == "/api/files/abc123/share_x.png"
             and ok["effective"]["image_url"] == "/api/files/abc123/share_x.png", ok)
    c, ok = await appel(R.referral_share_settings_put(req_coach(COACH_A, {"share_image_url": None})))
    verifier("4c. share_image_url null -> image par défaut", c == 200 and ok["share_image_url"] is None, ok)

    # ── 3. upload image ─────────────────────────────────────────────────
    media = tempfile.mkdtemp(prefix="banc-v551-")
    ancien = S._V413_MEDIA_DIR
    S._V413_MEDIA_DIR = media
    try:
        c, _ = await appel(R.referral_share_settings_image(Requete({}, {}), FauxFichier("a.png", "image/png", PNG_MIN)))
        verifier("3. upload sans jeton -> 401", c == 401, c)
        c, _ = await appel(R.referral_share_settings_image(Requete({}, {"X-User-Email": COACH_A}),
                                                           FauxFichier("a.png", "image/png", PNG_MIN)))
        verifier("3a. upload avec X-User-Email seul -> 401/403", c in (401, 403), c)
        refus = [
            ("mauvais MIME", FauxFichier("a.gif", "image/gif", b"GIF89a" + b"\x00" * 20)),
            ("faux PNG (magic bytes)", FauxFichier("a.png", "image/png", b"<html>pas une image</html>")),
            ("PNG déclaré mais JPEG réel", FauxFichier("a.png", "image/png", JPEG_MIN)),
            ("extension .svg", FauxFichier("a.svg", "image/png", PNG_MIN)),
            ("extension .html", FauxFichier("a.html", "image/png", PNG_MIN)),
            ("SVG", FauxFichier("a.svg", "image/svg+xml", b"<svg xmlns='http://www.w3.org/2000/svg'/>")),
            ("> 3 Mo", FauxFichier("a.png", "image/png", PNG_MIN + b"\x00" * (3 * 1024 * 1024))),
            ("vide", FauxFichier("a.png", "image/png", b"")),
        ]
        for nom, f in refus:
            c, _ = await appel(R.referral_share_settings_image(req_coach(COACH_A), f))
            verifier("3b. upload refusé (%s) -> 400/413/415/422" % nom, c in (400, 413, 415, 422), c)
        verifier("3c. aucun fichier enregistré pour les refus", not base["uploaded_files"].docs,
                 len(base["uploaded_files"].docs))
        c, r = await appel(R.referral_share_settings_image(req_coach(COACH_A),
                                                           FauxFichier("../../mon chemin/Photo.PNG", "image/png", PNG_MIN)))
        url = (r or {}).get("share_image_url") or ""
        verifier("3d. upload valide -> 200/201, URL /api/files/<id>/<nom uuid> enregistrée dans les réglages de A",
                 c in (200, 201) and E.url_image_partage_valide(url)
                 and "Photo" not in url and "chemin" not in url and url.endswith(".png")
                 and any(d["_id"] == COACH_A and d.get("share_image_url") == url
                         for d in base["referral_share_settings"].docs), (c, r))
        fdoc = base["uploaded_files"].docs[-1] if base["uploaded_files"].docs else {}
        verifier("3e. stockage réutilisé : `uploaded_files` (même format que /api/files), aucun nom client",
                 fdoc.get("file_id") and url == "/api/files/%s/%s" % (fdoc.get("file_id"), fdoc.get("filename"))
                 and fdoc.get("content_type") == "image/png" and "Photo" not in json.dumps(fdoc, default=str), fdoc)
        c, r = await appel(R.referral_share_settings_image(req_coach(COACH_A), FauxFichier("x.jpg", "image/jpeg", JPEG_MIN)))
        verifier("3f. JPEG valide accepté", c in (200, 201) and (r or {}).get("share_image_url", "").endswith(".jpg"), (c, r))
    finally:
        S._V413_MEDIA_DIR = ancien
        shutil.rmtree(media, ignore_errors=True)
    verifier("3g. dossier média temporaire nettoyé", not os.path.exists(media))


def _instantane_profil(base):
    return json.dumps([base[c].docs for c in ("subscriptions", "users", "discount_codes")], sort_keys=True, default=str)


async def partie_membre():
    base, occ = base_v2()
    base["referral_share_settings"].docs.append({"_id": "", "default_message": "Message plateforme"})
    c, _ = await appel(R.referral_invitation_get(Requete({}, {})))
    verifier("5. GET /invitation sans jeton abonné -> 403", c == 403, c)
    c, _ = await appel(R.referral_invitation_get(Requete({}, {"X-User-Email": H.PARRAIN_EMAIL})))
    verifier("5a. GET /invitation avec X-User-Email seul -> 403", c == 403, c)
    c, inv = await appel(R.referral_invitation_get(H.req_parrain(base)))
    verifier("5b. GET /invitation : identité filtrée, message plateforme, aucun pass",
             c == 200 and inv["identity"]["display_name"] == "Léa" and inv["identity"]["photo_url"] is None
             and inv["default_message"] == "Message plateforme" and inv["pass"] is None, inv)
    base["referral_share_settings"].docs.append({"_id": "coach.a@exemple.test", "default_message": "Message du coach A"})
    for d in base["subscriptions"].docs + base["discount_codes"].docs:
        d["coach_id"] = COACH_A
    c, inv = await appel(R.referral_invitation_get(H.req_parrain(base)))
    verifier("5c. message par défaut : coach du membre > plateforme", inv.get("default_message") == "Message du coach A", inv)
    base["referral_share_settings"].docs[:] = []
    c, inv = await appel(R.referral_invitation_get(H.req_parrain(base)))
    verifier("5d. sans réglage : message intégré", inv.get("default_message") == E.MESSAGE_INVITATION_DEFAUT, inv)

    _, dto = await H.creer_pass(base, occ)
    tok_avant, url_avant = dto["share_token"], dto["share_url"]
    verifier("5e. pass neuf : invitation vide (version 0), share_url INCHANGÉE (sans ?v=)",
             dto.get("invitation") == {"display_name": None, "photo_url": None, "message": None, "version": 0}
             and url_avant == "https://afroboost.com/api/share/duo/%s" % tok_avant, dto.get("invitation"))
    c, inv = await appel(R.referral_invitation_get(H.req_parrain(base)))
    verifier("5f. GET /invitation : pass courant rendu (dto_pass)",
             inv["pass"] and inv["pass"]["id"] == dto["id"] and inv["pass"]["share_token"] == tok_avant, inv.get("pass"))

    profil_avant = _instantane_profil(base)
    corps = {"display_name": "  Léa B.  ", "photo_url": "https://firebasestorage.googleapis.com/v0/b/x/o/p.jpg",
             "message": "Viens avec moi <b>samedi</b> !", "email": "pirate@exemple.test"}
    c, d2 = await appel(R.referral_pass_invitation_put(dto["id"], H.req_parrain(base, corps)))
    verifier("5g. PUT /pass/{id}/invitation propriétaire -> 200, share_token IDENTIQUE, version 1, ?v=1",
             c == 200 and d2["share_token"] == tok_avant and d2["invitation"]["version"] == 1
             and d2["invitation"]["display_name"] == "Léa B." and d2["share_url"] == url_avant + "?v=1"
             and d2["invitation"]["message"] == "Viens avec moi <b>samedi</b> !", (c, d2))
    verifier("5h. whatsapp_text = message + \\n + share_url",
             d2.get("whatsapp_text") == "Viens avec moi <b>samedi</b> !\n" + url_avant + "?v=1", d2.get("whatsapp_text"))
    c, d3 = await appel(R.referral_pass_invitation_put(dto["id"], H.req_parrain(base, {"message": "Deuxième version"})))
    verifier("5i. deuxième PUT : version 2, token toujours identique, display_name conservé",
             c == 200 and d3["invitation"]["version"] == 2 and d3["share_token"] == tok_avant
             and d3["share_url"].endswith("?v=2") and d3["invitation"]["display_name"] == "Léa B.", d3.get("invitation"))
    verifier("5j. profil principal (subscriptions / users / discount_codes) INCHANGÉ", _instantane_profil(base) == profil_avant)
    doc = base["referral_passes"].docs[0]
    verifier("5k. aucun e-mail du corps écrit sur le pass",
             "pirate" not in json.dumps(doc, default=str) and doc["share_token"] == tok_avant, doc.get("invitation"))

    for mauvais, attendu in ((({"display_name": "lea@exemple.test"}), 422), (({"display_name": "   "}), 422),
                             (({"display_name": "x" * 41}), 422), (({"message": "m" * 281}), 422),
                             (({"photo_url": "http://firebasestorage.googleapis.com/x.jpg"}), 422),
                             (({"photo_url": "https://evil.example/x.jpg"}), 422),
                             (({"photo_url": "javascript:alert(1)"}), 422)):
        c, _ = await appel(R.referral_pass_invitation_put(dto["id"], H.req_parrain(base, mauvais)))
        verifier("5l. invitation invalide refusée -> %d : %s" % (attendu, str(mauvais)[:60]), c == attendu, c)
    c, d4 = await appel(R.referral_pass_invitation_put(dto["id"], H.req_parrain(base, {"photo_url": "/api/files/abc/p.jpg"})))
    verifier("5m. photo_url relative /api/files/… acceptée", c == 200 and d4["invitation"]["photo_url"] == "/api/files/abc/p.jpg", (c, d4))

    # un autre membre
    base["subscriptions"].docs.append({
        "id": "sub-autre", "code": "AUTRE-01", "email": "autre@exemple.test", "name": "Autre Membre",
        "total_sessions": 10, "used_sessions": 0, "remaining_sessions": 10, "status": "active", "coach_id": "",
        "expires_at": "2099-01-01T00:00:00+00:00"})
    base["discount_codes"].docs.append({"id": "code-autre", "code": "AUTRE-01", "name": "Autre Membre",
                                        "assignedEmail": "autre@exemple.test", "active": True, "coach_id": ""})
    tok_autre = H.jeton_espace(base, code="AUTRE-01", email="autre@exemple.test")
    c, _ = await appel(R.referral_pass_invitation_put(dto["id"], H.req_parrain(base, {"display_name": "Pirate"}, tok=tok_autre)))
    verifier("5n. autre membre -> 403/404, rien d'écrit",
             c in (403, 404) and base["referral_passes"].docs[0]["invitation"]["display_name"] == "Léa B.", c)
    c, _ = await appel(R.referral_pass_invitation_put(dto["id"], Requete({"display_name": "X"}, {"X-User-Email": H.PARRAIN_EMAIL})))
    verifier("5o. X-User-Email seul -> 403", c == 403, c)

    # ── 6. POST /pass sur une séance déjà prise ─────────────────────────
    c6, d6 = await H.creer_pass(base, occ)
    verifier("6. POST /pass sur une séance où un pass actif existe -> deja_existant, MÊME token",
             c6 == 200 and d6.get("deja_existant") is True and d6["share_token"] == tok_avant
             and len(base["referral_passes"].docs) == 1, (c6, d6.get("deja_existant")))

    # pass annulé -> 409
    await appel(R.referral_annuler(dto["id"], H.req_parrain(base)))
    c, _ = await appel(R.referral_pass_invitation_put(dto["id"], H.req_parrain(base, {"message": "trop tard"})))
    verifier("5p. pass annulé -> 409", c == 409, c)

    # POST /pass avec invitation à la création
    base2, occ2 = base_v2()
    c, dc = await H.creer_pass(base2, occ2, invitation={"display_name": "Léa", "message": "Hello"})
    verifier("5q. POST /pass + invitation : appliquée à la création (version 1, ?v=1)",
             c == 201 and dc["invitation"]["display_name"] == "Léa" and dc["invitation"]["message"] == "Hello"
             and dc["invitation"]["version"] == 1 and dc["share_url"].endswith("?v=1"), (c, dc.get("invitation")))
    base3, occ3 = base_v2()
    c, _ = await H.creer_pass(base3, occ3, invitation={"display_name": "a@b.c"})
    verifier("5r. POST /pass + invitation invalide -> 422, aucun pass créé",
             c == 422 and not base3["referral_passes"].docs, c)


async def page(tok, methode="GET"):
    r = await S.share_duo_page(tok)
    corps = r.body.decode("utf-8") if hasattr(r, "body") else ""
    return r.status_code, corps, dict(r.headers)


def _og(html, prop):
    import re
    m = re.search(r'<meta property="%s" content="([^"]*)"' % re.escape(prop), html)
    return m.group(1) if m else None


async def partie_page():
    import html as _h
    base, occ = base_v2()
    _, dto = await H.creer_pass(base, occ)
    tok = dto["share_token"]
    c, html_avant, _ = await page(tok)
    verifier("7. ancien pass sans invitation : 200, og:title « Léa t'invite à Afroboost », description V538",
             c == 200 and _og(html_avant, "og:title") == _h.escape("Léa t'invite à Afroboost", quote=True)
             and _og(html_avant, "og:description") == _h.escape(E.og_description_invitation(
                 "Léa", "Afro Cardio", occ, "Essai gratuit")[:200], quote=True)
             and _og(html_avant, "og:image") == "https://afroboost.com/logo512.png", html_avant[:600])

    base["referral_share_settings"].docs.append({"_id": "", "share_image_url": "/api/files/plat01/share_p.png"})
    c, h, _ = await page(tok)
    verifier("7a. image plateforme utilisée à défaut d'image coach (rendue absolue)",
             _og(h, "og:image") == "https://afroboost.com/api/files/plat01/share_p.png", _og(h, "og:image"))
    base["referral_passes"].docs[0]["coach_id"] = COACH_A
    base["referral_share_settings"].docs.append({"_id": COACH_A, "share_image_url": "/api/files/coach01/share_c.jpg"})
    await appel(R.referral_pass_invitation_put(dto["id"], H.req_parrain(
        base, {"display_name": "Léa <script>", "message": 'Viens "danser" <img src=x onerror=alert(1)> & rire'})))
    c, h, _ = await page(tok)
    verifier("7b. invitation : og:title avec display_name ÉCHAPPÉ",
             _og(h, "og:title") == _h.escape("Léa <script> t'invite à Afroboost", quote=True) and "<script>" not in h, _og(h, "og:title"))
    verifier("7c. og:description = message ÉCHAPPÉ",
             _og(h, "og:description") == _h.escape('Viens "danser" <img src=x onerror=alert(1)> & rire', quote=True)
             and "<img src=x" not in h, _og(h, "og:description"))
    verifier("7d. og:image = image du coach du pass, absolue",
             _og(h, "og:image") == "https://afroboost.com/api/files/coach01/share_c.jpg", _og(h, "og:image"))
    # ?v= est une chaîne de requête : la route ne lit que le chemin ; le jeton reste le même.
    c, _, _ = await page(tok)
    verifier("7e. ?v=3 -> 200 (paramètre toléré, jeton identique)", c == 200, c)
    methodes = set()
    for rt in S.api_router.routes:
        if getattr(rt, "path", "") in ("/api/share/duo/{share_token}", "/share/duo/{share_token}"):
            methodes |= set(getattr(rt, "methods", set()) or set())
    verifier("7f. la route d'aperçu accepte GET ET HEAD", {"GET", "HEAD"} <= methodes, methodes)
    c, _, ent = await page("jeton-inexistant")
    verifier("7g. jeton invalide -> 302 accueil", c == 302 and ent.get("location") == "https://afroboost.com", (c, ent))

    # cas « bassicustomshoes »
    base2, occ2 = base_v2()
    _, d = await H.creer_pass(base2, occ2)
    p = base2["referral_passes"].docs[0]
    p["sponsor"]["name"] = "bassicustomshoes"
    p["sponsor"]["email_norm"] = "bassicustomshoes@gmail.com"
    c, h, _ = await page(d["share_token"])
    verifier("7h. sponsor.name == partie locale de l'e-mail : ni adresse ni partie locale dans le HTML",
             c == 200 and "bassicustomshoes" not in h.lower() and "@gmail" not in h
             and _og(h, "og:title") == _h.escape("Un membre Afroboost t'invite", quote=True), _og(h, "og:title"))
    c, pub = await appel(R.referral_pass_public(d["share_token"]))
    verifier("7i. dto_public : sponsor_first_name / sponsor_display_name filtrés, sponsor_photo_url null",
             c == 200 and pub["sponsor_first_name"] == "" and pub["sponsor_display_name"] == ""
             and pub["sponsor_photo_url"] is None and "bassicustomshoes" not in json.dumps(pub).lower(), pub)
    verifier("7j. le whatsapp_text du parrain ne porte plus la partie locale",
             "bassicustomshoes" not in (await R._dto(p))["whatsapp_text"].lower())


def partie_nom():
    na = E.nom_affichable
    verifier("8a. adresse e-mail -> \"\"", na("bassi@gmail.com", "bassi@gmail.com") == "")
    verifier("8b. partie locale de l'e-mail -> \"\" (casse et accents ignorés)",
             na("bassicustomshoes", "bassicustomshoes@gmail.com") == ""
             and na("BassiCustomShoes", "bassicustomshoes@gmail.com") == ""
             and na("élodie.m", "elodie.m@exemple.test") == "")
    verifier("8c. vide / None / espaces -> \"\"", na("", "x@y.z") == "" and na(None, None) == "" and na("   ", "") == "")
    verifier("8d. identifiant technique -> \"\" (sans lettre, ou >= 20 car. sans espace)",
             na("12345678", "") == "" and na("user_8f3a9c2b1d4e5f6a7b8c", "") == "" and na("--__--", "") == "")
    verifier("8e. prénom normal -> premier mot capitalisé proprement",
             na("léa parrain", "lea.parrain@exemple.test") == "Léa" and na("JEAN-PIERRE Dupont", "") == "Jean-Pierre"
             and na("Bassi", "contact.artboost@gmail.com") == "Bassi" and na("Léa Parrain", "") == "Léa",
             [na("léa parrain", ""), na("JEAN-PIERRE Dupont", "")])


def main():
    try:
        asyncio.set_event_loop(asyncio.new_event_loop())
    except Exception:  # noqa: BLE001
        pass
    boucle = asyncio.get_event_loop()
    for partie in (partie_coach, partie_membre, partie_page):
        try:
            boucle.run_until_complete(partie())
        except Exception as err:  # noqa: BLE001  (banc ROUGE : on le dit, on ne plante pas)
            import traceback
            verifier("PARTIE %s exécutée sans exception" % partie.__name__, False,
                     "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-800:]))
    try:
        partie_nom()
    except Exception as err:  # noqa: BLE001
        verifier("PARTIE partie_nom exécutée sans exception", False, "%s: %s" % (type(err).__name__, err))
    ok = sum(1 for _, c, _ in H.RESULTATS if c)
    print("=" * 78)
    print("V551 — PARRAINAGE V2 : %d vérifications" % len(H.RESULTATS))
    print("=" * 78)
    for nom, cond, detail in H.RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:600])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(H.RESULTATS)))
    return 0 if ok == len(H.RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

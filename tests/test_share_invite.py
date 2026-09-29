#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""INV-3 — L'APERÇU PARTAGEABLE D'UNE INVITATION-CAMPAGNE : le banc autonome.

Routes `api/routes/share_invite_routes.py` (page OG, carte 1200×630, aperçu
coach), rendu `referral_carte.rendre_carte_invitation`, moteur de l'AGENT 1
(`referral_campaigns_engine.cible_front` / `dto_public`, importés, jamais
réécrits). Même harnais que `test_referral_carte.py` (MongoDB en mémoire).
AUCUN réseau : le téléchargement est remplacé par un mouchard ; un hôte non
autorisé ne doit JAMAIS l'appeler. Seul disque touché : un dossier temporaire.

Lancement :  python3 tests/test_share_invite.py
"""
import asyncio
import io
import os
import re
import shutil
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

from fastapi import HTTPException  # noqa: E402
from PIL import Image  # noqa: E402

import api.routes.referral_carte as RC  # noqa: E402
import api.routes.referral_campaigns_engine as CE  # noqa: E402
import api.routes.share_invite_routes as SI  # noqa: E402

S, R = H.S, H.R
verifier = H.verifier
FRONT = "https://afroboost.com"
COACH = "coach.inv@exemple.test"
AUTRE = "autre.coach@exemple.test"
TOK = "tokInvA1b2C3d4"
UA_NAV = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit/605.1.15 Safari/604.1"
UA_ROBOT = "WhatsApp/2.23.20.0 A"


def _image(octets):
    try:
        _i = Image.open(io.BytesIO(octets))
        _i.load()
        return _i
    except Exception:  # noqa: BLE001
        return None


def _png(couleur=(40, 160, 200), taille=(900, 700)):
    _b = io.BytesIO()
    Image.new("RGB", taille, couleur).save(_b, "PNG")
    return _b.getvalue()


def _og(html, prop):
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(prop), html)
    return m.group(1) if m else None


def _invitation(**extra):
    d = {"id": "inv-0001", "coach_id": COACH, "type": "trial", "status": "active", "share_token": TOK,
         "version": 3, "title": "Cours découverte", "subtitle": "Viens danser avec nous",
         "message": "Je t'invite !", "cta_label": "Je réserve", "image_url": None, "image_source": "default",
         "course_id": "cours-inv", "occurrence": "2026-10-01T18:30:00", "offer_id": "offre-inv",
         "inviter_display": {"prenom": "Léa", "photo_url": None, "source": "coach"},
         "created_at": "2026-09-29T10:00:00+00:00", "updated_at": "2026-09-29T10:00:00+00:00"}
    d.update(extra)
    return d


def base_inv(*docs):
    base = H._Base()
    base["courses"].docs.append({"id": "cours-inv", "name": "Afro Cardio", "locationName": "Salle Nord, Genève",
                                 "coach_id": COACH})
    base["offers"].docs.append({"id": "offre-inv", "name": "Essai gratuit", "price": 0, "coach_id": COACH})
    base["coaches"].docs += [{"email": COACH, "name": "Coach Inv"}, {"email": AUTRE, "name": "Autre"}]
    base["concept"].docs.append({"id": "concept", "primaryColor": "#D91CD2"})
    base["referral_campaigns"].docs += [dict(d) for d in (docs or (_invitation(),))]
    S.db = base
    R.init_db(base)
    SI.init_db(base)
    S._V552_CACHE.clear()
    return base


def _req(ua=UA_NAV, jeton=None):
    ent = {"user-agent": ua}
    if jeton:
        ent["Authorization"] = "Bearer " + jeton
    return H.Requete(entetes=ent)


async def page(tok, v="", ua=UA_NAV):
    r = await SI.share_invite_page(tok, _req(ua), v)
    return r.status_code, bytes(r.body or b"").decode("utf-8", "replace"), {k.lower(): x for k, x in r.headers.items()}


async def carte(tok, v=""):
    r = await SI.share_invite_carte(tok, v)
    return r.status_code, bytes(r.body or b""), {k.lower(): x for k, x in r.headers.items()}


async def apercu(inv_id, jeton=None):
    try:
        r = await SI.share_invite_preview(inv_id, _req(jeton=jeton))
    except HTTPException as e:
        return e.status_code, b"", {}
    return r.status_code, bytes(r.body or b""), {k.lower(): x for k, x in r.headers.items()}


# ═══════════════════════════════════════════════════════════════════════════
# 1. RENDU PUR
# ═══════════════════════════════════════════════════════════════════════════
def partie_rendu():
    dto = CE.dto_public(_invitation(), cours={"locationName": "Salle Nord"}, offre={"price": 0})
    j = RC.rendre_carte_invitation(RC.donnees_carte_invitation(dto, "#D91CD2"))
    im = _image(j)
    verifier("J1. carte d'invitation : JPEG 1200×630 valide, < 400 Ko",
             im is not None and im.format == "JPEG" and im.size == (1200, 630) and len(j) < 400 * 1024,
             (im and im.size, len(j)))
    jf = RC.rendre_carte_invitation(RC.donnees_carte_invitation(dto, "#D91CD2", fond=_png()))
    imf = _image(jf)
    _px = imf.convert("RGB").getpixel((1150, 300))
    verifier("J2. avec image de fond : 1200×630, l'image se voit à droite (bleu > rouge)",
             imf.size == (1200, 630) and _px[2] > _px[0] + 40, _px)
    verifier("J3. fond/photo corrompus : carte valide quand même",
             _image(RC.rendre_carte_invitation(RC.donnees_carte_invitation(dto, None, b"xx", b"yy"))) is not None)
    # INV-3 (audit P2) : pic mémoire du FOND borné.
    _geant = _png((40, 160, 200), (4000, 3100))            # 12,4 Mpx, quelques Ko compressés
    import PIL.ImageOps as _IO
    _orig_fit, _tailles_fit = _IO.fit, []

    def _fit_espion(img, taille, *a, **k):
        _tailles_fit.append(img.size)
        return _orig_fit(img, taille, *a, **k)

    _IO.fit = _fit_espion
    try:
        _refus = RC._fond_image_invitation(_geant)
        _carte_geant = RC.rendre_carte_invitation({"titre": "T", "fond": _geant})
        _ok = RC._fond_image_invitation(_png((40, 160, 200), (3400, 3400)))   # 11,6 Mpx : accepté
    finally:
        _IO.fit = _orig_fit
    verifier("J7m. fond > 12 Mpx : refusé AVANT décodage -> fond de marque, carte 1200×630 (jamais 500)",
             len(_geant) < RC.PHOTO_MAX_OCTETS and _refus is None and _image(_carte_geant).size == (1200, 630)
             and RC.FOND_MAX_PIXELS == 12_000_000 < RC.PHOTO_MAX_PIXELS and _tailles_fit[:1] != [(4000, 3100)],
             (_refus, len(_geant)))
    verifier("J7n. fond accepté : réduit par thumbnail AVANT fit (entrée de fit <= 2402 px), sortie 1200×630",
             _ok is not None and _ok.size == (1200, 630) and len(_tailles_fit) == 1
             and max(_tailles_fit[0]) <= 2402 and min(_tailles_fit[0][0] / 1200.0, _tailles_fit[0][1] / 630.0) >= 1.0,
             _tailles_fit)
    g = RC.rendre_carte_invitation({})
    verifier("J4. carte vide / None : JPEG 1200×630", _image(g).size == (1200, 630)
             and _image(RC.rendre_carte_invitation(None)).size == (1200, 630))
    lg = RC.rendre_carte_invitation({"titre": "Titre " * 50, "sous_titre": "Sous " * 80, "quand": "x" * 90,
                                     "lieu": "Lieu " * 50, "cta": "Réserve " * 20, "prenom": "Maximilienne " * 5,
                                     "photo": _png(), "fond": _png()})
    verifier("J5. textes très longs : carte valide (ellipse, rien ne déborde)", _image(lg).size == (1200, 630))
    dc = RC.donnees_carte_invitation({"inviter_display": {"prenom": "lea@exemple.test"}, "title": "T",
                                      "date_label": "mercredi 1 octobre", "time_label": "18:30"})
    verifier("J6. donnees_carte_invitation : prénom en forme d'adresse effacé ; date + heure jointes",
             dc["prenom"] == "" and dc["quand"] == "mercredi 1 octobre · 18:30", dc)


# ═══════════════════════════════════════════════════════════════════════════
# 2. ROUTES PUBLIQUES
# ═══════════════════════════════════════════════════════════════════════════
async def partie_routes():
    base = base_inv()
    doc = base["referral_campaigns"].docs[0]

    methodes = {}
    for rt in SI.router.routes:
        methodes.setdefault(getattr(rt, "path", ""), set()).update(getattr(rt, "methods", set()) or set())
    verifier("R1. routes montées : page et carte en GET+HEAD, aperçu en GET",
             {"GET", "HEAD"} <= methodes.get("/api/share/invite/{token}", set())
             and {"GET", "HEAD"} <= methodes.get("/api/share/invite/{token}/carte.jpg", set())
             and "GET" in methodes.get("/api/share/invite-preview/{invite_id}.jpg", set()), methodes)

    # J : l'image
    c, corps, ent = await carte(TOK, "3")
    im = _image(corps)
    verifier("J7. GET carte : 200 image/jpeg, Pillow l'ouvre, 1200×630 exact",
             c == 200 and ent.get("content-type", "").startswith("image/jpeg") and im is not None
             and im.size == (1200, 630), (c, ent.get("content-type"), im and im.size))
    verifier("J8. bonne version dans ?v -> cache public 7 j ; sans ?v -> cache court",
             "max-age=604800" in ent.get("cache-control", "") and "public" in ent.get("cache-control", ""),
             ent.get("cache-control"))
    c2, _, ent2 = await carte(TOK)
    verifier("J8b. ancien lien sans ?v : 200, max-age=300", c2 == 200 and "max-age=300" in ent2.get("cache-control", ""))

    compteur = []
    _orig_rendre = RC.rendre_carte_invitation

    def rendre_compte(d=None):
        compteur.append(1)
        return _orig_rendre(d)

    RC.rendre_carte_invitation = rendre_compte
    try:
        c3, corps3, _ = await carte(TOK, "3")
    finally:
        RC.rendre_carte_invitation = _orig_rendre
    verifier("J9. cache (jeton, empreinte, couleur) : aucun nouveau rendu, mêmes octets",
             c3 == 200 and compteur == [] and corps3 == corps, (c3, len(compteur)))

    # OG
    c, h, ent = await page(TOK, "3", UA_ROBOT)
    _img = _og(h, "og:image")
    _attendu = "%s/api/share/invite/%s/carte.jpg?v=3" % (FRONT, TOK)
    verifier("O1. page OG : 200 text/html, og:image = URL ABSOLUE https avec ?v=3",
             c == 200 and "text/html" in ent.get("content-type", "") and _img == _attendu, (c, _img))
    verifier("O2. og:image == card_url du DTO coach (AGENT 1) : une seule adresse",
             _img == CE.dto_coach(doc, base_url=FRONT)["card_url"], CE.dto_coach(doc, base_url=FRONT)["card_url"])
    verifier("O3. og:image:secure_url/type/width/height/alt + twitter:card summary_large_image",
             _og(h, "og:image:secure_url") == _attendu and _og(h, "og:image:type") == "image/jpeg"
             and _og(h, "og:image:width") == "1200" and _og(h, "og:image:height") == "630"
             and bool(_og(h, "og:image:alt")) and _og(h, "twitter:card") == "summary_large_image"
             and _og(h, "twitter:image") == _attendu)
    verifier("O4. og:url = adresse exacte partagée (?v nettoyé) ; og:title/description présents",
             _og(h, "og:url") == "%s/api/share/invite/%s?v=3" % (FRONT, TOK)
             and "Cours découverte" in (_og(h, "og:title") or "") and bool(_og(h, "og:description")),
             (_og(h, "og:url"), _og(h, "og:title")))
    verifier("O5. robot : aucune redirection (pas de meta refresh), aucun <script>",
             'http-equiv="refresh"' not in h and "<script" not in h.lower())
    c, hn, _ = await page(TOK, "", UA_NAV)
    _cible = FRONT + CE.cible_front(doc)
    verifier("O6. navigateur : meta refresh + lien vers FRONT + cible_front(doc)",
             'content="0;url=%s"' % _cible.replace("&", "&amp;") in hn
             and 'href="%s"' % _cible.replace("&", "&amp;") in hn, _cible)
    # INV-2 : l'invitation « Essai » porte une séance -> l'humain est renvoyé
    # vers le formulaire AVEC cette séance (cours + AAAA-MM-JJTHH:MM).
    verifier("O6b. navigateur : la séance voyage (&course=cours-inv&occurrence=2026-10-01T18%3A30)",
             _cible == FRONT + "/?offre=offre-inv&reserver=1&course=cours-inv&occurrence=2026-10-01T18%3A30"
             and 'href="%s"' % _cible.replace("&", "&amp;") in hn, _cible)
    c, hv, _ = await page(TOK, "12\"><script>", UA_ROBOT)
    verifier("O7. ?v= hostile : ignoré (og:url sans v), og:image garde la version courante",
             _og(hv, "og:url") == "%s/api/share/invite/%s" % (FRONT, TOK) and _og(hv, "og:image") == _attendu
             and "<script" not in hv.lower())

    # PII
    verifier("P1. aucune PII dans la page : ni e-mail du coach, ni coach_id, ni « @ »",
             COACH not in h and COACH not in hn and "coach_id" not in h and "@" not in h and "@" not in hn)

    # K : changement de version
    doc["version"] = 4
    doc["title"] = "Soirée spéciale"
    c, hk, _ = await page(TOK, "3", UA_ROBOT)
    verifier("K1. version 4 : og:image porte ?v=4, jeton inchangé",
             _og(hk, "og:image") == "%s/api/share/invite/%s/carte.jpg?v=4" % (FRONT, TOK)
             and doc["share_token"] == TOK, _og(hk, "og:image"))
    ck, corpsk, entk = await carte(TOK, "4")
    verifier("K2. carte v4 : redessinée (octets différents de la v3), cache long pour ?v=4",
             ck == 200 and corpsk != corps and "max-age=604800" in entk.get("cache-control", ""))
    c, _, entv = await carte(TOK, "3")
    verifier("K3. ancien ?v=3 après changement : 200 (carte courante), cache court",
             c == 200 and "max-age=300" in entv.get("cache-control", ""))

    # XSS
    doc["title"] = 'Soirée <script>alert("x")</script> "guillemets" & \'apos\''
    doc["subtitle"] = '<img src=x onerror=alert(1)>'
    c, hx, _ = await page(TOK, "", UA_NAV)
    verifier("X1. titre avec <script> et guillemets : échappé dans le HTML (aucune balise injectée)",
             c == 200 and "<script" not in hx.lower() and "&lt;script&gt;" in hx and "&quot;guillemets&quot;" in hx
             and "<img src=x" not in hx and "&lt;img src=x" in hx, hx[:600])
    cx, corpsx, _ = await carte(TOK)
    verifier("X2. la carte d'un titre hostile reste une image valide", cx == 200 and _image(corpsx) is not None)

    # Statuts non publics
    corps_404 = None
    for statut in ("draft", "archived"):
        doc["status"] = statut
        cp, hp, _ = await page(TOK, "", UA_ROBOT)
        cc, bc, _ = await carte(TOK)
        verifier("S-%s. invitation %s : 404 page ET carte, corps neutre" % (statut, statut),
                 cp == 404 and cc == 404 and "Cours" not in hp and "Soir" not in hp and bc == b"Not Found",
                 (cp, cc, hp[:80]))
        corps_404 = hp
    doc["status"] = "active"
    cu, hu, _ = await page("jeton-inconnu")
    cb, _, _ = await carte("x" * 300)
    verifier("S-inconnu. jeton inconnu / absurde : 404, même corps que brouillon (aucun oracle)",
             cu == 404 and hu == corps_404 and cb == 404)


# ═══════════════════════════════════════════════════════════════════════════
# 3. IMAGES : priorités, anti-SSRF, jamais 500
# ═══════════════════════════════════════════════════════════════════════════
async def partie_images():
    appels = []
    _orig_tel = RC.telecharger_https

    async def mouchard(url, *a, **k):
        appels.append(url)
        return _png((40, 160, 200))

    RC.telecharger_https = mouchard
    try:
        base = base_inv(_invitation(image_url="https://evil.example/fond.jpg", image_source="upload",
                                    inviter_display={"prenom": "Léa", "photo_url": "http://169.254.169.254/x.jpg",
                                                     "source": "coach"}))
        c, corps, _ = await carte(TOK, "3")
        verifier("H1. hôtes NON autorisés (fond + photo) : AUCUNE requête réseau, carte 200 quand même",
                 appels == [] and c == 200 and _image(corps) is not None, appels)

        base = base_inv(_invitation(image_url="https://res.cloudinary.com/dtm0r7hwq/image/upload/i.jpg",
                                    image_source="upload"))
        c, corps, _ = await carte(TOK, "3")
        _px = _image(corps).convert("RGB").getpixel((1150, 300))
        verifier("H2. fond Cloudinary (hôte admis) : téléchargé une fois, visible sur la carte",
                 appels == ["https://res.cloudinary.com/dtm0r7hwq/image/upload/i.jpg"] and _px[2] > _px[0] + 40,
                 (appels, _px))

        # Fond par défaut : l'image de partage du coach (V551, `_reglages_effectifs`), lue SANS HTTP.
        appels.clear()
        base = base_inv(_invitation())
        base["referral_share_settings"].docs.append({"_id": COACH, "share_image_url": "/api/files/fidpartage/s.png"})
        # (le faux Mongo sérialise les octets en texte : la lecture locale est un mouchard)
        lus = []
        _orig_local = S._v552_lire_fichier_local

        async def lecture_locale(fid, nom, *a, **k):
            lus.append((fid, nom))
            return _png((30, 200, 60))

        S._v552_lire_fichier_local = lecture_locale
        try:
            c, corps, _ = await carte(TOK, "3")
        finally:
            S._v552_lire_fichier_local = _orig_local
        _px = _image(corps).convert("RGB").getpixel((1150, 300))
        verifier("H3. sans image d'invitation : l'image de partage du coach (lue en local, 0 requête)",
                 c == 200 and appels == [] and lus == [("fidpartage", "s.png")]
                 and _px[1] > _px[0] + 40 and _px[1] > _px[2], (lus, _px))

        # Jamais 500 : le rendu personnalisé plante -> carte de marque, cache court.
        base = base_inv()
        _orig = RC.rendre_carte_invitation

        def plante_perso(d=None):
            if d and (d.get("titre") or d.get("prenom")):
                raise RuntimeError("boum")
            return _orig(d)

        RC.rendre_carte_invitation = plante_perso
        try:
            c, corps, ent = await carte(TOK, "3")
        finally:
            RC.rendre_carte_invitation = _orig
        verifier("H4. rendu personnalisé en échec : 200 carte de marque valide, cache <= 300 s",
                 c == 200 and _image(corps) is not None and "max-age=300" in ent.get("cache-control", ""),
                 (c, ent.get("cache-control")))

        def plante_tout(d=None):
            raise RuntimeError("boum")

        RC.rendre_carte_invitation = plante_tout
        try:
            c, corps, ent = await carte(TOK, "3")
        finally:
            RC.rendre_carte_invitation = _orig
        verifier("H5. tout rendu en échec : 200 image de repli (logo ou JPEG embarqué), jamais 500",
                 c == 200 and len(corps) > 0 and _image(corps) is not None, (c, ent.get("content-type")))
    finally:
        RC.telecharger_https = _orig_tel


# ═══════════════════════════════════════════════════════════════════════════
# 4. APERÇU COACH (brouillon)
# ═══════════════════════════════════════════════════════════════════════════
async def partie_apercu():
    base_inv(_invitation(status="draft"), _invitation(id="inv-autre", coach_id=AUTRE, share_token="tokAutre9",
                                                      status="draft"))
    c, _, _ = await apercu("inv-0001")
    verifier("A1. aperçu sans jeton : 401", c == 401, c)
    c, _, _ = await apercu("inv-0001", jeton=H.jeton_admin("inconnu@exemple.test"))
    verifier("A2. aperçu avec jeton d'un non-coach : 403", c == 403, c)
    c, _, _ = await apercu("inv-autre", jeton=H.jeton_admin(COACH))
    verifier("A3. aperçu de l'invitation d'un AUTRE coach : 404", c == 404, c)
    c, corps, ent = await apercu("inv-0001", jeton=H.jeton_admin(COACH))
    im = _image(corps)
    verifier("A4. aperçu de SA propre invitation en brouillon : 200 JPEG 1200×630, private no-store",
             c == 200 and im is not None and im.size == (1200, 630)
             and "no-store" in ent.get("cache-control", "") and "private" in ent.get("cache-control", ""),
             (c, ent.get("cache-control")))
    c, _, _ = await apercu("inexistante", jeton=H.jeton_admin(COACH))
    verifier("A5. aperçu d'un id inconnu : 404", c == 404, c)
    cp, _, _ = await page(TOK)
    verifier("A6. la même invitation en brouillon reste 404 en public", cp == 404, cp)


# ═══════════════════════════════════════════════════════════════════════════
# 5. MONTAGE : une vraie appli, routes AVANT un catch-all SPA
# ═══════════════════════════════════════════════════════════════════════════
def partie_montage():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    base_inv()
    app = FastAPI()
    app.include_router(SI.router)

    @app.get("/{full_path:path}")
    async def _serve_spa(full_path: str):  # noqa: ARG001  (imite le catch-all de server.py)
        from starlette.responses import HTMLResponse
        return HTMLResponse("<html>SPA</html>")

    with TestClient(app) as cli:
        r = cli.get("/api/share/invite/%s?v=3" % TOK, headers={"user-agent": UA_ROBOT})
        rc = cli.get("/api/share/invite/%s/carte.jpg?v=3" % TOK)
        rh = cli.head("/api/share/invite/%s/carte.jpg" % TOK)
        ra = cli.get("/api/share/invite-preview/inv-0001.jpg")
        rb = cli.get("/api/share/invite-preview/inv-0001.jpg",
                     headers={"Authorization": "Bearer " + H.jeton_admin(COACH)})
    verifier("M1. montée avant le catch-all : page OG servie (pas la SPA), carte image/jpeg, HEAD 200",
             r.status_code == 200 and "og:image" in r.text and "SPA" not in r.text
             and rc.status_code == 200 and rc.headers.get("content-type", "").startswith("image/jpeg")
             and rh.status_code == 200, (r.status_code, rc.status_code, rh.status_code))
    verifier("M2. chemin `{invite_id}.jpg` : 401 sans jeton, 200 image avec le jeton du propriétaire",
             ra.status_code == 401 and rb.status_code == 200
             and rb.headers.get("content-type", "").startswith("image/jpeg"), (ra.status_code, rb.status_code))


def main():
    _tmp = tempfile.mkdtemp(prefix="banc_inv3_")
    _orig = S._V413_MEDIA_DIR
    S._V413_MEDIA_DIR = _tmp
    try:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:  # noqa: BLE001
            pass
        boucle = asyncio.get_event_loop()
        for partie in (partie_rendu, partie_routes, partie_images, partie_apercu, partie_montage):
            try:
                _r = partie()
                if asyncio.iscoroutine(_r):
                    boucle.run_until_complete(_r)
            except Exception as err:  # noqa: BLE001  (banc ROUGE : on le dit, on ne plante pas)
                import traceback
                verifier("PARTIE %s exécutée sans exception" % partie.__name__, False,
                         "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-1200:]))
    finally:
        S._V413_MEDIA_DIR = _orig
        shutil.rmtree(_tmp, ignore_errors=True)
    ok = sum(1 for _, c, _ in H.RESULTATS if c)
    print("=" * 78)
    print("INV-3 — APERÇU D'INVITATION : %d vérifications" % len(H.RESULTATS))
    print("=" * 78)
    for nom, cond, detail in H.RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:900])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(H.RESULTATS)))
    return 0 if ok == len(H.RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

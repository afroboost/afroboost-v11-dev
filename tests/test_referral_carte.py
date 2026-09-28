#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V552 — LA CARTE SOCIALE D'INVITATION (Parrainage V2) : le banc autonome.

Rendu Pillow pur (`referral_carte.py`), version de carte (`referral_engine`),
route publique GET/HEAD `/api/share/duo/<token>/carte.jpg`, balises OG de la
page d'aperçu, `card_url` des DTO. Même harnais que `test_referral_pass_duo.py`
(MongoDB en mémoire, VRAIES routes). AUCUN réseau : le téléchargement de photo
est remplacé par un mouchard, et on vérifie qu'un hôte non autorisé ne
l'appelle JAMAIS. Le seul disque touché est un dossier temporaire (cache).

Lancement :  python3 tests/test_referral_carte.py
"""
import asyncio
import io
import os
import shutil
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

from PIL import Image  # noqa: E402

import api.routes.referral_carte as RC  # noqa: E402

S, R, E = H.S, H.R, H.E
verifier, appel = H.verifier, H.appel
FRONT = "https://afroboost.com"


def _image(octets):
    try:
        _i = Image.open(io.BytesIO(octets))
        _i.load()
        return _i
    except Exception:  # noqa: BLE001
        return None


def _photo_png(couleur=(200, 120, 40), taille=(400, 300)):
    _b = io.BytesIO()
    Image.new("RGB", taille, couleur).save(_b, "PNG")
    return _b.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 1. RENDU PUR
# ═══════════════════════════════════════════════════════════════════════════
def partie_rendu():
    _d = {"nom": "Léa", "cours": "Afro Cardio", "offre": "Essai gratuit",
          "occurrence": "2026-09-30T18:45:00", "lieu": "Salle du Rhône, Genève", "couleur": "#D91CD2"}
    j = RC.rendre_carte(_d)
    im = _image(j)
    verifier("C1. carte JPEG 1200×630 valide, < 400 Ko",
             im is not None and im.format == "JPEG" and im.size == (1200, 630) and len(j) < 400 * 1024,
             (im and im.format, im and im.size, len(j)))
    jp = RC.rendre_carte(dict(_d, photo=_photo_png()))
    imp = _image(jp)
    verifier("C2. avec photo : JPEG 1200×630 valide, différent de la carte sans photo",
             imp is not None and imp.size == (1200, 630) and jp != j and len(jp) < 400 * 1024, len(jp))
    # la photo est bien posée : le pixel au centre du disque est la couleur de la photo
    _px = imp.convert("RGB").getpixel((80 + 8 + 118, 190 + 8 + 118))
    verifier("C2b. la photo ronde est dessinée à gauche (couleur de la photo au centre du disque)",
             abs(_px[0] - 200) < 30 and abs(_px[1] - 120) < 30 and abs(_px[2] - 40) < 30, _px)
    jc = RC.rendre_carte(dict(_d, photo=b"pas une image"))
    verifier("C3. photo corrompue : carte valide quand même (sans photo)",
             _image(jc) is not None and _image(jc).size == (1200, 630))
    g = RC.rendre_carte({})
    gn = RC.rendre_carte(None)
    verifier("C4. carte générique (aucune donnée / None) : JPEG 1200×630 valide",
             _image(g) is not None and _image(g).size == (1200, 630) and _image(gn) is not None)
    long_ = RC.rendre_carte({"nom": "Maximilienne-Alexandrine " * 3, "cours": "Cours " * 60,
                             "offre": "Offre " * 60, "lieu": "Lieu " * 80, "occurrence": "2026-09-30T18:45:00"})
    verifier("C5. textes très longs : carte valide (retour à la ligne + ellipse, rien ne déborde)",
             _image(long_) is not None and _image(long_).size == (1200, 630))
    verifier("C6. titre : prénom, sinon formule neutre ; jamais une adresse",
             RC.titre_carte("Léa") == "Léa t'invite à découvrir Afroboost"
             and RC.titre_carte("") == "Un membre Afroboost t'invite à découvrir Afroboost"
             and RC.titre_carte("lea@exemple.test") == "Un membre Afroboost t'invite à découvrir Afroboost")
    verifier("C7. date FR courte « Mercredi 30 sept. · 18:45 » ; illisible -> \"\"",
             RC.date_courte("2026-09-30T18:45:00") == "Mercredi 30 sept. · 18:45"
             and RC.date_courte("n'importe quoi") == "" and RC.date_courte(None) == "",
             RC.date_courte("2026-09-30T18:45:00"))
    verifier("C8. emoji et caractères de contrôle retirés du texte dessiné",
             RC._nettoyer("Léa \U0001F525‍\x07 !") == "Léa !", RC._nettoyer("Léa \U0001F525‍\x07 !"))
    verifier("C9. couleur : #RRGGBB / #RGB lues, invalide -> #D91CD2",
             RC.couleur_valide("#00ff00") == (0, 255, 0) and RC.couleur_valide("#0f0") == (0, 255, 0)
             and RC.couleur_valide("rouge") == (217, 28, 210) and RC.couleur_valide(None) == (217, 28, 210))
    # e-mail : donnees_carte passe par le filtre V551
    _p = {"sponsor": {"name": "bassicustomshoes", "email_norm": "bassicustomshoes@gmail.com"},
          "course_snapshot": {"name": "Afro", "locationName": "Genève"}, "occurrence": "2026-09-30T18:45:00",
          "offer_snapshot": {"id": "o1", "name": "Essai"}}
    _dc = RC.donnees_carte(_p)
    verifier("C10. donnees_carte : nom filtré (ni adresse ni partie locale)",
             _dc["nom"] == "" and "bassicustomshoes" not in repr(_dc).lower() and _dc["cours"] == "Afro"
             and _dc["offre"] == "Essai" and _dc["lieu"] == "Genève", _dc)
    _p2 = dict(_p, invitation={"display_name": "Bassi"})
    verifier("C10b. donnees_carte : display_name de l'invitation prioritaire",
             RC.donnees_carte(_p2)["nom"] == "Bassi")
    verifier("C11. police embarquée (DejaVu) présente avec sa licence, < 2 Mo",
             os.path.isfile(RC._POLICE_GRAS) and os.path.isfile(RC._POLICE_NORMALE)
             and os.path.isfile(os.path.join(RC._DOSSIER_POLICES, "LICENSE"))
             and os.path.getsize(RC._POLICE_GRAS) + os.path.getsize(RC._POLICE_NORMALE) < 2 * 1024 * 1024)
    verifier("C12. JPEG de secours embarqué valide", _image(RC.JPEG_SECOURS) is not None)


# ═══════════════════════════════════════════════════════════════════════════
# 2. SOURCE DE LA PHOTO (anti-SSRF)
# ═══════════════════════════════════════════════════════════════════════════
async def partie_photo():
    sp = RC.source_photo
    verifier("P1. nos fichiers (/api/files, https://afroboost.com/api/files) -> lus localement",
             sp("/api/files/abc123/p.jpg") == ("local", "abc123", "p.jpg")
             and sp("https://afroboost.com/api/files/abc123/p.jpg") == ("local", "abc123", "p.jpg"))
    verifier("P2. hôtes V551 autorisés -> distant",
             sp("https://firebasestorage.googleapis.com/v0/b/x/o/p.jpg")[0] == "distant"
             and sp("https://storage.googleapis.com/b/p.jpg")[0] == "distant"
             and sp("https://lh3.googleusercontent.com/a/xyz")[0] == "distant")
    verifier("P3. tout le reste refusé (autre hôte, http, port, identifiants, IP, afroboost hors /api/files)",
             all(sp(u) is None for u in ("https://evil.example/p.jpg", "http://storage.googleapis.com/p.jpg",
                                         "https://storage.googleapis.com:8443/p.jpg",
                                         "https://user:pw@storage.googleapis.com/p.jpg",
                                         "https://169.254.169.254/latest", "https://afroboost.com/admin",
                                         "https://storage.googleapis.com.evil.example/p.jpg",
                                         "/api/files/../etc/passwd", "", None, "ftp://x")))
    appels = []

    async def mouchard(url):
        appels.append(url)
        return _photo_png()

    async def local(fid, nom):
        appels.append(("local", fid, nom))
        return _photo_png()

    r = await RC.recuperer_photo("https://evil.example/p.jpg", local, mouchard)
    verifier("P4. hôte non autorisé : AUCUNE requête (ni réseau ni locale), pas de photo",
             r is None and appels == [], appels)
    r = await RC.recuperer_photo("https://storage.googleapis.com/b/p.jpg", local, mouchard)
    verifier("P5. hôte autorisé : une seule requête, octets rendus",
             r and appels == ["https://storage.googleapis.com/b/p.jpg"], appels)

    async def trop_gros(url):
        return b"x" * (RC.PHOTO_MAX_OCTETS + 1)

    verifier("P6. photo > 5 Mo -> ignorée",
             await RC.recuperer_photo("https://storage.googleapis.com/b/p.jpg", local, trop_gros) is None)

    async def plante(url):
        raise TimeoutError("lent")

    verifier("P7. délai dépassé / exception -> pas de photo (pas d'exception)",
             await RC.recuperer_photo("https://storage.googleapis.com/b/p.jpg", local, plante) is None)
    import inspect
    _src = inspect.getsource(RC.telecharger_https)
    verifier("P8. le téléchargement ne suit AUCUNE redirection, délai <= 3 s, 5 Mo",
             "follow_redirects=False" in _src and RC.PHOTO_TIMEOUT_S <= 3 and RC.PHOTO_MAX_OCTETS == 5 * 1024 * 1024)


# ═══════════════════════════════════════════════════════════════════════════
# 3. VERSION + DTO
# ═══════════════════════════════════════════════════════════════════════════
async def partie_version():
    base, occ = H.base_de_depart()
    c, dto = await H.creer_pass(base, occ)
    p = base["referral_passes"].docs[0]
    tok = p["share_token"]
    v0 = E.version_carte(p)
    verifier("V1. version de carte : 12 hexa, stable (deux calculs identiques)",
             len(v0) == 12 and all(ch in "0123456789abcdef" for ch in v0) and E.version_carte(dict(p)) == v0, v0)
    verifier("V2. card_url dans le PassDTO = URL absolue https de la carte avec ?v",
             dto.get("card_url") == "%s/api/share/duo/%s/carte.jpg?v=%s" % (FRONT, tok, v0), dto.get("card_url"))
    verifier("V2b. pas de card_url pour un pass sans share_token",
             "card_url" not in E.dto_pass(dict(p, share_token=None), "waiting", [], FRONT)
             and E.url_carte(FRONT, {}) == "")
    await appel(R.referral_pass_invitation_put(p["id"], H.req_parrain(base, {"message": "Viens danser"})))
    v1 = E.version_carte(p)
    verifier("V3. le message change -> la version change, le jeton non",
             v1 != v0 and p["share_token"] == tok, (v0, v1))
    v_occ = E.version_carte(dict(p, occurrence="2030-01-01T10:00:00"))
    v_off = E.version_carte(dict(p, offer_id="autre", offer_snapshot={"id": "autre", "name": "Autre"}))
    v_nom = E.version_carte(dict(p, invitation=dict(p["invitation"], display_name="Zoé")))
    v_pho = E.version_carte(dict(p, invitation=dict(p["invitation"], photo_url="/api/files/a/b.jpg")))
    verifier("V4. occurrence / offre / nom / photo changent la version",
             len({v1, v_occ, v_off, v_nom, v_pho}) == 5, (v1, v_occ, v_off, v_nom, v_pho))
    c, inv = await appel(R.referral_invitation_get(H.req_parrain(base, params={"pass_id": p["id"]})))
    _pass = (inv or {}).get("pass") or {}
    verifier("V5. GET /api/referral/invitation : pass.card_url = même URL versionnée",
             c == 200 and _pass.get("card_url") == E.url_carte(FRONT, p), (c, _pass.get("card_url")))


# ═══════════════════════════════════════════════════════════════════════════
# 4. ROUTE CARTE + OG
# ═══════════════════════════════════════════════════════════════════════════
async def carte(tok, v=""):
    r = await S.share_duo_carte(tok, v)
    corps = bytes(getattr(r, "body", b"") or b"")
    return r.status_code, corps, {k.lower(): v for k, v in dict(r.headers).items()}


def _og(html, prop):
    import re
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(prop), html)
    return m.group(1) if m else None


async def partie_route():
    base, occ = H.base_de_depart()
    _, dto = await H.creer_pass(base, occ)
    p = base["referral_passes"].docs[0]
    tok = p["share_token"]
    RC_rendre = RC.rendre_carte

    methodes = set()
    for rt in S.api_router.routes:
        if getattr(rt, "path", "") in ("/api/share/duo/{share_token}/carte.jpg", "/share/duo/{share_token}/carte.jpg"):
            methodes |= set(getattr(rt, "methods", set()) or set())
    verifier("R1. la route carte accepte GET ET HEAD", {"GET", "HEAD"} <= methodes, methodes)

    c, corps, ent = await carte(tok, E.version_carte(p))
    im = _image(corps)
    verifier("R2. GET carte : 200 image/jpeg 1200×630, Cache-Control public",
             c == 200 and ent.get("content-type", "").startswith("image/jpeg") and im is not None
             and im.size == (1200, 630) and "public" in ent.get("cache-control", "")
             and "max-age=" in ent.get("cache-control", ""), (c, ent))
    c2, _, _ = await carte(tok)
    verifier("R2b. ancien lien sans ?v : 200 quand même", c2 == 200, c2)

    # cache : un deuxième appel ne redessine pas
    compteur = []

    def rendre_compte(d=None):
        compteur.append(1)
        return RC_rendre(d)

    RC.rendre_carte = rendre_compte
    try:
        c3, corps3, _ = await carte(tok, E.version_carte(p))
    finally:
        RC.rendre_carte = RC_rendre
    verifier("R3. cache (jeton, version) : réutilisé, aucun nouveau rendu, mêmes octets",
             c3 == 200 and compteur == [] and corps3 == corps, (c3, len(compteur)))

    c, corps, ent = await carte("jeton-inexistant")
    verifier("R4. jeton inconnu -> 404 sans fuite (aucune donnée, pas d'image personnalisée)",
             c == 404 and b"Afro Cardio" not in corps and b"@" not in corps, (c, corps[:80]))
    c, corps, ent = await carte("x" * 300)
    verifier("R4b. jeton absurde -> 404", c == 404, c)

    # exception de rendu personnalisé -> carte générique
    def plante_perso(d=None):
        if d:
            raise RuntimeError("boum")
        return RC_rendre(d)

    await appel(R.referral_pass_invitation_put(p["id"], H.req_parrain(base, {"message": "nouvelle version"})))
    RC.rendre_carte = plante_perso
    try:
        c, corps, ent = await carte(tok, E.version_carte(p))
    finally:
        RC.rendre_carte = RC_rendre
    verifier("R5. rendu personnalisé en échec -> 200 image valide (carte générique), cache court",
             c == 200 and _image(corps) is not None and ent.get("content-type", "").startswith("image/")
             and "max-age=300" in ent.get("cache-control", ""), (c, ent))

    def plante_tout(d=None):
        raise RuntimeError("Pillow cassé")

    await appel(R.referral_pass_invitation_put(p["id"], H.req_parrain(base, {"message": "encore une"})))
    RC.rendre_carte = plante_tout
    try:
        c, corps, ent = await carte(tok, E.version_carte(p))
    finally:
        RC.rendre_carte = RC_rendre
    verifier("R6. tout rendu en échec -> 200 image valide quand même (image coach/logo/secours), jamais vide",
             c == 200 and len(corps) > 0 and _image(corps) is not None
             and ent.get("content-type", "").startswith("image/"), (c, ent, len(corps)))
    verifier("R6b. aucune route carte ne renvoie 500 : la page aperçu non plus n'est pas affectée",
             (await S.share_duo_page(tok)).status_code == 200)

    # photo : hôte non autorisé -> aucune requête réseau
    appels = []
    _orig_tel = RC.telecharger_https

    async def mouchard(url, *a, **k):
        appels.append(url)
        return _photo_png()

    RC.telecharger_https = mouchard
    try:
        p["invitation"] = dict(p.get("invitation") or {}, photo_url="https://evil.example/p.jpg")
        c, corps, _ = await carte(tok, E.version_carte(p))
        verifier("R7. photo sur un hôte NON autorisé : aucune requête réseau, carte rendue sans photo",
                 c == 200 and appels == [] and _image(corps) is not None, appels)
        p["invitation"]["photo_url"] = "https://firebasestorage.googleapis.com/v0/b/x/o/p.jpg"
        c, corps, _ = await carte(tok, E.version_carte(p))
        verifier("R8. photo sur un hôte autorisé : une requête, carte avec photo",
                 c == 200 and appels == ["https://firebasestorage.googleapis.com/v0/b/x/o/p.jpg"]
                 and _image(corps) is not None, appels)
        # photo locale (/api/files) : lue depuis la base, sans HTTP
        appels.clear()
        # stockage disque V413 (le faux MongoDB du banc ne sait pas garder du binaire)
        os.makedirs(os.path.join(S._V413_MEDIA_DIR, "phot01"), exist_ok=True)
        with open(os.path.join(S._V413_MEDIA_DIR, "phot01", "moi.png"), "wb") as _f:
            _f.write(_photo_png((10, 200, 30)))
        base["uploaded_files"].docs.append({"file_id": "phot01", "filename": "moi.png", "content_type": "image/png",
                                            "storage": "disk"})
        p["invitation"]["photo_url"] = "/api/files/phot01/moi.png"
        c, corps, _ = await carte(tok, E.version_carte(p))
        _px = _image(corps).convert("RGB").getpixel((80 + 8 + 118, 190 + 8 + 118))
        verifier("R9. photo locale /api/files : lue sans HTTP et dessinée",
                 c == 200 and appels == [] and _px[1] > 150 and _px[0] < 80, (appels, _px))
    finally:
        RC.telecharger_https = _orig_tel

    # OG de la page d'aperçu
    r = await S.share_duo_page(tok)
    h = r.body.decode("utf-8")
    _url = E.url_carte(FRONT, p)
    verifier("R10. og:image = URL ABSOLUE https de la carte avec ?v (priorité 1)",
             _og(h, "og:image") == _url and _url.startswith("https://") and "?v=" in _url, _og(h, "og:image"))
    verifier("R11. og:image:secure_url / type / width / height / alt présents",
             _og(h, "og:image:secure_url") == _url and _og(h, "og:image:type") == "image/jpeg"
             and _og(h, "og:image:width") == "1200" and _og(h, "og:image:height") == "630"
             and bool(_og(h, "og:image:alt")), [_og(h, k) for k in ("og:image:secure_url", "og:image:type",
                                                                     "og:image:width", "og:image:height")])
    verifier("R12. twitter:image = la carte, og:url et og:type conservés",
             _og(h, "twitter:image") == _url and _og(h, "og:url") == "%s/api/share/duo/%s" % (FRONT, tok)
             and _og(h, "og:type") == "website", (_og(h, "twitter:image"), _og(h, "og:url")))
    verifier("R13. la balise OG est servie avant le JS (meta refresh, aucune balise <script>)",
             "<script" not in h.lower() and h.index('property="og:image"') < h.index('http-equiv="refresh"'))


def main():
    _tmp = tempfile.mkdtemp(prefix="banc_v552_")
    _orig = S._V413_MEDIA_DIR
    S._V413_MEDIA_DIR = _tmp
    try:
        try:
            asyncio.set_event_loop(asyncio.new_event_loop())
        except Exception:  # noqa: BLE001
            pass
        boucle = asyncio.get_event_loop()
        try:
            partie_rendu()
        except Exception as err:  # noqa: BLE001
            import traceback
            verifier("PARTIE partie_rendu exécutée sans exception", False,
                     "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-800:]))
        for partie in (partie_photo, partie_version, partie_route):
            try:
                boucle.run_until_complete(partie())
            except Exception as err:  # noqa: BLE001  (banc ROUGE : on le dit, on ne plante pas)
                import traceback
                verifier("PARTIE %s exécutée sans exception" % partie.__name__, False,
                         "%s: %s\n%s" % (type(err).__name__, err, traceback.format_exc()[-800:]))
    finally:
        S._V413_MEDIA_DIR = _orig
        shutil.rmtree(_tmp, ignore_errors=True)
    ok = sum(1 for _, c, _ in H.RESULTATS if c)
    print("=" * 78)
    print("V552 — CARTE SOCIALE : %d vérifications" % len(H.RESULTATS))
    print("=" * 78)
    for nom, cond, detail in H.RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                               ("" if cond or not detail else "\n         -> " + str(detail)[:600])))
    print("-" * 78)
    print("%d / %d verifications au vert" % (ok, len(H.RESULTATS)))
    return 0 if ok == len(H.RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

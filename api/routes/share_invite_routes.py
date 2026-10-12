# -*- coding: utf-8 -*-
"""INV-3 — L'APERÇU PARTAGEABLE D'UNE INVITATION-CAMPAGNE (`referral_campaigns`).

Trois routes, calquées sur le contrat du Pass Duo (`/api/share/duo/...`,
server.py V538/V552/V556) — mêmes replis, même cache, mêmes en-têtes :

- GET/HEAD `/api/share/invite/{token}` : page Open Graph (ce que lit le robot
  WhatsApp) ; un vrai navigateur est renvoyé vers `FRONT + cible_front(doc)`.
- GET/HEAD `/api/share/invite/{token}/carte.jpg` : la carte 1200×630.
- GET `/api/share/invite-preview/{id}.jpg` : la même carte pour le coach
  propriétaire (JWT strict), brouillon compris, jamais en cache public.

PUBLIC = SEULEMENT `status == "active"`. Brouillon, archivée ou jeton inconnu :
404 neutre, le même corps pour tous (aucun oracle).

AUCUNE DONNÉE PERSONNELLE : la page ne lit que le `dto_public` du moteur
(`referral_campaigns_engine`, AGENT 1) — jamais coach_id, e-mail, téléphone.
Tout est échappé (`html.escape`).

CARTE : UN SEUL MOTEUR DE RENDU (`referral_carte.py`, Pillow). On réutilise
`recuperer_photo` (hôtes autorisés, sans redirection, 3 s, 5 Mo), le cache
mémoire+disque de la carte Duo (`_v552_cle_cache` / `_v552_cache_lire` /
`_v552_cache_ecrire`, clé préfixée `inv|`), la lecture locale de nos fichiers
(`_v552_lire_fichier_local`) et la couleur de marque (`_v259_primary_color`).
Jamais de 500 : rendu personnalisé -> carte de marque -> logo -> JPEG embarqué.

Montage (server.py, AVANT le catch-all SPA `_serve_spa`) :
    fastapi_app.include_router(share_invite_router); init_share_invite_db(db)
"""
import hashlib
import html
import json
import logging
import os
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse, Response

from api.routes import referral_campaigns_engine as CE
from api.routes import referral_carte as RC
from api.routes import referral_engine as E

logger = logging.getLogger(__name__)

router = APIRouter(tags=["share-invite"])

db = None

PREFIXE = "[INV-3]"
COLL = "referral_campaigns"
STATUT_PUBLIC = "active"
TOKEN_MAX = 128
AGE_VERSION_JUSTE = 604800     # 7 j quand l'URL porte LA bonne version (comme la Duo)
AGE_COURT = 300


def init_db(database):
    global db
    db = database


def _base():
    """La base injectée ; à défaut celle du serveur (même instance en prod)."""
    if db is not None:
        return db
    from api import server as _S
    return _S.db


def _front() -> str:
    return (os.environ.get("FRONTEND_URL") or "https://afroboost.com").rstrip("/")


PAGE_INDISPONIBLE = (
    '<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    '<meta name="robots" content="noindex"><title>Invitation indisponible — Afroboost</title></head>'
    '<body style="margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:rgb(8,4,12);'
    'color:rgba(255,255,255,0.96);font-family:system-ui,-apple-system,sans-serif;padding:24px;box-sizing:border-box">'
    '<div style="max-width:420px;text-align:center"><h1 style="font-size:22px;margin:0 0 10px">Cette invitation n\'est plus disponible</h1>'
    '<p style="color:rgba(255,255,255,0.7);margin:0 0 18px">Tu peux découvrir Afroboost directement.</p>'
    '<a href="/" style="display:inline-block;padding:12px 22px;border-radius:999px;background:rgb(217,28,210);color:rgba(255,255,255,1);'
    'text-decoration:none;font-weight:700">Découvrir Afroboost</a></div></body></html>')


def _page_indisponible():
    """V610k — `/i/<jeton>` inconnu, brouillon, masqué ou supprimé : 404, corps IDENTIQUE pour
    tous (aucun oracle). Pour un navigateur : l'application, qui affiche « Cette invitation
    n'est plus disponible » — ou l'écran de retour de Stripe (paiement déjà engagé) ; sans
    build : une page HTML autonome. Jamais une erreur technique."""
    _index = _index_spa()
    _corps = _index if _index else PAGE_INDISPONIBLE
    return HTMLResponse(_corps, status_code=404, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                                          "X-Robots-Tag": "noindex"})


def _non_trouve():
    # INV-3 : 404 NEUTRE — même corps quel que soit le motif (inconnu, brouillon, archivée).
    return Response(content=b"Not Found", status_code=404, media_type="text/plain",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def _jeton_valide(token) -> str:
    _t = str(token or "").strip()
    if not _t or len(_t) > TOKEN_MAX or any(c.isspace() or c in "/\\?#%" for c in _t):
        return ""
    return _t


def _version(doc) -> int:
    # INV-3 : même règle que le moteur (min 1) -> og:image == `dto_coach().card_url`.
    try:
        return max(1, int((doc or {}).get("version") or 1))
    except (TypeError, ValueError):
        return 1


def _cible(doc, chaine=False) -> str:
    """`FRONT + cible_front(doc)` ; un chemin non relatif (ou `//hôte`) -> l'accueil.
    PAR-1 : `chaine` (drapeaux lus par la page) -> `/duo/c/<jeton>` pour un `trial` complet."""
    try:
        _c = str(CE.cible_front(doc, chaine) or "/")
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s cible_front impossible (%s)", PREFIXE, type(_e).__name__)
        _c = "/"
    if not _c.startswith("/") or _c.startswith("//") or "\\" in _c:
        _c = "/"
    # V607 : un ÉVÉNEMENT emporte son jeton (`inv=`, JAMAIS `ref=` — réservé aux
    # partenaires) : le paiement / l'inscription donnera au participant SON lien.
    if (doc or {}).get("type") in ("event_paid", "event_free") and _c.startswith("/?"):
        _c += "&inv=" + quote(str((doc or {}).get("share_token") or ""), safe="")
    return _front() + _c


async def _invitation_active(token):
    _t = _jeton_valide(token)
    if not _t:
        return None
    try:
        _d = await _base()[COLL].find_one({"share_token": _t}, {"_id": 0})
        if not _d:
            # V607 : le jeton d'un RELAIS (participant d'un événement) — même page, même
            # carte que l'invitation du coach, mais c'est LE PARTICIPANT qui invite.
            _r = await _base()["invitation_relais"].find_one({"jeton": _t}, {"_id": 0})
            if _r:
                _c = await _base()[COLL].find_one({"id": _r.get("campagne_id")}, {"_id": 0})
                if _c and _c.get("status") == STATUT_PUBLIC:
                    # Le mot personnel est celui du COACH : il ne parle pas au nom du participant.
                    _d = dict(_c, share_token=_r.get("jeton"), _relais=True, message=None,
                              inviter_display={"prenom": _r.get("inviteur_prenom") or "", "photo_url": None,
                                               "source": "member"})
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s invitation illisible (%s)", PREFIXE, type(_e).__name__)
        raise
    if not _d or _d.get("status") != STATUT_PUBLIC:
        return None
    return _d


async def _dto(doc) -> dict:
    """Le DTO PUBLIC du moteur (cours et offre chargés par identifiant)."""
    _b = _base()
    _cours, _offre = None, None
    try:
        if doc.get("course_id"):
            _cours = await _b["courses"].find_one({"id": str(doc["course_id"])}, {"_id": 0})
        if doc.get("offer_id"):
            _offre = await _b["offers"].find_one({"id": str(doc["offer_id"])}, {"_id": 0})
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s cours/offre illisibles (%s)", PREFIXE, type(_e).__name__)
    try:
        _r = CE.dto_public(doc, cours=_cours, offre=_offre)
        return _r if isinstance(_r, dict) else {}
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s dto_public impossible (%s)", PREFIXE, type(_e).__name__)
        return {"title": doc.get("title"), "subtitle": doc.get("subtitle"), "cta_label": doc.get("cta_label")}


def _inviteur(dto) -> dict:
    _i = (dto or {}).get("inviter_display")
    return _i if isinstance(_i, dict) else {}


# ─── Carte ──────────────────────────────────────────────────────────────────
async def _couleur(doc) -> str:
    try:
        from api.server import _v259_primary_color
        return await _v259_primary_color(str((doc or {}).get("coach_id") or ""))
    except Exception:  # noqa: BLE001
        return RC.COULEUR_DEFAUT


async def _url_fond(doc, dto):
    """Image de l'invitation > image de partage du coach/plateforme (V551) >
    rien (fond de marque). Toute URL passe ensuite par `recuperer_photo`."""
    for _u in ((doc or {}).get("image_url"), (dto or {}).get("image_url")):
        if _u:
            return str(_u)
    try:
        from api.routes.referral_routes import _reglages_effectifs
        return (await _reglages_effectifs(str((doc or {}).get("coach_id") or "").strip().lower())).get("image_url")
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s réglages de partage illisibles (%s)", PREFIXE, type(_e).__name__)
        return None


def _empreinte(doc, dto, fond_url, photo_url) -> str:
    """16 hexa : tout ce que la carte dessine. Entre dans la clé de cache."""
    _i = _inviteur(dto)
    _cle = [RC.GABARIT_INVITATION, _version(doc), fond_url or "", photo_url or "", _i.get("prenom") or ""]
    _cle += [str((dto or {}).get(k) or "") for k in ("title", "subtitle", "cta_label", "date_label",
                                                     "time_label", "lieu", "occurrence", "mention_prix")]
    return hashlib.sha256(json.dumps(_cle, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


async def _octets_carte(doc, dto, cache=True):
    """(octets, type, personnalisée?) — même ordre de replis que la carte Duo.
    Jamais d'exception, jamais d'octets vides."""
    from api import server as _S
    _couleur_hex = await _couleur(doc)
    _hote = urlsplit(_front()).hostname or "afroboost.com"
    _fond_url = await _url_fond(doc, dto)
    _photo_url = _inviteur(dto).get("photo_url")
    _cle = None
    if cache:
        try:
            _cle = _S._v552_cle_cache("inv|" + str(doc.get("share_token") or doc.get("id") or ""),
                                      _empreinte(doc, dto, _fond_url, _photo_url), _couleur_hex)
            _deja = _S._v552_cache_lire(_cle)
            if _deja:
                return _deja, "image/jpeg", True
        except Exception:  # noqa: BLE001
            _cle = None
    # 1. la carte personnalisée
    try:
        _fond = await RC.recuperer_photo(_fond_url, _S._v552_lire_fichier_local, hote_front=_hote) \
            if _fond_url else None
        _photo = await RC.recuperer_photo(_photo_url, _S._v552_lire_fichier_local, hote_front=_hote) \
            if _photo_url else None
        _octets = RC.rendre_carte_invitation(RC.donnees_carte_invitation(dto, _couleur_hex, _fond, _photo))
        if not _octets:
            raise ValueError("rendu vide")
        if _cle:
            _S._v552_cache_ecrire(_cle, _octets)
        return _octets, "image/jpeg", True
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s carte personnalisée impossible (%s) -> carte de marque", PREFIXE, type(_e).__name__)
    # 2. la carte de marque (non mise en cache : on retentera)
    try:
        _octets = RC.rendre_carte_invitation({"couleur": _couleur_hex})
        if _octets:
            return _octets, "image/jpeg", False
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s carte de marque impossible (%s) -> logo", PREFIXE, type(_e).__name__)
    # 3. le logo, 4. le JPEG de secours embarqué
    try:
        _logo = _S._v552_logo_octets()
        if _logo:
            return _logo[0], _logo[1], False
    except Exception:  # noqa: BLE001
        pass
    return RC.JPEG_SECOURS, "image/jpeg", False


def _image(octets, type_mime="image/jpeg", cache_control="public, max-age=86400"):
    return Response(content=octets, media_type=type_mime, headers={
        "Cache-Control": cache_control, "X-Content-Type-Options": "nosniff"})


# INV-3 : GET ET HEAD (les robots d'aperçu sondent parfois en HEAD).
@router.head("/api/share/invite/{token}/carte.jpg")
@router.get("/api/share/invite/{token}/carte.jpg")
async def share_invite_carte(token: str, v: str = ""):
    """La carte 1200×630 d'une invitation ACTIVE. `v` ne sert qu'au cache des
    aperçus : la carte servie est toujours la courante ; cache HTTP long
    seulement si `v` est la version courante."""
    try:
        _doc = await _invitation_active(token)
    except Exception:  # noqa: BLE001  (base indisponible : carte de marque, cache court)
        try:
            return _image(RC.rendre_carte_invitation({}), cache_control="public, max-age=300")
        except Exception:  # noqa: BLE001
            return _image(RC.JPEG_SECOURS, cache_control="public, max-age=60")
    if not _doc:
        return _non_trouve()
    _dto_pub = await _dto(_doc)
    _octets, _type, _perso = await _octets_carte(_doc, _dto_pub)
    _age = AGE_VERSION_JUSTE if str(v or "") == str(_version(_doc)) else AGE_COURT
    return _image(_octets, _type, "public, max-age=%d" % (_age if _perso else min(_age, AGE_COURT)))


# ─── Page Open Graph ────────────────────────────────────────────────────────
def _majuscule(t) -> str:
    _t = str(t or "").strip()
    return (_t[:1].upper() + _t[1:]) if _t else ""


def titre_og(dto) -> str:
    """V607 — le titre d'aperçu PROPRE au type (jamais celui de l'accueil)."""
    _d = dto or {}
    _p = str(_inviteur(_d).get("prenom") or "").strip()
    _p = "" if "@" in _p else _p
    _t = str(_d.get("title") or "").strip()
    _type = _d.get("type")
    if _type == "trial":
        return ("%s t'invite à découvrir Afroboost 🔥" % _p) if _p else "Ton premier cours Afroboost est offert 🔥"
    if _type == "pass_duo":
        return ("%s t'invite à venir à deux avec le Pass Duo" % _p) if _p else (_t or "Viens à deux avec le Pass Duo")
    _nom = _t or str(_d.get("offre_nom") or "").strip() or RC.TITRE_INVITATION_DEFAUT
    return (("%s t'invite : %s" % (_p, _nom)) if _p and _p.lower() not in _nom.lower() else _nom)[:120]


def description_og(dto) -> str:
    """V607 — « Mercredi 14 octobre · 18:45 · Auvernier · Premier cours offert »."""
    _d = dto or {}
    _parts = [_majuscule(_d.get("date_label")), str(_d.get("time_label") or "").strip(),
              str(_d.get("lieu") or "").strip()]
    _type = _d.get("type")
    if _type == "trial":
        _parts.append("Premier cours offert")
    elif _type == "event_free":
        _parts.append("Gratuit")
    elif _type == "event_paid" and _d.get("mention_prix"):
        _parts.append(str(_d.get("mention_prix")))
    _texte = " · ".join(p for p in _parts if p)
    return (_texte or _description(_d))[:200]


def _description(dto) -> str:
    _d = dto or {}
    _quand = " · ".join(str(_d.get(k) or "").strip() for k in ("date_label", "time_label") if _d.get(k))
    _parts = [str(_d.get("subtitle") or "").strip(), _quand, str(_d.get("lieu") or "").strip()]
    _texte = " — ".join(p for p in _parts if p) or str(_d.get("message") or "").strip()
    return (_texte or "Viens essayer Afroboost : cardio, danse afrobeat et casques audio.")[:200]


def _titre(dto) -> str:
    _d = dto or {}
    _t = str(_d.get("title") or "").strip() or RC.TITRE_INVITATION_DEFAUT
    _p = str(_inviteur(_d).get("prenom") or "").strip()
    if _p and "@" not in _p and _p.lower() not in _t.lower():
        _t = "%s t'invite : %s" % (_p, _t)
    return _t[:120]


def page_invitation_html(titre, description, image, url, cible, couleur, robot=False) -> str:
    """INV-3 — la page d'aperçu, TOUT échappé. Pas de `<script>` : la
    redirection d'un navigateur passe par `meta refresh` + un lien ; un robot
    ne reçoit pas le `refresh` (il lirait les balises de l'accueil)."""
    e = lambda s: html.escape(str(s or ""), quote=True)  # noqa: E731
    _rgb = RC.couleur_valide(couleur)
    _coul = "#%02x%02x%02x" % _rgb
    _refresh = "" if robot else '\n    <meta http-equiv="refresh" content="0;url=%s"/>' % e(cible)
    return """<!DOCTYPE html>
<html lang="fr" prefix="og: https://ogp.me/ns#">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>{t}</title>
    <meta name="description" content="{d}"/>
    <meta property="og:type" content="website"/>
    <meta property="og:title" content="{t}"/>
    <meta property="og:description" content="{d}"/>
    <meta property="og:image" content="{i}"/>
    <meta property="og:image:secure_url" content="{i}"/>
    <meta property="og:image:type" content="image/jpeg"/>
    <meta property="og:image:width" content="1200"/>
    <meta property="og:image:height" content="630"/>
    <meta property="og:image:alt" content="{t}"/>
    <meta property="og:url" content="{u}"/>
    <meta property="og:site_name" content="Afroboost"/>
    <meta property="og:locale" content="fr_FR"/>
    <meta name="robots" content="noindex, nofollow"/>
    <meta name="twitter:card" content="summary_large_image"/>
    <meta name="twitter:title" content="{t}"/>
    <meta name="twitter:description" content="{d}"/>
    <meta name="twitter:image" content="{i}"/>{r}
</head>
<body style="margin:0;background:#000;color:#fff;font-family:system-ui,-apple-system,'Segoe UI',sans-serif;">
    <main style="max-width:520px;margin:0 auto;padding:28px 18px;text-align:center;">
        <p style="letter-spacing:.14em;text-transform:uppercase;font-size:12px;color:{k};margin:0 0 10px;">Invitation</p>
        <h1 style="font-size:26px;line-height:1.25;margin:0 0 10px;">{t}</h1>
        <p style="color:rgba(255,255,255,.72);font-size:15px;line-height:1.5;margin:0 0 20px;">{d}</p>
        <a href="{c}" style="display:inline-block;padding:14px 26px;border-radius:999px;background:{k};color:#fff;text-decoration:none;font-weight:700;">Voir l'invitation</a>
    </main>
</body>
</html>""".format(t=e(titre), d=e(description), i=e(image), u=e(url), c=e(cible), k=e(_coul), r=_refresh)


@router.head("/api/share/invite/{token}")
@router.get("/api/share/invite/{token}")
async def share_invite_page(token: str, request: Request = None, v: str = ""):
    """La page Open Graph d'une invitation ACTIVE. og:image = URL ABSOLUE
    `<FRONT>/api/share/invite/<token>/carte.jpg?v=<version>` ; og:url = l'adresse
    exacte partagée (avec `?v=` nettoyé). `v` n'a aucun effet sur la logique."""
    try:
        _doc = await _invitation_active(token)
    except Exception:  # noqa: BLE001
        _doc = None
    if not _doc:
        return _non_trouve()
    _tok = str(_doc.get("share_token"))
    _dto_pub = await _dto(_doc)
    _front_url = _front()
    _tq = quote(_tok, safe="")
    _image_url = "%s/api/share/invite/%s/carte.jpg?v=%d" % (_front_url, _tq, _version(_doc))
    _vr = E.version_depuis_requete(v)
    _url = "%s/api/share/invite/%s%s" % (_front_url, _tq, ("?v=%d" % _vr) if _vr else "")
    try:
        _ua = request.headers.get("user-agent", "") if request is not None else ""
    except Exception:  # noqa: BLE001
        _ua = ""
    # PAR-1 : les liens DÉJÀ partagés basculent vers la chaîne quand les drapeaux
    # sont allumés (même URL, nouvelle cible) ; éteints = cible d'avant.
    try:
        from api.routes.referral_routes import invitation_chaine_campagne_active
        _chaine = await invitation_chaine_campagne_active(_base())
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s drapeaux de chaîne illisibles (%s) — cible d'avant", PREFIXE, type(_e).__name__)
        _chaine = False
    # V607 : mêmes titres / descriptions que le lien court (propres au type).
    _page = page_invitation_html(titre_og(_dto_pub), description_og(_dto_pub), _image_url, _url,
                                 _cible(_doc, _chaine), await _couleur(_doc), robot=E.est_robot_apercu(_ua))
    return HTMLResponse(_page, headers={"Cache-Control": "public, max-age=300", "Vary": "User-Agent",
                                        "X-Content-Type-Options": "nosniff"})


# ─── V607 : LE LIEN COURT PUBLIC `/i/<jeton>` ─────────────────────────────────
def _index_spa() -> str:
    """Le index.html du build (servi par `_serve_spa`), ou "" si absent."""
    try:
        from api import server as _S
        _chemin = os.path.join(_S._STATIC_DIR, "index.html")
        with open(_chemin, encoding="utf-8") as _f:
            return _f.read()
    except Exception:  # noqa: BLE001
        return ""



def index_avec_og(index_html, titre, description, image, url) -> str:
    """Le index.html de l'app, ses balises og/twitter/description REMPLACÉES par
    celles de l'invitation (tout échappé). La page React `/i/<jeton>` s'affiche
    ensuite ; un robot qui lit le HTML voit l'aperçu de l'invitation."""
    import re as _re
    e = lambda s: html.escape(str(s or ""), quote=True)  # noqa: E731
    _h = _re.sub(r'\s*<meta\s+(?:property="og:[^"]*"|name="twitter:[^"]*"|name="description")[^>]*>', "", index_html)
    _h = _re.sub(r"<title>.*?</title>", "<title>%s</title>" % e(titre), _h, count=1, flags=_re.S)
    _meta = ('<meta name="description" content="{d}"/><meta property="og:type" content="website"/>'
             '<meta property="og:title" content="{t}"/><meta property="og:description" content="{d}"/>'
             '<meta property="og:image" content="{i}"/><meta property="og:image:secure_url" content="{i}"/>'
             '<meta property="og:image:type" content="image/jpeg"/><meta property="og:image:width" content="1200"/>'
             '<meta property="og:image:height" content="630"/><meta property="og:url" content="{u}"/>'
             '<meta property="og:site_name" content="Afroboost"/><meta property="og:locale" content="fr_FR"/>'
             '<meta name="robots" content="noindex, nofollow"/><meta name="twitter:card" content="summary_large_image"/>'
             '<meta name="twitter:title" content="{t}"/><meta name="twitter:description" content="{d}"/>'
             '<meta name="twitter:image" content="{i}"/>').format(t=e(titre), d=e(description), i=e(image), u=e(url))
    return _h.replace("<head>", "<head>" + _meta, 1) if "<head>" in _h else _meta + _h


@router.head("/i/{token}")
@router.get("/i/{token}")
async def lien_court(token: str, request: Request = None, v: str = ""):
    """V607 — `afroboost.com/i/<jeton>` : la façade COURTE des invitations (coach ou
    relais). Robot d'aperçu -> balises OG de l'invitation ; navigateur -> la page
    d'invitation (React) avec les mêmes balises. Les anciens liens
    `/api/share/invite/<jeton>` restent servis à l'identique. 404 neutre sinon."""
    try:
        _doc = await _invitation_active(token)
    except Exception:  # noqa: BLE001
        _doc = None
    if not _doc:
        return _page_indisponible()
    _tok = str(_doc.get("share_token"))
    _dto_pub = await _dto(_doc)
    _tq = quote(_tok, safe="")
    _front_url = _front()
    _image_url = "%s/api/share/invite/%s/carte.jpg?v=%d" % (_front_url, _tq, _version(_doc))
    _vr = E.version_depuis_requete(v)
    _url = "%s/i/%s%s" % (_front_url, _tq, ("?v=%d" % _vr) if _vr else "")
    try:
        _ua = request.headers.get("user-agent", "") if request is not None else ""
    except Exception:  # noqa: BLE001
        _ua = ""
    _titre, _desc = titre_og(_dto_pub), description_og(_dto_pub)
    _entetes = {"Cache-Control": "public, max-age=300", "Vary": "User-Agent", "X-Content-Type-Options": "nosniff"}
    _index = "" if E.est_robot_apercu(_ua) else _index_spa()
    if not _index:
        try:
            from api.routes.referral_routes import invitation_chaine_campagne_active
            _chaine = await invitation_chaine_campagne_active(_base())
        except Exception:  # noqa: BLE001
            _chaine = False
        return HTMLResponse(page_invitation_html(_titre, _desc, _image_url, _url, _cible(_doc, _chaine),
                                                 await _couleur(_doc), robot=E.est_robot_apercu(_ua)), headers=_entetes)
    return HTMLResponse(index_avec_og(_index, _titre, _desc, _image_url, _url), headers=_entetes)


@router.get("/api/invitation/publique/{token}")
async def invitation_publique(token: str):
    """V607 — ce que la page `/i/<jeton>` affiche : le `dto_public` (aucune PII) +
    la cible RÉELLE du bouton (chaîne de l'essai, vitrine, Pass Duo). 404 neutre."""
    try:
        _doc = await _invitation_active(token)
    except Exception:  # noqa: BLE001
        _doc = None
    if not _doc:
        return _non_trouve()
    _dto_pub = await _dto(_doc)
    try:
        from api.routes.referral_routes import invitation_chaine_campagne_active
        _chaine = await invitation_chaine_campagne_active(_base())
    except Exception:  # noqa: BLE001
        _chaine = False
    _sortie = dict(_dto_pub)
    _sortie.update({"cible": _cible(_doc, _chaine), "relais": bool(_doc.get("_relais")),
                    "card_url": "%s/api/share/invite/%s/carte.jpg?v=%d" % (_front(), quote(str(_doc.get("share_token")), safe=""), _version(_doc)),
                    "og_titre": titre_og(_dto_pub), "og_description": description_og(_dto_pub)})
    # V610i : événement payant à réservation AUTOMATIQUE, en vente -> « Je réserve ma place »
    # ouvre Stripe directement (prix décidé par le serveur au checkout). Sinon : la vitrine.
    _sortie["reservation_directe"] = None
    try:
        if _doc.get("type") == "event_paid" and _doc.get("offer_id"):
            _o = await _base()["offers"].find_one({"id": str(_doc["offer_id"])}, {"_id": 0})
            from api.routes import evenement_special as _v610_evt
            if _o and _v610_evt.reservation_auto(_o) and _o.get("visible") is not False and _o.get("archived") is not True \
                    and not _v610_evt.evenement_commence(_doc.get("occurrence")):
                _sortie["reservation_directe"] = {"offer_id": _o.get("id")}
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s réservation directe non évaluée (%s)", PREFIXE, type(_e).__name__)
    return _sortie


# ─── Aperçu coach (brouillon compris) ───────────────────────────────────────
@router.get("/api/share/invite-preview/{invite_id}.jpg")
async def share_invite_preview(invite_id: str, request: Request):
    """La carte d'une invitation du coach appelant, quel que soit son statut.
    JWT strict (`_coach_strict` : 401 sans jeton, 403 jeton non coach) ;
    cloisonnement `coach_id == cle` ; 404 sinon. Jamais en cache public."""
    from api.routes.referral_routes import _coach_strict
    _c = await _coach_strict(request)
    _id = str(invite_id or "").strip()
    if not _id or len(_id) > TOKEN_MAX:
        return _non_trouve()
    try:
        _doc = await _base()[COLL].find_one({"id": _id, "coach_id": _c["cle"]}, {"_id": 0})
    except Exception as _e:  # noqa: BLE001
        logger.warning("%s aperçu : invitation illisible (%s)", PREFIXE, type(_e).__name__)
        _doc = None
    if not _doc:
        return _non_trouve()
    _octets, _type, _ = await _octets_carte(_doc, await _dto(_doc), cache=False)
    return _image(_octets, _type, "private, no-store")

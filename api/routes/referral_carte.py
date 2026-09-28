# -*- coding: utf-8 -*-
"""V552 — LA CARTE SOCIALE D'UNE INVITATION PASS DUO (rendu Pillow pur).

POURQUOI. L'aperçu WhatsApp d'une invitation montrait l'image du coach ou de
l'offre : la même pour tout le monde, sans le visage ni le prénom de celui qui
invite. Ici on DESSINE une carte 1200×630 (le format d'aperçu « grande image »
d'Open Graph) : fond de marque, photo ronde du membre, « Léa t'invite à
découvrir Afroboost », l'activité, la date, le lieu.

CE MODULE EST PUR. Aucun accès réseau ni base dans `rendre_carte` : il reçoit
des données (et la photo déjà en octets), il rend des octets JPEG. Le seul
morceau « réseau » (`telecharger_https`) est isolé, borné (hôtes autorisés,
3 s, 5 Mo, AUCUNE redirection suivie) et injectable dans les tests.

CE QU'ELLE NE MONTRE JAMAIS : ni e-mail, ni téléphone, ni identifiant. Le nom
passe par `referral_engine.nom_parrain_affichable` (filtre V551).
"""
import base64
import io
import os
import unicodedata
from datetime import datetime
from urllib.parse import urlsplit

from api.routes import referral_engine as E

LARGEUR, HAUTEUR = 1200, 630
QUALITE_JPEG = 85
COULEUR_DEFAUT = "#D91CD2"      # valeur de secours ; la vraie vient de concept.primaryColor
PHOTO_MAX_OCTETS = 5 * 1024 * 1024
PHOTO_MAX_PIXELS = 40_000_000   # au-delà : bombe de décompression probable, on ignore la photo
PHOTO_TIMEOUT_S = 3.0

_DOSSIER_POLICES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "assets", "fonts")
_POLICE_GRAS = os.path.join(_DOSSIER_POLICES, "DejaVuSans-Bold.ttf")
_POLICE_NORMALE = os.path.join(_DOSSIER_POLICES, "DejaVuSans.ttf")

_JOURS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
_MOIS_COURTS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août",
                "sept.", "oct.", "nov.", "déc.")

# V552 : le DERNIER repli (Pillow indisponible, aucun logo lisible) — un JPEG
# valide 120×63 aux couleurs de la marque, jamais un corps vide.
JPEG_SECOURS = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAA0JCgsKCA0LCgsODg0PEyAVExISEyccHhcgLikxMC4p"
    "LSwzOko+MzZGNywtQFdBRkxOUlNSMj5aYVpQYEpRUk//2wBDAQ4ODhMREyYVFSZPNS01T09PT09P"
    "T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0//wAARCAA/AHgDASIA"
    "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQA"
    "AAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3"
    "ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWm"
    "p6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEA"
    "AwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSEx"
    "BhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElK"
    "U1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3"
    "uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDz2iii"
    "tzoCiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooo"
    "oAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiig"
    "AooooAKKKKACiiigD//Z"
)

_CACHE_POLICES = {}


# ─── Textes ──────────────────────────────────────────────────────────────────
def _nettoyer(texte, maxi=200) -> str:
    """Une ligne propre : espaces compactés, sans caractères de contrôle ni
    emoji (la police ne les a pas : ils sortiraient en carrés vides)."""
    _t = str(texte or "")
    _sortie = []
    for c in _t:
        o = ord(c)
        if o >= 0x1F000 or 0x2600 <= o <= 0x27BF or 0xFE00 <= o <= 0xFE0F or o in (0x200D, 0x20E3):
            continue
        if unicodedata.category(c) in ("Cc", "Cf", "Cs", "Co"):
            _sortie.append(" ")
            continue
        _sortie.append(c)
    return " ".join("".join(_sortie).split())[:maxi]


def date_courte(occurrence_iso) -> str:
    """« Mercredi 30 sept. · 18:45 » ; "" si illisible."""
    try:
        _d = datetime.fromisoformat(str(occurrence_iso or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return ""
    return "%s %d %s · %02d:%02d" % (_JOURS[_d.weekday()], _d.day, _MOIS_COURTS[_d.month - 1],
                                     _d.hour, _d.minute)


def titre_carte(nom) -> str:
    _n = _nettoyer(nom, 40)
    if not _n or "@" in _n:
        return "Un membre Afroboost t'invite à découvrir Afroboost"
    return "%s t'invite à découvrir Afroboost" % _n


def couleur_valide(valeur) -> tuple:
    """(r, g, b) depuis « #RRGGBB » / « #RGB » ; la couleur de marque sinon."""
    _v = str(valeur or "").strip().lstrip("#")
    if len(_v) == 3:
        _v = "".join(c * 2 for c in _v)
    try:
        if len(_v) != 6:
            raise ValueError(_v)
        return (int(_v[0:2], 16), int(_v[2:4], 16), int(_v[4:6], 16))
    except ValueError:
        _d = COULEUR_DEFAUT.lstrip("#")
        return (int(_d[0:2], 16), int(_d[2:4], 16), int(_d[4:6], 16))


def donnees_carte(pass_doc, couleur=None, photo=None) -> dict:
    """Ce que la carte affiche, depuis un pass (pur). Jamais d'e-mail."""
    _p = pass_doc or {}
    _cours = E.dto_course(_p)
    _offre = E.offre_du_pass(_p)
    return {
        "nom": E.nom_parrain_affichable(_p),
        "cours": _cours.get("name") or "",
        "offre": (_offre or {}).get("name") or "",
        "occurrence": _p.get("occurrence"),
        "lieu": _cours.get("locationName") or "",
        "couleur": couleur,
        "photo": photo,
    }


# ─── Rendu ───────────────────────────────────────────────────────────────────
def _police(gras, taille):
    from PIL import ImageFont
    _cle = (gras, taille)
    if _cle not in _CACHE_POLICES:
        try:
            _CACHE_POLICES[_cle] = ImageFont.truetype(_POLICE_GRAS if gras else _POLICE_NORMALE, taille)
        except Exception:  # noqa: BLE001  (police absente : la police intégrée de Pillow)
            _CACHE_POLICES[_cle] = ImageFont.load_default(size=taille)
    return _CACHE_POLICES[_cle]


def _tronquer(dessin, texte, police, largeur) -> str:
    if dessin.textlength(texte, font=police) <= largeur:
        return texte
    _t = texte
    while _t and dessin.textlength(_t.rstrip() + "…", font=police) > largeur:
        _t = _t[:-1]
    return (_t.rstrip() + "…") if _t else "…"


def _lignes(dessin, texte, police, largeur, maxi) -> list:
    """Retour à la ligne par mots ; la dernière ligne est tronquée (…)."""
    _mots = texte.split()
    _lignes = []
    _courante = ""
    for i, _m in enumerate(_mots):
        _essai = (_courante + " " + _m).strip()
        if dessin.textlength(_essai, font=police) <= largeur or not _courante:
            _courante = _essai
            continue
        _lignes.append(_courante)
        _courante = _m
        if len(_lignes) == maxi - 1:
            _courante = " ".join(_mots[i:])
            break
    if _courante:
        _lignes.append(_courante)
    return [_tronquer(dessin, l, police, largeur) for l in _lignes[:maxi]]


def _photo_ronde(octets, diametre, anneau_rgb):
    """La photo recadrée au centre, en disque, cerclée ; None si illisible."""
    from PIL import Image, ImageDraw, ImageOps
    if not octets or len(octets) > PHOTO_MAX_OCTETS:
        return None
    try:
        _img = Image.open(io.BytesIO(octets))
        if _img.size[0] * _img.size[1] > PHOTO_MAX_PIXELS:
            return None
        _img.draft("RGB", (diametre * 2, diametre * 2))
        _img = ImageOps.exif_transpose(_img).convert("RGB")
        _img = ImageOps.fit(_img, (diametre, diametre), method=Image.LANCZOS)
    except Exception:  # noqa: BLE001  (photo corrompue : carte sans photo)
        return None
    _anneau = 8
    _total = diametre + 2 * _anneau
    _sortie = Image.new("RGBA", (_total, _total), (0, 0, 0, 0))
    ImageDraw.Draw(_sortie).ellipse((0, 0, _total - 1, _total - 1), fill=anneau_rgb + (255,))
    _masque = Image.new("L", (diametre, diametre), 0)
    ImageDraw.Draw(_masque).ellipse((0, 0, diametre - 1, diametre - 1), fill=255)
    _sortie.paste(_img, (_anneau, _anneau), _masque)
    return _sortie


def rendre_carte(donnees=None) -> bytes:
    """JPEG 1200×630. `donnees` vide ou None -> la carte générique Afroboost.
    Clés lues : nom, cours, offre, occurrence, lieu, couleur, photo (octets)."""
    from PIL import Image, ImageDraw, ImageFilter
    _d = donnees if isinstance(donnees, dict) else {}
    _marque = couleur_valide(_d.get("couleur"))
    _generique = not any(_d.get(k) for k in ("nom", "cours", "offre", "occurrence", "lieu", "photo"))

    # Fond : noir violacé -> teinte de marque assombrie, en diagonale, + halo.
    _sombre = Image.new("RGB", (LARGEUR, HAUTEUR), (10, 4, 16))
    _teinte = Image.new("RGB", (LARGEUR, HAUTEUR), tuple(int(c * 0.42) for c in _marque))
    _horiz = Image.linear_gradient("L").rotate(90).transpose(Image.FLIP_LEFT_RIGHT).resize((LARGEUR, HAUTEUR))
    _vert = Image.linear_gradient("L").resize((LARGEUR, HAUTEUR))
    _grad = Image.blend(_horiz, _vert, 0.35)          # diagonale douce, sans arête
    _fond = Image.composite(_teinte, _sombre, _grad)
    _halo = Image.new("L", (LARGEUR, HAUTEUR), 0)
    ImageDraw.Draw(_halo).ellipse((720, -260, 1440, 460), fill=120)
    _halo = _halo.filter(ImageFilter.GaussianBlur(120))
    _fond = Image.composite(Image.new("RGB", (LARGEUR, HAUTEUR), _marque), _fond, _halo)
    _dessin = ImageDraw.Draw(_fond)

    _blanc = (255, 255, 255)
    _gris = (214, 206, 222)
    _clair = tuple(min(255, int(c + (255 - c) * 0.45)) for c in _marque)

    # En-tête : le mot-marque.
    _dessin.text((80, 62), "AFROBOOST", font=_police(True, 38), fill=_clair)
    _dessin.text((80 + _dessin.textlength("AFROBOOST", font=_police(True, 38)) + 18, 70), "Pass Duo",
                 font=_police(False, 30), fill=_gris)

    # Photo ronde (facultative) et colonne de texte.
    _x = 80
    _photo = _photo_ronde(_d.get("photo"), 236, _marque) if _d.get("photo") else None
    if _photo is not None:
        _fond.paste(_photo, (80, 190), _photo)
        _x = 80 + _photo.size[0] + 56
    _largeur = LARGEUR - _x - 70

    if _generique:
        _dessin.text((_x, 200), "Viens essayer", font=_police(True, 76), fill=_blanc)
        _dessin.text((_x, 292), "Afroboost avec nous", font=_police(True, 76), fill=_blanc)
        _dessin.text((_x, 410), "Cardio · danse afrobeat · casques audio", font=_police(False, 36), fill=_gris)
    else:
        _y = 170
        _pt = _police(True, 60)
        for _l in _lignes(_dessin, titre_carte(_d.get("nom")), _pt, _largeur, 2):
            _dessin.text((_x, _y), _l, font=_pt, fill=_blanc)
            _y += 74
        _y += 22
        _activite = " — ".join(t for t in (_nettoyer(_d.get("cours"), 80), _nettoyer(_d.get("offre"), 80)) if t)
        for _texte, _police_l, _couleur in ((_activite, _police(True, 38), _clair),
                                            (date_courte(_d.get("occurrence")), _police(False, 36), _blanc),
                                            (_nettoyer(_d.get("lieu"), 80), _police(False, 32), _gris)):
            if not _texte:
                continue
            _dessin.text((_x, _y), _tronquer(_dessin, _texte, _police_l, _largeur), font=_police_l, fill=_couleur)
            _y += 56

    # Pied : bandeau de marque + adresse.
    _dessin.rectangle((0, HAUTEUR - 12, LARGEUR, HAUTEUR), fill=_marque)
    _dessin.text((80, HAUTEUR - 70), "afroboost.com", font=_police(False, 28), fill=_gris)

    _sortie = io.BytesIO()
    _fond.save(_sortie, "JPEG", quality=QUALITE_JPEG, optimize=True, progressive=True)
    return _sortie.getvalue()


# ─── Photo : d'où a-t-on le droit de la lire ? ──────────────────────────────
def source_photo(url, hote_front="afroboost.com"):
    """("local", file_id, nom) pour un de NOS fichiers (lu sans HTTP),
    ("distant", url) pour un hôte autorisé (liste V551), None sinon."""
    _v = str(url or "").strip()
    if not _v or len(_v) > E.PHOTO_URL_MAX:
        return None
    if E.url_image_partage_valide(_v):
        _, _, _, _fid, _nom = _v.split("/", 4)
        return ("local", _fid, _nom)
    try:
        _u = urlsplit(_v)
    except ValueError:
        return None
    _hote = (_u.hostname or "").lower()
    if _u.scheme != "https" or _u.username or _u.password or _u.port not in (None, 443) \
            or any(c.isspace() for c in _v):
        return None
    if _hote in ("afroboost.com", "www.afroboost.com", str(hote_front or "").lower()):
        _chemin = _u.path if not _u.query and not _u.fragment else ""
        if E.url_image_partage_valide(_chemin):
            _, _, _, _fid, _nom = _chemin.split("/", 4)
            return ("local", _fid, _nom)
        return None
    if _hote in E.HOTES_PHOTO:
        return ("distant", _v)
    return None


async def telecharger_https(url, timeout=PHOTO_TIMEOUT_S, max_octets=PHOTO_MAX_OCTETS):
    """GET borné : AUCUNE redirection suivie, 3 s, 5 Mo, une image ; None sinon."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as _c:
            async with _c.stream("GET", url, headers={"Accept": "image/*"}) as _r:
                if _r.status_code != 200:
                    return None
                if not str(_r.headers.get("content-type", "")).lower().startswith("image/"):
                    return None
                try:
                    if int(_r.headers.get("content-length") or 0) > max_octets:
                        return None
                except ValueError:
                    return None
                _morceaux, _total = [], 0
                async for _b in _r.aiter_bytes():
                    _total += len(_b)
                    if _total > max_octets:
                        return None
                    _morceaux.append(_b)
                return b"".join(_morceaux)
    except Exception:  # noqa: BLE001  (délai, DNS, TLS : carte sans photo)
        return None


async def recuperer_photo(url, lire_local, telecharger=None, hote_front="afroboost.com"):
    """Les octets de la photo, ou None. `lire_local(file_id, nom)` et
    `telecharger(url)` sont des coroutines injectées (tests : mouchards)."""
    _src = source_photo(url, hote_front)
    if not _src:
        return None
    try:
        if _src[0] == "local":
            _o = await lire_local(_src[1], _src[2])
        else:
            _o = await (telecharger or telecharger_https)(_src[1])
    except Exception:  # noqa: BLE001
        return None
    if not _o or len(_o) > PHOTO_MAX_OCTETS:
        return None
    return bytes(_o)

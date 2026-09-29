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


# ═══════════════════════════════════════════════════════════════════════════
# INV-3 : LA CARTE D'UNE INVITATION-CAMPAGNE (`referral_campaigns`)
# ═══════════════════════════════════════════════════════════════════════════
# INV-3 : AJOUT PUR. Rien ci-dessus n'est modifié : la carte Pass Duo
# (`rendre_carte`) garde ses octets et sa version. On RÉUTILISE ses briques
# (_police, _lignes, _tronquer, _nettoyer, _photo_ronde, couleur_valide,
# date_courte) ; seule la mise en page diffère (image de fond, sous-titre, CTA).
GABARIT_INVITATION = "inv1"
TITRE_INVITATION_DEFAUT = "Invitation Afroboost"
CTA_INVITATION_DEFAUT = "Réserver ma place"
FOND_MAX_PIXELS = 12_000_000     # INV-3 (audit P2) : fond d'invitation, plus strict que PHOTO_MAX_PIXELS


def donnees_carte_invitation(dto, couleur=None, fond=None, photo=None) -> dict:
    """INV-3 — ce que la carte affiche, depuis le `dto_public` d'une invitation
    (pur). `fond` et `photo` sont des octets déjà lus. Jamais d'e-mail : un
    prénom contenant « @ » est effacé."""
    _d = dto if isinstance(dto, dict) else {}
    _inv = _d.get("inviter_display") if isinstance(_d.get("inviter_display"), dict) else {}
    _prenom = _nettoyer(_inv.get("prenom"), 40)
    if "@" in _prenom:
        _prenom = ""
    _date = _nettoyer(_d.get("date_label"), 60)
    _heure = _nettoyer(_d.get("time_label"), 20)
    _quand = " · ".join(t for t in (_date, _heure) if t) or date_courte(_d.get("occurrence"))
    return {
        "titre": _nettoyer(_d.get("title"), 120),
        "sous_titre": _nettoyer(_d.get("subtitle"), 160),
        "quand": _quand,
        "lieu": _nettoyer(_d.get("lieu"), 80),
        "cta": _nettoyer(_d.get("cta_label"), 40),
        "prenom": _prenom,
        "couleur": couleur,
        "fond": fond,
        "photo": photo,
    }


def _fond_marque_invitation(marque):
    """Le fond de marque (même recette que la carte Duo), sans image."""
    from PIL import Image, ImageDraw, ImageFilter
    _sombre = Image.new("RGB", (LARGEUR, HAUTEUR), (10, 4, 16))
    _teinte = Image.new("RGB", (LARGEUR, HAUTEUR), tuple(int(c * 0.42) for c in marque))
    _horiz = Image.linear_gradient("L").rotate(90).transpose(Image.FLIP_LEFT_RIGHT).resize((LARGEUR, HAUTEUR))
    _vert = Image.linear_gradient("L").resize((LARGEUR, HAUTEUR))
    _fond = Image.composite(_teinte, _sombre, Image.blend(_horiz, _vert, 0.35))
    _halo = Image.new("L", (LARGEUR, HAUTEUR), 0)
    ImageDraw.Draw(_halo).ellipse((720, -260, 1440, 460), fill=120)
    _halo = _halo.filter(ImageFilter.GaussianBlur(120))
    return Image.composite(Image.new("RGB", (LARGEUR, HAUTEUR), marque), _fond, _halo)


def _fond_image_invitation(octets):
    """L'image de l'invitation recadrée 1200×630 et assombrie à gauche/en bas
    (lisibilité du texte) ; None si absente, trop grosse ou illisible."""
    from PIL import Image, ImageOps
    if not octets or len(octets) > PHOTO_MAX_OCTETS:
        return None
    try:
        _img = Image.open(io.BytesIO(octets))      # INV-3 : en-tête seul, rien n'est décodé ici
        _l, _h0 = _img.size
        # INV-3 (audit P2) : plafond du FOND plus bas que celui de la photo Duo,
        # vérifié AVANT tout décodage (pic mémoire borné) ; au-delà -> fond de marque.
        if _l <= 0 or _h0 <= 0 or _l * _h0 > FOND_MAX_PIXELS:
            return None
        _img.draft("RGB", (LARGEUR * 2, HAUTEUR * 2))
        _img = ImageOps.exif_transpose(_img).convert("RGB")
        # INV-3 : réduction AVANT le recadrage — on ne garde que ce qu'il faut pour
        # couvrir 2× la carte (le côté court reste assez grand pour `fit`).
        _l, _h0 = _img.size
        _echelle = max(LARGEUR * 2.0 / _l, HAUTEUR * 2.0 / _h0)
        if _echelle < 1:
            _img.thumbnail((max(1, int(_l * _echelle + 1)), max(1, int(_h0 * _echelle + 1))), Image.LANCZOS)
        _img = ImageOps.fit(_img, (LARGEUR, HAUTEUR), method=Image.LANCZOS)
    except Exception:  # noqa: BLE001  (image corrompue : fond de marque)
        return None
    # Voile noir : 88 % à gauche -> 38 % à droite, renforcé vers le bas.
    _h = Image.new("L", (256, 1))
    _h.putdata([int(225 - i * 0.5) for i in range(256)])
    _v = Image.new("L", (1, 256))
    _v.putdata([int(max(0, (i - 110)) * 0.9) for i in range(256)])
    _voile = Image.composite(Image.new("L", (LARGEUR, HAUTEUR), 255),
                             _h.resize((LARGEUR, HAUTEUR)), _v.resize((LARGEUR, HAUTEUR)))
    return Image.composite(Image.new("RGB", (LARGEUR, HAUTEUR), (6, 2, 10)), _img, _voile)


def rendre_carte_invitation(donnees=None) -> bytes:
    """INV-3 — JPEG 1200×630 d'une invitation-campagne. Clés lues : titre,
    sous_titre, quand, lieu, cta, prenom, couleur, fond (octets), photo (octets).
    `donnees` vide -> carte « Invitation Afroboost » aux couleurs de marque."""
    from PIL import ImageDraw
    _d = donnees if isinstance(donnees, dict) else {}
    _marque = couleur_valide(_d.get("couleur"))
    _fond = _fond_image_invitation(_d.get("fond")) if _d.get("fond") else None
    if _fond is None:
        _fond = _fond_marque_invitation(_marque)
    _dessin = ImageDraw.Draw(_fond)
    _blanc, _gris = (255, 255, 255), (220, 212, 228)
    _clair = tuple(min(255, int(c + (255 - c) * 0.45)) for c in _marque)
    _largeur = LARGEUR - 160
    _limite = 500                      # rien ne descend sous le CTA / le pied

    _dessin.text((80, 56), "AFROBOOST", font=_police(True, 38), fill=_clair)
    _dessin.text((80 + _dessin.textlength("AFROBOOST", font=_police(True, 38)) + 18, 64), "Invitation",
                 font=_police(False, 30), fill=_gris)

    # Bandeau invitant : photo ronde + « Prénom t'invite ».
    _y = 150
    _prenom = _nettoyer(_d.get("prenom"), 40)
    if "@" in _prenom:
        _prenom = ""
    _photo = _photo_ronde(_d.get("photo"), 72, _marque) if _d.get("photo") else None
    if _photo is not None or _prenom:
        _x = 80
        if _photo is not None:
            _fond.paste(_photo, (80, 122), _photo)
            _x = 80 + _photo.size[0] + 18
        _txt = ("%s t'invite" % _prenom) if _prenom else "On t'invite"
        _pb = _police(True, 34)
        _dessin.text((_x, 148), _tronquer(_dessin, _txt, _pb, LARGEUR - _x - 80), font=_pb, fill=_blanc)
        _y = 236

    # Titre (2 lignes), sous-titre (2 lignes), quand, lieu — tant qu'il y a la place.
    _pt = _police(True, 58)
    for _l in _lignes(_dessin, _nettoyer(_d.get("titre"), 120) or TITRE_INVITATION_DEFAUT, _pt, _largeur, 2):
        _dessin.text((80, _y), _l, font=_pt, fill=_blanc)
        _y += 68
    _y += 8
    _ps = _police(False, 34)
    for _l in _lignes(_dessin, _nettoyer(_d.get("sous_titre"), 160), _ps, _largeur, 2) if _d.get("sous_titre") else []:
        if _y + 42 > _limite:
            break
        _dessin.text((80, _y), _l, font=_ps, fill=_gris)
        _y += 44
    _y += 6
    for _texte, _pl, _coul in ((_nettoyer(_d.get("quand"), 80), _police(True, 34), _clair),
                               (_nettoyer(_d.get("lieu"), 80), _police(False, 30), _gris)):
        if not _texte or _y + 40 > _limite:
            continue
        _dessin.text((80, _y), _tronquer(_dessin, _texte, _pl, _largeur), font=_pl, fill=_coul)
        _y += 48

    # CTA : pilule couleur de marque, en bas à droite.
    _pc = _police(True, 32)
    _cta = _tronquer(_dessin, _nettoyer(_d.get("cta"), 40) or CTA_INVITATION_DEFAUT, _pc, 560)
    _lc = int(_dessin.textlength(_cta, font=_pc)) + 72
    _x0, _y0 = LARGEUR - 80 - _lc, 516
    _dessin.rounded_rectangle((_x0, _y0, _x0 + _lc, _y0 + 68), radius=34, fill=_marque)
    _dessin.text((_x0 + 36, _y0 + 16), _cta, font=_pc, fill=_blanc)

    _dessin.rectangle((0, HAUTEUR - 12, LARGEUR, HAUTEUR), fill=_marque)
    _dessin.text((80, HAUTEUR - 74), "afroboost.com", font=_police(False, 28), fill=_gris)

    _sortie = io.BytesIO()
    _fond.save(_sortie, "JPEG", quality=QUALITE_JPEG, optimize=True, progressive=True)
    return _sortie.getvalue()

# -*- coding: utf-8 -*-
# INV-1 : « Invitation » de la page Campagnes du coach — le moteur PUR.
"""INV-1 — Une INVITATION est un lien partageable avec une carte (OG 1200×630),
PAS une campagne d'envoi. Elle vit dans `referral_campaigns`, JAMAIS dans
`campaigns` (moteur d'envoi massif, non touché) : elle n'a ni destinataires,
ni canal, ni date d'envoi, ni statut « scheduled » — rien qui puisse la faire
entrer dans ce moteur.

Ce module est PUR : aucun réseau, aucune base, aucune horloge implicite. Les
routes (`referral_campaigns_routes.py`) et la page de partage publique
(`share_invite_routes.py`, AGENT 3) l'importent. Les NOMS exportés sont un
contrat : `TYPES`, `STATUTS`, `CHAMPS_VISUELS`, `InvitationCampagneInvalide`,
`valider_entree`, `version_incrementee`, `cible_front`, `dto_public`,
`dto_coach`, `identite_coach`.

Réutilisé tel quel de `referral_engine` (jamais recopié) : `valider_photo_url`
(hôtes admis, dont res.cloudinary.com, et `/api/files/...`), `valider_message`
(280 max), `nom_affichable` (jamais une adresse ni sa partie locale).
"""
import re as _re
from datetime import datetime
from urllib.parse import quote

from api.routes import referral_engine as E

# ─── Le schéma (validé par le propriétaire — rien d'autre) ──────────────────
TYPES = ("trial", "pass_duo", "event_free", "event_paid")
STATUTS = ("draft", "active", "archived")
STATUTS_ENTREE = ("draft", "active")          # `archived` : seulement par POST /archive
SOURCES_IMAGE = ("default", "upload")

# Un changement RÉEL de l'un de ces champs incrémente `version` (-> `?v=N`,
# WhatsApp refait l'aperçu). `share_token` n'en fait JAMAIS partie.
CHAMPS_VISUELS = ("title", "subtitle", "message", "cta_label", "image_url", "image_source",
                  "course_id", "occurrence", "offer_id", "type")

# LISTE BLANCHE des champs acceptés en entrée. Tout le reste est ignoré —
# en particulier `coach_id`, `share_token`, `version`, `inviter_display`, `id`
# (décidés par le serveur) et `scheduled`, `sending`, `recipients`, `channel`,
# `send_at`, `scheduledAt`, `targetType` (vocabulaire du moteur d'envoi).
CHAMPS_ENTREE = ("type", "status") + tuple(c for c in CHAMPS_VISUELS if c != "type")

# Le document complet stocké (schéma fermé).
CHAMPS_DOCUMENT = ("id", "coach_id", "type", "status", "share_token", "version", "title",
                   "subtitle", "message", "cta_label", "image_url", "image_source", "course_id",
                   "occurrence", "offer_id", "inviter_display", "created_at", "updated_at")

TITRE_MAX = 80
SOUS_TITRE_MAX = 120
MESSAGE_MAX = E.MESSAGE_MAX                   # 280, la même borne que le Pass Duo
CTA_MAX = 30
ID_MAX = 64

# Ce que chaque type exige au passage en `active` (en draft : incomplet accepté).
EXIGENCES_ACTIVATION = {
    "trial": ("course_id", "occurrence", "offer_id"),
    "pass_duo": ("course_id", "occurrence"),
    "event_free": ("offer_id",),
    "event_paid": ("offer_id",),
}

MESSAGE_EVENT_PAYANT_BLOQUE = "Événement payant : activation après correction du fuseau horaire des paliers"


class InvitationCampagneInvalide(ValueError):
    """Une valeur d'invitation refusée (422 côté route)."""


# ─── Nettoyage du texte ──────────────────────────────────────────────────────
_RE_BALISE = _re.compile(r"<[^>]*>")
_RE_CONTROLE = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _nettoyer(valeur, champ, maximum, multiligne=False):
    """trim, balises HTML retirées, caractères de contrôle retirés ; None / ""
    -> None ; au-delà de `maximum` -> InvitationCampagneInvalide."""
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise InvitationCampagneInvalide("%s : texte attendu" % champ)
    _v = _RE_BALISE.sub("", valeur)
    _v = _v.replace("<", "").replace(">", "")
    _v = _RE_CONTROLE.sub("", _v)
    if multiligne:
        _v = "\n".join(" ".join(l.split()) for l in _v.replace("\r", "").split("\n")).strip()
    else:
        _v = " ".join(_v.split())
    if not _v:
        return None
    if len(_v) > maximum:
        raise InvitationCampagneInvalide("%s : %d caractères maximum" % (champ, maximum))
    return _v


def _identifiant(valeur, champ):
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise InvitationCampagneInvalide("%s : identifiant texte attendu" % champ)
    _v = valeur.strip()
    if not _v:
        return None
    if len(_v) > ID_MAX or any(c.isspace() for c in _v) or "$" in _v:
        raise InvitationCampagneInvalide("%s : identifiant illisible" % champ)
    return _v


def normaliser_occurrence(valeur):
    """La convention UNIQUE du dépôt (`lot1_occurrence_iso`, comme `referral_passes.occurrence`) :
    « 2026-10-01T18:30:00 », naïf, heure de Zurich. Une valeur avec fuseau est
    CONVERTIE ; une date seule est refusée (l'occurrence se choisit, jamais ne se
    reconstruit). None / "" -> None ; illisible -> InvitationCampagneInvalide."""
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise InvitationCampagneInvalide("occurrence : texte attendu")
    _v = valeur.strip()
    if not _v:
        return None
    if len(_v) < 16 or len(_v) > 40:
        raise InvitationCampagneInvalide("occurrence : date et heure attendues (AAAA-MM-JJTHH:MM)")
    try:
        _d = datetime.fromisoformat(_v.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise InvitationCampagneInvalide("occurrence : date illisible")
    if _d.tzinfo is not None:
        try:
            from zoneinfo import ZoneInfo
            _d = _d.astimezone(ZoneInfo("Europe/Zurich")).replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            raise InvitationCampagneInvalide("occurrence : fuseau horaire illisible")
    return _d.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def valider_image(url, source):
    """(image_url, image_source). `default` -> URL None. `upload` -> URL
    obligatoire, https d'un hôte admis ou `/api/files/...` (règle
    `referral_engine.valider_photo_url`)."""
    if source is not None and source not in SOURCES_IMAGE:
        raise InvitationCampagneInvalide("image_source : %s" % " | ".join(SOURCES_IMAGE))
    if source == "default":
        return None, "default"
    if url is None or (isinstance(url, str) and not url.strip()):
        if source == "upload":
            raise InvitationCampagneInvalide("image_url : requise pour une image envoyée")
        return None, "default"
    try:
        _u = E.valider_photo_url(url)
    except E.InvitationInvalide:
        raise InvitationCampagneInvalide("image_url : adresse refusée (https d'un hôte admis ou fichier Afroboost)")
    if not _u:
        return None, "default"
    return _u, "upload"


# ─── Le contrat ──────────────────────────────────────────────────────────────
def valider_entree(corps, existant=None) -> dict:
    """Liste blanche + validation. Rend les champs MODIFIABLES fusionnés sur
    `existant` : {type, status, title, subtitle, message, cta_label, image_url,
    image_source, course_id, occurrence, offer_id}. Tout autre champ du corps est
    ignoré (jamais stocké). Lève InvitationCampagneInvalide."""
    if not isinstance(corps, dict):
        raise InvitationCampagneInvalide("corps : objet attendu")
    _e = existant if isinstance(existant, dict) else {}
    _s = {c: _e.get(c) for c in CHAMPS_ENTREE}
    _b = {k: corps[k] for k in CHAMPS_ENTREE if k in corps}

    if "type" in _b:
        _s["type"] = _b["type"]
    if _s.get("type") not in TYPES:
        raise InvitationCampagneInvalide("type : %s" % " | ".join(TYPES))

    if "status" in _b:
        if _b["status"] not in STATUTS_ENTREE:
            raise InvitationCampagneInvalide("status : %s" % " | ".join(STATUTS_ENTREE))
        _s["status"] = _b["status"]
    if not _s.get("status"):
        _s["status"] = "draft"

    if "title" in _b:
        _s["title"] = _nettoyer(_b["title"], "title", TITRE_MAX)
    if "subtitle" in _b:
        _s["subtitle"] = _nettoyer(_b["subtitle"], "subtitle", SOUS_TITRE_MAX)
    if "message" in _b:
        _m = _nettoyer(_b["message"], "message", MESSAGE_MAX, multiligne=True)
        try:
            _s["message"] = E.valider_message(_m, "message")
        except E.InvitationInvalide as _err:
            raise InvitationCampagneInvalide(str(_err))
    if "cta_label" in _b:
        _s["cta_label"] = _nettoyer(_b["cta_label"], "cta_label", CTA_MAX)
    if "course_id" in _b:
        _s["course_id"] = _identifiant(_b["course_id"], "course_id")
    if "offer_id" in _b:
        _s["offer_id"] = _identifiant(_b["offer_id"], "offer_id")
    if "occurrence" in _b:
        _s["occurrence"] = normaliser_occurrence(_b["occurrence"])

    if "image_url" in _b or "image_source" in _b:
        _url = _b["image_url"] if "image_url" in _b else _s.get("image_url")
        _src = _b.get("image_source") if "image_source" in _b else None
        if _src is None and "image_url" not in _b:
            _src = _s.get("image_source")
        _s["image_url"], _s["image_source"] = valider_image(_url, _src)
    if _s.get("image_source") not in SOURCES_IMAGE:
        _s["image_source"] = "upload" if _s.get("image_url") else "default"
    if _s["image_source"] == "default":
        _s["image_url"] = None
    return _s


def version_incrementee(avant, apres) -> bool:
    """Un champ VISUEL a-t-il RÉELLEMENT changé ? (None et "" sont égaux.)"""
    _a = avant if isinstance(avant, dict) else {}
    _p = apres if isinstance(apres, dict) else {}
    return any((_a.get(c) or None) != (_p.get(c) or None) for c in CHAMPS_VISUELS)


def champs_manquants(doc) -> list:
    """Ce qui manque pour passer en `active` (vide = complet)."""
    _d = doc or {}
    return [c for c in EXIGENCES_ACTIVATION.get(_d.get("type"), ()) if not _d.get(c)]


def est_publiable(doc) -> bool:
    """Seule une invitation `active` se montre au monde (page de partage, carte)."""
    return isinstance(doc, dict) and doc.get("status") == "active"


# ─── Le prix d'une offre (jamais `price` seul : sentinelle 0 des paliers) ────
def _nombre(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def paliers_offre(offre) -> dict:
    """{early_bird, standard, last_minute} (float|None). Offre à prix progressif
    (V223, `progressive_pricing`) : les trois paliers ; sinon standard = prix."""
    _o = offre or {}
    if _o.get("progressive_pricing") is True:
        return {"early_bird": _nombre(_o.get("price_early_bird")),
                "standard": _nombre(_o.get("price_standard")),
                "last_minute": _nombre(_o.get("price_last_minute"))}
    _p = _nombre(_o.get("active_price"))
    if _p is None:
        _p = _nombre(_o.get("price"))
    return {"early_bird": None, "standard": _p, "last_minute": None}


def offre_gratuite(offre) -> bool:
    """0 CHF CERTAIN. Même lecture que ESSAI-1B (`active_price`, sinon `price`)
    et, pour un prix progressif (où `price` est une sentinelle à 0 — cf.
    `v440_prix_actif`), les TROIS paliers doivent valoir 0. Un inconnu n'est
    jamais « gratuit »."""
    if not isinstance(offre, dict):
        return False
    _vals = [v for v in paliers_offre(offre).values()]
    if offre.get("progressive_pricing") is True:
        return all(v is not None and v == 0 for v in _vals)
    return _vals[1] is not None and _vals[1] == 0


def offre_payante(offre) -> bool:
    """Un prix STRICTEMENT positif est connu (prix simple ou un palier)."""
    if not isinstance(offre, dict):
        return False
    return any(v is not None and v > 0 for v in paliers_offre(offre).values())


# ─── Où le destinataire humain est envoyé ───────────────────────────────────
# INV-2 : la SÉANCE de l'invitation voyage avec le lien. Noms de paramètres
# RÉUTILISÉS : `course` / `occurrence` sont déjà ceux du contexte de séance lu
# par /parrainage (`lireContexteUrl`, frontend/src/utils/parrainage.js).
# Mêmes motifs que la validation du front : hors motif -> rien n'est ajouté.
_RE_SEANCE_COURS = _re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_RE_SEANCE_OCC = _re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")


def _seance_params(doc) -> str:
    """INV-2 — `&course=<id>&occurrence=<AAAA-MM-JJTHH:MM>` (quote), ou "" si
    l'invitation ne porte pas une séance complète et bien formée."""
    _c = doc.get("course_id")
    _occ = doc.get("occurrence")
    if not isinstance(_c, str) or not isinstance(_occ, str):
        return ""
    _c = _c.strip()
    _occ = _occ.strip()[:16]
    if not _RE_SEANCE_COURS.match(_c) or not _RE_SEANCE_OCC.match(_occ):
        return ""
    return "&course=%s&occurrence=%s" % (quote(_c, safe=""), quote(_occ, safe=""))


def cible_front(doc) -> str:
    """Chemin RELATIF du front, par les liens profonds EXISTANTS (App.js) :
    `/?offre=<id>` ouvre la fiche offre ; `&reserver=1` ouvre la réservation —
    SEULEMENT si gratuit (sur une offre payante, Stripe s'ouvrirait seul) ;
    `/parrainage` = Centre Parrainage."""
    _d = doc or {}
    _t = _d.get("type")
    if _t == "pass_duo":
        return "/parrainage?campagne=%s" % quote(str(_d.get("share_token") or ""), safe="")
    _o = quote(str(_d.get("offer_id") or ""), safe="")
    if _t in ("trial", "event_free"):
        return "/?offre=%s&reserver=1%s" % (_o, _seance_params(_d))
    if _t == "event_paid":
        return "/?offre=%s" % _o
    return "/"


# ─── Libellés de date (français, sans année) ────────────────────────────────
def _instant_local(occurrence):
    try:
        return datetime.fromisoformat(str(occurrence or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def date_label(occurrence):
    """« mercredi 1 octobre », ou None."""
    _d = _instant_local(occurrence)
    if _d is None:
        return None
    return "%s %d %s" % (E._JOURS[_d.weekday()], _d.day, E._MOIS[_d.month - 1])


def time_label(occurrence):
    """« 18:30 », ou None."""
    _d = _instant_local(occurrence)
    if _d is None:
        return None
    return "%02d:%02d" % (_d.hour, _d.minute)


# ─── Qui invite ─────────────────────────────────────────────────────────────
def identite_coach(profil) -> dict:
    """`{prenom, photo_url, source:"coach"}` — le prénom passe par
    `nom_affichable` (jamais une adresse ni sa partie locale), la photo par
    `valider_photo_url` (invalide -> None : le front affiche l'avatar Afroboost).
    `profil` : {display_name?, name?, photo_url?, photoUrl?, email?}."""
    _p = profil if isinstance(profil, dict) else {}
    _email = _p.get("email") or ""
    _prenom = ""
    for _cle in ("display_name", "name"):
        _prenom = E.nom_affichable(_p.get(_cle), _email)
        if _prenom:
            break
    _photo = None
    for _cle in ("photo_url", "photoUrl"):
        try:
            _photo = E.valider_photo_url(_p.get(_cle)) if _p.get(_cle) else None
        except E.InvitationInvalide:
            _photo = None
        if _photo:
            break
    return {"prenom": _prenom or "", "photo_url": _photo, "source": "coach"}


def _inviter_public(doc) -> dict:
    """L'identité figée, re-filtrée à la lecture (jamais un champ de plus)."""
    _d = (doc or {}).get("inviter_display")
    if not isinstance(_d, dict):
        return {"prenom": "", "photo_url": None, "source": "afroboost"}
    _photo = _d.get("photo_url")
    try:
        _photo = E.valider_photo_url(_photo) if _photo else None
    except E.InvitationInvalide:
        _photo = None
    _prenom = str(_d.get("prenom") or "")[:E.NOM_INVITATION_MAX]
    if "@" in _prenom:
        _prenom = ""
    _src = _d.get("source") if _d.get("source") in E.SOURCES_INVITANT else "afroboost"
    return {"prenom": _prenom, "photo_url": _photo, "source": _src}


# ─── Les DTO ────────────────────────────────────────────────────────────────
def _version(doc) -> int:
    try:
        return max(1, int((doc or {}).get("version") or 1))
    except (TypeError, ValueError):
        return 1


def dto_public(doc, cours=None, offre=None) -> dict:
    """SANS AUCUNE PII : jamais coach_id, e-mail, téléphone, ni id interne."""
    _d = doc or {}
    _c = cours if isinstance(cours, dict) else {}
    _o = offre if isinstance(offre, dict) else {}
    _occ = _d.get("occurrence") or None
    _lieu = str(_c.get("locationName") or _c.get("location") or _o.get("location") or "").strip()[:160]
    return {
        "type": _d.get("type"),
        "title": _d.get("title") or None,
        "subtitle": _d.get("subtitle") or None,
        "message": _d.get("message") or None,
        "cta_label": _d.get("cta_label") or None,
        "image_url": _d.get("image_url") or None,
        "version": _version(_d),
        "share_token": _d.get("share_token"),
        "occurrence": _occ,
        "date_label": date_label(_occ) if _occ else None,
        "time_label": time_label(_occ) if _occ else None,
        "lieu": _lieu or None,
        "inviter_display": _inviter_public(_d),
        "target_url": cible_front(_d),
        "prix": paliers_offre(_o) if (_d.get("type") == "event_paid" and _o) else None,
    }


def dto_coach(doc, cours=None, offre=None, base_url="https://afroboost.com") -> dict:
    """dto_public + ce dont l'écran du coach a besoin. Pas de coach_id (inutile)."""
    _d = doc or {}
    _base = str(base_url or "https://afroboost.com").rstrip("/")
    _tok = quote(str(_d.get("share_token") or ""), safe="")
    _v = _version(_d)
    _sortie = dto_public(_d, cours, offre)
    _sortie.update({
        "id": _d.get("id"),
        "status": _d.get("status"),
        "image_source": _d.get("image_source") or "default",
        "course_id": _d.get("course_id") or None,
        "offer_id": _d.get("offer_id") or None,
        "created_at": _d.get("created_at"),
        "updated_at": _d.get("updated_at"),
        "share_url": "%s/api/share/invite/%s?v=%d" % (_base, _tok, _v),
        "card_url": "%s/api/share/invite/%s/carte.jpg?v=%d" % (_base, _tok, _v),
    })
    return _sortie

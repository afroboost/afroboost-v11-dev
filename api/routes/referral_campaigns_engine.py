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
                  "course_id", "occurrence", "offer_id", "type",
                  # V607 : le lieu saisi (événements), la vidéo / le mot audio (facultatifs).
                  "lieu", "video_url", "audio_url",
                  # V610d : l'audio APRÈS réservation (boule de neige « Deviens Afroboosteur »)
                  "audio_partage_url")

# LISTE BLANCHE des champs acceptés en entrée. Tout le reste est ignoré —
# en particulier `coach_id`, `share_token`, `version`, `inviter_display`, `id`
# (décidés par le serveur) et `scheduled`, `sending`, `recipients`, `channel`,
# `send_at`, `scheduledAt`, `targetType` (vocabulaire du moteur d'envoi).
CHAMPS_ENTREE = ("type", "status") + tuple(c for c in CHAMPS_VISUELS if c != "type")

# Le document complet stocké (schéma fermé).
CHAMPS_DOCUMENT = ("id", "coach_id", "type", "status", "share_token", "version", "title",
                   "subtitle", "message", "cta_label", "image_url", "image_source", "course_id",
                   "occurrence", "offer_id", "inviter_display", "created_at", "updated_at",
                   "lieu", "video_url", "audio_url", "audio_partage_url")

TITRE_MAX = 80
SOUS_TITRE_MAX = 120
MESSAGE_MAX = E.MESSAGE_MAX                   # 280, la même borne que le Pass Duo
CTA_MAX = 30
ID_MAX = 64
LIEU_MAX = 160
MEDIA_URL_MAX = 600

# Ce que chaque type exige au passage en `active` (en draft : incomplet accepté).
EXIGENCES_ACTIVATION = {
    "trial": ("course_id", "occurrence", "offer_id"),
    "pass_duo": ("course_id", "occurrence"),
    "event_free": ("offer_id",),
    # V607 : un billet se vend pour une DATE et une HEURE précises (les paliers en dépendent).
    "event_paid": ("offer_id", "occurrence"),
}

# V607 : le blocage « fuseau horaire des paliers » est levé (api/pricing.py lit
# désormais l'heure suisse). Le message reste exporté pour les appelants anciens.
MESSAGE_EVENT_PAYANT_BLOQUE = "Événement payant : activation après correction du fuseau horaire des paliers"

# V607 — le libellé FR de chaque champ, pour dire QUEL champ manque.
LIBELLES_CHAMPS = {
    "course_id": "la séance (cours)", "occurrence": "la date et l'heure", "offer_id": "l'offre",
    "lieu": "le lieu", "title": "le titre", "cta_label": "le texte du bouton",
}


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


def valider_media_url(valeur, champ):
    """V607 — vidéo / audio : un fichier Afroboost (`/api/files/...`) ou une
    adresse https (la bibliothèque Médias rend l'un ou l'autre). Jamais `//hôte`,
    jamais d'espace ni de guillemet (l'URL finit dans un attribut HTML)."""
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise InvitationCampagneInvalide("%s : adresse texte attendue" % champ)
    _v = valeur.strip()
    if not _v:
        return None
    if len(_v) > MEDIA_URL_MAX or any(c in _v for c in ' \t\n\r"\'<>\\'):
        raise InvitationCampagneInvalide("%s : adresse refusée" % champ)
    if _v.startswith("/api/files/") and not _v.startswith("//"):
        return _v
    if _re.match(r"^https://[A-Za-z0-9.-]+(:\d+)?/", _v):
        return _v
    raise InvitationCampagneInvalide("%s : adresse refusée (https ou fichier Afroboost)" % champ)


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
    if "lieu" in _b:
        _s["lieu"] = _nettoyer(_b["lieu"], "lieu", LIEU_MAX)
    if "video_url" in _b:
        _s["video_url"] = valider_media_url(_b["video_url"], "video_url")
    if "audio_url" in _b:
        _s["audio_url"] = valider_media_url(_b["audio_url"], "audio_url")
    if "audio_partage_url" in _b:
        _s["audio_partage_url"] = valider_media_url(_b["audio_partage_url"], "audio_partage_url")

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
    # V607 — un champ SANS OBJET pour le type est vidé (changement de type d'un
    # brouillon : Événement payant -> Essai ne garde ni lieu saisi ni billet).
    if _s.get("type") not in ("event_free", "event_paid"):
        _s["lieu"] = None
    if _s.get("type") == "pass_duo":
        _s["offer_id"] = None
    # V610d : l'audio d'APRÈS réservation n'existe que pour l'événement payant.
    if _s.get("type") != "event_paid":
        _s["audio_partage_url"] = None
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


# ─── V607 : le billet d'un ÉVÉNEMENT PAYANT ─────────────────────────────────
# Ce que le menu « Offre payante de l'événement » propose : un BILLET, pas un
# abonnement. Filtre PROPRE à l'événement payant : les autres types gardent
# leur propre règle (`offre_gratuite`), le catalogue n'est pas touché.
TYPES_OFFRE_NON_BILLET = ("subscription", "pack", "membership", "product")
MODES_PAIEMENT_BILLET = (None, "", "unique")


def raison_offre_non_billet(offre):
    """None si l'offre peut servir de billet d'événement, sinon la raison (FR)."""
    if not isinstance(offre, dict):
        return "offre introuvable"
    if not offre_payante(offre):
        return "offre gratuite"
    if offre.get("archived") is True:
        return "offre archivée"
    if offre.get("visible") is False:
        return "offre masquée"
    if offre.get("link_only") is True:
        return "offre privée"
    if offre.get("isProduct") is True:
        return "produit"
    if offre.get("offer_type") in TYPES_OFFRE_NON_BILLET:
        return "abonnement, pack ou carte membre"
    if offre.get("billing_mode") not in MODES_PAIEMENT_BILLET:
        return "abonnement (paiement récurrent ou échelonné)"
    if offre.get("creates_membership") is True or offre.get("requires_active_membership") is True:
        return "offre membres"
    if offre.get("duree_mois"):
        return "abonnement (durée en mois)"
    return None


def offre_billet_evenement(offre) -> bool:
    return raison_offre_non_billet(offre) is None


# Les noms des 3 paliers, tels que Bassi les veut sur l'invitation.
LIBELLES_PALIER = {"early_bird": "Tarif lancement", "standard": "Tarif standard",
                   "last_minute": "Dernière minute", "regular": "Tarif"}


def prix_actif(offre, maintenant=None):
    """V607 — LE prix encaissé MAINTENANT (le même calcul que le checkout :
    `api.pricing.compute_active_price`, heure suisse) + les paliers + la bascule
    suivante. None si l'offre n'a pas de prix positif. Pur (`maintenant` injectable)."""
    if not isinstance(offre, dict):
        return None
    from datetime import timezone as _tz
    from api.pricing import compute_active_price, tier_boundaries
    try:
        _r = compute_active_price(offre, now=maintenant)
    except Exception:  # noqa: BLE001
        return None
    _prix = _nombre(_r.get("price"))
    if _prix is None or _prix <= 0:
        return None
    _palier = _r.get("tier") or "regular"
    _sortie = {"prix": _prix, "palier": _palier,
               "libelle": (offre.get("label_" + _palier) if _palier != "regular" else None)
               or LIBELLES_PALIER.get(_palier, "Tarif"),
               "devise": "CHF", "paliers": [], "prochain": None}
    if offre.get("progressive_pricing") is True and _palier != "regular":
        # V607e : les MÊMES bornes que le checkout (jours = calendrier suisse).
        _b = tier_boundaries(offre)
        _fin = {"early_bird": _b["early_bird_end"], "standard": _b["standard_end"]} if _b else {}
        _ordre = ("early_bird", "standard", "last_minute")
        for _k in _ordre:
            _p = _nombre(offre.get("price_" + _k))
            if _p is None:
                continue
            _sortie["paliers"].append({"palier": _k, "libelle": offre.get("label_" + _k) or LIBELLES_PALIER[_k],
                                       "prix": _p, "actif": _k == _palier})
        _i = _ordre.index(_palier) if _palier in _ordre else -1
        if 0 <= _i < 2 and _palier in _fin:
            _suiv = _ordre[_i + 1]
            _ps = _nombre(offre.get("price_" + _suiv))
            if _ps is not None and _ps > _prix:
                _sortie["prochain"] = {"palier": _suiv, "prix": _ps,
                                       "a_partir_de": _fin[_palier].astimezone(_tz.utc).isoformat()}
    return _sortie


def libelle_prix(prix) -> str:
    """« 25 CHF » / « 12.50 CHF »."""
    _p = _nombre(prix)
    if _p is None:
        return ""
    return "%s CHF" % (int(_p) if float(_p).is_integer() else ("%.2f" % _p))


def offre_payante(offre) -> bool:
    """Un prix STRICTEMENT positif est connu (prix simple ou un palier)."""
    if not isinstance(offre, dict):
        return False
    return any(v is not None and v > 0 for v in paliers_offre(offre).values())


# ─── INV-5 : la séance que le lien profond peut RÉELLEMENT annoncer ─────────
# Copie Python EXACTE de `verdictSeanceInvitation` (frontend/src/utils/
# invitationSeance.js, INV-2) : ce que le front refuserait (« La séance de ton
# invitation n'est plus disponible »), le serveur le refuse à l'activation.
_RE_HEURE = _re.compile(r"^\s*(\d{1,2})\s*[:hH.]\s*(\d{2})")


def cours_public(cours) -> bool:
    """Le cours est-il servi au public ? `GET /courses` retire `archived: true`,
    la vitrine retire `visible: false` (App.js `baseCourses`, `v225EnrichedOffers`)."""
    return isinstance(cours, dict) and cours.get("visible") is not False and cours.get("archived") is not True


def cours_lies(offre) -> list:
    """Les cours rattachés à l'offre (`linked_course_ids`), sans valeur vide."""
    _l = (offre or {}).get("linked_course_ids") if isinstance(offre, dict) else None
    return [str(c) for c in _l if c] if isinstance(_l, list) else []


def cours_rattache(offre, cours_id) -> bool:
    """INV-2 : une offre qui LISTE ses cours n'accepte qu'eux ; une offre qui
    n'en liste aucun accepte tout cours public."""
    _l = cours_lies(offre)
    return not _l or str(cours_id or "") in _l


def _heure(t) -> str:
    _m = _RE_HEURE.match(str(t or ""))
    if not _m:
        return ""
    _h, _mn = int(_m.group(1)), int(_m.group(2))
    if _h > 23 or _mn > 59:
        return ""
    return "%02d:%02d" % (_h, _mn)


def seance_du_cours(cours, occurrence) -> bool:
    """L'occurrence (« AAAA-MM-JJTHH:MM[:SS] », heure de Zurich) est-elle une
    séance de CE cours ? Même heure ; même date si le cours est à date fixe,
    sinon même jour de semaine (convention des cours : JS, Dim=0..Sam=6)."""
    if not isinstance(cours, dict):
        return False
    try:
        _d = datetime.fromisoformat(str(occurrence or "")[:19])
    except (TypeError, ValueError):
        return False
    if _heure(cours.get("time")) != "%02d:%02d" % (_d.hour, _d.minute):
        return False
    _fixe = cours.get("date").strip()[:10] if isinstance(cours.get("date"), str) else ""
    if _fixe:
        return _fixe == _d.strftime("%Y-%m-%d")
    _v610_annules = cours.get("dates_annulees")      # V610 : jour annulé du cours récurrent
    if isinstance(_v610_annules, list) and _d.strftime("%Y-%m-%d") in {str(x).strip()[:10] for x in _v610_annules if x}:
        return False
    try:
        _wd = int(cours.get("weekday"))
    except (TypeError, ValueError):
        return False
    return 0 <= _wd <= 6 and (_d.weekday() + 1) % 7 == _wd


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


# PAR-1 : le jeton d'une campagne dans `/duo/c/<jeton>` — même motif que la
# route du front (`^\/duo\/c\/([A-Za-z0-9_-]+)\/?$`) ; hors motif -> lien d'avant.
_RE_JETON_CAMPAGNE = _re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def cible_chaine(doc) -> str:
    """PAR-1 — `/duo/c/<share_token>` pour une campagne `trial` qui porte une
    séance COMPLÈTE (la racine de chaîne P0 est créée sur CETTE séance) ; ""
    sinon (le lien d'avant s'applique)."""
    _d = doc or {}
    if _d.get("type") != "trial" or not _seance_params(_d):
        return ""
    _tok = str(_d.get("share_token") or "").strip()
    if not _RE_JETON_CAMPAGNE.match(_tok):
        return ""
    return "/duo/c/%s" % _tok


def cible_front(doc, chaine=False) -> str:
    """Chemin RELATIF du front, par les liens profonds EXISTANTS (App.js) :
    `/?offre=<id>` ouvre la fiche offre ; `&reserver=1` ouvre la réservation —
    SEULEMENT si gratuit (sur une offre payante, Stripe s'ouvrirait seul) ;
    `/parrainage` = Centre Parrainage.
    PAR-1 : `chaine=True` (drapeaux lus par l'appelant) -> une campagne `trial`
    complète mène à `/duo/c/<jeton>` (entrée dans la chaîne V556)."""
    _d = doc or {}
    _t = _d.get("type")
    if chaine:
        _c = cible_chaine(_d)
        if _c:
            return _c
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


def dto_public(doc, cours=None, offre=None, chaine=False) -> dict:
    """SANS AUCUNE PII : jamais coach_id, e-mail, téléphone, ni id interne."""
    _d = doc or {}
    _c = cours if isinstance(cours, dict) else {}
    _o = offre if isinstance(offre, dict) else {}
    _occ = _d.get("occurrence") or None
    # V607 : le lieu SAISI sur l'invitation (événement) passe avant celui du cours / de l'offre.
    _lieu = str(_d.get("lieu") or _c.get("locationName") or _c.get("location") or _o.get("location") or "").strip()[:160]
    _type = _d.get("type")
    _pa = prix_actif(_o) if (_type == "event_paid" and _o) else None
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
        "target_url": cible_front(_d, chaine),       # PAR-1 : `chaine` lu par l'appelant
        "prix": paliers_offre(_o) if (_d.get("type") == "event_paid" and _o) else None,
        # V607 — ce que la carte, la page, WhatsApp et le checkout disent du prix.
        "prix_actif": _pa,
        "gratuit": _type in ("trial", "event_free"),
        "mention_prix": (("%s · %s" % (libelle_prix(_pa["prix"]), _pa["libelle"])) if _pa
                         else ("Offert" if _type == "trial" else ("Gratuit" if _type == "event_free" else None))),
        "offre_nom": (str(_o.get("name") or "").strip()[:120] or None) if _o else None,
        "video_url": _d.get("video_url") or None,
        "audio_url": _d.get("audio_url") or None,
        # V610d : écouté APRÈS la réservation (bloc « Deviens Afroboosteur »), jamais avant.
        "audio_partage_url": (_d.get("audio_partage_url") or None) if _d.get("type") == "event_paid" else None,
        "cours_nom": (str(_c.get("name") or "").strip()[:120] or None) if _c else None,
        # V610 : gratuité accordée à certains abonnements actifs (liste d'offres
        # configurée sur l'offre-événement). AUCUNE capacité : pas de plafond de places.
        "gratuit_membres": bool(_o and isinstance(_o.get("gratuit_abonnements_offer_ids"), list)
                                and any(_o.get("gratuit_abonnements_offer_ids"))),
    }


def dto_coach(doc, cours=None, offre=None, base_url="https://afroboost.com", chaine=False) -> dict:
    """dto_public + ce dont l'écran du coach a besoin. Pas de coach_id (inutile)."""
    _d = doc or {}
    _base = str(base_url or "https://afroboost.com").rstrip("/")
    _tok = quote(str(_d.get("share_token") or ""), safe="")
    _v = _version(_d)
    _sortie = dto_public(_d, cours, offre, chaine)
    _sortie.update({
        "id": _d.get("id"),
        "status": _d.get("status"),
        "image_source": _d.get("image_source") or "default",
        "course_id": _d.get("course_id") or None,
        "offer_id": _d.get("offer_id") or None,
        "created_at": _d.get("created_at"),
        "updated_at": _d.get("updated_at"),
        # V607 : le lien COURT public (`/i/<jeton>`) ; l'ancien reste servi (`share_url_api`).
        "share_url": "%s/i/%s?v=%d" % (_base, _tok, _v),
        "share_url_api": "%s/api/share/invite/%s?v=%d" % (_base, _tok, _v),
        "lieu_saisi": _d.get("lieu") or None,
        "card_url": "%s/api/share/invite/%s/carte.jpg?v=%d" % (_base, _tok, _v),
    })
    return _sortie

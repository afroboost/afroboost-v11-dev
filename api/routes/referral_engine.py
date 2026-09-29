# -*- coding: utf-8 -*-
# V534: Centre Parrainage unique — MOTEUR PUR du Pass Duo.
"""V534 — Pass Duo : la machine d'états et les projections, SANS la moindre I/O.

POURQUOI UN MODULE À PART. Tout ce qui décide (états, refus, textes, KPI) vit
ici, en fonctions pures : aucune base, aucun réseau, aucune horloge implicite
(`now` est toujours passé en argument). Les routes (`referral_routes.py`) ne
font que lire, appeler ceci, puis écrire. C'est ce qui rend chaque règle
testable sans Mongo, et ce qui empêche qu'une règle dérive entre l'écran du
parrain, la page publique de l'invité et le cockpit admin.

LES ÉTATS (contrat §4) :
  locked            créé, aucune invitation
  waiting           au moins une invitation journalisée OU lien ouvert
  friend_registered l'ami est inscrit (essai octroyé + SA réservation), la
                    place du parrain n'est pas confirmée
  unlocked          les DEUX réservations existent
  used              dérivé en lecture : les deux réservations validées
  expired           dérivé en lecture : occurrence passée, pass jamais débloqué
  cancelled         annulé par le parrain (jamais depuis unlocked/used)
"""
import re as _re  # V551 : forme des URL de fichiers
from datetime import datetime, timezone

VERSION = "V534b"

# ─── États et libellés ───────────────────────────────────────────────────────
LOCKED = "locked"
WAITING = "waiting"
FRIEND_REGISTERED = "friend_registered"
UNLOCKED = "unlocked"
USED = "used"
EXPIRED = "expired"
CANCELLED = "cancelled"

ETATS = (LOCKED, WAITING, FRIEND_REGISTERED, UNLOCKED, USED, EXPIRED, CANCELLED)

# Les états dans lesquels le pass est encore « vivant » côté parrain : c'est
# sur eux que porte l'index unique partiel (sponsor, cours, occurrence).
ETATS_ACTIFS = (LOCKED, WAITING, FRIEND_REGISTERED, UNLOCKED)
# Les états depuis lesquels un ami peut encore rejoindre.
ETATS_OUVERTS_AU_JOIN = (LOCKED, WAITING)
# Les états qui expirent quand l'occurrence passe sans déblocage.
ETATS_EXPIRABLES = (LOCKED, WAITING, FRIEND_REGISTERED)
# Les états depuis lesquels le parrain peut annuler.
ETATS_ANNULABLES = (LOCKED, WAITING, FRIEND_REGISTERED)

LIBELLES = {
    LOCKED: "Verrouillé",
    WAITING: "En attente de ton ami",
    FRIEND_REGISTERED: "Ami inscrit",
    UNLOCKED: "Débloqué",
    USED: "Participation validée",
    EXPIRED: "Expiré",
    CANCELLED: "Annulé",
}

TRANSITIONS = {
    LOCKED: (WAITING, FRIEND_REGISTERED, UNLOCKED, CANCELLED, EXPIRED),
    WAITING: (FRIEND_REGISTERED, UNLOCKED, CANCELLED, EXPIRED),
    FRIEND_REGISTERED: (UNLOCKED, CANCELLED, EXPIRED),
    UNLOCKED: (USED,),
    USED: (),
    EXPIRED: (),
    CANCELLED: (),
}

# Canaux d'invitation acceptés (contrat §3).
CANAUX = ("whatsapp", "copy", "qr", "share", "share_image")   # V556 : + partage natif avec la carte

# Motifs de refus du join (contrat §5), portés par l'en-tête X-Refus-Raison.
REFUS_AUTO_PARRAINAGE = "auto_parrainage"
REFUS_DEJA_FILLEUL = "deja_filleul_occurrence"
REFUS_ABONNE_ACTIF = "abonne_actif"
REFUS_PASS_FERME = "pass_ferme"

BLOCAGE_SPONSOR_SANS_SEANCE = "sponsor_sans_seance"
BLOCAGE_CONDITIONS = "conditions_non_acceptees"

ROLE_SPONSOR = "sponsor"
ROLE_INVITEE = "invitee"

# ─── V534b : l'offre du pass ─────────────────────────────────────────────────
# Qui a changé l'offre (`offer_history[].changed_by`).
CHANGE_PAR = ("sponsor", "invitee", "coach", "admin")
# Les états dans lesquels l'offre du pass peut encore changer (avenant §4.2).
ETATS_OFFRE_MODIFIABLE = (LOCKED, WAITING, FRIEND_REGISTERED, UNLOCKED)
# Raisons 400 de `_offre_autorisee` (en-tête X-Refus-Raison).
REFUS_OFFRE_REQUISE = "offre_requise"
REFUS_OFFRE_NON_AUTORISEE = "offre_non_autorisee"
REFUS_OFFRE_INACTIVE = "offre_inactive"
REFUS_OFFRE_PAYANTE = "offre_payante"
REFUS_OFFRE_AUTRE_COACH = "offre_autre_coach"
# Raisons 409 du changement d'offre.
REFUS_PASS_NON_MODIFIABLE = "pass_non_modifiable"
REFUS_CONFLIT_VERSION = "conflit_version"
REFUS_PASS_DEJA_REJOINT = "pass_deja_rejoint"
# Le texte EXACT de l'avenant pour un pass `used`.
TEXTE_OFFRE_UTILISEE = ("Cette offre a déjà été utilisée. Tu peux choisir une autre offre "
                        "pour une prochaine réservation si elle est disponible.")
TEXTE_PRESENCE_VALIDEE = ("Une présence a déjà été validée sur ce Pass Duo : "
                          "son offre ne peut plus changer.")
CONDITIONS_MAX = 200
EVENEMENT_OFFRE = "offer_changed"
MOTIF_CHANGEMENT_OFFRE = "pass_duo_offer_change"   # `cancel_reason`, marques rollback

# Libellés FR de l'historique (`events[].type` -> phrase).
LIBELLES_EVENEMENTS = {
    "pass_created": "Pass Duo créé",
    "invitation_sent": "Invitation envoyée",
    "link_opened": "Lien ouvert par ton ami",
    "friend_registered": "Ami inscrit",
    "sponsor_blocked": "Ta place attend une recharge",
    "unlocked": "Pass débloqué : deux places réservées",
    "used": "Participation validée",
    "expired": "Pass expiré",
    "cancelled": "Pass annulé",
    EVENEMENT_OFFRE: "Offre modifiée",
    "offer_change_failed": "Changement d'offre annulé : l'offre précédente est conservée",
    # PAR-3 (A4) : les deux événements de chaîne V556 s'affichaient bruts dans l'historique.
    "chain_shared": "Invitation partagée",
    "chain_child_created": "Invitation de ton ami préparée",
}

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
         "août", "septembre", "octobre", "novembre", "décembre")


class TransitionInvalide(ValueError):
    """Une transition que la machine n'autorise pas."""


# ─── Normalisations ──────────────────────────────────────────────────────────
def normaliser_email(valeur) -> str:
    """Trim + minuscules, rien d'autre — même règle que `shared.normaliser_email`."""
    if not isinstance(valeur, str):
        return ""
    return valeur.strip().lower()


def prenom(nom) -> str:
    """Le premier mot d'un nom, borné. Jamais une adresse e-mail."""
    _n = str(nom or "").strip()
    if not _n or "@" in _n:
        return ""
    return _n.split()[0][:40]


# ─── V551 : LE NOM QU'ON MONTRE N'EST JAMAIS UN IDENTIFIANT ─────────────────
#
# Beaucoup de fiches ont été créées avec `name = email.split("@")[0]` : le nom
# « bassicustomshoes » partait alors dans l'aperçu WhatsApp. On ne réécrit PAS
# les données : on filtre ce qu'on AFFICHE, partout, avec cette seule fonction.
def _sans_accents(texte) -> str:
    import unicodedata
    _n = unicodedata.normalize("NFKD", str(texte or ""))
    return "".join(c for c in _n if not unicodedata.combining(c)).casefold()


def _capitaliser(mot) -> str:
    """« léa » -> « Léa », « JEAN-PIERRE » -> « Jean-Pierre » ; une casse déjà
    mixte (« McLean ») est respectée."""
    _m = str(mot or "")
    if _m != _m.lower() and _m != _m.upper():
        return _m
    return "-".join(p[:1].upper() + p[1:].lower() for p in _m.split("-"))


def nom_affichable(nom, email_norm) -> str:
    """V551 — "" si vide, contient « @ », égal (sans casse ni accents) à la
    partie locale de l'e-mail, ou ressemble à un identifiant (aucune lettre, ou
    >= 20 caractères sans espace) ; sinon le premier mot, capitalisé. Pure."""
    _n = str(nom or "").strip()
    if not _n or "@" in _n:
        return ""
    _local = normaliser_email(email_norm).split("@")[0] if "@" in normaliser_email(email_norm) else ""
    _cle = _sans_accents(_n)
    _premier = _n.split()[0]
    if _local and (_cle == _sans_accents(_local) or _sans_accents(_premier) == _sans_accents(_local)):
        return ""
    if not any(c.isalpha() for c in _n):
        return ""
    if len(_n) >= 20 and not any(c.isspace() for c in _n):
        return ""
    return _capitaliser(_premier)[:40]


# ─── V551 : l'invitation personnalisée d'un pass ────────────────────────────
MESSAGE_INVITATION_DEFAUT = "Je t'invite à venir essayer Afroboost avec moi. Réserve ta place ici :"
MESSAGE_MAX = 280
NOM_INVITATION_MAX = 40
PHOTO_URL_MAX = 500
HOTES_PHOTO = ("afroboost.com", "firebasestorage.googleapis.com", "storage.googleapis.com",
               "lh3.googleusercontent.com",
               # L0 (29/09) : beaucoup de photos de profil sont sur Cloudinary ; sans cet hôte,
               # elles étaient refusées SANS erreur et n'apparaissaient nulle part.
               "res.cloudinary.com")
_RE_FICHIER = _re.compile(r"^/api/files/[A-Za-z0-9_-]+/[^/?#]+$")


class InvitationInvalide(ValueError):
    """Une valeur d'invitation refusée (422 côté route)."""


def url_image_partage_valide(url) -> bool:
    """V551 — seule forme admise pour l'image de partage d'un coach : un de NOS
    fichiers (`/api/files/<id>/<nom>`), jamais une URL externe ni un `..`."""
    if not isinstance(url, str) or not _RE_FICHIER.match(url):
        return False
    _nom = url.rsplit("/", 1)[-1]
    return _nom not in (".", "..") and ".." not in url and "\\" not in url and "%" not in url \
        and not any(c.isspace() for c in url)


def valider_message(valeur, champ="message"):
    """trim ; None / "" -> None ; > 280 -> InvitationInvalide."""
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise InvitationInvalide("%s : texte attendu" % champ)
    _v = valeur.strip()
    if not _v:
        return None
    if len(_v) > MESSAGE_MAX:
        raise InvitationInvalide("%s : %d caractères maximum" % (champ, MESSAGE_MAX))
    return _v


def valider_nom_invitation(valeur):
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise InvitationInvalide("display_name : texte attendu")
    _v = " ".join(valeur.split())
    if not _v or len(_v) > NOM_INVITATION_MAX:
        raise InvitationInvalide("display_name : entre 1 et %d caractères" % NOM_INVITATION_MAX)
    if "@" in _v:
        raise InvitationInvalide("display_name : une adresse e-mail n'est pas un nom")
    return _v


def valider_photo_url(valeur):
    if valeur is None:
        return None
    if not isinstance(valeur, str):
        raise InvitationInvalide("photo_url : texte attendu")
    _v = valeur.strip()
    if not _v:
        return None
    if len(_v) > PHOTO_URL_MAX:
        raise InvitationInvalide("photo_url : trop longue")
    if url_image_partage_valide(_v):
        return _v
    from urllib.parse import urlsplit
    try:
        _u = urlsplit(_v)
    except ValueError:
        raise InvitationInvalide("photo_url : adresse illisible")
    _hote = (_u.hostname or "").lower()
    if _u.scheme != "https" or _hote not in HOTES_PHOTO or _u.username or _u.password \
            or any(c.isspace() for c in _v):
        raise InvitationInvalide("photo_url : hôte non autorisé")
    return _v


def valider_invitation(corps, existante=None) -> dict:
    """Fusionne les champs PRÉSENTS de `corps` sur l'invitation existante.
    Rend `{display_name, photo_url, message}` ; lève InvitationInvalide."""
    if not isinstance(corps, dict):
        raise InvitationInvalide("invitation : objet attendu")
    _e = existante if isinstance(existante, dict) else {}
    _sortie = {"display_name": _e.get("display_name"), "photo_url": _e.get("photo_url"),
               "message": _e.get("message")}
    if "display_name" in corps:
        _sortie["display_name"] = valider_nom_invitation(corps.get("display_name"))
    if "photo_url" in corps:
        _sortie["photo_url"] = valider_photo_url(corps.get("photo_url"))
    if "message" in corps:
        _sortie["message"] = valider_message(corps.get("message"))
    return _sortie


def version_invitation(pass_doc) -> int:
    try:
        return max(0, int((pass_doc or {}).get("invitation_version") or 0))
    except (TypeError, ValueError):
        return 0


def invitation_du_pass(pass_doc) -> dict:
    """`{display_name, photo_url, message, version}` — null partout, version 0,
    pour un pass sans invitation (rétro-compatible)."""
    _i = (pass_doc or {}).get("invitation")
    _i = _i if isinstance(_i, dict) else {}
    return {"display_name": _i.get("display_name") or None, "photo_url": _i.get("photo_url") or None,
            "message": _i.get("message") or None, "version": version_invitation(pass_doc)}


def nom_parrain_affichable(pass_doc) -> str:
    """Le nom montré au monde : celui choisi pour l'invitation, sinon le prénom
    réel FILTRÉ (jamais une adresse ni sa partie locale), sinon ""."""
    _i = invitation_du_pass(pass_doc)
    if _i["display_name"]:
        return _i["display_name"]
    _sp = (pass_doc or {}).get("sponsor") or {}
    return nom_affichable(_sp.get("name"), _sp.get("email_norm"))


# ─── L0 (29/09) : QUI invite — figé côté serveur, sans donnée personnelle ─────────
# Règle : invitation d'un MEMBRE -> photo choisie pour l'invitation, sinon photo de son
# profil ; aucune -> avatar Afroboost (photo None). Jamais la photo du coach à la place
# d'un membre (« coach » est réservé à une invitation directe du coach).
SOURCES_INVITANT = ("member", "coach", "afroboost")


def identite_invitant(pass_doc, photo_profil=None) -> dict:
    """`{prenom, photo_url, source}` (pure). `photo_profil` : URL de la photo de profil
    du membre invitant (lue par la route), revalidée ici."""
    _p = pass_doc or {}
    _prenom = nom_parrain_affichable(_p) or ""
    _photo = invitation_du_pass(_p)["photo_url"]
    if not _photo and photo_profil:
        try:
            _photo = valider_photo_url(photo_profil)
        except InvitationInvalide:
            _photo = None
    _membre = bool(_prenom or _photo or (_p.get("sponsor") or {}).get("name"))
    return {"prenom": _prenom, "photo_url": _photo or None, "source": "member" if _membre else "afroboost"}


def inviter_display_du_pass(pass_doc) -> dict:
    """L'identité montrée au monde. Le choix EXPLICITE de l'invitation (prénom, photo)
    prime toujours ; l'identité FIGÉE ne complète que ce qui manque (photo de profil).
    Anciens pass (sans identité figée) : même photo que l'invitation -> même carte."""
    _vif = identite_invitant(pass_doc)
    _d = (pass_doc or {}).get("inviter_display")
    if not (isinstance(_d, dict) and _d.get("source") in SOURCES_INVITANT):
        return _vif
    _photo = _d.get("photo_url")
    try:
        _photo = valider_photo_url(_photo) if _photo else None
    except InvitationInvalide:
        _photo = None
    return {"prenom": _vif["prenom"] or str(_d.get("prenom") or "")[:NOM_INVITATION_MAX],
            "photo_url": _vif["photo_url"] or _photo,
            "source": _d["source"] if _d["source"] != "afroboost" else _vif["source"]}


def version_apercu(pass_doc) -> int:
    """V556 — compteur d'APERÇU : +1 à chaque partage déclenché. Ne touche ni
    au jeton, ni au filleul, ni aux crédits : il ne sert qu'au cache WhatsApp."""
    try:
        return max(0, int((pass_doc or {}).get("preview_version") or 0))
    except (TypeError, ValueError):
        return 0


def version_partage(pass_doc) -> int:
    """V556 — le `v` de la share_url = invitation_version + preview_version.
    Deux compteurs qui ne font que monter : leur somme monte dès que l'un
    bouge, donc un partage n'a JAMAIS l'URL du partage précédent."""
    return version_invitation(pass_doc) + version_apercu(pass_doc)


def url_partage_versionnee(frontend_url, pass_doc) -> str:
    """`share_url` : inchangée si aucune version (0), sinon `?v=N` — même
    jeton, mais une URL neuve pour le cache d'aperçu de WhatsApp.
    V556 : N = `version_partage` (invitation + aperçu)."""
    _p = pass_doc or {}
    _url = partage_url(frontend_url, _p.get("share_token"))
    _v = version_partage(_p)
    return ("%s?v=%d" % (_url, _v)) if _v > 0 else _url


# V552: ─── LA CARTE SOCIALE — une URL qui change quand le CONTENU change ───
#
# Le `share_token` ne change jamais. La carte, elle, doit changer d'URL dès que
# ce qu'elle montre change (WhatsApp garde une image par URL, des jours) : la
# version est une empreinte courte de TOUT ce qui entre dans le dessin, plus
# `CARTE_GABARIT` (on l'incrémente quand le dessin lui-même change).
CARTE_GABARIT = "1"


def version_carte(pass_doc) -> str:
    """Empreinte stable (12 hexa) : gabarit, invitation_version, occurrence,
    offre, cours, lieu, nom affiché, photo, message. Pure."""
    import hashlib
    import json
    _p = pass_doc or {}
    _i = invitation_du_pass(_p)
    _c = _p.get("course_snapshot") or {}
    _o = _p.get("offer_snapshot") or {}
    _cle = [CARTE_GABARIT, version_invitation(_p), str(_p.get("occurrence") or ""),
            str(_p.get("offer_id") or _o.get("id") or ""), str(_o.get("name") or ""),
            str(_p.get("course_id") or ""), str(_c.get("name") or ""), str(_c.get("locationName") or ""),
            nom_parrain_affichable(_p), _i["photo_url"] or "", _i["message"] or ""]
    # V556 : la version d'aperçu entre dans l'empreinte SEULEMENT si elle
    # existe — les cartes déjà partagées (compteur absent) gardent leur URL.
    if version_apercu(_p) > 0:
        _cle.append("apercu:%d" % version_apercu(_p))
    # L0 : la photo de l'invitant n'entre dans l'empreinte QUE si elle diffère de celle de
    # l'invitation (photo de profil utilisée) — les anciens liens gardent leur version.
    _idt = inviter_display_du_pass(_p)
    if _idt["photo_url"] and _idt["photo_url"] != (_i["photo_url"] or None):
        _cle.append("invitant:%s" % _idt["photo_url"])
    return hashlib.sha256(json.dumps(_cle, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def url_carte(frontend_url, pass_doc) -> str:
    """`<front>/api/share/duo/<token>/carte.jpg?v=<version>` ; "" sans jeton."""
    _p = pass_doc or {}
    _tok = str(_p.get("share_token") or "").strip()
    if not _tok:
        return ""
    return "%s/carte.jpg?v=%s" % (partage_url(frontend_url, _tok), version_carte(_p))


def cle_pass(sponsor_email, course_id, occurrence) -> tuple:
    """La clé d'unicité d'un pass actif : (parrain, cours, occurrence)."""
    return (normaliser_email(sponsor_email), str(course_id or "").strip(),
            str(occurrence or "").strip())


# ─── Temps ───────────────────────────────────────────────────────────────────
def instant(valeur):
    """Un `datetime` aware UTC depuis une ISO (naïve = heure suisse, comme le
    reste du dépôt : `_a0_horodatage`), ou None si illisible. Pure."""
    from datetime import timedelta
    if isinstance(valeur, datetime):
        _d = valeur
    else:
        try:
            _d = datetime.fromisoformat(str(valeur or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if _d.tzinfo is None:
        try:
            from zoneinfo import ZoneInfo
            _d = _d.replace(tzinfo=ZoneInfo("Europe/Zurich"))
        except Exception:
            _d = _d.replace(tzinfo=timezone(timedelta(hours=2)))
    return _d.astimezone(timezone.utc)


def est_passee(occurrence_iso, now) -> bool:
    """L'occurrence est-elle derrière nous ? Une valeur illisible vaut « passée »
    (fail-closed : on ne fabrique pas de billet pour une date inconnue)."""
    _d = instant(occurrence_iso)
    _n = instant(now) if now is not None else None
    if _d is None or _n is None:
        return True
    return _n > _d


def occurrence_lisible(occurrence_iso) -> str:
    """« mercredi 23 septembre à 18:30 » — sans emoji, sans année (l'année est
    toujours celle en cours ou la suivante, l'invitation vit 30 jours)."""
    try:
        _d = datetime.fromisoformat(str(occurrence_iso or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(occurrence_iso or "")[:16].replace("T", " ")
    return "%s %d %s à %02d:%02d" % (_JOURS[_d.weekday()], _d.day, _MOIS[_d.month - 1],
                                     _d.hour, _d.minute)


# ─── Machine d'états ─────────────────────────────────────────────────────────
def transition(statut_actuel, cible) -> str:
    """Rend `cible` si la machine l'autorise depuis `statut_actuel`, sinon lève."""
    if cible not in ETATS:
        raise TransitionInvalide("etat inconnu: %r" % (cible,))
    if cible not in TRANSITIONS.get(statut_actuel, ()):
        raise TransitionInvalide("%s -> %s interdit" % (statut_actuel, cible))
    return cible


def statut_derive(pass_doc, now, reservations=None):
    """(statut, a_change) — l'état RÉEL d'un pass à l'instant `now`.

    Deux dérivations, dans cet ordre :
      * `used`    : le pass est `unlocked` et les deux réservations sont validées ;
      * `expired` : `now > expires_at` et le pass est encore verrouillé, en
                    attente ou avec un ami inscrit mais pas de parrain.
    `reservations` : les documents `reservations` du pass (liste, peut être vide).
    Ne modifie rien ; l'appelant persiste s'il le souhaite.
    """
    _p = pass_doc or {}
    _s = _p.get("status")
    if _s == UNLOCKED:
        _resas = [r for r in (reservations or []) if isinstance(r, dict)]
        _ids = _p.get("reservations") or {}
        _attendus = [_ids.get("sponsor_id"), _ids.get("invitee_id")]
        if sans_place_parrain(_p):
            # PAR-1 : racine de campagne — le coach n'a pas de place : seule la
            # présence de l'invité compte (jamais pour un pass sans `origin`).
            _attendus = [_ids.get("invitee_id")]
        if all(_attendus):
            _valides = {r.get("id") for r in _resas if r.get("validated") is True}
            if all(i in _valides for i in _attendus):
                return USED, True
        return _s, False
    if _s in ETATS_EXPIRABLES:
        _exp = _p.get("expires_at") or _p.get("occurrence")
        if est_passee(_exp, now):
            return EXPIRED, True
    return _s, False


def invite_autorise(pass_doc, email_norm, tel_norm=""):
    """(ok, raison) — cet e-mail / ce numéro peut-il être l'invité de ce pass ?

    AUTO-PARRAINAGE : refusé sur l'e-mail ET sur le téléphone. Un parrain qui
    change d'adresse mais garde son numéro n'invite pas son ami, il se
    fabrique un second essai.
    """
    _sp = (pass_doc or {}).get("sponsor") or {}
    _e = normaliser_email(email_norm)
    _t = "".join(ch for ch in str(tel_norm or "") if ch.isdigit())
    if not _e:
        return False, "email_requis"
    if _e == normaliser_email(_sp.get("email_norm")):
        return False, REFUS_AUTO_PARRAINAGE
    _sp_tel = "".join(ch for ch in str(_sp.get("whatsapp_norm") or "") if ch.isdigit())
    if _t and _sp_tel and _t == _sp_tel:
        return False, REFUS_AUTO_PARRAINAGE
    return True, ""


def peut_rejoindre(pass_doc, email_norm, now):
    """(code_http, raison) — le join est-il possible AVANT toute écriture ?
    200 = oui, 410 = pass fermé (expiré/annulé/occurrence passée),
    409 = pass déjà pourvu (raison `pass_ferme`), idempotent si même invité."""
    _p = pass_doc or {}
    _s, _ = statut_derive(_p, now)
    if _s in (EXPIRED, CANCELLED):
        return 410, _s
    _inv = _p.get("invitee") or {}
    if _inv and normaliser_email(_inv.get("email_norm")) == normaliser_email(email_norm):
        return 200, "idempotent"
    if _s in ETATS_OUVERTS_AU_JOIN and not _inv:
        return 200, ""
    return 409, REFUS_PASS_FERME


# ─── Textes ──────────────────────────────────────────────────────────────────
def texte_whatsapp(prenom_parrain, cours, occurrence, invite_url) -> str:
    """Le message prêt à coller, SANS emoji (contrainte du dépôt : aucun emoji
    dans ce qui part vers WhatsApp)."""
    _p = str(prenom_parrain or "").strip()
    _c = str(cours or "un cours Afroboost").strip()
    _quand = occurrence_lisible(occurrence)
    _intro = ("Salut ! C'est %s." % _p) if _p else "Salut !"
    return ("%s Je t'invite a mon cours Afroboost (%s) le %s : ton premier cours "
            "est offert grace a mon Pass Duo. Inscris-toi ici, ca prend 30 secondes : %s"
            % (_intro, _c, _quand, str(invite_url or "")))


def invite_url(frontend_url, share_token) -> str:
    return "%s/duo/%s" % (str(frontend_url or "https://afroboost.com").rstrip("/"),
                          str(share_token or ""))


# ─── V538 : LE LIEN QU'ON PARTAGE N'EST PAS LA PAGE QU'ON OUVRE ──────────────
#
# CE QUI NE MARCHAIT PAS. Le lien partagé pointait sur `/duo/<token>`, servi par
# l'application React : le robot de WhatsApp, lui, ne sait pas exécuter du
# JavaScript. Il lisait donc les balises de `index.html` — la description
# générale du site — et affichait un aperçu anonyme, sans nom, sans séance.
# Une invitation personnelle ressemblait à une publicité.
#
# LA CORRECTION. On partage une page SERVEUR qui porte les vraies balises
# Open Graph (nom de l'invitant, séance, image) et qui renvoie aussitôt un vrai
# navigateur vers `/duo/<token>`. Exactement le mécanisme déjà éprouvé pour le
# partage d'une offre (`/api/share/offer/<id>`, V278/V535) — repris, pas réinventé.
def partage_url(frontend_url, share_token) -> str:
    """L'URL à partager : la page d'aperçu, qui redirige vers l'invitation."""
    return "%s/api/share/duo/%s" % (str(frontend_url or "https://afroboost.com").rstrip("/"),
                                    str(share_token or ""))


def og_titre_invitation(prenom_parrain) -> str:
    """« Bassi t'invite à Afroboost » — le prénom, jamais le nom complet.
    Sans prénom exploitable : une formule qui reste vraie."""
    _p = str(prenom_parrain or "").strip()
    return ("%s t'invite à Afroboost" % _p) if _p else "Un membre Afroboost t'invite"


def og_description_invitation(prenom_parrain, cours, occurrence, offre_nom="") -> str:
    """La phrase d'aperçu : qui, quoi, quand, et ce que l'ami reçoit."""
    _p = str(prenom_parrain or "").strip()
    _c = str(cours or "").strip()
    _quand = occurrence_lisible(occurrence)
    _qui = ("Rejoins %s" % _p) if _p else "Rejoins-nous"
    _ou = (" pour %s" % _c) if _c else ""
    _date = (" le %s" % _quand) if _quand and _quand != "prochainement" else ""
    _cadeau = str(offre_nom or "").strip()
    _fin = ("Ton Pass Duo t'offre : %s." % _cadeau) if _cadeau else "Ton premier cours est offert grâce à son Pass Duo."
    return ("%s%s%s. %s" % (_qui, _ou, _date, _fin)).strip()


def media_apercu(offre=None, cours=None, concept=None) -> str:
    """V538 — L'IMAGE DE L'APERÇU, PAR ORDRE DE PRIORITÉ ET SANS INVENTER.

    1. la miniature (poster) du média de l'offre — c'est elle que le coach a
       choisie, et c'est la seule forme qu'un aperçu sait afficher : un réseau
       social ne lit pas une vidéo, il lit une image ;
    2. la première image de l'offre ;
    3. l'image de la séance, si la séance en porte une (aujourd'hui aucune n'en
       a : on lit le champ quand même, pour le jour où) ;
    4. l'image d'accueil du concept (la bannière du coach) ;
    5. rien — l'appelant posera le visuel Afroboost par défaut.

    Une URL de VIDÉO n'est jamais rendue : elle ferait un aperçu vide.
    """
    def _img(valeur):
        _v = str(valeur or "").strip()
        if not _v:
            return ""
        _bas = _v.lower().split("?")[0]
        if _bas.endswith((".mp4", ".mov", ".webm", ".m4v", ".avi")) or "/video/" in _bas or "video_" in _bas:
            return ""
        return _v

    _o = offre or {}
    _c = cours or {}
    _k = concept or {}
    for _cand in (_o.get("thumbnail"), _o.get("poster"), _o.get("video_poster")):
        _r = _img(_cand)
        if _r:
            return _r
    _images = _o.get("images")
    if isinstance(_images, list):
        for _i in _images:
            _r = _img(_i)
            if _r:
                return _r
    _r = _img(_o.get("videoUrl"))      # souvent une IMAGE en base (mesuré : 8 offres sur 11)
    if _r:
        return _r
    for _cand in (_c.get("image"), _c.get("thumbnail"), _c.get("cover")):
        _r = _img(_cand)
        if _r:
            return _r
    for _cand in (_k.get("heroImageUrl"), _k.get("logoUrl")):
        _r = _img(_cand)
        if _r:
            return _r
    return ""


def qr_value(frontend_url, reservation_code) -> str:
    """Le contenu du QR d'un billet — LE FORMAT QUE LE SCANNER ACCEPTE DÉJÀ.

    `_a0_code_depuis_qr` (reservation_routes.py) lit d'abord le paramètre `res`
    d'une URL ; le CAS A du scanner cherche alors `{"reservationCode": <res>}`
    et, parce que le code est ISSU D'UNE URL (`_issu_url`), il applique en plus
    la garde « la réservation est celle d'aujourd'hui » (A0-2) — exactement ce
    qu'il faut pour un billet lié à UNE occurrence. C'est aussi le format du QR
    de l'e-mail de confirmation. Jamais `AFROBOOST:<code>` (inconnu du
    scanner), et jamais `?code=<AFR->` : le code d'accès est le mot de passe de
    l'abonné, il ne voyage pas dans un billet montré à un tiers.
    """
    return "%s/chat?res=%s" % (str(frontend_url or "https://afroboost.com").rstrip("/"),
                               str(reservation_code or ""))


# ─── V534b : l'offre du pass (pur) ───────────────────────────────────────────
def sessions_offre(offer) -> int:
    """`offers.pack_sessions` sinon 1 — MÊME repli que `_process_successful_payment`
    (V260c : `int(float(ps)) > 0`, une valeur 10.0 ou "10" compte 10)."""
    try:
        _ps = (offer or {}).get("pack_sessions")
        if _ps is not None and int(float(_ps)) > 0:
            return int(float(_ps))
    except (TypeError, ValueError):
        pass
    return 1


def benefit_offre(sessions) -> str:
    try:
        _n = int(sessions or 1)
    except (TypeError, ValueError):
        _n = 1
    return "1 séance offerte" if _n <= 1 else "%d séances offertes" % _n


_UNITES = {"days": ("jour", "jours"), "weeks": ("semaine", "semaines"), "months": ("mois", "mois")}


def validity_offre(offer):
    """`duree_mois` d'abord (HIVER), sinon `duration_value` + `duration_unit`
    (v59), sinon None. Rend un libellé FR lisible (« 2 mois », « 14 jours »)."""
    _o = offer or {}
    try:
        _dm = _o.get("duree_mois")
        if _dm is not None and int(float(_dm)) > 0:
            return "%d mois" % int(float(_dm))
    except (TypeError, ValueError):
        pass
    try:
        _dv = _o.get("duration_value")
        _du = str(_o.get("duration_unit") or "").strip().lower()
        if _dv is not None and int(float(_dv)) > 0 and _du in _UNITES:
            _n = int(float(_dv))
            return "%d %s" % (_n, _UNITES[_du][0 if _n == 1 else 1])
    except (TypeError, ValueError):
        pass
    return None


def conditions_offre(offer):
    """`description` tronquée à 200 caractères, sinon None. Jamais du HTML."""
    _d = str((offer or {}).get("description") or "").strip()
    if not _d:
        return None
    return _d if len(_d) <= CONDITIONS_MAX else _d[:CONDITIONS_MAX - 1].rstrip() + "…"


def prix_offre(offer) -> float:
    try:
        return float((offer or {}).get("price") or 0)
    except (TypeError, ValueError):
        return 0.0


def dto_offre(offer, recommended=False) -> dict:
    """OffreDTO public : `{id, name, benefit, price, sessions, validity,
    conditions, recommended}` — AUCUN champ technique (pas de coach_id,
    linked_course_ids, source, collection). `price` 0 s'affiche « Offerte »."""
    _o = offer or {}
    _n = sessions_offre(_o)
    return {
        "id": _o.get("id"),
        "name": str(_o.get("name") or "")[:120],
        "benefit": benefit_offre(_n),
        "price": prix_offre(_o),
        "sessions": _n,
        "validity": validity_offre(_o),
        "conditions": conditions_offre(_o),
        "recommended": bool(recommended),
    }


def snapshot_offre(offer) -> dict:
    """Ce que le pass FIGE de l'offre au moment du choix (`offer_snapshot`) :
    l'OffreDTO sans `recommended` (la recommandation est celle du cours, elle
    peut changer ; le snapshot, non)."""
    _d = dto_offre(offer, False)
    _d.pop("recommended", None)
    return _d


def dto_offre_depuis_snapshot(snapshot, recommended=False) -> dict:
    """L'OffreDTO d'un pass, depuis son snapshot (l'offre peut avoir été
    renommée ou retirée depuis : le pass montre ce qui a été choisi)."""
    _s = snapshot or {}
    return {
        "id": _s.get("id"),
        "name": str(_s.get("name") or ""),
        "benefit": _s.get("benefit") or benefit_offre(_s.get("sessions")),
        "price": prix_offre(_s),
        "sessions": _s.get("sessions") or 1,
        "validity": _s.get("validity"),
        "conditions": _s.get("conditions"),
        "recommended": bool(recommended),
    }


def _proprietaire(coach_id) -> str:
    return coach_id.strip().lower() if isinstance(coach_id, str) else ""


def offre_eligible(offer, coach_id):
    """(ok, raison) — l'offre peut-elle être l'avantage d'un Pass Duo du cours
    dont le propriétaire est `coach_id` ? Raison ∈ `offre_inactive` (absente,
    invisible, archivée, désactivée) | `offre_payante` (V1 : 0 CHF seulement)
    | `offre_autre_coach` (même règle de propriété que `p1a_filtre_proprietaire` :
    propriétaire -> égalité stricte ; sans propriétaire -> offre sans
    propriétaire) | None."""
    _o = offer if isinstance(offer, dict) else None
    if not _o or not _o.get("id"):
        return False, REFUS_OFFRE_INACTIVE
    if _o.get("visible") is False or _o.get("archived") is True or _o.get("active") is False:
        return False, REFUS_OFFRE_INACTIVE
    if prix_offre(_o) != 0:
        return False, REFUS_OFFRE_PAYANTE
    if _proprietaire(coach_id) != _proprietaire(_o.get("coach_id")):
        return False, REFUS_OFFRE_AUTRE_COACH
    return True, None


def catalogue_du_cours(course, offers) -> tuple:
    """(offres valides dans l'ordre de `duo_offer_ids`, default_offer_id|None).
    `offers` : les documents relus en base. Le défaut n'est rendu que s'il
    fait partie des valides ; un cours sans `duo_offer_ids` rend ([], None)."""
    _c = course or {}
    _ids = [str(i).strip() for i in (_c.get("duo_offer_ids") or []) if str(i or "").strip()]
    _par_id = {str(o.get("id")): o for o in (offers or []) if isinstance(o, dict) and o.get("id")}
    _valides = []
    for _oid in _ids:
        _o = _par_id.get(_oid)
        if _o and offre_eligible(_o, _c.get("coach_id"))[0] and _oid not in [v.get("id") for v in _valides]:
            _valides.append(_o)
    _defaut = str(_c.get("duo_default_offer_id") or "").strip() or None
    if _defaut not in [v.get("id") for v in _valides]:
        _defaut = None
    return _valides, _defaut


def dtos_offres(offers, default_offer_id=None) -> list:
    return [dto_offre(o, bool(default_offer_id) and o.get("id") == default_offer_id) for o in (offers or [])]


def entree_historique_offre(ancienne, nouvelle, changed_by, at) -> dict:
    """`{from_offer_id, to_offer_id, from_name, to_name, changed_at, changed_by}`
    — `ancienne` / `nouvelle` : snapshots (ou OffreDTO)."""
    _a, _n = ancienne or {}, nouvelle or {}
    _qui = str(changed_by or "").strip().lower()
    if _qui not in CHANGE_PAR:
        raise ValueError("changed_by inconnu: %r" % (changed_by,))
    return {
        "from_offer_id": _a.get("id"),
        "to_offer_id": _n.get("id"),
        "from_name": str(_a.get("name") or ""),
        "to_name": str(_n.get("name") or ""),
        "changed_at": at,
        "changed_by": _qui,
    }


def ligne_historique_offre(entree, pass_id=None) -> dict:
    """La ligne d'`history[]` du parrain : « Offre modifiée : A → B »."""
    _e = entree or {}
    _de = str(_e.get("from_name") or _e.get("from_offer_id") or "?")
    _vers = str(_e.get("to_name") or _e.get("to_offer_id") or "?")
    return {
        "at": _e.get("changed_at") or _e.get("at"),
        "type": EVENEMENT_OFFRE,
        "label": "Offre modifiée : %s → %s" % (_de, _vers),
        "pass_id": pass_id,
        "from_offer_id": _e.get("from_offer_id"),
        "to_offer_id": _e.get("to_offer_id"),
        "changed_by": _e.get("changed_by"),
    }


def pass_modifiable_pour_offre(pass_doc, reservations=None, statut=None):
    """(ok, raison) — l'offre de ce pass peut-elle encore changer ?
    Raison : `used` | `expired` | `cancelled` | `presence_validee` (une
    réservation du pass est validée : l'avantage est consommé) | `statut_inconnu`.
    `statut` : le statut DÉRIVÉ (calculé par l'appelant), sinon le persisté."""
    _p = pass_doc or {}
    _s = statut or _p.get("status")
    if _s in (USED, EXPIRED, CANCELLED):
        return False, _s
    if _s not in ETATS_OFFRE_MODIFIABLE:
        return False, "statut_inconnu"
    _ids = _p.get("reservations") or {}
    _attendus = {i for i in (_ids.get("sponsor_id"), _ids.get("invitee_id")) if i}
    for _r in (reservations or []):
        if isinstance(_r, dict) and _r.get("id") in _attendus and _r.get("validated") is True:
            return False, "presence_validee"
    return True, None


def texte_non_modifiable(raison) -> str:
    if raison == USED:
        return TEXTE_OFFRE_UTILISEE
    if raison == "presence_validee":
        return TEXTE_PRESENCE_VALIDEE
    return "Ce Pass Duo ne peut plus changer d'offre (%s)." % LIBELLES.get(raison, raison)


def kpi_offres(passes) -> dict:
    """`{changements_offre, offre_la_plus_choisie: {offer_id, name, n}|None,
    par_offre: {offer_id: n}}` — l'offre COURANTE de chaque pass compte une
    fois ; `changements_offre` = nombre total d'entrées d'`offer_history`."""
    _par_offre, _noms, _changements = {}, {}, 0
    for _p in (passes or []):
        if not isinstance(_p, dict):
            continue
        _changements += len([e for e in (_p.get("offer_history") or []) if isinstance(e, dict)])
        _oid = str(_p.get("offer_id") or "").strip()
        if not _oid:
            continue
        _par_offre[_oid] = _par_offre.get(_oid, 0) + 1
        _noms.setdefault(_oid, str((_p.get("offer_snapshot") or {}).get("name") or ""))
    _top = None
    if _par_offre:
        _oid = sorted(_par_offre.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        _top = {"offer_id": _oid, "name": _noms.get(_oid, ""), "n": _par_offre[_oid]}
    return {"changements_offre": _changements, "offre_la_plus_choisie": _top, "par_offre": _par_offre}


# ─── DTO ─────────────────────────────────────────────────────────────────────
def dto_course(pass_doc) -> dict:
    _p = pass_doc or {}
    _c = _p.get("course_snapshot") or {}
    return {
        "id": _p.get("course_id"),
        "name": _c.get("name") or "",
        "time": _c.get("time") or "",
        "locationName": _c.get("locationName") or "",
        "mapsUrl": _c.get("mapsUrl") or "",
    }


def dto_ticket(reservation, role, first_name, frontend_url) -> dict:
    """TicketDTO : `{role, first_name, reservationCode, qr_value, validated,
    headphone_status}` — aucun e-mail, aucun code d'accès."""
    _r = reservation or {}
    _code = str(_r.get("reservationCode") or "")
    return {
        "role": role,
        "first_name": first_name or "",
        "reservationCode": _code,
        "qr_value": qr_value(frontend_url, _code) if _code else "",
        "validated": _r.get("validated") is True,
        "headphone_status": _r.get("headphone_status"),
    }


def tickets_du_pass(pass_doc, reservations, frontend_url) -> list:
    """Les billets RÉELS d'un pass : un par réservation existante, jamais un
    billet fabriqué pour une réservation qui n'existe pas."""
    _p = pass_doc or {}
    _ids = _p.get("reservations") or {}
    _par_id = {r.get("id"): r for r in (reservations or []) if isinstance(r, dict)}
    _sortie = []
    for _role, _cle, _qui in ((ROLE_SPONSOR, "sponsor_id", _p.get("sponsor")),
                              (ROLE_INVITEE, "invitee_id", _p.get("invitee"))):
        _rid = _ids.get(_cle)
        _r = _par_id.get(_rid) if _rid else None
        if _r:
            _sortie.append(dto_ticket(_r, _role, prenom((_qui or {}).get("name")), frontend_url))
    return _sortie


# ─── V539 : L'AMI CHOISIT SA SÉANCE ─────────────────────────────────────────
#
# CE QUI COINÇAIT. Le parrain choisissait une occurrence à la création, et
# l'ami n'avait qu'un choix : cette date, ou rien. Or c'est LUI qu'on invite :
# s'il ne peut pas venir ce mercredi-là, l'invitation est morte.
#
# CE QUE ÇA NE CHANGE PAS. Le cours reste celui du pass (l'avantage et les
# règles y sont attachés) : on change la DATE, pas la séance d'un autre coach
# ni une offre. Et seulement AVANT l'inscription de l'ami : une fois les
# billets émis, deux réservations existent, et les déplacer est un autre lot.
EVENEMENT_SEANCE = "occurrence_changed"
REFUS_OCCURRENCE_INCONNUE = "occurrence_inconnue"
REFUS_OCCURRENCE_PASSEE = "occurrence_passee"


def occurrence_choisissable(occurrence, occurrences_autorisees, maintenant=None) -> tuple:
    """(occurrence normalisée, "") ou ("", motif). L'occurrence doit venir de la
    LISTE DU SERVEUR — jamais d'une date tapée par le navigateur — et ne pas
    être déjà passée."""
    _cible = str(occurrence or "").strip()
    if not _cible:
        return "", REFUS_OCCURRENCE_INCONNUE
    _liste = [str(_o or "").strip() for _o in (occurrences_autorisees or []) if str(_o or "").strip()]
    if _cible not in _liste:
        return "", REFUS_OCCURRENCE_INCONNUE
    # `est_passee(x, None)` vaut « passée » (fail-closed voulu ailleurs) : ici,
    # un appelant qui ne précise pas l'instant veut dire « maintenant », pas
    # « refuse tout ». Les bancs, eux, passent un instant fixe.
    _now = maintenant if maintenant is not None else datetime.now(timezone.utc)
    if est_passee(_cible, _now):
        return "", REFUS_OCCURRENCE_PASSEE
    return _cible, ""


def entree_historique_seance(avant, apres, changed_by, quand) -> dict:
    """La ligne d'historique d'un changement de séance — même forme que celle
    des offres, pour que l'écran n'ait qu'une façon de lire un changement."""
    _qui = str(changed_by or "").strip().lower()
    if _qui not in CHANGE_PAR:
        raise ValueError("changed_by inconnu: %r" % (changed_by,))
    return {
        "from_occurrence": str(avant or ""),
        "to_occurrence": str(apres or ""),
        "changed_at": str(quand or ""),
        # MÊME liste d'auteurs autorisés que l'historique des offres : un seul
        # vocabulaire pour « qui a changé quoi ».
        "changed_by": _qui,
    }


def ligne_historique_seance(entree) -> str:
    """« Séance modifiée : mercredi 23 septembre à 18:45 -> dimanche 27… »"""
    _e = entree or {}
    return "Séance modifiée : %s -> %s" % (occurrence_lisible(_e.get("from_occurrence")),
                                           occurrence_lisible(_e.get("to_occurrence")))


def version_pass(pass_doc) -> int:
    """`version` du pass (V534b) — un pass sans champ vaut 1."""
    try:
        return max(1, int((pass_doc or {}).get("version") or 1))
    except (TypeError, ValueError):
        return 1


def offre_du_pass(pass_doc, catalogue=None) -> dict:
    """L'OffreDTO du pass depuis son snapshot ; `recommended` recopié du
    catalogue courant (liste d'OffreDTO) quand l'offre y figure encore."""
    _p = pass_doc or {}
    _snap = _p.get("offer_snapshot") or {"id": _p.get("offer_id")}
    _reco = any(o.get("id") == _snap.get("id") and o.get("recommended")
                for o in (catalogue or []) if isinstance(o, dict))
    return dto_offre_depuis_snapshot(_snap, _reco)


def invite_masque(pass_doc) -> bool:
    """PAR-1 (A3) — le parrain de CE pass voit-il son filleul ? Non pour une
    invitation de chaîne (enfant) ni pour un pass d'origine campagne : « sans
    exposer les données privées du filleul ». Pass Duo classique : oui (inchangé)."""
    return bool(chaine_du_pass(pass_doc).get("parent_pass_id")) or bool(campagne_du_pass(pass_doc))


def dto_pass(pass_doc, statut, tickets, frontend_url, deja_existant=None, offers=None,
             masquer_invite=None) -> dict:
    """PassDTO (parrain). Aucune donnée de l'invité au-delà de son prénom.
    V534b : + `offer` (OffreDTO du pass), `offers` (catalogue courant du
    cours, OffreDTO[]), `version`, `offer_history`."""
    _p = pass_doc or {}
    _sp = _p.get("sponsor") or {}
    _inv = _p.get("invitee") or None
    _url = invite_url(frontend_url, _p.get("share_token"))
    _offers = list(offers or [])
    _invitation = invitation_du_pass(_p)                     # V551
    _share = url_partage_versionnee(frontend_url, _p)        # V551
    # PAR-1 (A3) : chaîne / campagne -> ni prénom, ni billet, ni QR du filleul.
    _masque = invite_masque(_p) if masquer_invite is None else bool(masquer_invite)
    _tickets = [t for t in (tickets or []) if not (_masque and isinstance(t, dict) and t.get("role") == ROLE_INVITEE)]
    _dto = {
        "id": _p.get("id"),
        "status": statut,
        "status_label": LIBELLES.get(statut, statut),
        "course": dto_course(_p),
        "occurrence": _p.get("occurrence"),
        "share_token": _p.get("share_token"),
        "invite_url": _url,
        # V538 : CE QU'ON PARTAGE. `invite_url` reste la page que l'ami ouvre ;
        # `share_url` est la page d'aperçu qui y mène — c'est elle que WhatsApp,
        # le QR, « Copier » et « Partager » doivent porter, sinon l'aperçu est nu.
        # V551 : `?v=<invitation_version>` quand l'invitation a été personnalisée.
        "share_url": _share,
        "whatsapp_text": ("%s\n%s" % (_invitation["message"], _share)) if _invitation["message"] else
        texte_whatsapp(nom_parrain_affichable(_p), dto_course(_p)["name"], _p.get("occurrence"), _share),
        "invitation": _invitation,
        "invitee": {"first_name": prenom(_inv.get("name"))} if (_inv and not _masque) else None,
        # PAR-1 (A3) : le seul signal sur le filleul, pour TOUS les pass (booléen).
        "ami_rejoint": bool(_inv),
        "tickets": _tickets,
        "blocked_reason": _p.get("blocked_reason"),
        "created_at": _p.get("created_at"),
        "unlocked_at": _p.get("unlocked_at"),
        "expires_at": _p.get("expires_at"),
        "offer": offre_du_pass(_p, _offers),
        "offers": _offers,
        "version": version_pass(_p),
        "offer_history": [dict(e) for e in (_p.get("offer_history") or []) if isinstance(e, dict)],
    }
    # PAR-1 : une invitation de CHAÎNE (enfant) a-t-elle été partagée ? Booléen +
    # canal, sans aucune donnée personnelle (l'espace abonné affiche « Partagée »).
    _partage = partage_chaine(_p)
    _dto["chain_shared"] = _partage["shared"]
    _dto["chain_share_channel"] = _partage["channel"]
    # V552 : LA carte sociale (la même image que l'aperçu WhatsApp) ; jamais sans jeton.
    _carte = url_carte(frontend_url, _p)
    if _carte:
        _dto["card_url"] = _carte
    if deja_existant is not None:
        _dto["deja_existant"] = bool(deja_existant)
    return _dto


def dto_public(pass_doc, statut, now, offers=None) -> dict:
    """La page publique `/duo/<token>` : AUCUN e-mail, AUCUN téléphone, AUCUN
    code. Juste de quoi dire « X t'invite à tel cours, tel jour ».
    V534b : + `offer`, `offers` (catalogue courant), `version`."""
    _p = pass_doc or {}
    _sp = _p.get("sponsor") or {}
    _c = dto_course(_p)
    _c.pop("id", None)
    _offers = list(offers or [])
    return {
        "status": statut,
        "status_label": LIBELLES.get(statut, statut),
        # V551 : le prénom passe par le filtre (jamais une partie locale d'e-mail).
        "sponsor_first_name": nom_affichable(_sp.get("name"), _sp.get("email_norm")),
        "sponsor_display_name": nom_parrain_affichable(_p),
        "sponsor_photo_url": inviter_display_du_pass(_p)["photo_url"],
        # L0 : QUI invite (prénom, photo ou avatar Afroboost) — jamais d'e-mail/téléphone.
        "inviter_display": inviter_display_du_pass(_p),
        "course": _c,
        "occurrence": _p.get("occurrence"),
        "expired": statut in (EXPIRED, CANCELLED) or est_passee(_p.get("expires_at") or _p.get("occurrence"), now),
        "offer": offre_du_pass(_p, _offers),
        "offers": _offers,
        "version": version_pass(_p),
    }


def dto_admin(pass_doc, statut, tickets, frontend_url, offers=None) -> dict:
    """PassAdminDTO = PassDTO + prénoms ET e-mails (admin seulement)."""
    _d = dto_pass(pass_doc, statut, tickets, frontend_url, offers=offers, masquer_invite=False)
    _sp = (pass_doc or {}).get("sponsor") or {}
    _inv = (pass_doc or {}).get("invitee") or {}
    _d["coach_id"] = (pass_doc or {}).get("coach_id")
    _d["sponsor"] = {"first_name": prenom(_sp.get("name")),
                     # V556 : un parrain de chaîne pas encore inscrit n'a pas d'adresse
                     # PAR-1 : ni la clé « campagne: » d'une racine de campagne
                     "email": "" if (parrain_en_attente(pass_doc) or parrain_campagne(pass_doc))
                     else (_sp.get("email_norm") or "")}
    # PAR-1 : la lignée (source, campagne, parent, racine, profondeur), déduite.
    _d["lignage"] = lignage(pass_doc)
    # V556 : qui a invité qui — l'identifiant du pass parent et la profondeur.
    _ch = chaine_du_pass(pass_doc)
    if _ch.get("parent_pass_id"):
        _d["chain"] = {"parent_pass_id": _ch.get("parent_pass_id"), "root_pass_id": _ch.get("root_pass_id"),
                       "depth": _ch.get("depth"), "sponsor_pending": parrain_en_attente(pass_doc)}
    _d["invitee"] = ({"first_name": prenom(_inv.get("name")), "email": _inv.get("email_norm") or ""}
                     if _inv else None)
    _d["opened_at"] = (pass_doc or {}).get("opened_at")
    return _d


def historique(passes, limite=50) -> list:
    """[{at, type, label}] — les événements de tous les passes, récents d'abord."""
    _sortie = []
    for _p in (passes or []):
        for _e in ((_p or {}).get("events") or []):
            if not isinstance(_e, dict):
                continue
            _t = str(_e.get("type") or "")
            if _t == EVENEMENT_OFFRE:
                # V534b : « Offre modifiée : A → B » depuis le détail de l'événement.
                _ligne = ligne_historique_offre(dict(_e.get("detail") or {}, changed_at=_e.get("at")),
                                                (_p or {}).get("id"))
                _sortie.append(_ligne)
                continue
            _sortie.append({"at": _e.get("at"), "type": _t,
                            "label": LIBELLES_EVENEMENTS.get(_t, _t),
                            "pass_id": (_p or {}).get("id")})
    _sortie.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return _sortie[:limite]


def stats_parrain(passes, invitations, statuts) -> dict:
    """`{invited, opened, joined, unlocked, used}` pour l'écran du parrain.
    `statuts` : dict pass_id -> statut dérivé (déjà calculé par l'appelant)."""
    _st = statuts or {}
    # V538 — « MES RÉSULTATS » COMPTE CE QUI EST ENCORE VRAI.
    #
    # Le propriétaire l'a constaté en testant : il annule un Pass, et le
    # compteur « amis invités » reste gonflé. C'est que l'invitation existait
    # toujours — et elle existe toujours, c'est bien : l'historique ne se
    # réécrit pas. Mais un RÉSULTAT décrit ce qui est en cours, pas ce qui a
    # été tenté puis annulé. On écarte donc des compteurs les passes annulés et
    # expirés ; leurs invitations restent en base, et l'historique les montre.
    _vivants = [p for p in (passes or []) if isinstance(p, dict)
                and _st.get(p.get("id"), p.get("status")) not in (CANCELLED, EXPIRED)]
    _ids_vivants = {p.get("id") for p in _vivants}
    _inv_vivantes = [i for i in (invitations or []) if isinstance(i, dict)
                     and (i.get("pass_id") in _ids_vivants or not i.get("pass_id"))]
    return {
        "invited": len(_inv_vivantes),
        "opened": sum(1 for p in _vivants if p.get("opened_at")),
        "joined": sum(1 for p in _vivants if p.get("invitee")),
        "unlocked": sum(1 for p in _vivants if _st.get(p.get("id")) in (UNLOCKED, USED)),
        "used": sum(1 for p in _vivants if _st.get(p.get("id")) == USED),
    }


def kpi_parrainage(passes, invitations, reservations=None, statuts=None) -> dict:
    """Les 9 KPI du cockpit + la répartition par canal. Pure.

    `statuts` : dict pass_id -> statut dérivé ; à défaut le statut persisté.
    `reservations` : documents `reservations` portant `pass_id` (pour
    `presences_duo` = présences validées sur des billets Duo)."""
    _st = statuts or {}
    _passes = [p for p in (passes or []) if isinstance(p, dict)]

    def _s(p):
        return _st.get(p.get("id")) or p.get("status")

    # V556 : `share_image` (partage natif avec la carte) compte comme `share` —
    # la forme du KPI (4 canaux) ne change pas pour le cockpit.
    _par_canal = {c: 0 for c in CANAUX if c != "share_image"}
    for _i in (invitations or []):
        _c = str((_i or {}).get("channel") or "")
        _c = "share" if _c == "share_image" else _c
        if _c in _par_canal:
            _par_canal[_c] += 1
    _ids = {p.get("id") for p in _passes}
    _presences = sum(1 for r in (reservations or [])
                     if isinstance(r, dict) and r.get("pass_id") in _ids and r.get("validated") is True)
    return {
        "kpi": {
            "passes_crees": len(_passes),
            "invitations": len(invitations or []),
            "ouvertures": sum(1 for p in _passes if p.get("opened_at")),
            "inscriptions": sum(1 for p in _passes if p.get("invitee")),
            "debloques": sum(1 for p in _passes if _s(p) in (UNLOCKED, USED)),
            "utilises": sum(1 for p in _passes if _s(p) == USED),
            "expires": sum(1 for p in _passes if _s(p) == EXPIRED),
            "annules": sum(1 for p in _passes if _s(p) == CANCELLED),
            "presences_duo": _presences,
        },
        "par_canal": _par_canal,
    }


def contient_pii(objet, cles=("email", "whatsapp", "email_norm", "subscription_code",
                              "phone", "assignedEmail", "userEmail", "invitee_access_code")) -> list:
    """Les chemins d'un JSON qui portent une clé personnelle — outil de banc,
    pur, pour prouver qu'une réponse publique ne fuit rien."""
    _trouves = []

    def _marche(o, chemin):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k) in cles:
                    _trouves.append(chemin + "." + str(k))
                _marche(v, chemin + "." + str(k))
        elif isinstance(o, (list, tuple)):
            for i, v in enumerate(o):
                _marche(v, "%s[%d]" % (chemin, i))

    _marche(objet, "$")
    return _trouves


# ═══════════════════════════════════════════════════════════════════════════
# V556 — PARRAINAGE V3 : LA CHAÎNE (« boule de neige »)
# ═══════════════════════════════════════════════════════════════════════════
#
# Bassi invite A (pass P0). Avant de pouvoir s'inscrire, A prépare et PARTAGE
# une invitation ENFANT (pass P1, parrain = A) ; B ouvre P1 et fait de même...
# Ce n'est PAS un second moteur : l'enfant est un `referral_passes` ordinaire
# (mêmes états, même join, même essai, même anti-double), avec un bloc `chain`
# en plus. Qui a invité qui = `chain.parent_pass_id` remonté jusqu'à la racine.
#
# « PARTAGÉE » = l'action de partage a été DÉCLENCHÉE (WhatsApp ouvert, feuille
# de partage résolue, lien copié). Un navigateur ne peut pas savoir si le
# message est vraiment parti : on ne le prétend jamais.
#
# LE PARRAIN DE L'ENFANT N'EST PAS ENCORE CONNU à sa création (A n'est pas
# inscrit). Son `sponsor.email_norm` vaut `chaine-en-attente:<id du parent>` —
# unique par parent, donc sans collision sur l'index (parrain, cours,
# occurrence) — jusqu'au join de A sur le parent, qui le LIE (vraie adresse).
REFUS_INVITATION_REQUISE = "invitation_requise"
REFUS_CHAINE_EN_ATTENTE = "chaine_en_attente"
BLOCAGE_PARRAIN_NON_INSCRIT = "parrain_non_inscrit"
REFUS_AUTRE_APPAREIL = "invitation_autre_appareil"   # clé de l'appareil qui a partagé absente
PARTAGES_MAX = 30               # partages journalisés par invitation enfant (au-delà : accepté, rien écrit)
MESSAGE_CHAINE_DEFAUT = "Je t'invite à venir découvrir Afroboost avec moi 👇"
CHAINE_ATTENTE_MAX = 3          # maillons consécutifs dont le parrain n'est pas inscrit
PREFIXE_PARRAIN_EN_ATTENTE = "chaine-en-attente:"
EVENEMENT_CHAINE_CREEE = "chain_child_created"
EVENEMENT_CHAINE_PARTAGEE = "chain_shared"
EVENEMENT_PARRAIN_LIE = "chain_sponsor_bound"


def cle_parrain_en_attente(parent_id) -> str:
    return "%s%s" % (PREFIXE_PARRAIN_EN_ATTENTE, str(parent_id or ""))


def parrain_en_attente(pass_doc) -> bool:
    """Le parrain de ce pass n'est-il pas encore inscrit (enfant non lié) ?"""
    _sp = (pass_doc or {}).get("sponsor") or {}
    return _sp.get("pending") is True or str(_sp.get("email_norm") or "").startswith(PREFIXE_PARRAIN_EN_ATTENTE)


def chaine_du_pass(pass_doc) -> dict:
    _c = (pass_doc or {}).get("chain")
    return _c if isinstance(_c, dict) else {}


def chaine_partagee(pass_doc) -> bool:
    return bool(chaine_du_pass(pass_doc).get("shared_at"))


def chaine_requise(pass_doc, statut, drapeau) -> bool:
    """Le visiteur de ce pass doit-il inviter avant de s'inscrire ? Oui si la
    règle est active, que le pass attend encore son ami et que personne ne
    l'a rejoint. Les anciens liens y passent aussi, sans changer de jeton."""
    return bool(drapeau) and statut in ETATS_OUVERTS_AU_JOIN and not (pass_doc or {}).get("invitee")


def dto_chaine_public(pass_doc) -> dict:
    """Ce que la page publique a le droit de savoir : existe / partagée."""
    _c = chaine_du_pass(pass_doc)
    return {"exists": bool(_c.get("child_pass_id")), "shared": bool(_c.get("shared_at"))}


def attente_trop_longue(maillons_en_attente) -> bool:
    try:
        return int(maillons_en_attente) >= CHAINE_ATTENTE_MAX
    except (TypeError, ValueError):
        return True


def message_enfant(pass_doc) -> str:
    return invitation_du_pass(pass_doc)["message"] or MESSAGE_CHAINE_DEFAUT


def contact_invitant(pass_doc) -> dict:
    """UX-P1 — `{whatsapp_e164, consent, updated_at}` saisi sur une invitation
    enfant (serveur seulement : le numéro ne sort JAMAIS dans un DTO)."""
    _c = (pass_doc or {}).get("contact_invitant")
    return _c if isinstance(_c, dict) else {}


def photo_suggeree_enfant(pass_doc):
    """UX-P1 — la photo de PROFIL connue du créateur de l'invitation enfant
    (lue via son identité abonné), revalidée ; None sinon."""
    _u = (pass_doc or {}).get("inviter_profile_photo")
    if not _u:
        return None
    try:
        return valider_photo_url(_u)
    except InvitationInvalide:
        return None


def dto_enfant(pass_doc, frontend_url) -> dict:
    """L'invitation enfant telle que son créateur la voit : de quoi partager,
    rien de plus (ni e-mail, ni téléphone, ni identifiant interne)."""
    _p = pass_doc or {}
    _inv = invitation_du_pass(_p)
    _share = url_partage_versionnee(frontend_url, _p)
    _msg = message_enfant(_p)
    _c = dto_course(_p)
    _c.pop("id", None)
    _d = {
        "share_token": _p.get("share_token"),
        "share_url": _share,
        "invite_url": invite_url(frontend_url, _p.get("share_token")),
        "display_name": _inv["display_name"],
        "message": _msg,
        "whatsapp_text": "%s\n%s" % (_msg, _share),
        "course": _c,
        "occurrence": _p.get("occurrence"),
        "offer": offre_du_pass(_p),
        "preview_version": version_partage(_p),
        "joined": bool(_p.get("invitee")),
        "inviter_display": inviter_display_du_pass(_p),   # L0
        # UX-P1 : la photo CHOISIE pour l'invitation, la photo de profil proposée
        # (identité abonné présentée), et l'état du contact — jamais le numéro.
        "photo_url": _inv["photo_url"],
        "photo_suggeree": photo_suggeree_enfant(_p),
        "whatsapp_renseigne": bool(contact_invitant(_p).get("whatsapp_e164")),
        "consent_contact": contact_invitant(_p).get("consent") is True,
    }
    _carte = url_carte(frontend_url, _p)
    if _carte:
        _d["card_url"] = _carte
    return _d


def identite_correspond(email_norm, tel_norm, autres) -> bool:
    """`autres` = [(email, tel)] : l'une des identités est-elle la même
    personne (e-mail normalisé OU chiffres du téléphone) ?"""
    _e = normaliser_email(email_norm)
    _t = "".join(ch for ch in str(tel_norm or "") if ch.isdigit())
    for _ae, _at in (autres or []):
        _ae = normaliser_email(_ae)
        if _e and _ae and not _ae.startswith(PREFIXE_PARRAIN_EN_ATTENTE) and _e == _ae:
            return True
        _atc = "".join(ch for ch in str(_at or "") if ch.isdigit())
        if _t and _atc and _t == _atc:
            return True
    return False


# ─── V556 : l'aperçu (Open Graph) — pur, testable, partagé avec le contrôle ──
ROBOTS_APERCU = ("facebookexternalhit", "facebookcatalog", "meta-externalagent", "whatsapp",
                 "twitterbot", "telegrambot", "slackbot", "linkedinbot", "discordbot",
                 "skypeuripreview", "googlebot", "bingbot", "applebot", "pinterest", "redditbot",
                 "embedly", "vkshare", "iframely", "snapchat", "signal", "viber", "line/")


def est_robot_apercu(user_agent) -> bool:
    """Un robot d'aperçu ne doit PAS recevoir la redirection `meta refresh` :
    certains la suivent et lisent alors les balises génériques de l'appli."""
    _ua = str(user_agent or "").lower()
    return any(r in _ua for r in ROBOTS_APERCU)


def version_depuis_requete(v) -> int:
    """`?v=` nettoyé : des chiffres (7 au plus), sinon 0. Jamais recopié brut."""
    _v = str(v or "").strip()
    if not _v or len(_v) > 7 or not _v.isdigit():
        return 0
    return int(_v)


def page_apercu_html(titre, description, image, url, cible, robot=False) -> str:
    """LA page d'aperçu (`/api/share/duo/<token>`), tout échappé. `url` =
    l'adresse EXACTE partagée (avec `?v=`) : og:url doit la répéter, sinon le
    robot range l'aperçu sous l'URL nue et ressert l'ancien. `robot` : pas de
    `meta refresh` (un robot qui la suit lirait les balises de l'accueil)."""
    import html as _html
    e_titre = _html.escape(str(titre or ""), quote=True)
    e_desc = _html.escape(str(description or "")[:200], quote=True)
    e_image = _html.escape(str(image or ""), quote=True)
    e_url = _html.escape(str(url or ""), quote=True)
    e_cible = _html.escape(str(cible or ""), quote=True)
    _refresh = "" if robot else '\n    <meta http-equiv="refresh" content="0;url=%s"/>' % e_cible
    return """<!DOCTYPE html>
<html lang="fr" prefix="og: https://ogp.me/ns#">
<head>
    <meta charset="utf-8"/>
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
        <p style="letter-spacing:.14em;text-transform:uppercase;font-size:12px;color:#D91CD2;margin:0 0 10px;">Pass Duo</p>
        <h1 style="font-size:26px;line-height:1.25;margin:0 0 10px;">{t}</h1>
        <p style="color:rgba(255,255,255,.72);font-size:15px;line-height:1.5;margin:0 0 20px;">{d}</p>
        <a href="{c}" style="display:inline-block;padding:14px 26px;border-radius:999px;background:linear-gradient(135deg,#D91CD2,#8b5cf6);color:#fff;text-decoration:none;font-weight:700;">Voir l'invitation</a>
    </main>
</body>
</html>""".format(t=e_titre, d=e_desc, i=e_image, u=e_url, c=e_cible, r=_refresh)


_RE_META_OG = _re.compile(r'<meta\s+(?:property|name)="([^"]+)"\s+content="([^"]*)"', _re.I)


def extraire_og(html_texte) -> dict:
    """{propriété: contenu (dé-échappé)} des balises <meta> d'une page."""
    import html as _html
    _sortie = {}
    for _k, _v in _RE_META_OG.findall(str(html_texte or "")):
        _sortie.setdefault(_k.lower(), _html.unescape(_v))
    return _sortie


def controle_apercu(html_texte, image_octets, image_type) -> dict:
    """Le bilan d'aperçu — ce que WhatsApp exige pour afficher une carte :
    titre, description, image absolue HTTPS, image lisible de type image/*.
    `ok` = tout est vert ; sinon l'appelant sert un repli, jamais un trou."""
    _og = extraire_og(html_texte)
    _img = _og.get("og:image") or ""
    _octets = image_octets or b""
    _type = str(image_type or "")
    _jpeg = _octets[:3] == b"\xff\xd8\xff"
    _png = _octets[:8] == b"\x89PNG\r\n\x1a\n"
    _checks = {
        "share_page": bool(html_texte) and "<html" in str(html_texte)[:200].lower(),
        "og_title": bool(_og.get("og:title")),
        "og_description": bool(_og.get("og:description")),
        "og_image": bool(_img),
        "og_image_https": _img.startswith("https://"),
        "og_url": bool(_og.get("og:url")),
        "image_ok": bool(_octets) and (_jpeg or _png) and _type.startswith("image/"),
        "image_type": _type,
        "image_bytes": len(_octets),
    }
    _checks["image_leger"] = 0 < len(_octets) <= 600 * 1024     # au-delà, WhatsApp renonce souvent
    _ok = all(_checks[k] for k in ("share_page", "og_title", "og_description", "og_image",
                                   "og_image_https", "og_url", "image_ok", "image_leger"))
    return {"ok": _ok, "checks": _checks}


# ═══════════════════════════════════════════════════════════════════════════
# PAR-1 — LOT 1 : LA CAMPAGNE D'UN COACH, RACINE D'UNE CHAÎNE V556
# ═══════════════════════════════════════════════════════════════════════════
#
# Un visiteur d'une campagne `trial` reçoit UN pass racine ORDINAIRE (P0) : son
# « parrain » est la campagne (clé `campagne:<campaign_id>:<p0_id>`, jamais une
# adresse), il n'a PAS de place sur la séance. Le bloc additif `origin`
# ({source_type, source_id, campaign_id, entry_key_hash}) n'existe QUE sur ces
# pass et sur leurs descendants ({campaign_id, root_source_type, root_source_id}) :
# un pass sans `origin` suit exactement le chemin d'avant.
SOURCES_RACINE = ("coach", "partner", "super_admin")
SOURCE_ABONNE = "subscriber"
PREFIXE_PARRAIN_CAMPAGNE = "campagne:"


def cle_parrain_campagne(campaign_id, pass_id) -> str:
    return "%s%s:%s" % (PREFIXE_PARRAIN_CAMPAGNE, str(campaign_id or ""), str(pass_id or ""))


def parrain_campagne(pass_doc) -> bool:
    """Le « parrain » de ce pass est-il une campagne (P0) ?"""
    _sp = (pass_doc or {}).get("sponsor") or {}
    return str(_sp.get("email_norm") or "").startswith(PREFIXE_PARRAIN_CAMPAGNE)


def origine_du_pass(pass_doc) -> dict:
    """Le bloc `origin` (dict) ; {} pour tout pass d'avant PAR-1."""
    _o = (pass_doc or {}).get("origin")
    return _o if isinstance(_o, dict) else {}


def campagne_du_pass(pass_doc) -> str:
    """L'identifiant de la campagne racine (P0 et descendants), sinon ""."""
    return str(origine_du_pass(pass_doc).get("campaign_id") or "")


def type_invitation(pass_doc) -> str:
    """UX-P4 — le type affiché par le badge de la page publique (aucune PII, aucune
    lecture en base). Une chaîne de campagne ne naît aujourd'hui que d'une campagne
    « Essai gratuit » (seul type admis à /entry) et ses maillons héritent de
    `origin.campaign_id` → "trial" ; tout autre pass est un vrai Pass Duo."""
    return "trial" if campagne_du_pass(pass_doc) else "pass_duo"


def sans_place_parrain(pass_doc) -> bool:
    """Racine de campagne : `origin.source_type` ∈ coach/partner/super_admin ET
    aucun parent. Son déblocage ne réserve aucune place de parrain."""
    return (origine_du_pass(pass_doc).get("source_type") in SOURCES_RACINE
            and not chaine_du_pass(pass_doc).get("parent_pass_id"))


def lignage(pass_doc) -> dict:
    """`{source_type, source_id, campaign_id, parent_referral_id,
    root_referral_id, depth}` DÉDUIT de `chain` + `origin` (aucune migration) :
    un ancien pass vaut subscriber, sans parent, racine lui-même, profondeur 0."""
    _p = pass_doc or {}
    _o = origine_du_pass(_p)
    _c = chaine_du_pass(_p)
    _parent = _c.get("parent_pass_id") or None
    try:
        _prof = int(_c.get("depth") or 0)
    except (TypeError, ValueError):
        _prof = 0
    _type = _o.get("source_type") if (_o.get("source_type") in SOURCES_RACINE and not _parent) else SOURCE_ABONNE
    return {
        "source_type": _type,
        "source_id": (_o.get("source_id") if _type != SOURCE_ABONNE else None),
        "campaign_id": _o.get("campaign_id") or _p.get("referral_campaign_id") or None,
        "parent_referral_id": _parent,
        "root_referral_id": _c.get("root_pass_id") or _p.get("id"),
        "depth": _prof,
    }


def partage_chaine(pass_doc) -> dict:
    """PAR-1 — `{shared, channel}` d'une invitation ENFANT de chaîne : partagée
    dès qu'un partage a été DÉCLENCHÉ (`POST /chain/share` journalise
    `invitation_sent` sur l'enfant et incrémente `preview_version`). Canal = le
    dernier journalisé (∈ CANAUX), sinon None. Un pass hors chaîne : faux/None."""
    _p = pass_doc or {}
    if not chaine_du_pass(_p).get("parent_pass_id"):
        return {"shared": False, "channel": None}
    _canal = None
    for _e in (_p.get("events") or []):
        if isinstance(_e, dict) and _e.get("type") == "invitation_sent":
            _canal = _e.get("detail") if _e.get("detail") in CANAUX else _canal
    return {"shared": bool(_canal) or version_apercu(_p) > 0, "channel": _canal}


# PAR-1 (A1) — refus du join qui disent « cette personne ne pourra JAMAIS
# s'inscrire sur ce maillon » : la place d'enfant qu'elle a prise est libérée.
# Jamais un refus transitoire (invitation_requise, autre appareil, pass fermé,
# campagne complète, conflit de version, 410, 5xx).
REFUS_IDENTITE_DEFINITIFS = (REFUS_AUTO_PARRAINAGE, REFUS_DEJA_FILLEUL, REFUS_ABONNE_ACTIF,
                             "free_trial_already_used", "free_trial_already_granted")
EVENEMENT_CHAINE_LIBEREE = "chain_released"


def refus_identite_definitif(code_http, raison) -> bool:
    return code_http == 409 and str(raison or "") in REFUS_IDENTITE_DEFINITIFS

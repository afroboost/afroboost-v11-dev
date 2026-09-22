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
CANAUX = ("whatsapp", "copy", "qr", "share")

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


def dto_pass(pass_doc, statut, tickets, frontend_url, deja_existant=None, offers=None) -> dict:
    """PassDTO (parrain). Aucune donnée de l'invité au-delà de son prénom.
    V534b : + `offer` (OffreDTO du pass), `offers` (catalogue courant du
    cours, OffreDTO[]), `version`, `offer_history`."""
    _p = pass_doc or {}
    _sp = _p.get("sponsor") or {}
    _inv = _p.get("invitee") or None
    _url = invite_url(frontend_url, _p.get("share_token"))
    _offers = list(offers or [])
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
        "share_url": partage_url(frontend_url, _p.get("share_token")),
        "whatsapp_text": texte_whatsapp(prenom(_sp.get("name")), dto_course(_p)["name"],
                                        _p.get("occurrence"),
                                        partage_url(frontend_url, _p.get("share_token"))),
        "invitee": {"first_name": prenom(_inv.get("name"))} if _inv else None,
        "tickets": list(tickets or []),
        "blocked_reason": _p.get("blocked_reason"),
        "created_at": _p.get("created_at"),
        "unlocked_at": _p.get("unlocked_at"),
        "expires_at": _p.get("expires_at"),
        "offer": offre_du_pass(_p, _offers),
        "offers": _offers,
        "version": version_pass(_p),
        "offer_history": [dict(e) for e in (_p.get("offer_history") or []) if isinstance(e, dict)],
    }
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
        "sponsor_first_name": prenom(_sp.get("name")),
        "course": _c,
        "occurrence": _p.get("occurrence"),
        "expired": statut in (EXPIRED, CANCELLED) or est_passee(_p.get("expires_at") or _p.get("occurrence"), now),
        "offer": offre_du_pass(_p, _offers),
        "offers": _offers,
        "version": version_pass(_p),
    }


def dto_admin(pass_doc, statut, tickets, frontend_url, offers=None) -> dict:
    """PassAdminDTO = PassDTO + prénoms ET e-mails (admin seulement)."""
    _d = dto_pass(pass_doc, statut, tickets, frontend_url, offers=offers)
    _sp = (pass_doc or {}).get("sponsor") or {}
    _inv = (pass_doc or {}).get("invitee") or {}
    _d["coach_id"] = (pass_doc or {}).get("coach_id")
    _d["sponsor"] = {"first_name": prenom(_sp.get("name")), "email": _sp.get("email_norm") or ""}
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

    _par_canal = {c: 0 for c in CANAUX}
    for _i in (invitations or []):
        _c = str((_i or {}).get("channel") or "")
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

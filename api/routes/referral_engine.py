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

VERSION = "V534"

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


def dto_pass(pass_doc, statut, tickets, frontend_url, deja_existant=None) -> dict:
    """PassDTO (parrain). Aucune donnée de l'invité au-delà de son prénom."""
    _p = pass_doc or {}
    _sp = _p.get("sponsor") or {}
    _inv = _p.get("invitee") or None
    _url = invite_url(frontend_url, _p.get("share_token"))
    _dto = {
        "id": _p.get("id"),
        "status": statut,
        "status_label": LIBELLES.get(statut, statut),
        "course": dto_course(_p),
        "occurrence": _p.get("occurrence"),
        "share_token": _p.get("share_token"),
        "invite_url": _url,
        "whatsapp_text": texte_whatsapp(prenom(_sp.get("name")), dto_course(_p)["name"],
                                        _p.get("occurrence"), _url),
        "invitee": {"first_name": prenom(_inv.get("name"))} if _inv else None,
        "tickets": list(tickets or []),
        "blocked_reason": _p.get("blocked_reason"),
        "created_at": _p.get("created_at"),
        "unlocked_at": _p.get("unlocked_at"),
        "expires_at": _p.get("expires_at"),
    }
    if deja_existant is not None:
        _dto["deja_existant"] = bool(deja_existant)
    return _dto


def dto_public(pass_doc, statut, now) -> dict:
    """La page publique `/duo/<token>` : AUCUN e-mail, AUCUN téléphone, AUCUN
    code. Juste de quoi dire « X t'invite à tel cours, tel jour »."""
    _p = pass_doc or {}
    _sp = _p.get("sponsor") or {}
    _c = dto_course(_p)
    _c.pop("id", None)
    return {
        "status": statut,
        "status_label": LIBELLES.get(statut, statut),
        "sponsor_first_name": prenom(_sp.get("name")),
        "course": _c,
        "occurrence": _p.get("occurrence"),
        "expired": statut in (EXPIRED, CANCELLED) or est_passee(_p.get("expires_at") or _p.get("occurrence"), now),
    }


def dto_admin(pass_doc, statut, tickets, frontend_url) -> dict:
    """PassAdminDTO = PassDTO + prénoms ET e-mails (admin seulement)."""
    _d = dto_pass(pass_doc, statut, tickets, frontend_url)
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
            _sortie.append({"at": _e.get("at"), "type": _t,
                            "label": LIBELLES_EVENEMENTS.get(_t, _t),
                            "pass_id": (_p or {}).get("id")})
    _sortie.sort(key=lambda x: str(x.get("at") or ""), reverse=True)
    return _sortie[:limite]


def stats_parrain(passes, invitations, statuts) -> dict:
    """`{invited, opened, joined, unlocked, used}` pour l'écran du parrain.
    `statuts` : dict pass_id -> statut dérivé (déjà calculé par l'appelant)."""
    _st = statuts or {}
    return {
        "invited": len(invitations or []),
        "opened": sum(1 for p in (passes or []) if (p or {}).get("opened_at")),
        "joined": sum(1 for p in (passes or []) if (p or {}).get("invitee")),
        "unlocked": sum(1 for p in (passes or []) if _st.get((p or {}).get("id")) in (UNLOCKED, USED)),
        "used": sum(1 for p in (passes or []) if _st.get((p or {}).get("id")) == USED),
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

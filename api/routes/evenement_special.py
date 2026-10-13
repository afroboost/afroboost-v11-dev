# -*- coding: utf-8 -*-
# V610 : ÉVÉNEMENT SPÉCIAL — réservation automatique, gratuité membres, date annulée.
"""V610 — Un événement payant à date unique (ex. AFROBOOST SILENT du 28/10/2026).

Ce module ne crée AUCUN nouveau parcours de paiement : le billet payant reste le
parcours progressif existant (prix 3 paliers imposé par le serveur, Stripe/TWINT,
webhook). Il ajoute trois choses, toutes ACTIVÉES PAR L'OFFRE (aucune offre
existante n'est concernée tant qu'elle ne porte pas ces champs) :

1. `evenement_reservation_auto: true` (offre `offer_type == "event"`, liée à UN
   cours à date fixe) : le paiement confirmé (webhook) crée LA réservation de
   l'événement. L'acheteur n'a rien à réserver une seconde fois.
2. `gratuit_abonnements_offer_ids: [...]` : un abonnement ACTIF de l'une de ces
   offres, dont les droits couvrent le début de l'événement, donne une place à
   0 CHF — sans Stripe, sans faux paiement, sans code d'accès supplémentaire.
   Le droit est PERSONNEL (e-mail prouvé par la session d'espace) : il ne se
   transmet jamais à un ami invité.
3. `dates_annulees: ["AAAA-MM-JJ"]` sur un COURS récurrent : ce jour-là le cours
   n'a pas lieu (l'événement le remplace) — aucun générateur d'occurrences ne le
   propose, aucune route ne le réserve.

AUCUNE CAPACITÉ : pas de plafond de places, pas de compteur (décision du 12/10).

ANTI-DOUBLON : chaque place passe par une RÉCLAMATION à clé unique
(`evenement_places._id`) — `stripe:<session>` pour un billet, `membre:<offre>:<e-mail>`
pour une place offerte. Un webhook rejoué ou un double clic retrouve la même
réservation ; jamais une deuxième.
"""
import logging
import re
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
PREFIXE = "[V610-EVT]"
COLL_PLACES = "evenement_places"
SOURCE_PAYANT = "paid_event_auto"
SOURCE_MEMBRE = "member_free_event"
RE_JOUR = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_HEURE = re.compile(r"^(\d{1,2}):(\d{2})")

try:
    from zoneinfo import ZoneInfo
    _ZURICH = ZoneInfo("Europe/Zurich")
except Exception:  # noqa: BLE001
    _ZURICH = timezone.utc



# ── 3. DATES ANNULÉES (cours récurrent remplacé ce jour-là) ─────────────────────
def dates_annulees(cours) -> set:
    _v = (cours or {}).get("dates_annulees") if isinstance(cours, dict) else None
    if not isinstance(_v, list):
        return set()
    return {str(x).strip()[:10] for x in _v if RE_JOUR.match(str(x).strip()[:10])}


def jour_annule(cours, jour) -> bool:
    """`jour` : date, datetime ou chaîne ISO (« 2026-10-28 » / « 2026-10-28T18:45:00 »)."""
    _annules = dates_annulees(cours)
    if not _annules or jour is None:
        return False
    try:
        _j = jour.isoformat() if hasattr(jour, "isoformat") else str(jour)
    except Exception:  # noqa: BLE001
        return False
    return _j[:10] in _annules


# ── L'ÉVÉNEMENT ─────────────────────────────────────────────────────────────────
def reservation_auto(offre) -> bool:
    _o = offre or {}
    return str(_o.get("offer_type") or "") == "event" and _o.get("evenement_reservation_auto") is True


def offres_gratuite(offre) -> list:
    """Les offres d'abonnement qui ouvrent la place offerte — [] si la règle n'est pas
    configurée OU si le coach l'a suspendue (`gratuit_membres_actif: false`, V610e)."""
    if (offre or {}).get("gratuit_membres_actif") is False:
        return []
    _v = (offre or {}).get("gratuit_abonnements_offer_ids")
    return [str(x) for x in _v if str(x or "").strip()] if isinstance(_v, list) else []


def regle_membres_configuree(offre) -> bool:
    """La règle « offert aux membres » existe-t-elle pour cette offre (active ou suspendue) ?"""
    _v = (offre or {}).get("gratuit_abonnements_offer_ids")
    return isinstance(_v, list) and any(str(x or "").strip() for x in _v)


async def cours_de_l_evenement(db, offre):
    """Le cours à DATE FIXE de l'événement (le premier lié qui en a une), ou None."""
    _ids = [str(x) for x in ((offre or {}).get("linked_course_ids") or []) if x]
    if not _ids:
        return None
    _cours = await db.courses.find({"id": {"$in": _ids}}, {"_id": 0}).to_list(20)
    _par_id = {c.get("id"): c for c in _cours}
    for _i in _ids:
        _c = _par_id.get(_i)
        if _c and RE_JOUR.match(str(_c.get("date") or "").strip()[:10]):
            return _c
    return None


def occurrence(cours) -> str:
    """« 2026-10-28T18:45:00 » (heure LOCALE de Zurich, naïve — convention des réservations)."""
    _d = str((cours or {}).get("date") or "").strip()[:10]
    _m = RE_HEURE.match(str((cours or {}).get("time") or "").strip())
    if not RE_JOUR.match(_d) or not _m:
        return ""
    return "%sT%02d:%02d:00" % (_d, int(_m.group(1)), int(_m.group(2)))


def debut_utc(occ):
    """Début de l'événement en UTC (l'occurrence est lue à l'heure de Zurich)."""
    try:
        return datetime.strptime(str(occ)[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=_ZURICH).astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def evenement_commence(occ, maintenant=None) -> bool:
    _d = debut_utc(occ)
    return _d is None or (maintenant or datetime.now(timezone.utc)) >= _d


def _date_utc(valeur):
    try:
        _d = valeur if isinstance(valeur, datetime) else datetime.fromisoformat(str(valeur or "").replace("Z", "+00:00"))
        return _d if _d.tzinfo else _d.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


# ── 2. GRATUITÉ MEMBRES ─────────────────────────────────────────────────────────
def abonnement_donne_droit(sub, ids_autorises, debut):
    """(bool, motif). Règle UNIQUE de la gratuité : l'abonnement est de l'une des
    offres désignées, ACTIF, et ses droits courent encore au début de l'événement.
    Un abonnement sans date de fin connue ne prouve rien -> refus."""
    _s = sub or {}
    if not ids_autorises or str(_s.get("offer_id") or "") not in set(ids_autorises):
        return False, "autre_offre"
    if str(_s.get("status") or "") != "active":
        return False, "inactif"
    _fin = _date_utc(_s.get("expires_at"))
    if _fin is None:
        return False, "fin_inconnue"
    if debut is None or _fin < debut:
        return False, "expire_avant_evenement"
    return True, "ok"


async def abonnement_gratuit(db, email, offre, debut):
    """L'abonnement (de CETTE personne) qui lui donne la place offerte, ou None.

    V618 — SEUL l'abonnement ACTUEL (résolveur canonique) compte : jamais un ancien abonnement
    resté « active », jamais un autre abonnement de l'historique. Plusieurs abonnements actuels
    (conflit) -> aucune gratuité tant que le coach n'a pas tranché (fail closed, coach prévenu)."""
    _e = str(email or "").strip().lower()
    _ids = offres_gratuite(offre)
    if not _e or "@" not in _e or not _ids:
        return None
    from api.routes.abonnement_actuel import resoudre_abonnement_actuel, ETAT_COURANT, locataire
    # V618-b : résolu CHEZ le coach de l'événement (un abonnement chez un autre coach ne compte
    # ni pour accorder, ni pour créer un faux conflit).
    _r = await resoudre_abonnement_actuel(db, _e, perimetre=locataire((offre or {}).get("coach_id")))
    if _r["etat"] != ETAT_COURANT:
        return None
    _actuel = await db.subscriptions.find_one({"id": _r["abonnement"].get("id")}, {"_id": 0}) or _r["abonnement"]
    return _actuel if abonnement_donne_droit(_actuel, _ids, debut)[0] else None


# ── 1 + 2. LA RÉSERVATION (une seule par réclamation) ──────────────────────────
async def assurer_index(database) -> None:
    """`_id` est déjà unique : rien à créer. Index de lecture seulement."""
    try:
        await database[COLL_PLACES].create_index("reservation_id")
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s index non posé (%s)", PREFIXE, type(_err).__name__)


def _doublon(err) -> bool:
    return type(err).__name__ == "DuplicateKeyError" or "e11000" in str(err).lower()


async def _deja(db, cle):
    """(réservation, la_réclamation_existe). Une réclamation dont la réservation a été
    ANNULÉE (supprimée) est libérée : la personne peut réserver à nouveau."""
    _r = await db[COLL_PLACES].find_one({"_id": cle})
    if _r and _r.get("reservation_id"):
        _resa = await db.reservations.find_one({"id": _r["reservation_id"]}, {"_id": 0})
        if _resa:
            return _resa, True
        await db[COLL_PLACES].delete_one({"_id": cle, "reservation_id": _r["reservation_id"]})
        return None, False
    return None, bool(_r)


async def reserver(db, *, cle, offre, cours, occ, email, nom, prix, source, code="", whatsapp="",
                   subscription_id=None, extra=None):
    """(reservation, creee). `creee=False` : la réclamation existait (rejeu / double
    clic) -> la réservation DÉJÀ créée est rendue, ou None si elle est en cours."""
    _resa, _existe = await _deja(db, cle)
    if _existe:
        return _resa, False
    _maintenant = datetime.now(timezone.utc).isoformat()
    try:
        await db[COLL_PLACES].insert_one({"_id": cle, "offer_id": (offre or {}).get("id"), "source": source,
                                          "statut": "en_cours", "created_at": _maintenant})
    except Exception as _err:  # noqa: BLE001
        if _doublon(_err):
            _resa, _ = await _deja(db, cle)
            return _resa, False
        raise
    _email = str(email or "").strip().lower()
    _id = str(uuid.uuid4())
    _doc = {
        "id": _id,
        "reservationCode": "AF%s" % uuid.uuid4().hex[:8].upper(),
        "userName": str(nom or "").strip()[:80] or (_email.split("@")[0] if "@" in _email else "Participant"),
        "userEmail": _email,
        "userWhatsapp": str(whatsapp or "")[:40],
        "courseId": (cours or {}).get("id"),
        "courseName": (cours or {}).get("name"),
        "courseTime": (cours or {}).get("time"),
        "datetime": occ,
        "offerId": (offre or {}).get("id"),
        "offerName": (offre or {}).get("name"),
        "price": float(prix or 0),
        "quantity": 1,
        "totalPrice": float(prix or 0),
        "discountCode": str(code or "").upper(),
        "promoCode": str(code or "").upper(),
        "source": source,
        "type": "ticket",
        "validated": False,
        "validatedAt": None,
        "createdAt": _maintenant,
        "coach_id": (cours or {}).get("coach_id") or (offre or {}).get("coach_id") or "",
        "guests": [],
        "guest_headphones": [],
        "evenement_place_cle": cle,
    }
    if subscription_id:
        _doc["subscriptionId"] = str(subscription_id)
    if isinstance(extra, dict):
        _doc.update(extra)
    try:
        await db.reservations.insert_one(dict(_doc))
    except Exception:
        await db[COLL_PLACES].delete_one({"_id": cle, "statut": "en_cours"})   # un nouvel essai reste possible
        raise
    await db[COLL_PLACES].update_one({"_id": cle}, {"$set": {"reservation_id": _id, "statut": "reservee",
                                                             "reserve_le": datetime.now(timezone.utc).isoformat()}})
    logger.info("%s réservation %s (%s) — offre %s, %s", PREFIXE, _doc["reservationCode"], source,
                str((offre or {}).get("id"))[:8], occ)
    return _doc, True


# ── 1. APRÈS PAIEMENT (webhook) ─────────────────────────────────────────────────
async def apres_paiement(db, *, session_id, offre_id, email, nom, code, subscription_id, montant, whatsapp=""):
    """Billet payé -> réservation de l'événement. Rend (reservation, creee) ou (None, False)
    si l'offre n'est pas un événement à réservation automatique. Lève en cas de panne :
    l'appelant (webhook) l'enveloppe — le paiement encaissé ne dépend jamais de ceci."""
    if not session_id or not offre_id:
        return None, False
    _offre = await db.offers.find_one({"id": str(offre_id)}, {"_id": 0})
    if not reservation_auto(_offre):
        return None, False
    _cours = await cours_de_l_evenement(db, _offre)
    _occ = occurrence(_cours)
    if not _occ:
        logger.error("%s offre %s : aucun cours à date fixe — réservation NON créée", PREFIXE, str(offre_id)[:8])
        return None, False
    return await reserver(db, cle="stripe:%s" % session_id, offre=_offre, cours=_cours, occ=_occ, email=email,
                          nom=nom, prix=montant, source=SOURCE_PAYANT, code=code, whatsapp=whatsapp,
                          subscription_id=subscription_id,
                          extra={"stripe_session_id": str(session_id), "paiement": "stripe"})


# ── GARDE : un cours d'événement à billet ne se réserve JAMAIS avec une séance ──
MSG_BILLET_REQUIS = ("Cet événement se réserve avec son billet — ou avec ta place offerte "
                     "si tu as un abonnement 8 mois actif.")


async def offres_billet_par_cours(db) -> dict:
    """{course_id: offer_id} des cours rattachés à un événement à réservation automatique."""
    _sortie = {}
    for _o in await db.offers.find({"offer_type": "event", "evenement_reservation_auto": True, "archived": {"$ne": True}},
                                   {"_id": 0, "id": 1, "linked_course_ids": 1}).to_list(50):
        for _c in (_o.get("linked_course_ids") or []):
            _sortie.setdefault(str(_c), _o.get("id"))
    return _sortie


async def cours_a_billet(db, course_id):
    """L'id de l'offre-événement si CE cours ne se réserve qu'avec un billet (ou une place
    offerte), sinon None. Un forfait — même « tous les cours » (offre ancienne sans liste)
    — n'y donne pas accès : sinon l'événement payant se prendrait contre une séance."""
    if not course_id:
        return None
    _o = await db.offers.find_one({"offer_type": "event", "evenement_reservation_auto": True, "archived": {"$ne": True},
                                   "linked_course_ids": str(course_id)}, {"_id": 0, "id": 1})
    return (_o or {}).get("id")


MSG_PANIER = ("Cet événement se réserve depuis sa page : le prix suit les paliers "
              "et ta place est réservée automatiquement au paiement.")


async def article_hors_panier(db, item_id) -> bool:
    """Le panier (`/api/checkout/create-session` et `/free`) ne vend NI l'offre d'un
    événement à réservation automatique (son palier serait ignoré, aucune place
    réservée), NI le cours de cet événement (prix annoncé par le client)."""
    _i = str(item_id or "").strip()
    if not _i:
        return False
    _o = await db.offers.find_one({"id": _i}, {"_id": 0, "offer_type": 1, "evenement_reservation_auto": 1})
    return reservation_auto(_o) or bool(await cours_a_billet(db, _i))


# ── 2. ÉVÉNEMENTS OFFERTS VISIBLES DANS L'ESPACE ────────────────────────────────
async def evenements_offerts(db, email, coach_id=None, maintenant=None):
    """Pour l'espace : les événements dont CETTE personne a la place offerte."""
    _e = str(email or "").strip().lower()
    if not _e:
        return []
    # Une offre MASQUÉE (brouillon, pas encore publiée) n'apparaît dans aucun espace.
    _q = {"offer_type": "event", "gratuit_abonnements_offer_ids.0": {"$exists": True}, "archived": {"$ne": True},
          "visible": {"$ne": False}, "gratuit_membres_actif": {"$ne": False}}
    _sortie = []
    for _o in await db.offers.find(_q, {"_id": 0}).to_list(20):
        if coach_id and _o.get("coach_id") and str(_o.get("coach_id")).lower() != str(coach_id).lower():
            continue
        _c = await cours_de_l_evenement(db, _o)
        _occ = occurrence(_c)
        if not _occ or evenement_commence(_occ, maintenant):
            continue
        _sub = await abonnement_gratuit(db, _e, _o, debut_utc(_occ))
        if not _sub:
            continue
        _resa, _ = await _deja(db, "membre:%s:%s" % (_o.get("id"), _e))
        _sortie.append({"offer_id": _o.get("id"), "titre": _o.get("name"), "datetime": _occ,
                        "lieu": (_c or {}).get("locationName") or (_c or {}).get("location") or _o.get("location") or "",
                        "course_id": (_c or {}).get("id"), "deja_reserve": bool(_resa),
                        "reservation_code": (_resa or {}).get("reservationCode")})
    return _sortie

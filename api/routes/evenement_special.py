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
SOURCE_CODE = "promo_code_event"   # V628 : place offerte par un code promo réservé à l'événement
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


# ── V618M — AVANTAGES MEMBRES PAR OFFRE (réglés par le coach, jamais codés en dur) ──
# `avantages_membres` sur l'offre-événement : [{"offer_id": <id d'offre d'abonnement>,
#   "type": "gratuit" | "reduction" | "prix_fixe" | "aucun", "valeur": <% ou CHF>}].
# Ancienne forme (V610) : `gratuit_abonnements_offer_ids: [ids]` = « gratuit » pour chacune.
# Tant qu'un événement n'a pas `avantages_membres`, l'ancienne forme est LUE à l'identique :
# l'éligibilité d'avant la migration est conservée exactement.
TYPES_AVANTAGE = ("gratuit", "reduction", "prix_fixe", "aucun")
PRIX_FIXE_MAX = 10000.0


def _regle_valide(r):
    """{"type", "valeur"} propre, ou None (entrée illisible ignorée)."""
    if not isinstance(r, dict):
        return None
    _t = str(r.get("type") or "").strip()
    if _t not in TYPES_AVANTAGE:
        return None
    if _t == "reduction":
        try:
            _v = int(float(r.get("valeur")))
        except (TypeError, ValueError):
            return None
        if not 1 <= _v <= 100:
            return None
        return {"type": "gratuit", "valeur": None} if _v == 100 else {"type": "reduction", "valeur": _v}
    if _t == "prix_fixe":
        try:
            _v = round(float(r.get("valeur")), 2)
        except (TypeError, ValueError):
            return None
        if not 0 <= _v <= PRIX_FIXE_MAX:
            return None
        return {"type": "gratuit", "valeur": None} if _v == 0 else {"type": "prix_fixe", "valeur": _v}
    return {"type": _t, "valeur": None}


def avantages_configures(offre) -> list:
    """La configuration telle que le coach la voit (y compris « aucun »), forme normalisée."""
    _o = offre or {}
    _v = _o.get("avantages_membres")
    _sortie, _vus = [], set()
    if isinstance(_v, list):
        for _e in _v:
            _id = str((_e or {}).get("offer_id") or "").strip() if isinstance(_e, dict) else ""
            _r = _regle_valide(_e)
            if _id and _r and _id not in _vus:
                _vus.add(_id)
                _sortie.append(dict(_r, offer_id=_id))
        return _sortie
    _ids = _o.get("gratuit_abonnements_offer_ids")
    for _i in (_ids if isinstance(_ids, list) else []):
        _id = str(_i or "").strip()
        if _id and _id not in _vus:
            _vus.add(_id)
            _sortie.append({"offer_id": _id, "type": "gratuit", "valeur": None})
    return _sortie


def regles_avantages(offre) -> dict:
    """{offer_id: {"type", "valeur"}} des avantages EFFECTIFS ({} si suspendus par le coach,
    `gratuit_membres_actif: false`). « aucun » n'y figure pas."""
    if (offre or {}).get("gratuit_membres_actif") is False:
        return {}
    return {_e["offer_id"]: {"type": _e["type"], "valeur": _e["valeur"]}
            for _e in avantages_configures(offre) if _e["type"] != "aucun"}


def a_des_avantages(offre) -> bool:
    return bool(regles_avantages(offre))


def offres_gratuite(offre) -> list:
    """Les offres d'abonnement qui ouvrent la place OFFERTE (0 CHF) — [] si aucune, ou si le
    coach a suspendu les avantages (`gratuit_membres_actif: false`, V610e)."""
    return [_i for _i, _r in regles_avantages(offre).items() if _r["type"] == "gratuit"]


def regle_membres_configuree(offre) -> bool:
    """Une configuration d'avantages existe-t-elle (active ou suspendue) ?"""
    return any(_e["type"] != "aucun" for _e in avantages_configures(offre))


def prix_membre(regle, prix_public):
    """Le prix du MEMBRE (CHF, au centime, arrondi commercial) — jamais au-dessus du prix
    public : un « avantage » qui majore n'en est pas un (le prix public s'applique)."""
    from decimal import Decimal, ROUND_HALF_UP
    try:
        _pub = Decimal(str(float(prix_public or 0)))
    except (TypeError, ValueError):
        _pub = Decimal("0")
    _t = (regle or {}).get("type")
    if _t == "gratuit":
        _m = Decimal("0")
    elif _t == "reduction":
        _m = _pub * (Decimal(100) - Decimal(int((regle or {}).get("valeur") or 0))) / Decimal(100)
    elif _t == "prix_fixe":
        _m = Decimal(str(float((regle or {}).get("valeur") or 0)))
    else:
        _m = _pub
    _m = min(_m, _pub).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(max(_m, Decimal("0")))


# ── V618M — CAPACITÉ RÉELLE (optionnelle, séparée du texte marketing) ─────────────
CAPACITE_MAX = 10000


def capacite(offre):
    """Le nombre maximum de places si le coach a ACTIVÉ la limite, sinon None (aucune
    limite). Jamais déduite d'un texte (« 50 PLACES » n'est qu'un message)."""
    _o = offre or {}
    if _o.get("capacite_limitee") is not True:
        return None
    try:
        _c = int(_o.get("capacite_max"))
    except (TypeError, ValueError):
        return None
    return _c if 1 <= _c <= CAPACITE_MAX else None


async def places_prises(db, offre) -> int:
    """Places RÉELLEMENT réservées pour cet événement (billets payés + places membres)."""
    return int(await db[COLL_PLACES].count_documents({"offer_id": (offre or {}).get("id"), "statut": "reservee"}))


# ── V657 : CAPACITÉ ATOMIQUE (verrou court par offre + retenues) ────────────────
# OCCUPATION = places réservées (réclamations « reservee »)
#            + retenues de paiement Stripe encore vivantes (1 place chacune)
#            + places RETENUES par les contrats Corporate signés, moins celles déjà
#              réclamées par ce contrat (une place Corporate prise n'est jamais
#              comptée deux fois : elle est soit « retenue », soit « réservée »).
# ATOMICITÉ : toute prise de place sur un événement À CAPACITÉ LIMITÉE se fait sous
# un verrou court propre à l'offre (`evenement_verrous`, `_id` unique = exclusion
# mutuelle, expiration 15 s pour qu'un processus mort ne bloque jamais l'événement).
# Sous le verrou : on compte, puis on écrit. Deux demandes simultanées ne peuvent
# donc jamais lire la même occupation. Sans capacité (cas par défaut) : AUCUN verrou,
# aucune retenue, comportement d'avant strictement identique.
COLL_RETENUES = "evenement_retenues"
COLL_VERROUS = "evenement_verrous"
RETENUE_STRIPE = "stripe"
RETENUE_CORPORATE = "corporate"
# V657b : une retenue de paiement ne bloque une place que 35 minutes, pas toute la vie de la session Stripe
# (24 h) : sinon quelques paiements abandonnés suffiraient à vider la jauge. V657d : un paiement tardif
# n'est confirmé que s'il reste une place ; sinon il est tracé, signalé, et la place n'est PAS donnée.
RETENUE_STRIPE_DUREE_S = 35 * 60
# V657d : la session Stripe d'un événement à capacité expire à 31 min (minimum Stripe : 30) ;
# la retenue (35 min) lui survit toujours : un paiement dans les temps trouve sa place.
SESSION_STRIPE_DUREE_S = 31 * 60
VERROU_DUREE_S = 15
MSG_OCCUPE = "Beaucoup de demandes en même temps pour cet événement. Réessaie dans un instant."


class VerrouIndisponible(Exception):
    """Le verrou de l'offre n'a pas pu être pris dans le délai (forte concurrence)."""


class verrou_capacite:   # noqa: N801 — s'utilise comme `async with verrou_capacite(db, offre):`
    """Verrou court par offre. No-op pour un événement sans capacité (ou `force=False`
    et capacité absente). `attente_s` : temps maximum d'attente avant VerrouIndisponible."""

    def __init__(self, db, offre, attente_s=8.0, force=False):
        self.db, self.offre, self.attente_s = db, offre or {}, float(attente_s)
        self.actif = bool(force or capacite(self.offre) is not None) and bool(self.offre.get("id"))
        self.jeton = None

    async def __aenter__(self):
        if not self.actif:
            return self
        import asyncio
        import random
        import time
        from datetime import timedelta
        _cle = "evt:%s" % self.offre.get("id")
        _jeton = uuid.uuid4().hex
        _limite = time.monotonic() + self.attente_s
        while True:
            _now = datetime.now(timezone.utc)
            _jusqu = _now + timedelta(seconds=VERROU_DUREE_S)
            try:
                await self.db[COLL_VERROUS].insert_one({"_id": _cle, "jeton": _jeton, "jusqu_a": _jusqu})
                break
            except Exception as _err:  # noqa: BLE001
                if not _doublon(_err):
                    raise
            # Verrou abandonné (processus tombé) : repris seulement s'il a EXPIRÉ.
            _pris = await self.db[COLL_VERROUS].find_one_and_update(
                {"_id": _cle, "jusqu_a": {"$lt": _now}}, {"$set": {"jeton": _jeton, "jusqu_a": _jusqu}})
            if _pris:
                break
            if time.monotonic() > _limite:
                raise VerrouIndisponible(_cle)
            await asyncio.sleep(0.01 + random.random() * 0.03)
        self.jeton = _jeton
        return self

    async def __aexit__(self, *exc):
        if self.jeton:
            try:
                await self.db[COLL_VERROUS].delete_one({"_id": "evt:%s" % self.offre.get("id"), "jeton": self.jeton})
            except Exception as _err:  # noqa: BLE001 — il expirera de lui-même (15 s)
                logger.warning("%s verrou non rendu (%s)", PREFIXE, type(_err).__name__)
        return False


async def places_corporate_reclamees(db, offer_id, contrat_id) -> int:
    return int(await db[COLL_PLACES].count_documents(
        {"offer_id": offer_id, "statut": "reservee", "corporate_contract_id": contrat_id}))


async def occupation(db, offre) -> int:
    """V657 — places occupées ou retenues (voir l'en-tête de la section)."""
    _oid = (offre or {}).get("id")
    _n = await places_prises(db, offre)
    _now = datetime.now(timezone.utc)
    _n += int(await db[COLL_RETENUES].count_documents(
        {"offer_id": _oid, "type": RETENUE_STRIPE, "statut": "active", "expire_le": {"$gt": _now}}))
    async for _r in db[COLL_RETENUES].find({"offer_id": _oid, "type": RETENUE_CORPORATE, "statut": "active"},
                                           {"_id": 0, "places": 1, "corporate_contract_id": 1}):
        _pris = await places_corporate_reclamees(db, _oid, _r.get("corporate_contract_id"))
        _n += max(0, int(_r.get("places") or 0) - _pris)
    return _n


async def places_restantes(db, offre):
    """None = illimité ; sinon le nombre de places encore libres (jamais négatif)."""
    _c = capacite(offre)
    if _c is None:
        return None
    return max(0, _c - await occupation(db, offre))


async def complet(db, offre) -> bool:
    _c = capacite(offre)
    return _c is not None and await occupation(db, offre) >= _c


async def retenir_place_paiement(db, offre):
    """V657 — avant d'ouvrir un paiement Stripe pour un événement À CAPACITÉ : retient UNE
    place (sous verrou). Rend l'id de la retenue, None si l'événement est sans capacité.
    Lève `VerrouIndisponible`, ou `ValueError(MSG_COMPLET)` s'il n'y a plus de place."""
    if capacite(offre) is None:
        return None
    from datetime import timedelta
    async with verrou_capacite(db, offre):
        if await complet(db, offre):
            raise ValueError(MSG_COMPLET)
        _id = "rt-%s" % uuid.uuid4().hex
        _now = datetime.now(timezone.utc)
        await db[COLL_RETENUES].insert_one({
            "_id": _id, "id": _id, "offer_id": offre.get("id"), "type": RETENUE_STRIPE, "places": 1,
            "statut": "active", "cree_le": _now, "expire_le": _now + timedelta(seconds=RETENUE_STRIPE_DUREE_S)})
        return _id


async def liberer_retenue(db, retenue_id, motif="") -> bool:
    """Libère une retenue de paiement (session expirée, échec Stripe). Idempotent."""
    if not retenue_id:
        return False
    _r = await db[COLL_RETENUES].update_one(
        {"_id": str(retenue_id)[:80], "type": RETENUE_STRIPE, "statut": "active"},
        {"$set": {"statut": "liberee", "motif": str(motif or "")[:60], "liberee_le": datetime.now(timezone.utc)}})
    return bool(getattr(_r, "modified_count", 0))


async def retenue_vivante(db, retenue_id) -> bool:
    if not retenue_id:
        return False
    return bool(await db[COLL_RETENUES].find_one(
        {"_id": str(retenue_id)[:80], "type": RETENUE_STRIPE, "statut": "active",
         "expire_le": {"$gt": datetime.now(timezone.utc)}}, {"_id": 1}))


async def reserver_si_place(db, *, offre, **kw):
    """V657 — `reserver` derrière la capacité. Rend (reservation, creee, refus) ;
    refus = MSG_COMPLET quand l'événement à capacité limitée est plein. Une personne
    DÉJÀ inscrite (même réclamation) retrouve sa place sans consommer de capacité."""
    if capacite(offre) is None:
        _r, _c = await reserver(db, offre=offre, **kw)
        return _r, _c, None
    async with verrou_capacite(db, offre):
        _resa, _existe = await _deja(db, kw.get("cle"))
        if _existe:
            return _resa, False, None
        if await complet(db, offre):
            return None, False, MSG_COMPLET
        _r, _c = await reserver(db, offre=offre, **kw)
        return _r, _c, None


MSG_COMPLET = "Cet événement est complet."


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


async def avantage_du_membre(db, email, offre, debut):
    """V618M — (abonnement ACTUEL, règle) de CETTE personne pour cet événement, ou (None, None).
    L'avantage suit l'offre RÉELLE (`offer_id`) de son abonnement actuel (résolveur canonique) :
    jamais un titre, jamais un ancien abonnement, jamais celui d'un autre (l'ami ne l'hérite pas)."""
    _e = str(email or "").strip().lower()
    _regles = regles_avantages(offre)
    if not _e or "@" not in _e or not _regles:
        return None, None
    from api.routes.abonnement_actuel import resoudre_abonnement_actuel, ETAT_COURANT, locataire
    _r = await resoudre_abonnement_actuel(db, _e, perimetre=locataire((offre or {}).get("coach_id")))
    if _r["etat"] != ETAT_COURANT:
        return None, None
    _actuel = await db.subscriptions.find_one({"id": _r["abonnement"].get("id")}, {"_id": 0}) or _r["abonnement"]
    if not abonnement_donne_droit(_actuel, list(_regles), debut)[0]:
        return None, None
    return _actuel, _regles.get(str(_actuel.get("offer_id") or ""))


async def tarif_membre(db, email, offre, prix_public):
    """V618M — LA décision tarifaire d'un membre PROUVÉ pour cet événement :
    {"prix", "regle", "abonnement"}. `regle` None = aucun avantage (prix public). Une règle
    « gratuit » se réserve dans l'espace, jamais par Stripe : l'appelant la refuse au paiement."""
    _cours = await cours_de_l_evenement(db, offre)
    _sub, _regle = await avantage_du_membre(db, email, offre, debut_utc(occurrence(_cours)))
    _pub = float(prix_public or 0)
    if not _regle:
        return {"prix": _pub, "regle": None, "abonnement": None}
    return {"prix": prix_membre(_regle, _pub), "regle": _regle, "abonnement": _sub}


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
                   subscription_id=None, extra=None, reservation_id=None, place_extra=None):
    """(reservation, creee). `creee=False` : la réclamation existait (rejeu / double
    clic) -> la réservation DÉJÀ créée est rendue, ou None si elle est en cours.
    V657 : `place_extra` = champs ajoutés à la RÉCLAMATION (ex. `corporate_contract_id`)."""
    _resa, _existe = await _deja(db, cle)
    if _existe:
        return _resa, False
    _maintenant = datetime.now(timezone.utc).isoformat()
    _place = {"_id": cle, "offer_id": (offre or {}).get("id"), "source": source,
              "statut": "en_cours", "created_at": _maintenant}
    if isinstance(place_extra, dict):
        _place.update({k: v for k, v in place_extra.items() if k not in _place})
    try:
        await db[COLL_PLACES].insert_one(_place)
    except Exception as _err:  # noqa: BLE001
        if _doublon(_err):
            _resa, _ = await _deja(db, cle)
            return _resa, False
        raise
    _email = str(email or "").strip().lower()
    # V628 : l'appelant peut fixer l'id (place par code : le débit du code porte la MÊME clé).
    _id = str(reservation_id or "") or str(uuid.uuid4())
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


async def liberer_place(db, reservation, session=None) -> bool:
    """V628 — la réservation d'événement vient d'être SUPPRIMÉE : sa réclamation de place l'est
    aussi (sinon la place resterait comptée et la même personne ne pourrait pas se réinscrire
    sans repasser par `_deja`). Seule la réclamation de CETTE réservation est visée."""
    _r = reservation or {}
    _cle, _rid = _r.get("evenement_place_cle"), _r.get("id")
    if not _cle or not _rid:
        return False
    _k = {"session": session} if session is not None else {}
    _res = await db[COLL_PLACES].delete_one({"_id": _cle, "reservation_id": _rid}, **_k)
    return bool(getattr(_res, "deleted_count", 0))


# ── 1. APRÈS PAIEMENT (webhook) ─────────────────────────────────────────────────
async def apres_paiement(db, *, session_id, offre_id, email, nom, code, subscription_id, montant, whatsapp="",
                         retenue_id=None):
    """Billet payé -> réservation de l'événement. Rend (reservation, creee) ou (None, False)
    si l'offre n'est pas un événement à réservation automatique. Lève en cas de panne :
    l'appelant (webhook) l'enveloppe — le paiement encaissé ne dépend jamais de ceci.

    V657 — événement À CAPACITÉ : la place a été RETENUE à l'ouverture du paiement
    (`retenue_id`, metadata Stripe ; la retenue vit 35 min, la session Stripe 31 min).
    Sous verrou :
      * retenue VIVANTE -> convertie en réservation, une seule fois ;
      * pas de retenue vivante (paiement tardif) -> confirmée SEULEMENT s'il reste une place ;
      * sinon (V657d) la place n'est PAS confirmée : le paiement reste enregistré tel quel par
        le webhook (code, souscription, transaction), une réclamation `en_attente_place` garde
        la trace (aucun billet, aucun QR d'entrée), journal d'erreur + notification du tableau
        de bord. Aucun remboursement automatique : l'admin décide.
    Un rejeu du même webhook retrouve la même réclamation : jamais une deuxième place."""
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
    _kw = dict(cle="stripe:%s" % session_id, offre=_offre, cours=_cours, occ=_occ, email=email,
               nom=nom, prix=montant, source=SOURCE_PAYANT, code=code, whatsapp=whatsapp,
               subscription_id=subscription_id,
               extra={"stripe_session_id": str(session_id), "paiement": "stripe"})
    if capacite(_offre) is None:
        return await reserver(db, **_kw)
    try:
        async with verrou_capacite(db, _offre, attente_s=20):
            _resa, _existe = await _deja(db, _kw["cle"])
            if _existe:
                await liberer_retenue(db, retenue_id, "deja_traite")
                return _resa, False
            if await retenue_vivante(db, retenue_id) or not await complet(db, _offre):
                _r = await reserver(db, **_kw)
                await db[COLL_RETENUES].update_one({"_id": str(retenue_id or "")[:80], "statut": "active"},
                                                   {"$set": {"statut": "convertie", "session_id": str(session_id),
                                                             "convertie_le": datetime.now(timezone.utc)}})
                return _r
            await place_bloquee(db, offre=_offre, session_id=session_id, email=email, montant=montant,
                                code=code, subscription_id=subscription_id, retenue_id=retenue_id, motif="complet")
            return None, False
    except VerrouIndisponible:
        # Jamais de place sans verrou (elle pourrait être donnée deux fois) : le paiement est tracé.
        await place_bloquee(db, offre=_offre, session_id=session_id, email=email, montant=montant,
                            code=code, subscription_id=subscription_id, retenue_id=retenue_id, motif="verrou")
        return None, False


STATUT_EN_ATTENTE = "en_attente_place"
TYPE_NOTIF_BLOQUEE = "evenement_place_bloquee"


async def place_bloquee(db, *, offre, session_id, email, montant, code, subscription_id, retenue_id, motif):
    """V657d — paiement reçu SANS place confirmable : trace idempotente (réclamation
    `stripe:<session>` au statut `en_attente_place`, jamais comptée comme place), journal
    d'erreur et notification du tableau de bord (sans e-mail ni code). Aucun remboursement."""
    _now = datetime.now(timezone.utc).isoformat()
    try:
        await db[COLL_PLACES].insert_one({
            "_id": "stripe:%s" % session_id, "offer_id": (offre or {}).get("id"), "source": SOURCE_PAYANT,
            "statut": STATUT_EN_ATTENTE, "surreservation_bloquee": True, "motif": motif,
            "stripe_session_id": str(session_id), "email": str(email or "").strip().lower(),
            "montant": float(montant or 0), "code": str(code or "").upper(), "subscription_id": subscription_id,
            "retenue_id": retenue_id, "created_at": _now})
    except Exception as _err:  # noqa: BLE001
        if not _doublon(_err):
            raise
        return
    logger.error("%s PAIEMENT SANS PLACE : session %s, offre %s (%s) — place NON confirmée, à traiter par l'admin",
                 PREFIXE, str(session_id)[:24], str((offre or {}).get("id"))[:8], motif)
    try:
        await db["notifications"].update_one({"id": "evt_bloquee_%s" % session_id}, {"$setOnInsert": {
            "id": "evt_bloquee_%s" % session_id, "type": TYPE_NOTIF_BLOQUEE,
            "title": "Paiement reçu sans place disponible — à traiter",
            "message": "Un billet payé pour « %s » n'a pas pu recevoir de place (événement complet). "
                       "Aucun billet n'a été émis ; décide d'une place ou d'un remboursement." % ((offre or {}).get("name") or ""),
            "coach_id": proprietaire_evenement(offre) or "contact.artboost@gmail.com",
            "read": False, "created_at": _now}}, upsert=True)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s notification non écrite (%s)", PREFIXE, type(_err).__name__)


# ── GARDE : un cours d'événement à billet ne se réserve JAMAIS avec une séance ──
MSG_BILLET_REQUIS = ("Cet événement se réserve avec son billet — ou avec ton avantage membre "
                     "depuis ton espace, si ton abonnement en donne un.")


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
    _q = {"offer_type": "event", "archived": {"$ne": True}, "visible": {"$ne": False},
          "gratuit_membres_actif": {"$ne": False},
          "$or": [{"gratuit_abonnements_offer_ids": {"$exists": True, "$ne": []}},
                  {"avantages_membres": {"$exists": True, "$ne": []}}]}
    _sortie = []
    for _o in await db.offers.find(_q, {"_id": 0}).to_list(20):
        if coach_id and _o.get("coach_id") and str(_o.get("coach_id")).lower() != str(coach_id).lower():
            continue
        _c = await cours_de_l_evenement(db, _o)
        _occ = occurrence(_c)
        if not _occ or evenement_commence(_occ, maintenant):
            continue
        _sub, _regle = await avantage_du_membre(db, _e, _o, debut_utc(_occ))
        if not _sub or not _regle:
            continue
        # V618M : le prix PUBLIC du moment (serveur) et le prix du MEMBRE qui en découle.
        from api.pricing import compute_active_price
        _pub = float(compute_active_price(_o).get("price") or 0)
        _resa, _ = await _deja(db, "membre:%s:%s" % (_o.get("id"), _e))
        if not _resa:
            _resa = await db.reservations.find_one(
                {"offerId": _o.get("id"), "userEmail": _e, "source": SOURCE_PAYANT}, {"_id": 0})
        _jeton = await db.referral_campaigns.find_one(
            {"offer_id": _o.get("id"), "status": "active", "type": "event_paid", "share_token": {"$type": "string"}},
            {"_id": 0, "share_token": 1})
        _sortie.append({"offer_id": _o.get("id"), "titre": _o.get("name"), "datetime": _occ,
                        "lieu": (_c or {}).get("locationName") or (_c or {}).get("location") or _o.get("location") or "",
                        "course_id": (_c or {}).get("id"), "deja_reserve": bool(_resa),
                        "reservation_code": (_resa or {}).get("reservationCode"),
                        "avantage": {"type": _regle["type"], "valeur": _regle["valeur"],
                                     "prix_public": _pub, "prix_membre": prix_membre(_regle, _pub)},
                        "complet": await complet(db, _o),
                        "jeton_invitation": (_jeton or {}).get("share_token") or ""})
    return _sortie


# ── V628 : PLACE PAR CODE PROMO (ex. invités Hétaira, 28/10/2026) ───────────────
# Un code promo EXISTANT (`discount_codes`) donne une place à 0 CHF à UN événement à
# réservation automatique, et à lui seul. Rien de neuf côté codes : type 100 %, quota
# `maxUses`, `used`, expiration, `assignedEmail` — tout est lu tel que le coach le règle.
#
# « RÉSERVÉ À CET ÉVÉNEMENT » = les articles autorisés du code (`courses`) sont TOUS des
# identifiants de cet événement (son offre ou son cours daté), et il y en a au moins un.
# Un code « tous les articles » n'est PAS un code d'événement : refusé ici (il n'a pas été
# explicitement réglé pour lui). Un code d'événement, à l'inverse, est refusé par toutes
# les autres portes (réservation de cours, espace, remise de paiement, Live, Pass Duo).
MSG_CODE_INVALIDE = "Code promo invalide ou expiré."
MSG_CODE_UTILISE = "Ce code promo a déjà été utilisé."
MSG_CODE_RESERVE_EVENEMENT = ("Ce code promo est réservé à un événement : utilise-le depuis la page "
                              "de l'événement (« J'ai un code promo »).")


def _sans_accents(texte) -> str:
    import unicodedata
    _t = unicodedata.normalize("NFKD", str(texte or "").strip().upper())
    return "".join(c for c in _t if not unicodedata.combining(c))


def ids_evenement(offre) -> set:
    """L'offre-événement et ses cours liés : les seuls articles qu'un code d'événement peut viser."""
    _o = offre or {}
    _ids = {str(x) for x in (_o.get("linked_course_ids") or []) if x}
    if _o.get("id"):
        _ids.add(str(_o.get("id")))
    return _ids


def code_reserve_a(code_doc, ids) -> bool:
    _cs = {str(x) for x in ((code_doc or {}).get("courses") or []) if x}
    return bool(_cs) and bool(ids) and _cs <= set(ids)


def code_gratuit_total(code_doc) -> bool:
    _t = str((code_doc or {}).get("type") or "")
    try:
        _v = float((code_doc or {}).get("value") or 0)
    except (TypeError, ValueError):
        _v = 0.0
    return _t == "100%" or (_t == "%" and _v >= 100)


async def evenement_du_code(db, code_doc):
    """L'id de l'offre-événement à laquelle CE code est réservé, sinon None.
    Une seule requête, et seulement si le code a des articles. Panne de lecture -> None
    (journalisée) : les autres portes gardent alors leur comportement d'avant."""
    _cs = [str(x) for x in ((code_doc or {}).get("courses") or []) if x]
    if not _cs:
        return None
    try:
        _cands = await db.offers.find(
            {"offer_type": "event", "evenement_reservation_auto": True,
             "$or": [{"id": {"$in": _cs}}, {"linked_course_ids": {"$in": _cs}}]},
            {"_id": 0, "id": 1, "linked_course_ids": 1}).to_list(20)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s code d'événement illisible (%s)", PREFIXE, type(_err).__name__)
        return None
    for _o in _cands:
        if code_reserve_a(code_doc, ids_evenement(_o)):
            return _o.get("id")
    return None


async def evenement_du_code_saisi(db, code):
    """Même question pour un code SAISI (chaîne) : lit ses fiches (insensible à la casse)."""
    _c = str(code or "").strip()
    if not _c:
        return None
    try:
        _fiches = await db.discount_codes.find(
            {"code": {"$regex": "^%s$" % re.escape(_c), "$options": "i"}},
            {"_id": 0, "courses": 1}).to_list(20)
    except Exception as _err:  # noqa: BLE001
        logger.warning("%s code saisi illisible (%s)", PREFIXE, type(_err).__name__)
        return None
    for _f in _fiches:
        _e = await evenement_du_code(db, _f)
        if _e:
            return _e
    return None


async def fiche_code_evenement(db, saisie, offre):
    """(fiche, motif) — LA fiche `discount_codes` du code saisi pour CET événement.
    Recherche exacte (casse ignorée) ; à défaut, parmi les seuls codes de l'événement,
    une comparaison sans accents (« HETAIRA » = « HÉTAÏRA »). Jamais une regex construite
    sur la saisie. Plusieurs fiches vivantes et aucune canonique -> refus (« ambigu »)."""
    _s = str(saisie or "").strip()
    if not _s or len(_s) > 64:
        return None, "inconnu"
    _proj = {"_id": 0}
    _fiches = await db.discount_codes.find(
        {"code": {"$regex": "^%s$" % re.escape(_s), "$options": "i"}}, _proj).to_list(20)
    if not _fiches:
        _ids = list(ids_evenement(offre))
        _cible = _sans_accents(_s)
        _fiches = [f for f in await db.discount_codes.find({"courses": {"$in": _ids}}, _proj).to_list(200)
                   if _sans_accents(f.get("code")) == _cible]
    if not _fiches:
        return None, "inconnu"
    from api.routes.shared import seances_fiche_cible
    _id, _voie = seances_fiche_cible(_fiches)
    if not _id:
        return None, ("expire" if _voie == "code_mort" else _voie)
    return next((f for f in _fiches if f.get("id") == _id), None), "ok"


def proprietaire_evenement(offre, cours=None) -> str:
    """Le coach de l'événement (offre, sinon cours) ; vide = plateforme (le super-admin)."""
    return str((offre or {}).get("coach_id") or (cours or {}).get("coach_id") or "").strip().lower()


def code_du_proprietaire(fiche, offre, cours=None) -> bool:
    """V628 — un code ne vaut que pour un événement de SON coach. Événement de la plateforme
    (aucun coach) : seuls les codes du super-admin, ou sans coach (anciens), y donnent accès.
    Sans cette règle, un partenaire pourrait créer un code visant l'événement d'un autre."""
    from api.routes.shared import is_super_admin, DEFAULT_COACH_ID
    _code_coach = str((fiche or {}).get("coach_id") or "").strip().lower()
    _proprio = proprietaire_evenement(offre, cours)
    if _proprio and not is_super_admin(_proprio) and _proprio != str(DEFAULT_COACH_ID).lower():
        return _code_coach == _proprio
    return (not _code_coach) or is_super_admin(_code_coach) or _code_coach in ("bassi_default", str(DEFAULT_COACH_ID).lower())


def verifier_code_evenement(fiche, offre, jour=None, cours=None):
    """None si le code donne une place GRATUITE à cet événement, sinon le message de refus.
    `jour` : jour calendaire suisse (AAAA-MM-JJ) ; l'expiration court jusqu'au soir inclus."""
    _f = fiche or {}
    if not _f or _f.get("active") is not True:
        return MSG_CODE_INVALIDE
    from api.routes.shared import v617_jour_local
    _jour = jour or v617_jour_local()
    _exp = str(_f.get("expiresAt") or "")[:10]
    if _exp and _exp < _jour:
        return MSG_CODE_INVALIDE
    if not code_gratuit_total(_f):
        return MSG_CODE_INVALIDE
    if not code_reserve_a(_f, ids_evenement(offre)) or not code_du_proprietaire(_f, offre, cours):
        # Même message qu'un code inconnu : la route publique ne confirme pas l'existence
        # d'un code (AFR-, code d'un autre cours) qui ne la concerne pas.
        return MSG_CODE_INVALIDE
    try:
        _max, _used = int(float(_f.get("maxUses") or 0)), int(float(_f.get("used") or 0))
    except (TypeError, ValueError):
        return MSG_CODE_INVALIDE
    if _max <= 0 or _used >= _max:
        return MSG_CODE_UTILISE   # la route le transforme en refus neutre (sauf pour sa titulaire)
    return None


def diagnostic_code(fiche, offre, cours=None, jour=None) -> dict:
    """V628 — pour le COACH : ce code donnerait-il une place à cet événement, et sinon pourquoi.
    Lecture pure, aucune écriture ; jamais l'adresse attribuée (seulement « attribué : oui/non »)."""
    _f = fiche or {}
    from api.routes.shared import v617_jour_local
    _jour = jour or v617_jour_local()
    _motifs = []
    if _f.get("active") is not True:
        _motifs.append("inactif")
    _exp = str(_f.get("expiresAt") or "")[:10]
    if _exp and _exp < _jour:
        _motifs.append("expiré")
    if not code_gratuit_total(_f):
        _motifs.append("réduction inférieure à 100 %")
    if not code_reserve_a(_f, ids_evenement(offre)):
        _motifs.append("articles autorisés : pas uniquement cet événement")
    if not code_du_proprietaire(_f, offre, cours):
        _motifs.append("code d'un autre coach")
    try:
        _max, _used = int(float(_f.get("maxUses") or 0)), int(float(_f.get("used") or 0))
    except (TypeError, ValueError):
        _max, _used = 0, 0
    if _max <= 0 or _used >= _max:
        _motifs.append("déjà utilisé")
    return {"code": _f.get("code"), "utilisable": not _motifs, "motifs": _motifs,
            "utilisations": _used, "maximum": _max, "expiration": _exp or None,
            "nb_articles": len(_f.get("courses") or []), "adresse_attribuee": bool(_f.get("assignedEmail"))}

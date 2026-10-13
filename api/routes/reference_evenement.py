"""V618L — LA DATE DES PALIERS D'UN ÉVÉNEMENT = LA DATE DE L'ÉVÉNEMENT.

Incident (13/10/2026) : « AFROBOOST SILENT — ÉDITION SPÉCIALE » a lieu le mercredi 28 octobre
(son cours dédié le dit, la page le dit), mais la « date de référence » des paliers, saisie à la
main dans l'éditeur d'offre, valait le 28 NOVEMBRE. Le moteur de prix (api/pricing.py) ne lit que
cette date-là : la page annonçait « 30 CHF dès le samedi 21 novembre » et la prévente aurait duré
un mois de trop. Deux vérités pour une seule date.

Règle : pour une offre ÉVÉNEMENT liée à UN seul cours daté, la date de référence est TOUJOURS
celle de ce cours (heure de Zurich). Elle est recopiée par le serveur à chaque sauvegarde de
l'offre et à chaque changement de date du cours — le navigateur n'a plus voix au chapitre.
Événement sans cours daté, ou lié à plusieurs cours : rien ne change (la saisie du coach reste).
"""
import logging
import re

logger = logging.getLogger(__name__)

RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_HEURE = re.compile(r"^\d{2}:\d{2}$")


def reference_du_cours(offre, cours):
    """(date, heure) du cours dédié de l'offre événement, sinon None. PURE."""
    _o = offre or {}
    if _o.get("offer_type") != "event":
        return None
    _ids = [i for i in (_o.get("linked_course_ids") or []) if i]
    if len(_ids) != 1 or not cours or cours.get("id") != _ids[0]:
        return None
    _d = str(cours.get("date") or "").strip()[:10]
    _h = str(cours.get("time") or "").strip()[:5]
    if not RE_DATE.match(_d) or not RE_HEURE.match(_h):
        return None
    return _d, _h


async def champs_alignes(db, offre):
    """Les champs à poser sur l'offre pour que ses paliers suivent l'événement ({} sinon)."""
    _ids = [i for i in ((offre or {}).get("linked_course_ids") or []) if i]
    if (offre or {}).get("offer_type") != "event" or len(_ids) != 1:
        return {}
    _c = await db.courses.find_one({"id": _ids[0]}, {"_id": 0, "id": 1, "date": 1, "time": 1})
    _ref = reference_du_cours(offre, _c)
    if not _ref:
        return {}
    if (str(offre.get("countdown_date") or "")[:10], str(offre.get("countdown_time") or "")[:5]) != _ref:
        logger.info("[V618L] date de référence de l'offre %s alignée sur son événement : %s %s -> %s %s",
                    offre.get("id"), offre.get("countdown_date"), offre.get("countdown_time"), _ref[0], _ref[1])
    return {"countdown_date": _ref[0], "countdown_time": _ref[1]}


async def suivre_le_cours(db, cours):
    """Le cours dédié a changé de date : ses offres événement suivent. Renvoie le nombre d'offres."""
    if not cours or not cours.get("id"):
        return 0
    _n = 0
    async for _o in db.offers.find({"offer_type": "event", "linked_course_ids": cours["id"]},
                                   {"_id": 0, "id": 1, "offer_type": 1, "linked_course_ids": 1,
                                    "countdown_date": 1, "countdown_time": 1}):
        _ref = reference_du_cours(_o, cours)
        if not _ref or (str(_o.get("countdown_date") or "")[:10], str(_o.get("countdown_time") or "")[:5]) == _ref:
            continue
        await db.offers.update_one({"id": _o["id"]}, {"$set": {"countdown_date": _ref[0], "countdown_time": _ref[1]}})
        logger.info("[V618L] offre %s : date de référence suivie sur le cours %s -> %s %s", _o["id"], cours["id"], *_ref)
        _n += 1
    return _n

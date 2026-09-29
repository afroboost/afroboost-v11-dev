"""
MT-0 — PORTEFEUILLE DE CONTACTS D'UN COACH (multi-coach, 29/09/2026).

Une seule réponse, pour tout le serveur, à la question « ce contact appartient-il
au coach X ? ». Les routes Contacts ET le moteur de campagnes (destinataires
« tous », `targetIds`, segments, groupes) s'appuient sur ces fonctions : deux
règles différentes finiraient par diverger.

RÈGLE :
- super-admin (identité issue d'un JWT SIGNÉ, jamais d'un en-tête) -> portée globale ;
- coach -> uniquement ce qu'une relation SERVEUR rattache à lui :
  * `chat_participants` dont `coach_id` == son e-mail ;
  * `users` globaux SEULEMENT si une relation est prouvée (voir `emails_relies`) ;
  * `chat_sessions` / groupes dont `coach_id` == son e-mail.
- aucune identité -> refus (jamais un dictionnaire « vide = tout »).

FAIL-CLOSED : un document sans propriétaire n'appartient à aucun coach ordinaire ;
seul le super-admin le voit. On n'invente de propriétaire à personne.

Aucune dépendance FastAPI : testable hors ligne. Les routes convertissent
`PerimetreRefuse` en 403.
"""
from typing import Optional

from api.routes.shared import is_super_admin


class PerimetreRefuse(Exception):
    """Aucune identité exploitable : l'appelant doit répondre 403."""


def normaliser_email(e) -> str:
    return (e or "").strip().lower() if isinstance(e, str) else ""


def est_global(coach_email: str) -> bool:
    """Portée plateforme : réservée aux super-admins (identité déjà prouvée par JWT)."""
    _e = normaliser_email(coach_email)
    if not _e:
        raise PerimetreRefuse("identité requise")
    return is_super_admin(_e)


def filtre_proprietaire(coach_email: str) -> dict:
    """`{}` pour un super-admin, `{"coach_id": email}` pour un coach ; lève sinon."""
    _e = normaliser_email(coach_email)
    if est_global(_e):
        return {}
    return {"coach_id": _e}


async def emails_relies(db, coach_email: str) -> set:
    """E-mails (normalisés) que le SERVEUR rattache au coach — preuve de relation.

    Version MT-0 (prudente) : les e-mails de ses propres `chat_participants`.
    L'agent Contacts étend cette preuve (réservations, abonnements, codes…) —
    il est le SEUL à modifier cette fonction.
    """
    _e = normaliser_email(coach_email)
    if not _e:
        raise PerimetreRefuse("identité requise")
    _out = set()
    async for _p in db.chat_participants.find({"coach_id": _e}, {"_id": 0, "email": 1}):
        _m = normaliser_email(_p.get("email"))
        if _m:
            _out.add(_m)
    return _out


async def contact_appartient(db, coach_email: str, collection: str, doc_id: str) -> bool:
    """Le document `doc_id` de `collection` fait-il partie du portefeuille du coach ?

    Super-admin : vrai si le document existe. Coach : relation serveur exigée.
    Collections gérées : chat_participants, users, chat_sessions.
    """
    if not isinstance(doc_id, str) or not doc_id or "$" in doc_id or len(doc_id) > 128:
        return False
    _e = normaliser_email(coach_email)
    _global = est_global(_e)
    if collection in ("chat_participants", "chat_sessions"):
        _f = {"id": doc_id}
        if not _global:
            _f["coach_id"] = _e
        return bool(await db[collection].find_one(_f, {"_id": 1}))
    if collection == "users":
        _u = await db.users.find_one({"id": doc_id}, {"_id": 0, "email": 1, "coach_id": 1})
        if not _u:
            return False
        if _global:
            return True
        if normaliser_email(_u.get("coach_id")) == _e:
            return True
        return normaliser_email(_u.get("email")) in await emails_relies(db, _e)
    return False


async def filtrer_ids(db, coach_email: str, collection: str, ids) -> list:
    """Ne garde que les ids appartenant au coach (ordre conservé, doublons retirés)."""
    _vus, _out = set(), []
    for _i in ids or []:
        if isinstance(_i, str) and _i not in _vus:
            _vus.add(_i)
            if await contact_appartient(db, coach_email, collection, _i):
                _out.append(_i)
    return _out


async def filtre_users_du_coach(db, coach_email: str) -> Optional[dict]:
    """Filtre Mongo des `users` visibles par le coach : `{}` (super-admin) ou
    `{"$or": [coach_id == e-mail, email ∈ relation prouvée]}`."""
    _e = normaliser_email(coach_email)
    if est_global(_e):
        return {}
    _emails = sorted(await emails_relies(db, _e))
    return {"$or": [{"coach_id": _e}, {"email": {"$in": _emails}}]}

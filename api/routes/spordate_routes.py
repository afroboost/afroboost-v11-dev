"""
Pont « une seule clé » : afroboost (MongoDB) -> Spordate (Firebase). V387

Un membre connecté sur afroboost.com clique « Spordateur » et arrive dans
Rencontre DÉJÀ connecté, sans second mot de passe.

MÊME PRINCIPE QUE LE PONT DU LIVE, mais vers Firebase au lieu de Supabase :
afroboost émet un jeton HS256 court portant l'e-mail ; Spordate le vérifie,
retrouve (ou crée) le compte Firebase de cet e-mail via l'API admin, et émet un
`customToken` que son client échange contre une session. L'e-mail est la clé
d'identité des deux côtés — c'est déjà ainsi qu'afroboost reconnaît son admin.

SECRET DÉDIÉ. `AFRO_SPORDATE_SHARED_SECRET` est un secret NEUF, distinct de
`AFRO_BT_SHARED_SECRET` : ce dernier a fuité dans l'historique git (commit
86cd8ed) et sert encore au live. Les réutiliser propagerait la fuite.

CE QUE LE JETON NE PORTE PAS : ni le code d'abonné (secret long terme, il
resterait lisible dans l'URL et dans l'historique du navigateur), ni de rôle.
Seulement l'e-mail, un identifiant unique et une expiration courte.
"""
import os
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/spordate", tags=["spordate"])

db = None

# 15 minutes : le temps d'un aller-retour de navigation, pas davantage. Le jeton
# transite par l'URL, donc il finit dans l'historique du navigateur ; sa valeur
# doit être périmée avant que ça n'ait la moindre importance.
DUREE_JETON_S = 15 * 60

CHEMIN_RENCONTRE = "/rencontre"


def init_db(database):
    global db
    db = database


@router.get("/available")
async def spordate_available():
    """Dit au frontend si le pont est utilisable. Ne divulgue aucun secret."""
    return {"enabled": bool(os.environ.get("AFRO_SPORDATE_SHARED_SECRET"))}


@router.post("/access")
async def spordate_access(request: Request):
    """
    Émet un jeton de passage vers Spordate pour un membre RECONNU.

    Deux chemins d'identité, les mêmes que partout ailleurs sur afroboost :
      - un coach/admin authentifié (JWT, ou repli X-User-Email du dashboard) ;
      - un abonné qui présente son code, lu dans le CORPS et jamais en query
        string — pour qu'il n'atterrisse ni dans les journaux d'accès, ni dans
        l'en-tête Referer.

    Aucun crédit n'est débité : Rencontre n'est pas une prestation payante.
    """
    secret = os.environ.get("AFRO_SPORDATE_SHARED_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Le pont Spordateur n'est pas configuré.")

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        corps = {}

    # Import TARDIF : `api.server` importe ce module, un import en tête de
    # fichier créerait un cycle. Même motif que payment_activation/boost_routes.
    from api.server import _v263_authenticated_coach, _bt_subscriber_credit

    email = ""
    origine = ""

    appelant = await _v263_authenticated_coach(request)
    if appelant:
        email, origine = appelant.strip().lower(), "compte"

    if not email:
        # Jeton d'appareil abonné (V296) : c'est le porteur normal de l'identité
        # d'un abonné connecté, dérivé de son code. Chemin privilégié — il évite
        # de faire circuler le code lui-même.
        try:
            from api.routes.shared import subscriber_from_request
            abonne = subscriber_from_request(request)
        except Exception:
            abonne = None
        if abonne and abonne.get("email"):
            email, origine = abonne["email"].strip().lower(), "jeton_abonne"

    if not email:
        code = (corps.get("subscriber_code") or "").strip().upper()
        if code:
            info = await _bt_subscriber_credit(code)
            if info and info.get("email"):
                email, origine = info["email"].strip().lower(), "code"

    if not email:
        # 403 explicite plutôt que muet : le frontend doit pouvoir proposer le
        # login normal de Spordate au lieu de laisser un bouton mort.
        return JSONResponse(status_code=403, content={"reason": "identity_required"})

    jti = str(uuid.uuid4())
    maintenant = datetime.now(timezone.utc)
    emis = int(maintenant.timestamp())

    import jwt as _pyjwt
    jeton = _pyjwt.encode(
        {
            "email": email,
            "jti": jti,
            "aud": "spordate",
            "iss": "afroboost",
            "iat": emis,
            "exp": emis + DUREE_JETON_S,
        },
        secret,
        algorithm="HS256",
    )

    # Trace côté afroboost — utile pour comprendre après coup qui est passé.
    # L'anti-rejeu, lui, est tenu par Spordate : c'est LUI qui consomme le jeton,
    # et une garde posée ici ne saurait pas si l'échange a réellement abouti.
    if db is not None:
        try:
            await db.spordate_bridge_usage.insert_one({
                "_id": jti,
                "email": email,
                "origine": origine,
                "created_at": maintenant.isoformat(),
                "created_dt": maintenant,   # vrai Date BSON -> index TTL possible
            })
        except Exception as e:
            logger.warning(f"[SPORDATE] Trace non écrite ({jti}): {e}")

    logger.info(f"[SPORDATE] Jeton émis pour {email} (via {origine})")
    return {
        "url": f"{CHEMIN_RENCONTRE}?t={jeton}",
        "expires_in": DUREE_JETON_S,
    }

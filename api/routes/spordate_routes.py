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
import time
import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

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

    jeton = await _emettre_jeton_passage(email, origine, secret)
    return {
        "url": f"{CHEMIN_RENCONTRE}?t={jeton}",
        "expires_in": DUREE_JETON_S,
    }


# ============================================================================
# F3 FINAL — HANDOFF SERVEUR DIRECT (302), POUR LES SESSIONS À COOKIE
# ============================================================================
# `/access` (POST) émet un jeton à partir d'une identité portée dans un EN-TÊTE
# (JWT / X-User-Email / jeton d'appareil abonné). Une navigation navigateur de
# premier niveau (GET) n'emporte AUCUN en-tête — seulement les cookies. Donc un
# 302 serveur pur n'est possible QUE pour les porteurs du cookie de session
# coach `coach_session_token` (login Google / mot de passe).
#
# Pour EUX, `/enter` supprime tout aller-retour côté client : clic -> GET ->
# 302 vers /rencontre?t=…&next=… -> BridgeAutoLogin -> destination. Zéro fetch
# frontend, zéro attente, zéro écran intermédiaire.
#
# Pour les ABONNÉS (identité en en-tête, pas de cookie), ce chemin ne peut pas
# authentifier : le frontend les fait entrer avec un jeton PRÉ-OBTENU au montage
# (voir utils/spordateHandoff). `/enter` reste pour eux une porte de repli sûre
# qui, faute d'identité, renvoie vers /rencontre (login normal Spordate) — JAMAIS
# une redirection externe.

def _next_interne_sur(brut) -> str:
    """Réplique serveur de `cheminNextSur` : n'accepte qu'un chemin interne. Rend
    '' pour tout ce qui pourrait ouvrir une redirection externe. La cible du 302
    reste TOUJOURS /rencontre ; `next` n'y voyage qu'en paramètre de requête —
    cette garde est donc de la défense en profondeur, doublée côté Spordate."""
    v = (brut or "").strip()
    if not v:
        return ""
    # doit commencer par un seul '/', jamais '//' ni '/\' (URL protocole-relative)
    if v[0] != "/" or (len(v) > 1 and v[1] in ("/", "\\")):
        return ""
    low = v.lower()
    if "://" in v or "javascript:" in low or "\\" in v:
        return ""
    if any(ord(c) < 0x20 for c in v):
        return ""
    return v


async def _email_depuis_cookie_session(request: Request) -> str:
    """Identité coach TIRÉE DU COOKIE `coach_session_token` — le seul porteur
    d'identité qu'une navigation GET emporte. Exactement la chaîne de `/auth/me` :
    cookie -> coach_sessions (non périmée) -> google_users|users_auth -> email.
    Rend '' sans jamais lever (une porte de handoff ne doit pas tomber en 500)."""
    if db is None:
        return ""
    token = request.cookies.get("coach_session_token")
    if not token:
        return ""
    try:
        session = await db.coach_sessions.find_one({"session_token": token}, {"_id": 0})
        if not session:
            return ""
        expires_at = session.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < datetime.now(timezone.utc):
            return ""
        uid = session.get("user_id")
        user = await db.google_users.find_one({"user_id": uid}, {"_id": 0}) \
            or await db.users_auth.find_one({"user_id": uid}, {"_id": 0})
        if not user:
            return ""
        return (user.get("email") or "").strip().lower()
    except Exception as e:
        logger.warning(f"[SPORDATE] cookie->email a échoué: {e}")
        return ""


async def _emettre_jeton_passage(email: str, origine: str, secret: str) -> str:
    """Frappe le jeton HS256 de passage et écrit la trace. Partagé par /access
    et /enter — un seul endroit qui décide de la forme du jeton."""
    jti = str(uuid.uuid4())
    maintenant = datetime.now(timezone.utc)
    emis = int(maintenant.timestamp())
    import jwt as _pyjwt
    jeton = _pyjwt.encode(
        {"email": email, "jti": jti, "aud": "spordate", "iss": "afroboost",
         "iat": emis, "exp": emis + DUREE_JETON_S},
        secret, algorithm="HS256",
    )
    if db is not None:
        try:
            await db.spordate_bridge_usage.insert_one({
                "_id": jti, "email": email, "origine": origine,
                "created_at": maintenant.isoformat(), "created_dt": maintenant,
            })
        except Exception as e:
            logger.warning(f"[SPORDATE] Trace non écrite ({jti}): {e}")
    logger.info(f"[SPORDATE] Jeton émis pour {email} (via {origine})")
    return jeton


@router.get("/enter")
async def spordate_enter(request: Request):
    """Handoff serveur : clic/tap -> 302 vers Rencontre, déjà connecté, sans
    aucun aller-retour côté client. N'authentifie QUE par le cookie de session
    (voir l'encadré ci-dessus). Sans identité, renvoie proprement vers Rencontre
    (login normal) — la cible du 302 est TOUJOURS interne."""
    next_interne = _next_interne_sur(request.query_params.get("next"))
    secret = os.environ.get("AFRO_SPORDATE_SHARED_SECRET", "")

    email = await _email_depuis_cookie_session(request)
    if email and secret:
        jeton = await _emettre_jeton_passage(email, "cookie_302", secret)
        cible = f"{CHEMIN_RENCONTRE}?t={jeton}"
        if next_interne:
            cible += f"&next={next_interne}"
    else:
        # Pas de cookie exploitable (abonné, visiteur, ou pont non configuré) :
        # on n'invente aucune session. On renvoie vers Rencontre, en gardant
        # `next` pour que l'intention survive à un login manuel éventuel.
        cible = CHEMIN_RENCONTRE + (f"?next={next_interne}" if next_interne else "")

    # 303 : la réponse à un GET de navigation est une AUTRE ressource à charger
    # en GET. Cache interdit — le jeton est à usage unique.
    reponse = RedirectResponse(url=cible, status_code=303)
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


# ============================================================================
# F2 — LE PROFIL SOCIAL PARTAGÉ, LU EN RETOUR (READ-ONLY)
# ============================================================================
# Le pont ci-dessus fait ENTRER un membre afroboost dans Spordateur. Ce lot
# fait le chemin INVERSE : afroboost affiche, dans son propre espace profil, le
# profil social que la personne tient sur Spordateur — sans jamais le recopier.
#
# ─────────────────────────────────────────────────────────────────────────
# LE POINT DE SÉCURITÉ QUI COMMANDE TOUT (GO §3)
# ─────────────────────────────────────────────────────────────────────────
# afroboost identifie ses appelants par JWT signé (fiable) OU, en repli
# transitoire V265, par l'en-tête `X-User-Email` — que N'IMPORTE QUI peut
# écrire. Le pont d'accès tolère ce repli parce qu'il ne fait qu'ouvrir une
# session que l'utilisateur pouvait déjà ouvrir. ICI, c'est INTERDIT : accepter
# `X-User-Email` laisserait un `curl` lire le profil de n'importe qui en
# changeant une chaîne. Cette route n'accepte donc QUE deux identités SIGNÉES :
#   - le JWT coach/admin (`_v311_coach_email_from_jwt`, rejette même les jetons
#     abonné) ;
#   - le jeton d'appareil abonné (`subscriber_from_request`, signé HS256).
# Aucun repli `X-User-Email`. Pas d'identité signée -> 401, point final.
#
# ─────────────────────────────────────────────────────────────────────────
# CE QU'AFROBOOST N'A PAS, ET NE DOIT PAS AVOIR
# ─────────────────────────────────────────────────────────────────────────
# afroboost n'a aucun accès Firebase à Spordateur, et n'en aura pas : le profil
# et le bridge vivent chez Spordateur, seul détenteur légitime. afroboost se
# contente d'émettre un jeton signé prouvant « voici QUI j'ai authentifié »,
# puis appelle Spordateur, qui fait le reste (bridge -> uid -> profil ->
# liste blanche). afroboost RELAIE le résultat, il ne le fabrique pas.

# Audience DÉDIÉE, distincte de "spordate" (le pont d'accès) : un jeton de
# lecture de profil ne doit jamais pouvoir ouvrir une session, ni l'inverse.
AUDIENCE_PROFIL = "spordate-profile"
DUREE_JETON_PROFIL_S = 60  # une lecture est immédiate ; 60 s suffisent largement


def _f2_base_spordate() -> str:
    """L'URL de base de Spordateur, servie sous afroboost.com/rencontre.

    Configurable par `SPORDATE_INTERNAL_URL` (permet de viser le conteneur en
    interne si un réseau Docker partagé existe un jour) ; à défaut, le domaine
    public — qui fonctionne sans configuration supplémentaire.
    """
    return (os.environ.get("SPORDATE_INTERNAL_URL", "").strip()
            or "https://afroboost.com/rencontre")


@router.get("/unified-profile/me")
async def spordate_unified_profile_me(request: Request):
    """Le profil social Spordateur de l'appelant afroboost — LECTURE SEULE.

    Renvoie toujours 200 avec l'un de :
      - {"lie": true,  "profil": {...whitelist...}}
      - {"lie": false, "motif": "non_lie"|"introuvable"|"pont_indisponible"}
    Sauf 401 si l'appelant n'a pas d'identité SIGNÉE, et 503 si le secret du
    pont n'est pas configuré. Aucune écriture, ici comme chez Spordateur.
    """
    secret = os.environ.get("AFRO_SPORDATE_SHARED_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Le pont Spordateur n'est pas configuré.")

    # Import TARDIF : api.server importe ce module ; un import en tête créerait un
    # cycle. Même motif que le pont d'accès ci-dessus.
    from api.server import _v311_coach_email_from_jwt

    # ── IDENTITÉ SIGNÉE UNIQUEMENT — JAMAIS X-User-Email (GO §3, §4) ──────────
    email = _v311_coach_email_from_jwt(request)  # JWT coach/admin signé
    if not email:
        try:
            from api.routes.shared import subscriber_from_request
            abonne = subscriber_from_request(request)  # jeton abonné signé HS256
        except Exception:
            abonne = None
        if abonne and abonne.get("email"):
            email = str(abonne["email"]).strip().lower()
    if not email:
        # Ni JWT coach ni jeton abonné : on ne lit RIEN. Le repli falsifiable
        # n'existe pas ici.
        raise HTTPException(status_code=401, detail="Identité signée requise")

    # ── LE JETON DE LECTURE, signé, à audience dédiée et à vie courte ─────────
    import jwt as _pyjwt
    emis = int(datetime.now(timezone.utc).timestamp())
    jeton = _pyjwt.encode(
        {"email": email, "aud": AUDIENCE_PROFIL, "iss": "afroboost",
         "iat": emis, "exp": emis + DUREE_JETON_PROFIL_S},
        secret, algorithm="HS256",
    )
    if isinstance(jeton, bytes):
        jeton = jeton.decode("utf-8")

    # ── APPEL À SPORDATEUR, qui détient bridge + profil + liste blanche ───────
    import httpx
    url = f"{_f2_base_spordate()}/api/bridge/unified-profile"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.post(url, json={"t": jeton})
    except Exception as e:  # réseau : on ne casse pas l'espace profil afroboost
        logger.warning(f"[F2] pont profil injoignable: {e}")
        return {"lie": False, "motif": "pont_indisponible"}

    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return {"lie": False, "motif": "pont_indisponible"}
    if r.status_code == 401:
        # Spordateur a refusé le jeton : on ne réémet pas, on ferme.
        raise HTTPException(status_code=401, detail="Jeton de profil refusé")
    # 503/erreurs Spordateur : dégradation douce, jamais une page cassée.
    logger.warning(f"[F2] pont profil statut {r.status_code}")
    return {"lie": False, "motif": "pont_indisponible"}


@router.patch("/unified-profile/me")
async def spordate_unified_profile_patch(request: Request):
    """F3 — MODIFIER son profil social Spordateur DEPUIS afroboost (champs texte).

    Même contrat de sécurité que la lecture : identité SIGNÉE uniquement (JWT
    coach ou jeton abonné), JAMAIS X-User-Email. On émet un jeton signé à
    audience dédiée, on transmet le corps modifiable, et Spordateur — qui
    détient bridge + profil — résout le uid, applique SA liste blanche
    d'écriture (bio/city/sports), écrit `users/{uid}` et renvoie le DTO social.

    afroboost ne décide NI du uid (résolu chez Spordateur via le bridge), NI de
    ce qui est écrit (filtré chez Spordateur). Il relaie une intention signée.
    """
    secret = os.environ.get("AFRO_SPORDATE_SHARED_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="Le pont Spordateur n'est pas configuré.")

    from api.server import _v311_coach_email_from_jwt
    email = _v311_coach_email_from_jwt(request)
    if not email:
        try:
            from api.routes.shared import subscriber_from_request
            abonne = subscriber_from_request(request)
        except Exception:
            abonne = None
        if abonne and abonne.get("email"):
            email = str(abonne["email"]).strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Identité signée requise")

    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        corps = {}
    # On ne transmet QUE le sous-objet `profil` : Spordateur re-filtrera de
    # toute façon, mais on ne fait pas voyager plus que nécessaire.
    profil = corps.get("profil")
    if not isinstance(profil, dict):
        profil = {}

    import jwt as _pyjwt
    emis = int(datetime.now(timezone.utc).timestamp())
    jeton = _pyjwt.encode(
        {"email": email, "aud": AUDIENCE_PROFIL, "iss": "afroboost",
         "iat": emis, "exp": emis + DUREE_JETON_PROFIL_S},
        secret, algorithm="HS256",
    )
    if isinstance(jeton, bytes):
        jeton = jeton.decode("utf-8")

    import httpx
    url = f"{_f2_base_spordate()}/api/bridge/unified-profile"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.patch(url, json={"t": jeton, "profil": profil})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[F3] pont profil (écriture) injoignable: {e}")
        return {"lie": False, "motif": "pont_indisponible"}

    if r.status_code == 200:
        try:
            return r.json()
        except Exception:
            return {"lie": False, "motif": "pont_indisponible"}
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="Jeton de profil refusé")
    logger.warning(f"[F3] pont profil (écriture) statut {r.status_code}")
    return {"lie": False, "motif": "pont_indisponible"}


# ============================================================================
# F3 FINAL (2/2) — PROFIL SOCIAL DES AUTRES COMPTES LIÉS (RÉSOLUTION SERVEUR)
# ============================================================================
# afroboost, pour un utilisateur qu'il AFFICHE DÉJÀ (mini-profil, publication…),
# veut : (a) savoir s'il est lié à Spordateur, (b) pouvoir ouvrir son profil.
#
# LA RÈGLE DE CONFIDENTIALITÉ QUI COMMANDE TOUT (GO §5, §6) :
#   - AUCUNE API d'appartenance par e-mail exposée au navigateur. Le navigateur
#     n'envoie jamais d'e-mail à tester ; il reçoit une annotation sur une donnée
#     qu'il est DÉJÀ autorisé à voir.
#   - La correspondance e-mail → uid est lue SERVEUR À SERVEUR (jeton
#     `spordate-link-resolve`, secret partagé), jamais côté client.
#   - Le navigateur ne reçoit JAMAIS le uid : il reçoit un jeton de VUE OPAQUE
#     (`spordate-profile-view`) qui l'emballe ; seule la garde Spordateur
#     `/u/<jeton>` sait l'ouvrir.
#   - Tout est derrière le drapeau `SOCIAL_PROFILE_LINKS` (défaut OFF) : livré
#     dormant, aucun effet tant qu'il n'est pas activé en base.

AUDIENCE_RESOLUTION = "spordate-link-resolve"
AUDIENCE_VUE_PROFIL = "spordate-profile-view"
DUREE_JETON_RESOLUTION_S = 30          # aller-retour serveur, pas davantage
DUREE_JETON_VUE_S = 5 * 60             # le temps d'un clic vers un profil
_CACHE_LIENS_TTL_S = 120               # un lien change rarement : cache court
_cache_liens = {}                      # email -> (uid|None, ts monotone)


async def _social_links_actif() -> bool:
    """Le drapeau `SOCIAL_PROFILE_LINKS`, lu EN DIRECT (bascule/kill-switch sans
    redéploiement). Une panne de lecture ferme (OFF) — jamais d'annotation par
    accident."""
    try:
        from api.server import get_feature_flags
        return bool((await get_feature_flags()).get("SOCIAL_PROFILE_LINKS"))
    except Exception:
        return False


def _signer(charge: dict, secret: str, duree_s: int) -> str:
    import jwt as _pyjwt
    emis = int(datetime.now(timezone.utc).timestamp())
    charge = dict(charge)
    charge.update({"iss": "afroboost", "iat": emis, "exp": emis + duree_s})
    j = _pyjwt.encode(charge, secret, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


async def _resoudre_liens_sociaux(emails) -> dict:
    """SERVEUR À SERVEUR : {email(min) -> uid|None}. Cache court, échec fermé
    (une base injoignable = « non lié » pour cette fois, jamais une supposition
    positive). Ne part JAMAIS d'une saisie libre du navigateur — l'appelant lui
    fournit des e-mails d'utilisateurs déjà affichés."""
    secret = os.environ.get("AFRO_SPORDATE_SHARED_SECRET", "")
    if not secret or not emails:
        return {}
    maintenant = time.monotonic()
    resu, besoin = {}, []
    for e in emails:
        e = (e or "").strip().lower()
        if not e:
            continue
        c = _cache_liens.get(e)
        if c and (maintenant - c[1]) < _CACHE_LIENS_TTL_S:
            resu[e] = c[0]
        elif e not in besoin:
            besoin.append(e)
    if besoin:
        import httpx
        jeton = _signer({"aud": AUDIENCE_RESOLUTION}, secret, DUREE_JETON_RESOLUTION_S)
        url = f"{_f2_base_spordate()}/api/bridge/resolve-links"
        rs = {}
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.post(url, json={"t": jeton, "emails": besoin})
            if r.status_code == 200:
                rs = (r.json() or {}).get("resultats", {}) or {}
        except Exception as ex:  # noqa: BLE001
            logger.warning(f"[SOCIAL] resolve-links injoignable: {ex}")
        for e in besoin:
            info = rs.get(e) or {}
            uid = (info.get("uid") or "").strip() if info.get("lie") else None
            uid = uid or None
            resu[e] = uid
            _cache_liens[e] = (uid, maintenant)
    return resu


async def annoter_social_profile(email) -> dict:
    """Annotation pour UN e-mail déjà affiché : {"available": bool,
    "target": <jeton de vue opaque>?}. Le navigateur ne reçoit JAMAIS le uid.
    Renvoie None si le drapeau est OFF, le pont non configuré, ou l'e-mail vide —
    l'appelant n'ajoute alors rien à sa réponse."""
    email = (email or "").strip().lower()
    if not email:
        return None
    if not await _social_links_actif():
        return None
    secret = os.environ.get("AFRO_SPORDATE_SHARED_SECRET", "")
    if not secret:
        return None
    liens = await _resoudre_liens_sociaux([email])
    uid = liens.get(email)
    if not uid:
        return {"available": False}
    return {"available": True, "target": _signer({"aud": AUDIENCE_VUE_PROFIL, "uid": uid},
                                                 secret, DUREE_JETON_VUE_S)}

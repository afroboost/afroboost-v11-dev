#!/usr/bin/env python3
"""
F2 — LE RELAIS AFROBOOST DU PROFIL UNIFIÉ : IDENTITÉ SIGNÉE, OU RIEN.

Exécution :
  python3 tests/test_f2_profil_unifie.py

CE QUE CE BANC PROUVE
La route `/api/spordate/unified-profile/me` ne lit un profil QUE si l'appelant
est authentifié par un mécanisme SIGNÉ (JWT coach ou jeton abonné). Le repli
`X-User-Email`, falsifiable, ne donne JAMAIS accès. Et l'appel réseau vers
Spordateur porte un jeton signé à audience dédiée, jamais l'e-mail en clair.

AUCUN réseau réel : httpx est remplacé par un faux qui capture la requête. La
socket est interdite pour que rien ne parte par accident.
"""
import asyncio
import io
import os
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

os.environ.setdefault("MONGO_URL", "mongodb://bouchon-f2-inexistant:27017")
os.environ["JWT_SECRET"] = "secret-jwt-de-test-f2"
os.environ["AFRO_SPORDATE_SHARED_SECRET"] = "secret-pont-de-test-f2"

# — INTERDICTION DE CONNEXION SORTANTE : une vraie connexion réseau fait
#   ÉCHOUER le banc. On n'interdit PAS la création de socket (l'event loop
#   asyncio en a besoin en interne) — seulement `connect`, la sortie réelle. —
class SortieReseauInterdite(RuntimeError):
    pass
_vrai_connect = socket.socket.connect
def _connect_interdit(self, *a, **k):
    raise SortieReseauInterdite("connexion réseau réelle interdite dans le banc")
socket.socket.connect = _connect_interdit

import jwt as _pyjwt  # noqa: E402
import api.server as S  # noqa: E402
import api.routes.spordate_routes as SP  # noqa: E402

_p = 0
_f = 0
def verifier(libelle, cond, detail=""):
    global _p, _f
    if cond:
        print("PASS  " + libelle); _p += 1
    else:
        print("FAIL  " + libelle + ("  — " + detail if detail else "")); _f += 1

def lancer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class RequeteFictive:
    """Une requête minimale : on choisit ses en-têtes, rien d'autre."""
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.query_params = {}
        self.client = type("C", (), {"host": "127.0.0.1"})()
        self.url = type("U", (), {"path": "/api/spordate/unified-profile/me"})()
        self.method = "GET"


# — FAUX httpx : capture le jeton envoyé, renvoie ce qu'on lui dit —
CAPTURE = {"url": None, "corps": None, "appels": 0}
class _ReponseFausse:
    def __init__(self, code, data):
        self.status_code = code
        self._data = data
    def json(self):
        return self._data
class _ClientFaux:
    def __init__(self, reponse):
        self._rep = reponse
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def post(self, url, json=None):
        CAPTURE["url"] = url
        CAPTURE["corps"] = json
        CAPTURE["appels"] += 1
        if isinstance(self._rep, Exception):
            raise self._rep
        return self._rep
class _HttpxFaux:
    def __init__(self, reponse):
        self._rep = reponse
    def AsyncClient(self, *a, **k):
        return _ClientFaux(self._rep)

def _installer_httpx(reponse):
    CAPTURE.update({"url": None, "corps": None, "appels": 0})
    sys.modules["httpx"] = _HttpxFaux(reponse)

def jwt_coach(email):
    return _pyjwt.encode({"email": email, "role": "user"}, os.environ["JWT_SECRET"], algorithm="HS256")

def jwt_abonne(code, email):
    from api.routes.shared import make_subscriber_token
    return make_subscriber_token(code, email)


# ─────────────────────────────────────────────────────────────────────────
print("\n--- A : IDENTITÉ SIGNÉE ACCEPTÉE, PROFIL RELAYÉ (A du GO) ---")
_installer_httpx(_ReponseFausse(200, {"lie": True, "profil": {"displayName": "BASSI"}}))
_req = RequeteFictive({"Authorization": "Bearer " + jwt_coach("bassi@example.test")})
_res = lancer(SP.spordate_unified_profile_me(_req))
verifier("A1 JWT coach signé -> profil relayé", _res.get("lie") is True and _res["profil"]["displayName"] == "BASSI")
verifier("A2 exactement un appel au pont", CAPTURE["appels"] == 1)
verifier("A3 l'appel vise bien la route de profil Spordateur",
         str(CAPTURE["url"]).endswith("/api/bridge/unified-profile"), str(CAPTURE["url"]))

print("\n--- B : LE JETON ENVOYÉ EST SIGNÉ, À AUDIENCE DÉDIÉE, SANS E-MAIL EN CLAIR ---")
_env = CAPTURE["corps"] or {}
_jeton = _env.get("t", "")
verifier("B1 le corps ne porte QU'un jeton (pas d'e-mail en clair)", list(_env.keys()) == ["t"], str(list(_env.keys())))
_charge = _pyjwt.decode(_jeton, os.environ["AFRO_SPORDATE_SHARED_SECRET"], algorithms=["HS256"], audience="spordate-profile")
verifier("B2 audience dédiée 'spordate-profile'", _charge.get("aud") == "spordate-profile")
verifier("B3 émetteur 'afroboost'", _charge.get("iss") == "afroboost")
verifier("B4 l'e-mail du jeton est celui du JWT vérifié", _charge.get("email") == "bassi@example.test")
verifier("B5 expiration courte (<= 120 s)", 0 < (_charge.get("exp", 0) - _charge.get("iat", 0)) <= 120)
# signature : un secret faux doit faire échouer le décodage
_ok_sig = False
try:
    _pyjwt.decode(_jeton, "mauvais-secret", algorithms=["HS256"], audience="spordate-profile")
except Exception:
    _ok_sig = True
verifier("B6 le jeton est bien signé (secret faux -> échec)", _ok_sig)

print("\n--- C : ABONNÉ SIGNÉ ACCEPTÉ AUSSI ---")
_installer_httpx(_ReponseFausse(200, {"lie": False, "motif": "non_lie"}))
_tok = jwt_abonne("AFR-TEST01", "abonne@example.test")
_req = RequeteFictive({"X-Subscriber-Token": _tok})
_res = lancer(SP.spordate_unified_profile_me(_req))
verifier("C1 jeton abonné signé -> route ouverte", CAPTURE["appels"] == 1 and _res.get("lie") is False)
_charge2 = _pyjwt.decode(CAPTURE["corps"]["t"], os.environ["AFRO_SPORDATE_SHARED_SECRET"], algorithms=["HS256"], audience="spordate-profile")
verifier("C2 l'e-mail relayé est celui de l'abonné", _charge2.get("email") == "abonne@example.test")

print("\n--- D : X-User-Email FALSIFIÉ NE DONNE JAMAIS ACCÈS (D, M du GO) ---")
from fastapi import HTTPException  # noqa: E402
_installer_httpx(_ReponseFausse(200, {"lie": True, "profil": {"displayName": "VICTIME"}}))
_req = RequeteFictive({"X-User-Email": "victime@example.test"})
_bloque = False
try:
    lancer(SP.spordate_unified_profile_me(_req))
except HTTPException as e:
    _bloque = (e.status_code == 401)
verifier("D1 X-User-Email seul -> 401", _bloque)
verifier("D2 AUCUN appel au pont n'a été fait", CAPTURE["appels"] == 0)

print("\n--- E : AUCUNE IDENTITÉ -> 401 (B du GO) ---")
_installer_httpx(_ReponseFausse(200, {"lie": True}))
_bloque = False
try:
    lancer(SP.spordate_unified_profile_me(RequeteFictive({})))
except HTTPException as e:
    _bloque = (e.status_code == 401)
verifier("E1 aucun en-tête -> 401", _bloque)
verifier("E2 aucun appel réseau", CAPTURE["appels"] == 0)

print("\n--- F : JWT INVALIDE -> 401 (C du GO) ---")
_installer_httpx(_ReponseFausse(200, {"lie": True}))
_bloque = False
try:
    lancer(SP.spordate_unified_profile_me(RequeteFictive({"Authorization": "Bearer pas.un.jwt.valide"})))
except HTTPException as e:
    _bloque = (e.status_code == 401)
verifier("F1 jeton non signé -> 401", _bloque)
verifier("F2 aucun appel réseau", CAPTURE["appels"] == 0)

print("\n--- G : JWT SIGNÉ AVEC UN AUTRE SECRET -> 401 ---")
_faux = _pyjwt.encode({"email": "x@y.z"}, "autre-secret", algorithm="HS256")
_bloque = False
try:
    lancer(SP.spordate_unified_profile_me(RequeteFictive({"Authorization": "Bearer " + _faux})))
except HTTPException as e:
    _bloque = (e.status_code == 401)
verifier("G1 signature étrangère -> 401", _bloque)

print("\n--- H : SPORDATEUR REFUSE (401) -> ON FERME, ON NE RÉÉMET PAS ---")
_installer_httpx(_ReponseFausse(401, {"error": "unauthorized"}))
_bloque = False
try:
    lancer(SP.spordate_unified_profile_me(RequeteFictive({"Authorization": "Bearer " + jwt_coach("bassi@example.test")})))
except HTTPException as e:
    _bloque = (e.status_code == 401)
verifier("H1 401 du pont -> 401 relayé", _bloque)

print("\n--- I : PONT INJOIGNABLE -> DÉGRADATION DOUCE, PAS DE PAGE CASSÉE (GO §6) ---")
_installer_httpx(SortieReseauInterdite("timeout simulé"))
_res = lancer(SP.spordate_unified_profile_me(RequeteFictive({"Authorization": "Bearer " + jwt_coach("bassi@example.test")})))
verifier("I1 réseau KO -> lie:false, motif pont_indisponible", _res.get("lie") is False and _res.get("motif") == "pont_indisponible")

print("\n--- J : NON LIÉ -> RÉPONSE SÛRE, RELAYÉE TELLE QUELLE (F du GO) ---")
_installer_httpx(_ReponseFausse(200, {"lie": False, "motif": "non_lie"}))
_res = lancer(SP.spordate_unified_profile_me(RequeteFictive({"Authorization": "Bearer " + jwt_coach("solo@example.test")})))
verifier("J1 non lié -> lie:false", _res.get("lie") is False and _res.get("motif") == "non_lie")

print("\n--- K : LA SOURCE N'ACCEPTE AUCUN REPLI X-User-Email ---")
_src = io.open(os.path.join(RACINE, "api", "routes", "spordate_routes.py"), encoding="utf-8").read()
_bloc = _src[_src.index("async def spordate_unified_profile_me"):]
verifier("K1 identité coach par JWT SIGNÉ (_v311, pas _v263)", "_v311_coach_email_from_jwt" in _bloc)
verifier("K2 le repli _v263 (X-User-Email) n'est PAS utilisé ici", "_v263_authenticated_coach" not in _bloc)
# On vise la LECTURE réelle de l'en-tête, pas les mentions en commentaire :
# le bloc explique justement POURQUOI ce repli est interdit ici.
verifier("K3 l'en-tête X-User-Email n'est jamais LU dans cette route",
         'headers.get("X-User-Email")' not in _bloc and "headers['X-User-Email']" not in _bloc)
verifier("K4 aucune écriture Mongo dans cette route",
         all(m not in _bloc for m in ("insert_one", "update_one", "delete_one", "insert_many")))

# restaurer la socket
socket.socket.connect = _vrai_connect
print("\n%d PASS · %d FAIL" % (_p, _f))
sys.exit(0 if _f == 0 else 1)

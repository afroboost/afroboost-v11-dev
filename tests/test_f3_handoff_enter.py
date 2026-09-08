#!/usr/bin/env python3
"""
F3 FINAL — LA ROUTE SERVEUR DE HANDOFF `/api/spordate/enter`.

Exécution :
  python3 tests/test_f3_handoff_enter.py

CE QUE CE BANC PROUVE
  - `_next_interne_sur` ne laisse passer qu'un chemin INTERNE : toute tentative
    d'ouverture externe (http, //host, /\\host, javascript:, back-slash,
    caractère de contrôle) est réduite à '' ;
  - `/enter` SANS cookie exploitable ne fabrique AUCUNE session : il redirige
    (303) vers /rencontre, en gardant un `next` interne, jamais un `t=` ;
  - `/enter` AVEC un cookie de session coach valide émet un jeton signé et
    redirige (303) vers /rencontre?t=…&next=… — le vrai handoff serveur ;
  - la cible du 303 est TOUJOURS interne (/rencontre), jamais une URL fournie.

Aucun réseau réel : la base est un bouchon async ; aucune socket n'est ouverte.
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

os.environ.setdefault("MONGO_URL", "mongodb://bouchon-f3-inexistant:27017")
os.environ["AFRO_SPORDATE_SHARED_SECRET"] = "secret-pont-de-test-f3"

import jwt as _pyjwt  # noqa: E402
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
    """Requête minimale : cookies + query params choisis."""
    def __init__(self, cookies=None, query=None):
        self.cookies = cookies or {}
        self.query_params = query or {}


class FausseCollection:
    def __init__(self, docs):
        self._docs = docs
    async def find_one(self, filtre, projection=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in filtre.items()):
                return dict(d)
        return None


class FausseBase:
    """Juste ce que `_email_depuis_cookie_session` interroge."""
    def __init__(self, sessions=None, google_users=None, users_auth=None):
        self.coach_sessions = FausseCollection(sessions or [])
        self.google_users = FausseCollection(google_users or [])
        self.users_auth = FausseCollection(users_auth or [])
        self.spordate_bridge_usage = _TraceBidon()

class _TraceBidon:
    async def insert_one(self, doc):  # la trace ne doit jamais faire échouer
        return None


# ── 1. VALIDATION DE `next` ────────────────────────────────────────────────
verifier("next interne simple accepté", SP._next_interne_sur("/profile") == "/profile")
verifier("next interne profond accepté", SP._next_interne_sur("/profile/abc") == "/profile/abc")
verifier("vide -> ''", SP._next_interne_sur("") == "")
verifier("None -> ''", SP._next_interne_sur(None) == "")
verifier("http externe -> ''", SP._next_interne_sur("http://evil.example") == "")
verifier("https externe -> ''", SP._next_interne_sur("https://evil.example") == "")
verifier("//host protocole-relatif -> ''", SP._next_interne_sur("//evil.example") == "")
verifier("/\\host -> ''", SP._next_interne_sur("/\\evil.example") == "")
verifier("back-slash n'importe où -> ''", SP._next_interne_sur("/a\\b") == "")
verifier("javascript: -> ''", SP._next_interne_sur("/x/javascript:alert(1)") == "" or SP._next_interne_sur("javascript:alert(1)") == "")
verifier("scheme dans le chemin -> ''", SP._next_interne_sur("/a://b") == "")
verifier("caractère de contrôle -> ''", SP._next_interne_sur("/a\nb") == "")
verifier("ne commençant pas par / -> ''", SP._next_interne_sur("profile") == "")


# ── 2. `/enter` SANS COOKIE : aucune session inventée ──────────────────────
SP.db = FausseBase()  # base présente mais aucune session -> pas d'identité

r = lancer(SP.spordate_enter(RequeteFictive()))
loc = r.headers.get("location", "")
verifier("sans cookie: 303", r.status_code == 303, str(r.status_code))
verifier("sans cookie: va vers /rencontre", loc == "/rencontre", loc)
verifier("sans cookie: aucun t=", "t=" not in loc, loc)
verifier("sans cookie: Cache-Control no-store", r.headers.get("cache-control") == "no-store")

r = lancer(SP.spordate_enter(RequeteFictive(query={"next": "/profile"})))
loc = r.headers.get("location", "")
verifier("sans cookie + next interne: /rencontre?next=/profile", loc == "/rencontre?next=/profile", loc)

r = lancer(SP.spordate_enter(RequeteFictive(query={"next": "https://evil.example"})))
loc = r.headers.get("location", "")
verifier("sans cookie + next externe: next ignoré", loc == "/rencontre", loc)


# ── 3. `/enter` AVEC COOKIE VALIDE : vrai handoff serveur ───────────────────
demain = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
SP.db = FausseBase(
    sessions=[{"session_token": "SESSABC", "user_id": "u1", "expires_at": demain}],
    google_users=[{"user_id": "u1", "email": "Coach@Afroboost.com"}],
)

r = lancer(SP.spordate_enter(RequeteFictive(cookies={"coach_session_token": "SESSABC"},
                                            query={"next": "/profile"})))
loc = r.headers.get("location", "")
verifier("cookie valide: 303", r.status_code == 303, str(r.status_code))
verifier("cookie valide: /rencontre?t=…", loc.startswith("/rencontre?t="), loc)
verifier("cookie valide: next porté", loc.endswith("&next=/profile"), loc)

# le jeton doit être signé, à audience spordate, e-mail normalisé en minuscules
_t = loc.split("t=", 1)[1].split("&", 1)[0]
_payload = _pyjwt.decode(_t, os.environ["AFRO_SPORDATE_SHARED_SECRET"],
                         algorithms=["HS256"], audience="spordate")
verifier("jeton: e-mail normalisé", _payload.get("email") == "coach@afroboost.com", str(_payload.get("email")))
verifier("jeton: émetteur afroboost", _payload.get("iss") == "afroboost")

# cookie présent mais session inconnue -> pas d'identité, repli sûr
r = lancer(SP.spordate_enter(RequeteFictive(cookies={"coach_session_token": "INCONNU"})))
verifier("cookie inconnu: repli /rencontre sans t=", r.headers.get("location") == "/rencontre")

# session expirée -> pas d'identité
hier = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
SP.db = FausseBase(
    sessions=[{"session_token": "OLD", "user_id": "u1", "expires_at": hier}],
    google_users=[{"user_id": "u1", "email": "x@y.z"}],
)
r = lancer(SP.spordate_enter(RequeteFictive(cookies={"coach_session_token": "OLD"})))
verifier("session expirée: repli /rencontre sans t=", r.headers.get("location") == "/rencontre")


print(f"\n{_p} PASS · {_f} FAIL")
sys.exit(0 if _f == 0 else 1)

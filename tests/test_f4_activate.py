#!/usr/bin/env python3
"""
F4 — LA ROUTE D'ACTIVATION AFROBOOST : IDENTITÉ SIGNÉE + CONSENTEMENT, OU RIEN.

Exécution : python3 tests/test_f4_activate.py

CE QUE ÇA PROUVE (§16-B/G/H/I)
  - consentement absent / faux / non-booléen -> 400, aucun jeton ;
  - aucune identité signée -> 401 ;
  - X-User-Email seul -> 401 (aucune autorité, falsifiable) ;
  - e-mail/uid fourni par le client dans le corps -> IGNORÉ (jamais d'autorité) ;
  - JWT coach signé + consent:true -> 200, URL /rencontre/activer?t=…, et le
    jeton porte aud spordate-activate, consent:true, l'e-mail SIGNÉ (pas celui
    du corps).

Aucun réseau, aucune base (db=None).
"""
import asyncio, os, sys
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-f4:27017")
os.environ["JWT_SECRET"] = "secret-jwt-de-test-f4"
os.environ["AFRO_SPORDATE_SHARED_SECRET"] = "secret-pont-de-test-f4"

import jwt as _pyjwt
import api.routes.spordate_routes as SP

SP.db = None  # pas de trace en base pendant le test

# Le drapeau F4 est testé à part (gating dormant) ; ici on teste la LOGIQUE
# d'activation, donc on le force à ON.
async def _flag_on(): return True
SP._social_activation_actif = _flag_on

_p = 0; _f = 0
def ok(l, cond, d=""):
    global _p, _f
    if cond: print("PASS  " + l); _p += 1
    else: print("FAIL  " + l + ("  — " + d if d else "")); _f += 1
def lancer(c): return asyncio.get_event_loop().run_until_complete(c)

class Req:
    def __init__(self, corps=None, headers=None):
        self._corps = corps if corps is not None else {}
        self.headers = headers or {}
    async def json(self): return self._corps

def statut(rep):
    return getattr(rep, "status_code", 200)
def contenu(rep):
    import json as _j
    b = getattr(rep, "body", None)
    if b is not None:
        return _j.loads(b.decode() if isinstance(b, (bytes, bytearray)) else b)
    return rep  # dict simple

jwt_coach = _pyjwt.encode({"email": "Coach@X.com"}, os.environ["JWT_SECRET"], algorithm="HS256")
if isinstance(jwt_coach, bytes): jwt_coach = jwt_coach.decode()
AUTH = {"Authorization": "Bearer " + jwt_coach}

# 0 — DORMANT : drapeau OFF -> 403, la route est inerte
async def _flag_off(): return False
SP._social_activation_actif = _flag_off
ok("flag OFF -> 403 (dormant)", statut(lancer(SP.spordate_activate(Req({"consent": True}, AUTH)))) == 403)
SP._social_activation_actif = _flag_on

# 1 — consentement
ok("consent absent -> 400", statut(lancer(SP.spordate_activate(Req({}, AUTH)))) == 400)
ok("consent false -> 400", statut(lancer(SP.spordate_activate(Req({"consent": False}, AUTH)))) == 400)
ok("consent 'true' string -> 400", statut(lancer(SP.spordate_activate(Req({"consent": "true"}, AUTH)))) == 400)

# 2 — identité
ok("aucune identité -> 401", statut(lancer(SP.spordate_activate(Req({"consent": True}, {})))) == 401)
ok("X-User-Email seul -> 401 (aucune autorité)",
   statut(lancer(SP.spordate_activate(Req({"consent": True}, {"X-User-Email": "a@b.c"})))) == 401)

# 3 — succès : JWT coach + consent
rep = lancer(SP.spordate_activate(Req({"consent": True, "email": "attaquant@evil.com"}, AUTH)))
ok("JWT + consent -> 200", statut(rep) == 200, str(statut(rep)))
d = contenu(rep)
url = (d or {}).get("url", "")
ok("URL vers /rencontre/activer?t=", url.startswith("/rencontre/activer?t="), url)
jeton = url.split("t=", 1)[1] if "t=" in url else ""
charge = _pyjwt.decode(jeton, os.environ["AFRO_SPORDATE_SHARED_SECRET"], algorithms=["HS256"], audience="spordate-activate")
ok("jeton aud spordate-activate", charge.get("aud") == "spordate-activate")
ok("jeton consent:true", charge.get("consent") is True)
ok("jeton e-mail = identité SIGNÉE (pas le corps)", charge.get("email") == "coach@x.com", str(charge.get("email")))
ok("jeton NE prend PAS l'e-mail du corps (attaquant@evil.com ignoré)", charge.get("email") != "attaquant@evil.com")
ok("jeton a un jti", bool(charge.get("jti")))
ok("jeton émetteur afroboost", charge.get("iss") == "afroboost")

print(f"\n{_p} PASS · {_f} FAIL")
sys.exit(0 if _f == 0 else 1)

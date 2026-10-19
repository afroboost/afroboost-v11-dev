#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-A — UNE ADRESSE SUPER-ADMIN DÉCLARÉE NE DONNE AUCUN PRIVILÈGE.

Passe par l'APPLICATION RÉELLE (`S.fastapi_app`, intergiciels compris) via httpx
ASGITransport, sur une base EN MÉMOIRE. Aucun réseau, aucune base réelle, aucun e-mail.

  A. pures : `p0a_entete_super_admin_non_prouve` ;
  B. /api/auth/role : en-tête seul → aucun privilège ; JWT super-admin → super_admin ;
     JWT d'un autre coach + en-tête super-admin → aucun privilège ; JWT expiré → aucun ;
  C. une route `require_auth` + super-admin (PUT /platform-settings) : 401 avec l'en-tête seul,
     200 avec le JWT ;
  D. corps déclaré : /admin/create-code, /admin/delete-history, /admin/change-identity →
     403 sans JWT, contrôle passé avec JWT ;
  E. Live : /boosttribe/access → pas d'accès admin sur l'en-tête seul ; 200 avec JWT ;
  F. coach ordinaire : comportement inchangé (hors périmètre P0-A) ;
  G. retour arrière : drapeau P0A_REPLI_ENTETE_SUPERADMIN = true → ancien comportement ;
  H. aucune sortie réseau.
"""
try:
    import builtins as _b, os as _o, sys as _s
    _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
    import api.resend_central as _rc
    _b._rc = _rc
except Exception:  # noqa: BLE001
    pass
import asyncio
import io
import json
import os
import socket
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
_TENT = []
_GA = socket.getaddrinfo


def _dns(h, p, *a, **k):
    if str(h) in ("localhost", "127.0.0.1", "::1", None, "test", "testserver"):
        return _GA(h, p, *a, **k)
    _TENT.append(h)
    raise OSError("reseau interdit")


socket.getaddrinfo = _dns
SECRET = "secret-de-test-p0a-sans-aucun-rapport-avec-la-production-0123456789"
os.environ["JWT_SECRET"] = SECRET
os.environ["AFRO_BT_SHARED_SECRET"] = "secret-bt-de-test-p0a-0123456789abcdef"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("RESEND_API_KEY", None)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p0a-inexistant:27017")

import httpx  # noqa: E402
import jwt as _jwt  # noqa: E402
import api.server as S  # noqa: E402

SA = "contact.artboost@gmail.com"
COACH_B = "coach.b.fictif@exemple.test"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_src = io.open(_BANC, encoding="utf-8").read()
_esp = {"S": S, "asyncio": asyncio, "COACH_A": SA, "COACH_B": COACH_B, "INSTANT": "2026-10-19T08:00:00+00:00",
        "json": json, "os": os, "sys": sys, "_jwt": _jwt, "SECRET": SECRET, "HTTPException": S.HTTPException}
exec(compile(_src[_src.index("def lancer(coroutine):"):_src.index('# ============================================================================\nprint("\\n1.')],
             _BANC, "exec"), _esp)  # noqa: S102
BaseBouchon, _CollectionBase = _esp["BaseBouchon"], _esp["CollectionBouchon"]


class CollectionBouchon(_CollectionBase):
    """Complète le bouchon partagé de ce dont les routes admin ont besoin (en mémoire)."""
    async def update_many(self, filtre, maj, *a, **k):
        n = 0
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {}); n += 1
        return type("R", (), {"matched_count": n, "modified_count": n})()

R = []


def verifier(nom, ok, detail=""):
    R.append(bool(ok))
    print("  %-6s %s%s" % ("OK" if ok else "ECHEC", nom, "" if ok else "  -> %s" % detail))


def jeton(email, exp_s=3600, typ=None):
    p = {"email": email, "sub": email, "role": "super_admin" if email == SA else "coach",
         "exp": int(time.time()) + exp_s}
    if typ:
        p["type"] = typ
    return _jwt.encode(p, SECRET, algorithm="HS256")


def base(flags=None):
    b = BaseBouchon([])
    b["coaches"] = CollectionBouchon("coaches", [{"email": COACH_B, "is_active": True, "id": "c-b", "credits": 3}])
    b["feature_flags"] = CollectionBouchon("feature_flags", [dict({"id": "feature_flags"}, **(flags or {}))])
    b["platform_settings"] = CollectionBouchon("platform_settings", [{"id": "platform_settings"}])
    b["boosttribe_usage"] = CollectionBouchon("boosttribe_usage", [])
    b["boosttribe_live"] = CollectionBouchon("boosttribe_live", [])
    for nom in ("chat_messages", "chat_participants", "chat_sessions", "users", "notifications"):
        b[nom] = CollectionBouchon(nom, [])
    S.db = b
    import api.routes.coach_routes as _CR
    _CR.db = b                        # /auth/role vit dans coach_routes (handle `db` propre au module)
    S._p0a_cache["t"] = -1e9          # pas de mémoire entre deux scénarios
    return b


async def appel(methode, chemin, entetes=None, corps=None):
    transport = httpx.ASGITransport(app=S.fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.request(methode, chemin, headers=entetes or {}, json=corps)


def faire(methode, chemin, entetes=None, corps=None):
    return asyncio.get_event_loop().run_until_complete(appel(methode, chemin, entetes, corps))


H_SA = {"X-User-Email": SA}
J_SA = {"Authorization": "Bearer " + jeton(SA)}

print("\nA. FONCTION PURE")
verifier("A1. en-tête super-admin sans JWT → non prouvé", S.p0a_entete_super_admin_non_prouve(SA, ""))
verifier("A2. en-tête super-admin + JWT du même e-mail → prouvé", not S.p0a_entete_super_admin_non_prouve(SA, SA))
verifier("A3. casse / espaces ignorés", not S.p0a_entete_super_admin_non_prouve("  Contact.Artboost@Gmail.com ", SA))
verifier("A4. en-tête super-admin + JWT d'un autre → non prouvé", S.p0a_entete_super_admin_non_prouve(SA, COACH_B))
verifier("A5. en-tête d'un coach ordinaire → hors périmètre", not S.p0a_entete_super_admin_non_prouve(COACH_B, ""))

print("\nB. /api/auth/role")
base()
r = faire("GET", "/api/auth/role", H_SA)
verifier("B1. e-mail super-admin déclaré seul → AUCUN privilège", r.status_code == 200 and r.json().get("is_super_admin") is False
         and r.json().get("role") == "user", r.text)
r = faire("GET", "/api/auth/role", dict(H_SA, **J_SA))
verifier("B2. JWT super-admin (+ en-tête) → super_admin", r.json().get("is_super_admin") is True, r.text)
r = faire("GET", "/api/auth/role", dict(H_SA, Authorization="Bearer " + jeton(COACH_B)))
verifier("B3. JWT d'un autre coach + en-tête super-admin → aucun privilège", r.json().get("is_super_admin") is False, r.text)
r = faire("GET", "/api/auth/role", dict(H_SA, Authorization="Bearer " + jeton(SA, exp_s=-60)))
verifier("B4. JWT super-admin EXPIRÉ → aucun privilège", r.json().get("is_super_admin") is False, r.text)
r = faire("GET", "/api/auth/role", dict(H_SA, Authorization="Bearer " + jeton(SA, typ="subscriber")))
verifier("B5. jeton ABONNÉ portant l'adresse → aucun privilège", r.json().get("is_super_admin") is False, r.text)
r = faire("GET", "/api/auth/role", dict(H_SA, Authorization="Bearer " + _jwt.encode(
    {"email": SA, "exp": int(time.time()) + 3600}, "un-autre-secret-forge-0123456789abcdef", algorithm="HS256")))
verifier("B6. JWT FORGÉ (mauvaise signature) → aucun privilège", r.json().get("is_super_admin") is False, r.text)

print("\nC. ROUTE require_auth + super-admin : PUT /api/platform-settings")
b = base()
r = faire("PUT", "/api/platform-settings", H_SA, {"maintenance_mode": True})
verifier("C1. e-mail déclaré seul → 401/403", r.status_code in (401, 403), r.status_code)
verifier("C2. et RIEN n'est écrit", b["platform_settings"].documents[0].get("maintenance_mode") is None)
r = faire("PUT", "/api/platform-settings", {}, {"maintenance_mode": True})
verifier("C3. sans rien → 401/403", r.status_code in (401, 403), r.status_code)
r = faire("PUT", "/api/platform-settings", dict(H_SA, **J_SA), {"partner_access_enabled": True})
verifier("C4. JWT super-admin → 200", r.status_code == 200, "%s %s" % (r.status_code, r.text[:200]))

print("\nD. E-MAIL DÉCLARÉ DANS LE CORPS")
base()
r = faire("POST", "/api/admin/create-code", {}, {"admin_email": SA, "customer_email": "x@exemple.test", "sessions": 99})
verifier("D1. create-code : admin_email dans le corps, sans JWT → 403", r.status_code == 403, r.status_code)
r = faire("POST", "/api/admin/create-code", H_SA, {"admin_email": SA, "customer_email": "x@exemple.test"})
verifier("D2. create-code : + en-tête super-admin, sans JWT → 403", r.status_code == 403, r.status_code)
r = faire("POST", "/api/admin/create-code", J_SA, {})
verifier("D3. create-code : JWT super-admin → contrôle passé (400 « customer_email requis »)",
         r.status_code == 400 and "customer_email" in r.text, "%s %s" % (r.status_code, r.text[:200]))
for chemin, corps in (("/api/admin/delete-history", {"email": SA, "session_id": "s-1"}),
                      ("/api/admin/change-identity", {"email": SA, "participant_id": "p-1"})):
    r = faire("POST", chemin, {}, corps)
    verifier("D4. %s : e-mail du corps sans JWT → 403" % chemin, r.status_code == 403, r.status_code)
    r = faire("POST", chemin, J_SA, corps)
    verifier("D5. %s : JWT super-admin → contrôle passé (≠ 401/403)" % chemin, r.status_code not in (401, 403),
             "%s %s" % (r.status_code, r.text[:200]))

print("\nE. LIVE : /api/boosttribe/access")
b = base()
r = faire("POST", "/api/boosttribe/access", H_SA, {})
verifier("E1. e-mail super-admin déclaré seul → aucun accès admin (403)", r.status_code == 403, "%s %s" % (r.status_code, r.text[:200]))
verifier("E2. aucun jeton émis", len(b["boosttribe_usage"].documents) == 0)
r = faire("POST", "/api/boosttribe/access", dict(H_SA, **J_SA), {})
verifier("E3. JWT super-admin → 200 + URL d'embed", r.status_code == 200 and "bt_token" in r.text, "%s %s" % (r.status_code, r.text[:200]))

print("\nF. COACH ORDINAIRE : INCHANGÉ (hors P0-A)")
base()
r = faire("GET", "/api/auth/role", {"X-User-Email": COACH_B})
verifier("F1. /auth/role d'un coach ordinaire : même réponse qu'avant (coach)", r.json().get("role") == "coach", r.text)

print("\nG. RETOUR ARRIÈRE PAR DRAPEAU")
base({"P0A_REPLI_ENTETE_SUPERADMIN": True})
r = faire("GET", "/api/auth/role", H_SA)
verifier("G1. drapeau à true → ancien comportement rétabli", r.json().get("is_super_admin") is True, r.text)
base({"P0A_REPLI_ENTETE_SUPERADMIN": False})
r = faire("GET", "/api/auth/role", H_SA)
verifier("G2. drapeau à false → protection active", r.json().get("is_super_admin") is False, r.text)


class BaseEnPanne(BaseBouchon):
    def __getitem__(self, nom):
        if nom == "feature_flags":
            raise RuntimeError("base injoignable")
        return super().__getitem__(nom)


S.db = BaseEnPanne([])
S._p0a_cache["t"] = -1e9
r = faire("GET", "/api/auth/role", H_SA)
verifier("G3. base illisible → protection maintenue (repli fermé)", r.json().get("is_super_admin") is False, r.text)
verifier("G4. le drapeau est pilotable par PUT /feature-flags", "P0A_REPLI_ENTETE_SUPERADMIN" in S.FeatureFlagsUpdate.model_fields)

print("\nH. AUCUNE SORTIE RÉSEAU")
verifier("H1. aucune tentative réseau", not _TENT, _TENT)

ok = sum(R)
print("\nP0-A SUPER-ADMIN — %d/%d vérifications (application réelle, base en mémoire, aucun réseau)" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)

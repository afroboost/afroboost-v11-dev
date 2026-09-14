# -*- coding: utf-8 -*-
"""LIVE RAPIDE — « un live est-il en cours ? » et la porte directe vers la session.

CE QUE CES BANCS TIENNENT :
  * `GET /boosttribe/live-status` est public et MINIMAL : `{active}` — jamais
    le code de session, jamais l'hôte ;
  * `POST /boosttribe/live-status` exige un coach/admin authentifié (jeton
    signé) ; « started » pose le live, « ended » ne ferme QUE la session
    annoncée (un « ended » tardif ne coupe pas le live suivant) ;
  * un live sans fin depuis plus de 3 h n'est plus « en cours » ;
  * `bt_session` n'entre dans l'URL d'embed que par `/boosttribe/access`
    (réponse réservée à qui a le droit d'entrer), et seulement si un live est
    actif ;
  * les entrées sont bornées (event, code [A-Z0-9-]).

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_live_rapide.py
"""
import ast, asyncio, io, os, re, sys, types, urllib.parse
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(True)
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def _source(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            n.decorator_list = []
            return ast.unparse(n)
    raise AssertionError("fonction introuvable : " + nom)


class Coll:
    def __init__(self):
        self.doc = None

    async def find_one(self, f, p=None):
        if self.doc and all(self.doc.get(k) == v for k, v in f.items()):
            d = dict(self.doc); d.pop("_id", None); return d
        return None

    async def update_one(self, f, u, upsert=False):
        if self.doc and all(self.doc.get(k) == v for k, v in f.items()):
            self.doc.update(u.get("$set", {}))
            return types.SimpleNamespace(matched_count=1)
        if upsert:
            self.doc = dict(f); self.doc.update(u.get("$set", {}))
            return types.SimpleNamespace(matched_count=0)
        return types.SimpleNamespace(matched_count=0)


class HTTPException(Exception):
    def __init__(self, status_code, detail=""):
        self.status_code, self.detail = status_code, detail


class Req:
    def __init__(self, corps): self._c = corps
    async def json(self): return self._c


class Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass


def charger(admin="coach@exemple.invalid"):
    base = types.SimpleNamespace(boosttribe_live=Coll())
    env = {"db": base, "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
           "logger": Log(), "HTTPException": HTTPException, "re": re, "urllib": urllib,
           "require_auth": lambda r: getattr(r, "email", None) or (_ for _ in ()).throw(HTTPException(401)),
           "is_super_admin": lambda e: e == admin, "BTLIVE_MAX_H": 3, "Request": object}
    for nom in ("_btlive_etat", "boosttribe_live_status", "boosttribe_live_status_set"):
        exec(compile(_source(nom), "<prod>", "exec"), env)
    return env, base


def run(c): return asyncio.get_event_loop().run_until_complete(c)


def req(corps, email=None):
    r = Req(corps)
    if email: r.email = email
    return r


# ═══ 1. lecture publique minimale ═══
env, base = charger()
r = run(env["boosttribe_live_status"]())
verifier("sans live : {active: False}", r == {"active": False, "started_at": None}, repr(r))

# ═══ 2. écriture réservée au coach ═══
try:
    run(env["boosttribe_live_status_set"](req({"event": "started", "session_code": "ABCD-1234"})))
    verifier("anonyme -> refusé", False)
except HTTPException as e:
    verifier("anonyme -> refusé (401)", e.status_code == 401)
try:
    run(env["boosttribe_live_status_set"](req({"event": "started", "session_code": "ABCD-1234"}, email="autre@exemple.invalid")))
    verifier("non-admin -> refusé", False)
except HTTPException as e:
    verifier("non-admin -> refusé (403)", e.status_code == 403)

# ═══ 3. started puis lecture ═══
r = run(env["boosttribe_live_status_set"](req({"event": "started", "session_code": "abcd-1234"}, email="coach@exemple.invalid")))
verifier("coach started -> live actif", r["ok"] and r["live"]["active"] and r["live"]["session_code"] == "ABCD-1234", repr(r))
pub = run(env["boosttribe_live_status"]())
verifier("lecture publique : active True, SANS code de session ni hôte",
         pub["active"] is True and "session_code" not in pub and "host" not in pub, repr(pub))

# ═══ 4. ended tardif d'une autre session ne coupe rien ═══
run(env["boosttribe_live_status_set"](req({"event": "ended", "session_code": "ZZZZ-0000"}, email="coach@exemple.invalid")))
verifier("ended d'une AUTRE session : le live courant reste actif", run(env["_btlive_etat"]())["active"])
run(env["boosttribe_live_status_set"](req({"event": "ended", "session_code": "ABCD-1234"}, email="coach@exemple.invalid")))
verifier("ended de LA session : plus de live", run(env["_btlive_etat"]()) == {"active": False})

# ═══ 5. expiration 3 h ═══
env, base = charger()
run(env["boosttribe_live_status_set"](req({"event": "started", "session_code": "ABCD-1234"}, email="coach@exemple.invalid")))
base.boosttribe_live.doc["started_at"] = (datetime.now(timezone.utc) - timedelta(hours=3, minutes=1)).isoformat()
verifier("un live sans fin depuis > 3 h n'est plus en cours", run(env["_btlive_etat"]()) == {"active": False})

# ═══ 6. bornes ═══
for corps in ({"event": "boum", "session_code": "ABCD-1234"}, {"event": "started", "session_code": "../x"},
              {"event": "started", "session_code": ""}, {"event": "started", "session_code": "A" * 41}):
    try:
        run(env["boosttribe_live_status_set"](req(corps, email="coach@exemple.invalid")))
        verifier("entrée refusée : %r" % (corps,), False)
    except HTTPException as e:
        verifier("entrée refusée (400) : %r" % (corps,), e.status_code == 400)

# ═══ 7. l'URL d'embed porte bt_session seulement si un live est actif ═══
acces = _source("boosttribe_access")
verifier("access lit l'état du live et ajoute bt_session", "_btlive_etat()" in acces and "&bt_session=" in acces and "urllib.parse.quote" in acces)
verifier("access ne divulgue pas le code hors de l'URL d'embed",
         "'live': {'active': bool(_live.get('active')), 'kind': usage.get('kind')}" in acces)
statut = _source("boosttribe_live_status")
verifier("la route publique ne renvoie que active + started_at", "session_code" not in statut.split("return")[-1])

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + detail) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

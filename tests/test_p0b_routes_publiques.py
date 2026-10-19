#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0-B — ROUTES PUBLIQUES DANGEREUSES : AUTH SERVEUR + VALIDATION. AUCUN RÉSEAU, AUCUNE BASE RÉELLE.

Application RÉELLE (`S.fastapi_app`, intergiciels compris) via httpx ASGITransport,
base EN MÉMOIRE, dossier d'emojis TEMPORAIRE.

  A. anonyme / e-mail déclaré / autre coach → 401/403 (ou 404 sans oracle) ;
  B. appel légitime (JWT) → comportement normal ;
  C. `../` dans le nom / l'extension → refus ;
  D. chemin absolu → refus ;
  E. type de fichier interdit (texte, SVG, extension ≠ contenu) → refus ;
  F. image valide → écrite DANS le dossier temporaire, nom choisi par le serveur ;
  G. taille maximale ; H. propriété (emojis, sessions de chat) ; I. aucune sortie réseau.
"""
try:
    import builtins as _b, os as _o, sys as _s
    _s.path.insert(0, _o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))))
    import api.resend_central as _rc
    _b._rc = _rc
except Exception:  # noqa: BLE001
    pass
import asyncio
import base64
import io
import json
import os
import pathlib
import socket
import sys
import tempfile
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
_TENT = []
_GA = socket.getaddrinfo


def _dns(h, p, *a, **k):
    if str(h) in ("localhost", "127.0.0.1", "::1", None, "testserver"):
        return _GA(h, p, *a, **k)
    _TENT.append(h)
    raise OSError("reseau interdit")


socket.getaddrinfo = _dns
SECRET = "secret-de-test-p0b-sans-aucun-rapport-avec-la-production-0123456789"
os.environ["JWT_SECRET"] = SECRET
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("RESEND_API_KEY", None)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p0b-inexistant:27017")

import httpx  # noqa: E402
import jwt as _jwt  # noqa: E402
import api.server as S  # noqa: E402

SA = "contact.artboost@gmail.com"
COACH_B = "coach.b.fictif@exemple.test"
COACH_C = "coach.c.fictif@exemple.test"
_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_src = io.open(_BANC, encoding="utf-8").read()
_esp = {"S": S, "asyncio": asyncio, "COACH_A": SA, "COACH_B": COACH_B, "INSTANT": "2026-10-19T08:00:00+00:00",
        "json": json, "os": os, "sys": sys, "_jwt": _jwt, "SECRET": SECRET, "HTTPException": S.HTTPException}
exec(compile(_src[_src.index("def lancer(coroutine):"):_src.index('# ============================================================================\nprint("\\n1.')],
             _BANC, "exec"), _esp)  # noqa: S102
BaseBouchon, _Col = _esp["BaseBouchon"], _esp["CollectionBouchon"]


class Col(_Col):
    async def update_many(self, filtre, maj, *a, **k):
        n = 0
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {}); n += 1
        return type("R", (), {"matched_count": n, "modified_count": n})()

    async def delete_one(self, filtre, *a, **k):
        for i, d in enumerate(self.documents):
            if self._ok(d, filtre):
                self.documents.pop(i)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


R = []


def verifier(nom, ok, detail=""):
    R.append(bool(ok))
    print("  %-6s %s%s" % ("OK" if ok else "ECHEC", nom, "" if ok else "  -> %s" % detail))


def jeton(email):
    return _jwt.encode({"email": email, "sub": email, "role": "super_admin" if email == SA else "coach",
                        "exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")


J_SA = {"Authorization": "Bearer " + jeton(SA)}
J_B = {"Authorization": "Bearer " + jeton(COACH_B)}
J_C = {"Authorization": "Bearer " + jeton(COACH_C)}
H_SA = {"X-User-Email": SA}
DOSSIER = pathlib.Path(tempfile.mkdtemp(prefix="p0b_emojis_"))
S.EMOJIS_DIR = DOSSIER


def base():
    b = BaseBouchon([])
    for nom, docs in {
        "coaches": [{"email": COACH_B, "is_active": True}, {"email": COACH_C, "is_active": True}],
        "coach_auth": [{"id": "coach_auth", "email": SA}],
        "coach_subscriptions": [], "config": [{"id": "app_config"}], "emailjs_config": [], "categories": [],
        "custom_emojis": [], "messages": [], "comments": [], "users": [{"coach_id": COACH_B, "code": "AFR-T1", "name": "T",
                                                                       "subscription": {"end_date": "2099-01-01"}}],
        "chat_sessions": [{"id": "s-sa", "coach_id": SA, "is_ai_active": True},
                          {"id": "s-b", "coach_id": COACH_B, "is_ai_active": True},
                          {"id": "s-vieille", "is_ai_active": True}],
        "chat_messages": [], "feature_flags": [{"id": "feature_flags"}], "ai_config": [], "ai_logs": [],
    }.items():
        b[nom] = Col(nom, docs)
    S.db = b
    import api.routes.coach_routes as _CR
    _CR.db = b
    S._p0a_cache["t"] = -1e9
    return b


async def _appel(m, chemin, h=None, corps=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=S.fastapi_app), base_url="http://testserver") as c:
        return await c.request(m, chemin, headers=h or {}, json=corps)


def faire(m, chemin, h=None, corps=None):
    return asyncio.get_event_loop().run_until_complete(_appel(m, chemin, h, corps))


def refus(r):
    return r.status_code in (401, 403)


PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
GIF = base64.b64encode(b"GIF89a" + b"\x00" * 32).decode()
SVG = base64.b64encode(b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>").decode()
TXT = base64.b64encode(b"#!/bin/sh\nrm -rf /\n").decode()

print("\nA/B. ROUTES D'ADMINISTRATION → SUPER-ADMIN SIGNÉ")
ROUTES_SA = [("PUT", "/api/config", {"siteName": "pirate"}),
             ("PUT", "/api/coach-subscription", {"hasAudioService": True}),
             ("PUT", "/api/emailjs-config", {"serviceId": "x"}),
             ("POST", "/api/categories", {"name": "pirate"}),
             ("POST", "/api/v290-fix-publication-photos", None),
             ("POST", "/api/v299-fix-legacy-profile-photos", None),
             ("POST", "/api/v305-fix-quickreply-icons", None),
             ("POST", "/api/chat/sessions/restore-merged", None),
             ("GET", "/api/debug/network", None)]
for m, chemin, corps in ROUTES_SA:
    b = base()
    a = faire(m, chemin, {}, corps)
    e = faire(m, chemin, H_SA, corps)
    c = faire(m, chemin, J_B, corps)
    verifier("A. %s %s : anonyme %s / e-mail déclaré %s / coach ordinaire %s → refusés" % (m, chemin, a.status_code, e.status_code, c.status_code),
             refus(a) and refus(e) and refus(c))
b = base()
r = faire("PUT", "/api/config", J_SA, {"siteName": "Afroboost"})
verifier("B. PUT /api/config : super-admin signé → 200", r.status_code == 200 and b["config"].documents[0].get("siteName") == "Afroboost", r.status_code)
r = faire("PUT", "/api/emailjs-config", J_SA, {"serviceId": "svc"})
verifier("B. PUT /api/emailjs-config : super-admin signé → 200", r.status_code == 200, r.status_code)
r = faire("PUT", "/api/coach-subscription", J_SA, {"hasAudioService": False})
verifier("B. PUT /api/coach-subscription : super-admin signé → 200", r.status_code == 200, r.status_code)
r = faire("POST", "/api/categories", J_SA, {"name": "Danse"})
verifier("B. POST /api/categories : super-admin signé → 200", r.status_code == 200 and b["categories"].documents, r.status_code)
r = faire("POST", "/api/chat/sessions/restore-merged", J_SA)
verifier("B. POST /chat/sessions/restore-merged : super-admin signé → 200", r.status_code == 200, r.status_code)
b = base()
verifier("A. rien n'a été écrit par les appels refusés",
         not b["categories"].documents and b["config"].documents[0].get("siteName") is None)

print("\nA/B. ROUTES DU DASHBOARD → COACH SIGNÉ")
base()
r = faire("POST", "/api/ai-test", {}, {"message": "bonjour"})
verifier("A. POST /api/ai-test anonyme → refus (aucun appel OpenAI)", refus(r), r.status_code)
r = faire("POST", "/api/ai-test", H_SA, {"message": "bonjour"})
verifier("A. POST /api/ai-test e-mail déclaré → refus", refus(r), r.status_code)
r = faire("POST", "/api/ai-test", J_SA, {"message": ""})
verifier("B. POST /api/ai-test coach signé → contrôle passé (400 message requis)", r.status_code == 400, r.status_code)

b = base()
r = faire("PUT", "/api/chat/sessions/s-sa", {}, {"is_deleted": True})
verifier("A. PUT /chat/sessions anonyme → refus, session intacte", refus(r) and not b["chat_sessions"].documents[0].get("is_deleted"), r.status_code)
r = faire("PUT", "/api/chat/sessions/s-sa", J_B, {"is_deleted": True})
verifier("H. PUT /chat/sessions d'un AUTRE coach → 404, intacte", r.status_code == 404 and not b["chat_sessions"].documents[0].get("is_deleted"), r.status_code)
r = faire("PUT", "/api/chat/sessions/s-b", J_B, {"mode": "human"})
verifier("B. PUT /chat/sessions : SA session du coach → 200", r.status_code == 200, r.status_code)
r = faire("PUT", "/api/chat/sessions/s-vieille", J_SA, {"mode": "human"})
verifier("B. PUT /chat/sessions : super-admin → toutes, sessions anciennes comprises", r.status_code == 200, r.status_code)
r = faire("POST", "/api/chat/sessions/s-sa/toggle-ai", {})
verifier("A. toggle-ai anonyme → refus", refus(r), r.status_code)
r = faire("POST", "/api/chat/sessions/s-sa/toggle-ai", J_B)
verifier("H. toggle-ai par un autre coach → 404", r.status_code == 404, r.status_code)
r = faire("POST", "/api/chat/sessions/s-sa/toggle-ai", J_SA)
verifier("B. toggle-ai super-admin → 200 (IA basculée)", r.status_code == 200 and b["chat_sessions"].documents[0].get("is_ai_active") is False, r.status_code)

b = base()
r = faire("POST", "/api/reviews/request", {}, {"coach_email": COACH_B, "course_name": "x"})
verifier("A. reviews/request anonyme avec coach_email du corps → refus, aucun message", refus(r) and not b["messages"].documents, r.status_code)
r = faire("POST", "/api/reviews/request", J_C, {"coach_email": COACH_B, "course_name": "x"})
verifier("H. reviews/request : le coach du JWT fait foi (C n'écrit pas aux abonnés de B)",
         r.status_code == 200 and not b["messages"].documents, "%s %s" % (r.status_code, len(b["messages"].documents)))
r = faire("POST", "/api/reviews/request", J_B, {"course_name": "x"})
verifier("B. reviews/request : coach B → ses abonnés", r.status_code == 200 and len(b["messages"].documents) == 1, r.status_code)

print("\nEMOJIS DU CHAT (base)")
b = base()
URL_PNG = "data:image/png;base64," + PNG
r = faire("POST", "/api/chat/emojis", {}, {"name": "joie", "image_data": URL_PNG})
verifier("A. POST /chat/emojis anonyme → refus", refus(r) and not b["custom_emojis"].documents, r.status_code)
r = faire("POST", "/api/chat/emojis", J_B, {"name": "joie", "image_data": "data:image/svg+xml;base64," + SVG})
verifier("E. POST /chat/emojis SVG → 400", r.status_code == 400, r.status_code)
r = faire("POST", "/api/chat/emojis", J_B, {"name": "gros", "image_data": "data:image/png;base64," + "A" * (S.P0B_EMOJI_DATAURL_MAX + 10)})
verifier("G. POST /chat/emojis trop lourd → 413", r.status_code == 413, r.status_code)
r = faire("POST", "/api/chat/emojis", J_B, {"name": "../../joie<script>", "image_data": URL_PNG})
emoji = r.json() if r.status_code == 200 else {}
verifier("B. POST /chat/emojis coach → 200, propriétaire enregistré, nom nettoyé",
         r.status_code == 200 and emoji.get("coach_id") == COACH_B and "/" not in emoji.get("name", "/") and ".." not in emoji.get("name", ".."),
         r.text[:200])
r = faire("GET", "/api/chat/emojis", {})
verifier("B. GET /chat/emojis reste public (chat visiteur)", r.status_code == 200, r.status_code)
r = faire("DELETE", "/api/chat/emojis/" + emoji.get("id", "x"), {})
verifier("A. DELETE /chat/emojis anonyme → refus", refus(r) and len(b["custom_emojis"].documents) == 1, r.status_code)
r = faire("DELETE", "/api/chat/emojis/" + emoji.get("id", "x"), J_C)
verifier("H. DELETE par un autre coach → 404, emoji conservé", r.status_code == 404 and len(b["custom_emojis"].documents) == 1, r.status_code)
r = faire("DELETE", "/api/chat/emojis/" + emoji.get("id", "x"), J_B)
verifier("B. DELETE par son propriétaire → 200", r.status_code == 200 and not b["custom_emojis"].documents, r.status_code)

print("\nUPLOAD FICHIER : POST /api/custom-emojis/upload")
base()
avant = set(os.listdir(DOSSIER))
r = faire("POST", "/api/custom-emojis/upload", {}, {"name": "x", "image": PNG})
verifier("A. anonyme → refus, aucun fichier", refus(r) and set(os.listdir(DOSSIER)) == avant, r.status_code)
r = faire("POST", "/api/custom-emojis/upload", H_SA, {"name": "x", "image": PNG})
verifier("A. e-mail super-admin déclaré → refus", refus(r), r.status_code)
r = faire("POST", "/api/custom-emojis/upload", J_B, {"name": "x", "image": PNG})
verifier("A. coach ordinaire → refus", refus(r), r.status_code)
for nom in ("../../api/server", "..", "a/../b", "..\\..\\x", "x/y"):
    r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": nom, "image": PNG})
    verifier("C. nom %r → 400" % nom, r.status_code == 400, r.status_code)
for ext in ("../../py", "py", "php", "svg", "png/../../x"):
    r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "ok", "image": PNG, "extension": ext})
    verifier("C/E. extension %r → 400" % ext, r.status_code == 400, r.status_code)
for nom in ("/etc/passwd", "/app/api/server.py", "C:\\\\Windows\\\\x", "~/.ssh/x"):
    r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": nom, "image": PNG})
    verifier("D. chemin absolu %r → 400" % nom, r.status_code == 400, r.status_code)
r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "script", "image": TXT, "extension": "png"})
verifier("E. contenu texte déguisé en png → 400", r.status_code == 400, r.status_code)
r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "svg", "image": SVG})
verifier("E. SVG → 400", r.status_code == 400, r.status_code)
r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "gif", "image": GIF, "extension": "png"})
verifier("E. extension ≠ contenu (gif annoncé png) → 400", r.status_code == 400, r.status_code)
r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "lourd", "image": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * (S.P0B_EMOJI_MAX_OCTETS + 1)).decode()})
verifier("G. plus de 512 Ko → 413", r.status_code == 413, r.status_code)
r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "x", "image": "pas du base64 !!!"})
verifier("E. base64 invalide → 400", r.status_code == 400, r.status_code)
verifier("C/D/E/G. AUCUN fichier écrit par les refus", set(os.listdir(DOSSIER)) == avant, os.listdir(DOSSIER))
r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "Danse joyeuse", "image": "data:image/png;base64," + PNG, "extension": "png"})
nouveaux = set(os.listdir(DOSSIER)) - avant
fichier = next(iter(nouveaux), "")
verifier("F. PNG valide (super-admin) → 200, UN fichier dans le dossier imposé",
         r.status_code == 200 and len(nouveaux) == 1 and (DOSSIER / fichier).is_file(), "%s %s" % (r.status_code, nouveaux))
verifier("F. nom choisi par le SERVEUR (uuid.png), jamais celui du client",
         len(fichier) == 36 and fichier.endswith(".png") and "Danse" not in fichier, fichier)
verifier("F. contenu écrit à l'identique", (DOSSIER / fichier).read_bytes() == base64.b64decode(PNG) if fichier else False)
r = faire("POST", "/api/custom-emojis/upload", J_SA, {"name": "gif", "image": GIF})
verifier("F. GIF valide → extension déduite des octets (.gif)", r.status_code == 200 and r.json()["emoji"]["filename"].endswith(".gif"), r.text[:120])

print("\nFONCTIONS PURES")
verifier("p0b_type_image : png/jpg/gif/webp reconnus, texte/svg refusés",
         S.p0b_type_image(base64.b64decode(PNG)) == "png" and S.p0b_type_image(b"\xff\xd8\xff\xe0") == "jpg"
         and S.p0b_type_image(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp" and S.p0b_type_image(b"<svg") == "" and S.p0b_type_image(b"") == "")
verifier("p0b_nom_sur : chemins refusés, noms simples acceptés",
         S.p0b_nom_sur("Danse joyeuse") and not S.p0b_nom_sur("../x") and not S.p0b_nom_sur("/etc") and not S.p0b_nom_sur("") and not S.p0b_nom_sur(None))

print("\nAUCUNE SORTIE RÉSEAU")
verifier("I. aucune tentative réseau", not _TENT, _TENT)
for f in DOSSIER.iterdir():
    f.unlink()
DOSSIER.rmdir()

ok = sum(R)
print("\nP0-B ROUTES PUBLIQUES — %d/%d vérifications (application réelle, base en mémoire, dossier temporaire)" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)

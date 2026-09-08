#!/usr/bin/env python3
"""
F3 FINAL (2/2) — L'ANNOTATION « PROFIL SOCIAL », VUE DU SERVEUR AFROBOOST.

Exécution : python3 tests/test_f3_social_links.py

CE QUE CE BANC PROUVE (§5, §6, §12)
  - drapeau SOCIAL_PROFILE_LINKS OFF -> annotation None (livré DORMANT) ;
  - lié -> {available:True, target:<jeton de vue OPAQUE>} ; le navigateur ne
    reçoit JAMAIS le uid — il est EMBALLÉ dans un jeton signé aud
    `spordate-profile-view` que seule la garde /u/ sait ouvrir ;
  - non lié -> {available:False} ; jamais de faux profil ;
  - pont injoignable -> échec FERMÉ (available:False), jamais un lien supposé ;
  - le jeton de résolution serveur->serveur porte l'audience dédiée et une
    expiration courte ; il n'ouvre ni session ni lecture de profil.

Aucun réseau réel : `_resoudre_liens_sociaux` et le drapeau sont bouchonnés.
"""
import asyncio
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-f3s:27017")
os.environ["AFRO_SPORDATE_SHARED_SECRET"] = "secret-pont-de-test-f3s"

import jwt as _pyjwt  # noqa: E402
import api.routes.spordate_routes as SP  # noqa: E402

_p = 0; _f = 0
def verifier(libelle, cond, detail=""):
    global _p, _f
    if cond: print("PASS  " + libelle); _p += 1
    else: print("FAIL  " + libelle + ("  — " + detail if detail else "")); _f += 1
def lancer(coro): return asyncio.get_event_loop().run_until_complete(coro)

SECRET = os.environ["AFRO_SPORDATE_SHARED_SECRET"]

# ── Bouchons : on contrôle le drapeau et la résolution serveur->serveur ──────
_flag = {"on": True}
async def _faux_flag(): return _flag["on"]
SP._social_links_actif = _faux_flag

_liens = {"lie@x.com": "UID999", "pas-lie@x.com": None}
async def _fausse_resolution(emails):
    return {(e or "").strip().lower(): _liens.get((e or "").strip().lower()) for e in emails}
SP._resoudre_liens_sociaux = _fausse_resolution


# ── 1. DRAPEAU OFF -> DORMANT ────────────────────────────────────────────────
_flag["on"] = False
verifier("flag OFF -> None (dormant)", lancer(SP.annoter_social_profile("lie@x.com")) is None)
_flag["on"] = True

# ── 2. LIÉ -> cible OPAQUE, jamais le uid en clair ──────────────────────────
res = lancer(SP.annoter_social_profile("lie@x.com"))
verifier("lié -> available True", res and res.get("available") is True, str(res))
target = (res or {}).get("target", "")
verifier("lié -> target présent (jeton)", isinstance(target, str) and target.count(".") == 2, target[:20])
verifier("lié -> le uid n'apparaît PAS en clair dans la réponse", "UID999" not in str(res).replace(target, ""))
# le jeton de vue est signé, aud dédiée, et EMBALLE le uid (déchiffrable seulement avec le secret)
charge = _pyjwt.decode(target, SECRET, algorithms=["HS256"], audience="spordate-profile-view")
verifier("jeton de vue: aud spordate-profile-view", charge.get("aud") == "spordate-profile-view")
verifier("jeton de vue: iss afroboost", charge.get("iss") == "afroboost")
verifier("jeton de vue: contient le uid cible", charge.get("uid") == "UID999")
verifier("jeton de vue: a une expiration", isinstance(charge.get("exp"), int) and charge.get("exp") > charge.get("iat"))

# ── 3. NON LIÉ -> available False, jamais de faux profil ────────────────────
res2 = lancer(SP.annoter_social_profile("pas-lie@x.com"))
verifier("non lié -> available False", res2 == {"available": False}, str(res2))

# ── 4. E-MAIL VIDE -> None (rien à annoter) ─────────────────────────────────
verifier("email vide -> None", lancer(SP.annoter_social_profile("")) is None)
verifier("email None -> None", lancer(SP.annoter_social_profile(None)) is None)

# ── 5. ÉCHEC FERMÉ : résolution qui renvoie non lié -> available False ───────
async def _resolution_vide(emails): return {}
SP._resoudre_liens_sociaux = _resolution_vide
verifier("résolution vide -> available False (échec fermé)",
         lancer(SP.annoter_social_profile("inconnu@x.com")) == {"available": False})
SP._resoudre_liens_sociaux = _fausse_resolution

# ── 6. LE JETON DE RÉSOLUTION SERVEUR : audience dédiée, courte vie ──────────
jr = SP._signer({"aud": SP.AUDIENCE_RESOLUTION}, SECRET, SP.DUREE_JETON_RESOLUTION_S)
cr = _pyjwt.decode(jr, SECRET, algorithms=["HS256"], audience=SP.AUDIENCE_RESOLUTION)
verifier("jeton résolution: aud spordate-link-resolve", cr.get("aud") == "spordate-link-resolve")
verifier("jeton résolution: NE porte PAS d'email", "email" not in cr)
verifier("jeton résolution: vie <= 60 s", (cr.get("exp") - cr.get("iat")) <= 60)
# séparation d'audience : un jeton de résolution n'est pas un jeton de vue
try:
    _pyjwt.decode(jr, SECRET, algorithms=["HS256"], audience="spordate-profile-view")
    verifier("audiences séparées (résolution != vue)", False, "un jeton de résolution a été accepté comme vue")
except Exception:
    verifier("audiences séparées (résolution != vue)", True)

# ── 7. GATING DU VIEWER SUR LA ROUTE PUBLIQUE (§5, §12-K) ───────────────────
# La route /users/{id}/profile est PUBLIQUE. Elle ne doit annoter QUE pour un
# viewer SIGNÉ. Anonyme -> aucun social_profile. X-User-Email seul -> AUCUNE
# autorité -> aucun social_profile. JWT coach signé -> annotation.
os.environ["JWT_SECRET"] = "secret-jwt-de-test-f3s"
import api.server as S  # noqa: E402

async def _impl_bouchon(pid):
    return {"success": True, "participant_id": pid, "name": "X", "email": "lie@x.com", "photo_url": "u"}
S._get_user_profile_impl = _impl_bouchon

class Req:
    def __init__(self, headers=None): self.headers = headers or {}

# anonyme
r_anon = lancer(S.get_user_profile("pid", Req()))
verifier("anonyme -> pas de social_profile (aucune fuite)", "social_profile" not in r_anon, str(r_anon.get("social_profile")))

# X-User-Email seul : falsifiable, aucune autorité
r_hdr = lancer(S.get_user_profile("pid", Req({"X-User-Email": "lie@x.com"})))
verifier("X-User-Email seul -> pas de social_profile", "social_profile" not in r_hdr)

# JWT coach signé -> annotation présente
_jwt_coach = _pyjwt.encode({"email": "coach@x.com"}, os.environ["JWT_SECRET"], algorithm="HS256")
if isinstance(_jwt_coach, bytes): _jwt_coach = _jwt_coach.decode()
r_jwt = lancer(S.get_user_profile("pid", Req({"Authorization": "Bearer " + _jwt_coach})))
verifier("JWT coach signé -> social_profile annoté", isinstance(r_jwt.get("social_profile"), dict), str(r_jwt.get("social_profile")))
verifier("JWT coach signé -> cible du profil affiché résolue (available True)",
         (r_jwt.get("social_profile") or {}).get("available") is True)


print(f"\n{_p} PASS · {_f} FAIL")
sys.exit(0 if _f == 0 else 1)

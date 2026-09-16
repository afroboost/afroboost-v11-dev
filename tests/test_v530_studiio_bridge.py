# V530 — banc du raccord Afroboost → Studiio (brouillons du Calendrier IA).
# Aucun réseau : httpx est remplacé ; les fonctions RÉELLES de server.py sont extraites par nom.
# Lancer : python3 tests/test_v530_studiio_bridge.py
import asyncio, json, os, re, sys, logging
from datetime import datetime, timezone, timedelta

SRC = open(os.path.join(os.path.dirname(__file__), "..", "api", "server.py"), encoding="utf-8").read()

def extraire(nom):
    m = re.search(r"^(?:async def|def) " + nom + r"\(.*?(?=^\S)", SRC, re.S | re.M)
    assert m, nom
    return m.group(0)

class HTTPException(Exception):
    def __init__(self, status_code, detail=""): self.status_code = status_code; self.detail = detail

esp = {"re": re, "os": os, "HTTPException": HTTPException, "logger": logging.getLogger("v530"),
       "datetime": datetime, "timezone": timezone}
exec(compile("STUDIIO_PLATEFORMES = ('instagram', 'facebook', 'tiktok', 'youtube')\nSTUDIIO_UTM_MEDIUM = 'social'", "<c>", "exec"), esp)
for fn in ("studiio_lien_utm", "studiio_construire_brouillons", "envoyer_a_studiio"):
    exec(compile(extraire(fn), "<" + fn + ">", "exec"), esp)

# --- faux httpx : enregistre les appels, ne sort jamais du processus ---
class FauxRep:
    def __init__(self, status, corps): self.status_code = status; self._c = corps; self.headers = {"content-type": "application/json"}
    def json(self): return self._c
class FauxClient:
    appels = []; reponses = {}
    def __init__(self, timeout=None): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, json=None, headers=None):
        FauxClient.appels.append({"url": url, "json": json, "headers": headers})
        cle = json["metadata"]["afroboost_key"]
        if cle in FauxClient.reponses: return FauxClient.reponses[cle]
        return FauxRep(200, {"success": True, "post": {"id": "st-" + cle[-12:], "status": "draft"}})
import types
faux_httpx = types.ModuleType("httpx"); faux_httpx.AsyncClient = FauxClient
sys.modules["httpx"] = faux_httpx

ok = 0; total = 0
def verifier(nom, cond, detail=""):
    global ok, total; total += 1
    if cond: ok += 1
    print(("  PASS  " if cond else "  FAIL  ") + nom + ("" if cond else "   -> " + str(detail)))

PLAN = [
    {"date": "2026-09-17", "heure": "18:00", "plateformes": ["instagram", "facebook"], "titre": "J1 — lancement",
     "caption": "La saison reprend. Découvre l'offre : {lien} #Afroboost"},
    {"date": "2026-09-19", "heure": "12:00", "plateformes": ["tiktok", "youtube", "snapchat"], "titre": "J3", "caption": "{lien}"},
    {"date": "pas-une-date", "heure": "12:00", "plateformes": ["instagram"], "titre": "invalide", "caption": "x"},
]
URL = "https://afroboost.com/?offre=cc73f6ee-163a-433d-b5f0-c00c6392b437"

print("\n[A] construction pure des brouillons")
b = esp["studiio_construire_brouillons"]("camp-1", "AFROBOOST — FONDATEURS SEPTEMBRE 2026", "https://cdn/x.mp4", URL, "fondateurs2026", PLAN)
verifier("A1. 4 brouillons (2 + 2 ; snapchat et date invalide écartés)", len(b) == 4, len(b))
verifier("A2. tous en draft", all(x["status"] == "draft" for x in b))
verifier("A3. une plateforme par brouillon", all(len(x["platforms"]) == 1 for x in b))
ig = [x for x in b if x["platforms"] == ["instagram"]][0]
verifier("A4. lien UTM instagram dans la légende", "utm_source=instagram&utm_medium=social&utm_campaign=fondateurs2026" in ig["caption"] and "{lien}" not in ig["caption"])
verifier("A5. clé idempotente campagne|date|plateforme", ig["metadata"]["afroboost_key"] == "camp-1|2026-09-17|instagram")
verifier("A6. source afroboost + media_url + titre", ig["metadata"]["source"] == "afroboost" and ig["media_url"] == "https://cdn/x.mp4" and ig["title"] == "J1 — lancement")
verifier("A7. utm_content optionnel absent → pas de clé vide", "utm_content" not in ig["caption"])

print("\n[B] envoi : variables absentes → 503, aucun appel")
for k in ("STUDIIO_URL", "STUDIIO_SERVICE_TOKEN"): os.environ.pop(k, None)
try:
    asyncio.run(esp["envoyer_a_studiio"]("camp-1", "c", "https://cdn/x.mp4", URL, "fondateurs2026", PLAN)); verifier("B1. 503 sans configuration", False)
except HTTPException as e:
    verifier("B1. 503 sans configuration", e.status_code == 503, e.status_code)
verifier("B2. aucun appel réseau", len(FauxClient.appels) == 0)

print("\n[C] envoi configuré (valeurs factices, process de test seulement)")
os.environ["STUDIIO_URL"] = "https://studiio.test/"; os.environ["STUDIIO_SERVICE_TOKEN"] = "jeton-factice-de-test"
FauxClient.appels.clear()
bilan = asyncio.run(esp["envoyer_a_studiio"]("camp-1", "AFROBOOST — FONDATEURS", "https://cdn/x.mp4", URL, "fondateurs2026", PLAN))
verifier("C1. 4 POST vers {STUDIIO_URL}/api/posts", len(FauxClient.appels) == 4 and all(a["url"] == "https://studiio.test/api/posts" for a in FauxClient.appels), [a["url"] for a in FauxClient.appels][:1])
verifier("C2. Authorization: Bearer <jeton> sur chaque appel", all(a["headers"]["Authorization"] == "Bearer jeton-factice-de-test" for a in FauxClient.appels))
verifier("C3. statut draft envoyé partout", all(a["json"]["status"] == "draft" for a in FauxClient.appels))
verifier("C4. bilan : 4 ok, ids studiio présents", bilan["ok"] == 4 and all(l["studiio_id"] for l in bilan["lignes"]), bilan)
verifier("C5. le jeton n'apparaît pas dans le bilan", "jeton-factice" not in json.dumps(bilan))

print("\n[D] idempotence : Studiio renvoie deja_present → compté ok, pas d'erreur")
FauxClient.appels.clear(); FauxClient.reponses = {"camp-1|2026-09-17|instagram": FauxRep(200, {"success": True, "post": {"id": "st-old", "status": "draft"}, "deja_present": True})}
bilan = asyncio.run(esp["envoyer_a_studiio"]("camp-1", "c", "https://cdn/x.mp4", URL, "fondateurs2026", PLAN[:1]))
verifier("D1. 2 appels (instagram + facebook), 2 ok", bilan["ok"] == 2 and len(FauxClient.appels) == 2, bilan)
verifier("D2. instagram marqué deja_present", any(l["deja_present"] for l in bilan["lignes"] if l["plateforme"] == "instagram"))

print("\n[E] Studiio refuse (401) → ligne ok=False, pas d'exception")
FauxClient.appels.clear(); FauxClient.reponses = {"camp-1|2026-09-17|instagram": FauxRep(401, {"success": False, "error": "Unauthorized"})}
bilan = asyncio.run(esp["envoyer_a_studiio"]("camp-1", "c", "https://cdn/x.mp4", URL, "fondateurs2026", PLAN[:1]))
verifier("E1. 1 ok (facebook) / 1 refus (instagram), http 401 consigné", bilan["ok"] == 1 and any(l["http"] == 401 and not l["ok"] for l in bilan["lignes"]), bilan)

print("\n[F] la route ne parle jamais de publication")
route = extraire("v530_envoyer_campagne_a_studiio")
verifier("F1. garde JWT coach/admin + propriété", "_v309_require_coach_or_admin" in route and "is_super_admin" in route)
verifier("F2. media_url https requis", "startswith(\"https://\")" in route)
verifier("F3. aucun appel de publication (launch/publish) dans le raccord", "launch_campaign" not in route and "publish" not in route.lower())
print(f"\n{ok}/{total} verifications — 0 reseau, 0 secret")
sys.exit(0 if ok == total else 1)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V613 — temps de trajet routier automatique (OpenStreetMap : Nominatim + OSRM), avec cache.

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v613_trajet_auto.py

Le réseau est SIMULÉ (aucun appel réel), la base aussi. Aucun appel IA, aucun e-mail.
"""
import asyncio, os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v613"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v613:27017")
import api.server as S  # noqa: E402
R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

# --- réseau simulé : durées mesurées le 12/10/2026 (OSRM, voiture) ---
DUREES = {"besancon": (103, 103), "lyon": (190, 272), "bienne": (30, 32), "zurich": (120, 152), "mulhouse": (129, 158)}
APPELS = []
def reseau(panne=False, introuvable=False, osrm_ko=False):
    async def get_json(url):
        APPELS.append(url)
        if panne:
            raise ConnectionError("service indisponible")
        if "nominatim" in url:
            if introuvable:
                return []
            q = S.p3ai_sans_accents(url.split("q=")[1].split("&")[0].replace("%C3%A7", "c").replace("%C3%BC", "u")).lower()
            for v in DUREES:
                if v in q:
                    return [{"lat": "47.0", "lon": "6.0", "display_name": v.title()}]
            return []
        if osrm_ko:
            raise TimeoutError("osrm")
        for v, (m, km) in DUREES.items():
            if DERNIERE[0] == v:
                return {"code": "Ok", "routes": [{"duration": m * 60, "distance": km * 1000}]}
        return {"code": "NoRoute", "routes": []}
    return get_json
DERNIERE = [""]
class Col:
    def __init__(s): s.docs = {}
    async def find_one(s, q): return s.docs.get(q["_id"])
    async def update_one(s, q, u, upsert=False): s.docs[q["_id"]] = dict(u["$set"], _id=q["_id"])
class Base(dict):
    def __missing__(s, k): s[k] = Col(); return s[k]
def trajet(ville, **k):
    DERNIERE[0] = S.p3ai_sans_accents(ville).lower()
    return asyncio.run(S.v613_trajet_auto(ville, get_json=reseau(**{x: k.pop(x) for x in list(k) if x in ("panne", "introuvable", "osrm_ko")}),
                                          base=k.pop("base", Base()), **k))
def verdict(texte, ville, auto):
    c = S.p3ai_contexte({"id": "i", "body_text": texte}, {"id": "a"}, [{"city": ville}], [], "")
    c["fil"] = []; c["trajet_auto"] = auto
    c["contexte_commercial"] = S.v611_contexte_commercial(c, [{"city": ville}])
    ag = c["contexte_commercial"]["agenda"]
    return ag, (ag["creneaux"][0] if ag["creneaux"] else {}), c

print("\nA. Ville à moins de 2 h (Besançon, 103 min) → compatible le matin")
t = trajet("Besançon")
verifier("trajet routier mesuré : 103 min, 103 km, source OpenStreetMap / OSRM", t["statut"] == "ok" and t["minutes"] == 103 and t["km"] == 103 and "OSRM" in t["source"], t)
ag, cr, _ = verdict("Mercredi 9h chez nous ?", "Besançon", t)
verifier("mercredi 9h → compatible", ag["trajet_ok"] == "OUI" and cr["compatible"] == "OUI", ag)

print("\nB. Ville à plus de 2 h (Lyon, 190 min) → incompatible")
t = trajet("Lyon")
ag, cr, _ = verdict("Un mercredi matin ?", "Lyon", t)
verifier("190 min > 120 → trajet NON → incompatible", t["minutes"] == 190 and ag["trajet_ok"] == "NON" and cr["compatible"] == "NON", ag)

print("\nC. Service indisponible → À VÉRIFIER (rien d'inventé)")
t = trajet("Besançon", panne=True)
verifier("panne → statut indisponible, aucune durée", t["statut"] == "indisponible" and t["minutes"] is None, t)
ag, cr, _ = verdict("Dimanche matin ?", "Besançon", t)
verifier("créneau à vérifier", ag["trajet_ok"] == "A VERIFIER" and cr["compatible"] == "A VERIFIER", ag)
t = trajet("Besançon", osrm_ko=True)
verifier("géocodage OK mais itinéraire en panne (2 instances) → indisponible", t["statut"] == "indisponible" and t["minutes"] is None, t)

print("\nD. Ville inconnue → À VÉRIFIER")
t = trajet("Villeinexistante", introuvable=True)
verifier("ville introuvable → aucune durée", t["statut"] == "introuvable" and t["minutes"] is None, t)
verifier("ville vide → inconnu, aucun appel", asyncio.run(S.v613_trajet_auto("", get_json=reseau(), base=Base()))["statut"] == "inconnu")
ag, cr, _ = verdict("Dimanche à 10h ?", "Villeinexistante", t)
verifier("créneau à vérifier", cr["compatible"] == "A VERIFIER", cr)

print("\nE. Mercredi après-midi → refus même si trajet < 2 h")
t = trajet("Bienne")
ag, cr, _ = verdict("Mercredi à 15h ?", "Bienne", t)
verifier("30 min de trajet mais 15h → incompatible", ag["trajet_ok"] == "OUI" and cr["avant_midi"] == "NON" and cr["compatible"] == "NON", cr)

print("\nF. Dimanche matin + trajet < 2 h → possible")
ag, cr, _ = verdict("Dimanche matin au bord du lac ?", "Bienne", trajet("Bienne"))
verifier("dimanche matin, Bienne 30 min → compatible", cr["compatible"] == "OUI", cr)

print("\nG. Autres jours → aucune restriction ajoutée, aucun appel externe")
APPELS.clear()
c = S.p3ai_contexte({"id": "i", "body_text": "Jeudi à 16h ?"}, {"id": "a"}, [{"city": "Lyon"}], [], "")
verifier("jeudi : le trajet n'est même pas calculé (aucun appel)", S.v613_trajet_utile(c, [{"city": "Lyon"}], "Lyon") is False and APPELS == [])
ag, cr, _ = verdict("Jeudi à 16h ?", "Lyon", trajet("Lyon"))
verifier("jeudi 16h à Lyon (190 min) → compatible (pas de règle ce jour-là)", cr["compatible"] == "OUI", cr)
c = S.p3ai_contexte({"id": "i", "body_text": "Mercredi matin ?"}, {"id": "a"}, [{"city": "Peseux"}], [], "")
verifier("canton de Neuchâtel → aucun appel (local)", S.v613_trajet_utile(c, [{"city": "Peseux"}], "Peseux") is False)
verifier("durée posée sur la fiche → prioritaire, aucun appel", S.v613_trajet_utile(
    S.p3ai_contexte({"id": "i", "body_text": "Mercredi matin ?"}, {"id": "a"}, [], [], ""), [{"city": "Lyon", "trajet_depuis_neuchatel_min": 100}], "Lyon") is False)

print("\nH. Aucun temps inventé + zone d'incertitude + cache")
t = trajet("Zürich")
ag, cr, _ = verdict("Sonntag Vormittag?", "Zürich", t)
verifier("Zurich 120 min (sans trafic) → zone ±10 % → À VÉRIFIER, pas « possible »", t["incertain"] and ag["trajet_ok"] == "A VERIFIER" and cr["compatible"] == "A VERIFIER", (t, ag))
verifier("Mulhouse 129 min → À VÉRIFIER (jamais tranché dans la zone grise)", trajet("Mulhouse")["incertain"])
base = Base(); APPELS.clear()
r1 = trajet("Besançon", base=base); n1 = len(APPELS)
r2 = trajet("Besançon", base=base); n2 = len(APPELS)
verifier("2e demande servie par le CACHE, sans nouvel appel", r2.get("depuis_cache") and n2 == n1 and r2["minutes"] == r1["minutes"], (n1, n2))
r3 = trajet("Besançon", base=base, forcer=True)
verifier("mise à jour possible (forcer) → nouvel appel", len(APPELS) > n2 and not r3.get("depuis_cache"))
base_exp = Base(); trajet("Besançon", base=base_exp); APPELS.clear()
trajet("Besançon", base=base_exp, maintenant=datetime.now(timezone.utc) + timedelta(days=200))
verifier("cache expiré (> 180 j) → recalcul", len(APPELS) > 0)
base_panne = Base(); trajet("Besançon", base=base_panne, panne=True)
verifier("une panne n'est JAMAIS mise en cache (on réessaiera)", not base_panne[S.V613_CACHE].docs)
import inspect
src = inspect.getsource(S.v613_calculer) + inspect.getsource(S.v613_trajet_auto)
verifier("aucune clé API, aucun service payant dans le code", not any(k in src for k in ("api_key", "apikey", "googleapis", "mapbox", "Bearer")))
verifier("la seule durée possible vient d'une réponse d'itinéraire (`duration`)", "route[0][\"duration\"]" in src)

ok = sum(R); print("\n%d/%d vérifications réussies (réseau simulé, aucun appel externe, aucun e-mail)" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)

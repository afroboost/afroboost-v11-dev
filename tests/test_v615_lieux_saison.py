#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V615 — lieu officiel des cours d'hiver, bascule saisonnière des lieux d'offres et des cours d'été.

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v615_lieux_saison.py

Base simulée : aucune base réelle, aucun e-mail.
"""
import asyncio, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v615"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v615:27017")
import api.server as S  # noqa: E402
R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

class Cur:
    def __init__(s, d): s.d = d
    async def to_list(s, n): return [dict(x) for x in s.d][:n]
class Col:
    def __init__(s, docs): s.docs = docs
    def _ok(s, d, q):
        for k, v in q.items():
            if "." in k:
                a, b = k.split(".", 1); val = (d.get(a) or {}).get(b, "__absent__")
                if isinstance(v, dict) and "$exists" in v:
                    if (val != "__absent__") != v["$exists"]: return False
                continue
            if isinstance(v, dict) and "$in" in v:
                if d.get(k) not in v["$in"]: return False
            elif isinstance(v, dict) and "$ne" in v:
                if d.get(k) == v["$ne"]: return False
            elif d.get(k) != v: return False
        return True
    def find(s, q, p=None): return Cur([d for d in s.docs if s._ok(d, q)])
    async def update_one(s, q, u):
        n = 0
        for d in s.docs:
            if s._ok(d, q):
                avant = dict(d); d.update(u["$set"]); n = int(avant != d); break
        return type("R", (), {"modified_count": n})()
class Base:
    def __init__(s, offers, courses): s.offers, s.courses = Col(offers), Col(courses)

ETE = {"location": "Bord du Lac, Auvernier, Neuchâtel", "location_address": "Bord du Lac, Auvernier, Neuchâtel", "location_city": "Auvernier"}
HIVER = {"location": S.V615_ADRESSE_COURS, "location_address": S.V615_ADRESSE_COURS, "location_city": "Neuchâtel"}
def base():
    return Base(
        [dict(ETE, id="o1", name="Cours à l'unité", price=30.0, lieux_saison={"hiver": HIVER, "ete": ETE}),
         dict(location="", location_address="Bord du Lac, Auvernier, Neuchâtel", location_city="Auvernier", id="o2", name="Flex 4", price=49.0,
              lieux_saison={"hiver": dict(HIVER, location=""), "ete": dict(ETE, location="")}),
         {"id": "o3", "name": "T-shirt", "price": 59.99, "location": "Ailleurs"}],                    # sans lieux_saison
        [{"id": "c-ete-mer", "name": "Afroboost Silent", "saison": "ete", "visible": True, "locationName": "Bord du Lac, Auvernier, Neuchâtel"},
         {"id": "c-ete-dim", "name": "Afroboost Silent", "saison": "ete", "visible": True, "locationName": "Bord du Lac, Auvernier, Neuchâtel"},
         {"id": "c-hiver", "name": "Cours à l'unité", "visible": True, "weekday": 3, "time": "18:45", "locationName": S.V615_ADRESSE_COURS},  # sans étiquette
         {"id": "c-arch", "name": "ancien", "saison": "ete", "visible": True, "archived": True}])

print("\nA. Passage en HIVER")
b = base(); r = asyncio.run(S.v615_appliquer_saison("hiver", b))
o1, o2, o3 = b.offers.docs
verifier("offres : plus aucun « Bord du Lac, Auvernier »", all("Auvernier" not in str({k: o.get(k) for k in S.V615_CHAMPS_LIEU}) for o in (o1, o2)), (o1, o2))
verifier("lieu affiché = Chemin des Valangines 97, 2000 Neuchâtel (location ou location_address)",
         (o1["location"] or o1["location_address"]) == S.V615_ADRESSE_COURS and (o2["location"] or o2["location_address"]) == S.V615_ADRESSE_COURS)
verifier("la ville reste renseignée (Neuchâtel) — « Où pratiquer ? » intact", o1["location_city"] == "Neuchâtel" and o2["location_city"] == "Neuchâtel")
verifier("prix strictement identiques", (o1["price"], o2["price"], o3["price"]) == (30.0, 49.0, 59.99))
verifier("offre sans `lieux_saison` jamais touchée", o3["location"] == "Ailleurs")
cs = {c["id"]: c for c in b.courses.docs}
verifier("cours d'été masqués (non supprimés)", cs["c-ete-mer"]["visible"] is False and cs["c-ete-dim"]["visible"] is False and len(b.courses.docs) == 4)
verifier("cours d'hiver non étiqueté : intact (mercredi 18h45, Valangines, visible)", cs["c-hiver"]["visible"] is True and cs["c-hiver"]["time"] == "18:45")
verifier("cours archivé jamais touché", cs["c-arch"]["visible"] is True)
verifier("bilan : 2 offres, 2 cours masqués", r["offres"] == 2 and r["cours_masques"] == 2, r)

print("\nB. Retour en ÉTÉ (automatique) puis à nouveau HIVER")
r = asyncio.run(S.v615_appliquer_saison("ete", b))
verifier("été : Auvernier revient sur les offres, cours d'été réaffichés",
         o1["location"] == ETE["location"] and o2["location_address"] == ETE["location_address"] and cs["c-ete-mer"]["visible"] is True, (o1, r))
asyncio.run(S.v615_appliquer_saison("hiver", b))
verifier("hiver de nouveau : Valangines, cours d'été masqués", o1["location"] == S.V615_ADRESSE_COURS and cs["c-ete-dim"]["visible"] is False)
r = asyncio.run(S.v615_appliquer_saison("n'importe quoi", b))
verifier("saison inconnue → rien n'est modifié", r["offres"] == 0 and r["cours_masques"] == 0 and r["cours_affiches"] == 0)

print("\nC. Textes : réponses rapides, chat, amorçage")
qr = {x["id"]: x["response"] for x in S.V197B_DEFAULT_QUICK_REPLIES}
verifier("réponse « Cours & horaires » : mercredi 18h45 + dimanche 18h30 + Chemin des Valangines 97",
         "Mercredi à 18h45" in qr["cours_horaires"] and "Dimanche à 18h30" in qr["cours_horaires"]
         and qr["cours_horaires"].count("Chemin des Valangines 97, 2000 Neuchâtel") == 2 and "Mercredi à 18h30" not in qr["cours_horaires"])
verifier("réponse « Contact » : Chemin des Valangines 97", "Chemin des Valangines 97, 2000 Neuchâtel" in qr["contact"])
racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cw = open(os.path.join(racine, "frontend/src/components/ChatWidget.js"), encoding="utf-8").read()
srv = open(os.path.join(racine, "api/server.py"), encoding="utf-8").read()
verifier("plus aucune « Vallangines » dans le chat ni le serveur", "Vallangines" not in cw and "Vallangines" not in srv)
verifier("le chat (repli) dit mercredi 18h45 et Chemin des Valangines 97",
         "Mercredi à 18h45\\nChemin des Valangines 97, 2000 Neuchâtel" in cw and "Mercredi à 18h30" not in cw)
verifier("ChatWidget reste ES5 dans les lignes modifiées (aucune flèche ni template)",
         not re.search(r"Valangines[^\n]*(=>|`)", cw))
verifier("cours d'amorçage : mercredi 18:45 / dimanche 18:30 au Chemin des Valangines 97",
         '"weekday": 3, "time": "18:45", "locationName": V615_ADRESSE_COURS' in srv and '"weekday": 0, "time": "18:30", "locationName": V615_ADRESSE_COURS' in srv)
verifier("la bascule est branchée au changement de saison", "await v615_appliquer_saison(update_fields[\"saison_active\"])" in srv)

ok = sum(R); print("\n%d/%d vérifications réussies (base simulée, aucun e-mail)" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)

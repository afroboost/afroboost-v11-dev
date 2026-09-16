"""V533 — miniature du Reel sur la campagne : le modèle, la création et la liste
blanche du PUT portent les 3 champs ; aucun autre champ n'est retiré ; aucune
écriture réseau. Pur : lecture du source + instanciation des modèles Pydantic."""
import re, sys, os
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ok = 0; ko = 0
def verifier(nom, cond, detail=""):
    global ok, ko
    if cond: ok += 1; print("  PASS ", nom)
    else: ko += 1; print("  FAIL ", nom, "->", detail)

def bloc(nom_classe):
    m = re.search(r"^class " + nom_classe + r"\(BaseModel\):.*?(?=^class )", SRC, re.S | re.M)
    return m.group(0) if m else ""

for cls in ("Campaign", "CampaignCreate"):
    b = bloc(cls)
    verifier(f"{cls}.thumbnail_url", "thumbnail_url: Optional[str]" in b)
    verifier(f"{cls}.thumbnail_source", "thumbnail_source: Optional[str]" in b)
    verifier(f"{cls}.thumbnail_time", "thumbnail_time: Optional[float]" in b)
    verifier(f"{cls} garde mediaUrl / mediaFormat / mediaType", all(k in b for k in ("mediaUrl", "mediaFormat", "mediaType")))

m = re.search(r"allowed_fields = \[(.*?)\]", SRC, re.S)
lw = m.group(1) if m else ""
for champ in ("thumbnail_url", "thumbnail_source", "thumbnail_time", "mediaUrl", "mediaFormat", "mediaType", "name", "message", "scheduledAt", "targetCategories"):
    verifier(f"PUT liste blanche contient {champ}", f'"{champ}"' in lw)

verifier("create_campaign recopie thumbnail_url", "thumbnail_url=campaign.thumbnail_url" in SRC)
verifier("create_campaign recopie thumbnail_source", "thumbnail_source=campaign.thumbnail_source" in SRC)
verifier("create_campaign recopie thumbnail_time", "thumbnail_time=campaign.thumbnail_time" in SRC)

# Instanciation réelle des modèles (Pydantic) sans importer server.py entier
try:
    from pydantic import BaseModel, Field, ConfigDict
    from typing import Optional, List
    esp = {"BaseModel": BaseModel, "Field": Field, "ConfigDict": ConfigDict, "Optional": Optional, "List": List, "uuid": __import__("uuid"), "datetime": __import__("datetime").datetime, "timezone": __import__("datetime").timezone}
    exec(bloc("CampaignCreate"), esp)
    c = esp["CampaignCreate"](name="t", message="m", thumbnail_url="/api/files/x/min.jpg", thumbnail_source="video_frame", thumbnail_time=5.2)
    verifier("CampaignCreate accepte les 3 champs", c.thumbnail_url.endswith("min.jpg") and c.thumbnail_source == "video_frame" and c.thumbnail_time == 5.2)
    c2 = esp["CampaignCreate"](name="t", message="m")
    verifier("CampaignCreate sans miniature = valeurs vides (anciennes campagnes intactes)", c2.thumbnail_url == "" and c2.thumbnail_source is None and c2.thumbnail_time is None)
except Exception as e:  # noqa: BLE001
    verifier("instanciation Pydantic", False, repr(e))

print(f"\n{ok}/{ok + ko} au vert — V533 miniature campagne (0 réseau, 0 écriture)")
sys.exit(1 if ko else 0)

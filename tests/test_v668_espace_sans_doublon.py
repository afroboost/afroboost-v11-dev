# -*- coding: utf-8 -*-
"""V668 — L'ESPACE MEMBRE AFFICHAIT CHAQUE SÉANCE DEUX FOIS.

CE QUI A ÉTÉ REPRODUIT (11/11/2026). La capture d'écran montrait les mêmes
dates en double. Cause exacte, trouvée dans le code :

  `GET /sessions/agenda` applique le groupement V647 — vérifié EN PRODUCTION :
      36 occurrences servies, 36 portant `seance_physique`,
      une seule `seance_principale: true` par paire.
  L'ESPACE MEMBRE, lui, n'utilise pas cette route. Il construit ses propres
  occurrences fiche par fiche et ne regroupait RIEN : `seance_physique` n'était
  posé QUE dans `/sessions/agenda` (server.py, une seule occurrence du champ).

Le membre voyait donc, pour chaque date :
      mercredi 18:45 — Afroboost Silent – Session Cardio
      mercredi 18:45 — Cours à l'unité

Ce banc sème les quatre fiches RÉELLES dans une base locale, puis fait passer
la liste par la fonction de la route.
"""
import asyncio, io, os, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ["DB_NAME"] = "test_v668_espace"
os.environ["JWT_SECRET"] = "banc-v668"

_ok = _ko = 0


def v(nom, cond, detail=""):
    global _ok, _ko
    if cond:
        _ok += 1
        print("  PASS  %s" % nom)
    else:
        _ko += 1
        print("  RATE  %s  -> %s" % (nom, str(detail)[:170]))


import api.server as S                                             # noqa: E402

COACH = "contact.artboost@gmail.com"
VAL = "Chemin des Valangines 97, 2000 Neuchâtel"
# L'adresse est écrite DIFFÉREMMENT sur les deux fiches, comme en production.
FICHES = [
    {"id": "f-mer", "name": "Afroboost Silent – Session Cardio", "coach_id": COACH,
     "weekday": 3, "time": "18:45", "locationName": "Chem. des Valangines 97, 2000 Neuchâtel",
     "agenda_abonne": True, "archived": True, "visible": True},
    {"id": "p-mer", "name": "Cours à l'unité", "coach_id": COACH, "weekday": 3,
     "time": "18:45", "locationName": VAL, "archived": False, "visible": True},
    {"id": "f-dim", "name": "Afroboost Silent – Sunday Vibes", "coach_id": COACH,
     "weekday": 0, "time": "18:30", "locationName": "Chem. des Valangines 97, 2000 Neuchâtel",
     "agenda_abonne": True, "archived": True, "visible": True},
    {"id": "p-dim", "name": "Cours à l'unité", "coach_id": COACH, "weekday": 0,
     "time": "18:30", "locationName": VAL, "archived": False, "visible": True},
]


async def principal():
    db = S.db
    await db.courses.delete_many({})
    await db.offers.delete_many({})
    await db.courses.insert_many([dict(f) for f in FICHES])
    await db.offers.insert_one({"id": "o-unite", "name": "Cours à l'unité", "visible": True,
                                "coach_id": COACH,
                                "linked_course_ids": ["f-mer", "p-mer", "f-dim", "p-dim"]})

    # La liste TELLE QUE la route la construisait : une occurrence par fiche.
    brut = [
        {"course_id": "f-mer", "name": "Afroboost Silent – Session Cardio",
         "datetime": "2026-11-18T18:45:00"},
        {"course_id": "p-mer", "name": "Cours à l'unité", "datetime": "2026-11-18T18:45:00"},
        {"course_id": "f-dim", "name": "Afroboost Silent – Sunday Vibes",
         "datetime": "2026-11-22T18:30:00"},
        {"course_id": "p-dim", "name": "Cours à l'unité", "datetime": "2026-11-22T18:30:00"},
        {"course_id": "f-mer", "name": "Afroboost Silent – Session Cardio",
         "datetime": "2026-11-25T18:45:00"},
        {"course_id": "p-mer", "name": "Cours à l'unité", "datetime": "2026-11-25T18:45:00"},
    ]
    print("== AVANT : ce que le membre recevait ==")
    for o in brut:
        print("   %-34s %s" % (o["name"][:34], o["datetime"][:16]))

    sortie = await S._v668_regrouper_occurrences(brut)
    print()
    print("== APRÈS : une seule carte par séance physique ==")
    for o in sortie:
        print("   %-34s %s  ids=%s" % (str(o.get("name"))[:34], str(o.get("datetime"))[:16],
                                       o.get("ids")))
    print()

    v("6 occurrences deviennent 3", len(sortie) == 3, len(sortie))
    _dates = [str(o.get("datetime"))[:16] for o in sortie]
    v("aucune date n'apparaît deux fois", len(_dates) == len(set(_dates)), _dates)
    # Le nom gardé est celui de la fiche FORFAIT — le même que sur la vitrine.
    v("le nom gardé est celui de la vitrine (fiche forfait)",
      all("Silent" in str(o.get("name")) for o in sortie), [o.get("name") for o in sortie])
    v("le bon jour et la bonne heure sont conservés",
      sorted(_dates) == ["2026-11-18T18:45", "2026-11-22T18:30", "2026-11-25T18:45"], _dates)
    # LES DEUX FICHES RESTENT EXPOSÉES : c'est ce qui permet le comptage commun
    # des participants et des places.
    v("les deux fiches sont exposées pour le comptage commun",
      all(len(o.get("ids") or []) == 2 for o in sortie), [o.get("ids") for o in sortie])
    v("mercredi et dimanche restent DEUX séances distinctes",
      len({o.get("seance_physique") for o in sortie}) == 2,
      [o.get("seance_physique") for o in sortie])

    print("== CE QUI NE DOIT PAS ÊTRE TOUCHÉ ==")
    # Un cours seul, hors de tout groupe, passe tel quel.
    _seul = [{"course_id": "autre", "name": "Afroboost Live", "datetime": "2026-11-20T19:00:00"}]
    _s2 = await S._v668_regrouper_occurrences(_seul)
    v("un cours hors groupe traverse sans modification", _s2 == _seul, _s2)
    v("une liste vide ne casse rien", await S._v668_regrouper_occurrences([]) == [])
    # Sans offre, aucun groupe : la liste repart intacte plutôt qu'amputée.
    await db.offers.delete_many({})
    _s3 = await S._v668_regrouper_occurrences(brut)
    v("sans groupe calculable, AUCUNE occurrence n'est perdue", len(_s3) == len(brut), len(_s3))

    await db.courses.delete_many({})


asyncio.get_event_loop().run_until_complete(principal())

print()
print("== LA ROUTE APPLIQUE BIEN CETTE RÈGLE ==")
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
v("la route de l'espace appelle le regroupement",
  "occurrences = await _v668_regrouper_occurrences(occurrences)" in SRC)
v("il réutilise le groupement EXISTANT (pas un second mécanisme)",
  "v647_groupes_depuis_base" in SRC.split("async def _v668_regrouper_occurrences")[1][:1800])
v("et il est posé APRÈS la construction des occurrences",
  SRC.index("_v184_next_occurrences(course, days_ahead=14)")
  < SRC.index("occurrences = await _v668_regrouper_occurrences(occurrences)"))

print()
print("  %d/%d" % (_ok, _ok + _ko))
sys.exit(0 if _ko == 0 else 1)

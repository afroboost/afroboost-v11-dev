# -*- coding: utf-8 -*-
"""V665 — « Afroboost » : un seul créneau, le bon nom, aucune réservation perdue.

ÉTAT MESURÉ (11/11/2026). Le mercredi 18:45 et le dimanche 18:30 existent
CHACUN en deux fiches, au même lieu, avec le même coach — et les DEUX reçoivent
encore des réservations :

  mercredi 18:45  « Afroboost Silent – Session Cardio »  71 résa  ARCHIVÉE
                  « Cours à l'unité »                    13 résa  active
  dimanche 18:30  « Afroboost Silent – Sunday Vibes »    55 résa  ARCHIVÉE
                  « Cours à l'unité »                    12 résa  active

La fiche ARCHIVÉE est la principale : 71 réservations, dont une créée le
11/11/2026 — plus récente que la dernière de la fiche active (10/11). Elle est
archivée mais toujours utilisée.

CE QUE FAIT CETTE MIGRATION
  1. les deux fiches principales -> nom « Afroboost » + description sans casque,
     et DÉSARCHIVÉES pour redevenir le créneau servi ;
  2. les deux doublons -> ARCHIVÉS (jamais supprimés : leurs 25 réservations
     restent intactes et consultables) ;
  3. rien d'autre. Aucun identifiant changé, aucune réservation déplacée,
     aucune capacité ni offre touchée.

CE QU'ELLE NE TOUCHE SURTOUT PAS : les événements réellement organisés AVEC
casques (« SILENT Afroboost », « SILENT AFROBOOST », « Laff Festival-Afroboost
silent », « Silent Dance & Fitness », « AFROBOOST SILENT — ÉDITION SPÉCIALE »).
Ils sont nommés un par un en liste NOIRE de sécurité : si l'un d'eux apparaît
parmi les cibles, la migration s'arrête.

Usage :  python migration_v665_afroboost.py            (simulation)
         python migration_v665_afroboost.py --appliquer (écrit, après sauvegarde)
         python migration_v665_afroboost.py --rollback <fichier.json>
"""
import json
import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

NOUVEAU_NOM = "Afroboost"
DESCRIPTION = ("Cours collectif de cardio-danse afrobeat, sans casque audio, "
               "accessible à tous les niveaux.")

# Les fiches PRINCIPALES : on les renomme et on les remet en service.
PRINCIPALES = {
    "64b4c975-f507-447b-a44d-4623349fd24b": "mercredi 18:45 (71 réservations)",
    "23534f7c-938f-41ff-872b-d62a5314a5d6": "dimanche 18:30 (55 réservations)",
}
# Les DOUBLONS : on les archive, on ne supprime rien.
DOUBLONS = {
    "62fcac27-75ad-4429-bfb1-aee613858bdc": "mercredi 18:45 (13 réservations)",
    "01f3b303-1f64-48de-81f0-7c71dbbcb3b6": "dimanche 18:30 (12 réservations)",
}

# GARDE-FOU : aucun de ces noms ne doit se trouver parmi les cibles.
INTERDITS = ("silent afroboost", "laff festival", "silent dance",
             "edition speciale", "édition spéciale")

REP = os.path.dirname(os.path.abspath(__file__))


_VOIES = {"chem": "chemin", "av": "avenue", "bd": "boulevard", "blvd": "boulevard",
          "rte": "route", "pl": "place", "r": "rue", "imp": "impasse",
          "sq": "square", "all": "allee", "qu": "quai", "fbg": "faubourg"}


def norm(v):
    """Même normalisation que la garde serveur V664b. « Chem. » = « Chemin »."""
    import re
    t = re.sub(r"[^a-z0-9]+", " ",
               str(v or "").lower().translate(
                   str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc"))).strip()
    return " ".join(_VOIES.get(m, m) for m in t.split())


def main():
    appliquer = "--appliquer" in sys.argv
    db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)[os.environ["DB_NAME"]]

    cibles = list(PRINCIPALES) + list(DOUBLONS)
    docs = {d["id"]: d for d in db.courses.find({"id": {"$in": cibles}}, {"_id": 0})}

    print("=" * 74)
    print("V665 — %s" % ("APPLICATION" if appliquer else "SIMULATION (rien n'est écrit)"))
    print("=" * 74)

    if len(docs) != len(cibles):
        print("ARRÊT : %d fiches attendues, %d trouvées." % (len(cibles), len(docs)))
        print("  manquantes :", [i for i in cibles if i not in docs])
        return 1

    # GARDE-FOU 1 : aucun événement à casques parmi les cibles.
    for i, d in docs.items():
        n = norm(d.get("name"))
        for mot in INTERDITS:
            if mot in n:
                print("ARRÊT : « %s » ressemble à un événement AVEC casques." % d.get("name"))
                return 1

    # GARDE-FOU 2 : les quatre fiches doivent bien être deux paires au même
    # créneau, même lieu, même coach. Sinon on ne touche à rien.
    def cle(d):
        return (norm(d.get("coach_id")), str(d.get("time") or ""),
                norm(d.get("locationName") or d.get("location")), str(d.get("weekday")))
    for p, dd in ((list(PRINCIPALES)[0], list(DOUBLONS)[0]),
                  (list(PRINCIPALES)[1], list(DOUBLONS)[1])):
        if cle(docs[p]) != cle(docs[dd]):
            print("ARRÊT : ces deux fiches ne décrivent PAS la même séance physique.")
            print("   %s -> %s" % (docs[p].get("name"), cle(docs[p])))
            print("   %s -> %s" % (docs[dd].get("name"), cle(docs[dd])))
            return 1
    print("Les deux paires décrivent bien la même séance physique (coach, heure, lieu, jour).")
    print()

    for i, quoi in PRINCIPALES.items():
        d = docs[i]
        nres = db.reservations.count_documents({"courseId": i})
        print("PRINCIPALE  %s" % quoi)
        print("   nom        « %s »  ->  « %s »" % (d.get("name"), NOUVEAU_NOM))
        print("   archivée   %s  ->  False" % d.get("archived"))
        print("   réservations %d (inchangées)  |  offres liées %d (inchangées)"
              % (nres, db.offers.count_documents({"linked_course_ids": i})))
    print()
    for i, quoi in DOUBLONS.items():
        d = docs[i]
        nres = db.reservations.count_documents({"courseId": i})
        print("DOUBLON     %s" % quoi)
        print("   nom        « %s »  (inchangé : c'est une trace)" % d.get("name"))
        print("   archivée   %s  ->  True" % d.get("archived"))
        print("   réservations %d CONSERVÉES, aucune suppression" % nres)
    print()

    if not appliquer:
        print("Simulation terminée. Rien n'a été écrit.")
        print("Pour appliquer :  --appliquer")
        return 0

    horo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sauve = os.path.join(REP, "sauvegarde-v665-%s.json" % horo)
    with open(sauve, "w", encoding="utf-8") as f:
        json.dump(list(docs.values()), f, ensure_ascii=False, indent=2, default=str)
    print("Sauvegarde écrite : %s" % sauve)

    for i in PRINCIPALES:
        db.courses.update_one({"id": i}, {"$set": {
            "name": NOUVEAU_NOM, "description": DESCRIPTION,
            "archived": False, "visible": True,
            "v665_renomme_le": datetime.now(timezone.utc).isoformat()}})
    for i in DOUBLONS:
        db.courses.update_one({"id": i}, {"$set": {
            "archived": True,
            "v665_archive_le": datetime.now(timezone.utc).isoformat(),
            "v665_motif": "doublon de la seance physique, reservations conservees"}})

    print()
    print("=== VÉRIFICATION APRÈS ÉCRITURE ===")
    for i in list(PRINCIPALES) + list(DOUBLONS):
        d = db.courses.find_one({"id": i}, {"_id": 0, "name": 1, "archived": 1, "time": 1,
                                            "weekday": 1, "description": 1})
        nres = db.reservations.count_documents({"courseId": i})
        print("  %-30s arch=%-5s %s jour=%s  résa=%d"
              % (str(d.get("name"))[:30], d.get("archived"), d.get("time"),
                 d.get("weekday"), nres))
    print()
    print("Rollback :  python %s --rollback %s" % (os.path.basename(__file__), sauve))
    return 0


def rollback(chemin):
    db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)[os.environ["DB_NAME"]]
    with open(chemin, encoding="utf-8") as f:
        docs = json.load(f)
    print("Restauration de %d fiches depuis %s" % (len(docs), chemin))
    for d in docs:
        i = d.get("id")
        if not i:
            continue
        maj = {k: v for k, v in d.items() if k != "id"}
        db.courses.update_one({"id": i}, {"$set": maj,
                                         "$unset": {"v665_renomme_le": "", "v665_archive_le": "",
                                                    "v665_motif": ""}})
        print("  restauré : « %s »  arch=%s" % (d.get("name"), d.get("archived")))
    return 0


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        sys.exit(rollback(sys.argv[sys.argv.index("--rollback") + 1]))
    sys.exit(main())

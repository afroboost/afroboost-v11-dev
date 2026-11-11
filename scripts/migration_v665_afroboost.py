# -*- coding: utf-8 -*-
"""V665 — Renommer le cours récurrent en « Afroboost ». RIEN D'AUTRE.

════════════════════════════════════════════════════════════════════════════
CE SCRIPT A ÉTÉ RÉÉCRIT. SES DEUX VERSIONS PRÉCÉDENTES AURAIENT CASSÉ LE SITE.
════════════════════════════════════════════════════════════════════════════

CE QUE JE CROYAIS (et qui était faux). Les quatre fiches — deux nommées
« Afroboost Silent … », deux nommées « Cours à l'unité » — formaient deux
doublons à neutraliser. Je prévoyais d'archiver, puis de masquer, les deux
fiches « Cours à l'unité ».

CE QUE J'AI TROUVÉ EN VÉRIFIANT. Il n'y a PAS de doublon. Depuis V647, une
séance physique est VOLONTAIREMENT portée par DEUX fiches :
  - la fiche « forfait » (`agenda_abonne: true`) — celle des abonnés ;
  - la fiche « publiée » — celle du paiement à l'unité.
`v647_groupes_seance_physique` (api/routes/shared.py) les réunit, et cela
FONCTIONNE sur les données réelles : vérifié, les 4 fiches forment 2 groupes.
Le calendrier affiche donc UNE carte par séance, et les inscrits sont DÉJÀ
sommés sur les deux fiches (`SessionsModal`, `ids: [principale, publiée]`).

CE QUE MES VERSIONS PRÉCÉDENTES AURAIENT FAIT :
  - archiver la fiche publiée -> `_publiees` exige `archived is not True`
    -> GROUPE DÉTRUIT, et ses 13 réservations à un clic de la purge ;
  - la masquer (`visible: false`) -> `_publiees` exige `visible is not False`
    -> GROUPE DÉTRUIT, séance amputée de ses offres et de son adresse.
Dans les deux cas, la séance « Afroboost » aurait perdu sa moitié publique.
Le banc `tests/test_v667_doublon_groupe.py` fige ces deux refus.

CE QUE FAIT CE SCRIPT, DÉSORMAIS. Il renomme les DEUX fiches forfait — ce sont
elles qui donnent leur nom à la carte (`{...principale}`) — et leur pose la
description. Rien d'autre :
  - pas de changement d'archivage ni de visibilité ;
  - aucune réservation déplacée (les 151 restent où elles sont) ;
  - aucun identifiant, aucune offre, aucune capacité touchés ;
  - les deux séries récurrentes restent distinctes (mercredi / dimanche).

« Cours à l'unité » reste le nom de la fiche PUBLIÉE. Ce nom ne s'affiche pas
sur la carte : la carte prend celui de la fiche forfait. Le renommer serait
cosmétique et sans effet visible — je ne le fais donc pas sans ton avis.

Usage :  python scripts/migration_v665_afroboost.py            (simulation)
         python scripts/migration_v665_afroboost.py --appliquer
         python scripts/migration_v665_afroboost.py --rollback <fichier.json>
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

NOUVEAU_NOM = "Afroboost"
DESCRIPTION = ("Cours collectif de cardio-danse afrobeat, sans casque audio, "
               "accessible à tous les niveaux.")

# Les fiches FORFAIT : ce sont elles qui nomment la carte du calendrier.
A_RENOMMER = {
    "64b4c975-f507-447b-a44d-4623349fd24b": "mercredi 18:45 (71 réservations)",
    "23534f7c-938f-41ff-872b-d62a5314a5d6": "dimanche 18:30 (55 réservations)",
}
# Les fiches PUBLIÉES : on NE LES TOUCHE PAS. Listées pour le contrôle.
A_PRESERVER = {
    "62fcac27-75ad-4429-bfb1-aee613858bdc": "mercredi 18:45 (13 réservations)",
    "01f3b303-1f64-48de-81f0-7c71dbbcb3b6": "dimanche 18:30 (12 réservations)",
}

# GARDE-FOU : aucun événement AVEC casques ne doit se trouver parmi les cibles.
INTERDITS = ("silent afroboost", "laff festival", "silent dance",
             "edition speciale", "édition spéciale")

REP = os.path.dirname(os.path.abspath(__file__))
_VOIES = {"chem": "chemin", "av": "avenue", "bd": "boulevard", "rte": "route",
          "pl": "place", "r": "rue"}


def norm(v):
    t = re.sub(r"[^a-z0-9]+", " ",
               str(v or "").lower().translate(
                   str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc"))).strip()
    return " ".join(_VOIES.get(m, m) for m in t.split())


def main():
    appliquer = "--appliquer" in sys.argv
    db = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000)[os.environ["DB_NAME"]]

    cibles = list(A_RENOMMER) + list(A_PRESERVER)
    docs = {d["id"]: d for d in db.courses.find({"id": {"$in": cibles}}, {"_id": 0})}

    print("=" * 74)
    print("V665 — %s" % ("APPLICATION" if appliquer else "SIMULATION (rien n'est écrit)"))
    print("=" * 74)

    if len(docs) != len(cibles):
        print("ARRÊT : %d fiches attendues, %d trouvées." % (len(cibles), len(docs)))
        return 1

    for i, d in docs.items():
        for mot in INTERDITS:
            if mot in norm(d.get("name")):
                print("ARRÊT : « %s » ressemble à un événement AVEC casques." % d.get("name"))
                return 1

    # GARDE-FOU 2 : chaque fiche à renommer DOIT être une fiche forfait, et sa
    # jumelle publiée doit exister au même créneau. Sinon on ne touche à rien.
    def cle(d):
        return (norm(d.get("coach_id")), str(d.get("time") or ""),
                norm(d.get("locationName") or d.get("location")), str(d.get("weekday")))

    for a, b in zip(list(A_RENOMMER), list(A_PRESERVER)):
        if docs[a].get("agenda_abonne") is not True:
            print("ARRÊT : « %s » n'est pas une fiche forfait (`agenda_abonne`)."
                  % docs[a].get("name"))
            return 1
        if cle(docs[a]) != cle(docs[b]):
            print("ARRÊT : « %s » et « %s » ne sont pas au même créneau."
                  % (docs[a].get("name"), docs[b].get("name")))
            return 1
    print("Chaque fiche à renommer est bien la fiche FORFAIT d'une séance,")
    print("et sa jumelle publiée existe au même créneau. Le groupe V647 tient.")
    print()

    for i, quoi in A_RENOMMER.items():
        d = docs[i]
        print("RENOMMÉE    %s" % quoi)
        print("   nom          « %s »" % d.get("name"))
        print("                ->  « %s »" % NOUVEAU_NOM)
        print("   description  -> « %s »" % DESCRIPTION)
        print("   archivée     %s  (INCHANGÉE)   visible %s  (INCHANGÉE)"
              % (d.get("archived"), d.get("visible")))
        print("   réservations %d (inchangées)   offres liées %d (inchangées)"
              % (db.reservations.count_documents({"courseId": i}),
                 db.offers.count_documents({"linked_course_ids": i})))
    print()
    for i, quoi in A_PRESERVER.items():
        d = docs[i]
        print("INTACTE     %s  — « %s »" % (quoi, d.get("name")))
        print("   rien n'est modifié : la masquer ou l'archiver détruirait le")
        print("   groupe V647 et amputerait la séance de sa moitié publique.")
    print()
    _tot = sum(db.reservations.count_documents({"courseId": i}) for i in cibles)
    print("Réservations concernées au total : %d — AUCUNE n'est touchée." % _tot)
    print()

    if not appliquer:
        print("Simulation terminée. Rien n'a été écrit.")
        print("Pour appliquer :  --appliquer")
        return 0

    horo = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sauve = os.path.join(REP, "sauvegarde-v665-%s.json" % horo)
    with open(sauve, "w", encoding="utf-8") as f:
        json.dump([docs[i] for i in A_RENOMMER], f, ensure_ascii=False, indent=2, default=str)
    print("Sauvegarde écrite : %s" % sauve)

    for i in A_RENOMMER:
        db.courses.update_one({"id": i}, {"$set": {
            "name": NOUVEAU_NOM, "description": DESCRIPTION,
            "v665_renomme_le": datetime.now(timezone.utc).isoformat()}})

    print()
    print("=== VÉRIFICATION APRÈS ÉCRITURE ===")
    for i in cibles:
        d = db.courses.find_one({"id": i}, {"_id": 0, "name": 1, "archived": 1, "visible": 1,
                                            "time": 1, "weekday": 1, "agenda_abonne": 1})
        print("  %-30s jour=%s %s  arch=%s vis=%s forfait=%s  résa=%d"
              % (str(d.get("name"))[:30], d.get("weekday"), d.get("time"),
                 d.get("archived"), d.get("visible"), d.get("agenda_abonne"),
                 db.reservations.count_documents({"courseId": i})))
    print()
    print("Rollback :  python scripts/migration_v665_afroboost.py --rollback %s" % sauve)
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
        _unset = {"v665_renomme_le": ""}
        if "description" not in d:
            _unset["description"] = ""        # elle n'existait pas avant
        db.courses.update_one({"id": i}, {"$set": maj, "$unset": _unset})
        print("  restauré : « %s »" % d.get("name"))
    return 0


if __name__ == "__main__":
    if "--rollback" in sys.argv:
        sys.exit(rollback(sys.argv[sys.argv.index("--rollback") + 1]))
    sys.exit(main())

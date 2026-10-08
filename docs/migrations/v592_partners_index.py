"""V592 — migration des index de `partners` (Partenaire B1). NON EXÉCUTÉE PAR LE LOT.

PAR DÉFAUT : SIMULATION. Le script lit l'état, affiche les vérifications et les
commandes qu'il jouerait, et N'ÉCRIT RIEN. Il n'écrit qu'avec `--executer`.

    python3 docs/migrations/v592_partners_index.py                 # simulation
    python3 docs/migrations/v592_partners_index.py --executer      # migration
    python3 docs/migrations/v592_partners_index.py --rollback --executer

Connexion : variables MONGO_URL et DB_NAME (défaut `afroboost_db`).

CE QUI CHANGE
  lead_id_unique      {lead_id: 1} unique                -> {lead_id: 1} unique,
                      partialFilterExpression {lead_id: {$type: "string"}}
  prospect_id_unique  (nouveau) {prospect_id: 1} unique, partialFilterExpression
                      {prospect_id: {$type: "string"}}
  partner_slug_unique inchangé.

POURQUOI « string » : `leads.id` et `partner_prospects.id` sont tous deux
`str(uuid.uuid4())` (server.py, création d'un lead et d'un prospect) et la
décision P2-B recopie `lead_id` tel quel. Aucun ObjectId n'est stocké.

FENÊTRE : `lead_id_unique` est supprimé puis recréé sous le même nom (la consigne
garde ce nom). Entre les deux, quelques millisecondes sans unicité sur `lead_id` ;
seule l'acceptation manuelle d'une candidature pourrait s'y glisser.

ROLLBACK : remet l'index d'origine. Il ÉCHOUE (proprement, sans rien casser) dès
qu'il existe 2 partenaires sans candidature — c'est précisément ce que l'ancien
index interdit. Dans ce cas, revenir en arrière = retirer le code V592, pas l'index.
"""
import os
import sys

from pymongo import MongoClient

ANCIEN = {"key": [("lead_id", 1)], "unique": True}
FILTRE_LEAD = {"lead_id": {"$type": "string"}}
FILTRE_PROSPECT = {"prospect_id": {"$type": "string"}}


def etat(col):
    idx = col.index_information()
    return {n: {k: v for k, v in s.items() if k in ("key", "unique", "partialFilterExpression", "sparse")}
            for n, s in idx.items()}


def doublons(col, champ):
    return list(col.aggregate([
        {"$match": {champ: {"$type": "string"}}},
        {"$group": {"_id": "$" + champ, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}, {"$limit": 5}]))


def main():
    executer = "--executer" in sys.argv
    rollback = "--rollback" in sys.argv
    url = os.environ.get("MONGO_URL")
    if not url:
        sys.exit("MONGO_URL absent")
    db = MongoClient(url, serverSelectionTimeoutMS=15000)[os.environ.get("DB_NAME") or "afroboost_db"]
    col = db["partners"]

    print("MODE :", "EXÉCUTION" if executer else "SIMULATION (aucune écriture)",
          "— ROLLBACK" if rollback else "— MIGRATION")
    print("AVANT : documents =", col.count_documents({}))
    for n, s in etat(col).items():
        print("   index", n, s)
    sans_lead = col.count_documents({"lead_id": {"$not": {"$type": "string"}}})
    print("   partenaires sans lead_id chaîne :", sans_lead)

    if not rollback:
        d1, d2 = doublons(col, "lead_id"), doublons(col, "prospect_id")
        print("   doublons lead_id :", d1, "| doublons prospect_id :", d2)
        if d1 or d2:
            sys.exit("ARRÊT : doublons présents, rien n'a été modifié.")
        cmds = [
            'db.partners.dropIndex("lead_id_unique")',
            'db.partners.createIndex({lead_id: 1}, {name: "lead_id_unique", unique: true, '
            'partialFilterExpression: {lead_id: {$type: "string"}}})',
            'db.partners.createIndex({prospect_id: 1}, {name: "prospect_id_unique", unique: true, '
            'partialFilterExpression: {prospect_id: {$type: "string"}}})',
        ]
    else:
        if sans_lead > 1:
            sys.exit("ARRÊT : %d partenaires sans candidature — l'ancien index ne peut pas être "
                     "remis. Revenir en arrière = retirer le code V592. Rien n'a été modifié." % sans_lead)
        cmds = [
            'db.partners.dropIndex("prospect_id_unique")',
            'db.partners.dropIndex("lead_id_unique")',
            'db.partners.createIndex({lead_id: 1}, {name: "lead_id_unique", unique: true})',
        ]
    print("COMMANDES :")
    for c in cmds:
        print("   ", c)
    if not executer:
        print("SIMULATION terminée : rien n'a été écrit.")
        return

    noms = set(col.index_information())
    if not rollback:
        if "lead_id_unique" in noms:
            col.drop_index("lead_id_unique")
        col.create_index([("lead_id", 1)], name="lead_id_unique", unique=True,
                         partialFilterExpression=FILTRE_LEAD)
        if "prospect_id_unique" not in noms:
            col.create_index([("prospect_id", 1)], name="prospect_id_unique", unique=True,
                             partialFilterExpression=FILTRE_PROSPECT)
    else:
        if "prospect_id_unique" in noms:
            col.drop_index("prospect_id_unique")
        if "lead_id_unique" in noms:
            col.drop_index("lead_id_unique")
        col.create_index([("lead_id", 1)], name="lead_id_unique", unique=True)

    print("APRÈS :")
    for n, s in etat(col).items():
        print("   index", n, s)
    fin = etat(col)
    if not rollback:
        ok = (fin.get("lead_id_unique", {}).get("partialFilterExpression") == FILTRE_LEAD
              and fin.get("prospect_id_unique", {}).get("partialFilterExpression") == FILTRE_PROSPECT
              and "partner_slug_unique" in fin)
    else:
        ok = ("prospect_id_unique" not in fin
              and "partialFilterExpression" not in fin.get("lead_id_unique", {"partialFilterExpression": 1})
              and fin.get("lead_id_unique", {}).get("unique") is True)
    print("VÉRIFICATION :", "OK" if ok else "ÉCHEC")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

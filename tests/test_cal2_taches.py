#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAL-2 — LES TACHES, DANS LE MEME CALENDRIER ET LE MEME MOTEUR.

CE QUE LE LOT AJOUTE
==============================================================================
Une tache est un evenement de `calendar_events` portant `event_type: "task"`.
Aucune collection nouvelle, aucun second ecran, aucun second planificateur :
le depot en avait deja un, eprouve, et il manquait un type dans la liste
blanche des notifications.

CE QUE CE FICHIER PROUVE
==============================================================================
  * creer, modifier, reporter, terminer, annuler — et la date d'achevement
    suit le statut dans la MEME ecriture, donc jamais l'un sans l'autre ;
  * les quatre piles, dont « terminee » qui PASSE AVANT « en retard » : une
    tache faite hier n'est pas en retard ;
  * une tache en retard reste VISIBLE — la fenetre du calendrier la masquerait
    le jour ou elle compte le plus ;
  * l'echeance declenche UNE notification, et un second passage n'en cree pas
    une seconde : deux gardes independantes, verifiees separement ;
  * une tache close ou supprimee ne notifie jamais ;
  * le push qui echoue n'empeche pas la notification en-app ;
  * le calendrier affiche les taches A COTE des campagnes, sans fusion ;
  * aucune migration, aucun Google.

    python3 tests/test_cal2_taches.py
"""
import ast
import asyncio
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


SECRET = "secret-de-test-cal2-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-cal2-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


def _bloc(source, entete):
    debut = source.index(entete)
    banniere = "\n# " + "=" * 76 + "\n# "
    apres = source.index("\n\n", debut)
    bornes = [x for x in (source.find(banniere, apres),
                          source.find("# --- Leads Routes (Widget IA) ---", apres))
              if x != -1]
    return source[debut:min(bornes)] if bornes else source[debut:]


BLOC = _bloc(SRC, "# CAL-2 — LES TACHES, DANS LE MEME CALENDRIER")

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
Col, Base = _espace["CollectionBouchon"], _espace["BaseBouchon"]
RequeteFictive, lancer, jeton = _espace["RequeteFictive"], _espace["lancer"], _espace["jeton"]

JA, JB = jeton(COACH_A), jeton(COACH_B)
MAINTENANT = datetime.now(timezone.utc)
HIER = (MAINTENANT - timedelta(days=1)).isoformat()
TOUT_A_L_HEURE = (MAINTENANT - timedelta(hours=1)).isoformat()
DANS_UNE_HEURE = (MAINTENANT + timedelta(hours=1)).isoformat()
DEMAIN = (MAINTENANT + timedelta(days=1)).isoformat()

# Le push est remplace : on veut savoir s'il est appele, sans reseau.
_PUSH = []


async def _faux_push(email, titre, corps, data=None):
    _PUSH.append({"email": email, "titre": titre, "corps": corps, "data": data})
    return True


async def _push_qui_echoue(email, titre, corps, data=None):
    _PUSH.append({"echec": True})
    raise RuntimeError("appareil injoignable")


S.send_push_by_email = _faux_push


# LE BOUCHON PARTAGE IGNORE `upsert` ET `$setOnInsert` : son `update_one` ne
# fait rien quand aucun document ne correspond. Or la notification s'ecrit
# EXACTEMENT ainsi — c'est ce qui la rend idempotente. Reutiliser le bouchon
# tel quel aurait donne un test complaisant : il aurait vu « signalee » sans
# qu'aucune notification n'existe. On modelise donc la promesse REELLE de
# Mongo, comme les bancs P3-S2E et P3-U1 le font pour leurs propres pieges.
class CollectionUpsert(Col):
    """Le bouchon partage, complete de ce dont CE lot depend.

    IL LUI MANQUAIT AUSSI LES COMPARAISONS. `_ok` connait `$in`, `$nin`,
    `$exists` et `$ne`, mais pas `$lte` — or c'est EXACTEMENT ce qui distingue
    une tache echue d'une tache future. Sans cette addition, une tache prevue
    demain ressortait comme echue, et le banc mesurait le trou du bouchon au
    lieu de la regle du moteur.
    """

    def _ok(self, doc, filtre):
        for cle, val in (filtre or {}).items():
            if isinstance(val, dict):
                v = doc.get(cle)
                for op, borne in val.items():
                    if op in ("$lte", "$lt", "$gte", "$gt"):
                        if v is None:
                            return False
                        if op == "$lte" and not (v <= borne):
                            return False
                        if op == "$lt" and not (v < borne):
                            return False
                        if op == "$gte" and not (v >= borne):
                            return False
                        if op == "$gt" and not (v > borne):
                            return False
        return Col._ok(self, doc, filtre)

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1,
                                      "upserted_id": None})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0,
                                  "upserted_id": None})()
        neuf = {c: v for c, v in (filtre or {}).items() if not isinstance(v, dict)}
        neuf.update(maj.get("$setOnInsert") or {})
        neuf.update(maj.get("$set") or {})
        self.documents.append(neuf)
        self.ecritures += 1
        return type("R", (), {"matched_count": 0, "modified_count": 0,
                              "upserted_id": "upsert"})()


def base_neuve(taches=None):
    b = Base([])
    b["campaigns"] = Col("campaigns", [], uniques=[(("id",), None)])
    b["courses"] = Col("courses", [], uniques=[(("id",), None)])
    b["notifications"] = CollectionUpsert("notifications", [], uniques=[(("id",), None)])
    b[S.CAL1_COLLECTION] = CollectionUpsert(
        S.CAL1_COLLECTION, [dict(x) for x in (taches or [])], uniques=[(("id",), None)])
    S.db = b
    del _PUSH[:]
    return b


def creer(corps, jeton_=JA):
    return lancer(S.cal1_creer(RequeteFictive(jeton_=jeton_, corps=corps)))


def modifier(idt, corps, jeton_=JA):
    return lancer(S.cal1_modifier(idt, RequeteFictive(jeton_=jeton_, corps=corps)))


def taches(jeton_=JA, **params):
    return lancer(S.cal2_lister_taches(RequeteFictive(jeton_=jeton_, params=params)))


def tache(idt, titre, quand, statut="prevu", **extra):
    d = {"id": idt, "coach_id": COACH_A, "title": titre, "description": "",
         "starts_at": quand, "ends_at": "", "all_day": False,
         "event_type": "task", "status": statut, "location": "",
         "priority": "normale", "completed_at": None, "is_deleted": False,
         "created_at": INSTANT, "updated_at": INSTANT}
    d.update(extra)
    return d


# ============================================================================
print("\n1. UNE TACHE SE CREE DANS LE MEME MODELE")

_b = base_neuve()
_t = creer({"title": "Vérifier DKIM Resend", "starts_at": DANS_UNE_HEURE,
            "event_type": "task", "description": "avant le lancement",
            "priority": "haute"})["event"]
verifier("1a. la tache est creee", bool(_t["id"]))
verifier("1b. son type est `task`", _t["event_type"] == "task")
verifier("1c. son titre", _t["title"] == "Vérifier DKIM Resend")
verifier("1d. sa description", _t["description"] == "avant le lancement")
verifier("1e. sa priorite", _t["priority"] == "haute")
verifier("1f. son statut initial", _t["status"] == "prevu")
verifier("1g. elle n'est pas terminee", _t["completed_at"] is None)
verifier("1h. elle est modifiable", _t["modifiable"] is True)
verifier("1i. elle vit dans `calendar_events`, PAS ailleurs",
         len(_b[S.CAL1_COLLECTION].documents) == 1
         and _b[S.CAL1_COLLECTION].documents[0]["event_type"] == "task")
verifier("1j. son echeance EST `starts_at` — aucun second champ de date",
         "due_at" not in _b[S.CAL1_COLLECTION].documents[0])

verifier("1k. une priorite inconnue retombe sur `normale`",
         creer({"title": "x", "starts_at": DEMAIN, "event_type": "task",
                "priority": "urgentissime"})["event"]["priority"] == "normale")
verifier("1l. sans priorite, `normale` aussi",
         creer({"title": "y", "starts_at": DEMAIN,
                "event_type": "task"})["event"]["priority"] == "normale")
verifier("1m. un RENDEZ-VOUS n'a pas de priorite (donnee que rien ne lit)",
         creer({"title": "rdv", "starts_at": DEMAIN, "event_type": "appointment",
                "priority": "haute"})["event"]["priority"] is None)

for _corps, _quoi in (({"starts_at": DEMAIN}, "sans titre"),
                      ({"title": "x"}, "sans echeance"),
                      ({"title": "x", "starts_at": "pas-une-date"}, "echeance illisible")):
    try:
        creer(dict(_corps, event_type="task"))
        _refuse = False
    except HTTPException as e:
        _refuse = e.status_code == 400
    verifier("1n. %-20s -> 400" % _quoi, _refuse)


# ============================================================================
print("\n2. MODIFIER, REPORTER, TERMINER, ANNULER")

_b = base_neuve()
_id = creer({"title": "Appeler Festival X", "starts_at": DANS_UNE_HEURE,
             "event_type": "task"})["event"]["id"]

_m = modifier(_id, {"title": "Appeler Festival X (relance)"})
verifier("2a. le titre se modifie", _m["event"]["title"].endswith("(relance)"))
_m = modifier(_id, {"starts_at": DEMAIN})
verifier("2b. l'echeance se REPORTE", _m["event"]["starts_at"] == DEMAIN)
_m = modifier(_id, {"priority": "haute"})
verifier("2c. la priorite se change", _m["event"]["priority"] == "haute")

_m = modifier(_id, {"status": "fait"})
verifier("2d. TERMINER : le statut passe a `fait`", _m["event"]["status"] == "fait")
verifier("2e. ... et la date d'achevement est posee DANS LA MEME ecriture",
         bool(_m["event"]["completed_at"]), str(_m["event"]["completed_at"]))
_doc = _b[S.CAL1_COLLECTION].documents[0]
verifier("2f. impossible d'avoir `fait` sans date",
         not (_doc.get("status") == "fait" and not _doc.get("completed_at")))

_m = modifier(_id, {"status": "prevu"})
verifier("2g. rouvrir une tache efface la date d'achevement",
         _m["event"]["completed_at"] is None, str(_m["event"]["completed_at"]))

_m = modifier(_id, {"status": "annule"})
verifier("2h. ANNULER est un statut, pas une suppression",
         _m["event"]["status"] == "annule" and len(_b[S.CAL1_COLLECTION].documents) == 1)

try:
    modifier(_id, {"status": "termine"})   # faux ami : le statut est `fait`
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("2i. un statut inconnu -> 400", _refuse)


# ============================================================================
print("\n3. LES QUATRE PILES")

_b = base_neuve([
    tache("t-retard", "En retard", HIER),
    tache("t-auj", "Aujourd'hui", MAINTENANT.replace(hour=23, minute=0).isoformat()),
    tache("t-venir", "A venir", DEMAIN),
    tache("t-fait", "Faite", HIER, statut="fait", completed_at=HIER),
    tache("t-annul", "Annulee", HIER, statut="annule"),
])
_r = taches()
verifier("3a. les cinq taches sont rendues", _r["total"] == 5, str(_r["total"]))
_piles = {t["id"]: t["bucket"] for t in _r["tasks"]}
verifier("3b. une echeance passee -> `en_retard`", _piles["t-retard"] == "en_retard")
verifier("3c. une echeance du jour -> `aujourdhui`", _piles["t-auj"] == "aujourdhui",
         str(_piles.get("t-auj")))
verifier("3d. une echeance future -> `a_venir`", _piles["t-venir"] == "a_venir")
verifier("3e. UNE TACHE FAITE HIER N'EST PAS EN RETARD, elle est terminee",
         _piles["t-fait"] == "terminees", str(_piles.get("t-fait")))
verifier("3f. une tache annulee non plus", _piles["t-annul"] == "terminees")
verifier("3g. les compteurs comptent TOUT, pas la page filtree",
         _r["counts"] == {"aujourdhui": 1, "a_venir": 1, "en_retard": 1, "terminees": 2},
         str(_r["counts"]))

_f = taches(filtre="en_retard")
verifier("3h. le filtre ne garde que sa pile",
         [t["id"] for t in _f["tasks"]] == ["t-retard"], str([t["id"] for t in _f["tasks"]]))
verifier("3i. ... mais les compteurs restent complets",
         _f["counts"]["terminees"] == 2)
try:
    taches(filtre="nimporte")
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("3j. un filtre inconnu -> 400", _refuse)

verifier("3k. UNE TACHE EN RETARD RESTE VISIBLE (la fenetre du calendrier la masquerait)",
         any(t["id"] == "t-retard" for t in taches()["tasks"]))
verifier("3l. les taches sont triees par echeance",
         [t["starts_at"] for t in _r["tasks"]]
         == sorted(t["starts_at"] for t in _r["tasks"]))


# ============================================================================
print("\n4. L'ECHEANCE DECLENCHE UNE NOTIFICATION — UNE SEULE")

_b = base_neuve([tache("t-1", "Vérifier DKIM Resend", TOUT_A_L_HEURE)])
_p1 = lancer(S.cal2_passage_echeances())
verifier("4a. le passage examine la tache echue", _p1["examinees"] == 1, str(_p1))
verifier("4b. il la signale", _p1["signalees"] == 1, str(_p1))
_notifs = _b["notifications"].documents
verifier("4c. UNE notification est creee", len(_notifs) == 1, str(len(_notifs)))
_n = _notifs[0]
verifier("4d. son type est `task_due`", _n["type"] == S.CAL2_NOTIF_TYPE)
verifier("4e. son identifiant est STABLE (derive de la tache)",
         _n["id"] == "task_due_t-1", str(_n["id"]))
verifier("4f. elle porte le coach", _n["coach_id"] == COACH_A)
verifier("4g. elle est non lue", _n["read"] is False)
verifier("4h. le titre de la tache y figure", "DKIM" in _n["message"])
verifier("4i. le push est parti", len(_PUSH) == 1 and _PUSH[0]["email"] == COACH_A)
verifier("4j. la tache est marquee comme signalee",
         bool(_b[S.CAL1_COLLECTION].documents[0].get("notified_at")))

# --- L'IDEMPOTENCE : le coeur du lot ---
_p2 = lancer(S.cal2_passage_echeances())
verifier("4k. un SECOND passage n'examine plus rien", _p2["examinees"] == 0, str(_p2))
verifier("4l. ... et ne signale rien", _p2["signalees"] == 0)
verifier("4m. toujours UNE seule notification", len(_b["notifications"].documents) == 1)
verifier("4n. toujours UN seul push", len(_PUSH) == 1)

for _ in range(8):
    lancer(S.cal2_passage_echeances())
verifier("4o. dix passages -> toujours une notification",
         len(_b["notifications"].documents) == 1)

# --- LA SECONDE GARDE, eprouvee SEULE ---
_b = base_neuve([tache("t-2", "Deuxieme", TOUT_A_L_HEURE)])
_d = _b[S.CAL1_COLLECTION].documents[0]
lancer(S.cal2_signaler_echeance(_d, MAINTENANT.isoformat()))
# on efface la premiere garde, comme si elle avait cede
_b[S.CAL1_COLLECTION].documents[0].pop("notified_at", None)
_r2 = lancer(S.cal2_signaler_echeance(_b[S.CAL1_COLLECTION].documents[0],
                                      MAINTENANT.isoformat()))
verifier("4p. premiere garde forcee : l'identifiant stable retient le doublon",
         len(_b["notifications"].documents) == 1, str(len(_b["notifications"].documents)))


# ============================================================================
print("\n5. CE QUI NE DOIT JAMAIS NOTIFIER")

_b = base_neuve([
    tache("n-fait", "Faite", TOUT_A_L_HEURE, statut="fait"),
    tache("n-annul", "Annulee", TOUT_A_L_HEURE, statut="annule"),
    tache("n-futur", "Future", DEMAIN),
    tache("n-suppr", "Supprimee", TOUT_A_L_HEURE, is_deleted=True),
])
_p = lancer(S.cal2_passage_echeances())
verifier("5a. aucune de ces taches n'est examinee", _p["examinees"] == 0, str(_p))
verifier("5b. aucune notification", len(_b["notifications"].documents) == 0)
verifier("5c. aucun push", len(_PUSH) == 0)

# un evenement qui n'est PAS une tache n'entre jamais dans le planificateur
_b = base_neuve([dict(tache("e-1", "Rendez-vous echu", TOUT_A_L_HEURE),
                      event_type="appointment")])
verifier("5d. un rendez-vous echu n'est PAS notifie par ce moteur",
         lancer(S.cal2_passage_echeances())["examinees"] == 0)


# ============================================================================
print("\n6. LE PUSH EST ACCESSOIRE, JAMAIS BLOQUANT")

S.send_push_by_email = _push_qui_echoue
_b = base_neuve([tache("t-p", "Avec push casse", TOUT_A_L_HEURE)])
_p = lancer(S.cal2_passage_echeances())
verifier("6a. la tache est signalee malgre l'echec du push", _p["signalees"] == 1, str(_p))
verifier("6b. la notification en-app EXISTE", len(_b["notifications"].documents) == 1)
S.send_push_by_email = _faux_push


# ============================================================================
print("\n7. LE CALENDRIER MONTRE LES TACHES A COTE DU RESTE")

_b = base_neuve([tache("t-cal", "Tache visible", DEMAIN)])
_b["campaigns"].documents.append(
    {"id": "c-1", "coach_id": COACH_A, "name": "Campagne",
     "scheduledAt": DEMAIN, "status": "scheduled", "createdAt": INSTANT})
_cal = lancer(S.cal1_lister(RequeteFictive(jeton_=JA, params={
    "from": MAINTENANT.isoformat(),
    "to": (MAINTENANT + timedelta(days=10)).isoformat()})))
_types = sorted({e["event_type"] for e in _cal["events"]})
verifier("7a. la tache et la campagne sont dans la MEME liste",
         _types == ["campaign", "task"], str(_types))
verifier("7b. `task` est desormais un type annonce", "task" in _cal["types"])
verifier("7c. la tache reste modifiable depuis le calendrier",
         all(e["modifiable"] for e in _cal["events"] if e["event_type"] == "task"))
verifier("7d. la campagne, elle, ne l'est pas",
         all(not e["modifiable"] for e in _cal["events"] if e["event_type"] == "campaign"))


# ============================================================================
print("\n8. AUTH, ISOLATION, ET AUCUNE MIGRATION")

_b = base_neuve([tache("t-prive", "Privee", DEMAIN)])
try:
    taches(jeton_=None)
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code in (401, 403)
verifier("8a. lister les taches SANS jeton -> refuse", _ferme)
verifier("8b. un AUTRE coach ne voit aucune tache",
         taches(jeton_=JB)["total"] == 0, str(taches(jeton_=JB)["total"]))
try:
    modifier("t-prive", {"title": "vole"}, jeton_=JB)
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 404
verifier("8c. ... et ne peut pas la modifier -> 404", _ferme)

_CODE = BLOC[BLOC.index("CAL2_INTERVALLE_S"):]
_SANS_COMMENTAIRES = "\n".join(l for l in _CODE.split("\n") if not l.strip().startswith("#"))
_arbre = ast.parse(_CODE)
_cibles = set()
for _n in ast.walk(_arbre):
    if isinstance(_n, ast.Call) and getattr(_n.func, "attr", "") in (
            "update_one", "update_many", "insert_one", "insert_many",
            "delete_one", "delete_many", "replace_one"):
        c = getattr(_n.func, "value", None)
        if isinstance(c, ast.Subscript):
            _cibles.add(ast.get_source_segment(_CODE, c.slice) or "?")
        elif isinstance(c, ast.Attribute):
            _cibles.add(c.attr)
verifier("8d. le lot n'ecrit QUE dans le calendrier et les notifications",
         _cibles == {"CAL1_COLLECTION", "notifications"}, str(sorted(_cibles)))
verifier("8e. aucun `update_many` (donc aucune migration de masse)",
         "update_many" not in _CODE)
verifier("8f. AUCUNE trace de Google dans le CODE",
         not any(m in _SANS_COMMENTAIRES.lower()
                 for m in ("google", "oauth", "gapi")))
verifier("8g. aucune collection nouvelle",
         "prospect_tasks" not in SRC and "afroboost_tasks" not in SRC
         and SRC.count('CAL1_COLLECTION = "calendar_events"') == 1)
verifier("8h. le type de notification a ete AJOUTE, pas substitue",
         'C17J_TYPES = ("new_lead", "new_reservation", "task_due")' in SRC)
# ON INSPECTE LES IDENTIFIANTS REELLEMENT REFERENCES. Retirer les lignes `#`
# ne suffisait pas : la phrase « on n'active pas APScheduler » vit dans une
# DOCSTRING, qui est du code aux yeux d'une recherche textuelle. L'arbre
# syntaxique, lui, ne confond pas une chaine avec un appel.
_NOMS = {getattr(n, "id", None) for n in ast.walk(_arbre) if isinstance(n, ast.Name)}
_NOMS |= {getattr(n, "attr", None) for n in ast.walk(_arbre) if isinstance(n, ast.Attribute)}
_IMPORTS = {a.name.split(".")[0] for n in ast.walk(_arbre)
            if isinstance(n, ast.Import) for a in n.names}
_IMPORTS |= {(n.module or "").split(".")[0] for n in ast.walk(_arbre)
             if isinstance(n, ast.ImportFrom)}
verifier("8i. la boucle suit le motif du depot (asyncio, pas APScheduler)",
         "asyncio.create_task(_cal2_boucle_echeances())" in SRC
         and "SCHEDULER_RUNNING" not in _NOMS
         and not (_IMPORTS & {"apscheduler", "schedule", "celery"}),
         "noms suspects : %s" % sorted((_NOMS | _IMPORTS) & {
             "SCHEDULER_RUNNING", "apscheduler", "celery", "schedule"}))
verifier("8j. la reservation d'echeance est ATOMIQUE (condition dans le filtre)",
         '{"id": identifiant, "notified_at": {"$exists": False}}' in _CODE)
verifier("8k. la notification s'ecrit en `$setOnInsert` (identifiant stable)",
         "$setOnInsert" in _CODE and 'task_due_%s' in _CODE)
verifier("8l. un index sert la requete du planificateur",
         '[("event_type", 1), ("status", 1), ("starts_at", 1)]' in SRC)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("CAL-2 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Collections nouvelles : 0 — une tache est un evenement du calendrier")
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)

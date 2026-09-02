#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAL-1 — UN SEUL CALENDRIER, ET RIEN DE MIGRE.

CE QUE LE LOT FAIT
==============================================================================
Il generalise le calendrier des campagnes en calendrier Afroboost. Les
campagnes et les cours ne sont PAS deplaces : ils restent dans leurs
collections et sont PROJETES en lecture. Une collection nouvelle,
`calendar_events`, accueille ce que le calendrier possede en propre.

CE QUE CE FICHIER PROUVE
==============================================================================
  * les campagnes existantes ressortent du calendrier, inchangees, et AUCUNE
    n'est ecrite — c'est la garantie de non-regression, verifiee par le
    compteur d'ecritures du bouchon ;
  * un cours recurrent produit ses seances dans la fenetre, avec la convention
    JavaScript du depot (dimanche=0) et l'heure LOCALE ;
  * la fenetre est bornee : demander dix ans n'en charge que 62 jours ;
  * on ne peut creer ici ni campagne ni cours ;
  * la suppression est DOUCE ;
  * l'isolation par coach tient sur les quatre routes ;
  * aucune date n'est inventee ;
  * aucune trace de Google.

    python3 tests/test_cal1_calendrier.py
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


SECRET = "secret-de-test-cal1-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-cal1-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


def _bloc(source, entete):
    """Le bloc du lot, borne APRES son propre en-tete.

    Chercher la banniere depuis le titre mordait sur la banniere de FERMETURE
    de cet en-tete : le bloc se reduisait a une ligne, et les gardes ne
    verifiaient plus rien. On demarre donc la recherche au premier code.
    """
    debut = source.index(entete)
    code = source.index("CAL1_COLLECTION =", debut)
    # LA PLUS PROCHE DES DEUX BORNES. La banniere suivante peut se trouver
    # BIEN au-dela de la fin reelle du bloc ; prendre la premiere trouvee
    # emportait alors des milliers de lignes etrangeres, et les gardes
    # « le lot n'ecrit que ... » mesuraient tout le depot.
    banniere = "\n# " + "=" * 76 + "\n# "
    bornes = [x for x in (source.find(banniere, code),
                          source.find("# --- Leads Routes (Widget IA) ---", code))
              if x != -1]
    return source[debut:min(bornes)] if bornes else source[debut:]


BLOC = _bloc(SRC, "# CAL-1 — UN SEUL CALENDRIER")

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

# Un mois de reference FIXE : le banc ne doit pas changer de verdict selon le
# jour ou on le lance.
DEBUT = datetime(2026, 9, 1, tzinfo=timezone.utc)
FIN = datetime(2026, 9, 30, tzinfo=timezone.utc)

CAMPAGNES = [
    {"id": "c-1", "coach_id": COACH_A, "name": "Silent Lakeside – Rappel J-2",
     "scheduledAt": "2026-09-07T05:00:00.000Z", "status": "completed",
     "createdAt": "2026-08-30T10:41:27+00:00", "message": "secret", "targetIds": ["x"]},
    {"id": "c-2", "coach_id": COACH_A, "name": "LAFF Lausanne",
     "scheduledAt": "2026-09-15T10:00:00.000Z", "status": "failed",
     "createdAt": "2026-08-14T16:07:06+00:00"},
    {"id": "c-3", "coach_id": COACH_A, "name": "Hors fenetre",
     "scheduledAt": "2026-12-24T10:00:00.000Z", "status": "draft",
     "createdAt": "2026-08-01T10:00:00+00:00"},
]
# weekday 3 en convention JS = MERCREDI (dimanche=0). Le piege classique.
COURS = [
    {"id": "co-1", "coach_id": COACH_A, "name": "Session Cardio",
     "weekday": 3, "time": "18:30", "visible": True, "archived": False,
     "locationName": "Neuchatel"},
    {"id": "co-2", "coach_id": COACH_A, "name": "Cours archive",
     "weekday": 1, "time": "10:00", "visible": True, "archived": True},
    {"id": "co-3", "coach_id": COACH_A, "name": "Cours masque",
     "weekday": 2, "time": "10:00", "visible": False, "archived": False},
    {"id": "co-4", "coach_id": COACH_A, "name": "Seance ponctuelle",
     "date": "2026-09-12", "time": "20:00", "visible": True, "archived": False},
]


def base_neuve(evenements=None):
    b = Base([])
    b["campaigns"] = Col("campaigns", [dict(c) for c in CAMPAGNES], uniques=[(("id",), None)])
    b["courses"] = Col("courses", [dict(c) for c in COURS], uniques=[(("id",), None)])
    b[S.CAL1_COLLECTION] = Col(S.CAL1_COLLECTION,
                               [dict(e) for e in (evenements or [])], uniques=[(("id",), None)])
    S.db = b
    return b


def lister(jeton_=JA, **params):
    p = {"from": DEBUT.isoformat(), "to": FIN.isoformat()}
    p.update(params)
    return lancer(S.cal1_lister(RequeteFictive(jeton_=jeton_, params=p)))


def creer(corps, jeton_=JA):
    return lancer(S.cal1_creer(RequeteFictive(jeton_=jeton_, corps=corps)))


# ============================================================================
print("\n1. LES CAMPAGNES EXISTANTES NE PERDENT RIEN")

_b = base_neuve()
_r = lister()
_camps = [e for e in _r["events"] if e["event_type"] == "campaign"]
verifier("1a. les campagnes de la fenetre sont rendues", len(_camps) == 2,
         str([c["title"] for c in _camps]))
verifier("1b. celle de decembre est hors fenetre, donc absente",
         not any("Hors fenetre" in c["title"] for c in _camps))
verifier("1c. le titre vient de `name`",
         any("Silent Lakeside" in c["title"] for c in _camps))
verifier("1d. la date vient de `scheduledAt`",
         any(c["starts_at"].startswith("2026-09-07") for c in _camps), str(_camps))
verifier("1e. le statut de campagne est CONSERVE tel quel (pas traduit)",
         sorted(c["status"] for c in _camps) == ["completed", "failed"],
         str([c["status"] for c in _camps]))
verifier("1f. la campagne n'est PAS modifiable depuis le calendrier",
         all(c["modifiable"] is False for c in _camps))
verifier("1g. sa source est nommee", all(c["source"] == "campaigns" for c in _camps))
verifier("1h. son identifiant d'origine est rendu (pour retrouver la campagne)",
         sorted(c["source_id"] for c in _camps) == ["c-1", "c-2"])
verifier("1i. AUCUN champ prive de la campagne ne fuit (message, targetIds)",
         not any(k in json.dumps(_camps) for k in ("message", "targetIds", "secret")))

# LA PREUVE DE NON-REGRESSION : rien n'a ete ecrit.
verifier("1j. AUCUNE ecriture dans `campaigns`", _b["campaigns"].ecritures == 0,
         str(_b["campaigns"].ecritures))
verifier("1k. AUCUNE ecriture dans `courses`", _b["courses"].ecritures == 0)
verifier("1l. les 3 campagnes sont toujours la, intactes",
         len(_b["campaigns"].documents) == 3
         and _b["campaigns"].documents[0].get("message") == "secret")


# ============================================================================
print("\n2. LES COURS SONT PROJETES, SEANCE PAR SEANCE")

_cours = [e for e in _r["events"] if e["event_type"] == "course"]
verifier("2a. des seances sont produites", len(_cours) > 0, str(len(_cours)))

_recurrent = [c for c in _cours if "Session Cardio" in c["title"]]
verifier("2b. le cours recurrent produit plusieurs seances", len(_recurrent) >= 4,
         str(len(_recurrent)))
# septembre 2026 : les mercredis sont les 2, 9, 16, 23, 30
_jours = sorted({c["starts_at"][:10] for c in _recurrent})
verifier("2c. et elles tombent bien un MERCREDI (weekday JS 3, dimanche=0)",
         all(datetime.fromisoformat(j).weekday() == 2 for j in _jours), str(_jours))
verifier("2d. l'heure locale est respectee (18:30, pas 20:30)",
         all(c["starts_at"][11:16] == "18:30" for c in _recurrent),
         str([c["starts_at"] for c in _recurrent][:3]))
verifier("2e. la seance PONCTUELLE (champ `date`) est rendue une seule fois",
         len([c for c in _cours if "ponctuelle" in c["title"]]) == 1)
verifier("2f. un cours ARCHIVE ne produit rien",
         not any("archive" in c["title"] for c in _cours))
verifier("2g. un cours MASQUE ne produit rien",
         not any("masque" in c["title"] for c in _cours))
verifier("2h. le lieu est repris", any(c["location"] == "Neuchatel" for c in _recurrent))
verifier("2i. une seance n'est pas modifiable", all(c["modifiable"] is False for c in _cours))
verifier("2j. chaque seance a un identifiant DISTINCT",
         len({c["id"] for c in _recurrent}) == len(_recurrent))


# ============================================================================
print("\n3. LA FENETRE EST BORNEE")

_large = lister(**{"from": "2020-01-01T00:00:00+00:00", "to": "2030-01-01T00:00:00+00:00"})
_d = datetime.fromisoformat(_large["from"])
_f = datetime.fromisoformat(_large["to"])
verifier("3a. dix ans demandes -> 62 jours servis",
         (_f - _d).days == S.CAL1_FENETRE_MAX_JOURS, str((_f - _d).days))
verifier("3b. une fenetre inversee est remise a l'endroit",
         datetime.fromisoformat(lister(**{"from": FIN.isoformat(),
                                          "to": DEBUT.isoformat()})["from"]) <= FIN)
verifier("3c. sans fenetre, le mois courant est servi",
         bool(lancer(S.cal1_lister(RequeteFictive(jeton_=JA)))["from"]))
verifier("3d. une date illisible ne fait pas planter",
         bool(lister(**{"from": "n'importe quoi"})["from"]))


# ============================================================================
print("\n4. UNE SEULE FORME, ET DES FILTRES")

verifier("4a. les trois sources ont la MEME forme",
         len({tuple(sorted(e)) for e in _r["events"]}) == 1,
         str([sorted(e) for e in _r["events"][:2]]))
verifier("4b. le filtre par type ne garde que lui",
         all(e["event_type"] == "course" for e in lister(types="course")["events"]))
verifier("4c. un filtre `campaign` n'appelle pas les cours pour rien",
         all(e["event_type"] == "campaign" for e in lister(types="campaign")["events"]))
verifier("4d. les evenements sont tries par date",
         [e["starts_at"] for e in _r["events"]]
         == sorted(e["starts_at"] for e in _r["events"]))
verifier("4e. les types connus sont annonces",
         set(_r["types"]) == set(S.CAL1_TYPES))
# CETTE VERIFICATION BORNAIT CAL-1, ET ELLE AVAIT RAISON : declarer un type
# que rien ne savait creer aurait donne une palette pour du vide. CAL-2 a
# ouvert les taches ; le contrat s'inverse, et la propriete de fond monte d'un
# cran — le type n'est pas seulement annonce, il est CREABLE.
verifier("4f. `task` est desormais annonce (CAL-2 l'a ouvert)", "task" in _r["types"])
verifier("4f-bis. ... et il fait partie des types STOCKES, pas projetes",
         "task" in S.CAL1_TYPES_STOCKES and "task" not in S.CAL1_TYPES_PROJETES)


# ============================================================================
print("\n5. CE QU'ON PEUT CREER ICI — ET CE QU'ON NE PEUT PAS")

_b = base_neuve()
_e = creer({"title": "Appel partenariat", "starts_at": "2026-09-10T14:00:00+00:00",
            "event_type": "appointment", "description": "Suite a leur reponse"})
verifier("5a. un rendez-vous est cree", bool(_e["event"]["id"]))
verifier("5b. il est modifiable", _e["event"]["modifiable"] is True)
verifier("5c. sa source est le calendrier", _e["event"]["source"] == S.CAL1_COLLECTION)
verifier("5d. les liaisons metier existent, VIDES (CAL-3 les remplira)",
         _e["event"]["prospect_id"] is None and _e["event"]["campaign_id"] is None
         and _e["event"]["campaign_action_id"] is None)

# `task` A QUITTE CETTE LISTE : il etait refuse tant que CAL-2 n'existait pas.
# Ce qui reste interdit ici ne l'est pas par etape, mais par NATURE — une
# campagne et un cours vivent dans leurs propres collections, et les creer
# depuis le calendrier ouvrirait un second chemin de creation.
for _type, _quoi in (("campaign", "une campagne"), ("course", "un cours"),
                     ("nimporte", "un type inconnu")):
    try:
        creer({"title": "x", "starts_at": "2026-09-10T14:00:00+00:00", "event_type": _type})
        _refuse = False
    except HTTPException as ex:
        _refuse = ex.status_code == 400
    verifier("5e. creer %-22s ici -> 400" % _quoi, _refuse)

# ... et la tache, elle, se cree bien desormais.
verifier("5e-bis. creer une tache ici est desormais POSSIBLE",
         creer({"title": "Tache", "starts_at": "2026-09-10T14:00:00+00:00",
                "event_type": "task"})["event"]["event_type"] == "task")

for _corps, _quoi in (({"starts_at": "2026-09-10T14:00:00+00:00"}, "sans titre"),
                      ({"title": "x"}, "sans date"),
                      ({"title": "x", "starts_at": "pas-une-date"}, "date illisible"),
                      ({"title": "   ", "starts_at": "2026-09-10T14:00:00+00:00"}, "titre vide")):
    try:
        creer(dict(_corps, event_type="appointment"))
        _refuse = False
    except HTTPException as ex:
        _refuse = ex.status_code == 400
    verifier("5f. %-18s -> 400 (aucune date inventee)" % _quoi, _refuse)


# ============================================================================
print("\n6. MODIFICATION ET SUPPRESSION DOUCE")

_b = base_neuve()
_id = creer({"title": "A deplacer", "starts_at": "2026-09-10T14:00:00+00:00",
             "event_type": "appointment"})["event"]["id"]
_m = lancer(S.cal1_modifier(_id, RequeteFictive(jeton_=JA,
                                                corps={"title": "Deplace", "status": "confirme"})))
verifier("6a. le titre change", _m["event"]["title"] == "Deplace")
verifier("6b. le statut change", _m["event"]["status"] == "confirme")

try:
    lancer(S.cal1_modifier(_id, RequeteFictive(jeton_=JA, corps={"status": "nimporte"})))
    _refuse = False
except HTTPException as ex:
    _refuse = ex.status_code == 400
verifier("6c. un statut inconnu -> 400", _refuse)
try:
    lancer(S.cal1_modifier(_id, RequeteFictive(jeton_=JA, corps={})))
    _refuse = False
except HTTPException as ex:
    _refuse = ex.status_code == 400
verifier("6d. une modification vide -> 400", _refuse)

lancer(S.cal1_supprimer(_id, RequeteFictive(jeton_=JA)))
_doc = _b[S.CAL1_COLLECTION].documents[0]
verifier("6e. la suppression est DOUCE : le document existe encore",
         len(_b[S.CAL1_COLLECTION].documents) == 1)
verifier("6f. ... marque `is_deleted`", _doc.get("is_deleted") is True)
verifier("6g. ... et date", bool(_doc.get("deleted_at")))
verifier("6h. il disparait de la liste",
         not any(e["id"] == _id for e in lister()["events"]))
try:
    lancer(S.cal1_supprimer(_id, RequeteFictive(jeton_=JA)))
    _re = False
except HTTPException as ex:
    _re = ex.status_code == 404
verifier("6i. le supprimer deux fois -> 404, pas une seconde ecriture", _re)


# ============================================================================
print("\n7. ISOLATION PAR COACH, SUR LES QUATRE ROUTES")

_b = base_neuve()
_id = creer({"title": "Prive", "starts_at": "2026-09-10T14:00:00+00:00",
             "event_type": "appointment"})["event"]["id"]

for _f, _quoi in (
        (lambda j: lancer(S.cal1_lister(RequeteFictive(jeton_=j))), "lister"),
        (lambda j: lancer(S.cal1_creer(RequeteFictive(jeton_=j, corps={
            "title": "x", "starts_at": "2026-09-10T14:00:00+00:00",
            "event_type": "appointment"}))), "creer"),
        (lambda j: lancer(S.cal1_modifier(_id, RequeteFictive(jeton_=j, corps={"title": "y"}))), "modifier"),
        (lambda j: lancer(S.cal1_supprimer(_id, RequeteFictive(jeton_=j))), "supprimer")):
    try:
        _f(None)
        _ferme = False
    except HTTPException as ex:
        _ferme = ex.status_code in (401, 403)
    verifier("7a. %-9s SANS jeton -> refuse" % _quoi, _ferme)

try:
    lancer(S.cal1_modifier(_id, RequeteFictive(jeton_=JB, corps={"title": "vole"})))
    _ferme = False
except HTTPException as ex:
    _ferme = ex.status_code == 404
verifier("7b. un AUTRE coach ne peut pas modifier -> 404 (on ne revele rien)", _ferme)
try:
    lancer(S.cal1_supprimer(_id, RequeteFictive(jeton_=JB)))
    _ferme = False
except HTTPException as ex:
    _ferme = ex.status_code == 404
verifier("7c. ... ni supprimer -> 404", _ferme)
verifier("7d. l'evenement est intact", _b[S.CAL1_COLLECTION].documents[0]["title"] == "Prive")


# ============================================================================
print("\n8. AUCUNE MIGRATION, AUCUN GOOGLE")

# ON LIT LA CIBLE REELLE DE CHAQUE ECRITURE, par l'arbre syntaxique : le
# decoupage de chaine rendait « db » pour tout le monde et ne prouvait rien.
_CODE = BLOC[BLOC.index("CAL1_COLLECTION ="):]
_arbre = ast.parse(_CODE)
_ecrites = set()
for _n in ast.walk(_arbre):
    if isinstance(_n, ast.Call) and getattr(_n.func, "attr", "") in (
            "update_one", "update_many", "insert_one", "insert_many",
            "delete_one", "delete_many", "replace_one"):
        # `db[X].update_one(...)` -> la cible est X ; `db.y.update_one(...)` -> y
        cible = getattr(_n.func, "value", None)
        if isinstance(cible, ast.Subscript):
            _ecrites.add(ast.get_source_segment(_CODE, cible.slice) or "?")
        elif isinstance(cible, ast.Attribute):
            _ecrites.add(cible.attr)
        else:
            _ecrites.add("?")
verifier("8a. le lot n'ecrit QUE dans `calendar_events`",
         _ecrites == {"CAL1_COLLECTION"}, str(sorted(_ecrites)))
verifier("8b. AUCUNE ecriture dans campaigns ou courses",
         "db.campaigns.update" not in BLOC and "db.courses.update" not in BLOC
         and "db.campaigns.insert" not in BLOC and "db.courses.insert" not in BLOC)
verifier("8c. aucun `update_many` (donc aucune migration de masse)",
         "update_many" not in BLOC)
# LE CODE, PAS LES COMMENTAIRES : l'en-tete du bloc dit « AUCUNE DEPENDANCE
# GOOGLE », et une recherche naive mordait sur cette phrase-la.
_SANS_COMMENTAIRES = "\n".join(
    l for l in _CODE.split("\n") if not l.strip().startswith("#"))
# GOOGLE-2 A CHANGE CE QUI EST VRAI ICI, ET L'ASSERTION LE SUIT.
# Ce point garantissait que CAL-1 n'inventait pas de Google avant l'heure.
# L'heure est venue : la creation et la modification appellent desormais le
# report sortant. Ce qui doit rester vrai, et qui est verifie ci-dessous, c'est
# que CAL-1 ne DEPEND de Google pour rien — l'appel est conditionne a une
# demande explicite, et son echec ne remonte jamais a l'appelant.
verifier("8d. Google n'entre dans CAL-1 que par une demande EXPLICITE",
         _SANS_COMMENTAIRES.count("google_sync") >= 1
         and 'corps.get("google_sync")' in _SANS_COMMENTAIRES,
         "le report Google n'est pas conditionne")
verifier("8d2. aucune logique propre au calendrier ne depend de Google",
         not any(m in _SANS_COMMENTAIRES.lower()
                 for m in ("googleapis", "oauth", "gapi")),
         "CAL-1 parle directement a Google")
verifier("8e. l'ecriture Afroboost PRECEDE toujours l'appel Google",
         _SANS_COMMENTAIRES.index("insert_one")
         < _SANS_COMMENTAIRES.index('corps.get("google_sync")'),
         "Google serait appele avant l'ecriture Afroboost")
# On borne sur la fonction SUIVANTE, pas sur un nombre de caracteres : une
# longueur en dur se perime des qu'une ligne s'ajoute — ce qui vient d'arriver.
_CORPS_PATCH = SRC.split("async def cal1_modifier")[1].split("async def cal1_supprimer")[0]
verifier("8e2. un echec de Google ne remonte pas : la modification est rendue",
         "except Exception" in _CORPS_PATCH and "logger.warning" in _CORPS_PATCH
         and "raise" not in _CORPS_PATCH.split('google_sync_enabled')[-1])
verifier("8f. l'index de lecture porte une seconde cle UNIQUE (ordre total)",
         '[("coach_id", 1), ("starts_at", 1), ("id", 1)]' in SRC)
verifier("8g. `sparse` n'est pas utilise par ce lot",
         "sparse" not in SRC.split("CAL-1 — le calendrier se lit")[1][:600])


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("CAL-1 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Ecritures dans campaigns / courses : 0 — aucune migration")
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)

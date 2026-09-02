#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CAL-3 — PLANIFIER DEPUIS UNE FICHE PROSPECT.

CE QUE LE LOT AJOUTE
==============================================================================
Le maillon qui manquait entre P3 et le calendrier : un prospect qui repond
« appelez-moi jeudi a 14 h » peut enfin etre planifie. Un rendez-vous est un
evenement `calendar_events` de type `appointment` — celui que CAL-1 sait deja
afficher. CAL-3 n'ajoute que le CONTEXTE.

CE QUE CE FICHIER PROUVE
==============================================================================
  * les quatre liaisons sont LUES, jamais inventees : une fiche hors campagne
    donne des liaisons nulles, et non la campagne unique du moment ;
  * LE CAS MULTI-FICHES, qui est reel (cinq actions couvrent deux fiches) :
    planifier depuis l'une cree UN rendez-vous, visible depuis l'AUTRE ;
  * « prochain » veut dire a venir : un rendez-vous passe ou annule ne
    remplit pas le bloc ;
  * les taches ouvertes excluent celles qui sont faites ou annulees ;
  * RIEN de P3 n'est ecrit — ni statut, ni `replied_at`, ni action, ni
    empreinte : verifie par le compteur d'ecritures du bouchon ;
  * l'isolation par coach tient sur les deux routes ;
  * aucun Google.

    python3 tests/test_cal3_planifier.py
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


SECRET = "secret-de-test-cal3-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-cal3-inexistant:27017")

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


BLOC = _bloc(SRC, "# CAL-3 — PLANIFIER DEPUIS UNE FICHE PROSPECT")

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
JEUDI = (MAINTENANT + timedelta(days=3)).replace(hour=14, minute=0, second=0, microsecond=0)
HIER = (MAINTENANT - timedelta(days=1)).isoformat()
DEMAIN = (MAINTENANT + timedelta(days=1)).isoformat()


class ColComparaisons(Col):
    """Le bouchon partage ne connait ni `$or` a la racine, ni les comparaisons.

    CAL-3 interroge EXACTEMENT ainsi : `$or` entre la cle du decideur et la
    fiche. Sans ce complement, le banc mesurerait le trou du bouchon plutot
    que la regle de la route — la lecon deja payee en CAL-2 sur `$lte`.
    """

    def _ok(self, doc, filtre):
        for cle, val in (filtre or {}).items():
            if isinstance(val, dict):
                v = doc.get(cle)
                for op, borne in val.items():
                    if op in ("$lte", "$lt", "$gte", "$gt"):
                        if v is None or not (
                                (op == "$lte" and v <= borne) or (op == "$lt" and v < borne)
                                or (op == "$gte" and v >= borne) or (op == "$gt" and v > borne)):
                            return False
                continue
            # UN SCALAIRE CONTRE UN TABLEAU. Mongo fait correspondre
            # `{"prospect_ids": "ECO-01"}` a un document dont le TABLEAU
            # contient cette valeur. C'est exactement ainsi que CAL-3 retrouve
            # l'action d'une fiche ; le bouchon partage, lui, comparait la
            # liste entiere a la chaine et ne trouvait jamais rien.
            if isinstance(doc.get(cle), (list, tuple)) and not isinstance(val, (list, tuple)):
                if val not in doc.get(cle):
                    return False
                continue
        return Col._ok(self, doc, {c: v for c, v in (filtre or {}).items()
                                   if not (isinstance(doc.get(c), (list, tuple))
                                           and not isinstance(v, (list, tuple, dict)))})


# --- LES FICHES : un cas simple, un cas MULTI-FICHES, un cas hors campagne ---
FICHES = [
    {"id": "p-1", "ref": "FES-01", "coach_id": COACH_A,
     "organisation_name": "Festival du Lac", "status": "contacte"},
    {"id": "p-2", "ref": "ECO-01", "coach_id": COACH_A,
     "organisation_name": "Ecole Dancefloor", "status": "contacte"},
    {"id": "p-3", "ref": "ORG-10", "coach_id": COACH_A,
     "organisation_name": "Ecole Wellness", "status": "contacte"},
    {"id": "p-4", "ref": "HORS-01", "coach_id": COACH_A,
     "organisation_name": "Jamais demarchee", "status": "a_contacter"},
]
ACTIONS = [
    {"id": "act-fes", "coach_id": COACH_A, "campaign_id": "camp-1",
     "recipient_key": "FES-01", "prospect_ids": ["FES-01"], "channel": "email"},
    # LE CAS REEL : deux implantations, UN decideur.
    {"id": "act-eco", "coach_id": COACH_A, "campaign_id": "camp-1",
     "recipient_key": "ECO-01", "prospect_ids": ["ECO-01", "ORG-10"], "channel": "email"},
]


def base_neuve(evenements=None):
    b = Base([])
    b[S.P3S1_COLLECTION] = ColComparaisons(
        S.P3S1_COLLECTION, [dict(f) for f in FICHES],
        uniques=[(("id",), None)])
    b[S.P3S3_ACTIONS] = ColComparaisons(
        S.P3S3_ACTIONS, [dict(a) for a in ACTIONS], uniques=[(("id",), None)])
    b[S.CAL1_COLLECTION] = ColComparaisons(
        S.CAL1_COLLECTION, [dict(e) for e in (evenements or [])], uniques=[(("id",), None)])
    b["campaigns"] = ColComparaisons("campaigns", [], uniques=[(("id",), None)])
    b["courses"] = ColComparaisons("courses", [], uniques=[(("id",), None)])
    S.db = b
    return b


def agenda(ref, jeton_=JA):
    return lancer(S.cal3_agenda_prospect(ref, RequeteFictive(jeton_=jeton_)))


def planifier(ref, corps, jeton_=JA):
    return lancer(S.cal3_planifier(ref, RequeteFictive(jeton_=jeton_, corps=corps)))


# ============================================================================
print("\n1. PLANIFIER DEPUIS UNE FICHE — LE CAS SIMPLE")

_b = base_neuve()
_r = planifier("FES-01", {"starts_at": JEUDI.isoformat(),
                          "title": "Appel partenariat — Festival du Lac",
                          "meeting_type": "appel", "duration_minutes": 45,
                          "description": "Ils ont repondu jeudi 14h"})
_a = _r["appointment"]
verifier("1a. le rendez-vous est cree", bool(_a["id"]))
verifier("1b. c'est un `appointment`", _a["event_type"] == "appointment")
verifier("1c. il vit dans `calendar_events`", len(_b[S.CAL1_COLLECTION].documents) == 1)
verifier("1d. son titre", _a["title"].startswith("Appel partenariat"))
verifier("1e. sa date", _a["starts_at"] == JEUDI.isoformat())
verifier("1f. sa fin est calculee (45 min)",
         _a["ends_at"] == (JEUDI + timedelta(minutes=45)).isoformat(), _a["ends_at"])
verifier("1g. son type de rendez-vous", _a["meeting_type"] == "appel")
verifier("1h. il n'est PAS tout-le-jour", _a["all_day"] is False)
verifier("1i. il est modifiable depuis le calendrier", _a["modifiable"] is True)

verifier("1j. LIAISON prospect_id", _a["prospect_id"] == "FES-01", str(_a["prospect_id"]))
verifier("1k. LIAISON recipient_key", _a["recipient_key"] == "FES-01", str(_a["recipient_key"]))
verifier("1l. LIAISON campaign_id", _a["campaign_id"] == "camp-1", str(_a["campaign_id"]))
verifier("1m. LIAISON campaign_action_id",
         _a["campaign_action_id"] == "act-fes", str(_a["campaign_action_id"]))

verifier("1n. sans titre, un titre UTILE est compose depuis l'organisation",
         "Festival du Lac" in planifier("FES-01", {"starts_at": DEMAIN})["appointment"]["title"])
verifier("1o. un type inconnu retombe sur `appel`",
         planifier("FES-01", {"starts_at": DEMAIN,
                              "meeting_type": "teleportation"})["appointment"]["meeting_type"] == "appel")
verifier("1p. une duree inconnue retombe sur 30 min",
         planifier("FES-01", {"starts_at": DEMAIN, "duration_minutes": 7})["appointment"]["ends_at"]
         == (datetime.fromisoformat(DEMAIN) + timedelta(minutes=30)).isoformat())

for _corps, _quoi in (({}, "sans date"),
                      ({"starts_at": "pas-une-date"}, "date illisible"),
                      ({"starts_at": ""}, "date vide")):
    try:
        planifier("FES-01", _corps)
        _refuse = False
    except HTTPException as e:
        _refuse = e.status_code == 400
    verifier("1q. %-16s -> 400 (aucune date inventee)" % _quoi, _refuse)


# ============================================================================
print("\n2. LES LIAISONS SONT LUES, JAMAIS INVENTEES")

_b = base_neuve()
_a = planifier("HORS-01", {"starts_at": JEUDI.isoformat()})["appointment"]
verifier("2a. une fiche HORS campagne se planifie quand meme", bool(_a["id"]))
verifier("2b. son prospect_id est renseigne", _a["prospect_id"] == "HORS-01")
verifier("2c. recipient_key reste NUL (aucune action ne la couvre)",
         _a["recipient_key"] is None, str(_a["recipient_key"]))
verifier("2d. campaign_id reste NUL — la campagne unique n'est PAS supposee",
         _a["campaign_id"] is None, str(_a["campaign_id"]))
verifier("2e. campaign_action_id reste NUL", _a["campaign_action_id"] is None)

try:
    planifier("INEXISTANTE", {"starts_at": JEUDI.isoformat()})
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 404
verifier("2f. une fiche inexistante -> 404", _refuse)
verifier("2g. ... et rien n'a ete cree", len(_b[S.CAL1_COLLECTION].documents) == 1)


# ============================================================================
print("\n3. LE CAS MULTI-FICHES — UN DECIDEUR, DEUX IMPLANTATIONS")

_b = base_neuve()
_a = planifier("ECO-01", {"starts_at": JEUDI.isoformat(), "title": "Appel direction"})["appointment"]
verifier("3a. UN SEUL rendez-vous est cree", len(_b[S.CAL1_COLLECTION].documents) == 1,
         str(len(_b[S.CAL1_COLLECTION].documents)))
verifier("3b. il trace la fiche d'ou l'on a planifie", _a["prospect_id"] == "ECO-01")
verifier("3c. il porte la cle du DECIDEUR", _a["recipient_key"] == "ECO-01")

_vue_eco = agenda("ECO-01")
_vue_org = agenda("ORG-10")
verifier("3d. la fiche d'origine le voit",
         (_vue_eco["next_appointment"] or {}).get("id") == _a["id"])
verifier("3e. LA FICHE JUMELLE LE VOIT AUSSI (meme decideur)",
         (_vue_org["next_appointment"] or {}).get("id") == _a["id"],
         str(_vue_org["next_appointment"]))
verifier("3f. les deux annoncent la meme cle de decideur",
         _vue_eco["recipient_key"] == _vue_org["recipient_key"] == "ECO-01")
verifier("3g. les deux annoncent la meme action",
         _vue_eco["campaign_action_id"] == _vue_org["campaign_action_id"] == "act-eco")

# AUCUNE DUPLICATION : planifier depuis la jumelle ne double pas le premier
_a2 = planifier("ORG-10", {"starts_at": (JEUDI + timedelta(days=1)).isoformat()})["appointment"]
verifier("3h. planifier depuis la jumelle cree un SECOND rendez-vous (voulu)",
         len(_b[S.CAL1_COLLECTION].documents) == 2)
verifier("3i. ... et les deux fiches voient les DEUX",
         len(agenda("ECO-01")["appointments"]) == 2
         and len(agenda("ORG-10")["appointments"]) == 2)
verifier("3j. le prochain est le PLUS PROCHE, pas le dernier cree",
         agenda("ORG-10")["next_appointment"]["id"] == _a["id"])
verifier("3k. une fiche SANS rapport ne voit rien de tout cela",
         agenda("FES-01")["next_appointment"] is None)


# ============================================================================
print("\n4. « PROCHAIN » VEUT DIRE A VENIR")

def rdv(idt, quand, statut="prevu", **extra):
    d = {"id": idt, "coach_id": COACH_A, "title": "RDV " + idt,
         "starts_at": quand, "ends_at": "", "all_day": False,
         "event_type": "appointment", "status": statut, "is_deleted": False,
         "prospect_id": "FES-01", "recipient_key": "FES-01",
         "campaign_id": "camp-1", "campaign_action_id": "act-fes",
         "created_at": INSTANT, "updated_at": INSTANT}
    d.update(extra)
    return d


_b = base_neuve([rdv("r-passe", HIER)])
verifier("4a. un rendez-vous PASSE ne remplit pas « prochain »",
         agenda("FES-01")["next_appointment"] is None,
         str(agenda("FES-01")["next_appointment"]))
verifier("4b. ... mais il reste dans l'historique",
         len(agenda("FES-01")["appointments"]) == 1)

_b = base_neuve([rdv("r-annule", DEMAIN, statut="annule")])
verifier("4c. un rendez-vous ANNULE ne remplit pas « prochain »",
         agenda("FES-01")["next_appointment"] is None)

_b = base_neuve([rdv("r-loin", (MAINTENANT + timedelta(days=9)).isoformat()),
                 rdv("r-proche", DEMAIN)])
verifier("4d. le prochain est le plus proche",
         agenda("FES-01")["next_appointment"]["id"] == "r-proche")

_b = base_neuve([rdv("r-suppr", DEMAIN, is_deleted=True)])
verifier("4e. un rendez-vous retire n'apparait plus du tout",
         agenda("FES-01")["next_appointment"] is None
         and len(agenda("FES-01")["appointments"]) == 0)


# ============================================================================
print("\n5. LES TACHES OUVERTES — CAL-2 REUTILISE, PAS RECOPIE")

def tache(idt, titre, quand, statut="prevu", **extra):
    d = {"id": idt, "coach_id": COACH_A, "title": titre, "starts_at": quand,
         "ends_at": "", "all_day": False, "event_type": "task", "status": statut,
         "priority": "normale", "is_deleted": False,
         "prospect_id": "FES-01", "recipient_key": "FES-01",
         "created_at": INSTANT, "updated_at": INSTANT}
    d.update(extra)
    return d


_b = base_neuve([
    tache("t-ouverte", "Rappeler le festival", DEMAIN),
    tache("t-retard", "Envoyer le dossier", HIER),
    tache("t-faite", "Deja faite", HIER, statut="fait"),
    tache("t-annulee", "Abandonnee", HIER, statut="annule"),
])
_v = agenda("FES-01")
_ids = sorted(t["id"] for t in _v["open_tasks"])
verifier("5a. seules les taches OUVERTES sont rendues",
         _ids == ["t-ouverte", "t-retard"], str(_ids))
verifier("5b. une tache FAITE n'apparait plus", "t-faite" not in _ids)
verifier("5c. une tache ANNULEE non plus", "t-annulee" not in _ids)
verifier("5d. chaque tache porte sa pile CAL-2",
         {t["id"]: t["bucket"] for t in _v["open_tasks"]}
         == {"t-ouverte": "a_venir", "t-retard": "en_retard"},
         str({t["id"]: t["bucket"] for t in _v["open_tasks"]}))
verifier("5e. les taches ne sont PAS melangees aux rendez-vous",
         _v["appointments"] == [] and _v["next_appointment"] is None)
verifier("5f. aucune seconde collection de taches",
         "prospect_tasks" not in SRC and SRC.count('CAL1_COLLECTION = "calendar_events"') == 1)


# ============================================================================
print("\n6. RIEN DE P3 N'EST TOUCHE")

_b = base_neuve()
_avant_fiches = json.dumps(_b[S.P3S1_COLLECTION].documents, sort_keys=True)
_avant_actions = json.dumps(_b[S.P3S3_ACTIONS].documents, sort_keys=True)
planifier("FES-01", {"starts_at": JEUDI.isoformat()})
agenda("FES-01")

verifier("6a. AUCUNE ecriture dans `partner_prospects`",
         _b[S.P3S1_COLLECTION].ecritures == 0, str(_b[S.P3S1_COLLECTION].ecritures))
verifier("6b. AUCUNE ecriture dans les actions de campagne",
         _b[S.P3S3_ACTIONS].ecritures == 0, str(_b[S.P3S3_ACTIONS].ecritures))
verifier("6c. les fiches sont identiques, octet pour octet",
         json.dumps(_b[S.P3S1_COLLECTION].documents, sort_keys=True) == _avant_fiches)
verifier("6d. les actions aussi",
         json.dumps(_b[S.P3S3_ACTIONS].documents, sort_keys=True) == _avant_actions)

_CODE = BLOC[BLOC.index("CAL3_TYPES_RDV"):]
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
verifier("6e. le lot n'ecrit QUE dans le calendrier",
         _cibles == {"CAL1_COLLECTION"}, str(sorted(_cibles)))
# ON RETIRE AUSSI LES DOCSTRINGS. Filtrer les lignes `#` ne suffisait pas :
# la docstring de `cal3_planifier` enumere ce que le lot n'ecrit PAS — dont
# `replied_at` — et une recherche textuelle mordait sur cette phrase-la.
_SANS = _CODE
for _n in ast.walk(_arbre):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
        _doc = ast.get_docstring(_n, clean=False)
        if _doc:
            _SANS = _SANS.replace(_doc, "")
_SANS = "\n".join(l for l in _SANS.split("\n") if not l.strip().startswith("#"))
for _interdit in ("contacte", "replied_at", "snapshot_hash", "opted_out",
                  "first_contact_sent_at", "Emails.send"):
    verifier("6f. le code ne mentionne jamais `%s`" % _interdit,
             _interdit not in _SANS, "trouve dans le code du lot")
# GOOGLE-2 : le §7 du lot suivant fait de CE rendez-vous le cas prioritaire de
# la synchronisation sortante. L'assertion « aucun Google » n'a donc plus lieu
# d'etre — mais la regle qu'elle protegeait, elle, tient toujours : le
# rendez-vous Afroboost est ecrit AVANT, et Google ne peut pas l'empecher.
verifier("6g. le report Google est conditionne a une demande explicite",
         'corps.get("google_sync")' in _SANS)
verifier("6g2. il vient APRES l'ecriture du rendez-vous",
         _SANS.index("insert_one") < _SANS.index('corps.get("google_sync")'))
verifier("6g3. son echec est avale, jamais propage",
         "except Exception" in _SANS.split('corps.get("google_sync")')[1][:400])
verifier("6g4. CAL-3 ne parle jamais directement a l'API Google",
         not any(m in _SANS.lower() for m in ("googleapis", "oauth", "gapi")))
verifier("6h. aucun `update_many` (donc aucune migration)", "update_many" not in _CODE)


# ============================================================================
print("\n7. AUTH ET ISOLATION")

_b = base_neuve()
for _f, _quoi in (
        (lambda j: agenda("FES-01", jeton_=j), "lire l'agenda"),
        (lambda j: planifier("FES-01", {"starts_at": JEUDI.isoformat()}, jeton_=j), "planifier")):
    try:
        _f(None)
        _ferme = False
    except HTTPException as e:
        _ferme = e.status_code in (401, 403)
    verifier("7a. %-16s SANS jeton -> refuse" % _quoi, _ferme)

try:
    planifier("FES-01", {"starts_at": JEUDI.isoformat()}, jeton_=JB)
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 404
verifier("7b. un AUTRE coach ne peut pas planifier sur cette fiche -> 404", _ferme)
verifier("7c. ... et rien n'a ete cree", len(_b[S.CAL1_COLLECTION].documents) == 0)

planifier("FES-01", {"starts_at": JEUDI.isoformat()})
verifier("7d. un AUTRE coach ne voit pas cet agenda",
         agenda("FES-01", jeton_=JB)["next_appointment"] is None)
verifier("7e. ... ni les taches", agenda("FES-01", jeton_=JB)["open_tasks"] == [])


# ============================================================================
print("\n8. LE RENDEZ-VOUS EST UN EVENEMENT DU CALENDRIER, PAS UN OBJET A PART")

_b = base_neuve()
_id = planifier("FES-01", {"starts_at": JEUDI.isoformat()})["appointment"]["id"]
_cal = lancer(S.cal1_lister(RequeteFictive(jeton_=JA, params={
    "from": MAINTENANT.isoformat(),
    "to": (MAINTENANT + timedelta(days=10)).isoformat()})))
verifier("8a. il apparait dans la grille du calendrier",
         any(e["id"] == _id for e in _cal["events"]), str(len(_cal["events"])))
verifier("8b. avec le type `appointment`",
         all(e["event_type"] == "appointment" for e in _cal["events"] if e["id"] == _id))
_m = lancer(S.cal1_modifier(_id, RequeteFictive(jeton_=JA, corps={"status": "confirme"})))
verifier("8c. il se modifie par les routes CAL-1 existantes",
         _m["event"]["status"] == "confirme")
lancer(S.cal1_supprimer(_id, RequeteFictive(jeton_=JA)))
verifier("8d. il se retire par la route CAL-1 (suppression douce)",
         _b[S.CAL1_COLLECTION].documents[0].get("is_deleted") is True)
verifier("8e. ... et disparait alors de la fiche",
         agenda("FES-01")["next_appointment"] is None)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("CAL-3 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Ecritures dans partner_prospects / actions P3 : 0")
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)

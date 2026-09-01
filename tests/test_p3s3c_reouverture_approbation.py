#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S3-C — ROUVRIR UNE CAMPAGNE, ET L'APPROUVER UNE SEULE FOIS.

LE DEFAUT QUE CE LOT FERME
==============================================================================
L'ecran envoyait comme cle d'idempotence l'identifiant de son APERCU — un uuid
NEUF a chaque clic sur « Preparer ». Un double clic sur « Creer » etait donc
protege, mais la suite Preparer -> Creer -> Preparer -> Creer fabriquait DEUX
campagnes pour un seul lancement, chacune avec ses 137 actions. Deux campagnes
ouvertes sur les memes destinataires, c'est la porte ouverte au double premier
contact.

La protection est SERVEUR : une interface ne protege personne d'un appel
direct, d'un retour arriere ou d'un onglet oublie.

CE QUE CE FICHIER PROUVE
==============================================================================
  * une campagne OUVERTE est rendue au lieu d'etre dupliquee — quelle que soit
    la cle d'idempotence ;
  * une campagne CLOSE ne bloque PAS un lancement futur (la garde n'est pas
    « un coach n'aura jamais qu'une campagne ») ;
  * `allow_new` laisse le coach trancher explicitement ;
  * l'approbation est idempotente PAR ECRITURE CONDITIONNELLE, et la condition
    porte sur `approved_at: None` — pas sur `$exists`, puisque le champ existe
    des la creation avec la valeur nulle ;
  * approuver n'envoie rien, ne reserve rien, ne contacte personne ;
  * apres approbation le snapshot est FIGE, et l'empreinte le prouve.

AUCUNE ECRITURE EN PRODUCTION. Tout se joue en memoire.

    python3 tests/test_p3s3c_reouverture_approbation.py
"""
import ast
import asyncio
import io
import json
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


SECRET = "secret-de-test-p3s3c-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3s3c-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"

# Le banc de P3-S3-B est reutilise tel quel : meme bouchon, memes fiches, memes
# index honores. Deux bancs divergeraient, et le second finirait par mentir.
_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
ErreurUnicite = _espace["ErreurUnicite"]
BaseBouchon = _espace["BaseBouchon"]
fiche = _espace["fiche"]
FICHES = _espace["FICHES"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]

JA = jeton(COACH_A)
JB = jeton(COACH_B)


def base_neuve():
    b = BaseBouchon([dict(f) for f in FICHES])
    S.db = b
    return b


def preparer(**corps):
    return lancer(S.p3s3_preparer_campagne(RequeteFictive(jeton_=JA, corps=corps)))


def approuver(identifiant, jeton_=None):
    return lancer(S.p3s3_approuver_campagne(
        identifiant, RequeteFictive(jeton_=jeton_ or JA, corps={})))


# ============================================================================
print("\n1. LE CONTRAT — LES ETATS OUVERTS, ET RIEN DE NOUVEAU")

verifier("1a. les etats ouverts sont definis",
         S.P3S3_ETATS_OUVERTS == ("preparee", "approuvee", "en_cours"),
         str(S.P3S3_ETATS_OUVERTS))
verifier("1b. ils sont tous des etats DEJA connus de P3-S3-A",
         set(S.P3S3_ETATS_OUVERTS) <= set(S.P3S3_ETATS_CAMPAGNE))
verifier("1c. `terminee` et `annulee` ne sont PAS ouverts (elles ne bloquent rien)",
         not {"terminee", "annulee"} & set(S.P3S3_ETATS_OUVERTS))
verifier("1d. AUCUN nouvel etat de campagne n'a ete invente",
         S.P3S3_ETATS_CAMPAGNE == ("brouillon", "preparee", "approuvee",
                                   "en_cours", "terminee", "annulee"))
verifier("1e. les 6 statuts metier de P3-S1 restent intacts",
         S.P3S1_STATUTS == ("a_contacter", "contacte", "repondu", "interesse",
                            "sans_reponse_pause", "refuse"))

CHEMINS = [r.path for r in S.app.routes if "prospect-campaigns" in getattr(r, "path", "")]
verifier("1f. cinq routes de campagne, pas une de plus", len(CHEMINS) == 5, str(CHEMINS))
for _interdit in ("send", "launch", "dispatch", "execute", "retry", "j3", "j7"):
    verifier("1g. aucune route contenant %r" % _interdit,
             not any(_interdit in c for c in CHEMINS))


# ============================================================================
print("\n2. PAS DE DEUXIEME CAMPAGNE POUR UN MEME LANCEMENT")

# cas 1 — aucune campagne ouverte : la creation passe.
_b = base_neuve()
_un = preparer(dry_run=False, name="P3-LAUNCH", idempotency_key="cle-1")
verifier("2a. cas 1 — aucune campagne ouverte : la campagne est CREEE",
         _un["rejeu"] is False and len(_b["prospect_campaigns"].documents) == 1)
_id = _un["campaign"]["id"]

# cas 2 — une campagne preparee existe : une preparation EQUIVALENTE la rend.
_deux = preparer(dry_run=False, name="P3-LAUNCH", idempotency_key="cle-1")
verifier("2b. cas 2 — meme cle : la campagne existante est rendue",
         _deux["rejeu"] is True and _deux["campaign"]["id"] == _id)

# cas 3/4 — LE DEFAUT REEL : une cle DIFFERENTE (uuid neuf de l'apercu).
_trois = preparer(dry_run=False, name="P3-LAUNCH", idempotency_key="uuid-tout-neuf-1")
verifier("2c. cas 4 — cle DIFFERENTE : la campagne ouverte est rendue, pas dupliquee",
         _trois["rejeu"] is True and _trois.get("reouverte") is True
         and _trois["campaign"]["id"] == _id, str(_trois.get("campaign", {}).get("id")))
_quatre = preparer(dry_run=False, name="AUTRE NOM", idempotency_key="uuid-tout-neuf-2")
verifier("2d. ... meme avec un autre nom", _quatre["campaign"]["id"] == _id)
verifier("2e. une seule campagne en base apres 4 preparations",
         len(_b["prospect_campaigns"].documents) == 1,
         str(len(_b["prospect_campaigns"].documents)))
verifier("2f. 8 actions, pas 16 ni 32",
         len(_b["prospect_campaign_actions"].documents) == 8)

# cas 3 — double clic sans aucune cle : toujours une seule.
_b2 = base_neuve()
preparer(dry_run=False)
preparer(dry_run=False)
preparer(dry_run=False)
verifier("2g. cas 3 — trois preparations SANS cle : une seule campagne",
         len(_b2["prospect_campaigns"].documents) == 1,
         str(len(_b2["prospect_campaigns"].documents)))

# La garde est PAR COACH. COACH_B n'a aucun prospect ici : sa preparation doit
# echouer pour CETTE raison, jamais parce que COACH_A a une campagne ouverte.
try:
    lancer(S.p3s3_preparer_campagne(RequeteFictive(jeton_=JB, corps={"dry_run": False})))
    _motif = "aucune erreur"
except HTTPException as e:
    _motif = str(e.detail)
verifier("2h. la garde ne deborde pas sur un autre coach (refus pour absence de prospect)",
         "Aucun prospect" in _motif, _motif)
verifier("2h-bis. la garde est explicitement filtree par coach_id",
         '{"coach_id": appelant, "etat": {"$in": list(P3S3_ETATS_OUVERTS)}}' in SRC)


# ============================================================================
print("\n3. LA GARDE NE BLOQUE PAS LES CAMPAGNES FUTURES")

# cas 5 — campagne CLOSE : une nouvelle est possible, sans aucun drapeau.
for _etat in ("terminee", "annulee"):
    _b = base_neuve()
    preparer(dry_run=False, idempotency_key="c-" + _etat)
    _b["prospect_campaigns"].documents[0]["etat"] = _etat
    _neuve = preparer(dry_run=False, idempotency_key="suivante-" + _etat)
    verifier("3a. cas 5 — apres une campagne %-9s une NOUVELLE est creee" % _etat,
             _neuve["rejeu"] is False and len(_b["prospect_campaigns"].documents) == 2,
             str(len(_b["prospect_campaigns"].documents)))

# `allow_new` : le coach tranche explicitement, comme `allow_duplicate` en P3-S1.
_b = base_neuve()
preparer(dry_run=False, idempotency_key="a")
_forcee = preparer(dry_run=False, idempotency_key="b", allow_new=True)
verifier("3b. `allow_new: true` cree deliberement une seconde campagne",
         _forcee["rejeu"] is False and len(_b["prospect_campaigns"].documents) == 2)
verifier("3c. ... et la machine n'a donc jamais tranche toute seule",
         "allow_new" in SRC)

# Une campagne ouverte n'empeche pas de SIMULER.
_b = base_neuve()
_c = preparer(dry_run=False, idempotency_key="x")
_sim = preparer(dry_run=True)
verifier("3d. le dry-run reste possible malgre une campagne ouverte",
         _sim["dry_run"] is True and len(_b["prospect_campaigns"].documents) == 1)
verifier("3e. ... et il SIGNALE la campagne ouverte, pour proposer de la rouvrir",
         _sim.get("campagne_ouverte") is not None
         and _sim["campagne_ouverte"]["id"] == _c["campaign"]["id"])


# ============================================================================
print("\n4. ROUVRIR : LIRE, JAMAIS RECREER")

_b = base_neuve()
_c = preparer(dry_run=False, idempotency_key="ouverture")
_lu = lancer(S.p3s3_lire_campagne(_c["campaign"]["id"], RequeteFictive(jeton_=JA)))
verifier("4a. la campagne se relit avec ses actions",
         _lu["campaign"]["id"] == _c["campaign"]["id"] and len(_lu["actions"]) == 8)
verifier("4b. la relecture n'ecrit RIEN",
         _b["prospect_campaigns"].ecritures == 1 and
         _b["prospect_campaign_actions"].ecritures == 8)
_liste = lancer(S.p3s3_lister_campagnes(RequeteFictive(jeton_=JA, params={"ouvertes": "1"})))
verifier("4c. la liste des campagnes OUVERTES rend la campagne preparee",
         _liste["total"] == 1 and _liste["campaigns"][0]["etat"] == "preparee")
_b["prospect_campaigns"].documents[0]["etat"] = "terminee"
_liste = lancer(S.p3s3_lister_campagnes(RequeteFictive(jeton_=JA, params={"ouvertes": "1"})))
verifier("4d. une campagne TERMINEE ne figure plus parmi les ouvertes",
         _liste["total"] == 0)
_liste = lancer(S.p3s3_lister_campagnes(RequeteFictive(jeton_=JA, params={"etat": "terminee"})))
verifier("4e. ... mais reste lisible par son etat", _liste["total"] == 1)
try:
    lancer(S.p3s3_lister_campagnes(RequeteFictive(jeton_=JA, params={"etat": "inconnu"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("4f. un etat inconnu est REFUSE, jamais ignore en silence", _refuse)


# ============================================================================
print("\n5. APPROUVER — UNE FOIS, ET SANS RIEN ENVOYER")

_b = base_neuve()
_c = preparer(dry_run=False, idempotency_key="appro")
_id = _c["campaign"]["id"]
_avant_ecritures = _b.total_ecritures()

_a = approuver(_id)
verifier("5a. l'approbation passe", _a["deja_approuvee"] is False)
_camp = _b["prospect_campaigns"].documents[0]
verifier("5b. l'etat devient `approuvee`", _camp["etat"] == "approuvee", _camp["etat"])
verifier("5c. approved_at est pose", bool(_camp["approved_at"]))
verifier("5d. approved_by est le coach appelant", _camp["approved_by"] == COACH_A)
verifier("5e. une empreinte du snapshot est figee",
         bool(_camp.get("snapshot_hash")) and len(_camp["snapshot_hash"]) == 64)

# APPROUVER N'EST PAS ENVOYER, ET N'EST PAS RESERVER.
_acts = _b["prospect_campaign_actions"].documents
verifier("5f. AUCUNE action ne porte verrou_actif", not any("verrou_actif" in a for a in _acts))
verifier("5g. AUCUNE action ne porte claimed_at", not any("claimed_at" in a for a in _acts))
verifier("5h. AUCUNE action ne porte sent_at", not any("sent_at" in a for a in _acts))
verifier("5i. AUCUN provider_message_id", not any(a.get("provider_message_id") for a in _acts))
verifier("5j. 0 ecriture dans partner_prospects", _b["partner_prospects"].ecritures == 0)
verifier("5k. les fiches restent `a_contacter`",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("5l. first_contact_claimed_at ecrit sur 0 fiche",
         not any("first_contact_claimed_at" in f for f in _b["partner_prospects"].documents))
verifier("5m. first_contact_sent_at ecrit sur 0 fiche",
         not any("first_contact_sent_at" in f for f in _b["partner_prospects"].documents))
verifier("5n. AUCUNE autre collection n'a ete ecrite",
         _b.total_ecritures(sauf=("prospect_campaigns", "prospect_campaign_actions",)) == 0)
verifier("5o. la porte d'envoi reste fermee",
         S.p3s3_envoi_autorise({"P3_LAUNCH_ENABLED": False,
                                "P3_LAUNCH_ENVOI_REEL": False}) is False)


# ============================================================================
print("\n6. L'APPROBATION EST IDEMPOTENTE")

_date = _camp["approved_at"]
_par = _camp["approved_by"]
_empreinte = _camp["snapshot_hash"]
_b2 = approuver(_id)
_b3 = approuver(_id)
verifier("6a. le 2e appel dit `deja_approuvee`", _b2["deja_approuvee"] is True)
verifier("6b. le 3e aussi", _b3["deja_approuvee"] is True)
_camp = _b["prospect_campaigns"].documents[0]
verifier("6c. approved_at n'a PAS bouge", _camp["approved_at"] == _date)
verifier("6d. approved_by n'a PAS bouge", _camp["approved_by"] == _par)
verifier("6e. l'empreinte n'a PAS bouge", _camp["snapshot_hash"] == _empreinte)
verifier("6f. une seule campagne, toujours", len(_b["prospect_campaigns"].documents) == 1)

# La garde porte sur `approved_at: None`, pas sur `$exists` — le champ EXISTE
# des la creation avec la valeur nulle, un `$exists` ne garderait rien.
verifier("6g. la garde atomique porte sur `approved_at: None`",
         '{"id": identifiant, "approved_at": None}' in SRC)
verifier("6h. elle NE porte PAS sur `$exists` (qui serait toujours vrai)",
         '"approved_at": {"$exists": False}' not in SRC)
verifier("6i. le champ existe bien des la creation, a None",
         '"approved_at": None, "approved_by": None' in SRC)


# ============================================================================
print("\n7. LE SNAPSHOT EST FIGE APRES APPROBATION")

_cible = _acts[0]
try:
    lancer(S.p3s3_modifier_action(_id, _cible["id"],
                                  RequeteFictive(jeton_=JA, corps={"message_j0": "PIRATE"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("7a. modifier un MESSAGE apres approbation : refuse (409)", _refuse)
for _corps, _quoi in (({"channel": "instagram"}, "canal"),
                      ({"backup_channel": "email"}, "canal de secours"),
                      ({"excluded": True}, "exclusion")):
    try:
        lancer(S.p3s3_modifier_action(_id, _cible["id"], RequeteFictive(jeton_=JA, corps=_corps)))
        _refuse = False
    except HTTPException as e:
        _refuse = e.status_code == 409
    verifier("7b. modifier le %-16s apres approbation : refuse (409)" % _quoi, _refuse)
verifier("7c. le message approuve est intact",
         _b["prospect_campaign_actions"].documents[0]["message_j0"] == _cible["message_j0"])
verifier("7d. l'empreinte correspond toujours au contenu",
         S.p3s3_empreinte(_b["prospect_campaign_actions"].documents) == _empreinte)

# L'empreinte est PURE et ne couvre que ce qui partira.
_bouge = [dict(a) for a in _acts]
_bouge[0] = dict(_bouge[0], updated_at="2099-01-01", statut="pret")
verifier("7e. l'empreinte ignore les horodatages",
         S.p3s3_empreinte(_bouge) == _empreinte)
_bouge[0] = dict(_bouge[0], message_j0="autre chose")
verifier("7f. ... mais change si LE MESSAGE change",
         S.p3s3_empreinte(_bouge) != _empreinte)
_bouge = [dict(a) for a in _acts]
_bouge[0] = dict(_bouge[0], channel="instagram")
verifier("7g. ... et si LE CANAL change", S.p3s3_empreinte(_bouge) != _empreinte)
verifier("7h. l'ordre des actions ne change pas l'empreinte",
         S.p3s3_empreinte(list(reversed(_acts))) == _empreinte)


# ============================================================================
print("\n8. EDITION AVANT APPROBATION, ET EXCLUSIONS")

_b = base_neuve()
_c = preparer(dry_run=False, idempotency_key="edition")
_id = _c["campaign"]["id"]
_acts = _b["prospect_campaign_actions"].documents
_cible = next(a for a in _acts if a["recipient_key"] == "GVA-F3")

_r = lancer(S.p3s3_modifier_action(_id, _cible["id"],
                                   RequeteFictive(jeton_=JA, corps={"message_j0": "corrige"})))
verifier("8a. avant approbation, le message reste modifiable",
         _r["action"]["message_j0"] == "corrige")
verifier("8b. la FICHE source n'a pas bouge",
         next(f for f in _b["partner_prospects"].documents
              if f["ref"] == "GVA-F3")["j0_message"] == "Bonjour Wellness Geneve")

_r = lancer(S.p3s3_modifier_action(_id, _cible["id"],
                                   RequeteFictive(jeton_=JA, corps={"excluded": True})))
verifier("8c. exclure retire le destinataire du resume",
         _r["summary"]["destinataires"] == 7 and _r["summary"]["exclus"] == 1)
verifier("8d. l'exclu reste `a_contacter` dans partner_prospects",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("8e. l'exclu reste dans la campagne, trace",
         len(_b["prospect_campaign_actions"].documents) == 8)

_a = approuver(_id)
verifier("8f. l'approbation ne retient QUE les non-exclus",
         _a["summary"]["destinataires"] == 7 and _a["summary"]["exclus"] == 1)
verifier("8g. nb_destinataires de la campagne suit l'exclusion",
         _b["prospect_campaigns"].documents[0]["nb_destinataires"] == 7)
verifier("8h. l'empreinte ignore l'action exclue",
         S.p3s3_empreinte(_b["prospect_campaign_actions"].documents) ==
         S.p3s3_empreinte([a for a in _b["prospect_campaign_actions"].documents
                           if a["statut"] != "exclu"]))

# Tout exclure : il n'y a plus rien a approuver.
_b = base_neuve()
_c = preparer(dry_run=False, idempotency_key="tout-exclu")
for _a2 in list(_b["prospect_campaign_actions"].documents):
    lancer(S.p3s3_modifier_action(_c["campaign"]["id"], _a2["id"],
                                  RequeteFictive(jeton_=JA, corps={"excluded": True})))
try:
    approuver(_c["campaign"]["id"])
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("8i. approuver une campagne SANS destinataire retenu : refuse (400)", _refuse)


# ============================================================================
print("\n9. LANGUES ET MESSAGES — RIEN N'EST SUPPOSE")

_b = base_neuve()
_c = preparer(dry_run=False, idempotency_key="langues")
_acts = _b["prospect_campaign_actions"].documents
_par = {a["recipient_key"]: a for a in _acts}
verifier("9a. ZURICH garde son message ALLEMAND",
         _par["ZRH-D3"]["message_j0"] == "Guten Tag, wir sind Afroboost")
verifier("9b. ZURICH garde sa langue", _par["ZRH-D3"]["language"] == "allemand")
verifier("9c. la traduction FR reste A PART, jamais a la place",
         _par["ZRH-D3"]["j0_fr_translation"] != _par["ZRH-D3"]["message_j0"])
verifier("9d. une langue absente reste ABSENTE — jamais devinee francaise",
         (_par["BAR-09"]["language"] or "") == "")
approuver(_c["campaign"]["id"])
_acts = _b["prospect_campaign_actions"].documents
_par = {a["recipient_key"]: a for a in _acts}
verifier("9e. l'approbation n'a traduit ni reecrit AUCUN message",
         _par["ZRH-D3"]["message_j0"] == "Guten Tag, wir sind Afroboost"
         and (_par["BAR-09"]["language"] or "") == "")


# ============================================================================
print("\n10. AUTHENTIFICATION ET CLOISONNEMENT")

_b = base_neuve()
_c = preparer(dry_run=False, idempotency_key="auth")
_id = _c["campaign"]["id"]
try:
    lancer(S.p3s3_approuver_campagne(_id, RequeteFictive(corps={})))
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code in (401, 403)
verifier("10a. approuver SANS jeton -> refuse", _ferme)
try:
    approuver(_id, jeton_=JB)
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 403
verifier("10b. approuver la campagne d'un AUTRE coach -> 403", _ferme)
try:
    approuver("campagne-inexistante")
    _quatrecent = False
except HTTPException as e:
    _quatrecent = e.status_code == 404
verifier("10c. approuver une campagne inconnue -> 404", _quatrecent)
_b["prospect_campaigns"].documents[0]["etat"] = "annulee"
try:
    approuver(_id)
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("10d. approuver une campagne ANNULEE -> 409", _refuse)


# ============================================================================
print("\n11. IL RESTE IMPOSSIBLE D'ENVOYER")

ARBRE_SRV = ast.parse(SRC)
_NOEUD = next(n for n in ast.walk(ARBRE_SRV)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == "p3s3_approuver_campagne")
BLOC = ast.get_source_segment(SRC, _NOEUD) or ""
_appeles = set()
for _n in ast.walk(_NOEUD):
    if isinstance(_n, ast.Call):
        _appeles.add(getattr(_n.func, "id", None) or getattr(_n.func, "attr", None))
    if isinstance(_n, ast.Attribute):
        _appeles.add(_n.attr)
_appeles.discard(None)
for _interdit in ("send_email", "send_bulk_email", "_send_whatsapp_meta", "send_push",
                  "send_push_by_email", "notify_all", "create_task", "Emails",
                  "httpx", "requests", "aiohttp", "urlopen", "AsyncClient", "SMTP"):
    verifier("11a. l'approbation n'invoque jamais %r" % _interdit, _interdit not in _appeles)
verifier("11b. elle n'appelle meme pas la porte d'envoi (rien a autoriser)",
         "p3s3_envoi_autorise" not in _appeles)
verifier("11c. elle n'ecrit jamais dans partner_prospects",
         "P3S1_COLLECTION" not in BLOC)
_ECRITES = set()
for _n in ast.walk(_NOEUD):
    if isinstance(_n, ast.Dict):
        for _k, _v in zip(_n.keys, _n.values):
            if isinstance(_k, ast.Constant) and _k.value == "$set" and isinstance(_v, ast.Dict):
                _ECRITES |= {c.value for c in _v.keys if isinstance(c, ast.Constant)}
verifier("11d. les seuls champs ecrits sont ceux de l'approbation",
         _ECRITES == {"approved_at", "approved_by", "etat", "snapshot_hash",
                      "nb_destinataires", "summary", "updated_at"}, str(sorted(_ECRITES)))
for _interdit in ("claimed_at", "sent_at", "verrou_actif", "first_contact_claimed_at",
                  "first_contact_sent_at", "status", "provider_message_id"):
    verifier("11e. l'approbation n'ecrit JAMAIS %r" % _interdit, _interdit not in _ECRITES)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P3-S3-C : %d / %d verifications" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s  %s" % (_i, _d))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)

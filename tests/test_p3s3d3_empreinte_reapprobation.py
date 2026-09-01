#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S3-D3 — L'OBJET ENTRE DANS L'EMPREINTE, ET LA CAMPAGNE SE ROUVRE.

LE DEFAUT QUE CE LOT FERME
==============================================================================
L'objet de l'e-mail vit sur la CAMPAGNE ; l'empreinte ne lisait que les
ACTIONS. On pouvait donc changer l'objet d'une campagne approuvee sans que la
garde ne voie rien passer — approuver un sujet A et envoyer un sujet B,
exactement ce que cette empreinte existe pour empecher.

Et une campagne approuvee ne pouvait pas etre corrigee : la route
d'approbation est idempotente par conception, donc une SECONDE approbation
etait structurellement impossible. Corriger un objet oublie aurait exige de
fabriquer une deuxieme campagne.

CE QUE CE FICHIER PROUVE
==============================================================================
  * l'objet change l'empreinte, et tout ce qu'elle protegeait le reste ;
  * une campagne approuvee ne se modifie pas — il faut la ROUVRIR, ce qui
    archive l'approbation precedente au lieu de l'effacer ;
  * entre la reouverture et la nouvelle approbation, RIEN n'est executable,
    meme les deux drapeaux ouverts ;
  * un objet change apres approbation, sans passer par le chemin prevu, arrete
    la campagne entiere ;
  * un seul campaign_id, 137 actions, aucune seconde campagne.

AUCUNE ECRITURE EN PRODUCTION. AUCUN RESEAU. Tout se joue en memoire.

    python3 tests/test_p3s3d3_empreinte_reapprobation.py
"""
import ast
import asyncio
import io
import json
import os
import socket
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


# La meme trappe reseau qu'en D2 : on interdit ce qui SORT, pas la paire de
# sockets locale dont asyncio a besoin pour se reveiller.
class SortieReseauInterdite(RuntimeError):
    pass


_TENTATIVES_RESEAU = []
_GETADDR = socket.getaddrinfo


def _dns_interdit(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES_RESEAU.append(hote)
    raise SortieReseauInterdite("sortie reseau vers %r" % (hote,))


socket.getaddrinfo = _dns_interdit
socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(
    SortieReseauInterdite("connexion interdite"))

SECRET = "secret-de-test-p3s3d3-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3s3d3-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"
OBJET = "Proposition de collaboration avec Afroboost"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_d = _source.index("def lancer(coroutine):")
_f = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_d:_f], _BANC, "exec"), _espace)   # noqa: S102
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
FICHES = _espace["FICHES"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]
JA = jeton(COACH_A)
JB = jeton(COACH_B)

_D1 = io.open(os.path.join(RACINE, "tests", "test_p3s3d1_moteur_factice.py"),
              encoding="utf-8").read()
exec(compile(_D1[_D1.index("_maj_originale = CollectionBouchon.update_one"):   # noqa: S102
                 _D1.index("def base_prete(")], "d1", "exec"),
     {"CollectionBouchon": CollectionBouchon, "type": type})


# Le bouchon doit connaitre `$push` : la reouverture archive l'approbation.
async def _update_one_push(self, filtre, maj, *a, **k):
    for d in self.documents:
        if self._ok(d, filtre):
            candidat = dict(d)
            candidat.update(maj.get("$set") or {})
            for cle, pas in (maj.get("$inc") or {}).items():
                candidat[cle] = int(candidat.get(cle) or 0) + pas
            for cle in (maj.get("$unset") or {}):
                candidat.pop(cle, None)
            for cle, valeur in (maj.get("$push") or {}).items():
                candidat[cle] = list(candidat.get(cle) or []) + [valeur]
            self._verifier_uniques(candidat, sauf=d)
            d.clear()
            d.update(candidat)
            self.ecritures += 1
            return type("R", (), {"matched_count": 1, "modified_count": 1})()
    return type("R", (), {"matched_count": 0, "modified_count": 0})()


CollectionBouchon.update_one = _update_one_push


def base_prete(objet=None, approuver=True):
    b = BaseBouchon([dict(f) for f in FICHES])
    b["feature_flags"] = CollectionBouchon("feature_flags", [{
        "id": "feature_flags", "P3_LAUNCH_ENABLED": False,
        "P3_LAUNCH_ENVOI_REEL": False}])
    b["subscribers"] = CollectionBouchon("subscribers", [])
    S.db = b
    p = lancer(S.p3s3_preparer_campagne(RequeteFictive(
        jeton_=JA, corps={"dry_run": False, "idempotency_key": "d3"})))
    identifiant = p["campaign"]["id"]
    if objet:
        lancer(S.p3s3_modifier_campagne(identifiant, RequeteFictive(
            jeton_=JA, corps={S.P3S3D2_CHAMP_OBJET: objet})))
    if approuver:
        lancer(S.p3s3_approuver_campagne(identifiant, RequeteFictive(jeton_=JA, corps={})))
    return b, identifiant


def camp(b):
    return dict(b["prospect_campaigns"].documents[0])


def acts(b):
    return [dict(a) for a in b["prospect_campaign_actions"].documents]


# ============================================================================
print("\n1. L'EMPREINTE COUVRE DESORMAIS L'OBJET")

_b, _ID = base_prete(objet=OBJET)
_C, _A = camp(_b), acts(_b)

_h_avec = S.p3s3_empreinte(_A, _C)
_h_sans = S.p3s3_empreinte(_A, dict(_C, subject_j0=None))
_h_autre = S.p3s3_empreinte(_A, dict(_C, subject_j0="Un tout autre objet"))
verifier("1a. objet A -> une empreinte", bool(_h_avec) and len(_h_avec) == 64)
verifier("1b. objet ABSENT -> empreinte DIFFERENTE", _h_avec != _h_sans)
verifier("1c. objet B -> empreinte DIFFERENTE", _h_avec != _h_autre)
verifier("1d. objet A et objet B different entre eux", _h_sans != _h_autre)
verifier("1e. l'objet est bien la matiere protegee",
         len({_h_avec, _h_sans, _h_autre}) == 3)

# DETERMINISME : rien de volatile.
verifier("1f. 20 calculs sur le meme contenu -> UNE seule empreinte",
         len({S.p3s3_empreinte(_A, _C) for _ in range(20)}) == 1)
verifier("1g. l'ordre des actions ne change rien",
         S.p3s3_empreinte(list(reversed(_A)), _C) == _h_avec)
_volatil = [dict(a, updated_at="2099-01-01", created_at="2099-01-01",
                 attempt_count=7) for a in _A]
verifier("1h. horodatages et compteurs sont IGNORES",
         S.p3s3_empreinte(_volatil, _C) == _h_avec)
verifier("1i. les compteurs de la campagne aussi",
         S.p3s3_empreinte(_A, dict(_C, summary={"x": 1}, nb_destinataires=99,
                                   updated_at="2099-01-01")) == _h_avec)

# CE QU'ELLE PROTEGEAIT DEJA, ELLE LE PROTEGE TOUJOURS.
for _champ, _valeur in (("message_j0", "MESSAGE SUBSTITUE"), ("channel", "instagram"),
                        ("target", "autre@ailleurs.test"), ("language", "klingon"),
                        ("recipient_key", "AUTRE-01")):
    _mod = [dict(a) for a in _A]
    _mod[0] = dict(_mod[0], **{_champ: _valeur})
    verifier("1j. modifier %-14s -> empreinte differente" % _champ,
             S.p3s3_empreinte(_mod, _C) != _h_avec)
_exclu = [dict(a) for a in _A]
_exclu[0] = dict(_exclu[0], statut="exclu")
verifier("1k. une action EXCLUE sort de l'empreinte",
         S.p3s3_empreinte(_exclu, _C) != _h_avec)
_NOEUD_EMPREINTE = next(n for n in ast.walk(ast.parse(SRC))
                        if isinstance(n, ast.FunctionDef) and n.name == "p3s3_empreinte")
_TXT_EMPREINTE = ast.get_source_segment(SRC, _NOEUD_EMPREINTE) or ""
verifier("1l. AUCUN champ protege n'a ete retire",
         all(c in _TXT_EMPREINTE for c in ("recipient_key", "channel", "language",
                                           "target", "message_j0")))
verifier("1l-bis. et l'objet de campagne s'y ajoute",
         "p3s3d2_objet_campagne" in _TXT_EMPREINTE)
verifier("1m. la campagne est un parametre EXIGE par tous les appelants",
         SRC.count("p3s3_empreinte(actions, campagne)") == 2)


# ============================================================================
print("\n2. UNE CAMPAGNE APPROUVEE NE SE MODIFIE PAS")

_b, _ID = base_prete(objet=OBJET)
verifier("2a. la campagne est approuvee", camp(_b)["etat"] == "approuvee")
try:
    lancer(S.p3s3_modifier_campagne(_ID, RequeteFictive(
        jeton_=JA, corps={S.P3S3D2_CHAMP_OBJET: "OBJET PIRATE"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("2b. modifier l'objet d'une campagne approuvee : REFUSE (409)", _refuse)
verifier("2c. l'objet n'a pas bouge", camp(_b)[S.P3S3D2_CHAMP_OBJET] == OBJET)
try:
    lancer(S.p3s3_modifier_action(_ID, acts(_b)[0]["id"], RequeteFictive(
        jeton_=JA, corps={"message_j0": "PIRATE"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("2d. modifier une action : toujours refuse (409)", _refuse)


# ============================================================================
print("\n3. ROUVRIR — UNE DECISION EXPLICITE")

_b, _ID = base_prete(objet=OBJET)
_avant = camp(_b)
_r = lancer(S.p3s3_rouvrir_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
_apres = camp(_b)
verifier("3a. la reouverture passe", _r["deja_ouverte"] is False)
verifier("3b. l'etat redevient `preparee`", _apres["etat"] == "preparee")
verifier("3c. approved_at est vide", _apres["approved_at"] is None)
verifier("3d. approved_by est vide", _apres["approved_by"] is None)
verifier("3e. snapshot_hash est efface", _apres["snapshot_hash"] is None)

# L'HISTOIRE N'EST PAS REECRITE.
_h = _apres.get("approbations") or []
verifier("3f. l'approbation precedente est ARCHIVEE, pas effacee", len(_h) == 1)
verifier("3g. ... avec son empreinte", _h[0]["snapshot_hash"] == _avant["snapshot_hash"])
verifier("3h. ... sa date", _h[0]["approved_at"] == _avant["approved_at"])
verifier("3i. ... son auteur", _h[0]["approved_by"] == _avant["approved_by"])
verifier("3j. ... et qui l'a rouverte, et quand",
         _h[0]["reopened_by"] == COACH_A and bool(_h[0]["reopened_at"]))

# NI CAMPAGNE NI ACTION N'EST CREEE.
verifier("3k. MEME campaign_id", _apres["id"] == _ID)
verifier("3l. toujours UNE campagne", len(_b["prospect_campaigns"].documents) == 1)
verifier("3m. actions inchangees", len(acts(_b)) == len(_A))
verifier("3n. contenu des actions intact",
         acts(_b)[0]["message_j0"] == _A[0]["message_j0"])
verifier("3o. l'objet est conserve pendant la reouverture",
         _apres[S.P3S3D2_CHAMP_OBJET] == OBJET)

# Rouvrir deux fois n'archive pas deux fois.
_r2 = lancer(S.p3s3_rouvrir_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
verifier("3p. rouvrir une campagne DEJA ouverte : sans effet",
         _r2["deja_ouverte"] is True)
verifier("3q. ... et une seule archive", len(camp(_b).get("approbations") or []) == 1)


# ============================================================================
print("\n4. ENTRE LA REOUVERTURE ET LA NOUVELLE APPROBATION : RIEN NE PART")

_b, _ID = base_prete(objet=OBJET)
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
lancer(S.p3s3_rouvrir_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
lancer(S.p3s3_modifier_campagne(_ID, RequeteFictive(
    jeton_=JA, corps={S.P3S3D2_CHAMP_OBJET: "Objet corrige, PAS ENCORE approuve"})))

_C2, _A2 = camp(_b), acts(_b)
verifier("4a. l'objet a bien ete corrige",
         _C2[S.P3S3D2_CHAMP_OBJET] == "Objet corrige, PAS ENCORE approuve")
verifier("4b. la campagne n'est PAS approuvee", _C2["etat"] == "preparee")
verifier("4c. la garde d'empreinte refuse (aucune empreinte approuvee)",
         S.p3s3d_empreinte_conforme(_C2, _A2) is False)
verifier("4d. la garde d'action refuse la campagne",
         S.p3s3d_garde_action(_A2[0], _C2)["code"] == "CAMPAGNE_NON_APPROUVEE")

# MEME LES DEUX DRAPEAUX OUVERTS.
_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=False, fournisseur=S.P3S3DFournisseurFactice()))
verifier("4e. LE MOTEUR S'ARRETE, drapeaux ouverts compris",
         _r["arrete"] is True and _r["code"] == "EMPREINTE_ALTEREE")
verifier("4f. aucun resultat, donc aucun appel fournisseur", _r["resultats"] == [])
verifier("4g. aucune reservation", not any("claimed_at" in a for a in acts(_b)))
verifier("4h. aucun prospect contacte",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("4i. 0 ecriture dans partner_prospects", _b["partner_prospects"].ecritures == 0)


# ============================================================================
print("\n5. LA NOUVELLE APPROBATION")

_r = lancer(S.p3s3_approuver_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
_C3 = camp(_b)
verifier("5a. la reapprobation passe", _r["deja_approuvee"] is False)
verifier("5b. l'etat redevient `approuvee`", _C3["etat"] == "approuvee")
verifier("5c. approved_at est neuf", bool(_C3["approved_at"]))
verifier("5d. approved_by est l'appelant", _C3["approved_by"] == COACH_A)
verifier("5e. une NOUVELLE empreinte est figee", bool(_C3["snapshot_hash"]))
verifier("5f. elle couvre le NOUVEL objet",
         _C3["snapshot_hash"] == S.p3s3_empreinte(acts(_b), _C3))
_ancienne = (_C3.get("approbations") or [])[0]["snapshot_hash"]
verifier("5g. et elle DIFFERE de l'ancienne", _C3["snapshot_hash"] != _ancienne)
verifier("5h. l'ancienne reste tracee", bool(_ancienne))
verifier("5i. la garde d'empreinte redevient conforme",
         S.p3s3d_empreinte_conforme(_C3, acts(_b)) is True)
verifier("5j. MEME campaign_id", _C3["id"] == _ID)
verifier("5k. toujours UNE campagne", len(_b["prospect_campaigns"].documents) == 1)
verifier("5l. actions toujours au meme nombre", len(acts(_b)) == len(_A))

# IDEMPOTENCE conservee.
_d1 = lancer(S.p3s3_approuver_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
_d2 = lancer(S.p3s3_approuver_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
verifier("5m. double approbation -> `deja_approuvee`",
         _d1["deja_approuvee"] is True and _d2["deja_approuvee"] is True)
verifier("5n. approved_at n'a pas bouge", camp(_b)["approved_at"] == _C3["approved_at"])
verifier("5o. l'empreinte non plus", camp(_b)["snapshot_hash"] == _C3["snapshot_hash"])
verifier("5p. une seule archive, toujours", len(camp(_b).get("approbations") or []) == 1)


# ============================================================================
print("\n6. UN OBJET CHANGE HORS DU CHEMIN PREVU ARRETE TOUT")

_b, _ID = base_prete(objet=OBJET)
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
# On force l'objet directement en base, comme le ferait une ecriture sauvage.
_b["prospect_campaigns"].documents[0][S.P3S3D2_CHAMP_OBJET] = "OBJET SUBSTITUE"
_C4, _A4 = camp(_b), acts(_b)
verifier("6a. l'empreinte ne correspond plus",
         S.p3s3d_empreinte_conforme(_C4, _A4) is False)
_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=False, fournisseur=S.P3S3DFournisseurFactice()))
verifier("6b. LE MOTEUR ARRETE LA CAMPAGNE ENTIERE",
         _r["arrete"] is True and _r["code"] == "EMPREINTE_ALTEREE")
verifier("6c. aucun envoi", not any(x.get("verdict") == "SUCCESS" for x in _r["resultats"]))
verifier("6d. aucun prospect contacte",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("6e. la garde vaut aussi en simulation",
         lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=True))["arrete"] is True)


# ============================================================================
print("\n7. LE FOURNISSEUR E-MAIL ET L'OBJET APPROUVE")

_b, _ID = base_prete(objet=OBJET)
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_C5 = camp(_b)
_recus = []


async def _transport(params, options):
    _recus.append(params["subject"])
    return {"id": "re_%03d" % len(_recus)}


_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=False,
    fournisseur=S.p3s3d2_fournisseur_pour("email", _C5, True, _transport)))
verifier("7a. le fournisseur recoit EXACTEMENT l'objet approuve",
         _recus and set(_recus) == {OBJET}, str(set(_recus)))
verifier("7b. tous les envois portent le meme objet", len(set(_recus)) == 1)


async def _transport_interdit(params, options):
    raise AssertionError("le fournisseur a ete appele sans objet approuve")


_b, _ID = base_prete(objet=None)
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_C6 = camp(_b)
_r = lancer(S.p3s3d_executer_campagne(
    _ID, COACH_A, simulation=False,
    fournisseur=S.p3s3d2_fournisseur_pour("email", _C6, True, _transport_interdit)))
verifier("7c. SANS objet : le fournisseur n'est JAMAIS appele",
         all(x["verdict"] == "IGNORE" for x in _r["resultats"]))
verifier("7d. ... et le motif est nomme",
         any(x["code"] == "OBJET_ABSENT" for x in _r["resultats"]))
verifier("7e. l'adaptateur refuse aussi de lui-meme",
         lancer(S.P3S3DFournisseurEmail(objet="", envoi_autorise=True,
                                        transport=_transport_interdit).envoyer(
             {"destinataire": "a@b.test", "message": "x"}, "k"))["error_code"]
         == "OBJET_ABSENT")

# AUCUN REPLI CACHE.
_NOEUD = next(n for n in ast.walk(ast.parse(SRC))
              if isinstance(n, ast.ClassDef) and n.name == "P3S3DFournisseurEmail")
_TXT = ast.get_source_segment(SRC, _NOEUD) or ""
for _repli in ('objet or "Afroboost', 'subject" or "', 'or "Proposition'):
    verifier("7f. aucun objet par defaut cache (%s)" % _repli, _repli not in _TXT)
verifier("7g. une seule source de verite pour l'objet",
         S.P3S3D2_CHAMP_OBJET == "subject_j0"
         and "email_subject" not in SRC and "j0_subject" not in SRC)


# ============================================================================
print("\n8. AUTHENTIFICATION, ETATS ET GARDES")

_b, _ID = base_prete(objet=OBJET)
for _nom, _appel in (("rouvrir", lambda j: S.p3s3_rouvrir_campagne(
                          _ID, RequeteFictive(jeton_=j, corps={}))),
                     ("modifier", lambda j: S.p3s3_modifier_campagne(
                          _ID, RequeteFictive(jeton_=j, corps={"nom": "x"})))):
    try:
        lancer(_appel(None))
        _ferme = False
    except HTTPException as e:
        _ferme = e.status_code in (401, 403)
    verifier("8a. %-9s SANS jeton -> refuse" % _nom, _ferme)
    try:
        lancer(_appel(JB))
        _ferme = False
    except HTTPException as e:
        _ferme = e.status_code == 403
    verifier("8b. %-9s pour un AUTRE coach -> 403" % _nom, _ferme)

try:
    lancer(S.p3s3_rouvrir_campagne("inconnue", RequeteFictive(jeton_=JA, corps={})))
    _quatrecent = False
except HTTPException as e:
    _quatrecent = e.status_code == 404
verifier("8c. rouvrir une campagne inconnue -> 404", _quatrecent)

_b["prospect_campaigns"].documents[0]["etat"] = "annulee"
try:
    lancer(S.p3s3_rouvrir_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("8d. rouvrir une campagne ANNULEE -> 409", _refuse)

# Une campagne DEMARREE ne se rouvre pas : des contacts sont peut-etre partis.
_b, _ID = base_prete(objet=OBJET)
_b["prospect_campaigns"].documents[0]["started_at"] = INSTANT
try:
    lancer(S.p3s3_rouvrir_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 409
verifier("8e. rouvrir une campagne DEMARREE -> 409 (des contacts sont peut-etre partis)",
         _refuse)

# La modification refuse ce qu'elle ne connait pas.
_b, _ID = base_prete(objet=OBJET, approuver=False)
try:
    lancer(S.p3s3_modifier_campagne(_ID, RequeteFictive(jeton_=JA, corps={"etat": "approuvee"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("8f. un champ non modifiable est REFUSE, jamais ecrit en silence", _refuse)
try:
    lancer(S.p3s3_modifier_campagne(_ID, RequeteFictive(jeton_=JA, corps={"nom": "  "})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("8g. un nom vide est refuse", _refuse)
verifier("8h. l'objet peut etre EFFACE volontairement (et bloque alors l'envoi)",
         lancer(S.p3s3_modifier_campagne(_ID, RequeteFictive(
             jeton_=JA, corps={S.P3S3D2_CHAMP_OBJET: ""})))["campaign"][S.P3S3D2_CHAMP_OBJET]
         is None)
verifier("8i. un objet trop long est borne",
         len(lancer(S.p3s3_modifier_campagne(_ID, RequeteFictive(
             jeton_=JA, corps={S.P3S3D2_CHAMP_OBJET: "x" * 400})))
             ["campaign"][S.P3S3D2_CHAMP_OBJET]) == S.P3S3D2_OBJET_MAX)


# ============================================================================
print("\n9. LE CYCLE COMPLET, DE BOUT EN BOUT")

_b, _ID = base_prete(objet=None)
_etapes = []
_etapes.append(("prepare+approuve sans objet", camp(_b)["etat"],
                camp(_b)["snapshot_hash"][:12]))
_R = S.p3s3d_resume_execution(camp(_b), acts(_b))
verifier("9a. sans objet : 0 executable", _R["auto_executables"] == 0)
lancer(S.p3s3_rouvrir_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
_etapes.append(("rouverte", camp(_b)["etat"], str(camp(_b)["snapshot_hash"])))
lancer(S.p3s3_modifier_campagne(_ID, RequeteFictive(
    jeton_=JA, corps={S.P3S3D2_CHAMP_OBJET: OBJET})))
lancer(S.p3s3_approuver_campagne(_ID, RequeteFictive(jeton_=JA, corps={})))
_etapes.append(("reapprouvee avec objet", camp(_b)["etat"],
                camp(_b)["snapshot_hash"][:12]))
for _n, _e, _h in _etapes:
    print("     %-28s etat=%-10s hash=%s" % (_n, _e, _h))
_R = S.p3s3d_resume_execution(camp(_b), acts(_b))
verifier("9b. apres le cycle : des executables reapparaissent",
         _R["auto_executables"] > 0, str(_R["auto_executables"]))
verifier("9c. UNE campagne, du debut a la fin",
         len(_b["prospect_campaigns"].documents) == 1)
verifier("9d. le meme identifiant", camp(_b)["id"] == _ID)
verifier("9e. les actions n'ont jamais bouge", len(acts(_b)) == len(_A))
verifier("9f. les deux empreintes different", _etapes[0][2] != _etapes[2][2])
verifier("9g. l'historique garde la premiere approbation",
         len(camp(_b).get("approbations") or []) == 1)
verifier("9h. aucun prospect contacte de tout le cycle",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("9i. aucune reservation de tout le cycle",
         not any("claimed_at" in a for a in acts(_b)))


# ============================================================================
print("\n10. AUCUNE ROUTE D'ENVOI, AUCUN RESEAU")

_CHEMINS = [r.path for r in S.app.routes if "prospect-campaigns" in getattr(r, "path", "")]
verifier("10a. sept routes de campagne, pas une de plus", len(_CHEMINS) == 7, str(len(_CHEMINS)))
for _interdit in ("send", "launch", "dispatch", "execute", "retry", "j3", "j7"):
    verifier("10b. aucune route contenant %r" % _interdit,
             not any(_interdit in c for c in _CHEMINS))
verifier("10c. AUCUNE SORTIE RESEAU DE TOUT LE BANC",
         not _TENTATIVES_RESEAU, str(_TENTATIVES_RESEAU))


# ============================================================================
print("\n" + "=" * 78)
socket.getaddrinfo = _GETADDR
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P3-S3-D3 : %d / %d verifications" % (_ok, _total))
print("Sorties reseau tentees : %d" % len(_TENTATIVES_RESEAU))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s  %s" % (_i, _d))
print("=" * 78)
sys.exit(0 if _ok == _total and not _TENTATIVES_RESEAU else 1)

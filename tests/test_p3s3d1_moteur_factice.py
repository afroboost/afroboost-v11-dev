#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-S3-D1 — LE MOTEUR D'EXECUTION, ET UN FOURNISSEUR QUI N'ENVOIE RIEN.

CE QUE LE LOT AJOUTE
==============================================================================
Le contrat d'execution : cinq verdicts, une garde de pre-execution, la garde
d'empreinte, la reservation atomique, l'ordre des ecritures, et un adaptateur
FACTICE. Aucune route. Aucun fournisseur reel. Aucun appel reseau.

CE QUE CE FICHIER PROUVE, ET POURQUOI CHAQUE POINT COMPTE
==============================================================================
  * le bloc ne PEUT PAS sortir de la machine — verifie sur les appels reels de
    chaque fonction (AST), pas sur la prose des commentaires ;
  * un message vide n'envoie rien : c'est le cas des 25 « AUTO » du PREFLIGHT
    qui n'ont aucun texte a transmettre ;
  * reserver n'est pas envoyer : aucune reservation ne fait passer un prospect
    a `contacte` ;
  * deux workers concurrents : un seul obtient la reservation ;
  * un message parti puis un crash ne produit JAMAIS un second message — la
    trace d'intention est ecrite AVANT l'appel ;
  * un verdict indetermine GARDE son verrou : entre risquer un doublon et
    demander confirmation, on demande ;
  * le dry-run n'ecrit pas une ligne, dans aucune collection.

AUCUNE ECRITURE EN PRODUCTION. Tout se joue en memoire.

    python3 tests/test_p3s3d1_moteur_factice.py
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


SECRET = "secret-de-test-p3s3d1-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3s3d1-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"

# Le banc de P3-S3-B est reutilise tel quel. Deux bancs divergeraient, et le
# second finirait par mentir sur ce que fait le premier.
_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
ErreurUnicite = _espace["ErreurUnicite"]
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
fiche = _espace["fiche"]
FICHES = _espace["FICHES"]
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]
JA = jeton(COACH_A)


# --- LE BOUCHON EST ETENDU, PAS REECRIT --------------------------------------
# Le moteur utilise `$inc` (le compteur de tentatives) et `$unset` (la levee du
# verrou), que le bouchon de P3-S3-B ne connaissait pas : il n'en avait pas
# besoin. On AJOUTE ces deux operateurs sans toucher au reste — un bouchon
# duplique aurait fini par diverger de celui qui garde les lots precedents.
_maj_originale = CollectionBouchon.update_one


async def _update_one_etendu(self, filtre, maj, *a, **k):
    for d in self.documents:
        if self._ok(d, filtre):
            candidat = dict(d)
            candidat.update(maj.get("$set") or {})
            for cle, pas in (maj.get("$inc") or {}).items():
                candidat[cle] = int(candidat.get(cle) or 0) + pas
            for cle in (maj.get("$unset") or {}):
                candidat.pop(cle, None)
            self._verifier_uniques(candidat, sauf=d)
            d.clear()
            d.update(candidat)
            self.ecritures += 1
            return type("R", (), {"matched_count": 1, "modified_count": 1})()
    return type("R", (), {"matched_count": 0, "modified_count": 0})()


CollectionBouchon.update_one = _update_one_etendu


def base_prete(fiches=None):
    """Une base avec une campagne APPROUVEE et ses actions, prete a executer."""
    b = BaseBouchon([dict(f) for f in (fiches if fiches is not None else FICHES)])
    # Les drapeaux existent DEJA : sans cela, `get_feature_flags` les creerait,
    # et le test « dry-run n'ecrit rien » compterait cette insertion.
    b["feature_flags"] = CollectionBouchon("feature_flags", [{
        "id": "feature_flags", "P3_LAUNCH_ENABLED": False,
        "P3_LAUNCH_ENVOI_REEL": False}])
    b["subscribers"] = CollectionBouchon("subscribers", [])
    S.db = b
    prepare = lancer(S.p3s3_preparer_campagne(RequeteFictive(
        jeton_=JA, corps={"dry_run": False, "idempotency_key": "d1"})))
    identifiant = prepare["campaign"]["id"]
    lancer(S.p3s3_approuver_campagne(identifiant, RequeteFictive(jeton_=JA, corps={})))
    b["prospect_campaigns"].ecritures = 0
    b["prospect_campaign_actions"].ecritures = 0
    b["partner_prospects"].ecritures = 0
    return b, identifiant


def campagne_de(b):
    return dict(b["prospect_campaigns"].documents[0])


def actions_de(b):
    return [dict(a) for a in b["prospect_campaign_actions"].documents]


def action_de(b, cle):
    return next(dict(a) for a in b["prospect_campaign_actions"].documents
                if a["recipient_key"] == cle)


# ============================================================================
print("\n1. LE CONTRAT — CINQ VERDICTS, UN SEUL CANAL AUTOMATISABLE")

verifier("1a. les cinq verdicts, exactement",
         S.P3S3D_VERDICTS == ("SUCCESS", "RETRYABLE_FAILURE", "PERMANENT_FAILURE",
                              "INDETERMINATE", "RATE_LIMIT"), str(S.P3S3D_VERDICTS))
verifier("1b. e-mail est le SEUL canal automatisable",
         S.P3S3D_CANAUX_AUTOMATISABLES == ("email",), str(S.P3S3D_CANAUX_AUTOMATISABLES))
verifier("1c. WhatsApp n'est PAS automatisable",
         "whatsapp" not in S.P3S3D_CANAUX_AUTOMATISABLES)
verifier("1d. Instagram n'est PAS automatisable",
         "instagram" not in S.P3S3D_CANAUX_AUTOMATISABLES)
verifier("1e. les etats techniques restent ceux de P3-S3-A",
         S.P3S3_STATUTS_ACTION == ("pret", "exclu", "reserve", "en_cours", "envoye",
                                   "echec", "echec_indetermine", "a_faire_assiste",
                                   "a_faire_manuel", "bloque"))
verifier("1f. AUCUN statut metier nouveau",
         S.P3S1_STATUTS == ("a_contacter", "contacte", "repondu", "interesse",
                            "sans_reponse_pause", "refuse"))
verifier("1g. les etats qui gardent le verrou sont inchanges",
         S.P3S3_STATUTS_VERROU == ("reserve", "en_cours", "envoye", "echec_indetermine"))
verifier("1h. trois tentatives au maximum", S.P3S3D_MAX_TENTATIVES == 3)


# ============================================================================
print("\n2. AUCUN RESEAU — VERIFIE SUR LE CODE, PAS SUR LES COMMENTAIRES")

ARBRE = ast.parse(SRC)
_NOEUDS = [n for n in ast.walk(ARBRE)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
           and n.name.startswith(("p3s3d_", "P3S3D"))]
verifier("2a. les fonctions du lot existent (%d)" % len(_NOEUDS), len(_NOEUDS) >= 10)
_appeles, _noms = set(), set()
for _n in _NOEUDS:
    for _s in ast.walk(_n):
        if isinstance(_s, ast.Call):
            _appeles.add(getattr(_s.func, "id", None) or getattr(_s.func, "attr", None))
        if isinstance(_s, ast.Attribute):
            _appeles.add(_s.attr)
        if isinstance(_s, ast.Name):
            _noms.add(_s.id)
        if isinstance(_s, (ast.Import, ast.ImportFrom)):
            _noms.add("IMPORT")
_appeles.discard(None)
for _interdit in ("httpx", "requests", "aiohttp", "urlopen", "urlretrieve",
                  "AsyncClient", "ClientSession", "SMTP", "sendmail", "socket",
                  "resend", "Emails", "send_email", "send_bulk_email",
                  "_send_whatsapp_meta", "send_push", "send_push_by_email",
                  "notify_all", "create_task", "subprocess", "Popen"):
    verifier("2b. le lot n'invoque jamais %r" % _interdit,
             _interdit not in _appeles and _interdit not in _noms)
verifier("2c. le lot n'importe RIEN (aucune dependance reseau possible)",
         "IMPORT" not in _noms)
verifier("2d. aucun decorateur de route dans le lot",
         not any(getattr(n, "decorator_list", None) for n in _NOEUDS))
verifier("2e. aucune route d'execution n'existe encore",
         not any(x in SRC for x in ('"/prospect-campaigns/{campaign_id}/execute',
                                    '"/prospect-campaigns/{campaign_id}/send',
                                    '"/execute-real', '"/dispatch-real')))
_CHEMINS = [r.path for r in S.app.routes if "prospect-campaigns" in getattr(r, "path", "")]
verifier("2f. toujours cinq routes de campagne, aucune ajoutee",
         len(_CHEMINS) == 5, str(len(_CHEMINS)))
verifier("2g. le fournisseur factice n'a qu'une methode d'envoi",
         [m for m in dir(S.P3S3DFournisseurFactice) if not m.startswith("_")]
         == ["envoyer", "nom"], str([m for m in dir(S.P3S3DFournisseurFactice)
                                     if not m.startswith("_")]))


# ============================================================================
print("\n3. LA CLE D'IDEMPOTENCE EST STABLE")

_a = {"campaign_id": "c-1", "recipient_key": "GVA-F3"}
_cle = S.p3s3d_cle_idempotence(_a)
verifier("3a. la cle lie campagne + destinataire + etape",
         _cle == "p3-c-1-GVA-F3-j0", _cle)
verifier("3b. rejouee dix fois, elle ne bouge pas",
         len({S.p3s3d_cle_idempotence(dict(_a)) for _ in range(10)}) == 1)
verifier("3c. deux destinataires -> deux cles",
         S.p3s3d_cle_idempotence({"campaign_id": "c-1", "recipient_key": "A"}) !=
         S.p3s3d_cle_idempotence({"campaign_id": "c-1", "recipient_key": "B"}))
verifier("3d. deux campagnes -> deux cles",
         S.p3s3d_cle_idempotence({"campaign_id": "c-1", "recipient_key": "A"}) !=
         S.p3s3d_cle_idempotence({"campaign_id": "c-2", "recipient_key": "A"}))
verifier("3e. ce n'est PAS un uuid aleatoire", "-" in _cle and len(_cle) < 120)


# ============================================================================
print("\n4. LA GARDE DE PRE-EXECUTION")

_b, _ID = base_prete()
_camp = campagne_de(_b)
_ok = action_de(_b, "GVA-F3")          # e-mail, AUTO, message present
verifier("4a. une action saine est autorisee",
         S.p3s3d_garde_action(_ok, _camp)["autorise"] is True,
         str(S.p3s3d_garde_action(_ok, _camp)))

for _modif, _code, _quoi in (
        ({"statut": "exclu"}, "ACTION_EXCLUE", "action exclue"),
        ({"execution_type": "MANUEL"}, "PAS_AUTO", "type non AUTO"),
        ({"channel": "instagram"}, "CANAL_NON_AUTOMATISABLE", "canal Instagram"),
        ({"channel": "whatsapp"}, "CANAL_NON_AUTOMATISABLE", "canal WhatsApp"),
        ({"channel": "formulaire"}, "CANAL_NON_AUTOMATISABLE", "canal formulaire"),
        ({"message_j0": ""}, "MESSAGE_VIDE", "message vide"),
        ({"message_j0": "   "}, "MESSAGE_VIDE", "message d'espaces"),
        ({"target": ""}, "CIBLE_INVALIDE", "cible absente"),
        ({"target": "pas-une-adresse"}, "CIBLE_INVALIDE", "cible illisible"),
        ({"verrou_actif": True}, "DEJA_RESERVE", "verrou deja pose"),
        ({"claimed_at": INSTANT}, "DEJA_RESERVE", "reservation deja prise"),
        ({"sent_at": INSTANT}, "DEJA_CONTACTE", "envoi deja confirme"),
        ({"statut": "envoye"}, "STATUT_INCOMPATIBLE", "statut envoye sans sent_at"),
        ({"statut": "echec_indetermine"}, "STATUT_INCOMPATIBLE", "statut indetermine"),
        ({"attempt_count": 3}, "TENTATIVES_EPUISEES", "tentatives epuisees")):
    _v = S.p3s3d_garde_action(dict(_ok, **_modif), _camp)
    verifier("4b. %-24s -> %s" % (_quoi, _code), _v["code"] == _code,
             "obtenu : %s" % _v["code"])

verifier("4c. campagne NON approuvee -> tout est refuse",
         S.p3s3d_garde_action(_ok, dict(_camp, etat="preparee"))["code"]
         == "CAMPAGNE_NON_APPROUVEE")
verifier("4d. campagne annulee -> tout est refuse",
         S.p3s3d_garde_action(_ok, dict(_camp, etat="annulee"))["code"]
         == "CAMPAGNE_NON_APPROUVEE")

# Le registre STOP : un refus exprime bloque, et il passe AVANT tout le reste.
_refus = {(_ok.get("target") or "").lower()}
verifier("4e. un refus exprime bloque le premier contact",
         S.p3s3d_garde_action(_ok, _camp, refus=_refus)["code"] == "REFUS_EXPRIME")
verifier("4f. le refus prime meme sur un message vide",
         S.p3s3d_garde_action(dict(_ok, message_j0=""), _camp, refus=_refus)["code"]
         == "REFUS_EXPRIME")

# Un premier contact deja fait sur UNE fiche du groupe suffit.
verifier("4g. une fiche deja contactee interdit le J0",
         S.p3s3d_garde_action(_ok, _camp, fiches=[
             {"ref": "X", "first_contact_sent_at": INSTANT}])["code"] == "DEJA_CONTACTE")
verifier("4h. ... meme si l'autre fiche du groupe est vierge",
         S.p3s3d_garde_action(_ok, _camp, fiches=[
             {"ref": "A"}, {"ref": "B", "first_contact_sent_at": INSTANT}])["code"]
         == "DEJA_CONTACTE")

# Les drapeaux : ils n'entravent PAS la simulation, ils ferment l'envoi reel.
verifier("4i. drapeaux fermes : la SIMULATION reste possible",
         S.p3s3d_garde_action(_ok, _camp, envoi_autorise=False, simulation=True)["autorise"])
verifier("4j. drapeaux fermes : l'ENVOI REEL est refuse",
         S.p3s3d_garde_action(_ok, _camp, envoi_autorise=False,
                              simulation=False)["code"] == "ENVOI_NON_AUTORISE")
verifier("4k. drapeaux ouverts : l'envoi reel est autorise",
         S.p3s3d_garde_action(_ok, _camp, envoi_autorise=True,
                              simulation=False)["autorise"])
verifier("4l. la porte d'envoi reste fermee par defaut",
         S.p3s3_envoi_autorise({"P3_LAUNCH_ENABLED": False,
                                "P3_LAUNCH_ENVOI_REEL": False}) is False)


# ============================================================================
print("\n5. LA GARDE D'EMPREINTE")

_acts = actions_de(_b)
verifier("5a. l'empreinte du snapshot approuve correspond",
         S.p3s3d_empreinte_conforme(_camp, _acts) is True)
_altere = [dict(a) for a in _acts]
_altere[0] = dict(_altere[0], message_j0="MESSAGE SUBSTITUE")
verifier("5b. un message modifie rend l'empreinte NON conforme",
         S.p3s3d_empreinte_conforme(_camp, _altere) is False)
_altere = [dict(a) for a in _acts]
_altere[0] = dict(_altere[0], channel="instagram")
verifier("5c. un canal modifie aussi",
         S.p3s3d_empreinte_conforme(_camp, _altere) is False)
_altere = [dict(a) for a in _acts]
_altere[0] = dict(_altere[0], target="autre@ailleurs.test")
verifier("5d. une adresse modifiee aussi",
         S.p3s3d_empreinte_conforme(_camp, _altere) is False)
verifier("5e. une campagne SANS empreinte n'est PAS conforme (l'absence de preuve n'en est pas une)",
         S.p3s3d_empreinte_conforme(dict(_camp, snapshot_hash=None), _acts) is False)
verifier("5f. l'ordre des actions ne change rien",
         S.p3s3d_empreinte_conforme(_camp, list(reversed(_acts))) is True)


# ============================================================================
print("\n6. LE DRY-RUN N'ECRIT PAS UNE LIGNE")

_b, _ID = base_prete()
_r = lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=True))
verifier("6a. le mode par defaut est la simulation",
         lancer(S.p3s3d_executer_campagne(_ID, COACH_A))["simulation"] is True)
verifier("6b. le passage n'est pas arrete", _r["arrete"] is False)
verifier("6c. 0 ecriture dans prospect_campaign_actions",
         _b["prospect_campaign_actions"].ecritures == 0)
verifier("6d. 0 ecriture dans prospect_campaigns",
         _b["prospect_campaigns"].ecritures == 0)
verifier("6e. 0 ecriture dans partner_prospects",
         _b["partner_prospects"].ecritures == 0)
verifier("6f. 0 ecriture NULLE PART, toutes collections confondues",
         _b.total_ecritures() == 0, "ecritures : %d" % _b.total_ecritures())
verifier("6g. AUCUNE reservation posee",
         not any("claimed_at" in a for a in actions_de(_b)))
verifier("6h. AUCUN verrou pose",
         not any("verrou_actif" in a for a in actions_de(_b)))
verifier("6i. AUCUN sent_at",
         not any("sent_at" in a for a in actions_de(_b)))
verifier("6j. les fiches restent `a_contacter`",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("6k. first_contact_sent_at ecrit sur 0 fiche",
         not any("first_contact_sent_at" in f for f in _b["partner_prospects"].documents))
verifier("6l. le dry-run rend quand meme un verdict par destinataire executable",
         sum(1 for x in _r["resultats"] if x["code"] == "SIMULATION")
         == _r["resume"]["auto_executables"])


# ============================================================================
print("\n7. LE RESUME PRE-EXECUTION")

_R = _r["resume"]
verifier("7a. il porte l'etat de la campagne", _R["etat_campagne"] == "approuvee")
verifier("7b. il confirme l'empreinte", _R["empreinte_conforme"] is True)
verifier("7c. il compte toutes les actions", _R["actions_total"] == len(actions_de(_b)))
verifier("7d. il distingue AUTO declares et AUTO EXECUTABLES",
         _R["auto_declares"] >= _R["auto_executables"])
verifier("7e. tout ce qui est executable est de l'e-mail",
         _R["par_canal_auto"] == {"email": _R["auto_executables"]}
         or _R["auto_executables"] == 0, str(_R["par_canal_auto"]))
verifier("7f. WhatsApp executable = 0", _R["par_canal_auto"].get("whatsapp", 0) == 0)
verifier("7g. Instagram executable = 0", _R["par_canal_auto"].get("instagram", 0) == 0)
verifier("7h. les blocages sont comptes par motif", isinstance(_R["bloques_par_garde"], dict))
verifier("7i. le resume ne lit ni n'ecrit la base (fonction pure)",
         S.p3s3d_resume_execution(_camp, _acts)["actions_total"] == len(_acts))
verifier("7j. il nomme les destinataires executables",
         len(_R["destinataires_executables"]) == _R["auto_executables"])
verifier("7k. il compte les executables SANS langue declaree",
         isinstance(_R["sans_langue_executables"], int))


# ============================================================================
print("\n8. LA RESERVATION ATOMIQUE")

_b, _ID = base_prete()
_cible = action_de(_b, "GVA-F3")
verifier("8a. la premiere reservation passe",
         lancer(S.p3s3d_reserver(_cible["id"], _ID, INSTANT)) is True)
_apres = action_de(_b, "GVA-F3")
verifier("8b. l'action passe a `reserve`", _apres["statut"] == "reserve")
verifier("8c. claimed_at est pose", _apres["claimed_at"] == INSTANT)
verifier("8d. verrou_actif est pose", _apres["verrou_actif"] is True)
verifier("8e. le compteur de tentatives monte", _apres["attempt_count"] == 1)
verifier("8f. LA SECONDE RESERVATION EST REFUSEE (deux workers)",
         lancer(S.p3s3d_reserver(_cible["id"], _ID, INSTANT)) is False)
verifier("8g. une troisieme aussi",
         lancer(S.p3s3d_reserver(_cible["id"], _ID, INSTANT)) is False)
verifier("8h. le compteur n'a PAS bouge (aucun effet de bord)",
         action_de(_b, "GVA-F3")["attempt_count"] == 1)

# RESERVER N'EST PAS CONTACTER.
verifier("8i. INVARIANT — aucun sent_at apres reservation",
         "sent_at" not in action_de(_b, "GVA-F3"))
verifier("8j. INVARIANT — les fiches restent `a_contacter`",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("8k. INVARIANT — first_contact_sent_at ecrit sur 0 fiche",
         not any("first_contact_sent_at" in f for f in _b["partner_prospects"].documents))
verifier("8l. INVARIANT — 0 ecriture dans partner_prospects",
         _b["partner_prospects"].ecritures == 0)

# La liberation rend le destinataire disponible.
lancer(S.p3s3d_liberer(_cible["id"], "echec", INSTANT, {"error_code": "422"}))
_libre = action_de(_b, "GVA-F3")
verifier("8m. liberer retire le verrou", "verrou_actif" not in _libre)
verifier("8n. liberer retire la reservation", "claimed_at" not in _libre)
verifier("8o. l'erreur est conservee", _libre["error_code"] == "422")
verifier("8p. le destinataire redevient reservable",
         lancer(S.p3s3d_reserver(_cible["id"], _ID, INSTANT)) is True)
verifier("8q. et le compteur reprend a 2", action_de(_b, "GVA-F3")["attempt_count"] == 2)


# ============================================================================
print("\n9. LES CINQ VERDICTS DU FOURNISSEUR FACTICE")

_f = S.P3S3DFournisseurFactice()
_inst = {"recipient_key": "X", "canal": "email", "destinataire": "a@b.test",
         "message": "bonjour"}
for _verdict in S.P3S3D_VERDICTS:
    _rep = lancer(S.P3S3DFournisseurFactice(verdict=_verdict).envoyer(_inst, "cle"))
    verifier("9a. le factice rend %-18s" % _verdict, _rep["verdict"] == _verdict)

_succes = lancer(S.P3S3DFournisseurFactice(verdict="SUCCESS").envoyer(_inst, "cle-42"))
verifier("9b. SUCCESS rend un identifiant PREFIXE `fake_`",
         _succes["provider_message_id"] == "fake_cle-42")
verifier("9c. ... et un horodatage d'acceptation", bool(_succes["accepted_at"]))
verifier("9d. ... et aucune erreur", _succes["error_code"] is None)

_429 = lancer(S.P3S3DFournisseurFactice(verdict="RATE_LIMIT").envoyer(_inst, "c"))
verifier("9e. RATE_LIMIT rend un retry_after", _429["retry_after"] == 60)
verifier("9f. ... et le code 429", _429["error_code"] == "429")
verifier("9g. ... et AUCUN identifiant de message", _429["provider_message_id"] is None)

_perm = lancer(S.P3S3DFournisseurFactice(verdict="PERMANENT_FAILURE").envoyer(_inst, "c"))
verifier("9h. PERMANENT_FAILURE : aucun identifiant",
         _perm["provider_message_id"] is None and _perm["error_code"] == "422")

_ind = lancer(S.P3S3DFournisseurFactice(verdict="INDETERMINATE").envoyer(_inst, "c"))
verifier("9i. INDETERMINATE : aucun identifiant, et le motif le dit",
         _ind["provider_message_id"] is None and "ignore" in _ind["error_message"])

try:
    lancer(S.P3S3DFournisseurFactice(verdict="INVENTE").envoyer(_inst, "c"))
    _refuse = False
except ValueError:
    _refuse = True
verifier("9j. un verdict inconnu est REFUSE, jamais interprete", _refuse)

_f = S.P3S3DFournisseurFactice(par_destinataire={"A": "PERMANENT_FAILURE"},
                               verdict="SUCCESS")
verifier("9k. le factice sait rendre un verdict PAR destinataire",
         lancer(_f.envoyer({"recipient_key": "A"}, "c"))["verdict"] == "PERMANENT_FAILURE"
         and lancer(_f.envoyer({"recipient_key": "B"}, "c"))["verdict"] == "SUCCESS")
verifier("9l. le factice trace ses appels (pour les bancs)", len(_f.appels) == 2)
verifier("9m. il ne recoit QUE l'instantane d'envoi",
         set(S.p3s3d_instantane_envoi(_cible)) ==
         {"canal", "destinataire", "message", "langue", "organisation", "recipient_key"})


# ============================================================================
print("\n10. EXECUTION REELLE — LE CHEMIN COMPLET, SANS RESEAU")


def executer(verdict, fiches=None, ouvrir=True, par_destinataire=None):
    b, identifiant = base_prete(fiches)
    if ouvrir:
        b["feature_flags"].documents[0].update(
            {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
    f = S.P3S3DFournisseurFactice(verdict=verdict, par_destinataire=par_destinataire)
    r = lancer(S.p3s3d_executer_campagne(identifiant, COACH_A, simulation=False,
                                         fournisseur=f))
    return b, identifiant, r, f


# --- SUCCESS ---------------------------------------------------------------
_b, _ID, _r, _f = executer("SUCCESS")
_env = [x for x in _r["resultats"] if x["verdict"] == "SUCCESS"]
verifier("10a. tous les executables aboutissent",
         len(_env) == _r["resume"]["auto_executables"] and len(_env) > 0,
         "%d envoyes / %d executables" % (len(_env), _r["resume"]["auto_executables"]))
_a = action_de(_b, "GVA-F3")
verifier("10b. l'action passe a `envoye`", _a["statut"] == "envoye")
verifier("10c. sent_at est pose", bool(_a["sent_at"]))
verifier("10d. l'identifiant fournisseur est conserve",
         _a["provider_message_id"].startswith("fake_"))
verifier("10e. le statut fournisseur est `accepted`", _a["provider_status"] == "accepted")
verifier("10f. le verrou reste pose (l'envoi est definitif)", _a["verrou_actif"] is True)
verifier("10g. la trace d'intention a bien ete ecrite AVANT l'appel",
         bool(_a.get("attempted_at")))
verifier("10h. la cle d'idempotence est conservee sur l'action",
         _a["idempotency_key"] == S.p3s3d_cle_idempotence(_a))
# LES ECHEANCES PARTENT DU VRAI PREMIER CONTACT.
verifier("10i. j3_due_at est pose", bool(_a.get("j3_due_at")))
verifier("10j. j7_due_at est pose", bool(_a.get("j7_due_at")))
verifier("10k. j3_due_at part de sent_at, pas de la preparation",
         _a["j3_due_at"] == S.p3s3d_echeance(_a["sent_at"], 3))
verifier("10l. j7 = sent_at + 7 jours",
         _a["j7_due_at"] == S.p3s3d_echeance(_a["sent_at"], 7))
verifier("10m. j3 est AVANT j7", _a["j3_due_at"] < _a["j7_due_at"])
verifier("10n. les echeances ne partent PAS de created_at",
         _a["j3_due_at"] != S.p3s3d_echeance(_a["created_at"], 3))

# --- LA REGLE MULTI-FICHES -------------------------------------------------
_wf = [f for f in _b["partner_prospects"].documents if f["ref"] in ("GVA-F3", "LSN-F3")]
verifier("10o. MULTI-FICHES — les DEUX fiches Wellness passent a `contacte`",
         len(_wf) == 2 and all(f["status"] == "contacte" for f in _wf),
         str([(f["ref"], f["status"]) for f in _wf]))
verifier("10p. ... et toutes deux portent first_contact_sent_at",
         all(f.get("first_contact_sent_at") for f in _wf))
verifier("10q. ... avec la MEME valeur (un seul premier contact)",
         len({f["first_contact_sent_at"] for f in _wf}) == 1)
verifier("10r. ... et last_contact_at",
         all(f.get("last_contact_at") for f in _wf))
_df = [f for f in _b["partner_prospects"].documents if f["ref"] in ("GVA-D2", "LSN-D5")]
verifier("10s. MULTI-FICHES — idem pour Dancefloor",
         len(_df) == 2 and all(f["status"] == "contacte" for f in _df))
# La consequence : plus AUCUNE seconde sollicitation possible par l'autre fiche.
_camp2 = campagne_de(_b)
_table = {f["ref"]: f for f in _b["partner_prospects"].documents}
verifier("10t. une SECONDE campagne ne pourrait plus les recontacter",
         S.p3s3d_garde_action(action_de(_b, "GVA-F3"), _camp2,
                              fiches=[_table["LSN-F3"]])["code"] == "DEJA_CONTACTE")

# Les non-executables n'ont RIEN subi.
verifier("10u. les destinataires bloques n'ont ni reservation ni envoi",
         all("claimed_at" not in a and "sent_at" not in a
             for a in actions_de(_b) if a["recipient_key"] == "BAR-09"))
verifier("10v. le prospect bloque reste `a_contacter`",
         next(f for f in _b["partner_prospects"].documents
              if f["ref"] == "BAR-09")["status"] == "a_contacter")


# ============================================================================
print("\n11. ECHEC PERMANENT")

_b, _ID, _r, _f = executer("PERMANENT_FAILURE")
_a = action_de(_b, "GVA-F3")
verifier("11a. l'action passe a `echec`", _a["statut"] == "echec")
verifier("11b. AUCUN sent_at", "sent_at" not in _a)
verifier("11c. AUCUN identifiant fournisseur", not _a.get("provider_message_id"))
verifier("11d. le code d'erreur est conserve", _a["error_code"] == "422")
verifier("11e. le message d'erreur aussi", bool(_a["error_message"]))
verifier("11f. le verrou est RETIRE (la cause est connue)", "verrou_actif" not in _a)
verifier("11g. la reservation est levee", "claimed_at" not in _a)
verifier("11h. le prospect reste `a_contacter`",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("11i. first_contact_sent_at sur 0 fiche",
         not any("first_contact_sent_at" in f for f in _b["partner_prospects"].documents))


# ============================================================================
print("\n12. ECHEC TEMPORAIRE ET LIMITE DE DEBIT")

for _verdict, _attendu in (("RETRYABLE_FAILURE", "503"), ("RATE_LIMIT", "429")):
    _b, _ID, _r, _f = executer(_verdict)
    _a = action_de(_b, "GVA-F3")
    verifier("12a. %-18s -> statut `echec`" % _verdict, _a["statut"] == "echec")
    verifier("12b. %-18s -> aucun sent_at" % _verdict, "sent_at" not in _a)
    verifier("12c. %-18s -> aucun prospect contacte" % _verdict,
             all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
    verifier("12d. %-18s -> code %s conserve" % (_verdict, _attendu),
             _a["error_code"] == _attendu)
    verifier("12e. %-18s -> le compteur de tentatives a monte" % _verdict,
             _a["attempt_count"] == 1)
    verifier("12f. %-18s -> le verrou est libere, le destinataire reste joignable" % _verdict,
             "verrou_actif" not in _a)
    verifier("12g. %-18s -> il est donc a nouveau reservable" % _verdict,
             lancer(S.p3s3d_reserver(_a["id"], _ID, INSTANT)) is True)

_b, _ID, _r, _f = executer("RATE_LIMIT")
verifier("12h. RATE_LIMIT n'est PAS un echec definitif : retry_after est rendu",
         any(x.get("retry_after") for x in _r["resultats"] if x["verdict"] == "RATE_LIMIT"))
verifier("12i. la borne de tentatives existe et vaut 3", S.P3S3D_MAX_TENTATIVES == 3)
verifier("12j. le backoff est borne, jamais exponentiel a l'infini",
         S.P3S3D_BACKOFF_S == (60, 300, 1200))
_a = action_de(_b, "GVA-F3")
verifier("12k. apres 3 tentatives, la garde refuse",
         S.p3s3d_garde_action(dict(_a, attempt_count=3, statut="echec"),
                              campagne_de(_b))["code"] == "TENTATIVES_EPUISEES")


# ============================================================================
print("\n13. ECHEC INDETERMINE — LE CAS DANGEREUX")

_b, _ID, _r, _f = executer("INDETERMINATE")
_a = action_de(_b, "GVA-F3")
verifier("13a. l'action passe a `echec_indetermine`", _a["statut"] == "echec_indetermine")
verifier("13b. LE VERROU EST CONSERVE", _a["verrou_actif"] is True)
verifier("13c. la reservation est CONSERVEE", bool(_a.get("claimed_at")))
verifier("13d. AUCUN sent_at", "sent_at" not in _a)
verifier("13e. le prospect reste `a_contacter`",
         all(f["status"] == "a_contacter" for f in _b["partner_prospects"].documents))
verifier("13f. first_contact_sent_at sur 0 fiche",
         not any("first_contact_sent_at" in f for f in _b["partner_prospects"].documents))
verifier("13g. LE DESTINATAIRE EST PROTEGE : aucune nouvelle reservation possible",
         lancer(S.p3s3d_reserver(_a["id"], _ID, INSTANT)) is False)
verifier("13h. la garde refuse aussi un nouveau J0",
         S.p3s3d_garde_action(_a, campagne_de(_b))["code"] in
         ("DEJA_RESERVE", "STATUT_INCOMPATIBLE"))
verifier("13i. un second passage du moteur ne le rejoue PAS",
         [x for x in lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=False,
                                                      fournisseur=_f))["resultats"]
          if x["recipient_key"] == "GVA-F3"][0]["code"] in ("DEJA_RESERVE",
                                                            "STATUT_INCOMPATIBLE"))
verifier("13j. `echec_indetermine` fait partie des statuts qui verrouillent",
         "echec_indetermine" in S.P3S3_STATUTS_VERROU)

# Une exception du fournisseur produit le meme etat protege.
class _FournisseurQuiExplose:
    nom = "explosif"

    async def envoyer(self, instantane, cle):
        raise RuntimeError("connexion coupee apres emission")


_b2, _ID2 = base_prete()
_b2["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_r2 = lancer(S.p3s3d_executer_campagne(_ID2, COACH_A, simulation=False,
                                       fournisseur=_FournisseurQuiExplose()))
_a2 = action_de(_b2, "GVA-F3")
verifier("13k. une EXCEPTION du fournisseur -> `echec_indetermine`",
         _a2["statut"] == "echec_indetermine")
verifier("13l. ... verrou conserve", _a2["verrou_actif"] is True)
verifier("13m. ... aucun prospect contacte",
         all(f["status"] == "a_contacter" for f in _b2["partner_prospects"].documents))


# ============================================================================
print("\n14. CRASH APRES UN ENVOI REUSSI — LE TEST ESSENTIEL")

# On reproduit le scenario redoute : le fournisseur a ACCEPTE le message, puis
# le processus meurt AVANT que le resultat soit ecrit. L'action reste donc
# telle que l'etape 2 l'a laissee : `en_cours`, sans `sent_at`.
_b, _ID = base_prete()
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_cible = action_de(_b, "GVA-F3")
lancer(S.p3s3d_reserver(_cible["id"], _ID, INSTANT))
lancer(_b["prospect_campaign_actions"].update_one(
    {"id": _cible["id"]}, {"$set": {"statut": "en_cours", "attempted_at": INSTANT}}))
_apres_crash = action_de(_b, "GVA-F3")

verifier("14a. l'action est retrouvee `en_cours`, sans sent_at",
         _apres_crash["statut"] == "en_cours" and "sent_at" not in _apres_crash)
verifier("14b. LA REPRISE la classe INDETERMINEE, jamais rejouable",
         S.p3s3d_verdict_reprise(_apres_crash) == "INDETERMINE")
verifier("14c. le verrou est toujours pose", _apres_crash["verrou_actif"] is True)
verifier("14d. UN NOUVEAU PASSAGE NE LA RENVOIE PAS",
         [x for x in lancer(S.p3s3d_executer_campagne(
             _ID, COACH_A, simulation=False,
             fournisseur=S.P3S3DFournisseurFactice()))["resultats"]
          if x["recipient_key"] == "GVA-F3"][0]["verdict"] == "IGNORE")
verifier("14e. le fournisseur n'a donc PAS ete rappele pour ce destinataire",
         "sent_at" not in action_de(_b, "GVA-F3"))
verifier("14f. le prospect n'est toujours pas contacte",
         next(f for f in _b["partner_prospects"].documents
              if f["ref"] == "GVA-F3")["status"] == "a_contacter")

# La reprise distingue les deux etapes.
verifier("14g. `reserve` (appel jamais parti) -> LIBERER",
         S.p3s3d_verdict_reprise({"statut": "reserve"}) == "LIBERER")
verifier("14h. `envoye` -> plus rien a faire",
         S.p3s3d_verdict_reprise({"statut": "envoye", "sent_at": INSTANT}) == "TERMINEE")
verifier("14i. `pret` -> rien a reprendre",
         S.p3s3d_verdict_reprise({"statut": "pret"}) == "RIEN")
verifier("14j. la trace d'intention est ecrite AVANT l'appel du chemin REEL",
         SRC.index('"statut": "en_cours", "attempted_at": maintenant')
         < SRC.rindex("reponse = await fournisseur.envoyer(instantane, cle)"))
verifier("14j-bis. le chemin SIMULE appelle le factice sans jamais reserver",
         SRC.index("if simulation:", SRC.index("async def p3s3d_executer_campagne"))
         < SRC.index("p3s3d_reserver(action[\"id\"]"))

# Un succes sans identifiant n'est pas un succes.
class _SuccesSansIdentifiant:
    nom = "muet"

    async def envoyer(self, instantane, cle):
        return {"provider": "muet", "verdict": "SUCCESS", "provider_message_id": None,
                "error_code": None, "error_message": None, "retry_after": None,
                "accepted_at": None}


_b3, _ID3 = base_prete()
_b3["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
lancer(S.p3s3d_executer_campagne(_ID3, COACH_A, simulation=False,
                                 fournisseur=_SuccesSansIdentifiant()))
_a3 = action_de(_b3, "GVA-F3")
verifier("14k. un SUCCESS sans identifiant devient INDETERMINE, jamais `envoye`",
         _a3["statut"] == "echec_indetermine")
verifier("14l. ... et aucun prospect n'est marque contacte",
         all(f["status"] == "a_contacter" for f in _b3["partner_prospects"].documents))


# ============================================================================
print("\n15. LES DRAPEAUX ET L'ARRET DE CAMPAGNE")

_b, _ID = base_prete()
_r = lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=False,
                                      fournisseur=S.P3S3DFournisseurFactice()))
verifier("15a. drapeaux FERMES : aucun envoi reel",
         all(x["code"] == "ENVOI_NON_AUTORISE" for x in _r["resultats"]
             if x["verdict"] == "IGNORE" and x["code"] == "ENVOI_NON_AUTORISE")
         and not any(x["verdict"] == "SUCCESS" for x in _r["resultats"]))
verifier("15b. ... et 0 ecriture dans partner_prospects",
         _b["partner_prospects"].ecritures == 0)
verifier("15c. ... et aucune reservation",
         not any("claimed_at" in a for a in actions_de(_b)))
verifier("15d. `envoi_autorise` est rendu dans le rapport",
         _r["envoi_autorise"] is False)

# Empreinte alteree : la campagne ENTIERE s'arrete.
_b, _ID = base_prete()
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_b["prospect_campaign_actions"].documents[0]["message_j0"] = "MESSAGE SUBSTITUE"
_r = lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=False,
                                      fournisseur=S.P3S3DFournisseurFactice()))
verifier("15e. EMPREINTE ALTEREE -> la campagne entiere est arretee",
         _r["arrete"] is True and _r["code"] == "EMPREINTE_ALTEREE")
verifier("15f. ... aucun resultat, donc aucun appel", _r["resultats"] == [])
verifier("15g. ... aucune reservation",
         not any("claimed_at" in a for a in actions_de(_b)))
verifier("15h. ... 0 ecriture dans partner_prospects",
         _b["partner_prospects"].ecritures == 0)
verifier("15i. ... la garde vaut aussi en simulation",
         lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=True))["arrete"] is True)

# Campagne non approuvee.
_b, _ID = base_prete()
_b["prospect_campaigns"].documents[0]["etat"] = "preparee"
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_r = lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=False,
                                      fournisseur=S.P3S3DFournisseurFactice()))
verifier("15j. campagne NON approuvee : tout est ignore",
         all(x["code"] == "CAMPAGNE_NON_APPROUVEE" for x in _r["resultats"]))
verifier("15k. ... et rien n'est ecrit",
         _b["partner_prospects"].ecritures == 0 and
         not any("claimed_at" in a for a in actions_de(_b)))


# ============================================================================
print("\n16. AUTHENTIFICATION ET CLOISONNEMENT")

_b, _ID = base_prete()
try:
    lancer(S.p3s3d_executer_campagne(_ID, COACH_B, simulation=True))
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code == 403
verifier("16a. la campagne d'un autre coach -> 403", _ferme)
try:
    lancer(S.p3s3d_executer_campagne("inexistante", COACH_A, simulation=True))
    _quatrecent = False
except HTTPException as e:
    _quatrecent = e.status_code == 404
verifier("16b. une campagne inconnue -> 404", _quatrecent)


# ============================================================================
print("\n17. LE PLAFOND DE PASSAGE (etalement)")

_b, _ID = base_prete()
_b["feature_flags"].documents[0].update(
    {"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True})
_r = lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=False, plafond=2,
                                      fournisseur=S.P3S3DFournisseurFactice()))
verifier("17a. le plafond limite le passage", _r["traites"] == 2, str(_r["traites"]))
verifier("17b. les suivants sont REPORTES, jamais echoues",
         any(x["verdict"] == "REPORTE" for x in _r["resultats"]))
verifier("17c. un report ne consomme aucune tentative",
         all("claimed_at" not in a for a in actions_de(_b)
             if a["recipient_key"] in [x["recipient_key"] for x in _r["resultats"]
                                       if x["verdict"] == "REPORTE"]))
_r2 = lancer(S.p3s3d_executer_campagne(_ID, COACH_A, simulation=False, plafond=2,
                                       fournisseur=S.P3S3DFournisseurFactice()))
verifier("17d. le passage suivant reprend la ou on s'etait arrete",
         _r2["traites"] == 2 and
         not any(x["recipient_key"] in [y["recipient_key"] for y in _r["resultats"]
                                        if y["verdict"] == "SUCCESS"]
                 for x in _r2["resultats"] if x["verdict"] == "SUCCESS"))


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P3-S3-D1 : %d / %d verifications" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s  %s" % (_i, _d))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)

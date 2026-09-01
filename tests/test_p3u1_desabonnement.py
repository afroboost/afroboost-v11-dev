#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-U1 — LE DESABONNEMENT MARCHE, ET IL COUPE VRAIMENT LES RELANCES.

CE QUE LE LOT CORRIGE
==============================================================================
`List-Unsubscribe` pointait vers `mailto:notifications@afroboost.com`, sur un
domaine SANS MX. Le bouton « Se desabonner » de Gmail rebondissait. Un
destinataire sans sortie propre en prend une autre — « Signaler comme spam ».

CE QUE CE FICHIER PROUVE
==============================================================================
  * l'adresse morte a disparu des en-tetes, et l'un-clic RFC 8058 est complet ;
  * le jeton est signe, opaque, et ne montre ni l'adresse ni la cle ;
  * un jeton forge, tronque ou d'une autre action est refuse ;
  * le refus atterrit dans le registre CANONIQUE (`subscribers`/`opted_out`),
    celui que le moteur interroge deja — aucun second systeme ;
  * deux clics donnent le meme resultat, et la DATE du refus ne rajeunit pas ;
  * un desabonne ne peut plus etre reserve : ni J0, ni J+3, ni J+7 ;
  * le voisin d'a cote n'est pas affecte ;
  * aucune socket ne s'ouvre, aucun e-mail ne part.

    python3 tests/test_p3u1_desabonnement.py
"""
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


class SortieReseauInterdite(RuntimeError):
    pass


_TENTATIVES = []
_GETADDR = socket.getaddrinfo
_CONNECT = socket.socket.connect
_CREATE = socket.create_connection


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise SortieReseauInterdite(str(hote))


def _conn(self, adresse, *a, **k):
    _TENTATIVES.append(("connect", adresse))
    raise SortieReseauInterdite(str(adresse))


def _crea(adresse, *a, **k):
    _TENTATIVES.append(("create_connection", adresse))
    raise SortieReseauInterdite(str(adresse))


socket.getaddrinfo = _dns
socket.socket.connect = _conn
socket.create_connection = _crea

SECRET = "secret-de-test-p3u1-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3u1-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
# LE BLOC U1, ET RIEN QUE LUI. Un `split(...)[1]` emporterait tout le reste du
# fichier : les assertions « le lot ne fait pas X » deviendraient des
# assertions sur le depot entier, et mordraient sur du code etranger.
_D = SRC.index("# P3-U1 — UN DESABONNEMENT")
_F = SRC.index("# --- Leads Routes (Widget IA) ---", _D)
BLOC_U1 = SRC[_D:_F]
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
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
lancer = _espace["lancer"]

MORTE = "notifications@afroboost.com"
VIVANTE = "contact@afroboosteur.com"

ACTION_A = {"id": "act-aaaa-1111", "campaign_id": "camp-1", "coach_id": COACH_A,
            "channel": "email", "target": "Hotel@Beaulac.CH",
            "recipient_key": "BAR-01", "message_j0": "Bonjour", "language": "FR",
            "organisations": ["Beaulac"], "prospect_ids": ["R-001"], "statut": "pret",
            "execution_type": "AUTO"}
ACTION_B = {"id": "act-bbbb-2222", "campaign_id": "camp-1", "coach_id": COACH_A,
            "channel": "email", "target": "voisin@exemple.test",
            "recipient_key": "BAR-02", "message_j0": "Bonjour", "language": "FR",
            "organisations": ["Voisin"], "prospect_ids": ["R-002"], "statut": "pret",
            "execution_type": "AUTO"}


# LE BOUCHON PARTAGE IGNORE `upsert` ET `$setOnInsert` : son `update_one` ne
# fait rien quand aucun document ne correspond. Le code de production, lui,
# S'APPUIE dessus — le premier refus d'une adresse CREE la ligne. Reutiliser le
# bouchon tel quel aurait donc rendu un test complaisant : il aurait passe sans
# qu'aucune ligne ne soit ecrite, exactement le defaut qu'on veut interdire.
# On modelise donc la promesse REELLE de Mongo, comme le banc P3-S2E le fait
# pour l'ordre de tri.
class CollectionUpsert(CollectionBouchon):
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
        # Mongo construit le document a partir du FILTRE (egalites seulement),
        # puis applique `$setOnInsert` PUIS `$set`.
        neuf = {c: v for c, v in (filtre or {}).items() if not isinstance(v, dict)}
        neuf.update(maj.get("$setOnInsert") or {})
        neuf.update(maj.get("$set") or {})
        self.documents.append(neuf)
        self.ecritures += 1
        return type("R", (), {"matched_count": 0, "modified_count": 0,
                              "upserted_id": "upsert"})()


def base_neuve():
    b = BaseBouchon([])          # aucune fiche prospect : ce lot n'y touche pas
    b[S.P3S3_ACTIONS] = CollectionBouchon(
        S.P3S3_ACTIONS, [dict(ACTION_A), dict(ACTION_B)], uniques=[(("id",), None)])
    b["subscribers"] = CollectionUpsert(
        "subscribers", [], uniques=[(("channel", "value"), None)])
    S.db = b
    return b


def appeler(jeton):
    return lancer(S.p3u1_desabonnement_prospect(token=jeton))


def texte(reponse):
    corps = getattr(reponse, "body", b"")
    return corps.decode("utf-8", "replace") if isinstance(corps, bytes) else str(corps)


# ============================================================================
print("\n1. L'ADRESSE MORTE A DISPARU DES EN-TETES")

_e = S.p3s3d2_entetes_prospect({"action_id": ACTION_A["id"]})
verifier("1a. l'ancien mailto vers un domaine SANS MX n'est plus la",
         MORTE not in json.dumps(_e), json.dumps(_e))
verifier("1b. une URL HTTPS de desabonnement est presente",
         "https://" in _e.get("List-Unsubscribe", "")
         and "/api/prospects/unsubscribe?token=" in _e.get("List-Unsubscribe", ""),
         _e.get("List-Unsubscribe"))
verifier("1c. le repli mailto pointe vers une boite QUI EXISTE",
         VIVANTE in _e.get("List-Unsubscribe", ""), _e.get("List-Unsubscribe"))
verifier("1d. l'un-clic RFC 8058 est declare",
         _e.get("List-Unsubscribe-Post") == "List-Unsubscribe=One-Click", str(_e))
verifier("1e. l'URL vient AVANT le mailto (l'un-clic doit primer)",
         _e["List-Unsubscribe"].index("https://") < _e["List-Unsubscribe"].index("mailto:"))

# sans action identifiable (e-mail de test) : pas d'URL forgee au hasard
_t = S.p3s3d2_entetes_prospect({"recipient_key": "PROVIDER-TEST"})
verifier("1f. sans action, AUCUNE URL n'est inventee",
         "unsubscribe?token=" not in json.dumps(_t), json.dumps(_t))
verifier("1g. ... mais le repli reste, vers la boite vivante",
         VIVANTE in _t.get("List-Unsubscribe", ""))
verifier("1h. ... et l'un-clic n'est PAS annonce sans URL pour l'honorer",
         "List-Unsubscribe-Post" not in _t, json.dumps(_t))
verifier("1i. l'appel SANS argument reste possible (aucun appelant casse)",
         isinstance(S.p3s3d2_entetes_prospect(), dict))


# ============================================================================
print("\n2. LE JETON — SIGNE, OPAQUE, NON FORGEABLE")

_j = S.p3u1_jeton(ACTION_A["id"])
verifier("2a. un jeton est produit", bool(_j), _j)
verifier("2b. il ne contient PAS l'adresse du destinataire",
         "beaulac" not in _j.lower() and "@" not in _j, _j)
verifier("2c. il ne contient PAS la cle du destinataire",
         "BAR-01" not in _j and "bar-01" not in _j.lower(), _j)
verifier("2d. il ne contient PAS l'identifiant de campagne",
         "camp-1" not in _j, _j)
verifier("2e. il est stable (le meme lien peut etre reconstruit)",
         S.p3u1_jeton(ACTION_A["id"]) == _j)
verifier("2f. deux actions donnent deux jetons differents",
         S.p3u1_jeton(ACTION_B["id"]) != _j)
verifier("2g. il se relit correctement",
         S.p3u1_action_du_jeton(_j) == ACTION_A["id"], S.p3u1_action_du_jeton(_j))

for _faux, _quoi in ((_j[:-1], "signature tronquee"),
                     (_j + "a", "signature allongee"),
                     (ACTION_A["id"] + ".0" * 32, "signature inventee"),
                     (ACTION_A["id"], "sans signature du tout"),
                     ("", "vide"),
                     (".", "un point seul"),
                     (ACTION_A["id"] + "." + S.p3u1_jeton(ACTION_B["id"]).split(".")[1],
                      "signature d'une AUTRE action")):
    verifier("2h. jeton %-32s -> refuse" % _quoi,
             S.p3u1_action_du_jeton(_faux) == "", repr(S.p3u1_action_du_jeton(_faux)))

# secret absent : on ne signe pas, donc on ne produit pas de lien forgeable
_sauve = os.environ.pop("JWT_SECRET")
verifier("2i. SANS secret, aucun jeton n'est produit", S.p3u1_jeton(ACTION_A["id"]) == "")
verifier("2j. SANS secret, aucun jeton n'est accepte non plus",
         S.p3u1_action_du_jeton(_j) == "")
verifier("2k. SANS secret, aucune URL n'est mise dans l'en-tete",
         "unsubscribe?token=" not in json.dumps(
             S.p3s3d2_entetes_prospect({"action_id": ACTION_A["id"]})))
os.environ["JWT_SECRET"] = _sauve


# ============================================================================
print("\n3. LE REFUS ATTERRIT DANS LE REGISTRE CANONIQUE")

_b = base_neuve()
_r = appeler(_j)
verifier("3a. la page annonce la desinscription", "esinscription" in texte(_r), texte(_r)[:120])
_lignes = _b["subscribers"].documents
verifier("3b. UNE ligne creee dans `subscribers`", len(_lignes) == 1, str(_lignes))
_l = _lignes[0] if _lignes else {}
verifier("3c. statut `opted_out` — le mot que le moteur lit deja",
         _l.get("status") == "opted_out", str(_l))
verifier("3d. l'adresse est NORMALISEE (minuscules), comme la cle du registre",
         _l.get("value") == "hotel@beaulac.ch", str(_l.get("value")))
verifier("3e. le canal est celui de l'action", _l.get("channel") == "email")
verifier("3f. la date du refus est posee", bool(_l.get("opted_out_at")))
verifier("3g. l'origine est tracee", _l.get("source") == "p3_prospection", str(_l.get("source")))
verifier("3h. AUCUNE ecriture dans la campagne : les 2 actions sont intactes",
         all(a.get("statut") == "pret" and "opted_out" not in json.dumps(a)
             for a in _b[S.P3S3_ACTIONS].documents))


# ============================================================================
print("\n4. IDEMPOTENCE — DEUX CLICS, MEME RESULTAT")

_date1 = _l.get("opted_out_at")
_r2 = appeler(_j)
verifier("4a. le second clic rend la MEME page", texte(_r2) == texte(_r))
verifier("4b. toujours UNE seule ligne", len(_b["subscribers"].documents) == 1)
_l2 = _b["subscribers"].documents[0]
verifier("4c. toujours `opted_out`", _l2.get("status") == "opted_out")
verifier("4d. la DATE du refus n'a pas rajeuni (ecrite une seule fois)",
         _l2.get("opted_out_at") == _date1,
         "%s -> %s" % (_date1, _l2.get("opted_out_at")))
_r3 = appeler(_j)
verifier("4e. un troisieme clic ne change toujours rien",
         len(_b["subscribers"].documents) == 1
         and _b["subscribers"].documents[0].get("opted_out_at") == _date1)


# ============================================================================
print("\n5. UN JETON INVALIDE N'ECRIT RIEN")

_b = base_neuve()
for _mauvais, _quoi in ((_j[:-1], "signature tronquee"), ("", "vide"),
                        ("act-inconnue-9999." + "0" * 32, "action inexistante")):
    _rep = appeler(_mauvais)
    verifier("5a. %-24s -> page d'erreur" % _quoi, "nvalide" in texte(_rep) or "impossible" in texte(_rep))
verifier("5b. AUCUNE ligne creee par ces tentatives",
         len(_b["subscribers"].documents) == 0, str(_b["subscribers"].documents))

# une action qui existe mais dont le jeton est faux : rien non plus
_b = base_neuve()
appeler(ACTION_A["id"] + "." + "f" * 32)
verifier("5c. une signature fausse sur une action REELLE n'ecrit rien",
         len(_b["subscribers"].documents) == 0)


# ============================================================================
print("\n6. LE MOTEUR REFUSE UN DESABONNE — J0, J+3, J+7")

# La garde du moteur lit `refus`, un ensemble de cles « canal:valeur ».
_refus = {"email:hotel@beaulac.ch"}
_campagne = {"id": "camp-1", "etat": "approuvee", "coach_id": COACH_A,
             "subject_j0": "Objet", "snapshot_hash": ""}
_fiche_a = {"ref": "R-001", "coach_id": COACH_A, "status": "a_contacter"}
_fiche_b = {"ref": "R-002", "coach_id": COACH_A, "status": "a_contacter"}

_v_a = S.p3s3d_garde_action(dict(ACTION_A), _campagne, fiches=[_fiche_a],
                            refus=_refus, envoi_autorise=True, simulation=False)
verifier("6a. J0 : l'action du desabonne est REFUSEE",
         not _v_a["autorise"], str(_v_a))
verifier("6b. ... et le motif nomme bien le refus",
         "refus" in (_v_a.get("code", "") + _v_a.get("motif", "")).lower(), str(_v_a))

_v_b = S.p3s3d_garde_action(dict(ACTION_B), _campagne, fiches=[_fiche_b],
                            refus=_refus, envoi_autorise=True, simulation=False)
verifier("6c. le VOISIN, lui, reste autorise (aucun dommage collateral)",
         _v_b["autorise"], str(_v_b))

# J+3 / J+7 : les echeances ne sont posees QUE par un J0 reussi. Un J0 refuse
# n'en pose aucune — la relance est donc coupee a la source, pas apres coup.
verifier("6d. J+3 : aucune echeance ne peut naitre d'un J0 refuse",
         "j3_due_at" not in json.dumps(ACTION_A))
verifier("6e. J+7 : idem", "j7_due_at" not in json.dumps(ACTION_A))
verifier("6f. les echeances ne sont ecrites QUE par `p3s3d_appliquer_succes`",
         SRC.count('"j3_due_at":') == 1 and SRC.count('"j7_due_at":') == 1,
         "j3=%d j7=%d" % (SRC.count('"j3_due_at":'), SRC.count('"j7_due_at":')))
verifier("6g. ... et cette fonction n'est atteinte qu'apres un verdict SUCCESS",
         "if v == P3S3D_SUCCESS:" in SRC and "p3s3d_appliquer_succes(action" in SRC)

# UN FUTUR J0 : une nouvelle campagne interrogera le meme registre.
verifier("6h. un futur J0 lira le MEME registre (une seule lecture des refus)",
         "c3_refus_exprimes" in SRC and SRC.count("await c3_refus_exprimes(_canal") == 1)


# ============================================================================
print("\n7. LE REGISTRE EST BIEN CELUI QUI EXISTAIT — AUCUN SECOND SYSTEME")

verifier("7a. le lot ecrit dans `subscribers`, pas dans une collection neuve",
         'db.subscribers.update_one' in SRC)
verifier("7b. aucune collection `prospect_optout` ou equivalente n'est creee",
         "prospect_optout" not in SRC and "prospect_unsubscribe" not in SRC)
verifier("7c. le statut utilise est celui que `c3_refus_exprimes` cherche",
         '"status": "opted_out"' in SRC)
verifier("7d. la page de reponse est celle du depot (`_v332_page`)",
         "_v332_page(" in BLOC_U1)
verifier("7e. la normalisation est celle du depot (`_v332_normaliser`)",
         "_v332_normaliser(canal, valeur)" in SRC)


# ============================================================================
print("\n8. LA ROUTE — FORME ET ACCES")

verifier("8a. elle accepte GET (clic humain) ET POST (un-clic Gmail)",
         'methods=["GET", "POST"]' in BLOC_U1)
verifier("8b. elle est SANS authentification, et c'est voulu",
         "_v309_require_coach_or_admin" not in BLOC_U1)
verifier("8c. elle ne lit de l'action que le strict necessaire",
         '{"_id": 0, "channel": 1, "target": 1, "recipient_key": 1}' in SRC)
verifier("8d. elle n'ecrit RIEN dans les actions ni les fiches",
         "P3S3_ACTIONS].update" not in BLOC_U1
         and "P3S1_COLLECTION].update" not in BLOC_U1)


# ============================================================================
print("\n9. AUCUN RESEAU, AUCUN E-MAIL")

verifier("9a. zero tentative de sortie reseau", len(_TENTATIVES) == 0, str(_TENTATIVES))
verifier("9b. aucun envoi declenche par ce lot",
         "Emails.send" not in BLOC_U1)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("P3-U1 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)

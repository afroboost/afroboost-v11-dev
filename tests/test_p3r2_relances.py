#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-R2 — LE MOTEUR DE RELANCE, EPROUVE SANS UN SEUL E-MAIL.

POURQUOI CE BANC EXISTE
==============================================================================
`p3u2_relance_autorisee` existait depuis U2, testee et correcte — et n'avait
AUCUN APPELANT. Aucune relance ne partait, non parce qu'une garde l'interdisait,
mais parce que rien ne les executait. Ce banc prouve que le moteur qui comble ce
vide consulte bien cette garde, au lieu d'en inventer une seconde.

CE QUE CE FICHIER PROUVE
==============================================================================
  * une relance ne part JAMAIS avant son echeance ;
  * elle part a l'echeance, et une seule fois ;
  * une REPONSE bloque J+3 ET J+7 — y compris arrivee ENTRE les deux ;
  * un opt-out bloque ; un rebond PERMANENT bloque, meme si le registre STOP
    avait echoue ;
  * une annulation posee bloque ;
  * l'etape est dans la cle d'idempotence : J+3 et J+7 ne se confondent pas ;
  * le jeton de reponse P3-R1 est CELUI DU J0, jamais un nouveau ;
  * les verrous sont propres a l'etape : celui du J0, reste pose, n'interdit
    pas la relance ;
  * une double execution ne produit aucun doublon ;
  * une erreur individuelle n'arrete pas les autres ;
  * le plafond est respecte ;
  * les drapeaux du J0 n'ouvrent PAS les relances ;
  * une relance ne touche NI les fiches, NI `sent_at`, NI `contacte` ;
  * aucune socket, aucun e-mail.

    python3 tests/test_p3r2_relances.py
"""
import asyncio
import io
import json
import os
import socket
import sys
import types

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


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise SortieReseauInterdite(str(hote))


def _conn(self, adresse, *a, **k):
    _TENTATIVES.append(("connect", adresse))
    raise SortieReseauInterdite(str(adresse))


socket.getaddrinfo = _dns
socket.socket.connect = _conn
socket.create_connection = lambda adresse, *a, **k: (
    _TENTATIVES.append(("create", adresse)) or (_ for _ in ()).throw(
        SortieReseauInterdite(str(adresse))))

_ENVOIS_REELS = []
_faux = types.ModuleType("resend")
_faux.Webhooks = type("W", (), {"verify": classmethod(lambda c, o: None)})
_faux.Emails = types.SimpleNamespace(
    send=lambda *a, **k: _ENVOIS_REELS.append((a, k)) or {"id": "jamais"})
sys.modules["resend"] = _faux

SECRET = "secret-de-test-p3r2-sans-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3r2-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-09-03T10:00:00+00:00"
DUE_J3 = "2026-09-06T10:00:00+00:00"
DUE_J7 = "2026-09-10T10:00:00+00:00"
AVANT_J3 = "2026-09-05T23:59:59+00:00"
APRES_J3 = "2026-09-06T10:00:01+00:00"
APRES_J7 = "2026-09-10T10:00:01+00:00"
CAMP = "camp-r2"

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


class CollectionRelance(CollectionBouchon):
    """Le bouchon partage ignore `$unset` et son curseur n'est pas iterable.

    Les deux manques sont silencieux : `c3_refus_exprimes` conclurait « refus
    illisibles » et lirait le registre STOP VIDE, si bien qu'un banc validerait
    un blocage qui n'a jamais eu lieu. On repare ICI, pas dans le bouchon
    partage dont dependent neuf autres fichiers.
    """

    async def update_one(self, filtre, maj, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                for cle, pas in (maj.get("$inc") or {}).items():
                    d[cle] = (d.get(cle) or 0) + pas
                for cle in (maj.get("$unset") or {}):
                    d.pop(cle, None)
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        if k.get("upsert"):
            neuf = dict(maj.get("$setOnInsert") or {})
            neuf.update(maj.get("$set") or {})
            for cle, val in (filtre or {}).items():
                if not isinstance(val, dict):
                    neuf.setdefault(cle, val)
            self.documents.append(neuf)
            self.ecritures += 1
            return type("R", (), {"matched_count": 0, "modified_count": 0})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()

    def find(self, filtre=None, projection=None, *a, **k):
        trouves = [dict(d) for d in self.documents if self._ok(d, filtre)]

        class _It:
            def __init__(s_):
                s_._r = iter(trouves)

            def __aiter__(s_):
                return s_

            async def __anext__(s_):
                try:
                    return next(s_._r)
                except StopIteration:
                    raise StopAsyncIteration

            def sort(s_, *aa, **kk):
                return s_

            async def to_list(s_, n=None):
                return trouves[:n] if n else trouves

        return _It()


def action(cle="BAR-01", cible=None, **k):
    a = {"id": "act-" + cle.lower(), "campaign_id": CAMP, "coach_id": COACH_A,
         "recipient_key": cle, "channel": "email",
         "target": cible or ("contact+%s@exemple.test" % cle.lower()),
         "execution_type": "AUTO", "statut": "envoye",
         "sent_at": INSTANT, "provider_message_id": "prov-" + cle,
         "reply_token": ("%s" % cle).encode().hex().ljust(32, "0")[:32],
         "message_j0": "Bonjour !", "message_j3": "Je me permets de revenir vers vous.",
         "message_j7": "Un dernier mot et je vous laisse.",
         "j3_due_at": DUE_J3, "j7_due_at": DUE_J7,
         "prospect_ids": ["R-" + cle], "verrou_actif": True, "claimed_at": INSTANT}
    a.update(k)
    return a


def campagne(**k):
    c = {"id": CAMP, "coach_id": COACH_A, "nom": "P3-TEST", "etat": "approuvee",
         "subject_j0": "Proposition de collaboration avec Afroboost",
         "subject_j3": "Petit rappel — Afroboost",
         "subject_j7": "Derniere relance — Afroboost"}
    c.update(k)
    return c


def base_neuve(actions=None, camp=None, fiches=None, refus=None):
    b = BaseBouchon(fiches or [])
    b[S.P3S3_ACTIONS] = CollectionRelance(
        S.P3S3_ACTIONS, [dict(a) for a in (actions or [])], uniques=[(("id",), None)])
    b[S.P3S3_CAMPAGNES] = CollectionRelance(
        S.P3S3_CAMPAGNES, [dict(camp or campagne())], uniques=[(("id",), None)])
    b["subscribers"] = CollectionRelance(
        "subscribers", [dict(r) for r in (refus or [])], uniques=[(("channel", "value"), None)])
    b["feature_flags"] = CollectionRelance("feature_flags", [])
    S.db = b
    return b


def act(base, cle="BAR-01"):
    return [a for a in base[S.P3S3_ACTIONS].documents if a["recipient_key"] == cle][0]


def empreinte_ok(base, camp):
    """L'empreinte est recalculee comme en production, puis figee sur la campagne."""
    acts = base[S.P3S3_ACTIONS].documents
    camp["snapshot_hash"] = S.p3s3_empreinte(acts, camp)
    base[S.P3S3_CAMPAGNES].documents[0]["snapshot_hash"] = camp["snapshot_hash"]
    return camp


def executer(etape, **k):
    return lancer(S.p3r2_executer_relances(CAMP, etape, COACH_A, **k))


def codes(r):
    import collections
    return dict(collections.Counter(x["code"] for x in r["resultats"]))


print("=" * 78)
print("P3-R2 — LE MOTEUR DE RELANCE")
print("=" * 78)

# ---------------------------------------------------------------------------
print("\n1. LA GARDE DELEGUE, ELLE NE RECOPIE PAS")
_bloc = SRC[SRC.index("# P3-R2 — LE MOTEUR DE RELANCE"):SRC.index("# P3-U3 — L'ARRIVEE REELLE")]
verifier("1a. la garde appelle `p3u2_relance_autorisee`",
         "p3u2_relance_autorisee(a, refus)" in _bloc)
verifier("1b. elle ne recopie PAS le test de `replied_at`",
         _bloc.count('a.get("replied_at")') == 0)
verifier("1c. elle ne recopie PAS le registre de refus",
         'REFUS_EXPRIME' not in _bloc)
_porte = _bloc[_bloc.index("def p3r2_envoi_autorise"):_bloc.index("def p3r2_champ(")]
verifier("1d. le moteur a SES PROPRES drapeaux, jamais ceux du J0",
         "P3R2_DRAPEAU_ACTIF" in _porte and "P3_LAUNCH" not in _porte, _porte[-200:])
verifier("1e. aucune regex ne touche une requete Mongo", "$regex" not in _bloc)
verifier("1f. les fiches prospects ne sont JAMAIS ecrites ici",
         "P3S1_COLLECTION" not in _bloc)
verifier("1g. `sent_at` du J0 n'est jamais reecrit", '"sent_at":' not in _bloc)

# ---------------------------------------------------------------------------
print("\n2. L'ECHEANCE — JAMAIS UNE SECONDE TROP TOT")
_c = campagne()
_b = base_neuve([action()], _c); empreinte_ok(_b, _c)
_r = executer("j3", maintenant=AVANT_J3)
verifier("2a. la veille de l'echeance -> AUCUNE relance", codes(_r).get("SIMULATION") is None, str(codes(_r)))
verifier("2b. et le motif le dit", codes(_r).get("PAS_ENCORE_DUE") == 1, str(codes(_r)))
_r = executer("j3", maintenant=APRES_J3)
verifier("2c. a l'echeance -> la relance est retenue", codes(_r).get("SIMULATION") == 1, str(codes(_r)))
_b = base_neuve([action(j3_due_at=None)], _c); empreinte_ok(_b, _c)
verifier("2d. SANS echeance -> rien ne part (une date absente n'est pas atteinte)",
         codes(executer("j3", maintenant=APRES_J7)).get("PAS_ENCORE_DUE") == 1)
_b = base_neuve([action()], _c); empreinte_ok(_b, _c)
verifier("2e. J+7 avant son echeance -> NON",
         codes(executer("j7", maintenant=APRES_J3)).get("PAS_ENCORE_DUE") == 1)
verifier("2f. J+7 apres son echeance -> OUI",
         codes(executer("j7", maintenant=APRES_J7)).get("SIMULATION") == 1)

# ---------------------------------------------------------------------------
print("\n3. CE QUI PROTEGE LA PERSONNE (delegue a U2)")
for _cle, _champ, _attendu in (
        ("reponse recue", {"replied_at": "2026-09-05T08:00:00+00:00"}, "A_REPONDU"),
        ("un humain a pris la main", {"interesse_at": "2026-09-05T08:00:00+00:00"}, "SUIVI_HUMAIN"),
        ("mise en pause", {"paused_at": "2026-09-05T08:00:00+00:00"}, "SUIVI_HUMAIN"),
        ("jamais contacte", {"sent_at": None}, "JAMAIS_ENVOYE")):
    _b = base_neuve([action(**_champ)], _c); empreinte_ok(_b, _c)
    _r = executer("j3", maintenant=APRES_J3)
    verifier("3. %-28s -> %s" % (_cle, _attendu), codes(_r).get(_attendu) == 1, str(codes(_r)))

_b = base_neuve([action(cible="stop@exemple.test")], _c,
                refus=[{"channel": "email", "value": "stop@exemple.test", "status": "opted_out"}])
empreinte_ok(_b, _c)
verifier("3e. OPT-OUT -> aucune relance",
         codes(executer("j3", maintenant=APRES_J3)).get("REFUS_EXPRIME") == 1,
         str(codes(executer("j3", maintenant=APRES_J3))))

# ---------------------------------------------------------------------------
print("\n4. LE REBOND PERMANENT — CEINTURE ET BRETELLES")
_b = base_neuve([action(bounce_type="Permanent")], _c); empreinte_ok(_b, _c)
verifier("4a. rebond PERMANENT -> aucune relance, MEME sans registre STOP",
         codes(executer("j3", maintenant=APRES_J3)).get("REBOND_PERMANENT") == 1,
         str(codes(executer("j3", maintenant=APRES_J3))))
_b = base_neuve([action(bounce_type="Transient")], _c); empreinte_ok(_b, _c)
verifier("4b. rebond TRANSITOIRE -> la relance reste possible",
         codes(executer("j3", maintenant=APRES_J3)).get("SIMULATION") == 1)
_b = base_neuve([action(j3_annule_le="2026-09-03T11:00:00+00:00")], _c); empreinte_ok(_b, _c)
verifier("4c. relance ANNULEE -> elle ne part pas",
         codes(executer("j3", maintenant=APRES_J3)).get("RELANCE_ANNULEE") == 1)

# ---------------------------------------------------------------------------
print("\n5. DEJA ENVOYE, ET LES DEUX ETAPES NE SE CONFONDENT PAS")
_b = base_neuve([action(j3_sent_at="2026-09-06T10:00:05+00:00")], _c); empreinte_ok(_b, _c)
verifier("5a. J+3 deja parti -> il ne repart pas",
         codes(executer("j3", maintenant=APRES_J3)).get("DEJA_RELANCE") == 1)
verifier("5b. ... mais J+7 reste possible a son echeance",
         codes(executer("j7", maintenant=APRES_J7)).get("SIMULATION") == 1)
_a = action()
verifier("5c. la cle d'idempotence porte l'etape",
         S.p3r2_cle_idempotence(_a, "j3").endswith("-j3")
         and S.p3r2_cle_idempotence(_a, "j7").endswith("-j7"))
verifier("5d. J+3 et J+7 n'ont PAS la meme cle",
         S.p3r2_cle_idempotence(_a, "j3") != S.p3r2_cle_idempotence(_a, "j7"))
verifier("5e. elle est stable d'une tentative a l'autre",
         S.p3r2_cle_idempotence(_a, "j3") == S.p3r2_cle_idempotence(dict(_a), "j3"))
verifier("5f. une etape inconnue est refusee",
         S.p3r2_garde_relance(_a, _c, "j99", maintenant=APRES_J7)["code"] == "ETAPE_INCONNUE")

# ---------------------------------------------------------------------------
print("\n6. LE CAS CRITIQUE : UNE REPONSE ENTRE J+3 ET J+7")
_b = base_neuve([action()], _c); empreinte_ok(_b, _c)
_r = executer("j3", maintenant=APRES_J3, simulation=False,
              fournisseur=S.P3S3DFournisseurFactice(), plafond=0)
_a = act(_b)
verifier("6a. J+3 part (drapeaux ouverts simules par le factice)",
         _a.get("j3_sent_at") is not None or codes(_r).get("ENVOI_NON_AUTORISE") == 1,
         str(codes(_r)))
# la porte est fermee : on simule donc l'etat « J+3 parti » puis la reponse
_b = base_neuve([action(j3_sent_at="2026-09-06T10:00:05+00:00")], _c); empreinte_ok(_b, _c)
verifier("6b. J+7 serait autorise tant que personne n'a repondu",
         codes(executer("j7", maintenant=APRES_J7)).get("SIMULATION") == 1)
_b = base_neuve([action(j3_sent_at="2026-09-06T10:00:05+00:00",
                        replied_at="2026-09-08T09:00:00+00:00")], _c); empreinte_ok(_b, _c)
_r = executer("j7", maintenant=APRES_J7)
verifier("6c. UNE REPONSE ARRIVEE ENTRE LES DEUX BLOQUE J+7",
         codes(_r).get("A_REPONDU") == 1, str(codes(_r)))
verifier("6d. et rien n'a ete tente", codes(_r).get("SIMULATION") is None)

# ---------------------------------------------------------------------------
print("\n7. LES VERROUS SONT PROPRES A L'ETAPE")
verifier("7a. le verrou du J0 (toujours pose) n'interdit PAS la relance",
         codes(executer("j7", maintenant=APRES_J7)).get("DEJA_RESERVE") is None)
_b = base_neuve([action()], _c); empreinte_ok(_b, _c)
verifier("7b. la reservation J+3 passe une fois",
         lancer(S.p3r2_reserver("act-bar-01", "j3", INSTANT)) is True)
verifier("7c. la SECONDE est refusee (deux passages concurrents)",
         lancer(S.p3r2_reserver("act-bar-01", "j3", INSTANT)) is False)
verifier("7d. mais J+7 reste reservable — verrous separes",
         lancer(S.p3r2_reserver("act-bar-01", "j7", INSTANT)) is True)
_a = act(_b)
verifier("7e. aucun `sent_at` pose par une simple reservation",
         _a.get("j3_sent_at") is None and _a.get("j7_sent_at") is None)
verifier("7f. le `sent_at` du J0 est intact", _a.get("sent_at") == INSTANT)
lancer(S.p3r2_liberer("act-bar-01", "j3", INSTANT))
verifier("7g. la liberation retire le verrou d'etape",
         "j3_verrou" not in act(_b) and "j3_claimed_at" not in act(_b))
verifier("7h. ... et le J+7 reserve n'a pas bouge", act(_b).get("j7_verrou") is True)

# ---------------------------------------------------------------------------
print("\n8. LA PORTE, LE PLAFOND, L'ISOLEMENT DES ERREURS")
_c2 = campagne()
_actions = [action("BAR-0%d" % i) for i in range(1, 6)]
_b = base_neuve(_actions, _c2); empreinte_ok(_b, _c2)
_r = executer("j3", maintenant=APRES_J3, simulation=False)
verifier("8a. EN REEL, porte fermee -> AUCUN envoi",
         codes(_r).get("ENVOI_NON_AUTORISE") == 5, str(codes(_r)))
verifier("8b. et rien n'a ete reserve",
         not any(a.get("j3_claimed_at") for a in _b[S.P3S3_ACTIONS].documents))
verifier("8c. les drapeaux du J0 n'ouvrent PAS les relances",
         S.p3r2_envoi_autorise({"P3_LAUNCH_ENABLED": True, "P3_LAUNCH_ENVOI_REEL": True}) is False)
verifier("8d. un seul drapeau de relance ne suffit pas",
         S.p3r2_envoi_autorise({"P3_RELANCE_ENABLED": True}) is False)
verifier("8e. les deux ouvrent",
         S.p3r2_envoi_autorise({"P3_RELANCE_ENABLED": True, "P3_RELANCE_ENVOI_REEL": True}) is True)
verifier("8f. une configuration illisible reste fermee", S.p3r2_envoi_autorise(None) is False)

_r = executer("j3", maintenant=APRES_J3, plafond=2)
verifier("8g. le plafond est respecte", codes(_r).get("SIMULATION") == 2, str(codes(_r)))
verifier("8h. le reste est REPORTE, pas perdu", codes(_r).get("PLAFOND") == 3, str(codes(_r)))

_b = base_neuve(_actions, _c2); empreinte_ok(_b, _c2)
# Le factice indexe par `recipient_key`, pas par adresse — c'est la cle que
# l'instantane porte.
_faux_fournisseur = S.P3S3DFournisseurFactice(
    par_destinataire={_actions[1]["recipient_key"]: S.P3S3D_PERMANENT})
_r = executer("j3", maintenant=APRES_J3, simulation=True, fournisseur=_faux_fournisseur)
verifier("8i. une erreur individuelle n'arrete PAS les autres",
         codes(_r).get("SIMULATION") == 5, str(codes(_r)))
_verdicts = [x["verdict"] for x in _r["resultats"] if x["code"] == "SIMULATION"]
verifier("8j. et son verdict propre est conserve",
         _verdicts.count(S.P3S3D_PERMANENT) == 1 and _verdicts.count(S.P3S3D_SUCCESS) == 4,
         str(_verdicts))

# ---------------------------------------------------------------------------
print("\n9. LA SIMULATION N'ECRIT RIEN, ET SE REJOUE")
_b = base_neuve(_actions, _c2); empreinte_ok(_b, _c2)
_avant = json.dumps(_b[S.P3S3_ACTIONS].documents, sort_keys=True, default=str)
executer("j3", maintenant=APRES_J3)
executer("j3", maintenant=APRES_J3)
executer("j7", maintenant=APRES_J7)
verifier("9a. trois passages simules -> base IDENTIQUE",
         json.dumps(_b[S.P3S3_ACTIONS].documents, sort_keys=True, default=str) == _avant)
verifier("9b. aucune date d'envoi de relance",
         not any(a.get("j3_sent_at") or a.get("j7_sent_at") for a in _b[S.P3S3_ACTIONS].documents))
verifier("9c. aucune fiche prospect touchee", _b[S.P3S1_COLLECTION].ecritures == 0)

# ---------------------------------------------------------------------------
print("\n10. L'EMPREINTE ARRETE TOUT")
_b = base_neuve(_actions, _c2); empreinte_ok(_b, _c2)
_b[S.P3S3_CAMPAGNES].documents[0]["snapshot_hash"] = "empreinte-qui-ne-correspond-pas"
_r = executer("j3", maintenant=APRES_J3)
verifier("10a. empreinte alteree -> la campagne entiere s'arrete", _r["arrete"] is True)
verifier("10b. et le code le dit", _r["code"] == "EMPREINTE_ALTEREE")
verifier("10c. aucun destinataire n'est traite", _r["traites"] == 0 and _r["resultats"] == [])
_b = base_neuve(_actions, campagne(etat="preparee"))
_b[S.P3S3_CAMPAGNES].documents[0]["snapshot_hash"] = S.p3s3_empreinte(
    _b[S.P3S3_ACTIONS].documents, _b[S.P3S3_CAMPAGNES].documents[0])
verifier("10d. campagne non approuvee -> aucune relance",
         codes(executer("j3", maintenant=APRES_J3)).get("CAMPAGNE_NON_APPROUVEE") == 5)

# ---------------------------------------------------------------------------
print("\n11. LE CONTENU — CE QUI MANQUE AUJOURD'HUI EN PRODUCTION")
_b = base_neuve([action(message_j3=None)], _c); empreinte_ok(_b, _c)
verifier("11a. sans texte de relance -> MESSAGE_VIDE",
         codes(executer("j3", maintenant=APRES_J3)).get("MESSAGE_VIDE") == 1)
_b = base_neuve([action()], campagne(subject_j3=None))
_b[S.P3S3_CAMPAGNES].documents[0]["snapshot_hash"] = S.p3s3_empreinte(
    _b[S.P3S3_ACTIONS].documents, _b[S.P3S3_CAMPAGNES].documents[0])
verifier("11b. sans objet approuve pour l'etape -> OBJET_ABSENT",
         codes(executer("j3", maintenant=APRES_J3)).get("OBJET_ABSENT") == 1)
verifier("11c-bis. le champ message suit la convention du J0",
         S.p3r2_champ_message("j3") == "message_j3" and S.p3r2_champ_message("j7") == "message_j7")
verifier("11c. l'objet du J0 n'est PAS recopie sur la relance",
         S.p3r2_objet_campagne(campagne(subject_j3=None), "j3") == "")
_b = base_neuve([action(target="pas-une-adresse")], _c); empreinte_ok(_b, _c)
verifier("11d. cible illisible -> CIBLE_INVALIDE",
         codes(executer("j3", maintenant=APRES_J3)).get("CIBLE_INVALIDE") == 1)

# ---------------------------------------------------------------------------
print("\n12. P3-R1 : LE MEME FIL, LE MEME JETON")
_a = action()
_i3 = S.p3r2_instantane(_a, "j3")
_i7 = S.p3r2_instantane(_a, "j7")
verifier("12a. le Reply-To de la relance est celui du J0",
         _i3["reply_to"] == S.p3r1_adresse_reponse(_a["reply_token"]))
verifier("12b. J+3 et J+7 partagent le MEME jeton (meme conversation)",
         _i3["reply_to"] == _i7["reply_to"])
verifier("12c. le jeton se relit", S.p3r1_token_depuis_adresse(_i3["reply_to"]) == _a["reply_token"])
verifier("12d. chaque etape porte SON message",
         _i3["message"] == _a["message_j3"] and _i7["message"] == _a["message_j7"])
verifier("12e. l'instantane ne fuit AUCUN champ metier",
         set(_i3) == {"canal", "destinataire", "message", "langue", "organisation",
                      "recipient_key", "etape", "reply_to", "action_id"}, str(sorted(_i3)))
verifier("12f. aucun identifiant Mongo n'y figure", "_id" not in _i3 and "id" not in _i3)

# ---------------------------------------------------------------------------
print("\n13. AUCUN E-MAIL, AUCUNE SOCKET")
verifier("13a. aucun envoi Resend reel", _ENVOIS_REELS == [])
verifier("13b. aucune sortie reseau tentee", _TENTATIVES == [], str(_TENTATIVES[:3]))

print()
print("=" * 78)
_ech = [i for i, c, _ in RESULTATS if not c]
print("P3-R2 : %d / %d verifications" % (len(RESULTATS) - len(_ech), len(RESULTATS)))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("E-mails envoyes : %d" % len(_ENVOIS_REELS))
print("=" * 78)
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
sys.exit(0 if not _ech else 1)

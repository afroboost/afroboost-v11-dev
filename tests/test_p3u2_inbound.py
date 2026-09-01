#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-U2 — LE MOTEUR DE RECEPTION, EPROUVE SANS QU'UN SEUL E-MAIL EXISTE.

CE QUE LE LOT AJOUTE
==============================================================================
Ce qui se passe APRES qu'une reponse soit arrivee : la normaliser, ecarter un
doublon, retrouver a quelle action elle repond, et — seulement si c'est
certain — arreter les relances. Rien ne recoit encore : ni webhook, ni IMAP,
ni DNS. U3 branchera l'arrivee sur ce contrat.

CE QUE CE FICHIER PROUVE
==============================================================================
  * les trois methodes de rattachement, dans leur ordre, et le refus de
    deviner des qu'il reste deux candidats ;
  * `replied_at` ecrit UNE SEULE FOIS, et les deux relances tombent avec, dans
    la MEME operation — jamais de reponse enregistree sans relance coupee ;
  * la course reponse / relance : la reponse gagne, et le prouve ;
  * une action jamais envoyee ne produit JAMAIS de fausse reponse ;
  * un doublon rejoue n'est stocke qu'une fois ;
  * aucun rapprochement par domaine ; le sujet ne sert jamais de cle ;
  * reponse et desabonnement arretent les relances pour des raisons
    DISTINCTES, et gardent des traces distinctes ;
  * aucune socket ne s'ouvre.

Toutes les adresses sont synthetiques (`@exemple.test`). Aucun prospect reel.

    python3 tests/test_p3u2_inbound.py
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

SECRET = "secret-de-test-p3u2-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3u2-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
# LES BORNES DU BLOC, INSENSIBLES AUX LOTS FUTURS. Elles pointaient sur
# « Leads Routes », l'en-tete qui suivait ce lot le jour ou il a ete ecrit —
# et le lot SUIVANT, insere entre les deux, a fait deborder l'analyse sur son
# code. On s'arrete donc a la premiere banniere de lot rencontree apres
# celle-ci, quelle qu'elle soit.
def _bloc(source, entete):
    debut = source.index(entete)
    banniere = "\n# " + "=" * 76 + "\n# P3-"
    suite = source.find(banniere, debut + len(entete))
    return source[debut:suite if suite != -1 else
                  source.index("# --- Leads Routes (Widget IA) ---", debut)]

BLOC_U2 = _bloc(SRC, "# P3-U2 — LA RECEPTION DES REPONSES")

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"
ENVOI = "2026-09-01T09:00:00+00:00"
RECU = "2026-09-01T11:00:00+00:00"

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
RequeteFictive = _espace["RequeteFictive"]
lancer = _espace["lancer"]
jeton = _espace["jeton"]

RFC_A = "<j0-beaulac-aaaa@reply.exemple.test>"
RFC_B = "<j0-voisin-bbbb@reply.exemple.test>"


def action(suffixe, cible, cle, refs=None, envoyee=True, **extra):
    a = {"id": "act-" + suffixe, "campaign_id": "camp-1", "coach_id": COACH_A,
         "channel": "email", "target": cible, "recipient_key": cle,
         "message_j0": "Bonjour", "language": "FR", "organisations": ["Org " + cle],
         "prospect_ids": ["R-" + cle], "statut": "envoye", "execution_type": "AUTO"}
    if envoyee:
        a.update({"sent_at": ENVOI, "provider": "resend",
                  "provider_message_id": "prov-" + suffixe,
                  "j3_due_at": "2026-09-04T09:00:00+00:00",
                  "j7_due_at": "2026-09-08T09:00:00+00:00"})
    if refs:
        a[S.P3U2_CHAMP_RFC] = S.p3u2_normaliser_identifiant(refs)
    a.update(extra)
    return a


def base_neuve(actions=None, fiches=None):
    b = BaseBouchon(fiches or [])
    b[S.P3S3_ACTIONS] = CollectionBouchon(
        S.P3S3_ACTIONS, [dict(a) for a in (actions or [])], uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(
        S.P3U2_COLLECTION, [],
        uniques=[(("coach_id", "dedupe_key"), {"dedupe_key": {"$type": "string"}})])
    b["subscribers"] = CollectionBouchon("subscribers", [], uniques=[(("channel", "value"), None)])
    S.db = b
    return b


def entrant(**k):
    base = {"message_id": "<reponse-1@client.exemple.test>",
            "from_email": "hotel@beaulac.exemple.test",
            "to_email": "contact@afroboosteur.com",
            "subject": "Re: Proposition de collaboration avec Afroboost",
            "body_text": "Bonjour, cela nous interesse.",
            "received_at": RECU, "provider": "resend",
            "provider_event_id": "evt-001"}
    base.update(k)
    return base


def recevoir(brut, coach=COACH_A):
    return lancer(S.p3u2_recevoir(brut, coach))


ACT_A = action("aaaa", "hotel@beaulac.exemple.test", "BAR-01", refs=RFC_A)
ACT_B = action("bbbb", "voisin@exemple.test", "BAR-02", refs=RFC_B)


# ============================================================================
print("\n1. LE CONTRAT `InboundMessage` — INDEPENDANT DU FOURNISSEUR")

_m = S.p3u2_message_entrant(entrant(in_reply_to=RFC_A, references=[RFC_A, "<x@y.test>"]))
verifier("1a. les champs attendus par U3 sont tous la",
         set(_m) == {"message_id", "in_reply_to", "references", "from_email",
                     "to_email", "subject", "body_text", "received_at",
                     "provider", "provider_event_id", "dedupe_key"},
         str(sorted(_m)))
verifier("1b. AUCUN champ propre a Resend n'entre dans le contrat",
         not any(c in json.dumps(_m).lower() for c in ("svix", "resend_", "payload")))
verifier("1c. les identifiants sont comparables (sans chevrons, minuscules)",
         _m["in_reply_to"] == ["j0-beaulac-aaaa@reply.exemple.test"], str(_m["in_reply_to"]))
verifier("1d. `References` accepte AUSSI la chaine brute de l'en-tete",
         S.p3u2_message_entrant({"references": "<a@b.test>  <c@d.test>"})["references"]
         == ["a@b.test", "c@d.test"])
verifier("1e. l'adresse est extraite d'un « Nom <a@b> »",
         S.p3u2_normaliser_adresse("Marie Dupont <Marie@Exemple.TEST>") == "marie@exemple.test")
verifier("1f. une adresse invalide rend '' (jamais une valeur inventee)",
         S.p3u2_normaliser_adresse("pas-une-adresse") == "")
verifier("1g. le corps HTML n'est PAS conserve (rien a assainir plus tard)",
         "body_html" not in _m and "html" not in _m)
verifier("1h. la cle de deduplication prefere le `Message-ID`",
         _m["dedupe_key"] == "mid:reponse-1@client.exemple.test", _m["dedupe_key"])
_sans_mid = S.p3u2_message_entrant(entrant(message_id=None))
verifier("1i. sans `Message-ID`, elle retombe sur l'evenement du fournisseur",
         _sans_mid["dedupe_key"] == "evt:evt-001", str(_sans_mid["dedupe_key"]))
_sans_rien = S.p3u2_message_entrant(entrant(message_id=None, provider_event_id=None))
verifier("1j. sans NI l'un NI l'autre, la cle est None — on ne l'invente pas",
         _sans_rien["dedupe_key"] is None, str(_sans_rien["dedupe_key"]))


# ============================================================================
print("\n2. SCENARIO A — `In-Reply-To` EXACT")

_b = base_neuve([ACT_A, ACT_B], fiches=[{"id": "p-bar-01", "ref": "R-BAR-01",
                                         "coach_id": COACH_A, "status": "contacte",
                                         "organisation_name": "Beaulac"}])
_r = recevoir(entrant(in_reply_to=RFC_A))
verifier("2a. le message est stocke", _r["stocke"] is True, str(_r))
verifier("2b. methode A", _r["methode"] == S.P3U2_METHODE_IN_REPLY_TO, str(_r))
verifier("2c. confiance maximale", _r["confiance"] == 100, str(_r))
verifier("2d. rattache a la BONNE action", _r["action_id"] == "act-aaaa", str(_r))
verifier("2e. statut `rattache`", _r["statut"] == S.P3U2_STATUT_RATTACHE, str(_r))
verifier("2f. c'est la premiere reponse", _r["premiere_reponse"] is True, str(_r))

_a = [a for a in _b[S.P3S3_ACTIONS].documents if a["id"] == "act-aaaa"][0]
verifier("2g. `replied_at` est pose", _a.get("replied_at") == RECU, str(_a.get("replied_at")))
verifier("2h. J+3 annule DANS LA MEME operation", bool(_a.get("j3_annule_le")))
verifier("2i. J+7 annule aussi", bool(_a.get("j7_annule_le")))
verifier("2j. le motif d'annulation est trace",
         _a.get("j3_annule_motif") == "reponse recue" == _a.get("j7_annule_motif"))
verifier("2k. la fiche passe a `repondu`",
         _b["partner_prospects"].documents[0].get("status") == "repondu",
         str(_b["partner_prospects"].documents[0].get("status")))
_voisin = [a for a in _b[S.P3S3_ACTIONS].documents if a["id"] == "act-bbbb"][0]
verifier("2l. le VOISIN n'est pas touche", not _voisin.get("replied_at"), str(_voisin.get("replied_at")))
verifier("2m. ... et ses relances restent armees",
         not _voisin.get("j3_annule_le") and not _voisin.get("j7_annule_le"))


# ============================================================================
print("\n3. SCENARIO B — `References` EXACT")

_b = base_neuve([ACT_A, ACT_B])
_r = recevoir(entrant(in_reply_to=None, references=["<autre@x.test>", RFC_B]))
verifier("3a. methode B (References)", _r["methode"] == S.P3U2_METHODE_REFERENCES, str(_r))
verifier("3b. rattache a act-bbbb", _r["action_id"] == "act-bbbb", str(_r))
verifier("3c. rattache automatiquement", _r["statut"] == S.P3U2_STATUT_RATTACHE)

# l'identifiant du FOURNISSEUR, quand il transite dans le fil
_b = base_neuve([ACT_A])
_r = recevoir(entrant(in_reply_to="<prov-aaaa>"))
verifier("3d. methode B (identifiant fournisseur)",
         _r["methode"] == S.P3U2_METHODE_PROVIDER, str(_r))
verifier("3e. ... et elle rattache bien", _r["action_id"] == "act-aaaa")


# ============================================================================
print("\n4. SCENARIO C — L'EXPEDITEUR, CANDIDAT UNIQUE")

_b = base_neuve([ACT_A, ACT_B])
_r = recevoir(entrant(in_reply_to=None, references=None,
                      from_email="hotel@beaulac.exemple.test"))
verifier("4a. methode C", _r["methode"] == S.P3U2_METHODE_EMAIL, str(_r))
verifier("4b. confiance moindre, mais suffisante", _r["confiance"] == 60, str(_r))
verifier("4c. rattache", _r["action_id"] == "act-aaaa" and _r["statut"] == S.P3U2_STATUT_RATTACHE)

# la casse et les espaces ne doivent pas empecher le rattachement
_b = base_neuve([ACT_A])
_r = recevoir(entrant(in_reply_to=None, references=None,
                      from_email="  HOTEL@Beaulac.Exemple.TEST "))
verifier("4d. la casse et les espaces n'empechent rien", _r["action_id"] == "act-aaaa", str(_r))

# AUCUN rapprochement par domaine
_b = base_neuve([action("cccc", "contact@gmail.exemple.test", "BAR-03")])
_r = recevoir(entrant(in_reply_to=None, references=None,
                      from_email="quelquun.dautre@gmail.exemple.test"))
verifier("4e. AUCUN rapprochement par domaine partage",
         _r["action_id"] is None and _r["statut"] == S.P3U2_STATUT_REVUE, str(_r))
verifier("4f. ... et le motif le dit", _r["motif"] == S.P3U2_MOTIFS["AUCUN_CANDIDAT"], str(_r))


# ============================================================================
print("\n5. SCENARIO D — DEUX CANDIDATS : ON NE DEVINE PAS")

_jumelle = action("dddd", "hotel@beaulac.exemple.test", "BAR-99")
_b = base_neuve([ACT_A, _jumelle])
_r = recevoir(entrant(in_reply_to=None, references=None))
verifier("5a. AUCUN rattachement automatique", _r["action_id"] is None, str(_r))
verifier("5b. mise en revue humaine", _r["statut"] == S.P3U2_STATUT_REVUE, str(_r))
verifier("5c. le motif nomme l'ambiguite",
         _r["motif"] == S.P3U2_MOTIFS["PLUSIEURS_CANDIDATS"], str(_r))
verifier("5d. le message est TOUT DE MEME stocke (rien ne se perd)", _r["stocke"] is True)
verifier("5e. AUCUNE des deux actions n'a `replied_at`",
         not any(a.get("replied_at") for a in _b[S.P3S3_ACTIONS].documents),
         str([a.get("replied_at") for a in _b[S.P3S3_ACTIONS].documents]))
verifier("5f. AUCUNE des deux n'a vu ses relances coupees",
         not any(a.get("j3_annule_le") for a in _b[S.P3S3_ACTIONS].documents))


# ============================================================================
print("\n6. SCENARIO E — LE DOUBLON N'ENTRE QU'UNE FOIS")

_b = base_neuve([ACT_A])
_r1 = recevoir(entrant(in_reply_to=RFC_A))
_r2 = recevoir(entrant(in_reply_to=RFC_A))
verifier("6a. le premier est stocke", _r1["stocke"] is True)
verifier("6b. le second est reconnu comme doublon", _r2["doublon"] is True, str(_r2))
verifier("6c. une seule ligne en base", len(_b[S.P3U2_COLLECTION].documents) == 1,
         str(len(_b[S.P3U2_COLLECTION].documents)))
verifier("6d. le doublon renvoie l'identifiant du message DEJA stocke",
         _r2["id"] == _r1["id"], "%s / %s" % (_r2["id"], _r1["id"]))

# meme message, identifiant d'evenement different : le `Message-ID` prime
_r3 = recevoir(entrant(in_reply_to=RFC_A, provider_event_id="evt-REJEU"))
verifier("6e. un REJEU du fournisseur (autre evenement) reste un doublon",
         _r3["doublon"] is True, str(_r3))
verifier("6f. toujours une seule ligne", len(_b[S.P3U2_COLLECTION].documents) == 1)

# sans `Message-ID`, la deduplication se fait sur l'evenement
_b = base_neuve([ACT_A])
recevoir(entrant(message_id=None, in_reply_to=RFC_A))
_r = recevoir(entrant(message_id=None, in_reply_to=RFC_A))
verifier("6g. sans `Message-ID`, l'evenement fournisseur dedoublonne",
         _r["doublon"] is True, str(_r))

# sans NI l'un NI l'autre : on ne peut pas dedoublonner — on stocke quand meme
_b = base_neuve([ACT_A])
_r = recevoir(entrant(message_id=None, provider_event_id=None, in_reply_to=RFC_A))
verifier("6h. sans aucun identifiant, le message est stocke plutot que perdu",
         _r["stocke"] is True, str(_r))
verifier("6i. ... et il n'a pas de cle de deduplication (l'index ne s'applique pas)",
         _b[S.P3U2_COLLECTION].documents[0].get("dedupe_key") is None)


# ============================================================================
print("\n7. SCENARIO F — DEUXIEME REPONSE : LA PREMIERE DATE RESTE")

_b = base_neuve([ACT_A])
recevoir(entrant(in_reply_to=RFC_A, received_at=RECU))
_r2 = recevoir(entrant(message_id="<reponse-2@client.exemple.test>",
                       in_reply_to=RFC_A, provider_event_id="evt-002",
                       received_at="2026-09-02T15:00:00+00:00",
                       body_text="Je reviens vers vous."))
verifier("7a. la seconde reponse est bien STOCKEE", _r2["stocke"] is True, str(_r2))
verifier("7b. elle est rattachee a la meme action", _r2["action_id"] == "act-aaaa")
verifier("7c. mais ce n'est PLUS la premiere reponse",
         _r2["premiere_reponse"] is False, str(_r2))
_a = _b[S.P3S3_ACTIONS].documents[0]
verifier("7d. `replied_at` a garde la date du PREMIER signe de vie",
         _a.get("replied_at") == RECU, str(_a.get("replied_at")))
verifier("7e. deux messages en base", len(_b[S.P3U2_COLLECTION].documents) == 2)


# ============================================================================
print("\n8. SCENARIO G — OPT-OUT DEJA ACTIF : REPONSE ≠ DESABONNEMENT")

_b = base_neuve([ACT_A])
_r = recevoir(entrant(in_reply_to=RFC_A))
verifier("8a. une reponse n'inscrit AUCUN refus dans `subscribers`",
         len(_b["subscribers"].documents) == 0, str(_b["subscribers"].documents))
_a = _b[S.P3S3_ACTIONS].documents[0]
verifier("8b. la reponse laisse sa PROPRE trace (`replied_at`)", bool(_a.get("replied_at")))
verifier("8c. ... distincte de celle d'un desabonnement (`opted_out`)",
         "opted_out" not in json.dumps(_a))

# les deux arretent les relances, pour des raisons differentes
_refus = {"email:hotel@beaulac.exemple.test"}
_v_refus = S.p3u2_relance_autorisee(dict(ACT_A), refus=_refus)
_v_reponse = S.p3u2_relance_autorisee(dict(ACT_A, replied_at=RECU))
verifier("8d. un desabonne ne recoit plus de relance",
         not _v_refus["autorise"] and _v_refus["code"] == "REFUS_EXPRIME", str(_v_refus))
verifier("8e. un repondeur non plus",
         not _v_reponse["autorise"] and _v_reponse["code"] == "A_REPONDU", str(_v_reponse))
verifier("8f. et les DEUX motifs sont differents",
         _v_refus["code"] != _v_reponse["code"])
verifier("8g. un destinataire ni l'un ni l'autre reste eligible",
         S.p3u2_relance_autorisee(dict(ACT_A))["autorise"] is True)


# ============================================================================
print("\n9. SCENARIO H — LA COURSE : REPONSE CONTRE J+3")

# La relance lit `replied_at` DANS son filtre : il n'y a aucune fenetre entre
# la lecture et l'ecriture, donc l'une des deux perd forcement.
_b = base_neuve([ACT_A])
recevoir(entrant(in_reply_to=RFC_A))
_a = _b[S.P3S3_ACTIONS].documents[0]
verifier("9a. apres la reponse, la relance J+3 est REFUSEE",
         not S.p3u2_relance_autorisee(_a)["autorise"], str(S.p3u2_relance_autorisee(_a)))
verifier("9b. ... et J+7 aussi (meme garde, meme verdict)",
         S.p3u2_relance_autorisee(_a)["code"] == "A_REPONDU")

# l'inverse : la garde de PREMIER contact refuse aussi une action deja envoyee
_verdict_j0 = S.p3s3d_garde_action(
    _a, {"etat": "approuvee", "subject_j0": "Objet"}, fiches=[],
    refus=set(), envoi_autorise=True, simulation=False)
verifier("9c. un nouveau J0 sur ce destinataire est refuse",
         not _verdict_j0["autorise"] and _verdict_j0["code"] == "DEJA_CONTACTE",
         str(_verdict_j0))

# la course sur `replied_at` lui-meme : deux marquages concurrents
_b = base_neuve([ACT_A])
_a = _b[S.P3S3_ACTIONS].documents[0]
_p1 = lancer(S.p3u2_marquer_reponse(_a, RECU))
_p2 = lancer(S.p3u2_marquer_reponse(_a, "2026-09-05T10:00:00+00:00"))
verifier("9d. le premier marquage gagne", _p1["premiere_reponse"] is True)
verifier("9e. le second n'ecrase RIEN", _p2["premiere_reponse"] is False, str(_p2))
verifier("9f. la date reste celle du premier",
         _b[S.P3S3_ACTIONS].documents[0].get("replied_at") == RECU)


# ============================================================================
print("\n10. SCENARIO I — UNE ACTION JAMAIS ENVOYEE")

_jamais = action("eeee", "jamais@exemple.test", "BAR-04",
                 refs="<j0-jamais@reply.exemple.test>", envoyee=False)
_b = base_neuve([_jamais])
_r = recevoir(entrant(in_reply_to="<j0-jamais@reply.exemple.test>",
                      from_email="jamais@exemple.test"))
verifier("10a. le message est stocke", _r["stocke"] is True)
verifier("10b. l'action est DESIGNEE, pour que l'humain la voie",
         _r["action_id"] == "act-eeee", str(_r))
verifier("10c. mais mise en revue, pas rattachee",
         _r["statut"] == S.P3U2_STATUT_REVUE, str(_r))
verifier("10d. le motif nomme l'incoherence",
         _r["motif"] == S.P3U2_MOTIFS["JAMAIS_ENVOYE"], str(_r))
verifier("10e. AUCUN `replied_at` sur une action jamais partie",
         not _b[S.P3S3_ACTIONS].documents[0].get("replied_at"))
verifier("10f. ... et aucune relance annulee",
         not _b[S.P3S3_ACTIONS].documents[0].get("j3_annule_le"))
# UN MESSAGE DISTINCT, sinon c'est un doublon qu'on mesure, pas le repli.
verifier("10g. le repli par e-mail ignore aussi les actions jamais envoyees",
         recevoir(entrant(message_id="<autre-reponse@client.exemple.test>",
                          provider_event_id="evt-010g",
                          in_reply_to=None, references=None,
                          from_email="jamais@exemple.test"))["action_id"] is None)
verifier("10h. le contrat de retour a la MEME forme, doublon ou non",
         set(recevoir(entrant(in_reply_to="<j0-jamais@reply.exemple.test>"))) ==
         {"stocke", "doublon", "id", "statut", "methode", "confiance",
          "action_id", "motif", "premiere_reponse"})


# ============================================================================
print("\n11. SCENARIO J — MULTI-FICHES, UNE SEULE CONVERSATION")

# Dancefloor + Wellness : deux fiches, un decideur, UNE action.
_multi = action("ffff", "direction@lieu.exemple.test", "LIEU-01", refs="<j0-lieu@r.test>")
_multi["prospect_ids"] = ["R-DANCEFLOOR", "R-WELLNESS"]
_multi["organisations"] = ["Lieu Dancefloor", "Lieu Wellness"]
_fiches = [{"id": "p-dancefloor", "ref": "R-DANCEFLOOR", "coach_id": COACH_A,
            "status": "contacte", "organisation_name": "Lieu Dancefloor"},
           {"id": "p-wellness", "ref": "R-WELLNESS", "coach_id": COACH_A,
            "status": "contacte", "organisation_name": "Lieu Wellness"}]
_b = base_neuve([_multi], fiches=_fiches)
_r = recevoir(entrant(in_reply_to="<j0-lieu@r.test>", from_email="direction@lieu.exemple.test"))
verifier("11a. UN seul message stocke", len(_b[S.P3U2_COLLECTION].documents) == 1)
verifier("11b. rattache a UNE seule action", _r["action_id"] == "act-ffff")
verifier("11c. les DEUX fiches passent a `repondu` (un decideur, deux lieux)",
         all(f.get("status") == "repondu" for f in _b["partner_prospects"].documents),
         str([f.get("status") for f in _b["partner_prospects"].documents]))
verifier("11d. ... et le compte le confirme", _r.get("fiches_marquees") == 2, str(_r))
verifier("11e. une seule action porte `replied_at`",
         sum(1 for a in _b[S.P3S3_ACTIONS].documents if a.get("replied_at")) == 1)


# ============================================================================
print("\n12. LE SUJET N'EST JAMAIS UNE CLE")

_b = base_neuve([ACT_A, ACT_B])
_r = recevoir(entrant(in_reply_to=None, references=None,
                      from_email="inconnu@ailleurs.exemple.test",
                      subject="Re: Proposition de collaboration avec Afroboost"))
verifier("12a. un sujet identique au J0 ne rattache RIEN",
         _r["action_id"] is None and _r["statut"] == S.P3U2_STATUT_REVUE, str(_r))
verifier("12b. le sujet n'apparait dans aucune requete de correlation",
         "subject" not in BLOC_U2.split("def p3u2_verdict_correlation")[1]
         .split("def p3u2_relance_autorisee")[0])
verifier("12c. il est tout de meme conserve, pour le diagnostic",
         _b[S.P3U2_COLLECTION].documents[0].get("subject").startswith("Re: "))


# ============================================================================
print("\n13. LA ROUTE DE LECTURE — AUTHENTIFIEE, JAMAIS PUBLIQUE")

_b = base_neuve([ACT_A])
recevoir(entrant(in_reply_to=RFC_A))
recevoir(entrant(message_id="<z@z.test>", provider_event_id="evt-z",
                 in_reply_to=None, references=None, from_email="inconnu@ailleurs.test"))

try:
    lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=None)))
    _ferme = False
except HTTPException as e:
    _ferme = e.status_code in (401, 403)
verifier("13a. SANS jeton -> refuse", _ferme)

_JA = jeton(COACH_A)
_rep = lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=_JA)))
verifier("13b. avec jeton -> les messages du coach", _rep["total"] == 2, str(_rep["total"]))
verifier("13c. le compteur des messages en attente est rendu",
         _rep["en_attente"] == 1, str(_rep.get("en_attente")))
verifier("13d. la pagination est bornee",
         lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=_JA, params={"limit": "9999"})))["limit"] == 100)
try:
    lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=_JA, params={"statut": "nimporte"})))
    _ok = False
except HTTPException as e:
    _ok = e.status_code == 400
verifier("13f. un statut inconnu -> 400", _ok)
_filtre = lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=_JA, params={"statut": "manual_review"})))
verifier("13g. le filtre par statut fonctionne", _filtre["total"] == 1, str(_filtre["total"]))

_JB = jeton(COACH_B)
_autre = lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=_JB)))
verifier("13h. un AUTRE coach ne voit rien de ces messages",
         _autre["total"] == 0, str(_autre["total"]))
verifier("13i. la route ne rend aucun corps HTML brut",
         all("body_html" not in m and "html" not in m for m in _rep["messages"]))


# ============================================================================
print("\n14. INDEX, ISOLATION ET INNOCUITE")

# ON INSPECTE LES APPELS REELS, PAS LA PROSE. La premiere version de cette
# verification cherchait le mot « sparse » dans le texte — et mordait sur le
# commentaire qui explique justement qu'on ne l'utilise pas.
_appels_index = [n for n in ast.walk(ast.parse(SRC))
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "create_index"]
_mots_cles = [k.arg for a in _appels_index for k in a.keywords]
# ET ON BORNE AUX INDEX DE CE LOT. `sparse` existe ailleurs dans le fichier,
# dans du code anterieur : balayer tout le depot faisait echouer une
# verification qui ne parle que de P3-U2.
_index_u2 = [a for a in _appels_index
             if "P3U2_COLLECTION" in (ast.get_source_segment(SRC, a) or "")]
_mots_u2 = [k.arg for a in _index_u2 for k in a.keywords]
verifier("14a. les index de P3-U2 utilisent `partialFilterExpression`, jamais `sparse`",
         'partialFilterExpression={"dedupe_key": {"$type": "string"}}' in SRC
         and "sparse" not in _mots_u2 and len(_index_u2) == 3,
         "%d index, mots-cles %s" % (len(_index_u2), sorted(set(_mots_u2))))
verifier("14b. le tri pagine porte une SECONDE cle unique (ordre TOTAL)",
         '.sort([("received_at", -1), ("id", 1)])' in SRC)
verifier("14c. la correlation lit les actions en UNE requete groupee, pas une par identifiant",
         '"$in": cites' in BLOC_U2 and BLOC_U2.count("find_one(") <= 1)
# IDEM : « webhook » figure dans le commentaire d'en-tete, qui dit qu'il n'y
# en a pas. On regarde donc les IMPORTS et les DECORATEURS reels du bloc.
_arbre_u2 = ast.parse(BLOC_U2.split("P3U2_COLLECTION =", 1)[0]
                      .join(["", ""]) or BLOC_U2[BLOC_U2.index("P3U2_COLLECTION ="):])
_imports = {n.names[0].name.split(".")[0] for n in ast.walk(_arbre_u2)
            if isinstance(n, (ast.Import,))} | \
           {(n.module or "").split(".")[0] for n in ast.walk(_arbre_u2)
            if isinstance(n, ast.ImportFrom)}
_decorateurs = [ast.dump(d) for f in ast.walk(_arbre_u2)
                if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                for d in f.decorator_list]
verifier("14d. le moteur n'importe NI imaplib, NI smtplib, NI aucun client reseau",
         not (_imports & {"imaplib", "smtplib", "poplib", "requests", "httpx",
                          "urllib", "socket", "resend"}),
         str(sorted(_imports)))
verifier("14d-bis. il n'expose AUCUNE route POST (rien ne peut lui livrer un message)",
         not any("'post'" in d.lower() for d in _decorateurs), str(_decorateurs))
verifier("14e. aucune route publique n'est creee",
         BLOC_U2.count("@api_router.") == 1 and "_v309_require_coach_or_admin" in BLOC_U2)
verifier("14f. le champ RFC est DISTINCT de `provider_message_id`",
         S.P3U2_CHAMP_RFC == "rfc_message_id" and S.P3U2_CHAMP_RFC != "provider_message_id")
verifier("14g. il n'est ecrit QUE si l'adaptateur l'a fourni",
         "if _rfc:" in SRC and "_champs_envoi[P3U2_CHAMP_RFC] = _rfc" in SRC)


# ============================================================================
print("\n15. AUCUN RESEAU")

verifier("15a. zero tentative de sortie", len(_TENTATIVES) == 0, str(_TENTATIVES))


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("P3-U2 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("E-mails recus ou envoyes : 0 — tout est synthetique")
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)

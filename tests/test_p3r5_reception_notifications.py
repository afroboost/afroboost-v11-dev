#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-R5 / V631 — RECEVOIR SUR L'ADRESSE QUI ENVOIE, SANS JAMAIS DEVINER.

POURQUOI CE BANC EXISTE
==============================================================================
Mesure du 27/10/2026 : `afroboost.com` n'a AUCUN MX et le port 25 de ses IP est
injoignable. Une reponse adressee a `notifications@afroboost.com` — l'adresse que
le prospect VOIT — ne peut pas arriver. Groupe Danse Fictif EPFL l'a ecrit lui-meme :
« On a repondu deux fois a vos emails mais il nous semble qu'il y a un probleme
avec la boite. » Pendant ce temps il a recu J+3, J+7 puis J+14.

Ouvrir un MX repare la perte, mais ouvre DEUX trous neufs, et ce fichier existe
pour prouver qu'aucun des deux n'est ouvert :
  * tout le courrier du domaine entrerait dans la file de travail du coach ;
  * un message sans jeton pourrait couper les relances du mauvais prospect.

CE QUE CE FICHIER PROUVE
==============================================================================
  * A. les fonctions pures de lecture d'adresse (nom d'affichage, sous-adressage,
       domaine invalide, tentative d'injection de motif Mongo) ;
  * B. la porte ne refuse QUE le courrier de notre domaine d'envoi adresse a une
       boite non relevee ; le domaine a jeton et les domaines tiers passent comme
       avant — y compris le repli `C_FROM_EMAIL`, qui reste AUTOMATIQUE ;
  * C. recu sur la boite generique depuis l'adresse EXACTEMENT demarchee ->
       stocke, mais `manual_review` : AUCUN `replied_at`, AUCUNE relance annulee ;
  * D. recu depuis une AUTRE adresse du MEME domaine (le cas Groupe Danse Fictif) ->
       la bonne action est PROPOSEE (`D_DOMAINE_PROSPECT`, confiance 40), et
       toujours aucune ecriture ;
  * E. deux actions sur le meme domaine -> aucune proposition, revue manuelle ;
  * F. un expediteur inconnu n'est pas perdu : il est stocke sans proposition ;
  * G. NON-REGRESSION : le chemin a jeton est INCHANGE — `A0_REPLY_TOKEN`,
       confiance 100, `replied_at` ecrit, J+3 / J+7 / J+14 annules, fiche
       « repondu » ;
  * H. l'adaptateur lit `received_for` AVANT `to` ;
  * I. `POST /prospect-inbound/{id}/rattacher` : un humain tranche, et c'est la
       SEULE chose qui arrete les relances d'une reponse sans jeton ;
  * J. ses refus : deja rattache (409), action jamais envoyee (400), action
       inconnue (404), `action_id` manquant (400), hors portee de tenance (404) ;
  * K. `replied_at` reste ECRIT UNE SEULE FOIS ;
  * L. aucune socket, aucun e-mail envoye ;
  * M. une PISTE ne contamine rien avant confirmation : ni `action_id`, ni la
       conversation du prospect, ni le nom dans la notification ;
  * N. la liste des candidats est en lecture seule et sans regex utilisateur ;
  * un prospect qui ecrit a une AUTRE boite du domaine n'est pas jete.
"""
try:   # V608 : le point d'envoi Resend unique, visible aussi des fonctions EXTRAITES
    import builtins as _b630, os as _o630, sys as _s630
    _s630.path.insert(0, _o630.path.dirname(_o630.path.dirname(_o630.path.abspath(__file__))))
    import api.resend_central as _rc630
    _b630._rc = _rc630
except Exception:  # noqa: BLE001
    pass
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


# ---------------------------------------------------------------------------
# AUCUNE SORTIE RESEAU. Coupee AVANT l'import : un banc qui joindrait la vraie
# API de Resend ne prouverait pas notre cablage, il testerait Resend.
# ---------------------------------------------------------------------------
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


def _crea(adresse, *a, **k):
    _TENTATIVES.append(("create_connection", adresse))
    raise SortieReseauInterdite(str(adresse))


socket.getaddrinfo = _dns
socket.socket.connect = _conn
socket.create_connection = _crea

# ---------------------------------------------------------------------------
# LE FAUX SDK RESEND, pose AVANT l'import du serveur.
# ---------------------------------------------------------------------------
_RECU = {"reponse": None, "leve": None}
_ENVOIS = []


class _FauxReceiving:
    @classmethod
    def get(cls, email_id):
        if _RECU["leve"]:
            raise _RECU["leve"]
        return _RECU["reponse"]

    @classmethod
    def list(cls, params=None):
        return {"object": "list", "has_more": False, "data": []}


class _FauxWebhooks:
    @classmethod
    def verify(cls, options):
        return None


_faux_resend = types.ModuleType("resend")
_faux_resend.Webhooks = _FauxWebhooks
_faux_resend.Emails = types.SimpleNamespace(
    send=lambda *a, **k: _ENVOIS.append((a, k)) or {"id": "jamais"},
    Receiving=_FauxReceiving)
sys.modules["resend"] = _faux_resend

SECRET = "secret-de-banc-p3r5-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ["RESEND_API_KEY"] = "re_faux_de_banc_p3r5"
os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_valeur_de_banc_jamais_en_production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3r5-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-10-27T09:00:00+00:00"

# LES DOUBLES SONT CEUX DU DEPOT, PAS DES COPIES. Un second jeu de bouchons
# aurait sa propre semantique, et c'est exactement ce qui a fait croire un banc
# vert alors que `update_one(upsert=True)` n'ecrivait rien.
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

PROPRIO = S.P3U3_COACH_PAR_DEFAUT
JPROPRIO = jeton(PROPRIO)
JB = jeton(COACH_B)

JETON_DS = "9e8d7c6b5a49382716f5e4d3c2b1a098"
JETON_LSN = "1f2e3d4c5b6a79880716253443526170"
ADRESSE_JETON = "r-%s@reply.afroboosteur.com" % JETON_DS
BOITE = "notifications@" + S.P3R5_DOMAINE_ENVOI

ENVOI = "2026-10-11T08:24:33+00:00"
RECU = "2026-10-26T08:50:59.975Z"

ENTETES_OK = {"svix-id": "msg_p3r5", "svix-timestamp": "1793000000",
              "svix-signature": "v1,QUJD"}


class RequeteWebhook:
    def __init__(self, corps, entetes=None):
        self._corps = corps if isinstance(corps, bytes) else json.dumps(corps).encode()
        self.headers = dict(entetes if entetes is not None else ENTETES_OK)

    async def body(self):
        return self._corps


def action(id_="act-ds", target="groupe-danse@agepoly.exemple.test", token=JETON_DS,
           ref="TST-A1", **extra):
    a = {"id": id_, "campaign_id": "camp-g", "coach_id": PROPRIO,
         "channel": "email", "target": target, "recipient_key": ref,
         "prospect_ids": [ref], "prospect_uuids": ["uuid-" + ref.lower()],
         "language": "FR", "execution_type": "AUTO", "statut": "envoye",
         "sent_at": ENVOI, "message_j0": "Bonjour, ...",
         S.P3R1_CHAMP_TOKEN: token}
    a.update(extra)
    return a


def fiche(ref="TST-A1", **extra):
    f = {"id": "uuid-" + ref.lower(), "coach_id": PROPRIO, "ref": ref,
         "organisation_name": "Groupe Danse Fictif (AGEPoly EPFL)", "status": "contacte"}
    f.update(extra)
    return f


def base_neuve(actions=None, fiches=None):
    b = BaseBouchon([dict(f) for f in (fiches or [fiche()])])
    b[S.P3S3_ACTIONS] = CollectionBouchon(
        S.P3S3_ACTIONS, [dict(a) for a in (actions if actions is not None else [action()])],
        uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(
        S.P3U2_COLLECTION, [],
        uniques=[(("coach_id", "dedupe_key"), {"dedupe_key": {"$type": "string"}})])
    b["subscribers"] = CollectionBouchon("subscribers", [], uniques=[(("channel", "value"), None)])
    S.db = b
    return b


_COMPTEUR = {"n": 0}


def evenement(de="groupe-danse@agepoly.exemple.test", pour=BOITE, **donnees):
    """Un `email.received` tel que Resend le poste. `received_for` = NOTRE boite."""
    _COMPTEUR["n"] += 1
    identifiant = "evt_p3r5_%03d" % _COMPTEUR["n"]
    d = {"email_id": "0000a17c-0000-4000-8000-%012d" % _COMPTEUR["n"],
         "from": de, "to": [pour], "received_for": pour,
         "subject": "Re: Un atelier afro en invite chez Groupe Danse Fictif",
         "created_at": RECU,
         "message_id": "<reponse-%03d@agepoly.exemple.test>" % _COMPTEUR["n"]}
    d.update(donnees)
    return {"type": "email.received", "id": identifiant, "data": d}


_RECU["reponse"] = {"text": "Bonjour, on a repondu deux fois a vos emails.",
                    "html": None}


def appeler(evt):
    return lancer(S.p3u3_webhook_resend(RequeteWebhook(evt)))


def seul_message(b):
    docs = b[S.P3U2_COLLECTION].documents
    return dict(docs[0]) if len(docs) == 1 else {}


def action_en_base(b, id_="act-ds"):
    return next((dict(a) for a in b[S.P3S3_ACTIONS].documents if a.get("id") == id_), {})


# ============================================================================
print("\n1. A — LES FONCTIONS PURES DE LECTURE D'ADRESSE")
# ============================================================================
verifier("un nom d'affichage ne cache plus l'adresse",
         S.p3r5_adresse_nue("Coach Bassi <Notifications@Afroboost.com>")
         == "notifications@afroboost.com")
verifier("une adresse nue reste intacte",
         S.p3r5_adresse_nue("  info@club.ch ") == "info@club.ch")
verifier("le domaine est extrait et valide",
         S.p3r5_domaine_de("marie@agepoly.exemple.test") == "agepoly.exemple.test")
verifier("un domaine sans point n'est pas un domaine",
         S.p3r5_domaine_de("marie@localhost") == "")
verifier("deux arobases = adresse inexploitable",
         S.p3r5_domaine_de("a@b@c.ch") == "")
verifier("une tentative d'injection de motif Mongo ne rend RIEN",
         S.p3r5_domaine_de("x@.*") == "" and S.p3r5_domaine_de("x@a|b.ch") == "",
         "un domaine non conforme ne doit jamais atteindre la requete")
verifier("une adresse vide ne leve pas",
         S.p3r5_domaine_de(None) == "" and S.p3r5_adresse_nue(None) == "")

# ============================================================================
print("\n2. B — LA PORTE NE REFUSE QUE CE QU'ELLE DOIT REFUSER")
# ============================================================================
verifier("la boite generique est reconnue", S.p3r5_boite_generique(BOITE))
verifier("le sous-adressage est tolere",
         S.p3r5_boite_generique("notifications+p3@" + S.P3R5_DOMAINE_ENVOI))
verifier("une autre boite du MEME domaine n'est pas la boite generique",
         not S.p3r5_boite_generique("factures@" + S.P3R5_DOMAINE_ENVOI))
verifier("et elle, elle est REFUSEE",
         S.p3r5_courrier_non_releve("factures@" + S.P3R5_DOMAINE_ENVOI))
verifier("la boite generique n'est jamais refusee",
         not S.p3r5_courrier_non_releve(BOITE))
verifier("le domaine a jeton n'est JAMAIS refuse",
         not S.p3r5_courrier_non_releve(ADRESSE_JETON),
         "le chemin prouve par 98 reponses ne doit pas meme avoir a etre reconnu")
verifier("un jeton illisible sur le domaine a jeton n'est pas refuse non plus",
         not S.p3r5_courrier_non_releve("r-PAS-UN-JETON@" + S.P3R1_DOMAINE_REPONSE))
verifier("un domaine tiers n'est pas refuse par cette porte (elle n'est pas son role)",
         not S.p3r5_courrier_non_releve("bonjour@domaine-tiers.example"),
         "c'est la correlation qui le mettra en revue, comme avant ce lot")
verifier("un domaine tiers n'est pas la boite generique",
         not S.p3r5_boite_generique("r-%s@ailleurs.example" % JETON_DS))
verifier("une adresse vide ne refuse rien et n'ouvre rien",
         not S.p3r5_courrier_non_releve("") and not S.p3r5_boite_generique(""))
verifier("une seule boite est ouverte, et elle est nommee",
         S.P3R5_BOITES_ACCEPTEES == ("notifications",))

# ============================================================================
print("\n3. B — UN INCONNU SUR UNE BOITE NON RELEVEE EST ACQUITTE, NON STOCKE, TRACE")
# ============================================================================
b = base_neuve()
_avant = b.total_ecritures()
_r = appeler(evenement(de="robot@prospectus.example", pour="factures@" + S.P3R5_DOMAINE_ENVOI))
verifier("le webhook acquitte (pas de reessai du fournisseur)", _r.get("recu") is True)
verifier("il dit qu'il ignore", _r.get("ignore") is True and _r.get("stocke") is False)
verifier("AUCUN message n'est stocke", len(b[S.P3U2_COLLECTION].documents) == 0)
verifier("AUCUNE ecriture nulle part", b.total_ecritures() == _avant,
         "ecritures=%s" % (b.total_ecritures() - _avant))

# ============================================================================
print("\n3-ter. NE PAS JETER UN PROSPECT QUI ECRIT A LA MAUVAISE BOITE")
# ============================================================================
b = base_neuve()
_r = appeler(evenement(de="groupe-danse@agepoly.exemple.test", pour="contact@" + S.P3R5_DOMAINE_ENVOI))
m = seul_message(b)
verifier("un prospect demarche qui ecrit a `contact@` est STOCKE",
         _r.get("ignore") is not True and bool(m), "reponse=%s" % _r)
verifier("en revue manuelle, jamais rattache tout seul",
         m.get("statut") == S.P3U2_STATUT_REVUE and "replied_at" not in action_en_base(b))
b = base_neuve()
appeler(evenement(de="quelquun@agepoly.exemple.test", pour="info@" + S.P3R5_DOMAINE_ENVOI))
verifier("meme chose pour une autre personne du MEME domaine que la cible",
         len(b[S.P3U2_COLLECTION].documents) == 1)
b = base_neuve(actions=[action(sent_at=None)])
appeler(evenement(de="groupe-danse@agepoly.exemple.test", pour="contact@" + S.P3R5_DOMAINE_ENVOI))
verifier("mais une action JAMAIS envoyee ne rend pas l'expediteur « connu »",
         len(b[S.P3U2_COLLECTION].documents) == 0)

print("\n3-bis. NON-REGRESSION : LE CHEMIN `C_FROM_EMAIL` RESTE AUTOMATIQUE")
# ============================================================================
# Le contrat que la premiere version de ce lot avait casse (20 verifications de
# `test_p3u2_inbound`) : sur le domaine a jeton, un jeton INCONNU retombe sur
# l'expediteur exact, et ce rattachement-la reste AUTOMATIQUE. Verrouille ici.
b = base_neuve()
appeler(evenement(de="groupe-danse@agepoly.exemple.test",
                  pour="r-ffffffffffffffffffffffffffffffff@" + S.P3R1_DOMAINE_REPONSE))
m = seul_message(b)
verifier("jeton inconnu + adresse exacte -> rattache automatiquement",
         m.get("statut") == S.P3U2_STATUT_RATTACHE
         and m.get("matching_method") == S.P3U2_METHODE_EMAIL
         and m.get("matching_confidence") == 60,
         "statut=%s methode=%s" % (m.get("statut"), m.get("matching_method")))
verifier("et `replied_at` est ecrit, comme avant ce lot",
         bool(action_en_base(b).get("replied_at")))

# ============================================================================
print("\n4. C — BOITE GENERIQUE, ADRESSE EXACTE : STOCKE MAIS JAMAIS RATTACHE")
# ============================================================================
b = base_neuve()
_r = appeler(evenement(de="groupe-danse@agepoly.exemple.test"))
m = seul_message(b)
verifier("le message est STOCKE", _r.get("stocke") is True and bool(m))
verifier("il est en REVUE MANUELLE, pas rattache",
         m.get("statut") == S.P3U2_STATUT_REVUE, "statut=%s" % m.get("statut"))
verifier("la bonne action est designee COMME PISTE, pas comme association",
         m.get("piste_action_id") == "act-ds" and not m.get("action_id"),
         "piste=%s action_id=%s" % (m.get("piste_action_id"), m.get("action_id")))
verifier("`recipient_key` et `campaign_id` restent vides aussi",
         not m.get("recipient_key") and not m.get("campaign_id"))
verifier("la methode reste C_FROM_EMAIL avec sa confiance de 60",
         m.get("matching_method") == S.P3U2_METHODE_EMAIL
         and m.get("matching_confidence") == 60)
verifier("le motif dit POURQUOI on n'ecrit pas",
         m.get("motif") == S.P3U2_MOTIFS["SANS_JETON"], "motif=%s" % m.get("motif"))
a = action_en_base(b)
verifier("AUCUN `replied_at` n'est ecrit", "replied_at" not in a)
verifier("les TROIS relances restent armees",
         not any(k in a for k in ("j3_annule_le", "j7_annule_le", "j14_annule_le")))
verifier("la fiche reste `contacte`",
         next(f for f in b["partner_prospects"].documents
              if f.get("ref") == "TST-A1").get("status") == "contacte")
verifier("le corps du message est bien la",
         "repondu deux fois" in (m.get("body_text") or ""))

# ============================================================================
print("\n5. D — LE CAS GROUPE DANSE FICTIF : AUTRE ADRESSE, MEME MAISON")
# ============================================================================
b = base_neuve()
appeler(evenement(de="membre@agepoly.exemple.test"))
m = seul_message(b)
verifier("le message est stocke", bool(m))
verifier("la bonne action est PROPOSEE par le domaine (piste, pas association)",
         m.get("piste_action_id") == "act-ds" and not m.get("action_id")
         and m.get("matching_method") == S.P3U2_METHODE_DOMAINE,
         "methode=%s piste=%s" % (m.get("matching_method"), m.get("piste_action_id")))
verifier("la piste porte le nom du prospect pour l'affichage",
         m.get("piste_recipient_key") == "TST-A1")
verifier("la confiance de 40 est SOUS le seuil automatique",
         m.get("matching_confidence") == 40
         and m.get("matching_confidence") < S.P3U2_SEUIL_AUTOMATIQUE)
verifier("donc revue manuelle, et le motif le dit",
         m.get("statut") == S.P3U2_STATUT_REVUE
         and m.get("motif") == S.P3U2_MOTIFS["DOMAINE_SEUL"])
a = action_en_base(b)
verifier("AUCUNE ecriture metier : pas de `replied_at`", "replied_at" not in a)
verifier("AUCUNE relance annulee", "j3_annule_le" not in a)

# ============================================================================
print("\n6. E — DEUX CANDIDATS SUR LE MEME DOMAINE = ZERO PROPOSITION")
# ============================================================================
b = base_neuve(actions=[action(),
                        action(id_="act-ds2", target="comite@agepoly.exemple.test",
                               token="aaaa1180d1aeeab4da2899419f802687",
                               ref="TST-A2")],
               fiches=[fiche(), fiche(ref="TST-A2")])
appeler(evenement(de="inconnu@agepoly.exemple.test"))
m = seul_message(b)
verifier("aucune action n'est designee", not m.get("action_id"))
verifier("le motif nomme l'ambiguite",
         m.get("motif") == S.P3U2_MOTIFS["PLUSIEURS_CANDIDATS"], "motif=%s" % m.get("motif"))
verifier("mais le message n'est PAS perdu", m.get("statut") == S.P3U2_STATUT_REVUE)
verifier("aucune des deux actions n'est touchee",
         "replied_at" not in action_en_base(b, "act-ds")
         and "replied_at" not in action_en_base(b, "act-ds2"))

# ============================================================================
print("\n7. F — UN EXPEDITEUR INCONNU N'EST JAMAIS PERDU")
# ============================================================================
b = base_neuve()
appeler(evenement(de="quelquun@parfaitement-inconnu.example"))
m = seul_message(b)
verifier("le message est stocke malgre tout", bool(m))
verifier("sans proposition, et le motif le dit",
         not m.get("action_id") and m.get("motif") == S.P3U2_MOTIFS["AUCUN_CANDIDAT"])

# ============================================================================
print("\n8. G — NON-REGRESSION : LE CHEMIN A JETON EST INCHANGE")
# ============================================================================
b = base_neuve()
appeler(evenement(de="membre@epfl.exemple.test", pour=ADRESSE_JETON))
m = seul_message(b)
verifier("rattache automatiquement par le jeton",
         m.get("statut") == S.P3U2_STATUT_RATTACHE
         and m.get("matching_method") == S.P3U2_METHODE_TOKEN
         and m.get("matching_confidence") == 100,
         "statut=%s methode=%s" % (m.get("statut"), m.get("matching_method")))
verifier("il rattache MEME depuis une autre adresse que celle demarchee",
         m.get("action_id") == "act-ds")
a = action_en_base(b)
verifier("`replied_at` est ecrit", (a.get("replied_at") or "") == RECU,
         "replied_at=%s" % a.get("replied_at"))
verifier("les TROIS relances sont annulees",
         all(a.get(k) for k in ("j3_annule_le", "j7_annule_le", "j14_annule_le")))
verifier("le motif d'annulation est nomme", a.get("j3_annule_motif") == "reponse recue")
verifier("la fiche passe a `repondu`",
         next(f for f in b["partner_prospects"].documents
              if f.get("ref") == "TST-A1").get("status") == "repondu")

# ============================================================================
print("\n9. H — L'ADAPTATEUR LIT `received_for` AVANT `to`")
# ============================================================================
_adapte = S.p3u3_adapter_recu({"type": "email.received", "id": "evt_h", "data": {
    "from": "marie@club.ch", "to": ["copie@autre.example"],
    "received_for": ADRESSE_JETON, "subject": "Re: ...", "created_at": RECU}})
verifier("c'est `received_for` qui fait le destinataire",
         _adapte["to_email"] == ADRESSE_JETON, "to_email=%s" % _adapte["to_email"])
_adapte2 = S.p3u3_adapter_recu({"type": "email.received", "id": "evt_h2", "data": {
    "from": "marie@club.ch", "to": [ADRESSE_JETON], "subject": "Re: ...",
    "created_at": RECU}})
verifier("`to` reste le repli quand `received_for` manque",
         _adapte2["to_email"] == ADRESSE_JETON)

# ============================================================================
print("\n10. I — UN HUMAIN TRANCHE, ET C'EST CE QUI ARRETE LES RELANCES")
# ============================================================================
b = base_neuve()
appeler(evenement(de="membre@agepoly.exemple.test"))
m = seul_message(b)
verifier("point de depart : revue manuelle, relances armees",
         m.get("statut") == S.P3U2_STATUT_REVUE
         and "replied_at" not in action_en_base(b))
_r = lancer(S.p3r5_rattacher(m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-ds"})))
verifier("la route repond ok", _r.get("ok") is True)
verifier("la methode enregistree est la decision humaine",
         _r.get("methode") == S.P3U2_METHODE_HUMAIN)
m2 = seul_message(b)
verifier("le message est maintenant rattache, confiance 100",
         m2.get("statut") == S.P3U2_STATUT_RATTACHE
         and m2.get("matching_confidence") == 100
         and m2.get("matching_method") == S.P3U2_METHODE_HUMAIN)
verifier("la trace dit QUI a tranche et QUAND",
         m2.get("rattache_par") == PROPRIO and bool(m2.get("rattache_le")))
verifier("le motif de revue est efface", m2.get("motif") == "")
a = action_en_base(b)
verifier("`replied_at` est ENFIN ecrit", (a.get("replied_at") or "") == RECU)
verifier("les TROIS relances tombent",
         all(a.get(k) for k in ("j3_annule_le", "j7_annule_le", "j14_annule_le")))
verifier("la fiche passe a `repondu`",
         next(f for f in b["partner_prospects"].documents
              if f.get("ref") == "TST-A1").get("status") == "repondu")
verifier("c'est annonce comme la PREMIERE reponse", _r.get("premiere_reponse") is True)

# ============================================================================
print("\n11. J — LES REFUS DE LA ROUTE")
# ============================================================================


def refus(appel):
    try:
        appel()
        return 0
    except HTTPException as e:
        return e.status_code


verifier("un message DEJA rattache ne se redirige pas (409)",
         refus(lambda: lancer(S.p3r5_rattacher(
             m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-ds"})))) == 409,
         "deplacer une reponse falsifierait DEUX dossiers")

b = base_neuve()
appeler(evenement(de="membre@agepoly.exemple.test"))
m = seul_message(b)
verifier("sans `action_id` : 400",
         refus(lambda: lancer(S.p3r5_rattacher(m["id"], RequeteFictive(JPROPRIO, {})))) == 400)
verifier("une action inconnue : 404",
         refus(lambda: lancer(S.p3r5_rattacher(
             m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-inexistante"})))) == 404)
verifier("hors portee de tenance : 404 (et le meme 404 qu'un message absent)",
         refus(lambda: lancer(S.p3r5_rattacher(
             m["id"], RequeteFictive(JB, {"action_id": "act-ds"})))) == 404)
verifier("sans aucune session : 403",
         refus(lambda: lancer(S.p3r5_rattacher(
             m["id"], RequeteFictive(None, {"action_id": "act-ds"})))) == 403)

b = base_neuve(actions=[action(), action(id_="act-jamais", target="x@agepoly.exemple.test",
                                        token="bbbb1180d1aeeab4da2899419f802687",
                                        ref="TST-A3", sent_at=None)])
appeler(evenement(de="membre@epfl.exemple.test", pour=BOITE))
m = seul_message(b)
verifier("une action JAMAIS envoyee ne peut pas avoir recu de reponse (400)",
         refus(lambda: lancer(S.p3r5_rattacher(
             m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-jamais"})))) == 400)
verifier("et rien n'a ete ecrit sur elle",
         "replied_at" not in action_en_base(b, "act-jamais"))

# ============================================================================
print("\n12. K — `replied_at` RESTE ECRIT UNE SEULE FOIS")
# ============================================================================
b = base_neuve()
appeler(evenement(de="membre@agepoly.exemple.test"))
m1 = seul_message(b)
lancer(S.p3r5_rattacher(m1["id"], RequeteFictive(JPROPRIO, {"action_id": "act-ds"})))
_premier = action_en_base(b).get("replied_at")
appeler(evenement(de="membre@agepoly.exemple.test", created_at="2026-10-27T10:00:00Z"))
_apres = action_en_base(b).get("replied_at")
verifier("une seconde reponse ne rajeunit pas la premiere date",
         _premier == _apres, "%s -> %s" % (_premier, _apres))

# ============================================================================
print("\n12-bis. M — LA PISTE NE CONTAMINE RIEN AVANT CONFIRMATION")
# ============================================================================
b = base_neuve(actions=[action(organisations=["Groupe Danse Fictif (AGEPoly EPFL)"])])
appeler(evenement(de="membre@agepoly.exemple.test"))
m = seul_message(b)
notifs = [n for n in b["notifications"].documents]
verifier("la notification NE NOMME PAS le prospect propose",
         notifs and all("Groupe Danse Fictif" not in (n.get("message") or "")
                        and "Groupe Danse Fictif" not in (n.get("organisation") or "") for n in notifs),
         "%s" % [n.get("message") for n in notifs])
conv = S.pf_conversation(S.pf_cle_conversation(m), [m], {}, {}, {}, {})
verifier("la conversation a sa PROPRE cle, distincte de celle du prospect",
         S.pf_cle_conversation(m) == "inbound:%s" % m["id"] != "act-ds")
verifier("elle est marquee `a_rattacher`", conv["a_rattacher"] == 1)
verifier("elle porte la piste (nom + cle) pour l'affichage",
         (conv["piste"] or {}).get("recipient_key") == "TST-A1"
         and (conv["piste"] or {}).get("action_id") == "act-ds")
verifier("elle passe EN TETE de la file, meme si le message est lu",
         conv["rang"] == S.PF_RANG_NOUVEAU)
m_lu = dict(m, read_at="2026-10-27T09:00:00+00:00")
conv_lu = S.pf_conversation(S.pf_cle_conversation(m_lu), [m_lu], {}, {}, {}, {})
verifier("MEME LU, le message reste `a_rattacher` et en tete",
         conv_lu["a_rattacher"] == 1 and conv_lu["non_lues"] == 0
         and conv_lu["rang"] == S.PF_RANG_NOUVEAU)
m_ok = dict(m, statut=S.P3U2_STATUT_RATTACHE, action_id="act-ds", read_at="x")
conv_ok = S.pf_conversation("act-ds", [m_ok], {}, {}, {}, {})
verifier("une fois rattache, plus de drapeau ni de piste",
         conv_ok["a_rattacher"] == 0 and conv_ok["piste"] is None)
verifier("le compteur de la file compte les conversations a rattacher",
         S.pf_compteurs([conv, conv_ok])["a_rattacher"] == 1)

# ============================================================================
print("\n12-ter. N — CHOISIR LE BON PROSPECT : LA LISTE DES CANDIDATS")
# ============================================================================
b = base_neuve(actions=[
    action(),
    action(id_="act-b", target="autre@club.ch", token="cccc1180d1aeeab4da2899419f802687",
           ref="TST-B1", organisations=["Club B"]),
    action(id_="act-nope", target="x@y.ch", token="dddd1180d1aeeab4da2899419f802687",
           ref="TST-B2", sent_at=None)])
appeler(evenement(de="membre@agepoly.exemple.test"))
m = seul_message(b)
r = lancer(S.p3r5_candidats(m["id"], RequeteFictive(JPROPRIO)))
ids = [c["action_id"] for c in r["candidats"]]
verifier("la suggestion arrive en premier", ids and ids[0] == "act-ds" and r["candidats"][0]["suggere"])
verifier("une action jamais envoyee n'est PAS proposee", "act-nope" not in ids)
verifier("les autres prospects envoyes sont proposes", "act-b" in ids)
r2 = lancer(S.p3r5_candidats(m["id"], RequeteFictive(JPROPRIO, params={"q": "club b"})))
verifier("la recherche filtre", [c["action_id"] for c in r2["candidats"]] == ["act-b"])
r3 = lancer(S.p3r5_candidats(m["id"], RequeteFictive(JPROPRIO, params={"q": ".*"})))
verifier("une expression reguliere est traitee comme du TEXTE, pas comme un motif",
         r3["candidats"] == [])
verifier("sans session : 403",
         refus(lambda: lancer(S.p3r5_candidats(m["id"], RequeteFictive(None)))) == 403)
verifier("autre coach : 404",
         refus(lambda: lancer(S.p3r5_candidats(m["id"], RequeteFictive(JB)))) == 404)
lancer(S.p3r5_rattacher(m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-b"})))
verifier("une fois rattache, la liste n'a plus de raison d'etre (409)",
         refus(lambda: lancer(S.p3r5_candidats(m["id"], RequeteFictive(JPROPRIO)))) == 409)
verifier("on peut rattacher a un AUTRE prospect que la piste (c'est tout l'interet)",
         action_en_base(b, "act-b").get("replied_at") and "replied_at" not in action_en_base(b, "act-ds"))
m3 = seul_message(b)
verifier("le message porte alors le bon proprietaire",
         m3.get("action_id") == "act-b" and m3.get("recipient_key") == "TST-B1")

# ============================================================================
print("\n12-quater. O — SI LA CONFIRMATION ECHOUE, RIEN N'EST MODIFIE")
# ============================================================================
b = base_neuve()
appeler(evenement(de="membre@agepoly.exemple.test"))
m = seul_message(b)
_vrai = S.p3u2_marquer_reponse


async def _panne(*a, **k):
    raise RuntimeError("panne simulee de l'ecriture des relances")


S.p3u2_marquer_reponse = _panne
try:
    code = refus(lambda: lancer(S.p3r5_rattacher(
        m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-ds"}))))
finally:
    S.p3u2_marquer_reponse = _vrai
m_apres = seul_message(b)
a_apres = action_en_base(b)
verifier("la panne se traduit par un echec franc (500)", code == 500, "code=%s" % code)
verifier("le message est REVENU en revue manuelle",
         m_apres.get("statut") == S.P3U2_STATUT_REVUE
         and m_apres.get("matching_method") == S.P3U2_METHODE_DOMAINE)
verifier("il n'a AUCUN proprietaire",
         not m_apres.get("action_id") and not m_apres.get("recipient_key")
         and not m_apres.get("rattache_par"))
verifier("la piste est intacte", m_apres.get("piste_action_id") == "act-ds")
verifier("AUCUNE relance n'a ete touchee",
         "replied_at" not in a_apres and "j3_annule_le" not in a_apres)
verifier("la fiche n'a pas bouge",
         next(f for f in b["partner_prospects"].documents
              if f.get("ref") == "TST-A1").get("status") == "contacte")
_r = lancer(S.p3r5_rattacher(m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-ds"})))
verifier("et un NOUVEL essai reussit (pas de 409 coince)", _r.get("ok") is True)
verifier("les relances s'arretent alors", bool(action_en_base(b).get("replied_at")))

b = base_neuve(actions=[action(), action(id_="act-b", target="autre@club.ch",
                                         token="cccc1180d1aeeab4da2899419f802687", ref="TST-B1")])
appeler(evenement(de="membre@agepoly.exemple.test"))
m = seul_message(b)
lancer(S.p3r5_rattacher(m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-ds"})))
code = refus(lambda: lancer(S.p3r5_rattacher(
    m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-b"}))))
verifier("le second clic (autre prospect) est refuse (409)", code == 409)
verifier("et il n'a arrete AUCUNE relance de l'autre prospect",
         "replied_at" not in action_en_base(b, "act-b")
         and "j3_annule_le" not in action_en_base(b, "act-b"))

# ============================================================================
print("\n12-quinquies. P — LE COMPTEUR DU TABLEAU DE BORD NE DISPARAIT PAS UNE FOIS LU")
# ============================================================================
b = base_neuve()
appeler(evenement(de="membre@agepoly.exemple.test"))                      # a rattacher
m = seul_message(b)
liste = lancer(S.p3u2_lister_reponses(RequeteFictive(JPROPRIO)))
verifier("neuf : a rattacher ET non lu -> compte UNE fois dans `a_voir`",
         liste["a_rattacher"] == 1 and liste["non_lues"] == 1 and liste["a_voir"] == 1,
         "a_rattacher=%s non_lues=%s a_voir=%s" % (liste["a_rattacher"], liste["non_lues"], liste["a_voir"]))
lancer(S.p3ai_ouvrir_reponse(m["id"], RequeteFictive(JPROPRIO)))      # le coach l'ouvre
liste = lancer(S.p3u2_lister_reponses(RequeteFictive(JPROPRIO)))
verifier("APRES lecture : `non_lues` tombe a 0, mais `a_voir` RESTE a 1",
         liste["non_lues"] == 0 and liste["a_rattacher"] == 1 and liste["a_voir"] == 1,
         "non_lues=%s a_rattacher=%s a_voir=%s" % (liste["non_lues"], liste["a_rattacher"], liste["a_voir"]))
verifier("la ligne de la file reste `a_rattacher`, lue ou non",
         [c["a_rattacher"] for c in liste["conversations"]] == [1]
         and liste["conversations"][0]["non_lues"] == 0)
lancer(S.p3r5_rattacher(m["id"], RequeteFictive(JPROPRIO, {"action_id": "act-ds"})))
liste = lancer(S.p3u2_lister_reponses(RequeteFictive(JPROPRIO)))
verifier("une fois rattache ET lu : plus rien n'appelle le coach",
         liste["a_voir"] == 0 and liste["a_rattacher"] == 0 and liste["non_lues"] == 0)
verifier("la conversation est maintenant celle du prospect",
         [c["cle"] for c in liste["conversations"]] == ["act-ds"]
         and liste["conversations"][0]["a_rattacher"] == 0)
verifier("un autre coach ne voit rien de tout cela",
         lancer(S.p3u2_lister_reponses(RequeteFictive(JB)))["a_voir"] == 0)

# ============================================================================
print("\n13. L — NI RESEAU, NI E-MAIL")
# ============================================================================
verifier("aucune sortie reseau tentee", not _TENTATIVES, "%s" % _TENTATIVES[:3])
verifier("AUCUN e-mail envoye", not _ENVOIS, "%s envois" % len(_ENVOIS))
verifier("la route de rattachement est la SEULE ajoutee par ce lot",
         io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
         .count('@api_router.post("/prospect-inbound/{inbound_id}/rattacher")') == 1)

# ============================================================================
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("P3-R5 / V631 — %d/%d" % (_ok, _total))
print("=" * 78)
for intitule, cond, detail in RESULTATS:
    if not cond:
        print("  ECHEC : %s%s" % (intitule, (" -> " + detail) if detail else ""))
sys.exit(0 if _ok == _total else 1)

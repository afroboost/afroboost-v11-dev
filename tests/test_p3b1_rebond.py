#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-B1 — UN REBOND CESSE D'ETRE INVISIBLE, SANS UN SEUL E-MAIL.

POURQUOI CE BANC EXISTE
==============================================================================
Le 03/09/2026, sur les trois premiers J0 reels, UN a rebondi. Chez Resend :
`last_event = bounced`. Chez nous : `statut = envoye`, fiche `contacte`,
AUCUNE trace. La cause n'etait pas dans le code : l'abonnement Resend ne
demandait meme pas `email.bounced`.

CE QUE CE FICHIER PROUVE
==============================================================================
  * un rebond PERMANENT enregistre l'echec, annule J+3 ET J+7, et inscrit
    l'adresse au registre STOP ;
  * la garde `REFUS_EXPRIME` refuse ENSUITE tout envoi a cette adresse — la
    boucle est fermee, pas seulement commencee ;
  * un rebond TRANSITOIRE enregistre et ne bloque RIEN ;
  * le meme evenement rejoue dix fois n'ecrit qu'une fois et ne declenche
    qu'une fois ;
  * un identifiant inconnu ne touche AUCUNE action ;
  * une annulation de relance deja posee (par une reponse) N'EST PAS ecrasee ;
  * l'adresse bloquee est celle de NOTRE action, jamais celle annoncee par la
    charge utile ;
  * `contacte` n'est pas redefini ;
  * `email.received` et `email.sent` continuent de fonctionner ;
  * aucune socket ne s'ouvre, aucun appel Resend reel.

    python3 tests/test_p3b1_rebond.py
"""
import ast
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

# Le faux SDK, pose AVANT l'import du serveur : aucun appel reel possible.
_APPELS_VERIFY = []
_VERIFY_ACCEPTE = {"oui": True}


class _FauxWebhooks:
    @classmethod
    def verify(cls, options):
        _APPELS_VERIFY.append(options)
        if not _VERIFY_ACCEPTE["oui"]:
            raise ValueError("no matching signature found")


_ENVOIS_REELS = []
_faux_resend = types.ModuleType("resend")
_faux_resend.Webhooks = _FauxWebhooks
_faux_resend.Emails = types.SimpleNamespace(
    send=lambda *a, **k: _ENVOIS_REELS.append((a, k)) or {"id": "jamais"})
sys.modules["resend"] = _faux_resend

SECRET = "secret-de-test-p3b1-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3b1-inexistant:27017")
os.environ["RESEND_WEBHOOK_SECRET"] = "whsec_valeur_de_test_jamais_en_production"

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

COACH_A = "coach.a.fictif@exemple.test"
INSTANT = "2026-09-03T10:00:00+00:00"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": "b@exemple.test",
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
CollectionBouchon = _espace["CollectionBouchon"]
BaseBouchon = _espace["BaseBouchon"]
lancer = _espace["lancer"]

CIBLE = "gerant@bar-fictif-p3b1.exemple.test"
ID_MSG = "01a0-fictif-b1-0001"


def action(identifiant="act-b1", cible=CIBLE, cle="BAR-99", msg=ID_MSG, **k):
    a = {"id": identifiant, "campaign_id": "camp-b1", "coach_id": COACH_A,
         "recipient_key": cle, "channel": "email", "target": cible,
         "execution_type": "AUTO", "statut": "envoye", "sent_at": INSTANT,
         "message_j0": "Bonjour !", "provider": "resend",
         "provider_message_id": msg, "reply_token": "a" * 32,
         "j3_due_at": "2026-09-06T10:00:00+00:00",
         "j7_due_at": "2026-09-10T10:00:00+00:00",
         "prospect_ids": ["R-" + cle], "verrou_actif": True}
    a.update(k)
    return a


class CollectionUpsert(CollectionBouchon):
    """Le bouchon maison ignore `upsert`, `$setOnInsert` et `$unset`.

    `p3u1_enregistrer_refus` s'en sert pour inscrire un refus : sans ces trois
    verbes, le registre STOP resterait vide et le banc validerait un blocage
    qui n'a jamais eu lieu. On les ajoute ICI, dans le banc, plutot que de
    modifier le bouchon partage dont dependent huit autres fichiers.

    ET SON CURSEUR N'EST PAS ITERABLE DU TOUT. `Curseur` n'expose que
    `to_list` — ni `__aiter__`, ni `__anext__` : un `async for` leve `TypeError`, que `c3_refus_exprimes`
    rattrape en concluant « refus illisibles, on n'en deduit rien ». Le
    registre serait donc TOUJOURS lu comme vide, et le banc verrait la garde
    refuser pour une tout autre raison en croyant avoir prouve le blocage.
    C'est exactement le faux vert que ce banc doit eviter.
    """

    def find(self, filtre=None, projection=None, *a, **k):
        trouves = [dict(d) for d in self.documents if self._ok(d, filtre)]

        class _Iterable:
            def __init__(self_inner):
                self_inner._reste = iter(trouves)

            def __aiter__(self_inner):
                return self_inner

            async def __anext__(self_inner):
                try:
                    return next(self_inner._reste)
                except StopIteration:
                    raise StopAsyncIteration

            def sort(self_inner, *aa, **kk):
                return self_inner

            async def to_list(self_inner, n=None):
                return trouves[:n] if n else trouves

        return _Iterable()

    async def update_one(self, filtre, maj, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                for cle in (maj.get("$unset") or {}):
                    d.pop(cle, None)
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        if k.get("upsert") or (a and a[0]):
            neuf = {}
            neuf.update(maj.get("$setOnInsert") or {})
            neuf.update(maj.get("$set") or {})
            for cle, valeur in (filtre or {}).items():
                if not isinstance(valeur, dict):
                    neuf.setdefault(cle, valeur)
            self.documents.append(neuf)
            self.ecritures += 1
            return type("R", (), {"matched_count": 0, "modified_count": 0,
                                  "upserted_id": "neuf"})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


def base_neuve(actions=None, fiches=None):
    b = BaseBouchon(fiches or [])
    b[S.P3S3_ACTIONS] = CollectionBouchon(
        S.P3S3_ACTIONS, [dict(a) for a in (actions or [])], uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(
        S.P3U2_COLLECTION, [],
        uniques=[(("coach_id", "dedupe_key"), {"dedupe_key": {"$type": "string"}})])
    b["subscribers"] = CollectionUpsert("subscribers", [], uniques=[(("channel", "value"), None)])
    S.db = b
    return b


def rebond(type_="Permanent", subtype="General", identifiant=ID_MSG,
           message="mailbox does not exist", **k):
    corps = {"email_id": identifiant, "to": [CIBLE],
             "from": "Afroboost <notifications@afroboost.com>",
             "subject": "Proposition de collaboration avec Afroboost",
             "created_at": INSTANT,
             "bounce": {"message": message, "type": type_,
                        "subType": subtype, "diagnosticCode": []}}
    corps.update(k.pop("data", {}))
    e = {"type": "email.bounced", "created_at": INSTANT, "data": corps}
    e.update(k)
    return e


def act(base, identifiant="act-b1"):
    return [a for a in base[S.P3S3_ACTIONS].documents if a["id"] == identifiant][0]


print("=" * 78)
print("P3-B1 — LES REBONDS")
print("=" * 78)

# ---------------------------------------------------------------------------
print("\n1. LA LECTURE DE L'EVENEMENT (fonction pure)")
_lu = S.p3b1_rebond_depuis(rebond())
verifier("1a. l'identifiant est lu depuis data.email_id", _lu["identifiant"] == ID_MSG, str(_lu))
verifier("1b. le type est lu", _lu["type"] == "Permanent")
verifier("1c. le sous-type est lu", _lu["subtype"] == "General")
verifier("1d. le message est lu", _lu["message"] == "mailbox does not exist")
_alt = S.p3b1_rebond_depuis({"type": "email.bounced", "data": {"id": "X-1"},
                             "bounce": {"type": "Transient", "subType": "MailboxFull"}})
verifier("1e. `data.id` est accepte quand `email_id` manque", _alt["identifiant"] == "X-1", str(_alt))
verifier("1f. l'objet `bounce` est accepte a la racine", _alt["type"] == "Transient", str(_alt))
verifier("1g. un evenement vide ne rend RIEN d'invente",
         S.p3b1_rebond_depuis({}) == {"identifiant": "", "type": "", "subtype": "", "message": ""})
verifier("1h. un `bounce` non-dictionnaire ne casse pas la lecture",
         S.p3b1_rebond_depuis({"data": {"email_id": "Z", "bounce": "cassé"}})["type"] == "")
verifier("1i. le message est borne (pas de charge utile sans fin)",
         len(S.p3b1_rebond_depuis(rebond(message="x" * 5000))["message"]) == 500)
_src_pure = SRC[SRC.index("def p3b1_rebond_depuis"):SRC.index("def p3b1_est_permanent")]
verifier("1j. la lecture est PURE : elle ne touche jamais la base",
         "db[" not in _src_pure and "await" not in _src_pure)

# ---------------------------------------------------------------------------
print("\n2. PERMANENT OU NON — ET RIEN ENTRE LES DEUX")
verifier("2a. `Permanent` est permanent", S.p3b1_est_permanent("Permanent") is True)
verifier("2b. la casse n'a pas d'importance", S.p3b1_est_permanent("PERMANENT") is True)
verifier("2c. `Transient` ne l'est PAS", S.p3b1_est_permanent("Transient") is False)
verifier("2d. `Undetermined` ne l'est PAS", S.p3b1_est_permanent("Undetermined") is False)
verifier("2e. vide ne l'est PAS", S.p3b1_est_permanent("") is False)
verifier("2f. None ne l'est PAS", S.p3b1_est_permanent(None) is False)
verifier("2g. un type inconnu ne bloque PAS (le cas sur est de ne pas bloquer)",
         S.p3b1_est_permanent("PermanentPeutEtre") is False)

# ---------------------------------------------------------------------------
print("\n3. REBOND PERMANENT : ON ENREGISTRE, ON ANNULE, ON BLOQUE")
_b = base_neuve([action()], fiches=[{"id": "p-1", "ref": "R-BAR-99", "coach_id": COACH_A,
                                     "status": "contacte", "organisation_name": "Bar fictif"}])
_r = lancer(S.p3b1_traiter_rebond(rebond()))
_a = act(_b)
verifier("3a. le rebond est traite", _r["traite"] is True, str(_r))
verifier("3b. il est reconnu permanent", _r["permanent"] is True)
verifier("3c. l'action retrouvee est la bonne", _r["action_id"] == "act-b1")
verifier("3d. `provider_status` passe a `bounced`", _a.get("provider_status") == "bounced")
verifier("3e. `bounced_at` est pose", bool(_a.get("bounced_at")))
verifier("3f. `bounce_type` est enregistre", _a.get("bounce_type") == "Permanent")
verifier("3g. `bounce_subtype` est enregistre", _a.get("bounce_subtype") == "General")
verifier("3h. `bounce_message` est enregistre", _a.get("bounce_message") == "mailbox does not exist")
verifier("3i. J+3 est ANNULE", bool(_a.get("j3_annule_le")))
verifier("3j. J+7 est ANNULE", bool(_a.get("j7_annule_le")))
verifier("3k. le motif dit pourquoi", _a.get("j3_annule_motif") == "rebond permanent"
         and _a.get("j7_annule_motif") == "rebond permanent")
verifier("3l. l'adresse entre au registre STOP", _r["refus_pose"] is True)
_reg = _b["subscribers"].documents
verifier("3m. le registre porte la BONNE adresse et le bon canal",
         len(_reg) == 1 and _reg[0]["value"] == CIBLE and _reg[0]["channel"] == "email", str(_reg))
verifier("3n. le refus est bien un opt-out", _reg[0]["status"] == "opted_out")

print("\n   -- CE QUI COMPTE VRAIMENT : LA BOUCLE EST-ELLE FERMEE ? --")
_refus = lancer(S.c3_refus_exprimes("email", [CIBLE]))
_cle = set("email:%s" % v for v in _refus)
_g = S.p3s3d_garde_action(dict(_a, statut="pret", sent_at=None), {"etat": "approuvee",
     S.P3S3D2_CHAMP_OBJET: "Objet"}, fiches=[], refus=_cle, envoi_autorise=True, simulation=False)
verifier("3o. LA GARDE REFUSE ENSUITE CETTE ADRESSE", _g["autorise"] is False, str(_g))
verifier("3p. et elle dit REFUS_EXPRIME", _g["code"] == "REFUS_EXPRIME", str(_g))
verifier("3q. la relance est refusee elle aussi",
         S.p3u2_relance_autorisee(_a, _cle)["autorise"] is False)

print("\n   -- CE QUI NE DOIT PAS BOUGER --")
verifier("3r. la fiche prospect n'est PAS supprimee", len(_b[S.P3S1_COLLECTION].documents) == 1)
verifier("3s. `contacte` n'est PAS redefini",
         _b[S.P3S1_COLLECTION].documents[0]["status"] == "contacte")
verifier("3t. l'historique du premier envoi est intact",
         _a.get("sent_at") == INSTANT and _a.get("provider_message_id") == ID_MSG)
verifier("3u. le jeton de reponse survit", _a.get("reply_token") == "a" * 32)
verifier("3v. le message d'origine n'est pas touche", _a.get("message_j0") == "Bonjour !")

# ---------------------------------------------------------------------------
print("\n4. REBOND TRANSITOIRE : ON ENREGISTRE, ON NE BLOQUE RIEN")
_b = base_neuve([action()])
_r = lancer(S.p3b1_traiter_rebond(rebond(type_="Transient", subtype="General",
                                         message="general bounce message")))
_a = act(_b)
verifier("4a. le rebond est traite", _r["traite"] is True)
verifier("4b. il n'est PAS permanent", _r["permanent"] is False)
verifier("4c. il est bien enregistre", _a.get("bounce_type") == "Transient"
         and bool(_a.get("bounced_at")))
verifier("4d. `provider_status` passe a `bounced` aussi", _a.get("provider_status") == "bounced")
verifier("4e. J+3 n'est PAS annule", "j3_annule_le" not in _a)
verifier("4f. J+7 n'est PAS annule", "j7_annule_le" not in _a)
verifier("4g. AUCUNE inscription au registre STOP", _b["subscribers"].documents == [])
verifier("4h. l'adresse reste joignable", _r.get("refus_pose") is False)

# ---------------------------------------------------------------------------
print("\n5. LE REJEU — UN FOURNISSEUR REJOUE, C'EST DOCUMENTE")
_b = base_neuve([action()], fiches=[{"id": "p-1", "ref": "R-BAR-99", "coach_id": COACH_A,
                                     "status": "contacte"}])
_premier = lancer(S.p3b1_traiter_rebond(rebond()))
_date = act(_b).get("bounced_at")
_suivants = [lancer(S.p3b1_traiter_rebond(rebond())) for _ in range(9)]
_a = act(_b)
verifier("5a. le premier passage traite", _premier["traite"] is True)
verifier("5b. les neuf suivants NE traitent PAS", all(x["traite"] is False for x in _suivants))
verifier("5c. et ils le disent", all(x.get("doublon") is True for x in _suivants))
verifier("5d. la date de rebond n'a PAS bouge", _a.get("bounced_at") == _date)
verifier("5e. une seule inscription au registre", len(_b["subscribers"].documents) == 1)
verifier("5f. une seule annulation J+3", _a.get("j3_annule_motif") == "rebond permanent")

# ---------------------------------------------------------------------------
print("\n6. UN IDENTIFIANT INCONNU NE TOUCHE RIEN")
_b = base_neuve([action(), action("act-autre", "autre@exemple.test", "BAR-98", "01a0-autre")])
_r = lancer(S.p3b1_traiter_rebond(rebond(identifiant="identifiant-qui-n-existe-pas")))
verifier("6a. rien n'est traite", _r["traite"] is False)
verifier("6b. aucune action n'est designee", _r["action_id"] is None)
verifier("6c. AUCUNE action n'a bouge",
         not any(a.get("bounced_at") for a in _b[S.P3S3_ACTIONS].documents))
verifier("6d. aucun registre STOP", _b["subscribers"].documents == [])
_r2 = lancer(S.p3b1_traiter_rebond({"type": "email.bounced", "data": {}}))
verifier("6e. un evenement sans identifiant ne fait rien", _r2["traite"] is False)
verifier("6f. la correspondance est EXACTE, pas partielle",
         lancer(S.p3b1_traiter_rebond(rebond(identifiant=ID_MSG[:8])))["traite"] is False)

# ---------------------------------------------------------------------------
print("\n7. UNE ANNULATION DEJA POSEE N'EST PAS ECRASEE")
_b = base_neuve([action(j3_annule_le="2026-09-04T00:00:00+00:00",
                        j3_annule_motif="reponse recue")])
lancer(S.p3b1_traiter_rebond(rebond()))
_a = act(_b)
verifier("7a. la date d'annulation d'origine survit",
         _a.get("j3_annule_le") == "2026-09-04T00:00:00+00:00")
verifier("7b. son motif survit — une reponse reste une reponse",
         _a.get("j3_annule_motif") == "reponse recue")
verifier("7c. mais J+7, qui n'etait pas annule, l'est maintenant",
         _a.get("j7_annule_motif") == "rebond permanent")

# ---------------------------------------------------------------------------
print("\n8. L'ADRESSE BLOQUEE EST LA NOTRE, PAS CELLE DE LA CHARGE UTILE")
_b = base_neuve([action()])
lancer(S.p3b1_traiter_rebond(rebond(data={"to": ["adresse-injectee@pirate.exemple.test"]})))
_reg = _b["subscribers"].documents
verifier("8a. c'est le `target` de l'action qui est bloque",
         len(_reg) == 1 and _reg[0]["value"] == CIBLE, str(_reg))
verifier("8b. l'adresse annoncee par l'evenement n'entre PAS au registre",
         not any(d["value"] == "adresse-injectee@pirate.exemple.test" for d in _reg))

# ---------------------------------------------------------------------------
print("\n9. LE CABLAGE DANS LE WEBHOOK")
_route = SRC[SRC.index("async def p3u3_webhook_resend"):]
_route = _route[:_route.index("\n# =")]
verifier("9a. la signature est verifiee AVANT toute lecture du type",
         _route.index("p3u3_signature_valide") < _route.index("type_evenement ="))
verifier("9b. la branche rebond existe", "P3B1_EVENEMENT_REBOND" in _route)
verifier("9c. elle appelle le traitement dedie", "p3b1_traiter_rebond" in _route)
verifier("9d. elle passe APRES `email.sent`",
         _route.index("P3U3_EVENEMENT_ENVOYE") < _route.index("P3B1_EVENEMENT_REBOND"))
verifier("9e. `email.received` reste traite", "p3u2_recevoir" in _route)
verifier("9f. un rebond n'appelle PAS le moteur de reception",
         _route.index("p3b1_traiter_rebond") < _route.index("p3u3_adapter_recu"))
verifier("9g. un rebond n'ecrit jamais `replied_at`",
         "replied_at" not in SRC[SRC.index("async def p3b1_traiter_rebond"):
                                 SRC.index("@api_router.post(\"/webhooks/resend\")")])
_bloc_b1 = SRC[SRC.index("def p3b1_rebond_depuis"):SRC.index("@api_router.post(\"/webhooks/resend\")")]
verifier("9h. aucune regex ne touche la requete Mongo", "$regex" not in _bloc_b1)
verifier("9i. la recherche se fait sur `provider_message_id`",
         '"provider_message_id": lu["identifiant"]' in _bloc_b1)
verifier("9j. l'ecriture est conditionnee par `bounced_at` absent",
         '"bounced_at": {"$exists": False}' in _bloc_b1)
verifier("9k. le registre STOP passe par la fonction existante",
         "p3u1_enregistrer_refus" in _bloc_b1)
verifier("9l. `status` de la fiche n'est jamais reecrit ici", '"status"' not in _bloc_b1)

# ---------------------------------------------------------------------------
print("\n10. RIEN DE CE QUI MARCHAIT N'EST CASSE")
_b = base_neuve([action("act-recu", "hotel@exemple.test", "BAR-01", "01a0-recu")])
_msg = {"from_email": "quelquun@autre.exemple.test",
        "to_email": S.p3r1_adresse_reponse("a" * 32),
        "subject": "Re: Proposition", "body_text": "Oui !",
        "received_at": INSTANT, "provider": "resend",
        "provider_event_id": "evt-b1-recu", "message_id": "<r1@x.test>"}
_i = lancer(S.p3u2_recevoir(_msg, COACH_A))
verifier("10a. P3-R1 rattache toujours par jeton", _i.get("methode") == S.P3U2_METHODE_TOKEN, str(_i))
verifier("10b. avec la confiance maximale", _i.get("confiance") == 100)
verifier("10c. et `replied_at` est ecrit", bool(act(_b, "act-recu").get("replied_at")))
_b = base_neuve([action("act-envoi", CIBLE, "BAR-97", "01a0-envoi")])
_e = lancer(S.p3u3_traiter_envoi({"type": "email.sent", "data": {
    "email_id": "01a0-envoi", "message_id": "<sortant@ses.test>"}}))
verifier("10d. `email.sent` ecrit toujours le Message-ID RFC", _e["ecrit"] is True)
verifier("10e. et il est bien pose",
         act(_b, "act-envoi").get(S.P3U2_CHAMP_RFC) == "sortant@ses.test")

# ---------------------------------------------------------------------------
print("\n11. AUCUN E-MAIL, AUCUNE SOCKET")
verifier("11a. aucun envoi Resend reel", _ENVOIS_REELS == [])
verifier("11b. aucune sortie reseau tentee", _TENTATIVES == [], str(_TENTATIVES[:3]))
verifier("11c. le module analyse est bien du Python valide",
         isinstance(ast.parse(SRC), ast.Module))

print()
print("=" * 78)
_ech = [i for i, c, _ in RESULTATS if not c]
print("P3-B1 : %d / %d verifications" % (len(RESULTATS) - len(_ech), len(RESULTATS)))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
print("E-mails envoyes : %d — le SDK est un faux, pose avant l'import" % len(_ENVOIS_REELS))
print("=" * 78)
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
sys.exit(0 if not _ech else 1)

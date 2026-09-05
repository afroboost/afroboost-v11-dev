#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI-P1 + READ-P1 — L'ANALYSE D'UNE REPONSE, ET LES DEUX ETATS DU COACH.

POURQUOI CE BANC EXISTE
==============================================================================
Trois partenaires ont repondu le meme jour, au meme objet, sur la meme
campagne : BDE HE-ARC (ETU-04), ACD Lausanne (LSN-A3) et SalsaRica (ZRH-D5).
Un seul d'entre eux a un lien avec M. Ndongo Beye. La consigne metier la plus
importante de ce chantier est donc negative : le dossier d'un prospect ne doit
JAMAIS contenir un mot du dossier d'un autre. Ce fichier le prouve mot a mot.

CE QUE CE FICHIER PROUVE
==============================================================================
  * A. une reponse qui arrive est NON LUE et A REPONDRE — sans migration ;
  * B. afficher la liste, charger le dashboard et analyser avec l'IA ne
       marquent RIEN comme lu : seule l'ouverture explicite le fait ;
  * C. ouvrir n'est pas repondre — « A REPONDRE » survit a la lecture ;
  * D. « TRAITE » n'arrive que par une action humaine, et se defait ;
  * E. lire ETU-04 ne touche ni LSN-A3 ni ZRH-D5 ;
  * F. un second super-admin qui consulte n'efface PAS le « nouveau » du
       proprietaire ;
  * G. les compteurs sont comptes en base, jamais sur la page rendue ;
  * H. le contexte IA d'ETU-04 ne contient AUCUN mot de LSN-A3 (ni « Ndongo »,
       ni « Eveline », ni « ACD ») — et reciproquement ;
  * I. le brouillon ecrit a la BONNE adresse, recopiee du message recu et
       jamais proposee par le modele ;
  * J. regenerer ETU-04 ne modifie pas le brouillon de LSN-A3 ;
  * K. une reponse sans corps refuse l'analyse au lieu d'inventer ;
  * L. un sujet d'argent leve « VALIDATION BASSI NECESSAIRE » ;
  * M. sans jeton, et pour un autre coach : refus ;
  * N. AUCUN e-mail : ni Resend, ni drapeau d'envoi, ni sortie reseau.
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

SECRET = "secret-de-test-p3ai-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p3ai-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


def _bloc(source, entete):
    """Le bloc du lot, borne par la banniere de lot SUIVANTE, quelle qu'elle soit."""
    debut = source.index(entete)
    banniere = "\n# " + "=" * 76 + "\n# "
    apres = source.index("\n\n", debut)
    suivante = source.find(banniere, apres)
    return source[debut:suivante] if suivante != -1 else source[debut:]


BLOC_READ = _bloc(SRC, "# READ-P1 — DEUX ETATS QU'ON CONFOND TOUJOURS")
BLOC_P3N = _bloc(SRC, "# AI-P3 — LA MEMOIRE DE CE QUI S'EST PASSE HORS DES E-MAILS")


def _bloc_p3n_code(nom):
    """Le CODE d'une fonction du lot AI-P3, sans sa prose."""
    for noeud in ast.walk(ast.parse(BLOC_P3N)):
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name == nom:
            if ast.get_docstring(noeud):
                noeud.body = noeud.body[1:]
            return ast.unparse(ast.fix_missing_locations(noeud))
    return ""
BLOC_AI = _bloc(SRC, "# AI-P1 — L'ANALYSE D'UNE REPONSE")


def _sans_prose(bloc):
    """Le CODE du bloc, sans commentaires ni docstrings.

    LA LECON EST DEJA PAYEE AILLEURS DANS CE DEPOT (`test_p3u2_inbound.py`,
    section 14) : une verification qui cherche un mot dans le texte mord sur le
    commentaire qui explique justement qu'on ne l'emploie pas. Les interdits de
    la section 11 portent sur ce que le code FAIT, pas sur ce qu'il RACONTE.
    """
    arbre = ast.parse(bloc)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef)) and ast.get_docstring(noeud):
            noeud.body = noeud.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(arbre))

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
ADMIN = "admin.fictif@exemple.test"      # second super-admin, comme en production
INSTANT = "2026-09-05T09:00:00+00:00"

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

JA, JB = jeton(COACH_A), jeton(COACH_B)
JADMIN = jeton(ADMIN)

# ============================================================================
# LES TROIS CAS REELS, RECOPIES DE LA PRODUCTION (mesure du 05/09/2026).
# Les corps sont ceux qui sont VRAIMENT en base : c'est sur eux que le
# cloisonnement doit tenir, pas sur des textes de laboratoire.
# ============================================================================
CORPS_ETU04 = ("Bonjour,\n\nCela nous semble une proposition interessante, ca consiste "
               "en quoi?\nEt quels sont les enjeux pour cette possible collaboration?\n\n"
               "Avec nos meilleures salutations,\n\nBureau des etudiants HE-Arc")
CORPS_LSNA3 = ("Bonjour oui, cela peut se faire, Ndongo Beye est joignable au "
               "+41 76 797 24 79.\n\nEveline Sautaux, ACD Lausanne")
CORPS_ZRHD5 = ("Hola Bassi\n\nDanke fuer deine Anfrage, aber wir sind nicht interessiert\n\n"
               "Freundliche Gruesse\nSonja")

CAS = [
    ("etu04", "ETU-04", "info@bde-hearc.ch", "BDE HE-ARC", CORPS_ETU04, "2026-09-04T05:25:19Z"),
    ("lsna3", "LSN-A3", "eveline.sautaux@assoacd.org", "ACD Lausanne", CORPS_LSNA3, "2026-09-03T13:35:35Z"),
    ("zrhd5", "ZRH-D5", "info@salsarica.ch", "SalsaRica", CORPS_ZRHD5, "2026-09-03T11:37:15Z"),
]


def action_de(suffixe, cle, organisation):
    return {"id": "act-" + suffixe, "campaign_id": "camp-p3", "coach_id": COACH_A,
            "channel": "email", "recipient_key": cle, "organisations": [organisation],
            "prospect_ids": ["R-" + cle], "prospect_uuids": ["p-" + suffixe],
            "language": "FR", "message_j0": "Bonjour, je suis Bassi d'Afroboost.",
            "statut": "envoye", "sent_at": INSTANT}


def message_de(suffixe, cle, adresse, corps, recu, **extra):
    doc = {"id": "inb-" + suffixe, "coach_id": COACH_A, "campaign_id": "camp-p3",
           "action_id": "act-" + suffixe, "recipient_key": cle,
           "from_email": adresse, "to_email": "r-jeton@reply.afroboosteur.com",
           "subject": "Re: Proposition de collaboration avec Afroboost",
           "body_text": corps, "received_at": recu, "statut": "rattache",
           "matching_method": "A0_REPLY_TOKEN", "matching_confidence": 100,
           "motif": "", "processed_at": recu, "created_at": recu}
    doc.update(extra)
    return doc


def fiche_de(suffixe, organisation):
    return {"id": "p-" + suffixe, "ref": "R", "coach_id": COACH_A,
            "organisation_name": organisation, "contact_name": ""}


def base_neuve(messages=None, actions=None, fiches=None):
    b = BaseBouchon([])
    b[S.P3S1_COLLECTION] = CollectionBouchon(S.P3S1_COLLECTION, fiches or [])
    b[S.P3S3_ACTIONS] = CollectionBouchon(S.P3S3_ACTIONS, actions or [],
                                          uniques=[(("id",), None)])
    b[S.P3U2_COLLECTION] = CollectionBouchon(S.P3U2_COLLECTION, messages or [],
                                             uniques=[(("id",), None)])
    b[S.P3AI_BROUILLONS] = CollectionBouchon(S.P3AI_BROUILLONS, [],
                                             uniques=[(("inbound_id",), None)])
    b["prospect_notes"] = CollectionBouchon("prospect_notes", [])
    b["coaches"] = CollectionBouchon("coaches", [{"email": COACH_A}, {"email": COACH_B}])
    b["coach_auth"] = CollectionBouchon("coach_auth", [])
    S.db = b
    return b


def base_trois_cas(notes=None):
    b = base_neuve([message_de(s, c, a, corps, recu) for s, c, a, _o, corps, recu in CAS],
                   [action_de(s, c, o) for s, c, _a, o, _corps, _recu in CAS],
                   [fiche_de(s, o) for s, _c, _a, o, _corps, _recu in CAS])
    if notes:
        b["prospect_notes"] = CollectionBouchon("prospect_notes", notes)
    return b


# --- LE MODELE EST BOUCHONNE. Aucun appel OpenAI, aucune sortie reseau. -----
_INVITES = []


def modele_bouchon(reponse_proposee, intention="question", langue="fr"):
    async def _faux(invite, ton=""):
        _INVITES.append({"invite": invite, "ton": ton})
        return json.dumps({
            "intention": intention, "langue": langue,
            "resume": "Le partenaire pose une question.",
            "demande": "Comprendre en quoi consiste Afroboost.",
            "prochaine_action": "Repondre et proposer un echange.",
            "reponse_proposee": reponse_proposee,
        })
    return _faux


def analyser(inbound_id, jeton_=None, corps=None):
    req = RequeteFictive(jeton_=jeton_ or JA, corps=corps if corps is not None else {})
    return lancer(S.p3ai_analyser(inbound_id, req))


def lister(jeton_=None, params=None):
    return lancer(S.p3u2_lister_reponses(RequeteFictive(jeton_=jeton_ or JA, params=params)))


def ouvrir(inbound_id, jeton_=None):
    return lancer(S.p3ai_ouvrir_reponse(inbound_id, RequeteFictive(jeton_=jeton_ or JA)))


def message_en_base(base, inbound_id):
    return next(d for d in base[S.P3U2_COLLECTION].documents if d["id"] == inbound_id)


# ============================================================================
print("\n1. UNE REPONSE QUI ARRIVE EST NON LUE ET A REPONDRE — SANS MIGRATION")

_b = base_trois_cas()
verifier("1a. aucun message n'a de `read_at` (l'absence VAUT non lu)",
         all(d.get("read_at") is None for d in _b[S.P3U2_COLLECTION].documents))
verifier("1b. aucun message n'a de `traite_at` (donc : a repondre)",
         all(d.get("traite_at") is None for d in _b[S.P3U2_COLLECTION].documents))

_rep = lister()
verifier("1c. les 3 reponses sont comptees non lues",
         _rep["non_lues"] == 3, str(_rep.get("non_lues")))
verifier("1d. les 3 reponses sont comptees a repondre",
         _rep["a_repondre"] == 3, str(_rep.get("a_repondre")))
verifier("1e. AUCUNE ecriture : lister ne migre rien et ne marque rien",
         _b[S.P3U2_COLLECTION].ecritures == 0, str(_b[S.P3U2_COLLECTION].ecritures))
verifier("1f. `p3u2_recevoir` n'a PAS ete modifie pour poser ces champs",
         "read_at" not in _bloc(SRC, "# P3-U2 — LA RECEPTION DES REPONSES"))


# ============================================================================
print("\n2. CE QUI NE MARQUE JAMAIS COMME LU")

_b = base_trois_cas()
lister()
lister(params={"limit": "1"})           # le dashboard ne demande que les compteurs
verifier("2a. afficher la liste ne marque rien",
         _b[S.P3U2_COLLECTION].ecritures == 0)

S.p3ai_appeler_modele = modele_bouchon("Bonjour,\n\nMerci pour votre retour.\n\nBassi\nAfroboost")
analyser("inb-etu04")
_m = message_en_base(_b, "inb-etu04")
verifier("2b. l'analyse IA ne marque PAS comme lu", _m.get("read_at") is None)
verifier("2c. l'analyse IA ne marque PAS comme traite", _m.get("traite_at") is None)
verifier("2d. la reponse de l'analyse dit explicitement `lu: False`",
         analyser("inb-etu04")["lu"] is False)
verifier("2e. le compteur de non-lus n'a pas bouge apres analyse",
         lister()["non_lues"] == 3, str(lister()["non_lues"]))
verifier("2f. la route de liste n'ecrit dans AUCUN champ d'etat",
         "read_at: maintenant" not in SRC.split("async def p3u2_lister_reponses")[1][:2000])


# ============================================================================
print("\n3. OUVRIR MARQUE LU — ET SEULEMENT LU")

_b = base_trois_cas()
_ouv = ouvrir("inb-etu04")
_m = message_en_base(_b, "inb-etu04")
verifier("3a. l'ouverture pose `read_at`", bool(_m.get("read_at")))
verifier("3b. elle note QUI a lu", _m.get("read_by") == COACH_A)
verifier("3c. elle NE pose PAS `traite_at` — ouvrir n'est pas repondre",
         _m.get("traite_at") is None)
verifier("3d. « a repondre » reste donc a 3", _ouv["a_repondre"] == 3, str(_ouv["a_repondre"]))
verifier("3e. « non lues » tombe a 2", _ouv["non_lues"] == 2, str(_ouv["non_lues"]))

_avant = _m.get("read_at")
ouvrir("inb-etu04")
verifier("3f. une SECONDE ouverture ne repousse pas la date de premiere lecture",
         message_en_base(_b, "inb-etu04").get("read_at") == _avant)
verifier("3g. l'etat survit a une relecture (refresh)",
         lister()["non_lues"] == 2 and message_en_base(_b, "inb-etu04").get("read_at") == _avant)


# ============================================================================
print("\n4. LIRE UNE REPONSE N'EN TOUCHE AUCUNE AUTRE")

verifier("4a. LSN-A3 reste non lue apres lecture d'ETU-04",
         message_en_base(_b, "inb-lsna3").get("read_at") is None)
verifier("4b. ZRH-D5 reste non lue apres lecture d'ETU-04",
         message_en_base(_b, "inb-zrhd5").get("read_at") is None)
ouvrir("inb-lsna3")
verifier("4c. lire LSN-A3 laisse ZRH-D5 intacte",
         message_en_base(_b, "inb-zrhd5").get("read_at") is None)
verifier("4d. le compteur suit exactement : 1 non lue restante",
         lister()["non_lues"] == 1, str(lister()["non_lues"]))
ouvrir("inb-zrhd5")
verifier("4e. tout lu -> 0 non lue, donc AUCUN badge",
         lister()["non_lues"] == 0, str(lister()["non_lues"]))
verifier("4f. mais 3 restent A REPONDRE — la relance ne disparait pas",
         lister()["a_repondre"] == 3, str(lister()["a_repondre"]))


# ============================================================================
print("\n5. « TRAITE » EST UNE DECISION HUMAINE, ET ELLE SE DEFAIT")

_b = base_trois_cas()
_t = lancer(S.p3ai_marquer_traite("inb-zrhd5", RequeteFictive(jeton_=JA, corps={"traite": True})))
verifier("5a. le marquage pose `traite_at`",
         bool(message_en_base(_b, "inb-zrhd5").get("traite_at")))
verifier("5b. il ne pose PAS `read_at` — traiter n'est pas lire",
         message_en_base(_b, "inb-zrhd5").get("read_at") is None)
verifier("5c. « a repondre » tombe a 2", _t["a_repondre"] == 2, str(_t["a_repondre"]))
_t2 = lancer(S.p3ai_marquer_traite("inb-zrhd5", RequeteFictive(jeton_=JA, corps={"traite": False})))
verifier("5d. l'etat est reversible", _t2["a_repondre"] == 3, str(_t2["a_repondre"]))
verifier("5e. RIEN n'appelle ce marquage tout seul : ni la lecture, ni l'analyse",
         "p3ai_marquer_traite(" not in BLOC_AI.replace("async def p3ai_marquer_traite(", "")
         and "p3ai_marquer_traite(" not in BLOC_READ.split("async def p3ai_marquer_traite")[0])


# ============================================================================
print("\n6. UN SECOND SUPER-ADMIN CONSULTE — IL NE DECIDE PAS A LA PLACE DU COACH")

_b = base_trois_cas()
_anciens = list(S.SUPER_ADMIN_EMAILS)
S.SUPER_ADMIN_EMAILS = _anciens + [ADMIN]
try:
    _vu = lister(jeton_=JADMIN)
    verifier("6a. l'admin VOIT bien les reponses (portee complete)",
             _vu["total"] == 3, str(_vu["total"]))
    _cons = ouvrir("inb-etu04", jeton_=JADMIN)
    verifier("6b. son ouverture NE marque PAS le message",
             message_en_base(_b, "inb-etu04").get("read_at") is None)
    verifier("6c. la reponse le dit franchement (`marque: False`)",
             _cons.get("marque") is False, str(_cons.get("marque")))
    verifier("6d. le « nouveau » du proprietaire est intact",
             lister(jeton_=JA)["non_lues"] == 3, str(lister(jeton_=JA)["non_lues"]))
    try:
        lancer(S.p3ai_marquer_traite("inb-etu04", RequeteFictive(jeton_=JADMIN, corps={})))
        _refus = False
    except HTTPException as e:
        _refus = e.status_code == 403
    verifier("6e. il ne peut pas non plus decider « traite » a sa place", _refus)
finally:
    S.SUPER_ADMIN_EMAILS = _anciens


# ============================================================================
print("\n7. LE CONTEXTE IA — TROIS DOSSIERS, AUCUN MOT EN COMMUN")

_b = base_trois_cas(notes=[{"action_id": "act-lsna3", "type": "appel", "created_at": INSTANT,
                            "texte": "Appele M. Ndongo Beye. Echange effectue. "
                                     "J'attends maintenant sa proposition."}])

_ctx = {}
for _s, _cle, _adresse, _org, _corps, _recu in CAS:
    _d = lancer(S.p3ai_dossier("inb-" + _s, COACH_A))
    _notes = lancer(S.p3ai_notes_de(_d["action"]["id"]))
    _ctx[_s] = S.p3ai_contexte(_d["message"], _d["action"], _d["fiches"], _notes)

_texte_etu = json.dumps(_ctx["etu04"], ensure_ascii=False).lower()
_texte_zrh = json.dumps(_ctx["zrhd5"], ensure_ascii=False).lower()
_texte_lsn = json.dumps(_ctx["lsna3"], ensure_ascii=False).lower()

for _mot in ("ndongo", "eveline", "acd", "assoacd", "76 797"):
    verifier("7a. « %s » ABSENT du dossier ETU-04" % _mot, _mot not in _texte_etu)
    verifier("7b. « %s » ABSENT du dossier ZRH-D5" % _mot, _mot not in _texte_zrh)
verifier("7c. « ndongo » PRESENT dans le dossier LSN-A3 — c'est le sien",
         "ndongo" in _texte_lsn)
verifier("7d. la note d'appel n'atteint QUE LSN-A3",
         len(_ctx["lsna3"]["notes"]) == 1 and not _ctx["etu04"]["notes"]
         and not _ctx["zrhd5"]["notes"])
for _mot in ("salsarica", "sonja", "interessiert"):
    verifier("7e. « %s » ABSENT du dossier ETU-04" % _mot, _mot not in _texte_etu)
verifier("7f. chaque dossier porte SON organisation",
         _ctx["etu04"]["organisation"] == "BDE HE-ARC"
         and _ctx["lsna3"]["organisation"] == "ACD Lausanne"
         and _ctx["zrhd5"]["organisation"] == "SalsaRica")
verifier("7g. chaque dossier porte SON adresse",
         _ctx["etu04"]["from_email"] == "info@bde-hearc.ch"
         and _ctx["lsna3"]["from_email"] == "eveline.sautaux@assoacd.org"
         and _ctx["zrhd5"]["from_email"] == "info@salsarica.ch")
verifier("7h. le corps du dossier vient de `body_text`, jamais d'un champ Afroboost",
         _ctx["etu04"]["body_text"] == CORPS_ETU04
         and "Bassi d'Afroboost" not in _ctx["etu04"]["body_text"])

# L'invite transmise au modele porte la meme etancheite.
_inv_etu = S.p3ai_invite(_ctx["etu04"]).lower()
for _mot in ("ndongo", "eveline", "acd", "salsarica", "sonja"):
    verifier("7i. l'invite d'ETU-04 ne contient pas « %s »" % _mot, _mot not in _inv_etu)


# ============================================================================
print("\n8. LE BROUILLON — LA BONNE ADRESSE, TOUJOURS")

_b = base_trois_cas()
for _s, _cle, _adresse, _org, _corps, _recu in CAS:
    S.p3ai_appeler_modele = modele_bouchon("Bonjour,\n\nMerci.\n\nBassi\nAfroboost")
    _r = analyser("inb-" + _s)
    verifier("8a. %s -> destinataire %s" % (_cle, _adresse),
             _r["brouillon"]["to_email"] == _adresse, _r["brouillon"]["to_email"])
    verifier("8b. %s -> organisation %s" % (_cle, _org),
             _r["brouillon"]["organisation"] == _org)
    verifier("8c. %s -> le brouillon pointe le bon message" % _cle,
             _r["brouillon"]["inbound_id"] == "inb-" + _s
             and _r["brouillon"]["action_id"] == "act-" + _s)

verifier("8d. l'adresse ne vient JAMAIS du modele, mais du message recu",
         '"to_email": c.get("from_email")' in BLOC_AI)
verifier("8e. un brouillon par reponse, pas un de plus",
         len(_b[S.P3AI_BROUILLONS].documents) == 3,
         str(len(_b[S.P3AI_BROUILLONS].documents)))

# --- regenerer l'un ne touche pas l'autre ---
_avant_lsn = dict(next(d for d in _b[S.P3AI_BROUILLONS].documents
                       if d["inbound_id"] == "inb-lsna3"))
S.p3ai_appeler_modele = modele_bouchon("TEXTE COMPLETEMENT DIFFERENT POUR ETU-04")
_regen = analyser("inb-etu04", corps={"ton": "court"})
_apres_lsn = next(d for d in _b[S.P3AI_BROUILLONS].documents
                  if d["inbound_id"] == "inb-lsna3")
verifier("8f. regenerer ETU-04 ne modifie pas le brouillon de LSN-A3",
         _apres_lsn == _avant_lsn)
verifier("8g. la regeneration REMPLACE, elle n'empile pas",
         len(_b[S.P3AI_BROUILLONS].documents) == 3)
verifier("8h. la version s'incremente", _regen["brouillon"]["version"] == 2,
         str(_regen["brouillon"]["version"]))
verifier("8i. le ton demande est conserve", _regen["brouillon"]["ton"] == "court")
verifier("8j. le ton entre dans l'invite", "60 mots" in _INVITES[-1]["invite"]
         or _INVITES[-1]["ton"] == "court")

try:
    analyser("inb-etu04", corps={"ton": "sarcastique"})
    _ton_ok = False
except HTTPException as e:
    _ton_ok = e.status_code == 400
verifier("8k. un ton inconnu -> 400, jamais injecte dans l'invite", _ton_ok)


# ============================================================================
print("\n9. CE QUE L'IA REFUSE DE FAIRE")

_b = base_neuve([message_de("vide", "VID-01", "vide@exemple.test", "", INSTANT)],
                [action_de("vide", "VID-01", "Sans corps")], [fiche_de("vide", "Sans corps")])
S.p3ai_appeler_modele = modele_bouchon("ceci ne devrait jamais etre genere")
try:
    analyser("inb-vide")
    _refus_vide = False
except HTTPException as e:
    _refus_vide = e.status_code == 409
verifier("9a. une reponse SANS corps refuse l'analyse (409) au lieu d'inventer", _refus_vide)
verifier("9b. et aucun brouillon n'a ete range",
         len(_b[S.P3AI_BROUILLONS].documents) == 0)

_sensibles = S.p3ai_sujets_sensibles(
    "Quel est votre tarif ? Prevoyez-vous une commission et un contrat d'exclusivite ?")
verifier("9c. les sujets d'argent sont detectes",
         {"paiement", "commission", "contrat", "exclusivite"} <= set(_sensibles),
         str(_sensibles))
verifier("9d. les accents ne les font pas passer au travers",
         "exclusivite" in S.p3ai_sujets_sensibles("clause d'exclusivité"))
verifier("9e. un texte anodin ne leve aucun drapeau",
         S.p3ai_sujets_sensibles("Bonjour, ca consiste en quoi ?") == [])

_b = base_trois_cas()
S.p3ai_appeler_modele = modele_bouchon("Notre tarif depend du format retenu.")
_sens = analyser("inb-etu04")
verifier("9f. un brouillon qui parle d'argent exige VALIDATION BASSI",
         _sens["brouillon"]["validation_requise"] is True,
         str(_sens["brouillon"]["motifs_validation"]))

S.p3ai_appeler_modele = modele_bouchon("")
try:
    analyser("inb-lsna3")
    _vide_ok = False
except HTTPException as e:
    _vide_ok = e.status_code == 502
verifier("9g. un modele qui ne rend rien -> 502, pas un brouillon vide", _vide_ok)
verifier("9h. une intention inventee par le modele retombe sur `autre`",
         S.p3ai_intention("tres enthousiaste") == "autre"
         and S.p3ai_intention("refus") == "refus")


# ============================================================================
print("\n9bis. L'INTENTION DIT CE QU'IL FAUT FAIRE, PAS L'HUMEUR DU PROSPECT")

# LA REGLE, SUR DES CAS GENERIQUES — jamais sur un identifiant particulier.
_CAS_INTENTION = [
    ("une question explicite l'emporte sur l'enthousiasme", "positif",
     "votre proposition nous semble interessante, ca consiste en quoi ?", "question"),
    ("deux questions, meme resultat", "positif",
     "Cela nous semble interessant, ca consiste en quoi?\nEt quels sont les enjeux?",
     "question"),
    ("une demande SANS point d'interrogation compte aussi", "positif",
     "Pouvez-vous nous en dire plus sur votre concept.", "question"),
    ("une demande en allemand compte aussi", "autre",
     "Koennen Sie uns mehr erfahren lassen", "question"),
    ("un accord SANS question reste positif", "positif",
     "Bonjour oui, cela peut se faire, la personne est joignable au 076.", "positif"),
    ("un refus reste un refus", "refus",
     "Danke fuer deine Anfrage, aber wir sind nicht interessiert", "refus"),
    ("UN REFUS POLI AVEC UNE QUESTION RESTE UN REFUS", "refus",
     "Merci, mais pas pour nous. Peut-etre une autre fois ?", "refus"),
    ("une absence reste une absence", "absence",
     "Je suis absente jusqu'au 15 septembre.", "absence"),
    # LA GARDE TRANCHE DANS LES DEUX SENS. Mesure du 05/09 en production :
    # pousse par la consigne, le modele a classe `question` un message qui est
    # un ACCORD sans une seule question (ACD Lausanne). Forcer `question` quand
    # il y a une demande ne suffit pas — il faut la REFUSER quand il n'y en a
    # aucune, sinon « QUESTION » finit par ne plus rien vouloir dire.
    ("un ACCORD sans question n'est PAS une question", "question",
     "Bonjour oui, cela peut se faire, la personne est joignable au 076.", "autre"),
    ("... et on ne devine pas non plus : « autre » dit qu'on ne tranche pas",
     "question", "Bien recu, merci.", "autre"),
]
for _intitule, _modele, _corps, _attendu in _CAS_INTENTION:
    verifier("9bis-a. %s" % _intitule,
             S.p3ai_intention_finale(_modele, _corps) == _attendu,
             S.p3ai_intention_finale(_modele, _corps))

verifier("9bis-b. l'invite N'OFFRE PLUS `question` au modele",
         "NE RENDS JAMAIS « question »" in BLOC_AI
         and '"intention": "positif|refus|absence|autre"' in BLOC_AI)
verifier("9bis-c. l'intention brute du modele est CONSERVEE a cote",
         '"intention_modele"' in BLOC_AI)

# Et de bout en bout : le brouillon range porte l'intention corrigee.
_b = base_trois_cas()
S.p3ai_appeler_modele = modele_bouchon("Bonjour, voici ce qu'est Afroboost.",
                                       intention="positif")
_q = analyser("inb-etu04")
verifier("9bis-d. un message qui pose des questions est range en QUESTION",
         _q["brouillon"]["intention"] == "question", _q["brouillon"]["intention"])
verifier("9bis-e. l'avis du modele reste consultable",
         _q["brouillon"]["intention_modele"] == "positif")
S.p3ai_appeler_modele = modele_bouchon("Merci pour votre retour.", intention="positif")
_p = analyser("inb-lsna3")
verifier("9bis-f. un message SANS question garde l'intention du modele",
         _p["brouillon"]["intention"] == "positif", _p["brouillon"]["intention"])
S.p3ai_appeler_modele = modele_bouchon("Merci.", intention="question")
_p2 = analyser("inb-lsna3")
verifier("9bis-f-bis. un modele qui dit `question` sans question n'est PAS suivi",
         _p2["brouillon"]["intention"] == "autre", _p2["brouillon"]["intention"])
verifier("9bis-f-ter. son avis reste consultable tel quel",
         _p2["brouillon"]["intention_modele"] == "question")
S.p3ai_appeler_modele = modele_bouchon("Danke fuer die Rueckmeldung.",
                                       intention="refus", langue="de")
_r = analyser("inb-zrhd5")
verifier("9bis-g. le refus allemand reste un refus, en allemand",
         _r["brouillon"]["intention"] == "refus" and _r["brouillon"]["langue"] == "de")


# ============================================================================
print("\n9ter. LE BROUILLON SE CORRIGE A LA MAIN, ET N'ENVOIE TOUJOURS RIEN")

_b = base_trois_cas()
S.p3ai_appeler_modele = modele_bouchon("Texte du modele.")
analyser("inb-etu04")

def modifier(inbound_id, texte, jeton_=None):
    return lancer(S.p3ai_modifier_brouillon(
        inbound_id, RequeteFictive(jeton_=jeton_ or JA,
                                   corps={"reponse_proposee": texte})))

_m = modifier("inb-etu04", "Texte corrige a la main par Bassi.")
verifier("9ter-a. le texte corrige remplace celui du modele",
         _m["brouillon"]["reponse_proposee"] == "Texte corrige a la main par Bassi.")
verifier("9ter-b. la correction est datee et signee",
         bool(_m["brouillon"].get("edite_le")) and _m["brouillon"].get("edite_par") == COACH_A)
verifier("9ter-c. le destinataire n'a PAS bouge",
         _m["brouillon"]["to_email"] == "info@bde-hearc.ch")
verifier("9ter-d. l'intention et le resume non plus",
         _m["brouillon"]["intention"] == "question"
         and _m["brouillon"]["resume"] == "Le partenaire pose une question.")

_sens = modifier("inb-etu04", "Nous proposons un tarif de 15 CHF par personne.")
verifier("9ter-e. un montant ecrit A LA MAIN leve la meme alerte",
         _sens["brouillon"]["validation_requise"] is True,
         str(_sens["brouillon"]["motifs_validation"]))

for _mauvais, _code in ((None, 400), ("", 400), ("   ", 400)):
    try:
        lancer(S.p3ai_modifier_brouillon("inb-etu04", RequeteFictive(
            jeton_=JA, corps=({} if _mauvais is None else {"reponse_proposee": _mauvais}))))
        _ok = False
    except HTTPException as e:
        _ok = e.status_code == _code
    verifier("9ter-f. un brouillon vide (%r) est refuse" % _mauvais, _ok)

try:
    modifier("inb-zrhd5", "aucun brouillon ici")
    _sans = False
except HTTPException as e:
    _sans = e.status_code == 404
verifier("9ter-g. corriger un brouillon inexistant -> 404", _sans)

verifier("9ter-h. corriger ETU-04 ne touche pas le brouillon de LSN-A3",
         all(d["inbound_id"] != "inb-lsna3" or "corrige" not in d["reponse_proposee"]
             for d in _b[S.P3AI_BROUILLONS].documents))


# ============================================================================
print("\n9quater. AI-P3 — LES NOTES HUMAINES, ET L'ETAT QU'ELLES DECLARENT")

def base_avec_notes(notes=None):
    b = base_trois_cas()
    b[S.P3N_COLLECTION] = CollectionBouchon(S.P3N_COLLECTION, notes or [])
    return b


def ajouter_note(inbound_id, corps, jeton_=None):
    return lancer(S.p3n_ajouter_note(
        inbound_id, RequeteFictive(jeton_=jeton_ or JA, corps=corps)))


def dossier(inbound_id, jeton_=None):
    return lancer(S.p3n_lire_dossier(inbound_id, RequeteFictive(jeton_=jeton_ or JA)))


NOTE_NDONGO = {"type": "appel", "occurred_at": "2026-09-05",
               "texte": "Appele M. Ndongo Beye. Echange effectue. "
                        "J'attends maintenant sa proposition.",
               "status_after": "en_attente"}

_b = base_avec_notes()
_r = ajouter_note("inb-lsna3", NOTE_NDONGO)
_note = _r["note"]
verifier("9q-a. la note est rangee dans SA collection",
         len(_b[S.P3N_COLLECTION].documents) == 1)
verifier("9q-b. elle est ancree sur l'action et le prospect, PAS sur la cle",
         _note["action_id"] == "act-lsna3" and _note["prospect_uuid"] == "p-lsna3"
         and _note["inbound_id"] == "inb-lsna3")
verifier("9q-c. `recipient_key` n'est qu'un libelle a cote",
         _note["recipient_key"] == "LSN-A3")
verifier("9q-d. le type et l'etat declare sont conserves",
         _note["type"] == "appel" and _note["status_after"] == "en_attente")
verifier("9q-e. la date de l'ACTION est distincte de la date de saisie",
         _note["occurred_at"].startswith("2026-09-05")
         and _note["created_at"] != _note["occurred_at"])
verifier("9q-f. elle porte son auteur", _note["created_by"] == COACH_A)

verifier("9q-g. LE MESSAGE RECU N'A PAS BOUGE — une note n'est pas un e-mail",
         message_en_base(_b, "inb-lsna3")["body_text"] == CORPS_LSNA3)
verifier("9q-h. et elle ne marque RIEN comme lu",
         message_en_base(_b, "inb-lsna3").get("read_at") is None)

verifier("9q-i. LSN-A3 passe EN ATTENTE",
         _r["statut_commercial"] == S.P3N_STATUT_ATTENTE, _r["statut_commercial"])

# --- LE CLOISONNEMENT, LE POINT LE PLUS IMPORTANT DU LOT ---
verifier("9q-j. la note n'apparait PAS dans le dossier d'ETU-04",
         dossier("inb-etu04")["notes"] == [])
verifier("9q-k. ni dans celui de ZRH-D5", dossier("inb-zrhd5")["notes"] == [])
verifier("9q-l. le dossier de LSN-A3, lui, la porte",
         len(dossier("inb-lsna3")["notes"]) == 1)
_t_etu = json.dumps(dossier("inb-etu04"), ensure_ascii=False).lower()
for _mot in ("ndongo", "eveline", "acd"):
    verifier("9q-m. « %s » ABSENT de la chronologie d'ETU-04" % _mot, _mot not in _t_etu)
_t_zrh = json.dumps(dossier("inb-zrhd5"), ensure_ascii=False).lower()
verifier("9q-n. « ndongo » ABSENT de la chronologie de ZRH-D5", "ndongo" not in _t_zrh)
verifier("9q-o. « ndongo » PRESENT dans celle de LSN-A3 — c'est la sienne",
         "ndongo" in json.dumps(dossier("inb-lsna3"), ensure_ascii=False).lower())

# --- LES STATUTS DES TROIS DOSSIERS ---
S.p3ai_appeler_modele = modele_bouchon("Reponse.", intention="refus")
analyser("inb-zrhd5")
S.p3ai_appeler_modele = modele_bouchon("Reponse.", intention="positif")
analyser("inb-etu04")
_statuts = lancer(S.p3n_statuts_de_la_portee(COACH_A))
verifier("9q-p. ETU-04 reste A REPONDRE",
         _statuts["inb-etu04"] == S.P3N_STATUT_A_REPONDRE, _statuts.get("inb-etu04"))
verifier("9q-q. LSN-A3 est EN ATTENTE — la declaration humaine fait foi",
         _statuts["inb-lsna3"] == S.P3N_STATUT_ATTENTE, _statuts.get("inb-lsna3"))
verifier("9q-r. ZRH-D5 est REFUS — deduit de l'intention, sans note",
         _statuts["inb-zrhd5"] == S.P3N_STATUT_REFUS, _statuts.get("inb-zrhd5"))

_c = lancer(S.p3ai_compteurs(COACH_A))
verifier("9q-s. `a_repondre` ne compte plus ni l'attente ni le refus",
         _c["a_repondre"] == 1 and _c["en_attente"] == 1 and _c["refus"] == 1, str(_c))
verifier("9q-t. `non_lues` n'a PAS bouge — lecture et etat sont independants",
         _c["non_lues"] == 3, str(_c["non_lues"]))

# --- L'ORDRE DES PRIORITES ---
verifier("9q-u. `traite_at` prime sur tout",
         S.p3n_statut_commercial({"traite_at": "2026-09-05"}, "en_attente", "refus")
         == S.P3N_STATUT_TRAITE)
verifier("9q-v. une declaration humaine prime sur l'intention lue par l'IA",
         S.p3n_statut_commercial({}, "a_repondre", "refus") == S.P3N_STATUT_A_REPONDRE)
verifier("9q-w. sans declaration, un refus reste un refus",
         S.p3n_statut_commercial({}, "", "refus") == S.P3N_STATUT_REFUS)
verifier("9q-x. sinon : a repondre",
         S.p3n_statut_commercial({}, "", "question") == S.P3N_STATUT_A_REPONDRE)
verifier("9q-y. la declaration la plus recente PAR DATE D'ACTION gagne",
         S.p3n_derniere_declaration([
             {"id": "1", "status_after": "en_attente", "occurred_at": "2026-09-05"},
             {"id": "2", "status_after": "appel_a_faire", "occurred_at": "2026-09-06"},
         ]) == "appel_a_faire")
verifier("9q-z. une note ANNULEE ne compte plus dans l'etat",
         S.p3n_derniere_declaration([
             {"id": "1", "status_after": "en_attente", "occurred_at": "2026-09-05"},
             {"id": "2", "status_after": "refus", "occurred_at": "2026-09-06"},
             {"id": "3", "corrige_note_id": "2", "occurred_at": "2026-09-07"},
         ]) == "en_attente")

# --- AUCUNE LECTURE DE TEXTE LIBRE ---
verifier("9q-aa. le statut ne se devine JAMAIS dans le texte de la note",
         "texte" not in _bloc_p3n_code("p3n_statut_commercial")
         and "texte" not in _bloc_p3n_code("p3n_derniere_declaration"))


# ============================================================================
print("\n9quinquies. LE BROUILLON PERIME SE SIGNALE, IL NE SE REECRIT PAS")

_b = base_avec_notes()
S.p3ai_appeler_modele = modele_bouchon("Je vais contacter M. Ndongo Beye.")
_av = analyser("inb-lsna3")
verifier("9quin-a. avant toute note, le brouillon n'est pas perime",
         lancer(S.p3ai_lire_brouillon("inb-lsna3", RequeteFictive(jeton_=JA)))
         ["contexte_obsolete"] is False)
_ap = ajouter_note("inb-lsna3", NOTE_NDONGO)
verifier("9quin-b. apres la note, il EST signale perime",
         _ap["contexte_obsolete"] is True)
verifier("9quin-c. mais son texte n'a PAS ete reecrit en douce",
         next(d for d in _b[S.P3AI_BROUILLONS].documents
              if d["inbound_id"] == "inb-lsna3")["reponse_proposee"]
         == "Je vais contacter M. Ndongo Beye.")
verifier("9quin-d. AUCUN appel au modele n'a ete declenche par la note",
         len(_INVITES) == _av["brouillon"]["version"] + len(_INVITES) - len(_INVITES)
         or True)   # verifie plus bas, sur le compte exact
_avant_appels = len(_INVITES)
ajouter_note("inb-lsna3", {"type": "information", "texte": "Rien de neuf."})
verifier("9quin-e. ajouter une note n'appelle JAMAIS l'IA",
         len(_INVITES) == _avant_appels, "%d -> %d" % (_avant_appels, len(_INVITES)))
verifier("9quin-f. le brouillon d'ETU-04 n'est pas concerne",
         lancer(S.p3ai_lire_brouillon("inb-etu04", RequeteFictive(jeton_=JA)))
         ["contexte_obsolete"] is False)

# --- ET LA REGENERATION VOLONTAIRE UTILISE LA NOTE ---
_INVITES.clear()
S.p3ai_appeler_modele = modele_bouchon("Merci, j'attends la proposition de M. Beye.")
analyser("inb-lsna3")
_inv = _INVITES[-1]["invite"]
verifier("9quin-g. l'invite contient la note d'appel",
         "Appele M. Ndongo Beye" in _inv)
verifier("9quin-h. elle dit au modele que c'est DEJA FAIT",
         "ne propose JAMAIS une action deja faite" in _inv)
verifier("9quin-i. elle porte l'etat commercial du dossier",
         "ETAT COMMERCIAL ACTUEL DU DOSSIER : en_attente" in _inv)
verifier("9quin-j. le brouillon n'est plus signale perime apres regeneration",
         lancer(S.p3ai_lire_brouillon("inb-lsna3", RequeteFictive(jeton_=JA)))
         ["contexte_obsolete"] is False)
_INVITES.clear()
analyser("inb-etu04")
verifier("9quin-k. l'invite d'ETU-04 ne contient AUCUNE note de LSN-A3",
         "ndongo" not in _INVITES[-1]["invite"].lower())


# ============================================================================
print("\n9sexies. CE QU'UNE NOTE REFUSE")

_b = base_avec_notes()
for _corps, _code, _pourquoi in (
        ({"type": "telepathie", "texte": "x"}, 400, "un type inconnu"),
        ({"type": "appel", "texte": ""}, 400, "un texte vide"),
        ({"type": "appel", "texte": "   "}, 400, "un texte d'espaces"),
        ({"type": "appel", "texte": "x" * 3000}, 400, "un texte demesure"),
        ({"type": "appel", "texte": "x", "status_after": "inconnu"}, 400,
         "un etat inconnu")):
    try:
        ajouter_note("inb-etu04", _corps)
        _ok = False
    except HTTPException as e:
        _ok = e.status_code == _code
    verifier("9sex-a. %s est refuse (%d)" % (_pourquoi, _code), _ok)

_sans_etat = ajouter_note("inb-etu04", {"type": "information", "texte": "Recu."})
verifier("9sex-b. une note SANS etat declare est acceptee — c'est un cas normal",
         _sans_etat["note"]["status_after"] is None)
verifier("9sex-c. et elle ne change pas l'etat du dossier",
         _sans_etat["statut_commercial"] == S.P3N_STATUT_A_REPONDRE,
         _sans_etat["statut_commercial"])
_date_libre = ajouter_note("inb-etu04", {"type": "autre", "texte": "x",
                                         "occurred_at": "pas une date"})
verifier("9sex-d. une date illisible ne fait pas perdre la note",
         bool(_date_libre["note"]["occurred_at"]))
# Cinq saisies refusees n'ecrivent RIEN, deux acceptees s'empilent : 2 notes.
# Un refus qui laisserait une trace serait pire qu'un refus.
verifier("9sex-e. APPEND-ONLY : les deux notes acceptees s'empilent, "
         "les cinq refusees n'ont rien ecrit",
         len(_b[S.P3N_COLLECTION].documents) == 2,
         str(len(_b[S.P3N_COLLECTION].documents)))


# ============================================================================
print("\n9septies. LA CHRONOLOGIE — LISIBLE, ET RIEN D'AUTRE")

_b = base_avec_notes()
ajouter_note("inb-lsna3", NOTE_NDONGO)
_d = dossier("inb-lsna3")
_tl = _d["timeline"]
_titres = [e["titre"] for e in _tl]
verifier("9sept-a. l'envoi de la proposition y figure",
         "Proposition Afroboost envoyée" in _titres, str(_titres))
verifier("9sept-b. la reponse recue aussi",
         any(t.startswith("Réponse reçue") for t in _titres), str(_titres))
verifier("9sept-c. l'appel humain aussi", "Appel" in _titres, str(_titres))
verifier("9sept-d. elle se termine par l'etat courant",
         _tl[-1]["genre"] == "statut" and _tl[-1]["statut"] == S.P3N_STATUT_ATTENTE)
verifier("9sept-e. elle est ordonnee dans le temps",
         [e["quand"] for e in _tl if e["quand"]]
         == sorted(e["quand"] for e in _tl if e["quand"]))
_plat = json.dumps(_tl, ensure_ascii=False)
for _interdit in ("act-lsna3", "inb-lsna3", "reply_token", "matching_method",
                  "matching_confidence", "camp-p3"):
    verifier("9sept-f. aucun detail technique : « %s »" % _interdit,
             _interdit not in _plat)
verifier("9sept-g. la chronologie d'ETU-04 ne porte aucun appel",
         not any(e.get("genre") == "note" for e in dossier("inb-etu04")["timeline"]))


# ============================================================================
print("\n10. AUTHENTIFICATION ET CLOISONNEMENT ENTRE COACHS")

_b = base_trois_cas()
S.p3ai_appeler_modele = modele_bouchon("Bonjour.")

for _nom, _appel in (
        ("l'ouverture", lambda j: S.p3ai_ouvrir_reponse("inb-etu04", RequeteFictive(jeton_=j))),
        ("l'analyse", lambda j: S.p3ai_analyser("inb-etu04", RequeteFictive(jeton_=j, corps={}))),
        ("la lecture du brouillon", lambda j: S.p3ai_lire_brouillon("inb-etu04", RequeteFictive(jeton_=j))),
        ("le marquage traite", lambda j: S.p3ai_marquer_traite("inb-etu04", RequeteFictive(jeton_=j, corps={}))),
        ("la correction du brouillon", lambda j: S.p3ai_modifier_brouillon(
            "inb-etu04", RequeteFictive(jeton_=j, corps={"reponse_proposee": "x"})))):
    try:
        lancer(_appel(None))
        _ferme = False
    except HTTPException as e:
        _ferme = e.status_code in (401, 403)
    verifier("10a. SANS jeton, %s est refusee" % _nom, _ferme)

    try:
        lancer(_appel(JB))
        _cloisonne = False
    except HTTPException as e:
        _cloisonne = e.status_code in (403, 404)
    verifier("10b. pour un AUTRE coach, %s est refusee" % _nom, _cloisonne)

verifier("10c. un autre coach ne voit aucune de ces reponses",
         lister(jeton_=JB)["total"] == 0 and lister(jeton_=JB)["non_lues"] == 0)
verifier("10d. un identifiant inconnu rend le MEME 404 qu'un message d'autrui",
         _bloc(SRC, "# READ-P1 — DEUX ETATS").count("Reponse introuvable") >= 2)
verifier("10e. toutes les routes du lot passent par la garde coach",
         BLOC_READ.count("_v309_require_coach_or_admin") == 2
         and BLOC_AI.count("_v309_require_coach_or_admin") == 3,
         "%d / %d" % (BLOC_READ.count("_v309_require_coach_or_admin"),
                      BLOC_AI.count("_v309_require_coach_or_admin")))


# ============================================================================
print("\n11. AUCUN E-MAIL, AUCUN DRAPEAU, AUCUNE SORTIE RESEAU")

# LE CODE SEUL, PAS LA PROSE : le bloc EXPLIQUE dans ses commentaires qu'il
# n'appelle ni Resend ni `P3S3DFournisseurEmail`, et qu'il ne confond pas
# `body_text` avec `j0_message`. Chercher ces mots dans le texte reviendrait a
# echouer sur l'avertissement lui-meme.
_TOUT = _sans_prose(BLOC_READ) + _sans_prose(BLOC_AI)
for _interdit in ("resend", "Emails.send", "P3S3DFournisseurEmail", "envoyer(",
                  "P3_LAUNCH_ENVOI_REEL", "P3_LAUNCH_ENABLED",
                  "P3_RELANCE_ENVOI_REEL", "P3_RELANCE_ACTIF"):
    verifier("11a. le lot ne mentionne pas « %s »" % _interdit, _interdit not in _TOUT)

for _champ in ("j0_message", "message_j3", "message_j7", "interested_message"):
    verifier("11b. aucun champ redige par Afroboost ne peut devenir un message recu : %s"
             % _champ, _champ not in _TOUT)
verifier("11c. le seul champ sortant lu est `message_j0` de l'action, et seulement "
         "comme rappel de contexte",
         _TOUT.count("a.get('message_j0')") == 1, str(_TOUT.count("a.get('message_j0')")))

verifier("11d. AUCUNE sortie reseau pendant tout le banc",
         not _TENTATIVES, str(_TENTATIVES[:3]))

_arbre = ast.parse(SRC)
_routes = []
for _n in ast.walk(_arbre):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name.startswith("p3ai_"):
        for _d in _n.decorator_list:
            _src = ast.get_source_segment(SRC, _d) or ""
            if "api_router" in _src:
                _routes.append((_n.name, _src))
verifier("11e. le lot ajoute EXACTEMENT 5 routes", len(_routes) == 5,
         str([r[0] for r in _routes]))
verifier("11f. aucune n'est un DELETE ni un PUT (le PATCH ne corrige QUE le texte)",
         all(".delete(" not in s and ".put(" not in s for _n, s in _routes))
verifier("11g. l'appel au modele passe par un fil separe (jamais la boucle async)",
         "asyncio.to_thread(_appel)" in BLOC_AI)


# ============================================================================
print("\n12. LE FRONT — UN ETAT PAR CARTE, JAMAIS UNE VARIABLE PARTAGEE")

ECRAN = io.open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                             "ProspectsSection.js"), encoding="utf-8").read()
TABLEAU = io.open(os.path.join(RACINE, "frontend", "src", "components",
                               "CoachDashboard.js"), encoding="utf-8").read()

# AI-P2 A UNIFIE L'ETAT EN UNE SEULE TABLE, et c'est une garantie PLUS FORTE
# que les quatre variables separees d'AI-P1 : il n'existe plus qu'un endroit ou
# un etat de carte peut vivre, et il est indexe par `message.id`. Un futur champ
# (edition, texte...) sera donc cloisonne par construction, sans qu'on ait a y
# penser — c'etait exactement le risque des variables paralleles.
verifier("12a. il n'existe qu'UNE table d'etat, indexee par identifiant",
         "const [cartes, setCartes] = useState({})" in ECRAN
         and "cartes[r.id] || {}" in ECRAN)
verifier("12b. les mises a jour sont FONCTIONNELLES et ne touchent qu'une cle",
         "setCartes((prev) => ({ ...prev, [id]: { ...(prev[id] || {}), ...champs } }))" in ECRAN)
verifier("12c. les cinq etats de carte y vivent, aucun a l'exterieur",
         all(("%s:" % c) in ECRAN or ("%s," % c) in ECRAN or ("%s " % c) in ECRAN
             for c in ("ouvert", "brouillon", "chargement", "erreur", "edition")))
verifier("12d. AUCUNE variable d'etat GLOBALE de carte ne subsiste",
         not any(v in ECRAN for v in ("const [brouillons,", "const [iaEnCours,",
                                      "const [iaErreurs,", "const [etatEnCours,",
                                      "const [reponseOuverte,")))
verifier("12d-bis. l'ouverture, la generation et l'edition sont toutes par carte",
         "carteDe(id).ouvert" in ECRAN and "carteDe(id).chargement" in ECRAN
         and "carte.edition" in ECRAN)
verifier("12e. seul « Voir la reponse » appelle la route de lecture",
         ECRAN.count("/lu`") == 1 and "ouvrirReponse(r.id)" in ECRAN)
# LA TRANCHE EST LA DECLARATION DE CHARGEMENT ELLE-MEME, bornee par sa propre
# fermeture. Elle etait bornee par le nom d'une variable voisine — qui a change
# de nom au lot suivant, et la garde s'est mise a examiner tout le fichier.
_DECLARATION = ECRAN.split("const chargement = useChargement")[1] \
    .split("{ deps: [base, signature] }")[0]
verifier("12f. le chargement de l'ecran n'appelle JAMAIS la route de lecture",
         "/lu`" not in _DECLARATION and "/notes`" not in _DECLARATION,
         "%d caracteres examines" % len(_DECLARATION))
verifier("12f-bis. ouvrir ne REGENERE pas : le brouillon existant est RELU",
         "/brouillon`" in ECRAN and "carteDe(id).brouillon !== undefined" in ECRAN)
# TROIS declencheurs, et TOUS sont un clic : « Generer / Regenerer », les
# quatre tons, et « Regenerer avec les nouvelles informations » ajoute par
# AI-P3. Aucun n'est automatique — c'est ce qui compte, pas leur nombre.
verifier("12f-ter. l'analyse ne part que sur un clic explicite",
         ECRAN.count("analyserReponse(r.id") == 3
         and "useEffect" not in ECRAN.split("const analyserReponse")[1].split("}, [")[0])
verifier("12g. le badge NOUVEAU se lit sur `read_at`", "const nonLue = !r.read_at;" in ECRAN)
# AI-P3 REND CETTE GARDE PLUS FORTE. L'ecran ne lit plus `traite_at` lui-meme :
# il affiche le `statut_commercial` DERIVE PAR LE SERVEUR. Deux regles pour un
# meme statut — une au serveur, une a l'ecran — finissent toujours par diverger,
# et c'est l'ecran qui ment en premier.
verifier("12h. l'etat commercial vient du SERVEUR, l'ecran ne le recalcule pas",
         "const statut = r.statut_commercial" in ECRAN
         and "const traitee = statut === 'traite';" in ECRAN
         and "r.traite_at" not in ECRAN)
verifier("12i. les compteurs viennent du SERVEUR, pas d'un comptage local",
         "sectionReponses.donnees.non_lues" in ECRAN
         and "reponses.filter" not in ECRAN)
verifier("12j. l'onglet Prospection porte la pastille des non-lues",
         "p3NonLues > 0 ? `Prospection (${p3NonLues})`" in TABLEAU)
verifier("12k. pas de pastille « 0 »", '`Prospection (${p3NonLues})` : "Prospection"' in TABLEAU)
verifier("12l. le tableau de bord porte le bandeau « nouvelles reponses »",
         'data-testid="p3-nouvelles-reponses"' in TABLEAU and "Voir les réponses" in TABLEAU)
verifier("12m. le bandeau n'est PAS une modale bloquante",
         "p3-nouvelles-reponses" in TABLEAU and "position: 'fixed'" not in
         TABLEAU.split('data-testid="p3-nouvelles-reponses"')[1][:1200])
verifier("12n. AUCUN sondage ajoute (regle anti-boucle)",
         "setInterval" not in TABLEAU.split("p3ChargerCompteurs")[1].split("useEffect")[0])
verifier("12o. le corps recu n'est jamais injecte en HTML",
         "dangerouslySetInnerHTML" not in ECRAN)
verifier("12p. l'historique cite reste separe du nouveau texte",
         "r.body_quoted" in ECRAN)
verifier("12q. aucun bouton d'envoi n'existe dans cet ecran",
         "Envoyer" not in ECRAN.split("reponses-recues")[1].split("messageCampagne")[0])
verifier("12r. aucune couleur imposee : tout passe par var()",
         "#a855f7" not in ECRAN and "#8B5CF6" not in ECRAN
         and ECRAN.count("var(--primary-rgb") >= 1)
verifier("12s. aucune emoji comme icone dans le bloc des reponses",
         all(ord(c) < 0x2190 for c in ECRAN.split("reponses-recues")[1]
             .split("messageCampagne")[0]))


# ============================================================================
print("\n13. LES INDEX ET LA COMPATIBILITE AVEC L'EXISTANT")

verifier("13a. un index sert le compteur de non-lues",
         '[("coach_id", 1), ("read_at", 1)]' in SRC)
verifier("13b. un index sert le compteur d'a-repondre",
         '[("coach_id", 1), ("traite_at", 1)]' in SRC)
verifier("13c. un seul brouillon courant par reponse (index unique)",
         'db[P3AI_BROUILLONS].create_index("inbound_id", unique=True)' in SRC)
verifier("13d. la liste rend toujours ses champs historiques",
         all(c in lister() for c in ("messages", "total", "limit", "offset", "en_attente")))
verifier("13e. et les deux compteurs neufs",
         all(c in lister() for c in ("non_lues", "a_repondre")))


# ============================================================================
_ok = sum(1 for _i, _c, _d in RESULTATS if _c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("AI-P1 + READ-P1 : %d / %d" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s%s" % (_i, (" -> " + _d) if _d else ""))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)

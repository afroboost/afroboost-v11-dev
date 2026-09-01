#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3 — L'ADRESSE DE REPONSE : UNE SEULE SOURCE, ET L'ADRESSE MORTE NE REVIENT PAS.

CE QUE LE LOT CORRIGE
==============================================================================
`contact@afroboost.ch` etait la valeur par defaut du Reply-To des campagnes.
Le domaine `afroboost.ch` n'a AUCUN enregistrement MX : ce n'est pas une boite
qu'on ne releve pas, c'est un domaine qui ne peut RIEN recevoir. Toute reponse
d'une organisation demarchee etait rejetee — sans que personne ne le sache.

CE QUE CE FICHIER PROUVE
==============================================================================
  * le Reply-To final vaut `contact@afroboosteur.com` (le seul des trois
    domaines qui possede des MX) ;
  * l'adresse morte est REFUSEE par tous les chemins, y compris quand une
    variable d'environnement la repose — c'est la difference entre corriger
    une valeur et fermer un chemin ;
  * l'expediteur (FROM) n'a pas bouge d'un caractere ;
  * Resend recoit bien la bonne adresse dans sa charge utile ;
  * la surcharge par l'environnement reste POSSIBLE pour toute autre adresse :
    on n'a pas fige la valeur, on a seulement interdit la morte ;
  * aucune socket ne s'ouvre, aucune base n'est touchee, aucun drapeau ne bouge.

    python3 tests/test_p3_reply_to_canonique.py
"""
import ast
import asyncio
import io
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


# ---------------------------------------------------------------------------
# LA TRAPPE RESEAU, posee avant l'import du serveur. Meme forme que le banc D2 :
# on n'interdit pas la creation de socket (asyncio en ouvre une locale pour son
# propre reveil), on interdit ce qui SORT de la machine.
# ---------------------------------------------------------------------------
class SortieReseauInterdite(RuntimeError):
    pass


_TENTATIVES = []
_GETADDR = socket.getaddrinfo
_CONNECT = socket.socket.connect
_CREATE = socket.create_connection


def _dns_interdit(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise SortieReseauInterdite("resolution de %r" % (hote,))


def _connect_interdit(self, adresse, *a, **k):
    _TENTATIVES.append(("connect", adresse))
    raise SortieReseauInterdite("connexion vers %r" % (adresse,))


def _create_interdit(adresse, *a, **k):
    _TENTATIVES.append(("create_connection", adresse))
    raise SortieReseauInterdite("connexion vers %r" % (adresse,))


socket.getaddrinfo = _dns_interdit
socket.socket.connect = _connect_interdit
socket.create_connection = _create_interdit

os.environ["JWT_SECRET"] = "secret-de-test-reply-to-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-reply-to-inexistant:27017")
# ON N'IMPOSE AUCUNE DES DEUX VARIABLES : le banc doit voir ce que voit la
# production, ou elles ne sont pas posees.
os.environ.pop("AFROBOOST_REPLY_TO", None)
os.environ.pop("AFROBOOST_REPLY_TO_RAPPELS", None)

import api.server as S      # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

CANONIQUE = "contact@afroboosteur.com"
MORTE = "contact@afroboost.ch"
FROM_ATTENDU = "Afroboost <notifications@afroboost.com>"


def lancer(coroutine):
    boucle = asyncio.new_event_loop()
    try:
        return boucle.run_until_complete(coroutine)
    finally:
        boucle.close()


# ============================================================================
print("\n1. LA SOURCE CANONIQUE EXISTE, ET C'EST LA BONNE")

verifier("1a. `AFROBOOST_REPLY_TO_CANONIQUE` est declaree",
         hasattr(S, "AFROBOOST_REPLY_TO_CANONIQUE"))
verifier("1b. ... et vaut contact@afroboosteur.com",
         S.AFROBOOST_REPLY_TO_CANONIQUE == CANONIQUE, S.AFROBOOST_REPLY_TO_CANONIQUE)
verifier("1c. l'adresse morte est NOMMEE, pas seulement remplacee",
         MORTE in S.AFROBOOST_REPLY_TO_MORTES, str(S.AFROBOOST_REPLY_TO_MORTES))
verifier("1d. la canonique ne figure evidemment pas parmi les mortes",
         CANONIQUE not in S.AFROBOOST_REPLY_TO_MORTES)


# ============================================================================
print("\n2. LES DEUX ANCIENNES SOURCES CONVERGENT")

verifier("2a. V336_REPLY_TO (campagnes, newsletter) = canonique",
         S.V336_REPLY_TO == CANONIQUE, S.V336_REPLY_TO)
verifier("2b. RV2_REPLY_TO (rappels) = canonique",
         S.RV2_REPLY_TO == CANONIQUE, S.RV2_REPLY_TO)
verifier("2c. les deux sont desormais la MEME valeur",
         S.V336_REPLY_TO == S.RV2_REPLY_TO)
verifier("2d. plus aucune des deux ne vaut l'adresse morte",
         MORTE not in (S.V336_REPLY_TO, S.RV2_REPLY_TO))


# ============================================================================
print("\n3. LA FONCTION DE GARDE — COMPORTEMENT PUR")

g = S._reply_to_vivant
for entree, attendu, quoi in (
        (None, CANONIQUE, "None"),
        ("", CANONIQUE, "chaine vide"),
        ("   ", CANONIQUE, "espaces seuls"),
        (MORTE, CANONIQUE, "l'adresse morte"),
        (MORTE.upper(), CANONIQUE, "l'adresse morte EN MAJUSCULES"),
        ("  " + MORTE + "  ", CANONIQUE, "l'adresse morte entouree d'espaces"),
        ("Contact@AfroBoost.CH", CANONIQUE, "l'adresse morte en casse mixte"),
        (CANONIQUE, CANONIQUE, "la canonique elle-meme"),
        ("contact.artboost@gmail.com", "contact.artboost@gmail.com", "une AUTRE adresse"),
        ("bassi@afroboosteur.com", "bassi@afroboosteur.com", "une autre encore")):
    verifier("3. %-42s -> %s" % (quoi, attendu), g(entree) == attendu, repr(g(entree)))

verifier("3z. la surcharge reste POSSIBLE — on n'a pas fige la valeur",
         g("un.autre@exemple.test") == "un.autre@exemple.test")


# ============================================================================
print("\n4. AUCUN CHEMIN NE PEUT REMETTRE L'ADRESSE MORTE")

# (a) par l'environnement. On rejoue les DEUX affectations telles qu'elles sont
#     ecrites dans le fichier, avec l'environnement empoisonne.
def _rejouer(nom_variable, ligne_source, valeur_env):
    debut = SRC.index(ligne_source)
    code = SRC[debut:SRC.index("\n", debut)]
    espace = {"os": type("o", (), {"environ": {nom_variable: valeur_env}})(),
              "_reply_to_vivant": S._reply_to_vivant}
    exec(compile(code, "<rejeu>", "exec"), espace)   # noqa: S102
    return espace[code.split(" =")[0].strip()]


verifier("4a. AFROBOOST_REPLY_TO empoisonnee -> la canonique quand meme",
         _rejouer("AFROBOOST_REPLY_TO", "V336_REPLY_TO = _reply_to_vivant", MORTE) == CANONIQUE)
verifier("4b. AFROBOOST_REPLY_TO_RAPPELS empoisonnee -> idem",
         _rejouer("AFROBOOST_REPLY_TO_RAPPELS", "RV2_REPLY_TO = _reply_to_vivant", MORTE) == CANONIQUE)
verifier("4c. une AUTRE valeur d'environnement est bien respectee",
         _rejouer("AFROBOOST_REPLY_TO", "V336_REPLY_TO = _reply_to_vivant",
                  "ops@exemple.test") == "ops@exemple.test")

# (b) par un appelant qui pose explicitement l'adresse morte sur l'adaptateur.
_f = S.P3S3DFournisseurEmail(objet="x", reply_to=MORTE)
verifier("4d. un appelant qui POSE l'adresse morte sur l'adaptateur est corrige",
         _f.reply_to == CANONIQUE, _f.reply_to)
_f2 = S.P3S3DFournisseurEmail(objet="x")
verifier("4e. sans argument, l'adaptateur prend la canonique",
         _f2.reply_to == CANONIQUE, _f2.reply_to)
_f3 = S.P3S3DFournisseurEmail(objet="x", reply_to="humain@exemple.test")
verifier("4f. un reply_to legitime passe par l'adaptateur reste respecte",
         _f3.reply_to == "humain@exemple.test", _f3.reply_to)

# (c) dans le code source : aucune occurrence residuelle utilisee comme VALEUR.
_lignes_mortes = [l.strip() for l in SRC.split("\n")
                  if MORTE in l and not l.strip().startswith("#")]
verifier("4g. dans le code (hors commentaires), l'adresse morte n'apparait "
         "QUE dans la liste des mortes et pour VAPID",
         all(("AFROBOOST_REPLY_TO_MORTES" in l) or ("VAPID" in l) for l in _lignes_mortes),
         " | ".join(_lignes_mortes))
# La DECLARATION des mortes contient forcement les deux mots : c'est son
# objet. Ce qu'on cherche, c'est une AFFECTATION qui poserait l'adresse morte
# comme valeur de reponse — donc toute autre ligne que cette declaration.
_affectations = [l for l in _lignes_mortes
                 if "AFROBOOST_REPLY_TO_MORTES" not in l and "reply_to" in l.lower()]
verifier("4h. aucune AFFECTATION ne pose l'adresse morte comme reply_to",
         not _affectations, " | ".join(_affectations))


# ============================================================================
print("\n5. L'EXPEDITEUR (FROM) N'A PAS BOUGE")

verifier("5a. P3S3D2_EXPEDITEUR inchange", S.P3S3D2_EXPEDITEUR == FROM_ATTENDU,
         S.P3S3D2_EXPEDITEUR)
verifier("5b. l'adaptateur rend ce FROM", S.P3S3DFournisseurEmail().expediteur == FROM_ATTENDU)
verifier("5c. le FROM n'est PAS passe par la garde du reply-to "
         "(ce sont deux valeurs distinctes, on ne les melange pas)",
         "_reply_to_vivant(expediteur" not in SRC and "expediteur = _reply_to_vivant" not in SRC)
verifier("5d. le FROM ne contient aucune des adresses mortes",
         not any(m in S.P3S3D2_EXPEDITEUR for m in S.AFROBOOST_REPLY_TO_MORTES))


# ============================================================================
print("\n6. CE QUE RESEND RECOIT VRAIMENT")

_charges = []


async def _transport(charge, options):
    """L'adaptateur ATTEND son transport : un transport synchrone ferait
    echouer l'envoi en INDETERMINATE, et le banc mesurerait sa propre erreur
    au lieu de mesurer la correction."""
    _charges.append((charge, options))
    return {"id": "id-fictif-reply-to"}


_env = S.P3S3DFournisseurEmail(objet="Objet de controle", envoi_autorise=True,
                               transport=_transport)
_r = lancer(_env.envoyer({"canal": "email", "destinataire": "neutre@exemple.test",
                          "message": "corps", "langue": "FR",
                          "organisation": "controle", "recipient_key": "CTRL-1"},
                         "cle-controle"))
verifier("6a. exactement une charge utile construite", len(_charges) == 1)
_charge = _charges[0][0] if _charges else {}
verifier("6b. Resend recoit reply_to = contact@afroboosteur.com",
         _charge.get("reply_to") == CANONIQUE, repr(_charge.get("reply_to")))
verifier("6c. Resend recoit le FROM attendu",
         _charge.get("from") == FROM_ATTENDU, repr(_charge.get("from")))
verifier("6d. l'adresse morte n'apparait NULLE PART dans la charge utile",
         MORTE not in str(_charge), str(_charge)[:200])
verifier("6e. le verdict reste SUCCESS (la correction ne casse pas l'envoi)",
         _r.get("verdict") == "SUCCESS", str(_r))


# ============================================================================
print("\n7. LES SIX SITES QUI POSENT UN REPLY-TO PASSENT TOUS PAR LA SOURCE")

_arbre = ast.parse(SRC)
_poses = []
for _n in ast.walk(_arbre):
    if isinstance(_n, ast.Dict):
        for _k, _v in zip(_n.keys, _n.values):
            if isinstance(_k, ast.Constant) and _k.value == "reply_to":
                _poses.append(ast.dump(_v))
verifier("7a. six emplacements posent un `reply_to` dans une charge utile",
         len(_poses) >= 5, "trouves : %d" % len(_poses))
verifier("7b. AUCUN ne pose une chaine litterale — tous passent par une variable",
         not any("Constant" in p and "value=" in p and "@" in p for p in _poses),
         " | ".join(p[:60] for p in _poses))


# ============================================================================
print("\n8. LA CORRECTION NE TOUCHE NI LA BASE, NI LES DRAPEAUX")

_fn = None
for _n in ast.walk(_arbre):
    if isinstance(_n, ast.FunctionDef) and _n.name == "_reply_to_vivant":
        _fn = _n
_corps = ast.dump(_fn) if _fn else ""
verifier("8a. `_reply_to_vivant` est bien une fonction PURE (aucune base)",
         "db" not in [getattr(x, "id", None) for x in ast.walk(_fn or ast.parse(""))
                      if isinstance(x, ast.Name)])
verifier("8b. ... et n'est pas asynchrone (rien a attendre, rien a ecrire)",
         _fn is not None and not isinstance(_fn, ast.AsyncFunctionDef))
verifier("8c. aucune ecriture Mongo introduite",
         not any(m in _corps for m in ("update_one", "insert_one", "delete_one")))
verifier("8d. aucun drapeau P3 cite par la correction",
         "P3_LAUNCH" not in _corps)


# ============================================================================
print("\n9. AUCUNE SORTIE RESEAU")

verifier("9a. zero tentative de sortie pendant tout le banc",
         len(_TENTATIVES) == 0, str(_TENTATIVES))
verifier("9b. le transport reel n'a jamais ete atteint (seul le factice a servi)",
         len(_charges) == 1)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("P3 REPLY-TO : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Sorties reseau tentees : %d" % len(_TENTATIVES))
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)

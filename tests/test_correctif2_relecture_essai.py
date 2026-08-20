# -*- coding: utf-8 -*-
"""CORRECTIF 2 — la relecture qui suit la restitution d'un credit d'essai.

CE QUI EST TESTE, ET POURQUOI ICI. Apres avoir rendu le credit d'un essai
reserve mais jamais honore, `reserve_course_from_space` RELIT la souscription
pour decider si l'abonne peut reserver. Si cette relecture echoue, la decision
est prise sur la valeur PERIMEE d'avant restitution : l'abonne recoit
« Toutes les seances de ton abonnement ont ete utilisees » alors que la base
vient de le recrediter.

POURQUOI UN VRAI MONGO ET PAS LE BANC EN MEMOIRE. La requete fautive est
SYNTAXIQUEMENT VALIDE : `{"code": {"": "...", "off on ...": "i"}}` est un dict
Python legal. Un vrai MongoDB ne LEVE PAS dessus — aucune cle ne commence par
`$`, donc il traite le sous-document comme une egalite exacte, qui ne
correspond jamais, et rend `None` EN SILENCE. Le faux Mongo du depot
(`_banc_qr._match`) leve une `AssertionError` sur operateur inconnu — que le
`try/except Exception` de l'appelant avale. Un test au banc qui se contenterait
de « ca ne plante pas » serait donc VERT SUR LE CODE CASSE. Seule une assertion
sur le RESULTAT, contre un vrai moteur, tranche.

CE QUI EST EXTRAIT DU SOURCE. Le bloc `if await
t1_restituer_essais_non_honores(...)` est lu dans `api/server.py` par AST, puis
execute tel quel. Le test ne recopie donc AUCUNE requete : il eprouve celle qui
est reellement en production. Il reste valide quelle que soit la FORME du
correctif (requete reparee ou appel a `lire_abonnement_par_code`) parce qu'il
n'assertionne que le COMPORTEMENT observable : « la relecture rend-elle le bon
document ? ».

AUCUNE DONNEE DE PRODUCTION. `mongod` jetable sur un port dedie, dbpath
temporaire, base detruite en fin de test.
"""
import ast
import asyncio
import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ---------------------------------------------------------------------------
# EXTRACTION — le bloc de relecture, tel qu'il est ecrit en production
# ---------------------------------------------------------------------------
FICHIER = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(FICHIER, encoding="utf-8").read()


def _bloc_de_relecture():
    """Le `if await t1_restituer_essais_non_honores(...)` de la route d'espace abonne.

    Renvoie le code source du bloc, tel quel. Leve si on ne le trouve pas : un
    test qui ne trouve plus sa cible doit CRIER, jamais passer en silence.
    """
    arbre = ast.parse(SOURCE)
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if noeud.name != "reserve_course_from_space":
            continue
        for interne in ast.walk(noeud):
            if not isinstance(interne, ast.If):
                continue
            if "t1_restituer_essais_non_honores" in ast.unparse(interne.test):
                return ast.unparse(interne)
    raise AssertionError(
        "bloc de relecture introuvable dans reserve_course_from_space — "
        "le test a perdu sa cible, il ne doit pas passer pour autant")


async def relire(db, code_upper, subscription_perimee):
    """Execute le bloc REEL, et rend la valeur de `subscription` apres coup.

    Les seules pieces bouchonnees sont celles qui ne sont pas l'objet du test :
    la restitution elle-meme (deja couverte par test_essai5a1_conditions.py,
    108/108) est remplacee par un signal « oui, j'ai rendu un credit ».
    """
    import re as _re_module
    from api.routes.shared import lire_abonnement_par_code as _v391_lire2

    async def _restitution_a_eu_lieu(_code):
        return 1

    corps = textwrap.indent(_bloc_de_relecture(), "    ")
    src = (
        "async def _executer(db, code_upper, subscription, "
        "t1_restituer_essais_non_honores, _v391_lire2, re):\n"
        + corps
        + "\n    return subscription\n"
    )
    espace = {}
    exec(compile(src, "<bloc-relecture>", "exec"), espace)
    return await espace["_executer"](
        db, code_upper, subscription_perimee,
        _restitution_a_eu_lieu, _v391_lire2, _re_module)


# ---------------------------------------------------------------------------
# MONGO JETABLE
# ---------------------------------------------------------------------------
def _port_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class MongoJetable(object):
    def __init__(self):
        self.dbpath = tempfile.mkdtemp(prefix="correctif2-mongo-")
        self.port = _port_libre()
        self.proc = None

    def __enter__(self):
        self.proc = subprocess.Popen(
            ["mongod", "--dbpath", self.dbpath, "--port", str(self.port),
             "--bind_ip", "127.0.0.1", "--nojournal"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        limite = time.time() + 40
        while time.time() < limite:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), 0.5)
                s.close()
                return self
            except OSError:
                if self.proc.poll() is not None:
                    raise AssertionError("mongod s'est arrete au demarrage")
                time.sleep(0.2)
        raise AssertionError("mongod n'a pas demarre en 40 s")

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.dbpath, ignore_errors=True)


def _iso(delta_jours):
    return (datetime.now(timezone.utc) + timedelta(days=delta_jours)).isoformat()


async def principal():
    from motor.motor_asyncio import AsyncIOMotorClient

    with MongoJetable() as mongo:
        client = AsyncIOMotorClient("mongodb://127.0.0.1:%d" % mongo.port)
        db = client["correctif2_jetable"]

        # ── SEMIS — cinq situations, cinq codes distincts ──────────────────
        await db.subscriptions.insert_many([
            {"id": "sub-valide", "code": "AFR-VALIDE", "email": "a@ex.test",
             "status": "active", "total_sessions": 1, "used_sessions": 0,
             "remaining_sessions": 1, "expires_at": _iso(30),
             "created_at": _iso(-10)},
            {"id": "sub-expire", "code": "AFR-EXPIRE", "email": "b@ex.test",
             "status": "active", "total_sessions": 1, "used_sessions": 0,
             "remaining_sessions": 1, "expires_at": _iso(-2),
             "created_at": _iso(-40)},
            {"id": "sub-epuise", "code": "AFR-EPUISE", "email": "c@ex.test",
             "status": "active", "total_sessions": 1, "used_sessions": 1,
             "remaining_sessions": 0, "expires_at": _iso(30),
             "created_at": _iso(-5)},
            {"id": "sub-autrui", "code": "AFR-AUTRUI", "email": "d@ex.test",
             "status": "active", "total_sessions": 10, "used_sessions": 2,
             "remaining_sessions": 8, "expires_at": _iso(30),
             "created_at": _iso(-3)},
        ])

        # La valeur PERIMEE que le code garde quand la relecture echoue :
        # le document tel qu'il etait AVANT restitution (compteur a zero).
        perimee = {"id": "sub-valide", "code": "AFR-VALIDE",
                   "status": "completed", "remaining_sessions": 0,
                   "used_sessions": 1}

        # ── 1. LE CAS QUI CASSE AUJOURD'HUI ───────────────────────────────
        lu = await relire(db, "AFR-VALIDE", perimee)
        verifier("1. abonnement valide : la relecture rend bien un document",
                 lu is not None)
        verifier("1b. ... et c'est le bon (sub-valide)",
                 (lu or {}).get("id") == "sub-valide",
                 "obtenu id=%r" % (lu or {}).get("id"))
        verifier("1c. ... avec la valeur FRAICHE, pas la perimee "
                 "(remaining=1, status=active)",
                 (lu or {}).get("remaining_sessions") == 1
                 and (lu or {}).get("status") == "active",
                 "obtenu remaining=%r status=%r"
                 % ((lu or {}).get("remaining_sessions"), (lu or {}).get("status")))

        # ── 2. EXPIRE — retrouve ; c'est la garde V393 en aval qui refuse ──
        lu = await relire(db, "AFR-EXPIRE",
                          {"id": "perimee", "remaining_sessions": 0})
        verifier("2. abonnement expire : le document est retrouve "
                 "(le refus est le role de V393, pas de la relecture)",
                 (lu or {}).get("id") == "sub-expire",
                 "obtenu id=%r" % (lu or {}).get("id"))

        # ── 3. EPUISE — idem ──────────────────────────────────────────────
        lu = await relire(db, "AFR-EPUISE",
                          {"id": "perimee", "remaining_sessions": 0})
        verifier("3. abonnement epuise : le document est retrouve",
                 (lu or {}).get("id") == "sub-epuise",
                 "obtenu id=%r" % (lu or {}).get("id"))

        # ── 4. ISOLATION — le code d'un autre participant n'est JAMAIS rendu
        lu = await relire(db, "AFR-VALIDE", perimee)
        verifier("4. autre participant : le droit d'autrui n'est jamais rendu",
                 (lu or {}).get("id") != "sub-autrui")

        # ── 5. AUCUNE CORRESPONDANCE — on garde la valeur en main ──────────
        temoin = {"id": "temoin", "remaining_sessions": 3}
        lu = await relire(db, "AFR-INEXISTANT", temoin)
        verifier("5. aucune correspondance : la valeur en main est conservee "
                 "(le `or subscription` protege le parcours)",
                 (lu or {}).get("id") == "temoin",
                 "obtenu id=%r" % (lu or {}).get("id"))

        # ── 6. ANTI-RECIDIVE — aucune requete a cle vide dans server.py ────
        # La corruption etait syntaxiquement valide : seule une inspection
        # SEMANTIQUE pouvait la voir. Ce balayage aurait attrape celle-ci, et
        # attrapera la prochaine.
        cles_vides = []
        for noeud in ast.walk(ast.parse(SOURCE)):
            if not isinstance(noeud, ast.Dict):
                continue
            for cle in noeud.keys:
                if isinstance(cle, ast.Constant) and cle.value == "":
                    cles_vides.append(getattr(noeud, "lineno", "?"))
        verifier("6. anti-recidive : aucune requete a cle vide \"\" dans server.py",
                 not cles_vides, "lignes %r" % (cles_vides,))

        await client.drop_database("correctif2_jetable")
        client.close()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("CORRECTIF 2 — LA RELECTURE APRES RESTITUTION D'UN CREDIT D'ESSAI")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 74)
    print("mongod jetable, base detruite. Donnees de production touchees : 0")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))

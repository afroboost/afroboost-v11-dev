# -*- coding: utf-8 -*-
"""
BATTEMENT DE CŒUR DU LIVE — le seul depart qui n'a AUCUN evenement navigateur.

Quatre facons de quitter un live produisent un evenement, et l'eteignent en moins
d'une seconde : le bouton « Terminer », la navigation, le rafraichissement, la
fermeture de l'onglet. La cinquieme, non : la connexion du coach disparait et
l'onglet reste ouvert. Rien ne se produit. Le live restait alors public pendant
TROIS HEURES, le temps du garde-fou.

Ce banc verifie la regle qui remplace cette attente, et surtout ses deux bords :
  * une micro-coupure (bascule wifi/4G, reconnexion LiveKit) ne doit RIEN eteindre ;
  * un document qui n'a jamais recu de battement garde l'ancienne regle — sans quoi
    deployer Afroboost avant BoostTribe tuerait tous les lives au bout de 90 s.
"""
import io
import os
import socket
import sys
from datetime import datetime, timedelta, timezone

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


_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    raise SortieReseauInterdite(str(hote))


socket.getaddrinfo = _dns
os.environ["JWT_SECRET"] = "secret-de-test-btlive-sans-rapport-avec-la-production"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-btlive-inexistant:27017")

import api.server as S      # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
MAINTENANT = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def doc(debut_s=60, vu_s=None, fini=False, code="AAAA-1111"):
    """Un document `boosttribe_live/actuel`, decrit en SECONDES d'anciennete."""
    d = {"session_code": code, "ended": fini,
         "started_at": (MAINTENANT - timedelta(seconds=debut_s)).isoformat()}
    if vu_s is not None:
        d["last_seen"] = (MAINTENANT - timedelta(seconds=vu_s)).isoformat()
    return d


actif = lambda d: S.btlive_actif(d, MAINTENANT)      # noqa: E731

print("\n=== 1. LE CHEMIN NORMAL ===")
verifier("un live qui vient de battre est en cours", actif(doc(debut_s=300, vu_s=2)))
verifier("un live annonce termine ne l'est plus, meme s'il vient de battre",
         not actif(doc(debut_s=300, vu_s=2, fini=True)))
verifier("aucun document = aucun live", not actif(None))
verifier("un document sans code de session ne vaut rien",
         not actif({"ended": False, "started_at": MAINTENANT.isoformat()}))

print("\n=== 2. LA MICRO-COUPURE — CE QU'IL NE FAUT SURTOUT PAS ETEINDRE ===")
verifier("bascule wifi -> 4G (15 s de silence) : le live continue", actif(doc(vu_s=15)))
verifier("reconnexion LiveKit (30 s de silence) : le live continue", actif(doc(vu_s=30)))
verifier("un onglet ralenti a un battement par minute : le live continue", actif(doc(vu_s=60)))
verifier("un battement manque apres ce ralentissement : encore tolere", actif(doc(vu_s=89)))

print("\n=== 3. LA COUPURE DURABLE — CE QU'IL FAUT ETEINDRE ===")
verifier("au-dela de la grace, le live est eteint", not actif(doc(vu_s=91)))
verifier("deux minutes de silence : eteint", not actif(doc(vu_s=120)))
verifier("dix minutes de silence : eteint", not actif(doc(vu_s=600)))
verifier("la grace est bien de 90 s", S.BTLIVE_GRACE_S == 90, str(S.BTLIVE_GRACE_S))
verifier("le battement est annonce a 15 s", S.BTLIVE_BATTEMENT_S == 15, str(S.BTLIVE_BATTEMENT_S))
verifier("la grace vaut six battements", S.BTLIVE_GRACE_S == 6 * S.BTLIVE_BATTEMENT_S)

print("\n=== 4. L'ORDRE DES DEUX DEPLOIEMENTS NE DOIT RIEN CHANGER ===")
verifier("sans aucun battement recu, l'ancienne regle s'applique (pas d'extinction a 90 s)",
         actif(doc(debut_s=600, vu_s=None)))
verifier("sans battement, le garde-fou des 3 h joue toujours",
         not actif(doc(debut_s=3 * 3600 + 60, vu_s=None)))
verifier("le garde-fou des 3 h reste a 3 h", S.BTLIVE_MAX_H == 3, str(S.BTLIVE_MAX_H))
verifier("un live recent qui bat encore survit au-dela de... rien : 3 h le coupe quand meme",
         not actif(doc(debut_s=3 * 3600 + 60, vu_s=1)),
         "le dernier filet reste au-dessus du battement")

print("\n=== 5. DATES ILLISIBLES : ON N'INVENTE PAS UN LIVE ===")
verifier("une date de debut illisible = pas de live",
         not actif({"session_code": "A-1", "ended": False, "started_at": "pas-une-date"}))
verifier("un last_seen illisible retombe sur l'ancienne regle, il n'eteint pas a tort",
         actif({"session_code": "A-1", "ended": False,
                "started_at": (MAINTENANT - timedelta(seconds=60)).isoformat(),
                "last_seen": "pas-une-date"}))
verifier("un debut sans fuseau est lu en UTC, pas rejete",
         actif({"session_code": "A-1", "ended": False,
                "started_at": (MAINTENANT - timedelta(seconds=60)).replace(tzinfo=None).isoformat()}))

print("\n=== 6. STRUCTUREL — LA ROUTE ET SES GARDES ===")
verifier("l'evenement `heartbeat` est accepte par la route",
         'if evenement not in ("started", "ended", "heartbeat")' in SRC)
verifier("un battement n'ecrit QUE last_seen, sur la session annoncee et NON terminee",
         '{"_id": "actuel", "session_code": code, "ended": False},\n'
         '            {"$set": {"last_seen": maintenant, "updated_at": maintenant}})' in SRC)
verifier("le demarrage pose le premier battement",
         '"last_seen": maintenant}},' in SRC)
verifier("l'ecriture reste reservee au coach authentifie",
         'email = require_auth(request)' in SRC.split("async def boosttribe_live_status_set")[1][:400]
         and 'is_super_admin(email)' in SRC.split("async def boosttribe_live_status_set")[1][:400])
verifier("la lecture publique ne renvoie toujours que `active` et `started_at`",
         'return {"active": bool(etat.get("active")), "started_at"' in SRC)
verifier("`last_seen` ne sort PAS de la lecture publique",
         '"last_seen": etat' not in SRC.split('@api_router.get("/boosttribe/live-status")')[1][:500])

echecs = [r for r in RESULTATS if not r[1]]
print("\n%d verifications, %d echec(s)" % (len(RESULTATS), len(echecs)))
sys.exit(1 if echecs else 0)

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
# V555 : le battement pose aussi `surfaces.<owner>` (signe de vie de la surface) ;
# il n'écrit toujours QUE last_seen/updated_at (+ sa surface), sur la session non terminée.
verifier("un battement n'ecrit QUE last_seen (+ sa surface V555), sur la session annoncee et NON terminee",
         'pose = {"last_seen": maintenant, "updated_at": maintenant}' in SRC
         and 'pose[f"surfaces.{owner}"] = maintenant' in SRC
         and '{"_id": "actuel", "session_code": code, "ended": False, "host": actuel.get("host")},\n'
             '            {"$set": pose})' in SRC)
verifier("V549b : le demarrage EFFACE last_seen (il n'est pas un battement)",
         '"$unset": {"last_seen": ""}},' in SRC)
verifier("l'ecriture reste reservee au coach authentifie",
         'email = require_auth(request)' in SRC.split("async def boosttribe_live_status_set")[1][:400]
         and 'is_super_admin(email)' in SRC.split("async def boosttribe_live_status_set")[1][:400])
verifier("la lecture publique ne renvoie toujours que `active` et `started_at`",
         'return {"active": bool(etat.get("active")), "started_at"' in SRC)
verifier("`last_seen` ne sort PAS de la lecture publique",
         '"last_seen": etat' not in SRC.split('@api_router.get("/boosttribe/live-status")')[1][:500])

print("\n=== 7. PROPRIETE — SEUL L'HOTE MAINTIENT SON LIVE EN VIE ===")
# La route est APPELEE (base simulee en memoire, aucune sortie reseau). L'identite
# vient de `require_auth`, jamais du corps : un champ `host` / `coach_id` envoye
# par le client est ignore.
import asyncio  # noqa: E402


class _Res:
    def __init__(self, n):
        self.matched_count = n


class _Coll:
    def __init__(self):
        self.docs = {}

    @staticmethod
    def _ok(d, f):
        return all(d.get(k) == v for k, v in f.items())

    async def find_one(self, f, proj=None):
        for d in self.docs.values():
            if self._ok(d, f):
                return dict(d)
        return None

    async def update_one(self, f, u, upsert=False):
        for d in self.docs.values():
            if self._ok(d, f):
                d.update(u.get("$set", {}))
                for k in u.get("$unset", {}):
                    d.pop(k, None)
                return _Res(1)
        if upsert:
            d = {k: v for k, v in f.items()}
            d.update(u.get("$set", {}))
            self.docs[d["_id"]] = d
            return _Res(0)
        return _Res(0)


class _Req:
    def __init__(self, email, corps):
        self.email, self.corps = email, corps

    async def json(self):
        return self.corps


COACH_A, COACH_B = "coach-a@exemple.invalid", "coach-b@exemple.invalid"


def _auth(req):
    if not req.email:
        raise S.HTTPException(status_code=401, detail="Authentification requise")
    return req.email


S.require_auth = _auth
S.is_super_admin = lambda e: e in (COACH_A, COACH_B)
S.db = type("DB", (), {})()
S.db.boosttribe_live = _Coll()


def appel(email, event, code, extra=None):
    corps = {"event": event, "session_code": code}
    corps.update(extra or {})
    try:
        r = asyncio.new_event_loop().run_until_complete(
            S.boosttribe_live_status_set(_Req(email, corps)))
        return 200, r
    except S.HTTPException as e:
        return e.status_code, e.detail


def last_seen():
    return (S.db.boosttribe_live.docs.get("actuel") or {}).get("last_seen")


verifier("A demarre SON live", appel(COACH_A, "started", "SESS-AAAA")[0] == 200)
S.db.boosttribe_live.docs["actuel"]["last_seen"] = "2000-01-01T00:00:00+00:00"
st, _ = appel(COACH_A, "heartbeat", "SESS-AAAA")
verifier("l'hote reel bat : accepte, last_seen rafraichi",
         st == 200 and last_seen() != "2000-01-01T00:00:00+00:00", "statut %s" % st)
S.db.boosttribe_live.docs["actuel"]["last_seen"] = "2000-01-01T00:00:00+00:00"
st, det = appel(COACH_B, "heartbeat", "SESS-AAAA")
verifier("coach B (authentifie, connait le code) : 403", st == 403, "statut %s %s" % (st, det))
verifier("coach B n'a PAS prolonge le live de A", last_seen() == "2000-01-01T00:00:00+00:00")
st, _ = appel(COACH_B, "heartbeat", "SESS-AAAA", {"host": COACH_A, "coach_id": COACH_A})
verifier("un `host`/`coach_id` fourni par le client ne change rien : 403", st == 403, "statut %s" % st)
st, _ = appel("", "heartbeat", "SESS-AAAA")
verifier("sans authentification : 401", st == 401, "statut %s" % st)
st, _ = appel(COACH_A, "heartbeat", "SESS-ZZZZ")
verifier("session inexistante : refus propre (404)", st == 404, "statut %s" % st)
appel(COACH_A, "ended", "SESS-AAAA")
S.db.boosttribe_live.docs["actuel"]["last_seen"] = "2000-01-01T00:00:00+00:00"
st, _ = appel(COACH_A, "heartbeat", "SESS-AAAA")
verifier("session terminee : refusee (409) et NON prolongee",
         st == 409 and last_seen() == "2000-01-01T00:00:00+00:00"
         and S.db.boosttribe_live.docs["actuel"]["ended"] is True, "statut %s" % st)

print("\n=== 8. V549b — LE DEMARRAGE N'EST PAS UN BATTEMENT ===")
# Mesure du 28/09 : Afroboost deploye AVANT BoostTribe, une page hote qui ne bat
# pas encore. Si `started` posait `last_seen`, ce live mourait 90 s plus tard.
# Et un `last_seen` laisse par le live PRECEDENT le tuerait immediatement.
S.db.boosttribe_live.docs["actuel"]["last_seen"] = "2000-01-01T00:00:00+00:00"   # reste du live d'avant
verifier("A redemarre un NOUVEAU live", appel(COACH_A, "started", "SESS-BBBB")[0] == 200)
d = dict(S.db.boosttribe_live.docs["actuel"])
verifier("le demarrage efface le last_seen du live precedent (aucun battement recu)",
         "last_seen" not in d, repr(d.get("last_seen")))
d["started_at"] = (MAINTENANT - timedelta(seconds=120)).isoformat()
if "last_seen" in d:   # pose au demarrage, jamais rafraichi : il a le meme age
    d["last_seen"] = d["started_at"]
verifier("page hote SANS battement, 120 s apres le debut : le live reste en cours (regle des 3 h)",
         actif(d), repr(d))
st, _ = appel(COACH_A, "heartbeat", "SESS-BBBB")
verifier("le premier battement arme la grace de 90 s", st == 200 and last_seen() is not None)

print("\n=== 9. V550 — RECONNEXION != NOUVEAU LIVE ; LA FIN AUSSI EST A L'HOTE ===")
# Mesure du 28/09 (E97T2UNA-3Z3W5H) : CINQ `started` pour une seule session, a
# chaque remontage de la page hote. `started_at` repartait a zero a chaque fois :
# le garde-fou des 3 h glissait indefiniment.
DEBUT_ORIGINE = "2026-09-28T08:06:41+00:00"
S.db.boosttribe_live.docs["actuel"]["started_at"] = DEBUT_ORIGINE
st, _ = appel(COACH_A, "started", "SESS-BBBB")          # refresh / remontage
d = S.db.boosttribe_live.docs["actuel"]
verifier("G : re-annonce de la MEME session par le MEME hote -> started_at conserve",
         st == 200 and d["started_at"] == DEBUT_ORIGINE, repr(d.get("started_at")))
verifier("C : la reconnexion efface last_seen (la grace se rearme au prochain battement)",
         "last_seen" not in d, repr(d.get("last_seen")))
st, _ = appel(COACH_A, "heartbeat", "SESS-BBBB")
verifier("C : le battement reprend apres la reconnexion", st == 200 and last_seen() is not None)
st, det = appel(COACH_B, "ended", "SESS-BBBB")
verifier("F : coach B ne peut PAS terminer le live de A (403)", st == 403, "statut %s %s" % (st, det))
verifier("F : le live de A est toujours en cours", S.db.boosttribe_live.docs["actuel"]["ended"] is False)
st, _ = appel(COACH_A, "ended", "SESS-BBBB")
verifier("A termine SON live", st == 200 and S.db.boosttribe_live.docs["actuel"]["ended"] is True)
st, _ = appel(COACH_A, "started", "SESS-CCCC")
verifier("un VRAI nouveau live (autre code) repart avec un nouveau started_at",
         st == 200 and S.db.boosttribe_live.docs["actuel"]["started_at"] != DEBUT_ORIGINE
         and S.db.boosttribe_live.docs["actuel"]["ended"] is False)

echecs = [r for r in RESULTATS if not r[1]]
print("\n%d verifications, %d echec(s)" % (len(RESULTATS), len(echecs)))
sys.exit(1 if echecs else 0)

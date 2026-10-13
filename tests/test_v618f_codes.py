#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618f — écran « Codes » : « Abonnement actuel / Historique » par la règle canonique V618.

Banc permanent, sans réseau, données SYNTHÉTIQUES. Fonction pure `abonnement_actuel.classer_codes`
+ câblage de GET /discount-codes + règle « ancien code expiré + abonnement récent -> le récent ».

Lancement : python3 tests/test_v618f_codes.py
"""
import asyncio
import copy
import os
import sys
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v618f:27017")
import api.routes.abonnement_actuel as AA  # noqa: E402

MAINTENANT = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


def fiche(i, code, exp, used, maxu, classement, titulaire="", active=True, **extra):
    d = {"id": i, "code": code, "expiresAt": exp, "used": used, "maxUses": maxu, "active": active,
         "assignedEmail": titulaire, "v532": {"classement": classement, "motif": "x"}}
    d.update(extra)
    return d


def sub(i, code, email, status="active", exp="2027-06-04T23:59:59+00:00", used=1, total=32, **extra):
    d = {"id": i, "code": code, "email": email, "status": status, "expires_at": exp,
         "used_sessions": used, "total_sessions": total, "created_at": "2026-01-01"}
    d.update(extra)
    return d


def classer(codes, subs):
    return AA.classer_codes(copy.deepcopy(codes), subs, {}, MAINTENANT)


def par_id(codes):
    return {c["id"]: c for c in codes}


# 1. Cas BASSBOOSTX-31 : deux fiches (une expirée 6/7 au 30/09, une vivante 1/32 au 04/06/2027)
r = par_id(classer([fiche("f-exp", "BX-31", "2026-09-30", 6, 7, "historique"),
                    fiche("f-viv", "BX-31", "2027-06-04", 1, 32, "actuel")],
                   [sub("s31", "BX-31", "client@t.example")]))
verifier("1 BASSBOOSTX-31 : la fiche vivante reste ACTUELLE (1/32, fin 04/06/2027)",
         r["f-viv"]["v532"]["classement"] == "actuel" and r["f-viv"]["v532"]["total"] == 32
         and r["f-viv"]["v618"]["etat"] == "actuel", r["f-viv"])
verifier("1b … et la fiche expirée en doublon reste HISTORIQUE",
         r["f-exp"]["v532"]["classement"] == "historique" and r["f-exp"]["v618"]["etat"] == "historique")

# 2. Fiche unique à vieille date, abonnement actuel : le classement suit l'ABONNEMENT, plus la date
r = par_id(classer([fiche("f", "OLD-DATE", "2026-09-30", 6, 7, "historique")],
                   [sub("s", "OLD-DATE", "c@t.example", used=1, total=32)]))
verifier("2 fiche à vieille date + abonnement actuel -> ACTUEL, avec la fin et les séances de l'abonnement",
         r["f"]["v532"]["classement"] == "actuel" and r["f"]["v532"]["expire_le"].startswith("2027-06-04")
         and r["f"]["v532"]["utilise"] == 1 and r["f"]["v532"]["total"] == 32, r["f"])

# 3. Fiche vivante (aucune date), abonnement expiré (cas Dianaboo2026) -> HISTORIQUE
r = par_id(classer([fiche("f", "DIANA", None, 1, 9, "actuel")],
                   [sub("s", "DIANA", "d@t.example", status="expired", exp="2026-05-22T23:59:59+00:00")]))
verifier("3 fiche vivante mais abonnement expiré -> HISTORIQUE (jamais « actuel » sur la foi de la fiche)",
         r["f"]["v532"]["classement"] == "historique" and r["f"]["v618"]["etat"] == "historique")

# 4. Ancien code expiré + abonnement récent actif (même personne) -> le RÉCENT est l'actuel
r = par_id(classer([fiche("old", "ANCIEN", "2026-05-05", 4, 47, "historique", titulaire="p@t.example"),
                    fiche("new", "RECENT", "2027-06-07", 1, 31, "actuel", titulaire="p@t.example")],
                   [sub("s-old", "ANCIEN", "p@t.example", status="expired", exp="2026-05-05T23:59:59+00:00"),
                    sub("s-new", "RECENT", "p@t.example", total=31)]))
verifier("4 ancien code expiré + abonnement récent : le récent ACTUEL, l'ancien HISTORIQUE",
         r["new"]["v532"]["classement"] == "actuel" and r["old"]["v532"]["classement"] == "historique")

# 5. Conflit (deux actuels) -> CONFLIT, rien choisi
r = par_id(classer([fiche("a", "AMB-26", "2027-06-04", 1, 64, "actuel"), fiche("b", "AFR-Y8", "2026-12-03", 0, 1, "actuel")],
                   [sub("s1", "AMB-26", "amanda@t.example"), sub("s2", "AFR-Y8", "amanda@t.example", exp="2026-12-03T23:59:59+00:00")]))
verifier("5 conflit : les deux codes marqués CONFLIT, aucun étiquette changée (fail closed)",
         r["a"]["v618"]["etat"] == r["b"]["v618"]["etat"] == "conflit"
         and r["a"]["v532"]["classement"] == r["b"]["v532"]["classement"] == "actuel")

# 6. Doublons vivants à vérifier (cas Christoux10) -> l'étiquette À VÉRIFIER reste, aucun choix
r = par_id(classer([fiche("c1", "CHRIS", "2027-06-03", 0, 67, "a_verifier"), fiche("c2", "CHRIS", "2027-06-03", 0, 67, "a_verifier")],
                   [sub("s", "CHRIS", "chris@t.example", total=67, used=0)]))
verifier("6 doublons vivants À VÉRIFIER : aucune fiche choisie entre eux",
         r["c1"]["v532"]["classement"] == r["c2"]["v532"]["classement"] == "a_verifier")

# 7. Code sans abonnement (promo, club) -> règle LOT A d'avant, inchangée
r = par_id(classer([fiche("club", "CLUB", "2026-10-12", 21, 40, "historique", multi_member=True),
                    fiche("promo", "PROMO", "2027-01-01", 0, 10, "actuel")], []))
verifier("7 code sans abonnement (club / promo) : étiquette inchangée, aucun état V618",
         r["club"]["v532"]["classement"] == "historique" and r["promo"]["v532"]["classement"] == "actuel"
         and "v618" not in r["club"] and "v618" not in r["promo"])

# 8. Abonnement créé par la route publique /validate : ne rend jamais un code « actuel »
r = par_id(classer([fiche("v", "VAL", "2026-01-01", 0, 5, "historique")],
                   [sub("sv", "VAL", "x@t.example", source="promo_validate")]))
verifier("8 abonnement /validate non prouvé : aucune influence sur le classement", "v618" not in r["v"]
         and r["v"]["v532"]["classement"] == "historique")

# 9. Deux coachs, même adresse : chacun garde son abonnement actuel (pas un conflit)
r = par_id(classer([fiche("p", "PLAT", "2027-01-01", 0, 10, "actuel"),
                    fiche("b", "PART", "2027-01-01", 0, 10, "actuel", coach_id="coach.b@t.example")],
                   [sub("sp", "PLAT", "deux@t.example"), sub("sb", "PART", "deux@t.example", coach_id="coach.b@t.example")]))
verifier("9 deux coachs, même adresse : deux abonnements actuels, aucun conflit",
         r["p"]["v618"]["etat"] == r["b"]["v618"]["etat"] == "actuel")

# 9b. Cloisonnement : une fiche ne lit jamais l'abonnement d'un AUTRE périmètre (revue de sécurité)
r = par_id(classer([fiche("x", "MIXTE", "2026-01-01", 0, 10, "historique", coach_id="coach.b@t.example")],
                   [sub("sx", "MIXTE", "client@t.example", coach_id="contact.artboost@gmail.com", used=3, total=64)]))
verifier("9b fiche du coach B, abonnement de la plateforme : aucune date ni séance d'un autre coach exposée",
         "v618" not in r["x"] and r["x"]["v532"] == {"classement": "historique", "motif": "x"}, r["x"])

# 10. Câblage + lecture seule
PROMO = open(os.path.join(RACINE, "api", "routes", "promo_routes.py"), encoding="utf-8").read()
liste = PROMO[PROMO.index("async def get_discount_codes("):]
liste = liste[:liste.index("\n@promo_router")]
verifier("10 GET /discount-codes : classement canonique appliqué après LOT A / V617",
         liste.index("_v617(") < liste.index("enrichir_codes(_db, codes,"))


class _Curseur:
    def __init__(self, docs):
        self.docs = docs

    async def to_list(self, n=None):
        return list(self.docs)


class _Coll:
    def __init__(self, docs):
        self.docs = docs
        self.ecritures = 0

    def find(self, *a, **k):
        return _Curseur(self.docs)

    def __getattr__(self, nom):
        if nom.startswith(("insert", "update", "delete", "replace", "find_one_and")):
            self.ecritures += 1
            raise AssertionError("écriture interdite : " + nom)
        raise AttributeError(nom)


class _Base:
    def __init__(self):
        self.subscriptions = _Coll([sub("s", "OLD-DATE", "c@t.example")])
        self.discount_codes = _Coll([{"code": "OLD-DATE", "coach_id": ""}])


_b = _Base()
_out = asyncio.run(AA.enrichir_codes(_b, [fiche("f", "OLD-DATE", "2026-09-30", 6, 7, "historique")]))
verifier("11 enrichissement réel : lecture seule (aucune écriture) et classement appliqué",
         _b.subscriptions.ecritures == 0 and _b.discount_codes.ecritures == 0
         and _out[0]["v532"]["classement"] == "actuel")

_b = _Base()
_legacy = fiche("lg", "OLD-DATE", "2026-09-30", 6, 7, "historique")          # ancienne fiche sans coach_id
_out = asyncio.run(AA.enrichir_codes(_b, [_legacy], appelant="coach.b@t.example", admin=False))
verifier("12 coach partenaire : une ancienne fiche plateforme (visible dans sa liste) ne reçoit AUCUN état V618",
         "v618" not in _out[0] and _out[0]["v532"]["classement"] == "historique")
verifier("13 GET /discount-codes passe l'appelant et son rôle (cloisonnement)",
         "enrichir_codes(_db, codes, appelant=user_email, admin=is_super_admin)" in liste)


def main():
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:600])
        _ok += ok
    print("%d / %d verifications V618f au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""SCAN — LE COURS SUIVI ET LE DROIT UTILISE, COTE A COTE.

Le portier affichait « test01 — Cours a l'unite » pour quelqu'un dont le droit
etait un ESSAI GRATUIT : le coach lisait un achat la ou il avait un essayeur.
Ce n'etait pas un melange mais une OMISSION — la reponse du scan ne portait que
le cours.

Les VRAIES fonctions sont extraites de `api/routes/reservation_routes.py` par le
banc d'essai partage, et executees sur le meme faux MongoDB que R11, A0 et A1b.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE DE PRODUCTION.

Lancement :  python3 tests/test_scan_acces.py
"""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._banc_qr import (          # noqa: E402
    RESULTATS, verifier, construire_routes, faux_shared, _Base, _HTTPException,
    resa, cours, forfait, aujourdhui, _a0_jour, scanner, COACH_TEST,
)


class _Requete(object):
    """Le corps du scan, relisible — Starlette le garde en cache."""

    def __init__(self, code):
        self._c = {"code": code}
        self.lectures = 0

    async def json(self):
        await asyncio.sleep(0)
        self.lectures += 1
        return self._c


def monde(codes=None, subs=None, resas=None, cours_=None):
    db = _Base()
    if resas is not None:
        db.reservations = type(db.reservations)(resas)
    if subs is not None:
        db.subscriptions = type(db.subscriptions)(subs)
    if codes is not None:
        db.discount_codes = type(db.discount_codes)(codes)
    if cours_ is not None:
        db.courses = type(db.courses)(cours_)
    return db


def code_essai(code="AFR-248AJR"):
    """Le marqueur d'ESSAI-1, et rien d'autre : c'est LUI qui fait foi."""
    return {"code": code, "name": "test01", "payment_method": "free",
            "total_paid": 0, "maxUses": 1, "used": 1, "coach_id": ""}


def code_paye(code="BASSBOOSTX-11", **kw):
    d = {"code": code, "payment_method": "card", "total_paid": 250,
         "maxUses": 10, "used": 3}
    d.update(kw)
    return d


def sub(code="AFR-248AJR", offre="🎁 Cours d'essai GRATUIT ", **kw):
    d = {"id": "sub-" + code, "code": code, "offer_name": offre,
         "email": "test01@exemple.ch", "name": "test01",
         "total_sessions": 1, "used_sessions": 1, "remaining_sessions": 0}
    d.update(kw)
    return d


async def enrichir(ns, db, reponse, code):
    req = _Requete(code)
    return await ns["_scan_enrichir"](req, reponse), req


def reponse_type(rcode="AF0000001", nom="test01", abonnement=True):
    r = {"success": True, "type": "subscription" if abonnement else "reservation",
         "message": "Présence validée",
         "reservation": {"userName": nom, "reservationCode": rcode,
                         "courseName": "Cours à l'unité"}}
    if abonnement:
        r["subscriber"] = {"name": nom, "remaining": 0, "total": 1}
    return r


# ═════════════════════════════════ scenarios ════════════════════════════════
async def scenarios():
    # `api.routes.shared` est remplace par le banc d'essai : le scan y lit
    # ESSAI2_FILTRE_GRATUIT, et le test J7 compare cette copie a la VRAIE.
    faux_shared()

    # ─────────── A. ESSAI GRATUIT — le cas reel AFR-248AJR / test01 ─────────
    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="AFR-248AJR",
                           promoCode="AFR-248AJR", courseName="Cours à l'unité",
                           datetime=aujourdhui("18:30"), courseTime="18:30",
                           validated=True)])
    ns = construire_routes(db)
    rep, req = await enrichir(ns, db, reponse_type(), "AFR-248AJR")
    verifier("A1. essai gratuit -> le DROIT est annonce comme un essai",
             rep["acces"] == {"libelle": ns["SCAN_LIBELLE_ESSAI"], "essai": True},
             str(rep.get("acces")))
    verifier("A2. ... et le COURS reste le vrai cours, jamais remplace",
             rep["reservation"]["courseName"] == "Cours à l'unité",
             rep["reservation"]["courseName"])
    verifier("A3. ... avec la date de l'occurrence",
             rep["reservation"]["quand"].endswith("· 18:30")
             and rep["reservation"]["quand"][:3] in ("Dim","Lun","Mar","Mer","Jeu","Ven","Sam"),
             rep["reservation"].get("quand"))
    verifier("A4. ... et les seances restantes, inchangees",
             rep["subscriber"] == {"name": "test01", "remaining": 0, "total": 1},
             str(rep.get("subscriber")))

    # A5. Le nom du COURS n'entre pour RIEN dans la detection : le meme cours,
    #     paye, ne produit plus « Essai gratuit ».
    db = monde(codes=[code_paye(code="AFR-PAYE")],
               subs=[sub(code="AFR-PAYE", offre="Cours à l'unité")],
               resas=[resa(code="AF0000001", discountCode="AFR-PAYE",
                           promoCode="AFR-PAYE", courseName="Cours à l'unité",
                           datetime=aujourdhui("18:30"), validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "AFR-PAYE")
    verifier("A5. MEME cours, droit paye -> jamais « Essai gratuit »",
             rep["acces"] == {"libelle": "Cours à l'unité", "essai": False},
             str(rep.get("acces")))

    # A6. `source: social_proof` est l'autre porte de la gratuite (ESSAI-1).
    db = monde(codes=[{"code": "AFR-SOCIAL", "source": "social_proof",
                       "payment_method": "card", "total_paid": 25}],
               subs=[sub(code="AFR-SOCIAL", offre="Peu importe")],
               resas=[resa(code="AF0000001", discountCode="AFR-SOCIAL",
                           promoCode="AFR-SOCIAL", datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "AFR-SOCIAL")
    verifier("A6. preuve sociale -> reconnue comme essai, malgre un montant",
             rep["acces"]["essai"] is True, str(rep.get("acces")))

    # ─────────────── B / C. PACK ET ACHAT A L'UNITE ────────────────────────
    db = monde(codes=[code_paye(code="AFR-PULSE")],
               subs=[sub(code="AFR-PULSE", offre="PULSE x10 cours",
                         total_sessions=10, remaining_sessions=7)],
               resas=[resa(code="AF0000001", discountCode="AFR-PULSE",
                           promoCode="AFR-PULSE", courseName="Afroboost Silent",
                           datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    r = reponse_type()
    r["reservation"]["courseName"] = "Afroboost Silent"
    r["subscriber"] = {"name": "test01", "remaining": 7, "total": 10}
    rep, _ = await enrichir(ns, db, r, "AFR-PULSE")
    verifier("B. PULSE x10 -> cours reel + acces « PULSE x10 cours »",
             rep["reservation"]["courseName"] == "Afroboost Silent"
             and rep["acces"] == {"libelle": "PULSE x10 cours", "essai": False},
             str(rep.get("acces")))

    db = monde(codes=[code_paye(code="AFR-UNITE", maxUses=1)],
               subs=[sub(code="AFR-UNITE", offre="Cours à l'unité")],
               resas=[resa(code="AF0000001", discountCode="AFR-UNITE",
                           promoCode="AFR-UNITE", courseName="Cours à l'unité",
                           datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "AFR-UNITE")
    verifier("C. achat a l'unite -> les deux lignes disent la meme chose, et c'est vrai",
             rep["reservation"]["courseName"] == "Cours à l'unité"
             and rep["acces"] == {"libelle": "Cours à l'unité", "essai": False}, str(rep))

    # ─────────────── D / E. DONNEES HISTORIQUES : NE RIEN INVENTER ─────────
    db = monde(codes=[code_paye(code="BASSBOOSTX-11")],
               subs=[sub(code="BASSBOOSTX-11", offre="Abonnement")],
               resas=[resa(code="AF0000001", discountCode="BASSBOOSTX-11",
                           promoCode="BASSBOOSTX-11", datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "BASSBOOSTX-11")
    verifier("D. vieux forfait « Abonnement » -> rendu tel quel, aucun nom invente",
             rep["acces"] == {"libelle": "Abonnement", "essai": False}, str(rep.get("acces")))

    db = monde(codes=[code_paye(code="BASSBOOSTX-09")],
               subs=[sub(code="BASSBOOSTX-09", offre="BASSBOOSTX-09")],
               resas=[resa(code="AF0000001", discountCode="BASSBOOSTX-09",
                           promoCode="BASSBOOSTX-09", datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "BASSBOOSTX-09")
    verifier("E. code historique brut -> comportement deterministe, le code lui-meme",
             rep["acces"] == {"libelle": "BASSBOOSTX-09", "essai": False}, str(rep.get("acces")))

    # E2. Aucun forfait retrouve -> libelle VIDE, et l'ecran n'affiche rien.
    db = monde(codes=[code_paye(code="AFR-ORPHELIN")], subs=[],
               resas=[resa(code="AF0000001", discountCode="AFR-ORPHELIN",
                           promoCode="AFR-ORPHELIN", datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "AFR-ORPHELIN")
    verifier("E2. aucun forfait -> libelle vide, jamais un nom fabrique",
             rep["acces"] == {"libelle": "", "essai": False}, str(rep.get("acces")))

    # ─────────────── F / G. OCCURRENCES : RECURRENT ET PONCTUEL ────────────
    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="AFR-248AJR",
                           promoCode="AFR-248AJR", datetime=aujourdhui("18:30"),
                           courseTime="18:30", validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "AFR-248AJR")
    _attendu_jour = _a0_jour()
    verifier("F. cours recurrent -> la date rendue est celle de L'OCCURRENCE",
             rep["reservation"]["datetime"].startswith(_attendu_jour),
             rep["reservation"].get("datetime"))

    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="AFR-248AJR",
                           promoCode="AFR-248AJR", datetime="2026-08-21T18:30:00",
                           courseTime="18:30", validated=True)])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, reponse_type(), "AFR-248AJR")
    verifier("G. cours ponctuel -> sa propre date, pas celle du jour",
             rep["reservation"]["quand"] == "Ven 21 aout · 18:30",
             rep["reservation"].get("quand"))

    # ─────────────── H / I. DEJA VALIDE ET VALIDATION NEUVE ────────────────
    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="AFR-248AJR",
                           promoCode="AFR-248AJR", datetime=aujourdhui("18:30"),
                           courseTime="18:30", validated=True)])
    ns = construire_routes(db)
    r_deja = reponse_type(); r_deja["message"] = "Déjà validé"
    rep_deja, _ = await enrichir(ns, db, r_deja, "AFR-248AJR")
    rep_neuf, _ = await enrichir(ns, db, reponse_type(), "AFR-248AJR")
    verifier("H/I. « deja valide » et « validee » disent EXACTEMENT la meme chose",
             rep_deja["acces"] == rep_neuf["acces"]
             and rep_deja["reservation"]["quand"] == rep_neuf["reservation"]["quand"],
             "%s / %s" % (rep_deja.get("acces"), rep_neuf.get("acces")))

    # ─────────────── J. RIEN D'AUTRE NE BOUGE ──────────────────────────────
    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="AFR-248AJR",
                           promoCode="AFR-248AJR", datetime=aujourdhui("18:30"),
                           validated=True)])
    ns = construire_routes(db)
    avant = reponse_type()
    import copy
    ref = copy.deepcopy(avant)
    rep, _ = await enrichir(ns, db, avant, "AFR-248AJR")
    verifier("J1. aucun champ existant n'est ecrase",
             all(rep[k] == ref[k] for k in ("success", "type", "message", "subscriber"))
             and all(rep["reservation"][k] == ref["reservation"][k]
                     for k in ref["reservation"]), str(rep))
    verifier("J2. AUCUNE ecriture : la base est inchangee",
             db.reservations.docs[0].get("validated") is True
             and len(db.subscriptions.docs) == 1
             and db.subscriptions.docs[0].get("remaining_sessions") == 0, "")

    # J3. Une reponse d'echec n'est jamais enrichie.
    db = monde(codes=[code_essai()], subs=[sub()])
    ns = construire_routes(db)
    rep, _ = await enrichir(ns, db, {"success": False, "message": "Refus"}, "AFR-248AJR")
    verifier("J3. reponse en echec -> laissee strictement intacte",
             rep == {"success": False, "message": "Refus"}, str(rep))

    # J4. Une base en panne ne fait PAS echouer le scan : l'affichage cede,
    #     jamais la presence.
    class _Casse(object):
        def find_one(self, *a, **k):
            raise RuntimeError("Mongo indisponible (simule)")

    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="AFR-248AJR",
                           promoCode="AFR-248AJR", datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    db.reservations = _Casse()
    rep, _ = await enrichir(ns, db, reponse_type(), "AFR-248AJR")
    verifier("J4. lecture en panne -> le scan repond comme avant, sans exception",
             rep.get("success") is True and "acces" not in rep, str(rep))

    # J5. Le code peut venir du corps de la requete quand la reservation ne le
    #     porte pas — et une URL de QR est acceptee.
    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="", promoCode="",
                           datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    # L'URL suit la convention deja en service (`_a0_code_depuis_qr`) : le code
    # se lit dans un PARAMETRE, jamais dans le chemin.
    rep, req = await enrichir(ns, db, reponse_type(),
                              "https://afroboost.com/?qr=AFR-248AJR")
    verifier("J5. code repris du corps (QR en URL) -> essai reconnu quand meme",
             rep["acces"]["essai"] is True, str(rep.get("acces")))
    rep2, _ = await enrichir(ns, db, reponse_type(), "AFR-248AJR")
    verifier("J5b. code brut dans le corps -> meme resultat",
             rep2["acces"] == rep["acces"], str(rep2.get("acces")))

    # J6. Le libelle « Essai gratuit » n'est PAS ecrit dans le frontend : il
    #     vient du serveur, une seule fois, pour les deux scanners.
    verifier("J6. le libelle d'essai est une constante serveur",
             ns["SCAN_LIBELLE_ESSAI"] == "Essai gratuit", ns["SCAN_LIBELLE_ESSAI"])

    # J7. La regle d'essai du scan est LA MEME que celle de shared.py.
    import ast
    _sh = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "api", "routes", "shared.py"), encoding="utf-8").read()
    _ns2 = {}
    for n in ast.walk(ast.parse(_sh)):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "ESSAI2_FILTRE_GRATUIT":
            exec(compile("".join(_sh.splitlines(True)[n.lineno - 1:n.end_lineno]), "x", "exec"), _ns2)
    from tests import _banc_qr as _bq
    import sys as _sys
    verifier("J7. le scan et ESSAI-2 partagent LA MEME definition de « essai »",
             _ns2["ESSAI2_FILTRE_GRATUIT"]
             == _sys.modules["api.routes.shared"].ESSAI2_FILTRE_GRATUIT,
             str(_ns2.get("ESSAI2_FILTRE_GRATUIT")))

    # J8. Le nombre de lectures reste BORNE : jamais une boucle a la porte.
    db = monde(codes=[code_essai()], subs=[sub()],
               resas=[resa(code="AF0000001", discountCode="AFR-248AJR",
                           promoCode="AFR-248AJR", datetime=aujourdhui(), validated=True)])
    ns = construire_routes(db)
    _compte = {"n": 0}
    for _coll in ("reservations", "subscriptions", "discount_codes"):
        _c = getattr(db, _coll)
        _vrai = _c.find_one

        def _espion(*a, __v=_vrai, **k):
            _compte["n"] += 1
            return __v(*a, **k)
        _c.find_one = _espion
    await enrichir(ns, db, reponse_type(), "AFR-248AJR")
    verifier("J8. essai -> DEUX lectures a document unique, pas trois",
             _compte["n"] == 2, "lectures=%d" % _compte["n"])


def main():
    asyncio.run(scenarios())
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 78)
    print("SCAN — COURS vs ACCES")
    print("=" * 78)
    for nom, cond, detail in RESULTATS:
        print(("  OK   " if cond else "  ECHEC") + "  " + nom
              + ("" if cond else "\n           -> " + str(detail)[:300]))
    print("-" * 78)
    print("Presences / debits / ecritures REELS : 0 — base en memoire")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

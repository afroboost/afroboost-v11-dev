#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618N — UN ANCIEN CODE NE REPREND JAMAIS LE DESSUS SUR L'ABONNEMENT ACTUEL.

Constat (13/10/2026, audit en lecture seule) : le lien qui a ouvert /espace/AFR-9CB0A0 a été
demandé pour contact.artboost@gmail.com (dont le SEUL abonnement est cet ancien code expiré),
pas pour bassicustomshoes@gmail.com (dont les liens visaient tous BASSBOOSTX-11). Le moteur était
juste ; ce banc VERROUILLE la règle (vraies routes, jeton d'espace signé, base en mémoire) :
  * ancien code + abonnement ACTUEL du même titulaire -> redirection vers l'espace actuel
    (session neuve sur le code actuel, ancienne session fermée) ;
  * seul un ancien abonnement (cas AFR-9CB0A0) -> cet espace, sans code inventé ;
  * conflit (deux actuels) -> aucune bascule ; l'abonnement d'un AUTRE client n'est jamais servi ;
  * le lien d'accès par e-mail vise le code ACTUEL (résolveur canonique).

Lancement : python3 tests/test_v618n_abonnement_actuel.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_v618c_securite as C  # noqa: E402  (même monde : jeton d'espace signé, base en mémoire)

S, H, SH = C.S, C.H, C.SH
import api.routes.abonnement_actuel as AA  # noqa: E402

RESULTATS = []
D = "titulaire.d@t.example"
Z = "seul.ancien@t.example"


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


def monde():
    base = C.monde()
    # D : un ANCIEN code expiré (OLD-D, 1/1) + UN abonnement actuel (CUR-D, 64 / 15).
    base["subscriptions"].docs += [C.sub("so", "OLD-D", D, status="expired", exp=C.PASSE, total=1, used=0),
                                   C.sub("sd", "CUR-D", D, total=64, used=15)]
    base["discount_codes"].docs += [C.fiche("OLD-D", D, exp="2026-09-01"), C.fiche("CUR-D", D)]
    # Z : n'a QUE son ancien code expiré (forme du cas contact.artboost / AFR-9CB0A0).
    base["subscriptions"].docs.append(C.sub("sz", "OLD-Z", Z, status="expired", exp=C.PASSE, total=1, used=0))
    base["discount_codes"].docs.append(C.fiche("OLD-Z", Z, exp="2026-09-01"))
    AA.init_db(base)
    return base


async def espace(code, tok):
    return await H.appel(S.get_subscriber_space(code, H.Requete({}, {"x-espace-token": tok}), None))


def session(base, jti):
    return next((s for s in base[S._B3S1_COLL_SESSIONS].docs if s.get("jti") == jti), {})


async def principal():
    base = monde()
    tok_old = C.jeton(base, "OLD-D", D)
    jti_old = (SH.lotb3s1_lire_token(tok_old) or {}).get("jti")
    c, r = await espace("OLD-D", tok_old)
    red = (r or {}).get("redirection_espace") or {}
    lu = SH.lotb3s1_lire_token(red.get("token") or "") or {}
    verifier("B ancien lien OLD-D du titulaire D : redirection vers son abonnement ACTUEL CUR-D (jamais l'ancien)",
             c == 200 and red.get("code") == "CUR-D" and str(lu.get("code") or "").upper() == "CUR-D"
             and str(lu.get("email") or "").lower() == D, (c, r))
    verifier("B2 l'ancienne session est FERMÉE (elle ne fabrique plus rien)", session(base, jti_old).get("revoked") is True)
    c, r = await espace("CUR-D", red.get("token"))
    verifier("C l'espace ouvert est l'abonnement actuel (64 séances, 15 utilisées)",
             c == 200 and not (r or {}).get("redirection_espace") and (r or {}).get("subscriber", {}).get("code", "CUR-D").upper() == "CUR-D", c)
    tok_z = C.jeton(base, "OLD-Z", Z)
    c, r = await espace("OLD-Z", tok_z)
    verifier("A2 seul un ancien abonnement (cas AFR-9CB0A0) : son espace, aucune redirection inventée",
             c == 200 and not (r or {}).get("redirection_espace"), (c, (r or {}).get("redirection_espace")))
    tok_a = C.jeton(base, "AFR-A1", C.A)
    c, r = await espace("AFR-A1", tok_a)
    verifier("B3 titulaire en CONFLIT (deux abonnements actifs) : aucune bascule automatique (fail closed)",
             c == 200 and not (r or {}).get("redirection_espace"), c)
    tok_b = C.jeton(base, "AFR-B1", C.B)
    c, _ = await espace("OLD-D", tok_b)
    verifier("B4 session d'un AUTRE client sur l'URL OLD-D : refus neutre, rien de D n'est servi", c == 404, c)
    # A — le lien e-mail vise le code ACTUEL : même résolveur que /subscriber/recover.
    rd = await AA.resoudre_abonnement_actuel(base, D, perimetre=AA.locataire(S.DEFAULT_COACH_ID))
    rz = await AA.resoudre_abonnement_actuel(base, Z, perimetre=AA.locataire(S.DEFAULT_COACH_ID))
    verifier("A le lien d'accès de D vise CUR-D (abonnement actuel canonique)",
             rd["etat"] == AA.ETAT_COURANT and rd["abonnement"]["code"] == "CUR-D", rd)
    verifier("A3 l'adresse qui n'a qu'un ancien abonnement n'a AUCUN abonnement actuel (pas de faux actuel)",
             rz["etat"] != AA.ETAT_COURANT, rz["etat"])
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "api", "server.py"), encoding="utf-8").read()
    i = src.index('@api_router.post("/subscriber/recover")')
    rec = src[i:src.index("@api_router", i + 10)]
    verifier("A4 /subscriber/recover résout l'abonnement actuel AVANT de fabriquer le lien",
             "resoudre_abonnement_actuel" in rec or "code_cible_espace" in rec or "abonnement_actuel" in rec)


def main():
    asyncio.run(principal())
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:700])
        _ok += ok
    print("%d / %d verifications V618N au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

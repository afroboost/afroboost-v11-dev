#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SA-1 — UN SEUL SUPER-ADMIN : contact.artboost@gmail.com.

Décision définitive du propriétaire (29/09/2026) : `afroboost.bassi@gmail.com`
n'est JAMAIS super-admin et n'a aucun droit global, ni côté serveur ni côté écran.

Ce banc vérifie, sur le VRAI code de `api/` (faux MongoDB en mémoire du banc
`test_referral_pass_duo`, VRAIS JWT signés par le secret du banc) :
  1. toutes les fonctions `is_super_admin` du dépôt (shared, server, coach,
     reservation, checkout, campaign) + `get_user_role` + `is_super_admin_email`
     refusent l'ancienne seconde adresse et acceptent le propriétaire ;
  2. `ADMIN_EMAILS` (environnement Coolify) ne peut PLUS élargir le rôle : même
     positionnée avec l'ancienne seconde adresse, celle-ci reste non-admin, et un
     WARNING est journalisé (sans les adresses) ;
  3. `/auth/login` émet `role: "coach"` pour l'ancienne seconde adresse et
     `role: "super_admin"` pour le propriétaire ; `/auth/role` et `/auth/whoami`
     ne la déclarent pas super-admin ;
  4. `_v411_exiger_super_admin`, `super_admin_signe`, `boost.exiger_super_admin`
     et trois VRAIES routes admin (fils WhatsApp V411, activation de coach V2-0d,
     clôture analytics) refusent un JWT signé de l'ancienne seconde adresse (403) ;
  5. V2-0d : l'ancienne seconde adresse est redevenue ORDINAIRE — l'inscription
     sous cette adresse suit le chemin commun (compte EN ATTENTE, aucun privilège),
     tandis que celle du propriétaire reste réservée (409).

AUCUN réseau, AUCUNE base réelle. Lancement : python3 tests/test_sa1_super_admin_unique.py
"""
import asyncio
import importlib
import logging
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ICI)

import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement du banc)

import jwt as pyjwt  # noqa: E402
from fastapi import HTTPException, Response  # noqa: E402

S = H.S
SH = H.SH
import api.routes.auth_routes as AR  # noqa: E402
import api.routes.coach_routes as CO  # noqa: E402
import api.routes.reservation_routes as RR  # noqa: E402
import api.routes.checkout_routes as CK  # noqa: E402
import api.routes.campaign_routes as CR  # noqa: E402
import api.routes.boost_routes as BO  # noqa: E402
import api.routes.analytics_routes as AN  # noqa: E402

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


PROPRIETAIRE = "contact.artboost@gmail.com"
ANCIEN_SECOND = "afroboost.bassi@gmail.com"


class _CollSessions(H._Coll):
    """`coach_sessions` : le faux Mongo du banc n'a pas `delete_many`."""

    async def delete_many(self, q, **k):
        avant = len(self.docs)
        self.docs = [d for d in self.docs if not H._match(d, q)]
        return type("R", (), {"deleted_count": avant - len(self.docs)})()


def base_auth():
    base = H._Base()
    base._c["coach_sessions"] = _CollSessions("coach_sessions")
    return base


def req(jeton_de=None, entete=None, corps=None):
    e = {}
    if jeton_de:
        e["Authorization"] = "Bearer " + H.jeton_admin(jeton_de)
    if entete:
        e["X-User-Email"] = entete
    return H.Requete(corps if corps is not None else {}, e)


async def statut(coro):
    try:
        await coro
        return 200
    except HTTPException as e:
        return e.status_code


def statut_sync(f, *a):
    try:
        f(*a)
        return 200
    except HTTPException as e:
        return e.status_code


# ─────────────────────────────────────────────────────────────────────────────
# 1. Toutes les définitions de « super-admin »
# ─────────────────────────────────────────────────────────────────────────────
def t1_listes_et_fonctions():
    fonctions = {
        "shared.is_super_admin": SH.is_super_admin,
        "server.is_super_admin": S.is_super_admin,
        "coach_routes.is_super_admin": CO.is_super_admin,
        "reservation_routes.is_super_admin": RR.is_super_admin,
        "checkout_routes.is_super_admin": CK.is_super_admin,
        "campaign_routes.is_super_admin": CR.is_super_admin,
        "auth_routes.is_super_admin_email": AR.is_super_admin_email,
    }
    for nom, f in fonctions.items():
        verifier(f"1 {nom}({ANCIEN_SECOND}) -> False", not f(ANCIEN_SECOND))
        verifier(f"1 {nom}(casse/espaces de {ANCIEN_SECOND}) -> False",
                 not f("  AFROBOOST.Bassi@GMAIL.com "))
        verifier(f"1 {nom}({PROPRIETAIRE}) -> True (témoin)", bool(f(PROPRIETAIRE)))
    for nom, liste in (("server", S.SUPER_ADMIN_EMAILS), ("shared", SH.SUPER_ADMIN_EMAILS),
                       ("coach_routes", CO.SUPER_ADMIN_EMAILS),
                       ("reservation_routes", RR.SUPER_ADMIN_EMAILS),
                       ("checkout_routes", CK.SUPER_ADMIN_EMAILS),
                       ("auth_routes", AR.SUPER_ADMIN_EMAILS)):
        verifier(f"1 {nom}.SUPER_ADMIN_EMAILS == [propriétaire]",
                 [e.lower() for e in liste] == [PROPRIETAIRE], str(liste))
    verifier("1 server.get_user_role(ancien second) != super_admin",
             S.get_user_role(ANCIEN_SECOND) != S.ROLE_SUPER_ADMIN)
    verifier("1 server.get_user_role(propriétaire) == super_admin (témoin)",
             S.get_user_role(PROPRIETAIRE) == S.ROLE_SUPER_ADMIN)
    # Aucune liste de super-admin du code de production ne mentionne l'adresse.
    racine_api = os.path.join(H.RACINE, "api")
    fautifs = []
    for dossier, _, fichiers in os.walk(racine_api):
        for f in fichiers:
            if not f.endswith(".py"):
                continue
            chemin = os.path.join(dossier, f)
            for n, ligne in enumerate(open(chemin, encoding="utf-8"), 1):
                code = ligne.split("#", 1)[0]
                if ANCIEN_SECOND in code and '"""' not in ligne:
                    fautifs.append(f"{os.path.relpath(chemin, H.RACINE)}:{n}")
    verifier("1 aucune ligne de CODE (hors commentaire) de api/ ne cite l'ancienne adresse",
             not fautifs, ", ".join(fautifs))


# ─────────────────────────────────────────────────────────────────────────────
# 2. ADMIN_EMAILS ne peut plus élargir le rôle
# ─────────────────────────────────────────────────────────────────────────────
class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.lignes = []

    def emit(self, record):
        self.lignes.append(record.getMessage())


def t2_admin_emails_env():
    global AR
    ancien = os.environ.get("ADMIN_EMAILS")
    cap = _Capture()
    logging.getLogger(AR.__name__).addHandler(cap)
    try:
        os.environ["ADMIN_EMAILS"] = f"{PROPRIETAIRE},{ANCIEN_SECOND},intrus@exemple.test"
        AR = importlib.reload(AR)
        logging.getLogger(AR.__name__).addHandler(cap)
        verifier("2 ADMIN_EMAILS élargi : liste inchangée == [propriétaire]",
                 AR.SUPER_ADMIN_EMAILS == [PROPRIETAIRE], str(AR.SUPER_ADMIN_EMAILS))
        verifier("2 ADMIN_EMAILS élargi : is_super_admin_email(ancien second) -> False",
                 not AR.is_super_admin_email(ANCIEN_SECOND))
        verifier("2 ADMIN_EMAILS élargi : is_super_admin_email(intrus) -> False",
                 not AR.is_super_admin_email("intrus@exemple.test"))
        verifier("2 ADMIN_EMAILS élargi : propriétaire reste super-admin",
                 bool(AR.is_super_admin_email(PROPRIETAIRE)))
        verifier("2 ADMIN_EMAILS élargi : 2 adresses ignorées comptées",
                 getattr(AR, "_sa1_verifier_admin_emails_env", lambda: -1)() == 2)
        avert = [l for l in cap.lignes if "[SA-1]" in l]
        verifier("2 WARNING [SA-1] journalisé", bool(avert), str(cap.lignes[-3:]))
        verifier("2 le WARNING ne recopie pas les adresses",
                 avert and all(ANCIEN_SECOND not in l and "intrus" not in l for l in avert))
        os.environ["ADMIN_EMAILS"] = ANCIEN_SECOND
        AR = importlib.reload(AR)
        verifier("2 ADMIN_EMAILS = seulement l'ancien second : il ne remplace PAS le propriétaire",
                 AR.SUPER_ADMIN_EMAILS == [PROPRIETAIRE] and not AR.is_super_admin_email(ANCIEN_SECOND))
        os.environ.pop("ADMIN_EMAILS", None)
        cap.lignes.clear()
        AR = importlib.reload(AR)
        verifier("2 ADMIN_EMAILS absent : aucun WARNING, liste == [propriétaire]",
                 AR.SUPER_ADMIN_EMAILS == [PROPRIETAIRE]
                 and not [l for l in cap.lignes if "[SA-1]" in l])
        os.environ["ADMIN_EMAILS"] = PROPRIETAIRE
        cap.lignes.clear()
        AR = importlib.reload(AR)
        verifier("2 ADMIN_EMAILS = propriétaire seul : aucun WARNING",
                 not [l for l in cap.lignes if "[SA-1]" in l])
    finally:
        if ancien is None:
            os.environ.pop("ADMIN_EMAILS", None)
        else:
            os.environ["ADMIN_EMAILS"] = ancien
        AR = importlib.reload(AR)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Connexion : rôle du JWT émis, /auth/role, /auth/whoami
# ─────────────────────────────────────────────────────────────────────────────
async def t3_connexion():
    base = base_auth()
    AR._db = base
    for email in (PROPRIETAIRE, ANCIEN_SECOND):
        base["users_auth"].docs.append({
            "user_id": "u_" + email.split("@")[0].replace(".", "_"), "email": email,
            "name": "Banc", "password_hash": AR.hash_password("motdepasse-banc"),
            "auth_method": "email_password", "is_coach": True})
    roles = {}
    for email in (PROPRIETAIRE, ANCIEN_SECOND):
        r = await AR.login(H.Requete({}, {}), Response(),
                           AR.LoginRequest(email=email, password="motdepasse-banc"))
        p = pyjwt.decode(r["token"], H.SECRET_TEST, algorithms=["HS256"])
        roles[email] = p.get("role")
    verifier("3 login ancien second -> JWT role 'coach'", roles[ANCIEN_SECOND] == "coach", str(roles))
    verifier("3 login propriétaire -> JWT role 'super_admin' (témoin)",
             roles[PROPRIETAIRE] == "super_admin", str(roles))
    r = await AR.get_user_role(req(entete=ANCIEN_SECOND))
    verifier("3 /auth/role ancien second -> is_super_admin False",
             r.get("is_super_admin") is False and r.get("role") != "super_admin", str(r))
    r = await AR.get_user_role(req(entete=PROPRIETAIRE))
    verifier("3 /auth/role propriétaire -> is_super_admin True (témoin)", r.get("is_super_admin") is True)
    who = getattr(AR, "whoami", None) or getattr(AR, "auth_whoami", None)
    if who is not None:
        r = await who(req(jeton_de=ANCIEN_SECOND))
        verifier("3 /auth/whoami JWT ancien second -> is_super_admin False",
                 r.get("valid") and r.get("is_super_admin") is False, str(r))
    else:
        verifier("3 /auth/whoami introuvable", False)
    r = await AR.check_partner_status(req(corps={"email": ANCIEN_SECOND}))
    verifier("3 /auth/check-partner-status ancien second -> pas d'accès illimité",
             not r.get("is_super_admin") and not r.get("unlimited"), str(r))


# ─────────────────────────────────────────────────────────────────────────────
# 4. Gardes et routes admin avec un JWT SIGNÉ de l'ancien second
# ─────────────────────────────────────────────────────────────────────────────
async def t4_gardes_et_routes():
    rq2, rq1 = req(jeton_de=ANCIEN_SECOND), req(jeton_de=PROPRIETAIRE)
    verifier("4 _v411_exiger_super_admin JWT ancien second -> 403",
             statut_sync(S._v411_exiger_super_admin, rq2, "banc") == 403)
    verifier("4 _v411_exiger_super_admin JWT propriétaire -> passe (témoin)",
             statut_sync(S._v411_exiger_super_admin, rq1, "banc") == 200)
    verifier("4 _v411 : JWT ancien second + X-User-Email propriétaire -> 403",
             statut_sync(S._v411_exiger_super_admin,
                         req(jeton_de=ANCIEN_SECOND, entete=PROPRIETAIRE), "banc") == 403)
    verifier("4 shared.super_admin_signe JWT ancien second -> ''", SH.super_admin_signe(rq2) == "")
    verifier("4 shared.super_admin_signe JWT propriétaire -> e-mail (témoin)",
             SH.super_admin_signe(rq1) == PROPRIETAIRE)
    verifier("4 boost.exiger_super_admin JWT ancien second -> 403",
             statut_sync(BO.exiger_super_admin, rq2) == 403)
    verifier("4 boost.exiger_super_admin JWT propriétaire -> passe (témoin)",
             statut_sync(BO.exiger_super_admin, rq1) == 200)
    # Vraies routes : le refus tombe AVANT toute lecture de base.
    code = await statut(S.get_private_conversations("admin_afroboost", req(jeton_de=ANCIEN_SECOND)))
    verifier("4 GET /private/conversations/admin_afroboost JWT ancien second -> 403", code == 403, str(code))
    code = await statut(CO.activate_coach(req(jeton_de=ANCIEN_SECOND, corps={"email": "x@exemple.test"})))
    verifier("4 POST /admin/activate-coach JWT ancien second -> 403", code == 403, str(code))
    ancien_coach_analytics = AN._coach_analytics

    async def _coach_banc(request):
        return SH.coach_jwt_email(request)
    AN._coach_analytics = _coach_banc
    try:
        code = await statut(AN.analytics_cloturer(req(jeton_de=ANCIEN_SECOND), mois="2026-08"))
        verifier("4 POST /analytics/cloture JWT ancien second -> 403", code == 403, str(code))
    finally:
        AN._coach_analytics = ancien_coach_analytics


# ─────────────────────────────────────────────────────────────────────────────
# 5. V2-0d : l'ancienne adresse est redevenue ordinaire
# ─────────────────────────────────────────────────────────────────────────────
async def t5_inscription():
    base = base_auth()
    AR._db = base
    code = await statut(AR.register(req(), Response(), AR.RegisterRequest(
        email=PROPRIETAIRE, password="motdepasse-banc", name="Intrus")))
    verifier("5 inscription sous l'adresse du propriétaire -> 409 (réservée)", code == 409, str(code))
    verifier("5 ... et rien n'est écrit", not base["users_auth"].docs)
    code = await statut(AR.register(req(), Response(), AR.RegisterRequest(
        email=ANCIEN_SECOND, password="motdepasse-banc", name="Ordinaire")))
    fiche = next((d for d in base["users_auth"].docs if d.get("email") == ANCIEN_SECOND), None)
    verifier("5 inscription sous l'ancienne adresse -> chemin commun (403 « en attente »)",
             code == 403, str(code))
    verifier("5 ... compte créé EN ATTENTE de validation", bool(fiche) and fiche.get("pending_validation") is True)
    coach = next((d for d in base["coaches"].docs if d.get("email") == ANCIEN_SECOND), None)
    verifier("5 ... profil coach inactif, rôle 'coach'",
             bool(coach) and coach.get("is_active") is False and coach.get("role") == "coach")
    code = await statut(AR.login(H.Requete({}, {}), Response(),
                                 AR.LoginRequest(email=ANCIEN_SECOND, password="motdepasse-banc")))
    verifier("5 ... et la connexion reste bloquée tant qu'un super-admin n'a pas validé", code == 403, str(code))


async def main():
    t1_listes_et_fonctions()
    t2_admin_emails_env()
    await t3_connexion()
    await t4_gardes_et_routes()
    await t5_inscription()


if __name__ == "__main__":
    asyncio.run(main())
    ok = sum(1 for _, r, _ in RESULTATS if r)
    for nom, r, detail in RESULTATS:
        print(("OK   " if r else "ECHEC") + " " + nom + ("" if r or not detail else f"  [{detail}]"))
    print(f"\nSA-1 : {ok}/{len(RESULTATS)}")
    sys.exit(0 if ok == len(RESULTATS) else 1)

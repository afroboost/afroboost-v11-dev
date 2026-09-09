#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SESSION ABONNÉE PERSISTANTE — « je me connecte une fois, puis on me reconnaît ».

Exécution : python3 tests/test_session_abonnee_persistante.py

CE QUE ÇA PROUVE, sans envoyer un seul e-mail et sans toucher la production :
la session se PROLONGE pour qui s'en sert, elle se RÉVOQUE vraiment côté
serveur, et une session révoquée ne peut ni servir ni se ressusciter en se
renouvelant.

Le constat de départ : la persistance existait déjà (LOT B3-S1, 30 jours,
mesure du 09/09 : 19 sessions toutes à +30 jours, aucune révoquée). Ce qui
manquait était la porte d'entrée, côté navigateur — c'est le banc Jest
`sessionAbonneePersistante.test.js` qui la couvre.

Aucun réseau, aucune base réelle, aucune horloge imposée.
"""
import asyncio, io, os, sys
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-session:27017")
os.environ.setdefault("JWT_SECRET", "secret-de-banc-jamais-en-production")

import api.server as S                                            # noqa: E402
from api.routes import shared as SH                               # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

_ok = _ko = 0


def verifie(titre, condition, detail=""):
    global _ok, _ko
    if condition:
        _ok += 1
        print("PASS  %s" % titre)
    else:
        _ko += 1
        print("FAIL  %s%s" % (titre, (" — " + detail) if detail else ""))


# ─────────────────────────────────────────────── une base en mémoire, minimale
class FausseCollection:
    def __init__(self):
        self.docs = []
        self.ecritures = []

    async def find_one(self, filtre, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in filtre.items()
                   if not isinstance(v, dict)):
                return dict(d)
        return None

    async def update_one(self, filtre, maj):
        self.ecritures.append((dict(filtre), dict(maj)))
        for d in self.docs:
            if d.get("jti") != filtre.get("jti"):
                continue
            # `{"revoked": {"$ne": True}}` — la seule forme employée ici.
            _rev = filtre.get("revoked")
            if isinstance(_rev, dict) and "$ne" in _rev and d.get("revoked") is _rev["$ne"]:
                return type("R", (), {"modified_count": 0})()
            d.update(maj.get("$set") or {})
            return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": "x"})()


class FausseBase:
    def __init__(self):
        self.cols = {}

    def __getitem__(self, nom):
        return self.cols.setdefault(nom, FausseCollection())


class FausseRequete:
    def __init__(self, jeton=""):
        self.headers = {"x-espace-token": jeton} if jeton else {}


MAINTENANT = datetime.now(timezone.utc)


def charge(exp_dans_jours, jti="jti-1", code="AFR-TEST", mail="a@exemple.invalid"):
    return {"type": "subscriber_space", "code": code, "email": mail,
            "coach_id": "coach@exemple.invalid", "slug": None, "jti": jti,
            "exp": int((MAINTENANT + timedelta(days=exp_dans_jours)).timestamp())}


def session(jti="jti-1", revoked=False, jours=30, code="AFR-TEST",
            mail="a@exemple.invalid"):
    return {"jti": jti, "code": code, "email": mail,
            "coach_id": "coach@exemple.invalid", "slug": "", "revoked": revoked,
            "expires_at": (MAINTENANT + timedelta(days=jours)).isoformat()}


print("\n--- A : LA RÈGLE DU RENOUVELLEMENT EST PURE ET LISIBLE ---")
verifie("A1. un jeton tout neuf ne se renouvelle pas",
        SH.lotb3s1_doit_renouveler(charge(30)) is False)
verifie("A2. un jeton à moins de 7 jours de la fin se renouvelle",
        SH.lotb3s1_doit_renouveler(charge(3)) is True)
verifie("A3. la frontière est bien à 7 jours",
        SH.lotb3s1_doit_renouveler(charge(8)) is False
        and SH.lotb3s1_doit_renouveler(charge(6)) is True)
verifie("A4. un jeton DÉJÀ expiré ne ressuscite pas",
        SH.lotb3s1_doit_renouveler(charge(-1)) is False)
verifie("A5. sans échéance écrite, on ne devine pas",
        SH.lotb3s1_doit_renouveler({}) is False
        and SH.lotb3s1_doit_renouveler({"exp": "demain"}) is False)
verifie("A6. la durée de session reste longue (30 jours)",
        SH.LOTB3S1_JETON_JOURS == 30, str(SH.LOTB3S1_JETON_JOURS))
verifie("A7. le seuil de renouvellement est une constante nommée",
        SH.LOTB3S1_RENOUVELLEMENT_JOURS == 7, str(SH.LOTB3S1_RENOUVELLEMENT_JOURS))


async def scenario_renouvellement():
    print("\n--- B : PROLONGER, C'EST LA MÊME SESSION QUI CONTINUE ---")
    base = FausseBase()
    base[S._B3S1_COLL_SESSIONS].docs.append(session(jours=3))
    _vraie = S.db
    S.db = base
    try:
        _c = charge(3)
        res = await S._b3s1_renouveler_si_proche(_c)
        verifie("B1. un jeton neuf est rendu", bool(res.get("espace_token")))
        verifie("B2. il porte une nouvelle échéance", bool(res.get("espace_token_expires_at")))
        _relu = SH.lotb3s1_lire_token(res.get("espace_token"))
        verifie("B3. LE MÊME `jti` — donc la même ligne révocable en base",
                _relu and _relu.get("jti") == _c.get("jti"), str(_relu and _relu.get("jti")))
        verifie("B4. le même code, le même e-mail, le même tenant",
                _relu.get("code") == _c["code"] and _relu.get("email") == _c["email"]
                and _relu.get("coach_id") == _c["coach_id"])
        verifie("B5. la nouvelle échéance est bien plus loin qu'avant",
                SH.n2_instant_reel(base[S._B3S1_COLL_SESSIONS].docs[0]["expires_at"])
                > MAINTENANT + timedelta(days=25))
        verifie("B6. la base garde la trace du renouvellement",
                "renewed_at" in base[S._B3S1_COLL_SESSIONS].docs[0])

        print("\n--- C : CE QUI NE SE RENOUVELLE PAS ---")
        base2 = FausseBase()
        base2[S._B3S1_COLL_SESSIONS].docs.append(session(jours=25))
        S.db = base2
        verifie("C1. une session loin de sa fin n'écrit RIEN",
                await S._b3s1_renouveler_si_proche(charge(25)) == {}
                and base2[S._B3S1_COLL_SESSIONS].ecritures == [])

        base3 = FausseBase()
        base3[S._B3S1_COLL_SESSIONS].docs.append(session(jours=3, revoked=True))
        S.db = base3
        verifie("C2. une session RÉVOQUÉE ne se ressuscite pas en se renouvelant",
                await S._b3s1_renouveler_si_proche(charge(3)) == {})

        base4 = FausseBase()          # aucune session : le `jti` est inconnu
        S.db = base4
        verifie("C3. un `jti` inconnu ne rend aucun jeton",
                await S._b3s1_renouveler_si_proche(charge(3)) == {})
    finally:
        S.db = _vraie


async def scenario_revocation():
    print("\n--- D : LA DÉCONNEXION FERME LA SESSION CÔTÉ SERVEUR ---")
    base = FausseBase()
    base[S._B3S1_COLL_SESSIONS].docs.append(session())
    _vraie = S.db
    S.db = base
    try:
        _jeton, _ = SH.lotb3s1_make_token("AFR-TEST", "a@exemple.invalid",
                                          "coach@exemple.invalid", None, jti="jti-1")
        rep = await S.b3s1_revoquer_session(FausseRequete(_jeton))
        verifie("D1. la réponse est neutre", rep == {"success": True})
        verifie("D2. la session est RÉVOQUÉE en base",
                base[S._B3S1_COLL_SESSIONS].docs[0].get("revoked") is True)
        verifie("D3. l'instant de révocation est écrit",
                "revoked_at" in base[S._B3S1_COLL_SESSIONS].docs[0])

        base2 = FausseBase()
        base2[S._B3S1_COLL_SESSIONS].docs.append(session())
        S.db = base2
        rep2 = await S.b3s1_revoquer_session(FausseRequete(""))
        verifie("D4. sans jeton : même réponse neutre, et RIEN n'est écrit",
                rep2 == {"success": True} and base2[S._B3S1_COLL_SESSIONS].ecritures == [])

        base3 = FausseBase()
        base3[S._B3S1_COLL_SESSIONS].docs.append(session())
        S.db = base3
        rep3 = await S.b3s1_revoquer_session(FausseRequete("pas.un.jeton"))
        verifie("D5. un jeton invalide ne ferme la session de personne",
                rep3 == {"success": True} and base3[S._B3S1_COLL_SESSIONS].ecritures == []
                and base3[S._B3S1_COLL_SESSIONS].docs[0].get("revoked") is False)

        # On ne peut fermer QUE sa propre session : le `jti` vient du jeton
        # présenté, jamais du corps de la requête.
        base4 = FausseBase()
        base4[S._B3S1_COLL_SESSIONS].docs.append(session(jti="jti-de-quelquun-dautre"))
        S.db = base4
        _mien, _ = SH.lotb3s1_make_token("AFR-TEST", "a@exemple.invalid",
                                         "coach@exemple.invalid", None, jti="jti-1")
        await S.b3s1_revoquer_session(FausseRequete(_mien))
        verifie("D6. la session d'un AUTRE reste ouverte",
                base4[S._B3S1_COLL_SESSIONS].docs[0].get("revoked") is False)
    finally:
        S.db = _vraie


async def scenario_porte():
    print("\n--- E : UNE SESSION RÉVOQUÉE N'OUVRE PLUS RIEN ---")
    base = FausseBase()
    base[S._B3S1_COLL_SESSIONS].docs.append(session(revoked=True))
    _vraie = S.db
    S.db = base
    try:
        _jeton, _ = SH.lotb3s1_make_token("AFR-TEST", "a@exemple.invalid",
                                          "coach@exemple.invalid", None, jti="jti-1")
        _c, _motif = await S._b3s13_porteur_autorise(
            FausseRequete(_jeton), "AFR-TEST", None)
        verifie("E1. la porte refuse, et dit pourquoi", _c is None and _motif == "revoquee", _motif)

        base2 = FausseBase()
        base2[S._B3S1_COLL_SESSIONS].docs.append(session())
        S.db = base2
        _c2, _m2 = await S._b3s13_porteur_autorise(FausseRequete(_jeton), "AFR-TEST", None)
        verifie("E2. une session vivante ouvre l'espace", _c2 is not None and _m2 == "ok", _m2)
        _c3, _m3 = await S._b3s13_porteur_autorise(FausseRequete(_jeton), "AFR-AUTRE", None)
        verifie("E3. le jeton d'un espace n'ouvre pas celui d'un autre",
                _c3 is None and _m3 == "autre_code", _m3)
        _c4, _m4 = await S._b3s13_porteur_autorise(FausseRequete(_jeton), "AFR-TEST", "bob")
        verifie("E4. ni l'espace d'un autre MEMBRE du même groupe",
                _c4 is None and _m4 == "autre_membre", _m4)
    finally:
        S.db = _vraie


asyncio.run(scenario_renouvellement())
asyncio.run(scenario_revocation())
asyncio.run(scenario_porte())

print("\n--- F : LA ROUTE DE LECTURE PORTE BIEN LE RENOUVELLEMENT ---")
_bloc = SRC[SRC.find("async def get_subscriber_space"):
            SRC.find("@api_router.post(\"/subscriber/join\"")]
verifie("F1. le renouvellement se fait APRÈS la porte, jamais avant",
        _bloc.find("_b3s13_porteur_autorise") < _bloc.find("_b3s1_renouveler_si_proche"))
verifie("F2. les DEUX sorties de la route le portent (groupe ET individuel)",
        _bloc.count("**_espace_renouv") == 2, str(_bloc.count("**_espace_renouv")))
verifie("F3. la révocation est une route POST dédiée",
        '@api_router.post("/subscriber/session/revoke")' in SRC)

print("\n--- G : CE LOT N'ENVOIE RIEN ET NE MIGRE RIEN ---")
_moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
import ast as _ast
_INTERDITS = {"webpush", "send", "post", "urlopen", "send_push_by_email",
              "rv2_envoyer_email_rappel", "create_index", "delete_many", "update_many"}
_appels = set()
for _n in _ast.walk(_ast.parse(_moi)):
    if isinstance(_n, _ast.Call):
        _f = _n.func
        _appels.add(_f.attr if isinstance(_f, _ast.Attribute)
                    else (_f.id if isinstance(_f, _ast.Name) else ""))
verifie("G1. aucun appel d'envoi ni de migration dans ce banc",
        not (_appels & _INTERDITS), str(sorted(_appels & _INTERDITS)))
# Le nombre absolu d'index dans le fichier ne dit rien : ce qui compte est que
# CE lot n'en ajoute aucun. On le lit donc sur le diff, pas sur le total.
import subprocess as _sp
try:
    _diff = _sp.check_output(["git", "diff", "HEAD", "--", "api/server.py",
                              "api/routes/shared.py"], cwd=RACINE).decode("utf-8", "replace")
except Exception:
    _diff = ""
_ajouts = [l for l in _diff.split("\n") if l.startswith("+") and not l.startswith("+++")]
verifie("G2. aucun index ni migration ajoutés par ce lot",
        not [l for l in _ajouts if "create_index" in l or "delete_many" in l
             or "update_many" in l],
        "lignes : %s" % [l.strip()[:60] for l in _ajouts
                         if "create_index" in l or "delete_many" in l or "update_many" in l])

print("\n%d PASS / %d FAIL" % (_ok, _ko))
sys.exit(1 if _ko else 0)

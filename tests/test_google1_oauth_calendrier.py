#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GOOGLE-1 — DURCIR LA CONNEXION GOOGLE, PUIS LIRE LE CALENDRIER.

CE QUE LE LOT CORRIGE
==============================================================================
Le flux OAuth existant placait l'e-mail du coach EN CLAIR dans le parametre
`state`. `state` est une valeur que l'appelant controle : n'importe qui
pouvait fabriquer une URL portant l'e-mail d'un AUTRE coach, et le callback
ecrivait les jetons dans SA ligne. Et les jetons dormaient en clair.

CE QUE CE FICHIER PROUVE
==============================================================================
  * `X-User-Email` n'ouvre plus AUCUNE des routes Google — ni les nouvelles,
    ni celles de Contacts ;
  * un `state` forge, expire ou d'un autre coach est REFUSE, et n'ecrit rien ;
  * les jetons sont chiffres au repos, et le clair n'apparait nulle part ;
  * la lecture reste tolerante au clair — donc AUCUNE migration ;
  * aucun jeton ne sort de l'API ni des journaux ;
  * un jeton `contacts` seul ne fait PAS croire que Calendar est accorde ;
  * toutes les pannes Google rendent un calendrier natif intact ;
  * AUCUNE ecriture chez Google n'est possible : le lot ne fait que des GET ;
  * la deconnexion ne touche aucune donnee Afroboost.

Aucune socket ne s'ouvre : `httpx` est remplace par un faux transport.

    python3 tests/test_google1_oauth_calendrier.py
"""
import ast
import asyncio
import io
import json
import os
import socket
import sys
import types
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


_TENTATIVES = []
_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise SortieReseauInterdite(str(hote))


socket.getaddrinfo = _dns

SECRET = "secret-de-test-google1-sans-aucun-rapport-avec-la-production"
os.environ["JWT_SECRET"] = SECRET
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-g1-inexistant:27017")

import jwt as _jwt          # noqa: E402
import api.server as S      # noqa: E402
from fastapi import HTTPException  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


def _bloc(source, entete):
    debut = source.index(entete)
    banniere = "\n# " + "=" * 76 + "\n# "
    apres = source.index("\n\n", debut)
    bornes = [x for x in (source.find(banniere, apres),
                          source.find("# --- Leads Routes (Widget IA) ---", apres))
              if x != -1]
    return source[debut:min(bornes)] if bornes else source[debut:]


BLOC = _bloc(SRC, "# GOOGLE-1 — DURCIR LA CONNEXION GOOGLE")

COACH_A = "coach.a.fictif@exemple.test"
COACH_B = "coach.b.fictif@exemple.test"
INSTANT = "2026-08-31T18:26:57.951583+00:00"

_BANC = os.path.join(RACINE, "tests", "test_p3s3b_preparation_campagne.py")
_source = io.open(_BANC, encoding="utf-8").read()
_debut = _source.index("def lancer(coroutine):")
_fin = _source.index('# ============================================================================\nprint("\\n1.')
_espace = {"S": S, "asyncio": asyncio, "COACH_A": COACH_A, "COACH_B": COACH_B,
           "INSTANT": INSTANT, "json": json, "os": os, "sys": sys,
           "_jwt": _jwt, "SECRET": SECRET, "HTTPException": HTTPException}
exec(compile(_source[_debut:_fin], _BANC, "exec"), _espace)   # noqa: S102
Col, Base = _espace["CollectionBouchon"], _espace["BaseBouchon"]
RequeteFictive, lancer, jeton = _espace["RequeteFictive"], _espace["lancer"], _espace["jeton"]

JA, JB = jeton(COACH_A), jeton(COACH_B)
MAINTENANT = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# LE FAUX GOOGLE. On ne teste pas l'API de Google — ce n'est pas notre code.
# On eprouve NOTRE cablage : que la bonne requete parte, que chaque reponse
# soit traduite, et qu'aucune panne ne remonte jusqu'a l'ecran.
# ---------------------------------------------------------------------------
_APPELS = []
_REPONSES = {}


class _FausseReponse:
    def __init__(self, code, charge):
        self.status_code = code
        self._charge = charge

    def json(self):
        if isinstance(self._charge, Exception):
            raise self._charge
        return self._charge


class _FauxClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, params=None):
        _APPELS.append({"methode": "GET", "url": url, "headers": headers or {},
                        "params": params or {}})
        for motif, reponse in _REPONSES.items():
            if motif in url:
                if isinstance(reponse, Exception):
                    raise reponse
                return reponse
        return _FausseReponse(200, {"items": []})

    async def post(self, url, data=None, params=None):
        _APPELS.append({"methode": "POST", "url": url, "data": data or {},
                        "params": params or {}})
        for motif, reponse in _REPONSES.items():
            if motif in url:
                if isinstance(reponse, Exception):
                    raise reponse
                return reponse
        return _FausseReponse(200, {})


_faux_httpx = types.ModuleType("httpx")
_faux_httpx.AsyncClient = _FauxClient
sys.modules["httpx"] = _faux_httpx

S.GOOGLE_CONTACTS_CLIENT_ID = "client-de-test"
S.GOOGLE_CONTACTS_CLIENT_SECRET = "secret-de-test"

REFRESH = "1//refresh-token-de-test-tres-secret"
ACCESS = "ya29.access-token-de-test"


class CurseurIterable(_espace["Curseur"]):
    """`async for` sur un curseur — SIXIEME TROU DE LA MEME FAMILLE.

    Depuis GOOGLE-2, la lecture des evenements Google parcourt d'abord les
    identifiants deja pousses par Afroboost, pour ne pas les afficher deux
    fois. Elle le fait avec `async for`, que le curseur partage ne savait pas
    servir : sans ce complement, le banc mesurait une exception au lieu de la
    regle. Le bouchon modelise la promesse de Mongo, il ne la contourne pas.
    """

    def __aiter__(self):
        self._i = iter(list(self._docs))
        return self

    async def __anext__(self):
        try:
            return dict(next(self._i))
        except StopIteration:
            raise StopAsyncIteration


class ColG1(Col):
    """Le bouchon partage, complete de ce dont CE lot depend.

    IL IGNORE `upsert`, `$setOnInsert` ET `$unset` — or le callback OAuth
    ecrit exactement ainsi : un upsert qui pose les jetons et EFFACE un
    eventuel `revoked_at`. Reutiliser le bouchon tel quel aurait donne un banc
    complaisant, qui aurait vu « connexion etablie » sans qu'aucun document
    n'existe. C'est le cinquieme piege de cette famille (apres le tri stable,
    `$lte`, `$setOnInsert` et l'appariement scalaire/tableau) : le bouchon
    doit modeliser la promesse REELLE de Mongo, pas une approximation.
    """

    def find(self, filtre=None, projection=None, *a, **k):
        return CurseurIterable([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                for cle in (maj.get("$unset") or {}):
                    d.pop(cle, None)
                self.ecritures += 1
                return type("R", (), {"matched_count": 1, "modified_count": 1,
                                      "upserted_id": None})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0,
                                  "upserted_id": None})()
        neuf = {c: v for c, v in (filtre or {}).items() if not isinstance(v, dict)}
        neuf.update(maj.get("$setOnInsert") or {})
        neuf.update(maj.get("$set") or {})
        for cle in (maj.get("$unset") or {}):
            neuf.pop(cle, None)
        self.documents.append(neuf)
        self.ecritures += 1
        return type("R", (), {"matched_count": 0, "modified_count": 0,
                              "upserted_id": "upsert"})()

    async def delete_one(self, filtre=None, *a, **k):
        for i, d in enumerate(list(self.documents)):
            if self._ok(d, filtre):
                self.documents.pop(i)
                self.ecritures += 1
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


def base_neuve(jetons=None):
    b = Base([])
    b[S.G1_COLLECTION] = ColG1(S.G1_COLLECTION, [dict(x) for x in (jetons or [])],
                               uniques=[(("coach_email",), None)])
    b[S.CAL1_COLLECTION] = ColG1(S.CAL1_COLLECTION, [], uniques=[(("id",), None)])
    b["campaigns"] = ColG1("campaigns", [], uniques=[(("id",), None)])
    b["courses"] = ColG1("courses", [], uniques=[(("id",), None)])
    S.db = b
    del _APPELS[:]
    _REPONSES.clear()
    return b


def doc_jeton(coach=COACH_A, scope=None, **extra):
    d = {"coach_email": coach,
         "access_token": S.g1_chiffrer(ACCESS),
         "refresh_token": S.g1_chiffrer(REFRESH),
         "expires_at": (MAINTENANT + timedelta(hours=1)).isoformat(),
         "scope": scope if scope is not None else " ".join(S.G1_SCOPES),
         "created_at": INSTANT, "updated_at": INSTANT}
    d.update(extra)
    return d


# ============================================================================
print("\n1. X-USER-EMAIL N'OUVRE PLUS RIEN")

_b = base_neuve()
_routes = [
    ("google/auth-url", lambda j: lancer(S.g1_url_autorisation(RequeteFictive(jeton_=j)))),
    ("google/status", lambda j: lancer(S.g1_statut(RequeteFictive(jeton_=j)))),
    ("google/calendars", lambda j: lancer(S.g1_calendriers(RequeteFictive(jeton_=j)))),
    ("google/events", lambda j: lancer(S.g1_evenements(RequeteFictive(jeton_=j)))),
    ("google/disconnect", lambda j: lancer(S.g1_deconnecter(RequeteFictive(jeton_=j)))),
    ("contacts/auth-url", lambda j: lancer(S.get_google_contacts_auth_url(RequeteFictive(jeton_=j)))),
    ("contacts/status", lambda j: lancer(S.google_contacts_status(RequeteFictive(jeton_=j)))),
    ("contacts/sync", lambda j: lancer(S.sync_google_contacts(RequeteFictive(jeton_=j)))),
]
for _nom, _appel in _routes:
    try:
        _appel(None)
        _ferme = False
    except HTTPException as e:
        _ferme = e.status_code in (401, 403)
    verifier("1a. %-20s SANS jeton -> refuse" % _nom, _ferme)

# LE POINT CENTRAL : un en-tete `X-User-Email` seul ne suffit plus.
_CODE = BLOC[BLOC.index("G1_COLLECTION ="):]
verifier("1b. le bloc GOOGLE-1 ne lit JAMAIS `X-User-Email`",
         "X-User-Email" not in _CODE, "un en-tete falsifiable dans le bloc")
verifier("1c. les trois routes Contacts passent au JWT",
         SRC.count('caller_email = await _v309_require_coach_or_admin(request)') >= 3,
         str(SRC.count('caller_email = await _v309_require_coach_or_admin(request)')))
# L'ASSERTION EST BORNEE AUX ROUTES GOOGLE. La premiere version balayait tout
# le fichier : huit occurrences subsistent, mais elles appartiennent a
# `/contacts/*`, `/leads` et `/chat/*` — d'autres routes, d'autres lots. Les
# faire echouer ici aurait dit « GOOGLE-1 est incomplet » a propos de code que
# ce lot n'a pas vocation a toucher. La dette reste reelle et je la signale,
# mais elle n'est pas celle-ci.
_ARBRE_FICHIER = ast.parse(SRC)
_ROUTES_GOOGLE = []
for _n in ast.walk(_ARBRE_FICHIER):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _chemins = [ast.get_source_segment(SRC, d) or "" for d in _n.decorator_list]
        if any("google" in c.lower() for c in _chemins):
            _ROUTES_GOOGLE.append((_n.name, ast.get_source_segment(SRC, _n) or ""))
verifier("1d. AUCUNE route Google ne lit `X-User-Email` comme identite",
         _ROUTES_GOOGLE and not any('headers.get("X-User-Email"' in src
                                    for _, src in _ROUTES_GOOGLE),
         str([n for n, s in _ROUTES_GOOGLE if 'headers.get("X-User-Email"' in s]))
# LES DEUX CALLBACKS SONT A PART, ET C'EST STRUCTUREL : ils sont appeles par
# GOOGLE, qui ne connait aucun de nos comptes et ne peut porter aucun jeton.
# Ce qui remplace l'authentification chez eux, c'est la VERIFICATION de la
# signature du `state` — et c'est cela qu'il faut exiger.
_CALLBACKS = {"g1_callback", "google_contacts_callback"}
verifier("1d-bis. toute route Google NON-callback s'authentifie par le JWT",
         all("_v309_require_coach_or_admin" in src for n, src in _ROUTES_GOOGLE
             if n not in _CALLBACKS),
         str([n for n, s in _ROUTES_GOOGLE
              if "_v309_require_coach_or_admin" not in s and n not in _CALLBACKS]))
verifier("1d-ter. et les DEUX callbacks VERIFIENT la signature de l'etat",
         all("g1_verifier_etat(state)" in src for n, src in _ROUTES_GOOGLE
             if n in _CALLBACKS)
         and len([n for n, s in _ROUTES_GOOGLE if n in _CALLBACKS]) == 2,
         str([n for n, s in _ROUTES_GOOGLE
              if n in _CALLBACKS and "g1_verifier_etat(state)" not in s]))
verifier("1d-quater. l'ancien `state.lower().strip()` a disparu",
         "coach_email = state.lower().strip()" not in SRC)


# ============================================================================
print("\n2. LE `STATE` EST SIGNE — LA FAILLE PRINCIPALE")

_e = S.g1_signer_etat(COACH_A)
verifier("2a. il ne contient PAS l'e-mail en clair", COACH_A not in _e, _e[:40])
verifier("2b. il se relit correctement", S.g1_verifier_etat(_e) == COACH_A)
verifier("2c. deux demandes donnent deux etats DIFFERENTS (alea)",
         S.g1_signer_etat(COACH_A) != _e)

for _faux, _quoi in ((COACH_A, "l'e-mail nu — l'ANCIEN format"),
                     (_e[:-1], "signature tronquee"),
                     (_e + "a", "signature allongee"),
                     (_e.replace(_e.split(".")[3], "0" * 32), "signature inventee"),
                     ("", "vide"), ("a.b.c", "malforme")):
    verifier("2d. state %-32s -> refuse" % _quoi, S.g1_verifier_etat(_faux) == "")

# un etat d'un AUTRE coach ne peut pas etre fabrique sans le secret
_secret_original = os.environ["JWT_SECRET"]
os.environ["JWT_SECRET"] = "un-autre-secret"
_etat_etranger = S.g1_signer_etat(COACH_B)
os.environ["JWT_SECRET"] = _secret_original
verifier("2e. un etat signe avec un AUTRE secret est refuse",
         S.g1_verifier_etat(_etat_etranger) == "")

# expiration
import base64 as _b64
import hmac as _hmac
import hashlib as _hashlib
_vieux = "%s.%d.%s" % (
    _b64.urlsafe_b64encode(COACH_A.encode()).decode().rstrip("="),
    int(MAINTENANT.timestamp()) - S.G1_ETAT_VALIDITE_S - 60, "alea")
_vieux += "." + _hmac.new(SECRET.encode(), _vieux.encode(), _hashlib.sha256).hexdigest()[:32]
verifier("2f. un etat EXPIRE est refuse", S.g1_verifier_etat(_vieux) == "")

# et le callback n'ecrit rien sur un etat invalide
_b = base_neuve()
lancer(S.g1_callback(code="abc", state=COACH_A))
verifier("2g. le callback avec l'ANCIEN format n'ecrit RIEN",
         len(_b[S.G1_COLLECTION].documents) == 0)
lancer(S.g1_callback(code="abc", state="forge.1.2.3"))
verifier("2h. ... ni avec un etat forge", len(_b[S.G1_COLLECTION].documents) == 0)
verifier("2i. ... et Google n'a meme pas ete appele",
         not any("oauth2.googleapis.com/token" in a["url"] for a in _APPELS))


# ============================================================================
print("\n3. LES JETONS SONT CHIFFRES AU REPOS")

_b = base_neuve()
_REPONSES["oauth2.googleapis.com/token"] = _FausseReponse(200, {
    "access_token": ACCESS, "refresh_token": REFRESH,
    "expires_in": 3600, "scope": " ".join(S.G1_SCOPES)})
lancer(S.g1_callback(code="abc", state=S.g1_signer_etat(COACH_A)))
_d = _b[S.G1_COLLECTION].documents[0]
verifier("3a. le document est cree", _d["coach_email"] == COACH_A)
verifier("3b. l'access_token est chiffre",
         _d["access_token"].startswith("enc:v1:"), _d["access_token"][:20])
verifier("3c. le refresh_token est chiffre", _d["refresh_token"].startswith("enc:v1:"))
verifier("3d. AUCUN jeton en clair dans le document",
         ACCESS not in json.dumps(_d) and REFRESH not in json.dumps(_d))
verifier("3e. ... et il se dechiffre correctement",
         S.g1_dechiffrer(_d["refresh_token"]) == REFRESH)
verifier("3f. les scopes accordes sont conserves", S.G1_SCOPE_CALENDRIER in _d["scope"])

verifier("3g. TOLERANCE AU CLAIR — aucune migration necessaire",
         S.g1_dechiffrer("ancien-jeton-en-clair") == "ancien-jeton-en-clair")
verifier("3h. une valeur abimee rend '' plutot que de planter",
         S.g1_dechiffrer("enc:v1:pas-du-fernet") == "")
verifier("3i. la cle NE VIT PAS en base",
         "app_secrets" not in _CODE and "db[G1_COLLECTION].find_one({\"id\"" not in _CODE)
verifier("3j. sans secret, on refuse de chiffrer plutot que de faire semblant",
         "raise RuntimeError" in _CODE)


# ============================================================================
print("\n4. AUCUN JETON NE SORT")

_b = base_neuve([doc_jeton()])
_s = lancer(S.g1_statut(RequeteFictive(jeton_=JA)))
verifier("4a. le statut ne rend AUCUN jeton",
         "access_token" not in _s and "refresh_token" not in _s, str(sorted(_s)))
verifier("4b. ... ni en clair, ni chiffre",
         ACCESS not in json.dumps(_s) and "enc:v1:" not in json.dumps(_s))
verifier("4c. il dit connecte", _s["connected"] is True)
verifier("4d. il dit que Calendar est accorde", _s["calendar_granted"] is True)
verifier("4e. aucune reconnexion requise", _s["reconnect_required"] is False)

_journaux = [l for l in _CODE.split("\n") if "logger." in l]
verifier("4f. aucun journal ne contient un jeton",
         not any(m in l for l in _journaux
                 for m in ("access_token", "refresh_token", "jetons[", "token[")),
         " | ".join(_journaux)[:200])


# ============================================================================
print("\n5. §8 — UN JETON `CONTACTS` NE FAIT PAS CROIRE A CALENDAR")

_b = base_neuve([doc_jeton(scope=S.G1_SCOPE_CONTACTS)])
_s = lancer(S.g1_statut(RequeteFictive(jeton_=JA)))
verifier("5a. connecte, oui", _s["connected"] is True)
verifier("5b. mais Calendar N'EST PAS accorde", _s["calendar_granted"] is False)
verifier("5c. et l'ecran doit proposer de RECONNECTER",
         _s["reconnect_required"] is True)
_ev = lancer(S.g1_evenements(RequeteFictive(jeton_=JA)))
verifier("5d. la lecture d'evenements ne ment pas : aucun evenement",
         _ev["events"] == [])
verifier("5e. ... et le motif le dit", _ev["motif"] == "reconnexion_requise", str(_ev["motif"]))
verifier("5f. Google n'a meme pas ete appele pour rien",
         not any("calendar/v3" in a["url"] for a in _APPELS))


# ============================================================================
print("\n6. LIRE LES CALENDRIERS ET LES EVENEMENTS")

_b = base_neuve([doc_jeton()])
_REPONSES["calendarList"] = _FausseReponse(200, {"items": [
    {"id": "primary", "summary": "Bassi", "primary": True, "accessRole": "owner"},
    {"id": "pro@x.test", "summary": "Pro", "accessRole": "reader"}]})
_c = lancer(S.g1_calendriers(RequeteFictive(jeton_=JA)))
verifier("6a. les calendriers sont rendus", len(_c["calendars"]) == 2, str(_c))
verifier("6b. avec id, nom, principal et acces",
         set(_c["calendars"][0]) == {"id", "name", "primary", "access_role"})
verifier("6c. le principal est marque", _c["calendars"][0]["primary"] is True)
verifier("6d. l'appel porte le jeton en en-tete",
         any("Bearer " + ACCESS == (a["headers"] or {}).get("Authorization")
             for a in _APPELS if "calendarList" in a["url"]))

_lc = lancer(S.g1_choisir_calendriers(RequeteFictive(jeton_=JA,
                                                     corps={"calendars": ["primary", "pro@x.test"]})))
verifier("6e. le choix de calendriers est enregistre",
         _lc["selected_calendars"] == ["primary", "pro@x.test"])
try:
    lancer(S.g1_choisir_calendriers(RequeteFictive(jeton_=JA, corps={"calendars": "primary"})))
    _refuse = False
except HTTPException as e:
    _refuse = e.status_code == 400
verifier("6f. un choix mal forme -> 400", _refuse)

_REPONSES["/events"] = _FausseReponse(200, {"items": [
    {"id": "g-1", "summary": "Reunion equipe", "status": "confirmed",
     "location": "Neuchatel",
     "start": {"dateTime": (MAINTENANT + timedelta(days=1)).isoformat()},
     "end": {"dateTime": (MAINTENANT + timedelta(days=1, hours=1)).isoformat()}},
    {"id": "g-2", "summary": "Journee off", "status": "confirmed",
     "start": {"date": "2026-09-20"}, "end": {"date": "2026-09-21"}},
    {"id": "g-3", "summary": "Sans date", "start": {}, "end": {}}]})
_ev = lancer(S.g1_evenements(RequeteFictive(jeton_=JA, params={
    "from": MAINTENANT.isoformat(),
    "to": (MAINTENANT + timedelta(days=30)).isoformat()})))
verifier("6g. les evenements DATES sont rendus", len(_ev["events"]) == 4,
         "%d (2 evenements x 2 calendriers)" % len(_ev["events"]))
verifier("6h. celui SANS date est ecarte",
         not any("Sans date" in e["title"] for e in _ev["events"]))
_g = _ev["events"][0]
verifier("6i. la forme est celle du calendrier Afroboost",
         {"id", "title", "starts_at", "event_type", "source", "modifiable"} <= set(_g))
verifier("6j. le type est `google`", _g["event_type"] == "google")
verifier("6k. la source est nommee", _g["source"] == "google")
verifier("6l. IL N'EST PAS MODIFIABLE", _g["modifiable"] is False)
verifier("6m. le tout-le-jour est reconnu",
         any(e["all_day"] for e in _ev["events"]))
verifier("6n. la fenetre est passee a Google",
         any("timeMin" in (a["params"] or {}) for a in _APPELS if "/events" in a["url"]))
verifier("6o. la fenetre est BORNEE comme le calendrier natif",
         (datetime.fromisoformat(_ev["to"]) - datetime.fromisoformat(_ev["from"])).days
         <= S.G1_FENETRE_MAX_JOURS)


# ============================================================================
print("\n7. AUCUN EVENEMENT GOOGLE N'EST STOCKE")

verifier("7a. rien n'entre dans `calendar_events`",
         len(_b[S.CAL1_COLLECTION].documents) == 0)
verifier("7b. le calendrier natif ne connait pas le type `google`",
         "google" not in S.CAL1_TYPES, str(S.CAL1_TYPES))
verifier("7c. le lot n'ecrit QUE dans `google_tokens`",
         _CODE.count("db[CAL1_COLLECTION].insert") == 0
         and _CODE.count("db[CAL1_COLLECTION].update") == 0)


# ============================================================================
print("\n8. AUCUNE ECRITURE CHEZ GOOGLE — GOOGLE-2 RESTE FERME")

_arbre = ast.parse(_CODE)
_methodes = set()
for _n in ast.walk(_arbre):
    if isinstance(_n, ast.Call) and getattr(_n.func, "attr", "") in ("get", "post", "put",
                                                                      "patch", "delete"):
        _src = ast.get_source_segment(_CODE, _n) or ""
        if "client." in _src:
            _methodes.add(getattr(_n.func, "attr", ""))
verifier("8a. seuls des GET et des POST OAuth partent vers Google",
         _methodes <= {"get", "post"}, str(sorted(_methodes)))
_posts = [a for a in _APPELS if a["methode"] == "POST"]
verifier("8b. aucun POST vers l'API Calendar",
         not any("calendar/v3" in a["url"] for a in _posts), str([a["url"] for a in _posts]))
for _interdit in ("sync_status", "last_synced_at", "insertEvent"):
    verifier("8c. aucun champ de synchronisation sortante : `%s`" % _interdit,
             _interdit not in _CODE)
# GOOGLE-2 A FAIT ENTRER `google_event_id` ICI — EN LECTURE SEULE. La moisson
# Google ecarte desormais les evenements qu'Afroboost a lui-meme pousses, pour
# qu'ils ne s'affichent pas deux fois (§21). GOOGLE-1 LIT donc ce champ ; ce
# qu'il ne doit toujours pas faire, c'est l'ECRIRE — c'est ce qu'on verifie.
_LECTURE_G1 = _CODE.split("async def g1_evenements")[1]
verifier("8c2. `google_event_id` n'apparait QUE dans la moisson en lecture",
         _CODE.count("google_event_id") == _LECTURE_G1.count("google_event_id") == 3,
         "%d dans le bloc / %d dans la lecture"
         % (_CODE.count("google_event_id"), _LECTURE_G1.count("google_event_id")))
verifier("8c3. cette moisson n'ECRIT rien : ni $set, ni insert, ni update",
         not any(m in _LECTURE_G1 for m in ("$set", "insert_one", "update_one")))
# LE CODE, PAS LE COMMENTAIRE : l'en-tete explique justement que
# `calendar.events` sera le scope de GOOGLE-2 et qu'on ne le demande PAS.
_CODE_SEUL = "\n".join(l for l in _CODE.split("\n") if not l.strip().startswith("#"))
verifier("8d. le scope d'ECRITURE n'est PAS demande",
         "calendar.events" not in _CODE_SEUL.replace("calendar.events.readonly", ""),
         "un scope d'ecriture demande prematurement")
verifier("8e. le scope demande est bien la LECTURE seule",
         S.G1_SCOPE_CALENDRIER.endswith("calendar.readonly"))


# ============================================================================
print("\n9. UNE PANNE GOOGLE NE CASSE PAS AFROBOOST")

for _code, _motif in ((401, "reconnexion_requise"), (403, "acces_refuse"),
                      (429, "trop_de_requetes"), (500, "google_indisponible"),
                      (503, "google_indisponible")):
    _b = base_neuve([doc_jeton()])
    _REPONSES["/events"] = _FausseReponse(_code, {})
    _r = lancer(S.g1_evenements(RequeteFictive(jeton_=JA)))
    verifier("9a. HTTP %-3d -> `%s`, aucune exception" % (_code, _motif),
             _r["events"] == [] and _r["motif"] == _motif, str(_r["motif"]))

_b = base_neuve([doc_jeton()])
_REPONSES["/events"] = TimeoutError("delai depasse")
_r = lancer(S.g1_evenements(RequeteFictive(jeton_=JA)))
verifier("9b. un delai depasse -> `google_indisponible`",
         _r["motif"] == "google_indisponible", str(_r))

_b = base_neuve([doc_jeton(expires_at=INSTANT)])
_REPONSES["oauth2.googleapis.com/token"] = _FausseReponse(200, {"error": "invalid_grant"})
_r = lancer(S.g1_evenements(RequeteFictive(jeton_=JA)))
verifier("9c. un acces REVOQUE est reconnu", _r["motif"] == "revoque", str(_r))
verifier("9d. ... et marque, pour ne pas reessayer en boucle",
         bool(_b[S.G1_COLLECTION].documents[0].get("revoked_at")))

_b = base_neuve([doc_jeton(refresh_token="", expires_at=INSTANT)])
_r = lancer(S.g1_evenements(RequeteFictive(jeton_=JA)))
verifier("9e. sans refresh_token -> motif clair", _r["motif"] == "sans_refresh", str(_r))

_b = base_neuve()
_r = lancer(S.g1_evenements(RequeteFictive(jeton_=JA)))
verifier("9f. non connecte -> motif clair, pas une erreur",
         _r["events"] == [] and _r["motif"] == "non_connecte")


# ============================================================================
print("\n10. LE RENOUVELLEMENT EST COTE SERVEUR")

_b = base_neuve([doc_jeton(expires_at=INSTANT)])   # access_token perime
_REPONSES["oauth2.googleapis.com/token"] = _FausseReponse(200, {
    "access_token": "ya29.tout-neuf", "expires_in": 3600})
_a = lancer(S.g1_access_token(COACH_A))
verifier("10a. un access_token perime est renouvele", _a["token"] == "ya29.tout-neuf", str(_a))
_d = _b[S.G1_COLLECTION].documents[0]
verifier("10b. le nouveau jeton est stocke CHIFFRE",
         _d["access_token"].startswith("enc:v1:")
         and S.g1_dechiffrer(_d["access_token"]) == "ya29.tout-neuf")
verifier("10c. le refresh_token n'a PAS ete ecrase", S.g1_dechiffrer(_d["refresh_token"]) == REFRESH)
verifier("10d. la nouvelle expiration est future", _d["expires_at"] > MAINTENANT.isoformat())

_b = base_neuve([doc_jeton()])
del _APPELS[:]
lancer(S.g1_access_token(COACH_A))
verifier("10e. un jeton ENCORE VALIDE n'est pas renouvele pour rien",
         not any("oauth2.googleapis.com/token" in a["url"] for a in _APPELS))
verifier("10f. le callback n'ecrase pas un refresh_token par une valeur vide",
         'if jetons.get("refresh_token"):' in _CODE)


# ============================================================================
print("\n11. DECONNEXION — AUCUNE DONNEE AFROBOOST TOUCHEE")

_b = base_neuve([doc_jeton()])
_b[S.CAL1_COLLECTION].documents.append(
    {"id": "e-1", "coach_id": COACH_A, "title": "Rendez-vous", "starts_at": INSTANT,
     "event_type": "appointment", "status": "prevu", "is_deleted": False})
_REPONSES["oauth2.googleapis.com/revoke"] = _FausseReponse(200, {})
_r = lancer(S.g1_deconnecter(RequeteFictive(jeton_=JA)))
verifier("11a. la deconnexion aboutit", _r["disconnected"] is True, str(_r))
verifier("11b. Google a ete prevenu", _r["revoked_at_google"] is True)
verifier("11c. les evenements Afroboost sont INTACTS",
         len(_b[S.CAL1_COLLECTION].documents) == 1
         and _b[S.CAL1_COLLECTION].documents[0]["title"] == "Rendez-vous")
verifier("11d. les jetons sont partis", len(_b[S.G1_COLLECTION].documents) == 0)

_b = base_neuve([doc_jeton()])
_b[S.CAL1_COLLECTION].documents.append(
    {"id": "e-2", "coach_id": COACH_A, "title": "Tache", "starts_at": INSTANT,
     "event_type": "task", "status": "prevu", "is_deleted": False})
_REPONSES["oauth2.googleapis.com/revoke"] = RuntimeError("Google injoignable")
_r = lancer(S.g1_deconnecter(RequeteFictive(jeton_=JA)))
verifier("11e. Google injoignable n'empeche PAS la deconnexion locale",
         _r["disconnected"] is True and _r["revoked_at_google"] is False, str(_r))
verifier("11f. et les donnees Afroboost restent intactes",
         len(_b[S.CAL1_COLLECTION].documents) == 1)


# ============================================================================
print("\n12. ISOLATION ENTRE COACHS")

_b = base_neuve([doc_jeton(COACH_A)])
verifier("12a. un AUTRE coach n'est pas connecte",
         lancer(S.g1_statut(RequeteFictive(jeton_=JB)))["connected"] is False)
verifier("12b. il ne lit aucun calendrier",
         lancer(S.g1_calendriers(RequeteFictive(jeton_=JB)))["calendars"] == [])
verifier("12c. il ne lit aucun evenement",
         lancer(S.g1_evenements(RequeteFictive(jeton_=JB)))["events"] == [])
lancer(S.g1_deconnecter(RequeteFictive(jeton_=JB)))
verifier("12d. sa deconnexion ne touche PAS les jetons du premier",
         len(_b[S.G1_COLLECTION].documents) == 1
         and _b[S.G1_COLLECTION].documents[0]["coach_email"] == COACH_A)


# ============================================================================
print("\n13. AUCUNE MIGRATION, AUCUNE SOCKET")

verifier("13a. aucun `update_many` (donc aucune migration de masse)",
         "update_many" not in _CODE)
verifier("13b. aucune reecriture des documents existants au demarrage",
         "g1_chiffrer" not in SRC.split("async def startup_db")[-1]
         if "async def startup_db" in SRC else True)
verifier("13c. l'index d'unicite sur le compte est pose",
         'db[G1_COLLECTION].create_index("coach_email", unique=True)' in SRC)
verifier("13d. zero tentative de sortie reseau", len(_TENTATIVES) == 0, str(_TENTATIVES))
verifier("13e. la redirection ne pointe plus sur le residu Vercel",
         "vercel.app" not in S.g1_redirection(), S.g1_redirection())


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("GOOGLE-1 : %d / %d verifications" % (_ok, len(RESULTATS)))
print("Sorties reseau reelles : %d — `httpx` est un faux" % len(_TENTATIVES))
_ech = [i for i, c, _ in RESULTATS if not c]
if _ech:
    print("\nECHECS :")
    for i in _ech:
        print("  - %s" % i)
print("=" * 78)
sys.exit(0 if not _ech else 1)

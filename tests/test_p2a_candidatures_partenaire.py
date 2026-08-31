#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2-A — LES CANDIDATURES PARTENAIRE SONT-ELLES LISIBLES, ET PAR QUI ?

CE QUE CE LOT CORRIGE
==============================================================================
Le tunnel « Devenir Partenaire Afroboost » (`link_token = 807fe7`) enregistre des
candidatures depuis P1.2. Rien ne les affichait : `GET /api/leads` n'a aucun
appelant cote navigateur, et les badges de la carte comptent des clics, des
questions et des actions — jamais des candidatures. Le coach ne recevait qu'une
notification « Nouveau prospect ». Les reponses etaient en base, personne ne
pouvait les lire.

CE QUE CE FICHIER PROUVE
==============================================================================
Deux moities, et il faut les deux :

  * LA PORTE REFUSE — anonyme, `X-User-Email` forge, JWT invalide, jeton ABONNE,
    jeton d'ESPACE abonne, et un AUTRE coach que le proprietaire du lien.
  * LA PORTE S'OUVRE — le coach proprietaire et le super-admin obtiennent la
    liste, et ce qui en sort est exactement ce qu'on attend : les candidatures du
    SEUL lien demande, triees de la plus recente a la plus ancienne, avec leurs
    reponses intactes.

Et, tout du long : AUCUNE ECRITURE. La base est un bouchon qui COMPTE les
ecritures ; le compteur doit rester a zero. C'est le point le plus important d'un
lot annonce « strictement en lecture ».

LE PIEGE QUE COUVRE LA SECTION 3
==============================================================================
`application_decision` n'existe sur aucun document en base. La route doit rendre
« pending » SANS l'ecrire — sinon l'affichage d'un mot deviendrait une migration
de 150 documents. Le test verifie donc les deux faces : la valeur sort bien, et
rien n'a ete ecrit pour la produire.

    python3 tests/test_p2a_candidatures_partenaire.py
"""
import ast
import asyncio
import os
import re
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


# ============================================================================
# Bouchons — aucune base reelle, aucun reseau, aucune donnee de production
# ============================================================================
SECRET_FICTIF = "secret-de-test-p2a-sans-aucun-rapport-avec-la-production"
ADMIN_FICTIF = "admin.fictif@exemple.test"
COACH_FICTIF = "coach.fictif@exemple.test"
AUTRE_COACH_FICTIF = "autre.coach.fictif@exemple.test"
MEMBRE_FICTIF = "membre.fictif@exemple.test"

os.environ["JWT_SECRET"] = SECRET_FICTIF
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-inexistant:27017")

import jwt as pyjwt  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


def _jeton(payload, minutes=60):
    maintenant = datetime.now(timezone.utc)
    corps = dict(payload)
    corps["iat"] = int(maintenant.timestamp())
    corps["exp"] = int((maintenant + timedelta(minutes=minutes)).timestamp())
    j = pyjwt.encode(corps, SECRET_FICTIF, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


JETON_ADMIN = _jeton({"email": ADMIN_FICTIF, "role": "super_admin"})
JETON_COACH = _jeton({"email": COACH_FICTIF, "role": "coach"})
JETON_AUTRE_COACH = _jeton({"email": AUTRE_COACH_FICTIF, "role": "coach"})
JETON_ABONNE = _jeton({"type": "subscriber", "code": "AFR-TEST01", "email": MEMBRE_FICTIF})
JETON_ESPACE = _jeton({"type": "subscriber_space", "code": "AFR-TEST01",
                       "email": MEMBRE_FICTIF, "coach_id": COACH_FICTIF,
                       "slug": "test", "jti": "test-jti"})
JETON_MAUVAIS_SECRET = pyjwt.encode(
    {"email": ADMIN_FICTIF, "role": "super_admin",
     "exp": int((datetime.now(timezone.utc) + timedelta(minutes=60)).timestamp())},
    "un-autre-secret-qui-n-est-pas-le-bon", algorithm="HS256")
if isinstance(JETON_MAUVAIS_SECRET, bytes):
    JETON_MAUVAIS_SECRET = JETON_MAUVAIS_SECRET.decode("utf-8")


class RequeteFictive:
    def __init__(self, jeton=None, entete_email=None):
        e = {}
        if jeton:
            e["Authorization"] = "Bearer " + jeton
        if entete_email:
            e["X-User-Email"] = entete_email
        self.headers = e


class Curseur:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n):
        return list(self._docs)[:n]


class CollectionBouchon:
    """`find_one`/`find` honorent le filtre. TOUTE ecriture est COMPTEE."""

    def __init__(self, documents=None):
        self.documents = list(documents or [])
        self.ecritures = 0

    def _ok(self, doc, filtre):
        for cle, val in (filtre or {}).items():
            if str(cle).startswith("$"):
                continue
            if doc.get(cle) != val:
                return False
        return True

    async def find_one(self, filtre=None, projection=None, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                return dict(d)
        return None

    def find(self, filtre=None, projection=None, *a, **k):
        return Curseur([dict(d) for d in self.documents if self._ok(d, filtre)])

    async def update_one(self, *a, **k):
        self.ecritures += 1
        return None

    async def insert_one(self, *a, **k):
        self.ecritures += 1
        return None

    async def delete_one(self, *a, **k):
        self.ecritures += 1
        return None


# Deux liens PARTENAIRE de deux coachs differents, plus un lien participant :
# c'est ce qui permet de prouver le cloisonnement ET le refus par type.
LIENS = [
    {"link_token": "tok_partenaire", "title": "Devenir Partenaire (fictif)",
     "lead_type": "partner", "coach_id": COACH_FICTIF},
    {"link_token": "tok_autre_coach", "title": "Partenaire d'un autre coach",
     "lead_type": "partner", "coach_id": AUTRE_COACH_FICTIF},
    {"link_token": "tok_participant", "title": "Essai (fictif)",
     "lead_type": "participant", "coach_id": COACH_FICTIF},
    {"link_token": "tok_sans_proprietaire", "title": "Lien orphelin",
     "lead_type": "partner", "coach_id": ""},
]

# Volontairement DESORDONNES en base, et melanges avec le lien voisin : le tri et
# le cloisonnement doivent etre le fait de la route, pas de l'ordre d'insertion.
CANDIDATURES = [
    {"id": "c-milieu", "link_token": "tok_partenaire", "name": "Milieu Fictif",
     "email": "milieu@exemple.test", "whatsapp": "+41000000002",
     "answers": {"q_0": {"question": "Votre activite ?", "answer": "Salon fictif"},
                 "q_1": {"question": "Quelle collaboration ?", "answer": "Visibilite croisee"}},
     "source": "link_tok_partenaire", "created_at": "2026-08-20T10:00:00+00:00"},
    {"id": "c-ancienne", "link_token": "tok_partenaire", "name": "Ancienne Fictive",
     "email": "ancienne@exemple.test", "whatsapp": "+41000000001",
     "answers": {"q_0": {"question": "Votre activite ?", "answer": "Association fictive"}},
     "source": "link_tok_partenaire", "created_at": "2026-08-01T10:00:00+00:00",
     "submission_id": "sub-fictif-1"},
    {"id": "c-recente", "link_token": "tok_partenaire", "name": "Recente Fictive",
     "email": "recente@exemple.test", "whatsapp": "+41000000003",
     "answers": {"q_0": {"question": "Votre activite ?", "answer": "Commerce fictif"}},
     "source": "link_tok_partenaire", "createdAt": "2026-08-28T10:00:00+00:00"},
    {"id": "c-du-voisin", "link_token": "tok_autre_coach", "name": "Voisin Fictif",
     "email": "voisin@exemple.test", "whatsapp": "+41000000009",
     "answers": {"q_0": {"question": "Votre activite ?", "answer": "NE DOIT PAS FUIR"}},
     "source": "link_tok_autre_coach", "created_at": "2026-08-15T10:00:00+00:00"},
]


class BaseBouchon:
    def __init__(self):
        self.chat_sessions = CollectionBouchon(LIENS)
        self.leads = CollectionBouchon(CANDIDATURES)
        self.coaches = CollectionBouchon([{"email": COACH_FICTIF},
                                          {"email": AUTRE_COACH_FICTIF}])
        self.coach_auth = CollectionBouchon([])

    def __getattr__(self, nom):
        return CollectionBouchon([])

    def total_ecritures(self):
        return sum(c.ecritures for c in
                   (self.chat_sessions, self.leads, self.coaches, self.coach_auth))


import api.server as S  # noqa: E402

S.db = BaseBouchon()
S.SUPER_ADMIN_EMAILS = [ADMIN_FICTIF]

try:
    asyncio.set_event_loop(asyncio.new_event_loop())
except Exception:
    pass


def appeler(jeton=None, entete=None, token="tok_partenaire"):
    coro = S.p2a_candidatures_partenaire(token, RequeteFictive(jeton, entete))
    try:
        return 200, asyncio.get_event_loop().run_until_complete(coro)
    except S.HTTPException as e:
        return e.status_code, getattr(e, "detail", "")


# ============================================================================
print("=" * 78)
print("P2-A — LECTURE DES CANDIDATURES PARTENAIRE")
print("=" * 78)

print("\n=== 1. LA PORTE REFUSE ===")

for intitule, jeton, entete in [
    ("1a. anonyme -> 403", None, None),
    ("1b. `X-User-Email` d'un admin, forge, sans jeton -> 403", None, ADMIN_FICTIF),
    ("1c. `X-User-Email` du proprietaire, forge -> 403", None, COACH_FICTIF),
    ("1d. jeton signe d'un AUTRE secret -> 403", JETON_MAUVAIS_SECRET, None),
    ("1e. jeton ABONNE -> 403", JETON_ABONNE, None),
    ("1f. jeton d'ESPACE ABONNE -> 403", JETON_ESPACE, None),
]:
    statut, _ = appeler(jeton, entete)
    verifier(intitule, statut == 403, "statut=%s" % statut)

statut, _ = appeler(JETON_AUTRE_COACH)
verifier("1g. un AUTRE coach ne lit pas les candidatures du proprietaire -> 403",
         statut == 403, "statut=%s" % statut)

statut, _ = appeler(JETON_COACH, token="tok_autre_coach")
verifier("1h. ... et la reciproque est vraie -> 403",
         statut == 403, "statut=%s" % statut)

statut, _ = appeler(JETON_COACH, token="tok_sans_proprietaire")
verifier("1i. un lien SANS proprietaire n'est pas « a tout le monde » -> 403",
         statut == 403, "statut=%s" % statut)


print("\n=== 2. LA PORTE S'OUVRE, ET NE LAISSE PASSER QUE CE QU'IL FAUT ===")

statut, rep = appeler(JETON_COACH)
verifier("2a. le coach PROPRIETAIRE obtient la liste",
         statut == 200 and isinstance(rep, dict), "statut=%s" % statut)
verifier("2b. ... avec le bon total",
         rep.get("total") == 3, "total=%s" % rep.get("total"))
verifier("2c. ... et le titre du lien",
         rep.get("title") == "Devenir Partenaire (fictif)")

noms = [c["id"] for c in rep.get("applications", [])]
verifier("2d. SEULES les candidatures du lien demande sortent",
         set(noms) == {"c-recente", "c-milieu", "c-ancienne"}, "ids=%s" % noms)
verifier("2e. AUCUNE fuite du lien voisin",
         "c-du-voisin" not in noms
         and not any("NE DOIT PAS FUIR" in str(c.get("answers")) for c in rep["applications"]))

verifier("2f. tri de la PLUS RECENTE a la plus ancienne",
         noms == ["c-recente", "c-milieu", "c-ancienne"], "ordre=%s" % noms)

statut_admin, rep_admin = appeler(JETON_ADMIN)
verifier("2g. le SUPER-ADMIN lit aussi, sans etre proprietaire",
         statut_admin == 200 and rep_admin.get("total") == 3,
         "statut=%s total=%s" % (statut_admin, rep_admin.get("total") if isinstance(rep_admin, dict) else "-"))

statut, detail = appeler(JETON_COACH, token="tok_participant")
verifier("2h. un lien qui n'est PAS partenaire est refuse -> 404",
         statut == 404, "statut=%s detail=%s" % (statut, detail))

statut, _ = appeler(JETON_COACH, token="tok_inexistant")
verifier("2i. un jeton de lien inconnu -> 404", statut == 404, "statut=%s" % statut)

statut, _ = appeler(JETON_COACH, token="x" * 200)
verifier("2j. un jeton absurdement long est ecarte sans requete -> 404",
         statut == 404, "statut=%s" % statut)


print("\n=== 3. LES DONNEES RENDUES ===")

premiere = rep["applications"][0]
CHAMPS = {"id", "submission_id", "link_token", "name", "email", "whatsapp",
          "answers", "source", "created_at", "application_decision"}
verifier("3a. exactement les champs prevus, ni plus ni moins",
         set(premiere.keys()) == CHAMPS,
         "en trop=%s / manquants=%s" % (set(premiere.keys()) - CHAMPS,
                                        CHAMPS - set(premiere.keys())))

verifier("3b. aucun champ interne ne fuit (_id, participant_id, session_id)",
         not any(k in premiere for k in ("_id", "participant_id", "session_id")))

milieu = [c for c in rep["applications"] if c["id"] == "c-milieu"][0]
verifier("3c. `answers` est rendu TEL QUEL, libelles compris",
         milieu["answers"]["q_0"]["question"] == "Votre activite ?"
         and milieu["answers"]["q_1"]["answer"] == "Visibilite croisee")

verifier("3d. les DEUX questions sont conservees, pas seulement la premiere",
         len(milieu["answers"]) == 2)

verifier("3e. `application_decision` absent en base -> « pending » rendu",
         all(c["application_decision"] == "pending" for c in rep["applications"]))

verifier("3f. `submission_id` present quand il existe, `None` sinon",
         [c["submission_id"] for c in rep["applications"]] == [None, None, "sub-fictif-1"],
         "%s" % [c["submission_id"] for c in rep["applications"]])

recente = [c for c in rep["applications"] if c["id"] == "c-recente"][0]
verifier("3g. `createdAt` (camel) est normalise en `created_at` — les deux "
         "familles de schema de `leads` sont reconciliees",
         recente["created_at"] == "2026-08-28T10:00:00+00:00",
         "created_at=%r" % recente["created_at"])


print("\n=== 4. AUCUNE ECRITURE, NULLE PART ===")

verifier("4a. le compteur d'ecritures est reste a ZERO sur toute la suite",
         S.db.total_ecritures() == 0, "ecritures=%d" % S.db.total_ecritures())
verifier("4b. ... y compris sur `leads` (pending n'est PAS persiste)",
         S.db.leads.ecritures == 0, "ecritures=%d" % S.db.leads.ecritures)


print("\n=== 5. LE CODE LIVRE DIT BIEN CE QU'ON CROIT ===")

SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_ARBRE = ast.parse(SRC)
_LIGNES = SRC.split("\n")


def _corps_de(nom):
    for n in ast.walk(_ARBRE):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nom:
            return "\n".join(_LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


def _code_python(source):
    """Le CODE EXECUTE seul : signature, docstring et commentaires retires.

    Sans ce nettoyage, ce fichier se piegeait lui-meme : la docstring de la
    route explique qu'elle n'emploie ni `X-User-Email` ni `$regex`, et une
    recherche naive trouvait ces mots... dans l'explication. Le meme piege a
    deja coute deux corrections sur CHAT-LOOP. On verifie le code execute.

    Les guillemets sont normalises : `ast.unparse` reecrit `"x"` en `'x'`, ce
    qui ferait echouer une comparaison litterale pour une raison sans rapport
    avec ce qu'on veut prouver.
    """
    fonction = ast.parse(source).body[0]
    corps = list(fonction.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    if not hasattr(ast, "unparse"):
        # Python < 3.9 : repli par retrait des lignes de commentaire.
        return "\n".join(l for l in source.split("\n")
                          if not l.strip().startswith("#")).replace("'", '"')
    return "\n".join(ast.unparse(n) for n in corps).replace("'", '"')


def _code_js(source):
    """Le CODE JS seul : lignes `//` et blocs `/* */` retires."""
    sans_bloc = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return "\n".join(l for l in sans_bloc.split("\n")
                      if not l.strip().startswith("//"))


CORPS = _code_python(_corps_de("p2a_candidatures_partenaire"))

verifier("5a. la garde est `_v309_require_coach_or_admin`",
         "await _v309_require_coach_or_admin(request)" in CORPS)
verifier("5b. `require_auth` n'est PAS employe (il accepte les jetons abonne)",
         not re.search(r"\brequire_auth\s*\(", CORPS))
verifier("5b-bis. la garde est la PREMIERE instruction executee — rien ne "
         "peut se glisser avant elle",
         CORPS.strip().split("\n")[0].strip()
         == "appelant = await _v309_require_coach_or_admin(request)",
         "premiere instruction = %r" % CORPS.strip().split("\n")[0].strip())
verifier("5c. aucune decision d'acces ne vient de `X-User-Email` (code seul)",
         "X-User-Email" not in CORPS)
verifier("5d. aucune ecriture dans le corps de la route",
         not re.search(r"\b(insert_one|update_one|update_many|delete_one|delete_many)\b", CORPS))
verifier("5e. le jeton d'URL n'entre dans AUCUNE regex Mongo (code seul)",
         "$regex" not in CORPS and "re.compile" not in CORPS)
verifier("5f. la propriete se lit sur le document, pas sur le corps",
         'lien.get("coach_id")' in CORPS)
verifier("5g. `application_decision` est calcule, avec « pending » par defaut",
         'd.get("application_decision") or "pending"' in CORPS)

verifier("5h. GET /api/leads n'a PAS ete modifie par ce lot",
         'caller_email = request.headers.get("X-User-Email", "").lower().strip()'
         in _corps_de("get_leads"))


print("\n=== 6. LE FRONT LIT LA ROUTE, SANS RECOPIER LA LOGIQUE DU JETON ===")

APP = open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                        "PartnerApplications.js"), encoding="utf-8").read()
SEC = open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                        "SmartLinksSection.js"), encoding="utf-8").read()
CARD = open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                         "SmartLinkCard.js"), encoding="utf-8").read()
SW = open(os.path.join(RACINE, "frontend", "public", "sw.js"), encoding="utf-8").read()

APP_CODE, SEC_CODE, CARD_CODE = _code_js(APP), _code_js(SEC), _code_js(CARD)

for nom, code in [("PartnerApplications", APP_CODE), ("SmartLinksSection", SEC_CODE)]:
    verifier("6a. %s appelle la route en axios" % nom,
             "axios.get(`${API}/partner-applications/" in code)
    verifier("6c. %s ne relit PAS le jeton a la main (code seul)" % nom,
             "afroboost_jwt" not in code and "Authorization" not in code)

verifier("6b. le nouveau composant n'utilise AUCUN fetch",
         "fetch(" not in APP_CODE)
# SmartLinksSection contenait DEJA deux `fetch` (offres, strategie IA) dans le
# modal de creation : ils sont anterieurs a ce lot et hors de son perimetre. On
# prouve donc que le lot n'en a ajoute AUCUN, plutot que d'exiger zero — une
# exigence a zero ici aurait force un refactor non demande.
verifier("6b-bis. le lot n'ajoute aucun `fetch` a SmartLinksSection "
         "(les 2 existants sont anterieurs et hors perimetre)",
         SEC_CODE.count("fetch(") == 2,
         "trouve %d" % SEC_CODE.count("fetch("))

verifier("6d. le jeton de lien est encode dans l'URL",
         "encodeURIComponent(jeton)" in APP_CODE)
verifier("6e. le bouton n'apparait que sur un lien partenaire",
         "isPartner && onOpenApplications" in CARD_CODE
         and "(link.lead_type || '') === 'partner'" in CARD_CODE)
verifier("6f. le compteur vient des donnees, pas d'une constante",
         "applicationsCounts[link.link_token" in SEC_CODE
         and "data?.total" in SEC_CODE)
verifier("6g. l'effet de comptage depend d'une CHAINE, jamais du tableau d'objets",
         "[API, p2aJetonsPartenaires]" in SEC_CODE)
verifier("6h. l'etat n'est remplace que s'il a REELLEMENT change (anti-boucle)",
         "return change ? { ...prev, ...trouves } : prev;" in SEC_CODE)
verifier("6i. les reponses sont rendues generiquement, sans coder q_0/q_1 en dur",
         "p2aNormaliserReponses" in APP_CODE
         and not re.search(r"answers\.q_0|answers\['q_0'\]|\bq_1\b", APP_CODE))
verifier("6j. « pending » s'affiche « En attente »", "pending: 'En attente'" in APP_CODE)

# CE QUI RESTE INTERDIT APRES P2-B ET P2-C.
# P2-A n'avait ni decision ni slug ; P2-B les ajoute, P2-C ajoute le lien et le
# QR — toujours DELIBEREMENT. Les assertions correspondantes ont migre vers les
# suites de ces lots plutot que d'etre supprimees. Ne reste ici que ce qui
# n'appartient a aucun des trois : les statistiques de P2-D.
# P2-C ajoute le lien UTM et le QR sur une candidature ACCEPTEE — c'est son
# objet meme. Leur absence sur `pending` et `rejected` est prouvee dans la suite
# P2-C. Ce qui reste hors perimetre des trois lots, ce sont les statistiques.
for interdit, quoi in [("clics", "compteur de clics"), ("conversions", "conversions"),
                       ("taux de", "taux de conversion")]:
    verifier("6k. aucun %s dans ce lot (code seul)" % quoi,
             interdit not in APP_CODE and interdit not in CARD_CODE)

# Version MINIMALE, pas exacte : epingler « v469 » ferait echouer ce fichier a
# chaque bump ulterieur, pour une raison sans rapport avec P2-A. Le seul risque
# reel est le retour en arriere, qui reservirait un bundle sans l'ecran.
_sw = re.search(r"afroboost-v(\d+)", SW)
verifier("6l. le Service Worker est au moins en v469 (jamais revenu en arriere)",
         bool(_sw) and int(_sw.group(1)) >= 469,
         "version lue = %s" % (_sw.group(0) if _sw else "aucune"))


print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
_total = len(RESULTATS)
print("P2-A — %d / %d verifications au vert" % (_ok, _total))
print("=" * 78)
if _ok != _total:
    print("\nECHECS :")
    for i, c, d in RESULTATS:
        if not c:
            print("  - %s%s" % (i, ("  [%s]" % d) if d else ""))
sys.exit(0 if _ok == _total else 1)

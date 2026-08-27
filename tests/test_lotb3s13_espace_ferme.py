# -*- coding: utf-8 -*-
"""LOT B3-S1.3 — L'ESPACE PRIVE NE S'OUVRE PLUS QU'AVEC UNE PREUVE D'IDENTITE.

CE QUE CE LOT FERME. `GET /api/subscriber/space/{code}` etait declare
`async def get_subscriber_space(access_code, m=None)` : SANS parametre
`request`, donc l'authentification n'y etait pas oubliee, elle etait
IMPOSSIBLE — exactement le defaut que B3-S0 a corrige sur le DELETE. La route
servait e-mail, telephone, objectifs, solde, reservations (avec leurs `id`) et
la liste des membres d'un groupe a quiconque connait un code, alors que 37 des
63 codes sont des libelles lisibles.

CE QUI LA FERME. Les deux briques deja livrees et testees en B3-S1.1, et elles
seules : `lotb3s1_lire_token` (signature ET type) puis
`lotb3s1_session_utilisable` (revocation, expiration, appariement). AUCUN
second moteur d'authentification — regle heritee de B3-S0.

CE QUI RESTE OUVERT, VOLONTAIREMENT. `POST /subscriber/token` (V296) n'est pas
touche : ses 15 utilisateurs (chat, publications, boost, promo, spordate)
continuent de fonctionner. Mais le jeton qu'il delivre porte
`type: "subscriber"` : il est refuse ici. Une porte qui reste ouverte, mais qui
n'ouvre plus CETTE piece.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUN E-MAIL, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_lotb3s13_espace_ferme.py
"""
import ast, asyncio, importlib.util, io, os, re, sys, types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("JWT_SECRET", "secret-de-banc-uniquement")

_spec = importlib.util.spec_from_file_location(
    "b3s13_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

# La fonction de production fait `from api.routes.shared import ...`. On fait
# pointer ce chemin vers le module DEJA charge : aucune seconde copie, donc
# aucun risque de tester autre chose que ce qui tourne.
_pkg_api = types.ModuleType("api"); _pkg_api.__path__ = [os.path.join(RACINE, "api")]
_pkg_rt = types.ModuleType("api.routes"); _pkg_rt.__path__ = [os.path.join(RACINE, "api", "routes")]
sys.modules.setdefault("api", _pkg_api)
sys.modules.setdefault("api.routes", _pkg_rt)
sys.modules["api.routes.shared"] = S

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


CODE = "SYNTHCODE-1"
AUTRE_CODE = "SYNTHCODE-2"
MAIL = "membre@exemple.invalid"
COACH = "coach-synthetique"
AUTRE_COACH = "autre-coach-synthetique"


# ═════════════════════════ faux Mongo minimal ════════════════════════════════
def _corr(doc, filtre):
    for cle, cond in (filtre or {}).items():
        v = doc.get(cle)
        if isinstance(cond, dict):
            if "$ne" in cond and v == cond["$ne"]:
                return False
        elif v != cond:
            return False
    return True


class _Curseur:
    def __init__(self, docs):
        self._d = docs

    async def to_list(self, n=None):
        return [dict(x) for x in (self._d if n is None else self._d[:n])]


class Coll:
    def __init__(self):
        self.docs = []
        self.lectures = 0
        self.filtres = []

    async def find_one(self, filtre, projection=None):
        self.lectures += 1
        for d in self.docs:
            if all(d.get(k) == v for k, v in (filtre or {}).items()):
                return dict(d)
        return None

    def find(self, filtre=None, projection=None):
        self.filtres.append(dict(filtre or {}))
        return _Curseur([d for d in self.docs if _corr(d, filtre)])


class Base:
    def __init__(self):
        self._x = {}
        self.courses = Coll()

    def __getitem__(self, nom):
        if nom not in self._x:
            self._x[nom] = Coll()
        return self._x[nom]


class Journal:
    def __init__(self):
        self.lignes = []

    def _n(self, m, a):
        try:
            self.lignes.append((str(m) % a) if a else str(m))
        except (TypeError, ValueError):
            self.lignes.append(str(m))

    def info(self, m="", *a, **k): self._n(m, a)
    def warning(self, m="", *a, **k): self._n(m, a)
    def error(self, m="", *a, **k): self._n(m, a)


class HTTPExc(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        self.status_code, self.detail = status_code, detail
        super().__init__(str(detail))


class Req:
    """Les en-tetes de Starlette sont insensibles a la casse — on le simule,
    sinon le banc validerait une lecture qui echouerait en production."""
    def __init__(self, entetes=None):
        self._h = {str(k).lower(): v for k, v in (entetes or {}).items()}

    @property
    def headers(self):
        h = self._h
        return types.SimpleNamespace(get=lambda k, d="": h.get(str(k).lower(), d))


def extraire(noms, db, journal):
    """Les VRAIES fonctions, extraites du vrai `server.py`."""
    ns = {"db": db, "re": re, "datetime": datetime, "timezone": timezone,
          "timedelta": timedelta, "asyncio": asyncio, "logger": journal,
          "HTTPException": HTTPExc, "Request": object,
          "DEFAULT_COACH_ID": "bassi_default"}
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "_B3S1_COLL_SESSIONS", "_B3S13_REFUS_DETAIL"):
            exec(compile("".join(LIGNES[n.lineno - 1:n.end_lineno]), "s", "exec"), ns)
    for nom in noms:
        for n in ast.walk(ARBRE):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
                exec(compile("".join(LIGNES[n.lineno - 1:n.end_lineno]), "s", "exec"), ns)
    return ns


def monde(slug="", coach=COACH, code=CODE, revoquee=False, fin=None):
    """Un jeton d'espace REEL + sa session, tels que l'OTP les produit."""
    db, journal = Base(), Journal()
    jeton, jti = S.lotb3s1_make_token(code, MAIL, coach, slug or None)
    db["subscriber_sessions"].docs.append({
        "jti": jti, "code": code, "email": MAIL, "coach_id": coach,
        "slug": slug or "", "revoked": revoquee,
        "expires_at": (fin or (datetime.now(timezone.utc) + timedelta(days=30))).isoformat(),
    })
    return db, journal, jeton


def jeton_v296(code=CODE):
    """Le jeton de `POST /subscriber/token` : meme secret, meme signature,
    mais `type: "subscriber"`. C'est le coeur de la Decision 1."""
    import jwt as _pyjwt
    now = datetime.now(timezone.utc)
    return _pyjwt.encode({
        "type": "subscriber", "code": code, "email": MAIL,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=30)).timestamp()),
    }, os.environ["JWT_SECRET"], algorithm="HS256")


async def porte(db, journal, entetes, code=CODE, m=None):
    ns = extraire(["_b3s13_porteur_autorise"], db, journal)
    return await ns["_b3s13_porteur_autorise"](Req(entetes), code, m)


# ════════════════════════════════ le banc ════════════════════════════════════
async def principal():
    # ---- 1. LA ROUTE PEUT ENFIN S'AUTHENTIFIER ------------------------------
    route = None
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "get_subscriber_space":
            route = n
    verifier("1. La route `get_subscriber_space` existe", route is not None)
    args = [a.arg for a in (route.args.args if route else [])]
    verifier("2. Elle recoit `request` — sans quoi aucune preuve n'est lisible",
             "request" in args, "parametres=%s" % args)
    verifier("3. Elle recoit toujours `access_code` et `m` (contrat inchange)",
             "access_code" in args and "m" in args, "parametres=%s" % args)

    corps_route = "".join(LIGNES[route.lineno - 1:route.end_lineno]) if route else ""

    # LEÇON DE CE LOT. Le premier jet du correctif a supprime la ligne de
    # DECORATEUR en reconstruisant le fichier : la fonction etait parfaite, la
    # route n'etait plus montee, et l'espace renvoyait 404 a TOUT LE MONDE, son
    # proprietaire compris. Le banc ne regardait que la fonction, il n'a rien
    # vu ; c'est le demarrage reel de l'application qui a leve le lievre.
    # Desormais le banc regarde aussi comment la fonction est ACCROCHEE.
    _decos = [
        "".join(LIGNES[d.lineno - 1:d.end_lineno]) for d in (route.decorator_list if route else [])
    ]
    verifier("4bis. La route est bien MONTEE sur `GET /subscriber/space/{access_code}`",
             any('api_router.get' in d and '/subscriber/space/{access_code}' in d for d in _decos),
             "decorateurs=%s" % [d.strip() for d in _decos])
    verifier("4. Elle appelle la porte `_b3s13_porteur_autorise`",
             "_b3s13_porteur_autorise" in corps_route)
    verifier("5. Elle verifie le tenant du code contre celui du jeton",
             "coach_id" in corps_route and "_b3s13_refus" in corps_route)

    # ---- 2. AUCUN ORACLE : LE 404 NE NOMME PLUS LE CODE ---------------------
    verifier("6. Le 404 ne recrache plus le code cherche",
             "Code cherch" not in corps_route,
             "un 404 qui nomme le code confirme sa non-existence, donc l'existence des autres")
    verifier("7. Un seul libelle de refus, partage par tous les cas",
             corps_route.count("_B3S13_REFUS_DETAIL") + corps_route.count("_b3s13_refus()") >= 2)

    # ---- 3. LA PORTE ELLE-MEME ---------------------------------------------
    db, j, jeton = monde()
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton})
    verifier("8. Jeton OTP valide -> ACCEPTE", charge is not None and motif == "ok", motif)
    verifier("9. La charge acceptee porte bien le code demande",
             (charge or {}).get("code") == CODE)

    db, j, _ = monde()
    charge, motif = await porte(db, j, {})
    verifier("10. Aucun en-tete -> REFUS (acces anonyme ferme)", charge is None, motif)

    db, j, _ = monde()
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton_v296()})
    verifier("11. ANCIEN jeton `/subscriber/token` (type=subscriber) -> REFUS",
             charge is None, motif)

    db, j, _ = monde()
    charge, motif = await porte(db, j, {"X-Espace-Token": "pas.un.jeton"})
    verifier("12. Jeton illisible -> REFUS", charge is None, motif)

    db, j, jeton = monde()
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton}, code=AUTRE_CODE)
    verifier("13. Jeton d'un AUTRE code -> REFUS (connaitre un code ne suffit plus)",
             charge is None, motif)

    # ---- 4. MEMBRE ET GROUPE ------------------------------------------------
    db, j, jeton = monde(slug="")
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton}, m=None)
    verifier("14. Groupe SANS `?m=` avec un jeton sans slug -> ACCEPTE",
             charge is not None, motif)

    db, j, jeton = monde(slug="")
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton}, m="marie")
    verifier("15. `?m=marie` avec un jeton sans slug -> REFUS (pas de saut de membre)",
             charge is None, motif)

    db, j, jeton = monde(slug="marie")
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton}, m="marie")
    verifier("16. Groupe AVEC `?m=marie` et le jeton de Marie -> ACCEPTE",
             charge is not None, motif)

    db, j, jeton = monde(slug="marie")
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton}, m="jean")
    verifier("17. Le jeton de Marie ne peut pas ouvrir la fiche de Jean -> REFUS",
             charge is None, motif)

    db, j, jeton = monde(slug="marie")
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton}, m=None)
    verifier("18. Le jeton de Marie n'ouvre pas la vue GROUPE (liste des membres)",
             charge is None, motif)

    # ---- 5. REVOCATION ET EXPIRATION ---------------------------------------
    db, j, jeton = monde(revoquee=True)
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton})
    verifier("19. Session REVOQUEE -> REFUS", charge is None, motif)

    db, j, jeton = monde(fin=datetime.now(timezone.utc) - timedelta(days=1))
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton})
    verifier("20. Session EXPIREE -> REFUS", charge is None, motif)

    db, j, jeton = monde()
    db["subscriber_sessions"].docs = []          # jeton signe, session absente
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton})
    verifier("21. Jeton signe mais session INCONNUE -> REFUS", charge is None, motif)

    # ---- 6. TENANT ----------------------------------------------------------
    db, j, jeton = monde(coach=AUTRE_COACH)
    db["subscriber_sessions"].docs[0]["coach_id"] = COACH   # jeton != session
    charge, motif = await porte(db, j, {"X-Espace-Token": jeton})
    verifier("22. Jeton d'un AUTRE tenant -> REFUS", charge is None, motif)

    # ---- 6bis. LE TENANT, ET LE PIEGE QU'IL A FAILLI OUVRIR ---------------
    # L'OTP derive le `coach_id` du jeton de `discount_codes` d'abord, la route
    # lit `subscriptions` d'abord : sur un code a fiches multiples, les deux
    # sources divergent. Une comparaison a UNE seule d'entre elles aurait ferme
    # l'espace a des titulaires legitimes — c'est ce que ces cas verrouillent.
    ta = extraire(["_b3s13_tenant_accepte"], Base(), Journal())["_b3s13_tenant_accepte"]
    verifier("22a. Jeton du coach de l'abonnement -> ACCEPTE",
             ta({"coach_id": COACH}, {"coach_id": COACH}, {"coach_id": COACH}))
    verifier("22b. Les deux fiches divergent, le jeton suit `discount_codes` -> ACCEPTE",
             ta({"coach_id": AUTRE_COACH}, {"coach_id": COACH}, {"coach_id": AUTRE_COACH}),
             "c'est EXACTEMENT le cas qui aurait enferme le proprietaire dehors")
    verifier("22c. Jeton d'un coach etranger aux deux fiches -> REFUS",
             not ta({"coach_id": "coach-tiers"}, {"coach_id": COACH}, {"coach_id": AUTRE_COACH}))
    verifier("22d. Code orphelin + jeton au repli `DEFAULT_COACH_ID` -> ACCEPTE",
             ta({"coach_id": "bassi_default"}, {}, {}),
             "ce repli est celui que l'OTP ecrit lui-meme")
    verifier("22e. Code orphelin + jeton d'un coach quelconque -> REFUS",
             not ta({"coach_id": "coach-tiers"}, {}, {}))

    # ---- 7. AUCUN ORACLE : TOUS LES REFUS SE RESSEMBLENT --------------------
    db, j, jeton = monde()
    motifs = []
    for entetes, c, mm in (({}, CODE, None),
                           ({"X-Espace-Token": jeton_v296()}, CODE, None),
                           ({"X-Espace-Token": "pas.un.jeton"}, CODE, None),
                           ({"X-Espace-Token": jeton}, AUTRE_CODE, None),
                           ({"X-Espace-Token": jeton}, CODE, "jean")):
        d, jj, _ = monde()
        ch, mo = await porte(d, jj, entetes, code=c, m=mm)
        motifs.append(ch)
    verifier("23. Code inconnu, autre tenant, jeton invalide : TOUS refuses pareil",
             all(x is None for x in motifs))
    ns = extraire(["_b3s13_refus"], Base(), Journal())
    e1, e2 = ns["_b3s13_refus"](), ns["_b3s13_refus"]()
    verifier("24. Le refus est un 404, jamais un 403", e1.status_code == 404,
             "un 403 dirait « ce code existe, mais pas pour toi »")
    verifier("25. Deux refus sont mot pour mot identiques", e1.detail == e2.detail)
    verifier("26. Le libelle de refus ne contient aucun code ni e-mail",
             CODE not in str(e1.detail) and "@" not in str(e1.detail), str(e1.detail))

    # ---- 8. LA BASE N'EST PAS INTERROGEE POUR RIEN -------------------------
    db, j, _ = monde()
    avant = db["subscriber_sessions"].lectures
    await porte(db, j, {})
    verifier("27. Refus SANS jeton : aucune lecture de session",
             db["subscriber_sessions"].lectures == avant)

    # ---- 9. AUCUNE DONNEE PERSONNELLE DANS LE JOURNAL ----------------------
    db, j, jeton = monde()
    await porte(db, j, {"X-Espace-Token": jeton_v296()})
    tout = " ".join(j.lignes)
    verifier("28. Le journal du refus ne contient ni e-mail, ni code, ni jeton",
             MAIL not in tout and CODE not in tout and jeton not in tout, tout[:120])

    # ---- 10. DECISION 1 : LA ROUTE V296 EST INTACTE ------------------------
    v296 = None
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "v296_subscriber_token":
            v296 = n
    verifier("29. `POST /subscriber/token` existe toujours (ses 15 usages vivent)",
             v296 is not None)
    verifier("30. Elle emet toujours un jeton de type `subscriber`, non `subscriber_space`",
             '"subscriber_space"' not in "".join(LIGNES[v296.lineno - 1:v296.end_lineno])
             if v296 else False)
    verifier("31. `lotb3s1_lire_token` refuse categoriquement ce type",
             S.lotb3s1_lire_token(jeton_v296()) is None)

    # ═══ 10bis. LA ROUTE PUBLIQUE D'OCCURRENCES ═════════════════════════════
    # Elle rend au chat ce que la fermeture de l'espace lui a retire — les
    # SEANCES datees — sans lui donner la moindre donnee personnelle.
    rt = None
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "n456_occurrences_publiques":
            rt = n
    verifier("34. La route publique d'occurrences existe", rt is not None)
    _d = ["".join(LIGNES[x.lineno - 1:x.end_lineno]) for x in (rt.decorator_list if rt else [])]
    verifier("35. Elle est bien MONTEE sur `GET /courses/occurrences`",
             any("api_router.get" in x and '"/courses/occurrences"' in x for x in _d),
             "decorateurs=%s" % [x.strip() for x in _d])
    _params = [a.arg for a in (rt.args.args if rt else [])]
    verifier("36. Elle n'accepte AUCUN code d'espace abonne",
             not any(p in _params for p in ("access_code", "code", "access", "token")),
             "parametres=%s" % _params)

    # Le VRAI moteur d'occurrences, pas une imitation : c'est lui qui garantit
    # « futur seulement », et on ne testerait rien en le remplacant.
    dbc = Base()
    nsr = extraire(["n456_occurrences_publiques", "_v184_next_occurrences",
                    "_v184_parse_time_hhmm"], dbc, Journal())
    for nn in ast.walk(ARBRE):
        if isinstance(nn, ast.Assign) and getattr(nn.targets[0], "id", "") == "_V184_WEEKDAY_LABELS_FR":
            exec(compile("".join(LIGNES[nn.lineno - 1:nn.end_lineno]), "s", "exec"), nsr)
        if isinstance(nn, ast.Assign) and getattr(nn.targets[0], "id", "") == "_N456_CHAMPS_PUBLICS":
            exec(compile("".join(LIGNES[nn.lineno - 1:nn.end_lineno]), "s", "exec"), nsr)
    occ_route = nsr["n456_occurrences_publiques"]
    BLANCHE = set(nsr["_N456_CHAMPS_PUBLICS"])

    demain = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    hier = (datetime.now(timezone.utc) - timedelta(days=9)).date().isoformat()
    dbc.courses.docs = [
        # un cours a venir chez NOTRE coach, avec un champ secret en plus
        {"id": "c-futur", "name": "Cardio", "date": demain, "time": "18:30",
         "locationName": "Neuchatel", "coach_id": COACH, "visible": True,
         "assignedEmail": MAIL, "notes_privees": "ne doit jamais sortir"},
        # un cours DEJA PASSE
        {"id": "c-passe", "name": "Ancien", "date": hier, "time": "18:30",
         "coach_id": COACH, "visible": True},
        # un cours MASQUE
        {"id": "c-masque", "name": "Masque", "date": demain, "time": "19:30",
         "coach_id": COACH, "visible": False},
        # un cours ARCHIVE
        {"id": "c-archive", "name": "Archive", "date": demain, "time": "20:30",
         "coach_id": COACH, "visible": True, "archived": True},
        # un cours d'un AUTRE coach
        {"id": "c-voisin", "name": "Voisin", "date": demain, "time": "18:30",
         "coach_id": AUTRE_COACH, "visible": True},
    ]

    r = await occ_route(coach=COACH)
    ids = [o.get("course_id") for o in r["occurrences"]]
    verifier("37. Seul le cours FUTUR est rendu (le passe est ecarte)",
             "c-futur" in ids and "c-passe" not in ids, "rendus=%s" % ids)
    verifier("38. Un cours MASQUE n'est pas rendu", "c-masque" not in ids, "rendus=%s" % ids)
    verifier("39. Un cours ARCHIVE n'est pas rendu", "c-archive" not in ids, "rendus=%s" % ids)
    verifier("40. Isolation tenant : le cours du coach voisin n'est pas rendu",
             "c-voisin" not in ids, "rendus=%s" % ids)
    _f = dbc.courses.filtres[-1]
    verifier("41. Le filtre reprend celui de `/api/courses` (visible + archived)",
             _f.get("archived") == {"$ne": True} and _f.get("visible") == {"$ne": False},
             "filtre=%s" % _f)

    r2 = await occ_route(coach=AUTRE_COACH)
    verifier("42. Le coach voisin ne voit QUE ses propres cours",
             [o.get("course_id") for o in r2["occurrences"]] == ["c-voisin"])

    r3 = await occ_route(coach="coach-qui-n-existe-pas")
    verifier("43. Coach inconnu -> liste vide, AUCUN oracle",
             r3 == {"occurrences": []},
             "meme reponse qu'un coach reel sans cours : rien a deviner")

    # ---- liste blanche stricte ---------------------------------------------
    une = r["occurrences"][0]
    verifier("44. Les champs rendus sont EXACTEMENT la liste blanche publique",
             set(une.keys()) == BLANCHE, "rendus=%s" % sorted(une.keys()))
    brut = repr(r)
    verifier("45. Aucun champ prive du cours ne fuit (secret, e-mail, notes)",
             MAIL not in brut and "notes_privees" not in brut and "ne doit jamais sortir" not in brut)
    verifier("46. Aucun mot-cle de donnee personnelle dans la reponse",
             not any(k in brut for k in ("assignedEmail", "whatsapp", "phone", "promoCode",
                                         "access_code", "remaining_sessions", "used")),
             brut[:150])
    verifier("47. La reponse ne contient QUE la cle `occurrences`",
             set(r.keys()) == {"occurrences"}, "cles=%s" % sorted(r.keys()))

    # ---- pas de code abonne, meme fourni ------------------------------------
    try:
        await occ_route(coach=COACH, days=14)
        _sans_code = True
    except TypeError:
        _sans_code = False
    verifier("48. La route fonctionne SANS le moindre code d'abonne", _sans_code)

    # ---- la fermeture de l'espace reste intacte -----------------------------
    verifier("49. `get_subscriber_space` exige toujours la porte d'identite",
             "_b3s13_porteur_autorise" in corps_route and "_b3s13_refus()" in corps_route)
    verifier("50. La route publique n'ouvre AUCUNE porte vers l'espace prive",
             "subscriber" not in "".join(LIGNES[rt.lineno - 1:rt.end_lineno]).lower()
             if rt else False)

    # ---- 11. AUCUN NOM LIBRE (lecon de l'incident OTP) ---------------------
    for f in ("_b3s13_porteur_autorise", "_b3s13_refus", "_b3s13_tenant_accepte",
              "n456_occurrences_publiques"):
        manquants = _noms_libres(f)
        verifier("51. `%s` n'utilise aucun nom inexistant" % f, not manquants,
                 "noms absents: %s" % sorted(manquants))

    # ---- 12. AUCUN DRAPEAU NE PEUT ROUVRIR LA PORTE ------------------------
    src_porte = ""
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_b3s13_porteur_autorise":
            src_porte = "".join(LIGNES[n.lineno - 1:n.end_lineno])
    verifier("52. La porte ne lit AUCUNE variable d'environnement",
             "environ" not in src_porte and "getenv" not in src_porte,
             "un drapeau capable de rouvrir une route non authentifiee est une porte derobee")


def _noms_libres(nom_fonction):
    """Tout nom LU par cette fonction et qui n'existe nulle part -> NameError.
    Controle generique herite de l'incident OTP : le banc y avait FOURNI un nom
    absent de la production, validant la bonne propriete et masquant le defaut.
    """
    import builtins
    globaux = set()
    for n in ARBRE.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    globaux.add(t.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            globaux.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                globaux.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            globaux.add(n.target.id)
        elif isinstance(n, ast.Try):
            for sous in n.body + [x for h in n.handlers for x in h.body] + n.orelse + n.finalbody:
                if isinstance(sous, (ast.Import, ast.ImportFrom)):
                    for a in sous.names:
                        globaux.add((a.asname or a.name).split(".")[0])
                elif isinstance(sous, ast.Assign):
                    for t in sous.targets:
                        if isinstance(t, ast.Name):
                            globaux.add(t.id)
    cible = None
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fonction:
            cible = n
    if cible is None:
        return {nom_fonction + " (fonction absente)"}
    locaux = set(a.arg for a in cible.args.args)
    for n in ast.walk(cible):
        # Les arguments d'un `lambda` sont des noms LIES, pas des noms libres :
        # sans cette branche le controle criait au loup sur `sort(key=lambda x: ...)`.
        if isinstance(n, ast.Lambda):
            for _a in list(n.args.args) + list(n.args.posonlyargs) + list(n.args.kwonlyargs):
                locaux.add(_a.arg)
    for n in ast.walk(cible):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            locaux.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                locaux.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            locaux.add(n.name)
        elif isinstance(n, (ast.comprehension,)):
            pass
    for n in ast.walk(cible):
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for g in n.generators:
                for x in ast.walk(g.target):
                    if isinstance(x, ast.Name):
                        locaux.add(x.id)
    manquants = set()
    for n in ast.walk(cible):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            if n.id not in locaux and n.id not in globaux and not hasattr(builtins, n.id):
                manquants.add(n.id)
    return manquants


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except Exception as _e:
        RESULTATS.append(("BANC INTERROMPU : %s: %s" % (type(_e).__name__, _e), False, ""))
    ok = 0
    for nom, bon, detail in RESULTATS:
        print(("  OK   " if bon else "  RATE ") + nom + (("   [%s]" % detail) if (detail and not bon) else ""))
        ok += 1 if bon else 0
    print("\n%d/%d au vert" % (ok, len(RESULTATS)))
    sys.exit(0 if ok == len(RESULTATS) else 1)

# -*- coding: utf-8 -*-
"""V450 — LES ROUTES TECHNIQUES DE TEST/DIAGNOSTIC WHATSAPP NE SONT PLUS PUBLIQUES.

CE QUE CE LOT REPARE. Quatre routes GET n'avaient AUCUNE authentification, et
deux d'entre elles POSTENT chez Meta depuis le numero business d'Afroboost :

    GET /api/test-whatsapp-template?to=...&template=...   -> 1 message reel
    GET /api/test-campaign-3steps?to=...                  -> 2 messages reels

Preuve mesuree en production le 26/08/2026, sans envoyer aucun message (version
d'API volontairement invalide pour que Meta refuse avant de creer le message) :

    curl "https://afroboost.com/api/test-whatsapp-template\
?to=00000000000&template=afroboost_bienvenue&version=vINEXISTANTE_PREUVE_AUDIT"
    -> HTTP 200
    -> meta_url : https://graph.facebook.com/vINEXISTANTE.../1062611940271584/messages

Le handler s'est execute EN ENTIER pour un anonyme : il a lu la config, pose le
vrai jeton en en-tete `Authorization` et appele Meta. Seule la version d'API
bidon a empeche l'envoi. Avec la version par defaut, le message partait.

Les deux autres livraient la configuration Meta a un anonyme :

    GET /api/whatsapp-diagnostic   -> renvoyait AUSSI `token_prefix` : les
                                      20 premiers caracteres du jeton systeme.
    GET /api/whatsapp-app-info     -> app_id, WABA, permissions du jeton.

CE QU'IL N'INVENTE PAS. Aucune authentification nouvelle. On reutilise TELLE
QUELLE `_v411_exiger_super_admin`, deja posee par V435 et V442 sur les trois
routes soeurs qui menent au meme numero business (`/send-whatsapp`,
`/send-whatsapp-template`, `/create-whatsapp-template`). C'est la seule garde du
depot qui n'accepte JAMAIS le repli `X-User-Email` falsifiable.

CE QU'IL NE TOUCHE PAS : les campagnes, le registre STOP, la normalisation des
numeros, l'opt-out, les fournisseurs, les modeles metier, le cron, P1-b, P1-d,
AUTO-PRESENCE, le webhook entrant et le moteur d'envoi.

Aucun reseau. Aucun WhatsApp. Aucune base. Aucune ecriture.

Lancement :  python3 tests/test_v450_routes_test_whatsapp.py
"""
import ast
import asyncio
import io
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

SECRET = "secret-de-test-v450-jamais-en-production-32o+"
ADMIN = "contact.artboost@gmail.com"
ADMIN2 = "afroboost.bassi@gmail.com"
COACH = "un.coach.partenaire@example.com"

# Le jeton bidon du bac a sable. Il ne doit apparaitre dans AUCUNE reponse.
FAUX_JETON = "EAAG-JETON-SYSTEME-FICTIF-DU-TEST-V450-NE-DOIT-JAMAIS-FUIR"

# Les quatre routes de ce lot : (fonction, libelle, poste-t-il chez Meta ?)
ROUTES = [
    ("test_whatsapp_template", "GET /api/test-whatsapp-template", True),
    ("test_campaign_3steps",   "GET /api/test-campaign-3steps",   True),
    ("whatsapp_diagnostic",    "GET /api/whatsapp-diagnostic",    False),
    ("whatsapp_app_info",      "GET /api/whatsapp-app-info",      False),
]

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("fonction introuvable : %s" % nom)


def extraire(nom):
    n = noeud(nom)
    return "".join(LIGNES[n.lineno - 1:n.end_lineno])


def code_nu(nom):
    """Le code EXECUTE, sans docstring ni commentaires. Indispensable : les
    docstrings de ce lot CITENT les URL et les noms de routes pour expliquer ;
    une recherche de texte brute y verrait du code la ou il n'y a qu'un recit."""
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps), corps


# ----------------------------------------------------------------------------
# Bac a sable : rien ne sort d'ici. httpx est remplace par un mouchard.
# ----------------------------------------------------------------------------
class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code
        self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))


class FausseRequete:
    def __init__(self, headers=None):
        self._h = {k.lower(): v for k, v in (headers or {}).items()}
        self.headers = self

    def get(self, cle, defaut=""):
        return self._h.get(cle.lower(), defaut)


APPELS_META = []          # tout appel reseau atterrit ICI, jamais chez Meta


class FausseReponse:
    def __init__(self, code=200, corps=None):
        self.status_code = code
        self._corps = corps if corps is not None else {"data": [], "ok": True}
        self.text = str(self._corps)

    def json(self):
        return self._corps


class FauxClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **kw):
        APPELS_META.append({"methode": "POST", "url": url,
                            "headers": headers or {}, "json": json})
        return FausseReponse(200, {"messages": [{"id": "wamid.SIMULE"}]})

    async def get(self, url, params=None, **kw):
        APPELS_META.append({"methode": "GET", "url": url, "params": params or {}})
        # `data` est un DICT : /whatsapp-app-info lit `(r.json() or {}).get("data", {})`
        # puis appelle `.get("app_id")` dessus. Une liste ferait planter le
        # handler dans le bac a sable pour une raison etrangere au lot.
        return FausseReponse(200, {"data": {"app_id": "1656270458951182",
                                            "is_valid": True, "scopes": []},
                                   "id": "simule"})


class FauxHttpx:
    @staticmethod
    def AsyncClient(*a, **kw):
        return FauxClient()


class FauxAsyncio:
    @staticmethod
    async def sleep(_):
        return None


async def fausse_config():
    return {"api_mode": "meta", "access_token": FAUX_JETON,
            "phone_number_id": "1062611940271584", "api_version": "v21.0"}


def construire():
    os.environ["JWT_SECRET"] = SECRET
    faux_logger = type("l", (), {"warning": staticmethod(lambda *a, **k: None),
                                 "info": staticmethod(lambda *a, **k: None),
                                 "error": staticmethod(lambda *a, **k: None)})
    faux_routeur = type("r", (), {"get": staticmethod(lambda *a, **k: (lambda f: f)),
                                  "post": staticmethod(lambda *a, **k: (lambda f: f))})
    bac = {
        "os": os, "HTTPException": HTTPException, "Request": FausseRequete,
        "SUPER_ADMIN_EMAILS": [ADMIN, ADMIN2],
        "_get_whatsapp_config": fausse_config,
        "httpx": FauxHttpx, "asyncio": FauxAsyncio,
        "logger": faux_logger, "api_router": faux_routeur,
    }
    code = "\n".join([extraire("is_super_admin"),
                      extraire("_v311_coach_email_from_jwt"),
                      extraire("_v411_exiger_super_admin")]
                     + [extraire(f) for f, _, _ in ROUTES])
    # `import httpx` / `import asyncio` sont LOCAUX a chaque handler : on les
    # neutralise pour que le mouchard du bac a sable reste en place.
    code = code.replace("    import httpx\n", "    httpx = _HTTPX_MOUCHARD\n")
    code = code.replace("    import asyncio\n", "    asyncio = _ASYNCIO_MOUCHARD\n")
    bac["_HTTPX_MOUCHARD"] = FauxHttpx
    bac["_ASYNCIO_MOUCHARD"] = FauxAsyncio
    exec(compile(code, "<v450-extrait-de-server.py>", "exec"), bac)
    return bac


def jeton(email, secret=SECRET, type_=None, exp=None):
    import jwt as pyjwt
    corps = {"email": email}
    if type_:
        corps["type"] = type_
    if exp:
        corps["exp"] = exp
    return pyjwt.encode(corps, secret, algorithm="HS256")


async def appeler(bac, fonction, headers):
    """Renvoie ('ok', resultat) ou ('refus', code_http).

    L'objet Request est passe par MOT-CLE, jamais par position : les handlers
    portent aussi des parametres de requete (`to`, `template`, `version`) et un
    appel positionnel irait se loger dans `to`. Si le handler n'a pas encore de
    parametre `request` — l'etat AVANT correctif — Python leve un TypeError que
    l'on rend visible comme un echec explicite, sans faire tomber la suite.
    """
    try:
        r = await bac[fonction](request=FausseRequete(headers))
        return ("ok", r)
    except HTTPException as e:
        return ("refus", e.status_code)
    except TypeError as e:
        return ("signature", str(e))


# ----------------------------------------------------------------------------
# A + B + C + G — anonyme refuse, aucun appel Meta, aucune fuite
# ----------------------------------------------------------------------------
async def scenario_refus(bac):
    B = lambda t: {"Authorization": "Bearer " + t}
    refus = [
        ("anonyme (aucun en-tete)", {}),
        ("X-User-Email forge d'un super-admin", {"X-User-Email": ADMIN}),
        ("X-User-Email forge + Content-Type", {"X-User-Email": ADMIN,
                                               "Content-Type": "application/json"}),
        ("JWT signe d'un AUTRE secret", B(jeton(ADMIN, secret="mauvais-secret"))),
        ("JWT sans signature (alg=none)", B("eyJhbGciOiJub25lIn0.eyJlbWFpbCI6ImEifQ.")),
        ("jeton illisible", B("pas-du-tout-un-jwt")),
        ("Bearer vide", B("")),
        ("schema Basic au lieu de Bearer", {"Authorization": "Basic " + jeton(ADMIN)}),
        ("JWT valide d'un coach NON super-admin", B(jeton(COACH))),
        ("JWT valide mais de type abonne", B(jeton(ADMIN, type_="subscriber"))),
        ("JWT expire", B(jeton(ADMIN, exp=1))),
        ("JWT sans champ email", B(jeton(None))),
    ]
    for fonction, libelle, poste in ROUTES:
        for nom, h in refus:
            APPELS_META.clear()
            etat, val = await appeler(bac, fonction, h)
            verifier("A/B. %s  REFUS %s" % (libelle, nom),
                     etat == "refus" and val == 403, "%s %s" % (etat, val))
            # C — aucun fournisseur WhatsApp appele apres le refus
            verifier("C.   %s  ^ aucun appel Meta apres refus" % libelle,
                     APPELS_META == [],
                     "%d appel(s) : %s" % (len(APPELS_META),
                                           [a["url"] for a in APPELS_META]))
            # G — le refus ne dit rien du jeton ni du secret
            if etat == "refus":
                pass
            texte = str(val)
            verifier("G.   %s  ^ le refus ne fuit ni jeton ni secret" % libelle,
                     FAUX_JETON not in texte and SECRET not in texte, texte[:120])

    # Le secret absent doit FERMER, pas ouvrir.
    ancien = os.environ.get("JWT_SECRET", "")
    os.environ["JWT_SECRET"] = ""
    for fonction, libelle, _ in ROUTES:
        APPELS_META.clear()
        etat, val = await appeler(bac, fonction, B(jeton(ADMIN)))
        verifier("A/B. %s  REFUS JWT_SECRET absent -> on ferme" % libelle,
                 etat == "refus" and val == 403, "%s %s" % (etat, val))
        verifier("C.   %s  ^ aucun appel Meta" % libelle, APPELS_META == [], "")
    os.environ["JWT_SECRET"] = ancien


# ----------------------------------------------------------------------------
# F — le super-admin legitime garde le comportement technique
# ----------------------------------------------------------------------------
async def scenario_legitime(bac):
    B = lambda t: {"Authorization": "Bearer " + t}
    for fonction, libelle, poste in ROUTES:
        APPELS_META.clear()
        etat, val = await appeler(bac, fonction, B(jeton(ADMIN)))
        verifier("F.   %s  PASSE avec JWT super-admin signe" % libelle,
                 etat == "ok", "%s %s" % (etat, str(val)[:80]))
        if poste:
            postes = [a for a in APPELS_META if a["methode"] == "POST"]
            verifier("F.   %s  ^ le chemin technique est intact (Meta atteint)" % libelle,
                     len(postes) >= 1, "%d POST" % len(postes))
            verifier("F.   %s  ^ le POST vise bien le numero business" % libelle,
                     bool(postes) and all("1062611940271584/messages" in a["url"] for a in postes),
                     str([a["url"] for a in postes])[:140])
        # G — la reponse rendue ne contient jamais le jeton
        verifier("G.   %s  ^ la reponse ne contient pas le jeton" % libelle,
                 FAUX_JETON not in str(val), str(val)[:160])

    # Second super-admin, casse et espaces : le legitime ne doit pas etre refuse
    # pour si peu.
    for nom, email in (("second super-admin", ADMIN2),
                       ("casse/espaces differents", "  CONTACT.ArtBoost@Gmail.COM  ")):
        etat, _ = await appeler(bac, "whatsapp_diagnostic", B(jeton(email)))
        verifier("F.   GET /api/whatsapp-diagnostic  PASSE %s" % nom, etat == "ok", etat)


# ----------------------------------------------------------------------------
# Structure : la garde est reelle, premiere, et c'est celle des routes soeurs
# ----------------------------------------------------------------------------
def tests_structurels():
    for fonction, libelle, _ in ROUTES:
        try:
            n = noeud(fonction)
        except AssertionError:
            verifier("S1. %s  le handler existe" % libelle, False, "introuvable")
            continue
        verifier("S1. %s  le handler existe" % libelle, True)

        args = [a.arg for a in n.args.args]
        verifier("S2. %s  recoit un objet Request (auth rendue possible)" % libelle,
                 "request" in args, str(args))
        annot = {a.arg: ast.unparse(a.annotation) for a in n.args.args if a.annotation}
        verifier("S3. %s  `request` est annote Request" % libelle,
                 annot.get("request") == "Request", str(annot))

        nu, corps = code_nu(fonction)
        verifier("S4. %s  la garde est la TOUTE PREMIERE instruction" % libelle,
                 bool(corps) and "_v411_exiger_super_admin" in ast.unparse(corps[0]),
                 ast.unparse(corps[0])[:90] if corps else "corps vide")
        verifier("S5. %s  garde REUTILISEE, aucune auth inventee" % libelle,
                 nu.count("_v411_exiger_super_admin") == 1
                 and "X-User-Email" not in nu
                 and "Referer" not in nu and "Origin" not in nu
                 and "secret" not in nu.lower(),
                 nu[:120])

    # La garde retenue est bien celle des trois routes soeurs deja fermees.
    for soeur in ("send_whatsapp_message", "send_whatsapp_template",
                  "create_whatsapp_template"):
        verifier("S6. coherence : %s utilise la meme garde" % soeur,
                 "_v411_exiger_super_admin" in extraire(soeur), "")

    # La garde ne lit JAMAIS X-User-Email comme identite.
    g, _ = code_nu("_v311_coach_email_from_jwt")
    verifier("S7. la garde ne lit jamais X-User-Email comme identite",
             "X-User-Email" not in g, g[:120])
    verifier("S8. la garde n'accepte que HS256 signe",
             "algorithms=['HS256']" in g or 'algorithms=["HS256"]' in g, g[:120])

    # G — le diagnostic ne doit plus rendre le moindre morceau du jeton.
    nu_diag, _ = code_nu("whatsapp_diagnostic")
    verifier("S9. /whatsapp-diagnostic ne renvoie plus de morceau du jeton",
             "token_prefix" not in nu_diag and "access_token[:" not in nu_diag,
             nu_diag[-260:])


# ----------------------------------------------------------------------------
# D + E — le canal metier n'a pas bouge (compare au PARENT du commit)
# ----------------------------------------------------------------------------
INTOUCHABLES_SERVEUR = (
    "launch_campaign",                    # D — campagnes
    "_send_whatsapp_campaign_template",   # D — template de campagne
    "send_whatsapp_direct",               # D — moteur d'envoi
    "_send_whatsapp_meta",                # D — fournisseur Meta
    "_send_whatsapp_twilio",              # D — fournisseur Twilio
    "_get_whatsapp_config",               # D — config fournisseur
    "handle_meta_whatsapp_webhook",       # E — webhook entrant + registre STOP
    "send_whatsapp_message",              # garde soeur V442
    "send_whatsapp_template",             # garde soeur V435
    "create_whatsapp_template",           # garde soeur V435
)


_CACHE_REV = {}


def _index_fonctions(rev, chemin):
    """Toutes les fonctions d'un fichier a une revision, indexees par nom.

    Le fichier est lu et analyse UNE SEULE FOIS par revision : `api/server.py`
    fait 30 000 lignes et porte des centaines de fonctions — un `git show` par
    fonction rendait la suite interminable.
    """
    cle = (rev, chemin)
    if cle in _CACHE_REV:
        return _CACHE_REV[cle]
    try:
        texte = subprocess.check_output(["git", "show", "%s:%s" % (rev, chemin)],
                                        cwd=RACINE, stderr=subprocess.DEVNULL).decode("utf-8")
    except subprocess.CalledProcessError:
        _CACHE_REV[cle] = {}
        return {}
    _CACHE_REV[cle] = _indexer(texte)
    return _CACHE_REV[cle]


def _indexer(texte):
    """nom -> LISTE des sources de toutes les fonctions portant ce nom.

    Une liste, pas une chaine : `api/server.py` porte des noms EN DOUBLE
    (`_date` trois fois, `upload_custom_emoji` deux fois — fonctions locales et
    routes distinctes). Avec un dictionnaire simple, la derniere occurrence
    ecrasait les autres et la comparaison signalait comme « modifiees » des
    fonctions auxquelles personne n'avait touche.
    """
    lg = texte.splitlines(True)
    index = {}
    for x in ast.walk(ast.parse(texte)):
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index.setdefault(x.name, []).append(
                "".join(lg[x.lineno - 1:x.end_lineno]))
    return index


INDEX_TRAVAIL = _indexer(SOURCE)


def _src_au(rev, chemin, nom):
    return _index_fonctions(rev, chemin).get(nom)


# Le commit de ce lot. On compare V450 a SON PROPRE PARENT, jamais l'arbre de
# travail a un hachage fige : sinon le garde-fou tomberait en panne des qu'un
# correctif ULTERIEUR et parfaitement legitime toucherait l'une de ces
# fonctions. L'invariant « le commit V450 n'a pas touche au canal metier »,
# lui, reste vrai pour toujours. Meme raisonnement que V442 (S9b).
V450 = "1a7a0a70"


def tests_non_regression_metier():
    """Ce lot ne doit toucher QUE les 4 handlers, et AUCUN chemin metier."""
    if _index_fonctions(V450, "api/server.py") == {}:
        verifier("D/E. le commit V450 est visible par git", False,
                 "revision %s introuvable" % V450)
        return
    verifier("D/E. le commit V450 est visible par git", True)

    for nom in INTOUCHABLES_SERVEUR:
        avant = _src_au(V450 + "^", "api/server.py", nom)
        apres = _src_au(V450, "api/server.py", nom)
        verifier("D/E. le commit V450 n'a pas touche a %s" % nom,
                 avant is not None and avant == apres,
                 "modifie" if avant != apres else "absent du parent")

    # E — l'opt-out (C3), source de verite du refus, n'est pas touche non plus.
    for nom in ("p1b_destinataire_autorise",):
        avant = _src_au(V450 + "^", "api/server.py", nom)
        if avant is None:
            continue
        verifier("E.   le commit V450 n'a pas touche a %s" % nom,
                 avant == _src_au(V450, "api/server.py", nom), "")

    # Aucun fichier metier ne doit apparaitre dans le diff de ce lot.
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", V450 + "^", V450], cwd=RACINE).decode("utf-8").split()
    autorises = {"api/server.py", "tests/test_v450_routes_test_whatsapp.py"}
    hors = [f for f in diff if f not in autorises]
    verifier("D/E. le lot ne modifie AUCUN autre fichier", hors == [], " ".join(hors))

    # Et dans api/server.py, seules les 4 fonctions du lot changent.
    parent = _index_fonctions(V450 + "^", "api/server.py")
    lot = _index_fonctions(V450, "api/server.py")
    change = [nom for nom, srcs in lot.items()
              if nom not in parent or parent[nom] != srcs]
    attendues = {f for f, _, _ in ROUTES}
    verifier("D/E. seules les 4 routes du lot sont modifiees dans server.py",
             set(change) <= attendues, "aussi : %s" % sorted(set(change) - attendues))
    verifier("D/E. les 4 routes du lot sont bien toutes modifiees",
             attendues <= set(change), "manquantes : %s" % sorted(attendues - set(change)))


def main():
    tests_structurels()
    tests_non_regression_metier()
    bac = construire()
    asyncio.new_event_loop().run_until_complete(scenario_refus(bac))
    asyncio.new_event_loop().run_until_complete(scenario_legitime(bac))

    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    vus = set()
    for nom, r, detail in RESULTATS:
        if r and nom in vus:
            continue
        vus.add(nom)
        print(("  OK   " if r else "  ECHEC") + "  " + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    reels = [a for a in APPELS_META if "graph.facebook.com" in a.get("url", "")
             and not a["url"].startswith("https://graph.facebook.com/v21.0/1062611940271584")]
    print("Appels reseau REELS declenches par cette suite : 0 "
          "(httpx remplace par un mouchard, %d appel(s) simule(s) captures)"
          % len(APPELS_META))
    print("Envois WhatsApp REELS : 0")
    print("%d/%d tests passes" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

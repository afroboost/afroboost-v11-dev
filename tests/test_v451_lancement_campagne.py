# -*- coding: utf-8 -*-
"""V451 — UN ANONYME NE LANCE PLUS UNE CAMPAGNE DE MASSE.

CE QUE CE LOT REPARE. `POST /api/campaigns/{campaign_id}/launch` n'avait AUCUNE
authentification. Sa signature etait `async def launch_campaign(campaign_id: str)` :
sans parametre `Request`, l'authentification y etait STRUCTURELLEMENT impossible,
pas seulement oubliee — exactement le defaut ferme par V450 sur les routes de test.

Preuve mesuree en production le 26/08/2026, sans rien envoyer (identifiant
volontairement inexistant, la campagne n'existe pas donc aucun destinataire) :

    POST https://afroboost.com/api/campaigns/id-inexistant-preuve-audit-v450/launch
    -> HTTP 404  {"detail":"Campaign not found"}

404 et non 403 : le handler s'executait pour un anonyme. Avec un `campaign_id`
REEL, n'importe qui declenchait l'envoi de masse sur toute l'audience — WhatsApp,
e-mail ET push. Le canal e-mail (Resend) etant operationnel, le risque n'etait
meme pas theorique.

CE QU'IL N'INVENTE PAS. Aucune authentification nouvelle. On reutilise
`_v309_require_coach_or_admin`, deja en service sur les routes de LECTURE du
dashboard (`/api/users`, `/api/contacts/all`) : JWT signe, coach ou admin, 403
sinon. Le drapeau `REQUIRE_COACH_JWT` est deja a `true` en production, et ces
routes rendent un dashboard PLEIN au proprietaire — la preuve que son jeton
signe existe est donc anterieure a ce lot.

CE QU'IL NE TOUCHE PAS. `launch_campaign` — 754 lignes — n'est pas modifiee d'un
octet : credits et tarification, resolution des destinataires, segmentation,
depliage des groupes, opt-out C3, registre STOP S1, deduplication, verrou
anti-doublon atomique, fournisseurs. Seul son DECORATEUR de route se deplace
vers une enveloppe de 12 lignes qui garde, verifie la propriete, puis delegue.
Les appels INTERNES (`_cron_check_campaigns_body`, la boucle de fond) appellent
la fonction Python et ne passent JAMAIS par l'enveloppe : le cron n'a pas de
jeton, et n'en a pas besoin.

Aucun reseau. Aucun WhatsApp. Aucun e-mail. Aucun push. Aucune base.

Lancement :  python3 tests/test_v451_lancement_campagne.py
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

SECRET = "secret-de-test-v451-jamais-en-production-32o+"
ADMIN = "contact.artboost@gmail.com"
ADMIN2 = "afroboost.bassi@gmail.com"
COACH = "coach.proprietaire@example.com"
AUTRE_COACH = "coach.voisin@example.com"
INCONNU = "personne@example.com"

ENVELOPPE = "v451_lancer_campagne_http"
ROUTE = "POST /api/campaigns/{campaign_id}/launch"

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom, arbre=None):
    for n in ast.walk(arbre or ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("fonction introuvable : %s" % nom)


def extraire(nom):
    n = noeud(nom)
    return "".join(LIGNES[n.lineno - 1:n.end_lineno])


def code_nu(nom):
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps), corps


# ----------------------------------------------------------------------------
# Bac a sable
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


CAMPAGNES = {
    "camp-du-coach":  {"id": "camp-du-coach",  "coach_id": COACH,  "name": "Campagne du coach"},
    "camp-du-voisin": {"id": "camp-du-voisin", "coach_id": AUTRE_COACH, "name": "Campagne du voisin"},
    "camp-admin":     {"id": "camp-admin",     "coach_id": ADMIN,  "name": "Campagne admin"},
    "camp-vide":      {"id": "camp-vide",      "coach_id": COACH,  "name": "Campagne sans cible"},
    "camp-orpheline": {"id": "camp-orpheline", "name": "Campagne sans coach_id"},
}

# Ce que le moteur d'envoi rendrait. `camp-vide` : aucune cible, donc aucun envoi.
RENDUS = {
    "camp-vide": {"status": "completed", "results": []},
}

LANCEMENTS = []          # tout appel au moteur atterrit ICI
ENVOIS_PROVIDER = []     # doit rester VIDE en toutes circonstances


async def faux_launch_campaign(campaign_id):
    """Mouchard : enregistre au lieu de lancer. AUCUN fournisseur n'est joint."""
    LANCEMENTS.append(campaign_id)
    return RENDUS.get(campaign_id, {"status": "completed",
                                    "results": [{"channel": "whatsapp", "status": "success"}]})


class FausseCollection:
    def __init__(self, docs, cle="id"):
        self._docs, self._cle = docs, cle

    async def find_one(self, requete, projection=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in requete.items()):
                return dict(d)
        return None


class FausseBase:
    campaigns = FausseCollection(list(CAMPAGNES.values()))
    coaches = FausseCollection([{"email": COACH}, {"email": AUTRE_COACH}])
    coach_auth = FausseCollection([{"email": COACH}, {"email": AUTRE_COACH}])


def construire():
    os.environ["JWT_SECRET"] = SECRET
    bac = {
        "os": os, "HTTPException": HTTPException, "Request": FausseRequete,
        "SUPER_ADMIN_EMAILS": [ADMIN, ADMIN2],
        "db": FausseBase,
        "launch_campaign": faux_launch_campaign,
        "logger": type("l", (), {"warning": staticmethod(lambda *a, **k: None),
                                 "info": staticmethod(lambda *a, **k: None),
                                 "error": staticmethod(lambda *a, **k: None)}),
        "api_router": type("r", (), {"post": staticmethod(lambda *a, **k: (lambda f: f))}),
    }
    code = "\n".join([extraire("is_super_admin"),
                      extraire("_v311_coach_email_from_jwt"),
                      extraire("_v309_is_coach_or_admin"),
                      extraire("_v309_require_coach_or_admin"),
                      extraire(ENVELOPPE)])
    exec(compile(code, "<v451-extrait-de-server.py>", "exec"), bac)
    return bac


def jeton(email, secret=SECRET, type_=None, exp=None):
    import jwt as pyjwt
    corps = {"email": email}
    if type_:
        corps["type"] = type_
    if exp:
        corps["exp"] = exp
    return pyjwt.encode(corps, secret, algorithm="HS256")


async def appeler(bac, campaign_id, headers):
    try:
        r = await bac[ENVELOPPE](campaign_id=campaign_id, request=FausseRequete(headers))
        return ("ok", r)
    except HTTPException as e:
        return ("refus", e.status_code)
    except TypeError as e:
        return ("signature", str(e))


B = lambda t: {"Authorization": "Bearer " + t}


# ----------------------------------------------------------------------------
# 1. APPEL ANONYME -> REFUS, ET AUCUN FOURNISSEUR APPELE
# ----------------------------------------------------------------------------
async def scenario_refus(bac):
    refus = [
        ("anonyme (aucun en-tete)", {}),
        ("X-User-Email forge d'un super-admin", {"X-User-Email": ADMIN}),
        ("X-User-Email forge d'un coach", {"X-User-Email": COACH}),
        ("JWT signe d'un AUTRE secret", B(jeton(ADMIN, secret="mauvais-secret"))),
        ("JWT sans signature (alg=none)", B("eyJhbGciOiJub25lIn0.eyJlbWFpbCI6ImEifQ.")),
        ("jeton illisible", B("pas-du-tout-un-jwt")),
        ("Bearer vide", B("")),
        ("schema Basic au lieu de Bearer", {"Authorization": "Basic " + jeton(ADMIN)}),
        ("JWT expire", B(jeton(ADMIN, exp=1))),
        ("JWT sans champ email", B(jeton(None))),
        ("JWT valide d'un e-mail NI coach NI admin", B(jeton(INCONNU))),
    ]
    for nom, h in refus:
        LANCEMENTS.clear()
        etat, val = await appeler(bac, "camp-du-coach", h)
        verifier("1. ANONYME  %s -> refus" % nom,
                 etat == "refus" and val == 403, "%s %s" % (etat, val))
        verifier("2. ^ AUCUN fournisseur appele", LANCEMENTS == [] and ENVOIS_PROVIDER == [],
                 "lancements=%s" % LANCEMENTS)

    # Le secret absent ferme, il n'ouvre pas.
    ancien = os.environ.get("JWT_SECRET", "")
    os.environ["JWT_SECRET"] = ""
    LANCEMENTS.clear()
    etat, val = await appeler(bac, "camp-du-coach", B(jeton(ADMIN)))
    verifier("1. ANONYME  JWT_SECRET absent -> on ferme", etat == "refus" and val == 403,
             "%s %s" % (etat, val))
    verifier("2. ^ AUCUN fournisseur appele", LANCEMENTS == [], str(LANCEMENTS))
    os.environ["JWT_SECRET"] = ancien


# ----------------------------------------------------------------------------
# 2. CLOISONNEMENT — un coach ne lance pas la campagne d'un autre
# ----------------------------------------------------------------------------
async def scenario_cloisonnement(bac):
    LANCEMENTS.clear()
    etat, val = await appeler(bac, "camp-du-voisin", B(jeton(COACH)))
    verifier("3. CLOISON  un coach ne lance pas la campagne d'un AUTRE coach",
             etat == "refus" and val == 403, "%s %s" % (etat, val))
    verifier("3. ^ AUCUN fournisseur appele", LANCEMENTS == [], str(LANCEMENTS))

    LANCEMENTS.clear()
    etat, val = await appeler(bac, "camp-orpheline", B(jeton(COACH)))
    verifier("3. CLOISON  campagne SANS coach_id refusee a un coach ordinaire",
             etat == "refus" and val == 403, "%s %s" % (etat, val))
    verifier("3. ^ AUCUN fournisseur appele", LANCEMENTS == [], str(LANCEMENTS))

    LANCEMENTS.clear()
    etat, val = await appeler(bac, "id-qui-n-existe-pas", B(jeton(COACH)))
    verifier("3. CLOISON  campagne inconnue -> 404 (comportement historique)",
             etat == "refus" and val == 404, "%s %s" % (etat, val))
    verifier("3. ^ AUCUN fournisseur appele", LANCEMENTS == [], str(LANCEMENTS))


# ----------------------------------------------------------------------------
# 3. LE LEGITIME GARDE LE COMPORTEMENT HISTORIQUE
# ----------------------------------------------------------------------------
async def scenario_legitime(bac):
    for nom, email, camp in (
            ("le coach proprietaire", COACH, "camp-du-coach"),
            ("le super-admin sur sa campagne", ADMIN, "camp-admin"),
            ("le super-admin sur la campagne d'un coach", ADMIN, "camp-du-coach"),
            ("le second super-admin", ADMIN2, "camp-du-voisin"),
            ("un coach avec casse/espaces differents", "  Coach.Proprietaire@EXAMPLE.com  ",
             "camp-du-coach")):
        LANCEMENTS.clear()
        etat, val = await appeler(bac, camp, B(jeton(email)))
        verifier("4. LEGITIME  %s lance" % nom, etat == "ok", "%s %s" % (etat, val))
        verifier("4. ^ le moteur historique est appele UNE fois, avec le bon id",
                 LANCEMENTS == [camp], str(LANCEMENTS))
        verifier("4. ^ la reponse du moteur est rendue TELLE QUELLE",
                 isinstance(val, dict) and "results" in val, str(val)[:90])

    # Campagne vide -> le moteur est appele et ne fait rien. L'enveloppe ne doit
    # ni court-circuiter ni inventer un envoi.
    LANCEMENTS.clear()
    etat, val = await appeler(bac, "camp-vide", B(jeton(COACH)))
    verifier("5. VIDE  campagne sans cible : deleguee au moteur", etat == "ok" and LANCEMENTS == ["camp-vide"],
             "%s %s" % (etat, LANCEMENTS))
    verifier("5. VIDE  ^ aucun envoi n'est fabrique par l'enveloppe",
             isinstance(val, dict) and val.get("results") == [], str(val)[:90])


# ----------------------------------------------------------------------------
# 4. STRUCTURE
# ----------------------------------------------------------------------------
def tests_structurels():
    # L'enveloppe existe et porte le decorateur de route.
    try:
        env = noeud(ENVELOPPE)
    except AssertionError:
        verifier("S1. l'enveloppe %s existe" % ENVELOPPE, False, "introuvable")
        return
    verifier("S1. l'enveloppe %s existe" % ENVELOPPE, True)

    decos = [ast.unparse(d) for d in env.decorator_list]
    verifier("S2. l'enveloppe porte la route %s" % ROUTE,
             any("campaigns/{campaign_id}/launch" in d for d in decos), str(decos))

    args = [a.arg for a in env.args.args]
    annot = {a.arg: ast.unparse(a.annotation) for a in env.args.args if a.annotation}
    verifier("S3. l'enveloppe recoit campaign_id ET request",
             "campaign_id" in args and "request" in args, str(args))
    verifier("S4. `request` est annote Request (contrat FastAPI)",
             annot.get("request") == "Request", str(annot))
    verifier("S5. `campaign_id` est annote str (chemin d'URL inchange)",
             annot.get("campaign_id") == "str", str(annot))

    nu, corps = code_nu(ENVELOPPE)
    verifier("S6. la garde est la TOUTE PREMIERE instruction executee",
             bool(corps) and "_v309_require_coach_or_admin" in ast.unparse(corps[0]),
             ast.unparse(corps[0])[:90] if corps else "corps vide")
    verifier("S7. garde REUTILISEE, aucune auth inventee",
             nu.count("_v309_require_coach_or_admin") == 1
             and "X-User-Email" not in nu and "Referer" not in nu
             and "Origin" not in nu and "secret" not in nu.lower(), nu[:150])
    verifier("S8. l'enveloppe delegue au moteur historique launch_campaign",
             "launch_campaign(" in nu, nu[:150])
    verifier("S9. l'enveloppe reste une ENVELOPPE (moins de 30 instructions)",
             len(corps) < 30, "%d instructions" % len(corps))

    # Le moteur ne porte plus de decorateur de route : une seule porte HTTP.
    moteur = noeud("launch_campaign")
    verifier("S10. launch_campaign n'est PLUS une route HTTP",
             moteur.decorator_list == [], str([ast.unparse(d) for d in moteur.decorator_list]))
    verifier("S11. launch_campaign n'a PAS gagne de parametre request",
             [a.arg for a in moteur.args.args] == ["campaign_id"],
             str([a.arg for a in moteur.args.args]))

    # Une seule route porte ce chemin : pas de doublon oublie.
    portes = [n.name for n in ast.walk(ARBRE)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and any("campaigns/{campaign_id}/launch" in ast.unparse(d)
                      for d in n.decorator_list)]
    verifier("S12. une SEULE porte HTTP vers le lancement", portes == [ENVELOPPE], str(portes))

    # Les appels INTERNES visent la fonction, jamais l'enveloppe.
    internes = [ast.unparse(c) for c in ast.walk(ARBRE)
                if isinstance(c, ast.Call) and ENVELOPPE + "(" in ast.unparse(c)]
    verifier("S13. aucun code backend n'appelle l'enveloppe (le cron reste direct)",
             internes == [], " | ".join(internes))
    appels_moteur = [ast.unparse(c) for c in ast.walk(ARBRE)
                     if isinstance(c, ast.Call) and ast.unparse(c).startswith("launch_campaign(")]
    verifier("S14. le cron appelle toujours le moteur en direct",
             any("campaign_id" in a for a in appels_moteur), str(appels_moteur))


# ----------------------------------------------------------------------------
# 5. NON-REGRESSION : le moteur et le canal metier sont INTACTS
# ----------------------------------------------------------------------------
_CACHE_REV = {}


def _indexer(texte):
    """nom -> LISTE des sources (api/server.py porte des noms en double)."""
    lg = texte.splitlines(True)
    index = {}
    for x in ast.walk(ast.parse(texte)):
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
            index.setdefault(x.name, []).append("".join(lg[x.lineno - 1:x.end_lineno]))
    return index


def _index_rev(rev):
    if rev not in _CACHE_REV:
        try:
            t = subprocess.check_output(["git", "show", "%s:api/server.py" % rev],
                                        cwd=RACINE, stderr=subprocess.DEVNULL).decode("utf-8")
            _CACHE_REV[rev] = _indexer(t)
        except subprocess.CalledProcessError:
            _CACHE_REV[rev] = {}
    return _CACHE_REV[rev]


INDEX_TRAVAIL = _indexer(SOURCE)

INTOUCHABLES = (
    "launch_campaign",                    # le moteur : credits, cibles, segmentation
    "_send_whatsapp_campaign_template",   # template de campagne
    "send_whatsapp_direct",               # moteur d'envoi
    "_send_whatsapp_meta",                # fournisseur Meta
    "_send_whatsapp_twilio",              # fournisseur Twilio
    "_get_whatsapp_config",               # config fournisseur
    "handle_meta_whatsapp_webhook",       # webhook entrant + registre STOP (S1)
    "c3_refus_exprimes",                  # opt-out C3 : lecture des refus
    "c3_verdict",                         # opt-out C3 : verdict par destinataire
    "check_credits",                      # tarification
    "deduct_credit",                      # tarification
    "_parse_scheduled_at",                # programmation
)


def tests_non_regression():
    """Comparaison au dernier commit : tant que le lot n'est pas commite, HEAD
    EST le parent. Le commit qui suivra figera ce garde-fou sur son propre SHA
    (motif V442/V450), pour qu'il survive aux correctifs ulterieurs."""
    tete = _index_rev("HEAD")
    if not tete:
        verifier("N0. la revision HEAD est lisible", False, "git indisponible")
        return
    verifier("N0. la revision HEAD est lisible", True)

    for nom in INTOUCHABLES:
        avant, apres = tete.get(nom), INDEX_TRAVAIL.get(nom)
        if avant is None:
            continue
        verifier("6/7/8. %s INCHANGE (octet pour octet)" % nom, avant == apres,
                 "MODIFIE" if avant != apres else "")

    diff = subprocess.check_output(["git", "diff", "--name-only", "HEAD"],
                                   cwd=RACINE).decode("utf-8").split()
    autorises = {"api/server.py", "tests/test_v451_lancement_campagne.py"}
    hors = [f for f in diff if f not in autorises]
    verifier("9. le lot ne modifie AUCUN autre fichier", hors == [], " ".join(hors))

    change = [n for n, s in INDEX_TRAVAIL.items() if n not in tete or tete[n] != s]
    verifier("9. dans server.py, SEULE l'enveloppe est ajoutee",
             set(change) <= {ENVELOPPE}, "aussi : %s" % sorted(set(change) - {ENVELOPPE}))


def main():
    tests_structurels()
    tests_non_regression()
    try:
        bac = construire()
    except AssertionError as e:
        # Etat AVANT correctif : l'enveloppe n'existe pas encore. On le dit une
        # fois, clairement, au lieu de faire tomber la suite avec une trace.
        verifier("SCENARIOS  non joues : %s" % e, False,
                 "l'enveloppe gardee n'existe pas encore")
        bac = None
    if bac is not None:
        for scen in (scenario_refus, scenario_cloisonnement, scenario_legitime):
            asyncio.new_event_loop().run_until_complete(scen(bac))

    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    vus = set()
    for nom, r, detail in RESULTATS:
        if r and nom in vus:
            continue
        vus.add(nom)
        print(("  OK   " if r else "  ECHEC") + "  " + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Campagnes REELLEMENT lancees : 0 (moteur remplace par un mouchard)")
    print("WhatsApp / e-mails / push envoyes : 0 — aucun fournisseur charge")
    print("Ecritures en production : 0 — aucune base, aucun reseau")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

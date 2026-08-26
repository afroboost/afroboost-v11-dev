# -*- coding: utf-8 -*-
"""V453 — LE WEBHOOK META VERIFIE SA SIGNATURE. DRAPEAU PAR DEFAUT A OFF.

CE QUE CE LOT PREPARE. `POST /api/webhook/whatsapp-meta` n'a AUCUN controle
d'origine. Un POST forge qui imite un message entrant fait repondre le bot —
donc ENVOIE un vrai WhatsApp au numero choisi par l'attaquant — et peut ecrire
un faux STOP au nom de n'importe quel numero, desabonnant un client a son insu.

CE QU'IL NE FAIT PAS ENCORE. Le drapeau `META_WEBHOOK_SIGNATURE_ENABLED` est a
FALSE par defaut. Tant qu'il n'est pas bascule, le webhook se comporte EXACTEMENT
comme aujourd'hui : aucune requete legitime n'est refusee. Le lot pose la
mecanique et l'observation, pas le refus.

POURQUOI UN DRAPEAU EN BASE ET NON UNE VARIABLE D'ENVIRONNEMENT. C'est la
convention du projet (V319, V344, V349, V367) : lu EN DIRECT a chaque requete,
donc basculable — et surtout RETOMBABLE — sans redeploiement. Si la verification
etranglait le trafic entrant, il faut pouvoir l'eteindre en une seconde, pas en
quatre minutes de rebuild.

LA REGLE DU HMAC. La signature se calcule sur les OCTETS BRUTS recus, jamais sur
du JSON re-serialise. Mesure faite le 26/08/2026 sur un vrai FastAPI :
    corps recu        -> sha256 9ea864bc1cb3c316
    JSON re-serialise -> sha256 f139005dd67133ef   (DIFFERENT)
Recalculer depuis le JSON produirait donc un refus systematique.

CE QU'IL NE TOUCHE PAS : le handshake GET de Meta (route distincte, que Meta ne
signe pas), V450, V451, les campagnes, la normalisation des numeros, le STOP
sortant, les rappels avant cours, AUTO-PRESENCE, P1-d, la facturation Meta.

Aucun reseau. Aucune base. Aucun envoi. Aucun secret imprime.

Lancement :  python3 tests/test_v453_signature_webhook_meta.py
"""
import ast
import asyncio
import hashlib
import hmac as _hmac
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

GARDE = "_v453_signature_refusee"
DRAPEAU = "META_WEBHOOK_SIGNATURE_ENABLED"
VARIABLE = "META_APP_SECRET"
ENTETE = "X-Hub-Signature-256"

# Secret fictif du bac a sable. Ne doit apparaitre dans AUCUN journal.
# VOLONTAIREMENT OPAQUE : un secret de test contenant un mot comme « SECRET »
# declencherait un faux positif, ce mot figurant deja dans le NOM de la variable
# (« META_APP_SECRET absent... ») que le code journalise legitimement. On cherche
# la fuite d'une VALEUR, pas la presence d'un mot du vocabulaire du projet.
FAUX_SECRET = "k7Qz3vNb8pR2wX5yT9mL4hJ6dS1gA0cF"

# Corps realistes, aux octets EXACTS (espaces et ordre compris).
CORPS_STOP = (b'{"object":"whatsapp_business_account","entry":[{"id":"1","changes":'
              b'[{"value":{"messages":[{"from":"41791234567","type":"text",'
              b'"text":{"body":"STOP"}}]},"field":"messages"}]}]}')
CORPS_NORMAL = (b'{"object":"whatsapp_business_account","entry":[{"id":"1","changes":'
                b'[{"value":{"messages":[{"from":"41791234567","type":"text",'
                b'"text":{"body":"Bonjour, quels sont les horaires ?"}}]},'
                b'"field":"messages"}]}]}')

RESULTATS = []
JOURNAL = []          # tout ce que le code journalise atterrit ICI


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def noeud(nom, arbre=None):
    """Fonction OU classe : le drapeau se declare aussi dans deux modeles Pydantic
    (`FeatureFlags` et `FeatureFlagsUpdate`), qui sont des ClassDef."""
    for n in ast.walk(arbre or ARBRE):
        if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and n.name == nom):
            return n
    raise AssertionError("introuvable : %s" % nom)


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


def signature(corps, secret=FAUX_SECRET):
    return "sha256=" + _hmac.new(secret.encode("utf-8"), corps, hashlib.sha256).hexdigest()


# ----------------------------------------------------------------------------
# Bac a sable
# ----------------------------------------------------------------------------
class FausseRequete:
    def __init__(self, headers=None):
        self._h = {k.lower(): v for k, v in (headers or {}).items()}
        self.headers = self

    def get(self, cle, defaut=""):
        return self._h.get(cle.lower(), defaut)


class FauxLogger:
    @staticmethod
    def _note(niveau):
        def f(*a, **k):
            try:
                JOURNAL.append(str(a[0]) % tuple(a[1:]) if len(a) > 1 else str(a[0]))
            except Exception:
                JOURNAL.append(" ".join(str(x) for x in a))
        return staticmethod(f)


DRAPEAUX = {DRAPEAU: False}
PANNE_DRAPEAU = {"actif": False}


async def faux_get_feature_flags():
    if PANNE_DRAPEAU["actif"]:
        raise RuntimeError("MongoDB injoignable (simule)")
    return dict(DRAPEAUX)


def construire():
    log = type("l", (), {"info": FauxLogger._note("info"),
                         "warning": FauxLogger._note("warning"),
                         "error": FauxLogger._note("error")})
    bac = {"os": os, "logger": log, "get_feature_flags": faux_get_feature_flags,
           "Request": FausseRequete}
    exec(compile(extraire(GARDE), "<v453-extrait-de-server.py>", "exec"), bac)
    return bac


async def refuse(bac, corps, entetes, secret=FAUX_SECRET, drapeau=False, panne=False):
    """Renvoie True si la garde demande le REFUS."""
    anc = os.environ.get(VARIABLE)
    if secret is None:
        os.environ.pop(VARIABLE, None)
    else:
        os.environ[VARIABLE] = secret
    DRAPEAUX[DRAPEAU] = drapeau
    PANNE_DRAPEAU["actif"] = panne
    try:
        return await bac[GARDE](FausseRequete(entetes), corps)
    finally:
        PANNE_DRAPEAU["actif"] = False
        if anc is None:
            os.environ.pop(VARIABLE, None)
        else:
            os.environ[VARIABLE] = anc


# ----------------------------------------------------------------------------
# A -> I : la mecanique de signature
# ----------------------------------------------------------------------------
async def scenario_signature(bac):
    ok = {ENTETE: signature(CORPS_NORMAL)}
    faux = {ENTETE: "sha256=" + "0" * 64}
    autre_secret = {ENTETE: signature(CORPS_NORMAL, "un-autre-secret-completement")}

    # --- drapeau OFF : comportement historique, QUOI QU'IL ARRIVE (F) ---
    for nom, ent, corps in (
            ("signature absente", {}, CORPS_NORMAL),
            ("signature valide", ok, CORPS_NORMAL),
            ("signature invalide", faux, CORPS_NORMAL),
            ("mauvais secret", autre_secret, CORPS_NORMAL),
            ("corps STOP sans signature", {}, CORPS_STOP)):
        r = await refuse(bac, corps, ent, drapeau=False)
        verifier("F. DRAPEAU OFF + %s -> AUCUN refus (historique)" % nom, r is False, repr(r))

    r = await refuse(bac, CORPS_NORMAL, {}, secret=None, drapeau=False)
    verifier("F. DRAPEAU OFF + secret absent -> AUCUN refus", r is False, repr(r))

    # --- drapeau ON ---
    r = await refuse(bac, CORPS_NORMAL, ok, drapeau=True)
    verifier("I. DRAPEAU ON + signature VALIDE -> traitement normal", r is False, repr(r))
    verifier("A. signature correcte reconnue valide", r is False, repr(r))

    r = await refuse(bac, CORPS_NORMAL, faux, drapeau=True)
    verifier("H. DRAPEAU ON + signature INVALIDE -> refus", r is True, repr(r))
    verifier("B. signature incorrecte reconnue invalide", r is True, repr(r))

    r = await refuse(bac, CORPS_NORMAL, {}, drapeau=True)
    verifier("G. DRAPEAU ON + signature ABSENTE -> refus", r is True, repr(r))
    verifier("C. signature absente reconnue invalide", r is True, repr(r))

    # D — un seul octet change dans le corps invalide la signature
    corps_altere = CORPS_NORMAL.replace(b"Bonjour", b"Bonsoir")
    verifier("D. le corps altere fait bien la MEME taille (test honnete)",
             len(corps_altere) == len(CORPS_NORMAL), "%d vs %d" % (len(corps_altere), len(CORPS_NORMAL)))
    r = await refuse(bac, corps_altere, ok, drapeau=True)
    verifier("D. corps modifie apres signature -> refus", r is True, repr(r))

    # un seul octet, vraiment
    corps_1octet = bytearray(CORPS_NORMAL); corps_1octet[10] ^= 0x01
    r = await refuse(bac, bytes(corps_1octet), ok, drapeau=True)
    verifier("D. UN SEUL octet modifie -> refus", r is True, repr(r))

    # E — mauvais secret
    r = await refuse(bac, CORPS_NORMAL, autre_secret, drapeau=True)
    verifier("E. signature calculee avec un AUTRE secret -> refus", r is True, repr(r))

    # secret absent alors que la verification est ACTIVE -> refus sur (fail closed)
    r = await refuse(bac, CORPS_NORMAL, ok, secret=None, drapeau=True)
    verifier("3. DRAPEAU ON + META_APP_SECRET absent -> refus sur (fail closed)", r is True, repr(r))

    # panne de lecture du drapeau -> on N'ACTIVE PAS (ne jamais tuer le canal)
    r = await refuse(bac, CORPS_NORMAL, {}, drapeau=True, panne=True)
    verifier("2. panne de lecture du drapeau -> on n'active PAS (canal preserve)",
             r is False, repr(r))

    # --- formes tordues de l'en-tete ---
    for nom, val in (("sans le prefixe sha256=", signature(CORPS_NORMAL).split("=", 1)[1]),
                     ("prefixe seul", "sha256="),
                     ("valeur vide", ""),
                     ("espaces autour", "  " + signature(CORPS_NORMAL) + "  "),
                     ("hexa tronque", signature(CORPS_NORMAL)[:-4])):
        r = await refuse(bac, CORPS_NORMAL, {ENTETE: val}, drapeau=True)
        attendu = (nom == "espaces autour")      # seul un simple habillage reste valide
        verifier("B. DRAPEAU ON + en-tete %s -> %s" % (nom, "accepte" if attendu else "refus"),
                 r is (not attendu), repr(r))

    # casse de l'hexadecimal : Meta envoie en minuscules, on ne doit pas etre pointilleux
    sig_maj = signature(CORPS_NORMAL).replace("sha256=", "sha256=").upper().replace("SHA256=", "sha256=")
    r = await refuse(bac, CORPS_NORMAL, {ENTETE: sig_maj}, drapeau=True)
    verifier("A. signature valide en MAJUSCULES -> acceptee", r is False, repr(r))


# ----------------------------------------------------------------------------
# J / K / L : STOP et bot entrant
# ----------------------------------------------------------------------------
async def scenario_stop_et_bot(bac):
    r = await refuse(bac, CORPS_STOP, {ENTETE: signature(CORPS_STOP)}, drapeau=True)
    verifier("J. STOP + bonne signature -> passe (traitement inchange)", r is False, repr(r))

    r = await refuse(bac, CORPS_STOP, {ENTETE: "sha256=" + "f" * 64}, drapeau=True)
    verifier("K. STOP FORGE (mauvaise signature) -> bloque", r is True, repr(r))

    r = await refuse(bac, CORPS_STOP, {}, drapeau=True)
    verifier("K. STOP sans signature -> bloque", r is True, repr(r))

    r = await refuse(bac, CORPS_STOP, {}, drapeau=False)
    verifier("J. STOP sans signature, drapeau OFF -> passe (aucune regression)", r is False, repr(r))

    r = await refuse(bac, CORPS_NORMAL, {ENTETE: signature(CORPS_NORMAL)}, drapeau=True)
    verifier("L. message normal + bonne signature -> le bot repond comme avant", r is False, repr(r))

    r = await refuse(bac, CORPS_NORMAL, {ENTETE: "sha256=" + "a" * 64}, drapeau=True)
    verifier("5. message normal + mauvaise signature -> aucune reponse bot", r is True, repr(r))


# ----------------------------------------------------------------------------
# O : aucun secret ni signature complete dans les journaux
# ----------------------------------------------------------------------------
def scenario_journaux():
    tout = "\n".join(JOURNAL)
    verifier("O. le secret n'apparait dans AUCUN journal", FAUX_SECRET not in tout, "FUITE")
    for morceau in (FAUX_SECRET[:10], FAUX_SECRET[:6], FAUX_SECRET[-10:]):
        verifier("O. aucun morceau du secret (%s...) dans les journaux" % morceau[:4],
                 morceau not in tout, "FUITE")
    sig = signature(CORPS_NORMAL)
    verifier("O. la signature COMPLETE n'apparait dans aucun journal",
             sig not in tout and sig.split("=", 1)[1] not in tout, "FUITE")
    verifier("O. le corps du message n'apparait dans aucun journal",
             b"Bonjour, quels sont les horaires" .decode() not in tout
             and "41791234567" not in tout, "FUITE")
    verifier("7. l'observation journalise bien presence ET validite",
             any("presente" in j and "valide" in j for j in JOURNAL),
             (JOURNAL[:2] or ["(journal vide)"])[0])
    verifier("7. l'observation dit aussi l'etat du drapeau",
             any("OFF" in j or "ON" in j for j in JOURNAL), "")


# ----------------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------------
def tests_structurels():
    try:
        noeud(GARDE)
    except AssertionError:
        verifier("S1. la garde %s existe" % GARDE, False, "introuvable")
        return
    verifier("S1. la garde %s existe" % GARDE, True)

    nu, _ = code_nu(GARDE)
    verifier("S2. HMAC-SHA256 utilise", "hmac" in nu and "sha256" in nu, nu[:150])
    verifier("S3. comparaison en TEMPS CONSTANT (compare_digest)",
             "compare_digest" in nu, nu[:200])
    verifier("S4. jamais de JSON re-serialise (aucun json.dumps / .json())",
             "json.dumps" not in nu and ".json()" not in nu, nu[:200])
    verifier("S5. l'en-tete officiel %s est lu" % ENTETE, ENTETE in nu, nu[:200])
    verifier("S6. le drapeau %s est lu EN DIRECT" % DRAPEAU,
             DRAPEAU in nu and "get_feature_flags" in nu, nu[:250])
    verifier("S7. la variable %s est lue depuis l'environnement" % VARIABLE,
             VARIABLE in nu, nu[:250])
    verifier("S8. aucune troncature/fuite de secret (pas de secret[:n])",
             "secret[:" not in nu and "secret[0:" not in nu, nu[:250])

    # Le handler appelle la garde AVANT toute lecture metier.
    hnu, hcorps = code_nu("handle_meta_whatsapp_webhook")
    idx_garde = hnu.find(GARDE)
    idx_json = hnu.find("request.json()")
    verifier("S9. le webhook appelle la garde", idx_garde >= 0, hnu[:200])
    verifier("S10. la garde est appelee AVANT request.json()",
             idx_garde >= 0 and idx_json >= 0 and idx_garde < idx_json,
             "garde@%d json@%d" % (idx_garde, idx_json))
    verifier("S11. le corps BRUT est lu par request.body()",
             "request.body()" in hnu, hnu[:250])
    verifier("S12. un refus leve bien une erreur HTTP (rien ne s'execute apres)",
             "HTTPException" in hnu, hnu[:300])

    # Le handshake GET ne doit RIEN savoir de la signature.
    gnu, _ = code_nu("verify_meta_whatsapp_webhook")
    verifier("N. le handshake GET ignore totalement la signature",
             ENTETE not in gnu and GARDE not in gnu, gnu[:200])
    verifier("N. le handshake GET garde son verify_token",
             "META_WHATSAPP_VERIFY_TOKEN" in gnu and "hub.challenge" in gnu, gnu[:200])

    # Le drapeau est declare partout, et par defaut a FALSE.
    for bloc, attendu in (("FeatureFlags", "%s: bool = False" % DRAPEAU),
                          ("FeatureFlagsUpdate", "%s: Optional[bool] = None" % DRAPEAU)):
        n = noeud(bloc)
        src = "".join(LIGNES[n.lineno - 1:n.end_lineno])
        verifier("4. %s declare %s (defaut OFF)" % (bloc, DRAPEAU), attendu in src, "")
    fnu, _ = code_nu("get_feature_flags")
    verifier("4. get_feature_flags cree le drapeau a False",
             '"%s": False' % DRAPEAU in fnu or "'%s': False" % DRAPEAU in fnu, "")
    verifier("4. get_feature_flags complete le drapeau a la lecture (documents anciens)",
             '("%s", False)' % DRAPEAU in fnu or "('%s', False)" % DRAPEAU in fnu, "")


# ----------------------------------------------------------------------------
# Non-regression
# ----------------------------------------------------------------------------
INTOUCHABLES = (
    "verify_meta_whatsapp_webhook",   # handshake GET Meta
    "_v332_stop_whatsapp",            # traitement STOP entrant
    "launch_campaign",                # campagnes
    "v451_lancer_campagne_http",      # V451
    "test_whatsapp_template",         # V450
    "test_campaign_3steps",
    "whatsapp_diagnostic",
    "whatsapp_app_info",
    "send_whatsapp_direct",
    "_send_whatsapp_meta",
    "_send_whatsapp_twilio",
    "_get_whatsapp_config",
    "c3_refus_exprimes",
    "c3_verdict",
    "check_credits",
    "deduct_credit",
)

_CACHE = {}


def _index(rev):
    if rev not in _CACHE:
        try:
            t = subprocess.check_output(["git", "show", "%s:api/server.py" % rev],
                                        cwd=RACINE, stderr=subprocess.DEVNULL).decode("utf-8")
            lg = t.splitlines(True)
            idx = {}
            for x in ast.walk(ast.parse(t)):
                if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    idx.setdefault(x.name, []).append("".join(lg[x.lineno - 1:x.end_lineno]))
            _CACHE[rev] = idx
        except subprocess.CalledProcessError:
            _CACHE[rev] = {}
    return _CACHE[rev]


def _index_travail():
    lg = SOURCE.splitlines(True)
    idx = {}
    for x in ast.walk(ARBRE):
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)):
            idx.setdefault(x.name, []).append("".join(lg[x.lineno - 1:x.end_lineno]))
    return idx


def tests_non_regression():
    tete, travail = _index("HEAD"), _index_travail()
    if not tete:
        verifier("N0. la revision HEAD est lisible", False, "git indisponible")
        return
    verifier("N0. la revision HEAD est lisible", True)
    for nom in INTOUCHABLES:
        if nom not in tete:
            continue
        verifier("9. %s INCHANGE par ce lot" % nom, tete[nom] == travail.get(nom), "MODIFIE")
    diff = subprocess.check_output(["git", "diff", "--name-only", "HEAD"],
                                   cwd=RACINE).decode("utf-8").split()
    autorises = {"api/server.py", "tests/test_v453_signature_webhook_meta.py"}
    hors = [f for f in diff if f not in autorises]
    verifier("9. le lot ne modifie AUCUN autre fichier", hors == [], " ".join(hors))
    attendues = {GARDE, "handle_meta_whatsapp_webhook", "get_feature_flags"}
    change = [n for n, s in travail.items() if n not in tete or tete[n] != s]
    verifier("9. seules la garde, le webhook et get_feature_flags changent",
             set(change) <= attendues, "aussi : %s" % sorted(set(change) - attendues))


def main():
    tests_structurels()
    tests_non_regression()
    try:
        bac = construire()
    except AssertionError as e:
        verifier("SCENARIOS non joues : %s" % e, False, "la garde n'existe pas encore")
        bac = None
    if bac is not None:
        boucle = asyncio.new_event_loop()
        boucle.run_until_complete(scenario_signature(bac))
        boucle.run_until_complete(scenario_stop_et_bot(bac))
        scenario_journaux()

    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  OK   " if r else "  ECHEC") + "  " + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Secrets imprimes : 0   |   Reseau : 0   |   Base : 0   |   Envois WhatsApp : 0")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""C9-B — tests hors ligne. Aucune base, aucun reseau, aucun evenement PostHog.

Les fonctions testees sont EXTRAITES du vrai `api/server.py` et du vrai
`api/routes/shared.py` par AST — pas recopiees. Si le code change, le test suit.

POURQUOI HORS LIGNE, STRICTEMENT. Deux raisons, pas une :
  - une fusion PostHog est IRREVERSIBLE ; un test qui en declencherait une ne
    serait pas rattrapable ;
  - un appel reel a smart-entry AVEC des reponses de tunnel creerait un vrai
    lead ET declencherait une vraie notification push au coach.

`ast.get_source_segment` part du `def` : le decorateur `@api_router.post` ne
suit pas, la route redevient une coroutine ordinaire qu'on appelle directement.
"""
import ast
import asyncio
import os
import re as _re_module
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_SERVER = os.path.join(RACINE, "api", "server.py")
SRC_SHARED = os.path.join(RACINE, "api", "routes", "shared.py")


def morceaux(chemin, fonctions, constantes=frozenset()):
    src = open(chemin, encoding="utf-8").read()
    arbre = ast.parse(src)
    out, vus = [], set()
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in fonctions:
            out.append(ast.get_source_segment(src, n))
            vus.add(n.name)
        elif isinstance(n, ast.Assign):
            for c in n.targets:
                if isinstance(c, ast.Name) and c.id in constantes:
                    out.append(ast.get_source_segment(src, n))
                    vus.add(c.id)
    manquants = (fonctions | set(constantes)) - vus
    assert not manquants, "extraction incomplete : %s" % sorted(manquants)
    return "\n\n".join(out)


# --- ce que le module d'origine aurait fourni -------------------------------
class FauxHTTPException(Exception):
    def __init__(self, status_code=400, detail=""):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FausseCollection:
    """Documents en memoire + JOURNAL des filtres reellement envoyes.

    C'est le journal qui prouve ce qui a ete interroge — pas la seule valeur de
    retour. Une comparaison de reponse passerait avec un filtre trop large.
    """

    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.filtres = []

    async def find_one(self, filtre, projection=None):
        self.filtres.append(filtre)
        for d in self.docs:
            ok = True
            for k, v in filtre.items():
                val = d.get(k)
                if isinstance(v, dict) and "$regex" in v:
                    if not (isinstance(val, str)
                            and _re_module.match(v["$regex"], val, _re_module.I)):
                        ok = False
                elif val != v:
                    ok = False
            if ok:
                return dict(d)
        return None


class FausseBase:
    def __init__(self, discount_codes=None):
        self.discount_codes = FausseCollection(discount_codes)


class FauxJournal:
    def __init__(self):
        self.lignes = []

    def warning(self, *a, **k):
        self.lignes.append(("warning", a))

    def info(self, *a, **k):
        self.lignes.append(("info", a))


class FausseRequete:
    def __init__(self, corps):
        self._corps = corps

    async def json(self):
        return self._corps


# --- montage de l'espace de noms --------------------------------------------
NS_SHARED = {"os": os}
exec(morceaux(SRC_SHARED, {"posthog_id", "posthog_actif"}), NS_SHARED)

# `api.routes.shared` est importe PARESSEUSEMENT dans le corps de la route.
# L'importer pour de vrai chargerait `api/routes/__init__.py` -> fastapi, absent
# hors ligne. On pose donc des modules factices AVANT l'appel.
_faux_shared = types.ModuleType("api.routes.shared")
_faux_shared.make_subscriber_token = lambda code, email: "JETON:%s:%s" % (code, email)
_faux_shared.jwt_secret_is_set = lambda: True
_faux_shared.posthog_id = NS_SHARED["posthog_id"]
sys.modules.setdefault("api", types.ModuleType("api"))
sys.modules.setdefault("api.routes", types.ModuleType("api.routes"))
sys.modules["api.routes.shared"] = _faux_shared

NS = {
    "HTTPException": FauxHTTPException,
    "Request": FausseRequete,
    "re": _re_module,
    "logger": FauxJournal(),
    "db": None,
    "get_feature_flags": None,
    "_v261_resolve_subscriber": None,
}
exec(morceaux(SRC_SERVER,
              {"v296_subscriber_token", "is_super_admin"},
              {"SUPER_ADMIN_EMAILS"}), NS)

TOKEN = NS["v296_subscriber_token"]
posthog_id = NS_SHARED["posthog_id"]


def appeler(corps, codes, drapeau=True, code_valide=True, nom="Ana", flags_levent=False):
    """Rejoue la route avec des doublures ; renvoie (reponse, exception)."""
    NS["db"] = FausseBase(codes)
    NS["logger"] = FauxJournal()

    async def _flags():
        if flags_levent:
            raise RuntimeError("base indisponible")
        return {"POSTHOG_IDENTIFY_ENABLED": drapeau}

    async def _resolve(_code):
        return (code_valide, nom, "c1")

    NS["get_feature_flags"] = _flags
    NS["_v261_resolve_subscriber"] = _resolve
    try:
        return asyncio.run(TOKEN(FausseRequete(corps))), None
    except FauxHTTPException as e:
        return None, e


resultats = []


def verifier(nom, obtenu, attendu):
    resultats.append((obtenu == attendu, nom, obtenu, attendu))


ANA = "ana@exemple.ch"
ID_ANA = posthog_id(ANA)
CODE_INDIVIDUEL = [{"code": "AFR-1", "assignedEmail": ANA, "active": True}]
CODE_COLLECTIF = [{"code": "AFR-1", "assignedEmail": "", "active": True}]

# === Le seul cas qui identifie ==============================================
r, e = appeler({"code": "AFR-1", "email": ANA}, CODE_INDIVIDUEL)
verifier("cas 2 — code individuel apparie -> pseudonyme", r["analytics_id"], ID_ANA)
verifier("le pseudonyme a la forme attendue",
         bool(_re_module.fullmatch(r"[0-9a-f]{32}", r["analytics_id"])), True)
# Preuve que le pseudonyme est SALE : sans sel, il vaudrait le sha256 nu de
# l'adresse — donc rejouable par quiconque connait l'adresse. Verifier « pas de @
# dans 32 hexadecimaux » ne prouverait rien : c'est vrai par construction.
import hashlib as _hl
_NU = _hl.sha256(ANA.encode("utf-8")).hexdigest()[:32]
verifier("le pseudonyme n'est PAS le sha256 nu de l'adresse (donc sale)",
         r["analytics_id"] == _NU, False)

# === Les trois cas ambigus : AUCUNE identification ==========================
r, e = appeler({"code": "AFR-1", "email": ""}, CODE_INDIVIDUEL)
verifier("cas 4 — e-mail vide -> aucun pseudonyme", r["analytics_id"], "")

r, e = appeler({"code": "AFR-1", "email": ANA}, CODE_COLLECTIF)
verifier("cas 5 — code collectif -> aucun pseudonyme", r["analytics_id"], "")

r, e = appeler({"code": "AFR-1", "email": ANA}, [])
verifier("code absent de discount_codes -> aucun pseudonyme", r["analytics_id"], "")

# Quatrieme cas ambigu, ajoute apres revue : un meme code peut porter plusieurs
# documents en base, et `find_one` en rend un sans tri. Une ligne desactivee ne
# doit pas suffire a fonder une identite irreversible.
r, e = appeler({"code": "AFR-1", "email": ANA},
               [{"code": "AFR-1", "assignedEmail": ANA, "active": False}])
verifier("document inactif -> aucun pseudonyme", r["analytics_id"], "")
r, e = appeler({"code": "AFR-1", "email": ANA},
               [{"code": "AFR-1", "assignedEmail": ANA}])
verifier("champ `active` absent -> aucun pseudonyme", r["analytics_id"], "")

# === Le proprietaire n'entre jamais dans son propre entonnoir ===============
for _admin in NS["SUPER_ADMIN_EMAILS"]:
    _a = _admin.strip().lower()
    r, e = appeler({"code": "AFR-1", "email": _a},
                   [{"code": "AFR-1", "assignedEmail": _a, "active": True}])
    verifier("cas 6/7 — %s apparie mais JAMAIS identifie" % _a, r["analytics_id"], "")
    verifier("... et son jeton abonne est quand meme emis", bool(r["token"]), True)

r, e = appeler({"code": "AFR-1", "email": "CONTACT.ArtBoost@Gmail.com"},
               [{"code": "AFR-1", "assignedEmail": "contact.artboost@gmail.com", "active": True}])
verifier("la casse ne contourne pas l'exclusion admin", r["analytics_id"], "")

# === Une panne ne bloque jamais, et n'identifie jamais ======================
r, e = appeler({"code": "AFR-1", "email": ANA}, CODE_INDIVIDUEL, flags_levent=True)
verifier("cas 20 — lecture du drapeau en panne -> aucun pseudonyme", r["analytics_id"], "")
verifier("cas 19 — ... et la route repond normalement", r["success"], True)
verifier("... le jeton abonne est intact", r["token"], "JETON:AFR-1:%s" % ANA)

# === Refus ==================================================================
r, e = appeler({"code": "AFR-1", "email": "voisin@exemple.ch"}, CODE_INDIVIDUEL)
verifier("cas 1 — e-mail non apparie -> 403", getattr(e, "status_code", None), 403)
verifier("aucun corps renvoye sur refus, donc aucune fusion", r, None)

r, e = appeler({"code": "INCONNU", "email": ANA}, [], code_valide=False)
verifier("cas 3 — code inexistant -> 403", getattr(e, "status_code", None), 403)

# === Coupe-circuit ==========================================================
r, e = appeler({"code": "AFR-1", "email": ANA}, CODE_INDIVIDUEL, drapeau=False)
verifier("cas 13 — drapeau OFF -> aucun pseudonyme", r["analytics_id"], "")
verifier("drapeau OFF : le jeton abonne est emis NORMALEMENT",
         bool(r["token"]), True)
verifier("drapeau OFF : le parcours metier est intact", r["success"], True)

# === Non-regression du contrat ==============================================
r, e = appeler({"code": "AFR-1", "email": ANA}, CODE_INDIVIDUEL)
verifier("les 4 cles historiques sont conservees",
         sorted(k for k in r if k != "analytics_id"),
         ["name", "secret_set", "success", "token"])
verifier("`analytics_id` est le SEUL ajout", "analytics_id" in r, True)
verifier("le jeton reste calcule comme avant", r["token"], "JETON:AFR-1:%s" % ANA)

# === Stabilite du pseudonyme (cas 5 du cahier : autre navigateur) ===========
verifier("cas 5 — meme personne, casse differente -> meme pseudonyme",
         posthog_id("  ANA@Exemple.CH "), ID_ANA)
verifier("deux personnes -> deux pseudonymes",
         posthog_id("autre@exemple.ch") == ID_ANA, False)
verifier("e-mail vide -> chaine vide, jamais un hachage du vide",
         posthog_id(""), "")

# Le sel EST la source de verite : le changer scinderait toutes les personnes.
_ancien = os.environ.get("POSTHOG_ID_SALT")
os.environ["POSTHOG_ID_SALT"] = "autre-sel"
verifier("changer le sel change TOUTES les identites (invariant d'exploitation)",
         posthog_id(ANA) == ID_ANA, False)
if _ancien is None:
    os.environ.pop("POSTHOG_ID_SALT", None)
else:
    os.environ["POSTHOG_ID_SALT"] = _ancien
verifier("sel restaure -> pseudonyme d'origine retrouve", posthog_id(ANA), ID_ANA)

# === Le pseudonyme ne fuit rien =============================================
# Chercher « ana » ou « @ » dans 32 caracteres hexadecimaux serait tautologique :
# ces caracteres n'y sont pas representables. Ce qui se prouve reellement, c'est
# qu'on ne peut pas REMONTER a l'adresse : deux adresses proches doivent donner
# des pseudonymes sans rapport, et le sel doit etre indispensable au calcul.
verifier("une faute de frappe donne un pseudonyme SANS RAPPORT",
         posthog_id("ana@exemple.ch")[:8] == posthog_id("an@exemple.ch")[:8], False)
verifier("le pseudonyme ne se rejoue pas sans le sel", posthog_id(ANA) == _NU, False)
r, e = appeler({"code": "AFR-1", "email": ANA}, CODE_INDIVIDUEL)
verifier("aucune cle inattendue ne s'est glissee dans la reponse",
         sorted(r.keys()), ["analytics_id", "name", "secret_set", "success", "token"])

print("=" * 74)
echecs = 0
for ok, nom, obtenu, attendu in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom)
    if not ok:
        echecs += 1
        print("          obtenu  : %r" % (obtenu,))
        print("          attendu : %r" % (attendu,))
print("=" * 74)
print("  %d/%d" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)

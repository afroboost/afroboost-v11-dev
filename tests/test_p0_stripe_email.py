# -*- coding: utf-8 -*-
"""P0-STRIPE-EMAIL — le client paie, son acces est cree, mais l'e-mail ne part pas.

CE QUE CE FICHIER PROUVE
------------------------
Un client payait, son code AFR- etait bien cree en base, puis le webhook levait
`UnboundLocalError: primary_color` juste avant de construire l'e-mail d'acces.
Stripe rejouait, mais la garde d'idempotence V384 repondait `already_processed`
AVANT d'atteindre l'e-mail : le client ne recevait jamais son code.

Deux etats etaient confondus : « paiement traite » et « e-mail envoye ». Ils sont
desormais distincts. Ce fichier verifie les deux moities du correctif :
  - la cause racine (`primary_color` liee sur TOUS les chemins) ;
  - la voie de rattrapage (rejouer l'e-mail SANS rejouer le metier).

COMMENT CA TOURNE
-----------------
    python tests/test_p0_stripe_email.py

Aucune base, aucun reseau, aucun Stripe, aucun Resend, aucun e-mail. `api/server.py`
n'est pas importable hors ligne (fastapi, motor, stripe, resend absents) : on en
extrait donc le code par AST, comme le font deja test_v20_contacts_securite.py et
test_n1b2_rappels.py. `ast.get_source_segment` part du `def`, le decorateur
`@api_router` ne suit pas, et la route redevient une coroutine ordinaire.
"""
import ast
import asyncio
import io
import os
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(RACINE, "api", "server.py")

# Le commit sur lequel le bug a ete constate. Sert de reference pour prouver que
# le HTML de l'e-mail n'a pas bouge d'un octet malgre son deplacement.
COMMIT_AVANT = "79634eb"

source = io.open(SRC, encoding="utf-8").read()
arbre = ast.parse(source)

resultats = []


def verifier(nom, obtenu, attendu):
    resultats.append((obtenu == attendu, nom, obtenu, attendu))


def verifier_vrai(nom, condition, detail=""):
    resultats.append((bool(condition), nom, detail or bool(condition), True))


# ===========================================================================
# EXTRACTION DU VRAI CODE
# ===========================================================================
A_EXTRAIRE = (
    "_p0_html_email_acces",
    "_p0_envoyer_email_acces",
    "_p0_marquer_email_envoye",
    "_p0_rattrapage_email_acces",
    "stripe_webhook",
)
morceaux = {}
for noeud in arbre.body:
    if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name in A_EXTRAIRE:
        morceaux[noeud.name] = ast.get_source_segment(source, noeud)
    if isinstance(noeud, ast.Assign) and any(
        isinstance(c, ast.Name) and c.id == "P0_CLE_EMAIL_CLIENT" for c in noeud.targets
    ):
        morceaux["P0_CLE_EMAIL_CLIENT"] = ast.get_source_segment(source, noeud)

manquants = [n for n in A_EXTRAIRE + ("P0_CLE_EMAIL_CLIENT",) if n not in morceaux]
verifier("0. tout le code attendu est present dans api/server.py", manquants, [])
if manquants:
    print("Extraction impossible, arret : %r" % (manquants,))
    sys.exit(1)


# ===========================================================================
# DOUBLES — ils JOURNALISENT ce qu'on leur demande : le journal est la preuve.
# ===========================================================================
class FauxObjet(dict):
    """Objet Stripe : accessible en .attribut comme en ['cle']."""

    def __getattr__(self, nom):
        try:
            return self[nom]
        except KeyError:
            raise AttributeError(nom)


def _poser(doc, chemin, valeur):
    """`$set` avec cle pointee : emails_envoyes.client_acces -> imbrique."""
    morceaux_cle = chemin.split(".")
    courant = doc
    for m in morceaux_cle[:-1]:
        if not isinstance(courant.get(m), dict):
            courant[m] = {}
        courant = courant[m]
    courant[morceaux_cle[-1]] = valeur


class FausseCollection:
    def __init__(self, nom):
        self.nom = nom
        self.docs = []
        self.journal = []

    def _correspond(self, doc, filtre):
        for cle, val in filtre.items():
            if isinstance(val, dict):
                continue  # operateurs Mongo non simules
            if doc.get(cle) != val:
                return False
        return True

    async def find_one(self, filtre, projection=None):
        self.journal.append(("find_one", dict(filtre)))
        for d in self.docs:
            if self._correspond(d, filtre):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.journal.append(("insert_one", dict(doc)))
        self.docs.append(dict(doc))
        return FauxObjet({"inserted_id": "faux"})

    async def update_one(self, filtre, maj, upsert=False):
        self.journal.append(("update_one", dict(filtre)))
        cible = None
        for d in self.docs:
            if self._correspond(d, filtre):
                cible = d
                break
        if cible is None:
            if not upsert:
                return FauxObjet({"matched_count": 0})
            cible = dict((k, v) for k, v in filtre.items() if not isinstance(v, dict))
            self.docs.append(cible)
        for cle, val in (maj.get("$set") or {}).items():
            _poser(cible, cle, val)
        for cle, val in (maj.get("$setOnInsert") or {}).items():
            cible.setdefault(cle, val)
        for cle, val in (maj.get("$inc") or {}).items():
            cible[cle] = cible.get(cle, 0) + val
        for cle, val in (maj.get("$push") or {}).items():
            cible.setdefault(cle, []).append(val)
        return FauxObjet({"matched_count": 1})

    def compter(self, operation):
        return len([e for e in self.journal if e[0] == operation])


class FausseBase:
    def __init__(self):
        self.collections = {}

    def __getattr__(self, nom):
        if nom.startswith("_") or nom == "collections":
            raise AttributeError(nom)
        return self.collections.setdefault(nom, FausseCollection(nom))


class FauxResend:
    """`resend.Emails.send(payload)` — journalise, ou echoue N fois d'affilee."""

    def __init__(self, echecs=0):
        self.envois = []
        self.echecs = echecs
        self.Emails = self

    def send(self, payload):
        if self.echecs > 0:
            self.echecs -= 1
            raise RuntimeError("Resend indisponible (simule)")
        self.envois.append(payload)
        return {"id": "faux"}


class FauxLogger:
    def __init__(self):
        self.lignes = []

    def _note(self, *a, **k):
        if a:
            self.lignes.append(str(a[0]))

    info = warning = error = debug = exception = _note


class FausseHTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        Exception.__init__(self, detail)
        self.status_code = status_code
        self.detail = detail


class _FausseSessionStripe:
    @staticmethod
    def list_line_items(sid, limit=1):
        return FauxObjet({"data": []})

    @staticmethod
    def retrieve(sid, expand=None):
        return {}


class _FauxCheckout:
    Session = _FausseSessionStripe


class FauxStripe:
    api_key = "sk_test_faux"
    checkout = _FauxCheckout

    class Event:
        @staticmethod
        def construct_from(donnees, cle):
            return donnees


class FausseRequete:
    def __init__(self, evenement):
        self.state = FauxObjet({"afroboost_event_verifie": evenement})
        self.headers = {}

    async def body(self):
        return b"{}"


class _FauxModuleShared:
    """api.routes.shared — importe A L'INTERIEUR du webhook."""

    @staticmethod
    def date_expiration_code():
        return "2026-10-14T00:00:00+00:00"

    @staticmethod
    def expiration_forfait():
        return "2026-10-14T00:00:00+00:00"

    @staticmethod
    async def cloturer_anciens_forfaits(*a, **k):
        return 0

    @staticmethod
    async def posthog_capture(*a, **k):
        return None


sys.modules.setdefault("api", type(sys)("api"))
sys.modules.setdefault("api.routes", type(sys)("api.routes"))
sys.modules["api.routes.shared"] = _FauxModuleShared


# ===========================================================================
# CABLAGE — on rejoue le vrai code dans un environnement entierement faux.
# ===========================================================================
def construire_env(resend_echecs=0, couleur="#AA00BB"):
    import datetime as _dt
    import json as _json
    import uuid as _uuid

    base = FausseBase()
    faux_resend = FauxResend(echecs=resend_echecs)
    journal = FauxLogger()

    async def _faux_primary_color(coach_email=""):
        return couleur

    def _faux_primary_rgb(couleur_hex):
        return "170, 0, 187"

    async def _faux_push(*a, **k):
        return None

    async def _faux_pref(*a, **k):
        return False

    env = {
        "__builtins__": __builtins__,
        "db": base,
        "logger": journal,
        "resend": faux_resend,
        "stripe": FauxStripe,
        "asyncio": asyncio,
        "json": _json,
        "os": os,
        "uuid": _uuid,
        "datetime": _dt.datetime,
        "timezone": _dt.timezone,
        "timedelta": _dt.timedelta,
        "HTTPException": FausseHTTPException,
        # annotation de signature, evaluee au moment du `def`
        "Request": object,
        "RESEND_AVAILABLE": True,
        "RESEND_API_KEY": "re_faux",
        "SUPER_ADMIN_EMAIL": "admin@afroboost.com",
        "DEFAULT_COACH_ID": "coach_defaut",
        "V223_MAX_SESSIONS_REGEX": 50,
        "V398_DELAI_JOURS": 3,
        "V398_SUJET": "rappel",
        "_v398_corps_rappel": lambda *a, **k: "",
        "_v259_primary_color": _faux_primary_color,
        "_v259_primary_rgb": _faux_primary_rgb,
        "send_push_by_email": _faux_push,
        "_v286_should_send_notification": _faux_pref,
    }
    for nom in ("P0_CLE_EMAIL_CLIENT",) + A_EXTRAIRE:
        exec(compile(morceaux[nom], "<%s>" % nom, "exec"), env)
    env["_base"] = base
    env["_resend"] = faux_resend
    env["_logger"] = journal
    return env


def evenement(session_id="cs_test_1", email="cliente@example.com"):
    session = FauxObjet({
        "id": session_id,
        "metadata": {"customer_email": email, "product_name": "PULSE x10"},
        "customer_details": {"email": email, "phone": "+41760000000"},
        "amount_total": 15000,
        "currency": "chf",
        "payment_status": "paid",
    })
    return FauxObjet({
        "type": "checkout.session.completed",
        "data": FauxObjet({"object": session}),
    })


def jouer(env, evt):
    """Rejoue le webhook. Retourne (reponse, exception)."""
    try:
        return asyncio.run(env["stripe_webhook"](FausseRequete(evt))), None
    except Exception as err:  # noqa: BLE001 — on veut justement l'observer
        return None, err


def envois_client(env):
    """E-mails d'acces au CLIENT seulement.

    La notification de vente au coach part par le meme Resend : la confondre
    avec l'e-mail client fausserait tous les comptes de ce fichier.
    """
    return [e for e in env["_resend"].envois
            if str(e.get("subject", "")).startswith("Bienvenue chez Afroboost")]


def envois_coach(env):
    return [e for e in env["_resend"].envois
            if not str(e.get("subject", "")).startswith("Bienvenue chez Afroboost")]


# ===========================================================================
# 1-2. PAIEMENT NORMAL, ET SES COMPTES
# ===========================================================================
env = construire_env()
reponse, err = jouer(env, evenement())
codes = env["_base"].discount_codes
abos = env["_base"].subscriptions

verifier("1. paiement normal : aucune exception", err, None)
verifier("1. paiement normal : reponse Stripe", reponse, {"received": True})
verifier("1. paiement normal : UN code d'acces cree", codes.compter("insert_one"), 1)
verifier("1. paiement normal : UNE souscription creee", abos.compter("insert_one"), 1)
verifier("1. paiement normal : UN e-mail envoye", len(envois_client(env)), 1)

_code_cree = codes.docs[0]
verifier_vrai(
    "1. l'e-mail porte bien le code cree",
    _code_cree["code"] in envois_client(env)[0]["html"],
)
verifier_vrai(
    "1. l'e-mail part a l'adresse du client",
    envois_client(env)[0]["to"] == ["cliente@example.com"],
    envois_client(env)[0]["to"],
)

# --- 9. le marqueur n'est ecrit qu'apres un succes reel
verifier(
    "9. marqueur d'envoi pose apres le succes",
    isinstance(_code_cree.get("emails_envoyes"), dict)
    and bool(_code_cree["emails_envoyes"].get("client_acces")),
    True,
)

# ===========================================================================
# 3-4-5-6-7. REJEU STRIPE APRES UN SUCCES COMPLET : rien ne doit bouger
# ===========================================================================
reponse2, err2 = jouer(env, evenement())
verifier("4. rejeu apres succes : reponse already_processed",
         (reponse2 or {}).get("status"), "already_processed")
verifier("4. rejeu apres succes : le code renvoye est celui d'origine",
         (reponse2 or {}).get("code"), _code_cree["code"])
verifier("6. rejeu apres succes : AUCUN second code", codes.compter("insert_one"), 1)
verifier("5. rejeu apres succes : AUCUNE seconde souscription", abos.compter("insert_one"), 1)
verifier("7. rejeu apres succes : AUCUN second e-mail", len(envois_client(env)), 1)

# ===========================================================================
# 2-10-12-3. L'E-MAIL ECHOUE, PUIS LE REJEU LE RATTRAPE
# ===========================================================================
env = construire_env(resend_echecs=1)      # le 1er envoi echoue, le 2e passe
reponse, err = jouer(env, evenement("cs_echec"))
codes = env["_base"].discount_codes
abos = env["_base"].subscriptions

verifier_vrai(
    "2. echec e-mail : le webhook repond en erreur pour que Stripe rejoue",
    isinstance(err, FausseHTTPException) and err.status_code == 503,
    "%s / %s" % (type(err).__name__, getattr(err, "status_code", None)),
)
verifier("2. echec e-mail : le paiement reste traite (code conserve)",
         codes.compter("insert_one"), 1)
verifier("2. echec e-mail : l'acces reste cree (souscription conservee)",
         abos.compter("insert_one"), 1)
verifier("10. echec Resend : AUCUN marqueur pose",
         codes.docs[0].get("emails_envoyes"), {})
verifier("10. echec Resend : aucun e-mail parti", len(envois_client(env)), 0)

# --- le rejeu Stripe : e-mail SEULEMENT
reponse2, err2 = jouer(env, evenement("cs_echec"))
verifier("12. rejeu apres echec reel : aucune exception", err2, None)
verifier("3. rejeu : l'e-mail est renvoye", len(envois_client(env)), 1)
verifier("3. rejeu : AUCUN nouveau code", codes.compter("insert_one"), 1)
verifier("3. rejeu : AUCUNE nouvelle souscription", abos.compter("insert_one"), 1)
verifier("3. rejeu : reponse already_processed",
         (reponse2 or {}).get("status"), "already_processed")
verifier("9. rejeu reussi : marqueur pose apres coup",
         bool((codes.docs[0].get("emails_envoyes") or {}).get("client_acces")), True)

# --- 7. un troisieme passage ne doit plus rien envoyer
jouer(env, evenement("cs_echec"))
verifier("7. troisieme passage : toujours UN SEUL e-mail", len(envois_client(env)), 1)
verifier("7. troisieme passage : toujours UN SEUL code", codes.compter("insert_one"), 1)

# ===========================================================================
# 11. RETROCOMPATIBILITE — regle bloquante
# Un document ANTERIEUR au correctif n'a pas de champ `emails_envoyes`. Son
# absence ne veut PAS dire « e-mail jamais envoye » : on ne rejoue pas.
# ===========================================================================
env = construire_env()
env["_base"].discount_codes.docs.append({
    "code": "AFR-HIST01",
    "session_id": "cs_historique",
    "assignedEmail": "ancienne@example.com",
    "maxUses": 10,
    # PAS de champ emails_envoyes : document d'avant le correctif
})
env["_base"].subscriptions.docs.append({
    "code": "AFR-HIST01", "email": "ancienne@example.com",
    "status": "active", "total_sessions": 10,
})
reponse, err = jouer(env, evenement("cs_historique"))
verifier("11. document historique : aucune exception", err, None)
verifier("11. document historique : AUCUN e-mail rejoue", len(envois_client(env)), 0)
verifier("11. document historique : AUCUNE creation",
         env["_base"].discount_codes.compter("insert_one"), 0)
verifier("11. document historique : reponse inchangee",
         (reponse or {}).get("status"), "already_processed")

# ===========================================================================
# 13. CONTROLE D'INTEGRITE — pas d'objet metier, pas d'e-mail
# ===========================================================================
env = construire_env()
env["_base"].discount_codes.docs.append({
    "code": "AFR-ORPH01",
    "session_id": "cs_orphelin",
    "assignedEmail": "orpheline@example.com",
    "maxUses": 10,
    "emails_envoyes": {},          # ne du code corrige, e-mail jamais parti
})
# ... mais AUCUNE souscription correspondante (echec survenu avant sa creation)
reponse, err = jouer(env, evenement("cs_orphelin"))
verifier("13. integrite absente : aucune exception", err, None)
verifier("13. integrite absente : AUCUN e-mail envoye", len(envois_client(env)), 0)
verifier("13. integrite absente : aucun marqueur pose",
         env["_base"].discount_codes.docs[0]["emails_envoyes"], {})

# --- integrite presente mais adresse discordante : on n'envoie pas non plus
env = construire_env()
env["_base"].discount_codes.docs.append({
    "code": "AFR-DISC01", "session_id": "cs_discord",
    "assignedEmail": "titulaire@example.com", "maxUses": 10, "emails_envoyes": {},
})
env["_base"].subscriptions.docs.append({
    "code": "AFR-DISC01", "email": "quelquun.dautre@example.com",
    "status": "active", "total_sessions": 10,
})
jouer(env, evenement("cs_discord"))
verifier("13. souscription discordante : AUCUN e-mail", len(envois_client(env)), 0)

# ===========================================================================
# 14. LE DESTINATAIRE VIENT DE LA BASE, JAMAIS DU PAYLOAD STRIPE
# ===========================================================================
env = construire_env()
env["_base"].discount_codes.docs.append({
    "code": "AFR-VOL001", "session_id": "cs_detourne",
    "assignedEmail": "titulaire@example.com", "maxUses": 10, "emails_envoyes": {},
})
env["_base"].subscriptions.docs.append({
    "code": "AFR-VOL001", "email": "titulaire@example.com",
    "status": "active", "total_sessions": 10,
})
# L'evenement pretend que le client est quelqu'un d'autre.
jouer(env, evenement("cs_detourne", email="pirate@example.com"))
verifier("14. rattrapage : UN e-mail envoye", len(envois_client(env)), 1)
verifier("14. rattrapage : destinataire relu en BASE, pas dans le payload",
         envois_client(env)[0]["to"], ["titulaire@example.com"])
verifier_vrai(
    "14. rattrapage : l'adresse du payload n'apparait nulle part",
    "pirate@example.com" not in str(envois_client(env)[0]),
)

# ===========================================================================
# 8. PRIMARY_COLOR — cause racine, et anti-recidive
# ===========================================================================
# 8a. comportement : la fonction de rendu ne leve pas et pose bien la couleur
_html = construire_env()["_p0_html_email_acces"]("AFR-TEST01", 10, "#AA00BB")
verifier_vrai("8. rendu HTML : la couleur est bien interpolee", "#AA00BB" in _html)
verifier_vrai("8. rendu HTML : le code est bien present", "AFR-TEST01" in _html)
verifier_vrai("8. rendu HTML : aucun accolade non resolue",
              "{primary_color}" not in _html and "{new_code}" not in _html)


# 8b. anti-recidive : AUCUNE locale lue avant d'etre liee, sur tout server.py.
# Detecte la classe de bug entiere, pas seulement primary_color. Le socle connu
# est FIGE : toute nouvelle occurrence fait echouer ce test.
# Le detecteur ci-dessous repond a une question precise : « existe-t-il une
# lecture de variable locale qu'AUCUNE liaison ne couvre sur TOUS les chemins
# d'execution ? ». C'est exactement la classe du bug P0 : `primary_color` etait
# bien assignee dans la fonction, mais seulement dans une branche sur trois.
#
# Deux regles font toute la precision :
#   - un `if` ne lie surement que si son `else` existe ET lie aussi ;
#   - un bloc qui se termine par raise/return/continue/break n'a rien a lier,
#     puisque l'execution n'atteindra jamais la suite.
# Sans elles, on croule sous les faux positifs (1167 au lieu de 4).
PORTEES_IMBRIQUEES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
                      ast.GeneratorExp, ast.FunctionDef, ast.AsyncFunctionDef)


def _cibles(noeud):
    if isinstance(noeud, ast.Name):
        return {noeud.id}
    return {e.id for e in ast.walk(noeud)
            if isinstance(e, ast.Name) and isinstance(e.ctx, ast.Store)}


def _walrus(noeud, nom):
    return any(isinstance(e, ast.NamedExpr) and isinstance(e.target, ast.Name)
               and e.target.id == nom for e in ast.walk(noeud))


def _termine(instructions):
    """Ce bloc ne retombe-t-il jamais dans la suite ?"""
    if not instructions:
        return False
    dernier = instructions[-1]
    if isinstance(dernier, (ast.Raise, ast.Return, ast.Continue, ast.Break)):
        return True
    if isinstance(dernier, ast.If):
        return bool(dernier.orelse) and _termine(dernier.body) and _termine(dernier.orelse)
    return False


def _bloc_lie(instructions, nom):
    if _termine(instructions):
        return True
    return any(_instruction_lie(st, nom) for st in instructions)


def _instruction_lie(st, nom):
    """Toute execution de cette instruction lie-t-elle `nom` a coup sur ?"""
    if isinstance(st, ast.Assign):
        return any(nom in _cibles(t) for t in st.targets) or _walrus(st, nom)
    if isinstance(st, (ast.AugAssign, ast.AnnAssign)):
        return nom in _cibles(st.target)
    if isinstance(st, (ast.Import, ast.ImportFrom)):
        return any((a.asname or a.name).split(".")[0] == nom for a in st.names)
    if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return st.name == nom
    if isinstance(st, ast.If):
        return bool(st.orelse) and _bloc_lie(st.body, nom) and _bloc_lie(st.orelse, nom)
    if isinstance(st, ast.Try):
        if _bloc_lie(st.finalbody, nom):
            return True
        return (_bloc_lie(st.body, nom) and bool(st.handlers)
                and all(_bloc_lie(h.body, nom) for h in st.handlers))
    if isinstance(st, (ast.With, ast.AsyncWith)):
        for item in st.items:
            if item.optional_vars is not None and nom in _cibles(item.optional_vars):
                return True
        return _bloc_lie(st.body, nom)
    if isinstance(st, ast.Expr):
        return _walrus(st, nom)
    return False          # For / While : la boucle peut ne jamais tourner


def _chemins(fonction):
    chemin = {id(fonction): ()}
    pile = [fonction]
    while pile:
        parent = pile.pop()
        base = chemin[id(parent)]
        for champ, valeur in ast.iter_fields(parent):
            elements = valeur if isinstance(valeur, list) else [valeur]
            for i, enfant in enumerate(elements):
                if not isinstance(enfant, ast.AST):
                    continue
                chemin[id(enfant)] = base + ((id(parent), champ, i),)
                if enfant is not fonction and isinstance(enfant, PORTEES_IMBRIQUEES):
                    continue
                pile.append(enfant)
    return chemin


def _couverte(chemin_lecture, nom, noeuds):
    for k in range(len(chemin_lecture) - 1, -1, -1):
        pid, champ, idx = chemin_lecture[k]
        parent = noeuds[pid]
        if isinstance(parent, (ast.For, ast.AsyncFor)) and champ in ("body", "orelse"):
            if nom in _cibles(parent.target):
                return True
        if isinstance(parent, (ast.If, ast.While)) and champ in ("body", "orelse"):
            if _walrus(parent.test, nom):
                return True
        if isinstance(parent, (ast.With, ast.AsyncWith)) and champ == "body":
            for item in parent.items:
                if item.optional_vars is not None and nom in _cibles(item.optional_vars):
                    return True
        if isinstance(parent, ast.ExceptHandler) and champ == "body" and parent.name == nom:
            return True
        valeur = getattr(parent, champ, None)
        if isinstance(valeur, list) and idx < len(valeur) and isinstance(valeur[0], ast.stmt):
            if _bloc_lie(valeur[:idx], nom):
                return True
    return False


def _locales_de(fonction, chemin):
    """Noms reellement locaux : lies quelque part dans le corps, hors portees
    imbriquees, hors parametres, hors `global`/`nonlocal`.

    Calcule directement sur l'AST : `symtable` exigerait de re-extraire le texte
    de chaque fonction, ce qui relit les 26 000 lignes du fichier a chaque appel.
    """
    parametres = set()
    args = fonction.args
    for groupe in (args.posonlyargs, args.args, args.kwonlyargs):
        for a in groupe or []:
            parametres.add(a.arg)
    for a in (args.vararg, args.kwarg):
        if a is not None:
            parametres.add(a.arg)

    declares_ailleurs = set()
    lies = set()
    for n in ast.walk(fonction):
        if id(n) not in chemin or n is fonction:
            continue
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            declares_ailleurs.update(n.names)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            lies.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            lies.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                lies.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lies.add(n.name)
    return lies - parametres - declares_ailleurs


def locales_lues_avant_liaison(source_py, seulement=None):
    """{(fonction, variable, ligne)} des lectures non couvertes."""
    racine = ast.parse(source_py)
    trouves = set()
    for fonction in [n for n in ast.walk(racine)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        if seulement and fonction.name != seulement:
            continue
        chemin = _chemins(fonction)
        locales = _locales_de(fonction, chemin)
        if not locales:
            continue
        noeuds = {id(n): n for n in ast.walk(fonction)}
        for n in ast.walk(fonction):
            if id(n) not in chemin:
                continue
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in locales:
                if not _couverte(chemin[id(n)], n.id, noeuds):
                    trouves.add((fonction.name, n.id, n.lineno))
    return trouves


try:
    _source_avant = subprocess.check_output(
        ["git", "show", "%s:api/server.py" % COMMIT_AVANT],
        cwd=RACINE, stderr=subprocess.STDOUT).decode("utf-8")
except subprocess.CalledProcessError as _e:
    _source_avant = None

_apres_webhook = sorted(locales_lues_avant_liaison(source, "stripe_webhook"))
verifier("8. anti-recidive : AUCUNE locale non liee dans stripe_webhook",
         [(v, l) for (_f, v, l) in _apres_webhook], [])

if _source_avant is None:
    verifier_vrai("8. le detecteur est confronte au code d'avant correctif",
                  False, "git indisponible")
else:
    # Preuve que le detecteur DETECTE vraiment : confronte au code d'avant, il
    # doit retrouver les 5 lectures fautives — sinon un detecteur muet passerait
    # ce fichier avec les honneurs.
    _avant_webhook = {(v, l) for (_f, v, l) in
                      locales_lues_avant_liaison(_source_avant, "stripe_webhook")}
    verifier("8. le detecteur retrouve bien le bug d'origine",
             sorted(_avant_webhook),
             [("primary_color", 5945), ("primary_color", 5989),
              ("primary_color", 6007), ("primary_color", 6504),
              ("primary_rgb", 5990)])
    # Et rien n'a ete introduit ailleurs dans le fichier : le socle de dette
    # anterieure doit etre strictement identique avant et apres.
    _socle_avant = {(f, v) for (f, v, _l) in locales_lues_avant_liaison(_source_avant)}
    _socle_apres = {(f, v) for (f, v, _l) in locales_lues_avant_liaison(source)}
    verifier("8. le correctif ne retire QUE les lectures fautives du webhook",
             sorted(_socle_avant - _socle_apres),
             [("stripe_webhook", "primary_color"), ("stripe_webhook", "primary_rgb")])
    verifier("8. le correctif n'introduit AUCUNE nouvelle locale non liee",
             sorted(_socle_apres - _socle_avant), [])

# 8c. la liaison est bien AVANT l'aiguillage par type de paiement
_fn_webhook = [n for n in ast.walk(arbre)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == "stripe_webhook"][0]
_lignes_assign_pc = sorted(
    n.lineno for n in ast.walk(_fn_webhook)
    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == "primary_color"
)
_lignes_lecture_pc = sorted(
    n.lineno for n in ast.walk(_fn_webhook)
    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id == "primary_color"
)
verifier_vrai(
    "8. la premiere liaison de primary_color precede TOUTE lecture",
    _lignes_assign_pc and _lignes_lecture_pc
    and _lignes_assign_pc[0] < _lignes_lecture_pc[0],
    "liaisons=%s lectures=%s" % (_lignes_assign_pc[:3], _lignes_lecture_pc[:3]),
)
# 15. la branche coach_registration lisait elle aussi primary_color/primary_rgb
# sans liaison (e-mails perdus EN SILENCE, avales par leurs except). La liaison
# hissee les couvre : plus aucune lecture non liee (verifie en 8 ci-dessus).
verifier_vrai(
    "15. coach_registration : ses lectures de primary_rgb sont couvertes",
    "primary_rgb" not in [v for (_f, v, _l) in _apres_webhook],
)

# ===========================================================================
# H. NON-REGRESSION OCTET POUR OCTET DU HTML DEPLACE
# Le gabarit a change de place. Il ne doit pas avoir change d'un caractere.
# ===========================================================================
def _html_origine():
    """Rejoue le bloc en ligne tel qu'il etait avant le correctif."""
    brut = subprocess.check_output(
        ["git", "show", "%s:api/server.py" % COMMIT_AVANT],
        cwd=RACINE, stderr=subprocess.STDOUT,
    ).decode("utf-8")
    lignes = brut.split("\n")
    # 6489..6503 : du code, indente a 20 ; 6504..6590 : contenu de chaine, verbatim.
    tete = [l[20:] if l.startswith(" " * 20) else l for l in lignes[6489 - 1:6503]]
    corps = lignes[6504 - 1:6590]
    bloc = "\n".join(tete + corps)
    espace = {"new_code": "AFR-TEST01", "sessions_count": 10, "primary_color": "#AA00BB"}
    exec(compile(bloc, "<origine>", "exec"), espace)
    return espace["html"]


try:
    _avant = _html_origine()
    _apres = construire_env()["_p0_html_email_acces"]("AFR-TEST01", 10, "#AA00BB")
    verifier("H. le HTML de l'e-mail est identique octet pour octet", _apres, _avant)
except subprocess.CalledProcessError as _git_err:
    verifier_vrai("H. le HTML de l'e-mail est identique octet pour octet",
                  False, "git indisponible : %s" % _git_err)

# ===========================================================================
# I. NON-REGRESSION STRUCTURELLE — l'ordre du webhook n'a pas bouge
# ===========================================================================
_l_garde = source.index('_deja = await db.discount_codes.find_one')
_l_insert = source.index('await db.discount_codes.insert_one(discount_doc)')
_l_envoi = source.index('await _p0_envoyer_email_acces(customer_email')
verifier_vrai("I. ordre preserve : garde V384 -> creation du code -> e-mail",
              _l_garde < _l_insert < _l_envoi)
verifier_vrai("I. la garde V384 est toujours la, et sort toujours en already_processed",
              '"status": "already_processed"' in source)
# Aucun masquage d'erreur dans le code ajoute : le correctif ne doit pas
# « reparer » en avalant l'exception. On verifie le code P0 lui-meme, pas le
# reste du fichier (dette anterieure hors perimetre).
_handlers_p0 = []
for _nom in [n for n in A_EXTRAIRE if n.startswith("_p0")]:
    for _n in ast.walk(ast.parse(morceaux[_nom])):
        if isinstance(_n, ast.ExceptHandler):
            _handlers_p0.append((_nom, _n.lineno))
verifier("I. aucun try/except dans le code ajoute (zero masquage d'erreur)",
         _handlers_p0, [])


# ===========================================================================
# RAPPORT
# ===========================================================================
print("=" * 74)
print("  P0-STRIPE-EMAIL — paiement traite / e-mail envoye sont deux etats")
print("=" * 74)
echecs = 0
for ok, nom, obtenu, attendu in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom)
    if not ok:
        echecs += 1
        print("          obtenu  : %r" % (obtenu,))
        print("          attendu : %r" % (attendu,))
print("-" * 74)
print("  %d/%d" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)

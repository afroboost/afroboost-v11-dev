# -*- coding: utf-8 -*-
"""ESSAI-7 — `POST /checkout/free` rend le code AFR- QU'IL VIENT DE CREER.

POURQUOI CE CHANGEMENT N'EST PAS UN RETOUR EN ARRIERE SUR ESSAI-1A.

ESSAI-1A avait retire `access_code` de cette reponse, pour une raison juste :
la route n'a AUCUNE authentification, l'adresse est celle que le visiteur ecrit
lui-meme, et rendre le code d'un TIERS reviendrait a le remettre a quiconque
saisit son adresse. La meme prudence a fait retirer le code du refus ESSAI-4
(« vous avez deja un abonnement actif »), ou il s'agirait bel et bien du code
PRE-EXISTANT de quelqu'un d'autre.

La difference tient en une phrase, et c'est elle que cette suite prouve :
`_process_successful_payment` FABRIQUE un code neuf a chaque appel (`AFR-` plus
six caracteres tires au hasard). Le code rendu ici n'a donc JAMAIS appartenu a
personne avant cette requete. Et les deux chemins qui pourraient exposer le
code d'un tiers — essai deja consomme (ESSAI-1) et abonnement actif (ESSAI-4) —
LEVENT AVANT toute creation : ils ne rendent rien du tout.

Sans le code dans la reponse, la fin du tunnel etait un cul-de-sac : le code
n'existait pour le visiteur que dans un e-mail, donc dans une boite de
reception, un dossier « promotions », un delai. Mesure du 25/08/2026 : le code
etait accorde, la seance ne l'etait pas.

CE QUE FAIT CE BANC. Le VRAI `free_checkout` est extrait par AST du fichier de
production et execute avec des mouchards a la place de ses collaborateurs. Un
mouchard qui n'est JAMAIS appele est ici la preuve recherchee : un refus doit
s'arreter avant le moteur de creation.

Aucun reseau. Aucune base. Aucun e-mail. Aucun essai reel.

Lancement :  python3 tests/test_essai7_code_retour.py
"""

import ast
import asyncio
import io
import os
import re
import sys
import uuid as _uuid
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FICHIER = os.path.join(RACINE, "api", "routes", "checkout_routes.py")
SOURCE = io.open(FICHIER, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

# La forme EXACTE produite par `_process_successful_payment`, et la seule que le
# frontend accepte (`MOTIF_CODE_AFR`, frontend/src/utils/essaiReservation.js).
MOTIF_AFR = re.compile(r"^AFR-[A-Z0-9]{6}$")

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def extraire(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("introuvable : %s" % nom)


SRC_FREE = extraire("free_checkout")
SRC_VIERGE = extraire("_essai7_espace_vierge")
SRC_DEBIT = extraire("_essai7_debit_ok")
SRC_EXIGER = extraire("_essai7_exiger_debit")

# Les reglages du debit sont des variables de MODULE. On les relit dans le
# fichier de production plutot que de les recopier ici : un seuil change en
# production doit changer ce que ce banc mesure, sinon le banc ment.
SRC_REGLAGES = "\n".join(
    l for l in SOURCE.splitlines() if l.startswith("_ESSAI7_DEBIT"))
assert "_ESSAI7_DEBIT_MAX" in SRC_REGLAGES, "reglages de debit introuvables"
_SEUIL_DEBIT = int(re.search(r"_ESSAI7_DEBIT_MAX\s*=\s*(\d+)", SRC_REGLAGES).group(1))


# --------------------------------------------------------------- le decor ---
class _HTTP(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}
        Exception.__init__(self, "%s %s" % (status_code, detail))


class _Item(object):
    def __init__(self, id="off-essai", name="Essai", price=0.0, quantity=1,
                 type="offer"):
        self.id, self.name, self.price = id, name, price
        self.quantity, self.type = quantity, type

    def dict(self):
        return {"id": self.id, "name": self.name, "price": self.price,
                "quantity": self.quantity, "type": self.type}


class _Req(object):
    def __init__(self, email="ana@exemple.ch", nom="Ana", coach="coach@x.ch",
                 phone="", items=None, discount_code=None, terms_accepted=None):
        self.customer_email = email
        self.customer_name = nom
        self.customer_phone = phone
        self.coach_email = coach
        self.items = items if items is not None else [_Item()]
        self.discount_code = discount_code
        self.terms_accepted = terms_accepted


def _correspond(doc, requete):
    """Egalite simple, `$regex`/`$options` et `$or` — le strict necessaire."""
    for cle, attendu in (requete or {}).items():
        if cle == "$or":
            if not any(_correspond(doc, sous) for sous in attendu):
                return False
            continue
        obtenu = doc.get(cle)
        if isinstance(attendu, dict) and "$regex" in attendu:
            drapeaux = re.I if "i" in str(attendu.get("$options") or "") else 0
            if obtenu is None or not re.match(attendu["$regex"], str(obtenu), drapeaux):
                return False
        elif obtenu != attendu:
            return False
    return True


class _Coll(object):
    def __init__(self):
        self.docs = []
        self.panne_lecture = False

    async def find_one(self, q, p=None):
        await asyncio.sleep(0)
        if self.panne_lecture:
            raise RuntimeError("base injoignable")
        for d in self.docs:
            if _correspond(d, q):
                return dict(d)
        return None

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        self.docs.append(dict(doc))

    async def update_one(self, q, m, **k):
        await asyncio.sleep(0)
        self.docs.append({"_update": dict(q)})


class _Base(object):
    def __init__(self):
        self._c = {}

    def __getitem__(self, nom):
        return self._c.setdefault(nom, _Coll())


class _Requete(object):
    """Ce que FastAPI passe a la route : on n'a besoin que des en-tetes."""
    def __init__(self, ip="203.0.113.7"):
        self.headers = {"CF-Connecting-IP": ip}
        self.client = type("c", (), {"host": ip})()


class Journal(object):
    """Qui a ete appele, dans quel ordre, avec quoi."""

    def __init__(self):
        self.appels = []
        self.codes_crees = []

    def trace(self, nom, **kw):
        self.appels.append((nom, kw))

    def noms(self):
        return [n for n, _ in self.appels]


def bac(refus_garde=None, echec_moteur=False, octrois_autorises=None):
    """Monte le VRAI `free_checkout` sur des mouchards.

    `refus_garde` : nom de la garde qui doit lever (409), ou None.
    `octrois_autorises` : quota d'octrois pour `_essai1_garde` — a 1, la
    deuxieme demande simultanee est refusee, exactement comme le verrou atomique
    de production.
    """
    j = Journal()
    base = _Base()
    quota = {"reste": octrois_autorises if octrois_autorises is not None else 10**6}

    def garde(nom, statut=409, detail="Refusé.", entete=None):
        async def _g(*a, **k):
            await asyncio.sleep(0)
            j.trace(nom, args=a, kw=k)
            if refus_garde == nom:
                raise _HTTP(status_code=statut, detail=detail,
                            headers=entete or {})
        return _g

    async def _t1(accepte, items, coach_email=""):
        await asyncio.sleep(0)
        j.trace("_t1_preuve_checkout")
        return {}

    _essai1 = garde("_essai1_garde", detail="Votre essai gratuit a déjà été utilisé.",
                    entete={"X-Refus-Raison": "free_trial_already_used"})

    async def _essai1_garde(*a, **k):
        # Le verrou atomique de production, modelise par un quota : celui qui
        # arrive en second se fait refuser, meme a la milliseconde pres.
        await _essai1(*a, **k)
        await asyncio.sleep(0)
        if quota["reste"] <= 0:
            raise _HTTP(status_code=409, detail="Vous détenez déjà un essai.",
                        headers={"X-Refus-Raison": "free_trial_already_granted"})
        quota["reste"] -= 1

    async def _moteur(**kw):
        await asyncio.sleep(0)
        j.trace("_process_successful_payment", kw=kw)
        if echec_moteur:
            raise RuntimeError("panne simulee pendant la creation")
        # Ce que fait le vrai moteur : un code NEUF, tire au hasard, jamais vu
        # avant cette requete.
        import random
        import string
        code = "AFR-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        j.codes_crees.append(code)
        return {"access_code": code, "sessions_count": 1, "product_name": "Essai"}

    async def _liberer(email, telephone="", coach_id=None):
        await asyncio.sleep(0)
        j.trace("_essai1_liberer", email=email, telephone=telephone)

    async def _push(*a, **k):
        await asyncio.sleep(0)
        j.trace("push")

    async def _octroi(*a, **k):
        await asyncio.sleep(0)
        j.trace("essai2_tracer_octroi")

    sys.modules.setdefault("api", type("p", (), {})())
    sys.modules.setdefault("api.routes", type("p", (), {})())
    sys.modules["api.routes.shared"] = type(
        "m", (), {"essai2_tracer_octroi": staticmethod(_octroi)})
    sys.modules["api.server"] = type(
        "m", (), {"send_push_by_email": staticmethod(_push)})

    g = {
        "db": base,
        "asyncio": asyncio,
        "datetime": datetime, "timezone": timezone, "uuid": _uuid,
        "HTTPException": _HTTP,
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
        "router": type("r", (), {"post": staticmethod(lambda *a, **k: (lambda f: f))}),
        "FreeCheckoutRequest": object,
        "_t1_preuve_checkout": _t1,
        "_lot2_verifier_vendeur": garde("_lot2_verifier_vendeur", 403,
                                        "Cette offre n'appartient pas au vendeur indiqué."),
        "_essai1b_exiger_gratuit": garde("_essai1b_exiger_gratuit", 400,
                                         "Cette offre n'est pas gratuite."),
        "_essai4_garde": garde("_essai4_garde", 409,
                               "Vous avez déjà un abonnement Afroboost actif."),
        "_lotr_garde": garde("_lotr_garde", 403, "Offre réservée aux membres."),
        "_essai1_garde": _essai1_garde,
        "_process_successful_payment": _moteur,
        "_essai1_liberer": _liberer,
    }
    g["Request"] = _Requete
    exec(compile("\n\n".join([SRC_REGLAGES, SRC_VIERGE, SRC_DEBIT,
                               SRC_EXIGER, SRC_FREE]), "<essai7>", "exec"), g)
    # Le compteur de debit vit dans le module : on le remet a zero a chaque bac,
    # sinon les scenarios se pollueraient l'un l'autre.
    g["_ESSAI7_DEBIT"].clear()
    return g["free_checkout"], j, base


# ============================================================================
#                        A. CE QUE LA REPONSE CONTIENT
# ============================================================================
async def reponse():
    # --- A. un nouvel essai -------------------------------------------------
    libre, j, _ = bac()
    r = await libre(_Req(), _Requete())

    verifier("A1. un nouvel essai renvoie un access_code",
             bool(r.get("access_code")), repr(r))
    verifier("A2. le code renvoye a la forme AFR-XXXXXX",
             MOTIF_AFR.match(str(r.get("access_code") or "")),
             repr(r.get("access_code")))
    verifier("A3. le code renvoye est EXACTEMENT celui cree par le moteur",
             r.get("access_code") == (j.codes_crees[0] if j.codes_crees else None),
             "%r / %r" % (r.get("access_code"), j.codes_crees))
    verifier("A4. un seul code a ete cree", len(j.codes_crees) == 1,
             str(j.codes_crees))

    # --- A5. la reponse reste ADDITIVE : rien n'a disparu -------------------
    verifier("A5. success conserve", r.get("success") is True, repr(r))
    verifier("A5. free conserve", r.get("free") is True, repr(r))
    verifier("A5. transaction_id conserve",
             str(r.get("transaction_id") or "").startswith("free_"), repr(r))
    verifier("A5. message conserve", bool(r.get("message")), repr(r))

    # --- A6. le moteur est appele avec les MEMES arguments qu'avant ---------
    appel = [kw for n, kw in j.appels if n == "_process_successful_payment"]
    attendus = {"terms_fields", "transaction_id", "coach_email", "customer_name",
                "customer_email", "customer_phone", "items", "total", "currency",
                "payment_method", "discount_code"}
    verifier("A6. le moteur recoit exactement les memes arguments",
             appel and set(appel[0]["kw"]) == attendus,
             str(sorted(appel[0]["kw"])) if appel else "jamais appele")
    verifier("A6b. l'appel reste a 0 CHF, methode `free`",
             appel and appel[0]["kw"]["total"] == 0
             and appel[0]["kw"]["payment_method"] == "free")

    # --- A7. le client ne dicte RIEN ---------------------------------------
    libre, j, _ = bac()
    faux = _Req(email="bea@exemple.ch")
    faux.access_code = "AFR-PIRAT"      # pose de force sur la requete
    r = await libre(faux, _Requete())
    verifier("A7. un access_code fourni par le client est ignore",
             r.get("access_code") != "AFR-PIRAT", repr(r.get("access_code")))
    verifier("A7b. le code rendu reste celui du moteur",
             r.get("access_code") == j.codes_crees[0], repr(r.get("access_code")))

    # --- A8. rejeu : deux essais successifs, un seul octroi ----------------
    libre, j, _ = bac(octrois_autorises=1)
    r1 = await libre(_Req(email="cle@exemple.ch"), _Requete())
    leve = None
    try:
        await libre(_Req(email="cle@exemple.ch"), _Requete())
    except _HTTP as e:
        leve = e
    verifier("A8. rejeu : le premier octroi rend un code",
             MOTIF_AFR.match(str(r1.get("access_code") or "")))
    verifier("A8b. rejeu : le second est refuse (409)",
             leve is not None and leve.status_code == 409, repr(leve))
    verifier("A8c. rejeu : aucun second code n'est cree",
             len(j.codes_crees) == 1, str(j.codes_crees))


# ============================================================================
#                    B. LES REFUS NE RENDENT AUCUN CODE
# ============================================================================
async def refus():
    for nom, statut in (("_essai1_garde", 409),      # essai deja pris
                        ("_essai4_garde", 409),      # abonnement actif
                        ("_lotr_garde", 403),        # offre reservee aux membres
                        ("_lot2_verifier_vendeur", 403),
                        ("_essai1b_exiger_gratuit", 400)):
        libre, j, base = bac(refus_garde=nom)
        leve = None
        try:
            r = await libre(_Req(), _Requete())
            verifier("B. %s : la garde refuse" % nom, False, "reponse rendue : %r" % r)
            continue
        except _HTTP as e:
            leve = e
        verifier("B. %s : refus %d" % (nom, statut), leve.status_code == statut,
                 str(leve.status_code))
        verifier("B. %s : le refus ne porte AUCUN code AFR-" % nom,
                 "AFR-" not in str(leve.detail), str(leve.detail))
        verifier("B. %s : aucun code n'est cree" % nom,
                 len(j.codes_crees) == 0, str(j.codes_crees))
        verifier("B. %s : le moteur n'est jamais appele" % nom,
                 "_process_successful_payment" not in j.noms(), str(j.noms()))

    # --- B6. panne du moteur : l'essai est rendu, rien n'est fabrique ------
    libre, j, _ = bac(echec_moteur=True)
    leve = None
    try:
        await libre(_Req(), _Requete())
    except Exception as e:            # noqa: BLE001 — on veut TOUTE exception
        leve = e
    verifier("B6. une panne du moteur remonte a l'appelant",
             isinstance(leve, RuntimeError), repr(leve))
    verifier("B6b. l'essai est libere pour une nouvelle tentative",
             "_essai1_liberer" in j.noms(), str(j.noms()))
    verifier("B6c. aucun code n'est rendu apres une panne",
             len(j.codes_crees) == 0, str(j.codes_crees))

    # --- B7. concurrence : deux requetes nees a la meme milliseconde -------
    libre, j, _ = bac(octrois_autorises=1)
    sorties = await asyncio.gather(libre(_Req(email="eve@exemple.ch"), _Requete()),
                                   libre(_Req(email="eve@exemple.ch"), _Requete()),
                                   return_exceptions=True)
    rendus = [s for s in sorties if isinstance(s, dict)]
    refuses = [s for s in sorties if isinstance(s, _HTTP)]
    verifier("B7. concurrence : un seul octroi", len(rendus) == 1, repr(sorties))
    verifier("B7b. concurrence : l'autre est refusee (409)",
             len(refuses) == 1 and refuses[0].status_code == 409, repr(sorties))
    verifier("B7c. concurrence : un seul code cree et rendu",
             len(j.codes_crees) == 1
             and rendus and rendus[0].get("access_code") == j.codes_crees[0],
             "%r / %r" % (j.codes_crees, rendus))


# ============================================================================
#      D. LE DELTA DE SECURITE OUVERT PAR LE RETOUR DU CODE, ET SA FERMETURE
# ============================================================================
#
# CE QUE LE RETOUR DU CODE AJOUTE. Avant ce lot, un appelant anonyme pouvait
# deja BRULER l'essai d'un tiers en saisissant son adresse (trou pre-existant,
# non ouvert par ce lot). Il ne pouvait PAS, en revanche, apprendre le code
# ainsi cree. Or `GET /subscriber/space/{code}` resout les reservations PAR
# ADRESSE E-MAIL, pas par code : ouvrir `/espace/<CODE>` avec un code neuf
# frappe sur une adresse DEJA CONNUE afficherait tout l'historique de cette
# personne — noms de cours, dates, invites, presences.
#
# LA REGLE RETENUE, et elle ramene ce delta a zero : le code ne repart QUE si
# l'espace qu'il ouvre ne peut rien contenir d'autre que ce que CETTE requete
# vient de fournir. Autrement dit : aucune reservation, aucun forfait, aucun
# code d'acces anterieur sur cette adresse. Sinon, la reponse redevient
# exactement celle d'avant le lot — l'e-mail reste le seul canal.
#
# Un simple CONTACT (`chat_participants`) ne compte pas : l'espace n'en montre
# rien, et le tunnel Chat en cree un AVANT le checkout. L'y inclure aurait
# casse Option B pour l'entree principale du funnel.


async def securite():
    # --- D1. adresse inconnue : le parcours legitime, intact ---------------
    libre, j, base = bac()
    r = await libre(_Req(email="neuve@exemple.ch"), _Requete())
    verifier("D1. une adresse sans passe recoit son code",
             MOTIF_AFR.match(str(r.get("access_code") or "")), repr(r))

    # --- D2 a D4. une trace anterieure ferme le retour du code -------------
    for nom, collection, doc in (
        ("une reservation passee", "reservations",
         {"userEmail": "Vue@Exemple.ch", "courseName": "Pulse", "datetime": "2026-01-01"}),
        ("un forfait passe", "subscriptions",
         {"email": "vue@exemple.ch", "code": "AFR-ANCIEN", "remaining_sessions": 0}),
        ("un code d'acces passe", "discount_codes",
         {"assignedEmail": "vue@exemple.ch", "code": "AFR-ANCIEN"}),
        ("une adhesion LOT R", "memberships",
         {"email": "vue@exemple.ch", "coach_id": None}),
    ):
        libre, j, base = bac()
        base[collection].docs.append(doc)
        r = await libre(_Req(email="vue@exemple.ch"), _Requete())
        verifier("D2. %s : AUCUN code dans la reponse" % nom,
                 not r.get("access_code"), repr(r.get("access_code")))
        verifier("D2. %s : le reste de la reponse est inchange" % nom,
                 r.get("success") is True and r.get("free") is True
                 and str(r.get("transaction_id") or "").startswith("free_"),
                 repr(r))
        verifier("D2. %s : l'essai est bien accorde malgre tout" % nom,
                 len(j.codes_crees) == 1, str(j.codes_crees))

    # La casse de l'adresse ne doit pas servir de contournement.
    libre, j, base = bac()
    base["reservations"].docs.append({"userEmail": "vue@exemple.ch"})
    r = await libre(_Req(email="VUE@Exemple.CH"), _Requete())
    verifier("D3. la casse de l'adresse ne contourne pas la regle",
             not r.get("access_code"), repr(r.get("access_code")))

    # --- D5. un simple contact CRM ne ferme rien ---------------------------
    libre, j, base = bac()
    base["chat_participants"].docs.append({"email": "tunnel@exemple.ch",
                                           "name": "Ana"})
    r = await libre(_Req(email="tunnel@exemple.ch"), _Requete())
    verifier("D5. le tunnel Chat (contact deja cree) garde Option B",
             MOTIF_AFR.match(str(r.get("access_code") or "")), repr(r))

    # --- D6. panne de lecture : on ne rend RIEN (fail-closed) --------------
    libre, j, base = bac()
    base["reservations"].panne_lecture = True
    r = await libre(_Req(email="panne@exemple.ch"), _Requete())
    verifier("D6. base muette : aucun code, jamais de doute favorable",
             not r.get("access_code"), repr(r.get("access_code")))
    verifier("D6b. base muette : l'essai est quand meme accorde",
             r.get("success") is True and len(j.codes_crees) == 1, repr(r))

    # --- D7. debit : un appel fabrique en serie est coupe ------------------
    libre, j, base = bac()
    faits, refuses = 0, 0
    for i in range(_SEUIL_DEBIT + 3):
        try:
            await libre(_Req(email="tir%d@exemple.ch" % i), _Requete(ip="198.51.100.9"))
            faits += 1
        except _HTTP as e:
            if e.status_code == 429:
                refuses += 1
    verifier("D7. le debit par IP finit par couper", refuses >= 3,
             "faits=%d refuses=%d" % (faits, refuses))
    verifier("D7b. il ne coupe pas avant le seuil", faits == _SEUIL_DEBIT,
             "faits=%d" % faits)
    verifier("D7c. un refus de debit ne cree AUCUN essai",
             len(j.codes_crees) == faits, str(len(j.codes_crees)))

    # Le refus de debit intervient AVANT la garde anti-2e-essai : il ne doit
    # pas consommer le droit de quelqu'un qui n'a rien obtenu.
    libre, j, base = bac()
    for i in range(_SEUIL_DEBIT):
        await libre(_Req(email="plein%d@exemple.ch" % i), _Requete(ip="198.51.100.10"))
    avant = list(j.noms())
    try:
        await libre(_Req(email="tardif@exemple.ch"), _Requete(ip="198.51.100.10"))
        verifier("D8. au-dela du seuil, la route refuse", False, "aucun refus")
    except _HTTP as e:
        verifier("D8. au-dela du seuil, la route refuse (429)",
                 e.status_code == 429, str(e.status_code))
        verifier("D8b. le refus ne porte AUCUN code AFR-",
                 "AFR-" not in str(e.detail), str(e.detail))
    verifier("D8c. le refus de debit ne consomme pas l'essai",
             j.noms() == avant, str(j.noms()[len(avant):]))

    # Une AUTRE adresse IP n'est pas penalisee.
    libre2, j2, _ = bac()
    for i in range(_SEUIL_DEBIT):
        await libre2(_Req(email="a%d@exemple.ch" % i), _Requete(ip="198.51.100.11"))
    r = await libre2(_Req(email="ailleurs@exemple.ch"), _Requete(ip="198.51.100.12"))
    verifier("D9. le debit est par IP, pas global",
             MOTIF_AFR.match(str(r.get("access_code") or "")), repr(r))


# ============================================================================
#                  C. LA STRUCTURE DU CODE, LUE PAR AST
# ============================================================================
def structure():
    arbre = ast.parse(SRC_FREE)

    # C1. `req.access_code` n'est JAMAIS lu : le client ne dicte pas le code.
    lit_req = any(isinstance(n, ast.Attribute) and n.attr == "access_code"
                  and isinstance(n.value, ast.Name) and n.value.id == "req"
                  for n in ast.walk(arbre))
    verifier("C1. `req.access_code` n'est jamais lu", not lit_req)

    # C2. la route ne fabrique aucun code elle-meme : un litteral `AFR-` ici
    #     signifierait un code invente hors du moteur.
    # Le CODE seul : la docstring parle du « code AFR- », et la lire ici
    # ferait echouer C2 sur une phrase d'explication.
    _corps = list(ast.parse(SRC_FREE).body[0].body)
    if (_corps and isinstance(_corps[0], ast.Expr)
            and isinstance(getattr(_corps[0], "value", None), ast.Constant)
            and isinstance(_corps[0].value.value, str)):
        _corps = _corps[1:]
    corps = "\n".join(ast.unparse(x) for x in _corps)
    verifier("C2. la route ne fabrique aucun code AFR- elle-meme",
             "AFR-" not in corps, "litteral AFR- present")

    # C3. le code rendu vient de `result`, le retour du moteur.
    verifier("C3. le code rendu est lu sur `result`",
             re.search(r"result.*access_code|access_code.*result", corps) is not None,
             "aucune lecture d'access_code sur result")

    # C4. toutes les gardes restent AVANT la creation.
    # On vise l'APPEL, pas la premiere mention : le nom du moteur figure aussi
    # dans la docstring, tout en haut, et le test se serait auto-valide.
    pos_moteur = SRC_FREE.index("await _process_successful_payment(")
    for garde in ("_t1_preuve_checkout", "_lot2_verifier_vendeur",
                  "_essai1b_exiger_gratuit", "_essai4_garde", "_lotr_garde",
                  "_essai1_garde"):
        verifier("C4. %s reste avant la creation" % garde,
                 garde in SRC_FREE and SRC_FREE.index(garde) < pos_moteur, garde)

    # C5. ESSAI-1 (qui ECRIT le verrou) reste apres ESSAI-4 (qui LIT) : sans
    #     cet ordre, un abonne actif brulerait son droit a l'essai pour
    #     s'entendre refuser juste apres.
    verifier("C5. ESSAI-1 reste la derniere garde avant la creation",
             SRC_FREE.index("_essai1_garde") > SRC_FREE.index("_essai4_garde"))

    # C7. la vierginite de l'adresse est CONSTATEE AVANT la creation : apres,
    #     le forfait et le code que l'on vient d'ecrire la rendraient toujours
    #     fausse, et plus aucun code ne repartirait.
    verifier("C7. l'adresse est examinee AVANT la creation",
             "_essai7_espace_vierge" in SRC_FREE
             and SRC_FREE.index("_essai7_espace_vierge") < pos_moteur)

    # C8. le debit est la toute premiere garde : un refus ne doit rien couter.
    verifier("C8. le debit est verifie avant toute autre garde",
             "_essai7_exiger_debit" in SRC_FREE
             and SRC_FREE.index("_essai7_exiger_debit")
             < SRC_FREE.index("_t1_preuve_checkout"))

    # C6. la liberation en cas de panne reste branchee sur le `except`.
    verifier("C6. une panne libere toujours l'essai",
             "_essai1_liberer" in SRC_FREE and "raise" in SRC_FREE)


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(reponse())
        b.run_until_complete(refus())
        b.run_until_complete(securite())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Essais gratuits REELLEMENT crees : 0 — aucune base, aucun reseau")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

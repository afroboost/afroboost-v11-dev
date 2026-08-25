# -*- coding: utf-8 -*-
"""RAPPELS V2 — le rappel avant cours part sur DEUX canaux, suivis separement.

Ce test execute le VRAI `cron_reservation_reminders` extrait de `api/server.py`
par AST, avec ses vraies aides. Rien n'est recopie a la main : ce qui est
verifie ici est ce qui tournera en production.

Aucun reseau. Aucun Push. Aucun e-mail. Aucun WhatsApp. Aucune base.
Le module `resend` n'est jamais importe, `pywebpush` non plus : les deux
canaux sont des mouchards qui enregistrent au lieu d'emettre, et leur
compteur participe au verdict final.

Lancement :  python3 tests/test_rv2_rappels_push_email.py
"""

import ast
import asyncio
import io
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

BASE_AVANT = "ef0a6d1"          # l'etat du depot avant ce lot
LOT = "efe5071"                 # le dernier commit DU LOT — borne haute

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ----------------------------------------------------------------- extraction
def noeud(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("introuvable : %s" % nom)


def extraire(nom):
    n = noeud(nom)
    return "".join(LIGNES[n.lineno - 1:n.end_lineno])


def code_nu(nom):
    """Le code EXECUTE, sans docstring ni commentaires.

    Les commentaires de ce lot citent `courseTime`, `datetime` et `$unset` pour
    expliquer les pieges : une recherche de texte brute les prendrait pour du
    code et validerait n'importe quoi.
    """
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]
    return "\n".join(ast.unparse(x) for x in corps)


CONSTANTES = """
N1B_CLE_HERITEE = "defaut"
N1B2_MAX_REGLES = 2
N1B2_DELAIS_AUTORISES = (60, 180, 1440, 2880)
N1B2_MINUTES_AUTORISEES = (0, 30)
N1B2_REGLES_DEFAUT = ({"type": "relative", "minutes": 60},)
N1B2_DEMI_FENETRE_MIN = 30
N1B2_HORIZON_MIN = 2880 + N1B2_DEMI_FENETRE_MIN
N1B3B2_ECART_MIN = 60
_V259_DEFAULT_COLOR = "#D91CD2"
RV2_CANAL_PUSH = "push"
RV2_CANAL_EMAIL = "email"
RV2_CANAUX = (RV2_CANAL_PUSH, RV2_CANAL_EMAIL)
RV2_REPLY_TO = "contact.artboost@gmail.com"
RV2_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
RV2_MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin",
            "juillet", "aout", "septembre", "octobre", "novembre", "decembre")
RESEND_AVAILABLE = True
RESEND_API_KEY = "re_faux_jamais_utilisee"
RV2_ESPACE_CARACTERES = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
"""

A_EXTRAIRE = ["_v259_primary_rgb", "_email_wrapper",
              "_v184_public_origin", "rv2_lien_espace",
              "n1b2_cle", "n1b2_cible", "n1b2_titre", "n1b2_corps",
              "n1b2_valider_regles", "n1b3b2_plan", "n1b2_regles_du_coach",
              "n1b3b2_regles_trop_proches", "rv3_ecrire_rappels_du_cours",
              "rv2_deja_envoye", "rv2_normaliser_marqueur", "rv2_reserver_canal",
              "rv2_liberer_canal", "rv2_canal_autorise", "rv2_email_valide",
              "rv2_date_lisible", "rv2_contenu_rappel", "rv2_envoyer_email_rappel",
              "cron_reservation_reminders"]


# ------------------------------------------------------- faux client MongoDB
MANQUANT = object()


def _valeur(doc, chemin):
    """Resout un chemin pointe `a.b.c`, comme MongoDB."""
    cur = doc
    for part in chemin.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return MANQUANT
        cur = cur[part]
    return cur


def _match(doc, q):
    for cle, attendu in (q or {}).items():
        # E2 : `$or` est un operateur de PREMIER niveau — sa valeur est une
        # liste de sous-requetes, pas un champ du document.
        if cle == "$or":
            if not any(_match(doc, sous) for sous in (attendu or [])):
                return False
            continue
        obtenu = _valeur(doc, cle)
        if isinstance(attendu, dict):
            for op, val in attendu.items():
                if op == "$options":
                    continue        # lu avec `$regex`, jamais seul
                if op == "$regex":
                    # E2 : le cron retrouve un code d'acces par regex ANCREE et
                    # ECHAPPEE, sans tenir compte de la casse — l'idiome deja
                    # utilise partout dans server.py. Le harnais doit donc
                    # savoir le simuler, sinon il validerait a l'aveugle.
                    if obtenu is MANQUANT or not isinstance(obtenu, str):
                        return False
                    _dr = re.IGNORECASE if "i" in (attendu.get("$options") or "") else 0
                    if not re.search(val, obtenu, _dr):
                        return False
                elif op == "$exists":
                    if bool(obtenu is not MANQUANT) != bool(val):
                        return False
                elif op == "$gte":
                    if obtenu is MANQUANT:
                        return False
                    # CLOISONNEMENT PAR TYPE, comme MongoDB : comparer une
                    # chaine a autre chose ne matche pas, et ne leve pas.
                    if type(obtenu) is not type(val) or not (obtenu >= val):
                        return False
                elif op == "$ne":
                    if obtenu is not MANQUANT and obtenu == val:
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        else:
            if obtenu is MANQUANT or obtenu != attendu:
                return False
    return True


def _poser(doc, chemin, valeur):
    """Ecrit un chemin pointe. Refuse de creer un champ DANS une chaine —
    c'est exactement ce que fait MongoDB, et c'est ce qui rend
    `rv2_normaliser_marqueur` indispensable."""
    parts = chemin.split(".")
    cur = doc
    for i, part in enumerate(parts[:-1]):
        suite = cur.get(part, MANQUANT)
        if suite is MANQUANT:
            cur[part] = {}
        elif not isinstance(suite, dict):
            raise RuntimeError(
                "Cannot create field '%s' in element {%s: %r}"
                % (parts[i + 1], part, suite))
        cur = cur[part]
    cur[parts[-1]] = valeur


def _retirer(doc, chemin):
    parts = chemin.split(".")
    cur = doc
    for part in parts[:-1]:
        cur = cur.get(part)
        if not isinstance(cur, dict):
            return
    cur.pop(parts[-1], None)


def _appliquer(doc, m):
    for op, champs in m.items():
        if op == "$set":
            for k, v in champs.items():
                _poser(doc, k, v)
        elif op == "$unset":
            for k in champs:
                _retirer(doc, k)
        else:
            raise AssertionError("operateur de mise a jour non simule : %s" % op)


class _Res(object):
    def __init__(self, n):
        self.matched_count = n
        self.modified_count = n


class _Curseur(object):
    def __init__(self, d):
        self.d = d

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        await asyncio.sleep(0)
        import copy
        return [copy.deepcopy(x) for x in self.d[:n]]

    # E2 : Motor rend un curseur qu'on peut aussi PARCOURIR (`async for`), et
    # c'est cette forme qu'utilise la verification des codes d'acces. Sans elle,
    # le harnais levait une exception que le code de production rattrape — le
    # test aurait donc valide « pas de lien » en croyant tester le contraire.
    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        await asyncio.sleep(0)
        import copy
        if self._i >= len(self.d):
            raise StopAsyncIteration
        self._i += 1
        return copy.deepcopy(self.d[self._i - 1])


class _Coll(object):
    """Chaque methode REND LA MAIN a la boucle avant d'agir.

    C'est le trajet reseau vers MongoDB, et c'est indispensable : sans ce point
    de suspension, `asyncio.gather` deroulerait la premiere tache entierement
    avant de demarrer la seconde, aucun entrelacement ne se produirait, et un
    test de concurrence passerait meme sans reservation prealable.

    L'atomicite, elle, est modelisee par l'ABSENCE de `await` entre le filtre et
    l'ecriture DANS `update_one`. Rendre la main avant : oui. Pendant : jamais.
    C'est le contrat de MongoDB au niveau du document.
    """

    def __init__(self, docs=None):
        self.docs = docs or []
        self.lectures = 0

    def find(self, q=None, p=None):
        return _Curseur([d for d in self.docs if _match(d, q or {})])

    async def find_one(self, q, p=None):
        await asyncio.sleep(0)
        self.lectures += 1
        import copy
        for d in self.docs:
            if _match(d, q):
                return copy.deepcopy(d)
        return None

    async def update_one(self, q, m, **k):
        await asyncio.sleep(0)   # trajet reseau — AVANT la section atomique
        # --- section atomique : aucun await du filtre a l'ecriture ---
        for d in self.docs:
            if _match(d, q):
                _appliquer(d, m)
                return _Res(1)
        return _Res(0)


COURS_ACTIF = {"id": "c1", "name": "Danse Afro", "archived": False,
               "reminders_enabled": True,
               "reminder_rules": [{"type": "relative", "minutes": 60}]}


def cours(cid="c1", actif=True, regles=None, archive=False, **extra):
    """Un cours de test. `actif=None` laisse le champ ABSENT — le cas du parc
    historique, qui doit rester muet."""
    d = {"id": cid, "name": "Danse Afro", "archived": archive}
    if actif is not None:
        d["reminders_enabled"] = bool(actif)
    if regles is not None:
        d["reminder_rules"] = regles
    elif actif:
        d["reminder_rules"] = [{"type": "relative", "minutes": 60}]
    d.update(extra)
    return d


class _Base(object):
    def __init__(self, resas, prefs=None, profils=None, cours_docs=None,
                 codes=None):
        self.reservations = _Coll(resas)
        self.notification_preferences = _Coll(prefs or [])
        self.coach_profiles = _Coll(profils or [])
        self.courses = _Coll([dict(COURS_ACTIF)] if cours_docs is None else cours_docs)
        # E2 : le cron verifie qu'un code d'acces EXISTE avant d'en faire un
        # lien. Vide par defaut -> aucun lien, comme avant ce lot.
        self.discount_codes = _Coll(codes or [])


class _HTTP(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code
        self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))


APPELANT = ["coach@exemple.com"]


async def _appelant(request):
    await asyncio.sleep(0)
    return APPELANT[0]


class _Requete(object):
    """Requete minimale : la route ne lit que son corps JSON."""

    def __init__(self, corps=None):
        self._corps = corps if corps is not None else {}

    async def json(self):
        await asyncio.sleep(0)
        if self._corps is _ILLISIBLE:
            raise ValueError("corps illisible")
        return self._corps


_ILLISIBLE = object()


# ------------------------------------------------------------- les mouchards
PUSHS = []          # doit rester vide sauf quand le scenario l'autorise
EMAILS = []         # idem — aucun de ces deux n'atteint le reseau


class _FauxEmails(object):
    echec = False

    @staticmethod
    def send(payload):
        if _FauxEmails.echec:
            raise RuntimeError("Resend refuse (simule)")
        EMAILS.append(payload)
        return {"id": "faux"}


class _FauxResend(object):
    Emails = _FauxEmails


def bac(resas, prefs=None, profils=None, push_ok=True, email_ok=True, cours_docs=None,
        codes=None):
    PUSHS[:] = []
    EMAILS[:] = []
    _FauxEmails.echec = not email_ok
    base = _Base(resas, prefs, profils, cours_docs, codes)

    async def faux_push(email, titre, corps, data=None):
        await asyncio.sleep(0)
        if not push_ok:
            return False
        PUSHS.append({"email": email, "titre": titre, "corps": corps, "data": data})
        return True

    async def faux_couleur(coach_email=""):
        await asyncio.sleep(0)
        return "#D91CD2"

    b = {
        "db": base,
        "asyncio": asyncio,
        "os": os, "re": re,
        "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
        "resend": _FauxResend,
        "send_push_by_email": faux_push,
        "_v259_primary_color": faux_couleur,
        "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                 for k in ("info", "warning", "error", "debug")}),
        "api_router": type("r", (), {
            "get": staticmethod(lambda *a, **k: (lambda f: f)),
            "put": staticmethod(lambda *a, **k: (lambda f: f))}),
        "HTTPException": _HTTP,
        "Request": object,
        "is_super_admin": lambda e: (e or "").lower() == "admin@exemple.com",
        "_n1b3b2_coach_appelant": _appelant,
    }
    morceaux = [CONSTANTES] + [extraire(f) for f in A_EXTRAIRE]
    exec(compile("\n\n".join(morceaux), "<rv2>", "exec"), b)
    absents = [f for f in A_EXTRAIRE if f not in b]
    assert not absents, "extraction incomplete : %s" % absents
    return b, base


# ----------------------------------------------------------- jeux de donnees
ZURICH = None
try:
    from zoneinfo import ZoneInfo
    ZURICH = ZoneInfo("Europe/Zurich")
except Exception:
    pass


def resa(rid="r1", email="abo@exemple.com", course_time="18:30",
         decalage_min=60, nom="Awa Diallo", instant=None, **extra):
    """Une reservation dont le cours tombe dans la fenetre du rappel `defaut`.

    La regle par defaut vise 60 min avant le cours ; la fenetre est de +/- 30
    min. Un cours a `now + 60 min` place donc la cible exactement sur `now`.
    """
    quand = instant or (datetime.now(timezone.utc) + timedelta(minutes=decalage_min))
    d = {
        "id": rid,
        "userEmail": email,
        "userName": nom,
        "courseName": "Danse Afro",
        "courseTime": course_time,
        "coach_id": "coach@exemple.com",
        "courseId": "c1",
        "datetime": quand.astimezone(ZURICH).isoformat() if ZURICH else quand.isoformat(),
    }
    d.update(extra)
    return d


def pref(email="abo@exemple.com", **cles):
    return {"email": email, "role": "subscriber", "preferences": dict(cles)}


def marqueur(doc, cle="defaut"):
    return (doc.get("reminders_sent") or {}).get(cle)


async def passage(b):
    return await b["cron_reservation_reminders"]()


# ============================================================================
#                        LES 17 VERIFICATIONS BLOQUANTES
# ============================================================================
async def scenarios():
    # --- 1. Push ON + Email ON -> deux canaux ------------------------------
    b, base = bac([resa()])
    await passage(b)
    doc = base.reservations.docs[0]
    verifier("1. Push ON + Email ON -> les DEUX canaux partent",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    _m = marqueur(doc)
    verifier("1b. un marqueur par canal est ecrit",
             isinstance(_m, dict) and _m.get("push") and _m.get("email"), repr(_m))

    # --- 2. Push indisponible + Email ON -> e-mail seul --------------------
    b, base = bac([resa()], push_ok=False)
    await passage(b)
    doc = base.reservations.docs[0]
    verifier("2. Push indisponible -> l'e-mail part QUAND MEME",
             len(PUSHS) == 0 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    verifier("2b. le marqueur push a ete relache (canal reessayable)",
             not (marqueur(doc) or {}).get("push"), repr(marqueur(doc)))
    verifier("2c. le marqueur e-mail, lui, est pose",
             bool((marqueur(doc) or {}).get("email")), repr(marqueur(doc)))

    # --- 3. Push ON + Email OFF -> push seul -------------------------------
    b, base = bac([resa()], prefs=[pref(before_class_email=False)])
    await passage(b)
    verifier("3. Email OFF -> le Push part SEUL",
             len(PUSHS) == 1 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- 4. rappels avant cours desactives -> rien -------------------------
    b, base = bac([resa()], prefs=[pref(before_class=False)])
    await passage(b)
    verifier("4. before_class desactive -> AUCUN canal",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    verifier("4b. et aucun marqueur n'a ete laisse derriere",
             marqueur(base.reservations.docs[0]) in (None, {}),
             repr(marqueur(base.reservations.docs[0])))

    # --- 5. Push echoue, Email reussit -> push retentable ------------------
    docs = [resa()]
    b, base = bac(docs, push_ok=False)
    await passage(b)
    verifier("5. Push en echec -> e-mail marque, push NON marque",
             len(EMAILS) == 1 and not (marqueur(docs[0]) or {}).get("push"))
    b2, _ = bac(docs, push_ok=True)          # meme document, passage suivant
    await passage(b2)
    verifier("5b. au passage suivant le Push est REESSAYE, pas l'e-mail",
             len(PUSHS) == 1 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- 6. Email echoue, Push reussit -> e-mail retentable ----------------
    docs = [resa()]
    b, base = bac(docs, email_ok=False)
    await passage(b)
    verifier("6. E-mail en echec -> push marque, e-mail NON marque",
             len(PUSHS) == 1 and not (marqueur(docs[0]) or {}).get("email"),
             repr(marqueur(docs[0])))
    b2, _ = bac(docs, email_ok=True)
    await passage(b2)
    verifier("6b. au passage suivant l'e-mail est REESSAYE, pas le Push",
             len(EMAILS) == 1 and len(PUSHS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- 7. e-mail deja marque -> aucun doublon ----------------------------
    d = resa()
    d["reminders_sent"] = {"defaut": {"email": "2026-01-01T00:00:00+00:00"}}
    b, base = bac([d])
    await passage(b)
    verifier("7. e-mail deja marque -> aucun second e-mail",
             len(EMAILS) == 0 and len(PUSHS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- 8. push deja marque -> aucun doublon ------------------------------
    d = resa()
    d["reminders_sent"] = {"defaut": {"push": "2026-01-01T00:00:00+00:00"}}
    b, base = bac([d])
    await passage(b)
    verifier("8. push deja marque -> aucun second push",
             len(PUSHS) == 0 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- 9. concurrence ----------------------------------------------------
    b, base = bac([resa()])
    await asyncio.gather(*[passage(b) for _ in range(2)])
    verifier("9. 2 crons simultanes -> 1 push et 1 e-mail, pas deux",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    b, base = bac([resa()])
    await asyncio.gather(*[passage(b) for _ in range(10)])
    verifier("9b. 10 crons simultanes -> toujours 1 push et 1 e-mail",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- 10. courseTime present -> bonne heure -----------------------------
    b, base = bac([resa(course_time="18:30")])
    await passage(b)
    _e = EMAILS[0] if EMAILS else {}
    verifier("10. courseTime present -> l'heure figure dans l'e-mail",
             "18:30" in _e.get("html", "") and "18:30" in _e.get("text", ""),
             repr(_e.get("text", ""))[:160])

    # --- 11. reservations.datetime NE SERT JAMAIS d'heure ------------------
    _instant = datetime.now(timezone.utc) + timedelta(minutes=60)
    _hhmm_datetime = (_instant.astimezone(ZURICH) if ZURICH else _instant).strftime("%H:%M")
    _faux = "18:30" if _hhmm_datetime != "18:30" else "07:15"
    b, base = bac([resa(course_time=_faux, instant=_instant)])
    await passage(b)
    _e = EMAILS[0] if EMAILS else {}
    _tout = _e.get("subject", "") + _e.get("html", "") + _e.get("text", "")
    verifier("11. l'heure de `datetime` n'apparait NULLE PART dans l'e-mail",
             _faux in _tout and _hhmm_datetime not in _tout,
             "attendu %s, interdit %s" % (_faux, _hhmm_datetime))

    # --- 12. courseTime absent -> aucune heure inventee --------------------
    b, base = bac([resa(course_time="")])
    await passage(b)
    _e = EMAILS[0] if EMAILS else {}
    _tout = _e.get("subject", "") + _e.get("text", "")
    _heures = re.findall(r"\d{1,2}[:h]\d{2}", _tout)
    verifier("12. courseTime absent -> AUCUNE heure inventee",
             len(EMAILS) == 1 and not _heures, "trouve : %s" % _heures)

    # --- 13. ancien contact : rien ne se perd ------------------------------
    b, base = bac([resa()], prefs=[])
    await passage(b)
    verifier("13a. aucune preference enregistree -> les deux canaux",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    b, base = bac([resa()], prefs=[pref(before_class=True, new_offer=False)])
    await passage(b)
    verifier("13b. ancienne cle before_class=True -> les deux canaux",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    d = resa()
    d["reminders_sent"] = {"defaut": "2026-01-01T00:00:00+00:00"}   # forme heritee
    b, base = bac([d])
    await passage(b)
    verifier("13c. marqueur herite (chaine) -> push tenu pour fait, e-mail envoye",
             len(PUSHS) == 0 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    verifier("13d. la chaine heritee a ete convertie sans perdre l'horodatage",
             (marqueur(d) or {}).get("push") == "2026-01-01T00:00:00+00:00",
             repr(marqueur(d)))

    d = resa()
    d["reminder_sent"] = True                                        # booleen d'avant N1B-1
    b, base = bac([d])
    await passage(b)
    verifier("13e. booleen historique -> push tenu pour fait, e-mail envoye",
             len(PUSHS) == 0 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- 14 / 15. opt-out par canal ----------------------------------------
    b, base = bac([resa()], prefs=[pref(before_class_push=False)])
    await passage(b)
    verifier("14. opt-out Push -> aucun Push, l'e-mail passe",
             len(PUSHS) == 0 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    b, base = bac([resa()], prefs=[pref(before_class_email=False)])
    await passage(b)
    verifier("15. opt-out Email -> aucun e-mail, le Push passe",
             len(EMAILS) == 0 and len(PUSHS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # la cle de canal l'emporte sur la cle historique
    b, base = bac([resa()], prefs=[pref(before_class=False, before_class_email=True)])
    await passage(b)
    verifier("15b. la cle de canal prime sur la cle historique",
             len(EMAILS) == 1 and len(PUSHS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- adresse e-mail inexploitable --------------------------------------
    b, base = bac([resa(email="pas-une-adresse")])
    await passage(b)
    verifier("15c. adresse invalide -> aucun e-mail, le Push passe",
             len(EMAILS) == 0 and len(PUSHS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- l'e-mail lui-meme : forme ----------------------------------------
    b, base = bac([resa(nom="Awa Diallo")])
    await passage(b)
    _e = EMAILS[0] if EMAILS else {}
    verifier("16a. Reply-To pose sur une boite relevee",
             _e.get("reply_to") == "contact.artboost@gmail.com", repr(_e.get("reply_to")))
    verifier("16b. version HTML ET version texte",
             bool(_e.get("html")) and bool(_e.get("text")))
    verifier("16c. le sujet ne commence pas par un emoji",
             (_e.get("subject", "") or "x")[0].isalpha()
             and ord(_e.get("subject", "x")[0]) < 128, repr(_e.get("subject")))
    verifier("16d. le prenom seul est utilise, pas le nom complet",
             "Awa" in _e.get("text", "") and "Diallo" not in _e.get("text", ""),
             repr(_e.get("text", ""))[:120])
    verifier("16e. le nom du cours figure dans le sujet",
             "Danse Afro" in _e.get("subject", ""), repr(_e.get("subject")))


# ============================================================================
#            NIVEAU 1 — LE COACH DECIDE QUELS COURS ENVOIENT DES RAPPELS
# ============================================================================
async def scenarios_niveau1():
    R60 = [{"type": "relative", "minutes": 60}]
    R1440 = [{"type": "relative", "minutes": 1440}]

    # --- N1. champ absent : le parc historique reste muet ------------------
    b, base = bac([resa()], cours_docs=[cours(actif=None)])
    await passage(b)
    verifier("N1. reminders_enabled ABSENT -> aucun rappel",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    verifier("N1b. et aucun marqueur n'est laisse sur la reservation",
             marqueur(base.reservations.docs[0]) in (None, {}))

    # --- N2. explicitement desactive ---------------------------------------
    b, base = bac([resa()], cours_docs=[cours(actif=False)])
    await passage(b)
    verifier("N2. reminders_enabled = false -> aucun rappel",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N3. active avec des regles valides --------------------------------
    b, base = bac([resa()], cours_docs=[cours(actif=True, regles=R60)])
    await passage(b)
    verifier("N3. actif + regles valides -> les deux canaux",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N4. deux cours, un seul actif -------------------------------------
    b, base = bac([resa(rid="rA", courseId="cA"), resa(rid="rB", courseId="cB")],
                  cours_docs=[cours(cid="cA", actif=True, regles=R60),
                              cours(cid="cB", actif=False)])
    await passage(b)
    _dests = sorted(set([p["email"] for p in PUSHS]))
    verifier("N4. cours A ON / cours B OFF -> seul A emet",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    verifier("N4b. c'est bien la reservation du cours A qui a ete marquee",
             bool(marqueur(base.reservations.docs[0]))
             and not marqueur(base.reservations.docs[1]),
             "%r / %r" % (marqueur(base.reservations.docs[0]),
                          marqueur(base.reservations.docs[1])))

    # --- N5. chaque cours utilise SES regles --------------------------------
    # A vise 60 min avant (donc dans la fenetre), B vise 24 h avant (hors
    # fenetre pour un cours dans 60 min). Seul A doit sortir.
    b, base = bac([resa(rid="rA", courseId="cA"), resa(rid="rB", courseId="cB")],
                  cours_docs=[cours(cid="cA", actif=True, regles=R60),
                              cours(cid="cB", actif=True, regles=R1440)])
    await passage(b)
    verifier("N5. regles differentes par cours -> seule celle de A se declenche",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    verifier("N5b. B, regle a 24 h, n'est pas marque pour ce passage",
             not marqueur(base.reservations.docs[1]),
             repr(marqueur(base.reservations.docs[1])))

    # --- N6. actif mais sans regle : fail-closed ---------------------------
    b, base = bac([resa()], cours_docs=[cours(actif=True, regles=[])])
    await passage(b)
    verifier("N6. actif SANS regle exploitable -> aucun rappel (fail-closed)",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    b, base = bac([resa()], cours_docs=[cours(actif=True, regles=[{"type": "n_importe_quoi"}])])
    await passage(b)
    verifier("N6b. regles invalides -> aucun rappel, aucun repli invente",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N7. AUCUN repli sur les regles globales du coach ------------------
    b, base = bac([resa()],
                  profils=[{"email": "coach@exemple.com", "reminder_rules": R60}],
                  cours_docs=[cours(actif=None)])
    await passage(b)
    verifier("N7. cours non configure + regles globales coach -> toujours RIEN",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
    verifier("N7b. le cron ne lit meme plus coach_profiles",
             base.coach_profiles.lectures == 0,
             "%d lecture(s)" % base.coach_profiles.lectures)

    # --- N8. cours archive --------------------------------------------------
    b, base = bac([resa()], cours_docs=[cours(actif=True, regles=R60, archive=True)])
    await passage(b)
    verifier("N8. cours archive -> aucun rappel meme s'il est actif",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N9. reservation sans courseId --------------------------------------
    d = resa(); d.pop("courseId")
    b, base = bac([d])
    await passage(b)
    verifier("N9. reservation sans cours rattache -> aucun rappel",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N10. le cours est lu UNE fois, pas une fois par reservation --------
    _lot = [resa(rid="r%d" % i, email="abo%d@exemple.com" % i) for i in range(12)]
    b, base = bac(_lot, cours_docs=[cours(actif=True, regles=R60)])
    await passage(b)
    verifier("N10. 12 reservations du meme cours -> 1 SEULE lecture de cours",
             base.courses.lectures == 1, "%d lecture(s)" % base.courses.lectures)
    verifier("N10b. et les 12 rappels partent bien",
             len(PUSHS) == 12 and len(EMAILS) == 12,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N11. le niveau 1 prime sur les preferences participant -------------
    b, base = bac([resa()],
                  prefs=[pref(before_class_push=True, before_class_email=True)],
                  cours_docs=[cours(actif=False)])
    await passage(b)
    verifier("N11. cours OFF + participant tout ON -> AUCUN envoi",
             len(PUSHS) == 0 and len(EMAILS) == 0,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N12. cours ON : les preferences participant reprennent la main -----
    for _titre, _p, _ap, _ae in (
            ("N12. cours ON + Push ON + Email ON -> deux canaux", {}, 1, 1),
            ("N13. cours ON + Push OFF -> e-mail seul", {"before_class_push": False}, 0, 1),
            ("N14. cours ON + Email OFF -> push seul", {"before_class_email": False}, 1, 0)):
        b, base = bac([resa()], prefs=([pref(**_p)] if _p else []),
                      cours_docs=[cours(actif=True, regles=R60)])
        await passage(b)
        verifier(_titre, len(PUSHS) == _ap and len(EMAILS) == _ae,
                 "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- N15. cours recurrents mercredi et dimanche -------------------------
    # La configuration est portee par le COURS ; chaque occurrence en herite
    # sans reglage par date. On le prouve sur deux occurrences distinctes du
    # meme cours, traitees dans le meme passage.
    _j1 = datetime.now(timezone.utc) + timedelta(minutes=60)
    _j2 = datetime.now(timezone.utc) + timedelta(minutes=60)
    b, base = bac([resa(rid="occ1", email="a@exemple.com", instant=_j1, courseId="merc"),
                   resa(rid="occ2", email="b@exemple.com", instant=_j2, courseId="merc")],
                  cours_docs=[cours(cid="merc", actif=True, regles=R60)])
    await passage(b)
    verifier("N15. deux occurrences du meme cours recurrent -> memes regles, 1 lecture",
             len(PUSHS) == 2 and len(EMAILS) == 2 and base.courses.lectures == 1,
             "%d push / %d e-mail / %d lecture(s)"
             % (len(PUSHS), len(EMAILS), base.courses.lectures))

    # --- N16. les instants reels du mercredi et du dimanche 18:30 -----------
    # Calcul pur, sans envoi : on verifie que « la veille » et « le jour meme »
    # tombent ou le coach les attend, sur les vrais cours recurrents.
    if ZURICH is not None:
        _regles = [{"type": "relative", "minutes": 1440},
                   {"type": "same_day", "heure": 7, "minute": 0}]
        _base_j = datetime.now(ZURICH).date()
        for _nom_jour, _cible_py in (("mercredi", 2), ("dimanche", 6)):
            _d = _base_j
            for _ in range(8):
                _d = _d + timedelta(days=1)
                if _d.weekday() == _cible_py:
                    break
            _cours_local = datetime(_d.year, _d.month, _d.day, 18, 30, tzinfo=ZURICH)
            _gardees, _ = b["n1b3b2_plan"](_regles, _cours_local.astimezone(timezone.utc), ZURICH)
            _heures = sorted(c.astimezone(ZURICH).strftime("%a %d/%m %H:%M") for c, _cl in _gardees)
            _veille = (_cours_local - timedelta(minutes=1440)).strftime("%a %d/%m %H:%M")
            _jour_meme = _cours_local.replace(hour=7, minute=0).strftime("%a %d/%m %H:%M")
            verifier("N16-%s. veille + jour meme tombent aux bons instants" % _nom_jour,
                     _heures == sorted([_veille, _jour_meme]),
                     "obtenu %s / attendu %s" % (_heures, sorted([_veille, _jour_meme])))
            print("      %s %s 18:30 -> rappels : %s" % (_nom_jour, _d.strftime("%d/%m"), _heures))


# ============================================================================
#          LA ROUTE QUI ECRIT LA CONFIGURATION D'UN COURS
# ============================================================================
async def scenarios_route():
    R24 = [{"type": "relative", "minutes": 1440}]
    RSD = [{"type": "same_day", "heure": 7, "minute": 0}]
    APPELANT[0] = "coach@exemple.com"

    def _bac_route(cours_docs):
        b, base = bac([], cours_docs=cours_docs)
        return b["rv3_ecrire_rappels_du_cours"], base

    async def _appel(route, cid, corps):
        try:
            return await route(cid, _Requete(corps)), None
        except _HTTP as e:
            return None, e

    # R1. cours inconnu
    route, base = _bac_route([cours(cid="c1", actif=None)])
    _r, _e = await _appel(route, "inconnu", {"enabled": True, "rules": R24})
    verifier("R1. cours inconnu -> 404", _e is not None and _e.status_code == 404,
             repr(_e and _e.status_code))

    # R2. cours d'un autre coach
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="autre@exemple.com")])
    _r, _e = await _appel(route, "c1", {"enabled": True, "rules": R24})
    verifier("R2. cours d'un autre coach -> 403",
             _e is not None and _e.status_code == 403, repr(_e and _e.status_code))

    # R2b. le super-admin passe outre
    APPELANT[0] = "admin@exemple.com"
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="autre@exemple.com")])
    _r, _e = await _appel(route, "c1", {"enabled": True, "rules": R24})
    verifier("R2b. le super-admin peut configurer le cours d'un autre",
             _e is None and _r and _r.get("reminders_enabled") is True, repr(_e))
    APPELANT[0] = "coach@exemple.com"

    # R3. activer sans regle
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="coach@exemple.com")])
    _r, _e = await _appel(route, "c1", {"enabled": True})
    verifier("R3. activer SANS regle -> 400, rien n'est ecrit",
             _e is not None and _e.status_code == 400
             and base.courses.docs[0].get("reminders_enabled") is None,
             repr(_e and _e.status_code))

    # R4. regles invalides
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="coach@exemple.com")])
    _r, _e = await _appel(route, "c1", {"enabled": True,
                                        "rules": [{"type": "relative", "minutes": 42}]})
    verifier("R4. delai hors liste -> 400", _e is not None and _e.status_code == 400,
             repr(_e and _e.status_code))

    # R5. deux heures fixes trop proches
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="coach@exemple.com")])
    _r, _e = await _appel(route, "c1", {"enabled": True, "rules": [
        {"type": "same_day", "heure": 7, "minute": 0},
        {"type": "same_day", "heure": 7, "minute": 30}]})
    verifier("R5. deux rappels le jour meme a 30 min d'ecart -> 400",
             _e is not None and _e.status_code == 400, repr(_e and _e.status_code))

    # R6. activation nominale
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="coach@exemple.com")])
    _r, _e = await _appel(route, "c1", {"enabled": True, "rules": R24 + RSD})
    _doc = base.courses.docs[0]
    verifier("R6. activation valide -> le cours porte l'etat ET ses regles",
             _e is None and _doc.get("reminders_enabled") is True
             and _doc.get("reminder_rules") == R24 + RSD,
             "%r / %r" % (_doc.get("reminders_enabled"), _doc.get("reminder_rules")))

    # R7. couper ne detruit pas les regles
    route, base = _bac_route([cours(cid="c1", actif=True, regles=R24,
                                    coach_id="coach@exemple.com")])
    _r, _e = await _appel(route, "c1", {"enabled": False})
    _doc = base.courses.docs[0]
    verifier("R7. couper les rappels -> etat a faux, regles CONSERVEES",
             _e is None and _doc.get("reminders_enabled") is False
             and _doc.get("reminder_rules") == R24,
             "%r / %r" % (_doc.get("reminders_enabled"), _doc.get("reminder_rules")))

    # R8. corps illisible
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="coach@exemple.com")])
    _r, _e = await _appel(route, "c1", _ILLISIBLE)
    verifier("R8. corps illisible -> 400", _e is not None and _e.status_code == 400,
             repr(_e and _e.status_code))

    # R9. `enabled` absent vaut NON — jamais une activation par inadvertance
    route, base = _bac_route([cours(cid="c1", actif=None, coach_id="coach@exemple.com")])
    _r, _e = await _appel(route, "c1", {"rules": R24})
    verifier("R9. `enabled` absent -> desactivation, jamais activation",
             _e is None and base.courses.docs[0].get("reminders_enabled") is False,
             repr(base.courses.docs[0].get("reminders_enabled")))


# ============================================================================
#     FLEXIBILITE — LA CONFIGURATION TIENT AU COURS, JAMAIS AU JOUR
# ============================================================================
async def scenarios_flexibilite():
    """Aucun jour n'est code en dur nulle part.

    Ces verifications ne parlent volontairement pas de « mercredi » ni de
    « dimanche » : elles prennent des jours quelconques, deux cours le meme
    jour, un cours ponctuel, et vont jusqu'a DEPLACER un cours pour verifier
    que son reglage le suit. La cle est `course_id`, et rien d'autre.
    """
    R60 = [{"type": "relative", "minutes": 60}]
    R180 = [{"type": "relative", "minutes": 180}]

    # --- F1. un cours cree APRES coup, un jeudi, sans une ligne de code -----
    _jeudi = cours(cid="nouveau-jeudi", actif=True, regles=R60,
                   weekday=4, time="19:00", name="Atelier du jeudi")
    b, base = bac([resa(courseId="nouveau-jeudi")], cours_docs=[_jeudi])
    await passage(b)
    verifier("F1. cours du jeudi cree apres coup -> configurable tel quel",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- F2. deux cours LE MEME JOUR, reglages independants ----------------
    # Le premier vise 60 min avant (dans la fenetre), le second 3 h avant
    # (hors fenetre). Meme jour, meme heure, verdicts opposes.
    b, base = bac([resa(rid="r1", email="a@exemple.com", courseId="jeudi-a"),
                   resa(rid="r2", email="b@exemple.com", courseId="jeudi-b")],
                  cours_docs=[cours(cid="jeudi-a", actif=True, regles=R60,
                                    weekday=4, time="19:00"),
                              cours(cid="jeudi-b", actif=True, regles=R180,
                                    weekday=4, time="19:00")])
    await passage(b)
    verifier("F2. deux cours le MEME jour -> reglages independants",
             len(PUSHS) == 1 and PUSHS[0]["email"] == "a@exemple.com",
             "%d push, destinataires %s" % (len(PUSHS), [p["email"] for p in PUSHS]))

    # --- F3. deux cours le meme jour, l'un ON l'autre OFF -------------------
    b, base = bac([resa(rid="r1", email="a@exemple.com", courseId="sam-a"),
                   resa(rid="r2", email="b@exemple.com", courseId="sam-b")],
                  cours_docs=[cours(cid="sam-a", actif=True, regles=R60, weekday=6),
                              cours(cid="sam-b", actif=False, weekday=6)])
    await passage(b)
    verifier("F3. meme jour, un cours ON et un OFF -> seul le ON emet",
             len(PUSHS) == 1 and PUSHS[0]["email"] == "a@exemple.com",
             "%d push, destinataires %s" % (len(PUSHS), [p["email"] for p in PUSHS]))

    # --- F4. cours PONCTUEL (une date, aucun jour de semaine) ---------------
    _ponctuel = cours(cid="atelier-unique", actif=True, regles=R60,
                      weekday=None, date="2026-09-12", name="Atelier special")
    _ponctuel.pop("weekday", None)
    b, base = bac([resa(courseId="atelier-unique")], cours_docs=[_ponctuel])
    await passage(b)
    verifier("F4. cours ponctuel, sans jour de semaine -> configurable",
             len(PUSHS) == 1 and len(EMAILS) == 1,
             "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))

    # --- F5. cours RECURRENT, n'importe quel jour ---------------------------
    _tous = []
    for _j in range(7):
        _cid = "recurrent-%d" % _j
        _tous.append((_cid, cours(cid=_cid, actif=True, regles=R60, weekday=_j)))
    for _cid, _doc in _tous:
        b, base = bac([resa(courseId=_cid)], cours_docs=[_doc])
        await passage(b)
        if len(PUSHS) != 1 or len(EMAILS) != 1:
            verifier("F5. cours recurrent weekday=%s -> configurable" % _doc.get("weekday"),
                     False, "%d push / %d e-mail" % (len(PUSHS), len(EMAILS)))
            break
    else:
        verifier("F5. les SEPT jours de la semaine sont configurables a l'identique", True)

    # --- F6. deplacer un cours : le reglage le suit ------------------------
    _bouge = cours(cid="deplace", actif=True, regles=R60, weekday=2, time="18:30")
    b, base = bac([resa(rid="avant", courseId="deplace")], cours_docs=[_bouge])
    await passage(b)
    _avant = len(PUSHS)
    # Le coach change le jour ET l'heure du cours. Rien d'autre.
    _bouge["weekday"] = 5
    _bouge["time"] = "07:15"
    b2, base2 = bac([resa(rid="apres", courseId="deplace")], cours_docs=[_bouge])
    await passage(b2)
    verifier("F6. changer le jour et l'heure d'un cours -> son reglage le SUIT",
             _avant == 1 and len(PUSHS) == 1 and len(EMAILS) == 1
             and base2.courses.docs[0].get("reminders_enabled") is True
             and base2.courses.docs[0].get("reminder_rules") == R60,
             "avant %d push / apres %d push" % (_avant, len(PUSHS)))

    # --- F7. archivage : proprement, sans toucher aux autres ---------------
    b, base = bac([resa(rid="r1", email="a@exemple.com", courseId="vivant"),
                   resa(rid="r2", email="b@exemple.com", courseId="archive")],
                  cours_docs=[cours(cid="vivant", actif=True, regles=R60),
                              cours(cid="archive", actif=True, regles=R60, archive=True)])
    await passage(b)
    verifier("F7. un cours archive se tait, les autres continuent",
             len(PUSHS) == 1 and PUSHS[0]["email"] == "a@exemple.com",
             "%d push, destinataires %s" % (len(PUSHS), [p["email"] for p in PUSHS]))

    # --- F8. cours SUPPRIME : la reservation orpheline ne casse rien --------
    b, base = bac([resa(rid="r1", email="a@exemple.com", courseId="vivant"),
                   resa(rid="r2", email="b@exemple.com", courseId="disparu")],
                  cours_docs=[cours(cid="vivant", actif=True, regles=R60)])
    _sortie = await passage(b)
    verifier("F8. cours supprime -> reservation orpheline muette, le reste intact",
             len(PUSHS) == 1 and PUSHS[0]["email"] == "a@exemple.com"
             and isinstance(_sortie, dict) and "error" not in _sortie,
             "%d push, sortie %r" % (len(PUSHS), _sortie))

    # --- F9. aucun jour n'est code en dur dans la decision ------------------
    _nu = code_nu("cron_reservation_reminders")
    _jours = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
              "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    _trouves = [j for j in _jours if j in _nu.lower()]
    verifier("F9. le moteur ne nomme AUCUN jour de la semaine",
             not _trouves, "trouves : %s" % _trouves)
    verifier("F9b. il ne lit ni `weekday` ni `time` pour decider",
             "weekday" not in _nu and "'time'" not in _nu, "")


# ============================================================================
#                    TESTS DISCRIMINANTS — le harnais ment-il ?
# ============================================================================
async def discriminants():
    # D1 : le faux Mongo refuse bien de creer un champ dans une chaine.
    _doc = {"reminders_sent": {"defaut": "2026-01-01T00:00:00+00:00"}}
    _leve = False
    try:
        _poser(_doc, "reminders_sent.defaut.email", "x")
    except RuntimeError:
        _leve = True
    verifier("D1. le faux Mongo refuse un sous-champ dans une chaine "
             "(sinon la normalisation ne prouverait rien)", _leve)

    # D2 : le code d'AVANT le lot doit ECHOUER sous concurrence. Si le harnais
    # n'entrelacait pas, le test 9 passerait sur n'importe quoi.
    try:
        avant = subprocess.check_output(
            ["git", "show", "%s:api/server.py" % BASE_AVANT], cwd=RACINE).decode(errors="replace")
    except Exception as e:
        verifier("D2. code d'avant le lot rejoue sous concurrence", False, "git: %s" % e)
        return
    arbre_av = ast.parse(avant)
    lignes_av = avant.splitlines(True)
    src_av = None
    for n in ast.walk(arbre_av):
        if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == "cron_reservation_reminders"):
            src_av = "".join(lignes_av[n.lineno - 1:n.end_lineno])
    if not src_av:
        verifier("D2. code d'avant le lot rejoue sous concurrence", False, "handler introuvable")
        return
    b, base = bac([resa()])
    # on ecrase le handler par celui d'avant, dans le MEME bac
    b["n1b_deja_envoye"] = None
    for nom in ("n1b_deja_envoye", "n1b_marquer_envoye"):
        for x in ast.walk(arbre_av):
            if (isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == nom):
                exec(compile("".join(lignes_av[x.lineno - 1:x.end_lineno]), "<av>", "exec"), b)
    b["_v286_should_send_notification"] = lambda *a, **k: asyncio.sleep(0, result=True)
    exec(compile(src_av, "<av>", "exec"), b)
    PUSHS[:] = []
    await asyncio.gather(*[b["cron_reservation_reminders"]() for _ in range(10)])
    verifier("D2. SANS reservation prealable, le harnais voit BIEN des doublons",
             len(PUSHS) > 1,
             "%d push — le harnais n'entrelace pas, le test 9 ne prouve rien" % len(PUSHS))


# ============================================================================
#                        INVARIANTS DE STRUCTURE (sur le SOURCE)
# ============================================================================
def _src_a(rev, nom):
    """La source d'une fonction TELLE QU'ELLE ETAIT a une revision donnee.

    BORNEE AUX DEUX BOUTS, comme la garde de perimetre plus bas. Comparer
    `BASE_AVANT` a l'ARBRE DE TRAVAIL revenait a geler ces fonctions pour
    l'eternite : chaque lot ulterieur echouait sur du code qui ne concerne pas
    RV2. Le pied de page de `_email_wrapper` — un lien mort vers l'ancien
    domaine Vercel — a ete corrige APRES ce lot, et c'est cette garde-la, pas
    le correctif, qui etait fautive. Ce qu'elle doit prouver, et ce qu'elle
    prouve toujours : LE LOT RV2 n'a pas touche a ces fonctions.
    """
    src = subprocess.check_output(
        ["git", "show", "%s:api/server.py" % rev], cwd=RACINE).decode(errors="replace")
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    return None


def structure():
    nu_reserver = code_nu("rv2_reserver_canal")
    verifier("S1. la reservation est un compare-and-swap ($exists puis matched_count)",
             "$exists" in nu_reserver and "matched_count" in nu_reserver
             and "update_one" in nu_reserver, nu_reserver[:120])

    nu_cron = code_nu("cron_reservation_reminders")
    _i_res = nu_cron.find("rv2_reserver_canal")
    _i_push = nu_cron.find("send_push_by_email")
    _i_mail = nu_cron.find("rv2_envoyer_email_rappel")
    verifier("S2. le marquage precede les DEUX envois dans le code execute",
             0 < _i_res < _i_push and _i_res < _i_mail,
             "reserver@%d push@%d mail@%d" % (_i_res, _i_push, _i_mail))

    verifier("S3. l'echec libere le marqueur ($unset)",
             "$unset" in code_nu("rv2_liberer_canal"))
    verifier("S3b. et le cron appelle bien cette liberation",
             "rv2_liberer_canal" in nu_cron)

    nu_contenu = code_nu("rv2_contenu_rappel")
    verifier("S4. le contenu de l'e-mail n'a AUCUN acces a `datetime`",
             "datetime" not in nu_contenu, nu_contenu[:160])
    verifier("S4b. il ne connait que l'heure qu'on lui passe",
             "courseTime" not in nu_contenu)

    verifier("S5. le cron ne touche a AUCUN canal WhatsApp",
             not any(m in nu_cron.lower()
                     for m in ("whatsapp", "send_whatsapp", "meta_", "wa_")), "")

    nu_envoi = code_nu("rv2_envoyer_email_rappel")
    verifier("S6. l'e-mail porte Reply-To, HTML et texte",
             "reply_to" in nu_envoi and "'html'" in nu_envoi.replace('"', "'")
             and "'text'" in nu_envoi.replace('"', "'"), nu_envoi[:200])
    verifier("S6b. il reutilise le transport existant, sans nouveau moteur",
             "resend.Emails.send" in nu_envoi and "asyncio.to_thread" in nu_envoi)
    verifier("S6c. sans cle Resend, il ne tente rien",
             "RESEND_API_KEY" in nu_envoi and "RESEND_AVAILABLE" in nu_envoi)

    verifier("S7. le gabarit HTML existant est reutilise, pas reecrit",
             "_email_wrapper" in nu_contenu)

    # --- non-regression, bornee au COMMIT et jamais a l'arbre de travail ---
    intouchables = ["send_push_by_email", "n1b_deja_envoye", "n1b_marquer_envoye",
                    "n1b2_cle", "n1b2_cible", "n1b2_titre", "n1b2_corps",
                    "n1b3b2_plan", "n1b2_regles_du_coach", "n1b2_valider_regles",
                    "_v286_should_send_notification", "_email_wrapper",
                    "_v259_primary_color", "_v259_primary_rgb"]
    _ecarts = []
    for f in intouchables:
        if _src_a(BASE_AVANT, f) != _src_a(LOT, f):
            _ecarts.append(f)
    verifier("S8. le lot RV2 (%s..%s) n'a touche a aucune fonction hors perimetre"
             % (BASE_AVANT, LOT),
             not _ecarts, "modifiees : %s" % _ecarts)

    # --- perimetre des fichiers, borne AUX DEUX BOUTS ----------------------
    # `git diff BASE` sans borne haute compare a l'arbre de travail : la garde
    # s'elargit alors a chaque lot suivant et finit par echouer sur du code qui
    # ne la concerne pas. C'est precisement le defaut releve sur la garde de
    # V446 — inutile de le reproduire ici. On borne donc a la plage du lot.
    _modifs = subprocess.check_output(
        ["git", "diff", "--name-only", "%s..%s" % (BASE_AVANT, LOT)],
        cwd=RACINE).decode().split()
    _attendus = {
        "api/server.py",
        "frontend/src/components/ChatWidget.js",
        "frontend/src/components/coach/ReminderRulesCard.js",
        "frontend/src/components/coach/__tests__/ReminderRulesCard.test.js",
        "tests/test_rv2_rappels_push_email.py",
        "frontend/src/components/CoachDashboard.js",
        "frontend/src/components/coach/reminderMoments.js",
        "frontend/src/components/coach/CourseRemindersCard.js",
        "frontend/src/components/coach/__tests__/CourseRemindersCard.test.js",
    }
    verifier("S9. aucun fichier hors perimetre n'est touche",
             set(_modifs) <= _attendus, "inattendus : %s" % sorted(set(_modifs) - _attendus))

    # --- le lecteur de preferences ne doit rien ecrire ---------------------
    nu_pref = code_nu("rv2_canal_autorise")
    verifier("S10. la lecture des preferences n'ecrit JAMAIS en base",
             not any(m in nu_pref for m in ("update_one", "insert_one", "$set", "upsert")),
             nu_pref[:160])
    verifier("S10b. elle applique bien les trois echelons de repli",
             "before_class_%s" in nu_pref and "'before_class'" in nu_pref.replace('"', "'"))

    # --- ce test est-il vraiment hors ligne ? ------------------------------
    # On inspecte les IMPORTS REELS par AST : une recherche de texte se
    # trouverait elle-meme dans sa propre liste de mots interdits.
    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S11. ce test n'importe que la bibliotheque standard hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "re", "subprocess", "sys",
                      "datetime", "zoneinfo", "copy"}, str(sorted(mods)))
    verifier("S11b. ni resend, ni pywebpush, ni pymongo, ni client HTTP",
             not (mods & {"resend", "pywebpush", "pymongo", "requests",
                          "httpx", "socket", "urllib"}), str(sorted(mods)))


def main():
    structure()
    boucle = asyncio.new_event_loop()
    try:
        boucle.run_until_complete(discriminants())
        boucle.run_until_complete(scenarios())
        boucle.run_until_complete(scenarios_niveau1())
        boucle.run_until_complete(scenarios_route())
        boucle.run_until_complete(scenarios_flexibilite())
    finally:
        boucle.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Push REELLEMENT envoyes   : 0 — `pywebpush` n'est jamais importe")
    print("E-mails REELLEMENT envoyes: 0 — `resend` n'est jamais importe")
    print("WhatsApp                  : 0 — aucun module de messagerie n'est charge")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

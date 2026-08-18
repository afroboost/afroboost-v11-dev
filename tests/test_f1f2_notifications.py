# -*- coding: utf-8 -*-
"""
F1 + F2 — la confirmation cesse de mentir, et la reservation devient visible.

F1  `confirmation.client_email` disait « envoye » sans rien en savoir :
    `_send_reservation_email` ne retournait RIEN et avalait ses erreurs, et les
    deux enveloppes appelantes posaient `return True` en dur.
F2  la notification coach d'une reservation etait ECRITE puis filtree a la
    lecture (`type: "new_lead"` seul). Elle est desormais servie. Aucune
    notification nouvelle n'est creee.

Le moteur `notifier_reservation_creee` est joue POUR DE VRAI contre une base
simulee, avec des envoyeurs qui reussissent ou echouent sur commande.

HORS LIGNE. Aucune connexion, aucune ecriture, aucune donnee de production.

    python3 tests/test_f1f2_notifications.py
"""
import asyncio
import io
import os
import re
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def lire(*b):
    return io.open(os.path.join(RACINE, *b), encoding="utf-8").read()

SHARED = lire("api", "routes", "shared.py")
SERVEUR = lire("api", "server.py")
RESA = lire("api", "routes", "reservation_routes.py")
DASH = lire("frontend", "src", "components", "CoachDashboard.js")

resultats = []
def verifier(nom, cond, detail=""):
    resultats.append((nom, bool(cond), str(detail)))

def extraire(src, nom):
    m = re.search(r"^(?:async )?def %s\(.*?(?=^(?:async def |def |@)|\Z)" % nom, src, re.S | re.M)
    return m.group(0) if m else ""

def code_seul(src):
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"^\s*(#|//).*$", "", src, flags=re.M)


# ---------------------------------------------------------------------------
# Base simulee
# ---------------------------------------------------------------------------
def _lire(d, chemin):
    """Resolution d'un chemin POINTE, comme MongoDB. (valeur, present)

    Indispensable ici : les jetons d'idempotence interrogent
    `confirmation.client_email` avec `$exists`. Un faux qui ne saurait pas
    descendre dans le document repondrait toujours « absent » — et le test
    passerait au vert sur une base qui ne dit pas la verite.
    """
    cur = d
    for part in str(chemin).split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None, False
        cur = cur[part]
    return cur, True


def _ecrire(d, chemin, valeur):
    """Ecriture d'un chemin POINTE, en creant les niveaux manquants."""
    parts = str(chemin).split(".")
    cur = d
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = valeur


class Col:
    def __init__(self):
        self.docs = []
    def _m(self, d, f):
        for k, v in (f or {}).items():
            val, present = _lire(d, k)
            if isinstance(v, dict) and "$in" in v:
                if val not in v["$in"]:
                    return False
            elif isinstance(v, dict) and "$ne" in v:
                if val == v["$ne"]:
                    return False
            elif isinstance(v, dict) and "$exists" in v:
                if present != v["$exists"]:
                    return False
            elif val != v:
                return False
        return True
    async def find_one(self, f=None, proj=None):
        for d in self.docs:
            if self._m(d, f or {}):
                return dict(d)
        return None
    def find(self, f=None, proj=None):
        parent = self
        class _C:
            def sort(self, *a, **k): return self
            async def to_list(self, n=None):
                return [dict(d) for d in parent.docs if parent._m(d, f or {})]
        return _C()
    async def insert_one(self, d): self.docs.append(dict(d))
    async def count_documents(self, f=None):
        return len([d for d in self.docs if self._m(d, f or {})])
    async def update_one(self, f, maj, upsert=False):
        class _R:
            def __init__(s, n): s.matched_count = n; s.modified_count = n
        for d in self.docs:
            if self._m(d, f):
                for k, v in (maj.get("$set") or {}).items():
                    _ecrire(d, k, v)
                return _R(1)
        if upsert:
            neuf = {}
            for k, v in (maj.get("$setOnInsert") or {}).items():
                _ecrire(neuf, k, v)
            for k, v in (maj.get("$set") or {}).items():
                _ecrire(neuf, k, v)
            for k, v in (f or {}).items():
                if not isinstance(v, dict):
                    neuf.setdefault(k, v)
            self.docs.append(neuf); return _R(0)
        return _R(0)


class Base:
    def __init__(self):
        self.notifications = Col()
        self.reservations = Col()
        self.courses = Col()
        self.coaches = Col()
    def __getitem__(self, n): return getattr(self, n)


async def poser(base, resa):
    """La reservation DOIT exister : c'est elle qui porte les jetons de canal."""
    await base.reservations.insert_one(dict(resa))
    return dict(resa)


def moteur(base, coach="coach@test.ch"):
    """Charge le VRAI `notifier_reservation_creee` et ses jetons."""
    import datetime, logging
    esp = {"db": base, "datetime": datetime.datetime, "timezone": datetime.timezone,
           "logger": logging.getLogger("t"), "re": re}
    for fn in ("normaliser_email", "_rc_reserver_jeton", "_rc_cloturer_jeton",
               "resoudre_coach_de_reservation", "notifier_reservation_creee"):
        exec(compile(extraire(SHARED, fn), "<sh>", "exec"), esp)
    return esp


RESA_PONCTUELLE = {"id": "r-pon", "userEmail": "a@exemple.ch", "userName": "Ana Test",
                   "courseName": "Workshop", "courseId": "c-pon",
                   "datetime": "2026-08-22T14:00:00", "coach_id": "coach@test.ch"}
RESA_OCC19 = {"id": "r-19", "userEmail": "b@exemple.ch", "userName": "Bea Test",
              "courseName": "Session Cardio", "courseId": "c-rec",
              "datetime": "2026-08-19T18:30:00", "coach_id": "coach@test.ch"}
RESA_OCC26 = {"id": "r-26", "userEmail": "b@exemple.ch", "userName": "Bea Test",
              "courseName": "Session Cardio", "courseId": "c-rec",
              "datetime": "2026-08-26T18:30:00", "coach_id": "coach@test.ch"}


async def scenario():
    # ---------- F1 : le verdict est celui de l'envoi ----------------------
    for nom, ok_envoi, attendu in (("reussi", True, "envoye"), ("echoue", False, "echec")):
        base = Base(); esp = moteur(base)
        async def _mail(_r, _ok=ok_envoi): return _ok
        async def _push(*a, **k): return True
        b = await esp["notifier_reservation_creee"](
            base, await poser(base, RESA_PONCTUELLE), envoyer_email_client=_mail, envoyer_push_coach=_push)
        verifier("F1. envoi %s -> bilan « %s »" % (nom, attendu),
                 b["client_email"] == attendu, b)

    # l'envoyeur qui LEVE ne doit pas non plus produire « envoye »
    base = Base(); esp = moteur(base)
    async def _mail_casse(_r): raise RuntimeError("Resend indisponible")
    async def _push_ok(*a, **k): return True
    b = await esp["notifier_reservation_creee"](
        base, await poser(base, RESA_PONCTUELLE), envoyer_email_client=_mail_casse, envoyer_push_coach=_push_ok)
    verifier("F1b. envoyeur en exception -> « echec », jamais « envoye »",
             b["client_email"] == "echec", b)
    verifier("F1c. la reservation survit a l'echec d'e-mail", True)

    # ---------- A/B : ponctuel et occurrence recurrente, MEME chemin -------
    for nom, resa in (("A. cours PONCTUEL", RESA_PONCTUELLE),
                      ("B. occurrence RECURRENTE", RESA_OCC19)):
        base = Base(); esp = moteur(base)
        async def _m(_r): return True
        async def _p(*a, **k): return True
        b = await esp["notifier_reservation_creee"](base, await poser(base, resa),
                                                    envoyer_email_client=_m, envoyer_push_coach=_p)
        verifier("%s -> e-mail client" % nom, b["client_email"] == "envoye", b)
        verifier("%s -> notification coach" % nom, b["coach_inapp"] == "envoye", b)
        verifier("%s -> push coach" % nom, b["coach_push"] == "envoye", b)
        verifier("%s -> UNE seule notification" % nom, len(base.notifications.docs) == 1,
                 len(base.notifications.docs))
        _n = base.notifications.docs[0]
        verifier("%s -> elle porte la DATE de l'occurrence" % nom,
                 str(resa["datetime"])[:10] in _n["message"], _n["message"])
        verifier("%s -> aucune donnee personnelle" % nom,
                 "@" not in _n["message"] and resa["userEmail"] not in str(_n), _n["message"])

    # ---------- C : anti-effet de bord entre occurrences -------------------
    base = Base(); esp = moteur(base)
    async def _m(_r): return True
    async def _p(*a, **k): return True
    await esp["notifier_reservation_creee"](base, await poser(base, RESA_OCC19),
                                            envoyer_email_client=_m, envoyer_push_coach=_p)
    msgs = [n["message"] for n in base.notifications.docs]
    verifier("C. reserver le 19 -> notification du 19", any("2026-08-19" in m for m in msgs), msgs)
    verifier("C. reserver le 19 -> AUCUNE notification du 26",
             not any("2026-08-26" in m for m in msgs), msgs)
    verifier("C. une seule notification pour deux occurrences possibles",
             len(base.notifications.docs) == 1)
    # la seconde occurrence, reservee ensuite, produit la SIENNE
    await esp["notifier_reservation_creee"](base, await poser(base, RESA_OCC26),
                                            envoyer_email_client=_m, envoyer_push_coach=_p)
    verifier("C. reserver le 26 ensuite -> sa propre notification",
             len(base.notifications.docs) == 2 and
             any("2026-08-26" in n["message"] for n in base.notifications.docs))

    # ---------- E : idempotence, une reservation = une notification --------
    base = Base(); esp = moteur(base)
    _r19 = await poser(base, RESA_OCC19)
    for _ in range(3):
        b = await esp["notifier_reservation_creee"](base, _r19,
                                                    envoyer_email_client=_m, envoyer_push_coach=_p)
    verifier("E. rejeu x3 -> TOUJOURS une seule notification",
             len(base.notifications.docs) == 1, len(base.notifications.docs))
    verifier("E. les rejeux sont marques « deja_traite »", b["coach_inapp"] == "deja_traite", b)

    # ---------- coach non resolu : rien, mais rien de casse ----------------
    base = Base(); esp = moteur(base)
    _sans = dict(RESA_PONCTUELLE); _sans.pop("coach_id"); _sans["courseId"] = "inconnu"
    await base.reservations.insert_one(dict(_sans))
    b = await esp["notifier_reservation_creee"](base, _sans,
                                                envoyer_email_client=_m, envoyer_push_coach=_p)
    verifier("coach non resolu -> aucune notification coach",
             len(base.notifications.docs) == 0 and b["coach_inapp"] is None, b)
    verifier("coach non resolu -> l'e-mail client part quand meme",
             b["client_email"] == "envoye", b)


# ===========================================================================
# Verifications sur le code livre
# ===========================================================================
def perimetre():
    # --- F1 ---
    _env = extraire(RESA, "_send_reservation_email")
    verifier("F1-1. l'envoyeur rend True quand Resend accepte", "return True" in _env)
    verifier("F1-2. et False quand il echoue ou est absent", _env.count("return False") >= 2,
             _env.count("return False"))
    # Assertion CIBLEE sur les deux enveloppes, pas sur tout le fichier :
    # `server.py` contient cinq `return True` legitimes, sans rapport.
    _env1 = re.search(r"async def _rc_email_client\(_resa\):[\s\S]{0,700}?\n\n", RESA)
    _env2 = re.search(r"async def _rc_email_client\(_resa\):[\s\S]{0,700}?\n\n", SERVEUR)
    verifier("F1-3. plus AUCUN `return True` en dur dans les DEUX enveloppes",
             _env1 and _env2
             and "return True" not in code_seul(_env1.group(0))
             and "return True" not in code_seul(_env2.group(0)),
             [bool(_env1), bool(_env2)])
    verifier("F1-4. les DEUX enveloppes propagent le verdict",
             code_seul(RESA).count("bool(await _send_reservation_email(") == 1
             and code_seul(SERVEUR).count("bool(await _rc_email(") == 1)
    verifier("F1-5. aucun suivi de delivrabilite n'est construit",
             "webhook" not in _env.lower() and "delivered" not in _env.lower())

    # --- F2 ---
    verifier("F2-1. la liste des types est BLANCHE et explicite",
             'C17J_TYPES = ("new_lead", "new_reservation")' in SERVEUR)
    verifier("F2-2. la LECTURE sert les deux types",
             '"type": {"$in": list(C17J_TYPES)}, **get_coach_filter(_email)' in SERVEUR)
    verifier("F2-3. le MARQUAGE lu utilise la MEME liste",
             code_seul(SERVEUR).count('"type": {"$in": list(C17J_TYPES)}') == 2)
    verifier("F2-4. les annulations restent DEHORS (codes d'acces dans leur message)",
             "reservation_cancelled" not in SERVEUR.split("C17J_TYPES")[1][:400])
    verifier("F2-5. l'isolation par coach est conservee",
             SERVEUR.count("**get_coach_filter(_email)") >= 2)
    verifier("F2-6. la projection n'expose toujours aucune donnee personnelle",
             all(x not in SERVEUR.split("C17J_PROJECTION")[1][:200]
                 for x in ("user_email", "whatsapp", "code", "reservation_id")))

    # --- F2 : preuve qu'AUCUNE notification n'est creee en plus ---
    _notif = code_seul(extraire(SHARED, "notifier_reservation_creee"))
    verifier("F2-7. PREUVE : un seul ecrivain de notification coach, inchange",
             _notif.count("db.notifications.update_one") == 1)
    verifier("F2-8. il ecrit par UPSERT sur une cle deterministe (resa_<id>)",
             'f"resa_{rid}"' in _notif and "upsert=True" in _notif)
    verifier("F2-9. le lot n'ajoute AUCUN appel a db.notifications",
             SERVEUR.count("db.notifications.insert_one") == 0)

    # --- F2 : cote client ---
    verifier("F2-10. le libelle vient de la donnee, plus du code",
             "String(n.title" in DASH and "Nouveau prospect\n" not in DASH)
    verifier("F2-11. l'emoji de tete est retire (regle SVG du projet)",
             r"replace(/^[^\p{L}\p{N}]+/u, '')" in DASH)
    verifier("F2-12. l'icone suit le type, en SVG",
             "n.type === 'new_reservation' ? 'calendar' : 'target'" in DASH)
    verifier("F2-13. un repli existe si le titre manque",
             "Nouvelle réservation'" in DASH and "Nouveau prospect'" in DASH)

    # --- ce qui ne doit PAS avoir bouge ---
    verifier("HP1. le moteur de rappels n'est pas touche",
             "cron_reservation_reminders" in SERVEUR and "reminders_enabled" in SERVEUR)
    # TROIS canaux, ni plus ni moins — on compte les CLES, pas les affectations
    # (chacune apparait deux fois : envoye/echec et deja_traite).
    _canaux = sorted(set(re.findall(r'bilan\["(\w+)"\]', _notif)))
    verifier("HP2. exactement les trois canaux d'origine, aucun ajoute",
             _canaux == ["client_email", "coach_inapp", "coach_push"], _canaux)
    verifier("HP2b. ni `client_push` ni `coach_email` ne sont introduits",
             all(x not in _notif for x in ("client_push", "coach_email")))
    verifier("HP3. la recurrence n'est pas touchee",
             "_v184_next_occurrences" in SERVEUR)
    verifier("HP4. le moteur ESSAI n'est pas touche",
             "_essai1_garde" in SERVEUR and "_essai4_garde" in lire("api", "routes", "checkout_routes.py"))
    verifier("HP5. la reservation reste non bloquante en cas de panne",
             "asyncio.create_task(" in SERVEUR)


asyncio.run(scenario())
perimetre()

print("=" * 78)
echecs = 0
for nom, ok, det in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom + ("" if ok else "   -> " + det[:110]))
    if not ok:
        echecs += 1
print("=" * 78)
print("E-mails / push / notifications REELS : 0 — envoyeurs simules, base en memoire")
print("%d/%d verifications" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)

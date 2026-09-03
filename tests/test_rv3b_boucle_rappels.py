# -*- coding: utf-8 -*-
"""RV3-B — LE MOTEUR DE RAPPELS AVAIT UNE HORLOGE, ET ELLE NE TOURNAIT PLUS.

POURQUOI CE BANC EXISTE
==============================================================================
Le moteur de rappels avant cours est complet, testé et correct — et il n'était
appelé par PERSONNE. Son unique déclencheur vivait dans `vercel.json`, or le
site tourne sur Coolify : ces crons ne s'exécutent jamais. Mesure du 03/09/2026
sur la base réelle : 0 réservation sur 152 porte `reminders_sent`.

CE QUE CE FICHIER PROUVE
==============================================================================
  * la boucle appelle LE moteur existant — elle n'en recopie aucune règle ;
  * elle est enregistrée au démarrage, comme les cinq autres boucles ;
  * sa période recouvre EXACTEMENT la fenêtre du moteur ;
  * un rappel de la veille part à l'heure, un rappel du jour même aussi ;
  * Europe/Zurich est respecté en été COMME en hiver ;
  * un rappel dont l'heure est passée n'est JAMAIS rattrapé ;
  * plusieurs passages ne produisent jamais deux fois le même rappel ;
  * un participant sans push reçoit quand même son e-mail ;
  * un participant sans e-mail ne casse rien ;
  * des préférences fermées ferment le canal ;
  * une panne Resend ou Push n'arrête ni le passage ni la boucle ;
  * un redémarrage ne rejoue rien.

L'HORLOGE EST GELÉE pour les scénarios horaires : sans cela, « rappel du jour
même à 07:00 » ne serait testable qu'entre 06:30 et 07:30, une fois par jour.

Aucun réseau. Aucun e-mail. Aucun push. Aucune base réelle.
    python3 tests/test_rv3b_boucle_rappels.py
"""
import asyncio
import io
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import test_rv2_rappels_push_email as H   # noqa: E402  (harnais partagé)

try:
    from zoneinfo import ZoneInfo
    ZURICH = ZoneInfo("Europe/Zurich")
except Exception:                                        # pragma: no cover
    print("zoneinfo indisponible — banc impossible")
    sys.exit(1)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))
    print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond:
        print("           -> %s" % detail)


# ─────────────────────────── l'horloge gelée ────────────────────────────────
class Horloge(datetime):
    """Un `datetime` dont `now()` rend l'instant qu'on lui a posé.

    Sous-classe volontaire : `fromisoformat`, la comparaison et l'arithmétique
    du moteur continuent de fonctionner exactement comme en production. Seule
    la lecture de l'heure est détournée.
    """
    _instant = None

    @classmethod
    def poser(cls, instant):
        cls._instant = instant

    @classmethod
    def now(cls, tz=None):
        return cls._instant.astimezone(tz) if tz else cls._instant


REGLE_VEILLE = {"type": "relative", "minutes": 1440}
REGLE_MATIN = {"type": "same_day", "heure": 7, "minute": 0}
REGLES = [REGLE_VEILLE, REGLE_MATIN]
CODE = "AFR-2287CA"


def zurich(annee, mois, jour, heure, minute=0):
    return datetime(annee, mois, jour, heure, minute, tzinfo=ZURICH)


def cours_mercredi(regles=None):
    return H.cours(cid="c1", actif=True, regles=regles if regles is not None else REGLES,
                   locationName="Bord du Lac, Auvernier")


async def passage(resas, maintenant, cours_docs=None, **kw):
    """UN passage du VRAI moteur, à l'instant demandé. Aucune écriture réelle."""
    b, base = H.bac(resas, cours_docs=cours_docs or [cours_mercredi()],
                    codes=[{"code": CODE}], **kw)
    b["datetime"] = Horloge
    Horloge.poser(maintenant)
    resultat = await b["cron_reservation_reminders"]()
    return b, base, resultat


def resa_pour(instant_cours, **extra):
    d = H.resa(instant=instant_cours, **extra)
    d["promoCode"] = CODE
    return d


def envois(base, rid="r1"):
    doc = [d for d in base.reservations.docs if d.get("id") == rid]
    return (doc[0].get("reminders_sent") or {}) if doc else {}


# ============================================================================
print("\n1. LA BOUCLE APPELLE LE MOTEUR — ET NE DÉCIDE RIEN")

BLOC = SRC[SRC.index("# RV3-B — LE MOTEUR DE RAPPELS AVAIT UNE HORLOGE"):
           SRC.index("async def send_backup_email")]
CORPS = SRC[SRC.index("async def _rv3b_boucle_rappels"):
            SRC.index("async def send_backup_email")]
CODE_NU = "\n".join(l for l in CORPS.splitlines() if not l.strip().startswith("#"))

verifier("1a. la boucle appelle le moteur EXISTANT",
         "await cron_reservation_reminders()" in CODE_NU)
verifier("1b. AUCUN second moteur : pas une seule règle de sélection",
         not any(m in CODE_NU for m in ("reminders_enabled", "reminder_rules",
                                        "n1b2_", "n1b3b2_", "rv2_deja_envoye",
                                        "reservations.find", "db.reservations",
                                        "Emails.send", "send_push_by_email")),
         "la boucle ne doit être qu'un réveil")
verifier("1c. elle ne lit ni n'écrit la base", "db" not in CODE_NU.replace("db_", ""))
verifier("1d. elle ne peut pas mourir sur un incident",
         "except Exception" in CODE_NU and "while True:" in CODE_NU)
verifier("1e. elle est enregistrée au démarrage",
         "asyncio.create_task(_rv3b_boucle_rappels())" in SRC)
def _periode():
    return int(SRC.split("RV3B_PERIODE_S = ")[1].split()[0])


def _demi():
    return int(SRC.split("N1B2_DEMI_FENETRE_MIN = ")[1].split()[0])


verifier("1f. la période (%d s) recouvre exactement la fenêtre du moteur (2 × %d min)"
         % (_periode(), _demi()),
         _periode() == 2 * _demi() * 60, "%d != %d" % (_periode(), 2 * _demi() * 60))
verifier("1g. la boucle laisse l'application démarrer avant son premier passage",
         "RV3B_DEMARRAGE_S" in CODE_NU)


# ============================================================================
print("\n2. LA BOUCLE TOURNE, ET RIEN NE L'ARRÊTE")


async def boucle_scenario(issues):
    """Rejoue la VRAIE boucle, avec un moteur bouchon et un sommeil instantané."""
    appels = []

    async def faux_moteur():
        i = len(appels)
        appels.append(True)
        if i < len(issues) and isinstance(issues[i], Exception):
            raise issues[i]
        return issues[i] if i < len(issues) else {"checked": 0, "sent": 0}

    class Arret(Exception):
        pass

    async def faux_sleep(_s):
        if len(appels) >= len(issues):
            raise Arret()

    espace = {"asyncio": type("a", (), {"sleep": staticmethod(faux_sleep)}),
              "cron_reservation_reminders": faux_moteur,
              "logger": type("l", (), {k: staticmethod(lambda *a, **kw: None)
                                       for k in ("info", "warning", "error")}),
              "RV3B_PREFIXE": "[RV3-B]", "RV3B_PERIODE_S": 3600,
              "RV3B_DEMARRAGE_S": 90, "Exception": Exception}
    exec(compile(CORPS[:CORPS.index("async def send_backup_email")]
                 if "async def send_backup_email" in CORPS else CORPS,
                 "<rv3b>", "exec"), espace)
    try:
        await espace["_rv3b_boucle_rappels"]()
    except Arret:
        pass
    return appels


_a = asyncio.get_event_loop().run_until_complete(boucle_scenario(
    [{"checked": 1, "sent": 1}, {"checked": 0, "sent": 0}, {"checked": 2, "sent": 2}]))
verifier("2a. plusieurs passages ont bien lieu", len(_a) == 3, str(len(_a)))

_b = asyncio.get_event_loop().run_until_complete(boucle_scenario(
    [RuntimeError("Mongo injoignable"), {"checked": 0, "sent": 0}]))
verifier("2b. une panne du moteur n'arrête pas la boucle", len(_b) == 2, str(len(_b)))


# ============================================================================
print("\n3. LE RAPPEL DE LA VEILLE")

COURS = zurich(2026, 9, 9, 18, 30)          # mercredi 09/09, 18:30 (heure d'été)
CIBLE_VEILLE = COURS - timedelta(minutes=1440)   # mardi 08/09 18:30
CIBLE_MATIN = zurich(2026, 9, 9, 7, 0)           # mercredi 09/09 07:00

_, base, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE))
verifier("3a. le rappel de la veille part à son heure", r["sent"] >= 1, str(r))
verifier("3b. il est tracé sous SA propre clé, distincte de celle du matin",
         len(envois(base)) == 1 and "same_day" not in " ".join(envois(base)),
         str(envois(base)))
verifier("3c. l'e-mail est bien parti", len(H.EMAILS) == 1, str(len(H.EMAILS)))

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE - timedelta(minutes=45)))
verifier("3d. 45 min trop tôt : rien ne part", r["sent"] == 0, str(r))


# ============================================================================
print("\n4. LE RAPPEL DU JOUR MÊME À 07:00")

_, base_matin, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_MATIN))
verifier("4a. le rappel de 07:00 part à son heure", r["sent"] >= 1, str(r))
verifier("4a2. sa clé est celle du jour même, pas celle de la veille",
         "same_day" in " ".join(envois(base_matin)), str(envois(base_matin)))
verifier("4b. l'heure du cours figure dans le message",
         "18:30" in (H.EMAILS[-1].get("html") or "") if H.EMAILS else False)

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], zurich(2026, 9, 9, 9, 0)))
verifier("4c. deux heures après 07:00, plus rien ne part", r["sent"] == 0, str(r))


# ============================================================================
print("\n5. EUROPE/ZURICH — ÉTÉ ET HIVER")

COURS_HIVER = zurich(2026, 1, 14, 18, 30)        # mercredi de janvier, UTC+1
CIBLE_HIVER = zurich(2026, 1, 14, 7, 0)
_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS_HIVER)], CIBLE_HIVER))
verifier("5a. en HIVER, 07:00 suisse déclenche bien", r["sent"] >= 1, str(r))
verifier("5b. l'heure suisse d'hiver vaut bien UTC+1",
         CIBLE_HIVER.utcoffset() == timedelta(hours=1))
verifier("5c. l'heure suisse d'été vaut bien UTC+2",
         CIBLE_MATIN.utcoffset() == timedelta(hours=2))

# La date naïve — 67 réservations du parc en portent une — doit être lue en
# heure suisse, jamais en UTC. Sinon le rappel se décale de deux heures.
_naive = resa_pour(COURS)
_naive["datetime"] = "2026-09-09T18:30:00"
_, _, r = asyncio.get_event_loop().run_until_complete(passage([_naive], CIBLE_VEILLE))
verifier("5d. une date naïve est lue en heure suisse", r["sent"] >= 1, str(r))


# ============================================================================
print("\n6. AUCUN RATTRAPAGE D'UN RAPPEL PÉRIMÉ")

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE + timedelta(hours=3)))
verifier("6a. 3 h après l'heure prévue, le rappel de la veille est PERDU",
         r["sent"] == 0, str(r))
_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_MATIN + timedelta(hours=6)))
verifier("6b. 6 h après 07:00, le rappel du matin est PERDU", r["sent"] == 0, str(r))
_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], COURS + timedelta(minutes=1)))
verifier("6c. un cours DÉJÀ COMMENCÉ ne déclenche plus rien", r["sent"] == 0, str(r))


# ============================================================================
print("\n7. IDEMPOTENCE — PLUSIEURS PASSAGES, UN SEUL RAPPEL")

b, base = H.bac([resa_pour(COURS)], cours_docs=[cours_mercredi()], codes=[{"code": CODE}])
b["datetime"] = Horloge
Horloge.poser(CIBLE_VEILLE)
r1 = asyncio.get_event_loop().run_until_complete(b["cron_reservation_reminders"]())
r2 = asyncio.get_event_loop().run_until_complete(b["cron_reservation_reminders"]())
Horloge.poser(CIBLE_VEILLE + timedelta(minutes=20))
r3 = asyncio.get_event_loop().run_until_complete(b["cron_reservation_reminders"]())
verifier("7a. le premier passage envoie", r1["sent"] >= 1, str(r1))
verifier("7b. le deuxième passage n'envoie rien", r2["sent"] == 0, str(r2))
verifier("7c. un troisième, encore dans la fenêtre, n'envoie rien non plus",
         r3["sent"] == 0, str(r3))
verifier("7d. un seul e-mail au total", len(H.EMAILS) == 1, str(len(H.EMAILS)))
verifier("7e. la trace d'envoi existe en base", bool(envois(base)), str(envois(base)))

# Redémarrage du conteneur : un bac NEUF, mais la même base — l'état vit en base.
b2, _ = H.bac([dict(d) for d in base.reservations.docs], cours_docs=[cours_mercredi()],
              codes=[{"code": CODE}])
b2["datetime"] = Horloge
Horloge.poser(CIBLE_VEILLE + timedelta(minutes=10))
r4 = asyncio.get_event_loop().run_until_complete(b2["cron_reservation_reminders"]())
verifier("7f. après un REDÉMARRAGE, rien n'est rejoué", r4["sent"] == 0, str(r4))


# ============================================================================
print("\n8. LES CAS PARTICIPANTS")

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE, push_ok=False))
verifier("8a. sans push, l'e-mail part quand même", r["email"] >= 1, str(r))
verifier("8b. et le push est bien compté à zéro", r["push"] == 0, str(r))

_sans_mail = resa_pour(COURS)
_sans_mail["userEmail"] = ""
_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([_sans_mail], CIBLE_VEILLE))
verifier("8c. sans adresse, aucun e-mail et aucune erreur", r["email"] == 0, str(r))

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE,
            prefs=[H.pref(email="abo@exemple.com", before_class=False)]))
verifier("8d. le refus historique `before_class` ferme les DEUX canaux",
         r["sent"] == 0, str(r))

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE,
            prefs=[H.pref(email="abo@exemple.com", before_class_email=False)]))
verifier("8d2. un refus par canal ne ferme que le sien",
         r["email"] == 0 and r["push"] >= 1, str(r))

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE, email_ok=False))
verifier("8e. panne Resend : le passage se termine sans planter", isinstance(r, dict), str(r))
verifier("8f. panne Resend : aucun e-mail compté comme parti", r["email"] == 0, str(r))

_, _, r = asyncio.get_event_loop().run_until_complete(
    passage([resa_pour(COURS)], CIBLE_VEILLE, push_ok=False, email_ok=False))
verifier("8g. les DEUX canaux en panne : le passage tient debout",
         isinstance(r, dict) and r["sent"] == 0, str(r))


# ============================================================================
print("\n9. CE QUE LE LOT N'A PAS TOUCHÉ")

verifier("9a. la garde `reminders_enabled` est intacte",
         "if _c.get(\"reminders_enabled\") is not True:" in SRC)
verifier("9b. la fenêtre du moteur est intacte",
         "if (_cible - _demi) < now <= (_cible + _demi):" in SRC)
verifier("9c. aucun drapeau d'envoi n'apparaît dans le lot",
         not any(d in BLOC for d in ("feature_flags", "get_feature_flags",
                                     "_ENABLED", "_ENVOI_REEL")))
verifier("9d. le lot ne touche ni l'auto-présence ni les relances",
         not any(d in BLOC for d in ("p1b_", "p1d_", "ap_traiter", "AUTO_PRESENCE")))
verifier("9e. aucune route n'est ajoutée", "@api_router" not in BLOC)
verifier("9f. un cours sans `reminders_enabled` reste muet",
         asyncio.get_event_loop().run_until_complete(
             passage([resa_pour(COURS)], CIBLE_VEILLE,
                     cours_docs=[H.cours(cid="c1", actif=None)]))[2]["sent"] == 0)


# ============================================================================
print("\n" + "=" * 78)
_ok = sum(1 for _, c, _ in RESULTATS if c)
print("RV3-B : %d / %d verifications" % (_ok, len(RESULTATS)))
print("E-mails reels : 0 — Push reels : 0 — Reseau : aucun")
print("=" * 78)
if _ok != len(RESULTATS):
    print("\nECHECS :")
    for nom, cond, detail in RESULTATS:
        if not cond:
            print("  - %s%s" % (nom, ("  [%s]" % detail) if detail else ""))
    sys.exit(1)

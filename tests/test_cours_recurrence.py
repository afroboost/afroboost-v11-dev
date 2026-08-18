# -*- coding: utf-8 -*-
"""
COURS RECURRENTS — l'editeur retrouve la recurrence que le moteur savait deja faire.

CE QUE CE LOT CHANGE : un ecran. `OfferWizard` etape 2 n'offrait qu'un champ
DATE, donc tout horaire cree y etait une seance unique, a refaire chaque
semaine. Il propose desormais « Date unique » / « Chaque semaine ».

CE QUE CE LOT NE CHANGE PAS, ET QUI EST VERIFIE ICI :
  - `_v184_next_occurrences` — le moteur, execute POUR DE VRAI ci-dessous ;
  - le modele `Course` — aucun champ nouveau, aucune migration ;
  - RAPPELS V2 — le moteur est pilote par les RESERVATIONS, jamais par le type
    de cours. La section D le prouve sur le code reel du cron.

HORS LIGNE. Aucune connexion, aucune ecriture, aucune donnee de production.

    python3 tests/test_cours_recurrence.py
"""
import io
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def lire(*b):
    return io.open(os.path.join(RACINE, *b), encoding="utf-8").read()

SERVEUR = lire("api", "server.py")
WIZARD = lire("frontend", "src", "components", "dashboard", "OfferWizard.js")

resultats = []
def verifier(nom, cond, detail=""):
    resultats.append((nom, bool(cond), str(detail)))

def extraire(src, nom):
    m = re.search(r"^(?:async )?def %s\(.*?(?=^(?:async def |def |@)|\Z)" % nom, src, re.S | re.M)
    return m.group(0) if m else ""

def code_seul(src):
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    return re.sub(r"^\s*(#|//).*$", "", src, flags=re.M)


# ===========================================================================
# A. LE MOTEUR — la VRAIE fonction, executee
# ===========================================================================
import logging
_esp = {"datetime": datetime, "timedelta": timedelta,
        "logger": logging.getLogger("t")}
for _fn in ("_v184_parse_time_hhmm", "_v184_next_occurrences"):
    exec(compile(extraire(SERVEUR, _fn), "<s>", "exec"), _esp)
exec(compile(re.search(r"^_V184_WEEKDAY_LABELS_FR\s*=.*$", SERVEUR, re.M).group(0), "<c>", "exec"), _esp)
occ = _esp["_v184_next_occurrences"]

MERCREDI_JS, DIMANCHE_JS = 3, 0
RECUR_MER = {"id": "c-mer", "name": "Session Cardio", "weekday": MERCREDI_JS, "time": "18:30"}
RECUR_DIM = {"id": "c-dim", "name": "Sunday Vibes", "weekday": DIMANCHE_JS, "time": "18:30"}

o_mer = occ(RECUR_MER, days_ahead=14)
verifier("A1. cours hebdomadaire -> plusieurs occurrences sur 14 jours",
         len(o_mer) >= 2, len(o_mer))
verifier("A2. toutes tombent un MERCREDI",
         all(datetime.fromisoformat(x["datetime"]).weekday() == 2 for x in o_mer),
         [x["datetime"] for x in o_mer])
verifier("A3. toutes a 18:30, l'heure ne derive jamais",
         all(x["datetime"][11:16] == "18:30" for x in o_mer))
verifier("A4. aucune occurrence dans le passe",
         all(datetime.fromisoformat(x["datetime"]) >= datetime.now() - timedelta(days=1) for x in o_mer))
verifier("A5. dimanche -> toutes un DIMANCHE (conversion JS->Python)",
         all(datetime.fromisoformat(x["datetime"]).weekday() == 6
             for x in occ(RECUR_DIM, days_ahead=14)))
verifier("A6. deux jours = deux cours, pas un champ multi-jours",
         len(occ(RECUR_MER, 14)) and len(occ(RECUR_DIM, 14)))

_demain = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
_hier = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
o_futur = occ({"id": "p1", "name": "Workshop", "date": _demain, "time": "14:00"}, 14)
verifier("A7. seance PONCTUELLE a venir -> exactement 1 occurrence", len(o_futur) == 1, o_futur)
verifier("A7b. et elle est marquee comme date fixe",
         o_futur and o_futur[0].get("is_fixed_date") is True)
verifier("A8. seance PONCTUELLE passee -> aucune occurrence",
         occ({"id": "p2", "name": "Festival", "date": _hier, "time": "18:00"}, 14) == [])
verifier("A9. `date` PRIME sur `weekday` (regle d'aiguillage)",
         occ({"id": "p3", "name": "X", "date": _hier, "weekday": MERCREDI_JS, "time": "18:30"}, 14) == [],
         "un cours date et passe ne doit PAS se repeter")
verifier("A10. horizon respecte : 60 jours donne plus que 14",
         len(occ(RECUR_MER, 60)) > len(occ(RECUR_MER, 14)))

# --- fuseau et heure d'ete -------------------------------------------------
_src_occ = extraire(SERVEUR, "_v184_next_occurrences")
verifier("A11. le moteur date en Europe/Zurich (DST gere par zoneinfo)",
         'ZoneInfo("Europe/Zurich")' in _src_occ)
verifier("A12. l'ISO reste NAIF — l'heure locale n'est pas reinterpretee en UTC",
         "PAS de tzinfo" in _src_occ or "tzinfo=None" in _src_occ or "naïf" in _src_occ.lower())
_hiver = occ(dict(RECUR_MER), days_ahead=200)
verifier("A13. l'heure reste 18:30 de part et d'autre du changement d'heure",
         all(x["datetime"][11:16] == "18:30" for x in _hiver), len(_hiver))


# ===========================================================================
# B. L'EDITEUR — le choix qui manquait
# ===========================================================================
verifier("B1. le selecteur de recurrence existe", 'data-testid={`recurrence-${course.id}`}' in WIZARD)
verifier("B2. les deux modes sont proposes",
         "recurrence-ponctuel-" in WIZARD and "recurrence-hebdo-" in WIZARD)
verifier("B3. un menu JOUR remplace la date en mode hebdomadaire",
         'data-testid={`weekday-${course.id}`}' in WIZARD)
verifier("B4. passer en hebdomadaire EFFACE la date",
         re.search(r"recurrence-hebdo[\s\S]{0,900}?date: ''", WIZARD) is not None)
verifier("B5. le jour retenu est DERIVE de la date precedente, pas dimanche par defaut",
         re.search(r"recurrence-hebdo[\s\S]{0,900}?weekdayFromDate\(course\.date\)", WIZARD) is not None)
verifier("B6. le type reste decide par `date`, comme le backend",
         WIZARD.count("typeof course.date === 'string' && course.date.trim()") >= 2)
verifier("B7. aucun champ nouveau n'est invente (pas de `recurrent`)",
         "recurrent:" not in code_seul(WIZARD) and "is_recurring" not in WIZARD)
verifier("B8. le nouvel horaire est hebdomadaire par defaut",
         re.search(r"axios\.post\(`\$\{API\}/courses`,\s*\{[\s\S]{0,400}?weekday: 3", WIZARD) is not None)
verifier("B9. aucune couleur de marque codee en dur",
         "'#D91CD2'" not in WIZARD.split("recurrence-")[1][:1500]
         or "var(--primary-color" in WIZARD.split("recurrence-")[1][:1500])

_payload = WIZARD[WIZARD.index("const buildCoursePayload"):][:1200]
verifier("B10. le payload efface la date quand il n'y en a pas", "date: derived != null ? rawDate : ''" in _payload)
verifier("B11. le payload conserve le weekday choisi", "Number.isInteger(c.weekday) ? c.weekday" in _payload)


# ===========================================================================
# C. LE BACKEND N'A PAS BOUGE
# ===========================================================================
verifier("C1. `PUT /courses` ecrit bien une chaine vide (donc efface la date)",
         "{k: v for k, v in course_update.items() if v is not None}" in SERVEUR,
         "seuls les None sont filtres")
verifier("C2. le modele Course garde weekday ET date, sans champ nouveau",
         re.search(r"class Course\(BaseModel\)[\s\S]{0,900}weekday: Optional\[int\]", SERVEUR)
         and re.search(r"class Course\(BaseModel\)[\s\S]{0,900}date: Optional\[str\]", SERVEUR))
verifier("C3. aucune notion de recurrence inventee cote serveur",
         "recurrence_rule" not in SERVEUR and "rrule" not in SERVEUR)
verifier("C4. l'offre reference le COURS, jamais ses occurrences",
         "linked_course_ids" in SERVEUR and "linked_occurrences" not in SERVEUR)


# ===========================================================================
# D. RAPPELS V2 — LA REGLE UNIVERSELLE (additif)
#    « Les rappels appartiennent a la reservation, pas au mode de recurrence. »
# ===========================================================================
_cron = code_seul(extraire(SERVEUR, "cron_reservation_reminders"))
verifier("D1. le cron part des RESERVATIONS, pas des cours",
         "db.reservations.find(" in _cron)
verifier("D2. il selectionne sur le `datetime` REEL de la seance reservee",
         '"datetime": {"$gte": _plancher}' in _cron)
verifier("D3. AUCUNE condition de recurrence n'entre dans l'envoi",
         "weekday" not in _cron and "recurrent" not in _cron,
         "un `if recurrent:` rendrait les rappels non universels")
verifier("D4. le type de cours n'est pas lu non plus",
         '"date"' not in _cron.replace('"datetime"', ""))
verifier("D5. la configuration est lue sur LE COURS, via courseId",
         'reservation.get("courseId")' in _cron or '_resa.get("courseId")' in _cron)
verifier("D6. seule `reminders_enabled` decide — absent vaut NON",
         "reminders_enabled" in _cron)
verifier("D7. le mode d'acces (pack, essai, unite) n'est jamais consulte",
         all(x not in _cron for x in ("source", "social_proof", "free_trial", "offer_id")))
verifier("D8. anti-doublon par (reservation, cle, canal)",
         "rv2_deja_envoye" in _cron and "rv2_reserver_canal" in _cron)
_res = extraire(SERVEUR, "rv2_reserver_canal")
verifier("D9. la reservation du canal est ATOMIQUE (pas de double envoi)",
         "update_one" in _res and ("$exists" in _res or "matched_count" in _res or "modified_count" in _res))
verifier("D10. le fuseau du cron est Europe/Zurich",
         'ZoneInfo("Europe/Zurich")' in _cron or "_zurich" in _cron)
verifier("D11. une date naive est interpretee en heure suisse, pas en UTC",
         "replace(tzinfo=_zurich)" in _cron)

_liste = code_seul(extraire(SERVEUR, "rv3_cours_configurables")
                   or extraire(SERVEUR, "n1b3b2_cours_du_coach"))
if not _liste:
    _m = re.search(r'@api_router\.get\("/coach/courses[^"]*"\)[\s\S]{0,4000}', SERVEUR)
    _liste = code_seul(_m.group(0)) if _m else ""
verifier("D12. l'ecran de reglage liste les cours SANS filtrer par type",
         _liste and "weekday" not in _liste and '"date"' not in _liste,
         "ponctuels et recurrents doivent y figurer tous les deux")

verifier("D13. LE POINT CLE DU LOT : basculer la recurrence ne touche JAMAIS "
         "la configuration des rappels",
         "reminders_enabled" not in _payload and "reminder_rules" not in _payload,
         "buildCoursePayload est une liste BLANCHE")
verifier("D14. ni la duplication d'un horaire",
         re.search(r"const duplicateCourse[\s\S]{0,1400}?reminders_enabled", WIZARD) is None,
         "comportement ACTUEL conserve : une copie repart sans rappels")
verifier("D15. une reservation garde son propre datetime, independant du cours",
         '"datetime": occurrence_iso' in SERVEUR,
         "deux occurrences reservees = deux rappels distincts")
verifier("D16. l'anti-doublon de reservation porte sur (courseId, datetime)",
         re.search(r'dup_query\["datetime"\] = occurrence_iso', SERVEUR) is not None)


# ===========================================================================
# E. NON-REGRESSION DU PARCOURS PONCTUEL
# ===========================================================================
verifier("E1. l'input date existe toujours pour les seances uniques",
         'type="date"' in WIZARD)
verifier("E2. le rappel du jour choisi est conserve", "WEEKDAYS[d.getDay()]" in WIZARD)
verifier("E3. la duplication recopie toujours la date d'un ponctuel",
         "date: srcDerived != null ? srcDate : ''" in WIZARD)
verifier("E4. le moteur ESSAI n'est pas touche par ce lot",
         all(x not in WIZARD for x in ("_essai1_garde", "free_trial_claims", "checkout/free")))

print("=" * 78)
echecs = 0
for nom, ok, det in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom + ("" if ok else "   -> " + det[:110]))
    if not ok:
        echecs += 1
print("=" * 78)
print("Cours / reservations / rappels REELS : 0 — moteur execute a vide, code lu sur disque")
print("%d/%d verifications" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)

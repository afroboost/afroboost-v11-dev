# -*- coding: utf-8 -*-
"""N1B-2 — tests hors ligne. Aucune base, aucun reseau.

Les fonctions testees sont EXTRAITES du vrai `api/server.py` (via AST), pas
recopiees : si le code change, le test suit.
"""
import ast, os, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "server.py")
A_EXTRAIRE = {"n1b2_cle", "n1b2_titre", "n1b2_corps", "n1b2_cible",
              "n1b2_valider_regles", "n1b_deja_envoye"}
CONSTANTES = {"N1B_CLE_HERITEE", "N1B2_MAX_REGLES", "N1B2_DELAIS_AUTORISES",
              "N1B2_REGLES_DEFAUT", "N1B2_DEMI_FENETRE_MIN", "N1B2_HORIZON_MIN",
              "N1B2_MINUTES_AUTORISEES"}

src = open(SRC, encoding="utf-8").read()
arbre = ast.parse(src)
morceaux = []
for n in arbre.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in A_EXTRAIRE:
        morceaux.append(ast.get_source_segment(src, n))
    elif isinstance(n, ast.Assign):
        for c in n.targets:
            if isinstance(c, ast.Name) and c.id in CONSTANTES:
                morceaux.append(ast.get_source_segment(src, n))
NS = {"datetime": datetime, "timezone": timezone, "timedelta": timedelta}
exec("\n\n".join(morceaux), NS)
assert len(A_EXTRAIRE) == sum(1 for f in A_EXTRAIRE if f in NS), "extraction incomplete"

ZH = ZoneInfo("Europe/Zurich")
DEMI = timedelta(minutes=NS["N1B2_DEMI_FENETRE_MIN"])
HORIZON = timedelta(minutes=NS["N1B2_HORIZON_MIN"])


def instant_du_cours(valeur):
    """Copie fidele de `_v435_instant_du_cours` (imbriquee, non extractible)."""
    if not isinstance(valeur, str) or not valeur.strip():
        return None
    try:
        dt = datetime.fromisoformat(valeur.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZH)
    return dt.astimezone(timezone.utc)


def passage_cron(now, resa, regles):
    """Ce que le cron retiendrait a cet instant : liste de cles a envoyer."""
    quand = instant_du_cours(resa.get("datetime"))
    if not quand or quand <= now or quand > now + HORIZON:
        return []
    retenues = []
    for regle in regles:
        cle = NS["n1b2_cle"](regle)
        if NS["n1b_deja_envoye"](resa, cle):
            continue
        cible = NS["n1b2_cible"](regle, quand, ZH)
        if cible and (cible - DEMI) < now <= (cible + DEMI):
            retenues.append(cle)
    return retenues


def passage_v435_historique(now, resa):
    """L'ANCIENNE logique, avant N1B-2 — reference de non-regression."""
    if NS["n1b_deja_envoye"](resa, NS["N1B_CLE_HERITEE"]):
        return []
    quand = instant_du_cours(resa.get("datetime"))
    if quand and now + timedelta(minutes=30) <= quand < now + timedelta(minutes=90):
        return [NS["N1B_CLE_HERITEE"]]
    return []


def marquer(resa, cle, quand):
    resa.setdefault("reminders_sent", {})[cle] = quand
    if cle == NS["N1B_CLE_HERITEE"]:
        resa["reminder_sent"] = True


def simuler(resa, regles, depart, nb_heures, echecs=(), passages_sup=(), pas_min=60):
    """Passages du cron toutes les `pas_min` minutes. `echecs` = index rates.

    `pas_min=60` reproduit l'ancienne cadence (tests historiques inchanges) ;
    `pas_min=30` reproduit la cadence REELLE depuis N1B-3A.
    """
    envois, tentative = [], 0
    instants = [depart + timedelta(minutes=i * pas_min)
                for i in range(int(nb_heures * 60 // pas_min))]
    instants = sorted(instants + list(passages_sup))
    for now in instants:
        for cle in passage_cron(now, resa, regles):
            tentative += 1
            if tentative in echecs:
                continue                      # echec : AUCUN marquage
            marquer(resa, cle, now.isoformat())
            envois.append((cle, now.astimezone(ZH).strftime("%a %d/%m %H:%M")))
    return envois


DEFAUT = list(NS["N1B2_REGLES_DEFAUT"])
R24 = {"type": "relative", "minutes": 1440}
R48 = {"type": "relative", "minutes": 2880}
R1 = {"type": "relative", "minutes": 60}
R3 = {"type": "relative", "minutes": 180}
# N1B-3B1 : forme NORMALISEE (`minute` explicite). Le format N1B-2 sans `minute`
# reste accepte et produit la meme cle — verifie plus bas.
SD7 = {"type": "same_day", "heure": 7, "minute": 0}

# Mardi 18 aout 2026, 19:00 heure suisse.
COURS = "2026-08-18T19:00:00"
DEBUT = datetime(2026, 8, 15, 0, 0, tzinfo=ZH).astimezone(timezone.utc)

resultats = []


def verifier(nom, obtenu, attendu):
    ok = obtenu == attendu
    resultats.append((ok, nom, obtenu, attendu))


# 1. Comportement historique inchange par defaut — compare a l'ANCIEN moteur.
ecarts = []
for i in range(96):
    now = DEBUT + timedelta(hours=i)
    vierge = {"datetime": COURS}
    if passage_cron(now, vierge, DEFAUT) != passage_v435_historique(now, vierge):
        ecarts.append(now.isoformat())
verifier("historique inchange (96 passages compares a V435)", ecarts, [])

verifier("defaut : 1 seul rappel, 1 h avant",
         simuler({"datetime": COURS}, DEFAUT, DEBUT, 96),
         [("defaut", "Tue 18/08 18:00")])

# 2-4. Delais relatifs.
verifier("1 h avant", simuler({"datetime": COURS}, [R1], DEBUT, 96),
         [("defaut", "Tue 18/08 18:00")])
verifier("3 h avant", simuler({"datetime": COURS}, [R3], DEBUT, 96),
         [("relative:180m", "Tue 18/08 16:00")])
verifier("24 h avant", simuler({"datetime": COURS}, [R24], DEBUT, 96),
         [("relative:1440m", "Mon 17/08 19:00")])
verifier("48 h avant", simuler({"datetime": COURS}, [R48], DEBUT, 96),
         [("relative:2880m", "Sun 16/08 19:00")])

# 5. Heure fixe le jour du cours.
verifier("07:00 le jour du cours", simuler({"datetime": COURS}, [SD7], DEBUT, 96),
         [("same_day:07:00", "Tue 18/08 07:00")])

# 6. Les deux ensemble sur la MEME reservation.
verifier("24 h + 07:00 -> exactement deux rappels",
         simuler({"datetime": COURS}, [R24, SD7], DEBUT, 96),
         [("relative:1440m", "Mon 17/08 19:00"), ("same_day:07:00", "Tue 18/08 07:00")])

# 7. Rejeu du cron : le meme passage, deux fois.
r = {"datetime": COURS}
simuler(r, [R24, SD7], DEBUT, 96)
verifier("rejeu integral du cron -> aucun doublon", simuler(r, [R24, SD7], DEBUT, 96), [])

instant_24h = datetime(2026, 8, 17, 19, 0, tzinfo=ZH).astimezone(timezone.utc)
r2 = {"datetime": COURS}
verifier("meme passage joue deux fois -> un seul envoi",
         simuler(r2, [R24, SD7], instant_24h, 1) + simuler(r2, [R24, SD7], instant_24h, 1),
         [("relative:1440m", "Mon 17/08 19:00")])

# 8. Echec du premier rappel -> le second reste independant.
verifier("echec du rappel 24 h -> le rappel 07:00 part quand meme",
         simuler({"datetime": COURS}, [R24, SD7], DEBUT, 96, echecs=(1,)),
         [("same_day:07:00", "Tue 18/08 07:00")])

# ... et l'echec reste retentable si un passage retombe dans la fenetre.
verifier("echec puis nouveau passage dans la fenetre -> reessaye",
         simuler({"datetime": COURS}, [R24], DEBUT, 96, echecs=(1,),
                 passages_sup=(instant_24h + timedelta(minutes=20),)),
         [("relative:1440m", "Mon 17/08 19:20")])

# 9. Cours passe / cible absurde.
verifier("cours deja commence -> aucun envoi",
         simuler({"datetime": "2026-08-14T19:00:00"}, [R24, SD7], DEBUT, 96), [])
verifier("07:00 pour un cours a 06:00 -> aucun envoi (cible apres le cours)",
         simuler({"datetime": "2026-08-18T06:00:00"}, [SD7], DEBUT, 96), [])

# 10. Retrocompatibilite N1B-1 et garde-fous de configuration.
verifier("ancien booleen seul -> rappel historique deja fait",
         simuler({"datetime": COURS, "reminder_sent": True}, DEFAUT, DEBUT, 96), [])
verifier("cle 60 min = cle historique", NS["n1b2_cle"](R1), "defaut")
verifier("titre historique inchange", NS["n1b2_titre"]("defaut"), "📅 Ton cours commence dans 1h")
verifier("3 regles refusees", NS["n1b2_valider_regles"]([R1, R24, SD7]), None)
verifier("delai hors liste refuse", NS["n1b2_valider_regles"]([{"type": "relative", "minutes": 90}]), None)
verifier("heure hors bornes refusee", NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 24}]), None)
verifier("booleen refuse comme heure", NS["n1b2_valider_regles"]([{"type": "same_day", "heure": True}]), None)
verifier("doublon de cle refuse", NS["n1b2_valider_regles"]([R1, {"type": "relative", "minutes": 60}]), None)
verifier("liste vide refusee", NS["n1b2_valider_regles"]([]), None)
verifier("configuration valide acceptee", NS["n1b2_valider_regles"]([R24, SD7]), [R24, SD7])

# 11. Fuseau : le passage a l'heure d'hiver ne decale pas l'heure fixe.
verifier("07:00 local malgre le changement d'heure (cours du 26/10)",
         simuler({"datetime": "2026-10-26T19:00:00"}, [SD7],
                 datetime(2026, 10, 23, 0, 0, tzinfo=ZH).astimezone(timezone.utc), 96),
         [("same_day:07:00", "Mon 26/10 07:00")])

# 12. Libelles — valides par le coach le 13/08/2026.
CORPS = NS["n1b2_corps"]
verifier("corps 1 h — IDENTIQUE a l'ancienne expression",
         CORPS("defaut", "Danse Afro", "19:00"),
         "Danse Afro" + " à 19:00" + " — prépare-toi !")
verifier("corps 3 h", CORPS("relative:180m", "Danse Afro", "19:00"),
         "Danse Afro à 19:00 — ton moment Afroboost approche 🎧")
verifier("corps 24 h", CORPS("relative:1440m", "Danse Afro", "19:00"),
         "Danse Afro demain à 19:00. On se retrouve chez Afroboost 🎧")
verifier("corps 48 h", CORPS("relative:2880m", "Danse Afro", "19:00"),
         "Danse Afro après-demain à 19:00. Pense à garder ce moment pour toi 🎧")
verifier("corps jour meme", CORPS("same_day:07:00", "Danse Afro", "19:00"),
         "Danse Afro aujourd'hui à 19:00. À tout à l'heure 🎧🔥")

# Heure absente : la portion horaire disparait sans ponctuation orpheline.
verifier("sans heure — 1 h", CORPS("defaut", "Danse Afro", ""),
         "Danse Afro — prépare-toi !")
verifier("sans heure — 3 h", CORPS("relative:180m", "Danse Afro", ""),
         "Danse Afro — ton moment Afroboost approche 🎧")
verifier("sans heure — 24 h", CORPS("relative:1440m", "Danse Afro", ""),
         "Danse Afro demain. On se retrouve chez Afroboost 🎧")
verifier("sans heure — 48 h", CORPS("relative:2880m", "Danse Afro", ""),
         "Danse Afro après-demain. Pense à garder ce moment pour toi 🎧")
verifier("sans heure — jour meme", CORPS("same_day:07:00", "Danse Afro", ""),
         "Danse Afro aujourd'hui. À tout à l'heure 🎧🔥")

# Aucun corps ne doit contenir « à  » double, « à.» ou une virgule orpheline.
_anomalies = []
for _cle in ("defaut", "relative:180m", "relative:1440m", "relative:2880m", "same_day:07:00"):
    for _nom, _hr in (("Danse Afro", "19:00"), ("Danse Afro", ""), ("ton cours", "")):
        _t = CORPS(_cle, _nom, _hr)
        if "  " in _t or " ." in _t or " ," in _t or _t.rstrip().endswith("à"):
            _anomalies.append(_t)
verifier("aucune ponctuation orpheline (15 combinaisons)", _anomalies, [])

# Le repli de nom de cours reste lisible.
verifier("repli « ton cours »", CORPS("relative:1440m", "ton cours", ""),
         "ton cours demain. On se retrouve chez Afroboost 🎧")

# === N1B-3B1 : les demi-heures, avec la cadence REELLE du cron (30 min) ======
SD730 = {"type": "same_day", "heure": 7, "minute": 30}
SD18 = {"type": "same_day", "heure": 18, "minute": 0}
SD1830 = {"type": "same_day", "heure": 18, "minute": 30}

verifier("same_day 07:00 (cron 30 min)",
         simuler({"datetime": COURS}, [SD7], DEBUT, 96, pas_min=30),
         [("same_day:07:00", "Tue 18/08 07:00")])
verifier("same_day 07:30 (cron 30 min)",
         simuler({"datetime": COURS}, [SD730], DEBUT, 96, pas_min=30),
         [("same_day:07:30", "Tue 18/08 07:30")])
verifier("same_day 18:00 (cron 30 min)",
         simuler({"datetime": COURS}, [SD18], DEBUT, 96, pas_min=30),
         [("same_day:18:00", "Tue 18/08 18:00")])
verifier("same_day 18:30 (cron 30 min)",
         simuler({"datetime": COURS}, [SD1830], DEBUT, 96, pas_min=30),
         [("same_day:18:30", "Tue 18/08 18:30")])

# Rejeu integral du cron 30 min : aucun doublon.
_r30 = {"datetime": COURS}
simuler(_r30, [R24, SD730], DEBUT, 96, pas_min=30)
verifier("rejeu du cron 30 min -> aucun doublon",
         simuler(_r30, [R24, SD730], DEBUT, 96, pas_min=30), [])

# Balayage large : aucune demi-heure ne produit de doublon, quel que soit le cours.
_doublons = []
for _hh in range(6, 23):
    for _mm in ("00", "30"):
        _c = "2026-08-18T%02d:%s:00" % (_hh, _mm)
        for _rg in ([SD7], [SD730], [SD1830], [R24, SD730]):
            _e = [x[0] for x in simuler({"datetime": _c}, _rg, DEBUT, 96, pas_min=30)]
            if len(_e) != len(set(_e)):
                _doublons.append((_c, _e))
verifier("aucun doublon — 34 horaires x 4 configurations, cron 30 min", _doublons, [])

# Cours deja commence : jamais de rappel, meme a la demi-heure.
verifier("cours deja commence -> aucun rappel (demi-heure)",
         simuler({"datetime": "2026-08-14T18:30:00"}, [SD1830], DEBUT, 96, pas_min=30), [])
verifier("18:30 pour un cours a 18:00 -> rien (cible apres le cours)",
         simuler({"datetime": "2026-08-18T18:00:00"}, [SD1830], DEBUT, 96, pas_min=30), [])

# Retrocompatibilite du FORMAT de regle : `minute` absente == `minute: 0`.
verifier("regle au format N1B-2 -> cle inchangee",
         NS["n1b2_cle"]({"type": "same_day", "heure": 7}), "same_day:07:00")
verifier("minute 0 explicite -> meme cle", NS["n1b2_cle"](SD7), "same_day:07:00")
verifier("regle au format N1B-2 toujours valide",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7}]),
         [{"type": "same_day", "heure": 7, "minute": 0}])
verifier("cle distincte pour la demi-heure", NS["n1b2_cle"](SD730), "same_day:07:30")

# Garde-fous des minutes.
verifier("minute 30 acceptee", NS["n1b2_valider_regles"]([SD730]), [SD730])
verifier("minute 15 refusee",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": 15}]), None)
verifier("minute 60 refusee",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": 60}]), None)
verifier("minute negative refusee",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": -30}]), None)
verifier("booleen refuse comme minute",
         NS["n1b2_valider_regles"]([{"type": "same_day", "heure": 7, "minute": True}]), None)
verifier("07:00 et 07:30 restent deux regles distinctes",
         NS["n1b2_valider_regles"]([SD7, SD730]), [SD7, SD730])

# Le titre reste celui de la famille same_day, quelle que soit la minute.
verifier("titre same_day inchange a la demi-heure",
         NS["n1b2_titre"]("same_day:07:30"), "📅 Ton cours, c'est aujourd'hui")

print("=" * 74)
echecs_test = 0
for ok, nom, obtenu, attendu in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom)
    if not ok:
        echecs_test += 1
        print("          obtenu  : %r" % (obtenu,))
        print("          attendu : %r" % (attendu,))
print("=" * 74)
print("  %d/%d" % (len(resultats) - echecs_test, len(resultats)))
sys.exit(1 if echecs_test else 0)

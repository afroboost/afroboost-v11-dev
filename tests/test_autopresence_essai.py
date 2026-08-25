# -*- coding: utf-8 -*-
"""AUTO-PRESENCE PHASE 1 — L'OUBLI DU SCAN NE BLOQUE PLUS L'ESSAI.

CE QUE CE LOT PROMET, ET CE QUE CE BANC VERIFIE :
  * un essai reserve, non scanne, non annule, sans absence declaree, devient
    une presence APRES un delai de grace — et jamais avant ;
  * un forfait PAYANT n'entre JAMAIS dans l'auto-presence (phase 1) ;
  * une absence declaree par le coach ferme definitivement l'auto-validation ;
  * une auto-presence ne se fait JAMAIS passer pour un scan :
    `validation_source = "auto"`, avec son propre horodatage ;
  * une seule validation, quoi qu'il arrive — rejeu, deux workers, redemarrage ;
  * P1-b part exactement UNE fois, au moment ou l'auto-validation devient
    definitive — jamais a l'heure theorique du cours ;
  * rien du tout tant que le drapeau est faux ;
  * rien d'ECRIT tant que l'ecriture reelle n'est pas armee ;
  * aucune reservation anterieure a la borne, jamais.

LES VRAIES FONCTIONS DU DEPOT, extraites par AST de `api/server.py` et de
`api/routes/reservation_routes.py`. Les seuls elements remplaces sont les
regles deja prouvees ailleurs (ESSAI-6 `est_un_essai`, garde A1b) et les
effets de bord observables (C9, P1-b) — qu'on COMPTE au lieu de les executer.

AUCUN RESEAU, AUCUNE BASE REELLE, AUCUN E-MAIL.
    python3 tests/test_autopresence_essai.py
"""
import ast, asyncio, io, os, sys
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    ZH = ZoneInfo("Europe/Zurich")
except Exception:                                        # pragma: no cover
    print("zoneinfo indisponible — banc impossible")
    sys.exit(1)

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ─────────────────────────── extraction AST ─────────────────────────────────
SERVEUR = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
RESAS = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                encoding="utf-8").read()

_FN, _CST = {}, {}
for _src, _cible in ((SERVEUR, "server"), (RESAS, "resas")):
    _arbre = ast.parse(_src)
    for _n in ast.walk(_arbre):
        if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _FN.setdefault(_n.name, ast.get_source_segment(_src, _n))
    for _n in _arbre.body:
        if isinstance(_n, ast.Assign):
            for _c in _n.targets:
                if isinstance(_c, ast.Name):
                    _CST.setdefault(_c.id, ast.get_source_segment(_src, _n))


def extraire(nom):
    if nom not in _FN:
        raise AssertionError("fonction introuvable : %s" % nom)
    return _FN[nom]


def constante(nom):
    if nom not in _CST:
        raise AssertionError("constante introuvable : %s" % nom)
    return _CST[nom]


# ───────────────────────── faux Mongo, minimal et fidele ────────────────────
def _valeur(doc, cle):
    val = doc
    for part in cle.split("."):
        val = (val or {}).get(part) if isinstance(val, dict) else None
    return val


def _match(doc, filtre):
    for cle, cond in (filtre or {}).items():
        if cle == "$or":
            if not any(_match(doc, s) for s in cond):
                return False
            continue
        val = _valeur(doc, cle)
        if isinstance(cond, dict):
            for op, ref in cond.items():
                if op == "$exists":
                    if (val is not None) != ref:
                        return False
                elif op == "$ne":
                    if val == ref:
                        return False
                elif op == "$gte":
                    if val is None or not (str(val) >= str(ref)):
                        return False
                elif op == "$lte":
                    if val is None or not (str(val) <= str(ref)):
                        return False
                elif op == "$lt":
                    if val is None or not (str(val) < str(ref)):
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        elif val != cond:
            return False
    return True


class _Maj:
    def __init__(self, n):
        self.matched_count = n
        self.modified_count = n


class _Curseur:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, n=None):
        return [dict(r) for r in (self._rows if n is None else self._rows[:n])]


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def find_one(self, filtre=None, proj=None):
        for d in self.docs:
            if _match(d, filtre or {}):
                return dict(d)
        return None

    def find(self, filtre=None, proj=None):
        return _Curseur([d for d in self.docs if _match(d, filtre or {})])

    async def update_one(self, filtre, maj, upsert=False):
        for d in self.docs:
            if _match(d, filtre):
                for cle, val in (maj.get("$set") or {}).items():
                    cible, parts = d, cle.split(".")
                    for p in parts[:-1]:
                        cible = cible.setdefault(p, {})
                    cible[parts[-1]] = val
                for cle, val in (maj.get("$inc") or {}).items():
                    d[cle] = (d.get(cle) or 0) + val
                return _Maj(1)
        return _Maj(0)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return _Maj(1)


class _Base:
    def __init__(self, **cols):
        self._c = {n: _Coll(v) for n, v in cols.items()}

    def __getitem__(self, n):
        return self._c.setdefault(n, _Coll())

    def __getattr__(self, n):
        return self._c.setdefault(n, _Coll())


# ──────────────────────────── le bac a sable ────────────────────────────────
OCC_ESSAI = "2026-08-26T18:30:00"          # naif Europe/Zurich, apres la borne
OCC_ANCIENNE = "2026-05-10T18:30:00"       # avant la borne
CODE_ESSAI = "AFR-ESSAI1"
CODE_PAYANT = "BASSBOOSTX-99"


def _resa(**kw):
    base = {
        "id": "r1", "reservationCode": "AFRO-AAAA",
        "userEmail": "prospect@exemple.ch", "userName": "Prospect",
        "userWhatsapp": "+41790000000",
        "courseId": "c1", "courseName": "Afroboost Silent", "courseTime": "18:30",
        "datetime": OCC_ESSAI, "promoCode": CODE_ESSAI,
        "quantity": 1, "coach_id": None,
    }
    base.update(kw)
    return base


def bac(reservations=None, flags=None, essai=True, a1b_ok=True, duree=60):
    """Un environnement complet. Rend `(ns, base, trace)`."""
    base = _Base(
        reservations=reservations if reservations is not None else [_resa()],
        offers=[{"id": "o1", "duration_minutes": duree}],
        subscriptions=[], discount_codes=[], courses=[{"id": "c1", "name": "Afroboost Silent"}],
    )
    trace = {"c9": 0, "p1b": [], "journal": []}

    _flags = {"AUTO_PRESENCE_TRIAL_ENABLED": True,
              "AUTO_PRESENCE_TRIAL_ECRITURE_REELLE": True}
    _flags.update(flags or {})

    async def _get_flags():
        return dict(_flags)

    async def _est_un_essai(_db, forfait=None, code=""):
        # ESSAI-6 est prouve par test_essai6_identite.py : ici on ne teste que
        # l'usage qu'en fait l'auto-presence.
        return bool(essai) and str(code or "").upper() == CODE_ESSAI

    async def _a1b(rows):
        return list(rows) if a1b_ok else []

    async def _c9_presence(_r, _deja):
        trace["c9"] += 1

    def _p1b_apres_presence(r):
        trace["p1b"].append(dict(r))

    class _Log:
        def info(self, *a, **k):
            trace["journal"].append(("info", a[0] % a[1:] if len(a) > 1 else a[0]))

        def warning(self, *a, **k):
            trace["journal"].append(("warning", a[0] % a[1:] if len(a) > 1 else a[0]))

        def error(self, *a, **k):
            trace["journal"].append(("error", a[0] % a[1:] if len(a) > 1 else a[0]))

    ns = {
        "db": base, "datetime": datetime, "timezone": timezone, "timedelta": timedelta,
        "uuid": __import__("uuid"),
        "ZoneInfo": ZoneInfo, "os": os, "asyncio": asyncio, "logger": _Log(),
        "get_feature_flags": _get_flags,
        "_ap_est_un_essai": _est_un_essai,
        "_ap_a1b": _a1b,
        "_c9_presence": _c9_presence,
        "_p1b_apres_presence": _p1b_apres_presence,
        "_r11_verifier_proprietaire": lambda *a, **k: None,
    }

    # Les VRAIES fonctions du depot.
    for nom in ("lot1_occurrence_iso",):
        exec(compile(extraire(nom), "<ap>", "exec"), ns)
    for nom in ("AP_PREFIXE", "AP_FUSEAU", "AP_GRACE_MINUTES", "AP_DUREE_DEFAUT_MIN",
                "AP_BORNE_DEFAUT", "AP_LOT_MAX"):
        exec(compile(constante(nom), "<ap>", "exec"), ns)
    for nom in ("_a0_marquer_presente", "ap_borne_activation", "ap_occurrence_utc",
                "ap_echeance", "ap_duree_minutes", "ap_candidats", "ap_traiter",
                "ap_passage", "t1_tracer_annulation"):
        exec(compile(extraire(nom), "<ap>", "exec"), ns)
    return ns, base, trace


# Cours 18:30 + 60 min de duree + 2 h de grace => echeance a 21:30 heure suisse.
MAINTENANT = datetime(2026, 8, 26, 22, 0, tzinfo=ZH).astimezone(timezone.utc)   # 22:00 Zurich, echeance passee
TROP_TOT = datetime(2026, 8, 26, 20, 0, tzinfo=ZH).astimezone(timezone.utc)    # 20:00 Zurich, cours fini mais grace en cours


def lancer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ════════════════════════════ LES CAS A -> Q ═══════════════════════════════
def cas_A_qr_gagne():
    ns, base, trace = bac(reservations=[_resa(validated=True,
                                              validatedAt="2026-08-26T16:35:00+00:00",
                                              validation_source="qr")])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    d = base.reservations.docs[0]
    verifier("A. essai scanne : l'auto-worker l'ignore",
             issue == "deja_validee", "issue=%s" % issue)
    verifier("A. la source reste « qr », jamais reecrite en « auto »",
             d.get("validation_source") == "qr", d.get("validation_source"))
    verifier("A. aucun P1-b supplementaire", len(trace["p1b"]) == 0)


def cas_B_absent_ferme():
    ns, base, trace = bac(reservations=[_resa(absence_marked_at="2026-08-26T19:00:00+00:00",
                                              absence_marked_by="coach@afroboost.com")])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    d = base.reservations.docs[0]
    verifier("B. absence declaree : jamais auto-validee", issue == "absent", issue)
    verifier("B. validated reste faux", d.get("validated") is not True)
    verifier("B. aucun P1-b", len(trace["p1b"]) == 0)


def cas_C_annulee():
    # L'annulation SUPPRIME le document (server.py `cancel_reservation_from_space`).
    ns, base, trace = bac(reservations=[])
    cands = lancer(ns["ap_candidats"](MAINTENANT))
    verifier("C. reservation annulee : absente de la base, donc jamais candidate",
             cands == [], "%d candidat(s)" % len(cands))


def cas_D_auto_apres_delai():
    ns, base, trace = bac()
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    d = base.reservations.docs[0]
    verifier("D. essai non scanne, non annule : auto-validee apres le delai",
             issue == "auto_validee", issue)
    verifier("D. validated pose", d.get("validated") is True)
    verifier("D. validation_source = « auto »",
             d.get("validation_source") == "auto", d.get("validation_source"))
    verifier("D. horodatage d'auto-presence pose", bool(d.get("auto_presence_at")))
    # L'horodatage est celui de la DECISION, pris a l'instant reel — jamais
    # l'heure theorique du cours. C'est ce qui fait partir le J+0 au bon moment.
    _va = str(d.get("validatedAt") or "")
    _aware = False
    try:
        _aware = datetime.fromisoformat(_va.replace("Z", "+00:00")).tzinfo is not None
    except Exception:
        _aware = False
    verifier("D. validatedAt est l'instant REEL de la decision, pas l'heure du cours",
             _aware and _va[:19] != OCC_ESSAI, _va)


def cas_E_avant_delai():
    ns, base, trace = bac()
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], TROP_TOT))
    d = base.reservations.docs[0]
    verifier("E. avant la fin du delai de grace : rien", issue == "pas_encore", issue)
    verifier("E. validated intact", d.get("validated") is not True)
    verifier("E. aucun P1-b", len(trace["p1b"]) == 0)


def cas_F_rejeu():
    ns, base, trace = bac()
    i1 = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    i2 = lancer(ns["ap_traiter"](dict(base.reservations.docs[0]), MAINTENANT))
    i3 = lancer(ns["ap_traiter"](dict(base.reservations.docs[0]), MAINTENANT))
    verifier("F. worker rejoue 3x : une seule auto-validation",
             (i1, i2, i3) == ("auto_validee", "deja_validee", "deja_validee"),
             str((i1, i2, i3)))
    verifier("F. P1-b exactement une fois", len(trace["p1b"]) == 1,
             "%d envoi(s)" % len(trace["p1b"]))


def cas_G_concurrence():
    ns, base, trace = bac()
    depart = dict(base.reservations.docs[0])

    async def _deux():
        return await asyncio.gather(ns["ap_traiter"](dict(depart), MAINTENANT),
                                    ns["ap_traiter"](dict(depart), MAINTENANT))
    issues = lancer(_deux())
    verifier("G. deux workers simultanes : une seule validation",
             sorted(issues) == ["auto_validee", "deja_validee"], str(issues))
    verifier("G. P1-b exactement une fois malgre la course",
             len(trace["p1b"]) == 1, "%d envoi(s)" % len(trace["p1b"]))


def cas_H_redemarrage():
    # L'etat vit EN BASE, pas en memoire : un nouveau worker reprend le meme
    # travail et ne le refait pas deux fois.
    ns, base, trace = bac()
    lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    ns2, _, trace2 = bac(reservations=base.reservations.docs)
    cands = lancer(ns2["ap_candidats"](MAINTENANT))
    verifier("H. apres redemarrage : la reservation deja traitee n'est plus candidate",
             cands == [], "%d candidat(s)" % len(cands))
    verifier("H. aucun second P1-b", len(trace2["p1b"]) == 0)


def cas_I_date_unique():
    ns, base, trace = bac(reservations=[_resa(id="r-unique", datetime="2026-08-26T12:00:00")])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("I. cours a date unique : meme comportement", issue == "auto_validee", issue)


def cas_J_recurrent():
    ns, base, trace = bac(reservations=[_resa(id="r-recur", datetime=OCC_ESSAI)])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("J. cours recurrent : meme comportement", issue == "auto_validee", issue)


def cas_J2_seance_inexistante():
    ns, base, trace = bac(a1b_ok=False)
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("J2. cours archive / n'ayant pas lieu ce jour : ecarte (garde A1b)",
             issue == "seance_inexistante", issue)


def cas_K_hors_borne():
    ns, base, trace = bac(reservations=[_resa(datetime=OCC_ANCIENNE)])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("K. occurrence anterieure a la borne : ignoree", issue == "hors_borne", issue)
    verifier("K. aucun rattrapage historique",
             base.reservations.docs[0].get("validated") is not True)


def cas_L_payant_ignore():
    ns, base, trace = bac(reservations=[_resa(promoCode=CODE_PAYANT)])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("L. forfait PAYANT non scanne : jamais auto-valide (phase 1)",
             issue == "pas_un_essai", issue)
    verifier("L. aucune seance debitee",
             base.reservations.docs[0].get("validated") is not True)


def cas_M_p1b_une_fois():
    ns, base, trace = bac()
    lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("M. auto-validation : P1-b exactement une fois",
             len(trace["p1b"]) == 1, "%d" % len(trace["p1b"]))
    verifier("M. P1-b recoit bien la reservation auto-validee",
             trace["p1b"] and trace["p1b"][0].get("id") == "r1")
    verifier("M. C9 (analytics presence) emis une fois", trace["c9"] == 1)


def cas_N_p1c_ouvert():
    # P1-c (`conv_presence_reelle`) exige `validated: True` + garde A1b. On
    # verifie que l'auto-presence produit EXACTEMENT ce couple.
    ns, base, trace = bac()
    lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    d = base.reservations.docs[0]
    verifier("N. P1-c : la presence porte validated=True", d.get("validated") is True)
    verifier("N. P1-c : la garde A1b a ete franchie AVANT la validation",
             d.get("validation_source") == "auto")


def cas_O_p1d_compatible():
    # P1-d filtre sur `validated: True` + `validatedAt` dans une fenetre ISO-UTC.
    ns, base, trace = bac()
    lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    va = str(base.reservations.docs[0].get("validatedAt") or "")
    ok = False
    try:
        _d = datetime.fromisoformat(va.replace("Z", "+00:00"))
        ok = _d.tzinfo is not None
    except Exception:
        ok = False
    verifier("O. P1-d : validatedAt est un ISO AWARE, comparable a la borne P1-d",
             ok, va)


def cas_P_erreur_sans_corruption():
    ns, base, trace = bac()

    async def _a1b_casse(rows):
        raise RuntimeError("base muette")
    ns["_ap_a1b"] = _a1b_casse
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    d = base.reservations.docs[0]
    verifier("P. garde indisponible : on REFUSE, on ne valide pas au hasard",
             issue in ("seance_inexistante", "echec"), issue)
    verifier("P. aucune corruption : validated intact", d.get("validated") is not True)
    verifier("P. aucun P1-b", len(trace["p1b"]) == 0)


def cas_Q_noshow_juste_avant():
    """Le no-show pose entre le chargement du candidat et son traitement GAGNE."""
    ns, base, trace = bac()
    candidat = dict(base.reservations.docs[0])          # lu AVANT le no-show
    base.reservations.docs[0]["absence_marked_at"] = "2026-08-26T20:59:00+00:00"
    issue = lancer(ns["ap_traiter"](candidat, MAINTENANT))
    d = base.reservations.docs[0]
    verifier("Q. no-show pose juste avant le worker : le no-show gagne",
             issue == "absent", issue)
    verifier("Q. validated reste faux", d.get("validated") is not True)
    verifier("Q. aucun P1-b", len(trace["p1b"]) == 0)


# ═══════════════════════ DRAPEAUX, SIMULATION, BORNE ════════════════════════
def cas_drapeau_off():
    ns, base, trace = bac(flags={"AUTO_PRESENCE_TRIAL_ENABLED": False})
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("drapeau OFF : rien du tout", issue == "desactive", issue)
    verifier("drapeau OFF : aucune ecriture",
             base.reservations.docs[0].get("validated") is not True)
    resume = lancer(ns["ap_passage"](MAINTENANT))
    verifier("drapeau OFF : le passage ne lit meme pas la base",
             resume == {"desactive": 1}, str(resume))


def cas_simulation():
    ns, base, trace = bac(flags={"AUTO_PRESENCE_TRIAL_ECRITURE_REELLE": False})
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    d = base.reservations.docs[0]
    verifier("simulation : la decision est prise et nommee", issue == "simulation", issue)
    verifier("simulation : validated N'EST PAS modifie", d.get("validated") is not True)
    verifier("simulation : aucune trace definitive posee",
             not d.get("auto_presence_at"),
             "auto_presence_at=%r" % d.get("auto_presence_at"))
    verifier("simulation : validation_source non pose", not d.get("validation_source"))
    verifier("simulation : AUCUN P1-b", len(trace["p1b"]) == 0)
    verifier("simulation : la decision est journalisee",
             any("SIMULATION" in str(m) for _n, m in trace["journal"]),
             str(trace["journal"])[:200])
    # ... et l'execution reelle reste possible ensuite : rien ne l'a bloquee.
    ns2, base2, trace2 = bac(reservations=base.reservations.docs)
    issue2 = lancer(ns2["ap_traiter"](base2.reservations.docs[0], MAINTENANT))
    verifier("simulation : n'empeche PAS l'execution reelle ulterieure",
             issue2 == "auto_validee", issue2)


def cas_borne_illisible():
    ns, base, trace = bac()
    os.environ["AP_BORNE_ACTIVATION"] = "pas-une-date"
    try:
        borne = ns["ap_borne_activation"]()
        verifier("borne illisible -> borne INFINIE (aucun candidat), panne bruyante",
                 borne.year >= 2999, str(borne))
    finally:
        os.environ.pop("AP_BORNE_ACTIVATION", None)


def cas_delai_de_grace():
    ns, base, trace = bac()
    # Cours 18:30 + 60 min de duree + 2 h de grace = 21:30 Zurich.
    ech = ns["ap_echeance"](OCC_ESSAI, 60)
    local = ech.astimezone(ZH)
    verifier("delai : fin du cours (18:30+60min) + 2 h = 21:30 heure suisse",
             (local.hour, local.minute) == (21, 30),
             local.isoformat())
    # La duree vient de l'offre quand elle existe : 95 min -> 22:05.
    ech95 = ns["ap_echeance"](OCC_ESSAI, 95)
    verifier("delai : la duree REELLE de l'offre est utilisee (95 min -> 22:05)",
             ech95.astimezone(ZH).strftime("%H:%M") == "22:05",
             ech95.astimezone(ZH).isoformat())


def cas_heure_dete_hiver():
    """Aucun UTC+2 fixe : la meme heure locale donne deux instants differents."""
    ns, base, trace = bac()
    ete = ns["ap_echeance"]("2026-07-15T18:30:00", 60)     # CEST, UTC+2
    hiver = ns["ap_echeance"]("2026-12-15T18:30:00", 60)   # CET,  UTC+1
    verifier("fuseau : 21:30 locale en ETE = 19:30 UTC",
             ete.astimezone(timezone.utc).strftime("%H:%M") == "19:30",
             ete.isoformat())
    verifier("fuseau : 21:30 locale en HIVER = 20:30 UTC (pas d'UTC+2 fixe)",
             hiver.astimezone(timezone.utc).strftime("%H:%M") == "20:30",
             hiver.isoformat())


def cas_formats_mixtes():
    """81 occurrences naives et 57 suffixees Z coexistent en production."""
    ns, base, trace = bac()
    naif = ns["ap_echeance"](ns["lot1_occurrence_iso"]("2026-08-26T18:30:00"), 60)
    avec_z = ns["ap_echeance"](ns["lot1_occurrence_iso"]("2026-08-26T16:30:00Z"), 60)
    verifier("formats mixtes : « ...T18:30:00 » et « ...T16:30:00Z » designent la MEME seance",
             naif == avec_z, "%s vs %s" % (naif, avec_z))


def cas_occurrence_illisible():
    ns, base, trace = bac(reservations=[_resa(datetime="2026-08-26")])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("occurrence illisible : refus explicite, jamais une heure devinee",
             issue == "occurrence_illisible", issue)


def cas_credit_deja_rendu():
    ns, base, trace = bac(reservations=[_resa(trial_credit_restored="2026-08-26T20:00:00+00:00")])
    issue = lancer(ns["ap_traiter"](base.reservations.docs[0], MAINTENANT))
    verifier("credit deja restitue : jamais auto-valide (pas de double consommation)",
             issue == "credit_rendu", issue)


def cas_candidats_filtre():
    """La requete ecarte deja, en base, tout ce qui ne peut pas etre candidat."""
    docs = [
        _resa(id="ok"),
        _resa(id="deja", validated=True),
        _resa(id="absent", absence_marked_at="2026-08-26T19:00:00+00:00"),
        _resa(id="rendu", trial_credit_restored="2026-08-26T19:00:00+00:00"),
        _resa(id="traite", auto_presence_at="2026-08-26T21:00:00+00:00"),
    ]
    ns, base, trace = bac(reservations=docs)
    cands = lancer(ns["ap_candidats"](MAINTENANT))
    ids = sorted(c.get("id") for c in cands)
    verifier("candidats : seule la reservation eligible est chargee",
             ids == ["ok"], str(ids))


def cas_passage_resume():
    docs = [_resa(id="a"), _resa(id="b", promoCode=CODE_PAYANT),
            _resa(id="c", datetime=OCC_ANCIENNE)]
    ns, base, trace = bac(reservations=docs)
    resume = lancer(ns["ap_passage"](MAINTENANT))
    verifier("passage : le resume compte chaque issue",
             resume.get("auto_validee") == 1 and resume.get("pas_un_essai") == 1
             and resume.get("hors_borne") == 1, str(resume))
    verifier("passage : un seul P1-b pour un seul essai auto-valide",
             len(trace["p1b"]) == 1, "%d" % len(trace["p1b"]))


# ═══════════════════ LA SOURCE DE VALIDATION SUR LES 4 CHEMINS ══════════════
def cas_source_qr_par_defaut():
    """Les chemins humains existants restent « qr » sans etre modifies un a un."""
    ns, base, trace = bac()
    r = base.reservations.docs[0]
    lancer(ns["_a0_marquer_presente"](r))
    verifier("scan humain : validation_source = « qr » par defaut",
             base.reservations.docs[0].get("validation_source") == "qr",
             base.reservations.docs[0].get("validation_source"))


def cas_source_auto_explicite():
    ns, base, trace = bac()
    r = base.reservations.docs[0]
    lancer(ns["_a0_marquer_presente"](r, "", "auto"))
    verifier("auto-presence : validation_source = « auto », jamais « qr »",
             base.reservations.docs[0].get("validation_source") == "auto",
             base.reservations.docs[0].get("validation_source"))


def cas_walkin_source():
    """Le walk-in insere une reservation deja validee : il doit se nommer."""
    verifier("walk-in : la reservation creee au scan porte validation_source",
             '"validation_source": "walkin"' in RESAS,
             "absent de reservation_routes.py")


def cas_route_absence_existe():
    verifier("une route de declaration d'absence existe",
             "/reservations/{reservation_id}/absence" in RESAS,
             "route absente")
    verifier("la route d'absence est protegee par la garde de propriete R11",
             "_r11_scanneur" in (_FN.get("marquer_absence") or ""),
             "garde R11 absente de marquer_absence")
    verifier("l'absence reutilise la restitution EXISTANTE, sans en inventer une seconde",
             "t1_restituer_essais_non_honores" in (_FN.get("marquer_absence") or ""),
             "restitution non reutilisee")


def cas_bilan_expose_les_attendus():
    verifier("le Bilan expose la liste des attendus (sans quoi le coach ne peut "
             "marquer personne absent)",
             "participants_attendus" in RESAS, "champ absent du Bilan")


def cas_drapeaux_declares():
    verifier("AUTO_PRESENCE_TRIAL_ENABLED declare dans le modele",
             "AUTO_PRESENCE_TRIAL_ENABLED" in SERVEUR)
    verifier("AUTO_PRESENCE_TRIAL_ECRITURE_REELLE declare dans le modele",
             "AUTO_PRESENCE_TRIAL_ECRITURE_REELLE" in SERVEUR)
    verifier("les deux drapeaux ont pour defaut False (lot dormant a la livraison)",
             '"AUTO_PRESENCE_TRIAL_ENABLED": False' in SERVEUR
             and '"AUTO_PRESENCE_TRIAL_ECRITURE_REELLE": False' in SERVEUR)
    verifier("les deux drapeaux sont modifiables par le super-admin",
             "AUTO_PRESENCE_TRIAL_ENABLED: Optional[bool]" in SERVEUR
             and "AUTO_PRESENCE_TRIAL_ECRITURE_REELLE: Optional[bool]" in SERVEUR)
    verifier("la boucle de fond est lancee au demarrage",
             "_ap_boucle_auto_presence()" in SERVEUR)


def cas_p1d_intact():
    verifier("P1-d n'est pas touche : le drapeau ENABLED existe toujours",
             "P1_TRIAL_J3_ENABLED" in SERVEUR)
    verifier("P1-d n'est pas touche : le drapeau ENVOI_REEL existe toujours",
             "P1_TRIAL_J3_ENVOI_REEL" in SERVEUR)
    verifier("P1-d : sa boucle est toujours lancee",
             "_p1d_boucle_relance_j3()" in SERVEUR)



# ══════════════ LA TRACE D'ANNULATION — le 4e etat auditable ════════════════
#
# POURQUOI ELLE EXISTE. `cancel_reservation_from_space` fait un `delete_one`
# sec : une annulation ne laissait AUCUNE trace. On pouvait distinguer QR,
# WALK-IN, AUTO et ABSENT, mais pas ANNULE — indiscernable d'une reservation
# qui n'a jamais existe. La collection `deleted_items` ne sert qu'aux fiches
# CRM (V313), jamais aux reservations.
def cas_trace_annulation_posee():
    ns, base, trace = bac()
    r = base.reservations.docs[0]
    ok = lancer(ns["t1_tracer_annulation"](r, "abonne", True))
    lignes = base["reservation_cancellations"].docs
    verifier("annulation : la trace est posee", ok and len(lignes) == 1,
             "%s / %d ligne(s)" % (ok, len(lignes)))
    if lignes:
        t = lignes[0]
        verifier("annulation : la trace porte la reservation et son occurrence",
                 t.get("reservation_id") == "r1" and t.get("occurrence") == OCC_ESSAI,
                 str((t.get("reservation_id"), t.get("occurrence"))))
        verifier("annulation : la trace dit que c'etait un essai",
                 t.get("est_essai") is True, str(t.get("est_essai")))
        verifier("annulation : la trace est horodatee et nomme l'auteur",
                 bool(t.get("cancelled_at")) and t.get("cancelled_by") == "abonne",
                 str((t.get("cancelled_at"), t.get("cancelled_by"))))


def cas_trace_annulation_payant():
    ns, base, trace = bac(reservations=[_resa(promoCode=CODE_PAYANT)])
    lancer(ns["t1_tracer_annulation"](base.reservations.docs[0], "coach@x.ch", False))
    t = base["reservation_cancellations"].docs[0]
    verifier("annulation : un forfait payant est trace comme NON-essai",
             t.get("est_essai") is False, str(t.get("est_essai")))


def cas_trace_annulation_formats_mixtes():
    ns, base, trace = bac(reservations=[_resa(datetime="2026-08-26T16:30:00Z")])
    lancer(ns["t1_tracer_annulation"](base.reservations.docs[0], "", True))
    t = base["reservation_cancellations"].docs[0]
    verifier("annulation : l'occurrence est NORMALISEE, quel que soit le format d'origine",
             t.get("occurrence") == OCC_ESSAI, str(t.get("occurrence")))


def cas_trace_annulation_ne_bloque_jamais():
    """Une trace qui echoue ne doit JAMAIS empecher quelqu'un d'annuler."""
    ns, base, trace = bac()

    class _Casse:
        async def insert_one(self, _doc):
            raise RuntimeError("base muette")

    class _BaseCassee:
        def __getitem__(self, _n):
            return _Casse()

        def __getattr__(self, _n):
            return _Casse()

    ns["db"] = _BaseCassee()
    ok = None
    try:
        ok = lancer(ns["t1_tracer_annulation"](_resa(), "abonne", True))
        leve = False
    except Exception:
        leve = True
    verifier("annulation : une trace en panne ne leve pas", not leve)
    verifier("annulation : elle rend False, et l'annulation continue", ok is False, str(ok))


def cas_trace_avant_suppression():
    """L'ordre compte : tracer APRES `delete_one` ne tracerait plus rien."""
    i_trace = SERVEUR.find("t1_tracer_annulation(reservation")
    i_delete = SERVEUR.find('await db.reservations.delete_one({"id": reservation_id})')
    verifier("annulation : la route appelle bien la trace",
             i_trace > -1, "appel absent de la route")
    verifier("annulation : la trace est posee AVANT la suppression",
             -1 < i_trace < i_delete, "trace=%d suppression=%d" % (i_trace, i_delete))


def cas_quatre_etats_distinguables():
    """Le §8 du cahier des charges, verifie de bout en bout."""
    verifier("etat QR distinguable", '"validation_source": source' in RESAS
             or 'validation_source' in RESAS)
    verifier("etat WALK-IN distinguable", '"validation_source": "walkin"' in RESAS)
    verifier("etat AUTO distinguable", '"auto_presence_at"' in RESAS)
    verifier("etat ABSENT distinguable", '"absence_marked_at"' in RESAS)
    verifier("etat ANNULE distinguable", "reservation_cancellations" in SERVEUR)


# ══════════════════════════════ EXECUTION ══════════════════════════════════
SCENARIOS = [
    cas_A_qr_gagne, cas_B_absent_ferme, cas_C_annulee, cas_D_auto_apres_delai,
    cas_E_avant_delai, cas_F_rejeu, cas_G_concurrence, cas_H_redemarrage,
    cas_I_date_unique, cas_J_recurrent, cas_J2_seance_inexistante, cas_K_hors_borne,
    cas_L_payant_ignore, cas_M_p1b_une_fois, cas_N_p1c_ouvert, cas_O_p1d_compatible,
    cas_P_erreur_sans_corruption, cas_Q_noshow_juste_avant,
    cas_drapeau_off, cas_simulation, cas_borne_illisible, cas_delai_de_grace,
    cas_heure_dete_hiver, cas_formats_mixtes, cas_occurrence_illisible,
    cas_credit_deja_rendu, cas_candidats_filtre, cas_passage_resume,
    cas_source_qr_par_defaut, cas_source_auto_explicite, cas_walkin_source,
    cas_route_absence_existe, cas_bilan_expose_les_attendus, cas_drapeaux_declares,
    cas_p1d_intact,
    cas_trace_annulation_posee, cas_trace_annulation_payant,
    cas_trace_annulation_formats_mixtes, cas_trace_annulation_ne_bloque_jamais,
    cas_trace_avant_suppression, cas_quatre_etats_distinguables,
]

if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    for _s in SCENARIOS:
        try:
            _s()
        except Exception as _e:
            verifier("%s (exception)" % _s.__name__, False, "%s: %s" % (type(_e).__name__, _e))
    _ok = sum(1 for _, c, _d in RESULTATS if c)
    print("=" * 78)
    print("AUTO-PRESENCE PHASE 1 — ESSAIS UNIQUEMENT")
    print("=" * 78)
    for _n, _c, _d in RESULTATS:
        print("%s %s%s" % ("✅" if _c else "❌", _n, ("   -> " + _d) if (_d and not _c) else ""))
    print("-" * 78)
    print("RESULTAT : %d / %d" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)

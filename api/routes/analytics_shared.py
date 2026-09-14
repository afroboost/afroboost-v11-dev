# -*- coding: utf-8 -*-
"""ANALYTICS — LE MOTEUR, PUR. Aucune base, aucun réseau, aucune exception.

UNE TABLE DE FAITS, UNE FOIS. Tout KPI du cockpit se calcule depuis les mêmes
lignes : une ligne = UNE réservation de COURS, enrichie (occurrence locale,
jour de semaine, participant, essai, présence, valeur). Les produits de la
boutique n'y entrent jamais. Ce module ne DEVINE rien : quand une donnée n'est
pas là, la ligne le dit (`presence = inconnue`, `valeur = None`), et les KPI
portent leur couverture.

CE QUI EST RÉUTILISÉ, JAMAIS RÉÉCRIT :
  * `lot3f_valeur_presence` (shared.py) — la valeur d'une présence ;
  * `essai6_verdict` (shared.py) — la définition d'un essai gratuit ;
  * `lot1_occurrence_iso` (reservation_routes.py) — l'occurrence locale,
    INJECTÉE par l'appelant (`normaliser_occurrence`) : ce module reste pur.

CONVENTION DES JOURS : `courses.weekday` suit JavaScript — 0 = dimanche,
3 = mercredi. Python (`date.weekday()`) dit 0 = lundi. On convertit UNE fois,
ici (`weekday_js`), et un banc interdit toute inversion.

FUSEAU : les occurrences sont NAÏVES en heure de Zurich (convention du dépôt) ;
`createdAt` est en UTC. Le délai réservation → cours est calculé après avoir
ramené `createdAt` à Zurich.
"""
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    _ZURICH = ZoneInfo("Europe/Zurich")
except Exception:  # noqa: BLE001 — sans base de fuseaux, on reste en UTC et on le dit
    _ZURICH = None

from api.routes.shared import lot3f_valeur_presence, essai6_verdict

WEEKDAY_JS_DIMANCHE = 0
WEEKDAY_JS_MERCREDI = 3
NOMS_JOURS_JS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]

PRESENCE_CONFIRMEE = "confirmee"
PRESENCE_ABSENTE = "absente"
PRESENCE_INCONNUE = "inconnue"

CATEGORIES_DELAI = ["jour_meme", "1_jour", "2_3_jours", "4_7_jours", "plus_7_jours", "inconnu"]
CATEGORIES_FIDELITE = ["1", "2_5", "6_10", "plus_10"]

PERIODES = ("aujourdhui", "semaine", "mois", "annee", "perso")


# ─────────────────────────────── outils purs ───────────────────────────────

def cle_participant(email) -> str:
    """La clé d'identité de la phase 1 : e-mail normalisé (minuscules, sans espaces)."""
    return str(email or "").strip().lower()


def weekday_js_depuis_date(d) -> int:
    """Python (lundi = 0) -> JavaScript (dimanche = 0)."""
    return (d.weekday() + 1) % 7


def est_dimanche(weekday_js) -> bool:
    return weekday_js == WEEKDAY_JS_DIMANCHE


def est_mercredi(weekday_js) -> bool:
    return weekday_js == WEEKDAY_JS_MERCREDI


def parser_local(valeur):
    """« 2026-08-26T18:30:00 » (naïf Zurich) -> datetime naïf, ou None."""
    _v = str(valeur or "").strip()
    if len(_v) < 16:
        return None
    try:
        _dt = datetime.fromisoformat(_v.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if _dt.tzinfo is not None:
        return vers_local(_dt)
    return _dt


def vers_local(dt):
    """Un datetime avec fuseau -> naïf en heure de Zurich (UTC si zoneinfo absent)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    if _ZURICH is not None:
        return dt.astimezone(_ZURICH).replace(tzinfo=None)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def parser_utc(valeur):
    """`createdAt` (ISO, UTC ou avec fuseau) -> datetime naïf en heure de Zurich."""
    _v = str(valeur or "").strip()
    if not _v:
        return None
    try:
        _dt = datetime.fromisoformat(_v.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if _dt.tzinfo is None:
        _dt = _dt.replace(tzinfo=timezone.utc)
    return vers_local(_dt)


def categorie_delai(jours):
    """Anticipation, en jours calendaires (date du cours − date de réservation)."""
    if jours is None:
        return "inconnu"
    if jours <= 0:
        return "jour_meme"
    if jours == 1:
        return "1_jour"
    if jours <= 3:
        return "2_3_jours"
    if jours <= 7:
        return "4_7_jours"
    return "plus_7_jours"


def categorie_fidelite(n):
    n = int(n or 0)
    if n <= 1:
        return "1"
    if n <= 5:
        return "2_5"
    if n <= 10:
        return "6_10"
    return "plus_10"


def est_produit(reservation) -> bool:
    """Boutique / produit : jamais une séance. `isProduct`, ou aucun cours désigné."""
    _r = reservation if isinstance(reservation, dict) else {}
    if _r.get("isProduct") is True:
        return True
    if not _r.get("courseId") and not _r.get("courseName"):
        return True
    return False


def presence_de(reservation) -> str:
    """Une présence CONSTATÉE, une absence DÉCLARÉE, sinon on ne sait pas.

    Une réservation non validée n'est PAS une absence : la couverture du scan
    est partielle. Les inconnus restent inconnus.
    """
    _r = reservation if isinstance(reservation, dict) else {}
    if _r.get("validated") is True:
        return PRESENCE_CONFIRMEE
    if _r.get("absence_marked_at"):
        return PRESENCE_ABSENTE
    return PRESENCE_INCONNUE


def bornes_periode(periode, maintenant_local, du=None, au=None):
    """[debut, fin) en datetimes naïfs locaux. `perso` exige `du` et `au` (YYYY-MM-DD)."""
    _p = str(periode or "mois").strip().lower()
    _now = maintenant_local
    _jour = _now.replace(hour=0, minute=0, second=0, microsecond=0)
    if _p == "aujourdhui":
        return _jour, _jour + timedelta(days=1)
    if _p == "semaine":
        _lundi = _jour - timedelta(days=_jour.weekday())
        return _lundi, _lundi + timedelta(days=7)
    if _p == "mois":
        _d = _jour.replace(day=1)
        _f = (_d.replace(year=_d.year + 1, month=1) if _d.month == 12
              else _d.replace(month=_d.month + 1))
        return _d, _f
    if _p == "annee":
        _d = _jour.replace(month=1, day=1)
        return _d, _d.replace(year=_d.year + 1)
    # perso
    try:
        _d = datetime.fromisoformat(str(du)[:10])
        _f = datetime.fromisoformat(str(au)[:10]) + timedelta(days=1)
    except (TypeError, ValueError):
        return None, None
    if _f <= _d:
        return None, None
    return _d, _f


# ─────────────────────────────── la table de faits ─────────────────────────

def construire_faits(reservations, cours_par_id=None, forfaits_par_id=None,
                     forfaits_par_code=None, codes_par_code=None, offres_par_id=None,
                     memberships_par_email=None, normaliser_occurrence=None) -> dict:
    """Les réservations de COURS -> lignes de faits. Rend {faits, ecartees, qualite}.

    `normaliser_occurrence` : la fonction du dépôt (`lot1_occurrence_iso`),
    injectée. Sans elle, `parser_local` sert (même convention, sans conversion
    de fuseau exotique).
    """
    cours_par_id = cours_par_id or {}
    forfaits_par_id = forfaits_par_id or {}
    forfaits_par_code = forfaits_par_code or {}
    codes_par_code = codes_par_code or {}
    offres_par_id = offres_par_id or {}
    memberships_par_email = memberships_par_email or {}
    _norm = normaliser_occurrence or (lambda v: (parser_local(v).strftime("%Y-%m-%dT%H:%M:%S")
                                                 if parser_local(v) else ""))
    faits, ecartees = [], {"produits": 0, "sans_occurrence": 0}
    sans_email, noms_par_email = 0, {}
    for r in (reservations or []):
        if not isinstance(r, dict):
            continue
        if est_produit(r):
            ecartees["produits"] += 1
            continue
        _occ_iso = _norm(r.get("datetime"))
        _occ = parser_local(_occ_iso) if _occ_iso else None
        if _occ is None:
            ecartees["sans_occurrence"] += 1
            continue
        _cle = cle_participant(r.get("userEmail"))
        if not _cle:
            sans_email += 1
        _nom = str(r.get("userName") or "").strip()
        if _cle and _nom:
            noms_par_email.setdefault(_cle, set()).add(_nom.lower())
        _cours = cours_par_id.get(str(r.get("courseId") or ""), {}) or {}
        _wd = weekday_js_depuis_date(_occ.date())
        _cree = parser_utc(r.get("createdAt"))
        _delai_j = (_occ.date() - _cree.date()).days if _cree else None
        _code = str(r.get("discountCode") or r.get("promoCode") or "").strip().upper()
        _sid = str(r.get("subscriptionId") or "").strip()
        _forfait = forfaits_par_id.get(_sid) if _sid else None
        if _forfait is None and _code:
            _forfait = forfaits_par_code.get(_code)
        _code_doc = codes_par_code.get(_code) if _code else None
        _offre = offres_par_id.get(str((_forfait or {}).get("offer_id") or "")) if _forfait else None
        _essai = essai6_verdict(_code_doc, _forfait, _offre)
        _val = lot3f_valeur_presence(r, _forfait, _code_doc, _occ_iso)
        _offre_nom = str((_forfait or {}).get("offer_name") or r.get("offerName") or "").strip()
        _membership = memberships_par_email.get(_cle) if _cle else None
        faits.append({
            "reservation_id": r.get("id") or r.get("reservationCode") or "",
            "participant_key": _cle,
            "email": _cle,
            "nom": _nom,
            "coach_id": str(r.get("coach_id") or "").strip().lower(),
            "course_id": str(r.get("courseId") or ""),
            "course_name": str(r.get("courseName") or _cours.get("name") or ""),
            "occurrence": _occ_iso,
            "occurrence_dt": _occ,
            "weekday_js": _wd,
            "jour": NOMS_JOURS_JS[_wd],
            "mercredi": est_mercredi(_wd),
            "dimanche": est_dimanche(_wd),
            "lieu": str(_cours.get("locationName") or _cours.get("location") or ""),
            "created_at": _cree.strftime("%Y-%m-%dT%H:%M:%S") if _cree else "",
            "created_dt": _cree,
            "delai_jours": _delai_j,
            "delai_categorie": categorie_delai(_delai_j),
            "essai": bool(_essai),
            "presence": presence_de(r),
            "prix": r.get("price") if r.get("price") is not None else r.get("totalPrice"),
            "valeur": _val.get("valeur"),
            "valeur_statut": _val.get("statut_valeur"),
            "type_offre": _offre_nom,
            "pulse_x10": "pulse" in _offre_nom.lower() and "x10" in _offre_nom.lower().replace(" ", ""),
            "carte_membre": bool(_membership),
            "source": str(r.get("source") or ""),
        })
    conflits = sum(1 for _n in noms_par_email.values() if len(_n) > 1)
    return {"faits": faits, "ecartees": ecartees,
            "qualite": {"sans_email": sans_email, "conflits_nom_email": conflits}}


# ─────────────────────────────── les KPI ───────────────────────────────────

def _dans(fait, debut, fin):
    return fait["occurrence_dt"] is not None and debut <= fait["occurrence_dt"] < fin


def _cle_serie(dt, granularite):
    if granularite == "jour":
        return dt.strftime("%Y-%m-%d")
    if granularite == "semaine":
        _lundi = dt - timedelta(days=dt.weekday())
        return _lundi.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m")


def calculer_kpi(faits, debut, fin, granularite="jour") -> dict:
    """Les KPI de la phase 1, depuis les faits (TOUT l'historique) et une période.

    « Nouveau » = première réservation de cours de ce participant, toutes dates
    confondues, dans la période. « Récurrent » = présent dans la période avec
    au moins une réservation AVANT la période. Fidélité = participations
    cumulées (historique) des participants vus dans la période.
    """
    faits = [f for f in (faits or []) if f.get("occurrence_dt") is not None]
    periode = [f for f in faits if _dans(f, debut, fin)]

    premiere = {}
    total_hist = {}
    for f in faits:
        k = f["participant_key"]
        if not k:
            continue
        total_hist[k] = total_hist.get(k, 0) + 1
        if k not in premiere or f["occurrence_dt"] < premiere[k]:
            premiere[k] = f["occurrence_dt"]

    participants = {f["participant_key"] for f in periode if f["participant_key"]}
    nouveaux = {k for k in participants if debut <= premiere[k] < fin}
    recurrents = {k for k in participants
                  if any(x["participant_key"] == k and x["occurrence_dt"] < debut for x in faits)}
    seances = {(f["course_id"] or f["course_name"], f["occurrence"]) for f in periode}
    mercredi = [f for f in periode if f["mercredi"]]
    dimanche = [f for f in periode if f["dimanche"]]
    seances_mer = {(f["course_id"] or f["course_name"], f["occurrence"]) for f in mercredi}
    seances_dim = {(f["course_id"] or f["course_name"], f["occurrence"]) for f in dimanche}

    heures = {str(h).zfill(2): 0 for h in range(24)}
    jours_resa = {n: 0 for n in NOMS_JOURS_JS}
    delais = {c: 0 for c in CATEGORIES_DELAI}
    delais_valides = []
    for f in periode:
        if f["created_dt"] is not None:
            heures[f["created_dt"].strftime("%H")] += 1
            jours_resa[NOMS_JOURS_JS[weekday_js_depuis_date(f["created_dt"].date())]] += 1
        delais[f["delai_categorie"]] += 1
        if f["delai_jours"] is not None:
            delais_valides.append(max(0, f["delai_jours"]))

    fidelite = {c: 0 for c in CATEGORIES_FIDELITE}
    for k in participants:
        fidelite[categorie_fidelite(total_hist.get(k, 0))] += 1

    presence = {PRESENCE_CONFIRMEE: 0, PRESENCE_ABSENTE: 0, PRESENCE_INCONNUE: 0}
    for f in periode:
        presence[f["presence"]] += 1
    n = len(periode)
    connues = presence[PRESENCE_CONFIRMEE] + presence[PRESENCE_ABSENTE]

    serie = {}
    for f in periode:
        c = _cle_serie(f["occurrence_dt"], granularite)
        s = serie.setdefault(c, {"periode": c, "reservations": 0, "participants": set(), "essais": 0})
        s["reservations"] += 1
        if f["participant_key"]:
            s["participants"].add(f["participant_key"])
        if f["essai"]:
            s["essais"] += 1
    evolution = [{"periode": k, "reservations": v["reservations"],
                  "participants": len(v["participants"]), "essais": v["essais"]}
                 for k, v in sorted(serie.items())]

    valeurs_connues = sum(1 for f in periode if f["valeur"] is not None)
    essais = sum(1 for f in periode if f["essai"])

    def _taux(a, b):
        return round(100.0 * a / b, 1) if b else None

    return {
        "periode": {"debut": debut.strftime("%Y-%m-%d"), "fin_exclue": fin.strftime("%Y-%m-%d"),
                    "granularite": granularite},
        "participants": {
            "reservations_cours": n,
            "uniques": len(participants),
            "nouveaux": len(nouveaux),
            "recurrents": len(recurrents),
            "sans_email": sum(1 for f in periode if not f["participant_key"]),
        },
        "cours": {
            "seances": len(seances),
            "moyenne_par_seance": round(n / len(seances), 2) if seances else None,
            "mercredi": {"reservations": len(mercredi), "seances": len(seances_mer),
                         "moyenne": round(len(mercredi) / len(seances_mer), 2) if seances_mer else None,
                         "participants": len({f["participant_key"] for f in mercredi if f["participant_key"]})},
            "dimanche": {"reservations": len(dimanche), "seances": len(seances_dim),
                         "moyenne": round(len(dimanche) / len(seances_dim), 2) if seances_dim else None,
                         "participants": len({f["participant_key"] for f in dimanche if f["participant_key"]})},
            "autres_jours": n - len(mercredi) - len(dimanche),
        },
        "reservation": {
            "par_heure": heures,
            "par_jour": jours_resa,
            "delai_moyen_jours": round(sum(delais_valides) / len(delais_valides), 1) if delais_valides else None,
            "anticipation": delais,
        },
        "fidelite": fidelite,
        "essais": {"detectes": essais},
        "presence": {
            "confirmee": presence[PRESENCE_CONFIRMEE],
            "absente": presence[PRESENCE_ABSENTE],
            "inconnue": presence[PRESENCE_INCONNUE],
            "couverture_pct": _taux(connues, n),
            "libelle": "%d vérifiées sur %d réservations" % (connues, n),
        },
        "evolution": evolution,
        "qualite": {
            "presence": "fiable" if n and connues == n else ("partiel" if connues else "inconnu"),
            "valeur_financiere": "fiable" if n and valeurs_connues == n else ("partiel" if valeurs_connues else "inconnu"),
            "valeurs_connues": valeurs_connues,
            "identite": "partiel" if any(not f["participant_key"] for f in periode) else "fiable",
        },
    }

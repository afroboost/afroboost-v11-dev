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

# ─────────────────── TRACKING 2B — l'origine marketing d'un fait ──────────────
#
# UNE seule origine officielle : `attribution.first` (M2-A), telle qu'écrite sur
# la réservation / la souscription / la transaction (ou aplatie dans les
# metadata Stripe : `attribution_first_source`, …). Les champs techniques
# `source` (website, subscriber_space, stripe_auto…) ne sont JAMAIS lus ici.
SOURCE_INCONNUE = "inconnue"
SOURCE_PARTENAIRE = "partenaire"


def attribution_first(*docs):
    """(source, content) de la PREMIÈRE touche connue parmi les documents fournis
    (chacun : un dict portant `attribution` ou des metadata plates). ("", "") si aucune."""
    for d in docs:
        if not isinstance(d, dict):
            continue
        bloc = d.get("attribution") if isinstance(d.get("attribution"), dict) else None
        first = (bloc or {}).get("first") if isinstance((bloc or {}).get("first"), dict) else None
        if first and _texte(first.get("source")):
            return _texte(first.get("source")).lower(), _texte(first.get("content")).lower()
        meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else d
        if isinstance(meta, dict) and _texte(meta.get("attribution_first_source")):
            return _texte(meta.get("attribution_first_source")).lower(), _texte(meta.get("attribution_first_content")).lower()
    return "", ""


def libelle_source(source, content=""):
    """« Partenaire — restaurant-x » pour un partenaire, sinon la source, sinon « inconnue »."""
    src = _texte(source).lower() or SOURCE_INCONNUE
    if src == SOURCE_PARTENAIRE and _texte(content):
        return "Partenaire — %s" % _texte(content)
    return src


def cle_source(source, content=""):
    src = _texte(source).lower() or SOURCE_INCONNUE
    return "%s:%s" % (src, _texte(content).lower()) if src == SOURCE_PARTENAIRE and _texte(content) else src


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


def mois_suivant(d):
    """Le premier jour du mois qui suit `d` (naïf)."""
    _d = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return _d.replace(year=_d.year + 1, month=1) if _d.month == 12 else _d.replace(month=_d.month + 1)


def bornes_periode(periode, maintenant_local, du=None, au=None, mois=None):
    """[debut, fin) en datetimes naïfs locaux. `perso` exige `du` et `au` (YYYY-MM-DD).

    `mois` (YYYY-MM, phase 3) : avec `periode=mois`, LE mois demandé plutôt que
    le mois courant — le bilan Association regarde surtout le mois écoulé.
    Avec `periode=annee`, `mois=YYYY-MM` désigne l'année de ce mois.
    """
    _p = str(periode or "mois").strip().lower()
    _now = maintenant_local
    _jour = _now.replace(hour=0, minute=0, second=0, microsecond=0)
    _m = str(mois or "").strip()
    if _m:
        try:
            _jour = datetime.strptime(_m[:7], "%Y-%m")
        except ValueError:
            return None, None
    if _p == "aujourdhui":
        return _jour, _jour + timedelta(days=1)
    if _p == "semaine":
        _lundi = _jour - timedelta(days=_jour.weekday())
        return _lundi, _lundi + timedelta(days=7)
    if _p == "mois":
        _d = _jour.replace(day=1)
        return _d, mois_suivant(_d)
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
            # TRACKING 2B : l'origine marketing (first-touch) de la réservation,
            # jamais le canal technique `source` ci-dessus.
            "attribution_source": attribution_first(r)[0],
            "attribution_content": attribution_first(r)[1],
            # Phase 2 : le lien vers le DROIT (code, souscription) — le funnel
            # d'essai rattache les réservations à l'essai par ces deux clés,
            # comme le funnel existant (`subscriptionId` OU code).
            "code": _code,
            "subscription_id": _sid,
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


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2 — ACHATS, ABONNEMENTS, ESSAIS & CONVERSION. Toujours pur.
# ═══════════════════════════════════════════════════════════════════════════
#
# UN ACHAT = COMPTÉ UNE SEULE FOIS. L'unité n'est ni la souscription, ni la
# fiche code, ni la transaction : c'est LE DROIT D'ACCÈS (le code, en
# majuscules), parce que c'est lui que toutes les sources décrivent chacune à
# leur façon (LOT A : « discount_codes fait foi »).
#
#   1. Tous les documents `subscriptions` (hors `superseded`, qui sont des
#      remplacements d'un même droit) et toutes les fiches `discount_codes`
#      portant le même code = UN achat. La fiche retenue : `canonical` >
#      déclaration d'encaissement > session / transaction Stripe >
#      `stripe_amount` > la première.
#   2. Le montant vient de `a_finance_du_droit(souscription, fiche)` — LA règle
#      déjà utilisée par Réservations, Transactions et le Bilan de séance :
#      encaissement DÉCLARÉ (`montant_encaisse` + `origine_paiement`, sur la
#      souscription puis la fiche) → `stripe_amount` adossé à un `session_id` →
#      `total_paid` adossé à un `transaction_id` → gratuité prouvée → [2 bis,
#      propre à ce moteur] `amount_total` de la transaction JUMELLE (même
#      session) → montants déclarés NON prouvés (`renewal_price`,
#      `stripe_amount` seul, `offer_price`) → inconnu. Jamais une somme de
#      plusieurs sources : la première preuve gagne, les autres sont ignorées.
#   3. Une `payment_transactions` `paid` est RETIRÉE si son `session_id` est le
#      `session_id` ou le `transaction_id` d'une fiche : le droit porte déjà cet
#      achat (LOT 3C-0C). Une transaction à ZÉRO sans jumeau n'est pas un achat
#      (rien n'est encaissé ; la gratuité est comptée sur son droit). Le reste
#      = achats DIRECTS, prouvés seulement par `amount_total` (centimes Stripe).
#   4. `memberships` n'est JAMAIS une recette : l'adhésion est adossée à la
#      souscription qui l'a payée (`subscription_id`). C'est un STATUT.
#   5. Jamais de rapprochement par montant, nom ou date.
#
# QUALITÉ d'un achat : `fiable` = montant prouvé ; `partiel` = montant déclaré
# mais non prouvé ; `inconnu` = aucun montant. Le CA encaissé n'additionne que
# le FIABLE. Les remboursements n'existent dans aucune source : « non
# disponibles historiquement », jamais déduits.
#
# MOYEN DE PAIEMENT : `payment_methods` (la liste `['card','twint']` proposée
# au checkout) n'est JAMAIS lue. Un encaissement Stripe sans moyen unitaire
# enregistré est « Stripe — moyen non déterminé » (qualité partielle).
#
# ESSAIS : `essai6_verdict`, la règle de la phase 1 — aucune seconde règle.
# CONVERSION : la convention du funnel existant (`/coach/funnel/free-trial`)
# est reprise telle quelle — la cohorte = les essais ACCORDÉS dans la période,
# suivis où qu'ils en soient (AUCUNE fenêtre de 30 jours) ; CONFIRMÉE =
# `converted_at` (marqueur atomique ESSAI-2, mesuré depuis le 17/08/2026) ;
# PROBABLE = un achat non-essai du même `participant_key` daté APRÈS l'essai.
#
# RENOUVELLEMENTS : CONFIRMÉ = preuve explicite (`last_renewal_date` ou un
# marqueur `renewed_AAAAMMJJ` posé par V195) ; PROBABLE = nouveau droit
# multi-séances du même participant APRÈS un droit épuisé/expiré, ou nouvelle
# fiche d'un même code après une fiche épuisée ; INCONNU = plusieurs fiches
# vivantes d'un même code sans ordre lisible. Le KPI principal = CONFIRMÉS.

from api.routes.shared import (  # noqa: E402 — après le socle, volontairement
    a_finance_du_droit, a_montant_transaction, b_normaliser_origine,
    B_ORIGINES_MANUELLES,
)

CATEGORIE_PULSE = "pulse_x10"
CATEGORIE_ABONNEMENT = "abonnement"
CATEGORIE_CARTE = "carte_membre"
CATEGORIE_ESSAI = "essai"
CATEGORIE_AUTRE = "autre"
CATEGORIES_DROIT = (CATEGORIE_PULSE, CATEGORIE_ABONNEMENT, CATEGORIE_CARTE, CATEGORIE_ESSAI, CATEGORIE_AUTRE)

QUALITE_FIABLE = "fiable"
QUALITE_PARTIEL = "partiel"
QUALITE_INCONNU = "inconnu"

MOYEN_STRIPE_INDETERMINE = "stripe_indetermine"
MOYENS = ("stripe_card", "stripe_twint", MOYEN_STRIPE_INDETERMINE, "twint", "virement", "especes",
          "mobile_money", "offert", "inconnu")
CANAUX = ("stripe", "manuel", "offert", "inconnu")

RENOUV_CONFIRME = "confirme"
RENOUV_PROBABLE = "probable"
RENOUV_INCONNU = "inconnu"
EXPIRATION_PROCHE_JOURS = 30
RENOUV_LIBELLE_PROBABLES = "Renouvellements probables — non comptés dans le KPI principal"
# Le NOM d'un code n'est jamais une preuve : rien n'est filtré sur « test »,
# « BASS », « GROUP »… — on le dit, et on ne supprime rien.
RENOUV_AVERTISSEMENT_TEST = ("Certains droits probables peuvent provenir de comptes ou codes de test "
                             "historiques (aucun filtrage par nom, aucune donnée supprimée).")
REMBOURSEMENTS_LIBELLE = "Remboursements non disponibles historiquement"

CONVENTION_CONVERSION = {
    "ancre": "date d'octroi de l'essai (cohorte), comme le funnel /coach/funnel/free-trial",
    "fenetre": "aucune — l'essai est suivi où qu'il en soit aujourd'hui",
    "confirmee": "converted_at (marqueur atomique ESSAI-2, mesuré depuis le 2026-08-17)",
    "probable": "premier achat non-essai du même participant_key daté après l'essai",
}


def _nombre(v):
    try:
        return float(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _texte(v):
    return str(v or "").strip()


def categorie_droit(offer_name, offre=None, essai=False) -> str:
    """La classification canonique d'un droit, variantes historiques comprises.

    `essai` (verdict `essai6_verdict`) prime : un essai est un essai quel que
    soit le libellé. Puis le LIBELLÉ de l'offre : « PULSE x10 cours », « PULSE
    x10 cours (Membres) », « Membres » (le pack membre à 10 séances) → Pulse ;
    « Abonnement » → abonnement. Sinon l'offre elle-même : un pack ≥ 10 séances
    est un Pulse. Tout le reste (cours à l'unité, billets, codes nommés à la
    main) → autre. Le nombre de séances n'est jamais lu sur la souscription :
    `total_sessions` grandit avec les reconductions.
    """
    if essai:
        return CATEGORIE_ESSAI
    _n = _texte(offer_name).lower().replace(" ", "")
    _o = offre if isinstance(offre, dict) else {}
    _on = _texte(_o.get("name")).lower().replace(" ", "")
    if "pulse" in _n or "pulse" in _on or _n == "membres" or _on == "membres":
        return CATEGORIE_PULSE
    if "abonnement" in _n or "abonnement" in _on:
        return CATEGORIE_ABONNEMENT
    try:
        if int(_o.get("pack_sessions") or 0) >= 10:
            return CATEGORIE_PULSE
    except (TypeError, ValueError):
        pass
    return CATEGORIE_AUTRE


def choisir_fiche_code(fiches) -> dict:
    """Parmi plusieurs fiches `discount_codes` d'un même code, LA fiche du droit."""
    _l = [f for f in (fiches or []) if isinstance(f, dict)]
    if not _l:
        return {}

    def _rang(f):
        _decl = b_normaliser_origine(f.get("origine_paiement")) and _nombre(f.get("montant_encaisse")) is not None
        return (0 if f.get("canonical") is True else 1,
                0 if _decl else 1,
                0 if (f.get("session_id") or f.get("transaction_id")) else 1,
                0 if _nombre(f.get("stripe_amount")) is not None else 1)
    return sorted(_l, key=_rang)[0]


def moyen_de_paiement(fin, paiement=None):
    """(moyen, canal, qualité) d'un achat — sans jamais lire `payment_methods`."""
    _fin = fin if isinstance(fin, dict) else {}
    _p = paiement if isinstance(paiement, dict) else {}
    if _fin.get("montant") is None:
        return "inconnu", "inconnu", QUALITE_INCONNU
    _origine = b_normaliser_origine(_fin.get("origine_paiement"))
    _canal_stripe = (_fin.get("montant_source") in ("stripe", "checkout", "transaction") or _origine == "stripe"
                     or bool(_p.get("session_id")))
    if _fin.get("gratuit"):
        return "offert", "offert", QUALITE_FIABLE if _fin.get("montant_prouve") else QUALITE_PARTIEL
    if _origine in B_ORIGINES_MANUELLES or _origine == "mobile_money":
        return _origine, ("stripe" if _canal_stripe else "manuel"), \
            (QUALITE_FIABLE if _fin.get("montant_prouve") else QUALITE_PARTIEL)
    if _canal_stripe:
        _pm = _p.get("payment_method")
        if isinstance(_pm, str) and _pm.strip().lower() in ("card", "twint"):
            return "stripe_" + _pm.strip().lower(), "stripe", QUALITE_FIABLE
        return MOYEN_STRIPE_INDETERMINE, "stripe", QUALITE_PARTIEL
    return "inconnu", "inconnu", QUALITE_PARTIEL if _fin.get("montant") is not None else QUALITE_INCONNU


def _date_de_renouvellement_confirme(sub):
    """La date de la preuve explicite V195, ou None."""
    _d = parser_utc(sub.get("last_renewal_date"))
    if _d:
        return _d
    for _m in (sub.get("renewal_warnings_sent") or []):
        _m = _texte(_m)
        if _m.startswith("renewed_") and len(_m) >= 16:
            try:
                return datetime.strptime(_m[8:16], "%Y%m%d")
            except ValueError:
                continue
    return None


def construire_achats(subscriptions, fiches_codes, paiements, offres_par_id=None, maintenant=None) -> dict:
    """Les sources financières -> UNE ligne par achat. Rend {achats, ecartes, qualite}.

    `fiches_codes` : la liste brute des `discount_codes` (les doublons de code
    sont résolus ici). `paiements` : `payment_transactions`, tous statuts (les
    `pending` sont rendus à part, jamais comme des achats).
    """
    offres_par_id = offres_par_id or {}
    maintenant = maintenant or datetime.now()
    ecartes = {"souscriptions_superseded": 0, "paiements_jumeaux": 0, "paiements_zero_sans_jumeau": 0,
               "paiements_non_payes": 0}

    fiches_par_code = {}
    for f in (fiches_codes or []):
        if isinstance(f, dict) and _texte(f.get("code")):
            fiches_par_code.setdefault(_texte(f.get("code")).upper(), []).append(f)
    subs_par_code = {}
    for s in (subscriptions or []):
        if not isinstance(s, dict):
            continue
        if _texte(s.get("status")).lower() == "superseded":
            ecartes["souscriptions_superseded"] += 1
            continue
        subs_par_code.setdefault(_texte(s.get("code")).upper(), []).append(s)

    paiements_par_session = {}
    pending = []
    for p in (paiements or []):
        if not isinstance(p, dict):
            continue
        _st = _texte(p.get("payment_status")).lower()
        if _st == "paid":
            paiements_par_session[_texte(p.get("session_id"))] = p
        elif _st == "pending":
            pending.append(p)
        else:
            ecartes["paiements_non_payes"] += 1

    achats = []
    sessions_portees = set()
    for code in sorted(set(fiches_par_code) | set(subs_par_code)):
        fiche = choisir_fiche_code(fiches_par_code.get(code))
        subs = sorted(subs_par_code.get(code, []),
                      key=lambda s: (0 if (b_normaliser_origine(s.get("origine_paiement"))
                                           and _nombre(s.get("montant_encaisse")) is not None) else 1,
                                     _texte(s.get("created_at"))))
        principal = subs[0] if subs else {}
        if not code and not principal:
            continue
        for _k in ("session_id", "transaction_id"):
            if _texte(fiche.get(_k)):
                sessions_portees.add(_texte(fiche.get(_k)))
        paiement = paiements_par_session.get(_texte(fiche.get("session_id"))) \
            or paiements_par_session.get(_texte(fiche.get("transaction_id")))
        offre = offres_par_id.get(_texte(principal.get("offer_id"))) if principal else None
        essai = essai6_verdict(fiche or None, principal or None, offre)
        fin = a_finance_du_droit(principal or None, fiche or None)
        if not fin.get("montant_prouve") and paiement:
            # 2 bis. La transaction JUMELLE (même session) porte `amount_total`,
            # les centimes Stripe : c'est une preuve, prise AVANT tout montant
            # déclaré non prouvé. Le droit reste l'unité ; la transaction n'est
            # pas comptée une seconde fois (elle est retirée plus bas).
            _m_tx, _p_tx = a_montant_transaction(paiement)
            if _p_tx and _nombre(_m_tx) is not None:
                fin.update(montant=_nombre(_m_tx), montant_prouve=True, montant_source="transaction",
                           origine_paiement=fin.get("origine_paiement") or "stripe", gratuit=(_nombre(_m_tx) == 0))
        moyen, canal, q_moyen = moyen_de_paiement(fin, paiement)
        dates = [parser_utc(s.get("created_at")) for s in subs]
        dates = [d for d in dates if d]
        date_dt = min(dates) if dates else parser_utc(fiche.get("created_at") or fiche.get("createdAt"))
        expirations = [parser_utc(s.get("expires_at")) for s in subs]
        expirations = [d for d in expirations if d]
        expire_dt = max(expirations) if expirations else parser_utc(fiche.get("expiresAt") or fiche.get("expires_at"))
        if subs:
            actif = any(_texte(s.get("status")).lower() == "active"
                        and (parser_utc(s.get("expires_at")) is None or parser_utc(s.get("expires_at")) >= maintenant)
                        for s in subs)
            consomme = any(_texte(s.get("status")).lower() in ("completed", "expired")
                           or (_nombre(s.get("remaining_sessions")) == 0) for s in subs)
            statuts = {_texte(s.get("status")).lower() for s in subs}
        else:
            actif = bool(fiche.get("active")) and (expire_dt is None or expire_dt >= maintenant)
            consomme = (_nombre(fiche.get("maxUses")) or 0) > 0 and (_nombre(fiche.get("used")) or 0) >= (_nombre(fiche.get("maxUses")) or 0)
            statuts = {"code_seul"}
        renouv_dates = [_date_de_renouvellement_confirme(s) for s in subs]
        renouv_dates = [d for d in renouv_dates if d]
        montant = _nombre(fin.get("montant"))
        prouve = bool(fin.get("montant_prouve")) and montant is not None
        qualite = QUALITE_FIABLE if prouve else (QUALITE_PARTIEL if montant is not None else QUALITE_INCONNU)
        achats.append({
            "cle": "droit:" + (code or _texte(principal.get("id"))),
            "type": "droit",
            "code": code,
            "categorie": categorie_droit(principal.get("offer_name") or fiche.get("name"), offre, essai),
            "offre": _texte(principal.get("offer_name") or (offre or {}).get("name") or fiche.get("name")),
            "participant_key": cle_participant(principal.get("email") or fiche.get("assignedEmail")),
            "coach_id": _texte(principal.get("coach_id") or fiche.get("coach_id")).lower(),
            "date_dt": date_dt,
            "date": date_dt.strftime("%Y-%m-%d") if date_dt else "",
            "montant": montant,
            "montant_prouve": prouve,
            "montant_source": fin.get("montant_source") or "",
            "origine": b_normaliser_origine(fin.get("origine_paiement")),
            "moyen": moyen, "canal": canal, "moyen_qualite": q_moyen,
            "gratuit": bool(fin.get("gratuit")) and prouve,
            "qualite": qualite,
            "essai": bool(essai),
            "actif": bool(actif),
            "consomme": bool(consomme),
            "expire_dt": expire_dt,
            "statuts": sorted(statuts),
            "seances": fin.get("seances_achetees"),
            "fiches": len(subs),
            "fiches_dates": sorted(dates),
            "fiches_consommees_avant": sorted(parser_utc(s.get("created_at")) for s in subs
                                              if _texte(s.get("status")).lower() == "completed"
                                              and parser_utc(s.get("created_at"))),
            "sub_ids": [_texte(s.get("id")) for s in subs if _texte(s.get("id"))],
            "renouvellement_confirme_dates": sorted(renouv_dates),
            "converted_dt": min([d for d in (parser_utc(s.get("converted_at")) for s in subs) if d], default=None),
            # TRACKING 2B : la first-touch portée par le droit (souscription, fiche,
            # transaction jumelle) — la règle « un achat = une ligne » est intacte.
            "attribution_source": attribution_first(*subs, fiche, paiement or {})[0],
            "attribution_content": attribution_first(*subs, fiche, paiement or {})[1],
        })

    for sid, p in paiements_par_session.items():
        if sid and sid in sessions_portees:
            ecartes["paiements_jumeaux"] += 1
            continue
        montant, prouve = a_montant_transaction(p)
        montant = _nombre(montant)
        if not montant:
            ecartes["paiements_zero_sans_jumeau"] += 1
            continue
        fin = {"montant": montant, "montant_prouve": bool(prouve), "montant_source": "stripe" if prouve else "checkout",
               "origine_paiement": "stripe", "gratuit": False}
        moyen, canal, q_moyen = moyen_de_paiement(fin, p)
        meta = p.get("metadata") if isinstance(p.get("metadata"), dict) else {}
        date_dt = parser_utc(p.get("created_at"))
        achats.append({
            "cle": "paiement:" + _texte(p.get("id") or sid),
            "type": "paiement",
            "code": "",
            "categorie": CATEGORIE_AUTRE,
            "offre": _texte(p.get("product_name") or meta.get("product_name")),
            "participant_key": cle_participant(p.get("customer_email") or meta.get("customer_email")),
            "coach_id": _texte(p.get("coach_id")).lower(),
            "date_dt": date_dt,
            "date": date_dt.strftime("%Y-%m-%d") if date_dt else "",
            "montant": montant, "montant_prouve": bool(prouve),
            "montant_source": fin["montant_source"], "origine": "stripe",
            "moyen": moyen, "canal": canal, "moyen_qualite": q_moyen,
            "gratuit": False,
            "qualite": QUALITE_FIABLE if prouve else QUALITE_PARTIEL,
            "essai": False, "actif": False, "consomme": False, "expire_dt": None, "statuts": ["paiement"],
            "seances": None, "fiches": 0, "fiches_dates": [], "fiches_consommees_avant": [], "sub_ids": [],
            "renouvellement_confirme_dates": [], "converted_dt": None,
            "attribution_source": attribution_first(p)[0], "attribution_content": attribution_first(p)[1],
        })

    en_attente = []
    for p in pending:
        m, _ = a_montant_transaction(p)
        en_attente.append({"date_dt": parser_utc(p.get("created_at")), "montant": _nombre(m),
                           "coach_id": _texte(p.get("coach_id")).lower()})

    return {
        "achats": achats,
        "en_attente": en_attente,
        "ecartes": ecartes,
        "qualite": {
            "droits_multi_fiches": sum(1 for a in achats if a["fiches"] > 1),
            "sans_date": sum(1 for a in achats if a["date_dt"] is None),
            "sans_coach": sum(1 for a in achats if not a["coach_id"]),
            "essais_avec_montant": sum(1 for a in achats if a["essai"] and (a["montant"] or 0) > 0),
        },
    }


def _somme(vals):
    return round(sum(vals), 2)


def _taux(a, b):
    return round(100.0 * a / b, 1) if b else None


def _niveau(total, fiables, partiels):
    if total and fiables == total:
        return QUALITE_FIABLE
    return QUALITE_PARTIEL if (fiables or partiels) else QUALITE_INCONNU


def _dans_dt(dt, debut, fin):
    return dt is not None and debut <= dt < fin


def _mediane(vals):
    _v = sorted(vals)
    if not _v:
        return None
    _m = len(_v) // 2
    return _v[_m] if len(_v) % 2 else round((_v[_m - 1] + _v[_m]) / 2.0, 1)


def calculer_kpi_finance(achats, en_attente, memberships, faits, debut, fin, granularite="jour",
                         maintenant=None, cours_filtre="") -> dict:
    """Les KPI de la phase 2 : revenus, abonnements, essais & conversion.

    Tout est GLOBAL période/coach — sauf « valeur par cours », calculée sur les
    FAITS (réservations valorisées au tarif figé) et donc soumise au filtre
    cours. Le périmètre de chaque section est rendu avec elle.
    """
    maintenant = maintenant or datetime.now()
    achats = [a for a in (achats or []) if isinstance(a, dict)]
    periode = [a for a in achats if _dans_dt(a["date_dt"], debut, fin)]
    perimetre_global = "global période/coach — le filtre cours ne s'applique pas"

    # ── REVENUS ─────────────────────────────────────────────────────────────
    fiables = [a for a in periode if a["qualite"] == QUALITE_FIABLE]
    partiels = [a for a in periode if a["qualite"] == QUALITE_PARTIEL]
    inconnus = [a for a in periode if a["qualite"] == QUALITE_INCONNU]
    payants = [a for a in fiables if (a["montant"] or 0) > 0]
    gratuits = [a for a in fiables if a["gratuit"]]
    ca = _somme(a["montant"] for a in payants)
    acheteurs = {a["participant_key"] for a in payants if a["participant_key"]}
    par_moyen = {m: {"nombre": 0, "montant": 0.0} for m in MOYENS}
    for a in fiables:
        par_moyen[a["moyen"]]["nombre"] += 1
        par_moyen[a["moyen"]]["montant"] = round(par_moyen[a["moyen"]]["montant"] + (a["montant"] or 0), 2)
    par_canal = {c: {"nombre": 0, "montant": 0.0} for c in CANAUX}
    for a in fiables:
        par_canal[a["canal"]]["nombre"] += 1
        par_canal[a["canal"]]["montant"] = round(par_canal[a["canal"]]["montant"] + (a["montant"] or 0), 2)
    attente = [x for x in (en_attente or []) if _dans_dt(x.get("date_dt"), debut, fin)]
    serie = {}
    for a in fiables:
        c = _cle_serie(a["date_dt"], granularite)
        s = serie.setdefault(c, {"periode": c, "ca": 0.0, "achats": 0})
        s["ca"] = round(s["ca"] + (a["montant"] or 0), 2)
        s["achats"] += 1
    par_cours = {}
    faits_p = [f for f in (faits or []) if f.get("occurrence_dt") is not None and _dans(f, debut, fin)]
    for f in faits_p:
        k = f["course_id"] or f["course_name"]
        if not k:
            continue
        e = par_cours.setdefault(k, {"id": f["course_id"] or "", "name": f["course_name"] or k,
                                     "reservations": 0, "valeurs_connues": 0, "valeur": 0.0, "seances": set()})
        e["reservations"] += 1
        e["seances"].add(f["occurrence"])
        if f["valeur"] is not None:
            e["valeurs_connues"] += 1
            e["valeur"] = round(e["valeur"] + float(f["valeur"]), 2)
    valeur_cours = []
    for e in sorted(par_cours.values(), key=lambda x: (-x["valeur"], x["name"])):
        valeur_cours.append({"id": e["id"], "name": e["name"], "reservations": e["reservations"],
                             "seances": len(e["seances"]), "valeur": e["valeur"],
                             "valeurs_connues": e["valeurs_connues"],
                             "couverture_pct": _taux(e["valeurs_connues"], e["reservations"]),
                             "valeur_moyenne_par_seance": round(e["valeur"] / len(e["seances"]), 2) if e["seances"] and e["valeurs_connues"] else None})
    valeur_totale = _somme(e["valeur"] for e in valeur_cours)
    valeurs_connues = sum(e["valeurs_connues"] for e in valeur_cours)
    moyens_indetermines = sum(1 for a in fiables if a["moyen"] == MOYEN_STRIPE_INDETERMINE)

    revenus = {
        "perimetre": perimetre_global,
        "ca_encaisse": ca,
        "ca_stripe": par_canal["stripe"]["montant"],
        "ca_manuel": par_canal["manuel"]["montant"],
        "transactions_payees": len(payants),
        "gratuits": len(gratuits),
        "panier_moyen": round(ca / len(payants), 2) if payants else None,
        "acheteurs_uniques": len(acheteurs),
        "revenu_par_participant": round(ca / len(acheteurs), 2) if acheteurs else None,
        "declare_non_prouve": {"nombre": len(partiels), "montant": _somme((a["montant"] or 0) for a in partiels)},
        "montant_inconnu": len(inconnus),
        "en_attente": {"nombre": len(attente), "montant_declare": _somme((x["montant"] or 0) for x in attente)},
        "par_moyen": par_moyen,
        "par_canal": par_canal,
        "evolution": [serie[k] for k in sorted(serie)],
        "valeur_par_cours": {
            "perimetre": ("filtré par cours" if cours_filtre else "tous les cours") + " — valeur des réservations au tarif figé, jamais additionnée au CA",
            "cours": valeur_cours,
            "valeur_totale": valeur_totale,
            "valeurs_connues": valeurs_connues,
            "reservations": len(faits_p),
            "couverture_pct": _taux(valeurs_connues, len(faits_p)),
        },
        "remboursements": REMBOURSEMENTS_LIBELLE,
        "qualite": {
            "montants": _niveau(len(periode), len(fiables), len(partiels)),
            "moyen_paiement": QUALITE_FIABLE if fiables and not moyens_indetermines else (QUALITE_PARTIEL if fiables else QUALITE_INCONNU),
            "stripe_moyen_indetermine": moyens_indetermines,
            "achats_periode": len(periode), "fiables": len(fiables), "partiels": len(partiels), "inconnus": len(inconnus),
        },
    }

    # ── ABONNEMENTS ─────────────────────────────────────────────────────────
    droits = [a for a in achats if a["type"] == "droit"]
    par_cat = lambda liste: {c: sum(1 for a in liste if a["categorie"] == c) for c in CATEGORIES_DROIT}  # noqa: E731
    actifs = [a for a in droits if a["actif"]]
    nouveaux = [a for a in droits if _dans_dt(a["date_dt"], debut, fin)]
    # « Expiré pendant la période » = une expiration DÉJÀ passée : sur l'année en
    # cours, une échéance de décembre n'est pas une expiration, c'est un actif.
    expires = [a for a in droits if _dans_dt(a["expire_dt"], debut, min(fin, maintenant))]
    proche = [a for a in actifs if a["expire_dt"] is not None and maintenant <= a["expire_dt"] < maintenant + timedelta(days=EXPIRATION_PROCHE_JOURS)]

    confirmes = [d for a in droits for d in a["renouvellement_confirme_dates"] if _dans_dt(d, debut, fin)]
    probables, inconnus_renouv = [], []
    multi = [a for a in droits if a["categorie"] not in (CATEGORIE_ESSAI,) and (a["seances"] or 0) != 1]
    par_participant = {}
    for a in multi:
        if a["participant_key"] and a["date_dt"]:
            par_participant.setdefault(a["participant_key"], []).append(a)
    for a in multi:
        # nouvelle fiche d'un même code après une fiche épuisée
        for d in a["fiches_dates"][1:]:
            if any(c < d for c in a["fiches_consommees_avant"]):
                if _dans_dt(d, debut, fin):
                    probables.append((a["cle"], d))
            elif a["fiches"] > 1:
                inconnus_renouv.append((a["cle"], d))
    for k, liste in par_participant.items():
        liste = sorted(liste, key=lambda x: x["date_dt"])
        for i, a in enumerate(liste[1:], 1):
            anterieurs = liste[:i]
            if any(x["consomme"] or (x["expire_dt"] is not None and x["expire_dt"] < a["date_dt"]) for x in anterieurs):
                if _dans_dt(a["date_dt"], debut, fin):
                    probables.append((a["cle"], a["date_dt"]))
    probables = sorted(set(probables))
    inconnus_renouv = sorted(set(inconnus_renouv))

    cartes = [m for m in (memberships or []) if isinstance(m, dict)]
    def _deb(m): return parser_utc(m.get("date_debut"))
    def _fin(m): return parser_utc(m.get("date_fin"))
    cartes_actives = [m for m in cartes if _deb(m) and _fin(m) and _deb(m) <= maintenant <= _fin(m)]
    cartes_vendues = [m for m in cartes if _texte(m.get("source")).lower() == "achat" and _dans_dt(_deb(m), debut, fin)]
    cartes_regularisees = [m for m in cartes if _texte(m.get("source")).lower() != "achat" and _dans_dt(_deb(m), debut, fin)]
    cartes_expirees = [m for m in cartes if _dans_dt(_fin(m), debut, fin)]

    serie_ab = {}
    for a in nouveaux:
        c = _cle_serie(a["date_dt"], granularite)
        serie_ab.setdefault(c, {"periode": c, "nouveaux": 0, "expires": 0, "pulse": 0})
        serie_ab[c]["nouveaux"] += 1
        if a["categorie"] == CATEGORIE_PULSE:
            serie_ab[c]["pulse"] += 1
    for a in expires:
        c = _cle_serie(a["expire_dt"], granularite)
        serie_ab.setdefault(c, {"periode": c, "nouveaux": 0, "expires": 0, "pulse": 0})
        serie_ab[c]["expires"] += 1

    abonnements = {
        "perimetre": perimetre_global,
        "actifs": {"total": len(actifs), "par_categorie": par_cat(actifs)},
        "nouveaux": {"total": len(nouveaux), "par_categorie": par_cat(nouveaux)},
        "expires": {"total": len(expires), "par_categorie": par_cat(expires)},
        "expirant_bientot": {"jours": EXPIRATION_PROCHE_JOURS, "total": len(proche)},
        "pulse_x10": {"actifs": par_cat(actifs)[CATEGORIE_PULSE], "vendus": par_cat(nouveaux)[CATEGORIE_PULSE]},
        "cartes_membres": {"actives": len(cartes_actives), "vendues": len(cartes_vendues),
                           "regularisees": len(cartes_regularisees), "expirees": len(cartes_expirees), "total": len(cartes)},
        "renouvellements": {"confirmes": len(confirmes), "probables": len(probables), "inconnus": len(inconnus_renouv),
                            "kpi_principal": "confirmes",
                            "libelle_probables": RENOUV_LIBELLE_PROBABLES,
                            "avertissement": RENOUV_AVERTISSEMENT_TEST},
        "evolution": [serie_ab[k] for k in sorted(serie_ab)],
        "qualite": {
            "renouvellements": QUALITE_FIABLE if confirmes and not probables and not inconnus_renouv
            else (QUALITE_PARTIEL if (confirmes or probables) else QUALITE_INCONNU),
            "note": RENOUV_AVERTISSEMENT_TEST,
            "droits_sans_date": sum(1 for a in droits if a["date_dt"] is None),
            "droits_total": len(droits),
        },
    }

    # ── ESSAIS & CONVERSION ─────────────────────────────────────────────────
    cohorte = [a for a in droits if a["essai"] and _dans_dt(a["date_dt"], debut, fin)]
    faits_tous = [f for f in (faits or []) if isinstance(f, dict)]
    par_code = {}
    par_sub = {}
    for f in faits_tous:
        if f.get("code"):
            par_code.setdefault(f["code"], []).append(f)
        if f.get("subscription_id"):
            par_sub.setdefault(f["subscription_id"], []).append(f)
    achats_non_essai = [a for a in achats if not a["essai"] and a["date_dt"] and a["participant_key"]
                        and (a["type"] == "droit" or (a["montant"] or 0) > 0)]
    reserves = presents = absents = inconnus_pres = 0
    conv_confirmes = 0
    conv_prob = {"total": 0, CATEGORIE_PULSE: 0, CATEGORIE_ABONNEMENT: 0, CATEGORIE_CARTE: 0, CATEGORIE_AUTRE: 0}
    delais = []
    prob_sans_conf = 0
    for a in cohorte:
        _r = list(par_code.get(a["code"], []))
        for sid in a["sub_ids"]:
            _r.extend(x for x in par_sub.get(sid, []) if x not in _r)
        if _r:
            reserves += 1
            _p = {x["presence"] for x in _r}
            if PRESENCE_CONFIRMEE in _p:
                presents += 1
            elif PRESENCE_ABSENTE in _p:
                absents += 1
            else:
                inconnus_pres += 1
        if a["converted_dt"] is not None:
            conv_confirmes += 1
        suivants = sorted((x for x in achats_non_essai if x["participant_key"] == a["participant_key"]
                           and a["date_dt"] and x["date_dt"] > a["date_dt"]), key=lambda x: x["date_dt"])
        carte = next((m for m in cartes if cle_participant(m.get("email")) == a["participant_key"]
                      and _texte(m.get("source")).lower() == "achat" and _deb(m) and a["date_dt"] and _deb(m) > a["date_dt"]), None)
        if suivants or carte:
            conv_prob["total"] += 1
            if a["converted_dt"] is None:
                prob_sans_conf += 1     # un achat que le marqueur n'a pas vu : mesure partielle
            if suivants:
                conv_prob[suivants[0]["categorie"] if suivants[0]["categorie"] in conv_prob else CATEGORIE_AUTRE] += 1
                delais.append((suivants[0]["date_dt"] - a["date_dt"]).days)
            if carte:
                conv_prob[CATEGORIE_CARTE] += 1
    n = len(cohorte)
    essais = {
        "perimetre": perimetre_global,
        "convention": CONVENTION_CONVERSION,
        "accordes": n,
        "reserves": reserves,
        "presence": {"confirmee": presents, "absente": absents, "inconnue": inconnus_pres,
                     "couverture_pct": _taux(presents + absents, reserves)},
        "convertis_confirmes": conv_confirmes,
        "convertis_probables": conv_prob,
        "taux": {"reservation": _taux(reserves, n), "presence": _taux(presents, reserves),
                 "conversion_confirmee": _taux(conv_confirmes, n), "conversion_probable": _taux(conv_prob["total"], n)},
        "delai_conversion_probable_median_jours": _mediane(delais),
        "qualite": {
            "conversion": QUALITE_FIABLE if conv_confirmes and not prob_sans_conf else (QUALITE_PARTIEL if (conv_confirmes or conv_prob["total"]) else QUALITE_INCONNU),
            "probables_sans_marqueur": prob_sans_conf,
            "presence": QUALITE_FIABLE if reserves and inconnus_pres == 0 else (QUALITE_PARTIEL if (presents or absents) else QUALITE_INCONNU),
        },
    }

    return {"revenus": revenus, "abonnements": abonnements, "essais_funnel": essais}


# ─────────────── TRACKING 2B — ACQUISITION PAR SOURCE ────────────────────────
#
# AUCUNE nouvelle définition. Une source = la FIRST-TOUCH de la PERSONNE (la
# plus ancienne attribution connue sur ses réservations et ses achats) ; puis
# les MÊMES moteurs (`calculer_kpi`, `calculer_kpi_finance`) tournent sur le
# sous-ensemble de cette source. Essai, présence, conversion, un achat = une
# ligne, renouvellements confirmés / probables : règles inchangées, périmètre
# restreint. « inconnue » = personne sans aucune attribution ; on n'invente
# jamais une source. Le coût d'acquisition n'est pas calculé (aucune donnée).
def source_par_personne(faits, achats):
    """{participant_key: (source, content)} — la first-touch la plus ancienne connue."""
    meilleure = {}
    def _poser(cle, src, content, quand):
        if not cle or not src:
            return
        _q = quand or datetime.max.replace(tzinfo=timezone.utc)
        if cle not in meilleure or _q < meilleure[cle][2]:
            meilleure[cle] = (src, content, _q)
    for f in (faits or []):
        if isinstance(f, dict):
            _poser(f.get("participant_key"), f.get("attribution_source"), f.get("attribution_content"), f.get("created_dt"))
    for a in (achats or []):
        if isinstance(a, dict):
            _poser(a.get("participant_key"), a.get("attribution_source"), a.get("attribution_content"), a.get("date_dt"))
    return {k: (v[0], v[1]) for k, v in meilleure.items()}


def calculer_kpi_sources(faits, achats, memberships, debut, fin, maintenant=None) -> dict:
    """Une ligne par source : participants, essais, présences, achats, clients,
    taux essai -> client, CA prouvé, panier moyen, renouvellements. Même moteur."""
    maintenant = maintenant or datetime.now()
    faits = [f for f in (faits or []) if isinstance(f, dict)]
    achats = [a for a in (achats or []) if isinstance(a, dict)]
    personnes = source_par_personne(faits, achats)
    groupes = {}
    def _cle_de(cle_personne, src_doc, content_doc):
        src, content = personnes.get(cle_personne, (src_doc, content_doc))
        return cle_source(src, content), (src or SOURCE_INCONNUE), (content or "")
    for f in faits:
        k, src, content = _cle_de(f.get("participant_key"), f.get("attribution_source"), f.get("attribution_content"))
        g = groupes.setdefault(k, {"source": src, "content": content, "faits": [], "achats": []})
        g["faits"].append(f)
    for a in achats:
        k, src, content = _cle_de(a.get("participant_key"), a.get("attribution_source"), a.get("attribution_content"))
        g = groupes.setdefault(k, {"source": src, "content": content, "faits": [], "achats": []})
        g["achats"].append(a)
    lignes = []
    for k, g in groupes.items():
        kpi = calculer_kpi(g["faits"], debut, fin, "mois") if g["faits"] else {}
        fin_ = calculer_kpi_finance(g["achats"], [], memberships, g["faits"], debut, fin, "mois", maintenant)
        rev, ab, es = fin_["revenus"], fin_["abonnements"], fin_["essais_funnel"]
        achats_periode = [a for a in g["achats"] if _dans_dt(a["date_dt"], debut, fin)]
        payants = [a for a in achats_periode if not a["essai"] and (a["montant"] or 0) > 0]
        participants = {f.get("participant_key") for f in g["faits"] if f.get("participant_key") and _dans(f, debut, fin)} \
            | {a.get("participant_key") for a in achats_periode if a.get("participant_key")}
        clients = {a["participant_key"] for a in payants if a.get("participant_key")}
        offres = {}
        for a in payants:
            offres[a["offre"] or "?"] = offres.get(a["offre"] or "?", 0) + 1
        presences = sum(1 for f in g["faits"] if _dans(f, debut, fin) and f.get("presence") == PRESENCE_CONFIRMEE)
        lignes.append({
            "cle": k, "source": g["source"], "content": g["content"],
            "libelle": libelle_source(g["source"], g["content"]),
            "partenaire": g["source"] == SOURCE_PARTENAIRE and bool(g["content"]),
            "participants": len(participants),
            "reservations": (kpi.get("participants") or {}).get("reservations_cours", 0) if kpi else 0,
            "essais": es["accordes"],
            "essais_reserves": es["reserves"],
            "presences_confirmees": presences,
            "presence_essais": es["presence"],
            "achats": len(payants),
            "clients": len(clients),
            "convertis_confirmes": es["convertis_confirmes"],
            "convertis_probables": es["convertis_probables"]["total"],
            "taux_conversion_confirmee": es["taux"]["conversion_confirmee"],
            "taux_conversion_probable": es["taux"]["conversion_probable"],
            "ca_prouve": rev["ca_encaisse"],
            "panier_moyen": rev["panier_moyen"],
            "declare_non_prouve": rev["declare_non_prouve"],
            "offres": sorted(offres.items(), key=lambda x: -x[1]),
            "renouvellements": {"confirmes": ab["renouvellements"]["confirmes"], "probables": ab["renouvellements"]["probables"]},
            "qualite": {"conversion": es["qualite"]["conversion"], "presence": es["qualite"]["presence"],
                        "renouvellements": fin_["abonnements"]["qualite"]["renouvellements"]},
        })
    lignes.sort(key=lambda l: (l["source"] == SOURCE_INCONNUE, -(l["ca_prouve"] or 0), -l["participants"], l["libelle"]))
    attribues = [l for l in lignes if l["source"] != SOURCE_INCONNUE]
    return {
        "convention": "Source = première touche connue de la personne (attribution.first, M2-A) ; "
                      "mêmes règles que le cockpit (essai, présence, un achat = une ligne, renouvellements). "
                      "« inconnue » = aucune origine enregistrée ; aucun coût d'acquisition (donnée absente).",
        "lignes": lignes,
        "couverture": {"participants_attribues": sum(l["participants"] for l in attribues),
                       "participants_total": sum(l["participants"] for l in lignes),
                       "achats_attribues": sum(l["achats"] for l in attribues),
                       "achats_total": sum(l["achats"] for l in lignes)},
    }

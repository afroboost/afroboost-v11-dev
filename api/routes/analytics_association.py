# -*- coding: utf-8 -*-
"""ANALYTICS PHASE 3 — LE BILAN ASSOCIATION : une PROJECTION, jamais un recalcul.

Tout ce que ce module rend vient des dictionnaires DÉJÀ calculés par
`analytics_shared` (`calculer_kpi`, `calculer_kpi_finance`). Il ne lit aucune
base, n'additionne aucun montant nouveau, ne réinvente aucune règle : il
choisit, nomme, compare et met en forme. Une même période et un même périmètre
donnent donc EXACTEMENT les mêmes valeurs à l'écran SuperAdmin, à l'écran
Association, dans le CSV, le XLSX et le PDF — c'est ce que le banc de cohérence
vérifie.

CONFIDENTIALITÉ. La projection est AGRÉGÉE : aucun e-mail, téléphone, nom de
participant, code d'accès, identifiant Stripe ou de transaction n'y entre.
`verifier_anonymat` parcourt le résultat et refuse toute chaîne qui ressemble à
l'un d'eux ; la route ne sert rien qui ne l'ait franchi.

COMPARAISON. Le mois choisi est comparé au mois PRÉCÉDENT (même longueur pour
une période personnalisée). Quand la valeur précédente est zéro, aucun
pourcentage n'est inventé : « nouveau » si la valeur courante est positive,
« comparaison indisponible » sinon.

EXPORTS. CSV (UTF-8 avec BOM, `;`, lisible par Excel en français), XLSX écrit
à la main (paquet Office Open XML minimal, cellules `inlineStr`, sans
dépendance) et PDF (reportlab, déjà utilisé par les factures V199). Les trois
sont construits depuis les MÊMES lignes (`lignes_export`, `document_bilan`).
"""
import csv
import io
import re
import zipfile
from datetime import datetime, timedelta
from xml.sax.saxutils import escape as _xml

from api.routes.analytics_shared import (
    CATEGORIES_FIDELITE, MOYENS, QUALITE_FIABLE, QUALITE_INCONNU, QUALITE_PARTIEL, mois_suivant,
)

MOIS_COURTS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"]
MOIS_LONGS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre"]
LIBELLES_FIDELITE = {"1": "1 participation", "2_5": "2 à 5 participations",
                     "6_10": "6 à 10 participations", "plus_10": "plus de 10 participations"}
LIBELLES_MOYEN = {
    "stripe_card": "Stripe — carte", "stripe_twint": "Stripe — TWINT",
    "stripe_indetermine": "Stripe — moyen non déterminé", "twint": "TWINT (manuel)",
    "virement": "Virement", "especes": "Espèces", "mobile_money": "Mobile Money",
    "offert": "Offert", "inconnu": "Inconnu",
}
PERIMETRE_ENSEMBLE = "Ensemble Afroboost / Association"
PIED_PDF = ("Données générées à partir du système Afroboost. "
            "Les données personnelles des participants ne sont pas incluses.")
COMPARAISON_NOUVEAU = "nouveau"
COMPARAISON_INDISPONIBLE = "comparaison indisponible"
COMPARAISON_STABLE = "stable"

INDICATEURS_COMPARES = (
    ("reservations", "Réservations"),
    ("participants_uniques", "Participants uniques"),
    ("nouveaux", "Nouveaux participants"),
    ("moyenne_par_seance", "Moyenne par séance"),
    ("essais", "Essais accordés"),
    ("pulse_vendus", "Pulse X10 vendus"),
    ("abonnements_nouveaux", "Nouveaux abonnements"),
    ("ca_prouve", "CA prouvé (CHF)"),
)

_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RE_STRIPE = re.compile(r"\b(cs_(live|test)_|pi_|cus_|pm_|ch_|free_[0-9a-f]{6})")
_RE_CODE = re.compile(r"\bAFR-[A-Z0-9]{6}\b")
_RE_TEL = re.compile(r"(\+41|0041|\b0)[ .]?7[5-9][ .]?\d{3}[ .]?\d{2}[ .]?\d{2}\b")
_RE_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


# ─────────────────────────────── outils purs ───────────────────────────────

def _n(v, defaut=0):
    return defaut if v is None else v


def libelle_periode(debut, fin):
    """« Août 2026 », « Année 2026 » ou « Du 1 août au 15 août 2026 »."""
    if debut.day == 1 and fin == mois_suivant(debut):
        return "%s %d" % (MOIS_LONGS[debut.month - 1].capitalize(), debut.year)
    if debut.month == 1 and debut.day == 1 and fin == debut.replace(year=debut.year + 1):
        return "Année %d" % debut.year
    _dernier = fin - timedelta(days=1)
    return "Du %d %s au %d %s %d" % (debut.day, MOIS_LONGS[debut.month - 1], _dernier.day,
                                     MOIS_LONGS[_dernier.month - 1], _dernier.year)


def periode_precedente(debut, fin):
    """La période de comparaison : le mois d'avant pour un mois, l'année d'avant
    pour une année, la fenêtre de même longueur juste avant sinon."""
    if debut.day == 1 and fin == mois_suivant(debut):
        _p = (debut.replace(year=debut.year - 1, month=12) if debut.month == 1
              else debut.replace(month=debut.month - 1))
        return _p, debut
    if debut.month == 1 and debut.day == 1 and fin == debut.replace(year=debut.year + 1):
        return debut.replace(year=debut.year - 1), debut
    _longueur = fin - debut
    return debut - _longueur, debut


def comparer(actuel, precedent):
    """{actuel, precedent, variation_pct, libelle} — jamais un % sur un zéro."""
    _a = _n(actuel)
    _p = _n(precedent)
    if not _p:
        _lib = COMPARAISON_NOUVEAU if _a else COMPARAISON_INDISPONIBLE
        return {"actuel": _a, "precedent": _p, "variation_pct": None, "libelle": _lib}
    _v = round(100.0 * (_a - _p) / _p, 1)
    if _v == 0:
        _lib = COMPARAISON_STABLE
    else:
        _lib = ("+" if _v > 0 else "−") + ("%s" % abs(_v)).replace(".", ",") + " %"
    return {"actuel": _a, "precedent": _p, "variation_pct": _v, "libelle": _lib}


def _fmt_chf(v):
    if v is None:
        return "—"
    _e, _d = ("%.2f" % float(v)).split(".")
    _e = re.sub(r"\B(?=(\d{3})+(?!\d))", " ", _e)
    return "%s,%s CHF" % (_e, _d)


def _fmt_pct(v):
    return "—" if v is None else ("%s %%" % str(v).replace(".", ","))


def _fmt_nombre(v):
    if v is None:
        return "—"
    if isinstance(v, float) and not v.is_integer():
        return str(v).replace(".", ",")
    return str(int(v)) if isinstance(v, float) else str(v)


# ─────────────────────────────── la projection ─────────────────────────────

def indicateurs_compares(kpi):
    """Les valeurs qu'on compare d'une période à l'autre, tirées d'un KPI complet."""
    _k = kpi or {}
    _p = _k.get("participants") or {}
    _c = _k.get("cours") or {}
    _ab = _k.get("abonnements") or {}
    _r = _k.get("revenus") or {}
    _e = _k.get("essais_funnel") or {}
    return {
        "reservations": _n(_p.get("reservations_cours")),
        "participants_uniques": _n(_p.get("uniques")),
        "nouveaux": _n(_p.get("nouveaux")),
        "moyenne_par_seance": _c.get("moyenne_par_seance"),
        "essais": _n(_e.get("accordes")),
        "pulse_vendus": _n((_ab.get("pulse_x10") or {}).get("vendus")),
        "abonnements_nouveaux": _n((_ab.get("nouveaux") or {}).get("total")),
        "ca_prouve": _n(_r.get("ca_encaisse")),
        "seances": _n(_c.get("seances")),
    }


def projeter_association(kpi, kpi_precedent, kpis_annee, debut, fin, perimetre_libelle=PERIMETRE_ENSEMBLE,
                         cours_filtre="", maintenant=None):
    """Le bilan agrégé d'une période, depuis des KPI DÉJÀ calculés. Pur.

    `kpis_annee` : liste de 12 tuples (mois_dt, kpi) pour l'année de `debut`,
    calculés par le même moteur — ce module ne fait que les ranger.
    """
    maintenant = maintenant or datetime.now()
    _k = kpi or {}
    _p = _k.get("participants") or {}
    _c = _k.get("cours") or {}
    _pres = _k.get("presence") or {}
    _fid = _k.get("fidelite") or {}
    _e = _k.get("essais_funnel") or {}
    _ab = _k.get("abonnements") or {}
    _r = _k.get("revenus") or {}
    _q = _k.get("qualite") or {}
    _rq = _r.get("qualite") or {}
    _mer = _c.get("mercredi") or {}
    _dim = _c.get("dimanche") or {}
    _cartes = _ab.get("cartes_membres") or {}
    _pulse = _ab.get("pulse_x10") or {}
    _renouv = _ab.get("renouvellements") or {}
    _epres = _e.get("presence") or {}
    _conv = _e.get("convertis_probables") or {}
    _attente = _r.get("en_attente") or {}
    _decl = _r.get("declare_non_prouve") or {}

    activite = {
        "seances": _n(_c.get("seances")),
        "reservations": _n(_p.get("reservations_cours")),
        "participants_uniques": _n(_p.get("uniques")),
        "nouveaux": _n(_p.get("nouveaux")),
        "recurrents": _n(_p.get("recurrents")),
        "moyenne_par_seance": _c.get("moyenne_par_seance"),
        "mercredi": {"reservations": _n(_mer.get("reservations")), "seances": _n(_mer.get("seances")),
                     "moyenne": _mer.get("moyenne"), "participants": _n(_mer.get("participants"))},
        "dimanche": {"reservations": _n(_dim.get("reservations")), "seances": _n(_dim.get("seances")),
                     "moyenne": _dim.get("moyenne"), "participants": _n(_dim.get("participants"))},
        "autres_jours": _n(_c.get("autres_jours")),
    }
    presence = {
        "confirmee": _n(_pres.get("confirmee")), "absente": _n(_pres.get("absente")),
        "inconnue": _n(_pres.get("inconnue")), "reservations": activite["reservations"],
        "couverture_pct": _pres.get("couverture_pct"),
        "libelle": "%d présence(s) vérifiée(s) sur %d réservations — couverture %s" % (
            _n(_pres.get("confirmee")) + _n(_pres.get("absente")), activite["reservations"],
            _fmt_pct(_pres.get("couverture_pct"))),
    }
    essais = {
        "accordes": _n(_e.get("accordes")), "reserves": _n(_e.get("reserves")),
        "presence_confirmee": _n(_epres.get("confirmee")), "presence_inconnue": _n(_epres.get("inconnue")),
        "couverture_pct": _epres.get("couverture_pct"),
        "conversions_confirmees": _n(_e.get("convertis_confirmes")),
        "conversions_probables": _n(_conv.get("total")),
        "taux_reservation_pct": (_e.get("taux") or {}).get("reservation"),
    }
    fidelisation = {c: _n(_fid.get(c)) for c in CATEGORIES_FIDELITE}
    abonnements = {
        "actifs": _n((_ab.get("actifs") or {}).get("total")),
        "nouveaux": _n((_ab.get("nouveaux") or {}).get("total")),
        "expires": _n((_ab.get("expires") or {}).get("total")),
        "pulse_actifs": _n(_pulse.get("actifs")), "pulse_vendus": _n(_pulse.get("vendus")),
        "cartes_actives": _n(_cartes.get("actives")), "cartes_vendues": _n(_cartes.get("vendues")),
        "renouvellements_confirmes": _n(_renouv.get("confirmes")),
        "renouvellements_probables": _n(_renouv.get("probables")),
        "note_probables": _renouv.get("libelle_probables") or "",
    }
    par_moyen = {}
    for m in MOYENS:
        _v = (_r.get("par_moyen") or {}).get(m) or {}
        if _n(_v.get("nombre")):
            par_moyen[m] = {"libelle": LIBELLES_MOYEN.get(m, m), "nombre": _n(_v.get("nombre")),
                            "montant": _n(_v.get("montant"), 0.0)}
    finances = {
        "ca_prouve": _n(_r.get("ca_encaisse"), 0.0), "stripe": _n(_r.get("ca_stripe"), 0.0),
        "manuel": _n(_r.get("ca_manuel"), 0.0), "achats_payes": _n(_r.get("transactions_payees")),
        "gratuits": _n(_r.get("gratuits")), "panier_moyen": _r.get("panier_moyen"),
        "acheteurs_uniques": _n(_r.get("acheteurs_uniques")),
        "par_moyen": par_moyen,
        "hors_ca": {
            "declare_non_prouve_montant": _n(_decl.get("montant"), 0.0),
            "declare_non_prouve_nombre": _n(_decl.get("nombre")),
            "pending_nombre": _n(_attente.get("nombre")),
            "pending_montant": _n(_attente.get("montant_declare"), 0.0),
            "inconnus": _n(_r.get("montant_inconnu")),
            "note": "Jamais additionnés au CA prouvé.",
        },
        "remboursements": _r.get("remboursements") or "Remboursements non disponibles historiquement",
    }
    qualite = {
        "presence": _q.get("presence") or QUALITE_INCONNU,
        "valeur_financiere": _q.get("valeur_financiere") or QUALITE_INCONNU,
        "montants": _rq.get("montants") or QUALITE_INCONNU,
        "moyen_paiement": _rq.get("moyen_paiement") or QUALITE_INCONNU,
        "renouvellements": (_ab.get("qualite") or {}).get("renouvellements") or QUALITE_INCONNU,
        "conversion": (_e.get("qualite") or {}).get("conversion") or QUALITE_INCONNU,
        "phrases": [
            "Présence : " + presence["libelle"] + ". Une réservation non vérifiée n'est jamais comptée comme une absence.",
            "Finance : CA prouvé %s ; montants déclarés mais non suffisamment prouvés %s (%d) ; paiements en attente %s (%d) ; %d droit(s) sans montant connu."
            % (_fmt_chf(finances["ca_prouve"]), _fmt_chf(finances["hors_ca"]["declare_non_prouve_montant"]),
               finances["hors_ca"]["declare_non_prouve_nombre"], _fmt_chf(finances["hors_ca"]["pending_montant"]),
               finances["hors_ca"]["pending_nombre"], finances["hors_ca"]["inconnus"]),
            "Moyens de paiement : %d paiement(s) Stripe sans distinction carte / TWINT — présentés comme « Stripe — moyen non déterminé »."
            % _n(_rq.get("stripe_moyen_indetermine")),
            "Renouvellements : seuls les %d confirmé(s) comptent ; %d probable(s) affiché(s) à part."
            % (abonnements["renouvellements_confirmes"], abonnements["renouvellements_probables"]),
            finances["remboursements"] + ".",
        ],
    }

    # ── comparaison avec la période précédente ──
    _pd, _pf = periode_precedente(debut, fin)
    _ia, _ip = indicateurs_compares(_k), indicateurs_compares(kpi_precedent or {})
    comparaison = {
        "periode_precedente": {"debut": _pd.strftime("%Y-%m-%d"), "fin_exclue": _pf.strftime("%Y-%m-%d"),
                               "libelle": libelle_periode(_pd, _pf)},
        "indicateurs": {k: dict(comparer(_ia.get(k), _ip.get(k)), libelle_indicateur=lib)
                        for k, lib in INDICATEURS_COMPARES},
    }

    # ── évolution annuelle ──
    mois = []
    for _m_dt, _km in (kpis_annee or []):
        _i = indicateurs_compares(_km)
        mois.append({"mois": MOIS_COURTS[_m_dt.month - 1], "numero": _m_dt.month,
                     "participants": _i["participants_uniques"], "reservations": _i["reservations"],
                     "seances": _i["seances"], "essais": _i["essais"], "ca_prouve": _i["ca_prouve"],
                     "futur": _m_dt > maintenant})
    evolution = {"annee": debut.year, "mois": mois}

    assoc = {
        "periode": {"debut": debut.strftime("%Y-%m-%d"), "fin_exclue": fin.strftime("%Y-%m-%d"),
                    "libelle": libelle_periode(debut, fin)},
        "perimetre": {
            "libelle": perimetre_libelle or PERIMETRE_ENSEMBLE,
            "cours": cours_filtre or "tous",
            "note": ("Le filtre cours ne s'applique qu'à l'activité et à la présence ; essais, abonnements et finances restent globaux (période / coach)."
                     if cours_filtre else ""),
        },
        "activite": activite, "presence": presence, "essais": essais, "fidelisation": fidelisation,
        "abonnements": abonnements, "finances": finances, "qualite": qualite,
        "comparaison": comparaison, "evolution_annuelle": evolution,
        "genere_le": maintenant.strftime("%Y-%m-%d %H:%M"),
    }
    assoc["resume_executif"] = resume_executif(assoc)
    return assoc


def resume_executif(assoc) -> str:
    """Le résumé court, DÉTERMINISTE, écrit depuis les chiffres — sans IA, sans interprétation."""
    _a = assoc["activite"]
    _f = assoc["finances"]
    _e = assoc["essais"]
    _lib = assoc["periode"]["libelle"]
    _quand = ("En " + _lib[0].lower() + _lib[1:]) if _lib[0].isupper() and not _lib.startswith(("Du", "Année")) else \
        ("En " + _lib.replace("Année ", "")) if _lib.startswith("Année") else _lib
    _moy = _a["moyenne_par_seance"]
    phrases = [
        "%s, Afroboost a organisé %d séance(s) réunissant %d participant(s) unique(s) pour %d réservation(s)."
        % (_quand, _a["seances"], _a["participants_uniques"], _a["reservations"]),
    ]
    if _moy is not None:
        phrases.append("La fréquentation moyenne était de %s participant(s) par séance." % _fmt_nombre(_moy))
    phrases.append("Le chiffre d'affaires prouvé s'élève à %s (%d achat(s) payé(s))." % (_fmt_chf(_f["ca_prouve"]), _f["achats_payes"]))
    phrases.append("%d nouveau(x) participant(s) ont découvert l'activité et %d essai(s) gratuit(s) ont été accordé(s), dont %d avec une présence confirmée."
                   % (_a["nouveaux"], _e["accordes"], _e["presence_confirmee"]))
    if _f["hors_ca"]["declare_non_prouve_montant"] or _f["hors_ca"]["pending_nombre"]:
        phrases.append("À part, non additionnés : %s déclarés sans preuve suffisante et %d paiement(s) en attente."
                       % (_fmt_chf(_f["hors_ca"]["declare_non_prouve_montant"]), _f["hors_ca"]["pending_nombre"]))
    return " ".join(phrases)


def verifier_anonymat(obj, chemin="") -> list:
    """Les chaînes qui ressemblent à une donnée personnelle, avec leur chemin. Vide = conforme."""
    trouvees = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            trouvees.extend(verifier_anonymat(v, chemin + "." + str(k)))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            trouvees.extend(verifier_anonymat(v, chemin + "[%d]" % i))
    elif isinstance(obj, str):
        for _re, _quoi in ((_RE_EMAIL, "e-mail"), (_RE_STRIPE, "identifiant Stripe/transaction"),
                           (_RE_CODE, "code d'accès"), (_RE_TEL, "téléphone"), (_RE_JWT, "jeton")):
            if _re.search(obj):
                trouvees.append((chemin, _quoi))
    return trouvees


# ─────────────────────────────── les lignes d'export ───────────────────────

def lignes_export(assoc) -> list:
    """UNE ligne agrégée (en-têtes, valeurs) — la même pour le CSV et la feuille Résumé."""
    _a, _e, _ab, _f, _p = (assoc["activite"], assoc["essais"], assoc["abonnements"],
                           assoc["finances"], assoc["presence"])
    return [
        ("Période", assoc["periode"]["libelle"]),
        ("Périmètre", assoc["perimetre"]["libelle"]),
        ("Séances", _a["seances"]),
        ("Réservations", _a["reservations"]),
        ("Participants uniques", _a["participants_uniques"]),
        ("Nouveaux", _a["nouveaux"]),
        ("Récurrents", _a["recurrents"]),
        ("Moyenne par séance", _a["moyenne_par_seance"]),
        ("Essais", _e["accordes"]),
        ("Essais réservés", _e["reserves"]),
        ("Présences essais", _e["presence_confirmee"]),
        ("Conversions confirmées", _e["conversions_confirmees"]),
        ("Abonnements actifs", _ab["actifs"]),
        ("Pulse actifs", _ab["pulse_actifs"]),
        ("Pulse vendus", _ab["pulse_vendus"]),
        ("Cartes membres actives", _ab["cartes_actives"]),
        ("Cartes membres vendues", _ab["cartes_vendues"]),
        ("CA prouvé (CHF)", _f["ca_prouve"]),
        ("Stripe (CHF)", _f["stripe"]),
        ("Manuel (CHF)", _f["manuel"]),
        ("Achats payés", _f["achats_payes"]),
        ("Panier moyen (CHF)", _f["panier_moyen"]),
        ("Déclaré non prouvé (CHF, hors CA)", _f["hors_ca"]["declare_non_prouve_montant"]),
        ("Pending (nombre, hors CA)", _f["hors_ca"]["pending_nombre"]),
        ("Pending (CHF déclarés, hors CA)", _f["hors_ca"]["pending_montant"]),
        ("Couverture présence (%)", _p["couverture_pct"]),
        ("Présences vérifiées", _p["confirmee"] + _p["absente"]),
    ]


def document_bilan(assoc) -> list:
    """Les sections du rapport : [(titre, [(libellé, valeur, note)])]. Base du PDF et du XLSX."""
    _a, _e, _ab, _f, _p, _fid, _q = (assoc["activite"], assoc["essais"], assoc["abonnements"],
                                     assoc["finances"], assoc["presence"], assoc["fidelisation"],
                                     assoc["qualite"])
    _cmp = assoc["comparaison"]
    sections = [
        ("Activité", [
            ("Séances", _fmt_nombre(_a["seances"]), ""),
            ("Réservations", _fmt_nombre(_a["reservations"]), ""),
            ("Participants uniques", _fmt_nombre(_a["participants_uniques"]), ""),
            ("Nouveaux participants", _fmt_nombre(_a["nouveaux"]), ""),
            ("Participants récurrents", _fmt_nombre(_a["recurrents"]), ""),
            ("Moyenne participants / séance", _fmt_nombre(_a["moyenne_par_seance"]), ""),
            ("Mercredi", "%d réservation(s), %d séance(s), moy. %s" % (
                _a["mercredi"]["reservations"], _a["mercredi"]["seances"], _fmt_nombre(_a["mercredi"]["moyenne"])), ""),
            ("Dimanche", "%d réservation(s), %d séance(s), moy. %s" % (
                _a["dimanche"]["reservations"], _a["dimanche"]["seances"], _fmt_nombre(_a["dimanche"]["moyenne"])), ""),
            ("Autres jours", _fmt_nombre(_a["autres_jours"]), ""),
            ("Présence", _p["libelle"], "les réservations non vérifiées ne sont jamais des absences"),
        ]),
        ("Participants (agrégés)", [
            ("Participants uniques", _fmt_nombre(_a["participants_uniques"]), ""),
            ("Nouveaux", _fmt_nombre(_a["nouveaux"]), ""),
            ("Récurrents", _fmt_nombre(_a["recurrents"]), ""),
        ] + [(LIBELLES_FIDELITE[c], _fmt_nombre(_fid[c]), "") for c in CATEGORIES_FIDELITE]),
        ("Essais gratuits", [
            ("Essais accordés", _fmt_nombre(_e["accordes"]), ""),
            ("Essais réservés", _fmt_nombre(_e["reserves"]), ""),
            ("Présences confirmées", _fmt_nombre(_e["presence_confirmee"]), ""),
            ("Présences inconnues", _fmt_nombre(_e["presence_inconnue"]), "jamais comptées comme absences"),
            ("Couverture de présence", _fmt_pct(_e["couverture_pct"]), ""),
            ("Conversions confirmées", _fmt_nombre(_e["conversions_confirmees"]), "KPI principal"),
            ("Conversions probables", _fmt_nombre(_e["conversions_probables"]), "à part, non comptées"),
        ]),
        ("Abonnements", [
            ("Abonnements actifs", _fmt_nombre(_ab["actifs"]), ""),
            ("Nouveaux", _fmt_nombre(_ab["nouveaux"]), ""),
            ("Pulse X10 actifs", _fmt_nombre(_ab["pulse_actifs"]), ""),
            ("Pulse X10 vendus", _fmt_nombre(_ab["pulse_vendus"]), ""),
            ("Cartes membres actives", _fmt_nombre(_ab["cartes_actives"]), ""),
            ("Cartes membres vendues", _fmt_nombre(_ab["cartes_vendues"]), ""),
            ("Renouvellements confirmés", _fmt_nombre(_ab["renouvellements_confirmes"]), "KPI principal"),
            ("Renouvellements probables", _fmt_nombre(_ab["renouvellements_probables"]), "non comptés dans le KPI principal"),
        ]),
        ("Finances", [
            ("CA prouvé", _fmt_chf(_f["ca_prouve"]), ""),
            ("dont Stripe", _fmt_chf(_f["stripe"]), ""),
            ("dont manuel (TWINT, virement, espèces)", _fmt_chf(_f["manuel"]), ""),
            ("Achats payés", _fmt_nombre(_f["achats_payes"]), "%d gratuit(s) / offert(s)" % _f["gratuits"]),
            ("Panier moyen", _fmt_chf(_f["panier_moyen"]), ""),
        ] + [("Moyen : " + m["libelle"], "%d — %s" % (m["nombre"], _fmt_chf(m["montant"])), "")
             for m in _f["par_moyen"].values()] + [
            ("— À part, hors CA —", "", ""),
            ("Montants déclarés non prouvés", _fmt_chf(_f["hors_ca"]["declare_non_prouve_montant"]),
             "%d achat(s)" % _f["hors_ca"]["declare_non_prouve_nombre"]),
            ("Paiements en attente", "%d — %s déclarés" % (_f["hors_ca"]["pending_nombre"], _fmt_chf(_f["hors_ca"]["pending_montant"])), ""),
            ("Données financières inconnues", _fmt_nombre(_f["hors_ca"]["inconnus"]), "droits sans montant"),
            ("Remboursements", _f["remboursements"], ""),
        ]),
        ("Comparaison avec " + _cmp["periode_precedente"]["libelle"], [
            (v["libelle_indicateur"], "%s → %s" % (_fmt_nombre(v["precedent"]), _fmt_nombre(v["actuel"])), v["libelle"])
            for v in _cmp["indicateurs"].values()
        ]),
        ("Qualité des données", [
            ("Présence", _q["presence"], ""), ("Valeur financière des réservations", _q["valeur_financiere"], ""),
            ("Montants", _q["montants"], ""), ("Moyen de paiement", _q["moyen_paiement"], ""),
            ("Renouvellements", _q["renouvellements"], ""), ("Conversion", _q["conversion"], ""),
        ] + [("", ph, "") for ph in _q["phrases"]]),
    ]
    return sections


# ─────────────────────────────── CSV ───────────────────────────────────────

def _csv_val(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return ("%.2f" % v).replace(".", ",")
    return str(v)


def export_csv(assoc) -> bytes:
    """UTF-8 avec BOM, séparateur « ; » : Excel (français) l'ouvre tel quel."""
    lignes = lignes_export(assoc)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    if (assoc.get("cloture") or {}).get("officiel"):
        # Phase 4 : le fichier vient d'un bilan FIGÉ — il le dit en première ligne.
        w.writerow(["Statut", assoc["cloture"]["libelle"]])
    w.writerow([l[0] for l in lignes])
    w.writerow([_csv_val(l[1]) for l in lignes])
    w.writerow([])
    w.writerow(["Évolution %d" % assoc["evolution_annuelle"]["annee"], "Mois", "Participants", "Réservations", "Séances", "Essais", "CA prouvé (CHF)", "Statut"])
    for m in assoc["evolution_annuelle"]["mois"]:
        w.writerow(["", m["mois"], m["participants"], m["reservations"], m["seances"], m["essais"], _csv_val(float(m["ca_prouve"])),
                    "à venir" if m.get("futur") else "écoulé"])
    return ("﻿" + buf.getvalue()).encode("utf-8")


# ─────────────────────────────── XLSX (sans dépendance) ────────────────────

NOMS_FEUILLES = ("Résumé", "Activité", "Participants agrégés", "Essais", "Abonnements", "Finances", "Qualité des données")


def _cell(ref, v):
    if v is None or v == "":
        return '<c r="%s" t="inlineStr"><is><t></t></is></c>' % ref
    if isinstance(v, bool):
        return '<c r="%s" t="inlineStr"><is><t>%s</t></is></c>' % (ref, "oui" if v else "non")
    if isinstance(v, (int, float)):
        return '<c r="%s"><v>%s</v></c>' % (ref, repr(float(v)) if isinstance(v, float) else str(v))
    return '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, _xml(str(v)))


def _col(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _feuille_xml(lignes) -> str:
    rows = []
    for ri, ligne in enumerate(lignes, 1):
        cells = "".join(_cell("%s%d" % (_col(ci), ri), v) for ci, v in enumerate(ligne))
        rows.append('<row r="%d">%s</row>' % (ri, cells))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<cols><col min="1" max="1" width="44" customWidth="1"/><col min="2" max="8" width="22" customWidth="1"/></cols>'
            '<sheetData>%s</sheetData></worksheet>' % "".join(rows))


def feuilles_xlsx(assoc) -> list:
    """[(nom, lignes)] — les 7 feuilles, depuis les mêmes lignes que le PDF."""
    sections = dict(document_bilan(assoc))
    lignes = lignes_export(assoc)
    resume = [["Bilan Afroboost — " + assoc["periode"]["libelle"]], ["Périmètre", assoc["perimetre"]["libelle"]],
              ["Généré le", assoc["genere_le"]]] + \
             ([["Statut", assoc["cloture"]["libelle"]]] if (assoc.get("cloture") or {}).get("officiel") else [["Statut", "Données actuelles (dynamiques), non clôturées"]]) + \
             [[], ["Résumé exécutif", assoc["resume_executif"]], []] + [[l[0], l[1]] for l in lignes]
    def _sec(titre):
        return [[titre], ["Indicateur", "Valeur", "Note"]] + [[a, b, c] for a, b, c in sections[titre]]
    activite = _sec("Activité") + [[], ["Comparaison", "Précédent → actuel", "Variation"]] + \
        [["Comparaison — " + v["libelle_indicateur"], "%s → %s" % (_fmt_nombre(v["precedent"]), _fmt_nombre(v["actuel"])), v["libelle"]]
         for v in assoc["comparaison"]["indicateurs"].values()] + \
        [[], ["Évolution %d" % assoc["evolution_annuelle"]["annee"], "Participants", "Réservations", "Séances", "Essais", "CA prouvé (CHF)", "Statut"]] + \
        [[m["mois"], m["participants"], m["reservations"], m["seances"], m["essais"], float(m["ca_prouve"]), "à venir" if m.get("futur") else "écoulé"]
         for m in assoc["evolution_annuelle"]["mois"]]
    finances = _sec("Finances") + [[], ["Valeurs brutes (CHF, nombres)"], ["CA prouvé (brut)", float(assoc["finances"]["ca_prouve"])],
                                   ["Stripe (brut)", float(assoc["finances"]["stripe"])], ["Manuel (brut)", float(assoc["finances"]["manuel"])],
                                   ["Déclaré non prouvé (brut, hors CA)", float(assoc["finances"]["hors_ca"]["declare_non_prouve_montant"])],
                                   ["Pending déclaré (brut, hors CA)", float(assoc["finances"]["hors_ca"]["pending_montant"])]]
    return [("Résumé", resume), ("Activité", activite), ("Participants agrégés", _sec("Participants (agrégés)")),
            ("Essais", _sec("Essais gratuits")), ("Abonnements", _sec("Abonnements")), ("Finances", finances),
            ("Qualité des données", _sec("Qualité des données") + [[], [PIED_PDF]])]


def export_xlsx(assoc) -> bytes:
    feuilles = feuilles_xlsx(assoc)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   + "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1)
                             for i in range(len(feuilles))) + '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (_xml(nom), i + 1, i + 1)
                             for i, (nom, _) in enumerate(feuilles)) + '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1)
                             for i in range(len(feuilles))) + '</Relationships>')
        for i, (_, lignes) in enumerate(feuilles):
            z.writestr("xl/worksheets/sheet%d.xml" % (i + 1), _feuille_xml(lignes))
    return buf.getvalue()


def lire_xlsx(donnees: bytes) -> dict:
    """{nom de feuille: [[valeurs]]} — pour les BANCS uniquement : relit un fichier
    que CE module vient d'écrire (jamais un fichier reçu de l'extérieur)."""
    import xml.etree.ElementTree as ET  # entrée = notre propre sortie, pas d'entité externe
    NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    out = {}
    with zipfile.ZipFile(io.BytesIO(donnees)) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        for sh in wb.find("m:sheets", NS):
            nom = sh.get("name")
            rid = sh.get("{%s}id" % NS["r"])
            ws = ET.fromstring(z.read("xl/worksheets/sheet%s.xml" % rid[3:]))
            lignes = []
            for row in ws.find("m:sheetData", NS):
                vals = []
                for c in row:
                    t = c.find("m:is/m:t", NS)
                    v = c.find("m:v", NS)
                    vals.append(t.text if t is not None else (float(v.text) if v is not None else None))
                lignes.append(vals)
            out[nom] = lignes
    return out


# ─────────────────────────────── PDF (reportlab) ───────────────────────────

def export_pdf(assoc) -> bytes:
    """Le bilan transmissible : noir / magenta #D91CD2 / blanc, sans donnée personnelle."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.pdfgen import canvas
    from reportlab.graphics.shapes import Drawing, Rect, String, Line

    MAGENTA, NOIR, BLANC, GRIS = HexColor("#D91CD2"), black, white, HexColor("#555555")
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle("Bilan mensuel Afroboost — " + assoc["periode"]["libelle"])
    c.setAuthor("Afroboost / Association Afroboosteur")
    W, H = A4
    marge = 1.8 * cm
    y = [H - marge]

    def pied(page):
        c.setFillColor(GRIS)
        c.setFont("Helvetica", 7.5)
        c.drawString(marge, 1.35 * cm, PIED_PDF)
        c.drawRightString(W - marge, 0.9 * cm, "Page %d — généré le %s" % (page, assoc["genere_le"]))

    page = [1]

    def nouvelle_page():
        pied(page[0])
        c.showPage()
        page[0] += 1
        y[0] = H - marge

    def besoin(h):
        if y[0] - h < 2 * cm:
            nouvelle_page()

    def titre(txt, taille=13, couleur=MAGENTA):
        besoin(1.2 * cm)
        c.setFillColor(couleur)
        c.setFont("Helvetica-Bold", taille)
        c.drawString(marge, y[0], txt)
        y[0] -= 0.75 * cm

    def paragraphe(txt, taille=9.5, couleur=NOIR, largeur=None):
        from reportlab.lib.utils import simpleSplit
        largeur = largeur or (W - 2 * marge)
        c.setFont("Helvetica", taille)
        c.setFillColor(couleur)
        for ligne in simpleSplit(txt, "Helvetica", taille, largeur):
            besoin(0.5 * cm)
            c.drawString(marge, y[0], ligne)
            y[0] -= taille * 1.35
        y[0] -= 0.2 * cm

    def tableau(lignes):
        from reportlab.lib.utils import simpleSplit
        for lib, val, note in lignes:
            if not lib and not val:
                continue
            besoin(0.55 * cm)
            if lib.startswith("—"):
                c.setFillColor(MAGENTA); c.setFont("Helvetica-Bold", 9)
                c.drawString(marge, y[0], lib.strip("— ").strip())
                y[0] -= 0.5 * cm
                continue
            c.setFillColor(NOIR); c.setFont("Helvetica", 9)
            if lib:
                c.drawString(marge, y[0], lib)
                c.setFont("Helvetica-Bold", 9)
                _val = str(val)
                _long = len(_val) > 40 or (note and len(_val) > 24)
                if not _long:
                    c.drawString(marge + 8.2 * cm, y[0], _val)
                    if note:
                        c.setFillColor(GRIS); c.setFont("Helvetica-Oblique", 7.5)
                        c.drawString(marge + 13.2 * cm, y[0], note)
                    y[0] -= 0.48 * cm
                else:
                    # valeur longue : sur la largeur restante, la note en dessous —
                    # jamais deux textes l'un sur l'autre.
                    for _l in simpleSplit(_val, "Helvetica-Bold", 9, W - marge - (marge + 8.2 * cm)):
                        c.drawString(marge + 8.2 * cm, y[0], _l)
                        y[0] -= 0.42 * cm
                        besoin(0.5 * cm)
                    if note:
                        c.setFillColor(GRIS); c.setFont("Helvetica-Oblique", 7.5)
                        c.drawString(marge + 8.2 * cm, y[0], note)
                        y[0] -= 0.42 * cm
                    y[0] -= 0.1 * cm
            else:
                for l in simpleSplit(str(val), "Helvetica", 8.5, W - 2 * marge):
                    besoin(0.45 * cm)
                    c.setFont("Helvetica", 8.5); c.setFillColor(GRIS)
                    c.drawString(marge, y[0], l)
                    y[0] -= 0.42 * cm
        y[0] -= 0.3 * cm

    # ── en-tête noir ──
    c.setFillColor(NOIR); c.rect(0, H - 3.4 * cm, W, 3.4 * cm, stroke=0, fill=1)
    c.setFillColor(MAGENTA); c.rect(0, H - 3.5 * cm, W, 0.12 * cm, stroke=0, fill=1)
    c.setFillColor(BLANC); c.setFont("Helvetica-Bold", 20)
    c.drawString(marge, H - 1.6 * cm, "Bilan mensuel Afroboost")
    c.setFont("Helvetica", 12); c.setFillColor(MAGENTA)
    c.drawString(marge, H - 2.35 * cm, assoc["periode"]["libelle"])
    c.setFillColor(BLANC); c.setFont("Helvetica", 8.5)
    c.drawRightString(W - marge, H - 1.5 * cm, "Afroboost / Association Afroboosteur")
    c.drawRightString(W - marge, H - 2.1 * cm, "Périmètre : " + assoc["perimetre"]["libelle"])
    if (assoc.get("cloture") or {}).get("officiel"):
        c.setFillColor(MAGENTA); c.setFont("Helvetica-Bold", 8.5)
        c.drawRightString(W - marge, H - 2.7 * cm, assoc["cloture"]["libelle"])
    else:
        c.setFillColor(GRIS); c.setFont("Helvetica", 8)
        c.drawRightString(W - marge, H - 2.7 * cm, "Données actuelles (dynamiques) — bilan non clôturé")
    y[0] = H - 4.4 * cm

    titre("Résumé exécutif")
    paragraphe(assoc["resume_executif"], 10)
    if assoc["perimetre"].get("note"):
        paragraphe(assoc["perimetre"]["note"], 8, GRIS)

    sections = document_bilan(assoc)
    for nom, lignes in sections:
        titre(nom)
        tableau(lignes)
        if nom == "Activité":
            # graphique : réservations et participants par mois (année de la période)
            besoin(6.5 * cm)
            titre("Évolution %d — réservations (magenta) et participants uniques (noir)" % assoc["evolution_annuelle"]["annee"], 9.5, NOIR)
            mois = assoc["evolution_annuelle"]["mois"]
            maxi = max([1] + [m["reservations"] for m in mois] + [m["participants"] for m in mois])
            d = Drawing(W - 2 * marge, 5 * cm)
            lg = (W - 2 * marge) / max(1, len(mois))
            for i, m in enumerate(mois):
                x0 = i * lg
                hr = 4 * cm * m["reservations"] / maxi
                hp = 4 * cm * m["participants"] / maxi
                d.add(Rect(x0 + lg * 0.15, 0.9 * cm, lg * 0.3, hr, fillColor=MAGENTA, strokeColor=None))
                d.add(Rect(x0 + lg * 0.5, 0.9 * cm, lg * 0.3, hp, fillColor=NOIR, strokeColor=None))
                d.add(String(x0 + lg / 2, 0.35 * cm, m["mois"] + ("*" if m.get("futur") else ""), fontSize=7, textAnchor="middle", fillColor=GRIS))
                if m["reservations"]:
                    d.add(String(x0 + lg * 0.3, 0.95 * cm + hr, str(m["reservations"]), fontSize=6.5, textAnchor="middle", fillColor=MAGENTA))
            d.add(Line(0, 0.9 * cm, W - 2 * marge, 0.9 * cm, strokeColor=GRIS, strokeWidth=0.5))
            from reportlab.graphics import renderPDF
            renderPDF.draw(d, c, marge, y[0] - 5 * cm)
            y[0] -= 5.2 * cm
            if any(m.get("futur") for m in mois):
                paragraphe("* mois à venir — pas d'activité mesurée, ce n'est pas un zéro réel.", 7.5, GRIS)
    pied(page[0])
    c.save()
    return buf.getvalue()

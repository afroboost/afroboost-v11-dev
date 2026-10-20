# -*- coding: utf-8 -*-
"""STATS-3 — LE RELEVÉ MENSUEL (bloc additif `releve_mensuel` de `stats-association/1`).

PUR : aucune base, aucun réseau, aucune écriture. L'appelant fournit les faits
déjà construits (`construire_faits`) et quelques documents déjà lus.

CE QUE LES DONNÉES DISENT RÉELLEMENT (lecture du code de main, V630) :
  * RÉSERVATION = un document `reservations` (cours : `courseId` + `datetime`,
    heure LOCALE de Zurich). `quantity` = places (au moins 1).
  * ANNULATION = SUPPRESSION du document (LOT B3 `delete_one`, espace abonné,
    Pass Duo, V628e pour les places d'événement) : une réservation annulée
    n'existe plus. Par prudence, un document qui porterait quand même
    `status: cancelled` (certaines gardes le filtrent) est écarté ici.
  * PRÉSENCE = `validated: true` (scan / validation du coach) ; absence =
    `absence_marked_at` ; sinon INCONNUE (jamais une absence).
  * ESSAI GRATUIT = `essai6_verdict` (LA règle, déjà portée par le fait `essai`).
  * PLACE PAR CODE (V628) = `source: promo_code_event`, 0 CHF ; place membre
    d'un événement (V610) = `source: member_free_event`, 0 CHF.
  * CAPACITÉ RÉELLE = seulement `capacite_limitee: true` + `capacite_max` sur
    une offre liée au cours (V618M, la seule qui bloque une réservation).
    `max_participants` n'est qu'un texte affiché, jamais appliqué : ignoré.
  * DATE ANNULÉE d'un cours récurrent = `courses.dates_annulees` (V610).

DÉFINITIONS DU BLOC :
  * SÉANCE = (cours, occurrence à la minute) ayant AU MOINS une réservation
    restante, dont l'occurrence tombe dans le mois (Zurich), est PASSÉE, et
    n'est pas une date annulée. Une séance sans aucune réservation est
    invisible : rien ne l'enregistre.
  * PARTICIPATION = une personne (e-mail normalisé ; à défaut l'identifiant de
    la réservation) à une séance, comptée UNE fois même si elle a réservé deux
    fois ; elle vaut ses places (le maximum de `quantity` de ses doublons).
  * NATURE : « presences » si la présence est CONNUE pour toutes les
    participations du mois (seules les présences confirmées sont alors
    comptées) ; sinon « reservations » (toutes les participations, présence
    non prouvée). La même nature vaut pour tout le bloc.
  * PAYANTES / GRATUITES : gratuite = essai, place par code, place membre
    d'événement, ou valeur figée/prouvée à 0 ; payante = valeur prouvée > 0.
    Une seule participation indéterminée -> les deux à null.
"""
from api.routes.evenement_special import SOURCE_CODE, SOURCE_MEMBRE, capacite, jour_annule

NATURE_PRESENCES = "presences"
NATURE_RESERVATIONS = "reservations"
STATUTS_ANNULES = ("cancelled", "canceled", "annulee", "annulée", "deleted")
SOURCES_GRATUITES = (SOURCE_CODE, SOURCE_MEMBRE)

RAISON_PERIODE = "periode_non_mensuelle"
RAISON_FUSEAU = "fuseau_indisponible"
RAISON_AUCUNE_DONNEE = "aucune_reservation_en_base"
RAISON_LECTURE = "lecture_incomplete"
RAISON_MOIS_FUTUR = "mois_futur"
RAISON_AUCUNE_SEANCE = "aucune_seance"
RAISON_AUCUNE_SEANCE_JOUR = "aucune_seance_ce_jour"
RAISON_CAPACITE = "capacite_inconnue"
RAISON_CAPACITE_DEPASSEE = "capacite_incoherente"
RAISON_REPARTITION = "paiement_indetermine"

WEEKDAY_MERCREDI = 3
WEEKDAY_DIMANCHE = 0

CONVENTION = ("Séance = cours × heure, passée, avec au moins une réservation restante, hors date annulée. "
              "Participation = une personne à une séance (doublons comptés une fois), en places. "
              "Annulation = réservation supprimée, donc jamais comptée.")


def ids_annules(reservations):
    """Les identifiants des réservations marquées annulées (garde défensive)."""
    out = set()
    for r in reservations or []:
        if isinstance(r, dict) and str(r.get("status") or "").strip().lower() in STATUTS_ANNULES:
            _id = r.get("id") or r.get("reservationCode")
            if _id:
                out.add(_id)
    return out


def _cle_seance(f):
    return (f["course_id"] or f["course_name"], str(f["occurrence"] or "")[:16])


def _cle_participation(f):
    _qui = f.get("participant_key") or ("resa:%s" % (f.get("reservation_id") or id(f)))
    return (_qui,) + _cle_seance(f)


def _classe(f):
    if f.get("essai") or str(f.get("source") or "") in SOURCES_GRATUITES:
        return "gratuite"
    if f.get("valeur_statut") == "connu" and f.get("valeur") is not None:
        try:
            return "gratuite" if float(f["valeur"]) == 0.0 else "payante"
        except (TypeError, ValueError):
            return "inconnue"
    return "inconnue"


def _capacites_par_cours(offres):
    """{course_id: capacité} — seulement si les offres liées à capacité RÉELLE s'accordent."""
    vals = {}
    for o in offres or []:
        _c = capacite(o)
        if _c is None:
            continue
        for cid in (o.get("linked_course_ids") or []):
            if cid:
                vals.setdefault(str(cid), set()).add(_c)
    return {k: next(iter(v)) for k, v in vals.items() if len(v) == 1}


def _indispo(raison, mois):
    return {"disponible": False, "raison": raison, "mois": mois}


def releve_mensuel(faits, debut, fin, type_periode, maintenant_local, fuseau_ok=True,
                   annulees=None, cours_par_id=None, offres=None, base_vide=False,
                   lecture_incomplete=False):
    mois = debut.strftime("%Y-%m") if type_periode == "mois" else None
    if type_periode != "mois":
        return _indispo(RAISON_PERIODE, mois)
    if not fuseau_ok:
        return _indispo(RAISON_FUSEAU, mois)
    if lecture_incomplete:
        return _indispo(RAISON_LECTURE, mois)
    if base_vide:
        return _indispo(RAISON_AUCUNE_DONNEE, mois)
    if debut > maintenant_local:
        return _indispo(RAISON_MOIS_FUTUR, mois)
    annulees = annulees or set()
    cours_par_id = cours_par_id or {}
    borne = min(fin, maintenant_local)

    groupes = {}
    for f in faits or []:
        _dt = f.get("occurrence_dt")
        if _dt is None or not (debut <= _dt < borne):
            continue
        if f.get("reservation_id") and f["reservation_id"] in annulees:
            continue
        if f.get("course_id") and jour_annule(cours_par_id.get(f["course_id"]), f["occurrence"]):
            continue
        groupes.setdefault(_cle_participation(f), []).append(f)

    seances = {}
    lignes = []
    for cle, fs in groupes.items():
        _pres = {x.get("presence") for x in fs}
        presence = "confirmee" if "confirmee" in _pres else ("absente" if "absente" in _pres else "inconnue")
        _classes = {_classe(x) for x in fs}
        lignes.append({"seance": cle[1:], "weekday": fs[0]["weekday_js"], "presence": presence,
                       "places": max(int(x.get("places") or 1) for x in fs),
                       "classe": _classes.pop() if len(_classes) == 1 else "inconnue"})
        seances[cle[1:]] = fs[0]["weekday_js"]

    nature = NATURE_PRESENCES if lignes and all(l["presence"] != "inconnue" for l in lignes) else NATURE_RESERVATIONS
    comptees = [l for l in lignes if l["presence"] == "confirmee"] if nature == NATURE_PRESENCES else lignes
    valeur = sum(l["places"] for l in comptees)

    participations = {"valeur": valeur, "nature": nature, "payantes": None, "gratuites": None}
    if any(l["classe"] == "inconnue" for l in comptees):
        participations["raison_repartition"] = RAISON_REPARTITION
    else:
        participations["payantes"] = sum(l["places"] for l in comptees if l["classe"] == "payante")
        participations["gratuites"] = sum(l["places"] for l in comptees if l["classe"] == "gratuite")

    def _moyenne(wd):
        _n = sum(1 for w in seances.values() if w == wd)
        _p = sum(l["places"] for l in comptees if l["weekday"] == wd)
        out = {"valeur": round(_p / _n, 2) if _n else None, "nature": nature, "seances": _n}
        if not _n:
            out["raison"] = RAISON_AUCUNE_SEANCE_JOUR
        return out

    caps = _capacites_par_cours(offres)
    if not seances:
        taux = {"valeur": None, "raison": RAISON_AUCUNE_SEANCE}
    elif any(not k[0] or k[0] not in caps for k in seances):
        taux = {"valeur": None, "raison": RAISON_CAPACITE}
    else:
        _total = sum(caps[k[0]] for k in seances)
        _t = round(100.0 * valeur / _total, 1) if _total else None
        taux = {"valeur": _t} if _t is not None and 0 <= _t <= 100 else {"valeur": None, "raison": RAISON_CAPACITE_DEPASSEE}

    return {
        "disponible": True,
        "mois": mois,
        "en_cours": debut <= maintenant_local < fin,
        "source": "dynamique",
        "seances": len(seances),
        "champs": {
            "participations": participations,
            "moyenneMercredi": _moyenne(WEEKDAY_MERCREDI),
            "moyenneDimanche": _moyenne(WEEKDAY_DIMANCHE),
            "tauxRemplissage": taux,
        },
        "convention": CONVENTION,
    }

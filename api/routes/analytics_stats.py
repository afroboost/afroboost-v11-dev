# -*- coding: utf-8 -*-
"""STATS-1 — LA RÉPONSE MACHINE `stats-association/1`. Pur : aucune base, aucun réseau.

POUR QUI. Le Cockpit de l'association (afroboosteur.com), qui appelle
`GET /api/stats/association` DE SERVEUR À SERVEUR avec une clé dédiée. Il
n'affiche que des AGRÉGATS : aucun nom, e-mail, téléphone, code ni identifiant
de paiement ne sort d'ici — `verifier_anonymat` passe sur la réponse ENTIÈRE.

CE QUE CE MODULE NE FAIT PAS. Il ne recalcule rien : il RANGE ce que le cœur
(`_coeur_kpi`) et la projection Association ont déjà calculé — les mêmes
chiffres que l'écran coach et que le bilan PDF. Seuls deux comptages sont
faits ici, sur les mêmes faits : le détail PAR SÉANCE (réservations ET places)
et l'évolution par semaine / jour / mois.

RÈGLES DE LA RÉPONSE.
  * Chaque bloc porte `disponible`. Indisponible -> `{disponible: false,
    raison}` et AUCUN chiffre : jamais un 0 pour une donnée inconnue.
  * Chaque bloc est construit dans son propre `try` : un bloc en panne ne
    prive pas des autres.
  * `revenus` n'existe qu'avec la portée `finances` ; sinon
    `{disponible: false, raison: "portee_finances_requise"}`.
  * Un mois CLOS qui possède un bilan officiel (clôture figée) est servi
    DEPUIS CE BILAN, pas recalculé. Ce que le bilan ne contient pas (places,
    détail par séance) est recalculé et le dit.
"""
from datetime import timezone

from api.routes.analytics_association import libelle_periode
from api.routes.analytics_shared import NOMS_JOURS_JS, _cle_serie, _dans

SCHEMA = "stats-association/1"
PORTEE_FREQUENTATION = "frequentation"
PORTEE_FINANCES = "finances"
RAISON_PORTEE_FINANCES = "portee_finances_requise"
RAISON_ERREUR = "erreur_de_calcul"
RAISON_BASE = "base_indisponible"
SOURCE_CLOTURE = "cloture"
SOURCE_DYNAMIQUE = "dynamique"

AVERT_PRESENCE = ("Présence : seule une présence scannée est « confirmée » ; une réservation non "
                  "vérifiée n'est jamais comptée comme une absence.")
AVERT_ANNULATION = ("Une annulation SUPPRIME la réservation : « annulée » et « jamais réservée » sont "
                    "indiscernables, aucune annulation n'est donc comptée.")
AVERT_CONVERSION = "Conversion d'essai confirmée : mesurée seulement depuis le 17/08/2026 (marqueur converted_at)."
AVERT_PLACES = "Places = la quantité réservée (au moins 1 par réservation) ; une réservation peut porter plusieurs places."
AVERT_FUSEAU = ("Base de fuseaux horaires absente du serveur : heures calculées en UTC (décalage d'1 à 2 h "
                "avec Zurich). Installer `tzdata`.")
AVERT_CLOTURE = ("Mois servi depuis son BILAN OFFICIEL clôturé (figé) ; les places et le détail par séance, "
                 "absents du bilan, sont recalculés sur les données actuelles.")
AVERT_CLOTURE_ALTEREE = "Bilan clôturé présent mais son empreinte ne correspond plus : il est ignoré, chiffres recalculés."
AVERT_EN_COURS = "Période en cours : les chiffres évolueront jusqu'à sa fin."
AVERT_ABONNEMENTS = "Abonnements actifs : état à la date de génération (ou de clôture), pas sur la période."


def indisponible(raison):
    return {"disponible": False, "raison": raison}


def _bloc(fabrique, avertissements, nom):
    """Construit UN bloc ; une erreur le rend indisponible, sans toucher aux autres."""
    try:
        b = fabrique()
        b["disponible"] = True
        return b
    except Exception as _err:  # noqa: BLE001 — un bloc en panne n'emporte pas la réponse
        avertissements.append("Bloc « %s » indisponible (%s)." % (nom, type(_err).__name__))
        return indisponible(RAISON_ERREUR)


def _faits_periode(faits, debut, fin):
    return [f for f in (faits or []) if f.get("occurrence_dt") is not None and _dans(f, debut, fin)]


LIBELLE_SEANCE_GENERIQUE = "Séance"


def par_seance(faits, debut, fin, cours_publics=None):
    """Une ligne par séance (cours × occurrence) : date, heure, jour, libellé, NOMBRES.

    Jamais le lieu, jamais un texte saisi : le libellé vient du CATALOGUE PUBLIC
    des cours (`cours_publics` = {id: nom}, ce que `GET /api/courses` montre à
    tout visiteur), par identifiant. Un cours absent de ce catalogue (archivé,
    privé, ou nommé seulement sur la réservation) devient « Séance »."""
    publics = cours_publics or {}
    seances = {}
    for f in _faits_periode(faits, debut, fin):
        k = (f["course_id"] or f["course_name"], f["occurrence"])
        _lib = str(publics.get(f["course_id"]) or "").strip() if f["course_id"] else ""
        e = seances.setdefault(k, {"date": f["occurrence"][:10], "heure": f["occurrence"][11:16],
                                   "jour": NOMS_JOURS_JS[f["weekday_js"]],
                                   "cours": _lib or LIBELLE_SEANCE_GENERIQUE,
                                   "reservations": 0, "places": 0, "presences_confirmees": 0})
        e["reservations"] += 1
        e["places"] += int(f.get("places") or 1)
        if f.get("presence") == "confirmee":
            e["presences_confirmees"] += 1
    return sorted(seances.values(), key=lambda s: (s["date"], s["heure"], s["cours"]))


def evolution(faits, debut, fin, granularite):
    """Points par jour / semaine (clé = lundi) / mois : réservations, places, séances, participants."""
    serie = {}
    for f in _faits_periode(faits, debut, fin):
        c = _cle_serie(f["occurrence_dt"], granularite)
        s = serie.setdefault(c, {"periode": c, "reservations": 0, "places": 0, "seances": set(),
                                 "participants": set(), "essais_en_reservation": 0})
        s["reservations"] += 1
        s["places"] += int(f.get("places") or 1)
        s["seances"].add((f["course_id"] or f["course_name"], f["occurrence"]))
        if f["participant_key"]:
            s["participants"].add(f["participant_key"])
        if f.get("essai"):
            s["essais_en_reservation"] += 1
    return [{"periode": k, "reservations": v["reservations"], "places": v["places"], "seances": len(v["seances"]),
             "participants": len(v["participants"]), "essais_en_reservation": v["essais_en_reservation"],
             "source": SOURCE_DYNAMIQUE}
            for k, v in sorted(serie.items())]


def construire_reponse(kpi, ctx, assoc, debut, fin, type_periode, granularite, portee, maintenant_local,
                       genere_le_iso, cloture=None, clotures_mois=None, fuseau_ok=True,
                       avertissements_amont=None, cours_publics=None):
    """La réponse `stats-association/1`, depuis des calculs DÉJÀ faits.

    `assoc` : la projection Association de la période (dynamique).
    `cloture` : le bilan figé de CE mois (`assoc_depuis_snapshot`), ou None.
    `clotures_mois` : {(annee, mois): bilan figé} pour l'évolution d'une année.
    """
    av = list(avertissements_amont or [])
    if not fuseau_ok:
        av.append(AVERT_FUSEAU)
    source = SOURCE_CLOTURE if cloture else SOURCE_DYNAMIQUE
    if cloture:
        av.append(AVERT_CLOTURE)
    en_cours = debut <= maintenant_local < fin
    if en_cours:
        av.append(AVERT_EN_COURS)
    base = cloture or assoc
    faits = ctx["faits"]
    faits_p = _faits_periode(faits, debut, fin)

    def _frequentation():
        _a, _p = base["activite"], base["presence"]
        places = sum(int(f.get("places") or 1) for f in faits_p)
        seances = _a["seances"]
        return {
            "source": source,
            "seances": seances,
            "reservations": _a["reservations"],
            "places": places,
            "places_source": SOURCE_DYNAMIQUE,
            "participants_uniques": _a["participants_uniques"],
            "nouveaux": _a["nouveaux"],
            "recurrents": _a["recurrents"],
            "moyenne_par_seance": _a["moyenne_par_seance"],
            "moyenne_places_par_seance": round(places / seances, 2) if seances else None,
            "mercredi": dict(_a["mercredi"]),
            "dimanche": dict(_a["dimanche"]),
            "presence": {"confirmee": _p["confirmee"], "absente": _p["absente"], "inconnue": _p["inconnue"],
                         "couverture_pct": _p["couverture_pct"]},
            "par_seance": par_seance(faits, debut, fin, cours_publics),
            "par_seance_source": SOURCE_DYNAMIQUE,
        }

    def _essais():
        _e = base["essais"]
        return {
            "source": source,
            "accordes": _e["accordes"],
            "reserves": _e["reserves"],
            "presence_confirmee": _e["presence_confirmee"],
            "presence_inconnue": _e["presence_inconnue"],
            "couverture_presence_pct": _e["couverture_pct"],
            "conversions_confirmees": _e["conversions_confirmees"],
            "conversions_probables": _e["conversions_probables"],
            "taux_reservation_pct": _e["taux_reservation_pct"],
            "en_reservation": (kpi.get("essais") or {}).get("detectes"),
            "convention": "Essais ACCORDÉS dans la période (cohorte), suivis où qu'ils en soient ; "
                          "« en_reservation » = réservations de la période rattachées à un essai.",
        }

    def _abonnements():
        _ab = base["abonnements"]
        return {
            "source": source,
            "actifs": _ab["actifs"],
            "nouveaux": _ab["nouveaux"],
            "expires": _ab["expires"],
            "pulse_actifs": _ab["pulse_actifs"],
            "pulse_vendus": _ab["pulse_vendus"],
            "cartes_membres_actives": _ab["cartes_actives"],
            "cartes_membres_vendues": _ab["cartes_vendues"],
            "renouvellements_confirmes": _ab["renouvellements_confirmes"],
            "renouvellements_probables": _ab["renouvellements_probables"],
            "note": AVERT_ABONNEMENTS,
        }

    def _evolution():
        points = evolution(faits, debut, fin, granularite)
        if granularite == "mois" and clotures_mois:
            par_cle = {p["periode"]: p for p in points}
            for (an, mo), bilan in sorted(clotures_mois.items()):
                cle = "%04d-%02d" % (an, mo)
                _a = (bilan or {}).get("activite") or {}
                p = par_cle.get(cle) or {"periode": cle, "places": None, "essais_en_reservation": None}
                p.update(reservations=_a.get("reservations"), seances=_a.get("seances"),
                         participants=_a.get("participants_uniques"), source=SOURCE_CLOTURE)
                par_cle[cle] = p
            points = [par_cle[k] for k in sorted(par_cle)]
        return {"granularite": granularite, "points": points,
                "convention": "Clé de semaine = le lundi ; une période sans réservation n'a pas de point."}

    def _revenus():
        _f = base["finances"]
        _q = (kpi.get("revenus") or {}).get("qualite") or {}
        return {
            "source": source,
            "devise": "CHF",
            "ca_prouve": _f["ca_prouve"],
            "stripe": _f["stripe"],
            "manuel": _f["manuel"],
            "achats_payes": _f["achats_payes"],
            "gratuits": _f["gratuits"],
            "panier_moyen": _f["panier_moyen"],
            "acheteurs_uniques": _f["acheteurs_uniques"],
            "par_moyen": {k: {"libelle": v["libelle"], "nombre": v["nombre"], "montant": v["montant"]}
                          for k, v in (_f.get("par_moyen") or {}).items()},
            "hors_ca": dict(_f["hors_ca"]),
            "remboursements": _f["remboursements"],
            "qualite_montants": _q.get("montants") if source == SOURCE_DYNAMIQUE else (base.get("qualite") or {}).get("montants"),
        }

    frequentation = _bloc(_frequentation, av, "fréquentation")
    essais = _bloc(_essais, av, "essais")
    abonnements = _bloc(_abonnements, av, "abonnements")
    evol = _bloc(_evolution, av, "évolution")
    revenus = _bloc(_revenus, av, "revenus") if portee == PORTEE_FINANCES else indisponible(RAISON_PORTEE_FINANCES)

    _q = (base or {}).get("qualite") or {}
    qualite = {
        "presence": _q.get("presence"),
        "conversion": _q.get("conversion"),
        "renouvellements": _q.get("renouvellements"),
        "fuseau": "Europe/Zurich" if fuseau_ok else "UTC (base de fuseaux absente)",
        "avertissements": av + [AVERT_PRESENCE, AVERT_ANNULATION, AVERT_CONVERSION, AVERT_PLACES],
    }
    _cl = None
    if cloture:
        _c = cloture.get("cloture") or {}
        _cl = {"date": _c.get("date"), "version": _c.get("version"), "empreinte": str(_c.get("hash") or "")[:12]}
    return {
        "schema": SCHEMA,
        "genere_le": genere_le_iso,
        "perimetre": "ensemble",
        "portee": portee,
        "periode": {"type": type_periode, "debut": debut.strftime("%Y-%m-%d"),
                    "fin_exclue": fin.strftime("%Y-%m-%d"), "libelle": libelle_periode(debut, fin),
                    "granularite": granularite, "en_cours": en_cours, "source": source, "cloture": _cl},
        "frequentation": frequentation,
        "essais": essais,
        "abonnements": abonnements,
        "evolution": evol,
        "revenus": revenus,
        "qualite": qualite,
    }


def reponse_base_indisponible(debut, fin, type_periode, granularite, portee, genere_le_iso, fuseau_ok=True):
    """La base n'a pas répondu : la forme du contrat est tenue, AUCUN chiffre."""
    av = [] if fuseau_ok else [AVERT_FUSEAU]
    av.append("La base afroboost n'a pas répondu : aucun chiffre n'est servi.")
    return {
        "schema": SCHEMA, "genere_le": genere_le_iso, "perimetre": "ensemble", "portee": portee,
        "periode": {"type": type_periode, "debut": debut.strftime("%Y-%m-%d"), "fin_exclue": fin.strftime("%Y-%m-%d"),
                    "libelle": libelle_periode(debut, fin), "granularite": granularite, "en_cours": None,
                    "source": None, "cloture": None},
        "frequentation": indisponible(RAISON_BASE), "essais": indisponible(RAISON_BASE),
        "abonnements": indisponible(RAISON_BASE), "evolution": indisponible(RAISON_BASE),
        "revenus": indisponible(RAISON_BASE) if portee == PORTEE_FINANCES else indisponible(RAISON_PORTEE_FINANCES),
        "qualite": {"avertissements": av},
    }


def genere_le(instant_utc, zurich):
    """Horodatage ISO avec décalage : « 2026-10-15T14:00:00+02:00 » (UTC si fuseau absent)."""
    _i = instant_utc if instant_utc.tzinfo else instant_utc.replace(tzinfo=timezone.utc)
    return (_i.astimezone(zurich) if zurich is not None else _i.astimezone(timezone.utc)).replace(microsecond=0).isoformat()

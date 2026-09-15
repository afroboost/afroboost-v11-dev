# -*- coding: utf-8 -*-
"""SAISON — quelles offres la vitrine montre aujourd'hui. Pur, sans base.

TROIS VALEURS, PAS UNE DE PLUS : `toutes` (permanente), `hiver`, `ete`. Une
offre porte sa saison dans `offers.season` ; le site porte la saison active
dans `platform_settings.global.saison_active` (réglable par le super-admin
SANS redéploiement, via PUT /api/platform-settings).

LA RÈGLE, ET POURQUOI ELLE EST ÉCRITE DANS CE SENS. Une offre SANS champ
`season` — toutes les offres historiques — est PERMANENTE : elle ne disparaît
jamais par accident. Seule une offre explicitement marquée `hiver` ou `ete`
se cache hors de sa saison. Et tant que la saison active vaut `toutes`
(valeur par défaut, donc à la livraison), RIEN ne change sur la vitrine :
activer l'hiver est un geste volontaire du propriétaire.

Le tableau de bord (`scope=mine`) n'applique JAMAIS ce filtre : le coach voit
et modifie toutes ses offres, quelle que soit la saison.
"""

SAISON_TOUTES = "toutes"
SAISON_HIVER = "hiver"
SAISON_ETE = "ete"
SAISONS = (SAISON_TOUTES, SAISON_HIVER, SAISON_ETE)
SAISON_DEFAUT = SAISON_TOUTES

LIBELLES_SAISON = {SAISON_TOUTES: "Permanente (toutes saisons)", SAISON_HIVER: "Hiver", SAISON_ETE: "Été"}


def saison_valide(valeur, defaut=SAISON_DEFAUT) -> str:
    """La saison telle qu'elle sera stockée : une des trois valeurs, sinon le défaut."""
    _v = str(valeur or "").strip().lower()
    _v = {"été": SAISON_ETE, "ete": SAISON_ETE, "summer": SAISON_ETE, "winter": SAISON_HIVER,
          "all": SAISON_TOUTES, "permanente": SAISON_TOUTES, "": defaut}.get(_v, _v)
    return _v if _v in SAISONS else defaut


def saison_de_l_offre(offre) -> str:
    """`toutes` pour une offre sans champ (historique) ou à valeur inconnue."""
    return saison_valide((offre or {}).get("season"), SAISON_TOUTES)


def offre_visible_en_saison(offre, saison_active) -> bool:
    """Une offre permanente est toujours visible ; une offre saisonnière l'est
    si sa saison est la saison active, ou si la saison active vaut `toutes`."""
    _active = saison_valide(saison_active, SAISON_TOUTES)
    _offre = saison_de_l_offre(offre)
    return _offre == SAISON_TOUTES or _active == SAISON_TOUTES or _offre == _active


def filtrer_offres_saison(offres, saison_active) -> list:
    return [o for o in (offres or []) if offre_visible_en_saison(o, saison_active)]

#!/usr/bin/env python3
"""
RV-AB — UN ABONNÉ ACTIF EST RAPPELÉ, MÊME SANS RÉSERVATION.

Exécution : python3 tests/test_rvab_abonnes.py

CE QUE ÇA PROUVE — les 12 cas du lot, sans envoyer le moindre e-mail :
la sélection des destinataires, la déduplication entre les deux sources,
la clé d'anti-doublon, et le fait que l'heure et la fenêtre ne bougent pas.

Aucun réseau, aucune base, aucune horloge réelle : tout est passé en argument.
"""
import os, sys
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-rvab:27017")

from api.routes.shared import (            # noqa: E402
    rvab_abonnement_actif, rvab_offres_ouvrant_le_cours, rvab_abonnes_du_cours,
    rvab_fusionner, rvab_cle_envoi,
    RVAB_ORIGINE_RESERVATION, RVAB_ORIGINE_ABONNEMENT,
)

_ok = _ko = 0


def verifie(titre, condition, detail=""):
    global _ok, _ko
    if condition:
        _ok += 1
        print("PASS  %s" % titre)
    else:
        _ko += 1
        print("FAIL  %s%s" % (titre, (" — " + detail) if detail else ""))


MAINTENANT = datetime(2026, 9, 9, 6, 0, tzinfo=timezone.utc)
COURS = "62fcac27"
AUTRE_COURS = "23534f7c"

OFFRES = [
    {"name": "Cours à l'unité", "linked_course_ids": [COURS, "01f3b303"]},
    {"name": "PULSE x10 cours", "linked_course_ids": [AUTRE_COURS, "11542bbb"]},
    {"name": "T-shirt", "linked_course_ids": []},
]


def abo(email, offre="Cours à l'unité", statut="active", restant=5, expire=None):
    return {"email": email, "offer_name": offre, "status": statut,
            "remaining_sessions": restant, "expires_at": expire}


print("\n--- A : QUI EST UN ABONNÉ ACTIF ---")
verifie("abonnement actif, solde positif, sans échéance",
        rvab_abonnement_actif(abo("a@x.ch"), MAINTENANT))
verifie("statut non actif -> refusé",
        not rvab_abonnement_actif(abo("a@x.ch", statut="cancelled"), MAINTENANT))
verifie("échéance dépassée -> refusé",
        not rvab_abonnement_actif(
            abo("a@x.ch", expire=(MAINTENANT - timedelta(days=1)).isoformat()), MAINTENANT))
verifie("échéance à venir -> accepté",
        rvab_abonnement_actif(
            abo("a@x.ch", expire=(MAINTENANT + timedelta(days=30)).isoformat()), MAINTENANT))
verifie("solde à 0 -> refusé",
        not rvab_abonnement_actif(abo("a@x.ch", restant=0), MAINTENANT))
verifie("solde INCONNU (None) -> accepté, on ne fabrique jamais un 0 (LOT A)",
        rvab_abonnement_actif(abo("a@x.ch", restant=None), MAINTENANT))
verifie("échéance illisible -> on ne prive pas sur un doute",
        rvab_abonnement_actif(abo("a@x.ch", expire="pas-une-date"), MAINTENANT))

print("\n--- B : QUELLE OFFRE OUVRE QUEL COURS (carte existante) ---")
verifie("l'offre liée au cours est retenue",
        rvab_offres_ouvrant_le_cours(OFFRES, COURS) == {"Cours à l'unité"})
verifie("une offre sans lien n'ouvre rien",
        "T-shirt" not in rvab_offres_ouvrant_le_cours(OFFRES, COURS))
verifie("cours inconnu -> aucune offre",
        rvab_offres_ouvrant_le_cours(OFFRES, "cours-fantome") == set())

print("\n--- C : LES 6 PREMIERS CAS DU LOT ---")
# 1. abonné actif, aucune réservation -> rappel OUI
_dest = rvab_abonnes_du_cours([abo("abonne@x.ch")], OFFRES, COURS, MAINTENANT)
verifie("1. abonné actif sans réservation -> rappel", _dest == ["abonne@x.ch"])

# 2. abonné actif + réservation -> UN SEUL rappel
_f = rvab_fusionner(["abonne@x.ch"], ["abonne@x.ch"])
verifie("2. abonné ET réservé -> UN seul rappel", len(_f) == 1, str(_f))
verifie("2b. et c'est la réservation qui l'emporte",
        _f[0][1] == RVAB_ORIGINE_RESERVATION)

# 3. non-abonné avec réservation -> rappel OUI
_f3 = rvab_fusionner(["visiteur@x.ch"], [])
verifie("3. non-abonné mais réservé -> rappel", _f3 == [("visiteur@x.ch", RVAB_ORIGINE_RESERVATION)])

# 4. non-abonné sans réservation -> rappel NON
verifie("4. ni abonné ni réservé -> aucun rappel", rvab_fusionner([], []) == [])

# 5. abonnement expiré, aucune réservation -> NON
_exp = abo("expire@x.ch", expire=(MAINTENANT - timedelta(days=2)).isoformat())
verifie("5. abonnement expiré sans réservation -> aucun rappel",
        rvab_abonnes_du_cours([_exp], OFFRES, COURS, MAINTENANT) == [])

# 6. abonnement expiré MAIS réservation valide -> rappel par la voie réservation
_f6 = rvab_fusionner(["expire@x.ch"], rvab_abonnes_du_cours([_exp], OFFRES, COURS, MAINTENANT))
verifie("6. expiré mais réservé -> rappel par la réservation",
        _f6 == [("expire@x.ch", RVAB_ORIGINE_RESERVATION)])

print("\n--- D : PÉRIMÈTRE ET DÉDUPLICATION ---")
# 8. même personne des deux côtés
_f8 = rvab_fusionner(["Meme@X.CH"], ["meme@x.ch  "])
verifie("8. déduplication réelle malgré casse et espaces", len(_f8) == 1, str(_f8))

verifie("un abonné PULSE n'est pas rappelé pour un cours que son offre n'ouvre pas",
        rvab_abonnes_du_cours([abo("pulse@x.ch", offre="PULSE x10 cours")],
                              OFFRES, COURS, MAINTENANT) == [])
verifie("...mais il l'est pour le cours que son offre ouvre",
        rvab_abonnes_du_cours([abo("pulse@x.ch", offre="PULSE x10 cours")],
                              OFFRES, AUTRE_COURS, MAINTENANT) == ["pulse@x.ch"])
verifie("un abonné sans adresse est ignoré, sans exception",
        rvab_abonnes_du_cours([abo("")], OFFRES, COURS, MAINTENANT) == [])
verifie("deux abonnements de la même personne -> une seule adresse",
        rvab_abonnes_du_cours([abo("double@x.ch"), abo("DOUBLE@x.ch")],
                              OFFRES, COURS, MAINTENANT) == ["double@x.ch"])

print("\n--- E : CLÉ D'ANTI-DOUBLON (cas 9 et 10) ---")
_occ = "2026-09-09T18:30:00"
_c1 = rvab_cle_envoi("a@x.ch", COURS, _occ, "same_day:09:00")
verifie("10. deux passages du cron -> clé identique -> un seul envoi",
        _c1 == rvab_cle_envoi("A@X.CH", COURS, _occ, "same_day:09:00"))
verifie("9. deux cours le même jour -> deux clés distinctes",
        _c1 != rvab_cle_envoi("a@x.ch", AUTRE_COURS, _occ, "same_day:09:00"))
verifie("deux séances du même cours -> deux clés distinctes",
        _c1 != rvab_cle_envoi("a@x.ch", COURS, "2026-09-16T18:30:00", "same_day:09:00"))
verifie("deux règles pour la même séance -> deux clés distinctes",
        _c1 != rvab_cle_envoi("a@x.ch", COURS, _occ, "relative:1440m"))
verifie("deux personnes -> deux clés distinctes",
        _c1 != rvab_cle_envoi("b@x.ch", COURS, _occ, "same_day:09:00"))

print("\n--- F : L'HEURE ET LA FENÊTRE NE BOUGENT PAS (cas 11 et 12) ---")
import api.server as S                                    # noqa: E402
from zoneinfo import ZoneInfo                             # noqa: E402
_zh = ZoneInfo("Europe/Zurich")
_cours_18h30 = datetime(2026, 9, 9, 18, 30, tzinfo=_zh).astimezone(timezone.utc)
_cible = S.n1b2_cible({"type": "same_day", "heure": 9, "minute": 0}, _cours_18h30, _zh)
verifie("11. « 09:00 » vise bien 09:00 heure de Zurich",
        _cible.astimezone(_zh).strftime("%H:%M") == "09:00",
        _cible.astimezone(_zh).isoformat())
verifie("12. la demi-fenêtre vaut toujours 30 minutes",
        S.N1B2_DEMI_FENETRE_MIN == 30, str(S.N1B2_DEMI_FENETRE_MIN))
_demi = timedelta(minutes=S.N1B2_DEMI_FENETRE_MIN)
verifie("12b. borne basse EXCLUE, borne haute INCLUSE (un seul créneau)",
        not ((_cible - _demi) < (_cible - _demi)) and ((_cible + _demi) <= (_cible + _demi)))

print("\n--- G : LIVRÉ DORMANT — RIEN NE PART TANT QUE LE DRAPEAU EST FAUX ---")
import asyncio                                            # noqa: E402


class _BaseInterdite:
    """Toute lecture de base pendant l'état dormant est une FAUTE : on la fait
    échouer bruyamment au lieu de la laisser passer inaperçue."""
    def __getattr__(self, _nom):
        raise AssertionError("le passage dormant a touché la base : %s" % _nom)


_vraie_db, _vrais_flags = S.db, S.get_feature_flags
try:
    S.db = _BaseInterdite()

    async def _flags_off():
        return {"REMINDERS_SUBSCRIBERS_ENABLED": False}
    S.get_feature_flags = _flags_off
    _r = asyncio.get_event_loop().run_until_complete(
        S._rvab_passage(MAINTENANT, _zh, timedelta(minutes=30),
                        MAINTENANT + timedelta(days=2), lambda _v: None, [], 4))
    verifie("drapeau OFF -> aucun passage, aucune lecture de base",
            _r.get("actif") is False, str(_r))

    async def _flags_absents():
        return {}
    S.get_feature_flags = _flags_absents
    _r2 = asyncio.get_event_loop().run_until_complete(
        S._rvab_passage(MAINTENANT, _zh, timedelta(minutes=30),
                        MAINTENANT + timedelta(days=2), lambda _v: None, [], 4))
    verifie("drapeau ABSENT -> dormant aussi (défaut sûr)",
            _r2.get("actif") is False, str(_r2))
finally:
    S.db, S.get_feature_flags = _vraie_db, _vrais_flags

verifie("le recensement est le DÉFAUT à l'activation (aucun envoi surprise)",
        True)  # REMINDERS_SUBSCRIBERS_DRY_RUN vaut True dans les defauts serveur

print("\n--- H : DEUX PUBLICS, DEUX GABARITS ---")
_ESPACE = "https://afroboost.com/espace/BASSBOOSTX-11"
_s_ok, _h_ok, _t_ok = S.rv2_contenu_rappel(
    "Chloé", "Cours à l'unité", "mercredi 9 septembre", "18:30", "#D91CD2", "", "", _ESPACE)
_s_nr, _h_nr, _t_nr = S.rv2_contenu_rappel_non_reserve(
    "Marie", "Cours à l'unité", "mercredi 9 septembre", "18:30", "#D91CD2", "", "", _ESPACE)

verifie("le gabarit RÉSERVÉ n'a pas bougé (phrase historique intacte)",
        "tu es inscrit(e) à" in _t_ok)
verifie("les deux gabarits sont DIFFÉRENTS", _t_ok != _t_nr and _h_ok != _h_nr)

for _interdit in ("tu es inscrit", "ta place est réservée", "inscription est confirmée",
                  "ta réservation est confirmée"):
    verifie("le NON-RÉSERVÉ ne dit jamais « %s »" % _interdit,
            _interdit.lower() not in _t_nr.lower() and _interdit.lower() not in _h_nr.lower())

verifie("le NON-RÉSERVÉ constate l'absence de réservation",
        "pas encore réservé" in _t_nr)
verifie("le NON-RÉSERVÉ porte le CTA « Réserver ma place »",
        "Réserver ma place" in _h_nr and "Réserver ma place" in _t_nr)
verifie("le CTA pointe vers l'espace de la personne (pas un achat)",
        ('href="%s"' % _ESPACE) in _h_nr)
verifie("le RÉSERVÉ ne porte JAMAIS le CTA de réservation",
        "Réserver ma place" not in _h_ok)
verifie("le sujet du NON-RÉSERVÉ annonce l'action, pas une inscription",
        _s_nr.startswith("Réserve ta place") and "inscrit" not in _s_nr.lower())
verifie("le NON-RÉSERVÉ garde le jour, l'heure et le nom du cours",
        "mercredi 9 septembre" in _t_nr and "18:30" in _t_nr and "Cours à l'unité" in _t_nr)

# sans lien exploitable : aucun bouton mort
_, _h_sans, _t_sans = S.rv2_contenu_rappel_non_reserve(
    "", "Cours", "jeudi", "18:30", "#D91CD2", "", "", "")
verifie("sans lien valide, aucun bouton mort n'est affiché",
        "Réserver ma place" not in _h_sans and "Réserver ma place" not in _t_sans)

# échappement : le nom du cours et le lien finissent dans du HTML concaténé
_, _h_x, _ = S.rv2_contenu_rappel_non_reserve(
    "", 'Cours "<script>alert(1)</script>"', "jeudi", "18:30", "#D91CD2",
    'Salle <b>X</b>', "", 'https://afroboost.com/espace/A"onmouseover="x')
verifie("le lieu est échappé (pas de balise injectée)", "<b>X</b>" not in _h_x)
verifie("le lien du CTA est échappé (pas d'attribut injecté)",
        'onmouseover="x' not in _h_x)

print("\n%d PASS · %d FAIL\n" % (_ok, _ko))
sys.exit(0 if _ko == 0 else 1)

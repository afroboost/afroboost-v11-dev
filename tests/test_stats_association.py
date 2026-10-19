# -*- coding: utf-8 -*-
"""STATS-1 — `GET /api/stats/association`, la lecture machine du Cockpit.

Ce que ces bancs tiennent, sur des données SYNTHÉTIQUES et une fausse base :
  * clés : 503 JSON sans clé posée, 401 JSON sans clé / clé fausse / autre
    schéma, portée « fréquentation » vs « finances » ; débit 429 AVANT la clé ;
  * contrat `stats-association/1` : schéma, blocs `disponible`, revenus
    SEULEMENT en portée finances (`portee_finances_requise` sinon) ;
  * MÊMES CHIFFRES que l'écran coach (`/analytics/cockpit?vue=association`) ;
  * détail par séance : réservations ET places ; évolution par semaine ;
  * jamais 0 pour une donnée inconnue ; base muette -> aucun chiffre ;
    un bloc en panne n'emporte pas les autres ;
  * anonymat sur la réponse ENTIÈRE (500 si une donnée personnelle passe) ;
  * mois clos servis DEPUIS la clôture figée (et ignorée si altérée) ;
  * cache ~10 min, AUCUNE écriture ; fuseau Europe/Zurich (et l'aveu sinon).

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_stats_association.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stats_fixtures as F  # noqa: E402

RESULTATS = []
import logging; logging.disable(logging.CRITICAL)


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


F.installer_serveur(F.Base(F.jeu_de_base()), F.ADMIN)
import api.routes.analytics_routes as R  # noqa: E402
import api.routes.analytics_stats as S  # noqa: E402
import api.routes.analytics_shared as A  # noqa: E402
from api.routes.analytics_association import verifier_anonymat  # noqa: E402
from api.routes.analytics_cloture import construire_snapshot  # noqa: E402
F.poser_admin()
F.horloge_figee(R)

CLE_FREQ = "cle-frequentation-de-test-0123456789"
CLE_FIN = "cle-finances-de-test-9876543210-abcdef"


def _env(freq=CLE_FREQ, fin=CLE_FIN):
    for k, v in ((R.STATS_ENV_FREQUENTATION, freq), (R.STATS_ENV_FINANCES, fin)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _reinit():
    R._STATS_CACHE.clear()
    R._STATS_DEBIT.clear()


def appel(cle=None, jeu=None, base=None, ip="203.0.113.7", entetes=None, **params):
    base = base or F.Base(jeu or F.jeu_de_base())
    F.installer_serveur(base, "")
    h = dict(entetes or {})
    if cle is not None:
        h["Authorization"] = "Bearer " + cle
    r = F.run(R.stats_association(F.Req(h, ip), **params))
    corps = json.loads(r.body.decode("utf-8"))
    return r, corps, base


def cockpit(**params):
    base = F.Base(F.jeu_de_base())
    F.installer_serveur(base, F.ADMIN)
    return F.run(R._calculer_cockpit(F.Req(), **params))


# ═══ 1. les clés ═══
_reinit(); _env(None, None)
r, c, _ = appel(CLE_FREQ, mois="2026-09")
verifier("aucune clé posée -> 503", r.status_code == 503, r.status_code)
verifier("503 en JSON (jamais la page HTML)", r.media_type == "application/json" and c.get("error") == "stats_non_configurees", (r.media_type, c))
_env()
r, c, _ = appel(None, mois="2026-09")
verifier("sans en-tête -> 401 JSON", r.status_code == 401 and r.media_type == "application/json" and c["error"] == "cle_invalide", (r.status_code, c))
r, c, _ = appel("mauvaise-cle", mois="2026-09")
verifier("clé fausse -> 401", r.status_code == 401, r.status_code)
r, c, _ = appel(None, entetes={"Authorization": "Basic " + CLE_FREQ}, mois="2026-09")
verifier("autre schéma que Bearer -> 401", r.status_code == 401, r.status_code)
r, c, _ = appel(CLE_FREQ[:-1], mois="2026-09")
verifier("clé tronquée -> 401", r.status_code == 401, r.status_code)
_env(CLE_FIN, CLE_FIN)
for _k in (CLE_FIN, CLE_FREQ, "n-importe-quoi"):
    _reinit()
    r, c, _ = appel(_k, mois="2026-09")
    verifier("deux clés IDENTIQUES -> 503 configuration_invalide (avec %s)" % _k[:8],
             r.status_code == 503 and c.get("error") == "configuration_invalide" and "revenus" not in c, (r.status_code, c))
_reinit()
_env(CLE_FREQ, None)
r, c, _ = appel(CLE_FIN, mois="2026-09")
verifier("clé finances alors que seule la fréquentation est posée -> 401", r.status_code == 401, r.status_code)
_env()

# ═══ 2. portée fréquentation ═══
_reinit()
r, c, base = appel(CLE_FREQ, mois="2026-09")
verifier("clé fréquentation -> 200 JSON", r.status_code == 200 and r.media_type == "application/json", r.status_code)
verifier("schema = stats-association/1", c.get("schema") == "stats-association/1", c.get("schema"))
verifier("portée = frequentation, périmètre = ensemble", c["portee"] == "frequentation" and c["perimetre"] == "ensemble")
verifier("revenus refusés : {disponible:false, raison:portee_finances_requise}",
         c["revenus"] == {"disponible": False, "raison": "portee_finances_requise"}, c["revenus"])
_txt = json.dumps(c, ensure_ascii=False)
verifier("aucun montant en portée fréquentation (ni ca_prouve, ni CHF, ni panier)",
         "ca_prouve" not in _txt and "panier" not in _txt and "CHF" not in _txt and "montant" not in _txt)
verifier("blocs fréquentation / essais / abonnements / évolution disponibles",
         all(c[b]["disponible"] is True for b in ("frequentation", "essais", "abonnements", "evolution")))
verifier("genere_le : ISO avec le décalage de Zurich (+02:00 le 15/10)", c["genere_le"] == "2026-10-15T14:00:00+02:00", c["genere_le"])
verifier("période : mois de septembre, clos, granularité semaine par défaut",
         c["periode"]["debut"] == "2026-09-01" and c["periode"]["fin_exclue"] == "2026-10-01"
         and c["periode"]["granularite"] == "semaine" and c["periode"]["en_cours"] is False and c["periode"]["libelle"] == "Septembre 2026",
         c["periode"])
verifier("aucune écriture en base", not base.ecritures, base.ecritures)
verifier("lectures = les 7 du moteur + 1 clôture, rien d'autre",
         sorted(set(base.lectures)) == sorted({"reservations", "courses", "subscriptions", "discount_codes", "offers",
                                                "memberships", "payment_transactions", "analytics_monthly_reports"}), base.lectures)
verifier("anonymat : verifier_anonymat ne trouve rien", verifier_anonymat(c) == [])
verifier("aucun e-mail, code AFR-, identifiant Stripe dans la réponse",
         "@" not in _txt and "AFR-" not in _txt and "cs_test" not in _txt and "mail.invalid" not in _txt)

# ═══ 3. mêmes chiffres que l'écran coach ═══
K = cockpit(periode="mois", mois="2026-09", vue="association")
fq, es, ab = c["frequentation"], c["essais"], c["abonnements"]
verifier("réservations = écran coach", fq["reservations"] == K["participants"]["reservations_cours"] == 8, (fq["reservations"], K["participants"]))
verifier("séances = écran coach", fq["seances"] == K["cours"]["seances"], (fq["seances"], K["cours"]["seances"]))
verifier("participants uniques / nouveaux / récurrents = écran coach",
         (fq["participants_uniques"], fq["nouveaux"], fq["recurrents"]) ==
         (K["participants"]["uniques"], K["participants"]["nouveaux"], K["participants"]["recurrents"]))
verifier("présence = écran coach", fq["presence"]["confirmee"] == K["presence"]["confirmee"]
         and fq["presence"]["couverture_pct"] == K["presence"]["couverture_pct"])
verifier("essais accordés / réservés = écran coach",
         es["accordes"] == K["essais_funnel"]["accordes"] and es["reserves"] == K["essais_funnel"]["reserves"], (es, K["essais_funnel"]["accordes"]))
verifier("abonnements actifs = écran coach", ab["actifs"] == K["abonnements"]["actifs"]["total"], (ab["actifs"], K["abonnements"]["actifs"]))
verifier("pulse vendus = écran coach", ab["pulse_vendus"] == K["abonnements"]["pulse_x10"]["vendus"])

# ═══ 4. par séance : réservations ET places ═══
ps = {(x["date"], x["cours"]): x for x in fq["par_seance"]}
verifier("par séance : somme des réservations = total", sum(x["reservations"] for x in fq["par_seance"]) == fq["reservations"])
verifier("par séance : somme des places = total des places", sum(x["places"] for x in fq["par_seance"]) == fq["places"])
_mer = ps.get(("2026-09-09", "Silent")) or {}
verifier("mercredi 9/09 Silent : 4 réservations, 5 places (une réservation à 2)",
         _mer.get("reservations") == 4 and _mer.get("places") == 5 and _mer.get("heure") == "18:30" and _mer.get("jour") == "mercredi", _mer)
_m16 = ps.get(("2026-09-16", "Silent")) or {}
verifier("16/09 : 2 réservations, 4 places (une réservation à 3)", _m16.get("reservations") == 2 and _m16.get("places") == 4, _m16)
verifier("places ≠ réservations au total (11 places pour 8 réservations)", fq["places"] == 11 and fq["reservations"] == 8, (fq["places"], fq["reservations"]))
verifier("par séance : UNIQUEMENT date, heure, jour, libellé et nombres (ni lieu, ni occurrence, ni texte libre)",
         all(set(x) == {"date", "heure", "jour", "cours", "reservations", "places", "presences_confirmees"}
             for x in fq["par_seance"]), [sorted(x) for x in fq["par_seance"]][:1])
pts = c["evolution"]["points"]
verifier("évolution hebdomadaire : clés = lundis", pts and all(datetime.strptime(p["periode"], "%Y-%m-%d").weekday() == 0 for p in pts), pts)
verifier("évolution : somme des réservations = total du mois", sum(p["reservations"] for p in pts) == fq["reservations"])

# ═══ 4b. libellé de séance : seulement le catalogue PUBLIC des cours ═══
jeu = F.jeu_de_base()
jeu["courses"][0]["locationName"] = "Chez Jean Martin, Rue du Lac 12, 1200 Genève"
for x in jeu["reservations"]:
    if x["courseId"] == "c-mer":
        x["courseName"] = "Cours privé de Marie Dupont"       # texte libre de la réservation
jeu["courses"][1]["archived"] = True                           # Sunday n'est plus au catalogue public
jeu["reservations"].append(resa_libre := dict(F.resa("r-hors", "kim@mail.invalid", "2026-09-20T10:00:00",
                                                       "2026-09-18T08:00:00+00:00", "c-inconnu", "Coaching de Paul Durand")))
_reinit()
r, cc, _ = appel(CLE_FREQ, jeu=jeu, mois="2026-09")
_t = json.dumps(cc, ensure_ascii=False)
_lib = {(x["date"], x["cours"]) for x in cc["frequentation"]["par_seance"]}
verifier("libellé = nom du CATALOGUE (Silent), jamais le texte de la réservation (Marie Dupont)",
         ("2026-09-09", "Silent") in _lib and "Marie Dupont" not in _t, _lib)
verifier("le lieu n'est jamais servi (ni adresse ni nom dans le lieu)", "Jean Martin" not in _t and "Rue du Lac" not in _t and "lieu" not in json.dumps(cc["frequentation"]["par_seance"]))
verifier("cours archivé (hors catalogue public) -> « Séance »", ("2026-09-13", "Séance") in _lib and "Sunday" not in json.dumps(cc["frequentation"]["par_seance"]), _lib)
verifier("cours inconnu du catalogue, nommé seulement sur la réservation -> « Séance »",
         ("2026-09-20", "Séance") in _lib and "Paul Durand" not in _t, _lib)
_b = F.Base(F.jeu_de_base())
_reinit()
r, cc, _ = appel(CLE_FREQ, base=_b, mois="2026-09")
verifier("le catalogue est lu avec le filtre public (archived != True)",
         any(n == "courses" for n in _b.lectures) and cc["frequentation"]["par_seance"][0]["cours"] in ("Silent", "Sunday"))

# ═══ 5. portée finances : les revenus de l'écran coach ═══
_reinit()
r, c2, _ = appel(CLE_FIN, mois="2026-09")
rv = c2["revenus"]
verifier("clé finances -> portée finances, revenus disponibles", c2["portee"] == "finances" and rv["disponible"] is True, rv)
verifier("CA prouvé = écran coach (295 CHF)", rv["ca_prouve"] == K["association"]["finances"]["ca_prouve"] == 295.0,
         (rv.get("ca_prouve"), K["association"]["finances"]["ca_prouve"]))
verifier("en attente hors CA = écran coach", rv["hors_ca"]["pending_nombre"] == K["association"]["finances"]["hors_ca"]["pending_nombre"] == 1)
verifier("fréquentation identique quelle que soit la portée", c2["frequentation"] == c["frequentation"])
verifier("anonymat en portée finances", verifier_anonymat(c2) == [] and "cs_test" not in json.dumps(c2))

# ═══ 6. paramètres ═══
for p, nom in ((dict(mois="2026-09", annee="2026"), "mois ET annee"), (dict(mois="2026-13"), "mois 13"),
               (dict(mois="26-09"), "mois mal formé"), (dict(annee="20x6"), "année mal formée"),
               (dict(mois="2026-09", granularite="heure"), "granularité inconnue"),
               (dict(mois="٢٠٢٦-٠٩"), "mois en chiffres arabes-indiens"), (dict(annee="٢٠٢٦"), "année en chiffres arabes-indiens"),
               (dict(mois="２０２６-０９"), "chiffres pleine largeur"), (dict(mois="2026-09\n"), "saut de ligne final"),
               (dict(annee="2026\n"), "année + saut de ligne"), (dict(mois="2026-00"), "mois 00"), (dict(annee="1999"), "année hors bornes"),
               (dict(mois="2026-09'; --"), "injection"), (dict(mois="2026-09", granularite="ＪＯＵＲ"), "granularité non ASCII")):
    _reinit()
    r, cc, _ = appel(CLE_FREQ, **p)
    verifier("400 JSON — %s" % nom, r.status_code == 400 and cc.get("error") == "parametres", (r.status_code, cc))
_reinit()
r, cc, _ = appel(CLE_FREQ)
verifier("sans paramètre : le mois courant (octobre), signalé « en cours »",
         cc["periode"]["debut"] == "2026-10-01" and cc["periode"]["en_cours"] is True
         and S.AVERT_EN_COURS in cc["qualite"]["avertissements"], cc["periode"])
_reinit()
r, cc, _ = appel(CLE_FREQ, annee="2026")
verifier("annee=2026 : année entière, granularité mois", cc["periode"]["type"] == "annee"
         and cc["periode"]["fin_exclue"] == "2027-01-01" and cc["evolution"]["granularite"] == "mois", cc["periode"])
verifier("annee=2026 : réservations = écran coach (année)",
         cc["frequentation"]["reservations"] == cockpit(periode="annee", mois="2026-01")["participants"]["reservations_cours"])

# ═══ 7. jamais 0 pour une donnée inconnue ═══
_reinit()
r, cc, _ = appel(CLE_FREQ, mois="2026-03")
verifier("mois sans séance : moyenne = None (pas 0)", cc["frequentation"]["moyenne_par_seance"] is None
         and cc["frequentation"]["moyenne_places_par_seance"] is None, cc["frequentation"])
verifier("mois sans séance : couverture de présence = None", cc["frequentation"]["presence"]["couverture_pct"] is None)
_reinit()
b = F.Base(F.jeu_de_base()); b.panne = True
r, cc, _ = appel(CLE_FIN, base=b, mois="2026-09")
verifier("base muette : 200 JSON, schéma tenu", r.status_code == 200 and cc["schema"] == "stats-association/1")
verifier("base muette : TOUS les blocs indisponibles (base_indisponible), aucun chiffre",
         all(cc[k] == {"disponible": False, "raison": "base_indisponible"} for k in ("frequentation", "essais", "abonnements", "evolution", "revenus")), cc)
_reinit()
r, cc2, _ = appel(CLE_FIN, mois="2026-09")
verifier("base muette : rien n'a été mis en cache (l'appel suivant recalcule)", cc2["frequentation"]["disponible"] is True)

# ═══ 8. un bloc en panne n'emporte pas les autres ═══
_vrai = S.par_seance
S.par_seance = lambda *a, **k: (_ for _ in ()).throw(ValueError("panne simulée"))
_reinit()
r, cc, _ = appel(CLE_FREQ, mois="2026-09")
S.par_seance = _vrai
verifier("fréquentation en panne -> {disponible:false, raison:erreur_de_calcul}",
         cc["frequentation"] == {"disponible": False, "raison": "erreur_de_calcul"}, cc["frequentation"])
verifier("… essais, abonnements, évolution restent servis", all(cc[k]["disponible"] for k in ("essais", "abonnements", "evolution")))
verifier("… et la panne est avouée dans les avertissements", any("fréquentation" in a for a in cc["qualite"]["avertissements"]))

# ═══ 9. anonymat : une fuite bloque TOUTE la réponse ═══
jeu = F.jeu_de_base()
jeu["courses"] = [dict(x) for x in jeu["courses"]]
jeu["courses"][0]["name"] = "Silent avec anna@mail.invalid"      # e-mail dans le CATALOGUE public lui-même
_reinit()
r, cc, _ = appel(CLE_FREQ, jeu=jeu, mois="2026-09")
verifier("un e-mail glissé dans un nom de cours du catalogue -> 500 JSON, rien servi, rien en cache",
         r.status_code == 500 and not R._STATS_CACHE and cc.get("error") == "donnee_personnelle_detectee", (r.status_code, cc.get("error")))
verifier("un e-mail glissé dans un nom de cours -> 500 JSON, rien servi",
         r.status_code == 500 and cc.get("error") == "donnee_personnelle_detectee" and "anna" not in json.dumps(cc), (r.status_code, cc))

# ═══ 10. débit : par adresse (complément) et verrou GLOBAL des échecs ═══
_reinit()
codes = [appel(CLE_FREQ, ip="198.51.100.9", mois="2026-09")[0].status_code for _ in range(R.STATS_DEBIT_MAX)]
r, cc, _ = appel(CLE_FREQ, ip="198.51.100.9", mois="2026-09")
verifier("débit par adresse : au-delà de %d appels/min -> 429 JSON, Retry-After 60" % R.STATS_DEBIT_MAX,
         set(codes) == {200} and r.status_code == 429 and cc["error"] == "debit_depasse" and r.headers.get("retry-after") == "60", (codes[-1], r.status_code))
r, cc, _ = appel(CLE_FREQ, ip="198.51.100.10", mois="2026-09")
verifier("débit par adresse : une autre adresse n'est pas pénalisée", r.status_code == 200)
r, cc, _ = appel(CLE_FREQ, ip="10.0.0.1", entetes={"CF-Connecting-IP": "198.51.100.9"}, mois="2026-09")
verifier("débit par adresse : l'adresse vient de CF-Connecting-IP", r.status_code == 429, r.status_code)
_reinit()
verifier("IP : sans CF, le DERNIER saut de X-Forwarded-For (comme _live_guest_ip)",
         R._stats_ip(F.Req({"x-forwarded-for": "1.2.3.4, 203.0.113.50"}, "10.0.0.1")) == "203.0.113.50")
verifier("IP : ni CF ni XFF -> la socket", R._stats_ip(F.Req({}, "10.0.0.9")) == "10.0.0.9")

# FALSIFICATION D'IP : le débit par adresse n'est qu'un FREIN — et il n'y a
# PAS de verrou global (il permettait à n'importe qui de couper la route).
_reinit()
codes = [appel("devinette-%03d" % i, ip="10.0.0.1", entetes={"CF-Connecting-IP": "198.51.100.%d" % i}, mois="2026-09")[0].status_code
         for i in range(40)]
verifier("falsification : 40 clés fausses depuis 40 « adresses » -> 401 chacune (le frein par adresse est contourné, c'est assumé)",
         set(codes) == {401}, set(codes))
r, cc, _ = appel(CLE_FREQ, ip="192.0.2.77", mois="2026-09")
verifier("PAS de déni de service : après 40 clés fausses, la BONNE clé est toujours servie (aucun verrou global)",
         r.status_code == 200, r.status_code)
verifier("aucun compteur global d'échecs dans le module", not hasattr(R, "_STATS_ECHECS") and not hasattr(R, "STATS_ECHECS_MAX"))
_dc = open(os.path.join(F.RACINE, "docker-compose.yml"), encoding="utf-8").read()
verifier("docker-compose recommande 64 caractères hexadécimaux", "64 caractères hexadécimaux" in _dc)

# CLÉ TROP COURTE = ABSENTE
_reinit(); _env("courte-0123456789", None)
r, cc, _ = appel("courte-0123456789", mois="2026-09")
verifier("clé configurée < 32 caractères -> traitée comme absente : 503", r.status_code == 503 and cc["error"] == "stats_non_configurees", (r.status_code, cc))
_reinit(); _env("courte-0123456789", CLE_FIN)
r, cc, _ = appel("courte-0123456789", mois="2026-09")
verifier("clé courte à côté d'une clé valide : la courte est refusée (401), jamais acceptée", r.status_code == 401, r.status_code)
r, cc, _ = appel(CLE_FIN, mois="2026-09")
verifier("… la clé valide (≥ 32) fonctionne", r.status_code == 200 and cc["portee"] == "finances")
verifier("clés de ce banc ≥ 32 caractères", len(CLE_FREQ) >= 32 and len(CLE_FIN) >= 32)
_env()

# ═══ 11. cache ~10 min ═══
_reinit()
b = F.Base(F.jeu_de_base())
r1, c_a, _ = appel(CLE_FREQ, base=b, mois="2026-09")
n = len(b.lectures)
r2, c_b, _ = appel(CLE_FREQ, base=b, mois="2026-09")
verifier("cache : le 2e appel ne relit pas la base et rend la même réponse",
         len(b.lectures) == n and c_a == c_b and r2.headers.get("x-stats-cache") == "hit" and r1.headers.get("x-stats-cache") == "miss")
r3, c_c, _ = appel(CLE_FIN, base=b, mois="2026-09")
verifier("cache : séparé par portée (la portée fréquentation ne sert jamais un cache finances)",
         c_c["portee"] == "finances" and c_a["portee"] == "frequentation" and len(b.lectures) > n)
verifier("cache : TTL ≈ 10 min", R.STATS_CACHE_TTL == 600.0)

# ═══ 12. mois clos : servi depuis la clôture figée ═══
K9 = cockpit(periode="mois", mois="2026-09", vue="association")["association"]
bilan = json.loads(json.dumps(K9))
bilan["activite"]["reservations"] = 99          # le bilan figé dit autre chose que le dynamique
snap = construire_snapshot(bilan, datetime(2026, 9, 1), datetime(2026, 10, 1), "", F.ADMIN, datetime(2026, 10, 2, 9, 0))
jeu = F.jeu_de_base(); jeu["analytics_monthly_reports"] = [snap]
_reinit()
r, cc, _ = appel(CLE_FREQ, jeu=jeu, mois="2026-09")
verifier("mois clos AVEC clôture : réservations du bilan officiel (99), source = cloture",
         cc["frequentation"]["reservations"] == 99 and cc["periode"]["source"] == "cloture"
         and cc["frequentation"]["source"] == "cloture", (cc["frequentation"].get("reservations"), cc["periode"]))
verifier("… la clôture est référencée (empreinte 12 car., version), sans son auteur",
         (cc["periode"]["cloture"] or {}).get("empreinte") == snap["hash"][:12] and (cc["periode"]["cloture"] or {}).get("version") == 1
         and F.ADMIN not in json.dumps(cc), cc["periode"]["cloture"])
verifier("… et l'avertissement dit que places/par séance sont recalculés", S.AVERT_CLOTURE in cc["qualite"]["avertissements"])
snap2 = dict(snap); snap2["bilan"] = json.loads(json.dumps(snap["bilan"])); snap2["bilan"]["activite"]["reservations"] = 500
jeu = F.jeu_de_base(); jeu["analytics_monthly_reports"] = [snap2]
_reinit()
r, cc, _ = appel(CLE_FREQ, jeu=jeu, mois="2026-09")
verifier("clôture ALTÉRÉE (empreinte fausse) : ignorée, chiffres dynamiques (8) et aveu",
         cc["frequentation"]["reservations"] == 8 and cc["periode"]["source"] == "dynamique"
         and S.AVERT_CLOTURE_ALTEREE in cc["qualite"]["avertissements"], cc["frequentation"].get("reservations"))
jeu = F.jeu_de_base(); jeu["analytics_monthly_reports"] = [snap]
_reinit()
r, cc, _ = appel(CLE_FREQ, jeu=jeu, annee="2026")
p9 = [p for p in cc["evolution"]["points"] if p["periode"] == "2026-09"]
verifier("année : le point de septembre vient de sa clôture (99, source cloture)",
         p9 and p9[0]["reservations"] == 99 and p9[0]["source"] == "cloture", p9)
r, cc, b = appel(CLE_FREQ, jeu=jeu, mois="2026-10")
verifier("mois EN COURS : jamais lu depuis une clôture", cc["periode"]["source"] == "dynamique")

# ═══ 13. fuseau Europe/Zurich ═══
verifier("tzdata/zoneinfo disponible ici", A.fuseau_zurich_disponible())
verifier("été : 16:30 UTC -> 18:30 à Zurich", A.vers_local(datetime(2026, 7, 1, 16, 30, tzinfo=timezone.utc)) == datetime(2026, 7, 1, 18, 30))
verifier("hiver : 17:30 UTC -> 18:30 à Zurich", A.vers_local(datetime(2026, 1, 14, 17, 30, tzinfo=timezone.utc)) == datetime(2026, 1, 14, 18, 30))
verifier("bascule d'octobre : 25/10 00:30 UTC -> 02:30 (été), 01:30 UTC -> 02:30 (hiver)",
         A.vers_local(datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 25, 2, 30)
         and A.vers_local(datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 25, 2, 30))
_z = A._ZURICH
A._ZURICH = None
_reinit()
r, cc, _ = appel(CLE_FREQ, mois="2026-09")
A._ZURICH = _z
verifier("sans base de fuseaux : la réponse l'AVOUE (avertissement + qualite.fuseau UTC)",
         S.AVERT_FUSEAU in cc["qualite"]["avertissements"] and cc["qualite"]["fuseau"].startswith("UTC")
         and cc["genere_le"].endswith("+00:00"), (cc["qualite"]["fuseau"], cc["genere_le"]))
_req = open(os.path.join(F.RACINE, "api", "requirements.txt"), encoding="utf-8").read()
verifier("tzdata figure dans api/requirements.txt", any(l.strip().startswith("tzdata==") for l in _req.splitlines()))

# ═══ 14. câblage ═══
_srv = open(os.path.join(F.RACINE, "api", "server.py"), encoding="utf-8").read()
_i_stats = _srv.find("include_router(stats_router")
verifier("server.py inclut stats_router sous /api, AVANT le catch-all SPA",
         _i_stats > 0 and _i_stats < _srv.find('@fastapi_app.get("/{full_path:path}")'))
verifier("route déclarée : GET /stats/association", any(getattr(rt, "path", "") == "/stats/association" and "GET" in rt.methods
                                                         for rt in R.stats_router.routes))
_dc = open(os.path.join(F.RACINE, "docker-compose.yml"), encoding="utf-8").read()
verifier("docker-compose : les deux clés dans la liste environment",
         "- AFROBOOST_STATS_KEY_FREQUENTATION=${AFROBOOST_STATS_KEY_FREQUENTATION:-}" in _dc
         and "- AFROBOOST_STATS_KEY_FINANCES=${AFROBOOST_STATS_KEY_FINANCES:-}" in _dc)

ok = sum(1 for _, c_, _ in RESULTATS if c_)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)[:400]) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

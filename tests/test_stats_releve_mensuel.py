# -*- coding: utf-8 -*-
"""STATS-3 — le bloc ADDITIF `releve_mensuel` de `GET /api/stats/association`.

Ce que ces bancs tiennent, sur des données SYNTHÉTIQUES et une fausse base :
  * présences vs réservations (nature), annulation exclue (document supprimé
    OU marqué `cancelled`), doublon même personne / même séance compté une fois ;
  * essai gratuit et place par code (V628) en gratuites, tarif figé > 0 en payantes ;
  * frontière de mois ET de jour en Europe/Zurich, mercredi / dimanche ;
  * date annulée d'un cours (V610) et séances futures exclues ;
  * capacité : seulement la capacité RÉELLE (V618M) ; `max_participants` -> null ;
  * aucune écriture, aucune donnée personnelle, clé fréquentation suffisante,
    401 / 503 inchangés ; les blocs existants IDENTIQUES à la version d'avant.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_stats_releve_mensuel.py
"""
import copy
import json
import os
import subprocess
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stats_fixtures as F  # noqa: E402

import logging; logging.disable(logging.CRITICAL)  # noqa: E702
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


F.installer_serveur(F.Base(F.jeu_de_base()), F.ADMIN)
import api.routes.analytics_routes as R  # noqa: E402
import api.routes.analytics_stats as S  # noqa: E402
import api.routes.analytics_shared as A  # noqa: E402
import api.routes.analytics_releve as RL  # noqa: E402
from api.routes.analytics_association import verifier_anonymat  # noqa: E402
F.horloge_figee(R)

CF = "cle-frequentation-releve-0123456789abcdef"
CK = "cle-finances-releve-9876543210-fedcba-xyz"


def _env(freq=CF, fin=CK):
    for k, v in ((R.STATS_ENV_FREQUENTATION, freq), (R.STATS_ENV_FINANCES, fin)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _reinit():
    R._STATS_CACHE.clear()
    R._STATS_DEBIT.clear()


def jeu_releve():
    """Septembre : 5 participations après dédoublonnage, présence CONNUE pour toutes."""
    j = F.jeu_de_base()
    rs = F.resa
    j["reservations"] = [
        # anna, mercredi 02/09, réservée DEUX fois (2 documents) -> une participation, présente, payante
        rs("a1", "anna@mail.invalid", "2026-09-02T18:30:00", "2026-09-01T08:00:00+00:00", validated=True, tarif_applique=30),
        rs("a2", "Anna@Mail.invalid ", "2026-09-02T18:30:00", "2026-09-01T09:00:00+00:00", tarif_applique=30),
        # bob, même séance, absence déclarée -> connue, non comptée en présence
        rs("b1", "bob@mail.invalid", "2026-09-02T18:30:00", "2026-09-01T08:00:00+00:00", absence_marked_at="x", tarif_applique=30),
        # eve, dimanche 06/09, ESSAI gratuit (fiche free) -> gratuite, présente
        rs("e1", "eve@mail.invalid", "2026-09-06T10:00:00", "2026-09-05T08:00:00+00:00", "c-dim", "Sunday",
           discountCode="AFR-ESS001", validated=True),
        # kim, même dimanche, PLACE PAR CODE V628 -> gratuite, présente
        rs("k1", "kim@mail.invalid", "2026-09-06T10:00:00", "2026-09-05T08:00:00+00:00", "c-dim", "Sunday",
           source="promo_code_event", price=0.0, discountCode="AFR-EVT001", validated=True),
        # zoe : 22:30 UTC le MARDI 08/09 = 00:30 le MERCREDI 09/09 à Zurich -> séance du mercredi
        rs("z1", "zoe@mail.invalid", "2026-09-08T22:30:00Z", "2026-09-01T08:00:00+00:00", validated=True, tarif_applique=20),
        # carl : le 23/09 est une DATE ANNULÉE du cours -> exclu (sinon la présence deviendrait partielle)
        rs("c1", "carl@mail.invalid", "2026-09-23T18:30:00", "2026-09-20T08:00:00+00:00"),
        # xav : réservation marquée ANNULÉE -> exclue
        rs("x1", "xav@mail.invalid", "2026-09-16T18:30:00", "2026-09-10T08:00:00+00:00", status="cancelled"),
        # fay : 22:30 UTC le 30/09 = 00:30 le JEUDI 01/10 à Zurich -> octobre, pas septembre
        rs("f1", "fay@mail.invalid", "2026-09-30T22:30:00Z", "2026-09-25T08:00:00+00:00"),
        # gus : séance FUTURE d'octobre (le 21, après « maintenant » = 15/10) -> pas encore une participation
        rs("g1", "gus@mail.invalid", "2026-10-21T18:30:00", "2026-10-10T08:00:00+00:00"),
        # boutique : jamais une séance
        rs("p1", "shop@mail.invalid", "2026-09-10T00:00:00", "2026-09-10T08:00:00+00:00", "", "", isProduct=True),
    ]
    j["courses"] = [{"id": "c-mer", "name": "Silent", "weekday": 3, "locationName": "Lac", "dates_annulees": ["2026-09-23"]},
                    {"id": "c-dim", "name": "Sunday", "weekday": 0, "locationName": "Lac"}]
    j["discount_codes"].append({"code": "AFR-EVT001", "coach_id": F.COACH, "active": True})
    return j


def appel(cle=CF, jeu=None, base=None, entetes=None, **params):
    base = base or F.Base(jeu or jeu_releve())
    F.installer_serveur(base, "")
    h = dict(entetes or {})
    if cle is not None:
        h["Authorization"] = "Bearer " + cle
    r = F.run(R.stats_association(F.Req(h), **params))
    return r, json.loads(r.body.decode("utf-8")), base


_env()

# ═══ 1. septembre : présences, doublon, annulations, gratuites ═══
_reinit()
r, c, base = appel(mois="2026-09")
rm = c.get("releve_mensuel") or {}
ch = rm.get("champs") or {}
p = ch.get("participations") or {}
verifier("200 + bloc releve_mensuel disponible pour septembre", r.status_code == 200 and rm.get("disponible") is True
         and rm.get("mois") == "2026-09", (r.status_code, rm))
verifier("présence connue pour toutes -> nature = presences", p.get("nature") == "presences", p)
verifier("participations = 4 présences (doublon d'anna une fois, bob absent, annulée / date annulée / octobre exclues)",
         p.get("valeur") == 4, p)
verifier("payantes = 2 (tarif figé > 0), gratuites = 2 (essai + place par code)",
         p.get("payantes") == 2 and p.get("gratuites") == 2 and "raison_repartition" not in p, p)
verifier("séances = 3 (mer. 02/09, dim. 06/09, mer. 09/09 00:30 Zurich ; pas le 16/09 annulé ni le 23/09)",
         rm.get("seances") == 3, rm.get("seances"))
mer, dim = ch.get("moyenneMercredi") or {}, ch.get("moyenneDimanche") or {}
verifier("moyenne du mercredi = 2 présences / 2 séances = 1.0 (frontière de jour en Zurich)",
         mer.get("valeur") == 1.0 and mer.get("seances") == 2 and mer.get("nature") == "presences", mer)
verifier("moyenne du dimanche = 2 / 1 = 2.0", dim.get("valeur") == 2.0 and dim.get("seances") == 1, dim)
verifier("capacité absente -> tauxRemplissage null + capacite_inconnue",
         ch.get("tauxRemplissage") == {"valeur": None, "raison": "capacite_inconnue"}, ch.get("tauxRemplissage"))
verifier("aucune écriture en base (méthodes d'écriture espionnées)", not base.ecritures, base.ecritures)
_txt = json.dumps(rm, ensure_ascii=False)
verifier("anonymat du bloc : aucun e-mail, code, nom", verifier_anonymat(rm) == [] and "@" not in _txt
         and "AFR-" not in _txt and "anna" not in _txt.lower() and "Silent" not in _txt, _txt[:200])
verifier("anonymat de la réponse entière", verifier_anonymat(c) == [])
verifier("aucun montant dans le bloc (ni CHF, ni prix, ni tarif)",
         all(m not in _txt.lower() for m in ("chf", "prix", "price", "tarif", "montant", "ca_")), _txt[:200])

# ═══ 2. octobre (en cours) : frontière de mois, futur exclu, réservations faute de présence ═══
_reinit()
r, c, _ = appel(mois="2026-10")
rm = c["releve_mensuel"]
p = rm["champs"]["participations"]
verifier("octobre : le 30/09 22:30 UTC compte en octobre (01/10 00:30 Zurich)", p.get("valeur") == 1 and rm["seances"] == 1, rm)
verifier("octobre : séance future (21/10) exclue, mois marqué en_cours", rm.get("en_cours") is True, rm)
verifier("présence inconnue -> nature = reservations (dit, jamais présenté comme présence)",
         p.get("nature") == "reservations" and rm["champs"]["moyenneMercredi"]["nature"] == "reservations", p)
verifier("aucune séance un mercredi -> moyenne null + raison, seances = 0 (jamais 0 en moyenne)",
         rm["champs"]["moyenneMercredi"] == {"valeur": None, "nature": "reservations", "seances": 0,
                                              "raison": "aucune_seance_ce_jour"}, rm["champs"]["moyenneMercredi"])
verifier("fay sans moyen de paiement prouvé -> payantes / gratuites null + raison",
         p.get("payantes") is None and p.get("gratuites") is None and p.get("raison_repartition") == "paiement_indetermine", p)

# ═══ 3. capacité réelle vs texte affiché ═══
j = jeu_releve()
j["offers"].append({"id": "o-cap", "name": "Cours", "price": 30, "max_participants": 12, "linked_course_ids": ["c-mer", "c-dim"]})
_reinit()
_, c, _ = appel(jeu=j, mois="2026-09")
verifier("max_participants seul (jamais appliqué) -> taux null, capacite_inconnue",
         c["releve_mensuel"]["champs"]["tauxRemplissage"] == {"valeur": None, "raison": "capacite_inconnue"},
         c["releve_mensuel"]["champs"]["tauxRemplissage"])
j["offers"].append({"id": "o-cap2", "name": "Cours limité", "price": 30, "capacite_limitee": True, "capacite_max": 10,
                    "linked_course_ids": ["c-mer", "c-dim"]})
_reinit()
_, c, _ = appel(jeu=j, mois="2026-09")
verifier("capacité réelle (V618M) sur toutes les séances -> taux = 4 / 30 = 13.3 %",
         c["releve_mensuel"]["champs"]["tauxRemplissage"] == {"valeur": 13.3}, c["releve_mensuel"]["champs"]["tauxRemplissage"])
j2 = copy.deepcopy(j)
j2["offers"][-1]["linked_course_ids"] = ["c-mer"]
_reinit()
_, c, _ = appel(jeu=j2, mois="2026-09")
verifier("une séance sans capacité réelle -> taux null (pas de taux partiel)",
         c["releve_mensuel"]["champs"]["tauxRemplissage"].get("valeur") is None, c["releve_mensuel"]["champs"]["tauxRemplissage"])

# ═══ 4. clés, portées, refus inchangés ═══
_reinit()
_, cf, _ = appel(CF, mois="2026-09")
_reinit()
_, ck, _ = appel(CK, mois="2026-09")
verifier("clé FRÉQUENTATION suffit ; même bloc avec la clé finances", cf["releve_mensuel"]["disponible"] is True
         and cf["releve_mensuel"] == ck["releve_mensuel"] and cf["portee"] == "frequentation")
_reinit()
r, c, _ = appel(None, mois="2026-09")
verifier("sans clé -> 401 cle_invalide, aucun bloc", r.status_code == 401 and c.get("error") == "cle_invalide"
         and "releve_mensuel" not in c, (r.status_code, c))
_env(None, None)
_reinit()
r, c, _ = appel(CF, mois="2026-09")
verifier("aucune clé posée -> 503 stats_non_configurees, aucun bloc", r.status_code == 503
         and c.get("error") == "stats_non_configurees" and "releve_mensuel" not in c, (r.status_code, c))
_env()

# ═══ 5. cas où l'on ne sait pas : jamais un chiffre ═══
_reinit()
_, c, _ = appel(annee="2026")
verifier("période annuelle -> bloc indisponible (periode_non_mensuelle)",
         c["releve_mensuel"] == {"disponible": False, "raison": "periode_non_mensuelle", "mois": None}, c["releve_mensuel"])
_reinit()
_, c, _ = appel(mois="2026-12")
verifier("mois futur -> indisponible (mois_futur)", c["releve_mensuel"].get("raison") == "mois_futur", c["releve_mensuel"])
jv = jeu_releve(); jv["reservations"] = []
_reinit()
_, c, _ = appel(jeu=jv, mois="2026-09")
verifier("base sans aucune réservation -> indisponible, jamais 0",
         c["releve_mensuel"].get("disponible") is False and c["releve_mensuel"].get("raison") == "aucune_reservation_en_base"
         and "champs" not in c["releve_mensuel"], c["releve_mensuel"])
b = F.Base(jeu_releve()); b.panne = True
_reinit()
_, c, _ = appel(base=b, mois="2026-09")
verifier("base injoignable -> base_indisponible, aucun chiffre",
         c["releve_mensuel"] == {"disponible": False, "raison": "base_indisponible", "mois": "2026-09"}, c["releve_mensuel"])
_z = A._ZURICH
A._ZURICH = None
_reinit()
_, c, _ = appel(mois="2026-09")
A._ZURICH = _z
verifier("sans base de fuseaux -> indisponible (fuseau_indisponible), jamais une heure UTC",
         c["releve_mensuel"].get("raison") == "fuseau_indisponible", c["releve_mensuel"])

# ═══ 6. le pur : doublon de DOCUMENT sans e-mail, présence partielle ═══
from datetime import datetime  # noqa: E402
_tab = A.construire_faits([F.resa("n1", "", "2026-09-02T18:30:00", "2026-09-01T08:00:00+00:00"),
                           F.resa("n1", "", "2026-09-02T18:30:00", "2026-09-01T08:00:00+00:00"),
                           F.resa("n2", "", "2026-09-02T18:30:00", "2026-09-01T08:00:00+00:00", quantity=2)],
                          normaliser_occurrence=F.occurrence_iso)
_r = RL.releve_mensuel(_tab["faits"], datetime(2026, 9, 1), datetime(2026, 10, 1), "mois", datetime(2026, 10, 15, 14))
verifier("même document en double (sans e-mail) compté une fois ; quantity=2 -> 2 places : total 3",
         _r["champs"]["participations"]["valeur"] == 3 and _r["seances"] == 1, _r["champs"]["participations"])
_offres = [{"id": "o1", "max_participants": 12, "linked_course_ids": ["c-mer"]},
           {"id": "o2", "capacite_limitee": False, "capacite_max": 8, "linked_course_ids": ["c-mer"]}]
_r = RL.releve_mensuel(_tab["faits"], datetime(2026, 9, 1), datetime(2026, 10, 1), "mois", datetime(2026, 10, 15, 14),
                       offres=_offres)
verifier("pur : max_participants ou capacité non activée ne sont JAMAIS une capacité",
         _r["champs"]["tauxRemplissage"] == {"valeur": None, "raison": "capacite_inconnue"}, _r["champs"]["tauxRemplissage"])
_offres.append({"id": "o3", "capacite_limitee": True, "capacite_max": 6, "linked_course_ids": ["c-mer"]})
_offres.append({"id": "o4", "capacite_limitee": True, "capacite_max": 9, "linked_course_ids": ["c-mer"]})
_r = RL.releve_mensuel(_tab["faits"], datetime(2026, 9, 1), datetime(2026, 10, 1), "mois", datetime(2026, 10, 15, 14),
                       offres=_offres)
verifier("pur : deux capacités réelles en désaccord pour un cours -> capacité inconnue",
         _r["champs"]["tauxRemplissage"].get("valeur") is None, _r["champs"]["tauxRemplissage"])
_r = RL.releve_mensuel(_tab["faits"], datetime(2026, 9, 1), datetime(2026, 10, 1), "mois", datetime(2026, 10, 15, 14),
                       offres=_offres[:3])
verifier("pur : capacité réelle unique -> taux = 3 / 6 = 50.0", _r["champs"]["tauxRemplissage"] == {"valeur": 50.0},
         _r["champs"]["tauxRemplissage"])

# ═══ 7. les blocs existants : IDENTIQUES à la version d'avant (7354a552) ═══
try:
    _src = subprocess.check_output(["git", "-C", F.RACINE, "show", "7354a552:api/routes/analytics_stats.py"],
                                   stderr=subprocess.DEVNULL).decode("utf-8")
    _ref = types.ModuleType("api.routes._ref_analytics_stats")
    exec(compile(_src, "<analytics_stats@7354a552>", "exec"), _ref.__dict__)
except Exception:
    _ref = None
verifier("référence 7354a552 chargée depuis git", _ref is not None)
if _ref is not None:
    _orig = S.construire_reponse
    _captures = []

    def _espion(*a, **k):
        _captures.append((copy.deepcopy(a), copy.deepcopy(k)))
        return _orig(*a, **k)
    R.construire_reponse = _espion
    try:
        for _mois in ("2026-09", "2026-10"):
            _reinit()
            _, c, _ = appel(CK, mois=_mois)
            _a, _k = _captures[-1]
            _k.pop("releve_contexte", None)
            _attendu = _ref.construire_reponse(*_a, **_k)
            _c = dict(c)
            _c.pop("releve_mensuel", None)
            verifier("mois %s : réponse SANS releve_mensuel = version d'avant, clé pour clé" % _mois,
                     json.loads(json.dumps(_attendu)) == _c and list(_attendu.keys()) == [x for x in c.keys() if x != "releve_mensuel"])
    finally:
        R.construire_reponse = _orig
    _bi = S.reponse_base_indisponible(datetime(2026, 9, 1), datetime(2026, 10, 1), "mois", "semaine", "finances", "x")
    _bi.pop("releve_mensuel")
    verifier("réponse « base indisponible » inchangée hors releve_mensuel",
             _bi == _ref.reponse_base_indisponible(datetime(2026, 9, 1), datetime(2026, 10, 1), "mois", "semaine", "finances", "x"))

ok = sum(1 for _, c_, _ in RESULTATS if c_)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)[:400]) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

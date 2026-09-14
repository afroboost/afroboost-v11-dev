# -*- coding: utf-8 -*-
"""ANALYTICS PHASE 1 — le moteur pur et la route, sur des données SYNTHÉTIQUES.

Ce que ces bancs tiennent :
  * la règle « essai » du cockpit est LA MÊME que `est_un_essai` (même verdict
    sur les mêmes documents) et le filtre pur = le filtre Mongo ;
  * mercredi / dimanche : convention JS (0 = dimanche, 3 = mercredi), depuis la
    date RÉELLE de l'occurrence — toute inversion casse ;
  * exclusion des produits, e-mail normalisé, participants uniques, nouveaux,
    récurrents, délai (jour même, 1, 2-3, 4-7, > 7), fidélité, essais,
    présence inconnue ≠ absence, couverture ;
  * périodes : aujourd'hui, semaine, mois, année, perso ;
  * route : 401 sans jeton, 200 coach (isolé à son coach_id, 403 s'il demande un
    autre), 200 super-admin (tout), nombre FIXE de requêtes.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_analytics_cockpit.py
"""
import asyncio, os, sys, types
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

# `api.routes.shared` s'importe sans FastAPI ; `analytics_shared` aussi.
from api.routes import analytics_shared as A
from api.routes.shared import essai6_verdict, essai2_filtre_gratuit_pur, ESSAI2_FILTRE_GRATUIT, est_un_essai

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


# ═══ 0. données synthétiques ═══
COACH = "coach@exemple.invalid"
AUTRE = "autre@exemple.invalid"
ADMIN = "admin@exemple.invalid"


def resa(id_, email, occ, cree, course_id="c-mer", course_name="Silent", coach=COACH, **kw):
    d = {"id": id_, "userEmail": email, "userName": "P " + id_, "courseId": course_id,
         "courseName": course_name, "datetime": occ, "createdAt": cree, "coach_id": coach,
         "validated": False, "isProduct": False, "quantity": 1, "price": 30.0,
         "promoCode": None, "discountCode": None, "source": "subscriber_space"}
    d.update(kw)
    return d


# Mercredi 9 sept 2026 (weekday JS 3) et dimanche 13 sept 2026 (JS 0).
MER = "2026-09-09T18:30:00"
DIM = "2026-09-13T18:30:00"
RESAS = [
    resa("r1", "Anna@Mail.CH ", MER, "2026-09-09T10:00:00+00:00"),                 # jour même, mercredi
    resa("r2", "anna@mail.ch", DIM, "2026-09-12T20:00:00+00:00", "c-dim"),          # 1 jour, dimanche
    resa("r3", "bob@mail.ch", DIM, "2026-09-10T08:00:00+00:00", "c-dim", validated=True),   # 3 jours, présente
    resa("r4", "carl@mail.ch", MER, "2026-09-03T08:00:00+00:00", absence_marked_at="x"),    # 6 jours, absente
    resa("r5", "dora@mail.ch", DIM, "2026-08-30T08:00:00+00:00", "c-dim"),          # 14 jours
    resa("r6", "anna@mail.ch", "2026-08-05T18:30:00", "2026-08-01T08:00:00+00:00"),  # historique (avant période)
    resa("r7", "eve@mail.ch", MER, "2026-09-08T08:00:00+00:00", discountCode="AFR-ESSAI"),  # essai (P1)
    resa("r8", "", MER, "2026-09-08T08:00:00+00:00"),                               # sans e-mail
    resa("p1", "shop@mail.ch", "2026-09-10T00:00:00", "2026-09-10T08:00:00+00:00", "", "", isProduct=True),  # produit
    resa("x1", "autre@mail.ch", MER, "2026-09-08T08:00:00+00:00", coach=AUTRE),     # autre coach
]
COURS = {"c-mer": {"id": "c-mer", "name": "Silent", "weekday": 3, "locationName": "Lac"},
         "c-dim": {"id": "c-dim", "name": "Sunday", "weekday": 0, "locationName": "Lac"}}
CODES = {"AFR-ESSAI": {"code": "AFR-ESSAI", "payment_method": "free", "total_paid": 0}}


def faits_de(resas=RESAS):
    return A.construire_faits(resas, COURS, {}, {}, CODES, {}, {})


# ═══ 1. la règle essai : même verdict que le dépôt ═══
verifier("filtre pur == filtre Mongo (free & 0)", essai2_filtre_gratuit_pur({"payment_method": "free", "total_paid": 0}))
verifier("filtre pur : payé -> non", not essai2_filtre_gratuit_pur({"payment_method": "free", "total_paid": 30}))
verifier("filtre pur : social_proof -> oui", essai2_filtre_gratuit_pur({"source": "social_proof"}))
verifier("filtre pur : forme du filtre Mongo inchangée",
         ESSAI2_FILTRE_GRATUIT == {"$or": [{"payment_method": "free", "total_paid": 0}, {"source": "social_proof"}]})
verifier("P2 : forfait offert -> essai", essai6_verdict(None, {"origine_paiement": "offert"}, None))
verifier("P3 : offre à 0 -> essai", essai6_verdict(None, {"offer_id": "o"}, {"price": 0}))
verifier("forfait payant, offre payante -> pas un essai", not essai6_verdict(None, {"origine_paiement": "twint"}, {"price": 150}))


def _filtre_ok(d, f):
    for k, v in f.items():
        if k == "$or":
            if not any(_filtre_ok(d, alt) for alt in v):
                return False
        elif d.get(k) != v:
            return False
    return True


class _Coll:
    def __init__(self, docs): self.docs = docs
    async def find_one(self, f, p=None):
        for d in self.docs:
            if _filtre_ok(d, f):
                return d
        return None


class _DB:
    def __init__(self, subs, codes, offers):
        self._c = {"subscriptions": _Coll(subs), "discount_codes": _Coll(codes), "offers": _Coll(offers)}
    def __getitem__(self, n): return self._c[n]


for cas, subs, codes, offers, attendu in (
    ("P1 code gratuit", [], [{"code": "X", "payment_method": "free", "total_paid": 0}], [], True),
    ("P2 forfait offert", [{"code": "X", "origine_paiement": "offert"}], [], [], True),
    ("P3 offre 0", [{"code": "X", "offer_id": "o"}], [], [{"id": "o", "price": 0}], True),
    ("payant", [{"code": "X", "offer_id": "o", "origine_paiement": "twint"}], [], [{"id": "o", "price": 150}], False),
):
    db = _DB(subs, codes, offers)
    v_base = run(est_un_essai(db, code="X"))
    sub = subs[0] if subs else None
    v_pur = essai6_verdict(codes[0] if codes else None, sub, offers[0] if offers else None)
    verifier("est_un_essai (base) == essai6_verdict (pur) — %s" % cas, v_base == v_pur == attendu, (v_base, v_pur))

# ═══ 2. table de faits ═══
T = faits_de()
F = {f["reservation_id"]: f for f in T["faits"]}
verifier("le produit est écarté", "p1" not in F and T["ecartees"]["produits"] == 1)
verifier("9 faits de cours (10 réservations − 1 produit)", len(T["faits"]) == 9, len(T["faits"]))
verifier("e-mail normalisé : « Anna@Mail.CH  » -> anna@mail.ch", F["r1"]["participant_key"] == "anna@mail.ch")
verifier("MERCREDI : 9 sept 2026 -> weekday_js 3, mercredi=True, dimanche=False",
         F["r1"]["weekday_js"] == 3 and F["r1"]["mercredi"] and not F["r1"]["dimanche"] and F["r1"]["jour"] == "mercredi")
verifier("DIMANCHE : 13 sept 2026 -> weekday_js 0, dimanche=True, mercredi=False",
         F["r2"]["weekday_js"] == 0 and F["r2"]["dimanche"] and not F["r2"]["mercredi"] and F["r2"]["jour"] == "dimanche")
verifier("la convention vient de la DATE réelle, pas du cours",
         A.weekday_js_depuis_date(datetime(2026, 9, 13).date()) == 0 and A.weekday_js_depuis_date(datetime(2026, 9, 9).date()) == 3
         and A.weekday_js_depuis_date(datetime(2026, 9, 7).date()) == 1)   # lundi = 1 en JS
verifier("anti-inversion : NOMS_JOURS_JS[0] = dimanche, [3] = mercredi",
         A.NOMS_JOURS_JS[0] == "dimanche" and A.NOMS_JOURS_JS[3] == "mercredi")
verifier("délai : réservation le jour même -> jour_meme", F["r1"]["delai_categorie"] == "jour_meme")
verifier("délai : la veille -> 1_jour", F["r2"]["delai_categorie"] == "1_jour")
verifier("délai : 3 jours -> 2_3_jours", F["r3"]["delai_categorie"] == "2_3_jours")
verifier("délai : 6 jours -> 4_7_jours", F["r4"]["delai_categorie"] == "4_7_jours")
verifier("délai : 14 jours -> plus_7_jours", F["r5"]["delai_categorie"] == "plus_7_jours")
verifier("créé à 10:00 UTC -> 12:00 Zurich (été) : heure locale",
         F["r1"]["created_at"].endswith("T12:00:00"), F["r1"]["created_at"])
verifier("essai gratuit détecté par le code (P1)", F["r7"]["essai"] is True and F["r1"]["essai"] is False)
verifier("présence : validée -> confirmée ; absence déclarée -> absente ; sinon INCONNUE (jamais no-show)",
         F["r3"]["presence"] == "confirmee" and F["r4"]["presence"] == "absente" and F["r1"]["presence"] == "inconnue")
verifier("lieu depuis le cours", F["r1"]["lieu"] == "Lac")
verifier("sans e-mail : signalé", T["qualite"]["sans_email"] == 1)
verifier("valeur financière : prix présent mais aucun tarif figé -> valeur inconnue (on ne devine pas)",
         F["r1"]["valeur"] is None and F["r1"]["valeur_statut"] == "inconnu")

# ═══ 3. KPI sur le mois de septembre 2026 ═══
DEBUT, FIN = datetime(2026, 9, 1), datetime(2026, 10, 1)
faits_coach = [f for f in T["faits"] if f["coach_id"] == COACH]
K = A.calculer_kpi(faits_coach, DEBUT, FIN, "jour")
verifier("réservations cours du mois = 7 (r1..r5, r7, r8)", K["participants"]["reservations_cours"] == 7, K["participants"])
verifier("participants uniques = 5 (anna dédoublonnée, r8 sans e-mail exclu)", K["participants"]["uniques"] == 5, K["participants"])
verifier("nouveaux = 4 (anna a un historique en août)", K["participants"]["nouveaux"] == 4, K["participants"])
verifier("récurrents = 1 (anna)", K["participants"]["recurrents"] == 1)
verifier("séances détectées = 2 (mercredi 9, dimanche 13)", K["cours"]["seances"] == 2, K["cours"])
verifier("moyenne par séance = 3.5", K["cours"]["moyenne_par_seance"] == 3.5)
verifier("mercredi : 4 réservations, dimanche : 3", K["cours"]["mercredi"]["reservations"] == 4 and K["cours"]["dimanche"]["reservations"] == 3, K["cours"])
verifier("anticipation : jour_meme 1 (r1), 1_jour 3 (r2, r7, r8), 2_3 1 (r3), 4_7 1 (r4), plus_7 1 (r5)",
         [K["reservation"]["anticipation"][c] for c in ("jour_meme", "1_jour", "2_3_jours", "4_7_jours", "plus_7_jours")] == [1, 3, 1, 1, 1],
         K["reservation"]["anticipation"])
verifier("délai moyen calculé", isinstance(K["reservation"]["delai_moyen_jours"], float))
verifier("répartition par heure : 24 clés, somme = 7", len(K["reservation"]["par_heure"]) == 24 and sum(K["reservation"]["par_heure"].values()) == 7)
verifier("fidélité : anna (3 participations) en 2_5, les 4 autres en 1",
         K["fidelite"] == {"1": 4, "2_5": 1, "6_10": 0, "plus_10": 0}, K["fidelite"])
verifier("essais détectés = 1", K["essais"]["detectes"] == 1)
verifier("présence : 1 confirmée, 1 absente, 5 inconnues — jamais converties en no-show",
         K["presence"]["confirmee"] == 1 and K["presence"]["absente"] == 1 and K["presence"]["inconnue"] == 5)
verifier("couverture présence = 2/7 = 28.6 %", K["presence"]["couverture_pct"] == 28.6 and "2 vérifiées sur 7" in K["presence"]["libelle"])
verifier("qualité : présence partiel, valeur inconnu, identité partiel",
         K["qualite"]["presence"] == "partiel" and K["qualite"]["valeur_financiere"] == "inconnu" and K["qualite"]["identite"] == "partiel", K["qualite"])
verifier("évolution : 2 points (9 et 13 sept)", [e["periode"] for e in K["evolution"]] == ["2026-09-09", "2026-09-13"])
verifier("autre coach exclu du périmètre", all(f["coach_id"] == COACH for f in faits_coach) and len(faits_coach) == 8)

# ═══ 4. périodes ═══
NOW = datetime(2026, 9, 14, 15, 0, 0)   # lundi 14 sept 2026
d, f = A.bornes_periode("aujourdhui", NOW)
verifier("aujourd'hui = [14, 15)", (d, f) == (datetime(2026, 9, 14), datetime(2026, 9, 15)))
d, f = A.bornes_periode("semaine", NOW)
verifier("semaine = lundi 14 -> lundi 21", (d, f) == (datetime(2026, 9, 14), datetime(2026, 9, 21)))
d, f = A.bornes_periode("mois", NOW)
verifier("mois = 1er sept -> 1er oct", (d, f) == (datetime(2026, 9, 1), datetime(2026, 10, 1)))
d, f = A.bornes_periode("annee", NOW)
verifier("année = 1er jan 2026 -> 1er jan 2027", (d, f) == (datetime(2026, 1, 1), datetime(2027, 1, 1)))
d, f = A.bornes_periode("perso", NOW, "2026-09-09", "2026-09-13")
verifier("perso = [9, 14) (au inclus)", (d, f) == (datetime(2026, 9, 9), datetime(2026, 9, 14)))
verifier("perso invalide -> None", A.bornes_periode("perso", NOW, "x", "y") == (None, None))
verifier("mois de décembre -> janvier suivant", A.bornes_periode("mois", datetime(2026, 12, 3))[1] == datetime(2027, 1, 1))
K_sem = A.calculer_kpi(faits_coach, datetime(2026, 9, 7), datetime(2026, 9, 14), "jour")
verifier("filtre semaine 7-13 sept : 7 réservations (r6 d'août exclue)", K_sem["participants"]["reservations_cours"] == 7)
K_jour = A.calculer_kpi(faits_coach, datetime(2026, 9, 13), datetime(2026, 9, 14), "jour")
verifier("filtre jour 13 sept : 3 réservations (dimanche)", K_jour["participants"]["reservations_cours"] == 3)

# ═══ 5. la route : auth et isolation (faux serveur, faux Mongo) ═══
class _Cur:
    def __init__(self, docs): self.d = docs
    async def to_list(self, n): return [dict(x) for x in self.d]


def _match(doc, f):
    for k, v in f.items():
        if k == "$or":
            if not any(_match(doc, alt) for alt in v): return False
        elif isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]: return False
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]: return False
        elif doc.get(k) != v:
            return False
    return True


class _Coll2:
    def __init__(self, docs, base): self.docs, self.base = docs, base
    def find(self, f, p=None):
        self.base.requetes += 1
        return _Cur([d for d in self.docs if _match(d, f)])


class _Base:
    def __init__(self):
        self.requetes = 0
        self.reservations = _Coll2(RESAS, self)
        self.courses = _Coll2(list(COURS.values()), self)
        self.subscriptions = _Coll2([], self)
        self.discount_codes = _Coll2(list(CODES.values()), self)
        self.offers = _Coll2([], self)
        self.memberships = _Coll2([], self)


def _serveur(base, jwt_email):
    """`api.server` de substitution : db + les deux gardes JWT, sans FastAPI."""
    m = types.ModuleType("api.server")
    m.db = base
    m._v311_coach_email_from_jwt = lambda request: jwt_email
    async def _est_coach(email): return email in (COACH, AUTRE, ADMIN)
    m._v309_is_coach_or_admin = _est_coach
    sys.modules["api.server"] = m
    rr = types.ModuleType("api.routes.reservation_routes")
    rr.lot1_occurrence_iso = lambda v: (A.parser_local(v).strftime("%Y-%m-%dT%H:%M:%S") if A.parser_local(v) else "")
    sys.modules["api.routes.reservation_routes"] = rr


import api.routes.shared as _shared
_shared.is_super_admin = lambda e: (e or "").lower() == ADMIN      # le banc décide qui est admin

try:
    import fastapi  # noqa: F401
    from api.routes.analytics_routes import analytics_cockpit, _perimetre
    from fastapi import HTTPException

    class _Req:
        headers = {}

    def _appel(jwt, **params):
        base = _Base()
        _serveur(base, jwt)
        try:
            r = run(analytics_cockpit(_Req(), **params))
            return 200, r, base.requetes
        except HTTPException as e:
            return e.status_code, None, base.requetes

    s, _, _ = _appel("", periode="mois")
    verifier("JWT absent -> 401", s == 401, s)
    s, _, _ = _appel("inconnu@exemple.invalid", periode="mois")
    verifier("JWT sans droit coach -> 403", s == 403, s)
    s, r, n = _appel(COACH, periode="perso", du="2026-09-01", au="2026-09-30")
    verifier("JWT coach -> 200", s == 200, s)
    verifier("coach : périmètre imposé = son coach_id, l'autre coach est absent",
             r and r["perimetre"]["coach_id"] == COACH and r["participants"]["reservations_cours"] == 7, r and r["perimetre"])
    verifier("au plus 6 requêtes, jamais une par participant", n <= 6, n)
    # Le nombre de requêtes ne dépend PAS du nombre de participants : on triple
    # les réservations (participants distincts) et on recompte.
    _plus = [resa("z%d" % i, "z%d@mail.ch" % i, MER, "2026-09-08T08:00:00+00:00") for i in range(30)]
    RESAS.extend(_plus)
    s2, r2, n2 = _appel(COACH, periode="perso", du="2026-09-01", au="2026-09-30")
    del RESAS[-30:]
    verifier("30 participants de plus -> même nombre de requêtes (%d)" % n, s2 == 200 and n2 == n and r2["participants"]["uniques"] == 35, (n, n2))
    s, _, _ = _appel(COACH, periode="mois", coach_id=AUTRE)
    verifier("coach qui demande un autre coach -> 403", s == 403, s)
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30")
    verifier("JWT super-admin -> 200, tout le site (8 réservations cours)",
             s == 200 and r["perimetre"]["coach_id"] == "tous" and r["participants"]["reservations_cours"] == 8, r and r["participants"])
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30", coach_id=AUTRE)
    verifier("super-admin sur un coach -> 200, périmètre de ce coach (1)",
             s == 200 and r["participants"]["reservations_cours"] == 1)
    # ── filtre COURS : en mémoire, liste complète, retour à « tous » ──
    s, r, n = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30", course_id="c-dim")
    verifier("cours précis : 3 réservations (dimanche), périmètre course_id posé",
             s == 200 and r["participants"]["reservations_cours"] == 3 and r["perimetre"]["course_id"] == "c-dim", r and r["participants"])
    verifier("cours précis : la liste des cours reste COMPLÈTE (2 cours) et compte les réservations",
             [c["id"] for c in r["cours_disponibles"]] == ["c-mer", "c-dim"] and r["cours_disponibles"][0]["reservations"] == 6, r and r["cours_disponibles"])
    verifier("cours précis : toujours ≤ 6 requêtes (filtre en mémoire)", n <= 6, n)
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30", course_id="c-mer")
    verifier("changement de cours : 5 réservations (mercredi, autre coach inclus pour l'admin)", r["participants"]["reservations_cours"] == 5, r["participants"])
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30", course_id="")
    verifier("retour « tous les cours » : 8", r["participants"]["reservations_cours"] == 8 and r["perimetre"]["course_id"] == "tous")
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-13", au="2026-09-13", coach_id=COACH, course_id="c-dim")
    verifier("période + coach + cours combinés : 3 (dimanche 13, coach, c-dim)", s == 200 and r["participants"]["reservations_cours"] == 3, r and r["participants"])
    s, r, _ = _appel(ADMIN, periode="perso", du="2026-09-01", au="2026-09-30", course_id="inconnu")
    verifier("cours inconnu : 0 réservation, liste toujours complète", r["participants"]["reservations_cours"] == 0 and len(r["cours_disponibles"]) == 2)
    s, _, _ = _appel(ADMIN, periode="n_importe_quoi")
    verifier("période inconnue -> 400", s == 400, s)
    s, _, _ = _appel(ADMIN, periode="perso", du="", au="")
    verifier("perso sans bornes -> 400", s == 400, s)
    verifier("_perimetre : super-admin sans coach_id = tout", _perimetre(ADMIN, "") == "")
except ImportError:
    verifier("fastapi absent : la route n'a pas pu être exercée", False, "installer fastapi")

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

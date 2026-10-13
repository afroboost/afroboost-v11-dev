#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618L — PARCOURS ÉVÉNEMENT : paliers de prix datés par l'ÉVÉNEMENT, et plus de faux « 50 places ».

Incident reproduit (Playwright, 13/10/2026) : « AFROBOOST SILENT — ÉDITION SPÉCIALE » a lieu le
mercredi 28 octobre 2026 à 18h45 (son cours dédié), mais la date de référence des paliers de son
offre valait le 28 NOVEMBRE -> « 30 CHF dès le samedi 21 novembre ».

Attendu (Bassi, heure de Zurich, le serveur fait foi) :
  25 CHF prévente        jusqu'au 21 octobre 2026 18h45
  30 CHF standard        21 octobre 18h45 -> 27 octobre 18h45
  40 CHF dernière minute 27 octobre 18h45 -> début de l'événement

Banc permanent : moteur de prix pur + vraies routes (offre, cours) sur une base en mémoire.
Lancement : python3 tests/test_v618l_evenement.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.pop("JWT_SECRET", None)
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v618l-inexistant:27017")   # jamais contacté
import _base_memoire as B  # noqa: E402
import api.server as S  # noqa: E402
from api.pricing import compute_active_price, tier_boundaries  # noqa: E402
from api.routes import reference_evenement as RE  # noqa: E402
from api.routes import share_invite_routes as SI  # noqa: E402

RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


Z = timezone.utc
COURS_ID = "c-silent"
OFFRE = {"id": "o-silent", "name": "AFROBOOST SILENT — ÉDITION SPÉCIALE", "offer_type": "event", "price": 25.0,
         "progressive_pricing": True, "price_early_bird": 25.0, "price_standard": 30.0, "price_last_minute": 40.0,
         "early_bird_days_before": 7, "standard_hours_before": 24, "countdown_date": "2026-10-28", "countdown_time": "18:45",
         "linked_course_ids": [COURS_ID], "stock": -1, "max_participants": None, "coach_id": B.ADMIN, "visible": True}
COURS = {"id": COURS_ID, "name": "AFROBOOST SILENT — ÉDITION SPÉCIALE", "date": "2026-10-28", "time": "18:45",
         "coach_id": B.ADMIN, "visible": True}


def prix(offre, quand):
    return compute_active_price(offre, now=quand)["price"]


# ── Base en mémoire avec `async for` (suivre_le_cours) et filtre « tableau contient » ─────────
class Curseur:
    def __init__(self, docs):
        self.docs = docs

    def limit(self, n):
        return Curseur(self.docs[:n])

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None, length=None):
        n = n or length
        return list(self.docs)[:n] if n else list(self.docs)

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


def correspond(doc, filtre):
    for k, v in (filtre or {}).items():
        val = doc.get(k)
        if isinstance(v, dict):
            for op, arg in v.items():
                if op == "$in" and not (val in arg or (isinstance(val, list) and set(val) & set(arg))):
                    return False
                if op == "$ne" and val == arg:
                    return False
        elif isinstance(val, list) and not isinstance(v, list):
            if v not in val:
                return False
        elif val != v:
            return False
    return True


class Coll(B._Collection):
    def find(self, requete=None, proj=None):
        return Curseur([B._projeter(d, proj) for d in self.docs if correspond(d, requete)])

    async def find_one(self, requete=None, proj=None):
        for d in self.docs:
            if correspond(d, requete):
                return B._projeter(d, proj)
        return None

    async def update_one(self, requete, maj, **k):
        for d in self.docs:
            if correspond(d, requete):
                d.update(maj.get("$set", {}))
                return type("R", (), {"modified_count": 1, "matched_count": 1})()
        return type("R", (), {"modified_count": 0, "matched_count": 0})()


class Base(B._Base):
    def __init__(self):
        super().__init__()
        self.offers, self.courses, self.discount_codes = Coll(), Coll(), Coll()


def nouvelle_base(offre_countdown="2026-11-28"):
    b = Base()
    b.offers.docs.append(dict(OFFRE, countdown_date=offre_countdown))
    b.courses.docs.append(dict(COURS))
    return b


def partie_paliers():
    # 1) Les bascules ATTENDUES, à la minute, en heure de Zurich (CEST jusqu'au 25/10, CET après).
    o = dict(OFFRE)
    bornes = tier_boundaries(o)
    verifier("1 fin de prévente = 21/10/2026 18h45 Zurich (16:45 UTC)", bornes["early_bird_end"] == datetime(2026, 10, 21, 16, 45, tzinfo=Z), bornes)
    verifier("2 fin du standard = 27/10/2026 18h45 Zurich (17:45 UTC, heure d'hiver)", bornes["standard_end"] == datetime(2026, 10, 27, 17, 45, tzinfo=Z), bornes)
    cas = [
        (datetime(2026, 10, 13, 12, 0, tzinfo=Z), 25.0, "aujourd'hui (13/10)"),
        (datetime(2026, 10, 21, 16, 44, tzinfo=Z), 25.0, "21/10 18h44"),
        (datetime(2026, 10, 21, 16, 45, tzinfo=Z), 30.0, "21/10 18h45"),
        (datetime(2026, 10, 27, 17, 44, tzinfo=Z), 30.0, "27/10 18h44"),
        (datetime(2026, 10, 27, 17, 45, tzinfo=Z), 40.0, "27/10 18h45"),
        (datetime(2026, 10, 28, 17, 44, tzinfo=Z), 40.0, "28/10 18h44 (juste avant le début)"),
    ]
    for i, (quand, attendu, lib) in enumerate(cas):
        verifier("3.%d %s -> %s CHF" % (i + 1, lib, int(attendu)), prix(o, quand) == attendu, prix(o, quand))
    # 4) Le BUG reproduit avec la donnée fausse (28 novembre) : la prévente débordait d'un mois.
    faux = dict(OFFRE, countdown_date="2026-11-28")
    verifier("4 donnée fausse (28/11) : le 22/10 resterait en prévente 25 CHF (le bug)",
             prix(faux, datetime(2026, 10, 22, 12, 0, tzinfo=Z)) == 25.0)
    verifier("4b … et la bascule annoncée serait le samedi 21 NOVEMBRE",
             tier_boundaries(faux)["early_bird_end"].astimezone(Z).date().isoformat() == "2026-11-21")


async def partie_alignement():
    # 5) Règle pure : offre événement à UN cours daté -> la date du cours.
    verifier("5 règle : événement à un cours daté -> (date, heure) du cours",
             RE.reference_du_cours(OFFRE, COURS) == ("2026-10-28", "18:45"))
    verifier("5b offre NON événement : jamais touchée", RE.reference_du_cours(dict(OFFRE, offer_type="subscription"), COURS) is None)
    verifier("5c événement à DEUX cours : rien n'est deviné",
             RE.reference_du_cours(dict(OFFRE, linked_course_ids=[COURS_ID, "autre"]), COURS) is None)
    verifier("5d cours récurrent sans date : rien", RE.reference_du_cours(OFFRE, dict(COURS, date=None)) is None)

    # 6) Route réelle : sauvegarder l'offre avec la date fausse -> le serveur remet le 28 octobre.
    b = nouvelle_base("2026-11-28")
    S.db = b
    corps = {k: v for k, v in OFFRE.items() if k not in ("id", "coach_id")}
    corps["countdown_date"] = "2026-11-28"
    res, code = await _route(S.update_offer("o-silent", S.OfferCreate(**corps), B._Requete(B.ADMIN)))
    o = b.offers.docs[0]
    verifier("6 PUT /offers : date saisie 28/11 -> enregistrée 28/10 18:45 (date de l'événement)",
             code is None and (o["countdown_date"], o["countdown_time"]) == ("2026-10-28", "18:45"), (code, o.get("countdown_date")))
    verifier("6b … donc 30 CHF dès le 21/10 18h45 (et plus le 21/11)",
             prix(o, datetime(2026, 10, 22, 12, 0, tzinfo=Z)) == 30.0)
    verifier("6c prix, paliers, durées et liens INCHANGÉS par l'alignement",
             (o["price_early_bird"], o["price_standard"], o["price_last_minute"], o["early_bird_days_before"],
              o["standard_hours_before"], o["linked_course_ids"]) == (25.0, 30.0, 40.0, 7, 24, [COURS_ID]))

    # 7) Route réelle : le cours change de date -> les paliers de l'offre suivent.
    res, code = await _route(S.update_course(COURS_ID, {"date": "2026-11-04", "time": "19:00"}, B._Requete(B.ADMIN)))
    o = b.offers.docs[0]
    verifier("7 PUT /courses : l'événement passe au 04/11 19:00 -> l'offre suit",
             code is None and (o["countdown_date"], o["countdown_time"]) == ("2026-11-04", "19:00"), (code, o.get("countdown_date"), o.get("countdown_time")))
    res, code = await _route(S.update_course(COURS_ID, {"name": "Nouveau nom"}, B._Requete(B.ADMIN)))
    verifier("7b PUT /courses sans date : l'offre n'est pas réécrite", b.offers.docs[0]["countdown_date"] == "2026-11-04")

    # 8) Une offre NON événement liée au même cours garde SA date (compte à rebours d'une promo).
    b2 = nouvelle_base("2026-10-28")
    b2.offers.docs.append(dict(OFFRE, id="o-pack", offer_type="subscription", countdown_date="2026-12-31", countdown_time="23:59"))
    S.db = b2
    await _route(S.update_course(COURS_ID, {"date": "2026-10-30"}, B._Requete(B.ADMIN)))
    verifier("8 offre abonnement liée au même cours : date JAMAIS modifiée",
             next(x for x in b2.offers.docs if x["id"] == "o-pack")["countdown_date"] == "2026-12-31")


async def partie_cloisonnement():
    # 10) Un cours modifié ne réécrit JAMAIS l'offre d'un autre coach liée à ce cours.
    b = nouvelle_base("2026-10-28")
    b.offers.docs.append(dict(OFFRE, id="o-autre", coach_id="autre.coach@exemple.test", countdown_date="2026-10-28"))
    S.db = b
    await _route(S.update_course(COURS_ID, {"date": "2026-11-11"}, B._Requete(B.ADMIN)))
    verifier("10 cours modifié : l'offre du MÊME coach suit",
             next(x for x in b.offers.docs if x["id"] == "o-silent")["countdown_date"] == "2026-11-11")
    verifier("10b … l'offre d'un AUTRE coach liée au même cours n'est JAMAIS réécrite",
             next(x for x in b.offers.docs if x["id"] == "o-autre")["countdown_date"] == "2026-10-28")


async def partie_places():
    # 9) « 50 PLACES » : V618M — le texte est un réglage SÉPARÉ ; seule une capacité ACTIVÉE limite.
    from api.routes import evenement_special as EVS
    verifier("9 stock -1 / max_participants vide / aucun réglage : AUCUNE capacité",
             EVS.capacite(OFFRE) is None)
    verifier("9b ancienne heuristique abandonnée : max_participants 50 SANS la case -> aucune capacité",
             EVS.capacite(dict(OFFRE, max_participants=50, stock=30)) is None)
    verifier("9c capacité ACTIVÉE par le coach (50) : capacité réelle", EVS.capacite(dict(OFFRE, capacite_limitee=True, capacite_max=50)) == 50)
    verifier("9d texte « 50 PLACES » visible : jamais une capacité",
             EVS.capacite(dict(OFFRE, texte_urgence="50 PLACES", texte_urgence_visible=True)) is None)


async def _route(coro):
    try:
        return await coro, None
    except S.HTTPException as e:
        return None, e.status_code


def main():
    partie_paliers()
    asyncio.run(partie_alignement())
    asyncio.run(partie_cloisonnement())
    asyncio.run(partie_places())
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:700])
        _ok += ok
    print("%d / %d verifications V618L au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

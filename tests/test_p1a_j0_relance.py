# -*- coding: utf-8 -*-
"""P1A (07/10/2026) — la relance J+0 après un essai gratuit ne partait plus depuis mi-septembre.

CONSTAT EN PRODUCTION (lecture seule, 07/10) : drapeaux J+0 allumés ; 2 envois au total, le dernier
le 03/09 ; 7 essais présents depuis (20/09 → 04/10) et 0 relance — sans aucune trace, car la fonction
sort en silence sur « non_consomme ».

CAUSE : depuis mi-septembre, les offres de production portent `coach_id` = l'adresse du super-admin
(V535b l'a constaté et corrigé dans `lot2_filtre_offres`). Mais `essai6_offres_gratuites` filtrait
encore avec `p1a_filtre_proprietaire(None)`, qui ne reconnaît que « sans propriétaire » = None / "" /
absent. Appelée sans propriétaire par la relance J+0, elle ne trouvait donc PLUS l'offre d'essai, le
forfait d'essai était écarté par `essai6_forfaits`, et `essai6_consomme` répondait None.

Ce banc rejoue exactement cette situation avec les VRAIES fonctions (`p1b_relance_j0`, `est_un_essai`,
`essai6_consomme`, `essai6_forfaits`, `essai6_offres_gratuites`) sur une base en mémoire. Aucun
e-mail n'est envoyé : l'expéditeur est remplacé par un compteur.

Lancer : python3 -m pytest tests/test_p1a_j0_relance.py -q
"""
import asyncio
import os
import sys

os.environ.setdefault("JWT_SECRET", "secret-de-test-p1a-j0")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p1a-inexistant:27017")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import api.server as S
from api.routes import shared as SH

ADMIN = S.SUPER_ADMIN_EMAILS[0]
INVITEE = "invitee@exemple.test"
PARTENAIRE = "partenaire@exemple.test"


# ───────────────────── mini-Mongo en mémoire : $or, $in, $exists, $ne, chemins pointés ─────────────────────
def _lire(doc, chemin):
    cur = doc
    for morceau in chemin.split("."):
        if not isinstance(cur, dict) or morceau not in cur:
            return False, None
        cur = cur[morceau]
    return True, cur


def _correspond(doc, requete):
    for cle, attendu in (requete or {}).items():
        if cle == "$or":
            if not any(_correspond(doc, s) for s in attendu):
                return False
            continue
        present, valeur = _lire(doc, cle)
        if isinstance(attendu, dict) and any(k.startswith("$") for k in attendu):
            for op, arg in attendu.items():
                if op == "$exists" and present != bool(arg):
                    return False
                if op == "$in" and valeur not in arg:
                    return False
                if op == "$ne" and valeur == arg:
                    return False
        elif not present and attendu is None:
            continue
        elif valeur != attendu:
            return False
    return True


def _poser(doc, chemin, valeur):
    morceaux = chemin.split(".")
    cur = doc
    for m in morceaux[:-1]:
        cur = cur.setdefault(m, {})
    cur[morceaux[-1]] = valeur


class _Curseur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return [dict(d) for d in (self.docs[:n] if n else self.docs)]


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, requete=None, proj=None):
        return _Curseur([d for d in self.docs if _correspond(d, requete)])

    async def find_one(self, requete=None, proj=None):
        for d in self.docs:
            if _correspond(d, requete):
                return dict(d)
        return None

    async def update_one(self, requete, maj, upsert=False):
        for d in self.docs:
            if _correspond(d, requete):
                for k, v in maj.get("$set", {}).items():
                    _poser(d, k, v)
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        return type("R", (), {"matched_count": 0, "modified_count": 0})()


class _Base:
    def __init__(self, coach_des_offres=ADMIN):
        self.offers = _Coll([
            {"id": "offre-essai", "name": "Cours d'essai GRATUIT", "price": 0.0, "coach_id": coach_des_offres},
            {"id": "offre-pulse", "name": "PULSE x10", "price": 250, "coach_id": coach_des_offres},
        ])
        self.subscriptions = _Coll([
            {"id": "forfait-essai", "code": "AFR-ESSAI1", "offer_id": "offre-essai", "email": INVITEE,
             "payment_method": "free", "total_paid": 0},
            {"id": "forfait-pulse", "code": "AFR-PULSE1", "offer_id": "offre-pulse", "email": INVITEE,
             "payment_method": "stripe", "total_paid": 250},
        ])
        self.discount_codes = _Coll([
            {"code": "AFR-ESSAI1", "assignedEmail": INVITEE, "payment_method": "free", "total_paid": 0},
            {"code": "AFR-PULSE1", "assignedEmail": INVITEE, "payment_method": "stripe", "total_paid": 250},
        ])
        self.reservations = _Coll([
            {"id": "resa-essai", "promoCode": "AFR-ESSAI1", "discountCode": "AFR-ESSAI1", "userEmail": INVITEE,
             "userName": "Amina Test", "courseName": "Afroboost", "validated": True, "validatedAt": "2026-10-04T19:39:00"},
            {"id": "resa-pulse", "promoCode": "AFR-PULSE1", "userEmail": INVITEE, "userName": "Amina",
             "courseName": "Afroboost", "validated": True, "validatedAt": "2026-10-04T19:39:00"},
        ])

    def __getitem__(self, nom):
        return getattr(self, nom)


@pytest.fixture()
def env(monkeypatch):
    etat = {"envois": [], "reel": False}
    base = _Base()

    async def drapeaux():
        return {"P1_TRIAL_J0_ENABLED": True, "P1_TRIAL_J0_ENVOI_REEL": etat["reel"]}

    async def autorise(_email):
        return True

    async def couleur(_c):
        return "#D91CD2"

    async def faux_envoi(email, sujet, html, texte):
        etat["envois"].append(email)          # JAMAIS de vrai e-mail
        return True

    monkeypatch.setattr(S, "db", base)
    monkeypatch.setattr(S, "get_feature_flags", drapeaux)
    monkeypatch.setattr(S, "p1b_destinataire_autorise", autorise)
    monkeypatch.setattr(S, "_v259_primary_color", couleur)
    monkeypatch.setattr(S, "p1b_envoyer_email", faux_envoi)
    return base, etat


def j0(reservation):
    return asyncio.run(S.p1b_relance_j0(reservation))


def resa(base, rid):
    return next(r for r in base.reservations.docs if r["id"] == rid)


# ═══════════ LA CAUSE, isolée ═══════════
def test_offres_gratuites_au_nom_du_super_admin_sont_reconnues_sans_proprietaire(env):
    base, _ = env
    assert asyncio.run(SH.essai6_offres_gratuites(base, None)) == ["offre-essai"]


def test_essai_present_est_consomme(env):
    base, _ = env
    trouve = asyncio.run(SH.essai6_consomme(base, INVITEE, ""))
    assert trouve and trouve["id"] == "resa-essai"


# ═══════════ LE PARCOURS J+0 ═══════════
def test_j0_simulation_sans_envoi(env):
    base, etat = env
    assert j0(resa(base, "resa-essai")) == "simulation"
    assert etat["envois"] == [] and "confirmation" not in resa(base, "resa-essai")


def test_j0_reel_part_une_seule_fois(env):
    base, etat = env
    etat["reel"] = True
    assert j0(resa(base, "resa-essai")) == "envoye"
    assert etat["envois"] == [INVITEE]
    assert resa(base, "resa-essai")["confirmation"]["relance_j0"]["statut"] == "envoye"
    # rejeu, double scan, auto-présence qui repasse : jamais une 2e relance
    assert j0(resa(base, "resa-essai")) == "deja_traitee"
    assert etat["envois"] == [INVITEE]


def test_j0_jamais_pour_une_presence_payante(env):
    base, etat = env
    etat["reel"] = True
    assert j0(resa(base, "resa-pulse")) == "pas_un_essai"
    assert etat["envois"] == []


def test_j0_jamais_pour_un_absent(env):
    base, etat = env
    etat["reel"] = True
    resa(base, "resa-essai")["validated"] = False          # pas venu : l'essai n'est pas consommé
    assert j0(resa(base, "resa-essai")) == "non_consomme"
    assert etat["envois"] == []


def test_j0_jamais_si_deja_envoye(env):
    base, etat = env
    etat["reel"] = True
    resa(base, "resa-essai")["confirmation"] = {"relance_j0": {"statut": "envoye", "at": "2026-09-03T17:08:43"}}
    assert j0(resa(base, "resa-essai")) == "deja_traitee"
    assert etat["envois"] == []


def test_offres_sans_proprietaire_toujours_reconnues(monkeypatch):
    """Non-régression : les données d'avant mi-septembre (coach_id None) restent reconnues."""
    base = _Base(coach_des_offres=None)
    assert asyncio.run(SH.essai6_offres_gratuites(base, None)) == ["offre-essai"]


def test_catalogue_partenaire_reste_cloisonne(monkeypatch):
    """Un essai chez un partenaire ne compte pas comme l'essai de la plateforme, et inversement."""
    base = _Base(coach_des_offres=PARTENAIRE)
    assert asyncio.run(SH.essai6_offres_gratuites(base, None)) == []
    assert asyncio.run(SH.essai6_offres_gratuites(base, PARTENAIRE)) == ["offre-essai"]
    base2 = _Base(coach_des_offres=ADMIN)
    assert asyncio.run(SH.essai6_offres_gratuites(base2, PARTENAIRE)) == []

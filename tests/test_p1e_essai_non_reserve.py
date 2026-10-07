# -*- coding: utf-8 -*-
"""P1-e (07/10/2026) — essai gratuit accordé mais jamais réservé : relance +3 h, puis J+2.

Banc hors ligne sur les VRAIES fonctions (`p1e_etape`, `p1e_relance`, `p1e_passage`,
`p1e_candidats`, `p1e_mesure_pure`) avec une base en mémoire et des données TEST seulement.
Aucun e-mail : l'expéditeur est un compteur.

Lancer : python3 -m pytest tests/test_p1e_essai_non_reserve.py -q
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "secret-de-test-p1e")
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p1e-inexistant:27017")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import api.server as S
from api.routes import shared as SH

# 12/10/2026 10:00 Zurich (08:00 UTC) — dans la fenêtre 09-20 h, après la borne d'activation.
MAINTENANT = datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc)
ADMIN = S.SUPER_ADMIN_EMAILS[0]
LOCAL, DOMAINE = ADMIN.split("@")


# ───────────────── mini-Mongo : $or, $in, $exists, $gte, $lte, chemins pointés, tri ─────────────────
def _lire(doc, chemin):
    cur = doc
    for m in chemin.split("."):
        if not isinstance(cur, dict) or m not in cur:
            return False, None
        cur = cur[m]
    return True, cur


def _ok(doc, req):
    for cle, att in (req or {}).items():
        if cle == "$or":
            if not any(_ok(doc, s) for s in att):
                return False
            continue
        present, val = _lire(doc, cle)
        if isinstance(att, dict) and any(k.startswith("$") for k in att):
            for op, arg in att.items():
                if op == "$exists" and present != bool(arg):
                    return False
                if op == "$in" and val not in arg:
                    return False
                if op == "$gte" and not (present and val >= arg):
                    return False
                if op == "$lte" and not (present and val <= arg):
                    return False
        elif val != att:
            return False
    return True


def _poser(doc, chemin, v):
    m = chemin.split(".")
    cur = doc
    for x in m[:-1]:
        cur = cur.setdefault(x, {})
    cur[m[-1]] = v


class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, cle, sens=1):
        self.docs = sorted(self.docs, key=lambda d: d.get(cle) or "", reverse=sens < 0)
        return self

    async def to_list(self, n=None):
        return [dict(d) for d in (self.docs[:n] if n else self.docs)]


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, req=None, proj=None):
        return _Cur([d for d in self.docs if _ok(d, req)])

    async def find_one(self, req=None, proj=None):
        for d in self.docs:
            if _ok(d, req):
                return dict(d)
        return None

    async def update_one(self, req, maj, upsert=False):
        for d in self.docs:
            if _ok(d, req):
                for k, v in maj.get("$set", {}).items():
                    _poser(d, k, v)
                return type("R", (), {"matched_count": 1})()
        return type("R", (), {"matched_count": 0})()


class _Base:
    def __init__(self, forfaits=(), reservations=()):
        self.subscriptions = _Coll(forfaits)
        self.reservations = _Coll(reservations)

    def __getitem__(self, nom):
        return getattr(self, nom)


def essai(heures, rid="f1", code="AFR-TEST01", email=None, nom="Amina", **extra):
    f = {"id": rid, "code": code, "email": email or "amina.client@exemple-reel.ch", "name": nom,
         "offer_id": "offre-essai", "status": "active", "remaining_sessions": 1,
         "expires_at": (MAINTENANT + timedelta(days=60)).isoformat(),
         "created_at": (MAINTENANT - timedelta(hours=heures)).isoformat(), "coach_id": ADMIN}
    f.update(extra)
    return f


@pytest.fixture()
def env(monkeypatch):
    etat = {"envois": [], "reel": True, "test_controle": False, "achat": False, "base": _Base()}

    async def drapeaux():
        return {"P1E_ESSAI_NON_RESERVE_ENABLED": True, "P1E_ESSAI_NON_RESERVE_ENVOI_REEL": etat["reel"],
                "P1E_TEST_CONTROLE": etat["test_controle"]}

    async def est_essai(_db, forfait=None, code=""):
        return (forfait or {}).get("offer_id") == "offre-essai"

    async def achat(_f):
        return etat["achat"]

    async def autorise(_e):
        return True

    async def couleur(_c):
        return "#D91CD2"

    async def envoi(email, sujet, html, texte):
        etat["envois"].append((email, sujet, texte))
        return True

    monkeypatch.setattr(S, "get_feature_flags", drapeaux)
    monkeypatch.setattr(SH, "est_un_essai", est_essai)
    monkeypatch.setattr(S, "p1d_conversion_cours", achat)
    monkeypatch.setattr(S, "p1b_destinataire_autorise", autorise)
    monkeypatch.setattr(S, "_v259_primary_color", couleur)
    monkeypatch.setattr(S, "p1b_envoyer_email", envoi)

    def charger(forfaits=(), reservations=()):
        etat["base"] = _Base(forfaits, reservations)
        monkeypatch.setattr(S, "db", etat["base"])
        return etat["base"]

    etat["charger"] = charger
    charger()
    return etat


def relance(f, quand=MAINTENANT):
    return asyncio.run(S.p1e_relance(f, quand))


def doc(base, rid="f1"):
    return next(d for d in base.subscriptions.docs if d["id"] == rid)


# ═══════════ RÈGLES DE TEMPS (pure) ═══════════
def test_moins_de_3h_rien():
    assert S.p1e_etape(essai(2), MAINTENANT) == (None, "pas_encore")


def test_plus_de_3h_candidat_h3():
    assert S.p1e_etape(essai(4), MAINTENANT) == ("h3", "h3_du")


def test_j2_seulement_apres_h3_envoye():
    assert S.p1e_etape(essai(50), MAINTENANT) == (None, "pas_de_h3")
    f = essai(50, relances_essai={"h3": {"statut": "envoye", "at": "x"}})
    assert S.p1e_etape(f, MAINTENANT) == ("j2", "j2_du")
    f = essai(30, relances_essai={"h3": {"statut": "envoye", "at": "x"}})
    assert S.p1e_etape(f, MAINTENANT) == (None, "h3_deja_fait")


def test_sequence_close_et_fenetres_hautes():
    f = essai(60, relances_essai={"h3": {"statut": "envoye"}, "j2": {"statut": "envoye"}})
    assert S.p1e_etape(f, MAINTENANT) == (None, "sequence_close")
    assert S.p1e_etape(essai(24 * 8), MAINTENANT)[0] is None
    assert S.p1e_etape(essai(45), MAINTENANT) == (None, "h3_trop_tard")


def test_aucun_essai_anterieur_a_la_borne():
    vieux = essai(4)
    vieux["created_at"] = "2026-10-01T10:00:00+00:00"
    assert S.p1e_etape(vieux, datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)) == (None, "hors_borne")


# ═══════════ PARCOURS COMPLET ═══════════
def test_h3_envoye_une_seule_fois(env):
    base = env["charger"]([essai(4)])
    assert relance(doc(base)) == "envoye_h3"
    assert len(env["envois"]) == 1
    assert doc(base)["relances_essai"]["h3"]["statut"] == "envoye"
    assert relance(doc(base)) == "h3_deja_fait"             # passage suivant : aucun doublon
    assert relance(dict(essai(4))) == "deja_traitee"        # même forfait relu sans l'état : le jeton tient
    assert len(env["envois"]) == 1


def test_reservation_deja_faite_rien(env):
    env["charger"]([essai(4)], [{"promoCode": "AFR-TEST01", "createdAt": "2026-10-08T07:00:00+00:00"}])
    assert relance(essai(4)) == "deja_reserve" and env["envois"] == []


def test_achat_deja_fait_rien(env):
    env["charger"]([essai(4)])
    env["achat"] = True
    assert relance(essai(4)) == "deja_achete" and env["envois"] == []


def test_reservation_apres_h3_annule_j2(env):
    base = env["charger"]([essai(50, relances_essai={"h3": {"statut": "envoye", "at": "2026-10-10T09:00:00+00:00"}})],
                          [{"subscriptionId": "f1", "createdAt": "2026-10-10T12:00:00+00:00"}])
    assert relance(doc(base)) == "deja_reserve" and env["envois"] == []


def test_j2_si_toujours_rien(env):
    base = env["charger"]([essai(50, relances_essai={"h3": {"statut": "envoye", "at": "2026-10-06T09:00:00+00:00"}})])
    assert relance(doc(base)) == "envoye_j2"
    assert env["envois"][0][1] == "On te garde une place pour ton essai ?"
    assert relance(doc(base)) == "sequence_close" and len(env["envois"]) == 1


@pytest.mark.parametrize("modif,issue", [
    ({"status": "cancelled"}, "inactif"),
    ({"expires_at": "2026-10-01T00:00:00+00:00"}, "expire"),
    ({"remaining_sessions": 0}, "epuise"),
    ({"offer_id": "offre-payante"}, "pas_un_essai"),
])
def test_annule_expire_epuise_payant_rien(env, modif, issue):
    env["charger"]([essai(4, **modif)])
    assert relance(essai(4, **modif)) == issue and env["envois"] == []


def test_donnees_test_jamais_envoyees(env):
    for f in (essai(4, nom="TEST-J0-AFROBOOST"), essai(4, email="qa@example.com"),
              essai(4, email="%s+testj0n@%s" % (LOCAL, DOMAINE), nom="TEST-J0 NON RESERVE")):
        env["charger"]([f])
        assert relance(f) == "donnee_test"
    assert env["envois"] == []


def test_test_controle_n_ouvre_que_les_plus_adresses_du_super_admin(env):
    env["test_controle"] = True
    plus = essai(4, email="%s+testj0n@%s" % (LOCAL, DOMAINE), nom="TEST-J0 NON RESERVE")
    env["charger"]([plus])
    assert relance(plus) == "envoye_h3"
    autre = essai(4, rid="f2", code="AFR-TEST02", email="qa@example.com", nom="TEST")
    env["charger"]([autre])
    assert relance(autre) == "hors_test_controle"
    assert [e[0] for e in env["envois"]] == ["%s+testj0n@%s" % (LOCAL, DOMAINE)]


def test_mode_test_exclusif_aucun_vrai_client(env):
    """V579b : pendant le test contrôlé, un VRAI candidat parfaitement éligible ne reçoit RIEN."""
    env["test_controle"] = True
    vrai = essai(4, email="amina.client@exemple-reel.ch", nom="Amina")
    env["charger"]([vrai])
    assert relance(vrai) == "hors_test_controle" and env["envois"] == []
    env["test_controle"] = False
    assert relance(vrai) == "envoye_h3"                      # hors mode test : la règle normale


# ═══════════ ROUTES DE TEST (super-admin signé, mode test, plus-adresse) ═══════════
class _Req:
    def __init__(self, jeton=None, corps=None):
        self.headers = {"Authorization": "Bearer " + jeton} if jeton else {}
        self._c = corps or {}

    async def json(self):
        return dict(self._c)


def _jeton(email):
    import jwt as pyjwt
    return pyjwt.encode({"email": email}, os.environ["JWT_SECRET"], algorithm="HS256")


def _code_http(coro):
    from fastapi import HTTPException
    try:
        return asyncio.run(coro), None
    except HTTPException as e:
        return None, e.status_code


def test_antidater_triple_verrou(env):
    plus = essai(1, code="AFR-PLUS01", email="%s+testp1eh3@%s" % (LOCAL, DOMAINE), nom="TEST")
    vrai = essai(1, rid="f9", code="AFR-VRAI01", email="amina.client@exemple-reel.ch")
    base = env["charger"]([plus, vrai])
    corps = {"code": "AFR-PLUS01", "heures": 4}
    _r, c = _code_http(S.p1e_antidater_test(_Req(corps=corps)))
    assert c == 403                                            # sans jeton
    _r, c = _code_http(S.p1e_antidater_test(_Req(_jeton("coach@exemple.test"), corps)))
    assert c == 403                                            # jeton non super-admin
    _r, c = _code_http(S.p1e_antidater_test(_Req(_jeton(ADMIN), corps)))
    assert c == 403                                            # mode test inactif
    env["test_controle"] = True
    _r, c = _code_http(S.p1e_antidater_test(_Req(_jeton(ADMIN), {"code": "AFR-VRAI01", "heures": 4})))
    assert c == 403 and doc(base, "f9")["created_at"] == vrai["created_at"]   # jamais un vrai client
    r, c = _code_http(S.p1e_antidater_test(_Req(_jeton(ADMIN), corps)))
    assert c is None and r["ok"] is True and doc(base)["created_at"] != plus["created_at"]


def test_route_passage_super_admin_seulement(env):
    env["charger"]([])
    _r, c = _code_http(S.p1e_passage_route(_Req()))
    assert c == 403
    _r, c = _code_http(S.p1e_passage_route(_Req(_jeton("coach@exemple.test"))))
    assert c == 403
    r, c = _code_http(S.p1e_passage_route(_Req(_jeton(ADMIN))))
    assert c is None and "resume" in r


def test_simulation_rien_ecrit_rien_envoye(env):
    env["reel"] = False
    base = env["charger"]([essai(4)])
    assert relance(doc(base)) == "simulation_h3"
    assert env["envois"] == [] and "relances_essai" not in doc(base)


def test_nuit_reporte(env):
    env["charger"]([essai(4)])
    assert relance(essai(4), MAINTENANT.replace(hour=21)) == "hors_fenetre" and env["envois"] == []


def test_message_et_lien(env):
    base = env["charger"]([essai(4)])
    relance(doc(base))
    email, sujet, texte = env["envois"][0]
    assert sujet == "Ton cours d'essai Afroboost t'attend"
    assert "Amina," in texte and "Choisir ma séance : https://afroboost.com/espace/AFR-TEST01" in texte


# ═══════════ CANDIDATS ET PASSAGE ═══════════
def test_candidats_recents_tries_et_bornes(env):
    env["charger"]([essai(1, rid="trop-jeune", code="AFR-A"), essai(4, rid="bon", code="AFR-B"),
                    essai(24 * 9, rid="trop-vieux", code="AFR-C"),
                    essai(60, rid="clos", code="AFR-D", relances_essai={"j2": {"statut": "envoye"}})])
    ids = [f["id"] for f in asyncio.run(S.p1e_candidats(MAINTENANT))]
    assert ids == ["bon"]


def test_passage_decompte(env):
    env["charger"]([essai(4, rid="a", code="AFR-A"), essai(4, rid="b", code="AFR-B")],
                   [{"promoCode": "AFR-B", "createdAt": "2026-10-08T06:00:00+00:00"}])
    assert asyncio.run(S.p1e_passage(MAINTENANT)) == {"envoye_h3": 1, "deja_reserve": 1}


# ═══════════ TRACKING ═══════════
def test_mesure_du_funnel():
    forfaits = [
        essai(60, rid="a", code="AFR-A", relances_essai={"h3": {"statut": "envoye", "at": "2026-10-09T23:00:00+00:00"}}),
        essai(60, rid="b", code="AFR-B", relances_essai={"h3": {"statut": "envoye", "at": "2026-10-09T23:00:00+00:00"},
                                                         "j2": {"statut": "envoye", "at": "2026-10-11T21:00:00+00:00"}}),
        essai(60, rid="c", code="AFR-C", relances_essai={"h3": {"statut": "envoye", "at": "2026-10-09T23:00:00+00:00"},
                                                         "j2": {"statut": "envoye", "at": "2026-10-11T21:00:00+00:00"}}),
        essai(5, rid="d", code="AFR-D"),
        essai(1, rid="e", code="AFR-E"),
    ]
    resas = [{"promoCode": "AFR-A", "createdAt": "2026-10-10T10:00:00+00:00"},
             {"promoCode": "AFR-B", "createdAt": "2026-10-12T07:00:00+00:00"},
             {"promoCode": "AFR-E", "createdAt": "2026-10-12T07:30:00+00:00"}]
    m = S.p1e_mesure_pure(forfaits, resas, MAINTENANT)
    assert m["essais"] == 5
    assert m["h3_envoyes"] == 3 and m["j2_envoyes"] == 2
    assert m["reserves_apres_j2"] == 1                        # B
    assert m["sans_reservation"] == 2                         # C et D


# ═══════════ V579c : la borne ne gêne pas la preuve, et protège toujours les vrais clients ═══════════
def test_mode_test_ignore_la_borne_pour_un_essai_test_seulement(env):
    avant = datetime(2026, 10, 7, 8, 40, tzinfo=timezone.utc)             # avant la borne (12:00 UTC)
    plus = essai(4, email="%s+testp1eh3@%s" % (LOCAL, DOMAINE), nom="Testeur")
    plus["created_at"] = (avant - timedelta(hours=4)).isoformat()
    env["charger"]([plus])
    assert relance(plus, avant) == "hors_borne"                           # hors mode test : borne
    env["test_controle"] = True
    assert relance(plus, avant) == "envoye_h3"                            # mode test : la preuve passe
    vrai = essai(4, rid="f9", code="AFR-VRAI09")
    vrai["created_at"] = (avant - timedelta(hours=4)).isoformat()
    env["charger"]([vrai])
    assert relance(vrai, avant) == "hors_test_controle"                   # et jamais un vrai client


def test_candidats_mode_test_chargent_avant_la_borne(env):
    avant = datetime(2026, 10, 7, 8, 40, tzinfo=timezone.utc)
    f = essai(4, rid="t", code="AFR-T")
    f["created_at"] = (avant - timedelta(hours=50)).isoformat()
    env["charger"]([f])
    assert asyncio.run(S.p1e_candidats(avant)) == []
    assert [x["id"] for x in asyncio.run(S.p1e_candidats(avant, True))] == ["t"]

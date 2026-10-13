#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618c — LES TROIS DETTES DE SÉCURITÉ FERMÉES AVANT LA MIGRATION.

  1. Annulation depuis l'espace : session d'espace OBLIGATOIRE, réservation de CETTE session.
  2. Garde OTP : fiche canonique, jamais historique, jamais d'un autre titulaire ni coach.
  3. /discount-codes/validate : plus aucune adresse arbitraire attachée à un code.

Banc permanent, sans réseau, données SYNTHÉTIQUES : vraies routes de `api/server.py` et de
`api/routes/promo_routes.py`, jeton d'espace réellement signé, base en mémoire.

Lancement : python3 tests/test_v618c_securite.py
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_pass_duo as H  # noqa: E402  (pose l'environnement : JWT_SECRET de banc, api.server)

S = H.S
import api.routes.abonnement_actuel as AA  # noqa: E402
import api.routes.promo_routes as PR  # noqa: E402
from api.routes import shared as SH  # noqa: E402

RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), detail))


FUTUR = "2027-05-05T23:59:59+00:00"
PASSE = "2026-09-01T23:59:59+00:00"
A, B, M1, M2 = "titulaire.a@t.example", "membre.b@t.example", "club.m1@t.example", "club.m2@t.example"
COACH_P = "coach.p@partenaire.example"
DANS_10_JOURS = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%dT18:30:00")


def sub(i, code, email, status="active", exp=FUTUR, total=10, used=3, coach="", source=None):
    d = {"id": i, "code": code, "email": email, "status": status, "expires_at": exp, "total_sessions": total,
         "used_sessions": used, "remaining_sessions": total - used, "created_at": "2026-01-01", "coach_id": coach}
    if source:
        d["source"] = source
    return d


def fiche(code, titulaire, exp="2027-05-05", coach="", **extra):
    d = {"code": code, "assignedEmail": titulaire, "active": True, "expiresAt": exp, "maxUses": 10, "used": 3,
         "coach_id": coach}
    d.update(extra)
    return d


def resa(i, code, email, sid=None, slug=None):
    d = {"id": i, "userEmail": email, "discountCode": code, "promoCode": code, "courseId": "c1",
         "courseName": "Afro", "datetime": DANS_10_JOURS, "quantity": 1}
    if sid:
        d["subscriptionId"] = sid
    if slug:
        d["member_slug"] = slug
    return d


def jeton(base, code, email, coach=None, slug=None, revoque=False):
    # Comme l'OTP réel : coach du code, sinon DEFAULT_COACH_ID (jamais vide).
    coach = coach or S.DEFAULT_COACH_ID
    _j, _jti = SH.lotb3s1_make_token(code, email, coach, slug)
    base[S._B3S1_COLL_SESSIONS].docs.append({
        "jti": _jti, "code": code, "email": email, "coach_id": coach, "slug": slug or "",
        "revoked": revoque, "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()})
    return _j


def req(tok=None):
    return H.Requete({}, {"x-espace-token": tok} if tok else {})


def monde():
    base = H._Base()
    base["subscriptions"].docs += [
        sub("sa", "AFR-A1", A), sub("sh", "AFR-A1", A, status="superseded", exp=PASSE, used=5),
        sub("sb", "AFR-B1", B), sub("sc", "CLUB-9", A, used=2),
    ]
    base["discount_codes"].docs += [
        fiche("AFR-A1", A), fiche("AFR-B1", B), fiche("CLUB-9", A, multi_member=True, shared_sessions=True),
    ]
    base["code_members"].docs += [{"code": "CLUB-9", "slug": "m1", "email": M1, "name": "M1"},
                                  {"code": "CLUB-9", "slug": "m2", "email": M2, "name": "M2"}]
    base["reservations"].docs += [
        resa("r1", "AFR-A1", A, sid="sa"), resa("r2", "AFR-B1", B, sid="sb"),
        resa("r3", "AFR-A1", A, sid="sh"), resa("rm1", "CLUB-9", M1, slug="m1"),
        resa("rm2", "CLUB-9", M2, slug="m2"),
    ]
    S.db = base
    return base


def existe(base, rid):
    return any(r.get("id") == rid for r in base["reservations"].docs)


def le_sub(base, sid):
    return next(s for s in base["subscriptions"].docs if s["id"] == sid)


async def annuler(base, code, rid, tok=None):
    return await H.appel(S.cancel_reservation_from_space(code, rid, req(tok)))


async def principal():
    # ══ 1. ANNULATION DEPUIS L'ESPACE ═════════════════════════════════════════════
    base = monde()
    c, r = await annuler(base, "AFR-A1", "r1")
    verifier("A annulation SANS jeton -> refus neutre (404), réservation intacte",
             c == 404 and existe(base, "r1") and le_sub(base, "sa")["used_sessions"] == 3, (c, r))
    tok_b = jeton(base, "AFR-B1", B)
    c, _ = await annuler(base, "AFR-A1", "r1", tok_b)
    verifier("B jeton d'un AUTRE membre (autre code) sur l'URL de A -> refus", c == 404 and existe(base, "r1"))
    c, _ = await annuler(base, "AFR-B1", "r1", tok_b)
    verifier("B2 jeton de B, sur SON code, pour la réservation de A -> refus", c == 404 and existe(base, "r1"))
    tok_a = jeton(base, "AFR-A1", A)
    c, _ = await annuler(base, "AFR-A1", "r2", tok_a)
    verifier("C jeton de A pour une AUTRE réservation (celle de B) -> refus", c == 404 and existe(base, "r2"))
    c, _ = await annuler(base, "AFR-A1", "inexistante", tok_a)
    verifier("C2 réservation inconnue -> la même réponse neutre", c == 404)
    tok_rev = jeton(base, "AFR-A1", A, revoque=True)
    c, _ = await annuler(base, "AFR-A1", "r1", tok_rev)
    verifier("C3 session révoquée -> refus", c == 404 and existe(base, "r1"))
    tok_autre_coach = jeton(base, "AFR-A1", A, coach=COACH_P)
    c, _ = await annuler(base, "AFR-A1", "r1", tok_autre_coach)
    verifier("C4 jeton émis chez un AUTRE coach -> refus", c == 404 and existe(base, "r1"))
    c, r = await annuler(base, "AFR-A1", "r1", tok_a)
    verifier("C5 PREUVE DU CHEMIN LÉGITIME : son jeton, sa réservation -> 200, séance re-créditée",
             c == 200 and not existe(base, "r1") and le_sub(base, "sa")["used_sessions"] == 2
             and le_sub(base, "sa")["status"] == "active", (c, r))
    c, _ = await annuler(base, "AFR-A1", "r1", tok_a)
    verifier("C6 deuxième annulation de la même réservation -> rien n'est re-crédité deux fois",
             c == 404 and le_sub(base, "sa")["used_sessions"] == 2)
    c, r = await annuler(base, "AFR-A1", "r3", tok_a)
    verifier("C7 subscriptionId HISTORIQUE : exactement lui re-crédité, statut superseded JAMAIS réactivé",
             c == 200 and le_sub(base, "sh")["status"] == "superseded" and le_sub(base, "sh")["used_sessions"] == 4
             and le_sub(base, "sa")["used_sessions"] == 2, (c, r, le_sub(base, "sh")))

    # club / multi-membres
    tok_m1 = jeton(base, "CLUB-9", M1, slug="m1")
    c, _ = await annuler(base, "CLUB-9", "rm2", tok_m1)
    verifier("H club : un membre n'annule pas la réservation d'un autre membre", c == 404 and existe(base, "rm2"))
    c, r = await annuler(base, "CLUB-9", "rm1", tok_m1)
    verifier("H2 club : le membre annule SA réservation (multi-membres intact)", c == 200 and not existe(base, "rm1"), (c, r))

    # ══ 2. GARDE OTP ══════════════════════════════════════════════════════════════
    f_hist = fiche("DUO-1", "ancien@t.example", exp="2026-06-01")
    f_viv = fiche("DUO-1", "actuel@t.example")
    verifier("D OTP : une fiche HISTORIQUE n'est jamais retenue quand une fiche vivante existe",
             AA.contact_otp([f_hist, f_viv], [], "ancien@t.example")[0] == "actuel@t.example")
    base = monde()
    base["discount_codes"].docs += [f_hist, f_viv]
    em, _, _ = await S._b3s1_contact_enregistre("DUO-1", "", "ancien@t.example")
    verifier("D2 OTP (route réelle) : ancien titulaire d'une fiche historique -> jamais lui", em == "actuel@t.example")
    base["discount_codes"].docs += [fiche("DOUBLE", "p@t.example", coach=COACH_P), fiche("DOUBLE", "q@t.example")]
    em_p, cid_p, _ = await S._b3s1_contact_enregistre("DOUBLE", "", "p@t.example")
    em_z, _, _ = await S._b3s1_contact_enregistre("DOUBLE", "", "z@t.example")
    verifier("E OTP : même code chez DEUX coachs -> seule l'adresse qui désigne exactement une fiche (et SON coach)",
             em_p == "p@t.example" and cid_p == COACH_P and em_z is None, (em_p, cid_p, em_z))
    base["discount_codes"].docs.append({"code": "PROMO-X", "active": True, "expiresAt": "2027-01-01", "coach_id": ""})
    base["subscriptions"].docs.append(sub("px", "PROMO-X", "pirate@t.example", source="promo_validate"))
    em, _, _ = await S._b3s1_contact_enregistre("PROMO-X", "", "pirate@t.example")
    verifier("E2 OTP : jamais l'adresse d'un abonnement créé par la route publique /validate", em is None)
    base["discount_codes"].docs.append({"code": "SANS-TIT", "active": True, "expiresAt": "2027-01-01", "coach_id": ""})
    base["subscriptions"].docs += [sub("s1", "SANS-TIT", "un@t.example"), sub("s2", "SANS-TIT", "deux@t.example")]
    em_x, _, _ = await S._b3s1_contact_enregistre("SANS-TIT", "", "inconnu@t.example")
    em_1, _, _ = await S._b3s1_contact_enregistre("SANS-TIT", "", "un@t.example")
    verifier("E3 OTP : fiche sans titulaire et plusieurs adresses -> aucun choix arbitraire", em_x is None and em_1 == "un@t.example")
    em, _, sl = await S._b3s1_contact_enregistre("CLUB-9", "", M2)
    verifier("H3 OTP club : le membre s'identifie par SA propre adresse (slug du membre)", em == M2 and sl == "m2")
    em, _, _ = await S._b3s1_contact_enregistre("AFR-A1", "", A)
    verifier("H4 OTP titulaire unique : chemin d'avant intact", em == A)

    # ══ 3. /discount-codes/validate ═══════════════════════════════════════════════
    base = monde()
    PR._db = base
    base["discount_codes"].docs.append({"code": "BATCH-7", "active": True, "expiresAt": "2027-01-01", "type": "100%",
                                        "value": 100, "maxUses": 10, "used": 0, "coach_id": ""})
    r = await PR.validate_discount_code({"code": "BATCH-7", "email": "victime@t.example"})
    fb = next(f for f in base["discount_codes"].docs if f["code"] == "BATCH-7")
    verifier("F /validate + e-mail arbitraire sans identité : code valide MAIS aucune adresse attachée",
             r.get("valid") is True and not fb.get("assignedEmail"), r)
    verifier("F2 … et aucun abonnement créé, aucune fiche CRM modifiée",
             not any(s.get("email") == "victime@t.example" for s in base["subscriptions"].docs)
             and not any(p.get("email") == "victime@t.example" for p in base["chat_participants"].docs))
    r = await PR.validate_discount_code({"code": "BATCH-7", "email": "vi"})
    verifier("F3 vitrine (adresse à moitié tapée) : plus de verrouillage sur « vi »",
             not next(f for f in base["discount_codes"].docs if f["code"] == "BATCH-7").get("assignedEmail"))
    r = await PR.validate_discount_code({"code": "AFR-A1", "email": "pirate@t.example"})
    verifier("F4 code attribué à quelqu'un d'autre -> refusé", r.get("valid") is False)
    base["discount_codes"].docs.append(fiche("NEUF-1", "neuf@t.example"))
    r = await PR.validate_discount_code({"code": "NEUF-1", "email": "neuf@t.example"})
    nouveaux = [s for s in base["subscriptions"].docs if s.get("code") == "NEUF-1"]
    verifier("F5 titulaire désigné par le coach, code sans abonnement -> SON abonnement est créé (usage légitime)",
             r.get("valid") is True and len(nouveaux) == 1 and nouveaux[0]["source"] == "promo_validate_titulaire", nouveaux)
    await PR.validate_discount_code({"code": "NEUF-1", "email": "neuf@t.example"})
    verifier("F6 idempotent : jamais un second abonnement",
             len([s for s in base["subscriptions"].docs if s.get("code") == "NEUF-1"]) == 1)

    # G : faux conflit sur un autre membre
    r0 = await AA.resoudre_abonnement_actuel(base, B)
    _n0 = len(base["notifications"].docs)
    await PR.validate_discount_code({"code": "BATCH-7", "email": B})
    r1 = await AA.resoudre_abonnement_actuel(base, B)
    verifier("G impossible de provoquer un faux conflit sur un autre membre (/validate avec SON adresse)",
             r0["etat"] == r1["etat"] == "courant" and r1["abonnement"]["id"] == "sb" and len(base["notifications"].docs) == _n0)
    verifier("G2 aucune orientation de compte : son espace actuel reste le sien",
             await AA.code_cible_espace(base, B, "AFR-B1") is None)

    # ══ I / J : Stripe et création manuelle intacts ═══════════════════════════════
    base = monde()
    base["subscriptions"].docs += [sub("st-old", "OLD-S", "stripe@t.example", exp=PASSE),
                                   sub("st-new", "NEW-S", "stripe@t.example")]
    fermes = await SH.cloturer_anciens_forfaits(base, "stripe@t.example", "st-new")
    verifier("I Stripe : la clôture d'un renouvellement (appel sans restriction) est inchangée",
             fermes == ["st-old"] and le_sub(base, "st-old")["status"] == "superseded")
    promo = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "routes",
                              "promo_routes.py"), encoding="utf-8").read()
    verifier("J création manuelle coach : source admin_manual + coach_id + clôture limitée au coach",
             '"source": "admin_manual"' in promo and "ids_autorises=" in promo)
    srv = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api", "server.py"),
               encoding="utf-8").read()
    _annul = srv[srv.index("async def cancel_reservation_from_space("):]
    _annul = _annul[:_annul.index("\n@api_router")]
    verifier("K câblage : l'annulation exige la porte de session AVANT toute lecture de réservation",
             _annul.index("_b3s13_porteur_autorise") < _annul.index("db.reservations.find_one")
             and "reservation_de_la_session" in _annul and '"status": "active"' not in _annul)
    _val = promo[promo.index("async def validate_discount_code("):]
    _val = _val[:_val.index("\n@promo_router")]
    verifier("K2 câblage : /validate n'écrit plus jamais assignedEmail",
             '{"$set": {"assignedEmail"' not in _val and "update_one" not in _val.split("# Sync CRM")[0])


def main():
    asyncio.run(principal())
    _ok = 0
    for nom, ok, detail in RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:600])
        _ok += ok
    print("%d / %d verifications V618c au vert" % (_ok, len(RESULTATS)))
    sys.exit(0 if _ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

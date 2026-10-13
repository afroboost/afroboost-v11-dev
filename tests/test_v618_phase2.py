#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V618 PHASE 2 — toutes les routes passent par l'abonnement ACTUEL (résolveur canonique).

Banc permanent, sans réseau, données SYNTHÉTIQUES uniquement : annulation (espace + coach),
scan d'un ancien QR, réservation hors espace, /subscriptions/status, déduction, synchronisation,
validation, campagnes, ChatWidget, et les correctifs de sécurité F1 à F8 de la revue.

Lancement : python3 tests/test_v618_phase2.py
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_v607_invitation_evenement as V7  # noqa: E402  (pose l'environnement du banc)

T, H = V7.T, V7.H
verifier = H.verifier
import api.routes.abonnement_actuel as AA  # noqa: E402
import api.routes.promo_routes as PR  # noqa: E402
from api.routes.reactivation import est_droit_actif  # noqa: E402
from api.routes.shared import cloturer_anciens_forfaits  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lire(*chemin):
    return open(os.path.join(RACINE, *chemin), encoding="utf-8").read()


SERVEUR = lire("api", "server.py")
PROMO = lire("api", "routes", "promo_routes.py")
RESA = lire("api", "routes", "reservation_routes.py")
CHAT = lire("frontend", "src", "components", "ChatWidget.js")
MAINTENANT = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)
FUTUR = "2027-05-05T23:59:59+00:00"
PASSE = "2026-09-01T23:59:59+00:00"


def sub(i, code, email, status="active", exp=FUTUR, total=10, used=0, coach=None, source=None, offer="OFF-8M"):
    d = {"id": i, "code": code, "email": email, "status": status, "expires_at": exp, "offer_id": offer,
         "total_sessions": total, "used_sessions": used, "remaining_sessions": total - used, "created_at": "2026-01-01"}
    if coach is not None:
        d["coach_id"] = coach
    if source:
        d["source"] = source
    return d


def fiche(code, titulaire, exp="2027-05-05", coach=None):
    d = {"code": code, "assignedEmail": titulaire, "active": True, "expiresAt": exp, "maxUses": 10, "used": 0}
    if coach is not None:
        d["coach_id"] = coach
    return d


def bloc(texte, debut, fin):
    _a = texte.index(debut)
    return texte[_a:texte.index(fin, _a + len(debut))]


class _Req:
    def __init__(self):
        self.headers = {}
        self.cookies = {}
        self.query_params = {}
        self.client = type("C", (), {"host": "127.0.0.1"})()


async def principal():
    base, _ = T.depart()
    for nom in ("subscriptions", "discount_codes", "notifications"):
        if nom not in base._c:
            base._c[nom] = H._Coll(nom, uniques=[])
    AA.init_db(base)
    S, F = base["subscriptions"].docs, base["discount_codes"].docs

    # ── C : ANNULATION — exactement l'abonnement de la réservation, jamais réactivé à tort ──
    hist = sub("h", "OLD-1", "a@t.example", status="superseded", exp=PASSE, used=3)
    cour = sub("c", "OLD-1", "a@t.example")
    verifier("C-1 annulation : subscriptionId -> EXACTEMENT cet abonnement (même historique)",
             AA.cible_restitution({"subscriptionId": "h"}, [cour, hist], MAINTENANT) is hist)
    verifier("C-2 subscriptionId introuvable -> AUCUN abonnement crédité (jamais un autre)",
             AA.cible_restitution({"subscriptionId": "zzz"}, [cour, hist], MAINTENANT) is None)
    verifier("C-3 sans subscriptionId -> l'UNIQUE abonnement actuel du code",
             AA.cible_restitution({}, [hist, cour], MAINTENANT) is cour)
    verifier("C-4 sans subscriptionId et deux actuels -> aucun (fail closed)",
             AA.cible_restitution({}, [cour, dict(cour, id="c2")], MAINTENANT) is None)
    verifier("C-5 sans subscriptionId, rien d'actuel -> aucun (fiche du code seule)",
             AA.cible_restitution({}, [hist], MAINTENANT) is None)
    verifier("C-6 restitution : un `completed` dans ses dates se rouvre en active",
             AA.statut_apres_restitution({"status": "completed", "expires_at": FUTUR}, MAINTENANT) == "active")
    verifier("C-7 restitution : superseded / expired / cancelled / archived JAMAIS réactivés",
             all(AA.statut_apres_restitution({"status": st, "expires_at": FUTUR}, MAINTENANT) is None
                 for st in ("superseded", "expired", "cancelled", "archived")))
    verifier("C-8 restitution : un `completed` EXPIRÉ reste completed",
             AA.statut_apres_restitution({"status": "completed", "expires_at": PASSE}, MAINTENANT) is None)
    esp = bloc(SERVEUR, "async def cancel_reservation_from_space(", "\n@api_router")
    verifier("C-9 annulation espace : plus de `\"status\": \"active\"` forcé, cible = cible_restitution",
             '"status": "active"' not in esp and "cible_restitution" in esp and "statut_apres_restitution" in esp)
    dele = bloc(RESA, "async def delete_reservation(", "\n@")
    verifier("C-10 annulation coach : repli « par e-mail seul » (V216) supprimé ; plus de completed->active forcé",
             "Fallback ultime" not in dele and '_b3_maj["$set"]["status"] = "active"' not in dele
             and "cible_restitution" in dele)

    # ── B : SCAN À LA PORTE d'un ANCIEN QR ───────────────────────────────────────
    Q = "porte@t.example"
    S += [sub("q-old", "Q-OLD", Q, exp=PASSE), sub("q-new", "Q-NEW", Q, total=64, used=15)]
    F += [fiche("Q-OLD", Q, exp="2026-09-01"), fiche("Q-NEW", Q)]
    b = await AA.bascule_scan(base, S[-2])
    verifier("B-1 ancien QR (titulaire) + nouvel abonnement actuel -> validé sur l'ACTUEL (Q-NEW, 49 restantes)",
             b is not None and b[0] == "Q-NEW" and b[1]["remaining_sessions"] == 49, b)
    verifier("B-2 QR de l'abonnement actuel -> aucune bascule", await AA.bascule_scan(base, S[-1]) is None)
    Z = "pas.titulaire@t.example"
    S += [sub("z-old", "Z-OLD", Z, exp=PASSE), sub("z-new", "Z-NEW", Z)]
    F += [fiche("Z-OLD", "quelquun.dautre@t.example", exp="2026-09-01"), fiche("Z-NEW", Z)]
    verifier("B-3 assignedEmail ≠ subscription.email sur le code scanné -> aucune bascule",
             await AA.bascule_scan(base, S[-2]) is None)
    W = "nouveau.pas.titulaire@t.example"
    S += [sub("w-old", "W-OLD", W, exp=PASSE), sub("w-new", "W-NEW", W)]
    F += [fiche("W-OLD", W, exp="2026-09-01"), fiche("W-NEW", "autre@t.example")]
    verifier("B-4 nouveau code dont la personne n'est pas titulaire -> aucune bascule",
             await AA.bascule_scan(base, S[-2]) is None)
    P = "coach.b@partenaire.example"
    X = "deux.coachs@t.example"
    S += [sub("x-old", "X-OLD", X, exp=PASSE), sub("x-b", "X-B", X, coach=P)]
    F += [fiche("X-OLD", X, exp="2026-09-01"), fiche("X-B", X, coach=P)]
    verifier("B-5 deux coachs, même adresse : un ancien QR de la plateforme ne bascule JAMAIS chez le coach B",
             await AA.bascule_scan(base, S[-2]) is None)
    K = "conflit.porte@t.example"
    S += [sub("k-old", "K-OLD", K, exp=PASSE), sub("k1", "K-1", K), sub("k2", "K-2", K)]
    F += [fiche("K-OLD", K, exp="2026-09-01"), fiche("K-1", K), fiche("K-2", K)]
    verifier("B-6 multi-actifs -> aucune bascule (fail closed)", await AA.bascule_scan(base, S[-3]) is None)
    scan = bloc(RESA, "async def _qr_scan_validate_inner(", "\nasync def ")
    verifier("B-7 câblage : le scan bascule après lire_abonnement_par_code, jamais pour un membre (CODE::SLUG)",
             "bascule_scan" in scan and "if subscription and not member_slug_from_qr" in scan)
    vuac = bloc(RESA, "async def _validate_user_access_code(", "\nasync def ")
    verifier("B-8 validation par compte (CAS D) : résolveur dans le périmètre du scanneur, plus de find_one({email, active})",
             "_v618_res(db, user_email, perimetre=" in vuac and '"status": "active"}, scanneur)' not in vuac)

    # ── A : RÉSERVATION HORS ESPACE (vitrine / chat) ────────────────────────────
    ok, msg = await AA.garde_abonnement_actuel(base, S[S.index(next(s for s in S if s["id"] == "q-old"))])
    verifier("A-1 ancien code avec un abonnement actuel différent -> refus explicite", not ok and msg == AA.MSG_ANCIEN_CODE)
    ok, _ = await AA.garde_abonnement_actuel(base, next(s for s in S if s["id"] == "q-new"))
    verifier("A-2 abonnement actuel -> accepté", ok)
    ok, _ = await AA.garde_abonnement_actuel(base, next(s for s in S if s["id"] == "k1"))
    verifier("A-3 conflit : le code présenté par la personne, s'il est actuel, reste accepté", ok)
    ok, _ = await AA.garde_abonnement_actuel(base, next(s for s in S if s["id"] == "k-old"))
    verifier("A-4 conflit : un ancien code est refusé", not ok)
    V = "seul@t.example"
    S.append(sub("v-exp", "V-EXP", V, exp=PASSE))
    ok, _ = await AA.garde_abonnement_actuel(base, S[-1])
    verifier("A-5 aucun abonnement actuel -> la règle existante (forfait_utilisable) décide seule", ok)
    cr = bloc(RESA, "async def create_reservation(", "\n@")
    verifier("A-6 câblage vitrine : garde sur le TITULAIRE de l'abonnement (multi-membres préservés)",
             "await _v618_garde(db, subscription)" in cr)
    rs = bloc(SERVEUR, "async def reserve_course_from_space(", "\n@api_router")
    verifier("A-7 câblage espace : même garde (titulaire de l'abonnement)", "garde_abonnement_actuel" in rs and "_v618_garde(db, subscription)" in rs)

    # ── F3 : abonnements créés par /validate (public) ─────────────────────────────
    U = "victime@t.example"
    S += [sub("u-ok", "U-OK", U), sub("u-auto", "U-AUTO", U, source="promo_validate")]
    F += [fiche("U-OK", U), fiche("U-AUTO", U)]
    r = await AA.resoudre_abonnement_actuel(base, U, MAINTENANT)
    verifier("F3-1 un abonnement auto-créé par /validate ne crée NI conflit NI orientation de compte",
             r["etat"] == "courant" and r["abonnement"]["id"] == "u-ok")
    ok, _ = await AA.garde_abonnement_actuel(base, S[-1])
    verifier("F3-2 il reste utilisable sur son propre code (garde neutre)", ok)
    val = bloc(PROMO, "async def validate_discount_code(", "\n@promo_router")
    verifier("F3-3 /validate : abonnement seulement pour le titulaire désigné (marqué) ; ancien code refusé",
             '"source": "promo_validate_titulaire"' in val and "MSG_ANCIEN_CODE" in val)

    # ── F1 : périmètre via la fiche quand l'abonnement n'a pas de coach_id ────────────
    Y = "manuel@t.example"
    S += [sub("y-plat", "Y-PLAT", Y), sub("y-b", "Y-B", Y)]           # aucun coach_id sur les abonnements
    F += [fiche("Y-PLAT", Y), fiche("Y-B", Y, coach=P)]
    r = await AA.resoudre_abonnement_actuel(base, Y, MAINTENANT, perimetre=AA.PLATEFORME)
    rb = await AA.resoudre_abonnement_actuel(base, Y, MAINTENANT, perimetre=AA.locataire(P))
    verifier("F1-1 abonnements manuels sans coach_id : périmètre lu sur la fiche (un actuel chez chaque coach)",
             r["etat"] == "courant" and r["abonnement"]["id"] == "y-plat" and rb["etat"] == "courant" and rb["abonnement"]["id"] == "y-b")
    verifier("F1-2 création manuelle : coach_id + source écrits sur l'abonnement",
             '"source": "admin_manual"' in PROMO and '"coach_id": code_data.get("coach_id") or ""' in PROMO)

    # ── F2 : la clôture ne touche que le périmètre du coach qui crée ─────────────────
    G = "renouv2@t.example"
    S += [sub("g-plat", "G-PLAT", G, exp=PASSE), sub("g-b", "G-B", G, coach=P, exp=PASSE), sub("g-new", "G-NEW", G)]
    fermes = await cloturer_anciens_forfaits(base, G, "g-new", log_prefix="V618", ids_autorises={"g-plat"})
    verifier("F2-1 renouvellement : seul l'ancien abonnement DU MÊME coach passe en historique",
             fermes == ["g-plat"] and next(s for s in S if s["id"] == "g-b")["status"] == "active"
             and next(s for s in S if s["id"] == "g-plat")["status"] == "superseded", fermes)
    verifier("F2-2 compteurs intacts après clôture",
             next(s for s in S if s["id"] == "g-plat")["used_sessions"] == 0)

    # ── F5 / F7 / F8 : lien d'accès et redirection d'espace ─────────────────────────
    acc = await AA.fiches_pour_acces(base, Z, MAINTENANT)
    verifier("F5 e-mail d'accès : jamais une fiche dont l'adresse n'est pas titulaire",
             all(str(f.get("assignedEmail") or "").lower() == Z for f in acc["fiches"]))
    verifier("F7 redirection : session d'un autre coach -> aucune redirection",
             await AA.code_cible_espace(base, Q, "Q-OLD", coach_session=P) is None)
    verifier("F7-b redirection : session du bon coach -> espace actuel",
             (await AA.code_cible_espace(base, Q, "Q-OLD", coach_session="")) == {"code": "Q-NEW", "coach_id": ""})
    verifier("F8 deux coachs : l'espace plateforme ne renvoie jamais vers le coach B",
             await AA.code_cible_espace(base, X, "X-OLD", coach_session="") is None)
    gss = bloc(SERVEUR, "async def get_subscriber_space(", "V201: Log pour diagnostic")
    verifier("F4 redirection : la session de l'ANCIEN code est révoquée",
             "v618_remplacee_par_espace_actuel" in gss and "coach_session=" in gss)
    v400 = SERVEUR[SERVEUR.index("resoudre_abonnement_actuel(db, _email, perimetre=_v618.PLATEFORME)") - 400:
                   SERVEUR.index("resoudre_abonnement_actuel(db, _email, perimetre=_v618.PLATEFORME)") + 1500]
    verifier("F6 rappel Stripe V400 : périmètre plateforme + titulaire, plus de repli find_one",
             "assignedEmail" in v400)

    # ── F : /subscriptions/status — le serveur désigne l'abonnement actuel ───────────
    PR._db = base
    _coach = _Req()
    _coach.headers = {"Authorization": "Bearer " + H.jeton_admin()}      # V618i : l'historique exige une preuve
    r = await PR.get_subscription_status(_coach, email=Q)
    verifier("F-1 status : current_subscription = l'actuel (Q-NEW), ancien en history",
             r["success"] and r["current_subscription"]["id"] == "q-new" and r["subscription"]["id"] == "q-new"
             and r["integrity_conflict"] is False and [h["id"] for h in r["history"]] == ["q-old"], r)
    _anon = await PR.get_subscription_status(_Req(), email=Q)
    verifier("F-1b sans preuve d'identité : ni historique ni nom (V618i anti-fuite)",
             _anon.get("history") == [] and all("name" not in x for x in _anon.get("subscriptions") or []), _anon)
    r = await PR.get_subscription_status(_Req(), email=K)
    verifier("F-2 status en conflit : integrity_conflict, AUCUN current_subscription",
             r["integrity_conflict"] is True and r.get("current_subscription") is None and r.get("subscription") is None, r)
    r = await PR.get_subscription_status(_Req(), code="Q-OLD")
    verifier("F-3 status par ANCIEN code : il n'est plus présenté comme actuel", not r.get("current_subscription"), r)
    M1, M2 = "membre1@t.example", "membre2@t.example"
    S += [sub("m1", "CLUB-9", M1), sub("m2", "CLUB-9", M2, exp=PASSE)]
    F += [fiche("CLUB-9", M1)]
    r = await PR.get_subscription_status(_Req(), code="CLUB-9")
    verifier("F-4 multi-membres : l'historique ne révèle JAMAIS l'abonnement d'un autre membre du code",
             all(h.get("email") == M1 for h in r.get("history") or []) and "membre2" not in str(r), r)
    r = await PR.get_subscription_status(_Req(), code="X-B")
    verifier("F-5 deux coachs : par code, résolu dans le périmètre du coach du code (pas de faux conflit)",
             r.get("current_subscription") and r["current_subscription"]["id"] == "x-b" and r["integrity_conflict"] is False, r)

    # ── E : ChatWidget — plus aucun choix dans le navigateur ─────────────────────────
    verifier("E-1 ChatWidget : plus de allSubs[0] ni actives[0] ; le serveur fournit current_subscription",
             "allSubs[0]" not in CHAT and "actives[0]" not in CHAT and CHAT.count("current_subscription") >= 2 and "r.data.integrity_conflict" in CHAT)

    # ── G : DÉDUCTION / H : SYNCHRONISATION ──────────────────────────────────────────
    ded = bloc(PROMO, "async def deduct_session(", "\n@promo_router")
    verifier("G-1 déduction : résolveur (propriété vérifiée ensuite, 403), conflit sans code -> refus",
             "resoudre_abonnement_actuel(" in ded and "integrity_conflict" in ded
             and '{"email": email, "status": "active"}' not in ded)
    syn = bloc(PROMO, "async def sync_subscriptions_for_email(", "\n@promo_router")
    verifier("H-1 synchronisation : code expiré ignoré ; jamais un 2e abonnement pour un code (tout statut)",
             "_v618_expire(code.get(\"expiresAt\"))" in syn and '"status": "active"}' not in syn)

    # ── I : CAMPAGNES ─────────────────────────────────────────────────────────────────
    verifier("I-1 campagne : un abonnement « active » EXPIRÉ n'est plus un droit actif",
             not est_droit_actif({"status": "active", "expires_at": PASSE, "total_sessions": 10, "used_sessions": 0,
                                  "remaining_sessions": 10}, MAINTENANT))
    verifier("I-2 campagne : l'abonnement actuel reste un droit actif",
             est_droit_actif({"status": "active", "expires_at": FUTUR, "total_sessions": 10, "used_sessions": 0,
                              "remaining_sessions": 10}, MAINTENANT))
    ab = bloc(SERVEUR, "async def _v346_emails_abonnes(", "\nasync def ")
    verifier("I-3 liste « abonnés » : abonnements actuels + fiches non expirées seulement",
             "_v618_courant(sub)" in ab and "_v618_exp(dc.get(\"expiresAt\"))" in ab)

    # ── J : autres points ────────────────────────────────────────────────────────────
    res = bloc(SERVEUR, "async def _v261_resolve_subscriber(", "\nasync def ")
    verifier("J-1 identité abonné (publier, jeton d'appareil) : un abonnement historique ou expiré n'ouvre plus de droits",
             "_v618_hist" in res and "_v618_expire(sub)" in res)
    chk = bloc(SERVEUR, "async def check_subscriber_exists(", "\n@api_router")
    verifier("J-2 /subscriber/check : même règle que l'e-mail d'accès (fiche expirée = pas abonné)",
             "fiches_pour_acces" in chk and '{"assignedEmail": email, "active": True}' not in chk)
    chk2 = bloc(SERVEUR, "async def subscriber_stripe_checkout(", "\n@api_router")
    verifier("J-3 recharge : offre de l'abonnement ACTUEL du code (plus de find_one sans tri)", "_v618_choisir" in chk2)
    verifier("J-4 rappels de séance : seuls les abonnements actuels", "if not _v618_courant(_a, now):" in SERVEUR)

    lien = bloc(SERVEUR, "async def get_space_link_by_email(", "\n@api_router")
    verifier("J-5 lien d'espace coach : sans abonnement actuel, le PLUS RÉCENT (plus de find_one status active)",
             '"status": "active", **_mt2_portee}' not in lien and "_fiche_du_code" in lien)
    enr = bloc(RESA, "async def _scan_enrichir(", "\nasync def ")
    verifier("J-6 scan : libellé de l'abonnement retenu (règle V391), plus le premier document",
             "_v618_lire(db, _code)" in enr)

    # ── superseded / expired / renouvellement (rappel de la règle) ──────────────────────
    verifier("R-1 superseded / expired jamais actuels",
             not AA.est_courant({"status": "superseded", "expires_at": FUTUR}, MAINTENANT)
             and not AA.est_courant({"status": "active", "expires_at": PASSE}, MAINTENANT))


def main():
    asyncio.run(principal())
    _res = [r for r in H.RESULTATS if re.match(r"^([A-JR]-\d|F\d)", r[0])]
    _ok = 0
    for nom, ok, detail in _res:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:600])
        _ok += ok
    print("%d / %d verifications V618 phase 2 au vert" % (_ok, len(_res)))
    sys.exit(0 if _ok == len(_res) else 1)


if __name__ == "__main__":
    main()

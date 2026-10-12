#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V607 — Invitations : lien court, OG par type, boule de neige des ÉVÉNEMENTS, suivi honnête.

Exécute les VRAIES routes (`share_invite_routes`, `invitation_relais`,
`invitation_suivi`, `referral_campaigns_routes`) sur la base en mémoire des
bancs INV-1. AUCUN réseau, AUCUN e-mail, AUCUN paiement : le webhook Stripe est
simulé par l'objet session qu'il recevrait.

Lancement :  python3 tests/test_v607_invitation_evenement.py
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_referral_campaigns as T  # noqa: E402  (pose l'environnement INV-1, n'exécute rien à l'import ?)

H = T.H
verifier, appel = H.verifier, H.appel
import api.routes.referral_campaigns_engine as IC  # noqa: E402
import api.routes.share_invite_routes as SI  # noqa: E402
import api.routes.invitation_relais as RL  # noqa: E402
import api.routes.invitation_suivi as SV  # noqa: E402

UA_ROBOT = "WhatsApp/2.23.20.0 A"
UA_NAV = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"


class _Ent(dict):
    def get(self, k, d=None):
        return super().get(k.lower(), d)


class _Rq:
    def __init__(self, corps=None, ua=""):
        self._c = corps or {}
        self.headers = _Ent({"user-agent": ua})
        self.client = type("C", (), {"host": "10.0.0.1"})()

    async def json(self):
        return self._c


class _Session(dict):
    def __getattr__(self, k):
        return self.get(k)


def session(cs, jeton, email, nom, montant_cts=2500, offre=None):
    return _Session(id=cs, payment_status="paid", amount_total=montant_cts, currency="chf",
                    payment_intent="pi_" + cs, customer_details={"email": email, "name": nom},
                    metadata={"invitation_token": jeton, "offer_id": offre or T.OFFRE_A_PAYANTE,
                              "customer_name": nom})


async def principal():
    base, occ = T.depart()
    base._c["invitation_relais"] = H._Coll("invitation_relais", uniques=[(("jeton",), None), (("preuve_cle",), None)])
    base._c["invitation_events"] = H._Coll("invitation_events", uniques=[(("cle",), None)])
    for m in (SI, RL, SV):
        m.init_db(base)

    # ── A. Événement payant actif : lien court + OG ─────────────────────────
    c, ev = await T.creer(T.COACH_A, {"type": "event_paid", "status": "active", "offer_id": T.OFFRE_A_PAYANTE,
                                      "occurrence": occ, "title": "Soirée Festival"})
    verifier("A1 event_paid actif (offre billet, lieu de l'offre) -> 201", c == 201 and ev.get("status") == "active", (c, ev))
    verifier("A2 share_url = lien COURT /i/<jeton> (sans /api/)", "/i/" + ev["share_token"] in ev["share_url"]
             and "/api/" not in ev["share_url"], ev.get("share_url"))
    tok = ev["share_token"]
    r = await SI.lien_court(tok, _Rq(ua=UA_ROBOT), v="1")
    h = r.body.decode("utf-8")
    verifier("A3 /i/<jeton> robot : og:title = titre de l'événement (pas la home)",
             "Soirée Festival" in h and "Fitness Immersif" not in h, h[:400])
    verifier("A4 og:description : date · heure · lieu · prix actif", "Salle Événement" in h and "25 CHF" in h, h[:900])
    verifier("A5 og:image = carte de l'invitation", "/api/share/invite/%s/carte.jpg" % tok in h)
    r404 = await SI.lien_court("jetonInventeXXXXXXXXXXXX", _Rq(ua=UA_ROBOT))
    verifier("A6 jeton inventé -> 404 neutre", r404.status_code == 404)
    pub = await SI.invitation_publique(tok)
    verifier("A7 API publique : cible vitrine + inv=<jeton> (jamais ref=)", isinstance(pub, dict)
             and ("inv=" + tok) in pub.get("cible", "") and "ref=" not in pub.get("cible", ""), pub)
    verifier("A8 API publique : aucune PII (coach_id, e-mail)", T.COACH_A not in str(pub) and "coach_id" not in pub)
    verifier("A9 prix actif = celui du checkout (compute_active_price)", (pub.get("prix_actif") or {}).get("prix") == 25.0)

    # ── B. Boule de neige : Coach -> A -> B -> C (paiements simulés) ─────────
    a = await RL.relais_depuis_paiement_stripe(base, session("cs_test_A1", tok, "a@test.example", "Alice Test"))
    verifier("B1 A paie via le lien du coach -> relais génération 1, parent = coach",
             a and a["generation"] == 1 and a["parent_relais_id"] is None and a["parent_jeton"] == tok, a)
    b = await RL.relais_depuis_paiement_stripe(base, session("cs_test_B1", a["jeton"], "b@test.example", "Bob Test"))
    verifier("B2 B paie via le lien de A -> génération 2, invité par A",
             b and b["generation"] == 2 and b["parent_relais_id"] == a["id"], b)
    cc = await RL.relais_depuis_paiement_stripe(base, session("cs_test_C1", b["jeton"], "c@test.example", "Chloé Test"))
    verifier("B3 C paie via le lien de B -> génération 3, invitée par B",
             cc and cc["generation"] == 3 and cc["parent_relais_id"] == b["id"], cc)
    verifier("B4 prénom seul (jamais l'adresse)", cc["inviteur_prenom"] == "Chloé" and "@" not in str(cc.get("inviteur_prenom")))
    # Lien court d'un relais : C invite, carte/OG au nom de C
    rc = await SI.lien_court(cc["jeton"], _Rq(ua=UA_ROBOT))
    verifier("B5 /i/<jeton de C> : « Chloé t'invite : Soirée Festival »",
             rc.status_code == 200 and "Chloé t&#x27;invite" in rc.body.decode("utf-8"), rc.body.decode("utf-8")[:300])

    pc = await SI.invitation_publique(cc["jeton"])
    verifier("B6 page du relais : le mot personnel du COACH n'est pas repris au nom de Chloé",
             pc.get("message") is None and pc["inviter_display"]["prenom"] == "Chloé", pc.get("message"))

    # ── C. Anti-fraude ───────────────────────────────────────────────────────
    a_bis = await RL.relais_depuis_paiement_stripe(base, session("cs_test_A1", tok, "a@test.example", "Alice Test"))
    verifier("C1 webhook rejoué (même session) -> même relais, rien de neuf",
             a_bis["id"] == a["id"] and len(base["invitation_relais"].docs) == 3)
    boucle = await RL.relais_depuis_paiement_stripe(base, session("cs_test_A2", cc["jeton"], "a@test.example", "Alice"))
    verifier("C2 boucle A -> B -> C -> A : A garde son relais, inviteur INCHANGÉ",
             boucle["id"] == a["id"] and boucle["parent_relais_id"] is None and len(base["invitation_relais"].docs) == 3)
    auto = await RL.relais_depuis_paiement_stripe(base, session("cs_test_D1", cc["jeton"], "c@test.example", "Chloé"))
    verifier("C3 s'inviter soi-même (même e-mail) -> aucun 2e relais", auto["id"] == cc["id"] and len(base["invitation_relais"].docs) == 3)
    faux = await RL.relais_depuis_paiement_stripe(base, session("cs_test_E1", "jetonInventeXXXXXXXXXXXX", "e@test.example", "Eve"))
    verifier("C4 jeton inventé -> aucun relais", faux is None and len(base["invitation_relais"].docs) == 3)
    autre_offre = await RL.relais_depuis_paiement_stripe(base, session("cs_test_F1", tok, "f@test.example", "Fred", offre="autre"))
    verifier("C5 paiement d'une AUTRE offre avec le jeton -> aucun relais", autre_offre is None)
    impaye = _Session(session("cs_test_G1", tok, "g@test.example", "Gil"), payment_status="unpaid")
    verifier("C6 session non payée -> aucun relais", await RL.relais_depuis_paiement_stripe(base, impaye) is None)

    # ── D. Après paiement : lien personnel par session ───────────────────────
    c, d = await appel(RL.relais_par_session("cs_test_B1"))
    verifier("D1 GET relais/session/<cs> -> lien /i/<jeton de B>, prénom", c == 200 and d["share_url"].endswith("/i/" + b["jeton"])
             and d["prenom"] == "Bob" and "email" not in str(d).lower(), (c, d))
    c, _ = await appel(RL.relais_par_session("cs_inconnu_123456"))
    verifier("D2 session inconnue -> 404", c == 404)

    # ── E. Chaîne reconstruite (coach) ───────────────────────────────────────
    c, ch = await appel(RL.chaine_campagne(ev["id"], T.rq(T.COACH_A)))
    _g = {n["prenom"]: (n["generation"], n["invite_par"]) for n in (ch or {}).get("noeuds", [])}
    verifier("E1 chaîne : Alice g1 (coach), Bob g2 (Alice), Chloé g3 (Bob)", c == 200 and _g == {
        "Alice": (1, "coach"), "Bob": (2, "Alice"), "Chloé": (3, "Bob")}, (c, _g))
    c, _ = await appel(RL.chaine_campagne(ev["id"], T.rq(T.COACH_B)))
    verifier("E2 un autre coach -> 404", c == 404)
    c, _ = await appel(RL.chaine_campagne(ev["id"], T.rq(None)))
    verifier("E3 sans jeton -> 401", c == 401)

    # ── F. Événement gratuit : inscription -> relais facultatif ─────────────
    c, ef = await T.creer(T.COACH_A, {"type": "event_free", "status": "active", "offer_id": T.OFFRE_A_ESSAI})
    base["reservations"].docs.append({"id": "res-1", "reservationCode": "AFR-TEST1", "offerId": T.OFFRE_A_ESSAI,
                                      "userName": "Nadia Test", "userEmail": "n@test.example",
                                      "createdAt": datetime.now(timezone.utc)})
    c, rf = await appel(RL.relais_par_reservation(_Rq({"jeton": ef["share_token"], "reservation_code": "AFR-TEST1"})))
    verifier("F1 event_free : réservation récente -> lien personnel g1", c == 200 and rf.get("generation") == 1, (c, rf))
    c, _ = await appel(RL.relais_par_reservation(_Rq({"jeton": ef["share_token"], "reservation_code": "AFR-INCONNU"})))
    verifier("F2 code de réservation inconnu -> 404", c == 404)
    c, _ = await appel(RL.relais_par_reservation(_Rq({"jeton": tok, "reservation_code": "AFR-TEST1"})))
    verifier("F3 jeton d'un événement PAYANT par réservation -> 404 (le paiement fait foi)", c == 404)
    base["subscriptions"].docs.append({"code": "AFR-INSCR1", "offer_id": T.OFFRE_A_ESSAI, "email": "p@test.example",
                                       "name": "Paul Test", "created_at": datetime.now(timezone.utc).isoformat()})
    c, ri = await appel(RL.relais_par_inscription(_Rq({"jeton": ef["share_token"], "code": "AFR-INSCR1"})))
    verifier("F5 event_free (parcours vitrine -> espace) : accès récent -> lien personnel g1", c == 200
             and ri.get("prenom") == "Paul" and ri.get("generation") == 1, (c, ri))
    base["subscriptions"].docs.append({"code": "AFR-VIEUX1", "offer_id": T.OFFRE_A_ESSAI, "email": "v@test.example",
                                       "name": "Vieux", "created_at": "2020-01-01T00:00:00+00:00"})
    c, _ = await appel(RL.relais_par_inscription(_Rq({"jeton": ef["share_token"], "code": "AFR-VIEUX1"})))
    verifier("F6 accès ancien (> 48 h) -> 404", c == 404)
    pubf = await SI.invitation_publique(ef["share_token"])
    verifier("F4 event_free : « Gratuit », aucun prix", pubf.get("mention_prix") == "Gratuit" and pubf.get("prix_actif") is None)

    # ── G. Suivi honnête ─────────────────────────────────────────────────────
    _ev = [d["evenement"] for d in base["invitation_events"].docs]
    verifier("G1 serveur : invitation_creee + lien_active + paiement_confirme + nouvelle_invitation_generee",
             {"invitation_creee", "lien_active", "paiement_confirme", "nouvelle_invitation_generee"} <= set(_ev), _ev)
    verifier("G2 rejeu webhook : paiement compté UNE fois (3 acheteurs)", _ev.count("paiement_confirme") == 3, _ev)
    for _ in range(2):
        await SV.suivi_client(_Rq({"jeton": tok, "evenement": "partage_whatsapp_declenche", "visiteur": "appareil1"}))
    await SV.suivi_client(_Rq({"jeton": tok, "evenement": "whatsapp_envoye", "visiteur": "appareil1"}))
    await SV.suivi_client(_Rq({"jeton": "jetonInventeXXXXXXXXXXXX", "evenement": "lien_ouvert", "visiteur": "x"}))
    _ev = [d["evenement"] for d in base["invitation_events"].docs]
    verifier("G3 partage déclenché compté une fois par appareil ; « whatsapp_envoye » refusé ; jeton inventé ignoré",
             _ev.count("partage_whatsapp_declenche") == 1 and "whatsapp_envoye" not in _ev and _ev.count("lien_ouvert") == 0, _ev)
    verifier("G4 aucun libellé « envoyé » dans le suivi", not any("envoy" in v.lower() for v in SV.LIBELLES.values()))
    c, f = await appel(SV.suivi_funnel(T.rq(T.COACH_A), type="event_paid"))
    verifier("G5 funnel événement payant : CA 75 CHF, 3 nouvelles invitations, générations 1/2/3+",
             c == 200 and f["ca"] == 75.0 and f["evenements"].get("nouvelle_invitation_generee") == 3
             and set(f["par_generation"]) >= {"1", "2", "3+"}, (c, f))
    c, f2 = await appel(SV.suivi_funnel(T.rq(T.COACH_B), type="event_paid"))
    verifier("G6 un autre coach ne voit rien", c == 200 and not f2["evenements"], f2)
    verifier("G7 chaque ligne porte le TYPE d'invitation", all(d.get("type_invitation") in SV.TYPES
                                                                for d in base["invitation_events"].docs))
    _j = str(base["invitation_events"].docs)
    verifier("G8 aucune donnée de participant dans le journal (ni e-mail, ni nom, ni jeton en clair)",
             not any(x in _j for x in ("a@test.example", "b@test.example", "Alice", "Bob", tok)), _j[:300])

    # ── H. Pass Duo / essai : intouchés par les relais ──────────────────────
    verifier("H1 aucun relais pour un Pass Duo / essai", await RL.resoudre_parent(base, (await T.creer(
        T.COACH_A, {"type": "trial"}))[1]["share_token"]) == (None, None))


def main():
    asyncio.run(principal())
    _ok = 0
    for nom, ok, detail in H.RESULTATS:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:500])
        _ok += ok
    print("%d / %d verifications V607 au vert" % (_ok, len(H.RESULTATS)))
    return 0 if _ok == len(H.RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V610p — e-mail d'accès : le lien ouvre l'ESPACE (jamais le ChatWidget), l'événement est
conservé, le QR ne porte jamais le jeton. Banc sans réseau ni donnée réelle.

Lancement : python3 tests/test_v610p_lien_acces.py
"""
import asyncio
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_v607_invitation_evenement as V7  # noqa: E402  (pose l'environnement du banc)

T, H, RL, SI = V7.T, V7.H, V7.RL, V7.SI
verifier, appel = H.verifier, H.appel
import api.routes.espace_lien_acces as L  # noqa: E402
import api.routes.ambassadeur_routes as AMB  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()


async def principal():
    base, occ = T.depart()
    for nom, u in (("invitation_relais", [(("jeton",), None), (("preuve_cle",), None)]), ("invitation_events", [(("cle",), None)]),
                   (L.COLL, []), ("referral_programs", [])):
        if nom not in base._c:
            base._c[nom] = H._Coll(nom, uniques=u)
    for m in (SI, RL, AMB):
        m.init_db(base)
    c, ev = await T.creer(T.COACH_A, {"type": "event_paid", "status": "active", "offer_id": T.OFFRE_A_PAYANTE,
                                      "occurrence": occ, "title": "AFROBOOST SILENT"})
    _, essai = await T.creer(T.COACH_A, {"type": "trial"})
    tok = ev["share_token"]

    # ── lien d'accès ────────────────────────────────────────────────────────
    j = await L.creer_lien(base, code="AFR-TEST01", email="Bassi@Test.Example", coach_id="c1")
    doc = base[L.COLL].docs[0]
    verifier("P-1 jeton aléatoire long, stocké HACHÉ seulement (jamais en clair)",
             len(j) >= 40 and doc["_id"] == L.empreinte(j) and j not in str(doc), doc)
    verifier("P-2 lié au code et à l'adresse (minuscules), 24 h", doc["code"] == "AFR-TEST01" and doc["email"] == "bassi@test.example"
             and doc["expires_at"] > (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat())
    ok = await L.consommer(base, "AFR-TEST01", j)
    verifier("P-3 bon code + bon jeton -> ouvre (1 ouverture comptée)", ok and base[L.COLL].docs[0]["ouvertures"] == 1)
    verifier("P-4 AUTRE code avec ce jeton -> refusé", await L.consommer(base, "AFR-AUTRE", j) is None)
    verifier("P-5 jeton inventé / mal formé -> refusé", await L.consommer(base, "AFR-TEST01", "x" * 43) is None
             and await L.consommer(base, "AFR-TEST01", "<script>") is None)
    for _ in range(4):
        await L.consommer(base, "AFR-TEST01", j)
    verifier("P-6 au-delà de 5 ouvertures -> refusé (bouton + QR + quelques rechargements)",
             await L.consommer(base, "AFR-TEST01", j) is None and base[L.COLL].docs[0]["ouvertures"] == 5)
    j2 = await L.creer_lien(base, code="AFR-TEST01", email="b@t.example", coach_id="c1")
    verifier("P-7 lien expiré (25 h plus tard) -> refusé",
             await L.consommer(base, "AFR-TEST01", j2, maintenant=datetime.now(timezone.utc) + timedelta(hours=25)) is None)

    # ── contexte événement ──────────────────────────────────────────────────
    verifier("E-1 invitation active + bonne offre -> contexte conservé",
             await L.contexte_evenement(base, T.OFFRE_A_PAYANTE, tok) == (T.OFFRE_A_PAYANTE, tok))
    verifier("E-2 offre qui n'est PAS celle de l'invitation -> rien (pas de redirection arbitraire)",
             await L.contexte_evenement(base, "OFFRE-AUTRE", tok) == ("", ""))
    verifier("E-3 invitation Essai gratuit -> rien (ce parcours est réservé aux événements)",
             await L.contexte_evenement(base, T.OFFRE_A_PAYANTE, essai["share_token"]) == ("", ""))
    verifier("E-4 valeurs mal formées -> rien", await L.contexte_evenement(base, "../../x", "javascript:x") == ("", ""))
    sophie = await RL.relais_depuis_paiement_stripe(base, V7.session("cs_test_SOPHIE9", tok, "sophie@test.example", "Sophie Test"))
    verifier("E-5 lien PERSONNEL d'un participant (relais) -> contexte conservé",
             await L.contexte_evenement(base, T.OFFRE_A_PAYANTE, sophie["jeton"]) == (T.OFFRE_A_PAYANTE, sophie["jeton"]))

    # ── URL, QR, e-mail ─────────────────────────────────────────────────────
    u = L.url_acces("https://afroboost.com", "AFR-TEST01", "JETONabc", T.OFFRE_A_PAYANTE, tok)
    verifier("U-1 lien = ESPACE /espace/<CODE>?acces=…&evt=…&inv=… (jamais /?qr=)",
             u.startswith("https://afroboost.com/espace/AFR-TEST01?acces=JETONabc&evt=") and "inv=" in u and "?qr=" not in u, u)
    qr = L.url_espace("https://afroboost.com", "AFR-TEST01", T.OFFRE_A_PAYANTE, tok)
    verifier("U-2 QR = l'espace et l'événement, SANS jeton d'accès (service externe)",
             qr.startswith("https://afroboost.com/espace/AFR-TEST01?evt=") and "acces" not in qr, qr)
    h = L.html_email(nom="<script>x</script>", code="AFR-TEST01", restantes=3, total=8, url=u, qr_url="https://qr/x?d=1&e=2")
    verifier("M-1 e-mail : titre, GROS bouton « ACCÉDER À MON ESPACE AFROBOOST » vers l'espace",
             "Accède à ton espace Afroboost" in h and "ACCÉDER À MON ESPACE AFROBOOST" in h
             and 'href="https://afroboost.com/espace/AFR-TEST01?acces=JETONabc&amp;evt=' in h)
    verifier("M-2 code visible, QR SECONDAIRE « Sur ordinateur ? Scanne… », bouton AVANT le QR",
             "AFR-TEST01" in h and "Sur ordinateur ? Scanne ce QR code avec ton téléphone." in h
             and h.index("ACCÉDER À MON ESPACE") < h.index("Sur ordinateur"))
    verifier("M-3 prénom échappé (aucun HTML injecté)", "<script>" not in h and "&lt;script&gt;" in h)
    verifier("M-4 aucun petit lien « ?qr= » comme action", "?qr=" not in h)

    # ── câblage serveur ────────────────────────────────────────────────────
    rec = SERVEUR[SERVEUR.index('@api_router.post("/subscriber/recover")'):]
    rec = rec[:rec.index("@api_router", 10)]
    verifier("S-1 /subscriber/recover : e-mail V610p, contexte vérifié, QR sans jeton",
             "_v610p.html_email(" in rec and "contexte_evenement(db, body.get(\"offre\"), body.get(\"jeton\"))" in rec
             and "url_espace(_front, code, _evt, _inv)" in rec and "afroboost.com/?qr=" not in rec)
    verifier("S-2 /subscriber/recover : le code n'est toujours PAS renvoyé à l'appelant (V389)",
             '"code": code' not in rec and "email_masked" in rec)
    lien = SERVEUR[SERVEUR.index('@api_router.post("/subscriber/acces/lien")'):]
    lien = lien[:lien.index("@api_router", 10)]
    verifier("S-3 /subscriber/acces/lien : MÊME session révocable que l'OTP (jeton B3-S1 + collection de sessions)",
             "lotb3s1_make_token(" in lien and "_B3S1_COLL_SESSIONS" in lien and '"revoked": False' in lien
             and "_v610p.consommer(" in lien and "status_code=400" in lien)

    # ── page publique : « 50 PLACES » ───────────────────────────────────────
    # V618L (Bassi, 13/10) : plus de faux compteur. Le message n'apparaît QUE si l'offre a une
    # capacité RÉELLE (stock ou max_participants > 0) ; sans capacité, aucune ligne de places.
    _offre = next(d for d in SI._base()["offers"].docs if d.get("id") == T.OFFRE_A_PAYANTE)
    _avant = (_offre.get("stock"), _offre.get("max_participants"))
    _offre.update(stock=-1, max_participants=None)
    pub = await SI.invitation_publique(tok)
    verifier("W-1 événement SANS capacité réelle : aucun « 50 PLACES » (V618L), aucune capacité inventée",
             not pub.get("message_places") and "places_restantes" not in pub, pub.get("message_places"))
    _offre.update(max_participants=50)
    pub = await SI.invitation_publique(tok)
    verifier("W-1b événement AVEC capacité réelle : le message du coach s'affiche",
             pub.get("message_places") == "50 PLACES" and "places_restantes" not in pub, pub.get("message_places"))
    _offre.update(stock=_avant[0], max_participants=_avant[1])
    pe = await SI.invitation_publique(essai["share_token"]) if essai.get("status") == "active" else {"message_places": None}
    verifier("W-2 essai gratuit : aucun message de places", not (pe or {}).get("message_places"))


def main():
    asyncio.run(principal())
    _res = [r for r in H.RESULTATS if re.match(r"^[PEUMSW]-\d", r[0])]
    _ok = 0
    for nom, ok, detail in _res:
        print(("  OK     " if ok else "  ECHEC  ") + nom)
        if not ok:
            print("         -> %s" % str(detail)[:500])
        _ok += ok
    print("%d / %d verifications V610p au vert" % (_ok, len(_res)))
    sys.exit(0 if _ok == len(_res) else 1)


if __name__ == "__main__":
    main()

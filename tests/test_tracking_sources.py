# -*- coding: utf-8 -*-
"""TRACKING 2B — SOURCE → ESSAI → RÉSERVATION → PRÉSENCE → ACHAT → OFFRE → REVENU → RENOUVELLEMENT.

Sans paiement réel : les règles pures (shared.py, analytics_shared.py) et des
documents synthétiques dans la forme exacte de la base. Scénarios A–G du GO.
"""
import asyncio, os, re, sys
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from api.routes import shared as S          # noqa: E402
from api.routes import analytics_shared as A  # noqa: E402

OK = RATE = 0


def verifier(nom, cond, detail=""):
    global OK, RATE
    if cond:
        OK += 1; print("  OK  ", nom)
    else:
        RATE += 1; print("  RATE", nom, ("  [%s]" % (detail,)) if detail != "" else "")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


# ═══ 1. LISTE FERMÉE PARTAGÉE + ?ref= ═══════════════════════════════════════
_js = open(os.path.join(RACINE, "frontend", "src", "utils", "attribution.js"), encoding="utf-8").read()
_m = re.search(r"export const SOURCES = \[(.*?)\];", _js, re.S)
_sources_js = tuple(re.findall(r"'([a-z_-]+)'", _m.group(1)))
verifier("1. La liste des sources est IDENTIQUE client / serveur", _sources_js == S.M2A_SOURCES, (_sources_js, S.M2A_SOURCES))
verifier("2. Anciennes sources conservées + email/newsletter/sms/qr/flyer/site",
         all(x in S.M2A_SOURCES for x in ("google", "instagram", "tiktok", "youtube", "facebook", "whatsapp", "partenaire", "direct",
                                            "email", "newsletter", "sms", "qr", "flyer", "site")))
verifier("3. Une source hors liste est toujours rejetée (jamais inventée)", S.m2a_source_normalisee("linkedin") == "" and S.m2a_source_normalisee("Email") == "email")

_ref = S.m2a_attribution_entrante({"ref": "Restaurant-X"}, "", "/")
verifier("4. ?ref=restaurant-x -> partenaire / referral / content=restaurant-x (slug nettoyé)",
         _ref and _ref["source"] == "partenaire" and _ref["medium"] == "referral" and _ref["content"] == "restaurant-x", _ref)
_utm = S.m2a_attribution_entrante({"utm_source": "instagram", "utm_medium": "reel", "utm_campaign": "hiver2026", "ref": "x"}, "", "/")
verifier("5. Les UTM explicites gagnent sur ?ref", _utm["source"] == "instagram" and _utm["medium"] == "reel" and _utm["campaign"] == "hiver2026")
verifier("6. ?ref= vide ou illisible -> rien (pas de partenaire fantôme)", S.m2a_attribution_entrante({"ref": "   "}, "", "/") is None
         and S.m2a_attribution_entrante({"ref": "https://evil"}, "", "/")["content"] == "httpsevil")
_p = S.m2a_attribution_entrante({"utm_source": "partenaire", "utm_medium": "referral", "utm_campaign": "essai_neuchatel", "utm_content": "coach_y"}, "", "/")
verifier("7. Les liens partenaires UTM existants (P2) fonctionnent toujours", _p["source"] == "partenaire" and _p["content"] == "coach_y")
_e = S.m2a_attribution_entrante({"utm_source": "email", "utm_medium": "newsletter", "utm_campaign": "lancement_hiver"}, "", "/")
verifier("F. utm_source=email conservé (medium newsletter, campagne lancement_hiver)", _e["source"] == "email" and _e["medium"] == "newsletter" and _e["campaign"] == "lancement_hiver")
_q = S.m2a_attribution_entrante({"utm_source": "qr", "utm_medium": "offline", "utm_campaign": "festival2026"}, "", "/")
verifier("E. utm_source=qr conservé", _q["source"] == "qr" and _q["campaign"] == "festival2026")

# ═══ 2. METADATA STRIPE : ALLER-RETOUR ═══════════════════════════════════════
BLOC = {"first": {"source": "instagram", "medium": "reel", "campaign": "hiver2026", "content": "", "term": "",
                  "landing_path": "/", "touch_at": "2026-09-01T10:00:00+00:00"},
        "last": {"source": "google", "medium": "organic", "campaign": "", "content": "", "term": "",
                 "landing_path": "/cours-essai-gratuit-neuchatel", "touch_at": "2026-09-03T10:00:00+00:00"}}
_meta = S.m2a_vers_metadata(BLOC)
verifier("8. Aplatissement metadata : clés plates attribution_first_* / attribution_last_*",
         _meta.get("attribution_first_source") == "instagram" and _meta.get("attribution_first_campaign") == "hiver2026"
         and _meta.get("attribution_last_source") == "google" and all(isinstance(v, str) for v in _meta.values()), _meta)
_retour = S.m2a_depuis_metadata({"product_name": "x", **_meta})
verifier("9. Relecture au webhook : first ET last reconstitués, touch_at d'origine conservé",
         _retour["first"]["source"] == "instagram" and _retour["first"]["touch_at"].startswith("2026-09-01")
         and _retour["last"]["source"] == "google", _retour)
verifier("10. Metadata sans attribution -> None ; bloc vide -> {} (fail-open)", S.m2a_depuis_metadata({"product_name": "x"}) is None and S.m2a_vers_metadata(None) == {})
verifier("11. Une source hors liste dans les metadata est rejetée", S.m2a_depuis_metadata({"attribution_first_source": "linkedin"}) is None)
verifier("12. m2a_bloc_propre conserve touch_at, remplace un touch_at illisible par maintenant",
         S.m2a_bloc_propre(BLOC)["first"]["touch_at"].startswith("2026-09-01")
         and S.m2a_bloc_propre({"first": {"source": "qr", "touch_at": "n'importe quoi"}})["first"]["touch_at"][:4] == str(datetime.now(timezone.utc).year))


# ═══ 3. HÉRITAGE PAR PERSONNE (faux Mongo async) ═════════════════════════════
class _Curseur:
    def __init__(self, docs): self._docs = docs
    def limit(self, n): self._docs = self._docs[:n]; return self
    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _Coll:
    def __init__(self, docs): self.docs = docs
    def find(self, q, proj=None):
        def ok(d):
            for k, v in q.items():
                if k == "attribution.first.source":
                    if not ((d.get("attribution") or {}).get("first") or {}).get("source"):
                        return False
                elif d.get(k) != v:
                    return False
            return True
        return _Curseur([d for d in self.docs if ok(d)])


class _DB(dict):
    def __getitem__(self, k): return dict.__getitem__(self, k)


def db_avec(subs=(), resas=(), pays=()):
    return _DB({"subscriptions": _Coll(list(subs)), "reservations": _Coll(list(resas)), "payment_transactions": _Coll(list(pays))})


_first_ig = {"first": {"source": "instagram", "medium": "reel", "campaign": "hiver2026", "touch_at": "2026-09-01T10:00:00+00:00"}}
_first_go = {"first": {"source": "google", "medium": "organic", "touch_at": "2026-09-05T10:00:00+00:00"}}
db = db_avec(subs=[{"email": "a@mail.ch", "attribution": _first_go}], resas=[{"userEmail": "a@mail.ch", "attribution": _first_ig}])
_h = run(S.m2a_attribution_heritee(db, "A@Mail.ch "))
verifier("B. Héritage : la first-touch la plus ANCIENNE de la personne (instagram 01/09 < google 05/09), e-mail normalisé",
         _h and _h["first"]["source"] == "instagram", _h)
verifier("B2. Personne inconnue -> None (jamais une source inventée)", run(S.m2a_attribution_heritee(db, "z@mail.ch")) is None)
verifier("B3. Sans e-mail -> None ; base absente -> None", run(S.m2a_attribution_heritee(db, "")) is None and run(S.m2a_attribution_heritee(None, "a@mail.ch")) is None)
_r1 = run(S.m2a_resoudre(db, {"first": {"source": "qr", "campaign": "festival2026"}}, "a@mail.ch"))
# RÉACTIVATION 3B : une origine explicite ne remplace JAMAIS la first-touch déjà
# connue de la personne (a@mail.ch a une first instagram) — elle se lit en `last`.
verifier("13. Résolution : explicite revalidée en LAST, first connue conservée (3B)",
         _r1["first"]["source"] == "instagram" and _r1["last"]["source"] == "qr" and _r1["last"]["campaign"] == "festival2026", _r1)
verifier("13b. Sans historique, l'explicite fait foi tel quel (first = last = qr)",
         run(S.m2a_resoudre(db, {"first": {"source": "qr", "campaign": "festival2026"}}, "z@mail.ch"))["first"]["source"] == "qr")
_r2 = run(S.m2a_resoudre(db, None, "a@mail.ch"))
verifier("14. Résolution : 2) sinon la first-touch connue", _r2["first"]["source"] == "instagram")
_r3 = run(S.m2a_resoudre(db, {"first": {"source": "linkedin"}}, "a@mail.ch"))
verifier("15. Un explicite hors liste vaut « absent » -> héritage", _r3["first"]["source"] == "instagram")
verifier("G. Client inconnu, arrivée directe, aucun historique -> None : l'achat continue sans attribution",
         run(S.m2a_resoudre(db, None, "nouveau@mail.ch")) is None)
_c = run(S.m2a_resoudre(db, {"first": {"source": "direct", "touch_at": "2026-09-10T10:00:00+00:00"}}, "a@mail.ch"))
verifier("C. Une visite directe explicite n'est pas une origine externe : la first Instagram est gardée", _c["first"]["source"] == "instagram")


# ═══ 4. LE COCKPIT PAR SOURCE — scénarios A, B, D, G sur le vrai moteur ══════
COACH = "coach@afroboost.ch"
MAINTENANT = datetime(2026, 9, 20, 12, 0, 0)
DEBUT, FIN = datetime(2026, 9, 1), datetime(2026, 10, 1)
ATTR = lambda src, content="", quand="2026-09-01T10:00:00+00:00": {"first": {"source": src, "medium": "x", "campaign": "hiver2026", "content": content, "term": "", "landing_path": "/", "touch_at": quand}}  # noqa: E731


def sub(code, email, cree, offer_name, **kw):
    d = {"id": "sub-" + code.lower(), "code": code, "email": email, "name": email.split("@")[0], "offer_name": offer_name,
         "status": "active", "created_at": cree + "T10:00:00+00:00", "expires_at": "2027-05-01T23:59:59+00:00",
         "total_sessions": 64, "used_sessions": 0, "remaining_sessions": 64, "coach_id": COACH, "auto_renew": False, "renewal_warnings_sent": []}
    d.update(kw); return d


def fiche(code, email, **kw):
    d = {"code": code, "assignedEmail": email, "type": "sessions", "value": 64, "maxUses": 64, "used": 0, "active": True, "id": "dc-" + code.lower()}
    d.update(kw); return d


def pt(id_, session, email, cree, amount, **kw):
    d = {"id": id_, "session_id": session, "customer_email": email, "created_at": cree + "T10:00:00+00:00", "amount": amount, "amount_total": amount,
         "quantity": 1, "currency": "chf", "product_name": "Saison hiver — 8 mois", "payment_status": "paid", "coach_id": COACH,
         "payment_methods": ["card"], "metadata": {"customer_email": email, "product_name": "Saison hiver — 8 mois"}}
    d.update(kw); return d


def resa(id_, email, occ, cree, **kw):
    d = {"id": id_, "userEmail": email, "userName": email.split("@")[0], "courseId": "c-mer", "courseName": "Silent",
         "datetime": occ, "createdAt": cree, "coach_id": COACH, "validated": False, "isProduct": False, "price": 0}
    d.update(kw); return d


OFFRES = {"o-saison": {"id": "o-saison", "name": "Saison hiver — 8 mois", "price": 549.0, "pack_sessions": 64},
          "o-essai": {"id": "o-essai", "name": "🎁 Cours d'essai GRATUIT ", "price": 0.0, "pack_sessions": 1}}
SUBS = [
    # A — Instagram : essai attribué (explicite), réservation présente, achat Saison 8 mois 549 (attribution au webhook)
    sub("AFR-IGA", "ana@mail.ch", "2026-09-02", "🎁 Cours d'essai GRATUIT ", expires_at="2026-10-01T23:59:59+00:00",
        montant_encaisse=0, origine_paiement="offert", source="checkout_vitrine", coach_id="", attribution=ATTR("instagram"),
        converted_at="2026-09-10T10:00:00+00:00"),
    sub("AFR-SAIS-A", "ana@mail.ch", "2026-09-10", "Saison hiver — 8 mois", source="stripe_auto", stripe_session_id="cs_A",
        attribution=ATTR("instagram"), billing_mode="unique", duree_mois=8),
    # B — autre appareil : essai Instagram, puis achat SANS attribution explicite -> hérite (posé au webhook par m2a_attribution_heritee)
    sub("AFR-IGB", "bob@mail.ch", "2026-09-03", "🎁 Cours d'essai GRATUIT ", expires_at="2026-10-01T23:59:59+00:00",
        montant_encaisse=0, origine_paiement="offert", source="checkout_vitrine", coach_id="", attribution=ATTR("instagram", quand="2026-09-03T10:00:00+00:00")),
    sub("AFR-SAIS-B", "bob@mail.ch", "2026-09-12", "Saison hiver — 8 mois", source="stripe_auto", stripe_session_id="cs_B", billing_mode="unique", duree_mois=8),
    # D — partenaire restaurant-x : essai + présence + achat
    sub("AFR-PART", "dan@mail.ch", "2026-09-04", "🎁 Cours d'essai GRATUIT ", expires_at="2026-10-01T23:59:59+00:00",
        montant_encaisse=0, origine_paiement="offert", source="checkout_vitrine", coach_id="", attribution=ATTR("partenaire", "restaurant-x")),
    sub("AFR-SAIS-D", "dan@mail.ch", "2026-09-14", "Saison hiver — 8 mois", source="stripe_auto", stripe_session_id="cs_D",
        attribution=ATTR("partenaire", "restaurant-x"), billing_mode="unique", duree_mois=8),
    # G — inconnu, achat direct sans aucune attribution
    sub("AFR-SAIS-G", "gil@mail.ch", "2026-09-15", "Saison hiver — 8 mois", source="stripe_auto", stripe_session_id="cs_G", billing_mode="unique", duree_mois=8),
]
FICHES = [fiche("AFR-IGA", "ana@mail.ch", value=1, maxUses=1, stripe_amount=0, session_id="free_A", used=1),
          fiche("AFR-SAIS-A", "ana@mail.ch", session_id="cs_A", stripe_amount=549),
          fiche("AFR-IGB", "bob@mail.ch", value=1, maxUses=1, stripe_amount=0, session_id="free_B"),
          fiche("AFR-SAIS-B", "bob@mail.ch", session_id="cs_B", stripe_amount=549),
          fiche("AFR-PART", "dan@mail.ch", value=1, maxUses=1, stripe_amount=0, session_id="free_D", used=1),
          fiche("AFR-SAIS-D", "dan@mail.ch", session_id="cs_D", stripe_amount=549),
          fiche("AFR-SAIS-G", "gil@mail.ch", session_id="cs_G", stripe_amount=549)]
PAIEMENTS = [pt("pA", "cs_A", "ana@mail.ch", "2026-09-10", 549, attribution=ATTR("instagram")),
             pt("pB", "cs_B", "bob@mail.ch", "2026-09-12", 549),
             pt("pD", "cs_D", "dan@mail.ch", "2026-09-14", 549, attribution=ATTR("partenaire", "restaurant-x")),
             pt("pG", "cs_G", "gil@mail.ch", "2026-09-15", 549)]
RESAS = [
    resa("r1", "ana@mail.ch", "2026-09-06T18:30:00", "2026-09-02T12:00:00+00:00", discountCode="AFR-IGA", validated=True, attribution=ATTR("instagram")),
    resa("r2", "bob@mail.ch", "2026-09-07T18:30:00", "2026-09-03T12:00:00+00:00", discountCode="AFR-IGB", attribution=ATTR("instagram", quand="2026-09-03T10:00:00+00:00")),
    resa("r3", "dan@mail.ch", "2026-09-08T18:30:00", "2026-09-04T12:00:00+00:00", discountCode="AFR-PART", validated=True, attribution=ATTR("partenaire", "restaurant-x")),
]
COURS = {"c-mer": {"id": "c-mer", "name": "Silent", "weekday": 3}}


def _faits():
    fiches_par_code = {}
    for f in FICHES:
        fiches_par_code.setdefault(f["code"].upper(), []).append(f)
    codes_par_code = {k: A.choisir_fiche_code(v) for k, v in fiches_par_code.items()}
    subs_par_id = {s["id"]: s for s in SUBS}
    subs_par_code = {}
    for s in SUBS:
        subs_par_code.setdefault(s["code"].upper(), s)
    return A.construire_faits(RESAS, COURS, subs_par_id, subs_par_code, codes_par_code, OFFRES, {})["faits"]


FAITS = _faits()
ACHATS = A.construire_achats(SUBS, FICHES, PAIEMENTS, OFFRES, MAINTENANT)
verifier("16. Les faits portent l'origine marketing (jamais le canal technique)",
         all("attribution_source" in f for f in FAITS) and {f["attribution_source"] for f in FAITS} == {"instagram", "partenaire"}
         and all(f["source"] == "" for f in FAITS))
par_cle = {a["cle"]: a for a in ACHATS["achats"]}
verifier("17. Un achat = une ligne, inchangé : 7 lignes (4 saisons + 3 essais), 0 jumeau compté deux fois",
         len(ACHATS["achats"]) == 7 and ACHATS["ecartes"]["paiements_jumeaux"] == 4, (len(ACHATS["achats"]), ACHATS["ecartes"]))
verifier("18. L'achat Saison A porte instagram (souscription) ; D porte partenaire/restaurant-x",
         par_cle["droit:AFR-SAIS-A"]["attribution_source"] == "instagram" and par_cle["droit:AFR-SAIS-D"]["attribution_source"] == "partenaire"
         and par_cle["droit:AFR-SAIS-D"]["attribution_content"] == "restaurant-x")
verifier("19. L'achat B (sans attribution sur le droit) n'invente rien au niveau document", par_cle["droit:AFR-SAIS-B"]["attribution_source"] == "")
verifier("20. Metadata Stripe plates lues aussi (transaction seule)",
         A.attribution_first({"metadata": {"attribution_first_source": "qr", "attribution_first_content": ""}}) == ("qr", ""))

SRC = A.calculer_kpi_sources(FAITS, ACHATS["achats"], [], DEBUT, FIN, MAINTENANT)
lignes = {l["cle"]: l for l in SRC["lignes"]}
verifier("21. Trois sources + « inconnue » : instagram, Partenaire — restaurant-x, inconnue (jamais Google/Instagram inventés pour G)",
         set(lignes) == {"instagram", "partenaire:restaurant-x", "inconnue"}, set(lignes))
ig = lignes["instagram"]
verifier("A. Instagram : 2 participants, 2 essais, 1 présence confirmée, 2 achats, CA 1098 prouvé, offre Saison ×2",
         ig["participants"] == 2 and ig["essais"] == 2 and ig["presences_confirmees"] == 1 and ig["achats"] == 2
         and ig["ca_prouve"] == 1098 and ig["offres"] == [("Saison hiver — 8 mois", 2)], ig)
verifier("A2. Instagram : conversion confirmée 1/2 (marqueur), probable 2/2 (achat suivant) — règles existantes",
         ig["convertis_confirmes"] == 1 and ig["convertis_probables"] == 2 and ig["taux_conversion_confirmee"] == 50.0 and ig["taux_conversion_probable"] == 100.0, ig)
verifier("B. Autre appareil : l'achat de Bob est rattaché à Instagram par la first-touch de la PERSONNE (essai), pas au document",
         ig["clients"] == 2 and "bob@mail.ch" not in {a["participant_key"] for a in ACHATS["achats"] if a["attribution_source"]} or ig["achats"] == 2)
pa = lignes["partenaire:restaurant-x"]
verifier("D. Partenaire — restaurant-x : libellé, 1 essai, 1 présence, 1 achat 549, partenaire=True",
         pa["libelle"] == "Partenaire — restaurant-x" and pa["partenaire"] and pa["essais"] == 1 and pa["presences_confirmees"] == 1
         and pa["achats"] == 1 and pa["ca_prouve"] == 549, pa)
inc = lignes["inconnue"]
verifier("G. Inconnue : 1 achat 549 valide, aucune source inventée, triée en dernier",
         inc["achats"] == 1 and inc["ca_prouve"] == 549 and SRC["lignes"][-1]["cle"] == "inconnue")
verifier("22. Présence : Bob (réservé, non scanné) n'est PAS une absence — présence d'essais Instagram = 1 confirmée, 0 absente, 1 inconnue",
         ig["presence_essais"]["confirmee"] == 1 and ig["presence_essais"]["absente"] == 0 and ig["presence_essais"]["inconnue"] == 1, ig["presence_essais"])
verifier("23. Renouvellements : confirmés séparés des probables, 0 ici", ig["renouvellements"] == {"confirmes": 0, "probables": 0})
verifier("24. Couverture : 3 participants attribués sur 4, 3 achats attribués sur 4",
         SRC["couverture"] == {"participants_attribues": 3, "participants_total": 4, "achats_attribues": 3, "achats_total": 4}, SRC["couverture"])
verifier("25. Aucun coût d'acquisition (ni 0 CHF) dans la sortie", not any("cac" in k or "cout" in k for l in SRC["lignes"] for k in l))
verifier("26. Somme des CA par source = CA global du cockpit (même moteur)",
         sum(l["ca_prouve"] for l in SRC["lignes"]) == A.calculer_kpi_finance(ACHATS["achats"], [], [], FAITS, DEBUT, FIN, "jour", MAINTENANT)["revenus"]["ca_encaisse"])
# Renouvellement confirmé par source
SUBS_R = SUBS + [sub("AFR-REN", "ana@mail.ch", "2026-08-01", "Mensuel Liberté", source="stripe_auto", stripe_session_id="cs_R",
                     attribution=ATTR("instagram"), last_renewal_date="2026-09-16T10:00:00+00:00", total_sessions=8, remaining_sessions=8)]
ACH_R = A.construire_achats(SUBS_R, FICHES + [fiche("AFR-REN", "ana@mail.ch", session_id="cs_R", stripe_amount=89, value=8, maxUses=8)],
                            PAIEMENTS + [pt("pR", "cs_R", "ana@mail.ch", "2026-08-01", 89, attribution=ATTR("instagram"))], OFFRES, MAINTENANT)
SRC_R = A.calculer_kpi_sources(FAITS, ACH_R["achats"], [], DEBUT, FIN, MAINTENANT)
verifier("27. Renouvellement CONFIRMÉ (last_renewal_date dans la période) compté sur Instagram, règle existante",
         {l["cle"]: l for l in SRC_R["lignes"]}["instagram"]["renouvellements"]["confirmes"] == 1)


# ═══ 5. STRUCTURE : les points d'écriture existent bien ══════════════════════
_srv = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_chk = open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"), encoding="utf-8").read()
_res = open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"), encoding="utf-8").read()
_app = open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
_chat = open(os.path.join(RACINE, "frontend", "src", "components", "ChatWidget.js"), encoding="utf-8").read()
_rt = open(os.path.join(RACINE, "api", "routes", "analytics_routes.py"), encoding="utf-8").read()
verifier("28. create-checkout-session : `attribution` acceptée et aplatie dans les metadata Stripe",
         "attribution: Optional[dict] = None" in _srv[_srv.index("class CreateCheckoutRequest"):_srv.index("class CreateCheckoutRequest") + 4000]
         and "metadata.update(m2a_vers_metadata(" in _srv)
verifier("29. Webhook : metadata -> sinon héritage e-mail ; recopie sur souscription ET transaction",
         "m2a_depuis_metadata(metadata) or await m2a_attribution_heritee(db, customer_email)" in _srv
         and '"$set": {"attribution": _m2a_wh}' in _srv)
verifier("30. Les 3 créations de réservation passent par m2a_resoudre (website/chat, scan QR, espace abonné)",
         _res.count("_m2a_resoudre(db,") == 2 and "await m2a_resoudre(db, _m2a, reservation_doc.get(\"userEmail\"))" in _srv)
verifier("31. /checkout/free : explicite sinon héritage", "_m2a_resoudre(db, getattr(req, \"attribution\", None)" in _chk)
verifier("32. Le navigateur joint attributionActuelle() au checkout payant et aux réservations (App.js), ChatWidget en ES5",
         _app.count("attribution: (function () { try { return attributionActuelle(); }") >= 2 and "attribution: v2bAttribution" in _app
         and "localStorage.getItem('af_attribution')" in _chat and "var v2bBrut" in _chat and "const v2b" not in _chat and "let v2b" not in _chat)
verifier("33. Le cockpit sert `sources` (même appel, aucune requête de plus)", 'kpi["sources"] = calculer_kpi_sources(' in _rt and 'kpi["requetes"] = 7' in _rt)

print("\n%d/%d au vert" % (OK, OK + RATE))
sys.exit(1 if RATE else 0)

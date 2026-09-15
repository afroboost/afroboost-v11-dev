# -*- coding: utf-8 -*-
"""ANALYTICS PHASE 3 — bilan Association, comparaison, résumé, exports CSV / XLSX / PDF.

Ce que ces bancs tiennent :
  * la projection est une PROJECTION : chaque valeur du bilan est ÉGALE à celle
    du KPI SuperAdmin (même période, même périmètre) — écran = CSV = XLSX = PDF ;
  * comparaison mois précédent : %, « nouveau » si le précédent vaut zéro,
    « comparaison indisponible » si les deux valent zéro ; jamais un % inventé ;
  * mois courant, mois passé, année, période personnalisée, évolution 12 mois ;
  * hors CA (déclaré non prouvé, pending, inconnus) jamais additionnés ;
  * aucune donnée personnelle dans la projection ni dans les fichiers ;
  * CSV UTF-8 BOM « ; », XLSX 7 feuilles relisibles, PDF avec pied et sans nom ;
  * route : 401 sans jeton, 403 hors périmètre, 200 admin, export = même calcul.

AUCUNE BASE RÉELLE, AUCUN RÉSEAU.
    python3 tests/test_analytics_association.py
"""
import asyncio, io, os, sys, types
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from api.routes import analytics_shared as A
from api.routes import analytics_association as AS

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


COACH = "coach@exemple.invalid"
AUTRE = "autre@exemple.invalid"
ADMIN = "admin@exemple.invalid"
MAINTENANT = datetime(2026, 9, 15, 12, 0, 0)


def resa(id_, email, occ, cree, course_id="c-mer", course_name="Silent", coach=COACH, **kw):
    d = {"id": id_, "userEmail": email, "userName": "Prénom Nom " + id_, "courseId": course_id, "courseName": course_name,
         "datetime": occ, "createdAt": cree, "coach_id": coach, "validated": False, "isProduct": False, "price": 0,
         "userPhone": "+41 79 123 45 67"}
    d.update(kw)
    return d


def sub(code, email, cree, offer_name="PULSE x10 cours", coach=COACH, **kw):
    d = {"id": "sub-" + code.lower(), "code": code, "email": email, "name": "Prénom Nom", "offer_name": offer_name,
         "status": "active", "created_at": cree + "T10:00:00+00:00", "expires_at": "2027-03-01T23:59:59+00:00",
         "total_sessions": 10, "used_sessions": 0, "remaining_sessions": 10, "coach_id": coach, "renewal_warnings_sent": []}
    d.update(kw)
    return d


def fiche(code, email, **kw):
    d = {"code": code, "assignedEmail": email, "maxUses": 10, "used": 0, "active": True, "id": "dc-" + code.lower()}
    d.update(kw)
    return d


# août 2026 : 3 séances, 5 réservations, 4 uniques ; juillet : 1 séance, 2 réservations (dont anna -> récurrente en août)
RESAS = [
    resa("j1", "anna@mail.ch", "2026-07-08T18:30:00", "2026-07-01T10:00:00+00:00"),
    resa("j2", "bob@mail.ch", "2026-07-08T18:30:00", "2026-07-01T10:00:00+00:00"),
    resa("a1", "anna@mail.ch", "2026-08-05T18:30:00", "2026-08-01T10:00:00+00:00", validated=True, tarif_applique=25.0),
    resa("a2", "carl@mail.ch", "2026-08-05T18:30:00", "2026-08-01T10:00:00+00:00"),
    resa("a3", "dora@mail.ch", "2026-08-09T18:30:00", "2026-08-02T10:00:00+00:00", "c-dim", "Sunday", discountCode="AFR-ESSAI1", validated=True),
    resa("a4", "eve@mail.ch", "2026-08-12T18:30:00", "2026-08-10T10:00:00+00:00"),
    resa("a5", "anna@mail.ch", "2026-08-12T18:30:00", "2026-08-10T10:00:00+00:00"),
    resa("s1", "anna@mail.ch", "2026-09-09T18:30:00", "2026-09-01T10:00:00+00:00"),
    resa("x1", "zed@mail.ch", "2026-08-12T18:30:00", "2026-08-10T10:00:00+00:00", coach=AUTRE),
]
SUBS = [
    sub("PULSE-A", "anna@mail.ch", "2026-08-03", montant_encaisse=250, origine_paiement="twint"),
    sub("AFR-ESSAI1", "dora@mail.ch", "2026-08-02", "🎁 Cours d'essai GRATUIT ", montant_encaisse=0, origine_paiement="offert", coach=""),
    sub("AFR-ESSAI2", "fay@mail.ch", "2026-08-20", "🎁 Cours d'essai GRATUIT ", montant_encaisse=0, origine_paiement="offert", coach=""),
    sub("DECL-1", "kim@mail.ch", "2026-08-11", offer_price=250),
    sub("JUIL-1", "bob@mail.ch", "2026-07-03", montant_encaisse=100, origine_paiement="especes"),
    sub("AUTRE-1", "zed@mail.ch", "2026-08-12", montant_encaisse=100, origine_paiement="twint", coach=AUTRE),
]
FICHES = [fiche("PULSE-A", "anna@mail.ch"), fiche("AFR-ESSAI1", "dora@mail.ch", payment_method="free", total_paid=0, transaction_id="free_1a2b3c4"),
          fiche("AFR-ESSAI2", "fay@mail.ch", payment_method="free", total_paid=0), fiche("DECL-1", "kim@mail.ch"),
          fiche("JUIL-1", "bob@mail.ch"), fiche("AUTRE-1", "zed@mail.ch")]
PAIEMENTS = [
    {"id": "p1", "session_id": "cs_live_abc123", "customer_email": "carl@mail.ch", "created_at": "2026-08-06T10:00:00+00:00",
     "amount": 30.0, "amount_total": 3000, "quantity": 1, "currency": "chf", "product_name": "Cours", "payment_status": "paid",
     "coach_id": COACH, "metadata": {"customer_email": "carl@mail.ch", "customer_name": "Carl Nom"}},
    {"id": "p2", "session_id": "cs_live_pend", "customer_email": "eve@mail.ch", "created_at": "2026-08-07T10:00:00+00:00",
     "amount": 250.0, "amount_total": None, "quantity": 1, "currency": "chf", "product_name": "Pulse", "payment_status": "pending",
     "coach_id": COACH, "metadata": {"customer_email": "eve@mail.ch"}},
]
CARTES = [{"email": "anna@mail.ch", "date_debut": "2026-08-03", "date_fin": "2027-08-02", "source": "achat", "coach_id": COACH}]
COURS = {"c-mer": {"id": "c-mer", "name": "Silent", "weekday": 3}, "c-dim": {"id": "c-dim", "name": "Sunday", "weekday": 0}}
OFFRES = {}


def _kpi(d, f, resas=RESAS, subs=SUBS, fiches=FICHES, pays=PAIEMENTS, cartes=CARTES, cid=""):
    fpc = {}
    for x in fiches:
        fpc.setdefault(x["code"].upper(), []).append(x)
    codes = {k: A.choisir_fiche_code(v) for k, v in fpc.items()}
    spi = {s["id"]: s for s in subs}
    spc = {}
    for s in subs:
        spc.setdefault(s["code"].upper(), s)
    faits = A.construire_faits(resas, COURS, spi, spc, codes, OFFRES, {})["faits"]
    if cid:
        faits = [x for x in faits if x["course_id"] == cid]
    ach = A.construire_achats(subs, fiches, pays, OFFRES, MAINTENANT)
    k = A.calculer_kpi(faits, d, f, "mois")
    k.update(A.calculer_kpi_finance(ach["achats"], ach["en_attente"], cartes, faits, d, f, "mois", MAINTENANT, cours_filtre=cid))
    return k


def _assoc(periode="mois", mois="2026-08", du="", au="", cid="", **kw):
    d, f = A.bornes_periode(periode, MAINTENANT, du, au, mois)
    kpi = _kpi(d, f, cid=cid, **kw)
    pd_, pf = AS.periode_precedente(d, f)
    prec = _kpi(pd_, pf, cid=cid, **kw)
    m = d.replace(month=1, day=1)
    annee = []
    for _ in range(12):
        annee.append((m, _kpi(m, A.mois_suivant(m), cid=cid, **kw)))
        m = A.mois_suivant(m)
    return kpi, AS.projeter_association(kpi, prec, annee, d, f, AS.PERIMETRE_ENSEMBLE, cid, MAINTENANT)


KPI, ASSOC = _assoc()

# ═══ 1. la projection = le KPI (aucun recalcul) ═══
verifier("période : Août 2026, bornes du mois demandé (mois=2026-08 avec periode=mois)", ASSOC["periode"] == {"debut": "2026-08-01", "fin_exclue": "2026-09-01", "libelle": "Août 2026"}, ASSOC["periode"])
a = ASSOC["activite"]
# Le banc pur = la vue « tous les coachs » (l'autre coach compte) ; la vue coach est exercée sur la route.
verifier("activité août = KPI : 3 séances, 6 réservations, 5 uniques, 4 nouveaux, 1 récurrente, moyenne 2.0",
         (a["seances"], a["reservations"], a["participants_uniques"], a["nouveaux"], a["recurrents"], a["moyenne_par_seance"]) == (3, 6, 5, 4, 1, 2.0)
         and a["seances"] == KPI["cours"]["seances"] and a["reservations"] == KPI["participants"]["reservations_cours"], a)
verifier("mercredi 5 / dimanche 1, autres jours 0", a["mercredi"]["reservations"] == 5 and a["dimanche"]["reservations"] == 1 and a["autres_jours"] == 0)
verifier("présence : 2 vérifiées sur 6 — 33,3 %, libellé honnête", ASSOC["presence"]["libelle"] == "2 présence(s) vérifiée(s) sur 6 réservations — couverture 33,3 %", ASSOC["presence"])
e = ASSOC["essais"]
verifier("essais août : 2 accordés, 1 réservé, 1 présence confirmée, couverture 100 %, 0 conversion confirmée = KPI",
         (e["accordes"], e["reserves"], e["presence_confirmee"], e["couverture_pct"], e["conversions_confirmees"]) == (2, 1, 1, 100.0, 0)
         and e["accordes"] == KPI["essais_funnel"]["accordes"], e)
verifier("fidélisation = KPI", ASSOC["fidelisation"] == {c: KPI["fidelite"][c] for c in A.CATEGORIES_FIDELITE} and ASSOC["fidelisation"] == {"1": 4, "2_5": 1, "6_10": 0, "plus_10": 0})
ab = ASSOC["abonnements"]
verifier("abonnements = KPI : 6 actifs, nouveaux 5 en août, Pulse vendus 3 (PULSE-A, DECL-1, AUTRE-1), cartes 1 active / 1 vendue",
         ab["actifs"] == KPI["abonnements"]["actifs"]["total"] == 6 and ab["nouveaux"] == 5 and ab["pulse_vendus"] == 3 and ab["cartes_actives"] == 1 and ab["cartes_vendues"] == 1, ab)
f = ASSOC["finances"]
verifier("finances = KPI : CA prouvé 380 (250 + 100 + 30), Stripe 30, manuel 350, 3 achats payés, panier 126.67",
         (f["ca_prouve"], f["stripe"], f["manuel"], f["achats_payes"], f["panier_moyen"]) == (380.0, 30.0, 350.0, 3, 126.67) and f["ca_prouve"] == KPI["revenus"]["ca_encaisse"], f)
verifier("hors CA séparé : déclaré non prouvé 250 (1), pending 1 (250 déclarés), inconnus 0 — jamais dans le CA",
         f["hors_ca"]["declare_non_prouve_montant"] == 250 and f["hors_ca"]["pending_nombre"] == 1 and f["hors_ca"]["pending_montant"] == 250 and f["ca_prouve"] == 380.0, f["hors_ca"])
verifier("moyens : Stripe indéterminé reste « Stripe — moyen non déterminé », jamais carte/TWINT",
         f["par_moyen"]["stripe_indetermine"]["libelle"] == "Stripe — moyen non déterminé" and "stripe_card" not in f["par_moyen"])
verifier("renouvellements : KPI principal = confirmés (0), probables à part, libellé explicite", ab["renouvellements_confirmes"] == 0 and "non comptés dans le KPI principal" in ab["note_probables"])
q = ASSOC["qualite"]
verifier("qualité : phrases présence / finance / moyens / renouvellements / remboursements",
         len(q["phrases"]) == 5 and "2 présence(s) vérifiée(s) sur 6" in q["phrases"][0] and "380,00 CHF" in q["phrases"][1] and "250,00 CHF" in q["phrases"][1]
         and "Remboursements non disponibles historiquement" in q["phrases"][4], q["phrases"])

# ═══ 2. comparaison ═══
c = ASSOC["comparaison"]
verifier("période précédente = Juillet 2026", c["periode_precedente"]["libelle"] == "Juillet 2026")
verifier("réservations 2 -> 6 : +200,0 %", c["indicateurs"]["reservations"] == {"actuel": 6, "precedent": 2, "variation_pct": 200.0, "libelle": "+200,0 %", "libelle_indicateur": "Réservations"}, c["indicateurs"]["reservations"])
verifier("essais 0 -> 2 : « nouveau », aucun pourcentage", c["indicateurs"]["essais"]["libelle"] == "nouveau" and c["indicateurs"]["essais"]["variation_pct"] is None)
verifier("CA 100 -> 380 : +280,0 %", c["indicateurs"]["ca_prouve"]["libelle"] == "+280,0 %")
verifier("baisse : signe −", AS.comparer(3, 4)["libelle"] == "−25,0 %")
verifier("0 -> 0 : « comparaison indisponible »", AS.comparer(0, 0)["libelle"] == "comparaison indisponible" and AS.comparer(None, None)["variation_pct"] is None)
verifier("égal : « stable »", AS.comparer(4, 4)["libelle"] == "stable")
_, prem = _assoc(mois="2026-03")
verifier("mois précédent = zéro (février) : tout « nouveau » ou « indisponible », jamais un %",
         all(v["variation_pct"] is None for v in prem["comparaison"]["indicateurs"].values()) and prem["comparaison"]["periode_precedente"]["libelle"] == "Février 2026", prem["comparaison"])

# ═══ 3. périodes ═══
_, cour = _assoc(mois="")
verifier("mois courant (sans mois=) : Septembre 2026, 1 réservation", cour["periode"]["libelle"] == "Septembre 2026" and cour["activite"]["reservations"] == 1)
_, an = _assoc(periode="annee", mois="2026-01")
verifier("année : « Année 2026 », 8 réservations du coach + autre, comparaison = Année 2025", an["periode"]["libelle"] == "Année 2026" and an["activite"]["reservations"] == 9 and an["comparaison"]["periode_precedente"]["libelle"] == "Année 2025")
_, perso = _assoc(periode="perso", mois="", du="2026-08-01", au="2026-08-10")
verifier("perso 1–10 août : libellé « Du 1 août au 10 août 2026 », 3 réservations, précédent = fenêtre de même longueur (22–31 juillet)",
         perso["periode"]["libelle"] == "Du 1 août au 10 août 2026" and perso["activite"]["reservations"] == 3 and perso["comparaison"]["periode_precedente"]["debut"] == "2026-07-22", perso["periode"])
ev = ASSOC["evolution_annuelle"]
verifier("évolution annuelle : 12 mois Jan..Déc, chacun du même moteur (Juil 2 réservations, Août 6, Sept 1, CA Août 380)",
         [m["mois"] for m in ev["mois"]] == AS.MOIS_COURTS and [m["reservations"] for m in ev["mois"]][6:9] == [2, 6, 1] and ev["mois"][7]["ca_prouve"] == 380.0 and ev["mois"][9]["futur"] is True, ev)
_, parc = _assoc(cid="c-dim")
verifier("filtre cours : activité filtrée (1 réservation), finances et abonnements globaux inchangés, note explicite",
         parc["activite"]["reservations"] == 1 and parc["finances"]["ca_prouve"] == 380.0 and parc["abonnements"]["actifs"] == ab["actifs"] and "globaux" in parc["perimetre"]["note"])

# ═══ 4. résumé exécutif déterministe ═══
r = ASSOC["resume_executif"]
verifier("résumé : commence par « En août 2026 », porte séances/participants/réservations/CA/nouveaux/essais",
         r.startswith("En août 2026, Afroboost a organisé 3 séance(s) réunissant 5 participant(s) unique(s) pour 6 réservation(s).")
         and "de 2 participant(s) par séance" in r and "380,00 CHF (3 achat(s) payé(s))" in r and "4 nouveau(x)" in r and "2 essai(s)" in r
         and "250,00 CHF déclarés sans preuve suffisante et 1 paiement(s) en attente" in r, r)
verifier("résumé identique si recalculé (déterministe)", AS.resume_executif(ASSOC) == r)

# ═══ 5. anonymat ═══
verifier("projection sans e-mail, téléphone, nom, code, identifiant Stripe, jeton", AS.verifier_anonymat(ASSOC) == [], AS.verifier_anonymat(ASSOC))
verifier("le détecteur voit un e-mail, un code, un cs_live, un téléphone, un jeton",
         [q for _, q in AS.verifier_anonymat({"a": "x@y.ch", "b": ["AFR-ABC123"], "c": {"d": "cs_live_zz"}, "e": "+41 79 123 45 67", "f": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"})]
         == ["e-mail", "code d'accès", "identifiant Stripe/transaction", "téléphone", "jeton"])
import json as _json
_txt = _json.dumps(ASSOC, ensure_ascii=False)
verifier("aucun nom de participant ni 'Prénom Nom' dans la projection", "Prénom" not in _txt and "@" not in _txt and "cs_live" not in _txt)

# ═══ 6. CSV ═══
csv_b = AS.export_csv(ASSOC)
verifier("CSV : BOM UTF-8, séparateur ;, CRLF", csv_b.startswith(b"\xef\xbb\xbf") and b";" in csv_b and b"\r\n" in csv_b)
import csv as _csv
lignes = list(_csv.reader(io.StringIO(csv_b.decode("utf-8-sig")), delimiter=";"))
tete = dict(zip(lignes[0], lignes[1]))
verifier("CSV : colonnes attendues", all(k in tete for k in ("Période", "Séances", "Réservations", "Participants uniques", "Nouveaux", "Récurrents", "Essais", "Présences essais",
         "Conversions confirmées", "Pulse actifs", "Pulse vendus", "Cartes membres actives", "CA prouvé (CHF)", "Stripe (CHF)", "Manuel (CHF)",
         "Déclaré non prouvé (CHF, hors CA)", "Pending (nombre, hors CA)", "Couverture présence (%)")), list(tete))
verifier("CSV = écran : séances 3, réservations 6, uniques 5, essais 2, Pulse vendus 3, cartes 1, CA 380,00, déclaré 250,00, pending 1, couverture 33,30",
         (tete["Séances"], tete["Réservations"], tete["Participants uniques"], tete["Essais"], tete["Pulse vendus"], tete["Cartes membres actives"],
          tete["CA prouvé (CHF)"], tete["Déclaré non prouvé (CHF, hors CA)"], tete["Pending (nombre, hors CA)"], tete["Couverture présence (%)"])
         == ("3", "6", "5", "2", "3", "1", "380,00", "250,00", "1", "33,30"), tete)
verifier("CSV : évolution 12 mois en bas, mois futurs marqués « à venir » (Oct..Déc), aucune donnée personnelle",
         sum(1 for l in lignes if l and l[1:2] and l[1] in AS.MOIS_COURTS) == 12
         and [l[-1] for l in lignes if l and l[1:2] and l[1] in AS.MOIS_COURTS][8:] == ["écoulé", "à venir", "à venir", "à venir"] and "@" not in csv_b.decode("utf-8-sig"))

# ═══ 7. XLSX ═══
xlsx_b = AS.export_xlsx(ASSOC)
feuilles = AS.lire_xlsx(xlsx_b)
verifier("XLSX : archive zip valide, 7 feuilles dans l'ordre", xlsx_b[:2] == b"PK" and list(feuilles) == list(AS.NOMS_FEUILLES), list(feuilles))
_res = {l[0]: l[1] for l in feuilles["Résumé"] if len(l) >= 2}
verifier("XLSX Résumé = écran : séances 3, réservations 6, CA 380, déclaré 250, pending 1, résumé exécutif présent",
         (_res["Séances"], _res["Réservations"], _res["CA prouvé (CHF)"], _res["Déclaré non prouvé (CHF, hors CA)"], _res["Pending (nombre, hors CA)"]) == (3.0, 6.0, 380.0, 250.0, 1.0)
         and _res["Résumé exécutif"] == r, _res)
_fin = {l[0]: l[1] for l in feuilles["Finances"] if len(l) >= 2}
verifier("XLSX Finances : CA prouvé 380,00 CHF (texte) et 380.0 (brut), hors CA à part", _fin["CA prouvé"] == "380,00 CHF" and _fin["CA prouvé (brut)"] == 380.0 and _fin["Montants déclarés non prouvés"] == "250,00 CHF" and _fin["Déclaré non prouvé (brut, hors CA)"] == 250.0)
_ess = {l[0]: l[1] for l in feuilles["Essais"] if len(l) >= 2}
_abo = {l[0]: l[1] for l in feuilles["Abonnements"] if len(l) >= 2}
_act = {l[0]: l[1] for l in feuilles["Activité"] if len(l) >= 2}
verifier("XLSX Essais / Abonnements / Activité = écran", _ess["Essais accordés"] == "2" and _abo["Pulse X10 vendus"] == "3" and _abo["Cartes membres actives"] == "1" and _act["Séances"] == "3" and _act["Réservations"] == "6" and _act["Participants uniques"] == "5")
verifier("XLSX Activité : comparaison et 12 mois d'évolution, mois futurs « à venir »", any(l[:1] == ["Comparaison — Réservations"] and "+200,0 %" in l for l in feuilles["Activité"]) and sum(1 for l in feuilles["Activité"] if l and l[0] in AS.MOIS_COURTS) == 12
         and [l[-1] for l in feuilles["Activité"] if l and l[0] in ("Sept", "Oct")] == ["écoulé", "à venir"])
verifier("XLSX Qualité : phrases + pied « données personnelles non incluses »", any(l and AS.PIED_PDF == l[0] for l in feuilles["Qualité des données"]))
verifier("XLSX : aucune donnée personnelle", "@" not in _json.dumps(feuilles, ensure_ascii=False) and "Prénom" not in _json.dumps(feuilles, ensure_ascii=False))

# ═══ 8. PDF ═══
try:
    pdf_b = AS.export_pdf(ASSOC)
    verifier("PDF : en-tête %PDF, titre et sous-titre", pdf_b.startswith(b"%PDF") and len(pdf_b) > 3000)
    try:
        from pypdf import PdfReader
        texte = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(io.BytesIO(pdf_b)).pages)
        verifier("PDF = écran : titre, Août 2026, résumé, 380,00 CHF, 3 séances, 6 réservations, 5 uniques, essais 2, Pulse 3, cartes 1",
                 "Bilan mensuel Afroboost" in texte and "Août 2026" in texte and "380,00 CHF" in texte and r[:60] in texte
                 and "Séances 3" in texte and "Réservations 6" in texte and "Participants uniques 5" in texte and "Essais accordés 2" in texte
                 and "Pulse X10 vendus 3" in texte and "Cartes membres actives 1" in texte, texte[:1500])
        verifier("PDF : hors CA à part, comparaison, qualité, pied « données personnelles non incluses », date de génération",
                 "Montants déclarés non prouvés 250,00 CHF" in texte and "+200,0 %" in texte and "Qualité des données" in texte
                 and "Les données personnelles des participants ne sont pas incluses" in texte and ASSOC["genere_le"] in texte and "mois à venir" in texte)
        verifier("PDF : aucune donnée nominative", "@" not in texte and "Prénom" not in texte and "AFR-ESSAI" not in texte and "cs_live" not in texte)
    except ImportError:
        verifier("pypdf absent : texte du PDF non relu", False, "pip install pypdf")
except ImportError:
    verifier("reportlab absent : PDF non exercé", False, "pip install reportlab")

# ═══ 9. cohérence écran / CSV / XLSX / PDF (une différence = échec) ═══
cibles = {"Séances": ASSOC["activite"]["seances"], "Réservations": ASSOC["activite"]["reservations"],
          "Participants uniques": ASSOC["activite"]["participants_uniques"], "Essais": ASSOC["essais"]["accordes"],
          "Pulse vendus": ASSOC["abonnements"]["pulse_vendus"], "Cartes membres actives": ASSOC["abonnements"]["cartes_actives"],
          "CA prouvé (CHF)": ASSOC["finances"]["ca_prouve"]}
ecarts = []
for k, v in cibles.items():
    if float(str(tete[k]).replace(",", ".")) != float(v):
        ecarts.append(("csv", k, tete[k], v))
    if float(_res[k]) != float(v):
        ecarts.append(("xlsx", k, _res[k], v))
verifier("COHÉRENCE écran = CSV = XLSX sur séances, réservations, uniques, essais, Pulse, cartes, CA", not ecarts, ecarts)
verifier("COHÉRENCE écran = KPI SuperAdmin (même objet source)", ASSOC["finances"]["ca_prouve"] == KPI["revenus"]["ca_encaisse"] and ASSOC["activite"]["seances"] == KPI["cours"]["seances"])

# ═══ 10. la route : auth, isolation, export = même calcul ═══
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
    async def find_one(self, f, p=None):
        self.base.requetes += 1
        for d in self.docs:
            if _match(d, f): return dict(d)
        return None
    def __getattr__(self, name):
        if name in ("update_one", "insert_one", "delete_one", "update_many", "find_one_and_update", "replace_one", "insert_many"):
            raise AssertionError("ÉCRITURE INTERDITE : " + name)
        raise AttributeError(name)


class _Base:
    def __init__(self):
        self.requetes = 0
        self.reservations = _Coll2(RESAS, self)
        self.courses = _Coll2(list(COURS.values()), self)
        self.subscriptions = _Coll2(SUBS, self)
        self.discount_codes = _Coll2(FICHES, self)
        self.offers = _Coll2([], self)
        self.memberships = _Coll2(CARTES, self)
        self.payment_transactions = _Coll2(PAIEMENTS, self)
        self.concept = _Coll2([{"coach_id": COACH, "appName": "Studio Test"}], self)
        self.monthly_reports = _Coll2([], self)


def _serveur(base, jwt_email):
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
_shared.is_super_admin = lambda e: (e or "").lower() == ADMIN

try:
    import fastapi  # noqa: F401
    from api.routes.analytics_routes import analytics_cockpit, analytics_export
    from fastapi import HTTPException

    class _Req:
        headers = {}

    def _appel(fn, jwt, **params):
        base = _Base()
        _serveur(base, jwt)
        try:
            r = run(fn(_Req(), **params))
            return 200, r, base.requetes
        except HTTPException as e:
            return e.status_code, None, base.requetes

    s, _, _ = _appel(analytics_cockpit, "", periode="mois", mois="2026-08", vue="association")
    verifier("route vue=association sans jeton -> 401", s == 401, s)
    s, _, _ = _appel(analytics_export, "", format="pdf", mois="2026-08")
    verifier("export PDF sans jeton -> 401 (un lien direct ne contourne rien)", s == 401, s)
    s, _, _ = _appel(analytics_export, COACH, format="csv", mois="2026-08", coach_id=AUTRE)
    verifier("export d'un autre coach -> 403", s == 403, s)
    s, r_admin, n = _appel(analytics_cockpit, ADMIN, periode="mois", mois="2026-08", vue="association")
    verifier("admin vue=association -> 200, 7 requêtes (tout en mémoire), bilan présent, périmètre Ensemble",
             s == 200 and n == 7 and r_admin["association"]["perimetre"]["libelle"] == AS.PERIMETRE_ENSEMBLE, (s, n))
    verifier("route admin : le bilan de la route = la projection du banc, valeur pour valeur",
             r_admin["association"]["finances"] == ASSOC["finances"] and r_admin["association"]["activite"] == ASSOC["activite"]
             and r_admin["association"]["essais"] == ASSOC["essais"] and r_admin["association"]["abonnements"] == ASSOC["abonnements"]
             and r_admin["association"]["comparaison"] == ASSOC["comparaison"] and r_admin["association"]["evolution_annuelle"] == ASSOC["evolution_annuelle"],
             r_admin["association"]["finances"]["ca_prouve"])
    verifier("route : cockpit (phase 1/2) et bilan du même appel portent les mêmes chiffres",
             r_admin["association"]["finances"]["ca_prouve"] == r_admin["revenus"]["ca_encaisse"] and r_admin["association"]["activite"]["reservations"] == r_admin["participants"]["reservations_cours"])
    s, r_coach, n = _appel(analytics_cockpit, COACH, periode="mois", mois="2026-08", vue="association")
    verifier("coach : 200, 8 requêtes (+ concept), périmètre « Coach Studio Test » (nom public, jamais l'adresse), CA 280 (sans l'autre coach), 5 réservations",
             s == 200 and n == 8 and r_coach["association"]["perimetre"]["libelle"] == "Coach Studio Test" and r_coach["association"]["finances"]["ca_prouve"] == 280.0
             and r_coach["association"]["activite"]["reservations"] == 5, (s, n, r_coach and r_coach["association"]["perimetre"]))
    verifier("coach : aucune donnée personnelle dans le bilan servi", AS.verifier_anonymat(r_coach["association"]) == [])
    s, _, _ = _appel(analytics_cockpit, ADMIN, periode="mois", mois="2026-08")
    verifier("sans vue=association : réponse phase 1/2 inchangée (pas de bilan)", s == 200)
    for fmt, debut_attendu, ctype in (("csv", b"\xef\xbb\xbf", "text/csv"), ("xlsx", b"PK", "spreadsheetml"), ("pdf", b"%PDF", "application/pdf")):
        s, resp, n = _appel(analytics_export, ADMIN, format=fmt, mois="2026-08")
        ok = s == 200 and resp.body.startswith(debut_attendu) and ctype in resp.media_type and "bilan-afroboost-2026-08." + fmt in resp.headers.get("content-disposition", "")
        verifier("export %s admin -> 200, bon type, bon nom, pièce jointe, 7 requêtes" % fmt, ok and n == 7, (s, n, resp and resp.media_type))
    s, resp, _ = _appel(analytics_export, ADMIN, format="csv", mois="2026-08")
    _l = list(_csv.reader(io.StringIO(resp.body.decode("utf-8-sig")), delimiter=";"))
    verifier("export CSV admin = bilan admin de la route (CA 380,00, 6 réservations)", dict(zip(_l[0], _l[1]))["CA prouvé (CHF)"] == "380,00" and dict(zip(_l[0], _l[1]))["Réservations"] == "6")
    s, resp, _ = _appel(analytics_export, COACH, format="csv", mois="2026-08")
    _lc = dict(zip(*list(_csv.reader(io.StringIO(resp.body.decode("utf-8-sig")), delimiter=";"))[:2]))
    verifier("export CSV coach = bilan coach (CA 280,00, 5 réservations, périmètre Coach Studio Test)", _lc["CA prouvé (CHF)"] == "280,00" and _lc["Réservations"] == "5" and _lc["Périmètre"] == "Coach Studio Test", _lc)
    s, _, _ = _appel(analytics_export, ADMIN, format="docx", mois="2026-08")
    verifier("format inconnu -> 400", s == 400, s)
    s, _, _ = _appel(analytics_cockpit, ADMIN, periode="mois", mois="pas-un-mois", vue="association")
    verifier("mois mal formé -> 400", s == 400, s)
except ImportError:
    verifier("fastapi absent : la route n'a pas pu être exercée", False, "installer fastapi")

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

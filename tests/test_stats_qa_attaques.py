# -*- coding: utf-8 -*-
"""STATS-1 — attaques du CONTRÔLE QUALITÉ INDÉPENDANT, intégrées au dépôt.

Version d'origine : scratchpad qa-stats/attaque_stats.py. Adaptations, et
seulement elles : chemin des outils relatif ; attentes MISES À JOUR après les
corrections demandées (A2 bloqué par le catalogue public, A3 = PAS de verrou
global, A5d = 503 configuration_invalide, A6b/A6c = 400 JSON), la sortie
devient un code de retour.

    python3 tests/test_stats_qa_attaques.py
"""
import json, os, re, sys, logging
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _stats_fixtures as F
logging.disable(logging.CRITICAL)
F.installer_serveur(F.Base(F.jeu_de_base()), F.ADMIN)
import api.routes.analytics_routes as R
from api.routes.analytics_cloture import construire_snapshot
F.poser_admin(); F.horloge_figee(R)
CF = "cle-frequentation-de-test-0123456789"; CK = "cle-finances-de-test-9876543210-abcdef"
os.environ[R.STATS_ENV_FREQUENTATION] = CF; os.environ[R.STATS_ENV_FINANCES] = CK
RES = []
def v(n, c, d=""): RES.append((n, bool(c), d))
def reinit():
    R._STATS_CACHE.clear(); R._STATS_DEBIT.clear()
def appel(cle=None, jeu=None, ip="203.0.113.7", h=None, **p):
    b = F.Base(jeu or F.jeu_de_base()); F.installer_serveur(b, "")
    hh = dict(h or {})
    if cle is not None: hh["Authorization"] = "Bearer " + cle
    r = F.run(R.stats_association(F.Req(hh, ip), **p))
    return r.status_code, json.loads(r.body.decode()), b

FIN_KEYS = re.compile(r"(ca_|montant|prix|price|revenu|stripe|manuel|panier|chf|paye|encaiss|valeur|rembours|hors_ca|par_moyen|gratuits|acheteurs)", re.I)
def cles_fin(o, ch=""):
    out = []
    if isinstance(o, dict):
        for k, x in o.items():
            if k == "revenus" and x == {"disponible": False, "raison": "portee_finances_requise"}: continue
            if FIN_KEYS.search(str(k)): out.append(ch + "." + k)
            out += cles_fin(x, ch + "." + k)
    elif isinstance(o, list):
        for i, x in enumerate(o): out += cles_fin(x, "%s[%d]" % (ch, i))
    elif isinstance(o, str) and re.search(r"CHF|\d+[.,]\d{2}\s*(CHF|fr)", o): out.append(ch + "=" + o[:60])
    return out

# A1 — portée fréquentation : aucun champ financier, ni dynamique, ni depuis une clôture, ni en année
for p in (dict(mois="2026-09"), dict(mois="2026-10"), dict(annee="2026"), dict(annee="2026", granularite="semaine")):
    reinit(); s, c, _ = appel(CF, **p)
    v("A1 fréquentation %s : 200 et aucun champ financier" % p, s == 200 and not cles_fin(c), (s, cles_fin(c)[:5]))
reinit()
_, K, _ = appel(CK, mois="2026-09")
F.installer_serveur(F.Base(F.jeu_de_base()), F.ADMIN)
bilan = F.run(R._calculer_cockpit(F.Req(), periode="mois", mois="2026-09", vue="association"))["association"]
snap = construire_snapshot(json.loads(json.dumps(bilan)), datetime(2026, 9, 1), datetime(2026, 10, 1), "", F.ADMIN, datetime(2026, 10, 2, 9))
jeu = F.jeu_de_base(); jeu["analytics_monthly_reports"] = [snap]
for p in (dict(mois="2026-09"), dict(annee="2026")):
    reinit(); s, c, _ = appel(CF, jeu=jeu, **p)
    v("A1b fréquentation + CLÔTURE %s : aucun champ financier" % p, s == 200 and not cles_fin(c), cles_fin(c)[:5])
v("A1c finances : revenus bien présents (témoin)", K["revenus"].get("disponible") is True and K["revenus"].get("ca_prouve") is not None)

# A2 — anonymat : nom de personne dans le nom du cours / le lieu
jeu = F.jeu_de_base()
# Adaptation : le NOM DU CATALOGUE est public (GET /api/courses le montre à tout visiteur) et sert
# de libellé ; on attaque donc le texte libre de la réservation et le lieu, qui ne doivent JAMAIS sortir.
jeu["courses"][0]["locationName"] = "Chez Jean Martin, Rue du Lac 12, 1200 Genève"
for r_ in jeu["reservations"]:
    if r_["courseId"] == "c-mer": r_["courseName"] = "Cours privé de Marie Dupont"
reinit(); s, c, _ = appel(CF, jeu=jeu, mois="2026-09")
txt = json.dumps(c, ensure_ascii=False)
v("A2 nom de personne / adresse privée dans par_seance : BLOQUÉ (attendu par le contrat d'anonymat)",
  s != 200 or ("Marie Dupont" not in txt and "Jean Martin" not in txt),
  "200 ; fuite: %s" % [x for x in ("Marie Dupont", "Jean Martin", "Rue du Lac 12") if x in txt])
# A2b — un e-mail dans le nom du cours : toute la réponse en 500 et rien en cache
jeu = F.jeu_de_base()
for r_ in jeu["reservations"]:
    if r_["courseId"] == "c-mer": r_["courseName"] = "Silent (contact anna@mail.invalid)"
jeu["courses"][0]["name"] = "Silent (contact anna@mail.invalid)"
reinit(); s, c, _ = appel(CF, jeu=jeu, mois="2026-09")
v("A2b e-mail dans un nom de cours -> 500 JSON, rien servi, rien en cache", s == 500 and "anna@" not in json.dumps(c) and not R._STATS_CACHE, (s, c.get("error")))

# A3 — PAS de verrou global (décision M1) : 30 clés fausses depuis 30 IP falsifiées ne coupent pas la vraie clé
reinit()
for i in range(30):
    appel("x" * 40, h={"CF-Connecting-IP": "198.51.100.%d" % i})
s, c, _ = appel(CK, ip="10.9.9.9")
v("A3 30 clés fausses (IP falsifiées) -> la VRAIE clé finances est toujours servie (aucun déni de service)", s == 200, (s, c.get("error")))
# A3c — par IP : l'en-tête CF-Connecting-IP falsifié contourne le débit par IP
reinit(); ok429 = 0
for i in range(40):
    s, _, _ = appel(CF, h={"CF-Connecting-IP": "192.0.2.%d" % i})
    ok429 += (s == 429)
v("A3c débit par IP contournable en changeant CF-Connecting-IP (40 appels, 0 x 429) — attendu documenté", ok429 == 0, ok429)

# A4 — cache : finances puis fréquentation, même mois ; puis mois différent ; puis granularité
reinit()
_, c1, _ = appel(CK, mois="2026-09"); _, c2, _ = appel(CF, mois="2026-09")
v("A4 cache finances ne nourrit pas la fréquentation", c2["portee"] == "frequentation" and c2["revenus"].get("disponible") is False)
_, c3, _ = appel(CF, mois="2026-08")
v("A4b cache séparé par mois", c3["periode"]["debut"] == "2026-08-01")
_, c4, _ = appel(CF, mois="2026-09", granularite="jour")
v("A4c cache séparé par granularité", c4["evolution"]["granularite"] == "jour")
# mois="" et mois=2026-10 partagent la même clé (même mois) : attendu
# A4d — base en panne : pas de cache d'échec
reinit()
b = F.Base(F.jeu_de_base()); b.panne = True; F.installer_serveur(b, "")
r = F.run(R.stats_association(F.Req({"Authorization": "Bearer " + CF}), mois="2026-09"))
v("A4d base en panne -> pas de chiffre et rien en cache", not R._STATS_CACHE and json.loads(r.body)["frequentation"]["disponible"] is False)

# A5 — clés
reinit(); os.environ[R.STATS_ENV_FINANCES] = "a" * 31; os.environ[R.STATS_ENV_FREQUENTATION] = ""
s, c, _ = appel("a" * 31, mois="2026-09")
v("A5 clé posée de 31 caractères = absente -> 503 JSON", s == 503 and c.get("error") == "stats_non_configurees", (s, c))
os.environ[R.STATS_ENV_FREQUENTATION] = CF; os.environ[R.STATS_ENV_FINANCES] = CK
for hdr in ({"Authorization": "Basic " + CK}, {"Authorization": CK}, {"X-Api-Key": CK}, {"Authorization": "Bearer " + CK[:-1]},
            {"Authorization": "Bearer " + CK + "x"}, {"Authorization": "Bearer " + CK.upper()}):
    reinit(); s, c, _ = appel(None, h=hdr, mois="2026-09")
    v("A5b refus %s -> 401 JSON" % list(hdr.values())[0][:12], s == 401 and c.get("error") == "cle_invalide", s)
reinit(); s, c, _ = appel(None, h={"authorization": "bearer   " + CK + "  "}, mois="2026-09")
v("A5c 'bearer' minuscule + espaces acceptés (tolérance, pas une faille)", s == 200 and c["portee"] == "finances", s)
# même valeur pour les deux clés -> la portée devient finances (configuration à interdire ?)
os.environ[R.STATS_ENV_FREQUENTATION] = CK
reinit(); s, c, _ = appel(CK, mois="2026-09")
v("A5d clés identiques posées par erreur -> 503 configuration_invalide", s == 503 and c.get("error") == "configuration_invalide", (s, c.get("error")))
os.environ[R.STATS_ENV_FREQUENTATION] = CF

# A6 — paramètres invalides -> 400 JSON
for p in (dict(mois="2026-13"), dict(mois="2026-1"), dict(mois="26-09"), dict(annee="abc"), dict(annee="1999"),
          dict(mois="2026-09", annee="2026"), dict(granularite="heure"), dict(mois="2026-09'; --"), dict(mois="2026-00")):
    reinit(); s, c, _ = appel(CF, **p)
    v("A6 %s -> 400 JSON" % p, s == 400 and c.get("ok") is False, s)
reinit(); s, c, _ = appel(CF, mois="2026-09\n")
v("A6b mois='2026-09\\n' -> 400 JSON (ASCII strict, pas de saut final)", s == 400, s)
for _pp in (dict(mois="٢٠٢٦-٠٩"), dict(annee="٢٠٢٦")):
    reinit()
    try:
        s, c, _ = appel(CF, **_pp)
    except Exception as _e:
        s = "EXCEPTION NON GEREE (500 non JSON) %s" % type(_e).__name__
    v("A6c chiffres arabes-indiens %s -> 400 JSON attendu" % _pp, s == 400, s)

# A7 — aucune écriture sur tout le chemin (y compris clôture, panne de bloc)
reinit(); jeu = F.jeu_de_base(); jeu["analytics_monthly_reports"] = [snap]
s, c, b = appel(CK, jeu=jeu, annee="2026")
v("A7 aucune écriture (année + clôtures, finances)", not b.ecritures and s == 200, b.ecritures)

ok = sum(1 for _, c, _ in RES if c)
for n, c, d in RES:
    print("  %s  %s%s" % ("OK  " if c else "ECHEC", n, ("  <- " + str(d)) if (d != "" and not c) else ""))
print("\n%d/%d" % (ok, len(RES)))
sys.exit(0 if ok == len(RES) else 1)

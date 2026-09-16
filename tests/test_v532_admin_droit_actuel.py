"""V532 — admin Codes promo : « abonnement actuel » vs « historique » vs « à vérifier ».
Banc PUR : aucune base, aucun réseau, aucune écriture. Les fonctions sont importées
telles quelles depuis api/routes/shared.py (règles canoniques LOT A rejouées).
Lancer : python3 tests/test_v532_admin_droit_actuel.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.routes.shared import v532_classer_fiches, V532_ACTUEL, V532_HISTORIQUE, V532_A_VERIFIER

AUJ = "2026-09-16"
OK = 0; TOTAL = 0
def verifier(nom, cond, detail=""):
    global OK, TOTAL
    TOTAL += 1; OK += bool(cond)
    print(("  PASS  " if cond else "  FAIL  ") + nom + ("" if cond else f"   -> {detail}"))

def fiche(id, code, used, mx, exp, active=True, **k):
    d = {"id": id, "code": code, "used": used, "maxUses": mx, "expiresAt": exp, "active": active}
    d.update(k); return d

# ── CAS E : Amanda, données réelles rejouées (3 fiches, 2 codes) ─────────────
amanda_b09 = [fiche("8f4fb225", "BASSBOOSTX-09", 31, 47, "2026-05-05", active=False, canonical=False),
              fiche("d5737a11", "BASSBOOSTX-09", 8, 10, "2026-08-17", canonical=True)]
amanda_26  = [fiche("086e316f", "AmandaBoost-26", 8, 9, "2026-10-05")]
abos_26 = [{"status": "completed", "used_sessions": 9, "remaining_sessions": 0}]  # compteur dérivé faux (V531)
r09 = v532_classer_fiches(amanda_b09, [{"status": "completed", "used_sessions": 10, "remaining_sessions": 0}], 0, AUJ)
r26 = v532_classer_fiches(amanda_26, abos_26, 0, AUJ)
verifier("E1. AmandaBoost-26 = ACTUEL", r26["086e316f"]["classement"] == V532_ACTUEL, r26)
verifier("E2. compteurs canoniques 8 / 9, restant 1", (r26["086e316f"]["utilise"], r26["086e316f"]["total"], r26["086e316f"]["restant"]) == (8, 9, 1), r26)
verifier("E3. BASSBOOSTX-09 (8/10, expiré 17.08) = HISTORIQUE motif expire", r09["d5737a11"]["classement"] == V532_HISTORIQUE and r09["d5737a11"]["motif"] == "expire", r09)
verifier("E4. BASSBOOSTX-09 (fiche inactive 31/47) = HISTORIQUE motif inactif", r09["8f4fb225"]["classement"] == V532_HISTORIQUE and r09["8f4fb225"]["motif"] == "inactif", r09)
verifier("E5. aucun ACTUEL parmi les fiches BASSBOOSTX-09", all(v["classement"] != V532_ACTUEL for v in r09.values()))

# ── CAS A : 1 actif + 2 historiques (même code, fiches mortes) ───────────────
a = [fiche("h1", "PACK-A", 10, 10, "2026-03-01"), fiche("h2", "PACK-A", 5, 5, "2026-06-01"), fiche("ok", "PACK-A", 2, 8, "2026-12-31")]
ra = v532_classer_fiches(a, [], 0, AUJ)
verifier("A1. exactement 1 fiche ACTUEL", [k for k, v in ra.items() if v["classement"] == V532_ACTUEL] == ["ok"], ra)
verifier("A2. 2 fiches HISTORIQUE", sum(v["classement"] == V532_HISTORIQUE for v in ra.values()) == 2, ra)
verifier("A3. aucune fiche perdue (3 étiquettes pour 3 fiches)", len(ra) == 3)

# ── CAS B : 2 codes valides simultanés d'une même personne → 2 ACTUELS, rien fusionné
b1 = v532_classer_fiches([fiche("b1", "CODE-B1", 1, 8, "2026-12-31")], [], 0, AUJ)
b2 = v532_classer_fiches([fiche("b2", "CODE-B2", 0, 4, "2026-11-30")], [], 0, AUJ)
verifier("B1. les deux codes sont ACTUEL chacun", b1["b1"]["classement"] == V532_ACTUEL and b2["b2"]["classement"] == V532_ACTUEL)
verifier("B2. compteurs distincts conservés", (b1["b1"]["restant"], b2["b2"]["restant"]) == (7, 4))

# ── CAS C : ancien expiré + nouveau actif (codes différents) → nouveau = actuel
c_old = v532_classer_fiches([fiche("c0", "OLD", 8, 8, "2026-01-01")], [], 0, AUJ)
c_new = v532_classer_fiches([fiche("c1", "NEW", 0, 8, "2026-12-01")], [], 0, AUJ)
verifier("C1. ancien = HISTORIQUE", c_old["c0"]["classement"] == V532_HISTORIQUE)
verifier("C2. nouveau = ACTUEL", c_new["c1"]["classement"] == V532_ACTUEL)

# ── CAS D : vrai doublon technique (2 fiches VIVANTES, même code, aucun canonique)
d = [fiche("d1", "DOUBLE", 9, 45, "2026-12-31"), fiche("d2", "DOUBLE", 6, 12, "2026-12-31")]
rd = v532_classer_fiches(d, [], 0, AUJ)
verifier("D1. aucune ACTUEL (on ne devine pas)", all(v["classement"] != V532_ACTUEL for v in rd.values()), rd)
verifier("D2. les deux = À VÉRIFIER, motif plusieurs_docs_code", all(v["classement"] == V532_A_VERIFIER and v["motif"] == "plusieurs_docs_code" for v in rd.values()), rd)
verifier("D3. les deux fiches restent présentes (aucune suppression)", len(rd) == 2)
# doublon avec canonique tranché par l'humain → l'actuel est celui-là, l'autre reste visible
d2 = [fiche("d1", "DOUBLE", 9, 45, "2026-12-31"), fiche("d2", "DOUBLE", 6, 12, "2026-12-31", canonical=True)]
rd2 = v532_classer_fiches(d2, [], 0, AUJ)
verifier("D4. canonique tranché -> d2 ACTUEL, d1 HISTORIQUE (remplacé), rien supprimé",
         rd2["d2"]["classement"] == V532_ACTUEL and rd2["d1"]["classement"] == V532_HISTORIQUE and rd2["d1"]["motif"] == "remplace", rd2)

# ── Épuisé : 9/9 vivant par la date mais sans droit → HISTORIQUE motif epuise
r_ep = v532_classer_fiches([fiche("e", "FULL", 9, 9, "2026-12-31")], [], 0, AUJ)
verifier("F1. 9/9 = HISTORIQUE motif epuise", r_ep["e"]["classement"] == V532_HISTORIQUE and r_ep["e"]["motif"] == "epuise", r_ep)
# ── Divergence bloquante (LOT A) → à vérifier, jamais un chiffre inventé
r_div = v532_classer_fiches([fiche("g", "DIV", 3, 9, "2026-12-31")], [{"status": "active", "used_sessions": 9, "remaining_sessions": 0}], 0, AUJ)
verifier("G1. AMBIGU divergence_bloquante -> À VÉRIFIER", r_div["g"]["classement"] == V532_A_VERIFIER and r_div["g"]["motif"] == "divergence_bloquante", r_div)
# ── Structure : la fonction est pure (mêmes entrées -> mêmes sorties, entrées intactes)
avant = [dict(x) for x in amanda_26]; v532_classer_fiches(amanda_26, abos_26, 0, AUJ)
verifier("S1. les fiches d'entrée ne sont pas modifiées", amanda_26 == avant)
verifier("S2. liste vide -> {}", v532_classer_fiches([], [], 0, AUJ) == {})

print(f"\n{OK}/{TOTAL} — V532 admin droit actuel (pur, 0 base, 0 réseau, 0 écriture)")
sys.exit(0 if OK == TOTAL else 1)

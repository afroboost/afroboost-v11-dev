# -*- coding: utf-8 -*-
"""ANALYTICS PHASE 1 — `est_un_essai` AVANT (git HEAD) et APRÈS (arbre de travail)
sont la MÊME fonction : mêmes verdicts ET mêmes lectures base, dans le même ordre,
sur une matrice exhaustive d'entrées.

Pourquoi ce banc existe : `est_un_essai` est une règle de production (annulation
T1, relances P1-b/P1-d, auto-présence, conversion, création de réservation).
Le cockpit a besoin de la même règle EN MÉMOIRE (`essai6_verdict`) ; pour n'avoir
qu'UNE définition, `est_un_essai` délègue ses prédicats P2/P3 au pur. Ce banc
prouve que le chemin d'exécution historique n'a pas bougé.

    python3 tests/test_essai6_equivalence_refactor.py
"""
import ast, asyncio, io, itertools, os, subprocess, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


def _extraire(src, nom, sans_docstring=False):
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            if sans_docstring and n.body and isinstance(n.body[0], ast.Expr) \
               and isinstance(getattr(n.body[0], "value", None), ast.Constant):
                n.body = n.body[1:]
            return ast.unparse(n)
    raise AssertionError(nom)


# ── AVANT : la fonction telle qu'elle était AVANT le refactor de la phase 1 ──
# Référence FIGÉE : le parent du commit qui a introduit `essai6_verdict`
# (`bd3b8903` = feat(analytics) phase 1). Comparer à HEAD n'a de sens qu'avant
# ce commit ; depuis, HEAD contient le refactor et le banc se comparerait à
# lui-même. La règle essai ne change pas pour satisfaire ce banc : c'est le
# banc qui compare les bonnes versions.
REF_AVANT = "bd3b8903^"
SRC_AVANT = subprocess.check_output(["git", "-C", RACINE, "show", REF_AVANT + ":api/routes/shared.py"]).decode("utf-8")
SRC_APRES = io.open(os.path.join(RACINE, "api", "routes", "shared.py"), encoding="utf-8").read()
verifier("la référence %s ne connaît pas encore essai6_verdict (c'est bien la version d'avant)" % REF_AVANT,
         "def essai6_verdict" not in SRC_AVANT)
verifier("l'arbre de travail porte bien le refactor (essai6_verdict présent)", "def essai6_verdict" in SRC_APRES)

import api.routes.shared as S   # la version APRÈS, réelle


class _Log:
    def __init__(self): self.lignes = []
    def warning(self, *a, **k): self.lignes.append(a)
    info = warning


def charger_avant():
    env = {"ESSAI2_FILTRE_GRATUIT": S.ESSAI2_FILTRE_GRATUIT, "ESSAI6_ORIGINE_OFFERTE": S.ESSAI6_ORIGINE_OFFERTE,
           "logger": _Log()}
    exec(compile(_extraire(SRC_AVANT, "est_un_essai"), "<avant>", "exec"), env)
    return env["est_un_essai"]


def _filtre_ok(d, f):
    for k, v in f.items():
        if k == "$or":
            if not any(_filtre_ok(d, alt) for alt in v):
                return False
        elif d.get(k) != v:
            return False
    return True


class _Coll:
    def __init__(self, nom, docs, journal):
        self.nom, self.docs, self.journal = nom, docs, journal
    async def find_one(self, f, p=None):
        self.journal.append((self.nom, tuple(sorted(f.keys()))))
        for d in self.docs:
            if _filtre_ok(d, f):
                return dict(d)
        return None


class _DB:
    def __init__(self, subs, codes, offers):
        self.journal = []
        self._c = {"subscriptions": _Coll("subscriptions", subs, self.journal),
                   "discount_codes": _Coll("discount_codes", codes, self.journal),
                   "offers": _Coll("offers", offers, self.journal)}
    def __getitem__(self, n): return self._c[n]


est_un_essai_avant = charger_avant()
est_un_essai_apres = S.est_un_essai

# ── la matrice : fiche code × forfait × offre × mode d'appel ──
FICHES = [None,
          {"code": "X", "payment_method": "free", "total_paid": 0},          # P1 vrai
          {"code": "X", "source": "social_proof"},                          # P1 vrai (2e branche)
          {"code": "X", "payment_method": "free", "total_paid": 30},         # P1 faux
          {"code": "X", "payment_method": "card", "total_paid": 0}]          # P1 faux
FORFAITS = [None,
            {"code": "X", "origine_paiement": "offert"},                     # P2 vrai
            {"code": "X", "origine_paiement": "OFFERT "},                    # P2 vrai (casse/espace)
            {"code": "X", "origine_paiement": "twint", "offer_id": "o"},      # -> P3
            {"code": "X", "offer_id": "o"},                                  # -> P3
            {"code": "X", "offer_id": "absente"},                            # offre introuvable
            {"code": "X"}]                                                   # rien
OFFRES = [[], [{"id": "o", "price": 0}], [{"id": "o", "price": 0.0}], [{"id": "o", "price": 150}], [{"id": "o", "price": "abc"}]]
MODES = ["code", "forfait", "les_deux", "code_vide"]

n_cas, n_ok, n_journal_ok = 0, 0, 0
divergences = []
for fiche, forfait, offres, mode in itertools.product(FICHES, FORFAITS, OFFRES, MODES):
    subs = [forfait] if forfait else []
    codes = [fiche] if fiche else []
    if mode == "code":
        args = dict(code="X")
    elif mode == "forfait":
        args = dict(forfait=forfait)
    elif mode == "les_deux":
        args = dict(forfait=forfait, code="X")
    else:
        args = dict(code="")
    dba, dbb = _DB(subs, codes, offres), _DB(subs, codes, offres)
    va = run(est_un_essai_avant(dba, **args))
    vb = run(est_un_essai_apres(dbb, **args))
    n_cas += 1
    if va == vb:
        n_ok += 1
    else:
        divergences.append((fiche, forfait, offres, mode, va, vb))
    if dba.journal == dbb.journal:
        n_journal_ok += 1
    else:
        divergences.append(("JOURNAL", fiche, forfait, offres, mode, dba.journal, dbb.journal))

verifier("matrice exhaustive : %d cas" % n_cas, n_cas == len(FICHES) * len(FORFAITS) * len(OFFRES) * len(MODES))
verifier("AVANT == APRÈS sur TOUS les verdicts (%d/%d)" % (n_ok, n_cas), n_ok == n_cas, divergences[:3])
verifier("AVANT == APRÈS sur TOUTES les lectures base (collection + filtre, même ordre) (%d/%d)" % (n_journal_ok, n_cas),
         n_journal_ok == n_cas, [d for d in divergences if d[0] == "JOURNAL"][:2])

# ── la règle pure dit la même chose que la fonction avec base, sur les mêmes documents ──
n2, ok2 = 0, 0
for fiche, forfait, offres in itertools.product(FICHES, FORFAITS, OFFRES):
    db = _DB([forfait] if forfait else [], [fiche] if fiche else [], offres)
    v_base = run(est_un_essai_apres(db, code="X"))
    offre = next((o for o in offres if o.get("id") == (forfait or {}).get("offer_id")), None)
    v_pur = S.essai6_verdict(fiche, forfait, offre)
    n2 += 1
    ok2 += (v_base == v_pur)
verifier("essai6_verdict (pur) == est_un_essai (base) sur les mêmes documents (%d/%d)" % (ok2, n2), ok2 == n2)

# ── le diff exécutable : rien d'autre que P2/P3 délégués ──
apres = _extraire(SRC_APRES, "est_un_essai", sans_docstring=True)   # le CODE, pas le commentaire
verifier("APRÈS lit toujours P1 en base, en premier, avec le même filtre", 'ESSAI2_FILTRE_GRATUIT' in apres and apres.index("discount_codes") < apres.index("essai6_verdict"))
verifier("APRÈS relit le forfait par code exactement comme avant", "'code': 1, 'offer_id': 1, 'origine_paiement': 1" in apres.replace('"', "'"))
verifier("APRÈS relit l'offre avec la même projection", "'price': 1" in apres.replace('"', "'"))

ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)[:300]) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

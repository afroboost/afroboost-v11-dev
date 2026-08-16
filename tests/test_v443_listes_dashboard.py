# -*- coding: utf-8 -*-
"""V443 — les deux listes du dashboard coach ne mentent plus.

Rien n'est reecrit : `get_reservations` est EXTRAITE de api/routes/reservation_routes.py
par analyse AST et executee telle quelle contre une base factice en memoire. Les
verifications frontend portent sur le texte reellement compile, relu par AST.

Aucun reseau, aucune base reelle, aucun envoi.
Lancement :  python3 tests/test_v443_listes_dashboard.py
"""
import ast, asyncio, io, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACK = os.path.join(RACINE, "api", "routes", "reservation_routes.py")
FRONT = os.path.join(RACINE, "frontend", "src", "components", "CoachDashboard.js")

RESULTATS = []
def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ---------------------------------------------------------------- base factice
class _Curseur:
    def __init__(self, docs): self.d = list(docs)
    def sort(self, *a, **k): return self
    def skip(self, n): self.d = self.d[n:]; return self
    def limit(self, n): self.d = self.d[:n]; return self
    async def to_list(self, n): return [dict(x) for x in self.d[:n]]

class _Collection:
    def __init__(self, docs): self.docs = docs; self.requetes = []
    def _match(self, d, q):
        for k, v in q.items():
            if d.get(k) != v: return False
        return True
    def find(self, q, proj=None):
        self.requetes.append(("find", dict(q)))
        return _Curseur([d for d in self.docs if self._match(d, q)])
    async def count_documents(self, q):
        self.requetes.append(("count", dict(q)))
        return len([d for d in self.docs if self._match(d, q)])

class _Base:
    def __init__(self, docs): self.reservations = _Collection(docs)


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code; self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))

class FausseRequete:
    def __init__(self, headers=None):
        self._h = {k.lower(): v for k, v in (headers or {}).items()}
        self.headers = self
    def get(self, k, d=""): return self._h.get(k.lower(), d)


SOURCE_BACK = io.open(BACK, encoding="utf-8").read()
ARBRE_BACK = ast.parse(SOURCE_BACK)
LIGNES_BACK = SOURCE_BACK.splitlines(True)
SOURCE_FRONT = io.open(FRONT, encoding="utf-8").read()

def _sans_commentaires(js):
    """Le code JS reellement EXECUTE, sans les commentaires.

    Indispensable : les commentaires de V443 CITENT l'ancien filtre supprime pour
    expliquer pourquoi il l'a ete. Une recherche de texte brute y verrait le
    filtre encore present. On ne teste que ce qui tourne.
    (Suffisant ici : le fichier n'a ni `//` ni `/*` a l'interieur d'une chaine sur
    les lignes concernees — verifie par le test _sonde ci-dessous.)"""
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return "\n".join(l for l in js.splitlines() if not l.strip().startswith("//"))

FRONT_EXEC = _sans_commentaires(SOURCE_FRONT)

ADMIN = "contact.artboost@gmail.com"
COACH = "coach.partenaire@example.com"

def extraire(nom):
    for n in ast.walk(ARBRE_BACK):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES_BACK[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)

def construire(docs):
    from datetime import datetime as _dt, timezone as _tz
    base = _Base(docs)
    bac = {
        "db": base, "HTTPException": HTTPException, "Request": FausseRequete,
        "datetime": _dt, "timezone": _tz,
        "is_super_admin": lambda e: (e or "").lower().strip() == ADMIN,
        "reservation_router": type("r", (), {"get": staticmethod(lambda *a, **k: (lambda f: f))}),
    }
    exec(compile(extraire("get_reservations"), "<v443-extrait>", "exec"), bac)
    return bac, base


def docs_prod():
    """128 reservations, toutes au nom de l'admin — comme en production."""
    return [{"id": "r%03d" % i, "coach_id": ADMIN, "reservationCode": "AF%03d" % i,
             "userName": "Client %d" % i, "createdAt": "2026-08-%02dT10:00:00+00:00" % (1 + i % 28)}
            for i in range(128)]


async def scenario():
    # --- 1. identite valide -> la liste historique, a l'identique
    bac, base = construire(docs_prod())
    r = await bac["get_reservations"](FausseRequete({"X-User-Email": ADMIN}), page=1, limit=20)
    verifier("1. admin -> 20 reservations sur la page 1",
             len(r["data"]) == 20, str(len(r["data"])))
    verifier("1b. admin -> total = 128", r["pagination"]["total"] == 128, str(r["pagination"]))
    verifier("1c. admin -> requete NON filtree (super-admin voit tout)",
             base.reservations.requetes[0][1] == {}, str(base.reservations.requetes[0]))

    # --- 2. coach non-admin : filtre sur SON coach_id, comportement inchange
    bac, base = construire(docs_prod() + [{"id": "x1", "coach_id": COACH, "createdAt": "2026-08-01T10:00:00+00:00"}])
    r = await bac["get_reservations"](FausseRequete({"X-User-Email": COACH}), page=1, limit=20)
    verifier("2. coach -> ne voit QUE ses reservations",
             r["pagination"]["total"] == 1 and all(d.get("id") == "x1" for d in r["data"]), str(r["pagination"]))
    verifier("2b. coach -> requete filtree sur son coach_id",
             base.reservations.requetes[0][1] == {"coach_id": COACH}, str(base.reservations.requetes[0]))

    # --- 3. identite absente -> REFUS EXPLICITE, jamais une liste vide
    for nom, h in (("aucun en-tete", {}),
                   ("en-tete vide", {"X-User-Email": ""}),
                   ("en-tete d'espaces", {"X-User-Email": "   "})):
        bac, base = construire(docs_prod())
        try:
            r = await bac["get_reservations"](FausseRequete(h), page=1, limit=20)
            verifier("3. %s -> refus explicite" % nom, False,
                     "AUCUN refus : a renvoye %d element(s), total=%s"
                     % (len(r.get("data") or []), (r.get("pagination") or {}).get("total")))
        except HTTPException as e:
            verifier("3. %s -> refus explicite" % nom, e.status_code == 403, str(e.status_code))
            verifier("3b. %s -> la base n'est meme pas interrogee" % nom,
                     base.reservations.requetes == [], str(base.reservations.requetes))

    # --- 4. le sentinelle qui fabriquait la fausse liste vide a disparu
    src = extraire("get_reservations")
    corps = [x for x in ast.walk(ast.parse(src))]
    litteraux = [x.value for x in corps if isinstance(x, ast.Constant) and isinstance(x.value, str)]
    verifier("4. plus aucun sentinelle '__no_access__' EXECUTE",
             "__no_access__" not in [l for l in litteraux], str([l for l in litteraux if "no_access" in l]))

    # --- 5. aucune erreur d'auth ne peut redevenir une liste vide
    verifier("5. le refus precede toute construction de requete",
             src.index("raise HTTPException") < src.index("base_query ="), "")

    # --- 6. la strategie d'AUTH n'a pas change (point 4 NON touche)
    for interdit in ("coach_jwt_email", "_v311_coach_email_from_jwt", "_v319_coach_identity",
                     "v20_exiger_coach_signe", "Authorization", "jwt", "Bearer"):
        verifier("6. auth inchangee : %s absent de get_reservations" % interdit,
                 interdit not in src, interdit)
    verifier("6b. l'identite reste X-User-Email, comme avant",
             'request.headers.get("X-User-Email"' in src, "")


def tests_frontend():
    # --- A. le filtre client sur les codes promo a disparu
    # sonde du depouilleur lui-meme : il doit retirer les commentaires SANS
    # amputer le code (sinon tous les tests suivants seraient faussement verts).
    verifier("A0. le depouilleur de commentaires est fiable",
             "setDiscountCodes" in FRONT_EXEC and "Promise.allSettled" in FRONT_EXEC
             and "c.createdBy" in SOURCE_FRONT, "")
    verifier("A1. plus de filtre `createdBy` dans le code EXECUTE",
             "c.createdBy" not in FRONT_EXEC, "")
    verifier("A2. les codes promo sont poses tels que le backend les rend",
             "appliquer('Codes promo', cds, (r) => setDiscountCodes(r.data))" in SOURCE_FRONT, "")

    # --- B. le chargement est decouple
    bloc = SOURCE_FRONT[SOURCE_FRONT.index("const loadData = async"):]
    bloc = bloc[:bloc.index("loadData();")]
    verifier("B1. plus de Promise.all tout-ou-rien dans loadData",
             "Promise.all(" not in bloc, "")
    verifier("B2. Promise.allSettled est utilise", "Promise.allSettled(" in bloc, "")
    for section in ("Réservations", "Cours", "Offres", "Utilisateurs",
                    "Liens de paiement", "Vitrine", "Codes promo"):
        verifier("B3. « %s » alimente son etat independamment" % section,
                 ("appliquer('%s'" % section) in bloc, "")
    verifier("B4. un `poser` qui leve n'emporte pas les autres (try/catch interne)",
             "reponse.status !== 'fulfilled'" in bloc and "catch (e)" in bloc, "")
    verifier("B5. les echecs sont collectes, pas seulement journalises",
             "echecs.push" in bloc and "setV443Echecs(echecs)" in bloc, "")

    # --- C. l'erreur est VISIBLE, pas seulement dans la console
    verifier("C1. un bandeau d'erreur existe dans le rendu",
             'data-testid="v443-bandeau-echec"' in SOURCE_FRONT, "")
    verifier("C2. il est conditionne aux echecs reels",
             "v443Echecs.length > 0 &&" in SOURCE_FRONT, "")
    verifier("C3. il porte role=alert (lecteurs d'ecran)", 'role="alert"' in SOURCE_FRONT, "")
    verifier("C4. il nomme les sections concernees",
             "v443Echecs.join(', ')" in SOURCE_FRONT, "")

    # --- D. regle anti-boucle : l'etat du bandeau n'entre dans AUCUN tableau
    #        de dependances (sinon chaque ecriture relancerait les effets).
    #        On inspecte les vrais tableaux `}, [ ... ])`, pas le texte brut :
    #        `const [v443Echecs, setV443Echecs]` est une destructuration, pas
    #        une dependance.
    deps = re.findall(r"\}\s*,\s*\[([^\]]*)\]\s*\)", FRONT_EXEC)
    fautifs = [d.strip() for d in deps if "v443Echecs" in d]
    verifier("D1. v443Echecs n'entre dans aucun tableau de dependances",
             fautifs == [], " | ".join(fautifs))
    verifier("D2. le useEffect de chargement garde ses dependances vides",
             "loadData();\n  }, []);" in FRONT_EXEC, "")

    # --- E. le crash latent sur une identite absente est neutralise
    verifier("E1. `safeCoachUser?.email.toLowerCase()` non garde a disparu",
             "safeCoachUser?.email.toLowerCase()" not in SOURCE_FRONT, "")

    # --- F. aucune garde backend de securite rouverte, aucun autre domaine touche
    import subprocess
    diff = subprocess.check_output(["git", "diff", "--name-only", "79cdddf"], cwd=RACINE).decode()
    touches = sorted(f for f in diff.split() if f)
    attendus = ["api/routes/reservation_routes.py", "frontend/src/components/CoachDashboard.js"]
    verifier("F1. seuls 2 fichiers applicatifs modifies", touches == attendus, str(touches))
    for domaine in ("promo_routes", "stripe", "checkout", "campaign", "whatsapp",
                    "contact", "auth_routes", "cinetpay", "pawapay"):
        verifier("F2. aucun fichier %s touche" % domaine,
                 not any(domaine in f for f in touches), str(touches))


def main():
    tests_frontend()
    asyncio.get_event_loop().run_until_complete(scenario())
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 76)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 76)
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

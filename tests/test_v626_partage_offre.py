"""V626 — la page d'aperçu de partage d'une offre ne publie plus une offre masquée.

`/api/share/offer/<id>` (V278) sert les balises og:* lues par WhatsApp/Facebook.
Elle publiait nom, prix, description et image de N'IMPORTE QUELLE offre. Avec les
boutons « Copier le lien » / « Partager » de chaque offre (V626), on verrouille :
  - offre visible       -> aperçu + redirection vers /?offre=<id> ;
  - offre privée (link_only) -> aperçu (son lien est son accès voulu, V537) ;
  - offre masquée, archivée, inconnue -> redirection vers l'accueil, AUCUNE donnée.

Exécution : python3 tests/test_v626_partage_offre.py (aucun réseau, base factice).
"""
import ast
import asyncio
import os
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(keepends=True)
OK, KO = [], []


def v(nom, cond, detail=""):
    (OK if cond else KO).append(nom)
    print(("  OK    " if cond else "  RATE  ") + nom + ("" if cond else "  [%s]" % (detail,)))


class Coll:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, filtre, projection=None):
        for d in self.docs:
            if all(d.get(k) == val for k, val in filtre.items()):
                return dict(d)
        return None


class Base:
    def __init__(self, offres):
        self.offers = Coll(offres)


def monter(db):
    ns = {"db": db, "logger": None}
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "share_offer_page":
            exec(compile("".join(LIGNES[n.lineno - 1:n.end_lineno]), "share", "exec"), ns)
    return ns["share_offer_page"]


async def principal():
    offres = [
        {"id": "o-visible", "name": "Mensuel Liberté", "price": 89, "visible": True, "description": "Accès mensuel."},
        {"id": "o-prive", "name": "Offre privée", "price": 40, "visible": True, "link_only": True},
        {"id": "o-masque", "name": "Offre SECRETE masquée", "price": 12, "visible": False, "description": "ne doit pas fuir"},
        {"id": "o-archive", "name": "Offre ARCHIVEE", "price": 5, "visible": True, "archived": True},
    ]
    page = monter(Base(offres))

    r = await page("o-visible")
    corps = r.body.decode("utf-8")
    v("offre visible : aperçu OG (nom, prix)", r.status_code == 200 and "Mensuel Liberté" in corps and "89" in corps)
    v("offre visible : redirige vers /?offre=<id>", "afroboost.com/?offre=o-visible" in corps)

    r = await page("o-prive")
    v("offre privée (link_only) : aperçu conservé", r.status_code == 200 and "Offre privée" in r.body.decode("utf-8"))

    for oid, mot in (("o-masque", "SECRETE"), ("o-archive", "ARCHIVEE"), ("inconnue", "")):
        r = await page(oid)
        corps = r.body.decode("utf-8") if getattr(r, "body", None) else ""
        v("%s : redirection vers l'accueil (302)" % oid,
          r.status_code == 302 and r.headers.get("location") == "https://afroboost.com")
        if mot:
            v("%s : aucune donnée publiée" % oid, mot not in corps and "ne doit pas fuir" not in corps)

    print("\n%d/%d au vert" % (len(OK), len(OK) + len(KO)))
    return not KO


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(principal()) else 1)

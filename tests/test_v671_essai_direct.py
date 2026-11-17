"""V671 — « Réserver mon 1er cours gratuit » mène au FORMULAIRE, pas au chat.

CE QUE CE BANC PROTEGE. Deux boutons menaient encore au tunnel de discussion :
le CTA du Hero et celui de `/a-propos`. Mesure du 17/11/2026 sur la production :
la page `/cours-essai-gratuit-neuchatel` envoyait DEJA tout le monde droit au
formulaire (V622) — ces deux-la etaient restes en arriere. `/essai` les aligne.

LE RISQUE QUE CES TESTS COUVRENT, et qui n'est pas le plus evident : le bouton
du Hero vit dans le navigateur. Y recopier l'identifiant de l'offre gratuite
aurait cree une seconde verite, qui serait devenue FAUSSE EN SILENCE le jour ou
l'offre d'essai change dans le tableau de bord. `/essai` resout l'offre sur le
lien d'essai lui-meme ; on verifie donc surtout le REPLI (offre absente,
payante, base muette, exception) — car c'est lui qui decide si un bouton peut
devenir mort.

Execution : python3 tests/test_v671_essai_direct.py (aucun reseau, base factice).
Depuis la racine du depot — la fonction importe `api.routes.shared` elle-meme,
exactement comme en production.
"""
import ast
import asyncio
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(keepends=True)
OK, KO = [], []

TUNNEL = "/?link=b83914b4-c5a"
OFFRE = "c1e5f73c-0f16-402e-a746-2041e23f72e8"
CIBLE_NUE = "/?offre=%s&reserver=1&parcours=essai" % OFFRE


def v(nom, cond, detail=""):
    (OK if cond else KO).append(nom)
    print(("  OK    " if cond else "  RATE  ") + nom + ("" if cond else "  [%s]" % (detail,)))


def source_de(nom):
    """Le texte d'une fonction, SANS son decorateur de route."""
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    return ""


class Journal:
    def __init__(self):
        self.avertissements = []

    def warning(self, *a, **k):
        self.avertissements.append(a[0] if a else "")

    def info(self, *a, **k):
        pass


class Req:
    """Juste ce que la fonction lit d'une requete : la requete et le referrer."""

    def __init__(self, params=None, referer=None):
        from starlette.datastructures import QueryParams, Headers
        self.query_params = QueryParams(params or "")
        self.headers = Headers({"referer": referer} if referer else {})


def monter(offre=OFFRE, journal=None, offres_explose=False):
    """La vraie fonction `v671_essai_direct`, avec un resolveur factice.

    On n'injecte PAS `m2a_attribution_entrante` : la fonction doit l'importer
    elle-meme, comme en production. C'est ainsi qu'un import oublie se voit.
    """
    async def _offres_factice():
        if offres_explose:
            raise RuntimeError("base muette")
        return {"offres": [{"id": OFFRE, "price": 0}]}

    async def _resolveur_factice(catalogue):
        return offre

    # `Request` DOIT etre dans l'espace de noms : l'annotation de la signature
    # est evaluee a la DEFINITION de la fonction. On fournit la vraie classe
    # Starlette — celle que FastAPI resoudra en production — comme le fait deja
    # `tests/test_m1_page_seo_locale.py` pour la page d'essai.
    from starlette.requests import Request as _Request
    ns = {
        "_M1_TUNNEL": TUNNEL,
        "_V671_CHEMIN": "/essai",
        "_m1_offres": _offres_factice,
        "_v594_offre_du_tunnel_essai": _resolveur_factice,
        "logger": journal,
        "Request": _Request,
    }
    exec(compile(source_de("v671_essai_direct"), "essai", "exec"), ns)
    return ns["v671_essai_direct"]


async def essai(params=None, referer=None, offre=OFFRE, journal=None, offres_explose=False):
    """(cible de la redirection, reponse, journal)."""
    j = Journal() if journal is None else journal
    rep = await monter(offre=offre, journal=j, offres_explose=offres_explose)(Req(params, referer))
    return rep.headers.get("location", ""), rep, j


async def principal():
    print("\n--- 1. LA ROUTE EXISTE ET EST DECLAREE ---")
    src = source_de("v671_essai_direct")
    v("1. la fonction `v671_essai_direct` existe", bool(src))
    v("2. elle recoit la requete", "request: Request" in src)
    dec = ""
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "v671_essai_direct":
            dec = "".join(LIGNES[min(d.lineno for d in n.decorator_list) - 1:n.lineno - 1])
    v("3. elle est bien montee sur `_V671_CHEMIN`", "_V671_CHEMIN" in dec, dec.strip())
    v("4. le chemin vaut « /essai »", '_V671_CHEMIN = "/essai"' in SRC)

    print("\n--- 2. LE CHEMIN NORMAL : DROIT AU FORMULAIRE ---")
    cible, rep, j = await essai()
    v("5. redirection 302", rep.status_code == 302, rep.status_code)
    v("6. la cible est le parcours EXISTANT (offre + reserver + parcours)",
      cible == CIBLE_NUE, cible)
    v("7. l'identifiant d'offre vient du resolveur, pas du code", OFFRE in cible)
    v("8. aucun avertissement : l'offre a vraiment ete resolue", j.avertissements == [],
      j.avertissements)

    print("\n--- 3. L'ORIGINE SURVIT ---")
    cible, _, _ = await essai(referer="https://l.instagram.com/")
    v("9. Instagram SANS UTM : la source arrive par le referrer",
      "utm_source=instagram" in cible and "utm_medium=social" in cible, cible)
    v("10. ... et l'organique n'est JAMAIS du payant", "utm_medium=paid" not in cible, cible)
    cible, _, _ = await essai(params="utm_source=instagram&utm_medium=paid&utm_campaign=hiver")
    v("11. une campagne payante explicite est respectee",
      "utm_medium=paid" in cible and "utm_campaign=hiver" in cible, cible)
    cible, _, _ = await essai(params="utm_source=whatsapp", referer="https://l.instagram.com/")
    v("12. l'UTM explicite gagne sur le referrer",
      "utm_source=whatsapp" in cible and "instagram" not in cible, cible)
    cible, _, _ = await essai(referer="https://afroboost.com/a-propos")
    v("13. referrer INTERNE : aucune source inventee", cible == CIBLE_NUE, cible)
    cible, _, _ = await essai(params="utm_source=nimportequoi")
    v("14. source hors liste fermee : refusee", cible == CIBLE_NUE, cible)
    cible, _, _ = await essai()
    v("15. rien a signaler : la cible reste nue", cible == CIBLE_NUE, cible)

    print("\n--- 4. L'URL EST BIEN FORMEE (le piege le plus facile) ---")
    cible, _, _ = await essai(referer="https://l.instagram.com/")
    v("16. `&amp;` ne doit JAMAIS entrer dans un en-tete Location",
      "&amp;" not in cible, cible)
    v("17. un seul « ? » dans la cible", cible.count("?") == 1, cible)
    v("18. aucun parametre vide", not re.search(r"[?&]=|=&|=$", cible), cible)
    cible, _, _ = await essai(params="utm_campaign=%3Cimg%20onerror%3D1%3E&utm_source=instagram")
    v("19. injection impossible : aucun caractere d'echappement HTML",
      not (set('<>"\'') & set(cible)), cible)

    print("\n--- 5. LE REPLI : LE BOUTON NE PEUT PAS DEVENIR MORT ---")
    cible, rep, j = await essai(offre="")
    v("20. offre introuvable ou payante -> le tunnel, comme AUJOURD'HUI",
      cible == TUNNEL, cible)
    v("21. ... et c'est toujours un 302", rep.status_code == 302, rep.status_code)
    cible, rep, j = await essai(offres_explose=True)
    v("22. base muette -> le tunnel, aucune exception ne remonte",
      cible == TUNNEL, cible)
    v("23. ... et l'incident est journalise", any("V671" in a for a in j.avertissements),
      j.avertissements)
    # Les bancs de ce depot montent les fonctions avec `logger = None` : un
    # journal absent ne doit pas transformer un repli en panne.
    rep0 = await monter(journal=None, offres_explose=True)(Req())
    v("24. journal absent (`logger = None`) : repli quand meme, aucun crash",
      rep0.headers.get("location") == TUNNEL, rep0.headers.get("location"))

    print("\n--- 6. LES EN-TETES ---")
    _, rep, _ = await essai(referer="https://l.instagram.com/")
    v("25. `Cache-Control: no-store`", rep.headers.get("cache-control") == "no-store",
      rep.headers.get("cache-control"))
    v("26. `Vary: Referer` — une cible qui depend du referrer n'est jamais partagee",
      rep.headers.get("vary") == "Referer", rep.headers.get("vary"))

    print("\n--- 7. LE BOUTON DE /a-propos SUIT LE MEME CHEMIN ---")
    sgl = source_de("_seo_geo_lien_essai")
    v("27. il part de `_V671_CHEMIN`, plus du tunnel",
      "_lien = _V671_CHEMIN" in sgl and "_lien = _M1_TUNNEL" not in sgl)
    v("28. le separateur est « ? » (adresse nue), pas « & »",
      '_V671_CHEMIN + "?"' in sgl, sgl[sgl.find("_bouts:"):][:120])
    ns = {"_V671_CHEMIN": "/essai", "_M1_TUNNEL": TUNNEL, "logger": Journal()}
    exec(compile(sgl, "sgl", "exec"), ns)
    f = ns["_seo_geo_lien_essai"]
    v("29. sans origine : l'adresse nue", f(Req(), "/a-propos") == "/essai",
      f(Req(), "/a-propos"))
    lien = f(Req(referer="https://l.instagram.com/"), "/a-propos")
    v("30. depuis Instagram : l'origine voyage DANS le lien",
      lien.startswith("/essai?") and "utm_source=instagram" in lien, lien)
    # En HTML, un `&` nu entre deux parametres est une erreur de balisage : la
    # page d'essai echappe deja ses separateurs, celle-ci doit faire pareil.
    deux = f(Req(params="utm_source=instagram&utm_medium=social"), "/a-propos")
    v("31. deux UTM : le separateur HTML est echappe (`&amp;`), jamais nu",
      deux.count("&amp;") == 1 and not re.search(r"&(?!amp;)", deux), deux)
    v("32. plus aucun renvoi vers le tunnel depuis /a-propos",
      "?link=" not in lien and "?link=" not in f(Req(), "/a-propos"), lien)

    print("\n--- 8. CE QUI NE DOIT PAS AVOIR BOUGE ---")
    v("33. le tunnel EXISTE toujours (l'assistant garde son lien)",
      '_M1_TUNNEL = "/?link=b83914b4-c5a"' in SRC)
    v("34. la page d'essai garde son parcours V622 (`parcours=essai`)",
      "parcours=essai" in SRC)
    # LE CODE EXECUTE, commentaires et docstring exclus. La docstring CITE
    # `POST /checkout/free` — c'est meme l'essentiel de ce qu'elle explique :
    # le moteur d'octroi reste celui-la. Une recherche de texte brute prenait
    # cette explication pour du code (mesure : test 35 en echec au 1er essai).
    _sans_doc = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src
    code = "\n".join(l for l in _sans_doc.split("\n") if not l.strip().startswith("#"))
    v("35. aucun second `/checkout` n'est appele par cette route",
      "/checkout" not in code, code[:80])
    v("36. aucune ecriture en base dans cette route",
      not re.search(r"(insert_one|update_one|update_many|delete_one|delete_many)", code))
    v("37. aucun identifiant d'offre ecrit en dur dans la route",
      not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-", code))
    v("38. la route ne fabrique aucun prix ni paiement",
      not re.search(r"(price|amount|stripe|Stripe|montant)", code), code[:80])

    print("\n%d/%d au vert" % (len(OK), len(OK) + len(KO)))
    if KO:
        print("ECHECS : " + " | ".join(KO))
    return not KO


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(principal()) else 1)

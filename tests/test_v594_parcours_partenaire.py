"""V594 — page d'essai : un visiteur venu d'un Partenaire va droit au parcours simplifié.

Les VRAIES fonctions de `server.py` (page + nouvelle aide `_v594_offre_du_tunnel_essai`),
montées par le banc existant `test_m1_page_seo_locale` (base factice, aucune donnée réelle).

Ce qui est figé :
  * origine `partenaire` -> le bouton mène à `/?offre=<offre du tunnel>&reserver=1` + les
    QUATRE UTM, inchangés (attribution intacte) ;
  * toute autre origine, ou aucune -> le tunnel actuel, exactement comme avant ;
  * en cas de doute (offre absente, non gratuite, base muette) -> le tunnel (repli sûr) ;
  * la carte « offert » suit le même lien que le bouton ;
  * le démarrage du Chat (ChatWidget) n'est pas touché par ce lot.

    python3 tests/test_v594_parcours_partenaire.py
"""
import ast
import asyncio
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "tests"))

import test_m1_page_seo_locale as M1  # noqa: E402  — le banc EXISTANT de la page

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition)))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)


SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(keepends=True)


def source_de(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    return ""


class LiensFactices:
    def __init__(self, doc=None, panne=False):
        self.doc, self.panne, self.appels = doc, panne, 0

    async def find_one(self, filtre=None, projection=None):
        self.appels += 1
        if self.panne:
            raise RuntimeError("base muette")
        if self.doc and (filtre or {}).get("link_token") == "b83914b4-c5a":
            return dict(self.doc)
        return None


TUNNEL_ESSAI = {"end_actions": [{"type": "booking", "config": {"offer_id": "o-essai"}}]}
PARTENAIRE = {"utm_source": "partenaire", "utm_medium": "referral",
              "utm_campaign": "essai_neuchatel", "utm_content": "akoko_tresses"}


async def page(params=None, liens=None):
    db, j = M1.monde()
    db.chat_sessions = liens if liens is not None else LiensFactices(TUNNEL_ESSAI)
    ns = M1.monter(db, j)
    exec(compile(source_de("_v594_offre_du_tunnel_essai"), "s", "exec"), ns)
    rep = await ns["m1_page_essai_neuchatel"](Req(params))
    return rep.body.decode("utf-8"), j


class Req:
    def __init__(self, params=None):
        self._p = dict(params or {})

    @property
    def query_params(self):
        p = self._p
        return type("Q", (), {"get": lambda s, k, d=None: p.get(k, d)})()

    @property
    def headers(self):
        return type("H", (), {"get": lambda s, k, d="": d})()


def cta_de(html):
    m = re.search(r'<a class="cta" href="([^"]+)"', html)
    return m.group(1).replace("&amp;", "&") if m else ""


async def principal():
    print("\n1. VISITEUR PARTENAIRE")
    html, _ = await page(PARTENAIRE)
    cta = cta_de(html)
    verifier("le bouton mène au parcours simplifié avec l'offre d'essai du tunnel",
             cta.startswith("/?offre=o-essai&reserver=1&"), cta)
    for k, v in PARTENAIRE.items():
        verifier("UTM conservé : %s=%s" % (k, v), "%s=%s" % (k, v) in cta, cta)
    verifier("plus de détour par le tunnel Chat", "link=" not in cta, cta)
    verifier("la carte « offert » suit le même lien que le bouton",
             html.count('href="%s"' % cta.replace("&", "&amp;")) >= 2)
    verifier("le texte du bouton est inchangé", ">Réserver mon 1er cours gratuit</a>" in html)

    print("\n2. VISITEURS NON PARTENAIRES : COMPORTEMENT ACTUEL")
    html, _ = await page({"utm_source": "instagram", "utm_medium": "social"})
    cta = cta_de(html)
    verifier("Instagram -> tunnel actuel, UTM recopiés", cta.startswith("/?link=b83914b4-c5a&")
             and "utm_source=instagram" in cta, cta)
    html, _ = await page({})
    verifier("sans origine -> tunnel actuel, à l'identique", cta_de(html) == "/?link=b83914b4-c5a", cta_de(html))

    print("\n3. REPLI SÛR : EN CAS DE DOUTE, LE TUNNEL")
    html, _ = await page(PARTENAIRE, LiensFactices(
        {"end_actions": [{"type": "booking", "config": {"offer_id": "o-unite"}}]}))
    verifier("offre du tunnel payante -> tunnel (jamais un achat)", cta_de(html).startswith("/?link=b83914b4-c5a&"), cta_de(html))
    html, _ = await page(PARTENAIRE, LiensFactices({"end_actions": [{"type": "payment"}]}))
    verifier("tunnel sans action booking -> tunnel", cta_de(html).startswith("/?link=b83914b4-c5a&"), cta_de(html))
    html, j = await page(PARTENAIRE, LiensFactices(panne=True))
    verifier("base muette -> tunnel, et la page s'affiche quand même",
             cta_de(html).startswith("/?link=b83914b4-c5a&") and "<html" in html.lower(), cta_de(html))
    verifier("la panne est journalisée", any("V594" in l for l in j.lignes), j.lignes[-3:])
    html, _ = await page({"utm_source": "partenaire\"><script>", "utm_content": "akoko"})
    verifier("une source falsifiée n'ouvre pas le parcours (liste blanche M2-A)",
             not cta_de(html).startswith("/?offre="), cta_de(html))

    print("\n4. PÉRIMÈTRE")
    fn = source_de("m1_page_essai_neuchatel")
    verifier("seule la destination du bouton dépend de l'origine Partenaire",
             fn.count('(_attr or {}).get("source") == "partenaire"') == 1)
    decos = {n.name: [ast.unparse(d) for d in n.decorator_list] for n in ast.walk(ARBRE)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name in ("m1_page_essai_neuchatel", "_v594_offre_du_tunnel_essai")}
    verifier("la route reste posée sur la PAGE (et non sur l'aide)",
             decos.get("m1_page_essai_neuchatel") == ["fastapi_app.get(_M1_CHEMIN, response_class=HTMLResponse)"]
             and decos.get("_v594_offre_du_tunnel_essai") == [], decos)
    aide = source_de("_v594_offre_du_tunnel_essai")
    verifier("l'aide ne fait que LIRE (aucune écriture en base)",
             not re.search(r"\.(insert|update|delete|replace|find_one_and)", aide))


if __name__ == "__main__":
    asyncio.run(principal())
    ok = sum(1 for _, c in RESULTATS if c)
    print("\n" + "=" * 70)
    print("V594 parcours Partenaire — %d / %d verifications au vert" % (ok, len(RESULTATS)))
    sys.exit(0 if ok == len(RESULTATS) else 1)

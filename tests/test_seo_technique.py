# -*- coding: utf-8 -*-
"""SEO technique — ce qui doit être vrai des pages servies par Afroboost.

Trois défauts mesurés le 22/09/2026 sur la production, et leurs gardes :

1. TOUTES les routes de l'application recevaient le même `index.html`, donc
   `robots: index, follow` et un `canonical` vers l'accueil — y compris
   `/espace/<code>`, `/duo/<token>`, `/parrainage`, `/checkout`. Le contenu de
   ces pages vient d'appels authentifiés : rien de secret n'est servi. C'est
   l'URL qui est personnelle, et elle n'a rien à faire dans un index.
2. `/api/sitemap.xml` annonçait `afroboost-v11-dev-pm7l.vercel.app`, résidu
   d'une ancienne installation qui sert un bundle périmé.
3. L'accueil ne portait AUCUNE donnée structurée, alors que la page locale en
   porte depuis M1.

    python3 tests/test_seo_technique.py
"""
import ast
import io
import json
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
INDEX = io.open(os.path.join(RACINE, "frontend", "public", "index.html"), encoding="utf-8").read()
ROBOTS = io.open(os.path.join(RACINE, "frontend", "public", "robots.txt"), encoding="utf-8").read()
SITEMAP = io.open(os.path.join(RACINE, "frontend", "public", "sitemap.xml"), encoding="utf-8").read()

R = []
def v(nom, cond, detail=""):
    R.append((nom, bool(cond), detail))


def _bloc(depart, fin):
    return SRC[SRC.index(depart):SRC.index(fin)]


# ── Les règles pures, extraites de la source et exécutées ───────────────────
_NS = {"os": os, "re": re}
for _nom in ("_SEO_PRIVE", "_SEO_META_PRIVEE"):
    _m = re.search(r"^\s{4}(%s = .*?)\n\s{4}[_@A-Za-z]" % _nom, SRC, re.S | re.M)
    exec(ast.unparse(ast.parse(_m.group(1).replace("\n    ", "\n"))), _NS)
for _fn in ("_seo_est_prive", "_seo_index_prive"):
    _m = re.search(r"^\s{4}(def %s.*?)(?=\n\s{4}(?:def |# |@))" % _fn, SRC, re.S | re.M)
    exec(ast.unparse(ast.parse(_m.group(1).replace("\n    ", "\n"))), _NS)
est_prive = _NS["_seo_est_prive"]
index_prive = _NS["_seo_index_prive"]

# ── 1. Ce qui est privé, et ce qui ne l'est pas ────────────────────────────
for _c in ("/espace/AFR-1234", "/espace", "/duo/jeton-abc", "/parrainage",
           "/checkout", "/checkout/retour", "/login", "/admin", "/reset.html"):
    v("privé : %s n'est pas indexable" % _c, est_prive(_c), _c)
for _c in ("/", "", "/cours-essai-gratuit-neuchatel", "/coach/bassi", "/partner/x",
           "/devenir-coach", "/rencontre"):
    v("public : %s reste indexable" % (_c or "(racine)"), not est_prive(_c), _c)
v("aucun faux positif : un chemin qui COMMENCE par le même mot reste public",
  not est_prive("/espacement") and not est_prive("/duodecimal")
  and not est_prive("/parrainages-anciens"))
v("la casse et les barres obliques ne changent rien",
  est_prive("espace/AFR-1") and est_prive("/espace/AFR-1/") and est_prive("//duo//x"))

# ── 2. La page rendue pour un chemin privé ─────────────────────────────────
_faux = os.path.join(RACINE, "tests", "_seo_index_factice.html")
io.open(_faux, "w", encoding="utf-8").write(
    '<html><head><meta name="robots" content="index, follow" />'
    '<link rel="canonical" href="https://afroboost.com/" />'
    '<title>Afroboost</title></head><body>x</body></html>')
try:
    _rendu = index_prive(_faux)
    v("la page privée porte `noindex, nofollow`",
      'content="noindex, nofollow"' in _rendu and 'content="index, follow"' not in _rendu, _rendu[:120])
    # LE PIÈGE MESURÉ : le build CRA écrit `content="index, follow"/>` SANS
    # espace avant la barre. Une comparaison exacte échouait en silence.
    io.open(_faux, "w", encoding="utf-8").write(
        '<html><head><meta name="robots" content="index, follow"/>'
        '<link rel=\'canonical\' href="https://afroboost.com/"/><title>x</title></head><body>y</body></html>')
    _rendu2 = index_prive(_faux)
    v("la balise est remplacée quelle que soit son écriture (build CRA, guillemets simples)",
      'content="noindex, nofollow"' in _rendu2 and "index, follow" not in _rendu2
      and "canonical" not in _rendu2, _rendu2[:160])
    v("elle ne porte PLUS de canonical vers l'accueil (une URL privée ne canonise pas, elle s'efface)",
      "canonical" not in _rendu, _rendu[:160])
    v("rien d'autre n'est touché : même titre, même corps",
      "<title>Afroboost</title>" in _rendu and "<body>x</body>" in _rendu)
    io.open(_faux, "w", encoding="utf-8").write("<html><head><title>x</title></head><body>y</body></html>")
    v("index.html sans balise robots : on en ajoute une, sans casser la page",
      'content="noindex, nofollow"' in index_prive(_faux) and "<body>y</body>" in index_prive(_faux))
finally:
    os.remove(_faux)

# ── 3. Le catch-all applique la règle, et jamais au prix de la page ────────
_catch = _bloc("    # Catch-all: serve index.html", "# Export for Vercel Serverless")
v("le catch-all sert la page privée réécrite, en HTML",
  "if _seo_est_prive(full_path):" in _catch and "HTMLResponse(_seo_index_prive(_index)" in _catch)
v("une panne de réécriture ne casse pas la route : la page est servie telle quelle",
  "except Exception as _seo_err" in _catch and "return _FileResponse(_index, headers=_no_cache)" in _catch)
v("les fichiers réels (assets, sw.js) sont servis avant toute réécriture",
  _catch.index("_os.path.isfile(file_path") < _catch.index("_seo_est_prive(full_path)"))

# ── 4. robots.txt ──────────────────────────────────────────────────────────
v("robots.txt déclare le sitemap", "Sitemap: https://afroboost.com/sitemap.xml" in ROBOTS)
v("robots.txt n'interdit pas le rendu (ni /static/, ni JS, ni CSS)",
  "Disallow: /static" not in ROBOTS and ".js" not in ROBOTS and ".css" not in ROBOTS)

# ── SEO-1b : `noindex` ET `Disallow` s'annulent ────────────────────────────
# Un robot qui n'a pas le droit de CHARGER la page ne lit jamais la balise qui
# lui demande de ne pas l'indexer. Une page HTML qu'on sort de l'index par
# `noindex` doit donc rester crawlable. C'est la règle que ce banc verrouille :
# elle se serait re-cassée au premier « durcissons robots.txt » venu.
_ROBOTS_REGLES = [_l.strip() for _l in ROBOTS.splitlines() if _l.strip().startswith("Disallow:")]

def _bloque(chemin):
    _c = str(chemin)
    return any(_c.startswith(_r.split(":", 1)[1].strip()) for _r in _ROBOTS_REGLES)

for _c in ("/espace/AFR-1234", "/duo/jeton-abc", "/parrainage", "/checkout"):
    v("SEO-1b : %s est `noindex` ET reste crawlable (sinon la balise n'est jamais lue)" % _c,
      est_prive(_c) and not _bloque(_c), [_r for _r in _ROBOTS_REGLES if _bloque(_c)])
v("SEO-1b : les quatre règles ajoutées à tort ont bien été retirées",
  not any(("Disallow: %s" % _d) in ROBOTS for _d in ("/espace/", "/duo/", "/parrainage", "/checkout")))
v("les règles HISTORIQUES sont intactes (aucune retirée par mégarde)",
  all(("Disallow: %s" % _d) in ROBOTS
      for _d in ("/login", "/admin", "/reset.html", "/pwa-diag.html", "/api/")))
v("/api/ reste bloqué : ce ne sont pas des pages HTML, aucune balise n'y est lisible",
  "Disallow: /api/" in ROBOTS and _bloque("/api/sitemap.xml"))
v("l'accueil et la page locale restent autorisés et crawlables",
  "Disallow: /cours-essai" not in ROBOTS and re.search(r"^Allow: /$", ROBOTS, re.M)
  and not _bloque("/") and not _bloque("/cours-essai-gratuit-neuchatel"))
# `/reset.html` et `/pwa-diag.html` sont de VRAIS fichiers : le catch-all les
# sert tels quels, aucune balise ne peut y être posée — robots.txt est alors la
# seule règle possible, et il n'y a aucun conflit à signaler.
v("les fichiers statiques privés sont servis avant toute réécriture (aucun noindex possible, donc aucun conflit)",
  "_os.path.isfile(file_path" in _bloc("    # Catch-all: serve index.html", "# Export for Vercel Serverless"))

# ── 5. Le sitemap statique : des pages réelles, et elles seules ────────────
_urls = re.findall(r"<loc>(.*?)</loc>", SITEMAP)
v("le sitemap ne liste que des URL du bon domaine",
  _urls and all(u.startswith("https://afroboost.com/") for u in _urls), _urls)
v("le sitemap ne contient AUCUNE page privée", not any(est_prive(u.replace("https://afroboost.com", "")) for u in _urls), _urls)
v("le sitemap contient l'accueil et la page locale de Neuchâtel",
  "https://afroboost.com/" in _urls and "https://afroboost.com/cours-essai-gratuit-neuchatel" in _urls, _urls)

# ── 6. Le sitemap de l'API : plus jamais l'ancien domaine ──────────────────
_i = SRC.index('@api_router.get("/sitemap.xml")')
_sm = SRC[_i:SRC.index("@api_router", _i + 40)]
# Le commentaire a le droit de NOMMER le domaine qu'il exclut ; le code, non.
_sm_code = "\n".join(_l for _l in _sm.splitlines() if not _l.strip().startswith("#"))
v("SEO-2 : le sitemap de l'API n'annonce plus `vercel.app`",
  "vercel.app" not in _sm_code
  and 'os.environ.get("FRONTEND_URL", "https://afroboost.com")' in _sm_code, _sm_code[:200])

# ── 6b. SEO-4 — le sitemap n'annonce plus une adresse qui n'existe pas ─────
# `/devenir-coach` n'est une route NULLE PART dans le frontend : l'application
# y rend l'accueil, à l'octet près, avec le `canonical` de l'accueil. On
# annonçait donc à Google une deuxième adresse pour le même contenu, en lui
# disant dans la même page que la vraie adresse est l'accueil. Les liens
# « Devenir partenaire » du produit visent `/#devenir-coach` — une ANCRE sur
# l'accueil, pas cette adresse : la retirer ne casse aucun chemin.
v("SEO-4 : le sitemap de l'API n'annonce plus `/devenir-coach` (aucune route ne la sert)",
  "devenir-coach" not in _sm_code, _sm_code[:300])
v("SEO-4 : il annonce toujours l'accueil et les vitrines de coachs",
  "{base_url}/</loc>" in _sm_code and "{base_url}/coach/{slug}</loc>" in _sm_code, _sm_code[:300])
# Le garde qui compte vraiment : la règle vaut pour TOUT chemin ajouté un jour.
# Un sitemap ne liste que des adresses qui se présentent elles-mêmes. Tant que
# `_SEO_PRIVE` et les fiches publiques sont les seules exceptions connues du
# catch-all, la seule adresse fixe légitime est l'accueil.
_locs_api = re.findall(r"\{base_url\}(/[^<]*)</loc>", _sm_code)
v("SEO-4 : aucune adresse fixe du sitemap de l'API n'est privée ni inventée",
  set(_locs_api) <= {"/", "/coach/{slug}"}, _locs_api)
# Les ancres historiques ne sont PAS touchées : ce sont des liens vers
# l'accueil, pas des adresses indexables.
v("SEO-4 : les liens legacy `/#devenir-coach` restent en place (rien n'est cassé côté produit)",
  SRC.count("/#devenir-coach") >= 2)

# ── 7. Les données structurées de l'accueil ────────────────────────────────
_ld = re.findall(r'application/ld\+json">(.*?)</script>', INDEX, re.S)
v("l'accueil porte des données structurées", len(_ld) >= 2, len(_ld))
_types = []
for _b in _ld:
    _d = json.loads(_b)            # lève si le JSON est invalide
    _types.append(_d.get("@type"))
v("JSON-LD valide, et du bon type (Organization + WebSite)",
  "Organization" in _types and "WebSite" in _types, _types)
v("aucune donnée inventée : ni note, ni avis, ni effectif, ni prix, ni adresse postale",
  not any(_m in " ".join(_ld) for _m in ("aggregateRating", "review", "ratingValue",
                                         "priceCurrency", "streetAddress", "postalCode")))
v("le nom, l'URL et le logo sont ceux du site (une seule description d'Afroboost)",
  all(_m in " ".join(_ld) for _m in ('"name":"Afroboost"', "https://afroboost.com/",
                                     "logo512.png", "Neuchâtel")))

# ── 8. L'accueil garde ses balises ─────────────────────────────────────────
v("l'accueil reste indexable, avec son canonical absolu",
  '<meta name="robots" content="index, follow" />' in INDEX
  and '<link rel="canonical" href="https://afroboost.com/" />' in INDEX)
v("l'accueil garde son titre, sa description et ses balises de partage",
  "<title>" in INDEX and 'name="description"' in INDEX
  and 'property="og:title"' in INDEX and 'property="og:image"' in INDEX
  and 'name="twitter:card"' in INDEX)

ok = sum(1 for _, c, _ in R if c)
for n, c, d in R:
    print(("  OK    " if c else "  RATE  ") + n + ("" if c else "  [%s]" % str(d)[:200]))
print("\n%d / %d verifications au vert" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)

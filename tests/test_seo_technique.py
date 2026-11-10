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
# V655 : le chemin `/offres` est lu par le frontend — on verifie la SOURCE,
# pas un build, pour que le banc reste hors ligne et independant de `yarn build`.
APP = io.open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
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
  "_seo_est_prive(full_path)" in _catch and "HTMLResponse(_seo_index_prive(_index)" in _catch)
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
# V552b — APERÇU DES INVITATIONS : la page de partage et sa carte doivent être
# lisibles par les robots d'aperçu (Meta/Messenger respectent robots.txt), tout
# en restant hors index (`noindex` sur la page, cf. SEO-1b). Règle standard :
# la correspondance la plus LONGUE l'emporte, `Allow` gagnant à égalité.
def _autorise(chemin):
    _best, _ok = -1, True
    for _l in ROBOTS.splitlines():
        _l = _l.strip()
        for _k, _val in (("Allow:", True), ("Disallow:", False)):
            if _l.startswith(_k):
                _pref = _l.split(":", 1)[1].strip()
                if _pref and str(chemin).startswith(_pref) and (len(_pref) > _best or (len(_pref) == _best and _val)):
                    _best, _ok = len(_pref), _val
    return _ok
SRC_SRV = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
v("V552b : la page de partage Pass Duo et sa carte restent lisibles par les robots d'aperçu",
  _autorise("/api/share/duo/jeton-abc") and _autorise("/api/share/duo/jeton-abc/carte.jpg"))
v("V552b : le reste de /api/ reste interdit aux robots",
  not _autorise("/api/sitemap.xml") and not _autorise("/api/referral/me"))
_page_duo = SRC_SRV.split("async def share_duo_page", 1)[1][:6000]
# V556 : le gabarit HTML vit dans le moteur pur (`page_apercu_html`), partagé par la
# page ET par le contrôle d'aperçu avant partage ; la page y passe par `_v556_html_apercu`.
SRC_ENG = io.open(os.path.join(RACINE, "api", "routes", "referral_engine.py"), encoding="utf-8").read()
_gabarit_duo = SRC_ENG.split("def page_apercu_html(", 1)[1].split("_RE_META_OG = ", 1)[0]
_html_duo = SRC_SRV.split("async def _v556_html_apercu", 1)[1][:4000]
v("V552b : la page de partage est `noindex` (lisible pour l'aperçu, jamais indexée)",
  '<meta name="robots" content="noindex, nofollow"/>' in _gabarit_duo
  and "_v556_html_apercu(_p, v, robot=" in _page_duo
  and "_duo.page_apercu_html(" in _html_duo)
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
# SEO-GEO (19/10/2026) : les deux pages ÉCRITES PAR LE SERVEUR (lisibles sans
# JavaScript, avec leur propre titre et leur propre canonical) rejoignent la
# liste — ce sont des adresses qui « se présentent elles-mêmes ».
v("SEO-4 : aucune adresse fixe du sitemap de l'API n'est privée ni inventée",
  set(_locs_api) <= {"/", "/coach/{slug}", "/cours-essai-gratuit-neuchatel", "/a-propos",
                     # SEO-5 (10/11/2026) : « Politique de confidentialité »,
                     # ecrite par le serveur en amont du catch-all, lisible sans
                     # JavaScript. Elle « se presente elle-meme » : elle a sa
                     # place ici. Aucune vue React n'en a le droit.
                     "/confidentialite",
                     # SEO-6 : la boutique sert desormais son propre en-tete.
                     "/boutique",
                     # V655 : « Offres et tarifs » a une vraie adresse.
                     "/offres"}, _locs_api)
# Les ancres historiques ne sont PAS touchées : ce sont des liens vers
# l'accueil, pas des adresses indexables.
v("SEO-4 : les liens legacy `/#devenir-coach` restent en place (rien n'est cassé côté produit)",
  SRC.count("/#devenir-coach") >= 2)

# ── 6 bis. SEO-5 : une adresse inventée répond 404 ─────────────────────────
# AVANT, TOUT REPONDAIT 200. `/cours-de-salsa-a-geneve`, `/blog`, `/xyzabc123`
# renvoyaient l'accueil en 200 avec « index, follow » : Google pouvait explorer
# une infinite d'adresses qui n'existent pas. Seul le `canonical` evitait le
# doublon — une protection indirecte, qui ne rend pas le budget de crawl.
_racines = re.search(r"_SEO_RACINES_REELLES = frozenset\((.*?)\)\)", SRC, re.S)
v("SEO-5 : la liste des racines réelles existe", bool(_racines))
_noms = set(re.findall(r'"([a-z0-9-]+)"', _racines.group(1))) if _racines else set()
# Chaque racine lue dans le frontend DOIT y etre : en oublier une transformerait
# une vraie page en 404.
for _r in ("espace", "duo", "parrainage", "checkout", "login", "rdv", "admin",
           "coach", "partner", "partenaire", "entreprise", "chat", "i", "v",
           "validate", "boutique"):
    v("SEO-5 : la route SPA `/%s` reste servie" % _r, _r in _noms)
for _r in ("cours-essai-gratuit-neuchatel", "a-propos", "confidentialite",
           "privacy", "terms", "live", "rencontre"):
    v("SEO-5 : la page `/%s` reste servie" % _r, _r in _noms)
v("SEO-5 : le 404 n'est posé qu'APRÈS les fichiers réels et les chemins privés",
  _catch.index("_os.path.isfile(file_path") < _catch.index("_seo_racine_connue(full_path)")
  and _catch.index("_seo_est_prive(full_path)") < _catch.index("_seo_racine_connue(full_path)"))
v("SEO-5 : le 404 sert le MÊME index.html (l'application continue de marcher)",
  "status_code=404" in _catch and "_seo_index_prive(_index)" in _catch
  and "page-404" not in _catch)
v("SEO-5 : une panne du 404 ne casse pas la route",
  "except Exception as _e404" in _catch)
v("SEO-5 : la racine « / » n'est JAMAIS un 404",
  "(not _seg) or" in SRC)
# Les deux liens de l'interface qui ne menent nulle part : ils gardent leur 200
# (aucun clic casse) mais cessent d'etre indexables.
v("SEO-5 : `/conditions` et `/cgu` sont connus, donc pas en 404",
  "conditions" in _noms and "cgu" in _noms)
v("SEO-5 : et ils sont marqués `noindex` (sinon : deux accueils de plus indexés)",
  "_SEO_LIEN_SANS_PAGE" in SRC and '"/conditions", "/cgu"' in SRC
  and "_SEO_LIEN_SANS_PAGE" in _catch)

# SEO-5 — LE COMPORTEMENT, PAS SEULEMENT LE TEXTE. On extrait la vraie fonction
# de `server.py` et on lui fait juger un tableau de chemins. C'est ce qui prouve
# qu'aucune route reelle ne bascule en 404.
import textwrap as _tw
_src404 = (re.search(r"(    _SEO_RACINES_REELLES = frozenset\(\(.*?\n    \)\))", SRC, re.S).group(1)
           + "\n"
           + re.search(r"(    def _seo_racine_connue.*?return \(not _seg\)[^\n]*\n)", SRC, re.S).group(1))
_ns404 = {}
exec(compile(_tw.dedent(_src404), "racines", "exec"), _ns404)
_connue = _ns404["_seo_racine_connue"]

# Ces chemins DOIVENT rester servis (200). Chacun vient d'une expression lue
# dans le frontend ou d'une route declaree dans server.py.
for _ok in ("", "/", "/espace", "/espace/AFR-2287CA", "/duo/abc123", "/duo/c/xyz",
            "/parrainage", "/checkout", "/login", "/admin", "/rdv/" + "a" * 20,
            "/coach/bassi", "/partner/bassi", "/partenaire/" + "b" * 12,
            "/entreprise/" + "c" * 26, "/chat/42", "/i/jeton", "/v/code",
            "/validate/code", "/boutique", "/boutique/t-shirt-ab12cd34",
            "/offres", "/offres/",  # V655 : avec et sans barre finale
            "/cours-essai-gratuit-neuchatel", "/a-propos", "/confidentialite",
            "/privacy", "/terms", "/live", "/rencontre", "/health", "/healthz",
            "/conditions", "/cgu", "/ESPACE/AFR-1", "/Coach/Bassi",
            # Fichiers du site : un 404 ici ferait passer un defaut de build
            # pour un probleme de referencement.
            "/sitemap.xml", "/robots.txt", "/favicon.ico", "/manifest.json",
            "/sw.js", "/.well-known/acme-challenge/x", "/static/js/main.js"):
    v("SEO-5 : `%s` reste servi (jamais 404)" % (_ok or "/"), _connue(_ok))

# Ces chemins n'existent pas et doivent le dire.
for _ko in ("/cours-de-salsa-a-geneve", "/xyzabc123", "/blog", "/devenir-coach",
            "/partenaires", "/contact", "/mentions-legales", "/cgv",
            "/wp-admin", "/index.php", "/zumba-neuchatel"):
    v("SEO-5 : `%s` n'existe pas -> 404" % _ko, not _connue(_ko))

# ── 6 ter. SEO-6 : une page publique sert SON en-tête ──────────────────────
# AVANT, `/boutique` servait l'en-tete de l'accueil au chargement direct :
# meme titre, meme description, et `canonical` vers « / ». Elle declarait donc
# elle-meme que sa vraie adresse etait l'accueil, et aucun titre pose ensuite
# par React ne pouvait contredire cette declaration.
_sec6 = re.search(r"    _SEO6_PAGES = \{(.*?)\n    \}", SRC, re.S)
v("SEO-6 : la table des en-têtes existe", bool(_sec6))
_t6 = _sec6.group(1) if _sec6 else ""
v("SEO-6 : la boutique y figure", '"boutique"' in _t6)
v("SEO-6 : elle a son titre, sa description et son chemin",
  '"titre"' in _t6 and '"desc"' in _t6 and '"chemin": "/boutique"' in _t6)
# V655 — `/offres` EST DEVENUE UNE PAGE. Jusqu'ici ce chemin n'existait pas et
# les formules n'etaient atteignables que par `/?offres=toutes` : un parametre
# ne se dit pas au telephone et ne s'indexe pas. Le chemin emet desormais LE
# MEME signal vers LE MEME panneau — aucune seconde logique d'affichage.
v("V655 : `/offres` a son propre en-tête", '"offres"' in _t6 and '"chemin": "/offres"' in _t6)
v("V655 : sa description ne cite AUCUN tarif (ils changeraient sans elle)",
  not re.search(r'"desc":[^}]*\d+\s*(CHF|francs)', _t6))
v("SEO-6 : l'en-tête est posé APRÈS les chemins privés et AVANT le bloc d'accueil",
  _catch.index("_seo_est_prive(full_path)") < _catch.index("_seo6_page(full_path)")
  < _catch.index("_seo_geo_accueil(_index)"))
v("SEO-6 : une panne de réécriture ne casse pas la boutique",
  "except Exception as _e6" in _catch)
# Les huit balises doivent bouger ensemble : un `canonical` corrige avec un
# `og:url` reste de l'accueil enverrait deux signaux contradictoires.
_fn6 = re.search(r"def _seo6_index_page.*?return _html", SRC, re.S)
_c6 = _fn6.group(0) if _fn6 else ""
for _b in ("<title>", "description", "og:title", "og:description", "og:url",
           "twitter:title", "twitter:description", "canonical"):
    v("SEO-6 : `%s` est réécrit" % _b, _b in _c6)
v("SEO-6 : remplacement par MOTIF, jamais par égalité de chaîne (leçon SEO-1)",
  "_re.sub(" in _c6 and "flags=_re.I" in _c6)
v("SEO-6 : la boutique est bien une racine servie (jamais 404)", _connue("/boutique"))
v("V655 : `/offres` est servie (elle n'est plus un 404)", _connue("/offres"))
# LA PORTE D'ORIGINE RESTE OUVERTE. Le paramètre `?offres=toutes` est écrit dans
# la page d'essai servie par le serveur et dans des liens déjà partagés : le
# casser serait une régression silencieuse.
# LA REGLE VIT DANS UN SEUL FICHIER, teste a part (routeOffres.test.js).
_ROUTE_OFFRES = io.open(os.path.join(RACINE, "frontend", "src", "utils",
                                     "routeOffres.js"), encoding="utf-8").read()
v("V655 : `/?offres=toutes` est toujours lu (la porte d'origine reste ouverte)",
  "get('offres') === 'toutes'" in _ROUTE_OFFRES)
v("V655 : le chemin `/offres` est lu aussi", "/^\\/offres\\/?$/i" in _ROUTE_OFFRES)
v("V655 : les deux entrées mènent au MÊME signal, émis une seule fois",
  "ouvrirLesOffres(window.location.pathname" in APP
  and APP.count("setSignalToutesOffres(n => n + 1)") == 1)
v("V655 : aucune seconde logique d'affichage — App.js appelle la règle, ne la recopie pas",
  "offres') === 'toutes'" not in APP)
v("V655 : la page d'essai pointe toujours vers `/?offres=toutes` (lien inchangé)",
  'href="/?offres=toutes"' in SRC)

# ── 6 quater. V656 : `/offres` est une PAGE, pas un panneau sur l'accueil ──
# AVANT (V655), `/offres` ouvrait le panneau superposé à l'accueil : la page
# était à ~83 % identique à l'accueil, donc faible pour un moteur. Elle a
# maintenant sa propre mise en page et son propre texte, écrit par le SERVEUR
# — lisible sans JavaScript, ce qu'aucun titre posé par React ne permet.
_bloc656 = re.search(r"    _SEO6_BLOC_OFFRES = \((.*?)\n        '</section>'\)", SRC, re.S)
v("V656 : le texte éditorial de `/offres` existe côté serveur", bool(_bloc656))
_b6 = _bloc656.group(1) if _bloc656 else ""
v("V656 : il porte le H1 demandé",
  "Offres et tarifs Afroboost à Neuchâtel" in _b6 and "<h1" in _b6)
v("V656 : il présente le cardio-danse afrobeat et son accessibilité",
  "cardio-danse afrobeat" in _b6 and "savoir danser" in _b6)
v("V656 : il explique les possibilités d'inscription",
  all(m in _b6 for m in ("à la séance", "carte", "abonnement", "essai")))
v("V656 : il invite à choisir une formule et à réserver",
  "Choisissez" in _b6 and "réserv" in _b6)
# AUCUN TARIF, AUCUNE GARANTIE INVENTÉE : les prix vivent sur les cartes
# d'offres, qui viennent des données réelles. Un chiffre figé ici mentirait.
v("V656 : AUCUN prix n'est écrit dans ce texte",
  not re.search(r"\d+\s*(CHF|francs|€)", _b6) and "gratuit à vie" not in _b6)
v("V656 : le bloc est rattaché à la page `/offres`",
  '_SEO6_PAGES["offres"]["bloc"] = _SEO6_BLOC_OFFRES' in SRC)
v("V656 : il est injecté dans le HTML servi, après la zone React",
  "_SEO_GEO_ANCRE_ROOT + _bloc" in SRC)
# LE FRONTEND : une page dédiée, et l'ancienne porte intacte.
v("V656 : le drapeau de la page existe et vient de la règle unique",
  "const [pageOffres] = useState(() => parCheminOffres(" in APP)
v("V656 : pas de Hero sur `/offres` (même règle que `/boutique`, V646)",
  "{boutiqueRoute === null && !pageOffres && (" in APP)
v("V656 : les sections propres à l'accueil sont masquées (concept, produits, "
  "audio, horaires, FAQ)", APP.count("boutiqueRoute === null && !pageOffres") >= 6)
v("V656 : `/offres` active l'onglet « Offres » existant, aucun second composant",
  "setActiveFilter('offers');" in APP and APP.count("<OffresAimants") == 2)
v("V656 : `/?offres=toutes` garde son panneau superposé",
  "ouvrirLesOffres(window.location.pathname, window.location.search)" in APP
  and "setSignalToutesOffres(n => n + 1);" in APP)
# LA PREUVE QU'IL N'Y A PAS DEUX TEXTES : le contenu éditorial n'existe NULLE
# PART dans le frontend. React ne connaît que l'emplacement où le déplacer.
v("V656 : le texte éditorial est DÉPLACÉ, jamais recopié par React",
  "getElementById('af-offres-intro')" in APP
  and "Offres et tarifs Afroboost à Neuchâtel" not in APP
  and "cardio-danse afrobeat" not in APP.lower())
# V657 — UN COACH CONNECTE DOIT VOIR LA PAGE, PAS SON TABLEAU DE BORD.
# `/boutique` avait cette regle depuis V646 ; `/offres` ne l'avait pas, et un
# coach qui ouvrait son propre lien tombait sur le tableau de bord.
v("V657 : `/offres` bascule en « Vue Visiteur » pour un coach connecté",
  "if (coachMode && pageOffres) urlParams.set('visitor', 'true');" in APP)
v("V657 : même mécanisme que `/boutique`, pas un second",
  "if (coachMode && boutiqueRoute !== null) urlParams.set('visitor', 'true');" in APP
  and APP.count("urlParams.set('visitor', 'true')") == 2)
v("V657 : la règle est posée AVANT la bascule vers le tableau de bord",
  APP.index("if (coachMode && pageOffres)") < APP.index("return <CoachDashboard"))
# LA REGLE NE TOUCHE QUE L'URL. Elle pose un parametre de lecture, exactement
# comme « Vue Visiteur » : ni session effacee, ni jeton retire, ni redirection.
_l657 = [l for l in APP.split("\n") if "coachMode && pageOffres" in l]
v("V657 : la règle ne fait QUE poser le paramètre d'affichage (aucune déconnexion)",
  len(_l657) == 1
  and not any(m in _l657[0] for m in ("logout", "Logout", "removeItem", "clear(",
                                      "location.href", "setCoachMode", "localStorage")))

v("V656 : il se place au-dessus des formules",
  APP.index("{pageOffres && <div ref={afOffresIntroSlot} />}") < APP.index("{offersBlock}"))

# ── 7. Les données structurées de l'accueil ────────────────────────────────
_ld = re.findall(r'application/ld\+json">(.*?)</script>', INDEX, re.S)
v("l'accueil porte des données structurées", len(_ld) >= 2, len(_ld))
_types = []
for _b in _ld:
    _d = json.loads(_b)            # lève si le JSON est invalide
    _types.append(_d.get("@type"))
v("JSON-LD valide, et du bon type (Organization + WebSite)",
  "Organization" in _types and "WebSite" in _types, _types)
v("aucune donnée inventée : ni note, ni avis, ni effectif, ni prix",
  not any(_m in " ".join(_ld) for _m in ("aggregateRating", "review", "ratingValue",
                                         "priceCurrency")))
# SEO-GEO (19/10/2026) — DÉCISION DE BASSI : l'adresse des Valangines est
# publiée, mais comme LIEU DES COURS (SportsActivityLocation), jamais comme
# adresse de l'organisation (qui n'est pas celle de l'association).
_par_type = {json.loads(_b).get("@type"): json.loads(_b) for _b in _ld}
v("l'adresse postale n'est portée QUE par le lieu des cours (pas par l'organisation)",
  "address" not in _par_type.get("Organization", {})
  and (_par_type.get("SportsActivityLocation", {}).get("address") or {}).get("streetAddress")
      == "Chemin des Valangines 97", sorted(_par_type))
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

"""SEO-GEO (19/10/2026) — Afroboost lisible par Google ET par les IA.

Ce banc verrouille le lot validé par Bassi :
  1. `/llms.txt` existe, en TEXTE, avec le contenu exact demandé ;
  2. l'accueil : titre / descriptions / mots-clés sans casque, JSON-LD
     Organization + SportsActivityLocation IDENTIQUES à ceux du serveur ;
  3. le bloc de présentation de l'accueil n'est posé que sur `/` exact, hors
     de la zone React, avec deux vrais liens — toutes les autres adresses
     reçoivent `index.html` à l'octet près ;
  4. la page d'essai : nouveau H1, slogan conservé, plus aucune promesse de
     casque en salle (le bloc « Afroboost Silent » reste intact), FAQ
     accentuée identique dans le HTML et le JSON-LD, contact + carte au clic ;
  5. la page `/a-propos` : textes exacts, indexable, photo seulement si le
     fichier validé est déposé ;
  6. les deux sitemaps listent les mêmes pages ;
  7. la carte : AUCUNE ressource Google avant le clic.

Exécution : `python3 tests/test_seo_geo.py` (aucun réseau, aucune base).
"""
import ast
import asyncio
import io
import json
import os
import re
import sys
import tempfile
import textwrap

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "tests"))

import test_m1_page_seo_locale as M1  # noqa: E402 — le montage de la page d'essai

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(keepends=True)
PUBLIC = os.path.join(RACINE, "frontend", "public")
INDEX = io.open(os.path.join(PUBLIC, "index.html"), encoding="utf-8").read()

OK, KO = [], []


def v(nom, cond, detail=""):
    (OK if cond else KO).append(nom)
    print(("  OK    " if cond else "  RATE  ") + nom + ("" if cond else "  [%s]" % (detail,)))


def source_de(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign)):
            _id = n.name if hasattr(n, "name") else getattr(n.targets[0], "id", "")
            if _id == nom:
                return textwrap.dedent("".join(LIGNES[n.lineno - 1:n.end_lineno]))
    raise KeyError(nom)


def monter(*noms, ns=None):
    ns = ns if ns is not None else {}
    for nom in noms:
        exec(compile(source_de(nom), nom, "exec"), ns)
    return ns


LLMS_ATTENDU = """# Afroboost

> Afroboost est un concept de cardio-danse inspiré des danses africaines et de l'Afrobeat, proposé à Neuchâtel (Suisse) par l'association Afroboosteur. Cours collectifs avec un coach, accessibles aux débutants : pas besoin de savoir danser. Le premier cours d'essai est offert.

## Les cours
- Lieu en hiver : Chemin des Valangines 97, 2000 Neuchâtel (en salle, sans casque audio)
- Horaires : mercredi à 18h45 et dimanche à 18h30
- Durée : environ 1 heure
- En été : Afroboost Silent, séances en plein air au bord du lac de Neuchâtel (Auvernier), avec casques audio
- Coach et fondateur : Henri Bassi, dit Coach Bassi

## Pages principales
- [Cours d'essai gratuit à Neuchâtel](https://afroboost.com/cours-essai-gratuit-neuchatel) : présentation, planning, formules et tarifs, questions fréquentes
- [À propos de Coach Bassi et d'Afroboost](https://afroboost.com/a-propos) : le fondateur, la philosophie, l'association

## Contact
- E-mail : contact@afroboosteur.com
- Instagram : https://www.instagram.com/afroboosteur
- Facebook : https://www.facebook.com/profile.php?id=61574448227600
"""

CONSTANTES_GEO = ("SEO_GEO_EMAIL", "SEO_GEO_INSTAGRAM", "SEO_GEO_FACEBOOK", "SEO_GEO_ADRESSE",
                  "SEO_GEO_ORGANISATION", "SEO_GEO_LIEU", "SEO_GEO_CARTE_EMBED", "SEO_GEO_ITINERAIRE",
                  "SEO_GEO_CSS", "_SEO_GEO_PICTO_LIEU", "SEO_GEO_CARTE_JS")


def sans_google_avant_clic(html):
    """Aucune ressource Google CHARGÉE par la page : ni iframe, ni script, ni
    image, ni feuille de style. L'adresse de la carte n'existe que dans
    `data-carte-src` (inerte) et le lien « Itinéraire » (un simple lien)."""
    if "<iframe" in html.lower():
        return False
    for balise in re.findall(r"<(?:script|img|link|source|iframe|embed|object)\b[^>]*>", html, re.I):
        if "google" in balise.lower():
            return False
    return True


async def main():
    print("\n== 1. /llms.txt ==")
    _llms_chemin = os.path.join(PUBLIC, "llms.txt")
    v("llms.txt existe dans frontend/public/", os.path.isfile(_llms_chemin))
    _llms = io.open(_llms_chemin, encoding="utf-8").read() if os.path.isfile(_llms_chemin) else ""
    v("llms.txt : contenu EXACT demandé", _llms == LLMS_ATTENDU)
    v("llms.txt : ce n'est pas du HTML", "<html" not in _llms.lower() and "<!doctype" not in _llms.lower())
    import mimetypes
    v("llms.txt sera servi en texte (type deviné par le serveur de fichiers)",
      (mimetypes.guess_type("llms.txt")[0] or "").startswith("text/"), mimetypes.guess_type("llms.txt"))
    v("le catch-all sert un VRAI fichier avant tout (llms.txt ne tombe pas sur l'appli)",
      "_os.path.isfile(file_path := _os.path.join(_STATIC_DIR, full_path))" in SRC)

    print("\n== 2. Accueil : en-tête ==")
    _tete = re.sub(r"<!--.*?-->", "", INDEX, flags=re.S).split("</head>")[0]
    T = "Afroboost | Cardio-danse Afrobeat à Neuchâtel"
    D = ("Cardio-danse Afrobeat en groupe à Neuchâtel, avec un coach. Pas besoin de savoir danser. "
         "Ton premier cours est offert.")
    v("title exact", "<title>%s</title>" % T in _tete)
    for prop in ('name="description"', 'property="og:description"', 'name="twitter:description"'):
        v("%s exacte" % prop, '<meta %s content="%s" />' % (prop, D) in _tete)
    for prop in ('property="og:title"', 'name="twitter:title"'):
        v("%s exact" % prop, '<meta %s content="%s" />' % (prop, T) in _tete)
    v("aucune mention de casque dans l'en-tête servi (mots-clés compris)", "casque" not in _tete.lower())
    v("aucun emoji casque dans les balises de partage", "🎧" not in _tete)

    print("\n== 3. JSON-LD : accueil = serveur ==")
    ns = monter(*CONSTANTES_GEO, ns={})
    _blocs = [json.loads(b) for b in re.findall(r'application/ld\+json">(.*?)</script>', INDEX, re.S)]
    _par = {b.get("@type"): b for b in _blocs}
    v("accueil : Organization identique au serveur", _par.get("Organization") == ns["SEO_GEO_ORGANISATION"])
    v("accueil : SportsActivityLocation identique au serveur",
      _par.get("SportsActivityLocation") == ns["SEO_GEO_LIEU"])
    v("accueil : WebSite toujours là", "WebSite" in _par)
    _org, _lieu = ns["SEO_GEO_ORGANISATION"], ns["SEO_GEO_LIEU"]
    v("Organization : e-mail, sameAs, fondateur, 2023",
      _org["email"] == "contact@afroboosteur.com"
      and _org["sameAs"] == ["https://www.instagram.com/afroboosteur",
                             "https://www.facebook.com/profile.php?id=61574448227600"]
      and _org["founder"] == {"@type": "Person", "name": "Henri Bassi", "alternateName": "Coach Bassi"}
      and _org["foundingDate"] == "2023")
    v("Organization : PAS d'adresse (ce n'est pas celle de l'association)", "address" not in _org)
    v("lieu des cours : Chemin des Valangines 97, 2000 Neuchâtel, CH",
      _lieu["address"] == {"@type": "PostalAddress", "streetAddress": "Chemin des Valangines 97",
                           "postalCode": "2000", "addressLocality": "Neuchâtel", "addressCountry": "CH"})
    v("organisation et lieu reliés dans les deux sens",
      _org["location"] == {"@id": _lieu["@id"]} and _lieu["parentOrganization"] == {"@id": _org["@id"]})
    v("aucune note, aucun avis, aucun prix, aucun téléphone",
      not any(m in json.dumps(_blocs) for m in ("aggregateRating", "review", "price", "telephone")))

    print("\n== 4. Bloc de l'accueil (`_serve_spa`) ==")
    ns4 = monter("_SEO_GEO_ANCRE_ROOT", "_SEO_GEO_BLOC_ACCUEIL", "_seo_geo_accueil", ns={})
    with tempfile.TemporaryDirectory() as d:
        f = os.path.join(d, "index.html")
        io.open(f, "w", encoding="utf-8").write(INDEX)
        _acc = ns4["_seo_geo_accueil"](f)
        v("le bloc est posé", _acc is not None and 'id="af-presentation"' in _acc)
        v("juste APRÈS la zone React (jamais dedans)",
          _acc is not None and '<div id="root"></div><section id="af-presentation"' in _acc)
        v("le reste de la page est inchangé à l'octet près",
          _acc is not None and _acc.replace(ns4["_SEO_GEO_BLOC_ACCUEIL"], "", 1) == INDEX)
        _bloc = ns4["_SEO_GEO_BLOC_ACCUEIL"]
        v("texte exact du bloc",
          "Afroboost — Cardio-danse Afrobeat à Neuchâtel" in _bloc
          and ("Cours collectifs avec un coach, accessibles aux débutants : pas besoin de savoir danser. "
               "Le mercredi à 18h45 et le dimanche à 18h30, au Chemin des Valangines 97, à Neuchâtel. "
               "Ton premier cours est offert.") in _bloc)
        v("deux VRAIS liens <a href>",
          re.search(r'<a href="/cours-essai-gratuit-neuchatel"[^>]*>Réserver mon cours d\'essai gratuit</a>', _bloc)
          is not None and re.search(r'<a href="/a-propos"[^>]*>Qui est Coach Bassi \?</a>', _bloc) is not None)
        v("pas de texte caché (ni display:none, ni visibility:hidden, ni hors écran)",
          not re.search(r"display:\s*none|visibility:\s*hidden|left:\s*-\d|font-size:\s*0", _bloc))
        v("couleur du coach respectée (var(--primary-color) avec repli)", "var(--primary-color, #D91CD2)" in _bloc)
        io.open(f, "w", encoding="utf-8").write(INDEX.replace('<div id="root"></div>', '<div id="app"></div>'))
        v("ancre absente -> None (le fichier est servi tel quel)", ns4["_seo_geo_accueil"](f) is None)
    _spa = source_de("_serve_spa")
    v("condition : `/` exact ET sans paramètre (?link= / ?offre= intacts)",
      'if not str(full_path or "").strip("/") and not request.url.query:' in _spa)
    v("les chemins privés passent AVANT (noindex inchangé)", _spa.index("_seo_est_prive") < _spa.index("_seo_geo_accueil"))
    v("un vrai fichier passe AVANT tout", _spa.index("_os.path.isfile") < _spa.index("_seo_geo_accueil"))
    v("en cas d'erreur : la page d'origine", "except Exception as _geo_err" in _spa)
    # Le chemin `/` est le SEUL qui reçoit le bloc : on rejoue la condition sur
    # toutes les adresses à protéger.
    def _recoit(chemin, query):
        return (not str(chemin or "").strip("/")) and not query
    for chemin, query in (("", "link=b83914b4-c5a"), ("", "offre=abc&reserver=1"), ("espace/AFR-1", ""),
                          ("duo/tok", ""), ("parrainage", ""), ("checkout", ""), ("admin", ""),
                          ("coach/bassi", ""), ("partner/x", ""), ("login", "")):
        v("« /%s%s » ne reçoit PAS le bloc" % (chemin, ("?" + query) if query else ""), not _recoit(chemin, query))
    v("« / » reçoit le bloc", _recoit("", ""))

    print("\n== 5. Page d'essai ==")
    db, j = M1.monde()
    _, page = await M1.rendre(db, j)
    v("H1 = ligne descriptive", "<h1>Cardio-danse Afrobeat à Neuchâtel — 1er cours offert</h1>" in page)
    v("slogan conservé en grand, juste dessous",
      '</h1>\n<p class="slogan">DANSE. TRANSPIRE. LÂCHE PRISE.</p>' in page and ".slogan{font-size:clamp(1.9rem" in page)
    v("description exacte",
      'content="Afroboost Neuchâtel : cardio-danse africaine et fitness, avec un coach, en groupe. '
      'Pas besoin de savoir danser. Ton premier cours est offert."' in page)
    v("badges : « Aucun matériel à apporter »",
      "<li>Débutants bienvenus</li><li>Environ 1 heure</li><li>Aucun matériel à apporter</li><li>Neuchâtel</li>" in page)
    v("bloc musique remplacé",
      "<b>La musique, à fond.</b> Afrobeat, énergie de groupe et un coach qui te guide à chaque mouvement. "
      "On arrive seul, on repart avec le sourire." in page)
    # Le casque n'a plus droit de cité QUE dans : le bloc Silent (été), la FAQ
    # « Et le casque audio ? » (qui dit justement « sans casque en salle »), et
    # le texte alternatif de la photo d'été (description, pas promesse).
    _ete = page.split('<section class="ete">')[1].split("</section>")[0]
    _sans_ete = page.replace(_ete, "")
    _sans_ete = re.sub(r'alt="[^"]*"', "", _sans_ete)
    _sans_ete = re.sub(r'<script type="application/ld\+json">.*?</script>', "", _sans_ete, flags=re.S)
    _visible_faq = "Et le casque audio ?"
    _reponse = ("En salle, le cours se fait sans casque, sur la musique de la salle. Les casques audio sont "
                "réservés aux séances d'été au bord du lac (Afroboost Silent) et aux événements spéciaux.")
    _reste = _sans_ete.replace(_visible_faq, "")
    _reste = _reste.replace("En salle, le cours se fait sans casque, sur la musique de la salle. Les casques audio sont "
                            "réservés aux séances d&#x27;été au bord du lac (Afroboost Silent) et aux événements spéciaux.", "")
    v("plus AUCUNE promesse de casque hors Silent / FAQ casque / alt photo",
      "casque" not in _reste.lower(), re.findall(r".{40}casque.{40}", _reste.lower())[:3])
    v("bloc « Et l'été, Afroboost Silent » INTACT",
      "<h2>Et l’été, Afroboost Silent</h2>" in page
      and "les séances <b>Silent</b> au bord du lac, casque sur les oreilles" in page)
    v("phrases retirées : « Le casque est fourni »", "casque est fourni" not in page.lower())
    v("« un casque, » retiré du comparatif", "de la musique, un groupe et une communauté" in page)
    v("« avec la musique dans ton casque » retiré", "musique dans\nton casque" not in page and "dans ton casque" not in page)
    _faq = [b for b in (json.loads(x) for x in re.findall(r'application/ld\+json">(.*?)</script>', page, re.S))
            if isinstance(b, list)]
    _objets = _faq[0] if _faq else []
    _faqpage = next((o for o in _objets if o.get("@type") == "FAQPage"), {})
    _qr = {q["name"]: q["acceptedAnswer"]["text"] for q in _faqpage.get("mainEntity", [])}
    v("FAQ JSON-LD : « Et le casque audio ? » + réponse exacte", _qr.get("Et le casque audio ?") == _reponse)
    v("FAQ JSON-LD : « J'ai peur du regard des autres. » réponse exacte",
      _qr.get("J'ai peur du regard des autres.") ==
      "Tout le monde regarde le coach, pas ses voisins. Chacun est dans sa musique et dans son effort.")
    v("FAQ : l'ancienne question a disparu", "C'est quoi exactement, le cours au casque ?" not in _qr)
    v("FAQ : accents remis (majorité, préalable, généralement, âge, français)",
      all(m in json.dumps(_qr, ensure_ascii=False) for m in ("majorité", "préalable", "généralement", "âge", "français"))
      and not any(m in json.dumps(_qr, ensure_ascii=False) for m in ("majorite", "prealable", "generalement")))
    import html as _h
    v("FAQ visible = FAQ JSON-LD (mêmes questions, mêmes réponses)",
      all(("<summary>%s</summary>" % _h.escape(q, quote=True)) in page
          and ("<p>%s</p>" % _h.escape(r, quote=True)) in page for q, r in _qr.items()) and len(_qr) == 12)
    _types = [o.get("@type") for o in _objets]
    v("JSON-LD page d'essai : Organization + SportsActivityLocation + FAQPage + WebPage",
      all(t in _types for t in ("Organization", "SportsActivityLocation", "FAQPage", "WebPage")), _types)
    v("JSON-LD page d'essai : organisation = celle de l'accueil",
      next((o for o in _objets if o.get("@type") == "Organization"), None) == ns["SEO_GEO_ORGANISATION"])
    v("contact : texte exact",
      all(m in page for m in ("<h2>Contact</h2>", "<b>Afroboost — Association Afroboosteur</b>",
                              "Cours : Chemin des Valangines 97, 2000 Neuchâtel",
                              'E-mail : <a href="mailto:contact@afroboosteur.com">contact@afroboosteur.com</a>',
                              'Instagram : <a href="https://www.instagram.com/afroboosteur" target="_blank" rel="noopener">@afroboosteur</a>',
                              "Facebook : <a href=\"https://www.facebook.com/profile.php?id=61574448227600\"")))
    v("contact : aucun numéro de téléphone", "tel:" not in page and "telephone" not in page.lower())
    v("carte : bouton « Afficher la carte » + lien « Itinéraire »",
      '<button type="button" class="carte-btn">Afficher la carte</button>' in page
      and "https://www.google.com/maps/dir/?api=1&amp;destination=" in page and "Itinéraire</a>" in page)
    v("carte : AUCUNE ressource Google avant le clic", sans_google_avant_clic(page))
    v("icônes en SVG (aucun emoji 📍)", "📍" not in page and 'class="itineraire"' in page)
    v("lien « Qui est Coach Bassi ? » vers /a-propos", '<a href="/a-propos">Qui est Coach Bassi ?</a>' in page)
    v("le script de la carte est en fin de body (après </main>)",
      page.index(".carte[data-carte-src]") > page.index("</main>"))
    v("les boutons de réservation mènent TOUJOURS au tunnel d'essai",
      page.count('<a class="cta" href="/?link=b83914b4-c5a">Réserver mon 1er cours gratuit</a>') >= 3)

    print("\n== 6. Page /a-propos ==")
    nsa = {"_m1_echapper": None}
    monter("_m1_echapper", "_m1_jsonld", *CONSTANTES_GEO, "_M1_SITE", "_M1_TUNNEL", "_seo_geo_contact_html",
           "_seo_geo_lien_essai", "SEO_GEO_APROPOS_CHEMIN", "SEO_GEO_APROPOS_TITRE", "SEO_GEO_APROPOS_DESC",
           "SEO_GEO_APROPOS_PHOTO_ALT", "SEO_GEO_APROPOS_PHOTOS", "SEO_GEO_APROPOS_TEXTE",
           "_seo_geo_apropos_photo_html", ns=nsa)
    nsa.update({"json": json, "logger": M1.Journal()})
    from fastapi.responses import HTMLResponse
    nsa["HTMLResponse"] = HTMLResponse
    nsa["Request"] = object
    nsa["__file__"] = os.path.join(RACINE, "api", "server.py")   # -> <racine>/static (absent en local)
    _src_page = source_de("seo_geo_page_a_propos")   # `lineno` = la ligne `def`, sans le décorateur
    exec(compile(_src_page, "a_propos", "exec"), nsa)
    rep = await nsa["seo_geo_page_a_propos"](M1._RequeteNue())
    ap = rep.body.decode("utf-8")
    v("200 text/html", rep.status_code == 200 and "text/html" in str(rep.media_type))
    v("route déclarée sur /a-propos", '@fastapi_app.get(SEO_GEO_APROPOS_CHEMIN, response_class=HTMLResponse)' in SRC
      and 'SEO_GEO_APROPOS_CHEMIN = "/a-propos"' in SRC)
    v("route déclarée AVANT le catch-all", SRC.index("def seo_geo_page_a_propos") < SRC.index("async def _serve_spa"))
    v("title exact", "<title>Coach Bassi et Afroboost — cardio-danse Afrobeat à Neuchâtel</title>" in ap)
    v("description exacte",
      'content="Ex-basketteur professionnel, Coach Bassi a créé Afroboost en 2023 : un mélange de sport, de danse '
      'et de musique pour booster chacun vers son plein potentiel."' in ap)
    v("indexable + canonical absolu",
      '<meta name="robots" content="index, follow"/>' in ap
      and '<link rel="canonical" href="https://afroboost.com/a-propos"/>' in ap)
    v("un seul H1", ap.count("<h1") == 1)
    for morceau in (
        "<h2>Coach Bassi, le fondateur</h2>",
        "Avant Afroboost, il y a eu le basket. Henri Bassi, dit Coach Bassi, a d'abord été <b>basketteur professionnel</b>.",
        "il s'est formé en <b>fitness et wellness à l'Université de Lausanne</b>",
        "pour se former aux <b>danses traditionnelles et urbaines africaines</b>.",
        "De ce parcours est né <b>Afroboost, en 2023</b> : un concept qui mélange les mouvements de plusieurs sports, "
        "des gestes du quotidien, la danse, la musique et le chant. Ce sont toutes ses passions réunies dans un seul cours.",
        "<h2>Plus qu'un cours : une philosophie</h2>",
        "Depuis tout jeune, Coach Bassi a une conviction : <b>il est fait pour booster les autres</b>, pour les aider "
        "à briller et à atteindre leur plein potentiel. C'est le cœur d'Afroboost : <i>l'art de booster son prochain.</i>",
        "L'Afrique, berceau de l'humanité, est notre racine commune. Afroboost réunit des personnes de tous horizons, "
        "dans leur diversité : <b>un univers uni et divers.</b>",
        "<h2>L'association Afroboosteur</h2>",
        "Afroboost est porté par l'association Afroboosteur, dont la mission est de promouvoir la culture afrobeat "
        "et le bien-être à Neuchâtel à travers des activités sportives et artistiques innovantes.",
    ):
        v("texte exact : « %s… »" % re.sub("<[^>]+>", "", morceau)[:48], morceau in ap)
    v("bouton « Réserver mon cours d'essai gratuit » -> même tunnel que la page d'essai",
      '<a class="cta" href="/?link=b83914b4-c5a">Réserver mon cours d\'essai gratuit</a>' in ap)
    v("bouton placé AVANT le bloc Contact", ap.index('class="cta"') < ap.index("<h2>Contact</h2>"))
    v("bloc Contact identique à la page d'essai", nsa["_seo_geo_contact_html"]() in ap and nsa["_seo_geo_contact_html"]() in page)
    v("carte : AUCUNE ressource Google avant le clic", sans_google_avant_clic(ap))
    _ld = [json.loads(x) for x in re.findall(r'application/ld\+json">(.*?)</script>', ap, re.S)]
    _t = [o.get("@type") for o in (_ld[0] if _ld else [])]
    v("JSON-LD valide : AboutPage + Organization + SportsActivityLocation", _t == ["AboutPage", "Organization", "SportsActivityLocation"], _t)
    v("sans photo déposée : AUCUNE image (ni espace réservé)", "<img" not in ap and "<picture" not in ap)
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "a-propos"))
        io.open(os.path.join(d, "a-propos", "coach-bassi.webp"), "wb").write(b"x")
        io.open(os.path.join(d, "a-propos", "coach-bassi.jpg"), "wb").write(b"x")
        _ph = nsa["_seo_geo_apropos_photo_html"](d)
        v("photo déposée : <picture> WebP + repli JPG + texte alternatif exact",
          '<source srcset="/a-propos/coach-bassi.webp" type="image/webp"/>' in _ph
          and '<img src="/a-propos/coach-bassi.jpg" alt="Coach Bassi guide un cours Afroboost en salle à Neuchâtel"' in _ph)
    v("lien M2-A : un visiteur venu de Google garde sa source",
      "utm_source=google" in nsa["_seo_geo_lien_essai"](type("R", (), {
          "query_params": type("Q", (), {"get": staticmethod(lambda k, d=None: None)})(),
          "headers": type("H", (), {"get": staticmethod(lambda k, d="": "https://www.google.com/" if k == "referer" else d)})(),
      })(), "/a-propos"))

    print("\n== 7. Sitemaps ==")
    _sm = io.open(os.path.join(PUBLIC, "sitemap.xml"), encoding="utf-8").read()
    _locs_public = [l.replace("https://afroboost.com", "") for l in re.findall(r"<loc>([^<]+)</loc>", _sm)]
    _api = source_de("get_sitemap")
    _locs_api = [l for l in re.findall(r"\{base_url\}(/[^<]*)</loc>", _api) if "{slug}" not in l]
    v("sitemap.xml public : /a-propos présent", "/a-propos" in _locs_public, _locs_public)
    v("/api/sitemap.xml : /a-propos présent", "/a-propos" in _locs_api, _locs_api)
    v("les deux sitemaps listent les MÊMES pages fixes, dans le même ordre", _locs_public == _locs_api,
      (_locs_public, _locs_api))
    v("robots.txt intact (déclare toujours le sitemap)",
      "Sitemap: https://afroboost.com/sitemap.xml" in io.open(os.path.join(PUBLIC, "robots.txt"), encoding="utf-8").read())

    print("\n%d/%d au vert" % (len(OK), len(OK) + len(KO)))
    return not KO


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) else 1)

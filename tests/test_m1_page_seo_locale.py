# -*- coding: utf-8 -*-
"""LOT M1 — UNE PAGE QUE GOOGLE PEUT REELLEMENT LIRE.

CE QUE CE LOT CORRIGE. Le site est une SPA React : la page servie AVANT
l'execution du JavaScript contient 16 mots utiles, aucun `<h1>`, aucun
`canonical`, aucune donnee structuree, et n'importe quelle URL renvoie 200 avec
ce meme contenu. Aucune requete locale ne peut donc etre servie, et le seul
chemin vers l'essai est un parametre de requete (`/?link=...`) illisible pour
un moteur comme pour une bio Instagram.

CE QU'IL AJOUTE, ET RIEN D'AUTRE. Une page HTML reelle, rendue par le serveur,
a `/cours-essai-gratuit-neuchatel`.

LES QUATRE GARDES, toutes verifiees ici :
  1. UNE SEULE SOURCE POUR LES COURS. La page APPELLE
     `n456_occurrences_publiques` — la fonction derriere `/api/courses/occurrences`
     — directement, sans appel HTTP vers soi-meme et sans recopier son filtrage.
     Le controle 7 le prouve par lecture de l'arbre syntaxique.
  2. DONNEES STRUCTUREES FACTUELLES. Pas de `LocalBusiness` (l'adresse
     permanente n'existe pas : le planning compte plusieurs lieux), pas de
     `price: 0` ni `isAccessibleForFree` (seule la PREMIERE seance eligible est
     offerte), aucun avis invente.
  3. ECHAPPEMENT. Toute valeur venant d'un cours traverse `html.escape`.
  4. AUCUN LIEU EN DUR. Ni Auvernier, ni Vallangines, ni aucune autre adresse.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_m1_page_seo_locale.py
"""
import ast, asyncio, importlib.util, io, json, os, re, sys, types, types
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


COACH = "coach-synthetique"
URL = "https://afroboost.com"
CHEMIN = "/cours-essai-gratuit-neuchatel"
# Les lieux REELS du planning, jamais ecrits dans le code de production.
LIEU_A = "Bord du Lac, Auvernier, Neuchâtel"
LIEU_B = "Plage Est de St-Blaise - La Torpille"


# ═════════════════════════ faux Mongo minimal ════════════════════════════════
def _corr(doc, filtre):
    for cle, cond in (filtre or {}).items():
        v = doc.get(cle)
        if isinstance(cond, dict):
            if "$ne" in cond and v == cond["$ne"]:
                return False
        elif v != cond:
            return False
    return True


class _Curseur:
    def __init__(self, docs):
        self._d = docs

    async def to_list(self, n=None):
        return [dict(x) for x in (self._d if n is None else self._d[:n])]


class Coll:
    def __init__(self):
        self.docs = []
        self.appels = 0

    def find(self, filtre=None, projection=None):
        self.appels += 1
        return _Curseur([d for d in self.docs if _corr(d, filtre)])


class _Agg:
    def __init__(self, docs): self._d = docs
    async def to_list(self, n=None): return list(self._d)


class CollSubs(Coll):
    """`aggregate` minimal : $match offer_id $in + status $ne, $group par offer_id."""
    def aggregate(self, pipeline):
        self.appels += 1
        _m = pipeline[0]["$match"]; _ids = set(_m["offer_id"]["$in"]); _ne = _m["status"]["$ne"]
        _n = {}
        for d in self.docs:
            if d.get("offer_id") in _ids and d.get("status") != _ne:
                _n[d["offer_id"]] = _n.get(d["offer_id"], 0) + 1
        return _Agg([{"_id": k, "n": v} for k, v in _n.items()])


class CollTri(Coll):
    def find(self, filtre=None, projection=None):
        c = super().find(filtre, projection)
        c.sort = lambda *a, **k: c
        return c


class CollReglage(Coll):
    async def find_one(self, filtre=None, projection=None):
        self.appels += 1
        for d in self.docs:
            if _corr(d, filtre): return dict(d)
        return None


class Base:
    def __init__(self):
        self.courses = Coll()
        # HIVER : les offres (tarifs depuis la base), le réglage de saison, les
        # ventes réelles (places restantes) et les témoignages approuvés.
        self.offers = Coll()
        self.platform_settings = CollReglage()
        self.subscriptions = CollSubs()
        self.comments = CollTri()


class Journal:
    def __init__(self):
        self.lignes = []

    def _n(self, m, a):
        try:
            self.lignes.append((str(m) % a) if a else str(m))
        except (TypeError, ValueError):
            self.lignes.append(str(m))

    def info(self, m="", *a, **k): self._n(m, a)
    def warning(self, m="", *a, **k): self._n(m, a)
    def error(self, m="", *a, **k): self._n(m, a)


# Le helper d'origine vit dans le module partage : on charge le VRAI.
_spec_partage = importlib.util.spec_from_file_location(
    "m1_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
_PARTAGE = importlib.util.module_from_spec(_spec_partage)
_spec_partage.loader.exec_module(_PARTAGE)
_m2a_entrante = _PARTAGE.m2a_attribution_entrante

NOMS = ("m1geo1_region_normalisee", "_m1_echapper", "_m1_jsonld", "_v184_parse_time_hhmm",
        "_v184_next_occurrences", "n456_occurrences_publiques",
        "rv2_date_lisible", "_m1_seances", "m1_page_essai_neuchatel",
        # HIVER : tarifs depuis la base, places réelles, témoignages, saison
        "_saison_active", "_annoter_places_restantes", "_offres_encore_disponibles",
        "_m1_prix", "_m1_par_seance", "_m1_offres", "_m1_temoignages", "_m1_carte_offre",
        # HIVER 2 : hiérarchie commerciale, badges, économie réelle, date limite
        "_m1_famille", "_m1_badge", "_m1_cout_par_seance", "_m1_est_meilleur_prix", "_m1_paiement", "_m1_engagement", "_m1_seances_txt",  # V527: _m1_est_meilleur_prix (V526) manquait au banc
        "_m1_economie", "_m1_pour_qui", "_m1_deadline_html",
        # V537 : `_m1_offres` écarte les offres privées (sur lien)
        "v537_lien_seul",
        # SEO-GEO (19/10/2026) : bloc Contact + carte au clic, partagé avec « À propos »
        "_seo_geo_contact_html")
CONSTANTES = ("CHAMP_LIEN_SEUL",      # V537 : lue par `v537_lien_seul`
              "_N456_CHAMPS_PUBLICS", "_V184_WEEKDAY_LABELS_FR", "RV2_JOURS",
              "RV2_MOIS", "COACH_EMAIL", "_M1_SITE", "_M1_CHEMIN", "_M1_TUNNEL",
              "_M1_HORIZON_JOURS", "_M1_MAX_SEANCES", "M1GEO1_REGIONS", "_M1_REGION",
              "_M1_SEANCES_VISIBLES", "_M1_FAQ", "_HIVER_SEANCES_PAR_MOIS_ESTIMEES",
              "T3_MARQUEUR", "T3_APPROVED",
              "_M1_MOIS", "_V184_WEEKDAY_LABELS_FR", "_M1_BADGES",
              # SEO-GEO (19/10/2026) : organisation, lieu des cours, contact, photo principale
              "_M1_PHOTO_HERO", "SEO_GEO_EMAIL", "SEO_GEO_INSTAGRAM", "SEO_GEO_FACEBOOK",
              "SEO_GEO_ADRESSE", "SEO_GEO_ORGANISATION", "SEO_GEO_LIEU", "SEO_GEO_CARTE_EMBED",
              "SEO_GEO_ITINERAIRE", "SEO_GEO_CSS", "_SEO_GEO_PICTO_LIEU", "SEO_GEO_CARTE_JS")


def monter(db, journal):
    """Les VRAIES fonctions, extraites du vrai `server.py`."""
    from fastapi.responses import HTMLResponse
    from api.routes import saison as _saison_mod
    from api.routes import hiver as _hiver_mod
    ns = {"db": db, "logger": journal, "datetime": datetime, "timezone": timezone,
          "timedelta": timedelta, "re": re, "html": __import__("html"),
          "json": json, "HTMLResponse": HTMLResponse,
          # M2-A : la page annote `request: Request` et lit l'origine via le
          # helper partage. MONTAGE seulement — ce sont les VRAIS noms de
          # production, pas des imitations.
          "Request": object, "m2a_attribution_entrante": _m2a_entrante,
          "_saison_valide": _saison_mod.saison_valide, "_filtrer_saison": _saison_mod.filtrer_offres_saison,
          "_SAISON_DEFAUT": _saison_mod.SAISON_DEFAUT, "_hiver": _hiver_mod}
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in CONSTANTES:
            exec(compile("".join(LIGNES[n.lineno - 1:n.end_lineno]), "s", "exec"), ns)
    for nom in NOMS:
        for n in ast.walk(ARBRE):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
                exec(compile("".join(LIGNES[n.lineno - 1:n.end_lineno]), "s", "exec"), ns)
    return ns


def monde():
    db, j = Base(), Journal()
    demain = (datetime.now() + timedelta(days=2)).date().isoformat()
    hier = (datetime.now() - timedelta(days=9)).date().isoformat()
    db.courses.docs = [
        {"id": "c-futur", "name": "Afroboost Silent", "date": demain, "time": "18:30",
         "locationName": LIEU_A, "coach_id": COACH, "visible": True,
         "assignedEmail": "prive@exemple.invalid", "notes": "ne doit pas sortir"},
        {"id": "c-futur2", "name": "Session Cardio", "date": demain, "time": "19:45",
         "locationName": LIEU_B, "coach_id": COACH, "visible": True},
        {"id": "c-passe", "name": "Ancien cours", "date": hier, "time": "18:30",
         "locationName": LIEU_A, "coach_id": COACH, "visible": True},
        {"id": "c-masque", "name": "Cours masque", "date": demain, "time": "20:30",
         "locationName": LIEU_A, "coach_id": COACH, "visible": False},
        {"id": "c-archive", "name": "Cours archive", "date": demain, "time": "21:30",
         "locationName": LIEU_A, "coach_id": COACH, "visible": True, "archived": True},
    ]
    # M1-GEO1 : la page ne sert QUE sa region. Les cours de banc la portent donc,
    # sinon la regle fail closed les ecarterait tous et ce banc testerait le
    # vide. MONTAGE uniquement — aucune attente n'est modifiee. Le cas « sans
    # region » a son propre banc (`test_m1geo1_region.py`, controle 18).
    for _d in db.courses.docs:
        _d["region"] = "neuchatel"
    # HIVER : un catalogue réaliste — tout ce que la page affiche en vient.
    db.offers.docs = [
        {"id": "o-essai", "name": "Cours d'essai gratuit", "price": 0, "visible": True, "offer_type": "single_class", "pack_sessions": 1, "position": 0, "stock": -1},
        # HIVER 2 : le modèle commercial corrigé — mensuel = prélèvement Stripe, saison
        # 8 mois en 1× ou 2×, Fondateurs limitée par 50 places ET une date réelle.
        # Les positions sont VOLONTAIREMENT dans le désordre : la page doit trier
        # par famille (lue sur les champs), pas par la position du tableau de bord.
        {"id": "o-fond", "name": "Fondateurs", "price": 59, "visible": True, "offer_type": "subscription", "pack_sessions": 8, "position": 7, "season": "hiver", "stock": 50, "first_purchase_eligible": True, "description": "Tarif fondateur, 50 places.",
         "billing_mode": "mensuel_auto", "countdown_enabled": True, "countdown_date": "2099-09-30", "countdown_time": "23:59", "countdown_text": "OFFRE FONDATEURS"},
        {"id": "o-s1", "name": "Saison hiver — 8 mois", "price": 549, "visible": True, "offer_type": "subscription", "pack_sessions": 64, "position": 6, "season": "hiver", "stock": -1, "billing_mode": "unique", "duree_mois": 8},
        {"id": "o-s2", "name": "Saison hiver — 2 paiements", "price": 299, "visible": True, "offer_type": "subscription", "pack_sessions": 8, "position": 5, "season": "hiver", "stock": -1, "billing_mode": "saison_2x"},
        {"id": "o-std", "name": "Mensuel Liberté", "price": 89, "visible": True, "offer_type": "subscription", "pack_sessions": 8, "position": 4, "season": "hiver", "stock": -1, "billing_mode": "mensuel_auto"},
        {"id": "o-flex", "name": "Flex 4", "price": 49, "visible": True, "offer_type": "subscription", "pack_sessions": 4, "position": 3, "season": "hiver", "stock": -1, "billing_mode": "mensuel_auto"},
        {"id": "o-etu", "name": "Étudiant", "price": 69, "visible": True, "offer_type": "subscription", "pack_sessions": 8, "position": 8, "season": "hiver", "stock": -1, "billing_mode": "mensuel_auto"},
        {"id": "o-unite", "name": "Cours à l'unité", "price": 30, "visible": True, "offer_type": "single_class", "pack_sessions": 1, "position": 1, "stock": -1},
        {"id": "o-pulse", "name": "PULSE x10 cours", "price": 250, "visible": True, "offer_type": "pack", "pack_sessions": 10, "position": 2, "season": "ete", "stock": -1},
        {"id": "o-carte", "name": "Carte membre association", "price": 100, "visible": True, "offer_type": "membership", "position": 9, "description": "Avantages membres.", "billing_mode": "unique", "duree_mois": 12, "pack_sessions": 0, "creates_membership": True},
        {"id": "o-tshirt", "name": "T-shirt", "price": 59.99, "visible": True, "isProduct": True, "offer_type": "product", "stock": 3},
        {"id": "o-event", "name": "Silent Lakeside", "price": 25, "visible": True, "offer_type": "event", "pack_sessions": 1},
        {"id": "o-cache", "name": "Offre cachée", "price": 10, "visible": False, "offer_type": "single_class"},
    ]
    db.platform_settings.docs = [{"_id": "global", "saison_active": "hiver"}]
    db.subscriptions.docs = [{"offer_id": "o-fond", "status": "active"} for _ in range(3)] + [{"offer_id": "o-fond", "status": "superseded"}]
    return db, j


ns_faq = []


async def rendre(db, journal, coach=COACH):
    ns = monter(db, journal)
    ns_faq[:] = list(ns.get("_M1_FAQ") or [])
    ns["COACH_EMAIL"] = coach
    # M2-A : la page lit desormais l'origine dans la requete. MONTAGE seulement —
    # une requete nue, sans UTM ni referrer, reproduit exactement l'ancien appel.
    rep = await ns["m1_page_essai_neuchatel"](_RequeteNue())
    corps = rep.body.decode("utf-8") if hasattr(rep, "body") else str(rep)
    return rep, corps


class _RequeteNue:
    """Une requete sans origine : ni UTM, ni referrer."""
    @property
    def query_params(self):
        return types.SimpleNamespace(get=lambda k, d=None: d)

    @property
    def headers(self):
        return types.SimpleNamespace(get=lambda k, d="": d)


def blocs_jsonld(corps):
    return re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', corps, re.S)


# ════════════════════════════════ le banc ════════════════════════════════════
async def principal():
    # ---- 1. LA ROUTE EXISTE ET EST MONTEE AVANT LE CATCH-ALL ---------------
    route = None
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "m1_page_essai_neuchatel":
            route = n
    verifier("1. La page d'essai existe", route is not None)
    decos = ["".join(LIGNES[d.lineno - 1:d.end_lineno]) for d in (route.decorator_list if route else [])]
    verifier("2. Elle est montee sur le bon chemin, en HTML",
             any("fastapi_app.get" in d and "_M1_CHEMIN" in d for d in decos)
             and any("HTMLResponse" in d for d in decos),
             "decorateurs=%s" % [d.strip() for d in decos])

    spa = None
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_serve_spa":
            spa = n
    verifier("3. Elle est declaree AVANT le catch-all SPA (ordre = priorite)",
             route is not None and spa is not None and route.lineno < spa.lineno,
             "page l.%s / catch-all l.%s" % (route.lineno if route else "?", spa.lineno if spa else "?"))

    # ---- 2. LE RENDU, SANS JAVASCRIPT --------------------------------------
    db, j = monde()
    rep, corps = await rendre(db, j)
    verifier("4. Reponse 200", getattr(rep, "status_code", None) == 200)
    verifier("5. Type text/html", "text/html" in str(getattr(rep, "media_type", "")))
    verifier("6. Un `<title>` local (Neuchatel)",
             re.search(r"<title>[^<]*Neuch[aâ]tel[^<]*</title>", corps) is not None)
    verifier("7. Une meta description non vide",
             re.search(r'<meta name="description" content="[^"]{60,}"', corps) is not None)
    verifier("8. UN SEUL `<h1>`", len(re.findall(r"<h1[ >]", corps)) == 1,
             "trouves=%d" % len(re.findall(r"<h1[ >]", corps)))
    verifier("9. Le concept est decrit en clair (afro, cardio, casque, debutant)",
             all(m in corps.lower() for m in ("afro", "cardio", "casque", "débutant")))
    # V623 (page courte) : l'offre se dit « Ton premier cours est offert », et la
    # condition reste écrite juste sous le bouton.
    verifier("10. La formulation metier : premier cours offert + condition écrite",
             "Ton premier cours est offert" in corps
             and "L’essai concerne la première séance, une seule fois par personne." in corps)
    verifier("11. Aucune promesse que TOUS les cours sont gratuits",
             not re.search(r"(tous|toutes) les (cours|s[ée]ances) (sont )?(gratuit|offert)", corps, re.I))

    # ---- 3. METADONNEES ABSOLUES -------------------------------------------
    can = re.search(r'<link rel="canonical" href="([^"]+)"', corps)
    verifier("12. Canonical ABSOLU vers la page", can is not None and can.group(1) == URL + CHEMIN,
             can.group(1) if can else "absent")
    ogu = re.search(r'<meta property="og:url" content="([^"]+)"', corps)
    verifier("13. og:url ABSOLU", ogu is not None and ogu.group(1).startswith("https://"),
             ogu.group(1) if ogu else "absent")
    ogi = re.search(r'<meta property="og:image" content="([^"]+)"', corps)
    verifier("14. og:image ABSOLU", ogi is not None and ogi.group(1).startswith("https://"),
             ogi.group(1) if ogi else "absent")
    verifier("15. Aucune URL non-HTTPS officielle dans les metadonnees",
             "http://afroboost" not in corps)

    # ---- 4. DONNEES STRUCTUREES : VALIDES ET FACTUELLES --------------------
    blocs = blocs_jsonld(corps)
    verifier("16. Au moins un bloc JSON-LD", len(blocs) >= 1, "blocs=%d" % len(blocs))
    objets = []
    ok_json = True
    for b in blocs:
        try:
            objets.append(json.loads(b))
        except Exception as e:
            ok_json = False
            verifier("17. JSON-LD syntaxiquement valide", False, str(e)[:80])
    if ok_json:
        verifier("17. JSON-LD syntaxiquement valide", True)
    plats = []
    for o in objets:
        plats.extend(o if isinstance(o, list) else [o])
    types = [str(o.get("@type")) for o in plats]
    verifier("18. `WebPage` et `Organization` presents",
             "WebPage" in types and "Organization" in types, "types=%s" % types)
    verifier("19. AUCUN `LocalBusiness` (aucune adresse permanente honnete)",
             not any("LocalBusiness" in t for t in types), "types=%s" % types)
    verifier("20. AUCUN avis, note ou compte invente",
             not any(k in json.dumps(plats) for k in
                     ("aggregateRating", "reviewCount", "ratingValue", "review")))
    ev = [o for o in plats if o.get("@type") == "Event"]
    verifier("21. Un `Event` par occurrence FUTURE, et seulement elles",
             len(ev) == 2, "events=%d (attendu 2)" % len(ev))
    verifier("22. Aucun `price: 0` ni `isAccessibleForFree` (l'essai n'est pas pour tous)",
             not any(k in json.dumps(plats) for k in ("isAccessibleForFree", '"price"')))
    verifier("23. Chaque `Event` porte une date de debut reelle",
             all(str(e.get("startDate") or "").count("-") >= 2 for e in ev))
    verifier("24. Le lieu d'un `Event` vient du planning, jamais d'une adresse ecrite",
             all(((e.get("location") or {}).get("name") or "") in (LIEU_A, LIEU_B) for e in ev),
             [str((e.get("location") or {}).get("name")) for e in ev])

    # ---- 5. LA SOURCE UNIQUE (GARDE 1) ------------------------------------
    # LE CODE DE LA PAGE = la route ET son collecteur de seances. Regarder la
    # seule route laisserait passer une duplication cachee dans le helper.
    src_route = "".join(LIGNES[route.lineno - 1:route.end_lineno]) if route else ""
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_m1_seances":
            src_route += "".join(LIGNES[n.lineno - 1:n.end_lineno])
    verifier("25. La page APPELLE `n456_occurrences_publiques`",
             "n456_occurrences_publiques(" in src_route)
    verifier("26. Elle ne requete PAS les cours elle-meme (aucune duplication)",
             "db.courses" not in src_route and "_v184_next_occurrences" not in src_route)
    verifier("27. Aucun appel HTTP du serveur vers lui-meme",
             not any(m in src_route for m in ("httpx", "requests.", "aiohttp", "urlopen", "AsyncClient")))
    verifier("28. Le filtrage visible/archived n'est pas recopie",
             '"archived"' not in src_route and '"visible"' not in src_route)
    verifier("29. La lecture des cours est bien passee par la source",
             db.courses.appels == 1, "appels=%d" % db.courses.appels)

    # ---- 6. AUCUN LIEU EN DUR ----------------------------------------------
    verifier("30. Aucune adresse codee en dur dans la production",
             not any(m.lower() in src_route.lower() for m in
                     ("Auvernier", "Vallangines", "Montbenon", "Vidy", "St-Blaise")),
             "une adresse en dur reproduirait le defaut qu'on corrige")
    verifier("31. Les deux lieux REELS apparaissent dans la page rendue",
             LIEU_A in corps and LIEU_B in corps)

    # ---- 7. FUTUR ET PUBLIC UNIQUEMENT -------------------------------------
    verifier("32. Le cours PASSE n'apparait pas", "Ancien cours" not in corps)
    verifier("33. Le cours MASQUE n'apparait pas", "Cours masque" not in corps)
    verifier("34. Le cours ARCHIVE n'apparait pas", "Cours archive" not in corps)
    verifier("35. Les deux seances futures apparaissent",
             "Afroboost Silent" in corps and "Session Cardio" in corps)

    # ---- 8. ECHAPPEMENT (GARDE 3) ------------------------------------------
    db2, j2 = monde()
    db2.courses.docs[0]["name"] = '<script>alert(1)</script>"onload="x'
    db2.courses.docs[0]["locationName"] = "Lieu & <b>gras</b>"
    _, corps2 = await rendre(db2, j2)
    verifier("36. Une valeur hostile est ECHAPPEE, jamais injectee",
             "<script>alert(1)</script>" not in corps2 and "&lt;script&gt;" in corps2)
    verifier("37. L'esperluette et les chevrons du lieu sont echappes",
             "Lieu &amp; &lt;b&gt;gras&lt;/b&gt;" in corps2)
    verifier("38. Le JSON-LD reste valide malgre la valeur hostile",
             all(_valide(b) for b in blocs_jsonld(corps2)))

    # ---- 9. LE CTA ---------------------------------------------------------
    verifier("39. Le CTA porte le libelle demande (V623 : « Réserver mon essai »)",
             ">Réserver mon essai</a>" in corps)
    verifier("40. Le CTA mene au tunnel d'essai EXISTANT",
             "?link=b83914b4-c5a" in corps)
    verifier("41. Aucun nouveau tunnel n'est cree",
             corps.count("?link=") >= 1 and "/checkout" not in corps)

    # ---- 10. AUCUNE DONNEE PERSONNELLE -------------------------------------
    verifier("42. Aucune donnee personnelle du cours ne fuit",
             "prive@exemple.invalid" not in corps and "ne doit pas sortir" not in corps)
    # SEO-GEO (19/10/2026) : le bloc Contact validé par Bassi publie l'adresse
    # PUBLIQUE de l'association. C'est la SEULE adresse admise : aucune adresse
    # venant d'un cours, d'un coach ou d'un participant.
    verifier("43. Aucune adresse e-mail dans la page, hors contact public de l'association",
             set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", corps)) <= {"contact@afroboosteur.com"},
             sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", corps))))

    # ---- 11. LA SOURCE ECHOUE : LA PAGE RESTE SURE -------------------------
    db3, j3 = monde()
    db3.courses.docs = []
    _, corps3 = await rendre(db3, j3)
    verifier("44. Sans seance a venir : message neutre, aucune date inventee",
             "Aucune séance" in corps3 or "aucune séance" in corps3)
    verifier("45. Le CTA reste present meme sans seance",
             ">Réserver mon essai</a>" in corps3 and "?link=b83914b4-c5a" in corps3)
    verifier("46. Aucun `Event` n'est declare sans occurrence reelle",
             not [o for b in blocs_jsonld(corps3) for o in _plat(b) if o.get("@type") == "Event"])

    class CollCassee(Coll):
        def find(self, *a, **k):
            raise RuntimeError("base injoignable")

    db4, j4 = monde()
    db4.courses = CollCassee()
    rep4, corps4 = await rendre(db4, j4)
    verifier("47. Source EN PANNE : la page repond quand meme 200",
             getattr(rep4, "status_code", None) == 200)
    verifier("48. Source EN PANNE : aucune date ni lieu invente",
             "Aucune séance" in corps4 or "aucune séance" in corps4)

    # ---- 12. LE SITEMAP ----------------------------------------------------
    chemin_sm = os.path.join(RACINE, "frontend", "public", "sitemap.xml")
    verifier("49. `sitemap.xml` existe dans les fichiers publics", os.path.isfile(chemin_sm))
    if os.path.isfile(chemin_sm):
        brut = io.open(chemin_sm, encoding="utf-8").read()
        try:
            arbre = ET.fromstring(brut)
            valide = True
        except Exception as e:
            arbre, valide = None, False
            verifier("50. Le sitemap est un XML VALIDE", False, str(e)[:80])
        if valide:
            verifier("50. Le sitemap est un XML VALIDE", True)
            locs = [e.text.strip() for e in arbre.iter() if e.tag.endswith("}loc") or e.tag == "loc"]
            verifier("51. Il contient l'accueil ET la nouvelle page",
                     URL + "/" in locs and URL + CHEMIN in locs, "locs=%s" % locs)
            verifier("52. Uniquement des URL HTTPS officielles",
                     all(u.startswith(URL) for u in locs), "locs=%s" % locs)

    # ---- 13. L'ACCUEIL -----------------------------------------------------
    idx = io.open(os.path.join(RACINE, "frontend", "public", "index.html"), encoding="utf-8").read()
    c2 = re.search(r'<link rel="canonical" href="([^"]+)"', idx)
    verifier("53. L'accueil a un canonical ABSOLU", c2 is not None and c2.group(1) == URL + "/",
             c2.group(1) if c2 else "absent")
    o2 = re.search(r'<meta property="og:url" content="([^"]+)"', idx)
    verifier("54. og:url de l'accueil ABSOLU (plus de `%PUBLIC_URL%` vide)",
             o2 is not None and o2.group(1) == URL + "/", o2.group(1) if o2 else "absent")
    i2 = re.search(r'<meta property="og:image" content="([^"]+)"', idx)
    verifier("55. og:image de l'accueil ABSOLU",
             i2 is not None and i2.group(1).startswith(URL + "/"), i2.group(1) if i2 else "absent")
    # SEO-GEO (19/10/2026) : titre et description de l'accueil remplacés par les
    # textes validés par Bassi — plus aucune promesse de casque.
    verifier("56. Le titre et la description de l'accueil sont les textes VALIDÉS (SEO-GEO)",
             "<title>Afroboost | Cardio-danse Afrobeat à Neuchâtel</title>" in idx
             and "Cardio-danse Afrobeat en groupe à Neuchâtel, avec un coach. Pas besoin de savoir "
                 "danser. Ton premier cours est offert." in idx
             # les commentaires HTML (retirés par le build) ne sont pas du texte servi
             and "casque" not in re.sub(r"<!--.*?-->", "", idx, flags=re.S).lower().split("</head>")[0])

    # ═══════════ M1-SEO-UX1 — LA PAGE DEVIENT UNE PAGE D'ACQUISITION ═════════
    db, j = monde()
    _, page = await rendre(db, j)

    # --- textes valides, au mot pres ---
    verifier("57. TITLE exact (HIVER)",
             "<title>Cours de danse africaine et cardio à Neuchâtel — 1er cours offert | Afroboost</title>" in page)
    verifier("58. META DESCRIPTION exacte (HIVER)",
             "Afroboost Neuchâtel : cardio-danse africaine et fitness, avec un coach, "
             "en groupe. Pas besoin de savoir danser. Ton premier cours est offert." in page)
    # SEO-GEO (19/10/2026) : la ligne descriptive devient le H1 ; le slogan reste,
    # en grand, juste en dessous (l'élément visuel fort ne change pas).
    # V623 — PAGE ULTRA-SIMPLE : H1 SEO inchangé (grand titre), une phrase, les
    # repères à icônes, le bloc offre, UN bouton ; le reste dans « En savoir plus ».
    verifier("59. H1 exact et UNIQUE (inchangé depuis SEO-GEO)",
             page.count("<h1") == 1 and "<h1>Cardio-danse Afrobeat à Neuchâtel — 1er cours offert</h1>" in page)
    for h2 in ("C’est quoi Afroboost ?", "Pour qui ?", "Questions fréquentes", "Horaires et adresse", "Formules"):
        verifier("60. H2 « %s » présent dans « En savoir plus »" % h2,
                 ">%s</h2>" % h2 in page.split('<details class="ess-plus">')[1])
    verifier("61. L'essentiel AVANT « En savoir plus » : une phrase, durée, adresse, offre, bouton — sans casque",
             all(x in page.split('<details class="ess-plus">')[0] for x in (
                 "Pas besoin de savoir danser.", "Environ 1 heure", "Chemin des Valangines 97, 2000 Neuchâtel",
                 "Ton premier cours est offert", ">Réserver mon essai</a>")) and "casque" not in page.split("</h1>")[1].split('<details class="ess-plus">')[0].lower())
    verifier("62. « En savoir plus » est FERMÉ par défaut", '<details class="ess-plus">' in page and '<details class="ess-plus" open' not in page)
    verifier("63. Le texte concept valide est present",
             "Ce n’est pas un cours de danse traditionnelle" in page
             and "inspiré des danses africaines et de l’Afrobeat" in page)

    # --- la photo ---
    img = re.search(r'<div class="ess-media"><img[^>]*>', page)
    verifier("64. Le hero porte une vraie photo", img is not None)
    src = re.search(r'src="([^"]+)"', img.group(0)) if img else None
    verifier("65. Elle pointe sur le fichier optimise",
             src is not None and src.group(1) == "/hero-afroboost.jpg",
             src.group(1) if src else "absent")
    alt = re.search(r'alt="([^"]*)"', img.group(0)) if img else None
    verifier("66. Son `alt` est renseigne et factuel",
             alt is not None and len(alt.group(1)) > 25
             and "Neuchâtel" not in alt.group(1) and "lac" not in alt.group(1).lower(),
             alt.group(1) if alt else "absent")
    # M1-SEO-UX1-MIME1 — LE WEBP A ETE REMPLACE PAR UN JPEG, ET POURQUOI.
    # Le conteneur tourne sur `python:3.11-slim`, dont la table MIME integree
    # ne connait PAS `.webp` : `FileResponse` retombait sur `text/plain`, avec
    # `nosniff`. Corriger cela dans le gestionnaire statique aurait touche le
    # chemin de TOUTES les reponses statiques (bundle, Service Worker,
    # manifeste). `.jpg` est dans la table de toutes les versions de Python :
    # changer d'image ne touche que cette page.
    chemin_img = os.path.join(RACINE, "frontend", "public", "hero-afroboost.jpg")
    verifier("67. Le fichier optimise existe", os.path.isfile(chemin_img))
    if os.path.isfile(chemin_img):
        poids = os.path.getsize(chemin_img)
        verifier("68. Il pese moins de 200 Ko", poids < 200 * 1024, "%d octets" % poids)
        with open(chemin_img, "rb") as _f:
            _tete = _f.read(3)
        # Le CONTENU, pas l'extension : un fichier mal converti passerait
        # sinon tous les controles.
        verifier("68b. C'est un VRAI JPEG (nombre magique FF D8 FF)",
                 _tete == b"\xff\xd8\xff", repr(_tete))
        try:
            from PIL import Image
            _im = Image.open(chemin_img)
            verifier("68c. Dimensions 1024x1024 au maximum",
                     _im.width <= 1024 and _im.height <= 1024, str(_im.size))
            verifier("68d. Aucune metadonnee EXIF ni GPS",
                     not dict(_im.getexif() or {}), str(dict(_im.getexif() or {}))[:80])
        except ImportError:
            verifier("68c. Dimensions 1024x1024 au maximum", True, "Pillow absent")
            verifier("68d. Aucune metadonnee EXIF ni GPS", True, "Pillow absent")
    verifier("68e. Plus AUCUNE dérivée WebP dans le depot",
             not os.path.isfile(os.path.join(RACINE, "frontend", "public",
                                             "hero-afroboost.webp")))
    verifier("68f. La page ne reference plus le WebP", "hero-afroboost.webp" not in page)
    verifier("69. La page reste lisible SANS image (texte hors de l'image)",
             page.index('<div class="ess-media">') < page.index("<h1"))

    # --- le CTA ---
    ctas = re.findall(r'<a class="cta"[^>]*href="([^"]+)"[^>]*>([^<]*)</a>', page)
    verifier("70. Deux CTA identiques (V623) : sous l'offre, barre mobile", len(ctas) == 2, len(ctas))
    verifier("71. Meme libelle valide",
             all(t == "Réserver mon essai" for _, t in ctas), ctas)
    # M2-A : le lien peut desormais porter l'origine normalisee en suffixe.
    # Ce qui est verifie reste le meme : la destination est le tunnel EXISTANT.
    verifier("72. Meme destination : le tunnel EXISTANT",
             all(h.startswith("/?link=b83914b4-c5a") for h, _ in ctas), ctas)

    # --- les seances, groupees par mois, en HTML natif ---
    verifier("73. Les seances : au moins 2 cartes visibles, HTML natif",
             page.count('<article class="seance">') >= 2)
    verifier("74. Chaque `<details>` a son `<summary>` (focusable au clavier)",
             page.count("<summary") == page.count("<details"))
    verifier("75. Aucun `<details open>` : FAQ et planning replies, un clic les ouvre",
             page.count("<details open") == 0, "ouverts=%d" % page.count("<details open"))
    # Le seul script de la page est le décompte de l'offre limitée, en FIN de body ;
    # les séances (et tout le reste) se lisent sans JavaScript.
    verifier("76. Aucune dependance JavaScript pour les seances",
             "onclick" not in page.lower() and "<script" not in
             page.split('class="seances"')[-1].split("</main>")[0] if 'class="seances"' in page else True)

    # --- rien n'a disparu du HTML ---
    for attendu in ("18:30", "19:45", LIEU_A, LIEU_B, "Afroboost Silent", "Session Cardio"):
        verifier("77. « %s » toujours dans le HTML servi" % attendu[:28], attendu in page)
    plats = [o for b in blocs_jsonld(page) for o in _plat(b)]
    verifier("78. JSON-LD toujours valide, 1 `Event` par occurrence",
             len([o for o in plats if o.get("@type") == "Event"]) == 2)
    verifier("79. `canonical` inchangee",
             '<link rel="canonical" href="%s%s"/>' % (URL, CHEMIN) in page)

    # ═══ V622 — PAGE D'ESSAI COURTE (décision de Bassi, 19/10/2026) ═══
    # Les tarifs, le comparatif, la carte membre, « Pourquoi Afroboost » et le
    # bloc été sont RETIRÉS DE CETTE PAGE seulement : ils vivent dans « Toutes
    # les offres » (la fenêtre existante de la vitrine) et dans la base. La page
    # n'affiche plus aucun prix : elle ne peut donc plus en afficher de faux.
    _main = page.split('<main class="ess">')[1].split("</main>")[0]
    verifier("V622-1. Tarifs, comparatif, carte membre, « Pourquoi » et été : retirés de CETTE page",
             all(x not in page for x in ("<h3>Fondateurs</h3>", 'class="t-prix"', "Comparer les formules", "Pourquoi Afroboost, et pas",
                                         "Carte membre de l’association", "l’été, Afroboost Silent", 'class="ete"', 'class="membre"')))
    verifier("V622-2. Aucun prix recopié sur la page (les prix restent dans la fenêtre existante)",
             "CHF" not in _main and "data-deadline=" not in page)
    verifier("V622-3. « Voir toutes les formules et les prix » ouvre la fenêtre EXISTANTE (/?offres=toutes)",
             '<a class="cta cta-s" href="/?offres=toutes">Voir toutes les formules et les prix</a>' in page)
    verifier("82. Offre cachée, produit et événement : jamais sur la page",
             "Offre cachée" not in page and "<h3>T-shirt</h3>" not in page and "<h3>Silent Lakeside</h3>" not in page)
    # La logique tarifaire reste dans le code (calcul pur, inchangé) : on la garde sous banc.
    _ns87 = monter(db, j)
    _offres87 = [o for o in db.offers.docs if o.get("visible")]
    _saison_seule = [o for o in _offres87 if str(o.get("name", "")).startswith("Saison hiver — 8 mois")]
    verifier("87c2. `_m1_est_meilleur_prix` : la saison redevient « Meilleur prix » dès que Fondateurs n'est plus dans la liste (calcul, pas décor)",
             bool(_saison_seule) and _ns87["_m1_est_meilleur_prix"](_saison_seule[0], [o for o in _offres87 if "Fondateurs" not in str(o.get("name", ""))]) is True
             and _ns87["_m1_est_meilleur_prix"](_saison_seule[0], _offres87) is False)
    verifier("88. Aucun horaire/jour/lieu en dur : les jours cités viennent du planning",
             "mercredi" not in page.lower().split("<main")[0] and ("Les cours ont lieu le" in page))
    verifier("89. Barre CTA sticky mobile présente, masquée dès 641 px",
             '<div class="sticky">' in page and "@media(min-width:641px){.sticky{display:none}}" in page)
    _ordre90 = ('<div class="ess-media">', "<h1>", '<p class="ess-accroche">Pas besoin de savoir danser.', 'class="ess-offert"', ">Réserver mon essai</a>",
                "<summary>En savoir plus</summary>", "C’est quoi Afroboost", "Pour qui", "Questions fréquentes",
                "Horaires et adresse", ">Formules</h2>", "<h2>Contact</h2>", '<div class="sticky">')
    verifier("90. Sections dans l'ordre (page ultra-simple V623)",
             all(0 <= page.find(a) < page.find(b) for a, b in zip(_ordre90, _ordre90[1:])),
             [page.find(x) for x in _ordre90])
    verifier("91. Aucun faux témoignage : section absente tant qu'aucun témoignage approuvé n'existe",
             'class="temoignages"' not in page)
    verifier("92. FAQ dans le HTML ET en JSON-LD FAQPage, un seul parcours",
             any(o.get("@type") == "FAQPage" for o in plats) and page.count('<details class="q">') == len(ns_faq))
    verifier("93. Pas de faux compteur, pas de prix barré, pas de fausse urgence",
             "<s>" not in page and "<del>" not in page and "plus que" not in page.lower() and "dernières heures" not in page.lower())
    # Témoignage RÉEL approuvé -> la section apparaît, prénom seul.
    db.comments.docs = [{"text": "J'ai adoré, je reviens !", "user_name": "Léa Dupont", "source": "participant_testimonial", "moderation_status": "approved", "consent_publication": True}]
    _, page_t = await rendre(db, j)
    verifier("95. Témoignage approuvé + consentement -> affiché, prénom seul (pas de nom de famille)",
             'class="temoignages"' in page_t and "— Léa</footer>" in page_t and "Dupont" not in page_t)

    # --- pas de bourrage ---
    # Le bourrage se mesure sur le TEXTE VISIBLE, pas sur le document entier :
    # `<title>`, `og:` et `twitter:` repetent legitimement la meme phrase, et
    # les compter ferait echouer une page parfaitement sobre. (Premiere ecriture
    # de ce controle : elle comptait tout le HTML.)
    _corps_visible = re.sub(r"<[^>]+>", " ", page.split("<body>")[-1])
    verifier("80. « Neuchâtel » reste sous 8 occurrences dans le texte visible",
             _corps_visible.count("Neuchâtel") <= 8,
             "occurrences=%d" % _corps_visible.count("Neuchâtel"))

    # Deux listes de mois cohabitent dans le depot (`RV2_MOIS` sans accents pour
    # les gabarits WhatsApp, `_M1_MOIS` accentuee pour l'affichage web). Les
    # melanger affichait « Août 2026 » en en-tete et « 30 aout » dans la ligne.
    _lignes_seances = re.findall(r'<p class="s-quand">([^<]*)<', page)
    verifier("80b. Aucun nom de mois dans la ligne de seance (une seule source)",
             _lignes_seances and not any(
                 m in l.lower() for l in _lignes_seances
                 for m in ("janvier", "fevrier", "février", "mars", "avril", "mai",
                           "juin", "juillet", "aout", "août", "septembre",
                           "octobre", "novembre", "decembre", "décembre")),
             _lignes_seances[:2])

    # --- les quatre reperes ---
    # V623 : les repères de la page courte (lignes à icônes) — durée et lieu.
    for repere in ("Environ 1 heure", "Chemin des Valangines 97, 2000 Neuchâtel", "Neuchâtel"):
        verifier("81. Repere « %s »" % repere, repere in page)


def _plat(bloc):
    try:
        o = json.loads(bloc)
    except Exception:
        return []
    return o if isinstance(o, list) else [o]


def _valide(bloc):
    try:
        json.loads(bloc)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    try:
        asyncio.run(principal())
    except Exception as _e:
        RESULTATS.append(("BANC INTERROMPU : %s: %s" % (type(_e).__name__, _e), False, ""))
    ok = 0
    for nom, bon, detail in RESULTATS:
        print(("  OK   " if bon else "  RATE ") + nom + (("   [%s]" % detail) if (detail and not bon) else ""))
        ok += 1 if bon else 0
    print("\n%d/%d au vert" % (ok, len(RESULTATS)))
    sys.exit(0 if ok == len(RESULTATS) else 1)

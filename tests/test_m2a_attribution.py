# -*- coding: utf-8 -*-
"""LOT M2-A — D'OU VIENT VRAIMENT UNE RESERVATION D'ESSAI.

LE PROBLEME, ET IL A DEUX MOITIES.

1. L'UTM MOURAIT AU PREMIER CLIC. La page `/cours-essai-gratuit-neuchatel` est
   du HTML serveur SANS JavaScript, et son CTA etait un `href` constant :
   `?utm_source=instagram` disparaissait des le clic. Pire pour le SEO Google
   sans UTM — si l'on attend la SPA pour lire `document.referrer`, elle voit
   `afroboost.com`, jamais Google. L'origine externe doit donc etre lue
   COTE SERVEUR, a l'arrivee sur la page, et recopiee dans le CTA.

2. LA RESERVATION NAIT DES JOURS PLUS TARD, SOUVENT AILLEURS. Pour l'essai :
   tunnel -> `/checkout/free` -> e-mail -> `/espace/<code>` -> OTP ->
   reservation. Le `localStorage` du navigateur d'origine n'existe plus. Une
   attribution purement navigateur raterait donc le parcours principal. Elle
   est donc PERSISTEE au checkout, sur l'objet durable du code, et RECOPIEE
   sur la reservation le jour venu.

CE QUI NE BOUGE PAS. Le champ metier `source` (`website`/`subscriber_space`)
garde exactement son sens : LOT B3 s'en sert pour decider du montant restitue a
l'annulation. Le marketing vit dans un sous-document `attribution` SEPARE.

FAIL-OPEN PARTOUT : attribution absente, expiree, invalide ou illisible, le
parcours continue. Le suivi n'a jamais le droit de bloquer une reservation.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_m2a_attribution.py
"""
import ast, asyncio, importlib.util, io, os, re, sys, types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
sys.path.insert(0, os.path.join(RACINE, "tests"))

import test_m1_page_seo_locale as M1

_spec = importlib.util.spec_from_file_location(
    "m2a_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

ARBRE, LIGNES = M1.ARBRE, M1.LIGNES
SRC_CHECKOUT = io.open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
                       encoding="utf-8").read()
ARBRE_CHECKOUT = ast.parse(SRC_CHECKOUT)
LIGNES_CHECKOUT = SRC_CHECKOUT.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def source_de(nom, arbre=None, lignes=None):
    arbre = arbre or ARBRE
    lignes = lignes or LIGNES
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    return ""


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


class Req:
    """Une requete FastAPI credible : query insensible a rien, en-tetes en
    minuscules comme Starlette les expose."""
    def __init__(self, params=None, referer=None):
        self._p = dict(params or {})
        self._h = {}
        if referer is not None:
            self._h["referer"] = referer

    @property
    def query_params(self):
        p = self._p
        return types.SimpleNamespace(get=lambda k, d=None: p.get(k, d))

    @property
    def headers(self):
        h = self._h
        return types.SimpleNamespace(get=lambda k, d="": h.get(str(k).lower(), d))


async def page(params=None, referer=None):
    db, j = M1.monde()
    ns = M1.monter(db, j)
    rep = await ns["m1_page_essai_neuchatel"](Req(params, referer))
    return rep.body.decode("utf-8")


def cta_de(html):
    m = re.search(r'<a class="cta" href="([^"]+)"', html)
    return m.group(1) if m else ""


# ═══ V670 — LE MONTAGE DE `share_offer_page` (page de partage d'une offre) ═══
#
# On monte la VRAIE fonction, extraite de `api/server.py`, avec une base
# factice. Rien n'est imite : `m2a_attribution_entrante` n'est PAS injecte dans
# l'espace de noms — la fonction doit l'importer elle-meme, exactement comme en
# production. C'est la lecon de l'incident consigne dans `_noms_libres` : un
# banc qui fournit ce que la production n'a pas est un banc qui ment.

class _CollOffres:
    """Une seule offre visible, `o-ok`. Tout autre identifiant est inconnu."""
    async def find_one(self, filtre, projection=None):
        if (filtre or {}).get("id") != "o-ok":
            return None
        return {"id": "o-ok", "name": "Mensuel Liberté", "price": 89,
                "visible": True, "description": "Accès mensuel."}


class _BaseOffres:
    offers = _CollOffres()


_PARTAGE_DISPO = bool(source_de("share_offer_page"))


def _partage_monte(journal):
    from fastapi.responses import HTMLResponse
    ns = {"db": _BaseOffres(), "logger": journal, "HTMLResponse": HTMLResponse}
    exec(compile(source_de("share_offer_page"), "partage", "exec"), ns)
    return ns["share_offer_page"]


async def partage(params=None, referer=None, offre="o-ok"):
    """(cible de la redirection, corps HTML, reponse, journal)."""
    j = Journal()
    rep = await _partage_monte(j)(offre, Req(params, referer))
    corps = rep.body.decode("utf-8") if getattr(rep, "body", None) else ""
    m = re.search(r'content="0;url=([^"]+)"', corps)
    return (m.group(1) if m else ""), corps, rep, j


def _starlette_request():
    from starlette.requests import Request as _R
    return _R


def _partage_annotation_resolue():
    """Ce que FastAPI fait REELLEMENT de l'annotation differee `"Request"`.

    On lui donne les memes globals que `api/server.py` (ou `Request` est
    importe) et on lui demande la signature typee : si la resolution cessait de
    fonctionner, FastAPI traiterait `request` comme un simple parametre de
    requete et l'origine redeviendrait illisible — en silence.
    """
    try:
        from fastapi.dependencies.utils import get_typed_signature
        ns = {"Request": _starlette_request()}
        exec(compile(source_de("share_offer_page"), "partage", "exec"), ns)
        return get_typed_signature(ns["share_offer_page"]).parameters["request"].annotation
    except Exception as e:  # noqa: BLE001
        return "ECHEC: %s: %s" % (type(e).__name__, e)


async def principal():
    # ═══════════ 1. LES BRIQUES DE NORMALISATION ════════════════════════════
    for nom in ("m2a_valeur_propre", "m2a_source_normalisee", "m2a_source_du_referrer",
                "m2a_attribution_entrante", "m2a_fusionner", "m2a_bloc_propre"):
        verifier("1. `%s` existe" % nom, hasattr(S, nom))
    if not hasattr(S, "m2a_valeur_propre"):
        return

    propre, norm = S.m2a_valeur_propre, S.m2a_source_normalisee
    verifier("2. Les sources autorisees couvrent la liste demandee",
             set(("google", "instagram", "tiktok", "youtube", "facebook",
                  "whatsapp", "partenaire", "direct")) <= set(S.M2A_SOURCES),
             str(getattr(S, "M2A_SOURCES", ())))
    verifier("3. Une source hors liste est REFUSEE, pas recopiee",
             norm("mon-super-canal") == "" and norm("<script>") == "")
    verifier("4. Casse et espaces normalises", norm("  Instagram ") == "instagram")
    verifier("5. Une valeur trop longue est tronquee, jamais rejetee en erreur",
             len(propre("x" * 500)) <= 64, len(propre("x" * 500)))
    verifier("6. Les caracteres dangereux sont retires",
             propre("essai<script>alert(1)</script>") == "essaiscriptalert1script",
             propre("essai<script>alert(1)</script>"))
    verifier("7. `None` et vide ne cassent rien",
             propre(None) == "" and propre("") == "" and norm(None) == "")

    # ═══════════ 2. LE REFERRER, PAR HOTE ET JAMAIS EN ENTIER ═══════════════
    ref = S.m2a_source_du_referrer
    verifier("8. Referrer Google -> google / organic",
             ref("https://www.google.com/search?q=cours+danse+afro+neuchatel") == ("google", "organic"))
    verifier("9. Google regional (google.ch) reconnu",
             ref("https://www.google.ch/") == ("google", "organic"))
    verifier("10. Instagram (l.instagram.com) -> instagram / social",
             ref("https://l.instagram.com/?u=https%3A%2F%2Fafroboost.com") == ("instagram", "social"))
    verifier("11. TikTok, YouTube, Facebook, WhatsApp reconnus",
             ref("https://www.tiktok.com/@x")[0] == "tiktok"
             and ref("https://youtu.be/abc")[0] == "youtube"
             and ref("https://m.facebook.com/")[0] == "facebook"
             and ref("https://wa.me/41000")[0] == "whatsapp")
    verifier("12. Un referrer INTERNE n'est jamais une source",
             ref("https://afroboost.com/cours-essai-gratuit-neuchatel") == ("", ""))
    verifier("13. Un referrer inconnu ne fabrique pas de source",
             ref("https://exemple.invalid/page") == ("", ""))
    verifier("14. Un referrer illisible ne leve jamais",
             ref("pas une url") == ("", "") and ref(None) == ("", ""))

    # ═══════════ 3. LA PAGE M1 TRANSMET L'ORIGINE AU CTA ════════════════════
    rt = source_de("m1_page_essai_neuchatel")
    verifier("15. La page recoit `request` (sans quoi rien n'est lisible)",
             re.search(r"async def m1_page_essai_neuchatel\([^)]*request", rt) is not None)

    html = await page({"utm_source": "instagram", "utm_medium": "social",
                       "utm_campaign": "essai_neuchatel"})
    cta = cta_de(html)
    verifier("16. UTM Instagram recopies dans le CTA",
             "utm_source=instagram" in cta and "utm_medium=social" in cta
             and "utm_campaign=essai_neuchatel" in cta, cta)
    verifier("17. Le CTA mene TOUJOURS au tunnel existant",
             cta.startswith("/?link=b83914b4-c5a"), cta)

    # LE CAS QUI JUSTIFIE TOUT LE LOT : Google SEO, aucune UTM.
    html = await page({}, referer="https://www.google.com/search?q=danse+afro+neuchatel")
    cta = cta_de(html)
    verifier("18. GOOGLE SEO SANS UTM : le CTA porte google / organic",
             "utm_source=google" in cta and "utm_medium=organic" in cta, cta)
    verifier("19. La requete de recherche n'est JAMAIS recopiee",
             "danse+afro" not in cta and "q=" not in cta and "search" not in cta, cta)

    html = await page({"utm_source": "instagram", "utm_medium": "social"},
                      referer="https://www.google.com/search?q=x")
    cta = cta_de(html)
    verifier("20. UTM PRIORITAIRE sur le referrer",
             "utm_source=instagram" in cta and "utm_source=google" not in cta, cta)

    html = await page({}, referer="https://afroboost.com/")
    cta = cta_de(html)
    verifier("21. Navigation INTERNE : aucune source fabriquee",
             "utm_source=" not in cta, cta)

    html = await page({})
    verifier("22. Ni UTM ni referrer : le CTA reste le CTA nu",
             cta_de(html) == "/?link=b83914b4-c5a", cta_de(html))

    html = await page({"utm_source": "x" * 400, "utm_campaign": "<img onerror=1>"})
    cta = cta_de(html)
    verifier("23. UTM malformes : la page rend quand meme, sans injection",
             "<img" not in cta and "onerror" not in cta and len(cta) < 400, cta[:90])
    verifier("24. Une source inconnue n'entre pas dans le CTA",
             "utm_source=xxx" not in cta, cta[:90])

    # ═══════════ 4. LA FUSION first / last ══════════════════════════════════
    f = S.m2a_fusionner
    insta = {"source": "instagram", "medium": "social", "campaign": "essai_neuchatel"}
    whats = {"source": "whatsapp", "medium": "referral", "campaign": "essai_neuchatel"}
    direct = {"source": "direct", "medium": ""}

    a1 = f(None, insta)
    verifier("25. Premiere visite Instagram -> first = last = instagram",
             a1["first"]["source"] == "instagram" and a1["last"]["source"] == "instagram")
    a2 = f(a1, direct)
    verifier("26. Retour DIRECT : first conserve", a2["first"]["source"] == "instagram")
    verifier("27. Retour DIRECT : last non ecrase non plus",
             a2["last"]["source"] == "instagram", a2["last"]["source"])
    a3 = f(a2, whats)
    verifier("28. Instagram puis WhatsApp -> first=instagram, last=whatsapp",
             a3["first"]["source"] == "instagram" and a3["last"]["source"] == "whatsapp")
    a4 = f(None, direct)
    verifier("29. Sans historique, `direct` peut etre l'origine initiale",
             a4["first"]["source"] == "direct")
    verifier("30. Chaque touche porte son horodatage",
             a3["first"].get("touch_at") and a3["last"].get("touch_at"))
    verifier("31. Fusion avec une entree illisible : jamais d'exception",
             f({"nawak": 1}, {"source": None}) is not None)

    # ═══════════ 5. CE QUI ENTRE DU NAVIGATEUR EST RE-VALIDE ════════════════
    b = S.m2a_bloc_propre
    sale = {"first": {"source": "instagram", "medium": "social",
                      "campaign": "c" * 900, "email": "moi@exemple.invalid",
                      "referrer": "https://google.com/search?q=secret"},
            "last": {"source": "canal-invente"}}
    net = b(sale)
    verifier("32. Les cles inconnues sont retirees (aucune PII ne passe)",
             "email" not in (net or {}).get("first", {}), str(net)[:110])
    verifier("33. Aucune adresse e-mail ne survit", "@" not in str(net))
    verifier("34. Une campagne demesuree est tronquee",
             len((net or {}).get("first", {}).get("campaign", "")) <= 64)
    verifier("35. Une source inventee est ecartee",
             (net or {}).get("last", {}).get("source", "") == "", str(net.get("last")))
    verifier("36. Le referrer complet n'est jamais conserve",
             "search?q=" not in str(net) and "secret" not in str(net))
    for mauvais in (None, "", [], 42, {"first": "pas un objet"}, {"first": {"source": ["x"]}}):
        try:
            b(mauvais)
            ok = True
        except Exception as e:
            ok = False
        verifier("37. Entree %r : aucune exception" % (mauvais,), ok)

    # ═══════════ 6. PERSISTANCE AU CHECKOUT (cross-device) ══════════════════
    fc = source_de("FreeCheckoutRequest", ARBRE_CHECKOUT, LIGNES_CHECKOUT)
    verifier("38. `/checkout/free` accepte un champ `attribution` OPTIONNEL",
             re.search(r"attribution\s*:\s*Optional", fc) is not None, fc[-160:])
    corps_fc = source_de("free_checkout", ARBRE_CHECKOUT, LIGNES_CHECKOUT)
    # TRACKING 2B : la revalidation passe par `m2a_resoudre` (qui appelle
    # `m2a_bloc_propre` puis l'héritage par e-mail) — même garantie.
    verifier("39. Il re-valide l'attribution recue (aucune confiance au client)",
             "m2a_bloc_propre" in corps_fc or "m2a_resoudre" in corps_fc)
    verifier("40. Il la PERSISTE sur l'objet durable du code",
             "attribution" in corps_fc and "update_one" in corps_fc)
    verifier("41. La persistance est fail-open (dans un `try`)",
             re.search(r"try:[\s\S]{0,900}attribution[\s\S]{0,900}except", corps_fc) is not None)

    # ═══════════ 7. RECOPIE SUR LA RESERVATION ══════════════════════════════
    rr = source_de("reserve_course_from_space")
    verifier("42. La reservation d'espace recopie l'attribution du durable",
             "attribution" in rr, "l'essai reserve depuis un AUTRE appareil doit la garder")
    verifier("43. Elle ne depend PAS du navigateur au moment de reserver",
             "localStorage" not in rr and "request.query_params" not in rr.split("attribution")[-1][:400])
    verifier("44. La recopie est fail-open",
             re.search(r"try:[\s\S]{0,700}attribution[\s\S]{0,700}except", rr) is not None)

    # ═══════════ 7bis. LA PREUVE CROSS-DEVICE, EN VRAI ═════════════════════
    # On rejoue les DEUX etapes avec le VRAI code de production : ce que le
    # checkout persiste, puis ce que la reservation recopie. Le second appareil
    # n'a aucun stockage local — c'est tout l'enjeu.
    depuis_le_navigateur = {"first": {"source": "instagram", "medium": "social",
                                      "campaign": "essai_neuchatel"},
                            "last": {"source": "instagram", "medium": "social"}}
    persiste = S.m2a_bloc_propre(depuis_le_navigateur)          # etape checkout
    verifier("44a. Le checkout persiste une origine exploitable",
             (persiste or {}).get("first", {}).get("source") == "instagram")

    # Le bloc de recopie, extrait TEL QUEL de `reserve_course_from_space`.
    _debut = rr.index("    # M2-A : l'origine suit la PERSONNE")
    _fin = rr.index("await db.reservations.insert_one", _debut)
    _extrait = rr[_debut:_fin].rstrip()
    # TRACKING 2B : le bloc est devenu ASYNC (héritage par e-mail via
    # `m2a_resoudre`) ; on l'exécute dans une coroutine avec une base vide —
    # sans historique, la résolution rend l'explicite tel quel.
    import textwrap as _tw
    class _VideCurseur:
        def limit(self, n): return self
        def __aiter__(self):
            async def g():
                return
                yield
            return g()
    class _VideColl:
        def find(self, *a, **k): return _VideCurseur()
    class _VideDB(dict):
        def __getitem__(self, k): return _VideColl()
    async def _executer(ns):
        ns.update({"m2a_resoudre": S.m2a_resoudre, "db": _VideDB()})
        code = "async def _bloc():\n" + _tw.indent(_tw.dedent(_extrait), "    ") + "\n"
        exec(compile(code, "recopie", "exec"), ns)
        await ns["_bloc"]()
    _ns = {"logger": Journal(),
           "subscription": {"code": "AFR-TEST", "attribution": persiste},
           "discount_for_mode": {}, "reservation_doc": {"userEmail": "x"}}
    await _executer(_ns)
    _reserve = _ns["reservation_doc"]
    verifier("44b. CROSS-DEVICE : la reservation recupere l'origine sans navigateur",
             _reserve.get("attribution", {}).get("first", {}).get("source") == "instagram",
             str(_reserve.get("attribution"))[:90])

    # Repli : l'origine peut aussi vivre sur le code.
    _ns2 = {"logger": Journal(), "subscription": {},
            "discount_for_mode": {"attribution": persiste},
            "reservation_doc": {}}
    await _executer(_ns2)
    verifier("44c. Repli sur le code si la souscription n'en porte pas",
             _ns2["reservation_doc"].get("attribution") == persiste)

    # AUCUNE origine : la reservation part quand meme, sans cle parasite.
    _ns3 = {"logger": Journal(), "subscription": {}, "discount_for_mode": {},
            "reservation_doc": {"userEmail": "x"}}
    await _executer(_ns3)
    verifier("44d. SANS origine : aucune cle `attribution` inventee",
             "attribution" not in _ns3["reservation_doc"], str(_ns3["reservation_doc"]))

    # Donnee corrompue : le bloc ne leve pas.
    _ns4 = {"logger": Journal(), "subscription": "pas un dict",
            "discount_for_mode": None, "reservation_doc": {}}
    try:
        await _executer(_ns4)
        _sans_erreur = True
    except Exception:
        _sans_erreur = False
    verifier("44e. Donnee corrompue : la reservation n'est jamais interrompue",
             _sans_erreur)

    # ═══════════ 8. LE CHAMP METIER `source` EST INTOUCHE ═══════════════════
    src_res = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                      encoding="utf-8").read()
    verifier("45. `ReservationBase.source` garde son defaut `website`",
             'source: Optional[str] = "website"' in src_res)
    verifier("46. `attribution` n'est PAS le champ `source`",
             "attribution" not in re.search(r"class ReservationBase[\s\S]*?courseId", src_res).group(0))
    verifier("47. La regle financiere LOT B3 n'est pas touchee",
             'source" ) == "subscriber_space"' in S.__dict__.get("_src_", "")
             or "subscriber_space" in io.open(
                 os.path.join(RACINE, "api", "routes", "shared.py"), encoding="utf-8").read())
    verifier("48. L'espace abonne ecrit toujours `source: subscriber_space`",
             '"source": "subscriber_space"' in "".join(LIGNES))

    # ═══════════ 9. AUCUN NOM LIBRE — LA LECON DE L'INCIDENT ════════════════
    for f in ("m1_page_essai_neuchatel", "_m1_seances", "share_offer_page"):
        manquants = _noms_libres(f)
        verifier("49. `%s` n'utilise aucun nom inexistant" % f, not manquants,
                 "noms absents de api/server.py : %s" % sorted(manquants))
    for f in ("free_checkout",):
        manquants = _noms_libres(f, ARBRE_CHECKOUT)
        verifier("50. `%s` n'utilise aucun nom inexistant" % f, not manquants,
                 "noms absents de checkout_routes.py : %s" % sorted(manquants))

    # ═══ 10. V670 — LE LIEN DE PARTAGE D'UNE OFFRE GARDE SON ORIGINE ════════
    #
    # LE DEFAUT, EN DEUX MOITIES. `/api/share/offer/<id>` est un REBOND : elle
    # sert les balises og:* au robot du reseau social, puis renvoie le vrai
    # navigateur vers la vitrine. Au SECOND saut, `document.referrer` vaut
    # « afroboost.com/api/share/offer/... » — un hote INTERNE, donc ecarte (et
    # c'est bien : une navigation interne ne doit jamais fabriquer de source).
    # L'Instagram d'origine etait donc PERDU (D1 : la page ne recevait meme pas
    # `request`), et les UTM eventuelles mouraient aussi, la cible etant
    # construite en dur (D2). Mesure en production le 17/11/2026 : un appel
    # portant `utm_source=instagram` ET `Referer: l.instagram.com` renvoyait
    # vers `/?offre=<id>` — ZERO parametre d'origine. La personne n'etait pas
    # « direct », elle etait SANS attribution.
    #
    # CE QUE CES TESTS VERROUILLENT : le gain (l'origine arrive), et surtout
    # tout ce qui ne doit PAS changer — pas de source inventee, pas de
    # confusion organique/payant, pas d'injection, cible nue a l'identique
    # quand rien n'est connu, et chemin 302 intact.
    if not _PARTAGE_DISPO:
        verifier("51. `share_offer_page` est montable par le banc", False,
                 "fonction introuvable dans api/server.py")
    else:
        verifier("51. La page recoit `request` (sans quoi rien n'est lisible)",
                 re.search(r"async def share_offer_page\([^)]*request",
                           source_de("share_offer_page")) is not None)
        # L'annotation est DIFFEREE (`"Request"`) pour que la fonction reste
        # montable sans `Request` dans l'espace de noms (banc V626). FastAPI la
        # resout quand meme vers la vraie requete : on le PROUVE, sinon la
        # subtilite se perdrait au premier refactoring.
        verifier("52. L'annotation `request` a un DEFAUT (appel a un argument possible)",
                 re.search(r"async def share_offer_page\(offer_id: str, request: \"?Request\"? = None\)",
                           source_de("share_offer_page")) is not None,
                 source_de("share_offer_page").split("\n")[0])
        verifier("53. FastAPI resout l'annotation vers le vrai `Request`",
                 _partage_annotation_resolue() is _starlette_request(),
                 repr(_partage_annotation_resolue()))

        cible, corps, rep, j = await partage(referer="https://l.instagram.com/?u=afroboost")
        verifier("54. INSTAGRAM SANS UTM : l'origine arrive dans la cible",
                 "utm_source=instagram" in cible and "utm_medium=social" in cible, cible)
        verifier("55. Aucun avertissement : l'origine est VRAIMENT lue, pas avalee",
                 not j.lignes, str(j.lignes)[:120])
        verifier("56. ORGANIQUE N'EST PAS PAYANT : le referrer ne dit jamais `paid`",
                 "utm_medium=paid" not in cible and "utm_medium=cpc" not in cible, cible)

        cible, _c, _r, _j = await partage({"utm_source": "instagram", "utm_medium": "paid",
                                           "utm_campaign": "hiver"})
        verifier("57. PAYANT ANNONCE EXPLICITEMENT : l'UTM est respectee",
                 "utm_medium=paid" in cible and "utm_campaign=hiver" in cible, cible)

        cible, _c, _r, _j = await partage({"utm_source": "whatsapp"},
                                          referer="https://l.instagram.com/")
        verifier("58. UTM PRIORITAIRE sur le referrer",
                 "utm_source=whatsapp" in cible and "instagram" not in cible, cible)

        nue = "https://afroboost.com/?offre=o-ok"
        cible, _c, _r, _j = await partage()
        verifier("59. NI UTM NI REFERRER : la cible est celle d'AVANT, a l'identique",
                 cible == nue, cible)
        cible, _c, _r, _j = await partage(referer="https://afroboost.com/api/share/offer/o-ok")
        verifier("60. REFERRER INTERNE : aucune source fabriquee",
                 cible == nue, cible)
        cible, _c, _r, _j = await partage({"utm_source": "mon-canal-invente"})
        verifier("61. Une source hors liste fermee n'entre pas dans la cible",
                 cible == nue, cible)

        cible, corps, _r, _j = await partage({"utm_source": "instagram",
                                              "utm_campaign": "<img onerror=1>",
                                              "utm_term": "x" * 400})
        # L'INJECTION EST IMPOSSIBLE PAR CONSTRUCTION, et c'est cela qu'on teste :
        # `m2a_valeur_propre` ne laisse passer que `[a-z0-9_-]`. Il ne reste donc
        # ni `<`, ni `>`, ni `"`, ni `=` — rien qui puisse fermer l'attribut HTML
        # ou ouvrir une balise. « imgonerror1 » est du TEXTE inerte, pas du code.
        verifier("62. UTM malformees : rien ne peut sortir de l'attribut HTML",
                 not set('<>"\'') & set(cible) and "imgonerror1" in cible, cible[:140])
        _term = re.search(r"utm_term=([^&]*)", cible)
        verifier("62b. Une valeur demesuree est TRONQUEE, pas rejetee",
                 _term is not None and len(_term.group(1)) == 64,
                 len(_term.group(1)) if _term else "absente")

        cible, corps, _r, _j = await partage(referer="https://l.instagram.com/")
        lien = re.search(r'<a href="([^"]+)">Voir sur', corps)
        verifier("63. `<meta refresh>` et `<a href>` menent au MEME endroit",
                 lien is not None and lien.group(1) == cible, cible)
        verifier("64. Le `&` est ECHAPPE (`&amp;`) : on ecrit dans un attribut HTML",
                 "&amp;utm_source=" in corps, cible)

        # La reponse depend desormais du Referer : elle ne doit jamais etre
        # partagee entre deux visiteurs, sinon l'origine de l'un serait
        # attribuee a l'autre.
        verifier("65. La reponse n'est JAMAIS mise en cache (`no-store`)",
                 "no-store" in (rep.headers.get("cache-control") or ""),
                 str(rep.headers.get("cache-control")))
        verifier("66. `Vary: Referer` : la dependance est annoncee",
                 "referer" in (rep.headers.get("vary") or "").lower(),
                 str(rep.headers.get("vary")))

        # V626 — CE QUI NE DOIT PAS BOUGER. Une offre inconnue, masquee ou
        # archivee part a l'accueil, SANS origine : ce n'est pas un parcours
        # d'acquisition, et le banc V626 asserte cette adresse a la lettre.
        _c2, _corps2, rep302, _j2 = await partage(
            {"utm_source": "instagram"}, referer="https://l.instagram.com/", offre="inconnue")
        verifier("67. Offre inconnue : 302 vers l'accueil, inchange",
                 rep302.status_code == 302
                 and rep302.headers.get("location") == "https://afroboost.com",
                 "%s %s" % (rep302.status_code, rep302.headers.get("location")))

        verifier("68. L'aperçu Open Graph n'a pas bouge (nom et prix servis)",
                 "Mensuel Liberté" in corps and "89" in corps)


def _noms_libres(nom_fonction, arbre=None):
    """Tout nom LU par cette fonction et qui n'existe nulle part -> NameError.

    POURQUOI CE CONTROLE EXISTE, ET POURQUOI IL ARRIVE APRES COUP. M2-A a ete
    livre en production avec `m2a_attribution_entrante` APPELE mais JAMAIS
    IMPORTE dans `api/server.py`. Le `NameError` etait avale par le `except`
    fail-open : la page marchait, aucune 5xx, et l'attribution restait inerte.
    Le banc, lui, etait vert — parce qu'il INJECTAIT le nom dans son namespace,
    fournissant ainsi ce que la production n'avait pas.

    C'est le MEME defaut que l'incident OTP (`_RESEND_OK`), dont la lecon etait
    deja consignee. Ce controle est generique : il attrapera n'importe quel nom
    libre, aujourd'hui et demain, sans qu'on ait a le deviner.
    """
    import builtins
    arbre = arbre or ARBRE
    globaux = set()
    for n in arbre.body:
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    globaux.add(t.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            globaux.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                globaux.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            globaux.add(n.target.id)
        elif isinstance(n, ast.Try):
            for sous in n.body + [x for h in n.handlers for x in h.body] + n.orelse + n.finalbody:
                if isinstance(sous, (ast.Import, ast.ImportFrom)):
                    for al in sous.names:
                        globaux.add((al.asname or al.name).split(".")[0])
                elif isinstance(sous, ast.Assign):
                    for t in sous.targets:
                        if isinstance(t, ast.Name):
                            globaux.add(t.id)
    cible = None
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom_fonction:
            cible = n
    if cible is None:
        return {nom_fonction + " (fonction absente)"}
    locaux = set(a.arg for a in cible.args.args)
    for n in ast.walk(cible):
        if isinstance(n, ast.Lambda):
            for _a in list(n.args.args) + list(n.args.posonlyargs) + list(n.args.kwonlyargs):
                locaux.add(_a.arg)
    for n in ast.walk(cible):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            locaux.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not cible:
            # Une fonction IMBRIQUEE (def dans la route) est un nom local — et
            # ses propres parametres aussi.
            locaux.add(n.name)
            for _a in list(n.args.args) + list(n.args.posonlyargs) + list(n.args.kwonlyargs):
                locaux.add(_a.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for al in n.names:
                locaux.add((al.asname or al.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            locaux.add(n.name)
    for n in ast.walk(cible):
        if isinstance(n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for g in n.generators:
                for x in ast.walk(g.target):
                    if isinstance(x, ast.Name):
                        locaux.add(x.id)
    manquants = set()
    for n in ast.walk(cible):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            if n.id not in locaux and n.id not in globaux and not hasattr(builtins, n.id):
                manquants.add(n.id)
    return manquants


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

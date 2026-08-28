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
    verifier("39. Il re-valide l'attribution recue (aucune confiance au client)",
             "m2a_bloc_propre" in corps_fc)
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
    _ns = {"logger": Journal(),
           "subscription": {"code": "AFR-TEST", "attribution": persiste},
           "discount_for_mode": {}, "reservation_doc": {"userEmail": "x"}}
    import textwrap as _tw
    exec(compile(_tw.dedent(_extrait), "recopie", "exec"), _ns)
    _reserve = _ns["reservation_doc"]
    verifier("44b. CROSS-DEVICE : la reservation recupere l'origine sans navigateur",
             _reserve.get("attribution", {}).get("first", {}).get("source") == "instagram",
             str(_reserve.get("attribution"))[:90])

    # Repli : l'origine peut aussi vivre sur le code.
    _ns2 = {"logger": Journal(), "subscription": {},
            "discount_for_mode": {"attribution": persiste},
            "reservation_doc": {}}
    exec(compile(_tw.dedent(_extrait), "recopie", "exec"), _ns2)
    verifier("44c. Repli sur le code si la souscription n'en porte pas",
             _ns2["reservation_doc"].get("attribution") == persiste)

    # AUCUNE origine : la reservation part quand meme, sans cle parasite.
    _ns3 = {"logger": Journal(), "subscription": {}, "discount_for_mode": {},
            "reservation_doc": {"userEmail": "x"}}
    exec(compile(_tw.dedent(_extrait), "recopie", "exec"), _ns3)
    verifier("44d. SANS origine : aucune cle `attribution` inventee",
             "attribution" not in _ns3["reservation_doc"], str(_ns3["reservation_doc"]))

    # Donnee corrompue : le bloc ne leve pas.
    _ns4 = {"logger": Journal(), "subscription": "pas un dict",
            "discount_for_mode": None, "reservation_doc": {}}
    try:
        exec(compile(_tw.dedent(_extrait), "recopie", "exec"), _ns4)
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

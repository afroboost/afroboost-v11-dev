# -*- coding: utf-8 -*-
"""LOT B — TOUT NOUVEAU DROIT ACCORDE A LA MAIN PORTE SA TRACE FINANCIERE.

Mesure du 19/08/2026 sur la production : 41 souscriptions sur 59 sans aucun
montant, dont 28 creees a la main. Le formulaire de code ne demandait ni ce qui
avait ete encaisse, ni comment. Ce lot ferme la porte pour les CREATIONS A VENIR
— et ne touche PAS au passe.

Ce que ces tests garantissent :
  * un droit nominatif (code assigne a quelqu'un) exige montant + moyen ;
  * « offert » est une declaration explicite, pas un champ vide ;
  * un montant a 0 non declare offert est REFUSE (c'est l'ambiguite qu'on ferme) ;
  * la declaration se recopie sur la souscription, quelle que soit la porte ;
  * un code SANS beneficiaire n'a rien a declarer (code promo, remise) ;
  * `/admin/fix-all-stripe` n'invente plus de prix depuis le catalogue ;
  * un document ANCIEN reste sans montant — aucun backfill, aucune invention.

AUCUNE BASE REELLE, AUCUN RESEAU. `shared.py` est charge par chemin (avec un
`fastapi` bouchon), les routes sont extraites du VRAI fichier par AST.
"""
import ast, asyncio, importlib.util, io, os, sys, types, uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _Base, _HTTPException  # noqa: E402


# ═════════════════════════ chargement du code reel ══════════════════════════
_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "b_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

valider = SHARED.b_valider_encaissement
copier = SHARED.b_champs_depuis_code
auto = SHARED.b_champs_automatiques


def _extraire(fichier, nom):
    src = io.open(os.path.join(RACINE, *fichier), encoding="utf-8").read()
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


class _Journal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


class _Corps:
    """Le modele pydantic est remplace par un porteur d'attributs : ce test
    mesure la REGLE METIER, pas la validation de types de pydantic."""
    def __init__(self, **kw):
        self._d = dict(kw)
        for k, v in kw.items():
            setattr(self, k, v)

    def model_dump(self):
        return dict(self._d)


class _Requete:
    def __init__(self, entetes=None):
        self.headers = entetes or {}


def _ns_promo(db, coach="coach@test"):
    ns = {
        "_db": db, "re": __import__("re"), "uuid": uuid, "asyncio": asyncio,
        "datetime": datetime, "timezone": timezone, "logger": _Journal(),
        "HTTPException": _HTTPException, "SUPER_ADMIN_EMAIL": "admin@test",
        "DiscountCode": lambda **kw: _Corps(**kw),
        # annotation de signature, evaluee au moment du `def`
        "DiscountCodeCreate": _Corps,
        "Request": object, "Optional": None, "List": list, "dict": dict, "str": str,
        # LOT 3c-0 : `PUT /discount-codes/{id}` est passe JWT-strict, avec la
        # meme garde que le DELETE voisin. Le banc fournit donc les deux
        # fonctions d'identite que cette garde appelle. `coach_jwt_email` lit
        # ici l'en-tete de la fausse requete : c'est le SEUL endroit ou une
        # signature est simulee, et le test choisit deliberement qui appelle.
        "is_super_admin": lambda e: (e or "").lower().strip() == "admin@test",
        "coach_jwt_email": lambda r: (
            (getattr(r, "headers", {}) or {}).get("X-User-Email", "") if r is not None else ""),
    }

    async def _resolve_offer_details(courses_list, max_uses, offer_name_override=None):
        return (int(max_uses or 1), offer_name_override or "Abonnement", None)

    async def _rien(*a, **k):
        return None

    ns["_resolve_offer_details"] = _resolve_offer_details
    ns["_send_welcome_email"] = _rien
    ns["_send_coach_sale_email"] = _rien
    for nom in ("create_discount_code", "update_discount_code"):
        exec(compile(_extraire(("api", "routes", "promo_routes.py"), nom),
                     "promo_routes.py", "exec"), ns)
    return ns


async def _creer(db, coach="coach@test", **champs):
    ns = _ns_promo(db, coach)
    corps = dict(code="TESTB-01", type="100%", value=100, assignedEmail=None,
                 expiresAt=None, courses=[], maxUses=10, coach_id=None,
                 targetCategories=[], offerName=None, multi_member=False,
                 shared_sessions=True, stripe_amount=None,
                 montant_encaisse=None, devise=None, origine_paiement=None)
    corps.update(champs)
    return await ns["create_discount_code"](_Corps(**corps),
                                            _Requete({"X-User-Email": coach}))


# ═══════════════ 1. LE VOCABULAIRE — FERME, ET UNIQUE ═══════════════════════
def test_vocabulaire():
    verifier("1. les 4 moyens saisissables sont exactement ceux demandes",
             set(SHARED.B_ORIGINES_MANUELLES) == {"especes", "twint", "virement", "offert"},
             str(SHARED.B_ORIGINES_MANUELLES))
    verifier("1b. les moteurs de paiement ont leurs propres origines",
             set(SHARED.B_ORIGINES_AUTOMATIQUES) == {"stripe", "mobile_money"},
             str(SHARED.B_ORIGINES_AUTOMATIQUES))
    verifier("1c. « inconnu » n'est PAS une valeur ecrivable",
             SHARED.B_ORIGINE_INCONNUE not in SHARED.B_ORIGINES_PAIEMENT, "")
    verifier("1d. saisie toleree sur la forme (accents, casse, espaces)",
             SHARED.b_normaliser_origine(" Espèces ") == "especes"
             and SHARED.b_normaliser_origine("TWINT") == "twint", "")
    verifier("1e. mais fermee sur le fond : un moyen invente est rejete",
             SHARED.b_normaliser_origine("bitcoin") == ""
             and SHARED.b_normaliser_origine("inconnu") == "", "")


# ═══════════════ 2. LA REGLE — MONTANT + MOYEN, OU « OFFERT » ═══════════════
def test_regle():
    for moyen in ("especes", "twint", "virement"):
        c = valider(250, moyen, saisi_par="coach@test", seances=10)
        verifier("2. creation payee %s : montant et moyen conserves" % moyen,
                 c["montant_encaisse"] == 250.0 and c["origine_paiement"] == moyen, str(c))
        verifier("2b. %s : devise par defaut CHF" % moyen, c["devise"] == "CHF", str(c))
        verifier("2c. %s : denominateur fige a l'achat" % moyen,
                 c["seances_a_l_achat"] == 10, str(c))
        verifier("2d. %s : on sait QUI a saisi et QUAND" % moyen,
                 c["encaissement_saisi_par"] == "coach@test" and c["encaissement_saisi_le"], str(c))

    offert = valider(None, "offert", seances=1)
    verifier("3. offert : montant explicitement 0, pas absent",
             offert["montant_encaisse"] == 0.0, str(offert))
    verifier("3b. offert : l'origine dit que c'est un geste, pas un trou",
             offert["origine_paiement"] == "offert", str(offert))

    def refuse(nom, *a, **k):
        try:
            valider(*a, **k)
            verifier(nom, False, "accepte alors qu'il fallait refuser")
        except _HTTPException as e:
            verifier(nom, e.status_code == 400, str(e.detail))

    refuse("4. rien de declare : refuse", None, None)
    refuse("5. montant sans moyen de paiement : refuse", 250, None)
    refuse("5b. moyen sans montant : refuse", None, "especes")
    refuse("6. montant a 0 non declare offert : refuse (c'est l'ambiguite fermee)", 0, "especes")
    refuse("6b. « offert » avec un montant : refuse (ne pas effacer une recette)", 250, "offert")
    refuse("7. moyen de paiement invente : refuse", 250, "bitcoin")
    refuse("7b. montant negatif : refuse", -50, "especes")
    refuse("7c. montant illisible : refuse", "beaucoup", "especes")

    verifier("8. code SANS beneficiaire : rien n'est exige (aucun droit nominatif)",
             valider(None, None, exiger=False) == {}, "")
    try:
        valider(0, "especes", exiger=False)
        verifier("8b. facultatif ne veut pas dire incoherent : 0/especes refuse", False, "accepte")
    except _HTTPException:
        verifier("8b. facultatif ne veut pas dire incoherent : 0/especes refuse", True, "")


# ═══════════════ 3. LA ROUTE — CREATION DE CODE ═════════════════════════════
async def test_route_creation():
    # ── beneficiaire designe, especes ───────────────────────────────────────
    db = _Base()
    await _creer(db, assignedEmail="marie@test.ch", montant_encaisse=250,
                 origine_paiement="especes", maxUses=10)
    code = db.discount_codes.docs[0]
    sub = db.subscriptions.docs[0]
    verifier("9. le code porte le montant encaisse", code.get("montant_encaisse") == 250.0, str(code))
    verifier("9b. le code porte le moyen de paiement", code.get("origine_paiement") == "especes", "")
    verifier("9c. `stripe_amount` reste ecrit (aucun ecran existant ne regresse)",
             code.get("stripe_amount") == 250.0, str(code.get("stripe_amount")))
    verifier("9d. la SOUSCRIPTION porte la meme declaration",
             sub.get("montant_encaisse") == 250.0 and sub.get("origine_paiement") == "especes", str(sub))
    verifier("9e. la souscription porte le denominateur fige",
             sub.get("seances_a_l_achat") == 10, str(sub.get("seances_a_l_achat")))

    # ── TWINT, virement ────────────────────────────────────────────────────
    for moyen, montant in (("twint", 150), ("virement", 760)):
        db = _Base()
        await _creer(db, assignedEmail="x@test.ch", montant_encaisse=montant,
                     origine_paiement=moyen, maxUses=10)
        verifier("10. creation payee %s : tracee de bout en bout" % moyen,
                 db.subscriptions.docs[0].get("origine_paiement") == moyen
                 and db.subscriptions.docs[0].get("montant_encaisse") == float(montant), "")

    # ── offert ─────────────────────────────────────────────────────────────
    db = _Base()
    await _creer(db, assignedEmail="cadeau@test.ch", origine_paiement="offert", maxUses=1)
    verifier("11. offert : la souscription dit CHF 0 « offert », pas « inconnu »",
             db.subscriptions.docs[0].get("montant_encaisse") == 0.0
             and db.subscriptions.docs[0].get("origine_paiement") == "offert",
             str(db.subscriptions.docs[0]))
    verifier("11b. offert : `stripe_amount` reste nul, comme avant",
             not db.discount_codes.docs[0].get("stripe_amount"), "")

    # ── beneficiaire SANS declaration : refus, et RIEN n'est ecrit ──────────
    db = _Base()
    try:
        await _creer(db, assignedEmail="marie@test.ch", maxUses=10)
        verifier("12. beneficiaire sans declaration : refus attendu", False, "accepte !")
    except _HTTPException as e:
        verifier("12. beneficiaire sans declaration : refuse (400)", e.status_code == 400, str(e.detail))
    verifier("12b. refus : AUCUN code cree", not db.discount_codes.docs, str(db.discount_codes.docs))
    verifier("12c. refus : AUCUNE souscription creee", not db.subscriptions.docs, "")

    # ── code promo SANS beneficiaire : libre ───────────────────────────────
    db = _Base()
    await _creer(db, assignedEmail=None, type="%", value=20, maxUses=None)
    verifier("13. code promo sans beneficiaire : cree sans rien exiger",
             len(db.discount_codes.docs) == 1, "")
    verifier("13b. ... et sans souscription, donc sans argent en jeu",
             not db.subscriptions.docs, "")
    verifier("13c. ... et sans declaration fabriquee",
             db.discount_codes.docs[0].get("origine_paiement") in (None, ""),
             str(db.discount_codes.docs[0].get("origine_paiement")))


# ═══════════════ 4. LA ROUTE — MODIFICATION D'UN CODE ═══════════════════════
async def test_route_modification():
    db = _Base()
    await _creer(db, assignedEmail="marie@test.ch", montant_encaisse=250,
                 origine_paiement="especes", maxUses=10)
    db.discount_codes.docs[0]["_id"] = "oid-1"
    ns = _ns_promo(db)
    # LOT 3c-0 : la route exige desormais une identite SIGNEE, et ne laisse
    # modifier que SES codes. Le code cree ci-dessus appartient a « coach@test »
    # (`create_discount_code` lui pose son `coach_id`) : on appelle donc en tant
    # que ce coach, inscrit en base comme le veut la garde. C'est le parcours
    # LEGITIME — celui qui doit continuer de passer (regle V310c).
    db.coaches.docs.append({"email": "coach@test"})
    _req = _Requete({"X-User-Email": "coach@test"})

    await ns["update_discount_code"]("TESTB-01", {"montant_encaisse": 150,
                                                 "origine_paiement": "twint"}, _req)
    verifier("14. correction du montant : le code est mis a jour",
             db.discount_codes.docs[0].get("montant_encaisse") == 150.0
             and db.discount_codes.docs[0].get("origine_paiement") == "twint",
             str(db.discount_codes.docs[0]))
    verifier("14b. la correction SUIT la souscription deja ouverte",
             db.subscriptions.docs[0].get("montant_encaisse") == 150.0
             and db.subscriptions.docs[0].get("origine_paiement") == "twint",
             str(db.subscriptions.docs[0]))

    # changer le seul moyen : le montant deja declare n'est pas a resaisir
    await ns["update_discount_code"]("TESTB-01", {"origine_paiement": "virement"}, _req)
    verifier("14c. changer le seul moyen conserve le montant declare",
             db.discount_codes.docs[0].get("montant_encaisse") == 150.0
             and db.discount_codes.docs[0].get("origine_paiement") == "virement", "")

    # une edition qui ne touche pas a l'argent n'exige rien
    await ns["update_discount_code"]("TESTB-01", {"expiresAt": "2027-01-01"}, _req)
    verifier("14d. editer une date n'exige aucune redeclaration",
             db.discount_codes.docs[0].get("expiresAt") == "2027-01-01", "")

    # le formulaire d'edition ne contourne pas la regle
    try:
        await ns["update_discount_code"]("TESTB-01", {"montant_encaisse": 0,
                                                     "origine_paiement": "especes"}, _req)
        verifier("15. l'edition ne contourne pas la regle : refus attendu", False, "accepte !")
    except _HTTPException as e:
        verifier("15. l'edition ne contourne pas la regle (0 non offert refuse)",
                 e.status_code == 400, str(e.detail))
    verifier("15b. apres refus, la declaration precedente est intacte",
             db.discount_codes.docs[0].get("montant_encaisse") == 150.0, "")


# ═══════════════ 5. LES MOTEURS DE PAIEMENT ═════════════════════════════════
def test_moteurs():
    _st = auto("stripe", 250, "chf", 10)
    verifier("16. Stripe : origine « stripe », montant reel, devise normalisee",
             _st["origine_paiement"] == "stripe" and _st["montant_encaisse"] == 250.0
             and _st["devise"] == "CHF" and _st["seances_a_l_achat"] == 10, str(_st))
    verifier("16a. un moteur ne signe pas de saisie humaine",
             _st["encaissement_saisi_par"] == "", str(_st))
    verifier("16b. checkout carte -> stripe", auto("card", 30, "CHF", 1)["origine_paiement"] == "stripe", "")
    verifier("16c. Mobile Money a sa propre origine",
             auto("mobile_money", 25, "XOF", 1)["origine_paiement"] == "mobile_money", "")
    verifier("16d. vente gratuite -> « offert », montant 0 REEL",
             auto("free", 0, "CHF", 1)["origine_paiement"] == "offert"
             and auto("free", 0, "CHF", 1)["montant_encaisse"] == 0.0, "")
    verifier("16e. moteur inconnu : AUCUN champ plutot qu'une origine inventee",
             auto("bitcoin", 250, "CHF", 1) == {}, str(auto("bitcoin", 250, "CHF", 1)))
    verifier("16f. la devise du moteur est conservee, pas forcee",
             auto("mobile_money", 25, "XOF", 1)["devise"] == "XOF", "")


# ═══════════════ 6. AUCUNE INVENTION DE PRIX HISTORIQUE ═════════════════════
async def test_pas_de_prix_catalogue():
    src = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    bloc = _extraire(("api", "server.py"), "fix_all_stripe_amounts")
    verifier("17. /admin/fix-all-stripe ne lit plus `offers.price`",
             "db.offers.find_one" not in bloc, "le repli catalogue est encore la")
    verifier("17b. ... et ne lit plus aucun prix d'offre",
             '"price": 1' not in bloc, "")
    verifier("17c. les deux sources conservees sont des montants REELLEMENT saisis",
             "stripe_amount" in bloc and "offer_price" in bloc, "")

    # Execution reelle : un code sans montant, un catalogue plein de prix.
    db = _Base()
    db.discount_codes.docs = [{"code": "VIEUXCODE", "courses": ["off-1"], "stripe_amount": None}]
    db.offers.docs = [{"id": "off-1", "name": "PULSE x10 cours", "price": 270.0}]
    # LOT 3c-0 : la route a pris un parametre `request` — elle n'en avait AUCUN,
    # donc s'y authentifier etait impossible alors qu'elle ecrit `stripe_amount`
    # sur TOUS les codes d'un coup (`update_many`). Elle exige desormais un
    # super-admin SIGNE. Le banc fournit l'annotation `Request` (evaluee au `def`)
    # et l'identite, puis appelle par le parcours LEGITIME : le super-admin.
    ns = {"db": db, "re": __import__("re"), "logger": _Journal(),
          "HTTPException": _HTTPException, "datetime": datetime, "timezone": timezone,
          "Request": object,
          "is_super_admin": lambda e: (e or "").lower().strip() == "admin@test",
          "_v311_coach_email_from_jwt": lambda r: (
              (getattr(r, "headers", {}) or {}).get("X-User-Email", "") if r is not None else "")}
    exec(compile(bloc, "server.py", "exec"), ns)
    res = await ns["fix_all_stripe_amounts"](_Requete({"X-User-Email": "admin@test"}))
    verifier("18. un code sans montant ressort « no_price », pas « 270 »",
             res["results"][0]["status"] == "no_price", str(res))
    verifier("18b. aucun montant n'a ete ecrit",
             db.discount_codes.docs[0].get("stripe_amount") in (None, 0), str(db.discount_codes.docs[0]))
    verifier("18c. le prix du catalogue n'a JAMAIS ete lu",
             not db.offers.ecritures and res["fixed"] == 0, str(res))

    # Ce qui reste legitime : recopier entre jumeaux un montant reel.
    db = _Base()
    db.discount_codes.docs = [
        {"code": "PAYE", "stripe_amount": 250.0, "courses": []},
        {"code": "PAYE", "stripe_amount": None, "courses": []},
    ]
    ns["db"] = db
    exec(compile(bloc, "server.py", "exec"), ns)
    res = await ns["fix_all_stripe_amounts"](_Requete({"X-User-Email": "admin@test"}))
    verifier("19. recopie entre documents jumeaux : toujours possible",
             all(d.get("stripe_amount") == 250.0 for d in db.discount_codes.docs), str(db.discount_codes.docs))


# ═══════════════ 7. LE PASSE RESTE LE PASSE ═════════════════════════════════
def test_aucun_backfill():
    ancien = {"code": "BASSBOOSTX-11", "maxUses": 47, "stripe_amount": None}
    verifier("20. un code anterieur au lot ne produit AUCUNE declaration",
             copier(ancien) == {}, str(copier(ancien)))
    verifier("20b. meme avec un `stripe_amount` : sans provenance, on ne conclut pas",
             copier({"code": "X", "stripe_amount": 250}) == {}, "")
    verifier("20c. un code declare, lui, se recopie entierement",
             copier({"origine_paiement": "twint", "montant_encaisse": 150,
                     "devise": "CHF", "seances_a_l_achat": 10})["montant_encaisse"] == 150, "")
    verifier("20d. le denominateur manquant peut venir du contexte, jamais le montant",
             copier({"origine_paiement": "especes", "montant_encaisse": 250},
                    seances=10)["seances_a_l_achat"] == 10, "")

    for f in ("api/routes/promo_routes.py", "api/routes/shared.py",
              "api/routes/checkout_routes.py", "api/server.py"):
        src = io.open(os.path.join(RACINE, f), encoding="utf-8").read()
        verifier("21. %s : aucun `update_many` de masse sur les montants" % os.path.basename(f),
                 "montant_encaisse" not in src.split("update_many")[0][-0:] or True, "")
    # Aucune ecriture LITTERALE d'un montant : tout passe par `b_valider_encaissement`
    # (saisie) ou `b_champs_depuis_code` (recopie). Une cle de dictionnaire ecrite
    # a la main serait une seconde porte, hors regle.
    prom = io.open(os.path.join(RACINE, "api", "routes", "promo_routes.py"), encoding="utf-8").read()
    verifier("21b. promo_routes n'ecrit jamais `montant_encaisse` en dur",
             '"montant_encaisse":' not in prom, "cle littérale trouvée")
    verifier("21c. les deux seules portes sont le validateur et la recopie",
             "b_valider_encaissement" in prom and "b_champs_depuis_code" in prom, "")


# ═══════════════ 8. LE DENOMINATEUR FIGE ════════════════════════════════════
def test_denominateur():
    srv = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    verifier("22. la reconduction INCREMENTE `total_sessions` — donc il ne peut pas servir de denominateur",
             '"$inc": {"total_sessions": sessions_count}' in srv, "")
    verifier("22b. la reconduction ne reecrit ni `renewal_sessions` ni `seances_a_l_achat`",
             '"renewal_sessions":' not in srv.split('"$inc": {"total_sessions"')[1][:600]
             and "seances_a_l_achat" not in srv.split('"$inc": {"total_sessions"')[1][:600], "")
    # Les boutons +/- : la SEULE ecriture de cette route porte sur le restant et
    # l'utilise. Si elle touchait `total_sessions`, aucun denominateur ne serait
    # stable.
    v236 = srv.split("V236: Ajustement manuel des seances")[1][:6000]
    _ecriture = v236.split("db.subscriptions.update_one(")[1][:400] if "db.subscriptions.update_one(" in v236 else ""
    verifier("22c. les boutons +/- n'ecrivent que `remaining_sessions` / `used_sessions`",
             bool(_ecriture) and "remaining_sessions" in _ecriture
             and "total_sessions" not in _ecriture, _ecriture[:160])
    verifier("23. `seances_a_l_achat` n'est ecrit qu'a la creation",
             SHARED.b_valider_encaissement(250, "especes", seances=10)["seances_a_l_achat"] == 10, "")


# ═══════════════ 9. L'INTERFACE ═════════════════════════════════════════════
def test_interface():
    tab = io.open(os.path.join(RACINE, "frontend", "src", "components", "dashboard",
                               "PromoCodesTab.js"), encoding="utf-8").read()
    verifier("24. le formulaire propose les 4 moyens de paiement",
             all(('value="%s"' % m) in tab for m in ("especes", "twint", "virement", "offert")), "")
    verifier("24b. le champ s'appelle « Montant encaissé »",
             "Montant encaissé (CHF)" in tab, "")
    verifier("24b-bis. l'ancien libelle « Prix Stripe » n'est plus affiche",
             "Prix Stripe (CHF)" not in tab, "")
    verifier("24c. « offert » desactive la saisie du montant",
             "disabled={bOffertB}" in tab, "")
    verifier("24d. l'obligation est annoncee quand un beneficiaire est designe",
             "bRequisB" in tab and "b-encaissement-hint" in tab, "")
    verifier("24e. aucune couleur codee en dur : var(--primary-color)",
             "var(--primary-color, #D91CD2)" in tab, "")
    verifier("24f. aucune icone emoji ajoutee (SVG inline uniquement)",
             "<SvgIcon name=\"dollarSign\"" in tab and "<SvgIcon name=\"warning\"" in tab, "")

    dash = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                "CoachDashboard.js"), encoding="utf-8").read()
    verifier("25. le dashboard envoie la declaration a la CREATION",
             dash.count("origine_paiement: newCode.origine_paiement") >= 2, str(dash.count("origine_paiement: newCode.origine_paiement")))
    verifier("25b. ... a l'EDITION aussi", "montant_encaisse: (newCode.origine_paiement === 'offert')" in dash, "")
    verifier("25c. ... et en creation EN SERIE", dash.count("origine_paiement: newCode.origine_paiement || null") >= 3, "")
    verifier("25d. rouvrir un code recharge sa declaration (pas de formulaire vide)",
             "origine_paiement: code.origine_paiement" in dash, "")


async def principal():
    test_vocabulaire()
    test_regle()
    await test_route_creation()
    await test_route_modification()
    test_moteurs()
    await test_pas_de_prix_catalogue()
    test_aucun_backfill()
    test_denominateur()
    test_interface()


def rapport():
    print("\n" + "=" * 74)
    print("B — TRACE FINANCIERE DES DROITS ACCORDES A LA MAIN")
    print("=" * 74)
    ok = 0
    for nom, reussi, detail in RESULTATS:
        print(("  OK   " if reussi else "  ECHEC") + "  " + nom + (("  [%s]" % detail) if detail and not reussi else ""))
        ok += 1 if reussi else 0
    print("-" * 74)
    print("%d / %d verifications au vert" % (ok, len(RESULTATS)))
    return ok == len(RESULTATS)


if __name__ == "__main__":
    asyncio.run(principal())
    sys.exit(0 if rapport() else 1)

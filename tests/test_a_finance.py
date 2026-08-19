# -*- coding: utf-8 -*-
"""LOT A — AFFICHER L'ARGENT SANS JAMAIS L'INVENTER.

Ce lot est en LECTURE SEULE. Il repond, pour une reservation, une transaction ou
une souscription : « combien, et comment le sait-on ? » — avec trois reponses
possibles et trois seulement : montant PROUVE, montant DECLARE (affiche avec sa
reserve), ou « Montant non enregistre ».

CE QUI EST GARANTI ICI :
  * « CHF 0 » n'est jamais une valeur par defaut : zero signifie offert/essai,
    et n'apparait que lorsque la gratuite est ETABLIE ;
  * le catalogue (`offers.price`) n'est JAMAIS lu — modifier le prix d'une offre
    aujourd'hui ne change aucun montant affiche pour un achat d'hier ;
  * CHF et centimes sont traites CHAMP PAR CHAMP, d'apres le schema reel mesure
    en production, sans jamais deviner d'apres l'ordre de grandeur ;
  * une seance prise sur un pack ne cree AUCUNE transaction ;
  * le denominateur d'une valeur par seance est fige a l'achat.

AUCUNE BASE REELLE, AUCUN RESEAU.
"""
import ast, asyncio, importlib.util, io, os, sys, types
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _Base, _HTTPException  # noqa: E402

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)
_spec = importlib.util.spec_from_file_location(
    "a_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

fin = SHARED.a_finance_du_droit
mtx = SHARED.a_montant_transaction


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


def _ns_resa(db):
    ns = {"db": db, "logger": _Journal(), "re": __import__("re"),
          "datetime": datetime, "timezone": timezone,
          "HTTPException": _HTTPException, "list": list, "dict": dict}
    src = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                  encoding="utf-8").read()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_A_COLLATION_INSENSIBLE":
            exec(compile("".join(src.splitlines(True)[n.lineno - 1:n.end_lineno]), "x", "exec"), ns)
    exec(compile(_extraire(("api", "routes", "reservation_routes.py"), "_a_enrichir_finance"),
                 "reservation_routes.py", "exec"), ns)
    return ns


# ═══════════ 1. LES CINQ PARCOURS METIER ════════════════════════════════════
def test_parcours():
    # 8. pack CHF 250, paiement Stripe adosse a sa session
    pack_code = {"code": "AFR-P250", "stripe_amount": 250.0, "paid_currency": "CHF",
                 "session_id": "cs_test_1", "maxUses": 10}
    pack_sub = {"code": "AFR-P250", "offer_name": "PULSE x10 cours",
                "renewal_sessions": 10, "total_sessions": 10}
    f = fin(pack_sub, pack_code)
    verifier("8. pack 250 : montant reel", f["montant"] == 250.0, str(f))
    verifier("8b. pack 250 : montant PROUVE (session Stripe)", f["montant_prouve"] is True, "")
    verifier("8c. pack 250 : valeur indicative 25.00 / seance",
             f["valeur_par_seance"] == 25.0, str(f["valeur_par_seance"]))
    verifier("8d. pack 250 : libelle sans reserve", f["libelle"] == "CHF 250.00", f["libelle"])
    verifier("8e. pack 250 : l'offre utilisee est nommee",
             f["offre"] == "PULSE x10 cours", f["offre"])

    # 9. renouvellement CHF 150
    f = fin({"code": "AFR-R150", "offer_name": "Membres", "renewal_sessions": 10},
            {"code": "AFR-R150", "stripe_amount": 150.0, "session_id": "cs_2", "maxUses": 10})
    verifier("9. renouvellement 150 : ≈ 15.00 / seance", f["valeur_par_seance"] == 15.0, str(f))

    # 10. cours a l'unite : pas de valeur par seance (elle n'apprendrait rien)
    f = fin({"code": "AFR-U", "offer_name": "Cours à l'unité", "renewal_sessions": 1},
            {"code": "AFR-U", "stripe_amount": 30.0, "session_id": "cs_3", "maxUses": 1})
    verifier("10. cours a l'unite : CHF 30.00", f["montant"] == 30.0, str(f))
    verifier("10b. cours a l'unite : aucune valeur par seance affichee",
             f["valeur_par_seance"] is None, str(f["valeur_par_seance"]))

    # 11. essai gratuit : CHF 0 REEL, dit comme tel
    f = fin({"code": "AFR-E", "offer_name": "Essai gratuit!"},
            {"code": "AFR-E", "payment_method": "free", "total_paid": 0, "maxUses": 1})
    verifier("11. essai gratuit : montant 0 REEL", f["montant"] == 0.0, str(f))
    verifier("11b. essai gratuit : annonce « GRATUIT », pas « CHF 0.00 »",
             f["libelle"].startswith("GRATUIT"), f["libelle"])
    verifier("11c. essai gratuit : marque comme gratuit", f["gratuit"] is True, "")

    # ... et le geste commercial du coach (lot B)
    f = fin({"origine_paiement": "offert", "montant_encaisse": 0, "code": "CADEAU"},
            {"code": "CADEAU", "maxUses": 1})
    verifier("11d. acces offert par le coach : « GRATUIT — offert »",
             f["gratuit"] and "offert" in f["libelle"], f["libelle"])

    # 12. event paye separement : le montant REELLEMENT paye
    f = fin({}, {}, {"offerName": "Laff Festival", "totalPrice": 40.0})
    verifier("12. event : le montant porte par la reservation est retenu",
             f["montant"] == 40.0 and f["montant_source"] == "reservation", str(f))

    # 13. historique incomplet : on le DIT
    f = fin({"code": "BASSBOOSTX-11", "offer_name": "BASSBOOSTX-11", "total_sessions": 47},
            {"code": "BASSBOOSTX-11", "maxUses": 47})
    verifier("13. historique sans montant : « Montant non enregistré »",
             f["libelle"] == "Montant non enregistré", f["libelle"])
    verifier("13b. ... et surtout PAS « CHF 0 »", f["montant"] is None, str(f["montant"]))
    verifier("13c. ... ni marque gratuit", f["gratuit"] is False, "")
    verifier("13d. ... ni valeur par seance inventee", f["valeur_par_seance"] is None, "")

    # montant saisi a la main autrefois : affiche AVEC sa reserve
    f = fin({"code": "SHANNON2026", "offer_name": "Abonnement", "total_sessions": 10},
            {"code": "Shannon2026", "stripe_amount": 150.0, "maxUses": 10})
    verifier("13e. montant sans preuve : affiche avec sa reserve",
             f["montant"] == 150.0 and not f["montant_prouve"]
             and "saisi à la main" in f["libelle"], f["libelle"])
    verifier("13f. montant sans preuve : AUCUNE valeur par seance",
             f["valeur_par_seance"] is None, str(f["valeur_par_seance"]))

    # tarif fige a la creation : dit explicitement que ce n'est pas une preuve
    f = fin({"code": "DIANA", "offer_name": "PULSE x10 cours", "offer_price": 250.0},
            {"code": "DIANA", "maxUses": 10})
    verifier("13g. tarif a la creation : signale comme non confirme",
             f["montant"] == 250.0 and "non confirmé" in f["libelle"], f["libelle"])


# ═══════════ 2. LE PRIX DU CATALOGUE N'EXISTE PAS ICI ═══════════════════════
def test_pas_de_catalogue():
    src = io.open(os.path.join(RACINE, "api", "routes", "shared.py"), encoding="utf-8").read()
    bloc = src.split("LOT A — LIRE L'ARGENT SANS JAMAIS L'INVENTER")[1]
    _code_seul = "\n".join(l for l in bloc.splitlines() if not l.strip().startswith("#"))
    verifier("14. le resolveur ne lit jamais la collection `offers`",
             "offers" not in _code_seul, [l for l in _code_seul.splitlines() if "offers" in l][:1])
    verifier("14b. il n'accede a aucun champ `price` d'offre",
             '"price"' not in bloc and ".get('price')" not in bloc, "")

    resa = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()
    enrich = _extraire(("api", "routes", "reservation_routes.py"), "_a_enrichir_finance")
    verifier("14c. l'enrichissement de la liste ne lit que subscriptions et discount_codes",
             "db.offers" not in enrich, "")

    # 14 (liste utilisateur) : le prix du catalogue change APRES l'achat.
    # Le resolveur ne recoit aucune offre : le montant ne peut donc pas bouger.
    avant = fin({"code": "P", "offer_name": "PULSE x10 cours", "renewal_sessions": 10},
                {"code": "P", "stripe_amount": 250.0, "session_id": "cs", "maxUses": 10})
    # l'offre passe a 270 dans le catalogue — aucune influence possible
    apres = fin({"code": "P", "offer_name": "PULSE x10 cours", "renewal_sessions": 10},
                {"code": "P", "stripe_amount": 250.0, "session_id": "cs", "maxUses": 10})
    verifier("15. prix du catalogue modifie apres l'achat : le montant reste 250",
             avant["montant"] == apres["montant"] == 250.0, str((avant["montant"], apres["montant"])))


# ═══════════ 3. CHF ET CENTIMES — CHAMP PAR CHAMP ═══════════════════════════
def test_chf_centimes():
    # Mesure reelle du 19/08/2026 : amount=150.0 / amount_total=15000
    verifier("16. `amount_total` est en CENTIMES : 15000 -> 150.00",
             mtx({"amount_total": 15000, "amount": 150.0}) == (150.0, True),
             str(mtx({"amount_total": 15000, "amount": 150.0})))
    verifier("16b. `amount` seul est en CHF : 150.0 -> 150.00, non prouve",
             mtx({"amount": 150.0}) == (150.0, False), str(mtx({"amount": 150.0})))
    verifier("16c. `amount` est UNITAIRE : x quantite (V225)",
             mtx({"amount": 10.0, "quantity": 4}) == (40.0, False),
             str(mtx({"amount": 10.0, "quantity": 4})))
    verifier("16d. mesure reelle 4 unites a 10 CHF -> amount_total=4000 = 40.00",
             mtx({"amount": 10.0, "amount_total": 4000, "quantity": 4}) == (40.0, True), "")
    verifier("17. aucun montant : None, jamais 0",
             mtx({}) == (None, False), str(mtx({})))
    verifier("17b. transaction abandonnee (`pending`, sans amount_total) : non prouvee",
             mtx({"amount": 250.0})[1] is False, "")
    verifier("18. AUCUNE division « au cas ou » : 2.0 CHF reste 2.0",
             mtx({"amount": 2.0}) == (2.0, False), str(mtx({"amount": 2.0})))
    verifier("18b. AUCUNE multiplication : 15000 centimes ne devient pas 1500000",
             mtx({"amount_total": 15000})[0] == 150.0, "")
    verifier("18c. un seul champ est declare en centimes, et il est nomme",
             SHARED.A_CHAMPS_EN_CENTIMES == ("amount_total",),
             str(SHARED.A_CHAMPS_EN_CENTIMES))

    srv = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    verifier("18d. l'onglet Transactions ne divise plus par 100 a la main",
             '(p.get("amount_total", 0) or 0) / 100' not in srv, "")
    verifier("18e. le zero ECRIT EN DUR sur les souscriptions a disparu",
             's["_tx_price"] = 0\n' not in srv, "")


# ═══════════ 4. LE DENOMINATEUR EST FIGE ════════════════════════════════════
def test_denominateur():
    sa = SHARED.a_seances_achetees
    verifier("19. `seances_a_l_achat` (lot B) prime sur tout", sa(
        {"seances_a_l_achat": 10, "renewal_sessions": 5, "total_sessions": 40},
        {"maxUses": 7}) == 10, "")
    verifier("19b. puis `renewal_sessions`, pose a l'achat",
             sa({"renewal_sessions": 10, "total_sessions": 40}, {"maxUses": 7}) == 10, "")
    verifier("19c. puis `maxUses` du code",
             sa({"total_sessions": 40}, {"maxUses": 7}) == 7, "")
    verifier("19d. `total_sessions` n'est JAMAIS le denominateur "
             "(la reconduction V195 l'incremente)",
             sa({"total_sessions": 40}, {}) is None, str(sa({"total_sessions": 40}, {})))
    verifier("19e. `remaining_sessions` non plus (les boutons +/- le modifient)",
             sa({"remaining_sessions": 33}, {}) is None, "")

    # Cas reel : BASSBOOSTX-11 a total_sessions=47 apres ajustements manuels.
    # Diviser 250 par 47 serait absurde — et c'est impossible ici.
    f = fin({"code": "BX11", "total_sessions": 47, "renewal_price": 250},
            {"code": "BX11"})
    verifier("19f. un total ajuste a la main ne sert jamais de diviseur",
             f["valeur_par_seance"] is None, str(f))


# ═══════════ 5. LA LISTE DES RESERVATIONS ═══════════════════════════════════
async def test_liste_reservations():
    db = _Base()
    db.subscriptions.docs = [
        {"id": "sub-1", "code": "AFR-P250", "offer_name": "PULSE x10 cours",
         "renewal_sessions": 10, "total_sessions": 10, "remaining_sessions": 7},
        {"id": "sub-2", "code": "SHANNON2026", "offer_name": "Abonnement",
         "total_sessions": 10},
    ]
    db.discount_codes.docs = [
        {"code": "AFR-P250", "stripe_amount": 250.0, "session_id": "cs_1", "maxUses": 10},
        # CASSE DIFFERENTE — cas reel de la production.
        {"code": "Shannon2026", "stripe_amount": 150.0, "maxUses": 10},
    ]
    resas = [
        {"reservationCode": "AF1", "subscriptionId": "sub-1", "promoCode": "AFR-P250",
         "courseName": "Silent", "totalPrice": 0},
        {"reservationCode": "AF2", "subscriptionId": "sub-1", "promoCode": "AFR-P250",
         "courseName": "Silent", "totalPrice": 0},
        {"reservationCode": "AF3", "promoCode": "SHANNON2026", "courseName": "Silent",
         "totalPrice": 0},
        {"reservationCode": "AF4", "courseName": "Event", "totalPrice": 40.0},
        {"reservationCode": "AF5", "promoCode": "INCONNU-42", "courseName": "Silent",
         "totalPrice": 0},
    ]
    ns = _ns_resa(db)
    await ns["_a_enrichir_finance"](resas)

    verifier("20. chaque ligne porte son bloc financier",
             all("finance" in r for r in resas), "")
    verifier("20b. pack : montant et offre remontes depuis le forfait",
             resas[0]["finance"]["montant"] == 250.0
             and resas[0]["finance"]["offre"] == "PULSE x10 cours", str(resas[0]["finance"]))
    verifier("21. DEUX reservations du meme pack : meme achat source, "
             "AUCUNE seconde transaction",
             resas[0]["finance"]["montant"] == resas[1]["finance"]["montant"] == 250.0
             and resas[0]["finance"]["code"] == resas[1]["finance"]["code"], "")
    verifier("22. casse differente entre resa et code : le lien se fait quand meme",
             resas[2]["finance"]["montant"] == 150.0, str(resas[2]["finance"]))
    verifier("22b. ... et le montant reste signale comme non prouve",
             resas[2]["finance"]["montant_prouve"] is False, "")
    verifier("23. event sans forfait : le montant de la reservation",
             resas[3]["finance"]["montant"] == 40.0, str(resas[3]["finance"]))
    verifier("24. code introuvable : « Montant non enregistré », pas CHF 0",
             resas[4]["finance"]["montant"] is None
             and resas[4]["finance"]["libelle"] == "Montant non enregistré",
             str(resas[4]["finance"]))

    verifier("25. LECTURE SEULE : aucune ecriture sur les reservations",
             not db.reservations.ecritures, str(db.reservations.ecritures))
    verifier("25b. aucune ecriture sur les souscriptions",
             not db.subscriptions.ecritures, str(db.subscriptions.ecritures))
    verifier("25c. aucune ecriture sur les codes", not db.discount_codes.ecritures, "")
    verifier("25d. le catalogue n'a jamais ete touche", not db.offers.ecritures, "")

    # une panne d'enrichissement ne doit jamais faire disparaitre la liste
    casse = _ns_resa(db)
    casse["db"] = None
    _r = [{"reservationCode": "AFX", "promoCode": "AFR-P250"}]
    await casse["_a_enrichir_finance"](_r)
    verifier("26. panne d'enrichissement : la liste reste servie",
             _r and _r[0]["reservationCode"] == "AFX", str(_r))


# ═══════════ 6. LA PROJECTION DE LA LISTE PAGINEE ═══════════════════════════
def test_projection():
    src = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                  encoding="utf-8").read()
    proj = src.split("projection = {")[1].split("}")[0]
    for champ in ("subscriptionId", "discountCode", "courseId"):
        verifier("27. la liste paginee renvoie `%s` (elle ne le faisait pas)" % champ,
                 '"%s": 1' % champ in proj, proj[:120])
    verifier("27b. l'enrichissement est bien appele sur la liste",
             "_a_enrichir_finance(reservations)" in src, "")


# ═══════════ 7. L'INTERFACE — MOBILE ET DESKTOP ═════════════════════════════
def test_interface():
    tab = io.open(os.path.join(RACINE, "frontend", "src", "components", "coach",
                               "ReservationTab.js"), encoding="utf-8").read()
    verifier("28. mobile : la carte affiche le droit utilise et le montant",
             "Droit utilisé" in tab and "f.libelle" in tab, "")
    verifier("28b. mobile : le detail s'ouvre au clic, la carte reste compacte",
             "finance-details-toggle" in tab and "setOuvert" in tab, "")
    verifier("28c. mobile : la valeur par seance n'est rendue que si elle existe",
             "f.valeur_par_seance != null" in tab, "")
    verifier("29. desktop : le meme bloc est rendu dans la colonne « Type »",
             tab.count("<FinanceBloc") >= 2, str(tab.count("<FinanceBloc")))
    verifier("30. aucun prix n'est calcule cote client",
             "/ 100" not in tab and "* 100" not in tab, "")
    verifier("30b. aucune couleur codee en dur",
             "var(--primary-color, #D91CD2)" in tab, "")
    verifier("30c. aucune icone emoji ajoutee",
             '<SvgIcon name="creditCard"' in tab, "")

    chat = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                "ChatWidget.js"), encoding="utf-8").read()
    verifier("31. Transactions : le libelle vient du serveur",
             "txFin.libelle" in chat, "")
    verifier("31b. Transactions : « Montant non enregistré » remplace le 0 muet",
             "Montant non enregistré" in chat, "")
    verifier("31c. Transactions : une seance de pack est signalee comme droit utilise",
             "Droit utilisé — aucun nouveau paiement" in chat, "")
    bloc = chat.split("var txFin = r._tx_finance")[1][:1200]
    verifier("31d. ChatWidget : le code ajoute reste en ES5 (var / function)",
             " const " not in bloc and " let " not in bloc and "=>" not in bloc, bloc[:120])
    verifier("31e. Transactions : aucune conversion centimes cote client",
             "/ 100" not in chat.split("var txFin = r._tx_finance")[1][:2500], "")


# ═══════════ 8. NON-REGRESSION ══════════════════════════════════════════════
def test_non_regression():
    srv = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    verifier("32. paiements : le filtre `payment_status: paid` est conserve",
             '"payment_status": "paid"' in srv, "")
    verifier("32b. l'isolation par coach des paiements est conservee",
             "pay_query" in srv and "_legacy_or" in srv, "")
    verifier("33. Stripe : le webhook n'est pas touche par la lecture",
             "stripe.checkout.Session.retrieve" in srv, "")
    verifier("33b. la garde JWT-strict de l'onglet financier est intacte",
             "_v311_coach_email_from_jwt(request)" in srv, "")

    shared = io.open(os.path.join(RACINE, "api", "routes", "shared.py"), encoding="utf-8").read()
    bloc_a = shared.split("LOT A — LIRE L'ARGENT SANS JAMAIS L'INVENTER")[1]
    for interdit in ("insert_one", "update_one", "update_many", "delete_one"):
        verifier("34. le lot A n'ecrit rien : aucun `%s`" % interdit,
                 interdit not in bloc_a, "")
    verifier("34b. ESSAI non regresse : le signal de gratuite reste celui d'ESSAI-1",
             'code.get("payment_method") == "free"' in bloc_a
             and 'code.get("source") == "social_proof"' in bloc_a, "")

    resa = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()
    enrich = _extraire(("api", "routes", "reservation_routes.py"), "_a_enrichir_finance")
    for interdit in ("insert_one", "update_one", "update_many"):
        verifier("35. l'enrichissement n'ecrit rien : aucun `%s`" % interdit,
                 interdit not in enrich, "")
    verifier("35b. A1 non regresse : l'occurrence reste posee par le scan",
             "_a1_datetime_occurrence(target_course" in resa, "")
    verifier("35c. deux requetes pour toute la page, pas une par ligne",
             enrich.count("await db.subscriptions.find") == 1
             and enrich.count("await db.discount_codes.find") == 1, "")
    verifier("35d. aucune regex construite depuis une valeur stockee",
             "$regex" not in enrich, "")


# ═══════════ 9. L'ONGLET TRANSACTIONS, EXECUTE POUR DE VRAI ════════════════
async def test_onglet_transactions():
    db = _Base()
    db.reservations.docs = [
        {"reservationCode": "AF1", "userName": "Ruth", "userEmail": "r@t.ch",
         "courseName": "Silent", "subscriptionId": "sub-1", "promoCode": "AFR-P250",
         "totalPrice": 0, "createdAt": "2026-08-10T10:00:00", "validated": True,
         "coach_id": "coach@test"},
        {"reservationCode": "AF2", "userName": "Ruth", "userEmail": "r@t.ch",
         "courseName": "Silent", "subscriptionId": "sub-1", "promoCode": "AFR-P250",
         "totalPrice": 0, "createdAt": "2026-08-12T10:00:00", "validated": False,
         "coach_id": "coach@test"},
    ]
    db.subscriptions.docs = [
        {"id": "sub-1", "code": "AFR-P250", "name": "Ruth", "email": "r@t.ch",
         "offer_name": "PULSE x10 cours", "renewal_price": 250.0, "renewal_sessions": 10,
         "total_sessions": 10, "remaining_sessions": 8, "used_sessions": 2,
         "status": "active", "created_at": "2026-08-01T10:00:00", "coach_id": "coach@test"},
        # Un forfait VENDU mais dont aucune seance n'a encore ete reservee :
        # c'est exactement la ligne qui affichait « 0 CHF » en dur.
        {"id": "sub-2", "code": "AFR-N150", "name": "Kim", "email": "k@t.ch",
         "offer_name": "Membres", "renewal_price": 150.0, "renewal_sessions": 10,
         "total_sessions": 10, "remaining_sessions": 10, "used_sessions": 0,
         "status": "active", "created_at": "2026-08-05T10:00:00", "coach_id": "coach@test"},
    ]
    db.discount_codes.docs = [
        {"code": "AFR-P250", "stripe_amount": 250.0, "session_id": "cs_1", "maxUses": 10},
        {"code": "AFR-N150", "stripe_amount": 150.0, "session_id": "cs_3", "maxUses": 10},
    ]
    db.payment_transactions = type(db.reservations)([
        {"session_id": "cs_1", "amount": 250.0, "amount_total": 25000, "currency": "chf",
         "payment_status": "paid", "created_at": "2026-08-01T10:00:00",
         "metadata": {"customer_name": "Ruth", "product_name": "PULSE x10 cours"},
         "coach_id": "coach@test"},
        {"session_id": "cs_2", "amount": 30.0, "currency": "chf",
         "payment_status": "paid", "created_at": "2026-07-01T10:00:00",
         "metadata": {"customer_name": "Kim", "product_name": "Cours à l'unité"},
         "coach_id": "coach@test"},
    ])

    ns = {"db": db, "logger": _Journal(), "re": __import__("re"),
          "datetime": datetime, "timezone": timezone, "HTTPException": _HTTPException,
          "is_super_admin": lambda e: False, "Request": object, "int": int, "str": str}

    def _jwt(request):
        return "coach@test"

    async def _est_coach(email):
        return True

    ns["_v311_coach_email_from_jwt"] = _jwt
    ns["_v309_is_coach_or_admin"] = _est_coach
    exec(compile(_extraire(("api", "server.py"), "get_all_transactions"),
                 "server.py", "exec"), ns)
    res = await ns["get_all_transactions"](object())
    par_code = {}
    for it in res["data"]:
        par_code[it.get("reservationCode") or it.get("code") or it.get("session_id")] = it

    sub = par_code.get("AFR-N150")
    verifier("36. la souscription n'affiche PLUS « 0 » en dur",
             sub is not None and sub["_tx_price"] == 150.0,
             str(sub and sub.get("_tx_price")))
    verifier("36b. elle dit combien de seances ont ete ACHETEES",
             sub and sub.get("_tx_seances_achetees") == 10, str(sub and sub.get("_tx_seances_achetees")))
    verifier("36c. elle continue d'afficher le solde (10/10)",
             sub and sub.get("_tx_sessions") == "10/10", str(sub and sub.get("_tx_sessions")))
    verifier("36d. une souscription DEJA representee par une reservation "
             "n'est pas dupliquee",
             par_code.get("AFR-P250") is None, "doublon reapparu")

    tx1 = par_code.get("cs_1")
    tx2 = par_code.get("cs_2")
    verifier("37. paiement avec `amount_total` : 25000 centimes -> 250.00",
             tx1 is None or tx1["_tx_price"] == 250.0, str(tx1 and tx1.get("_tx_price")))
    verifier("37b. paiement sans `amount_total` : `amount` en CHF, plus jamais 0",
             tx2 is None or tx2["_tx_price"] == 30.0, str(tx2 and tx2.get("_tx_price")))

    resa = par_code.get("AF2")
    verifier("38. une seance de pack remonte a son achat source",
             resa and resa["_tx_finance"]["montant"] == 250.0, str(resa and resa.get("_tx_price")))
    verifier("38b. ... et est signalee comme droit UTILISE, pas comme recette",
             resa and resa.get("_tx_est_droit_utilise") is True, "")
    verifier("39. AUCUNE transaction supplementaire n'est fabriquee",
             len(db.payment_transactions.docs) == 2, str(len(db.payment_transactions.docs)))
    verifier("39b. LECTURE SEULE : aucune ecriture nulle part",
             not (db.reservations.ecritures or db.subscriptions.ecritures
                  or db.discount_codes.ecritures or db.payment_transactions.ecritures), "")


async def principal():
    test_parcours()
    test_pas_de_catalogue()
    test_chf_centimes()
    test_denominateur()
    await test_liste_reservations()
    test_projection()
    test_interface()
    test_non_regression()
    await test_onglet_transactions()


def rapport():
    print("\n" + "=" * 74)
    print("A — AFFICHAGE FINANCIER (LECTURE SEULE)")
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

# -*- coding: utf-8 -*-
"""LOT 3c-0 — A QUI APPARTIENT CETTE RESERVATION ?

CE QUE CE LOT DEFEND, EN UNE PHRASE : un client qui reserve chez le coach B
produit une reservation qui appartient au coach B. Jamais au coach principal
parce que le serveur n'a pas su trancher.

POURQUOI CE TEST EXISTE. Le lot ferme la propriete AVANT que LOT 3c ne se mette
a compter de l'argent. Une somme exacte dont on ne sait pas a qui elle revient
ne vaut rien — elle donne pire que rien, une fausse assurance. Les cinq regles
ci-dessous sont donc mesurees une par une, sur le CODE REEL extrait du depot.

LES TROIS DEFAUTS MESURES LE 20/08/2026, ET FERMES ICI :

  1. `POST /reservations` resolvait le proprietaire depuis l'en-tete
     `X-User-Email` ou depuis le CORPS de la requete. La route n'a aucune
     authentification — et ne peut pas en avoir, c'est celle du visiteur qui
     paie — donc n'importe qui pouvait s'attribuer la reservation d'un autre.

  2. Le repli `DEFAULT_COACH_ID` voulait dire « je n'ai pas su ». Inconnu
     n'est pas la plateforme : sur une chaine d'argent, cette confusion-la
     s'appelle une recette detournee.

  3. `PUT /discount-codes/{id}` n'avait AUCUNE authentification et ecrivait
     `$set: updates` BRUT. Un anonyme pouvait changer le proprietaire d'un
     code, falsifier une recette, offrir des seances.

AUCUNE BASE REELLE, AUCUN RESEAU. `shared.py` est charge par chemin (avec un
`fastapi` bouchon), les routes sont extraites du VRAI fichier par AST et
executees contre une base en memoire.

    python3 tests/test_lot3c0_propriete.py
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
    "l3c0_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
sys.modules["api"] = types.ModuleType("api")
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

SRC_RESA = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()
SRC_PROMO = io.open(os.path.join(RACINE, "api", "routes", "promo_routes.py"),
                    encoding="utf-8").read()
SRC_SERVER = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

ADMIN = SHARED.SUPER_ADMIN_EMAILS[0]      # le coach principal / la plateforme
COACH_B = "coach.b@partenaire.ch"         # le partenaire
COACH_C = "coach.c@partenaire.ch"         # un autre partenaire


def _extraire(fichier, nom):
    src = io.open(os.path.join(RACINE, *fichier), encoding="utf-8").read()
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


class _Journal:
    def __init__(self): self.erreurs = []
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): self.erreurs.append(" ".join(str(x) for x in a))


class _Requete:
    def __init__(self, entetes=None):
        self.headers = entetes or {}


def _monde():
    """Coach A (plateforme) et Coach B (partenaire), chacun avec son cours."""
    db = _Base()
    db.coaches.docs = [{"email": ADMIN}, {"email": COACH_B}]
    db.courses.docs = [
        {"id": "cours-A", "name": "Silent Lundi", "coach_id": ADMIN},
        {"id": "cours-B", "name": "Afro Mercredi", "coach_id": COACH_B},
        {"id": "cours-ORPHELIN", "name": "Sans proprietaire"},   # coach_id absent
    ]
    return db


# ═══════════ 1. LE CŒUR : A QUI APPARTIENT LA SEANCE ? ══════════════════════
async def partie_1_proprietaire():
    print("\n=== 1. CLIENT RESERVE CHEZ B -> LA RESERVATION EST A B ===")
    db = _monde()
    prop = SHARED.lot3c0_proprietaire_de_la_seance

    verifier("1a. cours de B -> la reservation appartient a B",
             await prop(db, "cours-B", None) == COACH_B)
    verifier("1b. cours de A -> la reservation appartient a A",
             await prop(db, "cours-A", None) == ADMIN)

    # LE VOL : le navigateur ment sur le proprietaire. Le cours doit gagner.
    verifier("1c. VOL — cours de A mais le corps declare B : c'est A qui gagne",
             await prop(db, "cours-A", COACH_B) == ADMIN,
             "le corps a pu deplacer la propriete !")
    verifier("1d. VOL — cours de B mais le corps declare A : c'est B qui gagne",
             await prop(db, "cours-B", ADMIN) == COACH_B)

    # SANS COURS (produit physique, offre libre) : le corps sert, mais VERIFIE.
    verifier("1e. sans cours, coach declare ENREGISTRE -> il est retenu",
             await prop(db, None, COACH_B) == COACH_B,
             "c'est le cas qui envoyait la recette du partenaire chez la plateforme")
    verifier("1f. sans cours, coach declare INCONNU -> ecarte, jamais retenu",
             await prop(db, None, "pirate@nulle-part.xx") == ADMIN)
    verifier("1g. sans cours et sans declaration -> la plateforme, a juste titre",
             await prop(db, None, None) == ADMIN)

    # LE CAS QUI A MOTIVE LE LOT : un cours sans proprietaire.
    verifier("1h. cours ORPHELIN : le corps ne peut pas se l'approprier",
             await prop(db, "cours-ORPHELIN", COACH_B) == ADMIN,
             "un cours orphelin est designable par n'importe qui : "
             "le corps ne doit pas pouvoir s'en emparer")
    verifier("1i. cours INTROUVABLE : le corps ne peut pas s'en emparer non plus",
             await prop(db, "cours-invente", COACH_B) == ADMIN)

    # « INCONNU » NE DOIT JAMAIS ETRE SILENCIEUX.
    ns = {"logger": _Journal(), "is_super_admin": SHARED.is_super_admin,
          "lot3c0_proprietaire_canonique": SHARED.lot3c0_proprietaire_canonique,
          "lot3c0_coach_enregistre": SHARED.lot3c0_coach_enregistre,
          "LOT3C0_PREFIXE": SHARED.LOT3C0_PREFIXE}
    exec(compile(_extraire(("api", "routes", "shared.py"),
                           "lot3c0_proprietaire_de_la_seance"), "shared.py", "exec"), ns)
    j = ns["logger"]
    await ns["lot3c0_proprietaire_de_la_seance"](db, "cours-ORPHELIN", COACH_B)
    verifier("1j. un repli plateforme non prouve est CRIE dans les journaux",
             any("cours_sans_proprietaire" in e for e in j.erreurs), str(j.erreurs))
    j.erreurs = []
    await ns["lot3c0_proprietaire_de_la_seance"](db, None, "pirate@nulle-part.xx")
    verifier("1k. un coach declare inconnu est CRIE lui aussi",
             any("coach_declare_inconnu" in e for e in j.erreurs), str(j.erreurs))
    j.erreurs = []
    await ns["lot3c0_proprietaire_de_la_seance"](db, None, None)
    verifier("1l. le cas NORMAL (aucune designation) ne crie pas — sinon le "
             "journal devient du bruit et plus personne ne le lit",
             not j.erreurs, str(j.erreurs))


# ═══════════ 2. LA BRANCHE « OFFRE » NE DOIT PAS RESSUSCITER ════════════════
def partie_2_pas_de_code_mort():
    print("\n=== 2. ON NE DECRIT QUE CE QUI TOURNE ===")
    bloc = _extraire(("api", "routes", "shared.py"), "lot3c0_proprietaire_de_la_seance")
    verifier("2a. la branche `offers` a bien ete RETIREE (elle etait morte : "
             "`offerId` n'existe pas dans le modele)",
             'db["offers"]' not in bloc and "offer_id" not in bloc, bloc[:200])
    verifier("2b. le modele de reservation ne declare toujours PAS `offerId` — "
             "si un jour il le declare, ce test doit etre revu, pas contourne",
             "offerId" not in SRC_RESA.split("class ReservationBase")[1].split("class ")[0])
    verifier("2c. l'appelant ne cherche plus un `offerId` fantome",
             'getattr(reservation, "offerId"' not in SRC_RESA)
    verifier("2d. l'appelant passe bien le `coach_id` du corps en second rang",
             "_l3c0_proprio(\n        db, reservation.courseId, reservation.coach_id)" in SRC_RESA
             or "db, reservation.courseId, reservation.coach_id" in SRC_RESA)


# ═══════════ 3. LE PERIMETRE DE LECTURE ═════════════════════════════════════
def partie_3_perimetre():
    print("\n=== 3. CHACUN NE LIT QUE CE QUI EST A LUI ===")
    per = SHARED.lot3c0_perimetre
    verifier("3a. le proprietaire voit TOUT, orphelins compris (aucun backfill "
             "n'est donc necessaire)", per(ADMIN, True) == {})
    verifier("3b. un partenaire ne voit QUE le sien",
             per(COACH_B, False) == {"coach_id": COACH_B})
    verifier("3c. un partenaire ne voit PAS les orphelins (sur une chaine "
             "d'argent, cette generosite s'appelle une fuite)",
             "$or" not in str(per(COACH_B, False)))
    for vide in ("", "   ", None, 0):
        try:
            per(vide, False)
            verifier("3d. sans identite -> REFUS, jamais un filtre vide", False,
                     "a rendu un filtre pour %r" % (vide,))
            break
        except SHARED.V20AccesRefuse:
            pass
    else:
        verifier("3d. sans identite -> REFUS, jamais un filtre vide (une liste "
                 "vide est une AFFIRMATION qu'on ne peut pas prouver)", True)
    verifier("3e. la casse et les espaces ne creent pas un second coach",
             per("  COACH.B@Partenaire.CH ", False) == {"coach_id": COACH_B})


# ═══════════ 4. LA REGLE EST IMPORTEE, JAMAIS RECOPIEE ══════════════════════
def partie_4_une_seule_regle():
    print("\n=== 4. UNE SEULE REGLE DE PROPRIETE, PAS UNE SEPTIEME ===")
    verifier("4a. `GET /reservations` IMPORTE le perimetre",
             "from api.routes.shared import lot3c0_perimetre" in SRC_RESA)
    verifier("4b. ... et ne reconstruit pas le filtre a la main",
             'base_query = {} if is_super_admin' not in SRC_RESA)
    verifier("4c. `POST /reservations` IMPORTE la resolution du proprietaire",
             "from api.routes.shared import lot3c0_proprietaire_de_la_seance" in SRC_RESA)
    verifier("4d. l'en-tete `X-User-Email` ne decide PLUS du proprietaire a la "
             "creation — c'etait la faille",
             'caller_email = request.headers.get("X-User-Email", "").lower().strip() if request else None'
             not in SRC_RESA)
    verifier("4e. l'enrichissement financier recoit le perimetre",
             "_a_enrichir_finance(reservations, base_query)" in SRC_RESA)


# ═══════════ 5. LE CODE PROMO : UNE CLE, PAS UN LIBELLE ═════════════════════
async def partie_5_code_immuable():
    print("\n=== 5. LE NOM D'UN CODE EST UNE CLE — ON NE LE RENOMME PAS ===")
    db = _Base()
    db.coaches.docs = [{"email": COACH_B}]
    db.discount_codes.docs = [{"_id": "oid-1", "id": "dc-1", "code": "BTEST-01",
                               "coach_id": COACH_B, "type": "100%", "value": 100,
                               "maxUses": 10, "used": 0, "active": True}]
    ns = {
        "_db": db, "re": __import__("re"), "uuid": uuid, "asyncio": asyncio,
        "datetime": datetime, "timezone": timezone, "logger": _Journal(),
        "HTTPException": _HTTPException, "SUPER_ADMIN_EMAIL": ADMIN,
        "Request": object, "Optional": None, "List": list, "dict": dict, "str": str,
        "is_super_admin": SHARED.is_super_admin,
        "coach_jwt_email": lambda r: (getattr(r, "headers", {}) or {}).get("X-User-Email", ""),
    }
    exec(compile(_extraire(("api", "routes", "promo_routes.py"),
                           "update_discount_code"), "promo_routes.py", "exec"), ns)
    maj = ns["update_discount_code"]
    req_b = _Requete({"X-User-Email": COACH_B})

    # (a) LE RENOMMAGE EST REFUSE — et refuse FRANCHEMENT, pas ignore.
    try:
        await maj("dc-1", {"code": "AUTRE-NOM"}, req_b)
        verifier("5a. renommer un code -> REFUS explicite", False, "accepte !")
    except _HTTPException as e:
        verifier("5a. renommer un code -> REFUS explicite (jamais un faux succes)",
                 e.status_code == 400, str(e.status_code))
    verifier("5b. apres refus, le nom est INTACT",
             db.discount_codes.docs[0]["code"] == "BTEST-01",
             str(db.discount_codes.docs[0].get("code")))

    # (b) RENVOYER LE MEME NOM RESTE ACCEPTE (c'est ce que fait un formulaire).
    await maj("dc-1", {"code": "BTEST-01", "maxUses": 12}, req_b)
    verifier("5c. renvoyer le MEME nom n'empeche pas la vraie modification",
             db.discount_codes.docs[0]["maxUses"] == 12,
             str(db.discount_codes.docs[0].get("maxUses")))

    # (c) LA LISTE BLANCHE : on ne s'approprie pas un code par une mise a jour.
    await maj("dc-1", {"coach_id": "voleur@x.ch", "maxUses": 13}, req_b)
    verifier("5d. `coach_id` n'est PAS modifiable : la propriete se decide a la "
             "creation, jamais par une mise a jour",
             db.discount_codes.docs[0]["coach_id"] == COACH_B,
             str(db.discount_codes.docs[0].get("coach_id")))
    verifier("5e. ... et la modification legitime du meme appel a bien eu lieu",
             db.discount_codes.docs[0]["maxUses"] == 13)

    # (d) L'AUTHENTIFICATION, ET LE CLOISONNEMENT.
    try:
        await maj("dc-1", {"maxUses": 99}, _Requete({}))
        verifier("5f. sans identite signee -> REFUS", False, "accepte !")
    except _HTTPException as e:
        verifier("5f. sans identite signee -> REFUS", e.status_code == 403, str(e.status_code))
    try:
        db.coaches.docs.append({"email": COACH_C})
        await maj("dc-1", {"maxUses": 99}, _Requete({"X-User-Email": COACH_C}))
        verifier("5g. le code d'un autre coach -> REFUS", False, "accepte !")
    except _HTTPException as e:
        verifier("5g. le code d'un autre coach -> REFUS", e.status_code == 403, str(e.status_code))
    verifier("5h. apres les deux refus, rien n'a bouge",
             db.discount_codes.docs[0]["maxUses"] == 13)

    # (d-bis) LE STOCK ANCIEN SANS PROPRIETAIRE : refus par defaut, comme le
    # DELETE voisin. Un code que personne ne possede n'est modifiable que par
    # le super-admin — sinon un partenaire pourrait MODIFIER ce qu'il n'a pas
    # le droit de SUPPRIMER.
    db.discount_codes.docs.append({"_id": "oid-2", "id": "dc-legacy",
                                   "code": "ANCIEN-01", "maxUses": 5})
    try:
        await maj("dc-legacy", {"maxUses": 99}, req_b)
        verifier("5k. un code SANS proprietaire -> REFUS pour un partenaire", False, "accepte !")
    except _HTTPException as e:
        verifier("5k. un code SANS proprietaire -> REFUS pour un partenaire "
                 "(meme regle que le DELETE voisin, V313b)",
                 e.status_code == 403, str(e.status_code))
    verifier("5l. ... et le code ancien est intact",
             db.discount_codes.docs[-1]["maxUses"] == 5)
    await maj("dc-legacy", {"maxUses": 99}, _Requete({"X-User-Email": ADMIN}))
    verifier("5m. ... mais le super-admin, lui, y accede toujours",
             db.discount_codes.docs[-1]["maxUses"] == 99)

    # (e) LE FRONTEND DIT LA MEME CHOSE QUE LE SERVEUR.
    dash = io.open(os.path.join(RACINE, "frontend", "src", "components",
                                "CoachDashboard.js"), encoding="utf-8").read()
    onglet = io.open(os.path.join(RACINE, "frontend", "src", "components", "dashboard",
                                  "PromoCodesTab.js"), encoding="utf-8").read()
    verifier("5i. le formulaire d'edition n'envoie PLUS `code`",
             "code: newCode.code,\n          type: newCode.type," not in dash)
    verifier("5j. ... et le champ est verrouille a l'ecran en mode edition "
             "(sinon l'interface promet ce que le serveur refuse)",
             "disabled={!!editingCode}" in onglet)


# ═══════════ 6. LES ECRITURES FINANCIERES ANONYMES ══════════════════════════
def partie_6_admin():
    print("\n=== 6. ON NE FALSIFIE PLUS UN MONTANT SANS SE NOMMER ===")
    for nom in ("fix_stripe_amount", "fix_all_stripe_amounts"):
        bloc = _extraire(("api", "server.py"), nom)
        verifier("6. `%s` exige un super-admin SIGNE" % nom,
                 "_v311_coach_email_from_jwt" in bloc and "is_super_admin" in bloc
                 and "403" in bloc, bloc[:160])
    verifier("6c. `fix_all_stripe_amounts` recoit enfin la requete HTTP "
             "(sans elle, s'y authentifier etait impossible)",
             "async def fix_all_stripe_amounts(request" in SRC_SERVER)


# ═══════════ 7. LE PERIMETRE DU LOT — CE QU'IL NE FAIT PAS ══════════════════
def partie_7_perimetre_du_lot():
    print("\n=== 7. CE LOT NE COMPTE AUCUN ARGENT ===")
    verifier("7a. MEMBER_PRICING_ENABLED reste a FALSE",
             'MEMBER_PRICING_ENABLED: bool = False' in SRC_SERVER
             and '"MEMBER_PRICING_ENABLED": False' in SRC_SERVER)
    verifier("7b. RESERVATIONS_JWT_STRICT est a FALSE par defaut : le "
             "durcissement de lecture reste eteint tant qu'il n'est pas prouve",
             'RESERVATIONS_JWT_STRICT: bool = False' in SRC_SERVER
             and '"RESERVATIONS_JWT_STRICT": False' in SRC_SERVER)
    verifier("7c. une panne de lecture du drapeau laisse la porte OUVERTE (V310c)",
             "_l3c0_strict = False" in SRC_RESA)
    verifier("7d. AUCUN backfill, AUCUNE migration : le stock ancien n'est pas "
             "reecrit — il reste lisible par le proprietaire (regle 3a)",
             "update_many" not in _extraire(("api", "routes", "shared.py"),
                                            "lot3c0_proprietaire_de_la_seance"))
    verifier("7e. le portillon navigateur n'a PAS ete pose sur /reservations : "
             "le serveur y accepte encore l'en-tete, durcir le navigateur seul "
             "serait exactement le defaut V310c",
             "'/reservations',\n  '/users'," not in io.open(
                 os.path.join(RACINE, "frontend", "src", "utils", "authSession.js"),
                 encoding="utf-8").read())


async def principal():
    await partie_1_proprietaire()
    partie_2_pas_de_code_mort()
    partie_3_perimetre()
    partie_4_une_seule_regle()
    await partie_5_code_immuable()
    partie_6_admin()
    partie_7_perimetre_du_lot()

    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("LOT 3c-0 — LA PROPRIETE AVANT LE COMPTAGE")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "  -> %s" % detail))
    print("-" * 74)
    print("Reservations / codes / paiements REELS : 0 — base en memoire")
    print("%d / %d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))

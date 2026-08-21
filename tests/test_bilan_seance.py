# -*- coding: utf-8 -*-
"""BILAN DE SEANCE — la route qui rend le bilan d'UNE occurrence.

CE QU'ELLE REND, ET CE QU'ELLE NE REND PAS. Pour un cours et une occurrence
precise : qui etait present, quel droit a servi, ce que vaut chaque presence, et
le total. Elle ne rend AUCUN pourcentage partenaire — ce sera le lot suivant.

ELLE NE RECALCULE RIEN. Tout le calcul vit deja dans `lot3f_valeur_presence` et
`lot3f_bilan_occurrence` (LOT 3 FINANCE), et la route se contente de LIRE les
documents et de les leur passer. Une seconde implementation du meme calcul dans
une route serait exactement ce que ce depot combat depuis LOT 3c-0.

TROIS GARANTIES QUI TIENNENT LE RESTE :
  * seul `validated: true` est un present ;
  * deux occurrences du meme cours sont DEUX bilans — jamais un regroupement
    approximatif par nom de cours ;
  * un coach ne voit que ses seances (`lot3c0_perimetre`), et la route REFUSE
    plutot que de rendre une liste vide quand l'identite manque (V443).

AUCUNE BASE REELLE, AUCUN RESEAU.
    python3 tests/test_bilan_seance.py
"""
import ast, asyncio, importlib.util, io, os, sys, types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import RESULTATS, verifier, _Base, _HTTPException  # noqa: E402

_fa = types.ModuleType("fastapi")
_fa.HTTPException = _HTTPException
_fa.APIRouter = object
_fa.Request = object
sys.modules.setdefault("fastapi", _fa)

_spec = importlib.util.spec_from_file_location(
    "bs_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
SHARED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SHARED)
_api = types.ModuleType("api")
_api.__path__ = []          # sans ceci, `api` n'est pas un PACKAGE et
                            # `from api.server import ...` echoue.
sys.modules["api"] = _api
sys.modules["api.routes"] = types.ModuleType("api.routes")
sys.modules["api.routes.shared"] = SHARED

# `api.server` factice : la route l'IMPORTE reellement (c'est ce que la garde 19
# exige), et le banc lui fournit l'identite signee comme le ferait le vrai.
_srv = types.ModuleType("api.server")
_srv._v311_coach_email_from_jwt = lambda r: getattr(r, "_signe", "") or ""
sys.modules["api.server"] = _srv

SRC_RESA = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
                   encoding="utf-8").read()

ADMIN = SHARED.SUPER_ADMIN_EMAILS[0]
COACH = "coach.b@partenaire.ch"
AUTRE = "coach.c@partenaire.ch"
OCC = "2026-08-21T18:30:00"
OCC2 = "2026-08-28T18:30:00"
COURS = "cours-afroboost"


def _extraire(nom):
    arbre = ast.parse(SRC_RESA)
    lignes = SRC_RESA.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(lignes[n.lineno - 1:n.end_lineno])
    return None


class _Journal:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass


class _Requete:
    def __init__(self, signe=None):
        self.headers = {}
        self._signe = signe or ""


def _monde():
    db = _Base()
    db.courses.docs = [{"id": COURS, "name": "Afroboost", "time": "18:30",
                        "coach_id": COACH}]
    db.subscriptions.docs = [
        {"id": "sub-pulse", "code": "PULSE-01", "email": "alice@ex.test",
         "coach_id": COACH, "status": "active", "renewal_sessions": 10},
    ]
    db.discount_codes.docs = [
        {"code": "PULSE-01", "stripe_amount": 150.0, "session_id": "cs_p",
         "maxUses": 10},
    ]
    db.reservations.docs = [
        # Alice — PULSE, tarif fige a 15
        {"id": "r1", "userName": "Alice Dupont", "userEmail": "alice@ex.test",
         "validated": True, "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "promoCode": "PULSE-01",
         "subscriptionId": "sub-pulse", "tarif_applique": 15.0,
         "tarif_raison": "forfait"},
        # Marc — cours a l'unite
        {"id": "r2", "userName": "Marc Diallo", "userEmail": "marc@ex.test",
         "validated": True, "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 30.0, "tarif_raison": "public"},
        # Sophie — essai gratuit : 0 CHF, et c'est CONNU
        {"id": "r3", "userName": "Sophie Martin", "userEmail": "sophie@ex.test",
         "validated": True, "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 0.0, "tarif_raison": "essai"},
        # Paul — historique sans preuve : A VERIFIER, jamais 0
        {"id": "r4", "userName": "Paul Ancien", "userEmail": "paul@ex.test",
         "validated": True, "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "promoCode": "VIEUX-01"},
        # Absent : reserve mais jamais valide
        {"id": "r5", "userName": "Absent", "userEmail": "abs@ex.test",
         "validated": False, "courseId": COURS, "datetime": OCC, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 30.0, "tarif_raison": "public"},
        # Meme cours, AUTRE date -> autre bilan
        {"id": "r6", "userName": "Alice Dupont", "userEmail": "alice@ex.test",
         "validated": True, "courseId": COURS, "datetime": OCC2, "coach_id": COACH,
         "courseName": "Afroboost", "tarif_applique": 15.0, "tarif_raison": "forfait"},
        # Un AUTRE coach, meme cours, meme date -> ne doit jamais fuiter
        {"id": "r7", "userName": "Etranger", "userEmail": "etr@ex.test",
         "validated": True, "courseId": COURS, "datetime": OCC, "coach_id": AUTRE,
         "courseName": "Afroboost", "tarif_applique": 99.0, "tarif_raison": "public"},
    ]
    return db


def _ns(db):
    ns = {
        "db": db, "logger": _Journal(), "HTTPException": _HTTPException,
        "Request": object, "re": __import__("re"), "int": int, "str": str,
        "bool": bool, "len": len, "sorted": sorted, "dict": dict, "set": set,
        "isinstance": isinstance, "float": float, "round": round, "list": list,
        "_v311_coach_email_from_jwt": lambda r: getattr(r, "_signe", "") or "",
        "is_super_admin": SHARED.is_super_admin,
        "lot1_occurrence_iso": None,   # remplace juste apres
    }
    src_occ = _extraire("lot1_occurrence_iso")
    if src_occ:
        _sous = {"datetime": __import__("datetime").datetime,
                 "timezone": __import__("datetime").timezone,
                 "timedelta": __import__("datetime").timedelta,
                 "str": str, "len": len, "int": int, "ValueError": ValueError,
                 "TypeError": TypeError, "Exception": Exception}
        exec(compile(src_occ, "rr.py", "exec"), _sous)
        ns["lot1_occurrence_iso"] = _sous["lot1_occurrence_iso"]
    src = _extraire("get_bilan_seance")
    if not src:
        return None
    exec(compile(src, "reservation_routes.py", "exec"), ns)
    return ns


async def principal():
    ns = _ns(_monde())
    if not ns:
        verifier("1. la route `get_bilan_seance` existe", False, "route absente")
        _resume()
        return 1
    verifier("1. la route `get_bilan_seance` existe", True)
    appel = ns["get_bilan_seance"]

    # ── LE BILAN D'UNE OCCURRENCE ───────────────────────────────────────────
    b = await appel(_Requete(signe=COACH), COURS, OCC)

    verifier("2. seuls les PRESENTS sont comptes (l'absent est exclu)",
             b.get("participants_presents") == 4,
             "presents=%r (attendu 4)" % b.get("participants_presents"))
    verifier("2b. ... et les absents sont comptes a part, pas oublies",
             b.get("participants_absents") == 1,
             "absents=%r" % b.get("participants_absents"))
    verifier("3. le total ne retient que les valeurs CONNUES : 15+30+0 = 45",
             b.get("total_connu") == 45.0, "total=%r" % b.get("total_connu"))
    verifier("4. la presence sans preuve reste A VERIFIER, jamais 0",
             b.get("participants_valeur_inconnue") == 1,
             "inconnues=%r" % b.get("participants_valeur_inconnue"))
    verifier("5. le total est marque PROVISOIRE tant qu'une valeur manque",
             b.get("provisoire") is True, "provisoire=%r" % b.get("provisoire"))

    _par_nom = {l.get("participant"): l for l in (b.get("lignes") or [])}
    verifier("6. PULSE : la valeur est le tarif FIGE (15), pas le pack divise",
             (_par_nom.get("Alice Dupont") or {}).get("valeur") == 15.0,
             "valeur=%r" % (_par_nom.get("Alice Dupont") or {}).get("valeur"))
    verifier("7. cours a l'unite : 30",
             (_par_nom.get("Marc Diallo") or {}).get("valeur") == 30.0)
    verifier("8. essai : 0 CHF et statut CONNU (zero prouve n'est pas un trou)",
             (_par_nom.get("Sophie Martin") or {}).get("valeur") == 0.0
             and (_par_nom.get("Sophie Martin") or {}).get("statut_valeur") == "connu")
    verifier("9. historique incomplet : valeur nulle et statut `inconnu`",
             (_par_nom.get("Paul Ancien") or {}).get("valeur") is None
             and (_par_nom.get("Paul Ancien") or {}).get("statut_valeur") == "inconnu")
    verifier("10. le cours et l'occurrence sont rendus pour l'affichage",
             b.get("course_name") == "Afroboost" and b.get("occurrence") == OCC,
             "cours=%r occurrence=%r" % (b.get("course_name"), b.get("occurrence")))

    # ── CROSS-COACH ─────────────────────────────────────────────────────────
    verifier("11. cross-coach : la presence d'un autre coach ne fuite pas "
             "(ni dans le compte, ni dans le total)",
             all(l.get("participant") != "Etranger" for l in (b.get("lignes") or []))
             and b.get("total_connu") == 45.0)

    b_autre = await appel(_Requete(signe=AUTRE), COURS, OCC)
    verifier("11b. ... et l'autre coach voit SA seance, pas celle du voisin",
             b_autre.get("participants_presents") == 1
             and (b_autre.get("lignes") or [{}])[0].get("participant") == "Etranger",
             "presents=%r" % b_autre.get("participants_presents"))

    # ── DEUX OCCURRENCES DU MEME COURS ──────────────────────────────────────
    b2 = await appel(_Requete(signe=COACH), COURS, OCC2)
    verifier("12. deux dates du meme cours = deux bilans SEPARES",
             b2.get("participants_presents") == 1 and b2.get("total_connu") == 15.0,
             "presents=%r total=%r" % (b2.get("participants_presents"),
                                       b2.get("total_connu")))

    # ── SEANCE VIDE ─────────────────────────────────────────────────────────
    b0 = await appel(_Requete(signe=COACH), COURS, "2026-12-31T10:00:00")
    verifier("13. seance sans participant : un bilan vide, pas une erreur",
             b0.get("participants_presents") == 0 and b0.get("total_connu") == 0.0
             and b0.get("provisoire") is False,
             "presents=%r total=%r" % (b0.get("participants_presents"),
                                       b0.get("total_connu")))

    # ── TOTAL DEFINITIF QUAND TOUT EST CONNU ────────────────────────────────
    db3 = _monde()
    db3.reservations.docs = [d for d in db3.reservations.docs if d["id"] != "r4"]
    ns3 = _ns(db3)
    b3 = await ns3["get_bilan_seance"](_Requete(signe=COACH), COURS, OCC)
    verifier("14. sans valeur inconnue, le total n'est plus provisoire",
             b3.get("provisoire") is False and b3.get("total_connu") == 45.0,
             "provisoire=%r total=%r" % (b3.get("provisoire"), b3.get("total_connu")))

    # ── IDENTITE EXIGEE ─────────────────────────────────────────────────────
    try:
        await appel(_Requete(), COURS, OCC)
        verifier("15. sans identite signee : REFUS (jamais une liste vide, V443)",
                 False, "accepte alors qu'il fallait refuser")
    except _HTTPException as e:
        verifier("15. sans identite signee : REFUS (jamais une liste vide, V443)",
                 e.status_code == 403, "obtenu %s" % e.status_code)

    # ── PERIMETRE ───────────────────────────────────────────────────────────
    corps = _extraire("get_bilan_seance") or ""
    verifier("16. la route ne RECALCULE rien : elle appelle le moteur LOT 3",
             "lot3f_valeur_presence" in corps and "lot3f_bilan_occurrence" in corps)
    # ── 17 A CHANGE DE CIBLE, ET IL FAUT LE DIRE ────────────────────────────
    #
    # Elle exigeait qu'AUCUN partage n'existe : le Bilan avait ete livre sans,
    # et cette assertion garantissait que le lot ne debordait pas sur le suivant.
    # Le lot PARTAGE PARTENAIRE l'ajoute — c'est sa raison d'etre.
    #
    # Elle n'est pas supprimee, elle est REMISE SUR SA CIBLE : le bilan peut
    # RESTITUER un partage, mais il ne doit ni le calculer lui-meme (le calcul
    # vit dans `lot3p_partage`, un seul endroit), ni declencher le moindre
    # paiement. Un pourcentage code en dur ici serait exactement la seconde
    # verite financiere que ce chantier existe pour empecher.
    verifier("17. le bilan RESTITUE le partage sans le recalculer : "
             "aucun pourcentage code en dur",
             "* 0.3" not in corps and "* 0.5" not in corps
             and "/ 100" not in corps)
    verifier("17b. ... et il ne declenche AUCUN paiement",
             not any(m in corps.lower() for m in
                     ("stripe.", "transfer", "payout", "virement", "invoice")))
    verifier("18. la route est en LECTURE PURE : aucune ecriture",
             "update_one" not in corps and "insert_one" not in corps
             and "delete_one" not in corps and "update_many" not in corps)

    # ── 19. LA GARDE QUI MANQUAIT, ET QUI A COUTE UN 500 ────────────────────
    #
    # Ce banc FOURNIT `_v311_coach_email_from_jwt` dans son espace de noms. La
    # route, elle, tournait sans l'avoir importe — il vit dans `api/server.py`.
    # Resultat : 20/20 ici, et un `NameError` (donc un 500, pas un 403) en vrai.
    # C'est le banc navigateur qui l'a attrape.
    #
    # On verifie donc que tout nom EXTERNE utilise par la route est soit importe
    # dans le fichier, soit defini dedans. Un banc en memoire ne doit plus
    # pouvoir masquer une dependance absente.
    _arbre = ast.parse(corps)
    _appeles = set()
    for _n in ast.walk(_arbre):
        if isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name):
            _appeles.add(_n.func.id)
    _module = ast.parse(SRC_RESA)
    _dispo = set(dir(__builtins__)) if isinstance(__builtins__, type(ast)) else set(dir(ast))
    _dispo |= {"dict", "set", "list", "str", "int", "float", "bool", "len",
               "sorted", "round", "isinstance", "print"}
    for _n in ast.walk(_module):
        if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _dispo.add(_n.name)
        elif isinstance(_n, ast.ImportFrom):
            for _a in _n.names:
                _dispo.add(_a.asname or _a.name)
        elif isinstance(_n, ast.Import):
            for _a in _n.names:
                _dispo.add((_a.asname or _a.name).split(".")[0])
        elif isinstance(_n, ast.Assign):
            for _t in _n.targets:
                if isinstance(_t, ast.Name):
                    _dispo.add(_t.id)
    _manquants = sorted(_appeles - _dispo)
    verifier("19. tout nom appele par la route est REELLEMENT disponible "
             "(un banc qui le fournit ne doit pas masquer un import absent)",
             not _manquants, "noms introuvables : %r" % (_manquants,))

    _resume()
    return 0 if all(c for _, c, _ in RESULTATS) else 1


def _resume():
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 74)
    print("BILAN DE SEANCE — QUI ETAIT LA, ET CE QUE VAUT CETTE SEANCE")
    print("=" * 74)
    for nom, cond, detail in RESULTATS:
        print("  %s  %s%s" % ("OK   " if cond else "ECHEC", nom,
                              "" if cond or not detail else "\n          -> %s" % detail))
    print("-" * 74)
    print("Base en memoire. Donnees de production : 0")
    print("%d / %d verifications" % (ok, len(RESULTATS)))


if __name__ == "__main__":
    sys.exit(asyncio.run(principal()))

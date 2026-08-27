# -*- coding: utf-8 -*-
"""LOT B3-S0 — LA SUPPRESSION D'UNE RESERVATION EXIGE UNE IDENTITE PROUVEE.

LE DEFAUT, STRUCTUREL. `DELETE /api/reservations/{id}`
(`api/routes/reservation_routes.py`) etait declaree
`async def delete_reservation(reservation_id: str)` — SANS parametre `request`.
Elle ne pouvait donc lire aucun en-tete : l'authentification n'etait pas
oubliee, elle etait IMPOSSIBLE. C'etait la seule route de ce routeur dans ce
cas ; ses voisines portent `_r11_scanneur`, `coach_jwt_email` ou
`is_super_admin`.

CE QUE CELA OUVRAIT, chaine verifiee : `GET /api/subscriber/space/{code}` rend
la liste des reservations AVEC leurs `id` sans authentification ; il suffisait
ensuite d'un DELETE pour supprimer DEFINITIVEMENT la reservation (`delete_one`,
aucun archivage) et recrediter un forfait. Sans compter le contournement du
delai d'annulation, que seul le chemin abonne verifie.

CE BANC N'EST PAS UN BANC DE COMPTEURS. La coherence
`discount_codes` / `subscriptions` reste au LOT B3 : on verifie ici que le
comportement de recredit du chemin coach legitime est INCHANGE.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_lotb3s0_delete_auth.py
"""
import ast, asyncio, importlib.util, io, os, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import tests._banc_qr as B
from tests._banc_qr import (_Base, _Collection, _HTTPException, _Requete, _Journal,
                            construire, extraire, faux_api_server, faux_shared)

# LOT B3 : `delete_reservation` importe desormais les fonctions LOT B3 depuis
# `shared.py` — que `faux_shared()` remplace par un bouchon. On charge donc le
# VRAI module pour les rebrancher (montage uniquement : aucune attente touchee).
_spec_reel = importlib.util.spec_from_file_location(
    "b3s0_shared_reel", os.path.join(RACINE, "api", "routes", "shared.py"))
_S_REEL = importlib.util.module_from_spec(_spec_reel)
_spec_reel.loader.exec_module(_S_REEL)
_DRAPEAU_B3_AVANT = os.environ.get("LOTB3_ANNULATION_CANONIQUE_ENABLED")

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


COACH = "coach@test"
AUTRE_COACH = "autre@test"
ADMIN = "admin@test"


def _match_tx(doc, filtre):
    """`_match` du banc partage, plus `$gte` — l'operateur des filtres bornes
    du LOT B3 (`used >= montant`). MONTAGE uniquement."""
    from tests._banc_qr import _match
    reste = {}
    for cle, cond in (filtre or {}).items():
        if isinstance(cond, dict) and "$gte" in cond:
            try:
                if float(doc.get(cle) or 0) < float(cond["$gte"]):
                    return False
            except (TypeError, ValueError):
                return False
            autres = {k: v for k, v in cond.items() if k != "$gte"}
            if autres:
                reste[cle] = autres
        else:
            reste[cle] = cond
    return _match(doc, reste) if reste else True


class FausseSession:
    """Journalise et sait DEFAIRE. Ne prouve PAS l'atomicite du moteur — c'est
    le role de `tests/test_lotb3_atomicite_reelle.py`. Ici on verifie seulement
    que l'AUTHENTIFICATION passe avant tout, transaction ou pas."""

    def __init__(self):
        self.journal, self.ouverte = [], False

    def start_transaction(self):
        self.ouverte, self.journal = True, []

    async def commit_transaction(self):
        self.ouverte = False

    async def abort_transaction(self):
        for defaire in reversed(self.journal):
            defaire()
        self.journal, self.ouverte = [], False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FauxClient:
    async def start_session(self):
        return FausseSession()


class CollectionSupprimable(_Collection):
    """Le banc partage ne simule ni `delete_one`, ni `find_one_and_delete`, ni
    le parametre `session=`, ni `$inc` — aucune suite existante n'en avait
    besoin. On les ajoute ICI, dans le MONTAGE de ce banc, et non dans
    `_banc_qr.py` qui sert a cinq autres suites."""

    async def find_one(self, filtre, projection=None, session=None):
        for d in self.docs:
            if _match_tx(d, filtre):
                return dict(d)
        return None

    async def find_one_and_delete(self, filtre, session=None):
        for i, d in enumerate(list(self.docs)):
            if _match_tx(d, filtre):
                doc = self.docs.pop(i)
                self.ecritures.append(("delete", dict(filtre), None))
                if session is not None and session.ouverte:
                    session.journal.append(lambda i=i, doc=doc: self.docs.insert(i, doc))
                return dict(doc)
        return None

    async def update_one(self, filtre, maj, session=None):
        for d in self.docs:
            if _match_tx(d, filtre):
                avant = dict(d)
                d.update(maj.get("$set", {}))
                for cle, pas in (maj.get("$inc") or {}).items():
                    d[cle] = int(float(d.get(cle) or 0)) + int(pas)
                self.ecritures.append(("update", dict(filtre), maj))
                if session is not None and session.ouverte:
                    session.journal.append(lambda d=d, avant=avant: (d.clear(), d.update(avant)))
                return types_simple_maj(1)
        return types_simple_maj(0)

    async def delete_one(self, filtre):
        for i, d in enumerate(list(self.docs)):
            if _match_tx(d, filtre):
                self.docs.pop(i)
                self.ecritures.append(("delete", dict(filtre), None))
                return types_simple(1)
        return types_simple(0)


def types_simple(n):
    import types as _t
    return _t.SimpleNamespace(deleted_count=n)


def types_simple_maj(n):
    import types as _t
    return _t.SimpleNamespace(matched_count=n, modified_count=n)


class BaseAvecNotifs(_Base):
    """`notifications` (la trace d'annulation), des collections qui savent
    supprimer et transiger, et le `client` que reclame la transaction."""

    def __init__(self):
        _Base.__init__(self)
        self.reservations = CollectionSupprimable()
        self.subscriptions = CollectionSupprimable()
        self.discount_codes = CollectionSupprimable()
        self.notifications = _Collection()
        self.client = FauxClient()


def resa(id_="res-1", coach_id=COACH, **kw):
    d = {"id": id_, "reservationCode": "AF0000001", "userName": "Marie",
         "userEmail": "marie@test.ch", "courseId": "cours-1",
         "courseName": "Silent Mercredi", "datetime": "2026-09-01T18:30:00",
         "validated": False, "promoCode": "AFR-TEST1", "quantity": 1,
         "subscriptionId": "sub-1", "coach_id": coach_id}
    d.update(kw)
    return d


def forfait(**kw):
    d = {"id": "sub-1", "code": "AFR-TEST1", "email": "marie@test.ch",
         "name": "Marie", "remaining_sessions": 3, "total_sessions": 10,
         "used_sessions": 7, "status": "active"}
    d.update(kw)
    return d


def fiche(**kw):
    d = {"id": "dc-1", "code": "AFR-TEST1", "maxUses": 10, "used": 7, "active": True}
    d.update(kw)
    return d


def monde(reservation=None, sub=None):
    db = BaseAvecNotifs()
    db.reservations.docs.append(reservation if reservation is not None else resa())
    db.subscriptions.docs.append(sub if sub is not None else forfait())
    db.discount_codes.docs.append(fiche())
    return db


def espace(db, appelant=COACH, admins=(ADMIN,)):
    """Namespace d'execution : `delete_reservation` et ses deux gardes, extraits
    du VRAI fichier. `appelant=""` simule un anonyme."""
    faux_api_server(appelant)
    faux_shared()
    for _n in ("lotb3_actif", "lotb3_montant_debite", "lotb3_montant_restitue",
               "lotb3_code_decrementable"):
        setattr(sys.modules["api.routes.shared"], _n, getattr(_S_REEL, _n))
    os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = "true"
    ns = construire(db)
    ns["is_super_admin"] = lambda e: (e or "").lower().strip() in [a.lower() for a in admins]
    ns["_RESEND_OK"] = False
    ns["_RESEND_KEY"] = ""
    ns["SUPER_ADMIN_EMAIL"] = "admin@test"
    for nom in ("_r11_scanneur", "_r11_verifier_proprietaire", "delete_reservation"):
        code = extraire(nom, obligatoire=False)
        if code:
            exec(compile(code, "reservation_routes.py", "exec"), ns)
    for n in ast.walk(B.ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "R11_MSG_ANONYME", "R11_MSG_AUTRE_COACH"):
            exec(compile("".join(B.LIGNES[n.lineno - 1:n.end_lineno]), "c", "exec"), ns)
    return ns


async def supprimer(ns, id_="res-1"):
    """Appelle la route. Renvoie (reponse, exception) — jamais les deux."""
    fn = ns.get("delete_reservation")
    try:
        import inspect
        if "request" in inspect.signature(fn).parameters:
            return await fn(id_, _Requete({})), None
        return await fn(id_), None
    except _HTTPException as e:
        return None, e


def intact(db, rem=3, used=7, dc=7):
    """Aucune mutation : reservation presente, compteurs au repos."""
    return (len(db.reservations.docs) == 1
            and db.subscriptions.docs[0]["remaining_sessions"] == rem
            and db.subscriptions.docs[0]["used_sessions"] == used
            and db.discount_codes.docs[0]["used"] == dc
            and db.reservations.ecritures == []
            and db.subscriptions.ecritures == []
            and db.discount_codes.ecritures == [])


async def principal():
    # ══ 1. SANS AUTHENTIFICATION -> REFUS, ET AUCUNE MUTATION ══════════════
    db = monde()
    _, err = await supprimer(espace(db, appelant=""))
    verifier("1. anonyme -> refus", err is not None and err.status_code == 403,
             "reponse=%s" % (err.status_code if err else "200 ACCEPTE"))
    verifier("1. anonyme -> la reservation existe toujours", intact(db), db.reservations.ecritures)

    # ══ 2. JETON INVALIDE -> REFUS ═════════════════════════════════════════
    # `_v309_require_coach_or_admin` refuse deja un jeton illisible : le banc
    # le simule par un appelant vide, exactement comme la vraie garde.
    db = monde()
    _, err = await supprimer(espace(db, appelant=""))
    verifier("2. jeton invalide -> refus", err is not None and err.status_code == 403,
             err.status_code if err else "200")
    verifier("2. jeton invalide -> aucune mutation", intact(db))

    # ══ 3. AUTHENTIFIE MAIS NON AUTORISE -> REFUS ══════════════════════════
    # Un coach authentifie qui n'est PAS proprietaire : ni suppression, ni
    # recredit. Et la reponse ne doit pas trahir l'existence du document.
    db = monde(resa(coach_id=AUTRE_COACH))
    rep, err = await supprimer(espace(db, appelant=COACH))
    verifier("3. autre tenant -> refus", err is not None, "ACCEPTE" if err is None else err.status_code)
    verifier("3. autre tenant -> aucune mutation", intact(db))

    # ══ 4. AUCUN ORACLE : autre tenant et id inconnu se ressemblent ════════
    db1 = monde(resa(coach_id=AUTRE_COACH))
    _, e1 = await supprimer(espace(db1, appelant=COACH))
    db2 = monde()
    _, e2 = await supprimer(espace(db2, appelant=COACH), id_="inexistant-xyz")
    verifier("4. meme code pour « autre tenant » et « id inconnu »",
             e1 is not None and e2 is not None and e1.status_code == e2.status_code,
             (getattr(e1, "status_code", None), getattr(e2, "status_code", None)))
    verifier("4. meme message, aucune fuite",
             e1 is not None and e2 is not None and str(e1.detail) == str(e2.detail),
             (getattr(e1, "detail", None), getattr(e2, "detail", None)))

    # ══ 5. PROPRIETE NON PROUVABLE -> REFUS ════════════════════════════════
    # Une reservation sans `coach_id` n'appartient a personne de demontrable.
    # Sur une action DESTRUCTIVE, on refuse — on ne choisit pas un proprietaire.
    db = monde(resa(coach_id=""))
    _, err = await supprimer(espace(db, appelant=COACH))
    verifier("5. reservation orpheline -> refus", err is not None,
             "ACCEPTE" if err is None else err.status_code)
    verifier("5. reservation orpheline -> aucune mutation", intact(db))

    # ══ 6. COACH PROPRIETAIRE -> COMPORTEMENT EXISTANT CONSERVE ════════════
    db = monde()
    rep, err = await supprimer(espace(db, appelant=COACH))
    verifier("6. coach proprietaire -> accepte", err is None and (rep or {}).get("success") is True,
             err.detail if err else rep)
    verifier("6. la reservation est supprimee", len(db.reservations.docs) == 0, db.reservations.docs)
    verifier("6. le recredit reste celui d'aujourd'hui (+1 / -1)",
             db.subscriptions.docs[0]["remaining_sessions"] == 4
             and db.subscriptions.docs[0]["used_sessions"] == 6,
             (db.subscriptions.docs[0]["remaining_sessions"], db.subscriptions.docs[0]["used_sessions"]))
    # ── ASSERTION SUPPRIMEE PAR LE LOT B3, ET ELLE EST NOMMEE ICI ─────────
    # « 6. LOT B3 non commence : discount_codes INTACT » exigeait
    # `discount_codes.used == 7` ET aucune ecriture sur la collection. Ce
    # n'etait pas un controle de securite : c'etait un marqueur d'avancement,
    # ecrit au LOT B3-S0 pour prouver que ce lot-la ne touchait a aucun
    # compteur. LOT B3 est precisement le lot qui rend cette affirmation
    # fausse — il decremente `used` de 7 a 6, ce qu'une annulation doit faire.
    # Elle VERROUILLAIT le defaut ; la garder aurait interdit sa correction.
    # La securite, elle, reste prouvee par les 26 controles restants et par
    # les trois controles d'execution du banc LOT B3 (anonyme -> 403 sans
    # mutation, autre tenant -> 404 sans oracle, et « sans e-mail ET anonyme
    # -> 403 » qui prouve que l'authentification passe avant le refus 409).

    # ══ 7. SUPER-ADMIN : contrat deja present dans le depot ════════════════
    # `_r11_verifier_proprietaire` accorde deja tout au super-admin (l. 2259).
    # On ne cree aucun role : on constate celui qui existe.
    db = monde(resa(coach_id=AUTRE_COACH))
    rep, err = await supprimer(espace(db, appelant=ADMIN))
    verifier("7. super-admin -> accepte, sans inventer de privilege",
             err is None and (rep or {}).get("success") is True,
             err.detail if err else rep)

    # ══ 8. LE CODE DE RESERVATION VAUT L'ID, AVEC LES MEMES CONTROLES ══════
    db = monde()
    _, err = await supprimer(espace(db, appelant=""), id_="AF0000001")
    verifier("8. par reservationCode, anonyme -> refus", err is not None and err.status_code == 403,
             err.status_code if err else "200")
    verifier("8. par reservationCode, anonyme -> aucune mutation", intact(db))
    db = monde()
    rep, err = await supprimer(espace(db, appelant=COACH), id_="AF0000001")
    verifier("8. par reservationCode, coach proprietaire -> accepte",
             err is None and len(db.reservations.docs) == 0, err.detail if err else "")


asyncio.get_event_loop().run_until_complete(principal())

# ══ 9. LE CHEMIN ABONNE N'EST PAS TOUCHE ══════════════════════════════════
_src_srv = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_arbre_srv = ast.parse(_src_srv)
_lignes_srv = _src_srv.splitlines(True)
_corps_abonne = ""
for _n in ast.walk(_arbre_srv):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name == "cancel_reservation_from_space":
        _corps_abonne = "".join(_lignes_srv[_n.lineno - 1:_n.end_lineno])
verifier("9. le chemin abonne existe toujours", bool(_corps_abonne), "")
verifier("9. il garde son controle de propriete",
         "ne t'appartient pas" in _corps_abonne, "")
verifier("9. il garde son delai d'annulation",
         "T1_DELAI_ANNULATION_H" in _corps_abonne, "")
verifier("9. il garde son decrement discount_codes (V186)",
         "discount_codes.update_one" in _corps_abonne, "")
verifier("9. LOT B3-S0 n'y a introduit aucune garde R11",
         "_r11_scanneur" not in _corps_abonne, "")

# ══ 10. LA ROUTE PEUT DESORMAIS LIRE UNE IDENTITE ═════════════════════════
_src = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"),
               encoding="utf-8").read()
_arbre = ast.parse(_src)
for _n in ast.walk(_arbre):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name == "delete_reservation":
        _args = [a.arg for a in _n.args.args]
        _corps = "".join(_src.splitlines(True)[_n.lineno - 1:_n.end_lineno])
        verifier("10. la signature accepte `request`", "request" in _args, _args)
        verifier("10. elle appelle la garde EXISTANTE `_r11_scanneur`",
                 "_r11_scanneur" in _corps, "")
        verifier("10. et l'autorisation EXISTANTE `_r11_verifier_proprietaire`",
                 "_r11_verifier_proprietaire" in _corps, "")
        verifier("10. aucun second moteur d'authentification",
                 "jwt.decode" not in _corps and "def _b3s0_auth" not in _corps, "")

# L'environnement est RESTAURE : ce banc ne laisse pas le drapeau LOT B3 pose
# derriere lui, sans quoi il changerait le resultat des bancs suivants.
if _DRAPEAU_B3_AVANT is None:
    os.environ.pop("LOTB3_ANNULATION_CANONIQUE_ENABLED", None)
else:
    os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = _DRAPEAU_B3_AVANT

echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT B3-S0 — AUTHENTIFICATION DU DELETE (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-58s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
sys.exit(1 if echecs else 0)

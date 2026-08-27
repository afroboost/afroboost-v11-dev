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
import ast, asyncio, io, os, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import tests._banc_qr as B
from tests._banc_qr import (_Base, _Collection, _HTTPException, _Requete, _Journal,
                            construire, extraire, faux_api_server, faux_shared)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


COACH = "coach@test"
AUTRE_COACH = "autre@test"
ADMIN = "admin@test"


class CollectionSupprimable(_Collection):
    """Le banc partage ne simule pas `delete_one` — aucune suite existante ne
    supprimait. On l'ajoute ICI et pas dans `_banc_qr.py` : le perimetre
    d'ecriture de ce lot est limite a deux fichiers."""

    async def delete_one(self, filtre):
        from tests._banc_qr import _match
        for i, d in enumerate(list(self.docs)):
            if _match(d, filtre):
                self.docs.pop(i)
                self.ecritures.append(("delete", dict(filtre), None))
                return types_simple(1)
        return types_simple(0)


def types_simple(n):
    import types as _t
    return _t.SimpleNamespace(deleted_count=n)


class BaseAvecNotifs(_Base):
    """`notifications` (la trace d'annulation) et une collection `reservations`
    qui sait supprimer."""

    def __init__(self):
        _Base.__init__(self)
        self.reservations = CollectionSupprimable()
        self.notifications = _Collection()


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
    verifier("6. LOT B3 non commence : discount_codes INTACT",
             db.discount_codes.docs[0]["used"] == 7 and db.discount_codes.ecritures == [],
             db.discount_codes.docs[0]["used"])

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

echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT B3-S0 — AUTHENTIFICATION DU DELETE (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-58s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
sys.exit(1 if echecs else 0)

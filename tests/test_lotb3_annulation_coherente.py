# -*- coding: utf-8 -*-
"""LOT B3 — UNE ANNULATION REND EXACTEMENT CE QU'ELLE A DEBITE.

LE DEFAUT. `delete_reservation` recreditait `subscriptions` et ne touchait
JAMAIS `discount_codes.used`. Depuis le LOT A la page « Code promo » fait foi :
la seance annulee restait comptee comme consommee et le membre ne la revoyait
jamais. Mesure du 27/08/2026 : 38 annulations par ce chemin depuis le 20/05,
29 seances rendues cote abonnement et jamais cote code, pour 4 membres.

CE BANC NE PROUVE PAS L'ATOMICITE, ET IL NE PRETEND PAS LE FAIRE. Un faux
Mongo ne peut que verifier que le code APPELLE correctement commit et abort.
La preuve d'atomicite vit dans `tests/test_lotb3_atomicite_reelle.py`, qui
execute ce meme code contre un VRAI replica set.

CE QU'IL PROUVE : le montant restitue, les plafonds, l'abstention sur code
ambigu ou mort, le drapeau, et l'absence totale de mutation sur chaque refus.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_lotb3_annulation_coherente.py
"""
import ast, asyncio, importlib.util, io, os, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import tests._banc_qr as B
from tests._banc_qr import (_Base, _Collection, _HTTPException, _Requete,
                            _match, construire, extraire, faux_api_server, faux_shared)

_spec = importlib.util.spec_from_file_location(
    "lotb3_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


COACH = "coach@test"
ADMIN = "admin@test"


def _match_tx(doc, filtre):
    """`_match` du banc partage, plus `$gte` — l'operateur qu'utilisent les
    filtres bornes du LOT B3 (`used >= montant`). Le banc commun ne le simule
    pas et n'est pas dans le perimetre d'ecriture de ce lot : on le complete
    donc ici, sans le modifier.
    """
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


# ═══════════ un faux Mongo qui sait ouvrir une transaction ═══════════════════
class FausseSession:
    """Journalise les operations et sait les DEFAIRE. Cela ne prouve pas
    l'atomicite du moteur — cela prouve que le code appelle bien `abort`."""

    def __init__(self, base):
        self.base, self.journal, self.ouverte = base, [], False
        self.commits, self.aborts = 0, 0

    def start_transaction(self):
        self.ouverte = True
        self.journal = []

    async def commit_transaction(self):
        self.ouverte = False
        self.commits += 1

    async def abort_transaction(self):
        for defaire in reversed(self.journal):
            defaire()
        self.journal = []
        self.ouverte = False
        self.aborts += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class CollectionTx(_Collection):
    def __init__(self, docs=None, nom=""):
        _Collection.__init__(self, docs)
        self.nom = nom

    async def find_one(self, filtre, projection=None, session=None):
        return await _Collection.find_one(self, filtre, projection)

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
                return types.SimpleNamespace(matched_count=1, modified_count=1)
        return types.SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, filtre):
        for i, d in enumerate(list(self.docs)):
            if _match_tx(d, filtre):
                self.docs.pop(i)
                self.ecritures.append(("delete", dict(filtre), None))
                return types.SimpleNamespace(deleted_count=1)
        return types.SimpleNamespace(deleted_count=0)


class FauxClient:
    def __init__(self, base):
        self.base = base
        self.sessions = []

    async def start_session(self):
        s = FausseSession(self.base)
        self.sessions.append(s)
        return s


class BaseTx(_Base):
    def __init__(self, planter_apres=None):
        _Base.__init__(self)
        self.reservations = CollectionTx(nom="reservations")
        self.subscriptions = CollectionTx(nom="subscriptions")
        self.discount_codes = CollectionTx(nom="discount_codes")
        self.notifications = _Collection()
        self.client = FauxClient(self)
        self._planter_apres = planter_apres
        self._mutations = 0

    def compter(self):
        self._mutations += 1
        if self._planter_apres is not None and self._mutations > self._planter_apres:
            raise RuntimeError("panne injectee apres %d mutation(s)" % self._planter_apres)


class CollectionPannable(CollectionTx):
    """Injecte une panne APRES la n-ieme mutation, pour eprouver l'abort."""

    def __init__(self, base, docs=None, nom=""):
        CollectionTx.__init__(self, docs, nom)
        self.base = base

    async def find_one_and_delete(self, filtre, session=None):
        r = await CollectionTx.find_one_and_delete(self, filtre, session)
        if r is not None:
            self.base.compter()
        return r

    async def update_one(self, filtre, maj, session=None):
        r = await CollectionTx.update_one(self, filtre, maj, session)
        if r.modified_count:
            self.base.compter()
        return r


def resa(**kw):
    d = {"id": "res-1", "reservationCode": "AF0000001", "userName": "Marie",
         "userEmail": "marie@exemple.invalid", "courseId": "cours-1",
         "courseName": "Silent", "datetime": "2026-09-01T18:30:00", "validated": False,
         "promoCode": "SYNTH-1", "discountCode": "SYNTH-1", "quantity": 1,
         "subscriptionId": "sub-1", "source": "website", "coach_id": COACH}
    d.update(kw)
    return d


def forfait(**kw):
    d = {"id": "sub-1", "code": "SYNTH-1", "email": "marie@exemple.invalid",
         "used_sessions": 5, "remaining_sessions": 5, "total_sessions": 10,
         "status": "active"}
    d.update(kw)
    return d


def fiche(**kw):
    d = {"id": "dc-1", "code": "SYNTH-1", "maxUses": 10, "used": 5,
         "active": True, "expiresAt": None}
    d.update(kw)
    return d


def monde(reservation=None, sub=None, fiches=None, planter_apres=None):
    db = BaseTx(planter_apres)
    if planter_apres is not None:
        db.reservations = CollectionPannable(db, nom="reservations")
        db.subscriptions = CollectionPannable(db, nom="subscriptions")
        db.discount_codes = CollectionPannable(db, nom="discount_codes")
    db.reservations.docs.append(reservation if reservation is not None else resa())
    if sub is not False:
        db.subscriptions.docs.append(sub if sub is not None else forfait())
    for f in (fiches if fiches is not None else [fiche()]):
        db.discount_codes.docs.append(f)
    return db


def espace(db, appelant=COACH):
    faux_api_server(appelant)
    faux_shared()
    # `faux_shared` remplace tout le module : on y REBRANCHE les VRAIES
    # fonctions LOT B3, chargees depuis le vrai `shared.py`. Le banc teste donc
    # la regle reelle, pas une copie.
    _stub = sys.modules["api.routes.shared"]
    for _n in ("lotb3_actif", "lotb3_montant_debite", "lotb3_montant_restitue",
               "lotb3_code_decrementable"):
        setattr(_stub, _n, getattr(S, _n))
    ns = construire(db)
    ns["is_super_admin"] = lambda e: (e or "").lower().strip() == ADMIN
    ns["_RESEND_OK"] = False
    ns["_RESEND_KEY"] = ""
    ns["SUPER_ADMIN_EMAIL"] = ADMIN
    for nom in ("_r11_scanneur", "_r11_verifier_proprietaire", "delete_reservation"):
        c = extraire(nom, obligatoire=False)
        if c:
            exec(compile(c, "reservation_routes.py", "exec"), ns)
    for n in ast.walk(B.ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "R11_MSG_ANONYME", "R11_MSG_AUTRE_COACH"):
            exec(compile("".join(B.LIGNES[n.lineno - 1:n.end_lineno]), "c", "exec"), ns)
    return ns


async def annuler(ns, id_="res-1"):
    try:
        return await ns["delete_reservation"](id_, _Requete({})), None
    except _HTTPException as e:
        return None, e


def etat(db):
    sub = db.subscriptions.docs[0] if db.subscriptions.docs else None
    dc = db.discount_codes.docs[0] if db.discount_codes.docs else None
    return (len(db.reservations.docs),
            None if sub is None else sub["used_sessions"],
            None if sub is None else sub["remaining_sessions"],
            None if dc is None else dc["used"])


async def principal():
    os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = "true"

    # ══ 1. ANNULATION SIMPLE : LES TROIS COMPTEURS BOUGENT ENSEMBLE ════════
    db = monde()
    rep, err = await annuler(espace(db))
    verifier("1. annulation acceptee", err is None and (rep or {}).get("success") is True,
             err.detail if err else rep)
    verifier("1. la reservation est supprimee", etat(db)[0] == 0, etat(db))
    verifier("1. used_sessions 5 -> 4", etat(db)[1] == 4, etat(db))
    verifier("1. remaining_sessions 5 -> 6", etat(db)[2] == 6, etat(db))
    verifier("1. discount_codes.used 5 -> 4  (LE DEFAUT CORRIGE)", etat(db)[3] == 4, etat(db))
    verifier("1. INVARIANT used == used_sessions", etat(db)[1] == etat(db)[3], etat(db))
    verifier("1. la transaction a ete commitee",
             db.client.sessions and db.client.sessions[0].commits == 1
             and db.client.sessions[0].aborts == 0,
             [(s.commits, s.aborts) for s in db.client.sessions])

    # ══ 2. LE MONTANT : CE QUI A ETE DEBITE, PAS `quantity` EN AVEUGLE ════
    # `website` avec 3 places n'a debite qu'UNE seance (reservation_routes:1404).
    db = monde(resa(source="website", quantity=3))
    await annuler(espace(db))
    verifier("2. website quantity=3 -> 1 seule rendue, pas 3",
             etat(db) == (0, 4, 6, 4), etat(db))
    # L'espace abonne, lui, debite `quantity` (server.py:14589).
    db = monde(resa(source="subscriber_space", quantity=2))
    await annuler(espace(db))
    verifier("2. subscriber_space quantity=2 -> 2 rendues",
             etat(db) == (0, 3, 7, 3), etat(db))
    verifier("2. et les deux compteurs rendent LE MEME nombre",
             etat(db)[1] == etat(db)[3], etat(db))

    # ══ 3. PLAFOND : AUCUN DROIT ARTIFICIEL ═══════════════════════════════
    db = monde(resa(source="subscriber_space", quantity=5),
               forfait(used_sessions=2, remaining_sessions=8), [fiche(used=2)])
    await annuler(espace(db))
    verifier("3. 5 demandees mais 2 consommees -> 2 rendues",
             etat(db) == (0, 0, 10, 0), etat(db))
    verifier("3. aucun compteur negatif", etat(db)[1] >= 0 and etat(db)[3] >= 0, etat(db))

    # ══ 4. `used = 0` : RIEN A RENDRE, ET SURTOUT PAS DE NEGATIF ══════════
    db = monde(sub=forfait(used_sessions=0, remaining_sessions=10), fiches=[fiche(used=0)])
    rep, err = await annuler(espace(db))
    verifier("4. la reservation est quand meme annulee", etat(db)[0] == 0, etat(db))
    verifier("4. aucun compteur ne descend sous 0", etat(db) == (0, 0, 10, 0), etat(db))

    # ══ 5. DOUBLE ANNULATION : UNE SEULE RESTITUTION ══════════════════════
    db = monde()
    ns = espace(db)
    await annuler(ns)
    apres1 = etat(db)
    rep, err = await annuler(ns)
    verifier("5. le second appel repond 404", err is not None and err.status_code == 404,
             err.status_code if err else "accepte")
    verifier("5. AUCUNE seconde restitution", etat(db) == apres1, (apres1, etat(db)))

    # ══ 6. DEUX ANNULATIONS CONCURRENTES ══════════════════════════════════
    db = monde()
    ns = espace(db)
    r1, r2 = await asyncio.gather(annuler(ns), annuler(ns))
    verifier("6. une seule des deux aboutit",
             [r1[1] is None, r2[1] is None].count(True) == 1,
             (getattr(r1[1], "status_code", "OK"), getattr(r2[1], "status_code", "OK")))
    verifier("6. une seule restitution", etat(db) == (0, 4, 6, 4), etat(db))

    # ══ 7. CODE AMBIGU : ABONNEMENT RECREDITE, CODE INTACT ════════════════
    db = monde(fiches=[fiche(), dict(fiche(), id="dc-2", used=9, maxUses=45)])
    await annuler(espace(db))
    verifier("7. deux fiches vivantes -> AUCUNE n'est ecrite",
             [d["used"] for d in db.discount_codes.docs] == [5, 9],
             [d["used"] for d in db.discount_codes.docs])
    verifier("7. l'abonnement est quand meme recredite",
             (etat(db)[1], etat(db)[2]) == (4, 6), etat(db))

    # ══ 8. CODE MORT : NON RESSUSCITE ═════════════════════════════════════
    db = monde(fiches=[fiche(expiresAt="2026-01-01")])
    await annuler(espace(db))
    verifier("8. code expire -> `used` inchange, aucun droit rouvert",
             db.discount_codes.docs[0]["used"] == 5, db.discount_codes.docs[0]["used"])
    db = monde(fiches=[fiche(active=False)])
    await annuler(espace(db))
    verifier("8. code inactif -> `used` inchange",
             db.discount_codes.docs[0]["used"] == 5, db.discount_codes.docs[0]["used"])
    db = monde(fiches=[fiche(used=10, maxUses=10)])
    await annuler(espace(db))
    verifier("8. code EPUISE -> decremente (c'est ce qu'une annulation defait)",
             db.discount_codes.docs[0]["used"] == 9, db.discount_codes.docs[0]["used"])

    # ══ 9. AUCUNE FICHE / AUCUN ABONNEMENT ════════════════════════════════
    db = monde(fiches=[])
    rep, err = await annuler(espace(db))
    verifier("9. aucune fiche -> abonnement seul recredite, aucune erreur",
             err is None and (etat(db)[0], etat(db)[1]) == (0, 4), (err, etat(db)))
    db = monde(resa(promoCode="", discountCode="", subscriptionId=""), sub=False, fiches=[])
    rep, err = await annuler(espace(db))
    verifier("9. reservation n'ayant consomme AUCUNE seance -> supprimee, rien d'autre",
             err is None and len(db.reservations.docs) == 0, (err.detail if err else "", etat(db)))

    # ══ 9bis. RESERVATION SANS E-MAIL : REFUS PROPRE, AUCUNE MUTATION ══════
    # Le defaut de portee levait ici un `NameError`, donc un 500. Corrige, mais
    # un 500 en moins ne suffit pas : sans e-mail la restitution n'est
    # rattachable a personne. On refuse plutot que de detruire la reservation
    # en laissant sa seance dans le vide.
    db = monde(resa(userEmail=""))
    rep, err = await annuler(espace(db))
    verifier("9bis. sans e-mail -> refus propre (409), jamais une erreur serveur",
             err is not None and err.status_code == 409,
             getattr(err, "status_code", "accepte"))
    verifier("9bis. sans e-mail -> AUCUNE mutation",
             etat(db) == (1, 5, 5, 5) and db.reservations.ecritures == []
             and db.subscriptions.ecritures == [] and db.discount_codes.ecritures == [],
             etat(db))
    # ... et la garde de propriete passe TOUJOURS avant : un anonyme est refuse
    # en 403, pas en 409 — l'authentification n'est pas contournee.
    db = monde(resa(userEmail=""))
    rep, err = await annuler(espace(db, appelant=""))
    verifier("9bis. sans e-mail ET anonyme -> 403, l'authentification prime",
             err is not None and err.status_code == 403,
             getattr(err, "status_code", "accepte"))

    # ══ 10. PANNE INJECTEE APRES CHAQUE MUTATION -> ABORT ═════════════════
    for n, libelle in ((1, "la suppression"), (2, "le compteur abonnement")):
        db = monde(planter_apres=n)
        rep, err = await annuler(espace(db))
        verifier("10. panne apres %s -> 500, aucune mutation conservee" % libelle,
                 err is not None and err.status_code == 500 and etat(db) == (1, 5, 5, 5),
                 (getattr(err, "status_code", "accepte"), etat(db)))
        verifier("10. ... et `abort` a bien ete appele (%s)" % libelle,
                 db.client.sessions and db.client.sessions[0].aborts == 1
                 and db.client.sessions[0].commits == 0,
                 [(s.commits, s.aborts) for s in db.client.sessions])

    # ══ 11. DRAPEAU ETEINT -> REFUS SANS AUCUNE MUTATION ══════════════════
    for valeur in ("false", ""):
        if valeur:
            os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = valeur
        else:
            os.environ.pop("LOTB3_ANNULATION_CANONIQUE_ENABLED", None)
        db = monde()
        rep, err = await annuler(espace(db))
        verifier("11. drapeau %s -> 503" % (valeur or "absent"),
                 err is not None and err.status_code == 503,
                 getattr(err, "status_code", "accepte"))
        verifier("11. drapeau %s -> AUCUNE mutation, aucun retour a l'ancien chemin" % (valeur or "absent"),
                 etat(db) == (1, 5, 5, 5) and db.reservations.ecritures == []
                 and db.subscriptions.ecritures == [] and db.discount_codes.ecritures == [],
                 etat(db))
    os.environ["LOTB3_ANNULATION_CANONIQUE_ENABLED"] = "true"

    # ══ 12. B3-S0 INTACT : L'AUTHENTIFICATION PASSE AVANT TOUT ════════════
    db = monde()
    rep, err = await annuler(espace(db, appelant=""))
    verifier("12. anonyme -> 403 (B3-S0 conserve)",
             err is not None and err.status_code == 403, getattr(err, "status_code", "accepte"))
    verifier("12. anonyme -> aucune mutation", etat(db) == (1, 5, 5, 5), etat(db))
    db = monde(resa(coach_id="autre@test"))
    rep, err = await annuler(espace(db, appelant=COACH))
    verifier("12. autre tenant -> 404 sans oracle (B3-S0 conserve)",
             err is not None and err.status_code == 404, getattr(err, "status_code", "accepte"))
    verifier("12. autre tenant -> aucune mutation", etat(db) == (1, 5, 5, 5), etat(db))
    db = monde(resa(coach_id=""))
    rep, err = await annuler(espace(db, appelant=COACH))
    verifier("12. propriete non prouvable -> refus, aucune mutation",
             err is not None and etat(db) == (1, 5, 5, 5), (getattr(err, "status_code", "accepte"), etat(db)))

    os.environ.pop("LOTB3_ANNULATION_CANONIQUE_ENABLED", None)


# ══ 13. LES FONCTIONS PURES, CAS PAR CAS ═════════════════════════════════
verifier("13. montant : website quantity=3 -> 1",
         S.lotb3_montant_debite({"source": "website", "quantity": 3}) == 1, "")
verifier("13. montant : subscriber_space quantity=2 -> 2",
         S.lotb3_montant_debite({"source": "subscriber_space", "quantity": 2}) == 2, "")
verifier("13. montant : source absente -> 1",
         S.lotb3_montant_debite({"quantity": 4}) == 1, "")
verifier("13. montant : quantity absurde -> 1",
         S.lotb3_montant_debite({"source": "subscriber_space", "quantity": 0}) == 1, "")
verifier("13. plafond : 3 demandes, 1 consomme -> 1",
         S.lotb3_montant_restitue(3, 1, 5) == 1, "")
verifier("13. plafond : le MEME nombre des deux cotes",
         S.lotb3_montant_restitue(3, 5, 2) == 2, "")
verifier("13. plafond : compteur absent ne contredit rien",
         S.lotb3_montant_restitue(2, None, None) == 2, "")
verifier("13. plafond : jamais negatif", S.lotb3_montant_restitue(2, 0, 0) == 0, "")
verifier("13. fiche : une seule vivante -> elle",
         S.lotb3_code_decrementable([{"id": "a", "active": True}]) == ("a", "unique"), "")
verifier("13. fiche : deux vivantes -> aucune",
         S.lotb3_code_decrementable(
             [{"id": "a", "active": True}, {"id": "b", "active": True}]) == (None, "ambigu"), "")
verifier("13. fiche : deux vivantes dont UNE canonique -> la canonique",
         S.lotb3_code_decrementable(
             [{"id": "a", "active": True},
              {"id": "b", "active": True, "canonical": True}]) == ("b", "canonical"), "")
verifier("13. fiche : toutes mortes -> aucune",
         S.lotb3_code_decrementable(
             [{"id": "a", "active": False}]) == (None, "code_mort"), "")
verifier("13. fiche : aucune -> aucune",
         S.lotb3_code_decrementable([]) == (None, "aucune_fiche"), "")

asyncio.get_event_loop().run_until_complete(principal())

echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT B3 — ANNULATION COHERENTE (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-62s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
sys.exit(1 if echecs else 0)

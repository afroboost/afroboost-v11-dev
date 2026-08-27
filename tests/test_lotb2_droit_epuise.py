# -*- coding: utf-8 -*-
"""LOT B2 — UN CODE MORT N'OUVRE PLUS DE RESERVATION.

LE DEFAUT, MESURE EN PRODUCTION AVANT D'ETRE CORRIGE. `forfait_utilisable()` ne
lit QUE `subscriptions` : ses deux entrees, `expires_at` et
`remaining_sessions`, viennent de la meme collection, et AUCUNE garde de
reservation ne consulte `discount_codes`. Deux abonnements en profitaient :

  `BASSBOOSTX-02` : code expire le 17.08, abonnement valide jusqu'au 24.10,
                    4 seances reservables, bouton « Reserver » VISIBLE ;
  `AFR-YXFCGP`    : code epuise (1/1), abonnement a `remaining_sessions: 1`.

CE QUE CE BANC PROUVE SURTOUT, C'EST CE QUE LA GARDE NE FERME PAS. Mesure du
27/08/2026 sur les 33 abonnements reservables : une garde « pas OK -> refus »
en bloquerait 19, dont 14 SANS aucune fiche `discount_codes` et `CHRISTOUX10`,
un client reel dont le seul tort est d'etre AMBIGU. La regle retenue en refuse
exactement 2. Les cas F, G et H sont donc aussi importants que A et D.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_lotb2_droit_epuise.py
"""
import asyncio, ast, importlib.util, io, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

_spec = importlib.util.spec_from_file_location(
    "lotb2_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def etat(e, motif, restant=None, total=None, expire_le=None):
    return {"etat": e, "motif": motif, "restant": restant, "total": total,
            "utilise": None if restant is None else (total or 0) - restant,
            "expire_le": expire_le, "partage": False, "codes_concurrents": []}


# ── A. CODE CANONIQUE A ZERO -> RESERVATION REFUSEE ─────────────────────────
# `AFR-YXFCGP` : maxUses 1, used 1. L'abonnement disait `remaining_sessions: 1`.
r, m = S.lotb2_verdict(etat("AUCUN_DROIT", "epuise"), 1)
verifier("A. code epuise -> refus", r is True, r)
verifier("A. le message dit pourquoi et vers qui", "utilisées" in m and "coach" in m, m)

# ── B. CODE AVEC UNE SEANCE -> RESERVATION AUTORISEE ────────────────────────
r, m = S.lotb2_verdict(etat("OK", "unique", restant=1, total=9), 1)
verifier("B. restant 1 -> autorise", r is False and m == "", (r, m))

# ── C. DROIT REELLEMENT DISTINCT ET VALIDE -> AUTORISE ──────────────────────
r, _ = S.lotb2_verdict(etat("OK", "unique", restant=8, total=9), 1)
verifier("C. droit valide -> autorise", r is False, r)
r, _ = S.lotb2_verdict(etat("OK", "unique_partage", restant=24, total=40), 1)
verifier("C. code partage valide (CLUBPMI) -> autorise", r is False, r)

# ── D. CODE EXPIRE -> REFUS ────────────────────────────────────────────────
# `BASSBOOSTX-02` : la seule fuite reellement cliquable.
r, m = S.lotb2_verdict(etat("AUCUN_DROIT", "expire", expire_le="2026-08-17"), 1)
verifier("D. code expire -> refus", r is True, r)
verifier("D. la date est rendue lisible au client", "17.08.2026" in m, m)
r, m = S.lotb2_verdict(etat("AUCUN_DROIT", "expire", expire_le=None), 1)
verifier("D. expiration inconnue -> refus quand meme, sans date inventee",
         r is True and "None" not in m and "expiré" in m, m)

# ── E. AMBIGU / MULTI-CODE -> AUCUN CHOIX ARBITRAIRE ───────────────────────
for motif in ("plusieurs_abonnements", "plusieurs_docs_code", "code_indetermine",
              "multi_codes", "consommation_contradictoire", "divergence_bloquante"):
    r, m = S.lotb2_verdict(etat("AMBIGU", motif), 1)
    verifier("E. AMBIGU/%s -> la garde s'abstient" % motif, r is False and m == "", (r, m))

# ── F. AUCUNE FICHE `discount_codes` -> ON NE FERME PAS ────────────────────
# 14 abonnements de production sont dans ce cas : essais et cours a l'unite
# parfaitement legitimes, crees sans fiche. Les fermer serait LE faux pas.
r, m = S.lotb2_verdict(etat("AUCUN_DROIT", "aucun_code_utilisable"), 1)
verifier("F. aucune fiche -> autorise (les 14 abonnements legitimes)",
         r is False and m == "", (r, m))
r, _ = S.lotb2_verdict(etat("INDISPONIBLE", "lecture_impossible"), 1)
verifier("F. lecture impossible -> autorise (une garde qui tombe ne ferme pas)",
         r is False, r)
r, _ = S.lotb2_verdict(None, 1)
verifier("F. etat absent -> autorise", r is False, r)
r, _ = S.lotb2_verdict(etat("OK", "unique", restant=None, total=None), 1)
verifier("F. OK sans chiffre -> autorise, aucun refus sur un vide", r is False, r)

# ── G. NON-REGRESSION DES MEMBRES ACTIFS NORMAUX ───────────────────────────
# Les 4 R1 surs et les 14 `OK/unique` reservables doivent tous passer.
for nom, rst in (("AmandaBoost-26", 4), ("BASSBOOSTX-31", 1),
                 ("DIANABOO2026", 8), ("AFR-AD4A77", 9)):
    r, _ = S.lotb2_verdict(etat("OK", "unique", restant=rst, total=10), 1)
    verifier("G. %s (restant %d) -> autorise" % (nom, rst), r is False, r)
# CHRISTOUX10 : client REEL, simplement AMBIGU. Une garde zelee le bloquerait.
r, _ = S.lotb2_verdict(etat("AMBIGU", "plusieurs_abonnements"), 1)
verifier("G. CHRISTOUX10 (client reel, AMBIGU) -> continue de reserver", r is False, r)

# ── H. QUANTITE ────────────────────────────────────────────────────────────
r, m = S.lotb2_verdict(etat("OK", "unique", restant=1, total=9), 3)
verifier("H. 3 places demandees, 1 restante -> refus", r is True, r)
verifier("H. le message donne les deux chiffres", "1 restante" in m and "3 demandée" in m, m)
r, _ = S.lotb2_verdict(etat("OK", "unique", restant=3, total=9), 3)
verifier("H. 3 places demandees, 3 restantes -> autorise", r is False, r)
r, _ = S.lotb2_verdict(etat("OK", "unique", restant=2, total=9), 0)
verifier("H. quantite absurde (0) -> traitee comme 1, autorise", r is False, r)

# ── I. LE DRAPEAU DE ROLLBACK ──────────────────────────────────────────────
os.environ["LOTB2_GARDE_CANONIQUE"] = "false"
verifier("I. drapeau false -> garde eteinte", S.lotb2_actif() is False, S.lotb2_actif())
os.environ["LOTB2_GARDE_CANONIQUE"] = "true"
verifier("I. drapeau true -> garde active", S.lotb2_actif() is True, S.lotb2_actif())
del os.environ["LOTB2_GARDE_CANONIQUE"]
verifier("I. drapeau absent -> active par defaut", S.lotb2_actif() is True, S.lotb2_actif())


# ── J. LA GARDE N'ECRIT RIEN, ET LIT LE BON CODE ───────────────────────────
class FausseCollection:
    def __init__(self, docs, journal, nom):
        self.docs, self.journal, self.nom = docs, journal, nom

    def _f(self, filtre):
        cond = (filtre or {}).get("code") or {}
        motif = cond.get("$regex", "")
        return [d for d in self.docs if re.search(motif, str(d.get("code") or ""), re.I)]

    def find(self, filtre, projection=None):
        self.journal.append((self.nom, "find"))
        docs = self._f(filtre)

        class _C:
            async def to_list(self_inner, n): return list(docs[:n])
        return _C()

    async def count_documents(self, filtre):
        self.journal.append((self.nom, "count"))
        return len(self._f(filtre))

    def __getattr__(self, nom):
        raise AssertionError("ecriture interdite dans le LOT B2 : %s" % nom)


class FausseBase:
    def __init__(self, codes, subs=(), membres=()):
        self.journal = []
        self.discount_codes = FausseCollection(list(codes), self.journal, "discount_codes")
        self.subscriptions = FausseCollection(list(subs), self.journal, "subscriptions")
        self.code_members = FausseCollection(list(membres), self.journal, "code_members")


_boucle = asyncio.get_event_loop()

# Le cas reel : code expire, abonnement encore garni.
db = FausseBase([{"id": "dc-1", "code": "BASSBOOSTX-02", "maxUses": 10, "used": 2,
                  "active": True, "expiresAt": "2026-08-17", "canonical": True}],
                [{"code": "BASSBOOSTX-02", "status": "active",
                  "used_sessions": 6, "remaining_sessions": 4}])
r, m = _boucle.run_until_complete(S.lotb2_refus_canonique(db, "bassboostx-02", 1))
verifier("J. BASSBOOSTX-02 : refus malgre un abonnement garni", r is True, (r, m))
verifier("J. la casse du code est indifferente", "expiré" in m, m)
verifier("J. aucune ecriture — seules des lectures ont eu lieu",
         all(x[1] in ("find", "count") for x in db.journal), db.journal)

# Un code vivant passe.
db2 = FausseBase([{"id": "dc-2", "code": "AFR-AD4A77", "maxUses": 10, "used": 1,
                   "active": True, "expiresAt": "2026-10-06"}])
r, _ = _boucle.run_until_complete(S.lotb2_refus_canonique(db2, "AFR-AD4A77", 1))
verifier("J. code vivant -> autorise", r is False, r)

# Drapeau eteint : la garde ne lit meme pas la base.
os.environ["LOTB2_GARDE_CANONIQUE"] = "false"
db3 = FausseBase([{"id": "dc-3", "code": "MORT", "maxUses": 1, "used": 1, "active": True}])
r, _ = _boucle.run_until_complete(S.lotb2_refus_canonique(db3, "MORT", 1))
verifier("J. drapeau eteint -> aucun refus ET aucune lecture",
         r is False and db3.journal == [], (r, db3.journal))
del os.environ["LOTB2_GARDE_CANONIQUE"]


# ── L. LE DEFAUT LUI-MEME, FIGE POUR TOUJOURS ──────────────────────────────
# Ce bloc ne teste pas la garde : il teste CE QUI LA REND NECESSAIRE. Sur les
# donnees exactes de `BASSBOOSTX-02`, l'ancienne garde dit OUI et la nouvelle
# dit NON. Le jour ou quelqu'un supprimera la garde en la croyant redondante,
# c'est cette verification qui le rattrapera.
_sub_reelle = {"status": "active", "total_sessions": 10, "used_sessions": 6,
               "remaining_sessions": 4, "expires_at": "2026-10-24T23:59:59+00:00"}
_ancienne_ok, _ = S.forfait_utilisable(_sub_reelle, 1)
verifier("L. l'ancienne garde (subscriptions seules) laissait passer",
         _ancienne_ok is True, _ancienne_ok)
_nouvelle_refus, _ = S.lotb2_verdict(
    etat("AUCUN_DROIT", "expire", expire_le="2026-08-17"), 1)
verifier("L. la nouvelle garde (code canonique) refuse",
         _nouvelle_refus is True, _nouvelle_refus)
verifier("L. les deux gardes sont donc COMPLEMENTAIRES, pas redondantes",
         _ancienne_ok is True and _nouvelle_refus is True, "")
# Et le miroir : la ou l'abonnement est mort, l'ancienne garde suffit toujours.
_ancienne_ko, _msg = S.forfait_utilisable(
    {"expires_at": "2026-10-24T23:59:59+00:00", "remaining_sessions": 0}, 1)
verifier("L. abonnement epuise : l'ancienne garde refuse toujours seule",
         _ancienne_ko is False and "utilisées" in _msg, _msg)


# ── K. LES DEUX CHEMINS D'ECRITURE APPELLENT BIEN LA GARDE ─────────────────
def _appelle(fichier, fonction, quoi="lotb2_refus_canonique"):
    src = io.open(os.path.join(RACINE, fichier), encoding="utf-8").read()
    arbre = ast.parse(src)
    lignes = src.splitlines(True)
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fonction:
            return quoi in "".join(lignes[n.lineno - 1:n.end_lineno])
    return False


verifier("K. l'espace abonne appelle la garde",
         _appelle("api/server.py", "reserve_course_from_space"), "")
verifier("K. la vitrine/chat appelle la garde",
         _appelle("api/routes/reservation_routes.py", "create_reservation"), "")
# L'ecran n'appelle pas `lotb2_refus_canonique` : l'etat canonique est DEJA en
# portee (`_lota`, pose par le LOT A). Il applique donc directement le meme
# verdict pur — une seule regle, deux points d'application, aucune relecture.
verifier("K. l'ecran ferme le bouton avec le MEME verdict",
         _appelle("api/server.py", "get_subscriber_space", "lotb2_verdict"), "")
# Le scan QR a la porte reste HORS PERIMETRE : quelqu'un est physiquement la.
verifier("K. le scan QR n'est PAS touche (hors perimetre assume)",
         not _appelle("api/routes/reservation_routes.py", "_qr_scan_validate_inner"), "")


echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT B2 — GARDE CANONIQUE (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-60s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
sys.exit(1 if echecs else 0)

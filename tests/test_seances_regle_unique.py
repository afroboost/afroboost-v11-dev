# -*- coding: utf-8 -*-
"""SEANCES — UNE SEULE REGLE POUR `discount_codes.used` (14/09/2026).

CE QUI ETAIT CASSE : sept chemins ecrivaient le compteur, chacun a sa facon,
sans cle d'evenement. 26 codes sur 57 avaient un `used` sans rapport avec
leurs reservations. Ce banc tient la regle unique de `api/routes/shared.py`
(`seances_consommer`, `seances_restituer`, `seances_confiance`) :

  consommation unique, rejeu identique, double clic, annulation, reservation
  echouee a mi-chemin, code simple, code club, code a plusieurs fiches,
  plafond, idempotence, atomicite (session propagee), scenario AFR-2287CA,
  et la garde : plus AUCUN `$inc` sur `used` hors de la regle.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_seances_regle_unique.py
"""
import ast, asyncio, importlib.util, io, os, re, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
_spec = importlib.util.spec_from_file_location(
    "seances_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ═════════════════════════ faux Mongo minimal (async) ════════════════════════
class DuplicateKeyError(Exception):
    code = 11000


def _val(doc, expr):
    if isinstance(expr, str) and expr.startswith("$"):
        return doc.get(expr[1:])
    if isinstance(expr, dict):
        (op, args), = expr.items()
        if op == "$ifNull":
            v = _val(doc, args[0]); return args[1] if v is None else v
        if op == "$add":
            return sum(_val(doc, a) for a in args)
        if op == "$subtract":
            return _val(doc, args[0]) - _val(doc, args[1])
        if op == "$lte":
            return _val(doc, args[0]) <= _val(doc, args[1])
        if op == "$gt":
            return _val(doc, args[0]) > _val(doc, args[1])
        raise AssertionError("operateur $expr non simule : " + op)
    return expr


def _match(doc, filtre):
    for k, v in (filtre or {}).items():
        if k == "$expr":
            if not _val(doc, v):
                return False
        elif k == "$or":
            if not any(_match(doc, f) for f in v):
                return False
        elif isinstance(v, dict) and "$regex" in v:
            if not re.match(v["$regex"], str(doc.get(k) or ""), re.I):
                return False
        elif isinstance(v, dict) and "$gte" in v:
            if (doc.get(k) or 0) < v["$gte"]:
                return False
        elif isinstance(v, dict) and "$nin" in v:
            if doc.get(k) in v["$nin"]:
                return False
        elif isinstance(v, dict) and "$gt" in v:
            if (doc.get(k) or 0) <= v["$gt"]:
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Curseur:
    def __init__(self, docs):
        self._d = docs

    def sort(self, cle, sens):
        self._d = sorted(self._d, key=lambda d: (d.get(cle) or 0), reverse=(sens < 0))
        return self

    async def to_list(self, n=None):
        await asyncio.sleep(0)
        return [dict(x) for x in (self._d if n is None else self._d[:n])]


class Coll:
    def __init__(self, base, docs=None):
        self.base = base
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, filtre=None, projection=None, session=None):
        self.base.sessions.append(("find", session))
        return _Curseur([d for d in self.docs if _match(d, filtre)])

    async def find_one(self, filtre=None, projection=None, session=None):
        await asyncio.sleep(0)
        self.base.sessions.append(("find_one", session))
        for d in self.docs:
            if _match(d, filtre):
                return dict(d)
        return None

    async def insert_one(self, doc, session=None):
        await asyncio.sleep(0)
        self.base.sessions.append(("insert_one", session))
        if "_id" in doc and any(d.get("_id") == doc["_id"] for d in self.docs):
            raise DuplicateKeyError("E11000 duplicate key")
        self.docs.append(dict(doc))
        return types.SimpleNamespace(inserted_id=doc.get("_id"))

    async def update_one(self, filtre, maj, session=None):
        await asyncio.sleep(0)
        self.base.sessions.append(("update_one", session))
        for d in self.docs:
            if _match(d, filtre):
                for k, v in (maj.get("$set") or {}).items():
                    d[k] = v
                for k, v in (maj.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                return types.SimpleNamespace(matched_count=1, modified_count=1)
        return types.SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, filtre, session=None):
        await asyncio.sleep(0)
        self.base.sessions.append(("delete_one", session))
        for i, d in enumerate(self.docs):
            if _match(d, filtre):
                del self.docs[i]
                return types.SimpleNamespace(deleted_count=1)
        return types.SimpleNamespace(deleted_count=0)

    async def find_one_and_update(self, filtre, maj, projection=None,
                                  return_document=None, session=None):
        await asyncio.sleep(0)
        self.base.sessions.append(("find_one_and_update", session))
        if self.base.panne_inc:
            raise RuntimeError("panne simulee entre la reclamation et le compteur")
        for d in self.docs:
            if _match(d, filtre):
                for k, v in (maj.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                return dict(d)
        return None


class Base:
    def __init__(self, fiches, mouvements=None):
        self.sessions = []
        self.panne_inc = False
        self.discount_codes = Coll(self, fiches)
        self.seance_mouvements = Coll(self, mouvements)

    def __getitem__(self, nom):
        return getattr(self, nom)


class _Log:
    def __init__(self):
        self.lignes = []

    def info(self, msg, *a, **k):
        self.lignes.append(("info", msg % a if a else msg))

    def warning(self, msg, *a, **k):
        self.lignes.append(("warn", msg % a if a else msg))

    error = warning


S.logger = _Log()


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def mouvements(base, type_=None):
    return [m for m in base.seance_mouvements.docs if type_ is None or m.get("type") == type_]


FICHE = {"id": "f1", "code": "PACK10", "maxUses": 10, "used": 0, "active": True,
         "expiresAt": "2099-01-01"}

# ═══════════════ 1. consommation unique ══════════════════════════════════════
b = Base([FICHE])
r = run(S.seances_consommer(b, "pack10", 1, reservation_id="r1", source="subscriber_space"))
verifier("consommation unique : used 0 -> 1", r["debite"] and r["used"] == 1, repr(r))
verifier("le mouvement debit:r1 est inscrit et applique",
         mouvements(b, "debit") and mouvements(b, "debit")[0]["_id"] == "debit:r1"
         and mouvements(b, "debit")[0]["statut"] == "applique")
verifier("la cible est la fiche par son id, pas par regex", r["fiche_id"] == "f1")

# ═══════════════ 2. rejeu identique ══════════════════════════════════════════
r2 = run(S.seances_consommer(b, "PACK10", 1, reservation_id="r1", source="subscriber_space"))
verifier("rejeu de la meme reservation : aucun second debit",
         (not r2["debite"]) and r2["motif"] == "deja_debite"
         and b.discount_codes.docs[0]["used"] == 1, repr(r2))
verifier("un seul mouvement pour r1", len(mouvements(b, "debit")) == 1)

# ═══════════════ 3. double clic (deux appels ENTRELACES) ═════════════════════
b = Base([FICHE])
async def _double_clic():
    return await asyncio.gather(
        S.seances_consommer(b, "PACK10", 1, reservation_id="r9", source="subscriber_space"),
        S.seances_consommer(b, "PACK10", 1, reservation_id="r9", source="subscriber_space"))
ra, rb = run(_double_clic())
verifier("double clic : exactement UN debit",
         sum(1 for x in (ra, rb) if x["debite"]) == 1 and b.discount_codes.docs[0]["used"] == 1,
         repr((ra, rb)))
verifier("double clic : l'autre appel est refuse comme rejeu",
         sorted(x["motif"] for x in (ra, rb)) == ["deja_debite", "ok"])

# ═══════════════ 4. annulation : restitution exacte, une seule fois ══════════
b = Base([FICHE])
run(S.seances_consommer(b, "PACK10", 2, reservation_id="r2", source="subscriber_space"))
r = run(S.seances_restituer(b, "PACK10", 2, reservation_id="r2", source="subscriber_space_cancel"))
verifier("annulation : used 2 -> 0", r["restitue"] and r["used"] == 0, repr(r))
verifier("annulation : rendue sur LA fiche du debit (voie mouvement)", r["fiche_id"] == "f1")
r = run(S.seances_restituer(b, "PACK10", 2, reservation_id="r2", source="subscriber_space_cancel"))
verifier("seconde annulation : rien de plus n'est rendu",
         (not r["restitue"]) and r["motif"] == "deja_restitue" and b.discount_codes.docs[0]["used"] == 0)
# la restitution ne rend jamais PLUS que le debit
b = Base([FICHE])
run(S.seances_consommer(b, "PACK10", 1, reservation_id="r3", source="reservations_create"))
b.discount_codes.docs[0]["used"] = 5
r = run(S.seances_restituer(b, "PACK10", 3, reservation_id="r3", source="reservations_delete"))
verifier("on rend la quantite DU DEBIT (1), pas celle demandee (3)",
         r["restitue"] and r["quantite"] == 1 and b.discount_codes.docs[0]["used"] == 4, repr(r))

# ═══════════════ 5. reservation echouee a mi-chemin ══════════════════════════
b = Base([FICHE])
b.panne_inc = True
try:
    run(S.seances_consommer(b, "PACK10", 1, reservation_id="r5", source="subscriber_space"))
    verifier("la panne remonte a l'appelant", False, "aucune exception")
except RuntimeError:
    verifier("la panne remonte a l'appelant", True)
verifier("panne : le compteur n'a pas bouge", b.discount_codes.docs[0]["used"] == 0)
verifier("panne : le mouvement reste `en_cours` (visible par l'audit)",
         mouvements(b, "debit") and mouvements(b, "debit")[0]["statut"] == "en_cours")
b.panne_inc = False
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id="r5", source="subscriber_space"))
verifier("panne puis rejeu : jamais de double debit",
         r["motif"] == "deja_debite" and b.discount_codes.docs[0]["used"] == 0)

# ═══════════════ 6. code simple : plafond porte par la requete ═══════════════
b = Base([dict(FICHE, used=9)])
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id="r6", source="subscriber_space"))
verifier("la derniere seance passe (9 -> 10)", r["debite"] and r["used"] == 10)
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id="r7", source="subscriber_space"))
verifier("plafond : la 11e est refusee, compteur intact",
         r["motif"] == "plafond_atteint" and b.discount_codes.docs[0]["used"] == 10)
verifier("plafond : le mouvement refuse est LIBERE (pas de fantome)",
         not any(m["_id"] == "debit:r7" for m in mouvements(b)))
b = Base([dict(FICHE, used=8)])
r = run(S.seances_consommer(b, "PACK10", 3, reservation_id="r8", source="subscriber_space"))
verifier("un debit groupe trop grand est refuse EN BLOC",
         r["motif"] == "plafond_atteint" and b.discount_codes.docs[0]["used"] == 8)

# ═══════════════ 7. code club (quota partage, N membres) ═════════════════════
CLUB = dict(FICHE, id="c1", code="CLUBTEST", maxUses=40, multi_member=True, shared_sessions=True)
b = Base([CLUB])
for i, slug in enumerate(("membre-a", "membre-b", "membre-c")):
    run(S.seances_consommer(b, "CLUBTEST", 1, reservation_id="club-%s" % slug,
                            source="subscriber_space"))
verifier("club : trois membres, trois seances sur LE compteur partage",
         b.discount_codes.docs[0]["used"] == 3 and len(mouvements(b, "debit")) == 3)
run(S.seances_consommer(b, "CLUBTEST", 1, reservation_id="club-membre-a", source="subscriber_space"))
verifier("club : le rejeu d'un membre ne debite pas les autres",
         b.discount_codes.docs[0]["used"] == 3)

# ═══════════════ 8. code a plusieurs fiches ══════════════════════════════════
MORTE = dict(FICHE, id="vieille", maxUses=47, used=31, expiresAt="2026-05-05")
VIVE = dict(FICHE, id="neuve", maxUses=10, used=6)
b = Base([MORTE, VIVE])
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id="m1", source="subscriber_space"))
verifier("deux fiches, une seule VIVANTE : c'est elle qui est debitee",
         r["debite"] and r["fiche_id"] == "neuve" and b.discount_codes.docs[1]["used"] == 7
         and b.discount_codes.docs[0]["used"] == 31, repr(r))
b = Base([dict(FICHE, id="a"), dict(FICHE, id="b")])
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id="m2", source="subscriber_space"))
verifier("deux fiches VIVANTES : abstention DITE, aucune ecriture",
         (not r["debite"]) and r["motif"] == "ambigu"
         and all(d["used"] == 0 for d in b.discount_codes.docs) and not mouvements(b))
b = Base([dict(FICHE, id="a"), dict(FICHE, id="b", canonical=True)])
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id="m3", source="subscriber_space"))
verifier("deux fiches vivantes dont une `canonical` : elle est designee",
         r["debite"] and r["fiche_id"] == "b")
b = Base([dict(FICHE, active=False)])
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id="m4", source="subscriber_space"))
verifier("code mort : aucun debit, motif nomme", r["motif"] == "code_mort" and not mouvements(b))

# ═══════════════ 9. idempotence de la restitution sans mouvement (historique) ═
b = Base([dict(FICHE, used=3)])
r = run(S.seances_restituer(b, "PACK10", 1, reservation_id="hist-1", source="reservations_delete"))
verifier("reservation d'avant le lot : restitution par la regle de cible",
         r["restitue"] and r["used"] == 2 and r["fiche_id"] == "f1")
r = run(S.seances_restituer(b, "PACK10", 1, reservation_id="hist-1", source="reservations_delete"))
verifier("... et une seule fois", r["motif"] == "deja_restitue" and b.discount_codes.docs[0]["used"] == 2)
b = Base([dict(FICHE, used=0)])
r = run(S.seances_restituer(b, "PACK10", 1, reservation_id="hist-2", source="reservations_delete"))
verifier("restitution sous zero refusee, mouvement libere",
         r["motif"] == "compteur_insuffisant" and b.discount_codes.docs[0]["used"] == 0
         and not mouvements(b))

# ═══════════════ 10. atomicite : la session est propagee a TOUTES les ecritures
b = Base([FICHE])
SES = object()
run(S.seances_consommer(b, "PACK10", 1, reservation_id="t1", source="reservations_delete", session=SES))
run(S.seances_restituer(b, "PACK10", 1, reservation_id="t1", source="reservations_delete", session=SES))
verifier("session : chaque acces base l'a recue (aucune ecriture hors transaction)",
         b.sessions and all(s is SES for _, s in b.sessions), repr(b.sessions[:4]))

# ═══════════════ 11. sans cle (BoostTribe) : borne, mais sans mouvement ══════
b = Base([dict(FICHE, used=9)])
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id=None, source="boosttribe_access"))
verifier("sans cle : debit borne, aucun mouvement inscrit",
         r["debite"] and r["used"] == 10 and not mouvements(b))
r = run(S.seances_consommer(b, "PACK10", 1, reservation_id=None, source="boosttribe_access"))
verifier("sans cle : le plafond tient quand meme", r["motif"] == "plafond_atteint")

# ═══════════════ 12. AFR-2287CA — scenario reel simule ═══════════════════════
# Fiche 10/7, abonnement used_sessions 7, QUATRE reservations vivantes (q=1).
niv, cause = S.seances_confiance(7, 4, [7], fiches_vivantes=1, fiches_total=1)
verifier("AFR-2287CA : PROBABLE, pas CERTAIN — aucune correction automatique",
         niv == "PROBABLE" and cause == "compteurs_concordants_registre_different", (niv, cause))
niv, cause = S.seances_confiance(0, 1, [1], fiches_vivantes=1, fiches_total=1)
verifier("AFR-E77BD4 (scan pre-B0) : CERTAIN, valeur vraie = registre",
         niv == "CERTAIN" and cause == "code_non_incremente", (niv, cause))
verifier("coherent quand compteur == registre", S.seances_confiance(4, 4, [4])[0] == "COHERENT")
verifier("BASSBOOSTX-31 : la fiche MORTE d'un code a deux fiches est HORS_CIBLE, jamais CERTAIN",
         S.seances_confiance(0, 7, [7], fiches_vivantes=1, fiches_total=2, est_cible=False)
         == ("HORS_CIBLE", "fiche_non_designee"))
verifier("... et la fiche vivante du meme code est jugee normalement",
         S.seances_confiance(7, 7, [7], fiches_vivantes=1, fiches_total=2, est_cible=True)[0] == "COHERENT")
verifier("fiches multiples encore vivantes : AMBIGU",
         S.seances_confiance(31, 8, [10], fiches_vivantes=2, fiches_total=2) == ("AMBIGU", "fiches_multiples"))
verifier("club : AMBIGU (quota partage)",
         S.seances_confiance(20, 14, [], multi_member=True) == ("AMBIGU", "quota_partage"))
verifier("aucun abonnement : AMBIGU", S.seances_confiance(19, 0, [])[0] == "AMBIGU")
verifier("deux abonnements : AMBIGU", S.seances_confiance(10, 9, [5, 10])[0] == "AMBIGU")
verifier("trois temoins differents : AMBIGU", S.seances_confiance(8, 6, [9])[0] == "AMBIGU")
verifier("code > registre == abonnement : PROBABLE (pre-B3), jamais CERTAIN",
         S.seances_confiance(4, 1, [1]) == ("PROBABLE", "code_non_decremente"))

# ═══════════════ 13. LA GARDE : plus aucune ecriture directe hors de la regle ═
SRV = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
RES = io.open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"), encoding="utf-8").read()
SHD = io.open(os.path.join(RACINE, "api", "routes", "shared.py"), encoding="utf-8").read()
for nom, src in (("server.py", SRV), ("reservation_routes.py", RES)):
    verifier("aucun `$inc` sur `used` dans %s" % nom,
             not re.search(r'\$inc"?\s*:\s*\{\s*"used"', src))
    verifier("aucun `$set` de `used` sur discount_codes dans %s" % nom,
             not re.search(r'discount_codes\.update_(one|many)\([^)]*"used"\s*:', src, re.S))
verifier("dans shared.py, `$inc` sur `used` n'apparait que DEUX fois (debit, restitution)",
         len(re.findall(r'\{"\$inc": \{"used": -?_q\}\}', SHD)) == 2
         and len(re.findall(r'\$inc"?\s*:\s*\{\s*"used"', SHD)) == 2)
for site in ("_seances_consommer(db, code_upper, quantity",          # espace abonne
             'source="subscriber_space_cancel"',                     # annulation abonne
             'source="t1_essai_non_honore"',                         # essai non honore
             'source="boosttribe_access"'):                          # BoostTribe
    verifier("server.py passe par la regle : %s" % site, site in SRV)
for site in ('source="reservations_create"', 'source="qr_scan_coach"',
             'source="reservations_delete", session=_b3_ses'):
    verifier("reservation_routes.py passe par la regle : %s" % site, site in RES)
verifier("le mouvement et la reservation partagent le meme id (espace abonne)",
         '"id": _seances_reservation_id,' in SRV)
verifier("le mouvement et la reservation partagent le meme id (scan)",
         '"id": _seances_reservation_id, "reservationCode"' in RES)
verifier("le mouvement et la reservation partagent le meme id (vitrine)",
         'reservation_data["id"] = _seances_reservation_id' in RES)

# ═══════════════ 14. l'audit : lecture seule, classement par confiance ═══════
_arbre = ast.parse(SRV)
_audit = next("".join(SRV.splitlines(True)[n.lineno - 1:n.end_lineno]) for n in ast.walk(_arbre)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "seances_audit")
verifier("l'audit est reserve a l'administrateur", "is_super_admin(email)" in _audit and "403" in _audit)
for interdit in ("update_one", "update_many", "insert_one", "delete_one", "delete_many",
                 "$inc", "$set", "find_one_and_update", "seances_consommer", "seances_restituer"):
    verifier("l'audit n'ecrit pas (%s)" % interdit, interdit not in _audit)
verifier("l'audit somme les QUANTITES et ecarte les essais restitues",
         '"quantity"' in _audit and "trial_credit_restored" in _audit)
verifier("l'audit classe par confiance et liste les mouvements en cours / orphelins",
         "seances_confiance" in _audit and "mouvements_en_cours" in _audit and "debits_orphelins" in _audit)

# ════════════════════════════════ rapport ════════════════════════════════════
ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + detail) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

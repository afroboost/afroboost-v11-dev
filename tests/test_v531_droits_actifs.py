# -*- coding: utf-8 -*-
"""V531 — LE CANONIQUE GOUVERNE L'ACCEPTATION (hotfix Amanda, 16/09/2026).

CE QUI ETAIT CASSE : `AmandaBoost-26` = 8/9 sur la page « Code promo » (LOT A,
la verite), 8 reservations vivantes, mais `subscriptions` portait 9/9 —
compteur non canonique jamais realigne. La garde d'ecriture
(`forfait_utilisable` sur `subscriptions`) et l'ecran fermaient la porte AVANT
le canonique ; LOT B2 n'ajoutait que des refus. Un abonne a jour etait bloque.
En plus, le verdict `plafond_atteint` de `seances_consommer` n'etait pas lu :
deux reservations simultanees sur la derniere seance passaient toutes les deux.

Ce banc tient les regles pures de `api/routes/shared.py` (`v531_valeurs_canoniques`,
`v531_refus_plafond`, `v531_fiche_vivante_existante`) sur un faux Mongo, en
rejouant les DONNEES REELLES d'Amanda (anonymisees) :
  CAS 1  ancien code expire + code actif 8/9            -> AUTORISE
  CAS 2  ancien code epuise + code actif                -> AUTORISE
  CAS 3  plusieurs anciens expires + 1 actif            -> le bon est choisi
  CAS 4  tout expire / epuise                           -> REFUSE
  CAS 5  8/9 -> reservation OK -> 9/9 -> suivante REFUSEE
  CAS 6  deux tentatives simultanees sur la derniere    -> UNE seule
  CAS 7  un code expire ne masque jamais un code actif
  CAS 8  creation manuelle d'un code deja VIVANT        -> refusee (409) ;
         un code MORT ne bloque pas un renouvellement
  + la garde de structure : la route lit le verdict du debit, le `$set` non
    atomique de `subscriptions` est remplace par un decrement conditionnel.
AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_v531_droits_actifs.py
"""
import asyncio, importlib.util, os, re, sys, types, uuid

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
_spec = importlib.util.spec_from_file_location(
    "v531_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ═════════════════════════ faux Mongo minimal (async) ════════════════════════
def _val(doc, expr):
    if isinstance(expr, str) and expr.startswith("$"):
        return doc.get(expr[1:])
    if isinstance(expr, dict):
        (op, args), = expr.items()
        if op == "$ifNull":
            v = _val(doc, args[0]); return args[1] if v is None else v
        if op == "$add":
            return sum(_val(doc, a) for a in args)
        if op == "$lte":
            return _val(doc, args[0]) <= _val(doc, args[1])
        if op == "$gte":
            return _val(doc, args[0]) >= _val(doc, args[1])
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
        elif isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in v["$in"]:
                return False
        elif isinstance(v, dict) and "$ne" in v:
            if doc.get(k) == v["$ne"]:
                return False
        elif isinstance(v, dict) and "$exists" in v:
            if (k in doc) != bool(v["$exists"]):
                return False
        elif doc.get(k) != v:
            return False
    return True


class _Curseur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        self.docs = self.docs[:n]; return self

    async def to_list(self, n=None):
        return [dict(d) for d in (self.docs if n is None else self.docs[:n])]

    def __aiter__(self):
        self._i = iter([dict(d) for d in self.docs]); return self

    async def __anext__(self):
        try:
            return next(self._i)
        except StopIteration:
            raise StopAsyncIteration


class Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, filtre=None, projection=None, session=None):
        return _Curseur([d for d in self.docs if _match(d, filtre)])

    async def find_one(self, filtre=None, projection=None, session=None):
        for d in self.docs:
            if _match(d, filtre):
                return dict(d)
        return None

    async def count_documents(self, filtre=None):
        return sum(1 for d in self.docs if _match(d, filtre))

    async def insert_one(self, doc, session=None):
        if "_id" in doc and any(d.get("_id") == doc["_id"] for d in self.docs):
            raise Exception("E11000 duplicate key")
        self.docs.append(dict(doc))
        return types.SimpleNamespace(inserted_id=doc.get("_id"))

    async def update_one(self, filtre, maj, session=None):
        for d in self.docs:
            if _match(d, filtre):
                for k, v in (maj.get("$set") or {}).items():
                    d[k] = v
                for k, v in (maj.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                return types.SimpleNamespace(matched_count=1, modified_count=1)
        return types.SimpleNamespace(matched_count=0, modified_count=0)

    async def delete_one(self, filtre, session=None):
        for i, d in enumerate(self.docs):
            if _match(d, filtre):
                del self.docs[i]
                return types.SimpleNamespace(deleted_count=1)
        return types.SimpleNamespace(deleted_count=0)

    async def find_one_and_update(self, filtre, maj, projection=None,
                                  return_document=None, session=None):
        for d in self.docs:
            if _match(d, filtre):
                for k, v in (maj.get("$inc") or {}).items():
                    d[k] = (d.get(k) or 0) + v
                for k, v in (maj.get("$set") or {}).items():
                    d[k] = v
                return dict(d)
        return None


class Base:
    def __init__(self, fiches, abonnements=None, membres=None, mouvements=None):
        self.discount_codes = Coll(fiches)
        self.subscriptions = Coll(abonnements)
        self.code_members = Coll(membres)
        self.seance_mouvements = Coll(mouvements)
        self.reservations = Coll()

    def __getitem__(self, nom):
        return getattr(self, nom)


# ═══════════════════════ données réelles d'Amanda, anonymisées ═══════════════
EMAIL = "abonnee@exemple.invalid"


def fiche(code, used, max_uses, expire, active=True, fid=None, canonical=None):
    d = {"id": fid or str(uuid.uuid4()), "code": code, "active": active,
         "maxUses": max_uses, "used": used, "expiresAt": expire,
         "assignedEmail": EMAIL, "coach_id": None, "multi_member": False}
    if canonical is not None:
        d["canonical"] = canonical
    return d


def abonnement(code, used, total, expire, status):
    return {"id": str(uuid.uuid4()), "code": code, "email": EMAIL,
            "used_sessions": used, "total_sessions": total,
            "remaining_sessions": max(0, total - used), "expires_at": expire,
            "status": status, "offer_name": "PULSE x10 cours (Membres)"}


def scenario_amanda():
    """Le cas de production : ancien code expiré (2 fiches, dont une inactive),
    code actif 8/9 sur la fiche, 9/9 sur l'abonnement (compteur dérivé faux)."""
    fiches = [
        fiche("BASSBOOSTX-09", 31, 47, "2026-05-05", active=False, canonical=False),
        fiche("BASSBOOSTX-09", 8, 10, "2026-08-17", active=True, canonical=True),
        fiche("AMANDABOOST-26", 8, 9, "2026-10-05", active=True, fid="fiche-amanda"),
    ]
    abos = [
        abonnement("BASSBOOSTX-09", 10, 10, "2026-08-17T23:59:59+00:00", "completed"),
        abonnement("AMANDABOOST-26", 9, 9, "2026-10-05T23:59:59+00:00", "completed"),
    ]
    return Base(fiches, abos)


async def garde_v531(db, code, quantite=1):
    """Rejoue la garde de `reserve_course_from_space` après V531 :
    abonnement V391 -> valeurs canoniques si OK -> forfait_utilisable -> LOT B2."""
    sub = await S.lire_abonnement_par_code(db, code)
    ref = dict(sub or {})
    remaining = (sub or {}).get("remaining_sessions", 0)
    ref["remaining_sessions"] = remaining
    canon = S.v531_valeurs_canoniques(await S.lota_droits_du_code(db, code))
    if canon:
        remaining = canon["remaining_sessions"]
        ref["remaining_sessions"] = remaining
        if canon.get("expires_at"):
            ref["expires_at"] = canon["expires_at"]
    ok, pourquoi = S.forfait_utilisable(ref, quantite)
    if not ok:
        return False, "V393:" + pourquoi
    refus, msg = await S.lotb2_refus_canonique(db, code, quantite)
    if refus:
        return False, "B2:" + msg
    return True, ""


async def reserver_v531(db, code):
    """Rejoue l'ordre d'écriture V531 : garde -> débit canonique (verdict lu)
    -> décrément conditionnel de `subscriptions` (ou resynchronisation)."""
    ok, pourquoi = await garde_v531(db, code)
    if not ok:
        return False, pourquoi
    rid = str(uuid.uuid4())
    debit = await S.seances_consommer(db, code, 1, reservation_id=rid, source="test")
    ferme, msg = S.v531_refus_plafond(debit)
    if ferme:
        return False, "409:" + msg
    sub = await S.lire_abonnement_par_code(db, code)
    apres = await db.subscriptions.find_one_and_update(
        {"id": sub["id"], "remaining_sessions": {"$gte": 1}},
        {"$inc": {"remaining_sessions": -1, "used_sessions": 1}})
    if apres is None and debit.get("debite") and debit.get("maxUses"):
        used = int(debit["used"]); rest = max(0, int(debit["maxUses"]) - used)
        await db.subscriptions.update_one({"id": sub["id"]}, {"$set": {
            "used_sessions": used, "remaining_sessions": rest,
            "status": "completed" if rest <= 0 else "active"}})
    await db.reservations.insert_one({"id": rid, "discountCode": code})
    return True, rid


# ═══════════════════════════════ les cas ═════════════════════════════════════
# --- helpers purs ---
verifier("pur. etat OK -> valeurs canoniques",
         S.v531_valeurs_canoniques({"etat": "OK", "restant": 1, "total": 9, "utilise": 8,
                                    "expire_le": "2026-10-05"})
         == {"remaining_sessions": 1, "used_sessions": 8, "total_sessions": 9,
             "expires_at": "2026-10-05"})
verifier("pur. AMBIGU -> None (comportement d'avant)",
         S.v531_valeurs_canoniques({"etat": "AMBIGU", "restant": None}) is None)
verifier("pur. AUCUN_DROIT -> None", S.v531_valeurs_canoniques({"etat": "AUCUN_DROIT"}) is None)
verifier("pur. restant non entier -> None",
         S.v531_valeurs_canoniques({"etat": "OK", "restant": None, "total": 9, "utilise": 8}) is None)
verifier("pur. plafond_atteint -> refus 409", S.v531_refus_plafond({"motif": "plafond_atteint"})[0] is True)
verifier("pur. ambigu / code_mort / aucune_fiche / ok -> pas de refus",
         all(S.v531_refus_plafond({"motif": m})[0] is False
             for m in ("ambigu", "code_mort", "aucune_fiche", "ok", "deja_debite")))

# --- CAS 1 : Amanda réelle — ancien expiré + actif 8/9 (abonnement 9/9) ---
db = scenario_amanda()
sub = run(S.lire_abonnement_par_code(db, "AMANDABOOST-26"))
verifier("CAS1. AVANT V531 : forfait_utilisable(subscriptions 9/9) refusait",
         S.forfait_utilisable(sub, 1)[0] is False)
lota = run(S.lota_droits_du_code(db, "AMANDABOOST-26"))
verifier("CAS1. canonique = OK 8/9, restant 1",
         lota.get("etat") == "OK" and lota.get("restant") == 1 and lota.get("utilise") == 8,
         str({k: lota.get(k) for k in ("etat", "motif", "restant", "utilise")}))
ok, pourquoi = run(garde_v531(db, "AMANDABOOST-26"))
verifier("CAS1. APRES V531 : reservation AUTORISEE", ok, pourquoi)
verifier("CAS1. AMANDA_REMAINING=1 / USED=8 / LIMIT=9",
         lota.get("restant") == 1 and lota.get("utilise") == 8 and lota.get("total") == 9)

# --- CAS 2 : ancien code ÉPUISÉ (non expiré) + actif ---
db = Base([fiche("VIEUX-10", 10, 10, "2026-12-31"), fiche("NOUVEAU-8", 3, 8, "2026-12-31")],
          [abonnement("VIEUX-10", 10, 10, "2026-12-31T23:59:59+00:00", "completed"),
           abonnement("NOUVEAU-8", 8, 8, "2026-12-31T23:59:59+00:00", "completed")])
ok, pourquoi = run(garde_v531(db, "NOUVEAU-8"))
verifier("CAS2. ancien epuise + actif (abonnement derive 8/8) -> AUTORISE", ok, pourquoi)

# --- CAS 3 : plusieurs anciens expirés + 1 actif -> la bonne fiche débitée ---
db = Base([fiche("A-2025", 5, 5, "2025-05-05"), fiche("A-2026-1", 10, 10, "2026-03-01"),
           fiche("A-ACTIF", 2, 8, "2026-12-31", fid="fiche-active")],
          [abonnement("A-ACTIF", 8, 8, "2026-12-31T23:59:59+00:00", "completed")])
ok, rid = run(reserver_v531(db, "A-ACTIF"))
f = next(d for d in db.discount_codes.docs if d["code"] == "A-ACTIF")
verifier("CAS3. autorise et la fiche ACTIVE est debitee (2 -> 3)", ok and f["used"] == 3, str((ok, rid, f["used"])))
verifier("CAS3. les fiches expirees ne bougent pas",
         all(d["used"] in (5, 10) for d in db.discount_codes.docs if d["code"] != "A-ACTIF"))
verifier("CAS3. subscriptions resynchronise sur le canonique (used 3, restant 5, active)",
         db.subscriptions.docs[0]["used_sessions"] == 3 and db.subscriptions.docs[0]["remaining_sessions"] == 5
         and db.subscriptions.docs[0]["status"] == "active", str(db.subscriptions.docs[0]))

# --- CAS 4 : tout expiré / épuisé -> refus ---
db = Base([fiche("X-EXP", 3, 10, "2026-01-01"), fiche("X-EPU", 10, 10, "2026-12-31")],
          [abonnement("X-EXP", 3, 10, "2026-01-01T23:59:59+00:00", "active"),
           abonnement("X-EPU", 10, 10, "2026-12-31T23:59:59+00:00", "completed")])
verifier("CAS4a. code expire -> REFUSE", run(garde_v531(db, "X-EXP"))[0] is False)
verifier("CAS4b. code epuise -> REFUSE", run(garde_v531(db, "X-EPU"))[0] is False)
verifier("CAS4c. abonnement 'active' mais code expire -> le canonique ferme quand meme",
         "expir" in run(garde_v531(db, "X-EXP"))[1].lower())

# --- CAS 5 : 8/9 -> OK -> 9/9 -> refus ---
db = scenario_amanda()
ok1, _ = run(reserver_v531(db, "AMANDABOOST-26"))
f = next(d for d in db.discount_codes.docs if d["code"] == "AMANDABOOST-26")
s2 = next(d for d in db.subscriptions.docs if d["code"] == "AMANDABOOST-26")
verifier("CAS5. premiere reservation OK, fiche 8 -> 9", ok1 and f["used"] == 9, str((ok1, f["used"])))
verifier("CAS5. subscriptions resynchronise 9/9 completed (pas 10)",
         s2["used_sessions"] == 9 and s2["remaining_sessions"] == 0 and s2["status"] == "completed", str(s2))
ok2, pourquoi2 = run(reserver_v531(db, "AMANDABOOST-26"))
verifier("CAS5. reservation suivante REFUSEE", ok2 is False, pourquoi2)
verifier("CAS5. aucun debit au-dela du plafond (fiche reste 9/9)", f["used"] == 9)
verifier("CAS5. un seul mouvement 'debit' journalise",
         sum(1 for m in db.seance_mouvements.docs if m.get("type") == "debit") == 1)

# --- CAS 6 : deux tentatives simultanées sur la dernière séance ---
db = scenario_amanda()


async def deux_en_meme_temps():
    return await asyncio.gather(reserver_v531(db, "AMANDABOOST-26"),
                                reserver_v531(db, "AMANDABOOST-26"))


r1, r2 = run(deux_en_meme_temps())
f = next(d for d in db.discount_codes.docs if d["code"] == "AMANDABOOST-26")
verifier("CAS6. exactement UNE des deux reussit", (r1[0] + r2[0]) == 1, str((r1, r2)))
verifier("CAS6. la perdante est refusee (garde canonique ou plafond 409)",
         any((not r[0]) and (r[1].startswith("409:") or r[1].startswith("V393:") or r[1].startswith("B2:"))
             for r in (r1, r2)), str((r1, r2)))
verifier("CAS6. la fiche n'est debitee qu'une fois (9/9)", f["used"] == 9, str(f["used"]))
verifier("CAS6. une seule reservation inseree", len(db.reservations.docs) == 1)
# La vraie course : les deux ont DEJA passe la garde (lecture 8/9 simultanee) ;
# seul le plafond atomique de `seances_consommer` peut alors departager.
db = scenario_amanda()


async def course_sur_le_plafond():
    return await asyncio.gather(
        S.seances_consommer(db, "AMANDABOOST-26", 1, reservation_id="resa-A", source="test"),
        S.seances_consommer(db, "AMANDABOOST-26", 1, reservation_id="resa-B", source="test"))


dA, dB = run(course_sur_le_plafond())
verifier("CAS6bis. garde passee par les deux : un seul debit, l'autre = plafond_atteint",
         sorted([dA["motif"], dB["motif"]]) == ["ok", "plafond_atteint"], str((dA["motif"], dB["motif"])))
verifier("CAS6bis. la route transforme ce plafond en 409 (aucune reservation)",
         any(S.v531_refus_plafond(d)[0] for d in (dA, dB)))

# --- CAS 7 : un code expiré ne masque jamais un code actif (même texte de code) ---
db = Base([fiche("MEME-CODE", 10, 10, "2026-05-05", canonical=False),
           fiche("MEME-CODE", 2, 10, "2026-12-31", fid="fiche-vivante")],
          [abonnement("MEME-CODE", 10, 10, "2026-12-31T23:59:59+00:00", "completed")])
lota = run(S.lota_droits_du_code(db, "MEME-CODE"))
verifier("CAS7. deux fiches, une morte : le canonique est OK sur la vivante (restant 8)",
         lota.get("etat") == "OK" and lota.get("restant") == 8, str({k: lota.get(k) for k in ("etat", "motif", "restant")}))
verifier("CAS7. reservation AUTORISEE malgre l'abonnement 10/10", run(garde_v531(db, "MEME-CODE"))[0] is True)

# --- CAS 8 : création manuelle -> pas de 2e fiche VIVANTE ---
db = Base([fiche("DOUBLON-1", 2, 10, "2026-12-31")])
verifier("CAS8a. un code VIVANT existe deja -> creation refusee",
         run(S.v531_fiche_vivante_existante(db, "doublon-1")) is not None)
db = Base([fiche("RENOUV-1", 10, 10, "2026-05-05"), fiche("RENOUV-2", 3, 10, "2026-06-01", active=False)])
verifier("CAS8b. un code MORT (expire) ne bloque pas un renouvellement",
         run(S.v531_fiche_vivante_existante(db, "RENOUV-1")) is None)
verifier("CAS8c. un code inactif ne bloque pas non plus",
         run(S.v531_fiche_vivante_existante(db, "RENOUV-2")) is None)
verifier("CAS8d. code vide -> None", run(S.v531_fiche_vivante_existante(db, "")) is None)

# --- Garde de structure sur la route (server.py) ---
SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
i = SRC.index('@api_router.post("/subscriber/space/{access_code}/reserve/{course_id}")')
j = SRC.index("@api_router.", i + 10)
ROUTE = SRC[i:j]
verifier("route. le verdict de seances_consommer est LU (v531_refus_plafond)",
         "v531_refus_plafond(_v531_debit)" in ROUTE)
verifier("route. le debit canonique precede l'ecriture subscriptions",
         ROUTE.index("_v531_debit = await _seances_consommer") < ROUTE.index("db.subscriptions.find_one_and_update"))
verifier("route. plus de `$set` non atomique en premier chemin (decrement conditionnel $gte)",
         '"remaining_sessions": {"$gte": quantity}' in ROUTE)
verifier("route. la garde lit les valeurs canoniques (v531_valeurs_canoniques)",
         "v531_valeurs_canoniques" in ROUTE and ROUTE.index("v531_valeurs_canoniques") < ROUTE.index("_ok, _pourquoi = _v393_ok(_ref, quantity)"))
GET = SRC[SRC.index('@api_router.get("/subscriber/space/{access_code}")'):SRC.index('@api_router.post("/subscriber/space/{access_code}/member/{member_slug}/block")')]
verifier("ecran. le GET de l'espace suit le canonique (miroir V531)", "_v531_valeurs(_lota)" in GET and "_v393_bloque = not _v531_valide" in GET)
PROMO = open(os.path.join(RACINE, "api", "routes", "promo_routes.py"), encoding="utf-8").read()
verifier("creation. POST /discount-codes refuse un code deja vivant (409)",
         "v531_fiche_vivante_existante(_db" in PROMO and "status_code=409" in PROMO[PROMO.index("v531_fiche_vivante_existante(_db"):PROMO.index("v531_fiche_vivante_existante(_db") + 600])

# ═════════════════════════════════ bilan ═════════════════════════════════════
ok = sum(1 for _, c, _ in RESULTATS if c)
for nom, cond, detail in RESULTATS:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + detail) if (detail and not cond) else ""))
print("\n%d/%d — V531 droits actifs (faux Mongo, 0 reseau, 0 donnee personnelle)" % (ok, len(RESULTATS)))
sys.exit(0 if ok == len(RESULTATS) else 1)

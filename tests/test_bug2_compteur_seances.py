# -*- coding: utf-8 -*-
"""COMPTEUR DE SEANCES — une seance ne peut plus etre comptee n'importe ou.

CE QUI ETAIT CASSE, mesure en production le 14/09/2026 : `discount_codes.used`
est un compteur LIBRE, ecrit par huit endroits, rattache a aucun evenement.
26 codes sur 57 avaient un `used` different du nombre de reservations portant
le code (`AFR-2287CA` : 7 annonces, 4 au registre).

DEUX DEFAUTS STRUCTURELS SONT FERMES, et ces bancs les tiennent :

  1. LA CIBLE — l'ecriture partait sur `update_one({"code": regex})`, donc la
     PREMIERE fiche venue. Plusieurs codes ont deux fiches (`BASSBOOSTX-02` :
     10 et 47 seances) : on debitait l'une et on affichait l'autre.
  2. LE PLAFOND — `$inc` ne connaissait aucune borne. `used` pouvait depasser
     `maxUses`, ce qu'aucun evenement reel ne justifie.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_bug2_compteur_seances.py
"""
import ast, asyncio, io, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC)
LIGNES = SRC.splitlines(True)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ═════════════════════════ faux Mongo minimal ════════════════════════════════
class _Tri:
    def __init__(self, docs):
        self._d = docs

    def sort(self, cle, sens):
        self._d = sorted(self._d, key=lambda d: (d.get(cle) or 0), reverse=(sens < 0))
        return self

    async def to_list(self, n=None):
        return [dict(x) for x in (self._d if n is None else self._d[:n])]


class Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, filtre=None, projection=None):
        def ok(d):
            for k, v in (filtre or {}).items():
                if isinstance(v, dict) and "$regex" in v:
                    if not re.match(v["$regex"], str(d.get(k) or ""), re.I):
                        return False
                elif d.get(k) != v:
                    return False
            return True
        return _Tri([d for d in self.docs if ok(d)])

    async def find_one_and_update(self, filtre, maj, projection=None, return_document=None):
        for d in self.docs:
            if d.get("id") != filtre.get("id"):
                continue
            # La seule condition que la production pose : used + q <= maxUses.
            _q = maj["$inc"]["used"]
            if int(d.get("used") or 0) + _q > int(d.get("maxUses") or 0):
                return None
            d["used"] = int(d.get("used") or 0) + _q
            return dict(d)
        return None


class Base:
    def __init__(self, fiches):
        self.discount_codes = Coll(fiches)


class _Log:
    def __init__(self):
        self.lignes = []

    def info(self, msg, *a):
        self.lignes.append(("info", msg % a if a else msg))

    def warning(self, msg, *a):
        self.lignes.append(("warn", msg % a if a else msg))


class _Retour:
    AFTER = "after"


def _source(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : " + nom)


def charger(fiches):
    base, journal = Base(fiches), _Log()
    env = {"re": re, "db": base, "logger": journal, "ReturnDocument": _Retour}
    exec(compile(_source("_bug2_consommer_seances"), "<prod>", "exec"), env)
    return env["_bug2_consommer_seances"], base, journal


def appel(fn, code, q):
    return asyncio.get_event_loop().run_until_complete(fn(code, q))


# ═══════════════ 1. Le plafond est porte par la requete elle-meme ════════════
fn, base, jrn = charger([{"id": "f1", "code": "PACK10", "maxUses": 10, "used": 9,
                          "stripe_amount": 150}])
r = appel(fn, "PACK10", 1)
verifier("la derniere seance passe", r["debite"] and r["used"] == 10, repr(r))
r = appel(fn, "PACK10", 1)
verifier("LE BUG : `used` ne peut plus depasser `maxUses`",
         (not r["debite"]) and r["motif"] == "plafond_atteint", repr(r))
verifier("le compteur n'a pas bouge apres le refus",
         base.discount_codes.docs[0]["used"] == 10)
verifier("le refus est journalise, pas avale",
         any("plafond" in m for _, m in jrn.lignes))

# Un debit groupe qui ne tient pas ENTIER est refuse entier : pas de moitie.
fn, base, _ = charger([{"id": "f1", "code": "PACK10", "maxUses": 10, "used": 8,
                        "stripe_amount": 150}])
r = appel(fn, "PACK10", 3)
verifier("un debit groupe trop grand est refuse en bloc",
         (not r["debite"]) and base.discount_codes.docs[0]["used"] == 8, repr(r))
r = appel(fn, "PACK10", 2)
verifier("le meme debit, s'il tient, passe", r["debite"] and r["used"] == 10, repr(r))

# ═══════════════ 2. La cible est DESIGNEE, plus « la premiere venue » ════════
fn, base, jrn = charger([
    {"id": "petite", "code": "BASSBOOSTX-02", "maxUses": 10, "used": 6, "stripe_amount": 0},
    {"id": "grande", "code": "BASSBOOSTX-02", "maxUses": 47, "used": 18, "stripe_amount": 470},
])
r = appel(fn, "BASSBOOSTX-02", 1)
_g = [d for d in base.discount_codes.docs if d["id"] == "grande"][0]
_p = [d for d in base.discount_codes.docs if d["id"] == "petite"][0]
verifier("code a deux fiches : on debite celle que l'ecran lit (stripe_amount max)",
         _g["used"] == 19 and _p["used"] == 6, "grande=%d petite=%d" % (_g["used"], _p["used"]))
verifier("l'ambiguite est DITE, pas tue",
         any("2 fiches" in m for _, m in jrn.lignes), repr(jrn.lignes))

# ═══════════════ 3. Les cas limites ne fabriquent aucune ecriture ════════════
fn, base, _ = charger([{"id": "f1", "code": "PACK10", "maxUses": 10, "used": 3,
                        "stripe_amount": 1}])
verifier("quantite nulle : rien", appel(fn, "PACK10", 0)["motif"] == "quantite_nulle")
verifier("quantite negative : rien", appel(fn, "PACK10", -5)["motif"] == "quantite_nulle")
verifier("code inconnu : rien, et on le dit",
         appel(fn, "CODE-INEXISTANT", 1)["motif"] == "code_absent")
verifier("aucun de ces cas n'a touche au compteur",
         base.discount_codes.docs[0]["used"] == 3)

# ═══════════════ 4. Le site de reservation passe bien par la regle ═══════════
_route = _source("bug2_reserve_course_from_space") if any(
    isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    and n.name == "bug2_reserve_course_from_space" for n in ast.walk(ARBRE)) else SRC
verifier("l'increment libre par regex a disparu du chemin de reservation",
         '{"$inc": {"used": quantity}}' not in SRC, "increment brut encore present")
verifier("la reservation depuis l'espace appelle la regle unique",
         "_bug2_consommer_seances(code_upper, quantity)" in SRC)

# ═══════════════ 5. L'audit existe, et il ne peut RIEN ecrire ════════════════
_audit = _source("bug2_audit_seances")
verifier("l'audit est reserve a l'administrateur",
         "is_super_admin(email)" in _audit and "403" in _audit)
for interdit in ("update_one", "update_many", "insert_one", "delete_one",
                 "delete_many", "$inc", "$set", "find_one_and_update"):
    verifier("l'audit n'ecrit pas (%s)" % interdit, interdit not in _audit)
verifier("l'audit compare au REGISTRE des reservations",
         "db.reservations.find" in _audit and "promoCode" in _audit
         and "discountCode" in _audit)
verifier("une reservation portant les deux champs ne compte qu'une fois",
         "setdefault" in _audit and "add(r.get(\"id\"))" in _audit)
verifier("l'audit signale les codes a fiches multiples",
         "codes_a_fiches_multiples" in _audit)

# ═══════ 6. La fonction resout SES noms toute seule (NameError en prod) ══════
# Piege paye le 14/09 : `ReturnDocument` n'est PAS importe au niveau du module
# de server.py — il l'est LOCALEMENT dans `_bt_debit_subscriber`. Les bancs
# ci-dessus l'injectent dans l'environnement, ce qui aurait masque un NameError
# a la premiere reservation en production. Ici, on charge la fonction SANS rien
# lui preter d'autre que `re`, `db` et `logger` : elle doit tourner quand meme.
_base_nue, _jrn_nu = Base([{"id": "f1", "code": "PACK10", "maxUses": 10,
                            "used": 0, "stripe_amount": 150}]), _Log()
_env_nu = {"re": re, "db": _base_nue, "logger": _jrn_nu}
exec(compile(_source("_bug2_consommer_seances"), "<prod>", "exec"), _env_nu)
try:
    _r_nu = appel(_env_nu["_bug2_consommer_seances"], "PACK10", 1)
    verifier("sans injection, la fonction importe elle-meme ReturnDocument",
             _r_nu["debite"] and _r_nu["used"] == 1, repr(_r_nu))
except NameError as e:
    verifier("sans injection, la fonction importe elle-meme ReturnDocument",
             False, "NameError : %s" % e)

# ════════════════════════════════ rapport ════════════════════════════════════
_ko = [r for r in RESULTATS if not r[1]]
for nom, ok, detail in RESULTATS:
    print(("  OK   " if ok else "  ECHEC") + " " + nom + ("" if ok else "  <- " + detail))
print("\n%d/%d" % (len(RESULTATS) - len(_ko), len(RESULTATS)))
sys.exit(1 if _ko else 0)

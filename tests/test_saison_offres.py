# -*- coding: utf-8 -*-
"""SAISON — offres saisonnières et saison active, sans base réelle.

  * une offre SANS champ `season` est permanente : jamais cachée ;
  * saison active `toutes` (défaut, donc à la livraison) : rien ne change ;
  * `hiver` actif : les offres `ete` se cachent, `hiver` + permanentes restent ;
  * valeurs inconnues -> `toutes` ; alias été/summer/winter acceptés ;
  * GET /api/offers (public) applique le filtre + la rareté réelle (stock − ventes) ;
    `scope=mine` (tableau de bord) ne filtre JAMAIS ;
  * PUT /api/offers sans `season` garde la saison stockée (piège audience évité).

    python3 tests/test_saison_offres.py
"""
import ast, asyncio, os, sys, types
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
from api.routes import saison as S

R = []
def v(nom, cond, detail=""): R.append((nom, bool(cond), detail))

# ── module pur ──
v("valide : toutes/hiver/ete + alias", [S.saison_valide(x) for x in ("hiver", "ETE", "été", "summer", "winter", "all", "", None, "printemps")]
  == ["hiver", "ete", "ete", "ete", "hiver", "toutes", "toutes", "toutes", "toutes"])
v("offre sans champ = permanente, visible quelle que soit la saison", all(S.offre_visible_en_saison({"name": "x"}, sa) for sa in S.SAISONS))
v("saison active toutes : tout visible", all(S.offre_visible_en_saison({"season": sn}, "toutes") for sn in S.SAISONS))
v("hiver actif : ete cachée, hiver visible, toutes visible",
  [S.offre_visible_en_saison({"season": sn}, "hiver") for sn in ("ete", "hiver", "toutes")] == [False, True, True])
v("ete actif : hiver cachée", S.offre_visible_en_saison({"season": "hiver"}, "ete") is False and S.offre_visible_en_saison({"season": "ete"}, "ete"))
v("valeur inconnue sur l'offre = permanente (jamais cachée par accident)", S.offre_visible_en_saison({"season": "n_importe"}, "hiver"))
v("filtrer_offres_saison garde l'ordre", [o["n"] for o in S.filtrer_offres_saison([{"n": 1, "season": "ete"}, {"n": 2}, {"n": 3, "season": "hiver"}], "hiver")] == [2, 3])

# ── routes : extraction par nom depuis server.py, faux Mongo ──
SRC = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
ARBRE = ast.parse(SRC); LIGNES = SRC.splitlines(keepends=True)

def _src(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno]).replace("\n@api_router", "\n#")
    raise KeyError(nom)

def _const(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise KeyError(nom)

def _corr(d, f):
    for k, c in (f or {}).items():
        if isinstance(c, dict) and "$ne" in c:
            if d.get(k) == c["$ne"]: return False
        elif isinstance(c, dict) and "$in" in c:
            if d.get(k) not in c["$in"]: return False
        elif d.get(k) != c: return False
    return True

class _Cur:
    def __init__(self, d): self.d = d
    async def to_list(self, n=None): return [dict(x) for x in self.d]

class Coll:
    def __init__(self, docs=None): self.docs = docs or []; self.ecrits = []
    def find(self, f=None, p=None): return _Cur([d for d in self.docs if _corr(d, f)])
    async def find_one(self, f=None, p=None):
        for d in self.docs:
            if _corr(d, f): return dict(d)
        return None
    async def insert_many(self, docs): self.docs.extend(docs)
    async def update_one(self, f, u, upsert=False):
        self.ecrits.append((f, u))
        for d in self.docs:
            if _corr(d, f): d.update(u.get("$set", {})); return
        if upsert: self.docs.append(dict(f, **u.get("$set", {})))
    def aggregate(self, pipeline):
        _m = pipeline[0]["$match"]; _ids = set(_m["offer_id"]["$in"]); _n = {}
        for d in self.docs:
            if d.get("offer_id") in _ids and d.get("status") != "superseded":
                _n[d["offer_id"]] = _n.get(d["offer_id"], 0) + 1
        return _Cur([{"_id": k, "n": n} for k, n in _n.items()])

class Base:
    def __init__(self):
        self.offers = Coll([
            {"id": "a", "name": "Ancienne sans saison", "price": 30, "visible": True, "coach_id": "c@x", "stock": -1},
            {"id": "h", "name": "Hiver", "price": 59, "visible": True, "season": "hiver", "coach_id": "c@x", "stock": 50, "offer_type": "subscription"},
            {"id": "e", "name": "Pulse été", "price": 250, "visible": True, "season": "ete", "coach_id": "c@x", "stock": -1},
            {"id": "x", "name": "Cachée", "price": 10, "visible": False, "season": "hiver", "coach_id": "c@x"},
            {"id": "p", "name": "Produit", "price": 20, "visible": True, "isProduct": True, "stock": 0},
        ])
        self.platform_settings = Coll([{"_id": "global", "saison_active": "hiver"}])
        self.subscriptions = Coll([{"offer_id": "h", "status": "active"}, {"offer_id": "h", "status": "superseded"}])

class _Log:
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass

def _ns(db):
    ns = {"db": db, "logger": _Log(), "List": list, "Optional": __import__("typing").Optional, "Request": object,
          "_saison_valide": S.saison_valide, "_filtrer_saison": S.filtrer_offres_saison, "_SAISON_DEFAUT": S.SAISON_DEFAUT,
          "uuid": __import__("uuid"), "SUPER_ADMIN_EMAILS": ["admin@x"], "is_super_admin": lambda e: e == "admin@x",
          "r2b_offre_publique": lambda o: o, "_enrich_offers_with_active_price": lambda o: o, "datetime": __import__("datetime").datetime, "timezone": __import__("datetime").timezone}
    async def _same(o): return o
    ns["_enrich_offers_with_next_date"] = _same
    # HIVER 2 : /api/offers retire les offres limitées fermées (épuisées / date passée).
    from api.routes import hiver as _H
    ns["_hiver"] = _H
    for nom in ("_saison_active", "_annoter_places_restantes", "_offres_encore_disponibles", "get_offers"):
        exec(compile(_src(nom), nom, "exec"), ns)
    return ns

class _Req:
    def __init__(self, email=""): self.headers = {"x-user-email": email}

async def _go():
    db = Base(); ns = _ns(db)
    pub = await ns["get_offers"](_Req(), "")
    v("GET /offers public, hiver actif : permanente + hiver ; été cachée ; invisible cachée ; produit stock 0 = produit (non concerné)",
      sorted(o["id"] for o in pub) == ["a", "h", "p"], sorted(o["id"] for o in pub))
    v("places restantes RÉELLES sur l'offre limitée : 50 − 1 (la superseded ne compte pas) = 49",
      next(o for o in pub if o["id"] == "h").get("places_restantes") == 49)
    v("offre sans stock : aucune place annotée", "places_restantes" not in next(o for o in pub if o["id"] == "a"))
    mine = await ns["get_offers"](_Req("admin@x"), "mine")
    v("scope=mine (tableau de bord) : TOUT, saison ignorée (5 offres)", len(mine) == 5)
    db.platform_settings.docs = [{"_id": "global", "saison_active": "toutes"}]
    v("saison toutes : tout le visible, été comprise", sorted(o["id"] for o in await ns["get_offers"](_Req(), "")) == ["a", "e", "h", "p"])
    db.platform_settings.docs = []
    v("aucun réglage en base = toutes (rien ne change à la livraison)", sorted(o["id"] for o in await ns["get_offers"](_Req(), "")) == ["a", "e", "h", "p"])
    db.platform_settings.docs = [{"_id": "global", "saison_active": "hiver"}]
    db.subscriptions.docs = [{"offer_id": "h", "status": "active"} for _ in range(50)]
    v("50 ventes réelles : l'offre limitée disparaît de la vitrine", "h" not in [o["id"] for o in await ns["get_offers"](_Req(), "")])
    db.subscriptions.aggregate = lambda p: (_ for _ in ()).throw(RuntimeError("panne"))
    v("panne du compteur : l'offre reste visible, sans place affichée (fail-open, aucune vente bloquée)",
      "h" in [o["id"] for o in await ns["get_offers"](_Req(), "")])

asyncio.run(_go())

# ── PUT garde la saison stockée quand le client ne l'envoie pas ──
src_put = _src("update_offer")
v("PUT /offers : la saison stockée est conservée si `offer.season is None` (client ancien)",
  "offer.season if offer.season is not None else _offre_avant.get(\"season\")" in src_put)
v("OfferCreate.season est None par défaut (« non fourni »), Offer.season vaut « toutes »",
  "season: Optional[str] = None" in _src("OfferCreate") and 'season: Optional[str] = "toutes"' in _src("Offer"))
src_ps = _src("update_platform_settings")
v("PUT /platform-settings accepte saison_active (super-admin) et la normalise", "saison_active" in src_ps and "_saison_valide(data[\"saison_active\"]" in src_ps)
v("GET /platform-settings renvoie saison_active", "saison_active" in _src("get_platform_settings"))
v("champs publics : pack_sessions, season, places_restantes exposés — aucun champ personnel ajouté",
  all(x in _const("R2B_CLES_OFFRE_PUBLIQUE") for x in ('"pack_sessions"', '"season"', '"places_restantes"')) and '"coach_id"' not in _const("R2B_CLES_OFFRE_PUBLIQUE"))

ok = sum(1 for _, c, _ in R if c)
for nom, cond, detail in R:
    print("  %s  %s%s" % ("OK  " if cond else "ECHEC", nom, ("  <- " + str(detail)) if (detail and not cond) else ""))
print("\n%d/%d" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)

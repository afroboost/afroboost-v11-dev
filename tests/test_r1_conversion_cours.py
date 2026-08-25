# -*- coding: utf-8 -*-
"""R1 — UN ACHAT DE PRODUIT PHYSIQUE N'EST PAS UNE CONVERSION DE COURS.

LE DEFAUT QUE CE LOT FERME. `essai2_marquer_conversion` juge QUI achete et
QUAND, jamais QUOI : ses trois conditions sont « un forfait d'essai existe »,
« une presence est validee », « `converted_at` est absent ». Le contenu du
panier n'entre nulle part. Un t-shirt paye posait donc `converted_at`, FERMAIT
l'ecran d'apres-essai (P1-c) et eteignait la relance J+3 (P1-d) — alors que
l'acheteur n'est pas entre dans la pratique.

LA REGLE DU PROPRIETAIRE, arretee le 25/08/2026 :
  Conversion = OUI si AU MOINS UNE LIGNE PAYEE de l'achat correspond
  reellement a une offre de cours / pratique.
  * PULSE 250, cours a l'unite, recharge 150      -> OUI
  * t-shirt seul, meme « + 1 cours offert »       -> NON
  * panier mixte t-shirt + vrai cours paye        -> OUI
  * checkout abandonne, transaction echouee       -> NON
  Une seance OFFERTE par un produit ne suffit JAMAIS : c'est la nature de la
  LIGNE PAYEE qui classe, pas le fait que des seances soient accordees.

TROIS DEFAUTS FERMES ENSEMBLE :
  R1-a  la nature de l'article n'etait pas regardee ;
  R1-b  le webhook Stripe « client » appelait ESSAI-2 SANS garde de montant,
        la ou la caisse en avait une (`total > 0` et `payment_method != free`) ;
  R1-c  seul le PREMIER article du panier etait retenu (`items_offer_id`), donc
        « t-shirt + PULSE » se classait sur le t-shirt.

CE QUE CE BANC NE TOUCHE PAS : `conv_etat` (P1-c), le funnel ESSAI-3 et P1-d
gardent leur code. Ils sont verifies ICI en non-regression.

AUCUN RESEAU, AUCUNE BASE REELLE, AUCUN PAIEMENT.
    python3 tests/test_r1_conversion_cours.py
"""
import ast, asyncio, io, os, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def _lire(chemin):
    src = io.open(os.path.join(RACINE, *chemin), encoding="utf-8").read()
    arbre = ast.parse(src)
    fns, csts = {}, {}
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fns.setdefault(n.name, ast.get_source_segment(src, n))
    for n in arbre.body:
        if isinstance(n, ast.Assign):
            for c in n.targets:
                if isinstance(c, ast.Name):
                    csts.setdefault(c.id, ast.get_source_segment(src, n))
    return src, fns, csts


SRC_SH, FN_SH, CST_SH = _lire(("api", "routes", "shared.py"))
SRC_CK, FN_CK, CST_CK = _lire(("api", "routes", "checkout_routes.py"))
SRC_SRV, FN_SRV, CST_SRV = _lire(("api", "server.py"))


# ───────────────────────── faux Mongo, minimal et fidele ────────────────────
def _valeur(doc, cle):
    val = doc
    for part in cle.split("."):
        val = (val or {}).get(part) if isinstance(val, dict) else None
    return val


def _match(doc, filtre):
    for cle, cond in (filtre or {}).items():
        if cle == "$or":
            if not any(_match(doc, sous) for sous in (cond or [])):
                return False
            continue
        val = _valeur(doc, cle)
        if isinstance(cond, dict):
            for op, ref in cond.items():
                if op == "$exists":
                    if (val is not None) != ref:
                        return False
                elif op == "$ne":
                    if val == ref:
                        return False
                elif op == "$in":
                    if val not in ref:
                        return False
                else:
                    raise AssertionError("operateur non simule : %s" % op)
        elif val != cond:
            return False
    return True


class _Maj:
    def __init__(self, n): self.matched_count = n; self.modified_count = n


class _Curseur:
    def __init__(self, rows): self._rows = rows

    async def to_list(self, n=None):
        return [dict(r) for r in (self._rows if n is None else self._rows[:n])]


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    async def find_one(self, filtre=None, proj=None):
        for d in self.docs:
            if _match(d, filtre or {}):
                return dict(d)
        return None

    def find(self, filtre=None, proj=None):
        return _Curseur([d for d in self.docs if _match(d, filtre or {})])

    async def update_one(self, filtre, maj, upsert=False):
        for d in self.docs:
            if _match(d, filtre):
                for cle, val in (maj.get("$set") or {}).items():
                    cible, parts = d, cle.split(".")
                    for p in parts[:-1]:
                        cible = cible.setdefault(p, {})
                    cible[parts[-1]] = val
                return _Maj(1)
        return _Maj(0)


class _Base:
    def __init__(self, **cols):
        self._c = {n: _Coll(v) for n, v in cols.items()}

    def __getitem__(self, n): return self._c.setdefault(n, _Coll())

    def __getattr__(self, n):
        if n.startswith("_"):
            raise AttributeError(n)
        return self[n]


JOURNAL = []


class _Journal:
    def _n(self, m, *a):
        try:
            JOURNAL.append(str(m) % a if a else str(m))
        except Exception:
            JOURNAL.append(str(m))
    info = warning = error = debug = _n


# ───────────────────────────── le catalogue du banc ─────────────────────────
OFFRES = [
    {"id": "off-pulse", "name": "PULSE x10 cours", "isProduct": False, "price": 250.0},
    {"id": "off-unite", "name": "Cours a l'unite", "isProduct": False, "price": 30.0},
    {"id": "off-membres", "name": "Membres", "isProduct": False, "price": 150.0},
    # Le vrai t-shirt de production : il ACCORDE une seance, et il reste un produit.
    {"id": "off-tshirt", "name": "T-shirt + 1 cours offert!", "isProduct": True,
     "price": 59.99, "category": "tshirt"},
    {"id": "off-chaussures", "name": "Chaussures", "isProduct": True, "price": 120.0},
    {"id": "off-essai", "name": "Cours d'essai GRATUIT", "isProduct": False, "price": 0.0},
]

ANA = "ana@exemple.ch"


def base_essai(converti=False):
    """Un essai HONORE : forfait gratuit + presence validee."""
    _f = {"id": "s-essai", "code": "AFR-ESSAI1", "email": ANA,
          "offer_id": "off-essai", "created_at": "2026-09-01T09:00:00+00:00"}
    if converti:
        _f["converted_at"] = "2026-09-02T10:00:00+00:00"
    return _Base(
        offers=OFFRES,
        subscriptions=[_f],
        discount_codes=[{"code": "AFR-ESSAI1", "assignedEmail": ANA,
                         "payment_method": "free", "total_paid": 0}],
        reservations=[{"id": "r-1", "validated": True, "promoCode": "AFR-ESSAI1",
                       "validatedAt": "2026-09-01T16:30:00+00:00",
                       "userEmail": ANA, "courseId": "c-1"}],
    )


def charger_shared(db):
    """Les VRAIES fonctions ESSAI-2 de shared.py, avec un decor controle."""
    from datetime import datetime, timezone
    esp = {"__builtins__": __builtins__, "logger": _Journal(),
           "datetime": datetime, "timezone": timezone, "asyncio": asyncio}

    async def _capture(*a, **k):
        return None
    esp["posthog_capture"] = _capture

    for c in ("ESSAI2_FILTRE_GRATUIT", "ESSAI2_CHAMP_PRODUIT"):
        exec(compile(CST_SH[c], "<cst>", "exec"), esp)
    for fn in ("normaliser_email", "essai2_codes_essai", "essai2_forfait_essai",
               "essai2_presence_essai", "essai2_marquer_conversion",
               # ── les fonctions R1, celles que ce lot ajoute ──
               "essai2_nature_est_un_cours", "essai2_prix_catalogue",
               "essai2_lire_offre", "essai2_offre_est_un_cours",
               "essai2_achat_convertit", "essai2_convertir_si_achat_de_cours"):
        if fn not in FN_SH:
            raise AssertionError("fonction absente de shared.py : %s" % fn)
        exec(compile(FN_SH[fn], "<sh>", "exec"), esp)
    esp["db"] = db
    return esp


async def scenarios():
    # ══ LA NATURE D'UNE OFFRE ═══════════════════════════════════════════════
    b = base_essai()
    sh = charger_shared(b)
    _nature = sh["essai2_offre_est_un_cours"]
    for oid, attendu, libelle in (
            ("off-pulse", True, "PULSE x10"),
            ("off-unite", True, "cours a l'unite"),
            ("off-membres", True, "recharge membre"),
            ("off-tshirt", False, "t-shirt + 1 cours offert"),
            ("off-chaussures", False, "chaussures"),
            ("off-introuvable", None, "offre introuvable"),
            ("", None, "identifiant vide")):
        _r = await _nature(b, oid)
        verifier("NATURE. %s -> %s" % (libelle, attendu), _r is attendu, _r)

    # ══ LA REGLE DU PANIER ══════════════════════════════════════════════════
    _panier = sh["essai2_achat_convertit"]
    for lignes, attendu, libelle in (
            (["off-pulse"], True, "PULSE 250 seul"),
            (["off-unite"], True, "cours a l'unite seul"),
            (["off-membres"], True, "recharge 150 seule"),
            (["off-tshirt"], False, "t-shirt seul (avec seance offerte)"),
            (["off-chaussures"], False, "chaussures seules"),
            (["off-tshirt", "off-chaussures"], False, "deux produits physiques"),
            # R1-c : le panier mixte, DANS LES DEUX ORDRES
            (["off-tshirt", "off-pulse"], True, "MIXTE t-shirt PUIS PULSE"),
            (["off-pulse", "off-tshirt"], True, "MIXTE PULSE PUIS t-shirt"),
            # Une ligne de cours NON PAYEE ne convertit pas : c'est la ligne
            # PAYEE qui classe.
            (["off-tshirt", "off-essai"], False, "t-shirt + cours a 0 CHF"),
            (["off-essai"], False, "cours a 0 CHF seul"),
            # Fail-closed : illisible -> on NE relance PAS quelqu'un qui a paye.
            (["off-introuvable"], True, "offre illisible -> conversion (fail-closed)"),
            ([], True, "panier sans identifiant -> conversion (fail-closed)")):
        _r = await _panier(b, lignes)
        verifier("PANIER. %s -> %s" % (libelle, attendu), _r is attendu, _r)

    # ══ LA PORTE UNIQUE DES DEUX CHEMINS D'AUTORITE ═════════════════════════
    _porte = sh["essai2_convertir_si_achat_de_cours"]

    # A/B/C/D — un vrai cours paye convertit
    for lignes, libelle in ((["off-pulse"], "PULSE 250"),
                            (["off-unite"], "cours a l'unite"),
                            (["off-membres"], "recharge 150"),
                            (["off-tshirt", "off-pulse"], "panier mixte")):
        b = base_essai(); sh = charger_shared(b)
        _r = await sh["essai2_convertir_si_achat_de_cours"](
            b, ANA, 250.0, "card", lignes, "s-achat")
        verifier("PORTE. %s -> conversion actee" % libelle, _r is True, _r)
        verifier("PORTE. %s -> converted_at pose" % libelle,
                 bool(b.subscriptions.docs[0].get("converted_at")))

    # E — t-shirt seul : PAYE, mais aucune conversion et AUCUNE ecriture
    b = base_essai(); sh = charger_shared(b)
    _r = await sh["essai2_convertir_si_achat_de_cours"](
        b, ANA, 59.99, "card", ["off-tshirt"], "s-achat")
    verifier("PORTE-E. t-shirt seul -> AUCUNE conversion", _r is False, _r)
    verifier("PORTE-E2. `converted_at` reste ABSENT",
             "converted_at" not in b.subscriptions.docs[0],
             b.subscriptions.docs[0].get("converted_at"))

    # R1-b — la garde de montant, sur la porte commune
    b = base_essai(); sh = charger_shared(b)
    _r = await sh["essai2_convertir_si_achat_de_cours"](
        b, ANA, 0, "card", ["off-pulse"], "s-achat")
    verifier("PORTE-F. montant nul -> aucune conversion", _r is False, _r)
    verifier("PORTE-F2. `converted_at` reste ABSENT",
             "converted_at" not in b.subscriptions.docs[0])
    b = base_essai(); sh = charger_shared(b)
    _r = await sh["essai2_convertir_si_achat_de_cours"](
        b, ANA, 250.0, "free", ["off-pulse"], "s-achat")
    verifier("PORTE-G. moyen « free » -> aucune conversion", _r is False, _r)

    # Idempotence : un second achat ne reconvertit pas
    b = base_essai(); sh = charger_shared(b)
    _1 = await sh["essai2_convertir_si_achat_de_cours"](b, ANA, 250.0, "card", ["off-pulse"], "s1")
    _2 = await sh["essai2_convertir_si_achat_de_cours"](b, ANA, 30.0, "card", ["off-unite"], "s2")
    verifier("PORTE-H. premier achat convertit", _1 is True, _1)
    verifier("PORTE-H2. second achat ne reconvertit pas", _2 is False, _2)

    # ══ R1-c : LA CAISSE PASSE TOUTES LES LIGNES, PAS LA PREMIERE ═══════════
    _src_caisse = FN_CK["_essai2_convertir_si_paye"]
    verifier("R1-c. la caisse accepte les ARTICLES du panier",
             "items" in _src_caisse, _src_caisse[:200])
    verifier("R1-c2. la caisse delegue a la porte commune",
             "essai2_convertir_si_achat_de_cours" in _src_caisse)
    _appel = [l for l in SRC_CK.splitlines()
              if "_essai2_convertir_si_paye(" in l and "async def" not in l]
    verifier("R1-c3. l'appelant transmet bien `items`",
             any("items" in l for l in _appel) or
             any("items" in SRC_CK.split("_essai2_convertir_si_paye(")[1][:200]
                 for _ in [0]),
             _appel)

    # ══ R1-b : LE WEBHOOK STRIPE « CLIENT » A DESORMAIS SA GARDE ════════════
    _i = SRC_SRV.find("# ESSAI-2 : cet achat convertit-il un essai deja HONORE ?")
    verifier("R1-b. le bloc ESSAI-2 du webhook client existe", _i > 0)
    _bloc = SRC_SRV[_i:_i + 1400]
    verifier("R1-b2. il passe par la porte commune",
             "essai2_convertir_si_achat_de_cours" in _bloc, _bloc[:300])
    verifier("R1-b3. il transmet un MONTANT (garde qui lui manquait)",
             "amount_chf" in _bloc or "_montant_paye" in _bloc, _bloc[:300])
    # On vise l'IMPORT reel, pas la prose : le commentaire du bloc cite la
    # fonction pour expliquer ce qui a change, et c'est voulu.
    verifier("R1-b4. il n'importe plus `essai2_marquer_conversion` en direct",
             "essai2_marquer_conversion as" not in _bloc, _bloc[:300])

    # ══ NON-REGRESSION — CE QUE R1 NE DOIT PAS CASSER ═══════════════════════
    # P1-c : apres un t-shirt seul, l'ecran reste OUVERT
    b = base_essai(); sh = charger_shared(b)
    await sh["essai2_convertir_si_achat_de_cours"](b, ANA, 59.99, "card", ["off-tshirt"], "s-t")
    verifier("NR-P1c. t-shirt seul -> le forfait d'essai n'est PAS marque converti",
             "converted_at" not in b.subscriptions.docs[0])
    # ... et apres un vrai cours, il se ferme (comportement d'avant, intact)
    b = base_essai(); sh = charger_shared(b)
    await sh["essai2_convertir_si_achat_de_cours"](b, ANA, 250.0, "card", ["off-pulse"], "s-p")
    verifier("NR-P1c2. PULSE -> le forfait EST marque converti",
             bool(b.subscriptions.docs[0].get("converted_at")))
    # ESSAI-2 : la fonction de marquage n'a pas change de regle
    verifier("NR-E2. `essai2_marquer_conversion` exige toujours une presence",
             "essai2_presence_essai" in FN_SH["essai2_marquer_conversion"])
    verifier("NR-E2b. ... et reste atomique sur `converted_at`",
             '"converted_at": {"$exists": False}' in FN_SH["essai2_marquer_conversion"])
    verifier("NR-E2c. ... et ne juge toujours PAS la nature de l'achat",
             "isProduct" not in FN_SH["essai2_marquer_conversion"])
    # P1-d : la regle nature est UNIQUE dans le depot
    verifier("NR-P1d. `p1d_offre_est_un_cours` delegue a la regle commune",
             "essai2_offre_est_un_cours" in FN_SRV.get("p1d_offre_est_un_cours", ""),
             FN_SRV.get("p1d_offre_est_un_cours", "(absente)")[:200])
    # Le funnel ESSAI-3 n'est pas touche
    verifier("NR-E3. le funnel ESSAI-3 lit toujours `converted_at`, inchange",
             "converted_at" in SRC_SRV[SRC_SRV.find("ESSAI3_CONVERSION_DEPUIS"):
                                       SRC_SRV.find("ESSAI3_CONVERSION_DEPUIS") + 6000])


def main():
    asyncio.run(scenarios())
    ok = sum(1 for _, c, _ in RESULTATS if c)
    for nom, cond, detail in RESULTATS:
        print(("  OK   " if cond else "  ECHEC") + "  " + nom
              + ("" if cond else "   -> %s" % (detail,)))
    print("\n=== R1 : %d/%d ===" % (ok, len(RESULTATS)))
    print("Achats REELS : 0 — base en memoire, aucun reseau, aucun paiement.")
    sys.exit(0 if ok == len(RESULTATS) else 1)


if __name__ == "__main__":
    main()

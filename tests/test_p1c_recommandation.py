# -*- coding: utf-8 -*-
"""P1-c — UNE offre recommandee, et des alternatives. Pas un catalogue a plat.

CE LOT N'INVENTE AUCUN MOTEUR. Il branche entre elles trois regles qui
existent deja et qui sont deja prouvees ailleurs :
  * LOT A  — `conv_offres_premier_achat` : qui a le droit d'etre propose ;
  * LOT R  — `lotr_verdict_recharge` : qui a le droit d'ACHETER une recharge ;
  * LOT 2  — `lot2_adhesion_active` : cette personne est-elle deja membre.

CE QU'IL AJOUTE, ET RIEN D'AUTRE :
  1. l'ecran ne propose plus ce que la CAISSE refuserait (403 LOT R) ;
  2. l'offre d'ENTREE n'est plus proposee a qui est deja membre — le serveur
     refuse deja de creer une seconde adhesion en aval (`motif=deja_membre`),
     l'ecran cesse simplement de mentir ;
  3. la RECOMMANDATION est l'offre d'entree, pas la premiere de la vitrine.

     POURQUOI CE CHANGEMENT. `recommended` valait `i == 0` apres tri par
     `offers.position` — or `position` est l'ordre de la VITRINE, ou « Cours a
     l'unite » est legitimement en tete parce que c'est le moins cher. Mesure
     de production du 24/08/2026 : l'ecran d'apres-essai recommandait donc
     « Cours a l'unite » (position 1) et releguait PULSE (position 4).
     Apres un essai, la suite naturelle est l'ENTREE dans le programme.

     LA REGLE DE REPLI EST L'ANCIENNE, INTACTE : sans offre d'entree, c'est
     `position` qui decide, exactement comme avant. Et si DEUX offres d'entree
     coexistent, on ne tranche pas : aucune recommandation, juste les options.
     « Ne jamais inventer une recommandation. »

Aucun reseau. Aucune vraie base. Aucune ecriture.

Lancement :  python3 tests/test_p1c_recommandation.py
"""

import asyncio
import importlib
import io
import os
import sys
import types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
# Paquets stub a `__path__` reel : les sous-modules se chargent VRAIMENT, sans
# executer `api/routes/__init__.py` (qui importe Stripe & toute l'application).
for _n, _c in (("api", RACINE + "/api"), ("api.routes", RACINE + "/api/routes")):
    _m = types.ModuleType(_n); _m.__path__ = [_c]; sys.modules[_n] = _m
SH = importlib.import_module("api.routes.shared")

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


# ----------------------------------------------------------- fausse base
class _Curseur:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, n):
        return [dict(r) for r in self._rows[:n]]


class _Col:
    def __init__(self, rows):
        self.rows = rows

    def _match(self, doc, q):
        for cle, att in (q or {}).items():
            if cle == "$or":
                if not any(self._match(doc, o) for o in att):
                    return False
                continue
            val = doc.get(cle)
            if isinstance(att, dict):
                if "$exists" in att and (cle in doc) != bool(att["$exists"]):
                    return False
                if "$regex" in att:
                    import re as _re
                    if not _re.match(att["$regex"], str(val or ""),
                                     _re.I if "i" in att.get("$options", "") else 0):
                        return False
                if "$gt" in att and not (val is not None and val > att["$gt"]):
                    return False
            elif val != att:
                return False
        return True

    def find(self, q=None, proj=None):
        return _Curseur([r for r in self.rows if self._match(r, q or {})])

    async def find_one(self, q=None, proj=None):
        for r in self.rows:
            if self._match(r, q or {}):
                return dict(r)
        return None


class _Db:
    def __init__(self, **cols):
        self._c = {k: _Col(v) for k, v in cols.items()}

    def __getitem__(self, k):
        return self._c.setdefault(k, _Col([]))

    def __getattr__(self, k):
        return self[k]


# ----------------------------------------------------------- le catalogue reel
def offre(oid, nom, prix, position, premier_achat=True, entree=False,
          recharge=False, coach=None):
    d = {"id": oid, "name": nom, "price": prix, "position": position,
         "first_purchase_eligible": premier_achat, "coach_id": coach}
    if entree:
        d["creates_membership"] = True
    if recharge:
        d[SH.LOTR_CHAMP_PROTECTION] = True
    return d


# Le catalogue de PRODUCTION, mesure le 24/08/2026.
UNITE = offre("fea0ab6a", "Cours à l'unité", 30.0, 1)
PULSE = offre("a687ce86", "PULSE x10 cours", 250.0, 4, entree=True)
TSHIRT = offre("84b7d8c6", "T-shirt + 1 cours offert!", 59.99, 6, premier_achat=False)
ESSAI = offre("c1e5f73c", "🎁 Cours d'essai GRATUIT", 0.0, 0, premier_achat=False)
MEMBRES = offre("484c4519", "Membres", 150.0, 5, premier_achat=False, recharge=True)
CATALOGUE = [UNITE, PULSE, TSHIRT, ESSAI, MEMBRES]

AUJ = SH.p1a_jour_suisse() if hasattr(SH, "p1a_jour_suisse") else "2026-08-24"


def adhesion(email, debut, fin, coach=None):
    return {"id": "adh-1", "email": email, "date_debut": debut, "date_fin": fin,
            "coach_id": coach}


def forfait(email, restant, expire=None):
    return {"id": "sub-1", "email": email, "status": "active",
            "remaining_sessions": restant, "expires_at": expire}


async def offres(catalogue=None, email="", coach_id="", adhesions=None, forfaits=None):
    db = _Db(offers=list(catalogue if catalogue is not None else CATALOGUE),
             memberships=list(adhesions or []),
             subscriptions=list(forfaits or []))
    return await SH.conv_offres_premier_achat(db, coach_id, email)


def noms(res):
    return [o["name"] for o in res]


def reco(res):
    r = [o["name"] for o in res if o.get("recommended")]
    return r[0] if len(r) == 1 else (None if not r else r)


def main():
    B = asyncio.get_event_loop().run_until_complete

    # --- A / B : nouveau participant, aucun historique -------------------
    r = B(offres(email="neuf@example.org"))
    verifier("A. essai consomme, participant NOUVEAU -> PULSE 250 recommande",
             reco(r) == "PULSE x10 cours", "%s | reco=%r" % (noms(r), reco(r)))
    verifier("B. « Cours à l'unité » reste visible comme ALTERNATIVE",
             "Cours à l'unité" in noms(r)
             and not [o for o in r if o["name"] == "Cours à l'unité"][0]["recommended"],
             noms(r))
    verifier("B2. exactement DEUX offres, comme en production", len(r) == 2, noms(r))

    # --- C : l'essai gratuit n'est jamais reproposé -----------------------
    verifier("C. l'essai gratuit qu'il vient de consommer est ABSENT",
             "🎁 Cours d'essai GRATUIT" not in noms(r), noms(r))
    verifier("C2. aucune offre a 0 CHF, quelle qu'elle soit",
             all((o.get("price") or 0) > 0 for o in r), r)

    # --- D / E : ce qui n'est pas declare n'existe pas --------------------
    verifier("D. une offre non declaree « apres essai » est ABSENTE",
             "T-shirt + 1 cours offert!" not in noms(r), noms(r))
    # La seule occurrence de `linked_course_ids` dans shared.py est un
    # COMMENTAIRE (l. 1453) qui explique justement qu'on ne s'en sert pas. On
    # verifie donc le CODE EXECUTE des fonctions de selection, pas le texte brut.
    import ast as _ast
    _src = io.open(os.path.join(RACINE, "api", "routes", "shared.py"),
                   encoding="utf-8").read()
    _arb = _ast.parse(_src)
    _nu = []
    for _n in _ast.walk(_arb):
        if isinstance(_n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and (
                _n.name.startswith("conv_") or _n.name.startswith("p1c_")):
            _corps = list(_n.body)
            if (_corps and isinstance(_corps[0], _ast.Expr)
                    and isinstance(getattr(_corps[0], "value", None), _ast.Constant)):
                _corps = _corps[1:]
            _nu.append("\n".join(_ast.unparse(_x) for _x in _corps))
    _nu = "\n".join(_nu)
    verifier("E. la selection ne depend PAS du cours de l'essai — c'est le "
             "drapeau du coach qui decide, et lui seul",
             "linked_course_ids" not in _nu and "courseId" not in _nu,
             "le cours de l'essai n'entre pas dans la selection")
    verifier("E2. aucun montant en dur dans la regle P1-c",
             not any(m in _nu for m in ("250", "150", " 30", "29.", "99.")), _nu[:200])

    # --- F : une seule recommandation ------------------------------------
    verifier("F0. la recommandee est EN TETE — l'ecran n'a rien a chercher",
             r[0]["recommended"] is True and r[0]["name"] == "PULSE x10 cours",
             [(o["name"], o["recommended"]) for o in r])
    verifier("F0b. le reste garde l'ordre `position`",
             [o["name"] for o in r[1:]] == ["Cours à l'unité"], noms(r))
    verifier("F. UNE SEULE offre porte `recommended`",
             len([o for o in r if o.get("recommended")]) == 1, r)

    # --- G : on ne tranche pas dans le doute ------------------------------
    _deux = [UNITE, PULSE, offre("x", "PULSE Duo", 400.0, 2, entree=True)]
    r_g = B(offres(_deux, email="neuf@example.org"))
    verifier("G. DEUX offres d'entree -> AUCUNE recommandation inventee, "
             "juste les options",
             len(r_g) == 3 and not any(o.get("recommended") for o in r_g),
             [(o["name"], o["recommended"]) for o in r_g])
    _sans = [UNITE, offre("y", "Carte 5", 120.0, 3)]
    r_s = B(offres(_sans, email="neuf@example.org"))
    verifier("G2. AUCUNE offre d'entree -> l'ancienne regle (`position`) "
             "s'applique, intacte",
             reco(r_s) == "Cours à l'unité", [(o["name"], o["recommended"]) for o in r_s])

    # --- H : membre actif, pack epuise -----------------------------------
    MEMBRE = "membre@example.org"
    _cat_h = [UNITE, PULSE, offre("484c4519", "Membres", 150.0, 5,
                                  premier_achat=True, recharge=True)]
    r_h = B(offres(_cat_h, email=MEMBRE,
                   adhesions=[adhesion(MEMBRE, "2026-01-01", "2026-12-31")],
                   forfaits=[forfait(MEMBRE, 0)]))
    verifier("H. membre actif + 0 seance -> l'entree 250 n'est PAS proposee",
             "PULSE x10 cours" not in noms(r_h), noms(r_h))
    verifier("H2. ... et la recharge, elle, est proposee",
             "Membres" in noms(r_h), noms(r_h))
    verifier("H3. la recharge devient la recommandation, faute d'entree",
             reco(r_h) == "Membres", [(o["name"], o["recommended"]) for o in r_h])

    # --- I : membre actif, seances restantes ------------------------------
    r_i = B(offres(_cat_h, email=MEMBRE,
                   adhesions=[adhesion(MEMBRE, "2026-01-01", "2026-12-31")],
                   forfaits=[forfait(MEMBRE, 3)]))
    verifier("I. membre actif + seances restantes -> AUCUNE recharge inutile",
             "Membres" not in noms(r_i), noms(r_i))
    verifier("I2. ... et toujours pas d'entree 250",
             "PULSE x10 cours" not in noms(r_i), noms(r_i))
    verifier("I3. il lui reste le cours a l'unite, qui a du sens",
             noms(r_i) == ["Cours à l'unité"], noms(r_i))

    # --- non-membre : la recharge ne doit JAMAIS apparaitre ---------------
    r_nm = B(offres(_cat_h, email="neuf@example.org"))
    verifier("H4. non-membre -> la recharge est ABSENTE (la caisse la "
             "refuserait en 403 : l'ecran ne la montre plus)",
             "Membres" not in noms(r_nm), noms(r_nm))
    verifier("H5. ... et l'entree 250 lui reste proposee, recommandee",
             reco(r_nm) == "PULSE x10 cours", noms(r_nm))

    # --- adhesion EXPIREE : c'est un non-membre ---------------------------
    r_ex = B(offres(_cat_h, email=MEMBRE,
                    adhesions=[adhesion(MEMBRE, "2024-01-01", "2024-12-31")],
                    forfaits=[forfait(MEMBRE, 0)]))
    verifier("H6. adhesion EXPIREE -> pas de recharge, mais l'entree revient",
             "Membres" not in noms(r_ex) and reco(r_ex) == "PULSE x10 cours",
             noms(r_ex))

    # --- J : le prix vient du serveur -------------------------------------
    _cher = [dict(UNITE, price=99.0), PULSE]
    r_j = B(offres(_cher, email="neuf@example.org"))
    _u = [o for o in r_j if o["name"] == "Cours à l'unité"][0]
    verifier("J. le prix rendu est celui de la BASE, pas une valeur d'ecran",
             _u["price"] == 99.0 and _u["currency"] == "CHF", _u)

    # --- K : cross-coach ---------------------------------------------------
    _autre = [UNITE, PULSE, offre("z", "Offre d'un autre coach", 80.0, 1,
                                  coach="autre@coach.ch")]
    r_k = B(offres(_autre, email="neuf@example.org"))
    verifier("K. aucune offre d'un autre coach",
             "Offre d'un autre coach" not in noms(r_k), noms(r_k))
    r_k2 = B(offres(_autre, email="neuf@example.org", coach_id="autre@coach.ch"))
    verifier("K2. et symetriquement : un essai d'un partenaire ne voit QUE "
             "les offres de ce partenaire",
             noms(r_k2) == ["Offre d'un autre coach"], noms(r_k2))

    # --- la forme du dict n'a pas bouge ------------------------------------
    verifier("L. la forme du dict d'offre est INCHANGEE (T21a de LOT A)",
             set(r[0]) == {"id", "name", "price", "currency", "sessions",
                           "description", "thumbnail", "recommended"},
             sorted(r[0]))

    # --- sans e-mail : le comportement d'AVANT, intact ---------------------
    r_ne = B(offres())
    verifier("M. sans e-mail (appelant historique), rien ne casse : "
             "les offres sortent, la recommandation aussi",
             len(r_ne) == 2 and reco(r_ne) == "PULSE x10 cours", noms(r_ne))

    # --- base en panne : on n'invente pas un droit -------------------------
    class _Casse(_Db):
        def __getitem__(self, k):
            if k in ("memberships", "subscriptions"):
                raise RuntimeError("base muette")
            return _Db.__getitem__(self, k)
    _dbc = _Casse(offers=list(_cat_h))
    r_p = B(SH.conv_offres_premier_achat(_dbc, "", MEMBRE))
    verifier("N. base d'adhesion muette -> la recharge n'est PAS proposee "
             "(fail closed, comme la garde LOT R)",
             "Membres" not in noms(r_p), noms(r_p))

    print("=" * 78)
    for nom, ok, detail in RESULTATS:
        print("  %-6s %s" % ("OK" if ok else "ECHEC", nom))
        if not ok and detail != "":
            print("         -> %s" % (detail,))
    _ok = sum(1 for _n, o, _d in RESULTATS if o)
    print("-" * 78)
    print("%d / %d verifications" % (_ok, len(RESULTATS)))
    print("Aucune base reelle, aucun reseau, aucune ecriture.")
    return 0 if _ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

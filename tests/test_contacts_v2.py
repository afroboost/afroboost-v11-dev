# -*- coding: utf-8 -*-
"""CONTACTS V2 — quatre dimensions derivees, aucun consentement invente.

Fonctions EXTRAITES de `api/server.py` par AST. Aucune base, aucun reseau,
aucune ecriture, aucun contact modifie.
"""
import ast
import asyncio
import io
import os
import sys
import types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), str(detail)))


_ARBRE = ast.parse(io.open(SERVEUR, encoding="utf-8").read())
_VOULUS = ("C2_INDICATIFS", "C2_ZONES", "C2_STATUTS", "C2_CONSENTEMENTS",
           "c2_pays_zone", "c2_canaux", "c2_consentement",
           "c2_index_abonnements", "c2_index_consentements", "c2_enrichir")
_NOEUDS = {}
for _n in _ARBRE.body:
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name in _VOULUS:
        _n.decorator_list = []
        _NOEUDS[_n.name] = _n
    elif isinstance(_n, ast.Assign):
        for _c in _n.targets:
            if isinstance(_c, ast.Name) and _c.id in _VOULUS:
                _NOEUDS[_c.id] = _n
_MANQUE = [v for v in _VOULUS if v not in _NOEUDS]
if _MANQUE:
    print("EXTRACTION IMPOSSIBLE : %s" % _MANQUE)
    sys.exit(1)
SOURCE = "\n".join(ast.unparse(_NOEUDS[v]) for v in _VOULUS)


def code_nu(nom):
    _n = ast.parse(ast.unparse(_NOEUDS[nom])).body[0]
    if getattr(_n, "body", None) and isinstance(_n.body[0], ast.Expr) \
       and isinstance(getattr(_n.body[0], "value", None), ast.Constant) \
       and isinstance(_n.body[0].value.value, str):
        _n.body = _n.body[1:]
    return ast.unparse(_n)


# Le VRAI `forfait_utilisable`, extrait de shared.py — on ne recopie pas la
# regle : si elle change, ce test la suit.
_PARTAGE = os.path.join(RACINE, "api", "routes", "shared.py")
_A = ast.parse(io.open(_PARTAGE, encoding="utf-8").read())
_SRC_UTIL = None
for _n in _A.body:
    if isinstance(_n, ast.FunctionDef) and _n.name in (
            "forfait_utilisable", "_v391_est_expire", "_v391_seances_restantes"):
        _SRC_UTIL = (_SRC_UTIL or "") + "\n" + ast.unparse(_n)
_g_util = {"datetime": datetime, "timezone": timezone}
exec(compile(_SRC_UTIL, "<util>", "exec"), _g_util)
for _nom in ("api", "api.routes", "api.routes.shared"):
    sys.modules.setdefault(_nom, types.ModuleType(_nom))
sys.modules["api.routes.shared"].forfait_utilisable = _g_util["forfait_utilisable"]


class _Journal:
    def __init__(self): self.lignes = []
    def _n(self, m, *a): self.lignes.append(str(m))
    info = warning = error = _n


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]
        self.ecritures = 0

    def find(self, f=None, p=None):
        docs = self.docs
        class _It:
            def __aiter__(self_inner):
                self_inner._i = 0
                return self_inner
            async def __anext__(self_inner):
                await asyncio.sleep(0)
                if self_inner._i >= len(docs):
                    raise StopAsyncIteration
                d = docs[self_inner._i]; self_inner._i += 1
                return dict(d)
        return _It()

    async def update_one(self, *a, **k):
        self.ecritures += 1
        raise AssertionError("CONTACTS V2 ne doit RIEN ecrire")

    async def insert_one(self, *a, **k):
        self.ecritures += 1
        raise AssertionError("CONTACTS V2 ne doit RIEN ecrire")


class _Base:
    def __init__(self, subs=None, optin=None):
        self.subscriptions = _Coll(subs)
        self.subscribers = _Coll(optin)


BAC = {}


def bac(subs=None, optin=None):
    base = _Base(subs, optin)
    journal = _Journal()
    g = {"__builtins__": __builtins__, "datetime": datetime, "timezone": timezone,
         "db": base, "logger": journal}
    exec(compile(SOURCE, "<c2>", "exec"), g)
    BAC.clear(); BAC.update(g)
    return g, base, journal


def iso(j):
    return (datetime.now(timezone.utc) + timedelta(days=j)).isoformat()


async def zones():
    g, _, _ = bac()
    z = g["c2_pays_zone"]
    for num, pays, zone in (
        ("+41791234567", "CH", "suisse"),
        ("+41 79 123 45 67", "CH", "suisse"),
        ("0041791234567", "CH", "suisse"),
        ("+33612345678", "FR", "europe"),
        ("+39061234567", "IT", "europe"),
        ("+237691234567", "CM", "afrique"),
        ("+221771234567", "SN", "afrique"),
        ("+225071234567", "CI", "afrique"),
        ("+233201234567", "GH", "afrique"),
        ("+243991234567", "CD", "afrique"),
    ):
        verifier("Z1. %-20s -> %s / %s" % (num, pays, zone), z(num) == (pays, zone), str(z(num)))

    for num, motif in (("0791234567", "national"), ("079 123 45 67", "national"),
                       ("", "vide"), (None, "nul"), ("+123", "trop court"),
                       ("abc", "texte"), ("+41", "tronque")):
        verifier("Z2. %-16s (%s) -> inconnue, jamais un pays certain" % (repr(num), motif),
                 z(num) == (None, "inconnue"), str(z(num)))

    verifier("Z3. un indicatif hors table -> « autre », pas un pays invente",
             z("+8613800138000") == (None, "autre"), str(z("+8613800138000")))
    verifier("Z4. la zone Afrique conserve le PAYS pour un filtrage fin",
             z("+237691234567")[0] == "CM" and z("+221771234567")[0] == "SN")
    verifier("Z5. toutes les zones rendues font partie du bareme",
             all(z(n)[1] in BAC["C2_ZONES"] for n in
                 ("+41791234567", "0791234567", "+8613800138000", "+33612345678", "")))


async def statuts():
    ACTIF = {"email": "a@x.io", "status": "active", "expires_at": iso(30),
             "remaining_sessions": 5, "total_sessions": 10}
    EXPIRE = {"email": "b@x.io", "status": "active", "expires_at": iso(-10),
              "remaining_sessions": 5, "total_sessions": 10}
    EPUISE = {"email": "c@x.io", "status": "active", "expires_at": iso(30),
              "remaining_sessions": 0, "total_sessions": 10}
    g, _, _ = bac(subs=[ACTIF, EXPIRE, EPUISE])
    idx = await g["c2_index_abonnements"]()
    verifier("S1. forfait utilisable -> actif", idx.get("a@x.io") == "actif", str(idx))
    verifier("S2. forfait EXPIRE -> ancien abonne", idx.get("b@x.io") == "ancien")
    verifier("S3. forfait EPUISE -> ancien abonne", idx.get("c@x.io") == "ancien")
    verifier("S4. aucun forfait -> absent de l'index (= non abonne)",
             "z@x.io" not in idx)

    # un actif l'emporte sur un ancien pour la meme adresse
    g, _, _ = bac(subs=[EXPIRE, dict(ACTIF, email="b@x.io")])
    idx = await g["c2_index_abonnements"]()
    verifier("S5. un forfait actif l'emporte sur un ancien",
             idx.get("b@x.io") == "actif", str(idx))

    verifier("S6. `isSubscriber` n'est JAMAIS consulte — il n'est jamais remis "
             "a faux et dirait « actif » d'un abonne expire",
             "isSubscriber" not in code_nu("c2_index_abonnements")
             and "isSubscriber" not in code_nu("c2_enrichir"))
    verifier("S7. la regle vient de `forfait_utilisable`, elle n'est pas recopiee",
             "forfait_utilisable" in code_nu("c2_index_abonnements"))


async def canaux_et_consentement():
    g, _, _ = bac()
    c = g["c2_canaux"]
    verifier("C1. e-mail seul", c({"email": "a@x.io"}) == {"email": True, "whatsapp": False, "telephone": False})
    verifier("C2. whatsapp compte aussi comme telephone",
             c({"whatsapp": "+41791234567"}) == {"email": False, "whatsapp": True, "telephone": True})
    verifier("C3. telephone seul", c({"phone": "+41791234567"})["telephone"] is True
             and c({"phone": "+41791234567"})["whatsapp"] is False)
    verifier("C4. aucun canal", c({}) == {"email": False, "whatsapp": False, "telephone": False})

    k = g["c2_consentement"]
    verifier("K1. confirmed -> autorise", k("confirmed") == "autorise")
    verifier("K2. opted_out -> refuse", k("opted_out") == "refuse")
    verifier("K3. PENDING -> inconnu : une inscription non confirmee n'est pas "
             "une autorisation", k("pending") == "inconnu")
    verifier("K4. absence de trace -> inconnu, JAMAIS autorise", k(None) == "inconnu")
    verifier("K5. valeur inattendue -> inconnu", k("bizarre") == "inconnu")

    # LE POINT CENTRAL : coordonnee != autorisation
    g, base, _ = bac(optin=[])
    e = g["c2_enrichir"]({"email": "a@x.io", "whatsapp": "+41791234567"}, {}, {})
    verifier("K6. avoir une adresse ET un numero ne donne AUCUNE autorisation",
             e["consentement"] == {"email": "inconnu", "whatsapp": "inconnu"}, str(e["consentement"]))
    verifier("K6b. mais les canaux, eux, sont bien disponibles",
             e["canaux"]["email"] and e["canaux"]["whatsapp"])

    g, _, _ = bac(optin=[{"channel": "email", "value": "a@x.io", "status": "confirmed"},
                         {"channel": "whatsapp", "value": "+41 79 123 45 67", "status": "opted_out"}])
    idx = await g["c2_index_consentements"]()
    e = g["c2_enrichir"]({"email": "A@X.IO", "whatsapp": "+41791234567"}, {}, idx)
    verifier("K7. opt-in confirme -> e-mail autorise (casse normalisee)",
             e["consentement"]["email"] == "autorise", str(e["consentement"]))
    verifier("K8. desinscription -> WhatsApp refuse (numero normalise)",
             e["consentement"]["whatsapp"] == "refuse", str(e["consentement"]))
    verifier("K9. aucune case generique n'autorise tous les canaux d'un coup",
             "marketing_consent" not in SOURCE)


async def enrichissement():
    g, base, _ = bac(subs=[{"email": "a@x.io", "status": "active", "expires_at": iso(30),
                            "remaining_sessions": 3, "total_sessions": 5}])
    abos = await g["c2_index_abonnements"]()
    e = g["c2_enrichir"]({"email": "a@x.io", "whatsapp": "+237691234567",
                          "contact_type": "participant"}, abos, {})
    verifier("E1. les quatre dimensions coexistent sans se confondre",
             e["contact_type"] == "participant" and e["statut_abonnement"] == "actif"
             and e["zone"] == "afrique" and e["pays"] == "CM"
             and e["canaux"]["whatsapp"] is True, str(e)[:150])
    verifier("E2. `contact_type` n'est jamais recalcule : il reste ce que "
             "le coach a pose", e["contact_type"] == "participant")
    e2 = g["c2_enrichir"]({"email": "inconnu@x.io"}, abos, {})
    verifier("E3. sans forfait -> non abonne", e2["statut_abonnement"] == "non_abonne")
    verifier("E4. sans numero -> zone inconnue", e2["zone"] == "inconnue" and e2["pays"] is None)
    verifier("W1. AUCUNE ecriture pendant tout l'enrichissement",
             base.subscriptions.ecritures == 0 and base.subscribers.ecritures == 0)


def structure():
    verifier("S8. aucune ecriture dans tout le socle V2",
             not any(m in SOURCE for m in ("insert_one", "update_one", "delete_", "$set")))
    verifier("S9. aucun backfill : rien ne transforme une coordonnee en accord",
             "autorise" in code_nu("c2_consentement")
             and "confirmed" in code_nu("c2_consentement"))
    verifier("S10. contact_type n'est ni ecrit ni devine ici",
             "contact_type" not in code_nu("c2_enrichir").replace('_c["contact_type"]', ""))
    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S11. ce test n'importe que la bibliotheque standard, hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "types", "datetime"}, str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(zones())
        b.run_until_complete(statuts())
        b.run_until_complete(canaux_et_consentement())
        b.run_until_complete(enrichissement())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Contacts modifies : 0 — aucune ecriture, aucun consentement fabrique")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

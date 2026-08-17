# -*- coding: utf-8 -*-
"""P0 — `participant_code` ne doit plus sortir d'une reponse publique.

Le code d'un abonne EST son mot de passe. `GET /api/comments` est anonyme et
projetait tout le document : il livrait donc ce mot de passe a qui le demandait.

Les fonctions testees sont EXTRAITES de `api/server.py` par AST. Aucune base,
aucun reseau, aucune ecriture.
"""
import ast
import asyncio
import io
import os
import sys
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), str(detail)))


_ARBRE = ast.parse(io.open(SERVEUR, encoding="utf-8").read())
_VOULUS = ("COMMENTS_CHAMPS_PUBLICS", "COMMENTS_PROJECTION_PUBLIQUE",
           "_comment_public", "get_comments", "submit_review")
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
    print("EXTRACTION IMPOSSIBLE — absents de server.py : %s" % _MANQUE)
    sys.exit(1)

SOURCE = "\n".join(ast.unparse(_NOEUDS[v]) for v in _VOULUS)


def code_nu(nom):
    _n = ast.parse(ast.unparse(_NOEUDS[nom])).body[0]
    if getattr(_n, "body", None) and isinstance(_n.body[0], ast.Expr) \
       and isinstance(getattr(_n.body[0], "value", None), ast.Constant) \
       and isinstance(_n.body[0].value.value, str):
        _n.body = _n.body[1:]
    return ast.unparse(_n)


# ── le bac ──────────────────────────────────────────────────────────────────
class _HTTPException(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Journal:
    def __init__(self): self.lignes = []
    def _n(self, m, *a): self.lignes.append(str(m))
    info = warning = error = _n


class _Curseur:
    def __init__(self, docs, projection):
        self.docs = docs
        self.projection = projection

    def sort(self, *a, **k): return self

    async def to_list(self, n=None):
        await asyncio.sleep(0)
        p = self.projection or {}
        gardes = [c for c, v in p.items() if v == 1 and c != "_id"]
        out = []
        for d in self.docs[: n or len(self.docs)]:
            # On simule MongoDB : une projection d'INCLUSION ne rend que les
            # champs nommes. Sans projection, tout sort — c'est l'ancien defaut.
            out.append({c: d[c] for c in gardes if c in d} if gardes else dict(d))
        return out


class _Comments:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.ecritures = 0

    def find(self, query=None, projection=None):
        return _Curseur(self.docs, projection)

    async def find_one(self, query=None, projection=None):
        await asyncio.sleep(0)
        return None

    async def count_documents(self, query=None):
        await asyncio.sleep(0)
        return len(self.docs)

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        self.ecritures += 1
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": "x"})()

    async def update_one(self, *a, **k):
        self.ecritures += 1
        raise AssertionError("ce lot ne doit RIEN modifier")


class _Base:
    def __init__(self, docs=None): self.comments = _Comments(docs)


class _Requete:
    def __init__(self, params=None, headers=None):
        self.query_params = params or {}
        self.headers = headers or {}
        self._corps = {}

    async def json(self): return self._corps


BAC = {}


def bac(docs=None):
    base = _Base(docs)
    journal = _Journal()
    g = {
        "__builtins__": __builtins__,
        "datetime": datetime, "timezone": timezone,
        "db": base, "logger": journal,
        "HTTPException": _HTTPException, "Request": _Requete,
        "_random": __import__("random"),
    }
    exec(compile(SOURCE, "<p0>", "exec"), g)
    BAC.clear(); BAC.update(g)
    return g, base, journal


# ── un document tel qu'il existe REELLEMENT en base ─────────────────────────
def avis(**extra):
    d = {
        "id": "review_20260812_101",
        "user_name": "Prenom L.",
        "text": "Super seance, ambiance incroyable.",
        "profile_photo": "https://exemple/x.svg",
        "rating": 5,
        "likes": 12,
        "is_ai": False,
        "is_review": True,
        "is_verified": True,
        "is_visible": True,
        "participant_code": "AFR-9K2M1P",     # le mot de passe de l'abonne
        "session_id": "sess-778",
        "coach_id": "contact.artboost@gmail.com",
        "created_at": "2026-08-12T10:10:00+00:00",
    }
    d.update(extra)
    return d


SENSIBLES = ("participant_code", "coach_id", "session_id", "is_visible",
             "email", "userEmail", "phone", "whatsapp", "consent_public",
             "consented_at", "moderation_status", "approved_at", "_id")


async def scenarios():
    # ── 1. la fuite elle-meme
    g, base, _ = bac([avis()])
    r = await g["get_comments"](_Requete())
    c = r["comments"][0]
    verifier("1. participant_code ABSENT de la reponse publique",
             "participant_code" not in c, str(sorted(c.keys())))
    verifier("1b. et sa valeur n'apparait nulle part dans la reponse",
             "AFR-9K2M1P" not in str(r), str(r)[:160])

    # ── 2. tout champ sensible, present ou futur
    g, base, _ = bac([avis(email="victime@exemple.io", userEmail="victime@exemple.io",
                           phone="+41760000000", whatsapp="+41760000000",
                           consent_public=True, consented_at="2026-08-12",
                           moderation_status="approved", approved_at="2026-08-12")])
    r = await g["get_comments"](_Requete())
    c = r["comments"][0]
    fuites = [k for k in SENSIBLES if k in c]
    verifier("2. aucun email, telephone, identifiant interne, champ de moderation "
             "ni de consentement ne sort", not fuites, str(fuites))
    verifier("2b. aucune de leurs VALEURS non plus",
             not any(v in str(r) for v in ("victime@exemple", "+4176", "approved")),
             str(r)[:200])

    # ── 3. liste blanche stricte : un champ inconnu ajoute demain ne sort pas
    g, base, _ = bac([avis(champ_invente_demain="secret", internal_note="x")])
    c = (await g["get_comments"](_Requete()))["comments"][0]
    verifier("3. un champ AJOUTE PLUS TARD au document ne sort pas tout seul",
             "champ_invente_demain" not in c and "internal_note" not in c,
             str(sorted(c.keys())))
    verifier("3b. la reponse se limite exactement a la liste blanche",
             set(c.keys()) <= set(g["COMMENTS_CHAMPS_PUBLICS"]), str(sorted(c.keys())))

    # ── 4. l'affichage public n'est pas casse
    g, base, _ = bac([avis()])
    c = (await g["get_comments"](_Requete()))["comments"][0]
    for champ, valeur in (("id", "review_20260812_101"), ("user_name", "Prenom L."),
                          ("text", "Super seance, ambiance incroyable."),
                          ("profile_photo", "https://exemple/x.svg"),
                          ("rating", 5), ("likes", 12), ("is_verified", True)):
        verifier("4. l'ecran garde « %s »" % champ, c.get(champ) == valeur,
                 "%r != %r" % (c.get(champ), valeur))
    verifier("4b. la date reste disponible pour un affichage futur",
             c.get("created_at") == "2026-08-12T10:10:00+00:00")

    # ── 5. les compteurs et le filtre coach continuent de fonctionner
    g, base, _ = bac([avis(), avis(id="r2")])
    r = await g["get_comments"](_Requete())
    verifier("5. le total et la liste restent coherents",
             r["total"] == 2 and r["total_count"] == 2 and len(r["comments"]) == 2)
    r = await g["get_comments"](_Requete({"coach_id": "Contact.Artboost@Gmail.com"}))
    verifier("5b. le filtre par coach passe toujours (casse normalisee)",
             len(r["comments"]) == 2)

    # ── 6. l'echo de POST /reviews
    g, base, _ = bac([])
    req = _Requete()
    req._corps = {"participant_code": "AFR-SECRET1", "participant_name": "Prenom",
                  "text": "Merci !", "rating": 5,
                  "coach_id": "contact.artboost@gmail.com", "session_id": "s1"}
    rep = await g["submit_review"](req)
    verifier("6. la reponse de POST /reviews ne renvoie plus le code",
             "participant_code" not in rep["comment"], str(sorted(rep["comment"].keys())))
    verifier("6b. ni aucune valeur sensible",
             "AFR-SECRET1" not in str(rep["comment"]) and "s1" not in str(rep["comment"]),
             str(rep["comment"])[:150])
    verifier("6c. mais le code est TOUJOURS enregistre en base — l'anti-spam en depend",
             base.comments.docs[0].get("participant_code") == "AFR-SECRET1")
    verifier("6d. l'avis reste affichable : nom, texte, note",
             rep["comment"].get("text") == "Merci !" and rep["comment"].get("rating") == 5)

    # ── 7. la seconde porte : le code etait ENCASTRE dans l'URL de l'avatar,
    #      donc a l'interieur d'un champ autorise, hors de portee de toute
    #      liste blanche de champs.
    g, base, _ = bac([])
    req = _Requete()
    req._corps = {"participant_code": "AFR-SECRET1", "participant_name": "Prenom",
                  "text": "Merci !", "rating": 5}
    rep = await g["submit_review"](req)
    photo = str(rep["comment"].get("profile_photo") or "")
    verifier("7. l'avatar genere ne contient PAS le code",
             "AFR-SECRET1" not in photo and "SECRET" not in photo, photo[:110])
    verifier("7b. l'avatar reste genere quand aucune photo n'est fournie",
             photo.startswith("https://api.dicebear.com/"), photo[:60])
    verifier("7c. le document ENREGISTRE non plus ne porte le code dans son avatar",
             "AFR-SECRET1" not in str(base.comments.docs[0].get("profile_photo")))
    g, base, _ = bac([])
    req2 = _Requete()
    req2._corps = dict(req._corps, profile_photo="https://exemple/vraie.jpg")
    rep2 = await g["submit_review"](req2)
    verifier("7d. une vraie photo fournie est conservee telle quelle",
             rep2["comment"].get("profile_photo") == "https://exemple/vraie.jpg")


def structure():
    verifier("S1. le filtre est fait par MongoDB, pas apres coup",
             "COMMENTS_PROJECTION_PUBLIQUE" in code_nu("get_comments")
             and '{"_id": 0}' not in code_nu("get_comments").replace("'", '"'))
    verifier("S2. c'est une liste BLANCHE, pas une suppression ponctuelle",
             "pop(" not in code_nu("get_comments"))
    _bl = ast.literal_eval(ast.unparse(_NOEUDS["COMMENTS_CHAMPS_PUBLICS"]).split("=", 1)[1].strip())
    verifier("S3. la liste blanche ne contient AUCUN champ sensible",
             not [c for c in _bl if c in SENSIBLES], str(_bl))
    verifier("S4. les deux sorties partagent la meme liste",
             "COMMENTS_CHAMPS_PUBLICS" in code_nu("_comment_public")
             and "_comment_public" in code_nu("submit_review"))
    verifier("S5. ce lot n'ecrit rien de nouveau : aucune modification de document",
             "update_one" not in code_nu("get_comments")
             and "update_many" not in SOURCE and "delete_" not in SOURCE)
    verifier("S6. l'anti-spam continue de lire le code en base",
             "participant_code" in code_nu("submit_review"))
    _nu = code_nu("submit_review")
    _graine = [l for l in _nu.splitlines() if "avatar_seed" in l and "=" in l]
    verifier("S8. la graine de l'avatar ne melange plus le code au nom",
             _graine and "participant_code" not in _graine[0], str(_graine)[:120])

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S7. ce test n'importe que la bibliotheque standard, hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "sys", "datetime"}, str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(scenarios())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Ecritures en base : 0 — documents fabriques, aucune connexion")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""V441 — tests HORS LIGNE du mécanisme « messages WhatsApp non lus ».

Aucun réseau, aucune base réelle, aucun WhatsApp. Les fonctions testées ne sont
PAS réécrites ici : leur code source est extrait de `api/server.py` par analyse
AST puis exécuté tel quel contre une base factice en mémoire. Un test qui passe
prouve donc quelque chose sur le code qui partira en production.

Lancement :  python3 tests/test_v441_nonlus.py
"""
import ast, asyncio, io, os, re, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")

# --------------------------------------------------------------------------
# Mini-Mongo asynchrone : uniquement les opérateurs réellement utilisés.
# --------------------------------------------------------------------------
def _match(doc, filtre):
    for cle, cond in filtre.items():
        if cle == "$or":
            if not any(_match(doc, c) for c in cond):
                return False
            continue
        val = doc.get(cle)
        if isinstance(cond, dict):
            for op, ref in cond.items():
                if op == "$ne":
                    if val == ref: return False
                elif op == "$gt":
                    if not (val is not None and val > ref): return False
                elif op == "$regex":
                    if not (isinstance(val, str) and re.search(ref, val)): return False
                else:
                    raise AssertionError("operateur non simule: %s" % op)
        elif val != cond:
            return False
    return True


class _Curseur:
    def __init__(self, docs): self._docs = docs
    async def to_list(self, n): return self._docs[:n]
    def __aiter__(self):
        async def gen():
            for d in self._docs: yield d
        return gen()


class Collection:
    def __init__(self): self.docs = []
    def find(self, filtre=None, projection=None):
        return _Curseur([dict(d) for d in self.docs if _match(d, filtre or {})])
    async def find_one(self, filtre, projection=None):
        for d in self.docs:
            if _match(d, filtre): return dict(d)
        return None
    async def insert_one(self, doc): self.docs.append(dict(doc))
    async def update_one(self, filtre, maj, upsert=False):
        for d in self.docs:
            if _match(d, filtre):
                d.update(maj.get("$set", {})); return
        if upsert:
            nouveau = {}
            nouveau.update(maj.get("$setOnInsert", {}))
            nouveau.update(maj.get("$set", {}))
            for k, v in filtre.items():
                if not isinstance(v, dict): nouveau.setdefault(k, v)
            self.docs.append(nouveau)
    def aggregate(self, pipeline):
        docs = [dict(d) for d in self.docs]
        for etape in pipeline:
            if "$match" in etape:
                docs = [d for d in docs if _match(d, etape["$match"])]
            elif "$group" in etape:
                g = etape["$group"]; cle = g["_id"].lstrip("$"); acc = {}
                for d in docs: acc[d.get(cle)] = acc.get(d.get(cle), 0) + 1
                docs = [{"_id": k, "n": v} for k, v in acc.items()]
            else:
                raise AssertionError("etape non simulee: %s" % etape)
        return _Curseur(docs)


class Base:
    def __init__(self):
        self.private_conversations = Collection()
        self.private_messages = Collection()
        self.private_lectures = Collection()


# --------------------------------------------------------------------------
# Extraction du VRAI code source depuis api/server.py
# --------------------------------------------------------------------------
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

def extraire(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            debut = n.lineno - 1  # sans les décorateurs : on les remplace
            return "".join(LIGNES[debut:n.end_lineno])
    raise AssertionError("fonction introuvable dans server.py : %s" % nom)

def extraire_constante(nom):
    for n in ARBRE.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("constante introuvable : %s" % nom)


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code; self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))


class _Horloge:
    """Remplace `datetime` dans le bac à sable pour maîtriser le temps."""
    courant = "2026-08-16T12:00:00.000000+00:00"
    class _DT:
        @staticmethod
        def now(tz=None):
            class _I:
                @staticmethod
                def isoformat(): return _Horloge.courant
            return _I()
    datetime = _DT


def construire(base, lecteur="contact.artboost@gmail.com", origine="2026-08-16T00:00:00+00:00"):
    """Exécute le code source réel dans un espace de noms contrôlé."""
    bac = {
        "db": base, "HTTPException": HTTPException, "Request": object,
        "datetime": _Horloge.datetime, "timezone": type("tz", (), {"utc": None}),
        "os": type("os", (), {"environ": {"NONLU_ORIGINE": origine}}),
        "logger": type("l", (), {"warning": staticmethod(lambda *a, **k: None),
                                 "info": staticmethod(lambda *a, **k: None)}),
        "BaseModel": object, "V441MarquerLu": Corps,
        "_v441_exiger_lecteur": lambda request, quoi: lecteur,
        "api_router": type("r", (), {"get": staticmethod(lambda *a, **k: (lambda f: f)),
                                     "post": staticmethod(lambda *a, **k: (lambda f: f))}),
    }
    code = (extraire_constante("V441_NONLU_ORIGINE") + "\n"
            + extraire("_v441_filtre_boite_coach") + "\n"
            + extraire("v441_compter_non_lus") + "\n"
            + extraire("v441_marquer_lu") + "\n")
    exec(compile(code, "<v441-extrait-de-server.py>", "exec"), bac)
    return bac


class Corps:
    def __init__(self, conversation_id): self.conversation_id = conversation_id


# --------------------------------------------------------------------------
# Jeu de données
# --------------------------------------------------------------------------
ADMIN = "admin_afroboost"

def base_neuve():
    b = Base()
    for cid, tel in (("conv-A", "41790000001"), ("conv-B", "41790000002")):
        b.private_conversations.docs.append({
            "id": cid, "channel": "whatsapp", "phone": "+" + tel,
            "participant_1_id": "whatsapp_" + tel, "participant_2_id": ADMIN,
            "last_message_at": "2026-04-22T10:00:00.000000+00:00",
        })
    return b

def entrant(b, cid, quand, tel="41790000001"):
    b.private_messages.docs.append({
        "id": "m%d" % len(b.private_messages.docs), "conversation_id": cid,
        "sender_id": "whatsapp_" + tel, "recipient_id": ADMIN,
        "content": "coucou", "created_at": quand, "channel": "whatsapp"})

def sortant(b, cid, quand, tel="41790000001"):
    b.private_messages.docs.append({
        "id": "m%d" % len(b.private_messages.docs), "conversation_id": cid,
        "sender_id": ADMIN, "recipient_id": "whatsapp_" + tel,
        "content": "reponse", "created_at": quand, "channel": "whatsapp"})


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------
RESULTATS = []

def verifier(nom, condition, detail=""):
    RESULTATS.append((nom, bool(condition), detail))

async def scenario():
    APRES = "2026-08-16T13:00:00.000000+00:00"
    ENCORE = "2026-08-16T13:05:00.000000+00:00"
    PLUS_TARD = "2026-08-16T14:00:00.000000+00:00"

    # --- 1 : nouveau WhatsApp entrant -> unread = 1
    b = base_neuve(); bac = construire(b)
    entrant(b, "conv-A", APRES)
    r = await bac["v441_compter_non_lus"](None)
    verifier("1. nouvel entrant -> unread=1", r["total"] == 1 and r["nonlus"].get("conv-A") == 1, str(r))

    # --- 2 : deuxieme message du meme client -> unread = 2
    entrant(b, "conv-A", ENCORE)
    r = await bac["v441_compter_non_lus"](None)
    verifier("2. deuxieme message -> unread=2", r["total"] == 2 and r["nonlus"]["conv-A"] == 2, str(r))

    # --- 3 : polling de la liste -> reste unread
    for _ in range(5):
        r = await bac["v441_compter_non_lus"](None)
    verifier("3. polling x5 -> reste unread=2", r["total"] == 2, str(r))
    verifier("3b. le polling n'ecrit RIEN", len(b.private_lectures.docs) == 0,
             "private_lectures=%d" % len(b.private_lectures.docs))

    # --- 4 : refresh navigateur -> reste unread (etat serveur, contexte neuf)
    bac2 = construire(b)
    r = await bac2["v441_compter_non_lus"](None)
    verifier("4. refresh navigateur -> reste unread=2", r["total"] == 2, str(r))

    # --- 5 : ouverture reelle de la conversation -> unread = 0
    _Horloge.courant = "2026-08-16T13:30:00.000000+00:00"
    await bac["v441_marquer_lu"](Corps("conv-A"), None)
    r = await bac["v441_compter_non_lus"](None)
    verifier("5. ouverture reelle -> unread=0", r["total"] == 0 and "conv-A" not in r["nonlus"], str(r))

    # --- 6 : nouvel entrant apres lecture -> repart a 1
    entrant(b, "conv-A", PLUS_TARD)
    r = await bac["v441_compter_non_lus"](None)
    verifier("6. entrant apres lecture -> unread=1", r["nonlus"].get("conv-A") == 1, str(r))

    # --- 7 : autre conversation independante
    entrant(b, "conv-B", APRES, tel="41790000002")
    entrant(b, "conv-B", ENCORE, tel="41790000002")
    r = await bac["v441_compter_non_lus"](None)
    verifier("7. autre conversation independante",
             r["nonlus"].get("conv-A") == 1 and r["nonlus"].get("conv-B") == 2
             and r["conversations_non_lues"] == 2, str(r))
    _Horloge.courant = "2026-08-16T14:30:00.000000+00:00"
    await bac["v441_marquer_lu"](Corps("conv-B"), None)
    r = await bac["v441_compter_non_lus"](None)
    verifier("7b. lire B ne touche pas A", r["nonlus"].get("conv-A") == 1 and "conv-B" not in r["nonlus"], str(r))

    # --- 8 : autre appareil du MEME coach -> meme etat serveur
    bac_tel = construire(b, lecteur="contact.artboost@gmail.com")
    r_tel = await bac_tel["v441_compter_non_lus"](None)
    verifier("8. autre appareil, meme coach -> meme etat",
             r_tel["nonlus"] == r["nonlus"] and r_tel["total"] == r["total"], "%s vs %s" % (r_tel, r))

    # --- 8b : un AUTRE super-admin garde son propre etat
    bac_autre = construire(b, lecteur="autre.admin@afroboost.com")
    r_autre = await bac_autre["v441_compter_non_lus"](None)
    # Ce lecteur-la n'a jamais rien ouvert : il voit TOUS les entrants postérieurs
    # a l'origine (3 sur conv-A + 2 sur conv-B), la ou le premier coach n'en voit
    # plus qu'un. C'est exactement l'independance recherchee.
    verifier("8b. autre super-admin -> etat independant",
             r_autre["total"] == 5 and r["total"] == 1, "%s vs %s" % (r_autre, r))

    # --- 9 : message SORTANT du coach -> ne cree PAS d'unread
    b9 = base_neuve(); bac9 = construire(b9)
    sortant(b9, "conv-A", APRES)
    sortant(b9, "conv-A", ENCORE)
    r = await bac9["v441_compter_non_lus"](None)
    verifier("9. sortant coach -> aucun unread", r["total"] == 0, str(r))

    # --- 10 : ancien historique -> ne devient PAS unread au deploiement
    b10 = base_neuve(); bac10 = construire(b10)
    for quand in ("2026-04-22T10:12:11.536185+00:00", "2026-05-03T09:00:00.000000+00:00",
                  "2026-08-14T02:03:59.672666+00:00"):
        entrant(b10, "conv-A", quand)
    sortant(b10, "conv-A", "2026-08-14T02:04:30.000000+00:00")
    r = await bac10["v441_compter_non_lus"](None)
    verifier("10. historique -> 0 unread au deploiement", r["total"] == 0, str(r))
    verifier("10b. rien n'a ete ecrit en base", len(b10.private_lectures.docs) == 0,
             "private_lectures=%d" % len(b10.private_lectures.docs))
    entrant(b10, "conv-A", APRES)
    r = await bac10["v441_compter_non_lus"](None)
    verifier("10c. le 1er message d'apres compte bien", r["total"] == 1, str(r))

    # --- 11 : fil inconnu -> 404, aucune ecriture parasite
    b11 = base_neuve(); bac11 = construire(b11)
    try:
        await bac11["v441_marquer_lu"](Corps("conv-INEXISTANTE"), None)
        verifier("11. fil inconnu -> 404", False, "aucune exception levee")
    except HTTPException as e:
        verifier("11. fil inconnu -> 404", e.status_code == 404, str(e.status_code))
    verifier("11b. fil inconnu -> aucune ecriture", len(b11.private_lectures.docs) == 0, "")

    # --- 12 : base vide -> reponse neutre, pas d'exception
    b12 = Base(); bac12 = construire(b12)
    r = await bac12["v441_compter_non_lus"](None)
    verifier("12. aucune conversation -> total=0", r["total"] == 0 and r["nonlus"] == {}, str(r))

    # --- 13 : message supprime -> jamais compte
    b13 = base_neuve(); bac13 = construire(b13)
    entrant(b13, "conv-A", APRES)
    b13.private_messages.docs[-1]["is_deleted"] = True
    r = await bac13["v441_compter_non_lus"](None)
    verifier("13. message supprime -> non compte", r["total"] == 0, str(r))


# --------------------------------------------------------------------------
# Vérifications STRUCTURELLES : ce que le code n'a pas le droit de faire
# --------------------------------------------------------------------------
def noeud(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return n
    raise AssertionError("fonction introuvable : %s" % nom)


def code_nu(nom):
    """Le code de la fonction SANS sa docstring ni ses commentaires.

    On repasse par l'AST plutot que par une recherche de texte : sinon une simple
    mention de `results["skipped"]` dans un commentaire d'explication ferait
    passer (ou echouer) un test a tort. Ce qui compte est ce qui S'EXECUTE.
    """
    n = noeud(nom)
    corps = list(n.body)
    if (corps and isinstance(corps[0], ast.Expr)
            and isinstance(getattr(corps[0], "value", None), ast.Constant)
            and isinstance(corps[0].value.value, str)):
        corps = corps[1:]          # on retire la docstring
    return "\n".join(ast.unparse(x) for x in corps)


def tests_structurels():
    get_nu = code_nu("v441_compter_non_lus")
    for interdit in ("update_one", "update_many", "insert_one", "delete_one",
                     "delete_many", "$set", "replace_one", "upsert"):
        verifier("S1. GET /nonlus n'ecrit jamais (%s absent du code execute)" % interdit,
                 interdit not in get_nu, interdit)

    verifier("S2. GET /nonlus ne compte que les ENTRANTS",
             "'$regex': '^whatsapp_'" in get_nu, get_nu[:120])

    post_nu = code_nu("v441_marquer_lu")
    verifier("S3. POST /lecture exige le lecteur authentifie",
             "_v441_exiger_lecteur" in post_nu, "")
    verifier("S4. GET /nonlus exige le lecteur authentifie",
             "_v441_exiger_lecteur" in get_nu, "")
    verifier("S5. l'identite passe par la porte V411 (JWT super-admin)",
             "_v411_exiger_super_admin" in code_nu("_v441_exiger_lecteur"), "")

    verifier("S5b. POST /lecture est le SEUL ecrivain de private_lectures",
             sum(1 for n in ast.walk(ARBRE)
                 if isinstance(n, ast.Attribute) and n.attr in
                 ("update_one", "update_many", "insert_one", "insert_many",
                  "delete_one", "delete_many", "replace_one")
                 and "private_lectures" in ast.unparse(n)) == 1, "")

    for fn in ("get_private_messages", "get_private_conversations",
               "mark_private_messages_read", "get_unread_private_count"):
        try: src = code_nu(fn)
        except AssertionError: continue
        verifier("S6. %s ne touche pas private_lectures" % fn,
                 "private_lectures" not in src, "")

    # --- Non-regression P0-A : plus AUCUNE indexation par cle sur `results`.
    lc = noeud("launch_campaign")
    indexations = [ast.unparse(c) for c in ast.walk(lc)
                   if isinstance(c, ast.Subscript)
                   and isinstance(c.value, ast.Name) and c.value.id == "results"
                   and not isinstance(getattr(c, "slice", None), ast.Slice)]
    verifier("S7. launch_campaign : aucune indexation results[...] (AST)",
             indexations == [], " | ".join(indexations))

    lc_nu = code_nu("launch_campaign")
    verifier("S8. launch_campaign : compteur local skipped_count",
             "skipped_count += 1" in lc_nu and "skipped_count = 0" in lc_nu, "")
    verifier("S9. launch_campaign : results reste une liste",
             "results = []" in lc_nu, "")
    verifier("S9b. launch_campaign : aucun appel results.get(",
             not any(isinstance(c, ast.Call) and ast.unparse(c).startswith("results.get(")
                     for c in ast.walk(lc)), "")

    verifier("S10. le webhook WhatsApp n'ecrit aucun etat de lecture",
             "private_lectures" not in code_nu("_save_whatsapp_conversation")
             and "lu_jusqu_a" not in code_nu("_save_whatsapp_conversation"), "")


def main():
    tests_structurels()
    asyncio.get_event_loop().run_until_complete(scenario())
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 72)
    for nom, r, detail in RESULTATS:
        print(("  OK   " if r else "  ECHEC") + "  " + nom + (("   -> " + detail) if not r else ""))
    print("=" * 72)
    print("%d/%d tests passes" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

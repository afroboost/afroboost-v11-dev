# -*- coding: utf-8 -*-
"""ESSAI-5a-2 — temoignages authentiques.

Fonctions EXTRAITES de `api/server.py` par AST. Aucune base, aucun reseau,
aucun temoignage reel, aucun contact modifie.
"""
import ast
import asyncio
import io
import os
import re
import sys
import types
from datetime import datetime, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
RESULTATS = []


def verifier(nom, ok, detail=""):
    RESULTATS.append((nom, bool(ok), str(detail)))


_ARBRE = ast.parse(io.open(SERVEUR, encoding="utf-8").read())
_VOULUS = ("T3_MARQUEUR", "T3_PENDING", "T3_APPROVED", "T3_HIDDEN", "T3_ETATS",
           "T3_CHAMPS_PUBLICS", "T3_LONGUEUR_MAX", "T3_TYPES_CONTACT",
           "t3_deja_temoigne", "t3_contact_type", "t3_eligibilite", "t3_public",
           "t3_soumettre", "t3_publics", "t3_liste_coach", "t3_moderer",
           "t3_classer_contact", "t3_suggestions_participant")
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


for _nom in ("api", "api.routes", "api.routes.shared"):
    sys.modules.setdefault(_nom, types.ModuleType(_nom))
POSTHOG = []


async def _faux_capture(event, email="", props=None):
    await asyncio.sleep(0)
    POSTHOG.append({"event": event, "email": email, "props": dict(props or {})})


sys.modules["api.routes.shared"].posthog_capture = _faux_capture


class _HTTPException(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Journal:
    def __init__(self): self.lignes = []
    def _n(self, m, *a):
        try: self.lignes.append(str(m) % a if a else str(m))
        except Exception: self.lignes.append(str(m))
    info = warning = error = _n


def _match(doc, f):
    for k, v in (f or {}).items():
        if k == "$or":
            if not any(_match(doc, c) for c in v): return False
            continue
        d = doc.get(k)
        if isinstance(v, dict):
            if "$regex" in v:
                if not (isinstance(d, str) and re.match(v["$regex"], d, re.I)): return False
            if "$exists" in v and (k in doc) != v["$exists"]: return False
            if "$lt" in v and not (d is not None and str(d) < str(v["$lt"])): return False
        elif d != v:
            return False
    return True


class _Curseur:
    def __init__(self, docs, projection=None):
        self.docs = docs
        self.projection = projection or {}

    def sort(self, *a, **k): return self

    async def to_list(self, n=None):
        await asyncio.sleep(0)
        gardes = [c for c, v in self.projection.items() if v == 1 and c != "_id"]
        out = []
        for d in self.docs[: n or len(self.docs)]:
            out.append({c: d[c] for c in gardes if c in d} if gardes else dict(d))
        return out


class _Coll:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, f=None, p=None):
        return _Curseur([d for d in self.docs if _match(d, f)], p)

    async def find_one(self, f=None, p=None, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, f):
                gardes = [c for c, v in (p or {}).items() if v == 1 and c != "_id"]
                return {c: d[c] for c in gardes if c in d} if gardes else dict(d)
        return None

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": "x"})()

    async def update_one(self, f, u, **k):
        await asyncio.sleep(0)
        cible = next((d for d in self.docs if _match(d, f)), None)
        if cible is None:
            return type("R", (), {"matched_count": 0})()
        cible.update(u.get("$set") or {})
        for c in (u.get("$unset") or {}):
            cible.pop(c, None)
        return type("R", (), {"matched_count": 1})()


class _Base:
    def __init__(self, comments=None, contacts=None, resas=None):
        self.comments = _Coll(comments)
        self.chat_participants = _Coll(contacts)
        self.reservations = _Coll(resas)


class _Requete:
    def __init__(self, params=None, corps=None):
        self.query_params = params or {}
        self._corps = corps or {}

    async def json(self): return self._corps


BAC = {}
COACH = "coach@x.io"


def bac(comments=None, contacts=None, resas=None, coach=COACH, admin=True,
        refus=None, resolveur=None):
    base = _Base(comments, contacts, resas)
    journal = _Journal()
    POSTHOG[:] = []

    async def _garde(request):
        await asyncio.sleep(0)
        if refus:
            raise _HTTPException(status_code=refus, detail="refuse")
        return coach

    async def _resolve(code):
        await asyncio.sleep(0)
        if resolveur is not None:
            return resolveur(code)
        return (True, "Marie Dupont", COACH)

    g = {
        "__builtins__": __builtins__, "datetime": datetime, "timezone": timezone,
        "re": re, "db": base, "logger": journal,
        "HTTPException": _HTTPException, "Request": _Requete,
        "DEFAULT_COACH_ID": COACH,
        "is_super_admin": lambda e: bool(admin),
        "_n1b3b2_coach_appelant": _garde,
        "_v261_resolve_subscriber": _resolve,
        "_random": __import__("random"),
    }
    exec(compile(SOURCE, "<t3>", "exec"), g)
    BAC.clear(); BAC.update(g)
    return g, base, journal


def contact(mail="marie@x.io", type_=None, cid="c1"):
    d = {"id": cid, "email": mail, "name": "Marie Dupont"}
    if type_: d["contact_type"] = type_
    return d


def temoignage(etat="pending", consent=True, identite=False, tid="t1", code="AFR-A"):
    return {"id": tid, "source": "participant_testimonial", "text": "Super expérience.",
            "user_name": "Marie Dupont", "participant_code": code, "coach_id": COACH,
            "moderation_status": etat, "consent_publication": consent,
            "consent_identity": identite, "is_visible": etat == "approved" and consent,
            "created_at": "2026-08-17T10:00:00+00:00"}


# ════════════════════════════════════════════════════════════════════════════
#          E — QUI VOIT L'INVITATION (contact_type SEUL)
# ════════════════════════════════════════════════════════════════════════════
async def eligibilite():
    g, _, _ = bac(contacts=[contact(type_="participant")])
    e = await g["t3_eligibilite"]("AFR-A", "marie@x.io")
    verifier("E1. contact classe « participant » -> invitation",
             e["eligible"] is True and e["contact_type"] == "participant", str(e))

    for _t in ("prospect", "partner", "other"):
        g, _, _ = bac(contacts=[contact(type_=_t)])
        e = await g["t3_eligibilite"]("AFR-A", "marie@x.io")
        verifier("E2. contact « %s » -> AUCUNE invitation" % _t,
                 e["eligible"] is False and e["contact_type"] == _t, str(e))

    g, _, _ = bac(contacts=[contact()])
    e = await g["t3_eligibilite"]("AFR-A", "marie@x.io")
    verifier("E3. contact NON CLASSE -> aucune invitation, et « absent » "
             "n'est pas « other »",
             e["eligible"] is False and e["contact_type"] is None, str(e))

    g, _, _ = bac(contacts=[])
    verifier("E4. absent des Contacts -> aucune invitation",
             (await g["t3_eligibilite"]("AFR-A", "inconnu@x.io"))["eligible"] is False)

    # LE TEST CENTRAL : un nouveau venu possede deja un code et un forfait.
    g, base, _ = bac(contacts=[], resas=[{"userEmail": "neuf@x.io", "validated": True}])
    e = await g["t3_eligibilite"]("AFR-NEUF", "neuf@x.io")
    verifier("E5. un nouveau participant, meme avec code, forfait et presence, "
             "n'est PAS invite tant que le coach ne l'a pas classe",
             e["eligible"] is False, str(e))

    g, _, _ = bac(contacts=[dict(contact(), contact_type="PARTICIPANT")])
    verifier("E6. la casse est normalisee",
             (await g["t3_eligibilite"]("AFR-A", "marie@x.io"))["eligible"] is True)
    g, _, _ = bac(contacts=[dict(contact(), contact_type="ancien")])
    verifier("E7. une valeur hors bareme ne vaut pas participant",
             (await g["t3_eligibilite"]("AFR-A", "marie@x.io"))["eligible"] is False)

    # deja temoigne -> plus sollicite
    g, _, _ = bac(comments=[temoignage()], contacts=[contact(type_="participant")])
    e = await g["t3_eligibilite"]("AFR-A", "marie@x.io")
    verifier("E8. qui a deja temoigne n'est plus sollicite",
             e["already_submitted"] is True and e["status"] == "pending", str(e))

    _nu = code_nu("t3_eligibilite")
    verifier("S1. AUCUNE deduction : ni reservation, ni forfait, ni code, ni source",
             not any(m in _nu for m in ("reservations", "subscriptions",
                                        "discount_codes", "source")), "")


# ════════════════════════════════════════════════════════════════════════════
#                    S — SOUMISSION
# ════════════════════════════════════════════════════════════════════════════
async def soumission():
    g, base, j = bac()
    r = await g["t3_soumettre"](_Requete(corps={
        "code": "AFR-A", "text": "Une heure qui m'a fait du bien.",
        "consent_publication": True, "consent_identity": True,
        "consent_text": "J'autorise…", "offer_id": "off-1"}))
    d = base.comments.docs[0]
    verifier("S2. un temoignage arrive EN ATTENTE", r["status"] == "pending"
             and d["moderation_status"] == "pending")
    verifier("S3. et n'est JAMAIS visible a la creation", d["is_visible"] is False)
    verifier("S4. il porte le marqueur qui le separe des commentaires IA",
             d["source"] == "participant_testimonial" and d["is_ai"] is False)
    verifier("S5. le nom vient de la BASE, pas du corps de la requete",
             d["user_name"] == "Marie Dupont")
    verifier("S6. le consentement est horodate",
             d["consent_publication"] is True and d["consented_at"])
    verifier("S7. aucune note n'est fabriquee", "rating" not in d)
    verifier("S8. le code n'apparait pas en clair dans le journal",
             not any("AFR-A," in l or "AFR-A)" in l for l in j.lignes), str(j.lignes))

    # un client ne peut pas se faire passer pour un autre
    g, base, _ = bac()
    await g["t3_soumettre"](_Requete(corps={
        "code": "AFR-A", "text": "x", "user_name": "Quelqu un d autre",
        "is_visible": True, "moderation_status": "approved"}))
    d = base.comments.docs[0]
    verifier("S9. un client ne peut ni choisir son nom, ni s'auto-approuver, "
             "ni se rendre visible",
             d["user_name"] == "Marie Dupont" and d["is_visible"] is False
             and d["moderation_status"] == "pending", str(d)[:120])

    # code invalide -> refus
    g, _, _ = bac(resolveur=lambda c: (False, "", None))
    try:
        await g["t3_soumettre"](_Requete(corps={"code": "AFR-FAUX", "text": "x"}))
        verifier("S10. un code invalide est refuse", False, "aucune exception")
    except _HTTPException as e:
        verifier("S10. un code invalide est refuse (le trou d'avant ce lot)",
                 e.status_code == 403)

    # doublon
    g, _, _ = bac(comments=[temoignage()])
    try:
        await g["t3_soumettre"](_Requete(corps={"code": "AFR-A", "text": "x"}))
        verifier("S11. un second temoignage est refuse", False, "aucune exception")
    except _HTTPException as e:
        verifier("S11. un second temoignage du meme code est refuse", e.status_code == 409)

    for _corps, _nom in (({"code": "AFR-A", "text": ""}, "vide"),
                         ({"code": "AFR-A", "text": "x" * 2000}, "trop long")):
        g, _, _ = bac()
        try:
            await g["t3_soumettre"](_Requete(corps=_corps))
            verifier("S12. texte %s refuse" % _nom, False, "accepte")
        except _HTTPException as e:
            verifier("S12. texte %s refuse" % _nom, e.status_code == 400)

    # Une soumission REUSSIE juste avant l'assertion : les refus ci-dessus
    # n'emettent rien, et `bac()` remet le mouchard a zero a chaque fois.
    g, _, _ = bac()
    await g["t3_soumettre"](_Requete(corps={
        "code": "AFR-A", "text": "Un texte tres personnel que PostHog ne doit jamais voir.",
        "consent_publication": True, "offer_id": "off-1"}))
    verifier("PH0. l'evenement de soumission est bien emis",
             any(p["event"] == "testimonial_submitted" for p in POSTHOG), str(POSTHOG)[:120])
    verifier("PH1. AUCUN texte libre, nom, adresse ni code dans PostHog",
             POSTHOG and all(
                 "text" not in p["props"] and "user_name" not in p["props"]
                 and not p["email"] and "AFR-" not in str(p)
                 and "tres personnel" not in str(p) and "Marie" not in str(p)
                 for p in POSTHOG), str(POSTHOG)[:160])


# ════════════════════════════════════════════════════════════════════════════
#              M — MODERATION ET AFFICHAGE PUBLIC
# ════════════════════════════════════════════════════════════════════════════
async def moderation():
    IA = {"id": "ai1", "text": "Génial !", "is_ai": True, "is_visible": True,
          "user_name": "Bot", "created_at": "2026-01-01"}

    # pending -> jamais public
    g, _, _ = bac(comments=[temoignage("pending"), IA])
    r = await g["t3_publics"](_Requete())
    verifier("M1. un temoignage EN ATTENTE n'apparait jamais",
             r["testimonials"] == [], str(r))
    verifier("M2. et aucun commentaire IA ne peut passer par cette porte",
             not any("Génial" in str(t) for t in r["testimonials"]))

    # approuve SANS consentement -> jamais public
    g, base, _ = bac(comments=[temoignage("approved", consent=False)])
    verifier("M3. approuve SANS consentement -> jamais public",
             (await g["t3_publics"](_Requete()))["testimonials"] == [])

    # approuve AVEC consentement -> public
    g, _, _ = bac(comments=[temoignage("approved", consent=True, identite=True)])
    r = await g["t3_publics"](_Requete())
    verifier("M4. approuve + consenti + visible -> public",
             len(r["testimonials"]) == 1, str(r))
    verifier("M4b. le prenom SEUL est affiche, jamais le nom complet",
             r["testimonials"][0].get("user_name") == "Marie", str(r["testimonials"][0]))

    g, _, _ = bac(comments=[temoignage("approved", consent=True, identite=False)])
    r = await g["t3_publics"](_Requete())
    verifier("M5. sans consentement d'identite -> aucun prenom rendu",
             "user_name" not in r["testimonials"][0], str(r["testimonials"][0]))

    g, _, _ = bac(comments=[temoignage("hidden", consent=True)])
    verifier("M6. masque -> jamais public",
             (await g["t3_publics"](_Requete()))["testimonials"] == [])

    # le cycle complet
    g, base, _ = bac(comments=[temoignage("pending")])
    await g["t3_moderer"]("t1", _Requete(corps={"status": "approved"}))
    verifier("M7. approuver rend visible", base.comments.docs[0]["is_visible"] is True)
    verifier("M7b. et l'evenement d'approbation est emis",
             any(p["event"] == "testimonial_approved" for p in POSTHOG))
    await g["t3_moderer"]("t1", _Requete(corps={"status": "hidden"}))
    verifier("M8. masquer apres publication -> disparait",
             base.comments.docs[0]["is_visible"] is False
             and (await g["t3_publics"](_Requete()))["testimonials"] == [])
    verifier("M9. et il ne revient JAMAIS seul : seul un appel explicite "
             "a `approved` le republie",
             base.comments.docs[0]["moderation_status"] == "hidden")
    await g["t3_moderer"]("t1", _Requete(corps={"status": "approved"}))
    verifier("M9b. la re-approbation est une action explicite, et elle marche",
             base.comments.docs[0]["is_visible"] is True)

    # approuver un non-consenti ne le publie pas
    g, base, _ = bac(comments=[temoignage("pending", consent=False)])
    await g["t3_moderer"]("t1", _Requete(corps={"status": "approved"}))
    verifier("M10. approuver un temoignage NON consenti ne le rend pas visible",
             base.comments.docs[0]["is_visible"] is False)

    for _mauvais in ("public", "", "APPROVED", "supprime"):
        g, _, _ = bac(comments=[temoignage()])
        try:
            await g["t3_moderer"]("t1", _Requete(corps={"status": _mauvais}))
            verifier("M11. etat « %s » refuse" % _mauvais, False, "accepte")
        except _HTTPException as e:
            verifier("M11. etat de moderation « %s » refuse" % _mauvais, e.status_code == 400)

    # la moderation est impossible sans identite coach
    for _code in (401, 403):
        g, _, _ = bac(comments=[temoignage()], refus=_code)
        try:
            await g["t3_moderer"]("t1", _Requete(corps={"status": "approved"}))
            verifier("M12. moderation refusee en %d" % _code, False, "aucune exception")
        except _HTTPException as e:
            verifier("M12. moderer exige une identite coach (%d)" % _code,
                     e.status_code == _code)
        g2, _, _ = bac(comments=[temoignage()], refus=_code)
        try:
            await g2["t3_liste_coach"](_Requete())
            verifier("M12b. la liste de moderation aussi (%d)" % _code, False, "")
        except _HTTPException as e:
            verifier("M12b. la liste de moderation exige la meme identite (%d)" % _code,
                     e.status_code == _code)


# ════════════════════════════════════════════════════════════════════════════
#                    P — PII ET PROJECTION
# ════════════════════════════════════════════════════════════════════════════
async def confidentialite():
    _sale = dict(temoignage("approved", consent=True, identite=True),
                 participant_code="AFR-SECRET", session_id="sess-9",
                 email="marie@x.io", whatsapp="+41760000000",
                 consented_at="2026-08-17", moderated_by="coach@x.io")
    g, _, _ = bac(comments=[_sale])
    r = await g["t3_publics"](_Requete())
    _txt = str(r)
    verifier("P1. aucun code, aucune adresse, aucun telephone, aucun "
             "identifiant interne dans la reponse publique",
             not any(x in _txt for x in ("AFR-SECRET", "marie@x.io", "+4176",
                                         "sess-9", "coach@x.io")), _txt[:180])
    verifier("P2. aucune donnee de moderation ni de consentement brut",
             not any(k in r["testimonials"][0] for k in
                     ("moderation_status", "consent_publication", "consent_identity",
                      "consented_at", "moderated_by", "coach_id", "is_visible")),
             str(sorted(r["testimonials"][0])))
    verifier("P3. la reponse se limite au texte, a la date, a l'id et au prenom",
             set(r["testimonials"][0]) <= {"id", "text", "created_at", "user_name"},
             str(sorted(r["testimonials"][0])))

    g, _, _ = bac(comments=[_sale])
    lc = await g["t3_liste_coach"](_Requete())
    verifier("P4. meme le COACH ne recoit pas le code d'acces : il n'en a pas "
             "besoin pour moderer, et c'est le mot de passe de la personne",
             "participant_code" not in lc["testimonials"][0],
             str(sorted(lc["testimonials"][0])))


# ════════════════════════════════════════════════════════════════════════════
#            C — CLASSEMENT DES CONTACTS ET SUGGESTIONS
# ════════════════════════════════════════════════════════════════════════════
async def contacts():
    g, base, _ = bac(contacts=[contact()])
    await g["t3_classer_contact"]("c1", _Requete(corps={"contact_type": "participant"}))
    verifier("C1. le coach classe un contact", base.chat_participants.docs[0]["contact_type"] == "participant")
    verifier("C1b. et la trace de qui l'a fait est gardee",
             base.chat_participants.docs[0].get("contact_type_set_by") == COACH)
    await g["t3_classer_contact"]("c1", _Requete(corps={"contact_type": ""}))
    verifier("C2. declasser RETIRE le champ — « absent » n'est pas « other »",
             "contact_type" not in base.chat_participants.docs[0])
    try:
        await g["t3_classer_contact"]("c1", _Requete(corps={"contact_type": "ancien"}))
        verifier("C3. valeur hors bareme refusee", False, "acceptee")
    except _HTTPException as e:
        verifier("C3. une valeur hors bareme est refusee", e.status_code == 400)
    try:
        await g["t3_classer_contact"]("inconnu", _Requete(corps={"contact_type": "participant"}))
        verifier("C4. contact inconnu -> 404", False, "aucune exception")
    except _HTTPException as e:
        verifier("C4. un contact inconnu ne se classe pas", e.status_code == 404)

    # suggestions : LECTURE SEULE
    g, base, _ = bac(contacts=[contact(), contact("paul@x.io", "prospect", "c2")],
                     resas=[{"userEmail": "marie@x.io", "validated": True,
                             "validatedAt": "2026-04-02T18:00:00+00:00", "coach_id": COACH},
                            {"userEmail": "paul@x.io", "validated": True,
                             "validatedAt": "2026-04-03T18:00:00+00:00", "coach_id": COACH},
                            {"userEmail": "zoe@x.io", "validated": True,
                             "validatedAt": "2026-04-04T18:00:00+00:00", "coach_id": COACH}])
    r = await g["t3_suggestions_participant"](_Requete())
    _ids = [s["contact_id"] for s in r["suggestions"]]
    verifier("C5. suggestion pour un contact NON classe avec presence confirmee",
             _ids == ["c1"], str(r["suggestions"]))
    verifier("C5b. aucune suggestion pour un contact deja classe", "c2" not in _ids)
    verifier("C5c. aucune suggestion pour une presence sans contact", len(_ids) == 1)
    verifier("C5d. la raison est donnee",
             r["suggestions"][0]["raison"] == "présence confirmée")
    verifier("C6. AUCUNE ecriture : les contacts sont inchanges",
             "contact_type" not in base.chat_participants.docs[0]
             and base.chat_participants.docs[1]["contact_type"] == "prospect")
    verifier("C6b. et la route le dit elle-meme", "Lecture seule" in r["note"])


def structure():
    _src = SOURCE
    verifier("S13. la soumission ne publie jamais : is_visible faux par defaut",
             "'is_visible': False" in code_nu("t3_soumettre").replace('"', "'"))
    verifier("S14. la lecture publique exige les TROIS conditions",
             all(m in code_nu("t3_publics") for m in
                 ("T3_MARQUEUR", "consent_publication", "T3_APPROVED")))
    verifier("S15. la visibilite exige le consentement A L'ECRITURE aussi",
             "consent_publication" in code_nu("t3_moderer"))
    verifier("S16. les valeurs stockees sont en anglais",
             ast.literal_eval(ast.unparse(_NOEUDS["T3_TYPES_CONTACT"]).split("=", 1)[1].strip())
             == ("participant", "prospect", "partner", "other"))
    verifier("S17. les suggestions n'ecrivent rien",
             not any(m in code_nu("t3_suggestions_participant")
                     for m in ("update_one", "insert_one", "$set")))
    verifier("S18. aucun commentaire IA n'est touche par ce lot",
             "is_ai" not in code_nu("t3_moderer")
             and "is_ai" not in code_nu("t3_publics"))

    moi = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    mods = set()
    for n in ast.walk(ast.parse(moi)):
        if isinstance(n, ast.Import):
            mods.update(x.name.split(".")[0] for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            mods.add(n.module.split(".")[0])
    verifier("S19. ce test n'importe que la bibliotheque standard, hors reseau",
             mods <= {"ast", "asyncio", "io", "os", "re", "sys", "types", "datetime"},
             str(sorted(mods)))


def main():
    structure()
    b = asyncio.new_event_loop()
    try:
        b.run_until_complete(eligibilite())
        b.run_until_complete(soumission())
        b.run_until_complete(moderation())
        b.run_until_complete(confidentialite())
        b.run_until_complete(contacts())
    finally:
        b.close()
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 78)
    for nom, r, detail in RESULTATS:
        print(("  PASS  " if r else "  FAIL  ") + nom + (("   -> " + detail) if not r else ""))
    print("=" * 78)
    print("Temoignages / contacts REELS : 0 — base en memoire")
    print("%d/%d verifications" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""LOT B3-S1.1 — PROUVER QU'ON POSSEDE SON E-MAIL, PAS SEULEMENT SON CODE.

CE QUE CE LOT AJOUTE, ET CE QU'IL NE FAIT PAS. Il ajoute un OTP par e-mail et
un jeton d'espace revocable. Il NE DURCIT RIEN : `get_subscriber_space`,
`/subscriber/token`, `/subscriber/recover` et le frontend sont intacts.

POURQUOI IL EXISTE. `GET /api/subscriber/space/{code}` sert e-mail, telephone,
objectifs, solde, reservations et liste des membres a qui connait le code — et
37 des 63 codes en base sont des libelles lisibles du type prenom + annee. Le
jeton V296 ne pouvait pas servir de preuve : `POST /subscriber/token` n'exige
que le code, son controle d'appartenance etant conditionne par `if email:`
(api/server.py:32499). Un jeton derive du secret qu'il protege ne protege rien.

AUCUN E-MAIL REEL N'EST ENVOYE : `_RESEND_OK` est force a False, et un mouchard
compte les envois pour le PROUVER, cas par cas.

AUCUNE BASE REELLE, AUCUN RESEAU, AUCUNE DONNEE PERSONNELLE.
    python3 tests/test_lotb3s1_otp_identite.py
"""
import ast, asyncio, importlib.util, io, os, re, sys, types
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

os.environ.setdefault("JWT_SECRET", "secret-de-banc-uniquement")

_spec = importlib.util.spec_from_file_location(
    "b3s1_shared", os.path.join(RACINE, "api", "routes", "shared.py"))
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)

RESULTATS = []


def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


CODE = "SYNTHCODE-1"
MAIL = "membre@exemple.invalid"
AUTRE = "voisin@exemple.invalid"
COACH = "coach-synthetique"
ENVOIS = []                      # le mouchard : tout e-mail « parti » atterrit ici


# ═════════════════════ faux Mongo minimal (montage local) ════════════════════
def _corr(doc, filtre):
    for cle, cond in (filtre or {}).items():
        v = doc.get(cle)
        if isinstance(cond, dict):
            if "$regex" in cond:
                if not re.search(cond["$regex"], str(v or ""), re.I):
                    return False
            if "$gte" in cond and not (str(v or "") >= str(cond["$gte"])):
                return False
        elif v != cond:
            return False
    return True


class Coll:
    def __init__(self):
        self.docs = []

    async def insert_one(self, d):
        self.docs.append(dict(d))
        return types.SimpleNamespace(inserted_id="x")

    async def find_one(self, filtre, projection=None, sort=None):
        c = [d for d in self.docs if _corr(d, filtre)]
        if sort:
            cle, sens = sort[0]
            c.sort(key=lambda d: str(d.get(cle) or ""), reverse=(sens < 0))
        return dict(c[0]) if c else None

    async def count_documents(self, filtre):
        return len([d for d in self.docs if _corr(d, filtre)])

    async def update_one(self, filtre, maj):
        for d in self.docs:
            if _corr(d, filtre):
                d.update(maj.get("$set", {}))
                for k, p in (maj.get("$inc") or {}).items():
                    d[k] = int(d.get(k) or 0) + int(p)
                return types.SimpleNamespace(modified_count=1)
        return types.SimpleNamespace(modified_count=0)


class Base:
    def __init__(self):
        self.discount_codes = Coll()
        self.subscriptions = Coll()
        self.code_members = Coll()
        self._extra = {}

    def __getitem__(self, nom):
        if nom not in self._extra:
            self._extra[nom] = Coll()
        return self._extra[nom]


class Req:
    def __init__(self, corps):
        self._c = corps

    async def json(self):
        return self._c


class Journal:
    def __init__(self):
        self.lignes = []

    def _n(self, m, a):
        try:
            self.lignes.append((str(m) % a) if a else str(m))
        except (TypeError, ValueError):
            self.lignes.append(str(m))

    def info(self, m="", *a, **k):
        self._n(m, a)

    def warning(self, m="", *a, **k):
        self._n(m, a)

    def error(self, m="", *a, **k):
        self._n(m, a)


class HTTPExc(Exception):
    def __init__(self, status_code=500, detail="", headers=None):
        self.status_code, self.detail = status_code, detail
        super().__init__(str(detail))


def espace(db):
    """Les VRAIES routes, extraites du vrai `server.py`."""
    src = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    arbre, lignes = ast.parse(src), src.splitlines(True)
    faux_resend = types.ModuleType("resend")
    faux_resend.api_key = ""
    faux_resend.Emails = types.SimpleNamespace(send=lambda p: ENVOIS.append(p))
    sys.modules["resend"] = faux_resend
    ns = {"db": db, "re": re, "datetime": datetime, "timezone": timezone,
          "timedelta": timedelta, "asyncio": asyncio, "uuid": __import__("uuid"),
          "logger": Journal(), "HTTPException": HTTPExc, "Request": object,
          "DEFAULT_COACH_ID": COACH,
          # AUCUN e-mail reel : la garde d'envoi est fermee, et le mouchard
          # ci-dessus prouve que rien ne part meme si elle s'ouvrait.
          "_RESEND_OK": False, "_RESEND_KEY": ""}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in (
                "_B3S1_COLL_OTP", "_B3S1_COLL_SESSIONS"):
            exec(compile("".join(lignes[n.lineno - 1:n.end_lineno]), "s", "exec"), ns)
    for nom in ("_b3s1_contact_enregistre", "b3s1_demander_otp", "b3s1_verifier_otp"):
        for n in ast.walk(arbre):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
                exec(compile("".join(lignes[n.lineno - 1:n.end_lineno]), "s", "exec"), ns)
    return ns


def monde(assigned=MAIL, membres=None):
    db = Base()
    db.discount_codes.docs.append(
        {"code": CODE, "assignedEmail": assigned, "coach_id": COACH, "active": True})
    db.subscriptions.docs.append(
        {"code": CODE, "email": assigned, "coach_id": COACH, "status": "active"})
    for m in (membres or []):
        db.code_members.docs.append(dict(m, code=CODE))
    return db


async def demander(ns, **corps):
    try:
        return await ns["b3s1_demander_otp"](Req(corps)), None
    except HTTPExc as e:
        return None, e


async def verifier_otp(ns, **corps):
    try:
        return await ns["b3s1_verifier_otp"](Req(corps)), None
    except HTTPExc as e:
        return None, e


def otp_de(db, code=CODE, slug=""):
    """Retrouve l'OTP en clair en le RE-DERIVANT — le banc ne peut pas le lire
    en base, puisque seule l'empreinte y est stockee. C'est la preuve que le
    stockage est bien hache."""
    d = [x for x in db["subscriber_otp"].docs
         if x.get("code") == code and x.get("slug") == (slug or "") and x.get("envoye")]
    if not d:
        return None
    emp = d[-1].get("otp_empreinte")
    for n in range(1000000):
        c = "%06d" % n
        if S.lotb3s1_empreinte(c, code) == emp:
            return c
    return None


async def principal():
    # ══ 1. DEMANDE VALIDE ══════════════════════════════════════════════════
    ENVOIS.clear()
    db = monde()
    ns = espace(db)
    rep, err = await demander(ns, code=CODE, email=MAIL)
    verifier("1. demande acceptee", err is None and rep.get("success") is True, err)
    verifier("1. une ligne OTP est creee", len(db["subscriber_otp"].docs) == 1, "")
    d = db["subscriber_otp"].docs[0]
    verifier("1. l'OTP n'est PAS stocke en clair",
             "otp" not in d and "otp_empreinte" in d, sorted(d.keys()))
    verifier("1. la ligne porte une expiration et un compteur d'essais",
             d.get("expires_at") and d.get("essais") == 0 and d.get("used") is False, "")
    verifier("1. AUCUN e-mail reel n'est parti", ENVOIS == [], len(ENVOIS))
    verifier("1. aucun OTP ni adresse dans le journal",
             not any("@" in l or re.search(r"\b\d{6}\b", l) for l in ns["logger"].lignes),
             ns["logger"].lignes)

    # ══ 2. CODE OU E-MAIL INCONNU : AUCUN ORACLE ══════════════════════════
    db1 = monde(); ns1 = espace(db1)
    r1, _ = await demander(ns1, code=CODE, email=AUTRE)          # adresse fausse
    db2 = Base(); ns2 = espace(db2)
    r2, _ = await demander(ns2, code="CODE-INEXISTANT", email=MAIL)
    verifier("2. reponse IDENTIQUE pour adresse fausse et code inconnu",
             r1 == r2, (r1, r2))
    verifier("2. adresse fausse -> aucun OTP genere",
             db1["subscriber_otp"].docs[0].get("envoye") is False
             and "otp_empreinte" not in db1["subscriber_otp"].docs[0], "")
    verifier("2. ... mais la demande est comptee (limite de debit)",
             len(db1["subscriber_otp"].docs) == 1, "")

    # ══ 3. OTP INCORRECT, PUIS 5e TENTATIVE ═══════════════════════════════
    db = monde(); ns = espace(db)
    await demander(ns, code=CODE, email=MAIL)
    bon = otp_de(db)
    faux = "%06d" % ((int(bon) + 1) % 1000000)
    for i in range(4):
        _, err = await verifier_otp(ns, code=CODE, email=MAIL, otp=faux)
    verifier("3. OTP incorrect -> refus", err is not None and err.status_code == 400,
             getattr(err, "status_code", "accepte"))
    verifier("3. les tentatives sont comptees",
             db["subscriber_otp"].docs[0]["essais"] == 4,
             db["subscriber_otp"].docs[0]["essais"])
    _, err = await verifier_otp(ns, code=CODE, email=MAIL, otp=faux)
    verifier("3. 5e tentative -> refus", err is not None, "")
    rep, err = await verifier_otp(ns, code=CODE, email=MAIL, otp=bon)
    verifier("3. essais epuises : meme le BON code ne passe plus",
             err is not None and rep is None, rep)

    # ══ 4. EXPIRATION ═════════════════════════════════════════════════════
    db = monde(); ns = espace(db)
    await demander(ns, code=CODE, email=MAIL)
    bon = otp_de(db)
    db["subscriber_otp"].docs[0]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    rep, err = await verifier_otp(ns, code=CODE, email=MAIL, otp=bon)
    verifier("4. OTP expire -> refus", err is not None and rep is None, rep)

    # ══ 5. RENVOI TROP RAPIDE ET LIMITE DE DEBIT ══════════════════════════
    db = monde(); ns = espace(db)
    await demander(ns, code=CODE, email=MAIL)
    _, err = await demander(ns, code=CODE, email=MAIL)
    verifier("5. renvoi sous 2 min -> 429", err is not None and err.status_code == 429,
             getattr(err, "status_code", "accepte"))
    # On recule les horodatages pour franchir l'anti-renvoi sans franchir la fenetre.
    for x in db["subscriber_otp"].docs:
        x["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    await demander(ns, code=CODE, email=MAIL)
    for x in db["subscriber_otp"].docs:
        x["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    await demander(ns, code=CODE, email=MAIL)
    for x in db["subscriber_otp"].docs:
        x["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    _, err = await demander(ns, code=CODE, email=MAIL)
    verifier("5. 4e demande dans la fenetre de 10 min -> 429",
             err is not None and err.status_code == 429,
             getattr(err, "status_code", "accepte"))

    # ══ 6. USAGE UNIQUE : REJEU D'UN OTP CONSOMME ═════════════════════════
    db = monde(); ns = espace(db)
    await demander(ns, code=CODE, email=MAIL)
    bon = otp_de(db)
    rep, err = await verifier_otp(ns, code=CODE, email=MAIL, otp=bon)
    verifier("6. OTP correct -> jeton delivre",
             err is None and rep.get("token"), getattr(err, "detail", ""))
    rep2, err2 = await verifier_otp(ns, code=CODE, email=MAIL, otp=bon)
    verifier("6. rejeu du meme OTP -> refus", err2 is not None and rep2 is None, rep2)

    # ══ 7. LE JETON : CONTENU, APPARIEMENT, REVOCATION ════════════════════
    charge = S.lotb3s1_lire_token(rep["token"])
    verifier("7. le jeton est lisible et de type `subscriber_space`",
             charge and charge.get("type") == "subscriber_space", charge)
    verifier("7. il porte le code, l'e-mail ET le coach_id (V296 n'a pas le tenant)",
             charge.get("code") == CODE and charge.get("email") == MAIL
             and charge.get("coach_id") == COACH, charge)
    verifier("7. il porte un `jti` — sans quoi rien n'est revocable",
             bool(charge.get("jti")), "")
    sess = db["subscriber_sessions"].docs[-1]
    ok, motif = S.lotb3s1_session_utilisable(sess, charge)
    verifier("7. session ouverte -> utilisable", ok is True, motif)
    # revocation
    sess["revoked"] = True
    ok, motif = S.lotb3s1_session_utilisable(sess, charge)
    verifier("7. session revoquee -> refus", ok is False and motif == "revoquee", motif)
    sess["revoked"] = False
    sess["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    ok, motif = S.lotb3s1_session_utilisable(sess, charge)
    verifier("7. session expiree -> refus", ok is False and motif == "expiree", motif)
    sess["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    for cle, valeur in (("code", "AUTRECODE"), ("email", AUTRE), ("coach_id", "autre-coach")):
        copie = dict(sess); copie[cle] = valeur
        ok, motif = S.lotb3s1_session_utilisable(copie, charge)
        verifier("7. jeton inutilisable pour un autre %s" % cle,
                 ok is False and motif == "appariement_%s" % cle, motif)
    verifier("7. un jeton V296 n'est PAS accepte comme jeton d'espace",
             S.lotb3s1_lire_token(S.make_subscriber_token(CODE, MAIL)) is None, "")

    # ══ 8. GROUPE : AVEC ET SANS `m=slug` ═════════════════════════════════
    db = monde(assigned="", membres=[{"slug": "aaa", "email": MAIL},
                                     {"slug": "bbb", "email": AUTRE}])
    ns = espace(db)
    rep, err = await demander(ns, code=CODE, email=MAIL, m="aaa")
    d = [x for x in db["subscriber_otp"].docs if x.get("slug") == "aaa"]
    verifier("8. groupe avec slug : OTP envoye au MEMBRE designe",
             d and d[0].get("envoye") is True and d[0].get("email") == MAIL, d)
    rep, err = await demander(ns, code=CODE, email=MAIL, m="bbb")
    d = [x for x in db["subscriber_otp"].docs if x.get("slug") == "bbb"]
    verifier("8. groupe : l'adresse d'un AUTRE membre ne recoit rien",
             d and d[0].get("envoye") is False, d)
    verifier("8. la liste des membres n'est jamais renvoyee",
             all("members" not in (rep or {}) and "group_members" not in (rep or {})
                 for rep in [rep]), rep)
    # sans slug, sur un code de groupe sans assignedEmail : aucun contact
    db2 = monde(assigned="", membres=[{"slug": "aaa", "email": MAIL}])
    db2.subscriptions.docs[0]["email"] = ""
    ns2 = espace(db2)
    rep2, err2 = await demander(ns2, code=CODE, email=MAIL)
    d2 = db2["subscriber_otp"].docs
    verifier("8. groupe SANS slug -> aucun OTP, reponse neutre",
             err2 is None and d2 and d2[0].get("envoye") is False, d2)

    # ══ 9. CONNAITRE LE CODE SEUL NE SUFFIT PAS ═══════════════════════════
    db = monde(); ns = espace(db)
    rep, err = await demander(ns, code=CODE, email="")
    verifier("9. code seul, sans e-mail -> aucune ligne, aucune fuite",
             err is None and db["subscriber_otp"].docs == [], db["subscriber_otp"].docs)
    rep, err = await verifier_otp(ns, code=CODE, email=MAIL, otp="123456")
    verifier("9. et aucun jeton n'est delivrable sans OTP valide",
             err is not None and rep is None, rep)

    # ══ 10. AUCUN E-MAIL REEL SUR L'ENSEMBLE DU BANC ══════════════════════
    verifier("10. mouchard d'envoi : ZERO e-mail parti sur tout le banc",
             ENVOIS == [], len(ENVOIS))


# ══ 11. LES FONCTIONS PURES ══════════════════════════════════════════════
o = S.lotb3s1_generer_otp()
verifier("11. OTP : 6 chiffres", len(o) == 6 and o.isdigit(), o[:1] + "*****")
# Lecture par AST plutot que par fenetre de caracteres : une assertion qui
# depend d'une distance en octets casse au premier commentaire ajoute.
_src_shared = io.open(os.path.join(RACINE, "api", "routes", "shared.py"), encoding="utf-8").read()
_corps_gen = ""
for _n in ast.walk(ast.parse(_src_shared)):
    if isinstance(_n, (ast.FunctionDef, ast.AsyncFunctionDef)) and _n.name == "lotb3s1_generer_otp":
        _corps_gen = "".join(_src_shared.splitlines(True)[_n.lineno - 1:_n.end_lineno])
verifier("11. OTP : tire par `secrets`, jamais par `random`",
         "secrets" in _corps_gen and "random.choice" not in _corps_gen
         and "random.randint" not in _corps_gen, "")
verifier("11. empreinte : deux codes differents -> empreintes differentes",
         S.lotb3s1_empreinte("111111", "A") != S.lotb3s1_empreinte("111111", "B"), "")
verifier("11. empreinte : jamais l'OTP en clair",
         "111111" not in S.lotb3s1_empreinte("111111", "A"), "")
ok, m = S.lotb3s1_peut_demander(3, None)
verifier("11. 3 demandes atteintes -> refus", ok is False and m == "trop_de_demandes", m)
ok, m = S.lotb3s1_peut_demander(1, datetime.now(timezone.utc).isoformat())
verifier("11. renvoi immediat -> refus", ok is False and m == "renvoi_trop_rapide", m)
ok, m = S.lotb3s1_peut_demander(
    1, (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat())
verifier("11. renvoi apres 5 min -> autorise", ok is True, m)
verifier("11. aucune demande -> refus explicite",
         S.lotb3s1_otp_valide(None, "123456", "X") == (False, "aucune_demande"), "")

asyncio.get_event_loop().run_until_complete(principal())

echecs = [x for x in RESULTATS if not x[1]]
print("\nLOT B3-S1.1 — OTP E-MAIL ET JETON D'ESPACE (%d verifications)\n" % len(RESULTATS))
for nom, ok, detail in RESULTATS:
    print("  %s %-62s %s" % ("OK  " if ok else "ECHEC", nom, "" if ok else detail))
print("\n%d/%d au vert" % (len(RESULTATS) - len(echecs), len(RESULTATS)))
print("e-mails reellement envoyes pendant tout le banc : %d" % len(ENVOIS))
sys.exit(1 if echecs else 0)

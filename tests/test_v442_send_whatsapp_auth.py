# -*- coding: utf-8 -*-
"""V442 — la route POST /api/send-whatsapp exige un JWT super-admin signé.

Rien n'est simulé de la chaîne d'authentification : le code du handler, celui de
la garde `_v411_exiger_super_admin` et celui de `_v311_coach_email_from_jwt` sont
EXTRAITS de api/server.py par analyse AST et exécutés tels quels, avec un vrai
PyJWT et un vrai secret. Seul `send_whatsapp_direct` est remplacé par un mouchard
qui ENREGISTRE l'appel au lieu d'envoyer — garantie qu'aucun WhatsApp ne part.

Aucun réseau, aucune base, aucun envoi.
Lancement :  python3 tests/test_v442_send_whatsapp_auth.py
"""
import ast, asyncio, io, os, sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = os.path.join(RACINE, "api", "server.py")
SOURCE = io.open(SERVEUR, encoding="utf-8").read()
ARBRE = ast.parse(SOURCE)
LIGNES = SOURCE.splitlines(True)

SECRET = "secret-de-test-v442-jamais-en-production-32o+"
ADMIN = "contact.artboost@gmail.com"
ADMIN2 = "afroboost.bassi@gmail.com"
COACH = "un.coach.partenaire@example.com"

RESULTATS = []
def verifier(nom, cond, detail=""):
    RESULTATS.append((nom, bool(cond), detail))


def code_nu(nom):
    """Le code EXECUTE d'une fonction, sans sa docstring ni ses commentaires.

    Indispensable : la docstring de `_v311_coach_email_from_jwt` contient la
    phrase « JAMAIS X-User-Email », et une simple recherche de texte y verrait
    une lecture de l'en-tete la ou il n'y a qu'une explication.
    """
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            corps = list(n.body)
            if (corps and isinstance(corps[0], ast.Expr)
                    and isinstance(getattr(corps[0], "value", None), ast.Constant)
                    and isinstance(corps[0].value.value, str)):
                corps = corps[1:]
            return "\n".join(ast.unparse(x) for x in corps)
    raise AssertionError("fonction introuvable : %s" % nom)


def extraire(nom):
    for n in ast.walk(ARBRE):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom:
            return "".join(LIGNES[n.lineno - 1:n.end_lineno])
    raise AssertionError("fonction introuvable : %s" % nom)


class HTTPException(Exception):
    def __init__(self, status_code=500, detail=""):
        self.status_code = status_code
        self.detail = detail
        Exception.__init__(self, "%s %s" % (status_code, detail))


class FausseRequete:
    """Le strict nécessaire de starlette.Request : des en-têtes insensibles à la casse."""
    def __init__(self, headers=None):
        self._h = {k.lower(): v for k, v in (headers or {}).items()}
        self.headers = self
    def get(self, cle, defaut=""):
        return self._h.get(cle.lower(), defaut)


class Payload:
    def __init__(self, to, message, mediaUrl=None):
        self.to, self.message, self.mediaUrl = to, message, mediaUrl


ENVOIS = []          # tout appel au moteur d'envoi atterrit ICI, jamais chez Meta

async def faux_send_whatsapp_direct(to_phone=None, message=None, media_url=None, **kw):
    ENVOIS.append({"to_phone": to_phone, "message": message, "media_url": media_url, "extra": kw})
    return {"status": "simulated-par-le-test", "to": to_phone}


def construire():
    os.environ["JWT_SECRET"] = SECRET
    bac = {
        "os": os, "HTTPException": HTTPException, "Request": FausseRequete,
        "SendWhatsAppRequest": Payload,
        "SUPER_ADMIN_EMAILS": [ADMIN, ADMIN2],
        "send_whatsapp_direct": faux_send_whatsapp_direct,
        "logger": type("l", (), {"warning": staticmethod(lambda *a, **k: None),
                                 "info": staticmethod(lambda *a, **k: None)}),
        "api_router": type("r", (), {"post": staticmethod(lambda *a, **k: (lambda f: f))}),
    }
    code = "\n".join([extraire("is_super_admin"),
                      extraire("_v311_coach_email_from_jwt"),
                      extraire("_v411_exiger_super_admin"),
                      extraire("send_whatsapp_message")])
    exec(compile(code, "<v442-extrait-de-server.py>", "exec"), bac)
    return bac


def jeton(email, secret=SECRET, type_=None, exp=None):
    import jwt as pyjwt
    corps = {"email": email}
    if type_: corps["type"] = type_
    if exp: corps["exp"] = exp
    return pyjwt.encode(corps, secret, algorithm="HS256")


async def appeler(bac, headers, to="+41791234567", message="Test"):
    """Renvoie ('ok', resultat) ou ('refus', code_http)."""
    try:
        r = await bac["send_whatsapp_message"](Payload(to, message), FausseRequete(headers))
        return ("ok", r)
    except HTTPException as e:
        return ("refus", e.status_code)


async def scenario():
    bac = construire()
    B = lambda t: {"Authorization": "Bearer " + t}

    # ---------- TESTS BLOQUANTS : ce qui doit être REFUSÉ ----------
    refus = [
        ("anonyme (aucun en-tete)", {}),
        ("X-User-Email forge d'un super-admin", {"X-User-Email": ADMIN}),
        ("X-User-Email forge + Content-Type", {"X-User-Email": ADMIN, "Content-Type": "application/json"}),
        ("JWT signe d'un AUTRE secret", B(jeton(ADMIN, secret="mauvais-secret"))),
        ("JWT sans signature (alg=none simule)", B("eyJhbGciOiJub25lIn0.eyJlbWFpbCI6ImEifQ.")),
        ("jeton illisible", B("pas-du-tout-un-jwt")),
        ("Bearer vide", B("")),
        ("schema Basic au lieu de Bearer", {"Authorization": "Basic " + jeton(ADMIN)}),
        ("JWT valide mais d'un coach NON super-admin", B(jeton(COACH))),
        ("JWT valide mais de type abonne", B(jeton(ADMIN, type_="subscriber"))),
        ("JWT expire", B(jeton(ADMIN, exp=1))),
        ("JWT sans champ email", B(jeton(None))),
    ]
    for nom, h in refus:
        avant = len(ENVOIS)
        etat, val = await appeler(bac, h)
        verifier("REFUS  %s" % nom, etat == "refus" and val == 403, "%s %s" % (etat, val))
        verifier("       ^ et AUCUN envoi declenche", len(ENVOIS) == avant,
                 "%d envoi(s) parasite(s)" % (len(ENVOIS) - avant))

    # ---------- TESTS BLOQUANTS : ce qui doit PASSER ----------
    for nom, email in (("super-admin principal", ADMIN), ("second super-admin", ADMIN2)):
        avant = len(ENVOIS)
        etat, val = await appeler(bac, B(jeton(email)))
        verifier("PASSE  %s (JWT signe valide)" % nom, etat == "ok", "%s %s" % (etat, val))
        verifier("       ^ le moteur d'envoi est bien atteint", len(ENVOIS) == avant + 1, "")

    # casse de l'e-mail et espaces : le legitime ne doit pas etre refuse pour si peu
    etat, _ = await appeler(bac, B(jeton("  CONTACT.ArtBoost@Gmail.COM  ")))
    verifier("PASSE  super-admin avec casse/espaces differents", etat == "ok", etat)

    # ---------- LE PAYLOAD WHATSAPP EST INCHANGE ----------
    ENVOIS.clear()
    await bac["send_whatsapp_message"](
        Payload("+41791234567", "Bonjour {prenom}", "https://exemple.test/a.jpg"),
        FausseRequete(B(jeton(ADMIN))))
    verifier("PAYLOAD  un seul appel au moteur", len(ENVOIS) == 1, str(len(ENVOIS)))
    e = ENVOIS[0] if ENVOIS else {}
    verifier("PAYLOAD  to_phone transmis tel quel", e.get("to_phone") == "+41791234567", repr(e.get("to_phone")))
    verifier("PAYLOAD  message transmis tel quel", e.get("message") == "Bonjour {prenom}", repr(e.get("message")))
    verifier("PAYLOAD  media_url transmis tel quel", e.get("media_url") == "https://exemple.test/a.jpg", repr(e.get("media_url")))
    verifier("PAYLOAD  aucun argument supplementaire", e.get("extra") == {}, repr(e.get("extra")))

    # mediaUrl absent -> None, comme avant
    ENVOIS.clear()
    await bac["send_whatsapp_message"](Payload("+41790000000", "x"), FausseRequete(B(jeton(ADMIN))))
    verifier("PAYLOAD  media_url absent reste None", ENVOIS[0]["media_url"] is None, repr(ENVOIS[0]["media_url"]))

    # ---------- LE SECRET ABSENT NE DOIT PAS OUVRIR LA PORTE ----------
    ancien = os.environ.get("JWT_SECRET", "")
    os.environ["JWT_SECRET"] = ""
    avant = len(ENVOIS)
    etat, val = await appeler(bac, B(jeton(ADMIN)))
    verifier("REFUS  JWT_SECRET absent -> on ferme, on n'ouvre pas",
             etat == "refus" and val == 403, "%s %s" % (etat, val))
    verifier("       ^ et AUCUN envoi declenche", len(ENVOIS) == avant, "")
    os.environ["JWT_SECRET"] = ancien


def tests_structurels():
    n = None
    for x in ast.walk(ARBRE):
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == "send_whatsapp_message":
            n = x
    verifier("S1. le handler existe", n is not None)

    args = [a.arg for a in n.args.args]
    verifier("S2. le handler recoit bien un objet Request", "request" in args, str(args))
    verifier("S3. le corps est renomme `payload`", "payload" in args, str(args))
    annot = {a.arg: ast.unparse(a.annotation) for a in n.args.args if a.annotation}
    verifier("S4. `payload` est annote SendWhatsAppRequest (contrat d'API inchange)",
             annot.get("payload") == "SendWhatsAppRequest", str(annot))
    verifier("S5. `request` est annote Request", annot.get("request") == "Request", str(annot))

    corps = [x for x in n.body]
    if corps and isinstance(corps[0], ast.Expr) and isinstance(getattr(corps[0], "value", None), ast.Constant):
        corps = corps[1:]
    verifier("S6. la garde est la TOUTE PREMIERE instruction executee",
             corps and "_v411_exiger_super_admin" in ast.unparse(corps[0]),
             ast.unparse(corps[0])[:80] if corps else "corps vide")

    nu = "\n".join(ast.unparse(x) for x in corps)
    verifier("S7. plus aucune reference a `request.to/.message/.mediaUrl`",
             "request.to" not in nu and "request.message" not in nu and "request.mediaUrl" not in nu, nu)
    verifier("S8. le moteur d'envoi est appele avec les champs de `payload`",
             "payload.to" in nu and "payload.message" in nu and "payload.mediaUrl" in nu, nu)

    # Le moteur d'envoi lui-meme ne doit pas avoir bouge.
    src_moteur = extraire("send_whatsapp_direct")
    for interdit in ("_v411_exiger_super_admin", "Request", "Authorization", "HTTPException"):
        verifier("S9. send_whatsapp_direct intact (%s absent)" % interdit, interdit not in src_moteur, interdit)
    # Ce que V442 doit prouver, c'est que SON COMMIT n'a pas touche au moteur
    # d'envoi. On compare donc le commit V442 a SON PROPRE PARENT, et non l'arbre
    # de travail a un hachage fige : sinon le garde-fou tombe en panne des qu'un
    # correctif ULTERIEUR et parfaitement legitime touche l'une de ces fonctions.
    # C'est arrive des le lot suivant : V441 modifie `launch_campaign` a dessein
    # (il y retire l'indexation `results["skipped"]` qui tuait les campagnes).
    # L'invariant ci-dessous, lui, reste vrai pour toujours.
    import subprocess
    V442 = "5b4338b"

    def _src_au(rev, nom):
        texte = subprocess.check_output(
            ["git", "show", "%s:api/server.py" % rev], cwd=RACINE).decode("utf-8")
        lg = texte.splitlines(True)
        for x in ast.walk(ast.parse(texte)):
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) and x.name == nom:
                return "".join(lg[x.lineno - 1:x.end_lineno])
        return None

    for f in ("send_whatsapp_direct", "_send_whatsapp_meta", "_send_whatsapp_twilio",
              "launch_campaign", "_send_whatsapp_campaign_template",
              "handle_meta_whatsapp_webhook", "v434_envoyer"):
        verifier("S9b. le commit V442 n'a pas touche a %s" % f,
                 _src_au(V442 + "^", f) == _src_au(V442, f), "")

    # Et dans l'arbre courant, le moteur d'envoi lui-meme reste intact : c'est la
    # fonction que V442 ne doit JAMAIS modifier, quel que soit le lot en cours.
    verifier("S9c. send_whatsapp_direct intact dans l'arbre courant",
             _src_au(V442, "send_whatsapp_direct") == src_moteur, "")

    # La garde doit etre la MEME que celle de la route soeur fermee par V435.
    for soeur in ("send_whatsapp_template", "create_whatsapp_template"):
        try: s = extraire(soeur)
        except AssertionError: continue
        verifier("S10. %s utilise la meme garde (coherence)" % soeur,
                 "_v411_exiger_super_admin" in s, "")

    # La garde choisie ne doit accepter AUCUN repli X-User-Email.
    g = code_nu("_v311_coach_email_from_jwt")
    verifier("S11. la garde ne lit jamais X-User-Email comme identite",
             "X-User-Email" not in g, g)
    verifier("S12. la garde n'accepte que HS256 signe",
             "algorithms=['HS256']" in g or 'algorithms=["HS256"]' in g, g)
    # La garde de refus, elle, a le droit de LIRE X-User-Email : uniquement pour
    # le journaliser dans le message de refus. Verifions qu'elle ne s'en sert
    # jamais comme identite.
    ex = code_nu("_v411_exiger_super_admin")
    verifier("S12b. le refus journalise l'en-tete mais ne s'y fie pas",
             "revendique" in ex and "is_super_admin(appelant)" in ex, ex[:150])

    # Aucun appel interne ne doit passer par la ROUTE.
    appels_route = [ast.unparse(c) for c in ast.walk(ARBRE)
                    if isinstance(c, ast.Call) and "send_whatsapp_message(" in ast.unparse(c)]
    verifier("S13. aucun code backend n'appelle le handler de route",
             appels_route == [], " | ".join(appels_route))


def main():
    tests_structurels()
    asyncio.get_event_loop().run_until_complete(scenario())
    ok = sum(1 for _, r, _ in RESULTATS if r)
    print("=" * 74)
    for nom, r, detail in RESULTATS:
        print(("  OK   " if r else "  ECHEC") + "  " + nom + (("   -> " + detail) if not r else ""))
    print("=" * 74)
    print("Envois WhatsApp REELS declenches par cette suite : 0 (moteur remplace par un mouchard)")
    print("%d/%d tests passes" % (ok, len(RESULTATS)))
    return 0 if ok == len(RESULTATS) else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""V563 — OTP de l'espace abonné : chaque demande laisse UNE trace serveur.

URGENCE DU 30/09/2026. « Le code n'arrive plus. » Resend était sain (domaine
vérifié, envois délivrés), et le vrai gestionnaire, dans le vrai module,
envoyait bien l'e-mail. Mais une demande SANS envoi — adresse non reconnue,
envoi désactivé, erreur du fournisseur — ne laissait aucune ligne exploitable :
impossible de dire, depuis les journaux, où la chaîne cassait.

CE BANC IMPORTE LE VRAI `api.server` (et non des tranches de texte : un banc
qui reconstruit la fonction peut fournir lui-même un nom absent de la
production — cf. B3-S1.2D). Base et Resend simulés, aucun réseau, aucun e-mail.
    python3 tests/test_v563_otp_observabilite.py
"""
import asyncio, logging, os, re, sys, types

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.update(MONGO_URL="mongodb://127.0.0.1:1", JWT_SECRET="secret-de-banc",
                  RESEND_API_KEY="re_banc_factice", DB_NAME="banc_v562")

# Faux Mongo du banc B3-S1 (on n'exécute que ses classes, pas ses tests).
_src = open(os.path.join(RACINE, "tests", "test_lotb3s1_otp_identite.py"), encoding="utf-8").read()
F = {"__file__": os.path.join(RACINE, "tests", "x.py")}
exec(_src.split("def espace(db):")[0], F)

import api.server as S   # noqa: E402
import resend            # noqa: E402

JOURNAL = []


class _Capte(logging.Handler):
    def emit(self, rec):
        JOURNAL.append(rec.getMessage())


S.logger.addHandler(_Capte())
S.logger.setLevel(logging.INFO)

ENVOIS, MODE = [], {"echec": False}


def _faux_send(p):
    if MODE["echec"]:
        raise Exception("The afroboost.com domain is not verified")
    ENVOIS.append(p)
    return {"id": "resend-id-banc"}


resend.Emails.send = staticmethod(_faux_send)
RES = []


def ok(nom, cond):
    RES.append((nom, bool(cond)))


def traces(resultat):
    return [l for l in JOURNAL if "subscriber_otp_request" in l and ("result=%s " % resultat) in l]


def otp_du_dernier_mail():
    return re.search(r">(\d{6})<", ENVOIS[-1]["html"]).group(1)


async def main():
    S.db = db = F["Base"]()
    await db.discount_codes.insert_one({"code": "SYNTH-1", "assignedEmail": "membre@exemple.invalid",
                                        "coach_id": "c1"})
    await db.discount_codes.insert_one({"code": "SYNTH-2", "assignedEmail": "autre@exemple.invalid",
                                        "coach_id": "c1"})
    await db.discount_codes.insert_one({"code": "SYNTH-3", "assignedEmail": "titulaire@exemple.invalid",
                                        "coach_id": "c1"})
    Req = F["Req"]

    # A + B — demande valide, fournisseur OK
    r = await S.b3s1_demander_otp(Req({"code": "synth-1", "email": "Membre@Exemple.invalid"}))
    neutre = r
    lignes = db["subscriber_otp"].docs
    ok("A. demande valide -> ligne OTP avec empreinte (jamais l'OTP en clair)",
       len(lignes) == 1 and lignes[0].get("otp_empreinte") and lignes[0].get("envoye") is True)
    ok("B. fournisseur OK -> 1 envoi a l'adresse ENREGISTREE", len(ENVOIS) == 1
       and ENVOIS[0]["to"] == ["membre@exemple.invalid"])
    ok("B. trace send_ok avec l'id du fournisseur", traces("send_ok")
       and "provider_id=resend-id-banc" in traces("send_ok")[0])
    otp = otp_du_dernier_mail()
    ok("B. l'OTP n'apparait dans AUCUNE ligne de journal", not any(otp in l for l in JOURNAL))
    ok("B. l'adresse est masquee dans la trace", "me***[exemple.invalid]" in traces("send_ok")[0]
       and not any("@" in l for l in JOURNAL if "subscriber_otp_request" in l))

    # D — OTP valide -> jeton (validation inchangée)
    v = await S.b3s1_verifier_otp(Req({"code": "SYNTH-1", "email": "membre@exemple.invalid", "otp": otp}))
    ok("D. OTP valide -> jeton delivre", bool(v.get("token")))

    # E — OTP invalide -> refus 400 inchangé
    try:
        await S.b3s1_verifier_otp(Req({"code": "SYNTH-1", "email": "membre@exemple.invalid", "otp": "000000"}))
        ok("E. OTP invalide -> refus", False)
    except S.HTTPException as e:
        ok("E. OTP invalide -> 400", e.status_code == 400)

    # C — fournisseur en échec : même réponse, erreur journalisée avec son motif
    MODE["echec"] = True
    r = await S.b3s1_demander_otp(Req({"code": "SYNTH-2", "email": "autre@exemple.invalid"}))
    MODE["echec"] = False
    ok("C. echec fournisseur -> reponse IDENTIQUE (aucun oracle)", r == neutre)
    t = traces("send_failed")
    ok("C. trace send_failed avec le motif du fournisseur", t and "not verified" in t[0])
    ok("C. aucune cle dans la trace", not any("re_banc_factice" in l for l in JOURNAL))

    # C bis — adresse non reconnue : même réponse, aucun envoi, trace no_match
    n = len(ENVOIS)
    r = await S.b3s1_demander_otp(Req({"code": "SYNTH-3", "email": "intrus@exemple.invalid"}))
    ok("C bis. adresse inconnue -> reponse IDENTIQUE", r == neutre)
    ok("C bis. adresse inconnue -> aucun envoi", len(ENVOIS) == n)
    t = traces("no_match")
    ok("C bis. trace no_match (code connu, adresses masquees)", t and "code_known=True" in t[0]
       and "in***[exemple.invalid]" in t[0] and "intrus@" not in t[0])
    r = await S.b3s1_demander_otp(Req({"code": "INCONNU-9", "email": "x@exemple.invalid"}))
    ok("C bis. code inconnu -> reponse IDENTIQUE", r == neutre)

    # F — limite de débit inchangée : renvoi sous 2 min -> 429 + trace
    try:
        await S.b3s1_demander_otp(Req({"code": "SYNTH-1", "email": "membre@exemple.invalid"}))
        ok("F. renvoi sous 2 min -> 429", False)
    except S.HTTPException as e:
        ok("F. renvoi sous 2 min -> 429", e.status_code == 429)
    ok("F. trace rate_limited", bool(traces("rate_limited")))

    # Route réellement montée (leçon B3-S1.3 : le décorateur compte)
    chemins = {getattr(r, "path", "") for r in S.fastapi_app.routes}
    ok("route /api/subscriber/otp/request montee", "/api/subscriber/otp/request" in chemins)


asyncio.run(main())
for nom, c in RES:
    print(("  OK   " if c else "  ECHEC ") + nom)
ech = [n for n, c in RES if not c]
print("\n%d/%d au vert" % (len(RES) - len(ech), len(RES)))
sys.exit(1 if ech else 0)

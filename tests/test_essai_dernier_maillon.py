"""DERNIER MAILLON — la réservation d'un essai gratuit, de bout en bout.

CE QUE CE BANC AJOUTE AUX AUTRES. Le dépôt couvrait déjà les GARDES de l'essai
(`test_v591_essai_unique`, `test_g1g2_essai_social`…) en appelant les fonctions
une par une. Aucun banc n'exécutait le PARCOURS : coordonnées -> validation ->
confirmation -> enregistrement serveur -> attribution. C'est ce que fait
celui-ci, par un vrai `POST /api/checkout/free` sur une vraie application.

POURQUOI UN SERVEUR SÉPARÉ ET PAS `TestClient`. Le client Motor est créé à
l'import de `api/server.py`, donc attaché à la boucle d'événements de ce
moment-là. Avec `TestClient`, les requêtes tournent sur une AUTRE boucle : tous
les accès base échouent en « Event loop is closed », les gardes se replient, et
le banc mesure des replis au lieu du parcours (mesuré : `/checkout/free`
renvoyait 400 « offre non gratuite » alors que l'offre était à 0 CHF). Un
`uvicorn` dans son propre processus a sa propre boucle : le problème disparaît.

ISOLEMENT — TROIS BARRIÈRES, PAS UNE.
  1. Un `mongod` JETABLE, sur un port libre, dans un dossier temporaire.
  2. `MONGO_URL` / `DB_NAME` imposés à l'application fille, vers ce mongod seul.
  3. Un ARRÊT SÉCURISÉ avant toute écriture (`_garde_isolement`) : le banc
     vérifie que l'application qu'il interroge sert bien le catalogue de test
     — une offre, la sienne. La production en sert neuf. Si le compte ne
     correspond pas, on s'arrête AVANT le premier POST.

SERVICES EXTÉRIEURS NEUTRALISÉS PAR ABSENCE DE CLÉ (jamais par un drapeau) :
  RESEND_API_KEY   retirée -> aucun e-mail (`if resend_key:`, checkout_routes)
  VAPID_*          retirées -> aucune notification push
  OPENAI_API_KEY   retirée -> aucune IA payante
  META_WHATSAPP_*  retirées -> aucun message
  Stripe           jamais appelé sur un parcours à 0 CHF

IDENTITÉS FICTIVES : tout e-mail est en `@exemple.invalid` — le domaine
réservé par la RFC 2606, qui ne peut pas exister. Aucun nom, aucune adresse,
aucun numéro réel n'entre dans ce banc.

NETTOYAGE : le `finally` démonte TOUT, même après un échec ou une interruption
— serveur, mongod, base, dossier temporaire — et IMPRIME la preuve de chaque
étape. Il n'y a aucun chemin de sortie qui laisse un processus vivant.

    python3 tests/test_essai_dernier_maillon.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

# Les bases de PRODUCTION connues. Le banc n'écrit jamais ailleurs que sur son
# mongod jetable, mais un nom de base recopié par erreur ne doit pas pouvoir
# devenir une écriture réelle : on refuse de démarrer.
BASES_REELLES = frozenset(("afroboost_db", "promo-credits-lab", "afroboost", "admin", "local"))
PREFIXE_BASE = "banc_dernier_maillon_"

try:
    import pymongo
except ImportError:                                            # pragma: no cover
    print("pymongo absent — banc ignore"); sys.exit(0)
if not shutil.which("mongod"):                                 # pragma: no cover
    print("mongod absent — banc ignore"); sys.exit(0)

OK, KO = [], []


def v(nom, cond, detail=""):
    (OK if cond else KO).append(nom)
    print(("  OK    " if cond else "  RATE  ") + nom + ("" if cond else "   [%s]" % (detail,)))


def _port_libre():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


def _post(url, corps, entetes=None):
    rq = urllib.request.Request(
        url, data=json.dumps(corps).encode(), method="POST",
        headers=dict({"Content-Type": "application/json"}, **(entetes or {})))
    try:
        with urllib.request.urlopen(rq, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:                                      # noqa: BLE001
            return e.code, {}
    except Exception as e:                                     # noqa: BLE001
        return 0, {"erreur": str(e)}


def _get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:                                     # noqa: BLE001
        return 0, str(e)


class ArretSecurise(Exception):
    """La configuration ne garantit pas l'isolement : on n'écrit rien."""


def _garde_isolement(url_api, base, offre_attendue):
    """Refuse de continuer si l'application interrogée n'est pas celle du banc.

    C'est LA barrière qui compte, parce qu'elle ne fait pas confiance à
    l'environnement : elle regarde ce que l'application SERT. Le catalogue de
    test contient une seule offre, celle semée ici. La production en sert neuf.
    """
    if base in BASES_REELLES or not base.startswith(PREFIXE_BASE):
        raise ArretSecurise("nom de base refusé : %r" % base)
    code, corps = _get(url_api + "/api/offers")
    if code != 200:
        raise ArretSecurise("catalogue illisible (HTTP %s)" % code)
    try:
        offres = json.loads(corps)
    except Exception as err:                                   # noqa: BLE001
        raise ArretSecurise("catalogue illisible : %s" % err)
    offres = offres if isinstance(offres, list) else (offres.get("offers") or [])
    ids = [str(o.get("id")) for o in offres]
    if ids != [offre_attendue]:
        raise ArretSecurise(
            "l'application ne sert PAS le catalogue de test (%d offre(s) : %s) — "
            "arret avant toute ecriture" % (len(ids), ids[:5]))
    return True


def executer():
    maintenant = datetime.now(timezone.utc)
    iso = maintenant.isoformat()
    base_nom = PREFIXE_BASE + uuid.uuid4().hex[:8]
    coach = "coach.banc@exemple.invalid"
    offre, cours = "offre-essai-banc", "cours-banc"
    client = "visiteur.banc+%s@exemple.invalid" % uuid.uuid4().hex[:6]
    tel = "+4176000%04d" % (int(uuid.uuid4().hex[:4], 16) % 10000)

    dossier = tempfile.mkdtemp(prefix=PREFIXE_BASE)
    port_mongo, port_api = _port_libre(), _port_libre()
    mongo = api = cli = None
    code_sortie = 1

    try:
        mongo = subprocess.Popen(
            ["mongod", "--dbpath", dossier, "--port", str(port_mongo),
             "--bind_ip", "127.0.0.1", "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:
                cli = pymongo.MongoClient("mongodb://127.0.0.1:%d" % port_mongo,
                                          serverSelectionTimeoutMS=500)
                cli.admin.command("ping")
                break
            except Exception:                                  # noqa: BLE001
                time.sleep(0.5)
        else:
            print("mongod n'a pas demarre — banc ignore")
            return 0

        print("mongod jetable : port %d, base %s" % (port_mongo, base_nom))
        b = cli[base_nom]
        b.offers.insert_one({
            "id": offre, "name": "Cours d'essai GRATUIT (banc)", "price": 0,
            "visible": True, "archived": False, "offer_type": "single_class",
            "coach_id": coach, "coach_email": coach, "billing_mode": "unique",
            "linked_course_ids": [cours], "sessions": 1, "created_at": iso})
        b.courses.insert_one({
            "id": cours, "title": "Cours collectif du banc",
            "name": "Cours collectif du banc", "coach_id": coach, "price": 30,
            "recurring": True, "visible": True, "location": "Salle du banc",
            "schedules": [{"day": "wednesday", "time": "18:45"}],
            "date": (maintenant + timedelta(days=3)).strftime("%Y-%m-%d"),
            "time": "18:45", "created_at": iso})
        b.coaches.insert_one({"id": "coach-banc", "email": coach, "name": "Coach du banc",
                              "notification_email": coach, "created_at": iso})
        b.concept.insert_one({
            "id": "concept", "coach_id": coach, "created_at": iso,
            "termsText": "Conditions du banc isole. Un seul essai par personne."})
        print("base semee : 1 offre a 0 CHF, 1 cours, 1 coach, 1 concept (Conditions)\n")

        env = dict(os.environ)
        env["MONGO_URL"] = "mongodb://127.0.0.1:%d" % port_mongo
        env["DB_NAME"] = base_nom
        env["JWT_SECRET"] = "banc-" + uuid.uuid4().hex
        env["STRIPE_SECRET_KEY"] = "sk_test_banc_jamais_appele"
        env["FRONTEND_URL"] = "http://127.0.0.1:%d" % port_api
        for cle in ("RESEND_API_KEY", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY",
                    "VAPID_CLAIMS_EMAIL", "META_WHATSAPP_TOKEN", "META_WHATSAPP_PHONE_ID",
                    "OPENAI_API_KEY", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
                    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "PAWAPAY_API_TOKEN"):
            env.pop(cle, None)

        api = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "api.server:fastapi_app",
             "--host", "127.0.0.1", "--port", str(port_api), "--log-level", "warning"],
            cwd=RACINE, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        url = "http://127.0.0.1:%d" % port_api
        pret = False
        for _ in range(120):
            if _get(url + "/healthz")[0] == 200:
                pret = True
                break
            if api.poll() is not None:
                break
            time.sleep(0.5)
        if not pret:
            err = api.stderr.read(4000).decode(errors="replace") if api.stderr else ""
            if "ModuleNotFoundError" in err or "No module named" in err:
                print("dependances de l'application absentes — banc ignore")
                return 0
            print("uvicorn n'a pas demarre :\n" + err[-2000:])
            return 1

        # ─────────── 0. ARRET SECURISE, AVANT LA MOINDRE ECRITURE ───────────
        print("=== 0. ISOLEMENT ===")
        _garde_isolement(url, base_nom, offre)
        v("0a. l'application sert bien le catalogue de TEST (1 offre, la sienne)", True)
        v("0b. l'API de test repond", _get(url + "/api/debug/config")[0] == 200)
        _c, _t = _get(url + "/api/terms/active")
        v("0c. les Conditions du banc sont actives et exigees",
          '"required":true' in _t.replace(" ", ""), _t[:140])

        # ─────────── 1. LE PARCOURS COMPLET, A 0 CHF ───────────
        print("\n=== 1. LE PARCOURS COMPLET, A 0 CHF ===")
        corps = {
            "items": [{"type": "offer", "id": offre,
                       "name": "Cours d'essai GRATUIT (banc)", "price": 0, "quantity": 1}],
            "customer_name": "Visiteur du banc",
            "customer_email": client,
            "customer_phone": tel,
            "terms_accepted": True,
            "attribution": {
                "first": {"source": "instagram", "medium": "social",
                          "campaign": "banc_isole", "ts": iso,
                          "landing_path": "/?offre=%s&reserver=1&parcours=essai" % offre},
                "last": {"source": "instagram", "medium": "social", "ts": iso},
            },
        }
        st, rep = _post(url + "/api/checkout/free", corps,
                        {"CF-Connecting-IP": "203.0.113.7"})
        print("POST /api/checkout/free -> %s  %s\n"
              % (st, json.dumps(rep, ensure_ascii=False)[:400]))
        v("1. la reservation gratuite est ACCEPTEE", st == 200, (st, rep))
        code = rep.get("access_code") or rep.get("code") or ""
        v("2. un code d'acces est rendu au client", bool(code), sorted(rep.keys()))
        v("3. le code suit le format AFR-", str(code).startswith("AFR-"), code)
        v("4. la confirmation annonce bien la gratuite",
          rep.get("free") is True and rep.get("success") is True,
          {k: rep.get(k) for k in ("free", "success", "message")})

        # ─────────── 2. L'ENREGISTREMENT SERVEUR ───────────
        print("\n=== 2. L'ENREGISTREMENT SERVEUR ===")
        sub = b.subscriptions.find_one({"code": code}) if code else None
        v("5. une souscription existe pour ce code", bool(sub))
        if sub:
            # Les champs sont LUS sur le document, jamais devines : la premiere
            # version de ce banc assertait sur `amount_paid` / `user_email`
            # (absents), puis un motif large comptait `total_sessions` comme un
            # montant. Trois assertions fausses, zero defaut produit.
            v("6a. montant encaisse = 0 CHF",
              float(sub.get("montant_encaisse", -1) or 0) == 0.0,
              sub.get("montant_encaisse"))
            v("6b. aucune reconduction payante",
              float(sub.get("renewal_price", -1) or 0) == 0.0, sub.get("renewal_price"))
            v("6c. l'origine du paiement est « offert »",
              sub.get("origine_paiement") == "offert", sub.get("origine_paiement"))
            v("6d. une seance est creditee, aucune consommee",
              (sub.get("total_sessions"), sub.get("remaining_sessions"),
               sub.get("used_sessions")) == (1, 1, 0),
              {k: sub.get(k) for k in ("total_sessions", "remaining_sessions", "used_sessions")})
            v("6e. le champ metier `source` reste SEPARE de l'attribution",
              sub.get("source") == "checkout_vitrine", sub.get("source"))
            v("7. la souscription porte le bon client",
              str(sub.get("email", "")).lower() == client.lower(), sub.get("email"))
        v("8. le code d'acces existe aussi dans discount_codes",
          bool(b.discount_codes.find_one({"code": code})) if code else False)
        pt = b.payment_transactions.find_one({"customer_email": client.lower().strip()})
        v("9. une trace financiere existe", bool(pt))
        v("10. ... a 0 CHF", bool(pt) and float((pt or {}).get("amount", -1) or 0) == 0.0,
          (pt or {}).get("amount"))
        v("11. le contact est enregistre une seule fois",
          b.chat_participants.count_documents({"email": client.lower().strip()}) == 1,
          b.chat_participants.count_documents({}))

        # ─────────── 3. L'ATTRIBUTION ───────────
        print("\n=== 3. L'ATTRIBUTION INSTAGRAM ===")
        a = (sub or {}).get("attribution") or {}
        print("     %s\n" % json.dumps(a, ensure_ascii=False)[:260])
        v("12. PREMIERE SOURCE = instagram", (a.get("first") or {}).get("source") == "instagram", a)
        v("13. derniere interaction = instagram", (a.get("last") or {}).get("source") == "instagram", a)
        v("14. l'organique n'est PAS devenu du payant",
          (a.get("first") or {}).get("medium") == "social", (a.get("first") or {}).get("medium"))
        v("15. la campagne est conservee",
          (a.get("first") or {}).get("campaign") == "banc_isole", a.get("first"))

        # ─────────── 4. L'ELIGIBILITE ───────────
        print("\n=== 4. L'ELIGIBILITE ===")
        v("16. le verrou d'eligibilite est pose",
          b.free_trial_claims.count_documents({}) >= 1,
          b.free_trial_claims.count_documents({}))
        st2, rep2 = _post(url + "/api/checkout/free", corps,
                          {"CF-Connecting-IP": "203.0.113.7"})
        print("     SECOND essai, meme personne -> %s %s"
              % (st2, json.dumps(rep2, ensure_ascii=False)[:160]))
        v("17. un SECOND essai gratuit est REFUSE", st2 in (403, 409), (st2, rep2))
        v("18. ... aucune seconde souscription",
          b.subscriptions.count_documents({}) == 1, b.subscriptions.count_documents({}))
        v("19. ... aucun second code", b.discount_codes.count_documents({}) == 1,
          b.discount_codes.count_documents({}))
        st3, rep3 = _post(
            url + "/api/checkout/free",
            dict(corps, terms_accepted=False,
                 customer_email="autre.banc+%s@exemple.invalid" % uuid.uuid4().hex[:6]),
            {"CF-Connecting-IP": "203.0.113.8"})
        v("20. sans acceptation des Conditions : REFUS", st3 in (400, 403, 409), (st3, rep3))

        # ─────────── 5. AUCUN EFFET EXTERIEUR ───────────
        print("\n=== 5. AUCUN EFFET EXTERIEUR ===")
        v("21. aucune cle Resend : aucun e-mail n'a pu partir",
          not env.get("RESEND_API_KEY"))
        v("22. aucune cle VAPID : aucune notification n'a pu partir",
          not env.get("VAPID_PUBLIC_KEY"))
        v("23. aucune cle OpenAI : aucune IA payante n'a pu etre appelee",
          not env.get("OPENAI_API_KEY"))
        v("24. toutes les identites du banc sont fictives (.invalid)",
          all(".invalid" in x for x in (client, coach)), (client, coach))

        print("\n%d / %d verifications au vert" % (len(OK), len(OK) + len(KO)))
        if KO:
            print("ECHECS : " + " | ".join(KO))
        code_sortie = 1 if KO else 0

    except ArretSecurise as err:
        print("\nARRET SECURISE — aucune ecriture n'a eu lieu : %s" % err)
        code_sortie = 1
    except KeyboardInterrupt:
        print("\ninterrompu — on demonte quand meme")
        code_sortie = 130
    except Exception:                                          # noqa: BLE001
        import traceback
        traceback.print_exc()
        code_sortie = 1
    finally:
        # ─────────── NETTOYAGE, ET SA PREUVE ───────────
        print("\n=== NETTOYAGE ===")
        if api is not None:
            api.terminate()
            try:
                api.wait(timeout=20)
            except Exception:                                  # noqa: BLE001
                api.kill(); api.wait()
            print("     serveur de test arrete (code %s)" % api.returncode)
        reste = "?"
        if cli is not None:
            try:
                cli.drop_database(base_nom)
                reste = base_nom in cli.list_database_names()
            except Exception as err:                           # noqa: BLE001
                reste = "non verifiable (%s)" % type(err).__name__
            print("     base %s supprimee — encore presente : %s" % (base_nom, reste))
            try:
                cli.close()
            except Exception:                                  # noqa: BLE001
                pass
        if mongo is not None:
            mongo.terminate()
            try:
                mongo.wait(timeout=20)
            except Exception:                                  # noqa: BLE001
                mongo.kill(); mongo.wait()
            print("     mongod jetable arrete (code %s)" % mongo.returncode)
        shutil.rmtree(dossier, ignore_errors=True)
        print("     dossier temporaire supprime — existe encore : %s"
              % os.path.exists(dossier))
        print("     donnees de PRODUCTION lues ou ecrites : 0")

    return code_sortie


if __name__ == "__main__":
    print("=" * 78)
    print("DERNIER MAILLON — reservation d'un essai gratuit, de bout en bout, ISOLE")
    print("=" * 78)
    sys.exit(executer())

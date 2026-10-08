"""V592 — PARTENAIRE B1 : « Activer comme partenaire » depuis une fiche Prospect.

Ce banc tourne contre un VRAI mongod jetable (créé puis détruit ici). Aucune
donnée de production n'est lue ni écrite, aucun envoi n'est possible.

  1. Les index : `lead_id_unique` PARTIEL (vrais lead_id chaîne seulement) et
     `prospect_id_unique` PARTIEL — cas A/B/C/D de la consigne, plus la preuve
     que l'index ACTUEL (non partiel) bloque bien un 2e partenaire sans candidature.
  2. Les VRAIES routes de `api/server.py` (motor -> mongod local) : auth,
     propriété, création sans candidature, idempotence, double clic simultané,
     collision de slug, index non migré -> 503 sans rien créer.
  3. Les VRAIES statistiques `/partners/{slug}/stats` sur un parcours fictif
     AKOKO : essai -> réservation -> présence -> conversion = 1/1/1/1.
  4. La VRAIE garde d'essai V591 (`_essai_porte_garde`) : un ancien client
     payant est refusé et n'apparaît dans aucun compteur du partenaire.

    python3 tests/test_v592_partenaire_prospect.py
"""
import asyncio
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


SECRET_FICTIF = "secret-de-test-v592-sans-aucun-rapport-avec-la-production"
COACH = "coach.v592@exemple.test"
AUTRE = "autre.coach.v592@exemple.test"
os.environ["JWT_SECRET"] = SECRET_FICTIF
os.environ["MONGO_URL"] = "mongodb://bouchon-inexistant:27017"

import jwt as pyjwt  # noqa: E402
import pymongo  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _jeton(email):
    m = datetime.now(timezone.utc)
    j = pyjwt.encode({"email": email, "role": "coach", "iat": int(m.timestamp()),
                      "exp": int((m + timedelta(hours=1)).timestamp())},
                     SECRET_FICTIF, algorithm="HS256")
    return j.decode("utf-8") if isinstance(j, bytes) else j


class Requete:
    def __init__(self, email=None, corps=None, entete=None):
        self.headers = {}
        if email:
            self.headers["Authorization"] = "Bearer " + _jeton(email)
        if entete:
            self.headers["X-User-Email"] = entete
        self._corps = corps

    async def json(self):
        if self._corps is None:
            raise ValueError("corps vide")
        return self._corps


# ── les index, tels que la migration de production les posera ───────────────
INDEX_LEAD = dict(name="lead_id_unique", unique=True,
                  partialFilterExpression={"lead_id": {"$type": "string"}})
INDEX_PROSPECT = dict(name="prospect_id_unique", unique=True,
                      partialFilterExpression={"prospect_id": {"$type": "string"}})
INDEX_SLUG = dict(name="partner_slug_unique", unique=True)


def poser_index(col, lead_partiel=True):
    col.create_index([("partner_slug", 1)], **INDEX_SLUG)
    if lead_partiel:
        col.create_index([("lead_id", 1)], **INDEX_LEAD)
    else:
        col.create_index([("lead_id", 1)], name="lead_id_unique", unique=True)
    col.create_index([("prospect_id", 1)], **INDEX_PROSPECT)


def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def essai_insertions(col, docs):
    res = []
    for d in docs:
        try:
            col.insert_one(dict(d)); res.append("OK")
        except DuplicateKeyError:
            res.append("REFUS")
    return res


def section_index(cli):
    print("\n1. INDEX (pymongo direct)")
    b = cli["v592_index"]
    b.drop_collection("partners"); col = b["partners"]; poser_index(col)
    verifier("A. 3 partenaires SANS lead_id -> acceptés",
             essai_insertions(col, [{"partner_slug": s} for s in ("a1", "a2", "a3")]) == ["OK"] * 3)
    verifier("B. 3 partenaires lead_id = null -> acceptés (null n'est pas une chaîne, non indexé)",
             essai_insertions(col, [{"partner_slug": s, "lead_id": None} for s in ("b1", "b2", "b3")]) == ["OK"] * 3)
    verifier("C. même vrai lead_id deux fois -> le second refusé",
             essai_insertions(col, [{"partner_slug": "c1", "lead_id": "L-1"},
                                    {"partner_slug": "c2", "lead_id": "L-1"}]) == ["OK", "REFUS"])
    verifier("D. deux lead_id différents -> acceptés",
             essai_insertions(col, [{"partner_slug": "d1", "lead_id": "L-2"},
                                    {"partner_slug": "d2", "lead_id": "L-3"}]) == ["OK", "OK"])
    verifier("E. même prospect_id deux fois -> le second refusé",
             essai_insertions(col, [{"partner_slug": "e1", "prospect_id": "P-1"},
                                    {"partner_slug": "e2", "prospect_id": "P-1"}]) == ["OK", "REFUS"])
    verifier("F. chaîne vide en lead_id : indexée (c'est une chaîne) -> 2e refusée, documenté",
             essai_insertions(col, [{"partner_slug": "f1", "lead_id": ""},
                                    {"partner_slug": "f2", "lead_id": ""}]) == ["OK", "REFUS"])
    b.drop_collection("partners"); col = b["partners"]; poser_index(col, lead_partiel=False)
    verifier("G. index ACTUEL (non partiel) : 2e partenaire sans candidature REFUSÉ (le blocage)",
             essai_insertions(col, [{"partner_slug": "g1"}, {"partner_slug": "g2"}]) == ["OK", "REFUS"])
    cli.drop_database("v592_index")


async def section_routes(S, sync_db):
    print("\n2. ROUTES (vraies fonctions de server.py)")
    from fastapi import HTTPException

    async def appel(coro):
        try:
            return 200, await coro
        except HTTPException as e:
            return e.status_code, e.detail

    sync_db.coaches.insert_many([{"email": COACH}, {"email": AUTRE}])
    pid = str(uuid.uuid4())
    sync_db.partner_prospects.insert_one({"id": pid, "coach_id": COACH,
                                          "organisation_name": "AKOKO TRESSES TEST",
                                          "public_email": "akoko.test@exemple.test",
                                          "public_phone": "+41 79 000 00 01",
                                          "partner_id": None, "partner_application_id": None})
    # partenaire HISTORIQUE issu d'une vraie candidature : doit cohabiter
    sync_db.partners.insert_one({"id": "hist", "lead_id": str(uuid.uuid4()),
                                 "partner_slug": "historique", "coach_id": COACH})

    st, _ = await appel(S.v592_activer_partenaire(pid, Requete()))
    verifier("sans jeton -> 403", st == 403, st)
    st, _ = await appel(S.v592_activer_partenaire(pid, Requete(entete=COACH)))
    verifier("X-User-Email seul (falsifiable) -> 403", st == 403, st)
    st, _ = await appel(S.v592_activer_partenaire(pid, Requete(AUTRE)))
    verifier("autre coach -> 403", st == 403, st)
    st, _ = await appel(S.v592_activer_partenaire("inconnu", Requete(COACH)))
    verifier("prospect inconnu -> 404", st == 404, st)
    verifier("aucun partenaire créé par les refus", sync_db.partners.count_documents({"prospect_id": pid}) == 0)

    st, r1 = await appel(S.v592_activer_partenaire(pid, Requete(COACH)))
    verifier("1. activation -> 200, partenaire créé", st == 200 and r1.get("already") is False, r1)
    doc = sync_db.partners.find_one({"prospect_id": pid}) or {}
    verifier("2. prospect_id correct", doc.get("prospect_id") == pid)
    verifier("3. AUCUN lead_id (champ absent, pas de fausse candidature)", "lead_id" not in doc, doc)
    verifier("4. slug suggéré par la règle existante = akoko_tresses_test",
             doc.get("partner_slug") == "akoko_tresses_test", doc.get("partner_slug"))
    verifier("5. propriétaire = coach du prospect, statut decouverte, source prospection",
             doc.get("coach_id") == COACH and doc.get("partner_status") == "decouverte"
             and doc.get("source") == "prospection")
    verifier("6. aucun e-mail ni téléphone renvoyé à l'écran",
             "email" not in r1["partner"] and "whatsapp" not in r1["partner"])
    pr = sync_db.partner_prospects.find_one({"id": pid})
    verifier("7. la fiche pointe vers le partenaire (partner_id)", pr.get("partner_id") == doc.get("id"))
    verifier("8. aucun lead créé", sync_db.leads.count_documents({}) == 0)

    st, r2 = await appel(S.v592_activer_partenaire(pid, Requete(COACH)))
    verifier("9. 2e activation -> même partenaire, already=True",
             st == 200 and r2.get("already") is True and r2["partner"]["id"] == doc.get("id"), r2)
    verifier("   toujours UN seul partenaire", sync_db.partners.count_documents({"prospect_id": pid}) == 1)

    st, lu = await appel(S.v592_partenaire_du_prospect(pid, Requete(COACH)))
    verifier("lecture du partenaire lié -> slug", st == 200 and lu["partner"]["partner_slug"] == "akoko_tresses_test")
    st, _ = await appel(S.v592_partenaire_du_prospect(pid, Requete(AUTRE)))
    verifier("lecture par un autre coach -> 403", st == 403)

    # 10. CONCURRENCE : 8 clics simultanés sur un prospect neuf
    pid2 = str(uuid.uuid4())
    sync_db.partner_prospects.insert_one({"id": pid2, "coach_id": COACH,
                                          "organisation_name": "Salon Concurrence Test"})
    res = await asyncio.gather(*[appel(S.v592_activer_partenaire(pid2, Requete(COACH))) for _ in range(8)])
    ids = {r[1]["partner"]["id"] for r in res if r[0] == 200}
    verifier("10. 8 activations simultanées -> 8 x 200, UN seul partenaire",
             all(r[0] == 200 for r in res) and len(ids) == 1
             and sync_db.partners.count_documents({"prospect_id": pid2}) == 1, res)

    pid3 = str(uuid.uuid4())
    sync_db.partner_prospects.insert_one({"id": pid3, "coach_id": COACH, "organisation_name": "Autre"})
    st, _ = await appel(S.v592_activer_partenaire(pid3, Requete(COACH, {"partner_slug": "akoko_tresses_test"})))
    verifier("slug déjà pris -> 409, rien créé",
             st == 409 and sync_db.partners.count_documents({"prospect_id": pid3}) == 0, st)
    st, _ = await appel(S.v592_activer_partenaire(pid3, Requete(COACH, {"partner_slug": "É!"})))
    verifier("slug invalide -> 400", st == 400, st)
    st, r = await appel(S.v592_activer_partenaire(pid3, Requete(COACH, {"partner_slug": "autre_choisi"})))
    verifier("slug choisi par le coach -> accepté", st == 200 and r["partner"]["partner_slug"] == "autre_choisi")
    verifier("le partenaire historique (vraie candidature) est intact",
             sync_db.partners.count_documents({"id": "hist", "lead_id": {"$type": "string"}}) == 1)
    verifier("plusieurs partenaires SANS candidature cohabitent (3)",
             sync_db.partners.count_documents({"lead_id": {"$exists": False}}) == 3)
    return doc.get("partner_slug")


async def section_index_non_migre(S, cli, url):
    print("\n2b. INDEX NON MIGRÉ (état actuel de la production)")
    from fastapi import HTTPException
    sync = cli["v592_ancien"]
    poser_index(sync["partners"], lead_partiel=False)
    sync.coaches.insert_one({"email": COACH})
    sync.partners.insert_one({"id": "seul", "partner_slug": "deja_un"})   # 1er sans candidature
    p = str(uuid.uuid4())
    sync.partner_prospects.insert_one({"id": p, "coach_id": COACH, "organisation_name": "Index Ancien"})
    ancien = S.db
    S.db = AsyncIOMotorClient(url)["v592_ancien"]
    try:
        await S.v592_activer_partenaire(p, Requete(COACH))
        st = 200
    except HTTPException as e:
        st = e.status_code
    finally:
        S.db = ancien
    verifier("index non partiel -> 503 explicite (pas un faux « slug pris »), rien créé",
             st == 503 and sync.partners.count_documents({"prospect_id": p}) == 0, st)
    cli.drop_database("v592_ancien")


async def section_parcours(S, sync_db, slug):
    print("\n3. PARCOURS FICTIF AKOKO -> STATISTIQUES")
    import api.routes.checkout_routes as CK
    from fastapi import HTTPException
    attribution = {"first": {"source": "partenaire", "medium": "referral",
                             "campaign": "essai_neuchatel", "content": slug},
                   "last": {"source": "partenaire", "medium": "referral",
                            "campaign": "essai_neuchatel", "content": slug}}
    sync_db.offers.insert_many([
        {"id": "offre-essai", "name": "Essai", "price": 0},
        {"id": "offre-pack", "name": "Carte 10", "price": 150},
    ])
    mail = "cliente.akoko@exemple.test"
    # premier cours offert : forfait d'essai (origine posée par M2-A) + code gratuit
    sync_db.subscriptions.insert_one({"code": "AFR-ESSAI1", "email": mail, "offer_id": "offre-essai",
                                      "status": "active", "origine_paiement": "offert",
                                      "attribution": attribution})
    sync_db.discount_codes.insert_one({"code": "AFR-ESSAI1", "payment_method": "free", "total_paid": 0})
    # réservation d'un cours existant (l'origine est recopiée), puis présence
    sync_db.reservations.insert_one({"id": "res-1", "reservationCode": "R-1",
                                     "createdAt": datetime.now(timezone.utc).isoformat(),
                                     "userEmail": mail, "discountCode": "AFR-ESSAI1",
                                     "offerId": "offre-essai", "validated": True,
                                     "attribution": attribution})
    # conversion : achat payant APRÈS l'essai
    sync_db.subscriptions.insert_one({"code": "AFR-PAYE1", "email": mail, "offer_id": "offre-pack",
                                      "status": "active", "attribution": attribution})

    st = await S.p2d_stats_partenaire(slug, Requete(COACH))
    verifier("essais = 1", st.get("trials") == 1, st.get("trials"))
    verifier("réservations = 1", st.get("reservations") == 1, st.get("reservations"))
    verifier("présences = 1", st.get("attendances") == 1, st.get("attendances"))
    verifier("conversions = 1 (le forfait d'essai n'en est pas une)",
             (st.get("conversions") or {}).get("total") == 1, st.get("conversions"))
    verifier("taux de présence = 100 %", st.get("attendance_rate") == 1.0, st.get("attendance_rate"))
    verifier("taux de conversion = 100 %", st.get("conversion_rate") == 1.0, st.get("conversion_rate"))
    verifier("aucune donnée personnelle dans la réponse",
             mail not in repr(st) and "AFR-" not in repr(st))

    print("\n4. ANCIEN CLIENT PAYANT (garde V591 réelle)")
    ancien = "ancien.client@exemple.test"
    sync_db.subscriptions.insert_one({"code": "AFR-VIEUX", "email": ancien, "offer_id": "offre-pack",
                                      "status": "expired"})
    CK.db = S.db
    try:
        await CK._essai_porte_garde(ancien, "offre-essai", "+41 79 000 00 02")
        refus = None
    except HTTPException as e:
        refus = e
    verifier("essai refusé (409) avec le code PUBLIC neutre not_eligible",
             refus is not None and refus.status_code == 409
             and (refus.headers or {}).get("X-Refus-Raison") == "not_eligible",
             getattr(refus, "headers", None))
    verifier("aucun forfait d'essai créé pour lui",
             sync_db.subscriptions.count_documents({"email": ancien}) == 1)
    st2 = await S.p2d_stats_partenaire(slug, Requete(COACH))
    verifier("statistiques du partenaire INCHANGÉES (aucune fausse conversion)",
             (st2.get("trials"), st2.get("reservations"), st2.get("attendances"),
              (st2.get("conversions") or {}).get("total")) == (1, 1, 1, 1), st2)


def section_statique():
    print("\n5. CHAÎNE D'ATTRIBUTION EXISTANTE (inchangée, vérifiée dans le code)")
    ck = open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"), encoding="utf-8").read()
    rr = open(os.path.join(RACINE, "api", "routes", "reservation_routes.py"), encoding="utf-8").read()
    pl = open(os.path.join(RACINE, "frontend", "src", "utils", "partnerLink.js"), encoding="utf-8").read()
    verifier("l'essai gratuit pose l'origine sur son forfait (M2-A)",
             '{"$set": {"attribution": _m2a_attribution}}' in ck)
    verifier("la réservation recopie l'origine du forfait",
             'new_reservation["attribution"] = _m2a' in rr)
    verifier("le lien Partenaire garde ses 3 UTM verrouillés",
             "utm_source: 'partenaire'" in pl and "utm_campaign: 'essai_neuchatel'" in pl)
    sv = open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
    bloc = sv[sv.index("def v592_activer_partenaire"):sv.index("# P3-S3-A — SOCLE")]
    verifier("la route n'écrit JAMAIS de lead_id ni dans leads",
             '"lead_id":' not in bloc and "db.leads" not in bloc)
    verifier("aucune génération de lien/QR côté serveur", "utm_" not in bloc and "qr" not in bloc.lower())


async def principal():
    dossier, port = tempfile.mkdtemp(prefix="v592_"), _port()
    proc = subprocess.Popen(["mongod", "--dbpath", dossier, "--port", str(port),
                             "--bind_ip", "127.0.0.1", "--quiet"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = "mongodb://127.0.0.1:%d" % port
    try:
        cli = None
        for _ in range(60):
            try:
                cli = pymongo.MongoClient(url, serverSelectionTimeoutMS=500)
                cli.admin.command("ping"); break
            except Exception:
                time.sleep(0.5)
        section_index(cli)
        import api.server as S
        S.db = AsyncIOMotorClient(url)["v592"]
        sync_db = cli["v592"]
        poser_index(sync_db["partners"])
        slug = await section_routes(S, sync_db)
        await section_index_non_migre(S, cli, url)
        await section_parcours(S, sync_db, slug)
        section_statique()
    finally:
        proc.terminate(); proc.wait(timeout=30); shutil.rmtree(dossier, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(principal())
    ok = sum(1 for _, c, _ in RESULTATS if c)
    print("\n" + "=" * 78)
    print("V592 — %d / %d verifications au vert" % (ok, len(RESULTATS)))
    print("mongod jetable détruit. Production : 0 connexion.")
    sys.exit(0 if ok == len(RESULTATS) else 1)

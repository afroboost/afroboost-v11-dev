#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V617 — abonnements manuels : fin de journée suisse, un seul abonnement actuel,
historique qui ne ressurgit jamais, nouvel abonnement neuf, suivi de paiement.

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v617_abonnements_manuels.py

Partie 1 : fonctions PURES (aucune base, aucun réseau).
Partie 2 : les VRAIES routes `promo_routes.py` contre un `mongod` JETABLE
(port dédié, dossier temporaire détruit à la fin). AUCUNE donnée de production,
aucun e-mail (les deux envois de la création sont remplacés par des bouchons).
"""
import asyncio, copy, inspect, os, shutil, socket, subprocess, sys, tempfile, time
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ["JWT_SECRET"] = "secret-de-test-v617"
os.environ["MONGO_URL"] = "mongodb://127.0.0.1:1/factice-v617"
os.environ.pop("RESEND_API_KEY", None)
import api.server  # noqa: E402,F401  (initialise les routeurs comme en production)
import api.routes.shared as SH  # noqa: E402
import api.routes.promo_routes as PR  # noqa: E402

R = []


def verifier(nom, cond, detail=""):
    R.append(bool(cond))
    print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond:
        print("           ->", detail)


def utc(a, mo, j, h=0, mi=0, s=0):
    return datetime(a, mo, j, h, mi, s, tzinfo=timezone.utc)


# ════════════════════════ PARTIE 1 — FONCTIONS PURES ════════════════════════
print("\nA / B. Une date sans heure = valable jusqu'à la fin du jour, heure suisse")
E = SH._v391_est_expire
# 11/10/2026 = heure d'été (UTC+2) : fin du jour = 11/10 22:00 UTC
verifier("A. expire le 11/10 -> utilisable le 11/10 à 09:00 (CH)", not E("2026-10-11", utc(2026, 10, 11, 7)))
verifier("A. -> utilisable le 11/10 à 17:00 (CH) (le bug du 11/10 : refusé)", not E("2026-10-11", utc(2026, 10, 11, 15)))
verifier("A. -> utilisable le 11/10 à 23:59 (CH)", not E("2026-10-11", utc(2026, 10, 11, 21, 59, 59)))
verifier("A. -> expiré le 12/10 à 00:00 (CH)", E("2026-10-11", utc(2026, 10, 11, 22)))
verifier("B. expire hier -> expiré", E("2026-10-10", utc(2026, 10, 11, 12)))
print("   passage heure d'été -> hiver (dimanche 25/10/2026) et hiver -> été (28/03/2027)")
verifier("A. 25/10 (jour du changement) : 23:59 CET = 22:59 UTC -> utilisable", not E("2026-10-25", utc(2026, 10, 25, 22, 59, 59)))
verifier("A. 25/10 : 26/10 00:00 CET = 25/10 23:00 UTC -> expiré", E("2026-10-25", utc(2026, 10, 25, 23)))
verifier("A. 28/03/2027 (passage à l'été) : 23:59 CEST = 21:59 UTC -> utilisable", not E("2027-03-28", utc(2027, 3, 28, 21, 59, 59)))
verifier("A. 28/03/2027 : 29/03 00:00 CEST = 28/03 22:00 UTC -> expiré", E("2027-03-28", utc(2027, 3, 28, 22)))
verifier("A. hiver (15/01/2027) : fin du jour = 23:00 UTC", SH.v617_fin_du_jour("2027-01-15") == utc(2027, 1, 15, 23))
verifier("une valeur AVEC heure garde son instant exact (inchangé)",
         not E("2026-10-11T23:59:59+00:00", utc(2026, 10, 11, 23)) and E("2026-10-11T23:59:59+00:00", utc(2026, 10, 12, 0)))
verifier("absent / illisible -> jamais expiré (inchangé)", not E(None) and not E("") and not E("pas une date"))
verifier("jour suisse : 11/10 23:30 CH (21:30 UTC) = 2026-10-11", SH.v617_jour_local(utc(2026, 10, 11, 21, 30)) == "2026-10-11")
verifier("jour suisse : 12/10 00:30 CH (22:30 UTC le 11/10) = 2026-10-12", SH.v617_jour_local(utc(2026, 10, 11, 22, 30)) == "2026-10-12")
_doc = {"active": True, "expiresAt": "2026-10-11", "maxUses": 10, "used": 7}
verifier("code promo (LOT A) : vivant le 11/10, mort le 12/10 (jour suisse)",
         SH.lota_droit_utilisable(_doc, "2026-10-11")[0] and not SH.lota_droit_utilisable(_doc, "2026-10-12")[0])
_p = PR._v200_parse_expiry("2026-10-11", "T")
verifier("validation d'un code : « 2026-10-11 » -> 11/10 23:59:59 heure suisse",
         _p is not None and _p.astimezone(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S") == "2026-10-11 23:59:59", _p)
_p = PR._v200_parse_expiry("11.10.2026", "T")
verifier("validation : format « 11.10.2026 » -> même règle", _p is not None and _p > utc(2026, 10, 11, 21, 59) and _p < utc(2026, 10, 11, 22))

print("\nC / D / G. Un seul abonnement actuel, jamais un historique")
A = SH.abo_actuel_du_code
hist = [{"id": "h1", "status": "superseded"}, {"id": "h2", "status": "expired"},
        {"id": "h3", "status": "cancelled"}, {"id": "h4", "status": "completed"}]
verifier("A. 4 anciens + 1 actuel -> l'actuel, et lui seul", A(hist + [{"id": "a1", "status": "active"}]) == ({"id": "a1", "status": "active"}, "unique"))
verifier("aucun actuel (épuisé compris) -> aucun, jamais un historique", A(hist) == (None, "aucun"))
verifier("G. deux actuels -> erreur d'intégrité, aucun choix", A([{"id": "a", "status": "active"}, {"id": "b", "status": "active"}]) == (None, "plusieurs"))
verifier("le bénéficiaire départage deux personnes sur un même code",
         A([{"id": "a", "status": "active", "email": "x@t.ch"}, {"id": "b", "status": "active", "email": "y@t.ch"}], "y@t.ch")[0]["id"] == "b")

print("\nH / E. L'espace abonné n'ouvre jamais de droits sur un abonnement historique")
FU = SH.forfait_utilisable
for st in ("superseded", "expired", "cancelled", "archived"):
    ok, msg = FU({"status": st, "remaining_sessions": 5, "expires_at": "2099-01-01"}, 1)
    verifier("abonnement « %s » non expiré avec 5 séances -> refusé" % st, not ok and "remplacé" in msg, msg)
verifier("abonnement actif -> autorisé (inchangé)", FU({"status": "active", "remaining_sessions": 5, "expires_at": "2099-01-01"}, 1)[0])
verifier("épuisé (`completed`) : jugé sur ses séances comme avant (une annulation le rouvre)",
         FU({"status": "completed", "remaining_sessions": 1}, 1)[0] and not FU({"status": "completed", "remaining_sessions": 0}, 1)[0])
verifier("sans statut (dictionnaire construit par l'espace) -> inchangé", FU({"remaining_sessions": 2}, 1)[0])

print("\nJ / K / L. Suivi de paiement, aucun prélèvement, rappel coach")
V = SH.suivi_paiement_valider


def refus(f, *a):
    try:
        f(*a)
        return False
    except Exception as e:  # noqa: BLE001
        return getattr(e, "status_code", None) == 400


s = V({"montant_total": 400, "plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 1,
       "prochaine_echeance": "2026-11-07", "note_interne": "2e paiement de 200 CHF le mois prochain"}, 200)
lu = SH.suivi_paiement_lire({"suivi_paiement": s, "montant_encaisse": 200})
verifier("J. 400 total / 200 encaissé -> reste 200 (recalculé, jamais stocké)", lu.get("reste_a_payer") == 200 and "reste_a_payer" not in s, lu)
verifier("J. 1/2, échéance et note conservées", lu.get("nb_paiements") == 2 and lu.get("paiement_actuel") == 1
         and lu.get("prochaine_echeance") == "2026-11-07" and "200 CHF" in lu.get("note_interne", ""))
verifier("encaissé > total -> refus 400", refus(V, {"montant_total": 100}, 200))
verifier("3e paiement sur 2 -> refus 400", refus(V, {"plusieurs_fois": True, "nb_paiements": 2, "paiement_actuel": 3}))
verifier("1 seul paiement en « plusieurs fois » -> refus 400", refus(V, {"plusieurs_fois": True, "nb_paiements": 1, "paiement_actuel": 1}))
verifier("échéance illisible -> refus 400", refus(V, {"prochaine_echeance": "07/11/2026"}))
verifier("suivi vide -> rien n'est stocké (abonnement ancien inchangé)", V({}) == {} and V(None) == {} and SH.suivi_paiement_lire({}) == {})
verifier("note interne bornée à %d caractères" % SH.SUIVI_NOTE_MAX, len(V({"note_interne": "x" * 5000})["note_interne"]) == SH.SUIVI_NOTE_MAX)
sub = {"id": "s1", "code": "AURE-8M", "email": "a@t.ch", "name": "aurelie", "montant_encaisse": 200, "suivi_paiement": s}
verifier("L. échéance dans 10 jours -> pas encore de rappel", SH.suivi_rappel(sub, utc(2026, 10, 28, 10)) is None)
r = SH.suivi_rappel(sub, utc(2026, 10, 31, 10))
verifier("L. échéance dans 7 jours -> rappel « paiement 2/2, 200 CHF »", r and r["reste_a_payer"] == 200 and r["paiement_suivant"] == "2/2" and not r["en_retard"], r)
verifier("L. échéance dépassée -> rappel « en retard »", SH.suivi_rappel(sub, utc(2026, 11, 9, 10))["en_retard"])
verifier("L. tout est payé -> aucun rappel", SH.suivi_rappel(dict(sub, montant_encaisse=400), utc(2026, 11, 9, 10)) is None)
import ast as _ast, textwrap as _tw
_appels = set()
for _f in (SH.suivi_paiement_valider, SH.suivi_paiement_lire, SH.suivi_rappel,
           SH.v617_echeances, SH.v617_enrichir_codes, PR.get_echeances_paiement):
    for _n in _ast.walk(_ast.parse(_tw.dedent(inspect.getsource(_f)))):
        if isinstance(_n, _ast.Call):
            _appels.add(_ast.unparse(_n.func).lower() if hasattr(_ast, "unparse") else _ast.dump(_n.func).lower())
        if isinstance(_n, (_ast.Import, _ast.ImportFrom)):
            _appels.update(a.name.lower() for a in _n.names)
verifier("K. aucun débit, aucun envoi : aucun appel Stripe, e-mail, WhatsApp ni tâche de fond",
         not any(m in a for a in _appels for m in ("stripe", "resend", "send", "whatsapp", "create_task", "payment")), sorted(_appels))


# ═════════════ PARTIE 2 — VRAIES ROUTES, MONGOD JETABLE ═════════════════════
def mongod_jetable():
    if not shutil.which("mongod"):
        return None, None, None
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    dossier = tempfile.mkdtemp(prefix="v617-mongod-")
    p = subprocess.Popen(["mongod", "--dbpath", dossier, "--port", str(port), "--bind_ip", "127.0.0.1", "--quiet"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from pymongo import MongoClient
    for _ in range(80):
        try:
            MongoClient("127.0.0.1", port, serverSelectionTimeoutMS=500).admin.command("ping")
            return p, port, dossier
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    p.terminate()
    raise AssertionError("mongod n'a pas démarré")


class Req:
    def __init__(self, email): self.headers = {"X-User-Email": email}


ADMIN = SH.SUPER_ADMIN_EMAILS[0]
COACH = "coach.partenaire@exemple.test"
ENVOIS = []


async def _pas_d_envoi(*a, **k):
    ENVOIS.append(a)


def sans_id(docs):
    return [{k: v for k, v in d.items() if k != "_id"} for d in docs]


async def partie2(db):
    PR._db = db
    PR.coach_jwt_email = lambda r: r.headers.get("X-User-Email", "")
    SH.coach_jwt_email = PR.coach_jwt_email
    PR._send_welcome_email = _pas_d_envoi
    PR._send_coach_sale_email = _pas_d_envoi
    await db.coaches.insert_one({"email": COACH})
    req = Req(ADMIN)

    # Un client avec 4 anciens abonnements sur le MÊME code + 1 actuel.
    await db.discount_codes.insert_one({"id": "dc-x", "code": "CLIENT-X", "type": "100%", "value": 100,
                                        "assignedEmail": "x@exemple.test", "maxUses": 10, "used": 3,
                                        "expiresAt": "2027-06-07", "active": True})
    anciens = [{"id": "x-%s" % st, "code": "CLIENT-X", "email": "x@exemple.test", "status": st,
                "total_sessions": 10, "used_sessions": 9, "remaining_sessions": 1,
                "expires_at": "2026-07-13T23:59:59+00:00"} for st in ("superseded", "expired", "cancelled", "completed")]
    await db.subscriptions.insert_many(copy.deepcopy(anciens))
    await db.subscriptions.insert_one({"id": "x-actuel", "code": "CLIENT-X", "email": "x@exemple.test",
                                       "status": "active", "total_sessions": 10, "used_sessions": 3,
                                       "remaining_sessions": 7, "expires_at": "2027-06-07T23:59:59+00:00"})
    avant_anciens = sans_id(await db.subscriptions.find({"id": {"$ne": "x-actuel"}}).sort("id", 1).to_list(50))

    print("\nB / C. Modifier l'abonnement actuel -> lui seul (par son id)")
    rep = await PR.update_discount_code("dc-x", {"maxUses": 31, "expiresAt": "2027-06-30", "used": 4,
                                                 "montant_encaisse": 200, "origine_paiement": "twint",
                                                 "suivi_paiement": {"montant_total": 400, "plusieurs_fois": True,
                                                                    "nb_paiements": 2, "paiement_actuel": 1,
                                                                    "prochaine_echeance": "2026-11-07",
                                                                    "note_interne": "note coach"}}, req)
    act = await db.subscriptions.find_one({"id": "x-actuel"}, {"_id": 0})
    verifier("C. la réponse désigne l'abonnement modifié par son id", rep["v617"]["abonnement_modifie"] == "x-actuel", rep.get("v617"))
    verifier("C. l'actuel suit : 31 séances, 4 utilisées, 27 restantes, expire le 30/06/2027",
             act["total_sessions"] == 31 and act["used_sessions"] == 4 and act["remaining_sessions"] == 27
             and act["expires_at"].startswith("2027-06-30") and act["status"] == "active", act)
    verifier("C. encaissement 200 TWINT et suivi posés sur l'actuel", act.get("montant_encaisse") == 200
             and act.get("origine_paiement") == "twint" and act["suivi_paiement"]["montant_total"] == 400)
    apres_anciens = sans_id(await db.subscriptions.find({"id": {"$ne": "x-actuel"}}).sort("id", 1).to_list(50))
    verifier("B / D / E. les 4 anciens sont STRICTEMENT inchangés (statut, compteurs, expiration)", apres_anciens == avant_anciens)
    code = await db.discount_codes.find_one({"id": "dc-x"}, {"_id": 0})
    verifier("la note interne n'est PAS sur la fiche du code (renvoyée par la validation publique)",
             "suivi_paiement" not in code and "note_interne" not in str(code))

    print("\nA. Liste du coach : un seul abonnement actuel, l'historique compté à part")
    liste = await PR.get_discount_codes(req)
    x = [c for c in liste if c["code"] == "CLIENT-X"][0]
    verifier("A. zone actuelle = 1 seul abonnement ; historique = 4",
             x["v617_abonnement"]["id"] == "x-actuel" and x["v617_abonnement"]["historiques"] == 4, x.get("v617_abonnement"))
    verifier("J. reste à payer recalculé = 200 CHF", x["v617_abonnement"]["suivi"].get("reste_a_payer") == 200)

    print("\nG. Plusieurs abonnements actuels -> erreur d'intégrité, RIEN n'est écrit")
    await db.discount_codes.insert_one({"id": "dc-d", "code": "DOUBLE", "type": "100%", "value": 100,
                                        "assignedEmail": "d@exemple.test", "maxUses": 10, "used": 2, "active": True})
    await db.subscriptions.insert_many([{"id": "d1", "code": "DOUBLE", "email": "d@exemple.test", "status": "active", "total_sessions": 10, "used_sessions": 2, "remaining_sessions": 8},
                                        {"id": "d2", "code": "DOUBLE", "email": "d@exemple.test", "status": "active", "total_sessions": 10, "used_sessions": 0, "remaining_sessions": 10}])
    avant = (sans_id(await db.discount_codes.find({"id": "dc-d"}).to_list(5)), sans_id(await db.subscriptions.find({"code": "DOUBLE"}).sort("id", 1).to_list(5)))
    try:
        await PR.update_discount_code("dc-d", {"maxUses": 20}, req)
        verifier("G. modification refusée (409)", False, "acceptée !")
    except Exception as e:  # noqa: BLE001
        verifier("G. modification refusée (409 « erreur d'intégrité »)", e.status_code == 409 and e.detail["type"] == "integrite_plusieurs_actuels", getattr(e, "detail", e))
    apres = (sans_id(await db.discount_codes.find({"id": "dc-d"}).to_list(5)), sans_id(await db.subscriptions.find({"code": "DOUBLE"}).sort("id", 1).to_list(5)))
    verifier("G. ni le code ni les abonnements n'ont bougé", avant == apres)
    rep = await PR.update_discount_code("dc-d", {"active": True}, req)
    verifier("un changement sans effet sur les droits (activer) reste possible", rep.get("v617", {}).get("motif") == "sans_abonnement")

    print("\nD / E. Aucun abonnement actuel -> on ne ressuscite pas l'historique")
    await db.discount_codes.insert_one({"id": "dc-h", "code": "ANCIEN", "type": "100%", "value": 100,
                                        "assignedEmail": "h@exemple.test", "maxUses": 10, "used": 10,
                                        "expiresAt": "2026-05-05", "active": True})
    await db.subscriptions.insert_many([{"id": "h-sup", "code": "ANCIEN", "email": "h@exemple.test", "status": "superseded", "total_sessions": 10, "used_sessions": 5, "remaining_sessions": 5, "expires_at": "2099-01-01"},
                                        {"id": "h-exp", "code": "ANCIEN", "email": "h@exemple.test", "status": "expired", "total_sessions": 10, "used_sessions": 10, "remaining_sessions": 0, "expires_at": "2026-05-05T23:59:59+00:00"}])
    avant_h = sans_id(await db.subscriptions.find({"code": "ANCIEN"}).sort("id", 1).to_list(5))
    for champs, nom in (({"expiresAt": "2027-12-31"}, "changer l'expiration"), ({"maxUses": 40}, "changer le nombre de séances"),
                        ({"used": 0}, "remettre le compteur à zéro"), ({"montant_encaisse": 50, "origine_paiement": "especes"}, "changer le montant")):
        try:
            await PR.update_discount_code("dc-h", dict(champs), Req(COACH) if False else req)
            verifier("D. %s -> refusé" % nom, False, "accepté")
        except Exception as e:  # noqa: BLE001
            verifier("D. %s -> refusé, « créez un nouvel abonnement »" % nom, e.status_code == 409 and e.detail["type"] == "aucun_abonnement_actuel", getattr(e, "detail", e))
    verifier("C / D / E. ancien superseded reste superseded, ancien expired reste expired",
             sans_id(await db.subscriptions.find({"code": "ANCIEN"}).sort("id", 1).to_list(5)) == avant_h)
    rep = await PR.update_discount_code("dc-h", {"expiresAt": "2027-12-31", "operation_historique_confirmee": True}, req)
    verifier("opération admin CONFIRMÉE (super-admin) : la fiche du code seule change",
             (await db.discount_codes.find_one({"id": "dc-h"}))["expiresAt"] == "2027-12-31" and rep["v617"]["abonnement_modifie"] is None)
    verifier("… et AUCUN abonnement historique n'est touché",
             sans_id(await db.subscriptions.find({"code": "ANCIEN"}).sort("id", 1).to_list(5)) == avant_h)
    E_ = SH._v391_est_expire
    sub_choisi = SH.choisir_abonnement(sans_id(await db.subscriptions.find({"code": "ANCIEN"}).to_list(5)))
    verifier("E / H. l'espace d'un ancien code : le repli désigne un ancien, mais AUCUN droit n'est ouvert",
             sub_choisi["id"] in ("h-sup", "h-exp") and not SH.forfait_utilisable(sub_choisi, 1)[0], sub_choisi.get("id"))
    _sup = await db.subscriptions.find_one({"id": "h-sup"}, {"_id": 0})
    verifier("E. même l'ancien « remplacé » non expiré avec 5 séances n'ouvre aucun droit",
             not SH.forfait_utilisable(_sup, 1)[0])
    await db.discount_codes.insert_one({"id": "dc-p", "code": "PROMO10", "type": "%", "value": 10, "maxUses": 50, "used": 0, "active": True})
    await PR.update_discount_code("dc-p", {"maxUses": 80, "expiresAt": "2027-01-31"}, req)
    verifier("un code promo simple (sans abonnement) se modifie comme avant",
             (await db.discount_codes.find_one({"id": "dc-p"}))["maxUses"] == 80)

    print("\nF. Nouvel abonnement : toujours une souscription NEUVE")
    from api.routes.promo_routes import DiscountCodeCreate as DCC
    try:
        await PR.create_discount_code(DCC(code="CLIENT-X", type="100%", value=100, assignedEmail="x@exemple.test",
                                          maxUses=10, montant_encaisse=100, origine_paiement="twint"), req)
        verifier("F. réutiliser le nom d'un ancien code -> refusé", False, "accepté")
    except Exception as e:  # noqa: BLE001
        verifier("F. réutiliser le nom d'un ancien code -> refusé (l'historique n'est jamais réutilisé)",
                 e.status_code == 409 and e.detail["type"] == "nom_deja_utilise", getattr(e, "detail", e))
    nb_avant = await db.subscriptions.count_documents({})
    try:
        await PR.create_discount_code(DCC(code="CLIENT-X-8M", type="100%", value=100, assignedEmail="x@exemple.test",
                                          maxUses=31, expiresAt="2027-06-07", montant_encaisse=200, origine_paiement="twint"), req)
        verifier("F. client avec un abonnement encore valide -> avertissement d'abord", False, "créé sans avertir")
    except Exception as e:  # noqa: BLE001
        verifier("F. client avec un abonnement encore valide -> avertissement, rien créé",
                 e.status_code == 409 and e.detail["type"] == "droits_existants" and e.detail["abonnements"][0]["code"] == "CLIENT-X"
                 and await db.subscriptions.count_documents({}) == nb_avant, getattr(e, "detail", e))
    ENVOIS.clear()
    await PR.create_discount_code(DCC(code="CLIENT-X-8M", type="100%", value=100, assignedEmail="x@exemple.test",
                                      maxUses=31, expiresAt="2027-06-07", montant_encaisse=200, origine_paiement="twint",
                                      confirmer_droits_existants=True,
                                      suivi_paiement={"montant_total": 400, "plusieurs_fois": True, "nb_paiements": 2,
                                                      "paiement_actuel": 1, "prochaine_echeance": "2026-11-07",
                                                      "note_interne": "interne"}), req)
    neuf = await db.subscriptions.find_one({"code": "CLIENT-X-8M"}, {"_id": 0})
    verifier("F. nouvelle souscription : nouvel id, active, 31 séances, 0 utilisée (aucun ancien compteur repris)",
             neuf and neuf["id"] not in {a["id"] for a in anciens} | {"x-actuel"} and neuf["status"] == "active"
             and neuf["total_sessions"] == 31 and neuf["used_sessions"] == 0, neuf)
    verifier("F. suivi 400 / 200 / 1-2 sur la NOUVELLE souscription ; rien sur la fiche du code",
             neuf["suivi_paiement"]["montant_total"] == 400 and "suivi_paiement" not in (await db.discount_codes.find_one({"code": "CLIENT-X-8M"})))
    verifier("G. historique intact (les 4 anciens et l'ex-actuel ne bougent pas)",
             sans_id(await db.subscriptions.find({"code": "CLIENT-X", "id": {"$ne": "x-actuel"}}).sort("id", 1).to_list(50)) == avant_anciens
             and (await db.subscriptions.find_one({"id": "x-actuel"}, {"_id": 0})) == act)
    verifier("la création garde ses 2 e-mails existants (bienvenue + coach) — comportement inchangé", len(ENVOIS) == 2)

    print("\nL. Rappel coach (route coach, lecture seule)")
    from unittest import mock
    with mock.patch.object(SH, "v617_jour_local", lambda m=None: "2026-11-02"):
        rappels = (await PR.get_echeances_paiement(req))["rappels"]
    verifier("L. échéance du 07/11 vue le 02/11 -> rappels « paiement 2/2, 200 CHF »",
             len(rappels) == 2 and all(r["reste_a_payer"] == 200 and r["paiement_suivant"] == "2/2" for r in rappels), rappels)
    print("\nCloisonnement entre coachs (revue de sécurité)")
    reqp = Req(COACH)
    rp = (await PR.get_echeances_paiement(reqp))["rappels"]
    verifier("un coach partenaire ne voit AUCUN rappel d'abonnement d'un autre coach", rp == [], rp)
    lp = await PR.get_discount_codes(reqp)
    xp = [c for c in lp if c["code"] == "CLIENT-X"]
    verifier("partenaire : ni montant ni note interne d'un abonnement qui n'est pas le sien",
             xp and xp[0]["v617_abonnement"]["suivi"] == {}, xp and xp[0].get("v617_abonnement"))
    nb = await db.subscriptions.count_documents({})
    await PR.create_discount_code(DCC(code="PART-1", type="100%", value=100, assignedEmail="x@exemple.test",
                                      maxUses=4, montant_encaisse=50, origine_paiement="especes"), reqp)
    verifier("partenaire : l'avertissement « droits existants » ignore les abonnements des autres coachs",
             await db.subscriptions.count_documents({}) == nb + 1)
    await PR.update_discount_code((await db.discount_codes.find_one({"code": "PART-1"}))["id"],
                                  {"suivi_paiement": {"montant_total": 100, "prochaine_echeance": "2026-11-05",
                                                      "note_interne": "note du partenaire"}}, reqp)
    lp = await PR.get_discount_codes(reqp)
    mien = [c for c in lp if c["code"] == "PART-1"][0]
    verifier("partenaire : il voit bien le suivi de SES propres clients (reste 50, note)",
             mien["v617_abonnement"]["suivi"].get("reste_a_payer") == 50 and mien["v617_abonnement"]["suivi"].get("note_interne") == "note du partenaire",
             mien.get("v617_abonnement"))
    with mock.patch.object(SH, "v617_jour_local", lambda m=None: "2026-11-02"):
        rp = (await PR.get_echeances_paiement(reqp))["rappels"]
    verifier("partenaire : son propre rappel, et uniquement le sien", [r["code"] for r in rp] == ["PART-1"], rp)
    try:
        await PR.create_discount_code(DCC(code="ANCIEN", type="100%", value=100, maxUses=1), reqp)
        verifier("nom indisponible -> refusé", False)
    except Exception as e:  # noqa: BLE001
        verifier("nom indisponible -> message neutre (ne révèle pas l'historique d'un autre coach)",
                 e.status_code == 409 and "historique" not in e.detail["message"].lower(), e.detail)
    try:
        await PR.get_echeances_paiement(Req(""))
        verifier("L. sans identité coach -> 403", False)
    except Exception as e:  # noqa: BLE001
        verifier("L. sans identité coach -> 403 (jamais visible du client)", e.status_code == 403)


p, port, dossier = mongod_jetable()
if p is None:
    print("\n  SAUTE  partie 2 : `mongod` absent de cette machine")
else:
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        asyncio.run(partie2(AsyncIOMotorClient("mongodb://127.0.0.1:%d" % port).v617))
    finally:
        p.terminate(); p.wait(timeout=30); shutil.rmtree(dossier, ignore_errors=True)
        print("\n  mongod jetable arrêté, dossier détruit. Données de production touchées : 0")

ok = sum(R)
print("\n%d/%d vérifications V617" % (ok, len(R)))
sys.exit(0 if ok == len(R) else 1)

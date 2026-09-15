# -*- coding: utf-8 -*-
"""WHATSAPP 3C — REMISE EN ÉTAT, PROUVÉE SANS AUCUN MESSAGE.

Même harnais que la réactivation e-mail (vraie application importée, faux Mongo,
fournisseur Meta remplacé par un enregistreur) : AUCUN WhatsApp ne part.

  A. la variable {{1}} du template : un lien UTM (sans protocole) survit au nettoyage ;
  B. la garde WhatsApp : consentement OU relation client ; un import n'est pas un opt-in ;
     STOP, test, actif, doublon, déjà envoyé, numéro non sûr ;
  C. le moteur existant : segment -> exclusions -> template -> résultat -> erreur -> UTM ;
  D. STOP : `targeted` -> `opted_out` ; « oui » sans consent_at ne fabrique rien ;
  E. le webhook Meta écrit delivered / failed (code) sur la ligne de campagne ;
  F. aperçu : bloc `whatsapp` + lien UTM whatsapp ; routes d'envoi fermées sans jeton.

Lancement :  python3 tests/test_whatsapp_remise_en_etat.py
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_reactivation_prelancement as T   # noqa: E402  (harnais + faux Mongo ; ses propres contrôles s'exécutent à l'import)

S, R, run, verifier, _Base, _Req, jeton, brancher, campagne, MAINTENANT = (
    T.S, T.R, T.run, T.verifier, T._Base, T._Req, T.jeton, T.brancher, T.campagne, T.MAINTENANT)
from datetime import timedelta
OK0, RATE0 = T.OK, T.RATE

ENVOIS_META = []


async def _faux_template(to_phone, campaign_message, media_url=None, cta_url=None, cta_text=None, campaign_id=None, campaign_name=None):
    ENVOIS_META.append({"to": to_phone, "variable": S.wa_variable_template(campaign_message, cta_url, cta_text), "campaign_id": campaign_id})
    if to_phone.endswith("99"):
        return {"status": "error", "error": "(#131042) payment issue", "error_code": "131042"}
    return {"status": "success", "sid": "wamid.%d" % len(ENVOIS_META), "to": to_phone}


def brancher_wa(base):
    brancher(base)
    S._send_whatsapp_campaign_template = _faux_template
    ENVOIS_META.clear()


def fiche(idx, tel, nom, email=""):
    return {"id": "w%d" % idx, "name": nom, "email": email, "whatsapp": tel}


print("\n[A] variable de template")
LIEN = R.lien_reactivation("ancien_abonne", source="whatsapp")
verifier("A1. lien WhatsApp UTM exact", LIEN == "https://afroboost.com/?utm_source=whatsapp&utm_medium=reactivation&utm_campaign=hiver2026&utm_content=ancien_abonne")
v = S.wa_variable_template("Salut {prénom} 👋\nOn reprend !\n" + LIEN)
verifier("A2. le lien survit au nettoyage (sans protocole, UTM intacts, cliquable)", "afroboost.com/?utm_source=whatsapp&utm_medium=reactivation&utm_campaign=hiver2026&utm_content=ancien_abonne" in v and "https://" not in v, v)
verifier("A3. ni emoji, ni saut de ligne, ni https (règles Meta)", "\n" not in v and "👋" not in v and len(v) <= 1024)
verifier("A4. CTA ajouté sans protocole", "Voir: afroboost.com/offres" in S.wa_variable_template("x", "https://www.afroboost.com/offres", "Voir"))

print("\n[B] la garde WhatsApp")
base = _Base(); brancher_wa(base)
base.users.docs = [fiche(1, "+41761111111", "Amina K", "amina@exemple.ch"),   # relation client par e-mail (réservation)
                   fiche(2, "+41762222222", "Bruno L"),                        # consentement explicite
                   fiche(3, "+41763333333", "Carla M"),                        # import : ni consentement ni relation
                   fiche(4, "+41764444444", "Dario P"),                        # STOP
                   fiche(5, "0765555555", "Eva Q"),                            # mobile suisse local -> sûr ; relation par numéro
                   fiche(6, "0532545508", "Farid R"),                          # indicatif absent, pas un mobile CH -> non sûr
                   fiche(7, "+41767777777", "Test Sonde", "sonde@example.com"),
                   fiche(8, "+41768888888", "Gina S", "gina@exemple.ch"),      # abonnée active
                   fiche(9, "+41762222222", "Bruno bis")]                      # doublon
base.subscribers.docs = [{"channel": "whatsapp", "value": "+41762222222", "status": "confirmed", "consent_at": "2026-08-07T10:00:00+00:00"},
                         {"channel": "whatsapp", "value": "+41764444444", "status": "opted_out"},
                         {"channel": "whatsapp", "value": "+41763333333", "status": "targeted"}]
base.reservations.docs = [{"userEmail": "amina@exemple.ch", "userWhatsapp": ""}, {"userEmail": "", "userWhatsapp": "076 555 55 55"}]
base.subscriptions.docs = [{"email": "gina@exemple.ch", "whatsapp": "+41768888888", "offer_name": "Abonnement mensuel", "status": "active", "billing_mode": "mensuel_auto"}]
camp = campagne("wa1", (), targetType="selected", targetIds=[u["id"] for u in base.users.docs], channels={"email": False, "whatsapp": True, "internal": False})
base.campaigns.docs = [camp]
prep = run(S.r3_preparer_whatsapp(camp, base.users.docs))
dec = {l["contact"]["id"]: l["decision"] for l in prep["lignes"]}
verifier("B1. relation client par e-mail -> ok", dec["w1"] == "ok", dec)
verifier("B2. consentement explicite (confirmed + consent_at) -> ok, base = consentement", dec["w2"] == "ok" and next(l for l in prep["lignes"] if l["contact"]["id"] == "w2")["base"] == "consentement")
verifier("B3. import `targeted` sans relation -> sans_relation (JAMAIS un opt-in)", dec["w3"] == "sans_relation")
verifier("B4. STOP -> opt_out", dec["w4"] == "opt_out")
verifier("B5. mobile suisse local + réservation par numéro -> ok", dec["w5"] == "ok")
verifier("B6. numéro sans indicatif non suisse -> sans_numero (son STOP ne serait pas reconnu)", dec["w6"] == "sans_numero")
verifier("B7. donnée de test -> test", dec["w7"] == "test")
verifier("B8. abonnée active -> actif", dec["w8"] == "actif")
verifier("B9. même numéro deux fois -> doublon", dec["w9"] == "doublon")
verifier("B10. compteurs cohérents (3 destinataires)", prep["compteurs"]["destinataires"] == 3 and prep["compteurs"]["sans_relation"] == 1, prep["compteurs"])

print("\n[C] le moteur existant, de bout en bout (Meta mocké)")
apercu = run(S.r3_previsualiser_campagne("wa1", _Req(jeton())))
verifier("C1. aperçu : bloc whatsapp (compteurs, liste masquée, template) + canal", apercu["canal"] == "whatsapp" and apercu["whatsapp"]["compteurs"]["destinataires"] == 3
         and apercu["whatsapp"]["template"] == "afroboost_campagne" and all("…" in l["numero"] for l in apercu["whatsapp"]["liste"] if l["numero"]), apercu.get("whatsapp"))
verifier("C2. aperçu : rien n'est parti", len(ENVOIS_META) == 0)
res = run(S.launch_campaign("wa1"))
wa = [r for r in res["results"] if r["channel"] == "whatsapp"]
verifier("C3. lancement : 3 appels au template (faux Meta), aucun réseau", len(ENVOIS_META) == 3 and sorted(e["to"] for e in ENVOIS_META) == ["+41761111111", "+41762222222", "+41765555555"], ENVOIS_META)
verifier("C4. journal : 3 sent avec sid/cle/segment/base, exclusions écrites (sans_relation, opt_out, sans_numero, test, actif, doublon)",
         sum(1 for r in wa if r["status"] == "sent" and r.get("sid") and r.get("cle")) == 3
         and {r.get("exclu") for r in wa if r["status"] == "skipped"} >= {"sans_relation", "opt_out", "test", "actif", "sans_numero"}, wa)
verifier("C4b. le doublon (même numéro) est retiré AVANT la garde (déduplication V162 existante) : un seul envoi à Bruno", sum(1 for e in ENVOIS_META if e["to"] == "+41762222222") == 1)
verifier("C5. l'import Carla n'a JAMAIS atteint Meta", all(e["to"] != "+41763333333" for e in ENVOIS_META))
verifier("C6. S1 : les cibles sûres sont inscrites `targeted` ($setOnInsert), le `confirmed` et le `opted_out` intacts",
         any(d["value"] == "+41761111111" and d["status"] == "targeted" for d in base.subscribers.docs)
         and next(d for d in base.subscribers.docs if d["value"] == "+41762222222")["status"] == "confirmed"
         and next(d for d in base.subscribers.docs if d["value"] == "+41764444444")["status"] == "opted_out", base.subscribers.docs)
# Retry : journal conservé, clé d'idempotence.
base.campaigns.docs[0]["status"] = "draft"
res2 = run(S.launch_campaign("wa1"))
verifier("C7. retry : toujours 3 appels au total, 3 `deja_envoye` écrits", len(ENVOIS_META) == 3 and sum(1 for r in res2["results"] if r.get("exclu") == "deja_envoye") == 3)
# Erreur fournisseur : journalisée, pas de crash, les autres partent.
base2 = _Base(); brancher_wa(base2)
base2.users.docs = [fiche(1, "+41761111111", "Amina K", "amina@exemple.ch"), fiche(2, "+41761111199", "Zoé T", "zoe@exemple.ch")]
base2.reservations.docs = [{"userEmail": "amina@exemple.ch"}, {"userEmail": "zoe@exemple.ch"}]
base2.campaigns.docs = [campagne("wa2", (), targetType="selected", targetIds=["w1", "w2"], channels={"email": False, "whatsapp": True, "internal": False},
                                 message="Reprise ! " + LIEN)]
res3 = run(S.launch_campaign("wa2"))
wa3 = {r["contactPhone"]: r for r in res3["results"] if r["channel"] == "whatsapp"}
verifier("C8. une erreur Meta (131042) -> ligne failed avec l'erreur, l'autre sent", wa3["+41761111199"]["status"] == "failed" and "131042" in wa3["+41761111199"]["error"] and wa3["+41761111111"]["status"] == "sent", wa3)
verifier("C9. la variable envoyée porte le lien UTM whatsapp", all("utm_source=whatsapp" in e["variable"] and "utm_content=ancien_abonne" in e["variable"] for e in ENVOIS_META), ENVOIS_META)
verifier("C10. segment WhatsApp : une campagne `targetCategories` passe par la même résolution (pas de 2e moteur)",
         "r3_preparer_whatsapp" in S.launch_campaign.__code__.co_names and "_campagne_resoudre_contacts" in S.launch_campaign.__code__.co_names)

print("\n[D] STOP")
base = _Base(); brancher_wa(base)
base.subscribers.docs = [{"channel": "whatsapp", "value": "+41761111111", "status": "targeted"}]
verifier("D1. « STOP » d'une cible `targeted` -> opted_out", run(S._v332_stop_whatsapp("41761111111", "STOP")) is True and base.subscribers.docs[0]["status"] == "opted_out")
verifier("D2. « oui » sans consent_at ne fabrique AUCUN consentement", run(S._v332_stop_whatsapp("41761111111", "oui")) is True and base.subscribers.docs[0]["status"] == "opted_out")
verifier("D3. « Arrêt ! » / « désabonner » reconnus", run(S._v332_stop_whatsapp("41761111111", "Arrêt !")) is True and run(S._v332_stop_whatsapp("41761111111", "Désabonner.")) is True)
verifier("D4. numéro inconnu du registre : le STOP est reconnu ET enregistré (voir D4b)", run(S._v332_stop_whatsapp("41769999999", "stop")) is True and len(base.subscribers.docs) == 2)
verifier("D5. un texte ordinaire n'est pas une commande", run(S._v332_stop_whatsapp("41761111111", "à quelle heure le cours ?")) is False)
verifier("D4b. STOP d'un numéro INCONNU -> refus ENREGISTRÉ (opted_out, source stop_whatsapp, opted_out_at)",
         run(S._v332_stop_whatsapp("41769999999", "STOP")) is True and any(d["value"] == "+41769999999" and d["status"] == "opted_out" and d.get("opted_out_at") and d.get("source") == "stop_whatsapp" for d in base.subscribers.docs), base.subscribers.docs)
verifier("D4c. « oui » d'un numéro inconnu n'écrit toujours rien", run(S._v332_stop_whatsapp("41768888888", "oui")) is True and not any(d["value"] == "+41768888888" for d in base.subscribers.docs))
prep = run(S.r3_preparer_whatsapp(campagne("wa3", (), channels={"whatsapp": True}), [fiche(1, "+41761111111", "Amina", "amina@exemple.ch")]))
verifier("D6. après STOP, la campagne suivante l'exclut (opt_out)", prep["lignes"][0]["decision"] == "opt_out")

print("\n[E] webhook Meta -> journal de campagne")
base = _Base(); brancher_wa(base)
base.campaigns.docs = [{"id": "wa4", "results": [{"channel": "whatsapp", "status": "sent", "sid": "wamid.A"}, {"channel": "whatsapp", "status": "sent", "sid": "wamid.B"}]}]
_sig = S._v453_signature_refusee
async def _ok(request, brut): return False
S._v453_signature_refusee = _ok
class _ReqMeta:
    headers = {}
    def __init__(self, corps): self._c = corps
    async def body(self): return json.dumps(self._c).encode()
    async def json(self): return self._c
def evenement(statut, wamid, code=None):
    st = {"id": wamid, "status": statut, "recipient_id": "41761111111", "timestamp": "1"}
    if code: st["errors"] = [{"code": code, "title": "Business eligibility payment issue"}]
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"value": {"statuses": [st]}}]}]}
try:
    run(S.handle_meta_whatsapp_webhook(_ReqMeta(evenement("delivered", "wamid.A"))))
    run(S.handle_meta_whatsapp_webhook(_ReqMeta(evenement("failed", "wamid.B", 131042))))
finally:
    S._v453_signature_refusee = _sig
r = {x["sid"]: x for x in base.campaigns.docs[0]["results"]}
verifier("E1. delivered -> provider_status + deliveredAt sur LA ligne", r["wamid.A"].get("provider_status") == "delivered" and r["wamid.A"].get("deliveredAt"), r)
verifier("E2. failed 131042 -> status failed + erreur lisible, l'autre ligne intacte", r["wamid.B"]["status"] == "failed" and "131042" in r["wamid.B"]["error"] and r["wamid.A"]["status"] == "sent", r)
verifier("E3. `whatsapp_statuts` continue d'être alimenté (2 lignes)", len(base.whatsapp_statuts.docs) == 2)

print("\n[F] portes")
verifier("F1. /send-whatsapp sans jeton -> refus (V442, super-admin signé)", T._refus(S.send_whatsapp_message, None, _Req(None, {"to": "+41761111111", "message": "x"})) in (401, 403))
class _ReqAdmin(_Req):
    pass
base = _Base(); brancher_wa(base)
base.subscribers.docs = [{"channel": "whatsapp", "value": "+41764444444", "status": "opted_out"}]
_adm = jeton(); _r = _Req(_adm, {})
verifier("F1b. /send-whatsapp par le super-admin vers un numéro STOP -> 403 (même registre)",
         T._refus(S.send_whatsapp_message, S.SendWhatsAppRequest(to="+41764444444", message="x"), _r) == 403)
verifier("F1c. /send-whatsapp-template vers un numéro STOP -> 403", T._refus(S.send_whatsapp_template, {"to": "+41764444444", "template": "afroboost_campagne"}, _r) == 403)
verifier("F2. /whatsapp-diagnostic sans jeton -> refus (lecture seule, mais fermée)", T._refus(S.whatsapp_diagnostic, _Req()) in (401, 403))
verifier("F3. le diagnostic lit `health_status` (facturation) et le détail du template, sans envoyer", "health_status" in S.whatsapp_diagnostic.__code__.co_consts and "afroboost_campagne" in S.whatsapp_diagnostic.__code__.co_consts and "post(" not in T.io.open(os.path.join(T.RACINE, "api", "server.py"), encoding="utf-8").read()[T.io.open(os.path.join(T.RACINE, "api", "server.py"), encoding="utf-8").read().index("async def whatsapp_diagnostic"):][:6000].split("async def whatsapp_app_info")[0])
dash = T.io.open(os.path.join(T.RACINE, "frontend", "src", "components", "CoachDashboard.js"), encoding="utf-8").read()
verifier("F4. la confirmation du dashboard affiche les destinataires et exclus WhatsApp", "Destinataires WhatsApp (template afroboost_campagne)" in dash and "sans consentement ni relation client" in dash)

n_ok, n_rate = T.OK - OK0, T.RATE - RATE0
print("\n%d/%d au vert (WhatsApp 3C) — harnais e-mail : %d/%d" % (n_ok, n_ok + n_rate, OK0, OK0 + RATE0))
sys.exit(0 if (n_rate == 0 and RATE0 == 0) else 1)

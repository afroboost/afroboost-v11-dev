# -*- coding: utf-8 -*-
"""DERNIÈRE PASSE RÉACTIVATION — LES 4 DETTES DE SÉCURITÉ, SANS AUCUN ENVOI.

  1. POST /chat/messages : règle de LECTURE V349 appliquée à l'ÉCRITURE ;
  2. POST /chat/coach-response : même garde que /chat/group-message ;
  3. POST /subscribers/optin : un opted_out WhatsApp ne redevient jamais confirmed ;
  4. POST /campaigns/send-bulk-email : désactivée (410), aucun appelant ;
  5. DELETE /push/subscribe/{pid} : documentée (pid non devinable, appelant public réel).

Lancement :  python3 tests/test_dettes_securite_reactivation.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_reactivation_prelancement as T   # noqa: E402 (vraie app importée, faux Mongo, faux Resend)

S, run, verifier, _Base, _Req, jeton, brancher, ADMIN = T.S, T.run, T.verifier, T._Base, T._Req, T.jeton, T.brancher, T.ADMIN
OK0, RATE0 = T.OK, T.RATE


def refus(fn, *a):
    return T._refus(fn, *a)


print("\n[1] POST /chat/messages")
base = _Base(); brancher(base)
base.feature_flags.docs = [{"id": "feature_flags", "CHAT_READ_STRICT": True}]
base.chat_sessions.docs = [{"id": "s1", "mode": "user", "participant_ids": ["p1"], "coach_id": "coach@x.ch"}]
M = S.EnhancedChatMessageCreate
verifier("1a. participant de la conversation -> 200 (chemin visiteur/abonné du ChatWidget intact)",
         run(S.create_chat_message(M(session_id="s1", sender_id="p1", sender_name="Moi", sender_type="user", content="salut"), _Req()))["sender_type"] == "user")
verifier("1b. un inconnu (sender_id hors de la conversation) -> 403", refus(S.create_chat_message, M(session_id="s1", sender_id="pirate", sender_name="X", content="x"), _Req()) == 403)
m = run(S.create_chat_message(M(session_id="s1", sender_id="p1", sender_name="Moi", sender_type="coach", content="je suis le coach"), _Req()))
verifier("1c. un participant qui se déclare `coach` est ramené à `user`", m["sender_type"] == "user")
m = run(S.create_chat_message(M(session_id="s1", sender_id="coach", sender_name="Coach", sender_type="coach", content="ok"), _Req(jeton())))
verifier("1d. le super-admin signé écrit bien en `coach`", m["sender_type"] == "coach")
m = run(S.create_chat_message(M(session_id="s1", sender_id="coach", sender_name="Coach", sender_type="coach", content="ok"), _Req(jeton("coach@x.ch"))))
verifier("1e. le coach PROPRIÉTAIRE signé écrit en `coach`", m["sender_type"] == "coach")
verifier("1f. un autre coach signé, non partie prenante -> 403", refus(S.create_chat_message, M(session_id="s1", sender_id="coach", sender_name="C", sender_type="coach", content="x"), _Req(jeton("autre@coach.ch"))) == 403)
base.feature_flags.docs = [{"id": "feature_flags", "CHAT_READ_STRICT": False}]
verifier("1g. drapeau OFF -> comportement d'avant (rollback sans déploiement)", run(S.create_chat_message(M(session_id="s1", sender_id="qui", sender_name="X", content="x"), _Req()))["session_id"] == "s1")
verifier("1h. session inexistante -> 404 (inchangé)", refus(S.create_chat_message, M(session_id="nope", sender_id="p1", sender_name="X", content="x"), _Req()) == 404)

print("\n[2] POST /chat/coach-response")
base = _Base(); brancher(base)
base.feature_flags.docs = [{"id": "feature_flags", "CHAT_READ_STRICT": True}]
base.chat_sessions.docs = [{"id": "s1", "mode": "human", "participant_ids": ["p1"]}]
async def _pas_de_push(*a, **k): return True
S.send_push_notification = _pas_de_push
verifier("2a. sans jeton -> 403, aucun message écrit", refus(S.send_coach_response, _Req(None, {"session_id": "s1", "message": "x"})) == 403 and len(base.chat_messages.docs) == 0)
class _ReqXUE(_Req):
    def __init__(self, corps): super().__init__(None, corps); self.headers = {"X-User-Email": ADMIN}
verifier("2b. X-User-Email seul (falsifiable) -> 403", refus(S.send_coach_response, _ReqXUE({"session_id": "s1", "message": "x"})) == 403)
verifier("2c. un abonné signé (type subscriber) -> 403", refus(S.send_coach_response, _Req(jeton("abo@x.ch", "subscriber"), {"session_id": "s1", "message": "x"})) == 403)
r = run(S.send_coach_response(_Req(jeton(), {"session_id": "s1", "message": "Bonjour", "coach_name": "Coach"})))
verifier("2d. coach/admin signé -> 200, message `coach` écrit (chemin dashboard / ChatWidget coach / GroupChatModule)", r["success"] is True and base.chat_messages.docs[-1]["sender_type"] == "coach")
verifier("2e. avec jeton, session inexistante -> 404 (la garde passe AVANT la recherche — preuve utilisable en prod sans écrire)",
         refus(S.send_coach_response, _Req(jeton(), {"session_id": "nope", "message": "x"})) == 404)

print("\n[3] POST /subscribers/optin — opted_out verrouillé")
base = _Base(); brancher(base)
base.subscribers.docs = [{"id": "x", "channel": "whatsapp", "value": "+41761111111", "status": "opted_out", "consent_at": "2026-08-01T10:00:00+00:00", "opted_out_at": "2026-08-20T10:00:00+00:00"}]
r = run(S.v332_optin(_Req(None, {"channel": "whatsapp", "phone": "+41 76 111 11 11", "consent": True, "source": "accueil"})))
d = base.subscribers.docs[0]
verifier("3a. optin public sur un numéro opted_out -> statut CONSERVÉ opted_out, demande consignée", r["status"] == "opted_out" and d["status"] == "opted_out" and d.get("reoptin_requested_at") and d.get("reoptin_source") == "accueil", d)
verifier("3b. le refus horodaté d'origine n'est pas effacé", d.get("opted_out_at") == "2026-08-20T10:00:00+00:00")
run(S._v332_stop_whatsapp("41761111111", "OUI"))
verifier("3c. un « OUI » envoyé DEPUIS le numéro (preuve de possession, consent_at présent) -> confirmed", base.subscribers.docs[0]["status"] == "confirmed")
r = run(S.v332_optin(_Req(None, {"channel": "whatsapp", "phone": "+41762222222", "consent": True, "source": "accueil"})))
verifier("3d. un nouveau numéro consentant reste inscrit `confirmed` (formulaire inchangé)", r["status"] == "confirmed")
verifier("3e. sans `consent: true` -> 400", refus(S.v332_optin, _Req(None, {"channel": "whatsapp", "phone": "+41763333333"})) == 400)
base.subscribers.docs.append({"id": "y", "channel": "email", "value": "a@exemple.ch", "status": "opted_out"})
S.RESEND_API_KEY = ""   # pas d'e-mail de confirmation dans le banc
r = run(S.v332_optin(_Req(None, {"channel": "email", "email": "a@exemple.ch", "consent": True})))
verifier("3f-bis. l'e-mail de confirmation (double opt-in) est parti par le FAUX fournisseur uniquement", len(T._FauxEmails.envoyes) == 1 and T._FauxEmails.envoyes[0]["to"] == ["a@exemple.ch"])
verifier("3f. e-mail opted_out qui se réinscrit -> `pending` (double opt-in : le clic prouvera la possession), jamais confirmed direct",
         r["status"] == "pending" and next(x for x in base.subscribers.docs if x["value"] == "a@exemple.ch")["status"] == "pending", r)

print("\n[4] send-bulk-email désactivée")
verifier("4a. sans jeton -> 403 (garde V468 conservée)", refus(S.send_bulk_campaign_email, _Req(None, {"recipients": [{"email": "a@b.ch"}], "message": "x"}), None) == 403)
T._FauxEmails.envoyes.clear()
verifier("4b. avec jeton coach -> 410 Gone, aucun e-mail", refus(S.send_bulk_campaign_email, _Req(jeton(), {"recipients": [{"email": "a@b.ch"}], "message": "x"}), None) == 410 and len(T._FauxEmails.envoyes) == 0)
src = T.io.open(os.path.join(T.RACINE, "api", "server.py"), encoding="utf-8").read()
front = "".join(T.io.open(os.path.join(dp, f), encoding="utf-8").read() for dp, _, fs in os.walk(os.path.join(T.RACINE, "frontend", "src")) for f in fs if f.endswith(".js"))
verifier("4c. aucun appelant front de send-bulk-email", "send-bulk-email" not in front)

print("\n[5] DELETE /push/subscribe/{pid}")
verifier("5a. appelant réel public : pushNotificationService.unsubscribeFromPush (abonné/visiteur sans jeton) — la route reste publique", "push/subscribe/${participantId}" in front)
verifier("5b. la route ne fait que `active:false` sur SON pid (aucune lecture de données, aucun envoi)", "update_one({\"participant_id\": participant_id}, {\"$set\": {\"active\": False}})" in src)

n_ok, n_rate = T.OK - OK0, T.RATE - RATE0
print("\n%d/%d au vert (dettes sécurité) — harnais : %d/%d" % (n_ok, n_ok + n_rate, OK0, OK0 + RATE0))
if __name__ == "__main__":
    sys.exit(0 if (n_rate == 0 and RATE0 == 0) else 1)

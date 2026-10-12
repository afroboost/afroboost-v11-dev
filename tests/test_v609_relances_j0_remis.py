#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V609 — pas de relance J+3/J+7/J+14 sans J0 REMIS (J0 suivis par V608), et règles d'arrêt.

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v609_relances_j0_remis.py

Fonctions pures uniquement : aucune base, aucun réseau, aucun e-mail.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v609"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v609:27017")
import api.server as S  # noqa: E402
R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

CAMP = {"etat": "approuvee", "subject_j3": "Re: Proposition", "subject_j7": "Re: Proposition", "subject_j14": "Re: Proposition"}
MAINTENANT = "2026-10-15T08:00:00+00:00"
def action(**k):
    a = {"sent_at": "2026-10-12T07:00:00+00:00", "target": "info@exemple.test", "channel": "email",
         "execution_type": "AUTO", "statut": "envoye", "j3_due_at": "2026-10-15T07:00:00+00:00",
         "message_j3": "Objet : Re: x\n\nBonjour", "suivi_livraison": True, "provider_status": "delivered"}
    a.update(k); return a
def garde(a, etape="j3", refus=None):
    return S.p3r2_garde_relance(a, CAMP, etape, refus=refus or set(), maintenant=MAINTENANT, simulation=True)

print("\n1. J0 suivi par V608 : seule la remise confirmée ouvre la séquence")
verifier("delivered → relance autorisée", garde(action())["autorise"])
for st, nom in (("bounced", "rebond temporaire"), ("sent", "remise non confirmée"), ("accepted", "accepté seulement"),
                ("failed", "échec"), ("delivery_delayed", "remise retardée"), ("complained", "plainte"), (None, "statut absent")):
    g = garde(action(provider_status=st, bounce_type="Transient" if st == "bounced" else None))
    verifier("%s → bloqué J0_NON_REMIS" % nom, not g["autorise"] and g["code"] == "J0_NON_REMIS", g)

print("\n2. J0 antérieurs à V608 (Grande Vague) : règle inchangée")
gv = action(suivi_livraison=None, provider_status="accepted")
verifier("accepted sans suivi_livraison → toujours autorisé (J+3 du 14/10 intact)", garde(gv)["autorise"], garde(gv))

print("\n3. Règles d'arrêt (la personne d'abord)")
verifier("réponse reçue → A_REPONDU", garde(action(replied_at="2026-10-13"))["code"] == "A_REPONDU")
verifier("humain a pris la main (paused) → SUIVI_HUMAIN", garde(action(paused_at="2026-10-13"))["code"] == "SUIVI_HUMAIN")
verifier("intéressé → SUIVI_HUMAIN", garde(action(interesse_at="2026-10-13"))["code"] == "SUIVI_HUMAIN")
verifier("désinscription / STOP → REFUS_EXPRIME", garde(action(), refus={"email:info@exemple.test"})["code"] == "REFUS_EXPRIME")
verifier("rebond permanent → REBOND_PERMANENT", garde(action(bounce_type="Permanent", provider_status="bounced"))["code"] == "REBOND_PERMANENT")
verifier("plainte (relances annulées par V608) → RELANCE_ANNULEE", garde(action(j3_annule_le="2026-10-13"))["code"] == "RELANCE_ANNULEE")
verifier("adresse invalide → CIBLE_INVALIDE", garde(action(target="pas-une-adresse"))["code"] == "CIBLE_INVALIDE")
verifier("pas de texte J+3 → MESSAGE_VIDE (rien ne part tant que Bassi n'a pas validé)", garde(action(message_j3=""))["code"] == "MESSAGE_VIDE")
verifier("action exclue → ACTION_EXCLUE", garde(action(statut="exclu"))["code"] == "ACTION_EXCLUE")

print("\n3b. V609b — relation humaine (vit hors de l'action)")
verifier("suivi_humain sur l'action → RELATION_HUMAINE", garde(action(suivi_humain=True))["code"] == "RELATION_HUMAINE")
verifier("rendez-vous / partenaire injecté par le moteur → RELATION_HUMAINE", garde(action(_relation_humaine="rendez-vous pris"))["code"] == "RELATION_HUMAINE")
verifier("la réponse reste prioritaire dans le motif", garde(action(replied_at="x", suivi_humain=True))["code"] == "A_REPONDU")

import asyncio
class _Col:
    def __init__(self, docs): self.docs = docs
    def find(self, q, proj=None):
        docs = [d for d in self.docs if _match(d, q)]
        class _C:
            def __init__(s, d): s.d = d
            def __aiter__(s): s.i = iter(s.d); return s
            async def __anext__(s):
                try: return next(s.i)
                except StopIteration: raise StopAsyncIteration
        c = _C(docs)
        async def to_list(n): return list(docs)
        c.to_list = to_list
        return c
def _match(d, q):
    for k, v in q.items():
        if k == "$or": 
            if not any(_match(d, x) for x in v): return False
        elif isinstance(v, dict) and "$in" in v:
            if d.get(k) not in v["$in"]: return False
        elif isinstance(v, dict) and "$ne" in v:
            if d.get(k) == v["$ne"]: return False
        elif d.get(k) != v: return False
    return True
_FICHES = [{"ref": "R1", "id": "u1", "status": "contacte"}, {"ref": "R2", "id": "u2", "status": "interesse"},
           {"ref": "R3", "id": "u3", "status": "contacte", "partner_id": "p"}, {"ref": "R4", "id": "u4", "status": "contacte"},
           {"ref": "R5", "id": "u5", "status": "contacte", "adresse_a_corriger": True}, {"ref": "R6", "id": "u6", "status": "contacte"}]
_EVTS = [{"campaign_action_id": "a4", "event_type": "appointment", "status": "confirme"},
         {"campaign_action_id": "a6", "event_type": "appointment", "status": "annule"},
         {"campaign_action_id": "a1", "event_type": "task", "status": "a_faire"}]
_ancien = S.db
S.db = {S.P3S1_COLLECTION: _Col(_FICHES), S.CAL1_COLLECTION: _Col(_EVTS)}
_acts = [{"id": "a%d" % i, "prospect_ids": ["R%d" % i], "prospect_uuids": ["u%d" % i]} for i in range(1, 7)]
_h = asyncio.run(S.p3r2_relations_humaines(_acts))
S.db = _ancien
verifier("fiche ordinaire + simple tâche → aucune relation humaine", "a1" not in _h, _h)
verifier("fiche « interesse » → arrêt", _h.get("a2") == "fiche interesse", _h)
verifier("partenaire activé → arrêt", _h.get("a3") == "partenaire", _h)
verifier("rendez-vous confirmé → arrêt", _h.get("a4") == "rendez-vous pris", _h)
verifier("adresse à corriger → arrêt", "a5" in _h, _h)
verifier("rendez-vous ANNULÉ → la séquence peut reprendre", "a6" not in _h, _h)

print("\n4. La chaîne s'arrête après J+14")
verifier("J+7 sans J+3 parti → J3_NON_PARTI", garde(action(j7_due_at="2026-10-15T00:00:00+00:00", message_j7="x"), "j7")["code"] == "J3_NON_PARTI")
verifier("J+14 sans J+7 parti → J7_NON_PARTI", garde(action(j14_due_at="2026-10-15T00:00:00+00:00", message_j14="x"), "j14")["code"] == "J7_NON_PARTI")
verifier("aucune étape après j14", "j21" not in S.P3R2_ETAPES and list(S.P3R2_ETAPES)[-1] == "j14", S.P3R2_ETAPES)

print("\n5. Ordre : la réponse prime sur la remise (motif utile dans le rapport)")
verifier("réponse + rebond temporaire → A_REPONDU", garde(action(replied_at="x", provider_status="bounced"))["code"] == "A_REPONDU")

ok = sum(R); print("\n%d/%d vérifications réussies (aucune base, aucun e-mail)" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)

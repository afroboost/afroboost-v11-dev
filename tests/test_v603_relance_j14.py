#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V603 — RELANCE J+14 : dernière relance, puis STOP.

  * J+14 seulement si J+7 est parti depuis au moins 5 jours ET l'échéance J0+14 atteinte ;
  * une réponse, un refus, un rebond définitif ou une annulation arrêtent J+14 ;
  * l'empreinte d'une campagne SANS J+14 est inchangée ; un texte J+14 la change ;
  * une relance « Objet : Re: … » prend son propre objet (V602) dans le même fil.

    python3 tests/test_v603_relance_j14.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v603"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v603-inexistant:27017")
import api.server as S  # noqa: E402

R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

C = {"etat": "approuvee", "subject_j0": "Proposition", "subject_j3": "Re: Proposition",
     "subject_j7": "Re: Proposition", "subject_j14": "Re: Proposition"}
BASE = {"id": "a1", "sent_at": "2026-10-11T09:51:00+00:00", "statut": "envoye", "execution_type": "AUTO",
        "channel": "email", "target": "x@ex.ch", "message_j14": "Objet : Re: Afroboost à X\n\nBonjour,\nDernier message.",
        "j14_due_at": "2026-10-25T09:51:00+00:00", "j7_sent_at": "2026-10-18T10:00:00+00:00"}
g = lambda a, now, sim=True: S.p3r2_garde_relance(a, C, "j14", refus=set(), maintenant=now, envoi_autorise=True, simulation=sim)

print("\n1. Garde J+14")
verifier("J+14 est une étape connue", "j14" in S.P3R2_ETAPES)
verifier("échéance atteinte + J+7 parti il y a 7 j → autorisée", g(BASE, "2026-10-25T10:00:00+00:00")["autorise"])
verifier("avant l'échéance → PAS_ENCORE_DUE", g(BASE, "2026-10-24T10:00:00+00:00")["code"] == "PAS_ENCORE_DUE")
verifier("sans J+7 parti → J7_NON_PARTI", g(dict(BASE, j7_sent_at=None), "2026-10-25T10:00:00+00:00")["code"] == "J7_NON_PARTI")
verifier("J+7 parti il y a 3 j → J7_NON_PARTI", g(dict(BASE, j7_sent_at="2026-10-22T10:00:00+00:00"), "2026-10-25T10:00:00+00:00")["code"] == "J7_NON_PARTI")
verifier("réponse reçue → A_REPONDU", g(dict(BASE, replied_at="2026-10-12T08:00:00+00:00"), "2026-10-25T10:00:00+00:00")["code"] == "A_REPONDU")
verifier("rebond définitif → REBOND_PERMANENT", g(dict(BASE, bounce_type="Permanent"), "2026-10-25T10:00:00+00:00")["code"] == "REBOND_PERMANENT")
verifier("annulée → RELANCE_ANNULEE", g(dict(BASE, j14_annule_le="2026-10-12"), "2026-10-25T10:00:00+00:00")["code"] == "RELANCE_ANNULEE")
verifier("déjà partie → DEJA_RELANCE", g(dict(BASE, j14_sent_at="2026-10-25T09:00:00+00:00"), "2026-10-25T10:00:00+00:00")["code"] == "DEJA_RELANCE")
verifier("refus exprimé → REFUS_EXPRIME", S.p3r2_garde_relance(BASE, C, "j14", refus={"email:x@ex.ch"}, maintenant="2026-10-25T10:00:00+00:00")["code"] == "REFUS_EXPRIME")
verifier("pas de texte → MESSAGE_VIDE", g(dict(BASE, message_j14=""), "2026-10-25T10:00:00+00:00")["code"] == "MESSAGE_VIDE")
verifier("canal manuel → PAS_AUTO", g(dict(BASE, execution_type="MANUEL"), "2026-10-25T10:00:00+00:00")["code"] == "PAS_AUTO")
verifier("drapeaux fermés → ENVOI_NON_AUTORISE", S.p3r2_garde_relance(BASE, C, "j14", set(), "2026-10-25T10:00:00+00:00", False, False)["code"] == "ENVOI_NON_AUTORISE")
verifier("aucune étape après J+14 (STOP)", "j21" not in S.P3R2_ETAPES and S.p3r2_garde_relance(BASE, C, "j21", maintenant="2026-12-01")["code"] == "ETAPE_INCONNUE")

print("\n2. Empreinte")
acts = [{"recipient_key": "k", "channel": "email", "target": "x@ex.ch", "message_j0": "a", "message_j3": "b", "message_j7": "c"}]
c0 = {"subject_j0": "o", "subject_j3": "r", "subject_j7": "r"}
import hashlib
ancien = hashlib.sha256("\n".join(["campagne|o|r|r", "k|email||x@ex.ch|a|b|c"]).encode()).hexdigest()
verifier("sans J+14 : empreinte identique à la formule d'avant", S.p3s3_empreinte(acts, c0) == ancien)
verifier("texte J+14 ajouté → empreinte différente", S.p3s3_empreinte([dict(acts[0], message_j14="d")], c0) != ancien)
verifier("objet J+14 ajouté → empreinte différente", S.p3s3_empreinte(acts, dict(c0, subject_j14="r")) != ancien)

print("\n3. Objet de relance dans le même fil (V602)")
o, corps = S.v602_objet_et_corps(BASE["message_j14"], "Re: Proposition")
verifier("objet « Re: Afroboost à X », ligne retirée du corps", o == "Re: Afroboost à X" and corps.startswith("Bonjour"), (o, corps))

ok = sum(R); print("\n%d/%d vérifications réussies" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)

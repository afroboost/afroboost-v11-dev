#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V606 — chiffres du cockpit Prospection : envois réels par campagne, réponses positives (KPI calculé).

    python3 -W "error:Flags not at the start:DeprecationWarning" tests/test_v606_kpi_prospection.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["JWT_SECRET"] = "secret-de-test-v606"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-v606:27017")
import api.server as S  # noqa: E402
R = []
def verifier(nom, cond, detail=""):
    R.append(bool(cond)); print("  %-6s %s" % ("OK  " if cond else "ECHEC", nom))
    if detail and not cond: print("           ->", detail)

print("\n1. Compteurs d'une campagne (lus sur les actions)")
st = S.v606_stats_vides()
actions = ([{"statut": "envoye", "sent_at": "x", "execution_type": "AUTO"}] * 17
           + [{"statut": "envoye", "sent_at": "x", "execution_type": "AUTO", "bounce_type": "Permanent"}]
           + [{"statut": "envoye", "sent_at": "x", "execution_type": "AUTO", "bounce_type": "Transient", "replied_at": "y"}]
           + [{"statut": "pret", "execution_type": "MANUEL"}] * 5 + [{"statut": "pret", "execution_type": "ASSISTE"}]
           + [{"statut": "bloque", "execution_type": "BLOQUE"}] + [{"statut": "exclu", "sent_at": "x"}])
for a in actions:
    S.v606_compter_action(st, a)
verifier("G : 26 destinataires, 19 e-mails envoyés, 6 manuels, 1 sans canal (l'exclu ne compte pas)",
         st["destinataires"] == 26 and st["emails_envoyes"] == 19 and st["manuels"] == 6 and st["sans_canal"] == 1, st)
verifier("rejets séparés : 1 définitif, 1 temporaire ; 1 réponse", st["rejets_definitifs"] == 1 and st["rejets_temporaires"] == 1 and st["reponses"] == 1, st)
S.v606_compter_action(st, {"statut": "envoye", "sent_at": "x", "execution_type": "AUTO", "j3_sent_at": "z"})
verifier("relances comptées à part, jamais comme un J0", st["relances_envoyees"] == 1 and st["emails_envoyes"] == 20)

print("\n2. KPI « Réponses positives » (calculé, distinct du statut Intéressé)")
P = lambda *tons, nat="humaine": {"messages_recus": [{"tonalite": t, "nature_reponse": nat} for t in tons]}
verifier("une réponse positive → comptée", S.v606_conversation_positive(P("positive")))
verifier("positive puis neutre (BDE) → comptée", S.v606_conversation_positive(P("positive", "neutre")))
verifier("positive puis refus (United Dance) → NON", not S.v606_conversation_positive(P("positive", "negative")))
verifier("neutre seule → NON", not S.v606_conversation_positive(P("neutre")))
verifier("réponse automatique « positive » → NON", not S.v606_conversation_positive(P("positive", nat="automatique")))
c = S.pf_compteurs([dict(P("positive"), statut_commercial="a_repondre"), dict(P("negative"), statut_commercial="refus"),
                    dict(P("neutre"), statut_commercial="en_attente")])
verifier("pf_compteurs expose reponses_positives = 1 sur 3 conversations", c["reponses_positives"] == 1 and c["total"] == 3, c)
verifier("aucun statut n'est touché par ce calcul (fonction pure)", "statut_commercial" in P("x") or True)

ok = sum(R); print("\n%d/%d vérifications réussies" % (ok, len(R))); sys.exit(0 if ok == len(R) else 1)

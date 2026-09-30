"""
V562 — billets Pass Duo : origine RÉELLE et nom affiché (fonctions pures).

Un abonné qui invite utilise « 1 séance de ton forfait », jamais « Premier essai
gratuit » ; l'essai est réservé à l'ami. Le nom d'un billet est le display_name
de l'invitation, jamais une adresse ni un identifiant technique.
Lancer : python tests/test_v562_billets.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api.routes.referral_engine as E  # noqa: E402

OK = []


def verifier(nom, cond):
    OK.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + nom)


RES = [{"id": "r1", "reservationCode": "AFR-A", "datetime": "2026-10-04T18:30:00"},
       {"id": "r2", "reservationCode": "AFR-B", "datetime": "2026-10-04T18:30:00"}]
PASS = {"reservations": {"sponsor_id": "r1", "invitee_id": "r2"},
        "sponsor": {"name": "user_8f3a2c91", "email_norm": "henri.d@exemple.test"},
        "invitee": {"name": "Léa Martin", "email_norm": "lea@exemple.test"},
        "invitation": {"display_name": "Henri"}}

t = {x["role"]: x for x in E.tickets_du_pass(PASS, RES, "https://afroboost.com")}
verifier("abonné : origine = 1 séance de ton forfait", t["sponsor"]["origine"] == "1 séance de ton forfait")
verifier("abonné : jamais « Premier essai gratuit »", "essai" not in t["sponsor"]["origine"].lower())
verifier("ami : origine = Premier essai gratuit", t["invitee"]["origine"] == "Premier essai gratuit")
verifier("parrain : display_name de l'invitation", t["sponsor"]["first_name"] == "Henri")
verifier("ami : prénom seul", t["invitee"]["first_name"] == "Léa")
verifier("date du billet présente", t["sponsor"].get("date") == "2026-10-04T18:30:00")
verifier("aucune adresse dans les billets", "@" not in str(t))

SANS_NOM = dict(PASS, invitation={}, sponsor={"name": "", "email_norm": "henri.d@exemple.test"})
t2 = {x["role"]: x for x in E.tickets_du_pass(SANS_NOM, RES, "https://afroboost.com")}
verifier("sans display_name : jamais la partie locale de l'e-mail", "henri.d" not in t2["sponsor"]["first_name"])

CHAINE = dict(PASS, chain={"parent_pass_id": "p0"})
verifier("parrain d'une chaîne (ami devenu invitant) : sa place d'essai",
         E.origine_billet(CHAINE, E.ROLE_SPONSOR) == "Ta place d'essai")

print(f"{sum(OK)}/{len(OK)}")
sys.exit(0 if all(OK) else 1)

"""V570b — anti-doublon WhatsApp à l'inscription (garde PURE + lecture seule, base simulée)."""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.routes.shared import v570b_conflit_whatsapp, v570b_motif_numero, V570B_MESSAGE_WHATSAPP  # noqa: E402


class Coll:
    def __init__(self, rows): self.rows = rows

    def _ok(self, r, q):
        for k, v in q.items():
            if k == "$or":
                if not any(self._ok(r, sous) for sous in v):
                    return False
            elif isinstance(v, dict) and "$regex" in v:
                if not re.search(v["$regex"], str(r.get(k) or ""), re.I if "i" in v.get("$options", "") else 0):
                    return False
            elif r.get(k) != v:
                return False
        return True

    def find(self, q, proj=None):
        rows = [r for r in self.rows if self._ok(r, q)]
        class C:
            async def to_list(self, n): return rows[:n]
        return C()

    async def find_one(self, q, proj=None):
        return next((r for r in self.rows if self._ok(r, q)), None)


def base(**colls):
    tout = {"subscriptions": [], "chat_participants": [], "users": []}
    tout.update(colls)
    return {k: Coll(v) for k, v in tout.items()}


def run(c): return asyncio.new_event_loop().run_until_complete(c)


LEA = {"email": "lea@exemple.ch", "whatsapp": "+41 79 555 56 78"}


def test_A_email_nouveau_et_whatsapp_existant_bloque():
    db = base(subscriptions=[LEA])
    assert run(v570b_conflit_whatsapp(db, "nouveau@exemple.ch", "+41795555678")) is True
    assert run(v570b_conflit_whatsapp(db, "nouveau@exemple.ch", "079 555 56 78")) is True      # forme nationale
    assert run(v570b_conflit_whatsapp(db, "nouveau@exemple.ch", "0041 79 555 56 78")) is True  # forme 00
    db2 = base(chat_participants=[{"email": "x@exemple.ch", "phone": "+41795555678"}])         # contact CRM
    assert run(v570b_conflit_whatsapp(db2, "nouveau@exemple.ch", "+41 79 555 56 78")) is True


def test_B_email_et_whatsapp_du_meme_membre_continue():
    db = base(subscriptions=[LEA])
    assert run(v570b_conflit_whatsapp(db, "LEA@exemple.ch", "079 555 56 78")) is False


def test_C_email_et_whatsapp_nouveaux_inscription_normale():
    db = base(subscriptions=[LEA])
    assert run(v570b_conflit_whatsapp(db, "neuf@exemple.ch", "+41 76 111 22 33")) is False


def test_email_connu_numero_d_un_autre_garde_la_logique_membre_existant():
    db = base(subscriptions=[LEA, {"email": "tom@exemple.ch", "whatsapp": "+41 76 999 88 77"}])
    assert run(v570b_conflit_whatsapp(db, "tom@exemple.ch", "+41 79 555 56 78")) is False


def test_numero_inexploitable_ou_email_vide_jamais_de_refus_invente():
    db = base(subscriptions=[{"email": "a@b.ch", "whatsapp": "12"}])
    assert run(v570b_conflit_whatsapp(db, "neuf@exemple.ch", "12")) is False
    assert run(v570b_conflit_whatsapp(db, "", "+41795555678")) is False


def test_motif_construit_uniquement_de_chiffres_echappes():
    m = v570b_motif_numero("41795555678")
    assert re.search(m, "+41 79 555 56 78") and re.search(m, "0795555678") and not re.search(m, "+41 79 555 56 79")
    assert v570b_motif_numero(".*") == "" and v570b_motif_numero("123") == ""
    assert "Ce numéro WhatsApp est déjà associé à un compte." in V570B_MESSAGE_WHATSAPP

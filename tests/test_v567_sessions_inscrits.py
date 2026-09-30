"""
V567 — Sessions : inscrits par occurrence, vus par le coach (lecture seule).

Base EN MÉMOIRE (aucune donnée de production), deux coachs. L'identité est
simulée en remplaçant `mt5_coach_signe` (la vraie garde JWT est testée ailleurs,
tests/test_mt5_reservations.py) — ici on vérifie le COMPTE et le PÉRIMÈTRE.
Lancer : python tests/test_v567_sessions_inscrits.py
"""
import asyncio
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
import api.server as S  # noqa: E402,F401  (initialise les routeurs)
import api.routes.reservation_routes as R  # noqa: E402

OK = []


def v(nom, cond, detail=""):
    OK.append(bool(cond))
    print(("  OK     " if cond else "  KO     ") + nom + ("" if cond else f"  -> {detail}"))


_ABS = object()


def _vaut(doc, cle, a):
    val = doc.get(cle, _ABS)
    if isinstance(a, dict) and any(k.startswith("$") for k in a):
        for op, arg in a.items():
            if op == "$in":
                if isinstance(val, list):
                    if not set(val) & set(arg):
                        return False
                elif val is _ABS or val not in arg:
                    return False
            if op == "$nin" and val is not _ABS and val in arg:
                return False
            if op == "$gte" and (val is _ABS or val < arg):
                return False
            if op == "$lt" and (val is _ABS or not val < arg):
                return False
            if op == "$ne" and val == arg:
                return False
            if op == "$regex":
                if val is _ABS or not re.search(arg, str(val), re.I if "i" in str(a.get("$options", "")) else 0):
                    return False
        return True
    if isinstance(val, list):
        return a in val
    return val is not _ABS and val == a


def correspond(doc, q):
    for k, a in (q or {}).items():
        if k == "$or":
            if not any(correspond(doc, x) for x in a):
                return False
        elif not _vaut(doc, k, a):
            return False
    return True


class Curseur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, cle, sens=1):
        self.docs = sorted(self.docs, key=lambda d: str(d.get(cle) or ""), reverse=sens < 0)
        return self

    async def to_list(self, n):
        return [dict(d) for d in self.docs[:n]]


class Coll:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, q=None, proj=None):
        return Curseur([d for d in self.docs if correspond(d, q)])

    async def find_one(self, q=None, proj=None):
        for d in self.docs:
            if correspond(d, q):
                return dict(d)
        return None


class Db(dict):
    def __getattr__(self, nom):
        return self.setdefault(nom, Coll())

    def __getitem__(self, nom):
        return self.setdefault(nom, Coll())


A = "coacha@exemple.test"
B = "coachb@exemple.test"
ADMIN = R.SUPER_ADMIN_EMAILS[0] if hasattr(R, "SUPER_ADMIN_EMAILS") else S.SUPER_ADMIN_EMAILS[0]
J = "2026-10-07"


def resa(i, cours, heure, coach, **x):
    d = {"id": f"r{i}", "courseId": cours, "datetime": f"{J}T{heure}:00", "quantity": 1, "coach_id": coach,
         "userName": f"Personne {i}", "userEmail": f"p{i}@exemple.test", "userWhatsapp": "+41790000000",
         "offerName": "Pulse X10", "totalPrice": 0, "createdAt": f"2026-09-2{i % 9}T10:00:00"}
    d.update(x)
    return d


RESAS = ([resa(i, "silent", "18:45", A, userWhatsapp="", **({"subscriptionId": "sub-3"} if i == 3 else {}))
          for i in range(1, 6)]                       # 5 actives
         + [resa(10, "unite", "18:45", A, offerName="Cours à l'unité", totalPrice=30)]  # même jour/heure, autre cours
         + [resa(11, "silent", "18:45", A, source="pass_duo", offerName="Pulse X10"),
            resa(12, "silent", "18:45", A, source="pass_duo", offerName="Pulse X10")]  # Pass Duo = 2 places
         + [resa(13, "silent", "18:45", A, quantity=3)]                                  # 3 places
         + [resa(14, "silent", "18:45", A, discountCode="ESSAI-1", promoCode="ESSAI-1", offerName="Essai gratuit")]
         + [resa(20, "cours-b", "18:45", B), resa(21, "silent", "18:45", B)])          # coach B
db = Db()
db["reservations"] = Coll(RESAS)
db["offers"] = Coll([{"id": "o1", "linked_course_ids": ["silent"], "max_participants": 20},
                     {"id": "o2", "linked_course_ids": ["unite"]}])
db["courses"] = Coll([{"id": "silent", "name": "Afroboost Silent — Session Cardio", "locationName": "Valangines 97"},
                      {"id": "unite", "name": "Cours à l'unité", "locationName": "Valangines 97"}])
db["discount_codes"] = Coll([{"code": "ESSAI-1", "payment_method": "free", "total_paid": 0},
                            {"code": "PAYE-1", "payment_method": "stripe", "total_paid": 150}])
db["chat_participants"] = Coll([
    {"email": "P1@exemple.test", "whatsapp": "079 123 45 67", "coach_id": A},          # contact du coach A
    {"email": "p1@exemple.test", "whatsapp": "+41 78 999 99 99", "coach_id": B},       # MÊME e-mail chez B
    {"email": "p2@exemple.test", "phone": "0041 76 555 44 33", "coach_id": B},         # seulement chez B
])
db["subscriptions"] = Coll([{"id": "sub-3", "email": "p3@exemple.test", "whatsapp": "+33 6 12 34 56 78"}])
db["subscriber_infos"] = Coll([{"email": "p4@exemple.test", "whatsapp": "(079) 222-33-44", "coach_id": A}])
db["coaches"] = Coll([{"email": A, "name": "Bassi"}])
db["notifications"] = Coll([{"type": "reservation_cancelled", "coach_id": A, "course_id": "silent",
                             "occurrence_cle": f"silent|{J}T18:45", "user_name": "Marc", "places": 1,
                             "created_at": "2026-09-29T12:00:00"}])
R.db = db
import api.routes.shared as SH  # noqa: E402
SH.db = db


def en_tant_que(email):
    async def _faux(request):
        return email
    R.mt5_coach_signe = _faux


run = asyncio.get_event_loop().run_until_complete

print("COMPTEURS")
en_tant_que(A)
c = run(R.v567_inscriptions_par_session(None, J, J))["sessions"]
v("2+5+9. session « silent » : 5 + Pass Duo (2) + 3 places + essai (1) = 11 places actives",
  c.get(f"silent|{J}T18:45", {}).get("inscrits") == 11, c)
v("6. même jour, même heure, même lieu : « Cours à l'unité » compté À PART (1)", c.get(f"unite|{J}T18:45", {}).get("inscrits") == 1, c)
v("7. capacité des offres liées (20) remontée ; sans capacité -> None",
  c[f"silent|{J}T18:45"]["capacite"] == 20 and c[f"unite|{J}T18:45"]["capacite"] is None, c)
v("12. coach A : jamais la session du coach B, ni ses réservations sur « silent »",
  f"cours-b|{J}T18:45" not in c and c[f"silent|{J}T18:45"]["inscrits"] == 11, c)
v("1. session sans réservation -> absente de la carte (0 affiché)", "vide|" not in " ".join(c))

en_tant_que(B)
cb = run(R.v567_inscriptions_par_session(None, J, J))["sessions"]
v("12bis. coach B : SES réservations seulement (cours-b 1, silent 1)",
  cb.get(f"cours-b|{J}T18:45", {}).get("inscrits") == 1 and cb.get(f"silent|{J}T18:45", {}).get("inscrits") == 1, cb)
en_tant_que(ADMIN)
ca = run(R.v567_inscriptions_par_session(None, J, J))["sessions"]
v("15. super-admin existant : vue globale conservée (silent 12)", ca.get(f"silent|{J}T18:45", {}).get("inscrits") == 12, ca)

print("DÉTAIL")
en_tant_que(A)
d = run(R.v567_detail_session(None, "silent", f"{J}T18:45"))
noms = [p["nom"] for p in d["participants"]]
v("9. liste : 9 réservations de A sur cette session, rien de B", len(d["participants"]) == 9 and "Personne 21" not in noms, noms)
v("7bis. 11 / 20 -> 9 places restantes, pas complet", (d["inscrits"], d["capacite"], d["restantes"], d["complet"]) == (11, 20, 9, False), d)
duo = [p for p in d["participants"] if p["offre"] == "Pass Duo"]
v("5. Pass Duo : deux billets (2 places), offre « Pass Duo », forfait d'origine rappelé",
  len(duo) == 2 and all(p["forfait"] == "Pulse X10" for p in duo), duo)
trois = next(p for p in d["participants"] if p["id"] == "r13")
v("places réelles : une réservation de 3 places affiche 3", trois["places"] == 3, trois)
essai = next(p for p in d["participants"] if p["id"] == "r14")
v("11. essai -> badge ESSAI + « Essai gratuit »", essai["essai"] is True and essai["paiement"] == "Essai gratuit", essai)
v("10. offre utilisée affichée (Pulse X10)", next(p for p in d["participants"] if p["id"] == "r1")["offre"] == "Pulse X10")
v("3-4. annulation : hors du compte actif, présente dans l'historique",
  d["annulations"] and d["annulations"][0]["nom"] == "Marc" and all(p["nom"] != "Marc" for p in d["participants"]), d["annulations"])
en_tant_que(B)
db_ = run(R.v567_detail_session(None, "silent", f"{J}T18:45"))
v("12ter. coach B sur la même session : ses participants seulement, aucune annulation de A",
  [p["nom"] for p in db_["participants"]] == ["Personne 21"] and db_["annulations"] == [], db_)
d0 = run(R.v567_detail_session(None, "vide", f"{J}T18:45"))
v("1bis. session sans réservation -> 0 inscrit, liste vide", d0["inscrits"] == 0 and d0["participants"] == [], d0)

print("WHATSAPP (V568)")
en_tant_que(A)
dw = {p["id"]: p for p in run(R.v567_detail_session(None, "silent", f"{J}T18:45"))["participants"]}
v("rouge 1. e-mail dans la résa, numéro dans les CONTACTS du coach -> whatsapp normalisé 41791234567",
  dw["r1"].get("whatsapp") == "41791234567", dw["r1"])
v("2. numéro du FORFAIT de la réservation (subscriptionId) -> +33 conservé : 33612345678", dw["r3"].get("whatsapp") == "33612345678", dw["r3"])
v("3. subscriber_infos du coach, parenthèses et tirets -> 41792223344", dw["r4"].get("whatsapp") == "41792223344", dw["r4"])
v("8. isolation : le numéro de p2 n'existe que chez B -> jamais rendu au coach A", not dw["r2"].get("whatsapp"), dw["r2"])
v("8bis. même e-mail chez B avec un autre numéro : A reçoit le SIEN, jamais celui de B", dw["r1"].get("whatsapp") != "41789999999")
v("réservation qui porte déjà un numéro : il reste prioritaire (Pass Duo r11 : +41790000000)",
  dw["r11"].get("whatsapp") == "41790000000", dw["r11"])
v("9. e-mail toujours rendu", dw["r1"].get("email") == "p1@exemple.test")
v("message : le nom du coach authentifié est fourni (Bassi)",
  run(R.v567_detail_session(None, "silent", f"{J}T18:45")).get("coach_nom") == "Bassi")
en_tant_que(B)
dwb = {p["id"]: p for p in run(R.v567_detail_session(None, "silent", f"{J}T18:45"))["participants"]}
v("8ter. coach B : ses participants seulement, avec SES contacts", list(dwb) == ["r21"], list(dwb))
en_tant_que(A)

print("PURES")
v("clé : UTC converti en heure de Zurich (16:45Z -> 18:45)", R.v567_cle_occurrence("c", "2026-10-07T16:45:00Z") == "c|2026-10-07T18:45")
v("capacité : offres en désaccord -> aucune (jamais inventée)",
  R.v567_capacite([{"max_participants": 20}, {"max_participants": 12}]) is None and R.v567_capacite([]) is None)
v("paiement : payé / inclus / gratuit",
  (R.v567_paiement({"totalPrice": 30}, False), R.v567_paiement({"subscriptionId": "s"}, False), R.v567_paiement({}, False))
  == ("Payé", "Inclus dans le forfait", "Gratuit"))
v("annulation : le journal porte désormais la session (course_id, occurrence_cle, places)",
  '"occurrence_cle": v567_cle_occurrence(reservation.get("courseId"), reservation.get("datetime")),'
  in open(os.path.join(RACINE, "api/routes/reservation_routes.py")).read())
v("lecture seule : aucune écriture dans les deux routes",
  not re.search(r"insert_one|update_one|delete_one|update_many",
                open(os.path.join(RACINE, "api/routes/reservation_routes.py")).read().split("V567 — SESSIONS")[1]))

print(f"{sum(OK)}/{len(OK)}")
sys.exit(0 if all(OK) else 1)

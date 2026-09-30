"""
V565 — Recharger (catalogue réel du coach) + Affiche Événement dans l'espace abonné.

Base EN MÉMOIRE (aucune donnée de production). Deux coachs : la plateforme
(offres au nom du super-admin) et un partenaire « coachb@exemple.test ».
Lancer : python tests/test_v565_recharge_affiche.py
"""
import asyncio
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
import api.server as S  # noqa: E402

OK = []


def v(nom, cond, detail=""):
    OK.append(bool(cond))
    print(("  OK     " if cond else "  KO     ") + nom + ("" if cond else f"  -> {detail}"))


# ── fausse base : égalité, $ne, $in, $exists, $or, $regex ─────────────────────
def _vaut(doc, cle, attendu):
    val = doc.get(cle, _ABS)
    if isinstance(attendu, dict) and any(k.startswith("$") for k in attendu):
        for op, arg in attendu.items():
            if op == "$ne" and not ((val is _ABS and arg is not None) or (val is not _ABS and val != arg)):
                return False
            if op == "$in" and (val is _ABS or val not in arg):
                return False
            if op == "$exists" and (val is not _ABS) != bool(arg):
                return False
            if op == "$regex":
                fl = re.I if "i" in str(attendu.get("$options", "")) else 0
                if val is _ABS or not re.search(arg, str(val), fl):
                    return False
            if op == "$gte" and (val is _ABS or val < arg):
                return False
        return True
    if attendu is None:
        return val is _ABS or val is None
    return val is not _ABS and val == attendu


_ABS = object()


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

    def aggregate(self, pipeline):
        return Curseur([])


class Db(dict):
    def __getattr__(self, nom):
        return self.setdefault(nom, Coll())

    def __getitem__(self, nom):
        return self.setdefault(nom, Coll())


ADMIN = S.SUPER_ADMIN_EMAILS[0]
COACH_B = "coachb@exemple.test"
MEMBRE = "lea.membre@exemple.test"
PULSE = {"id": "o-pulse", "name": "Pulse X10", "price": 150, "pack_sessions": 10, "duree_mois": 2, "coach_id": ADMIN, "position": 1}
UNITE = {"id": "o-unite", "name": "Cours à l'unité", "price": 30, "coach_id": ADMIN, "position": 2}
MEMBRES = {"id": "o-membres", "name": "Membres", "price": 150, "pack_sessions": 10, "coach_id": ADMIN,
           "requires_active_membership": True, "visible": False, "position": 0}
ENTREE = {"id": "o-entree", "name": "Carte membre", "price": 40, "pack_sessions": 0, "coach_id": ADMIN,
          "creates_membership": True, "position": 3}
ESSAI = {"id": "o-essai", "name": "Essai gratuit", "price": 0, "coach_id": ADMIN}
CACHEE = {"id": "o-cachee", "name": "Offre masquée", "price": 99, "coach_id": ADMIN, "visible": False}
PRIVEE = {"id": "o-privee", "name": "Offre privée", "price": 50, "coach_id": ADMIN, "link_only": True}
PRODUIT = {"id": "o-tshirt", "name": "T-shirt", "price": 25, "coach_id": ADMIN, "isProduct": True}
OFFRE_B = {"id": "o-b", "name": "Pack Coach B", "price": 120, "pack_sessions": 8, "coach_id": COACH_B}


def base(adhesion=None, restantes=0):
    db = Db()
    db["offers"] = Coll([PULSE, UNITE, MEMBRES, ENTREE, ESSAI, CACHEE, PRIVEE, PRODUIT, OFFRE_B])
    db["memberships"] = Coll([adhesion] if adhesion else [])
    db["subscriptions"] = Coll([{"email": MEMBRE, "status": "active", "remaining_sessions": restantes,
                                 "total_sessions": 10, "used_sessions": 10 - restantes, "expires_at": "2099-01-01"}])
    db["platform_settings"] = Coll([])
    db["concept"] = Coll([])
    return db


def recharge(db, offre_courante, restantes=0):
    S.db = db
    import api.routes.shared as SH
    SH.db = db
    return asyncio.get_event_loop().run_until_complete(
        S._lotr_etat_recharge(MEMBRE, offre_courante, restantes))


ADH = {"email": MEMBRE, "coach_id": None, "date_debut": "2026-01-01", "date_fin": "2099-12-31"}

print("RECHARGER")
r = recharge(base(adhesion=ADH), PULSE)
ids = [o["offer_id"] for o in r.get("offres", [])]
v("1. membre existant (adhésion active) -> « Membres » proposée, sans « Commence par l'offre d'entrée »",
  "o-membres" in ids and all("offre d'entrée" not in (o.get("message") or "") for o in r["offres"]), r)
v("2-3. offres actives du coach chargées : Pulse X10 + Cours à l'unité + Membres", {"o-pulse", "o-unite", "o-membres"} <= set(ids), ids)
pulse = next(o for o in r["offres"] if o["offer_id"] == "o-pulse")
unite = next(o for o in r["offres"] if o["offer_id"] == "o-unite")
v("4. offre actuelle rachetable -> « renouveler » (actuelle)", pulse["action"] == "renouveler" and pulse["actuelle"] is True, pulse)
v("5. autre offre -> « acheter »", unite["action"] == "acheter" and unite["actuelle"] is False, unite)
v("A3. carte : 10 séances · 2 mois · 150 CHF ; unité : 1 séance · 30 CHF",
  (pulse["seances"], pulse["duree_mois"], pulse["prix"]) == (10, 2, 150.0) and (unite["seances"], unite["prix"]) == (1, 30.0), (pulse, unite))
v("jamais : essai gratuit, offre masquée, offre privée (lien seul), produit physique",
  not {"o-essai", "o-cachee", "o-privee", "o-tshirt"} & set(ids), ids)
v("entrée (creates_membership) masquée pour un membre actif", "o-entree" not in ids, ids)
v("7. isolation : le catalogue du coach A ne contient JAMAIS l'offre du coach B", "o-b" not in ids, ids)
v("8. aucune carte morte : chaque carte a un CTA (eligible) ou un message", all(o["eligible"] or o["message"] for o in r["offres"]), r["offres"])

r2 = recharge(base(adhesion=None), PULSE)
ids2 = [o["offer_id"] for o in r2["offres"]]
v("non-membre : « Membres » MASQUÉE (pas de carte morte), l'offre d'entrée est proposée à l'achat",
  "o-membres" not in ids2 and "o-entree" in ids2 and "o-pulse" in ids2, ids2)
r3 = recharge(base(adhesion=ADH, restantes=3), PULSE, restantes=3)
m3 = [o for o in r3["offres"] if o["offer_id"] == "o-membres"]
v("séances restantes : « Membres » visible AVEC son explication (règle LOT R inchangée)",
  m3 and m3[0]["eligible"] is False and "Termine-les" in m3[0]["message"], m3)
rb = recharge(base(), OFFRE_B)
v("7bis. abonné du coach B -> offres du coach B uniquement", [o["offer_id"] for o in rb["offres"]] == ["o-b"], rb)

cat = r.get("catalogue") or []
v("V566. catalogue = les MÊMES offres que la liste, forme publique de GET /offers",
  [c.get("id") for c in cat] == ids and all("name" in c and "price" in c for c in cat), [c.get("id") for c in cat])
v("V566. catalogue : jamais l'e-mail du coach (projection r2b_offre_publique)", all("coach_id" not in c for c in cat))
v("V566. catalogue du coach B : ses offres seulement", [c.get("id") for c in rb.get("catalogue") or []] == ["o-b"])

print("PURES")
v("seances créditées : pack 10 -> 10, absent -> 1, 0 -> None (miroir du webhook)",
  (S.v565_seances_creditees(PULSE), S.v565_seances_creditees(UNITE), S.v565_seances_creditees(ENTREE)) == (10, 1, None))
v("6. CTA : checkout EXISTANT (/create-checkout-session + offerId) — aucun nouveau chemin de paiement",
  "axios.post(`${API}/create-checkout-session`, corps)" in open(os.path.join(RACINE, "frontend/src/components/SubscriberSpace.js")).read())

print("AFFICHE ÉVÉNEMENT")
C_A = {"id": "concept", "eventPosterEnabled": True, "eventPosterMediaUrl": "https://res.cloudinary.com/x/affiche.jpg",
       "eventPosterReserveLabel": "Je réserve"}
C_B = {"id": f"concept_{COACH_B}", "eventPosterEnabled": True, "eventPosterMediaUrl": "https://youtu.be/abc123"}


def affiche(concepts, source):
    db = Db()
    db["concept"] = Coll(concepts)
    S.db = db
    return asyncio.get_event_loop().run_until_complete(S.v565_affiche_evenement(source))


a = affiche([C_A, C_B], ADMIN)
v("10. activée + image -> projetée (média, libellé du coach)", a and a["media_url"].endswith("affiche.jpg") and a["reserve_label"] == "Je réserve", a)
v("12. libellé jamais renseigné -> ABSENT (défaut côté écran) ; vide -> conservé vide (bouton masqué)",
  "offers_label" not in a and S.v565_projection_affiche(dict(C_A, eventPosterOffersLabel=""))["offers_label"] == "", a)
v("9. désactivée -> None (rien dans l'espace)", affiche([dict(C_A, eventPosterEnabled=False)], ADMIN) is None)
v("B3. sans média / média non http(s) -> None",
  affiche([dict(C_A, eventPosterMediaUrl="")], ADMIN) is None and affiche([dict(C_A, eventPosterMediaUrl="javascript:alert(1)")], ADMIN) is None)
b = affiche([C_A, C_B], COACH_B)
v("15. coach B -> SON affiche (vidéo), jamais celle de A", b and "youtu.be" in b["media_url"], b)
v("15bis. coach sans concept -> rien, jamais l'affiche de la plateforme", affiche([C_A], "coachc@exemple.test") is None)
v("14. nouvel événement -> nouvelle clé (l'affiche fermée peut réapparaître)",
  S.v565_projection_affiche(C_A)["cle"] != S.v565_projection_affiche(dict(C_A, eventPosterMediaUrl="https://res.cloudinary.com/x/nouvelle.jpg"))["cle"])
v("B1. aucune écriture : la projection ne fait qu'un find_one sur concept",
  "insert" not in __import__("inspect").getsource(S.v565_affiche_evenement)
  and "update" not in __import__("inspect").getsource(S.v565_affiche_evenement))

print(f"{sum(OK)}/{len(OK)}")
sys.exit(0 if all(OK) else 1)

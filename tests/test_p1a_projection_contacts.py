# -*- coding: utf-8 -*-
"""
P1-A.1 — la projection sur `chat_participants` ne change RIEN a la reponse.

Ce test rejoue la logique EXACTE de /api/contacts/all deux fois — une fois avec
le document complet, une fois avec la projection — et exige des reponses
IDENTIQUES, champ par champ.

HORS LIGNE ET SANS BASE : les documents sont fabriques ici, avec exactement les
25 champs observes sur la collection reelle. Aucune connexion, aucune ecriture,
aucune donnee de production.

    python3 tests/test_p1a_projection_contacts.py
"""
import io
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()

resultats = []


def verifier(nom, condition, detail=""):
    resultats.append((nom, bool(condition), detail))


# ---------------------------------------------------------------------------
# La projection, lue DANS le fichier reel (pas recopiee ici)
# ---------------------------------------------------------------------------
def lire_projection():
    m = re.search(r"_P1A_CHAMPS_CONTACT = \{(.*?)\}", SERVEUR, re.S)
    if not m:
        return None
    champs = {}
    for cle, val in re.findall(r'"([^"]+)"\s*:\s*(\d)', m.group(1)):
        champs[cle] = int(val)
    return champs


PROJECTION = lire_projection()
verifier("0. la projection est bien declaree dans api/server.py", PROJECTION is not None)

CHAMPS_GARDES = {c for c, v in (PROJECTION or {}).items() if v == 1}
verifier(
    "0b. elle garde EXACTEMENT les huit champs lus par la fonction",
    CHAMPS_GARDES == {"id", "name", "email", "whatsapp", "phone", "source", "contact_type", "tags"},
    str(sorted(CHAMPS_GARDES)),
)
verifier("0c. elle exclut `_id`", (PROJECTION or {}).get("_id") == 0)


# ---------------------------------------------------------------------------
# Les 25 champs reellement observes sur chat_participants (production)
# ---------------------------------------------------------------------------
def participant(i):
    """Une fiche COMPLETE, telle qu'elle existe en base."""
    return {
        "id": "p%d" % i,
        "name": "Contact %d" % i,
        "email": "c%d@exemple.ch" % i,
        "whatsapp": "+41791234%03d" % (i % 1000),
        "phone": "+41791234%03d" % (i % 1000) if i % 3 else None,
        "source": "google" if i % 7 == 0 else "import",
        "contact_type": ["participant", "prospect", "partner", "other", None][i % 5],
        "tags": ["vip"] if i % 4 == 0 else [],
        # --- champs que la projection ecarte ---
        "photo_url": "https://exemple/photo%d.jpg" % i,
        "photoUrl": "https://exemple/photo%d.jpg" % i,
        "created_at": "2026-01-01T10:00:00+00:00",
        "coach_id": "coach@test.ch",
        "last_seen_at": "2026-08-01T10:00:00+00:00",
        "link_token": "tok%d" % i,
        "updated_at": "2026-08-02T10:00:00+00:00",
        "contact_type_set_at": "2026-08-03T10:00:00+00:00",
        "contact_type_set_by": "coach@test.ch",
        "subscriptionCode": "AFR-%06d" % i,
        "code": "AFR-%06d" % i,
        "isSubscriber": True,
        "objectifs": {"poids": 70},
        "birthday": "01-01",
        "categories": ["cat1"],
        "birthday_updated_at": "2026-01-01",
        "show_age_public": True,
    }


def projeter(doc, projection):
    """Ce que Mongo renverrait avec cette projection."""
    gardes = {c for c, v in projection.items() if v == 1}
    return {k: v for k, v in doc.items() if k in gardes}


# ---------------------------------------------------------------------------
# La construction de la fiche, transcrite de /api/contacts/all
# ---------------------------------------------------------------------------
def construire(participants):
    """Reproduit la boucle `for p in participants:` de l'endpoint."""
    contacts, seen_ids, seen_emails, seen_phones = [], set(), set(), set()
    for p in participants:
        pid = p.get("id", "")
        email = (p.get("email") or "").strip().lower()
        phone = (p.get("whatsapp") or p.get("phone") or "").strip()
        if pid and pid in seen_ids:
            continue
        if email and email in seen_emails:
            continue
        if phone and phone in seen_phones:
            continue
        if pid:
            seen_ids.add(pid)
        if email:
            seen_emails.add(email)
        if phone:
            seen_phones.add(phone)
        contacts.append({
            "id": pid,
            "name": p.get("name") or email or phone or "Sans nom",
            "type": "user",
            "category": p.get("source", "import"),
            "phone": phone or None,
            "email": email or None,
            "source": p.get("source", "import"),
            "contact_type": p.get("contact_type") or None,
            "tags": p.get("tags", []),
        })
    return contacts


COMPLETS = [participant(i) for i in range(400)]
PROJETES = [projeter(d, PROJECTION) for d in COMPLETS] if PROJECTION else []

avant = construire(COMPLETS)
apres = construire(PROJETES)

verifier("1. MEME nombre de contacts", len(avant) == len(apres), "%d vs %d" % (len(avant), len(apres)))
verifier("2. fiches STRICTEMENT identiques, champ par champ", avant == apres,
         next((("%r != %r" % (a, b)) for a, b in zip(avant, apres) if a != b), ""))

verifier("3. contact_type intact", [c["contact_type"] for c in avant] == [c["contact_type"] for c in apres])
verifier("4. email intact", [c["email"] for c in avant] == [c["email"] for c in apres])
verifier("5. phone (whatsapp puis phone) intact", [c["phone"] for c in avant] == [c["phone"] for c in apres])
verifier("6. tags intacts", [c["tags"] for c in avant] == [c["tags"] for c in apres])
verifier("7. source / category intacts",
         [(c["source"], c["category"]) for c in avant] == [(c["source"], c["category"]) for c in apres])
verifier("8. la deduplication se comporte pareil",
         len({c["id"] for c in apres}) == len(apres))

# ---------------------------------------------------------------------------
# Les quatre dimensions CONTACTS V2 doivent rester calculables
# ---------------------------------------------------------------------------
c2 = {}
# Les constantes dont dependent les fonctions extraites, lues elles aussi dans
# le fichier reel : si elles changent, ce test suit.
for cste in ("C2_INDICATIFS", "C2_ZONES", "C2_CONSENTEMENTS"):
    m = re.search(r"^%s = .*?(?=^\w|\Z)" % cste, SERVEUR, re.S | re.M)
    if m:
        exec(compile(m.group(0), "<c2>", "exec"), c2)
for nom in ("c2_pays_zone", "c2_canaux", "c2_consentement"):
    m = re.search(r"^def %s\(.*?(?=^def |\Z)" % nom, SERVEUR, re.S | re.M)
    if m:
        exec(compile(m.group(0), "<c2>", "exec"), c2)

if "c2_canaux" in c2 and "c2_pays_zone" in c2:
    def dimensions(fiches):
        """Les quatre dimensions Contacts V2, calculees comme dans l'endpoint."""
        out = []
        for f in fiches:
            pays, zone = c2["c2_pays_zone"](f.get("whatsapp") or f.get("phone") or "")
            out.append({"pays": pays, "zone": zone, "canaux": c2["c2_canaux"](f)})
        return out

    dim_avant, dim_apres = dimensions(avant), dimensions(apres)
    verifier("9. pays/zone IDENTIQUES avant et apres projection", dim_avant == dim_apres)
    verifier("10. canaux IDENTIQUES avant et apres projection",
             [d["canaux"] for d in dim_avant] == [d["canaux"] for d in dim_apres])
    verifier("11. le canal email reste detecte",
             sum(1 for d in dim_apres if d["canaux"]["email"]) == len(dim_apres))
    verifier("12. le canal telephone reste detecte (via whatsapp puis phone)",
             sum(1 for d in dim_apres if d["canaux"]["telephone"]) == len(dim_apres))
    # NOTE : `canaux.whatsapp` lit la cle `whatsapp` de la FICHE CONSTRUITE, que
    # seul l'enrichissement V300 (subscriber_infos) ajoute — jamais la lecture de
    # chat_participants. Comportement inchange par ce lot, et prouve identique
    # par les verifications 9 et 10.
    verifier("12b. zone non triviale sur au moins une fiche",
             any(d["zone"] != "inconnue" for d in dim_apres),
             str(sorted({d["zone"] for d in dim_apres})))
else:
    verifier("9-12. fonctions Contacts V2 extraites", False, "extraction impossible")

# compteurs Contacts V2
_u = [c for c in apres if c.get("type") != "group"]
compteurs = {
    "tous": len(_u),
    "participants": sum(1 for c in _u if c.get("contact_type") == "participant"),
    "prospects": sum(1 for c in _u if c.get("contact_type") == "prospect"),
    "partenaires": sum(1 for c in _u if c.get("contact_type") == "partner"),
    "autres": sum(1 for c in _u if c.get("contact_type") == "other"),
    "non_classes": sum(1 for c in _u if not c.get("contact_type")),
}
verifier("13. les compteurs Contacts V2 se calculent encore",
         compteurs["tous"] == sum(compteurs[k] for k in
                                  ("participants", "prospects", "partenaires", "autres", "non_classes")),
         str(compteurs))

# ---------------------------------------------------------------------------
# Garde-fous de perimetre
# ---------------------------------------------------------------------------
# P1-A.2 a hisse les lectures dans un `asyncio.gather` : le filtre d'isolation
# est desormais calcule dans `_filtre_participants` juste avant. L'INVARIANT
# verifie ici est le meme — un coach non-admin reste borne a ses propres fiches.
verifier("14. le FILTRE d'isolation coach_id est conserve",
         '_filtre_participants = {} if is_super_admin(caller_email) else {"coach_id": caller_email}' in SERVEUR)
verifier("14b. et il est bien celui passe a la lecture",
         "db.chat_participants.find(_filtre_participants, _P1A_CHAMPS_CONTACT)" in SERVEUR)
_FONCTION = SERVEUR.split("async def get_all_contacts_unified")[1].split("\n@api_router")[0]
verifier("15. dans /contacts/all, plus aucune lecture sans projection",
         'db.chat_participants.find({}, {"_id": 0})' not in _FONCTION)
# P1-A.2 a fusionne les deux branches (admin / coach) en un seul appel dont le
# filtre varie : il n'y a donc plus qu'une declaration et un usage.
verifier("15b. la projection est declaree puis utilisee une seule fois",
         _FONCTION.count("_P1A_CHAMPS_CONTACT") == 2,
         "declaration + 1 usage attendus, trouve %d" % _FONCTION.count("_P1A_CHAMPS_CONTACT"))
verifier("15d. les DEUX cas d'isolation restent couverts par le filtre unique",
         'is_super_admin(caller_email) else {"coach_id": caller_email}' in _FONCTION)
# Hors perimetre, mais consigne : /chat/participants lit encore le document
# entier (limite a 1000). Ce lot ne le touche PAS.
verifier("15c. /chat/participants reste inchange (hors perimetre de ce lot)",
         SERVEUR.count('db.chat_participants.find({}, {"_id": 0})') == 1)
verifier("16. l'enrichissement V300 lit toujours subscriber_infos",
         'db.subscriber_infos.find(' in SERVEUR)
verifier("17. l'enrichissement Contacts V2 est toujours appele",
         "c2_enrichir(c, _abos, _cons)" in SERVEUR)
verifier("18. maxPoolSize INCHANGE (hors perimetre de ce lot)",
         "maxPoolSize=3" in SERVEUR)
verifier("19. aucun index cree par ce lot",
         SERVEUR.count("create_index") == 7, str(SERVEUR.count("create_index")))
# Cette verification existait pour prouver que P1-A.1 n'embarquait PAS le
# gather. P1-A.2 l'implemente volontairement : l'assertion s'inverse donc, et
# c'est `test_p1a2_gather_contacts.py` qui en verifie desormais la correction.
verifier("20. le gather de P1-A.2 est en place (couvert par son propre test)",
         "await asyncio.gather(" in SERVEUR.split("get_all_contacts_unified")[1][:8000])

# ---------------------------------------------------------------------------
print("=" * 78)
echecs = 0
for nom, ok, detail in resultats:
    print(("  PASS  " if ok else "  FAIL  ") + nom + ("" if ok else "   -> " + detail[:120]))
    if not ok:
        echecs += 1
print("=" * 78)
print("Documents de production lus : 0 — tout est fabrique en memoire")
print("%d/%d verifications" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)

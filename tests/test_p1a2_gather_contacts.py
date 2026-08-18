# -*- coding: utf-8 -*-
"""
P1-A.2 — les six lectures de /api/contacts/all partent ENSEMBLE, sans rien changer.

Deux garanties a tenir :
  1. INDEPENDANCE — aucune des six lectures ne consomme le resultat d'une autre.
     Sans cela, les paralleliser serait faux.
  2. SEMANTIQUE INCHANGEE — l'ordre du TRAITEMENT (donc la deduplication) et la
     degradation gracieuse en cas d'echec restent exactement ce qu'ils etaient.

HORS LIGNE ET SANS BASE. Aucune connexion, aucune ecriture, aucune donnee.

    python3 tests/test_p1a2_gather_contacts.py
"""
import asyncio
import io
import os
import re
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVEUR = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
FONCTION = SERVEUR.split("async def get_all_contacts_unified")[1].split("\n@api_router")[0]

resultats = []


def verifier(nom, condition, detail=""):
    resultats.append((nom, bool(condition), detail))


# ---------------------------------------------------------------------------
# A. Les six lectures partent ensemble
# ---------------------------------------------------------------------------
verifier("A1. asyncio.gather est utilise", "await asyncio.gather(" in FONCTION)
verifier("A2. return_exceptions=True (degradation preservee)",
         "return_exceptions=True" in FONCTION)

BLOC = FONCTION.split("await asyncio.gather(")[-1].split("return_exceptions=True")[0] if \
    "await asyncio.gather(" in FONCTION else ""
for collection in ("chat_sessions", "chat_participants", "users",
                   "subscriber_infos", "c2_index_abonnements", "c2_index_consentements"):
    verifier("A3. %s est dans le gather" % collection, collection in BLOC)

verifier("A4. les six resultats sont recuperes nommement",
         all(v in FONCTION.split("= await asyncio.gather(")[0][-260:]
             for v in ("sessions", "participants", "all_users", "infos", "_abos", "_cons")))

# ---------------------------------------------------------------------------
# B. INDEPENDANCE : aucune lecture ne consomme le resultat d'une autre
# ---------------------------------------------------------------------------
PRODUITS = {"sessions", "participants", "all_users", "infos", "_abos", "_cons",
            "contacts", "seen_ids", "seen_emails", "seen_phones",
            "existing_ids", "info_by_email"}
noms = set(re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", BLOC))
verifier("B1. le gather ne reference AUCUNE variable produite par une lecture",
         not (noms & PRODUITS), str(sorted(noms & PRODUITS)))
verifier("B2. les seules entrees sont le filtre et la projection",
         "_filtre_participants" in BLOC and "_si_query" in BLOC and "_P1A_CHAMPS_CONTACT" in BLOC)
verifier("B3. les index Contacts V2 sont appeles SANS argument",
         "c2_index_abonnements()" in BLOC and "c2_index_consentements()" in BLOC)
verifier("B4. le filtre d'isolation derive d'une fonction PURE (aucune lecture)",
         "_filtre_participants = {} if is_super_admin(caller_email)" in FONCTION and
         "_si_query = {} if is_super_admin(caller_email)" in FONCTION)

# plus aucune lecture isolee ne subsiste dans le corps.
# `return_exceptions=True` apparait AUSSI dans le commentaire explicatif : on
# prend donc le DERNIER segment, celui qui suit reellement l'appel.
apres_gather = FONCTION.split("return_exceptions=True")[-1]
verifier("B0. le decoupage vise bien le corps APRES le gather",
         "for p in participants:" in apres_gather)
verifier("B5. plus AUCUN `await db.` apres le gather",
         "await db." not in apres_gather,
         re.findall(r"await db\.\w+", apres_gather)[:3])
verifier("B6. plus aucun await sur les index Contacts V2",
         "await c2_index_" not in apres_gather)

# ---------------------------------------------------------------------------
# C. L'ordre du TRAITEMENT est preserve (la deduplication en depend)
# ---------------------------------------------------------------------------
i_sessions = apres_gather.find("for session in sessions:")
i_parts = apres_gather.find("for p in participants:")
i_users = apres_gather.find("for u in all_users:")
verifier("C1. groupes traites en premier", 0 <= i_sessions < i_parts)
verifier("C2. participants traites AVANT users (source prioritaire)",
         0 <= i_parts < i_users, "%d < %d" % (i_parts, i_users))
verifier("C3. la deduplication reste par id, puis email, puis telephone",
         "if pid and pid in seen_ids:" in apres_gather and
         "if email and email in seen_emails:" in apres_gather and
         "if phone and phone in seen_phones:" in apres_gather)

# ---------------------------------------------------------------------------
# D. Degradation : un echec doit se comporter comme avant
# ---------------------------------------------------------------------------
verifier("D1. les 3 lectures structurantes remontent leur exception",
         "for _lecture in (sessions, participants, all_users):" in FONCTION and
         "raise _lecture" in FONCTION)
verifier("D2. un echec sur subscriber_infos prive seulement de l'enrichissement",
         "if isinstance(infos, BaseException):" in FONCTION and
         "[V300] enrichissement subscriber_infos ignoré" in FONCTION)
verifier("D3. un echec sur les index Contacts V2 prive seulement de l'enrichissement",
         "if isinstance(_abos, BaseException):" in FONCTION and
         "if isinstance(_cons, BaseException):" in FONCTION and
         "[C2] enrichissement ignore" in FONCTION)


# comportement REEL de la degradation, joue pour de vrai
async def _degradation():
    async def ok(v):
        return v

    async def casse():
        raise RuntimeError("lecture indisponible")

    res = await asyncio.gather(ok(1), ok(2), casse(), return_exceptions=True)
    return res


_res = asyncio.get_event_loop().run_until_complete(_degradation()) \
    if sys.version_info < (3, 10) else asyncio.run(_degradation())
verifier("D4. return_exceptions rend bien l'exception SANS annuler les autres",
         _res[0] == 1 and _res[1] == 2 and isinstance(_res[2], BaseException),
         str(_res))

# ---------------------------------------------------------------------------
# E. Perimetre : rien d'autre n'a bouge
# ---------------------------------------------------------------------------
verifier("E1. la projection P1-A.1 est conservee",
         '"_id": 0, "id": 1, "name": 1, "email": 1, "whatsapp": 1,' in FONCTION)
verifier("E2. le filtre d'isolation coach_id est conserve",
         '{"coach_id": caller_email}' in FONCTION)
verifier("E3. la garde JWT-strict est intacte",
         "_v311_coach_email_from_jwt(request)" in FONCTION and
         "Authentification coach requise" in FONCTION)
verifier("E4. maxPoolSize INCHANGE", "maxPoolSize=3" in SERVEUR)
verifier("E5. aucun index ajoute", SERVEUR.count("create_index") == 7,
         str(SERVEUR.count("create_index")))
verifier("E6. les compteurs Contacts V2 sont intacts",
         '"abonnes_actifs": sum(' in FONCTION and '"non_classes": sum(' in FONCTION)
verifier("E7. l'enrichissement V300 est intact",
         'c["subscriber_code"] = _info.get("code") or None' in FONCTION)
verifier("E8. c2_enrichir est toujours applique a chaque fiche",
         "c2_enrichir(c, _abos, _cons)" in FONCTION)
verifier("E9. AUCUN autre endpoint ne recoit de gather",
         SERVEUR.count("await asyncio.gather(") == 1,
         "occurrences: %d" % SERVEUR.count("await asyncio.gather("))

# ---------------------------------------------------------------------------
print("=" * 78)
echecs = 0
for nom, ok_, detail in resultats:
    print(("  PASS  " if ok_ else "  FAIL  ") + nom + ("" if ok_ else "   -> " + str(detail)[:120]))
    if not ok_:
        echecs += 1
print("=" * 78)
print("Lectures de production : 0 — analyse du source + un gather joue en memoire")
print("%d/%d verifications" % (len(resultats) - echecs, len(resultats)))
sys.exit(1 if echecs else 0)

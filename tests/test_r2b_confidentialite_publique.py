#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2b — AUCUNE ROUTE PUBLIQUE NE DIT QUI EST LE COACH.

CE BANC N'APPELLE RIEN EN PRODUCTION. Toute sortie reseau est interdite au
niveau socket, et la base est un bouchon : `GET /api/offers` INSERE trois
offres par defaut quand la collection est vide — un test qui l'appellerait pour
de vrai pourrait donc ECRIRE en production.

CE QU'IL PROUVE
==============================================================================
  * A. la liste blanche laisse passer ce qui s'affiche, et rien d'autre ;
  * B. un `coach_id` qui est une adresse e-mail ne sort JAMAIS ;
  * C. un champ prive ajoute demain n'est pas transmis — c'est une liste
       BLANCHE, pas une liste noire ;
  * D. les quatre routes publiques sont couvertes ;
  * E. un balayage RECURSIF ne trouve aucune chaine ressemblant a un e-mail ;
  * F. les champs d'affichage necessaires restent presents ;
  * G. le vendeur se resout cote serveur — le navigateur n'est plus l'autorite
       sur qui recoit l'argent ;
  * H. les routes AUTHENTIFIEES gardent l'e-mail (ce n'est une fuite pour
       personne quand le coach lit ses propres donnees).
"""
import ast
import io
import os
import re
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
RESULTATS = []


def verifier(intitule, condition, detail=""):
    detail = "" if detail == "" else str(detail)
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)


_TENTATIVES = []
_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    _TENTATIVES.append(("dns", hote))
    raise RuntimeError("sortie reseau interdite : %s" % hote)


socket.getaddrinfo = _dns

os.environ["JWT_SECRET"] = "secret-de-test-r2b"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-r2b-inexistant:27017")
import api.server as S  # noqa: E402

SRC = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
SRC_COACH = io.open(os.path.join(RACINE, "api", "routes", "coach_routes.py"), encoding="utf-8").read()
SRC_CHECKOUT = io.open(os.path.join(RACINE, "api", "routes", "checkout_routes.py"), encoding="utf-8").read()

RE_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def emails_trouves(valeur):
    """Balayage RECURSIF. Un e-mail cache dans un sous-objet reste un e-mail."""
    trouves = []
    if isinstance(valeur, dict):
        for v in valeur.values():
            trouves += emails_trouves(v)
    elif isinstance(valeur, (list, tuple)):
        for v in valeur:
            trouves += emails_trouves(v)
    elif isinstance(valeur, str):
        trouves += RE_MAIL.findall(valeur)
    return trouves


# L'offre telle qu'elle vit VRAIMENT en base (champs mesures en production).
OFFRE = {
    "id": "off-1", "name": "Cours à l'unité", "price": 30,
    "description": "Séance découverte", "thumbnail": "https://x/i.jpg",
    "images": ["https://x/i2.jpg"], "visible": True,
    "location": "Bord du Lac, Auvernier", "max_participants": 30,
    "category": "service", "isProduct": False, "linked_course_ids": ["c1"],
    "duration_value": None, "duration_unit": None, "active_price": 30,
    "active_tier": "regular", "next_date": "2026-09-10",
    # 🔴 UNE ADRESSE E-MAIL.
    "coach_id": "coach.prive@exemple.test",
}

COACH = {
    "id": "c-42", "name": "Coach Test", "photo_url": "https://x/p.jpg",
    "logo_url": None, "bio": "Bio publique", "platform_name": "TestBoost",
    "is_active": True,
    "email": "coach.prive@exemple.test",   # 🔴
}

# ============================================================================
print("\n1. L'OFFRE PUBLIQUE — CE QUI SORT, ET RIEN D'AUTRE")

pub = S.r2b_offre_publique(OFFRE)
verifier("1a. `coach_id` ABSENT de l'offre publique", "coach_id" not in pub, sorted(pub))
verifier("1b. AUCUNE adresse e-mail, balayage recursif",
         emails_trouves(pub) == [], str(emails_trouves(pub)))
for champ in ("id", "name", "price", "description", "thumbnail", "images",
              "location", "max_participants", "category", "isProduct",
              "linked_course_ids", "active_price", "next_date"):
    verifier("1c. l'affichage garde `%s`" % champ, champ in pub)
verifier("1d. rien hors de la liste blanche",
         set(pub) <= set(S.R2B_CLES_OFFRE_PUBLIQUE))

print("\n2. LISTE BLANCHE — UN CHAMP AJOUTE DEMAIN NE PASSE PAS")
demain = dict(OFFRE, owner_email="autre@exemple.test", phone="+41 79 000 00 00",
              stripe_account="acct_123", internal_notes="ne jamais publier",
              coach_email="encore@exemple.test")
pub2 = S.r2b_offre_publique(demain)
for secret in ("owner_email", "phone", "stripe_account", "internal_notes", "coach_email"):
    verifier("2a. « %s » non transmis" % secret, secret not in pub2)
verifier("2b. et aucun e-mail n'a fui par un autre chemin",
         emails_trouves(pub2) == [], str(emails_trouves(pub2)))
verifier("2c. c'est bien une RECOPIE selective, pas une suppression",
         "for c in R2B_CLES_OFFRE_PUBLIQUE if c in d" in SRC)

print("\n3. LE COACH PUBLIC")
cpub = S.r2b_coach_public(COACH)
verifier("3a. `email` ABSENT", "email" not in cpub, sorted(cpub))
verifier("3b. aucun e-mail, balayage recursif", emails_trouves(cpub) == [])
for champ in ("id", "name", "photo_url", "bio", "platform_name"):
    verifier("3c. la vitrine garde `%s`" % champ, champ in cpub)
verifier("3d. `id` reste — identifiant opaque, deja public",
         cpub.get("id") == "c-42")
cpub2 = S.r2b_coach_public(dict(COACH, stripe_connect_id="acct_x",
                                whatsapp="+41 79 111 11 11", password_hash="x"))
for secret in ("stripe_connect_id", "whatsapp", "password_hash"):
    verifier("3e. « %s » non transmis" % secret, secret not in cpub2)

print("\n4. LES QUATRE ROUTES PUBLIQUES SONT COUVERTES")
verifier("4a. /offers — branche publique filtree",
         "return [r2b_offre_publique(o) for o in _publiques]" in SRC)
verifier("4b. /offers — la branche d'amorcage aussi",
         "for o in _enrich_offers_with_active_price(default_offers)" in SRC)
verifier("4c. /coaches/public/{id} — l'e-mail a quitte la PROJECTION",
         '"id": 1, "name": 1, "photo_url": 1, "bio": 1}' in SRC_COACH)
verifier("4d. /partners/active — sortie filtree",
         "return [r2b_coach_public(p) for p in partners_with_videos]" in SRC_COACH)
verifier("4e. /coach/vitrine — coach ET offres filtres",
         "_coach_public = r2b_coach_public(coach)" in SRC_COACH
         and "[r2b_offre_publique(o) for o in offers]" in SRC_COACH)
verifier("4f. la vitrine rend `username` a la place de l'e-mail",
         '_coach_public["username"] = username' in SRC_COACH)

print("\n5. LA REGRESSION SILENCIEUSE QUI GUETTAIT LES COMMENTAIRES")
verifier("5a. /comments traduit un `username` en e-mail, cote serveur",
         'if coach_id and "@" not in coach_id:' in SRC)
verifier("5b. et la vitrine envoie desormais ce `username`",
         "res.data.coach.username || username" in io.open(
             os.path.join(RACINE, "frontend", "src", "components", "CoachVitrine.js"),
             encoding="utf-8").read())

print("\n6. LE VENDEUR SE LIT DANS LE CATALOGUE, PAS DANS LA REQUETE")
verifier("6a. la resolution existe", "_r2b_resoudre_vendeur" in SRC_CHECKOUT)
verifier("6b. elle est posee sur les DEUX portes de paiement",
         SRC_CHECKOUT.count("await _r2b_vendeur_si_absent(req)") == 2,
         str(SRC_CHECKOUT.count("await _r2b_vendeur_si_absent(req)")))
verifier("6c. elle ne s'applique QUE si le client n'a rien declare",
         'if str(getattr(req, "coach_email", "") or "").strip():\n        return' in SRC_CHECKOUT)
verifier("6d. la garde du vendeur est CONSERVEE, intacte",
         SRC_CHECKOUT.count("await _lot2_verifier_vendeur(req.items, req.coach_email)") == 2)
_modeles = [n for n in ast.walk(ast.parse(SRC_CHECKOUT))
            if isinstance(n, ast.ClassDef)
            and n.name in ("CreateCheckoutRequest", "FreeCheckoutRequest")]
_facultatif = [c.name for c in _modeles if any(
    isinstance(a, ast.AnnAssign) and getattr(a.target, "id", "") == "coach_email"
    and isinstance(a.value, ast.Constant) and a.value.value == "" for a in c.body)]
verifier("6e. `coach_email` devient facultatif sur les DEUX modeles de requete",
         sorted(_facultatif) == ["CreateCheckoutRequest", "FreeCheckoutRequest"],
         str(_facultatif))
verifier("6f. le navigateur ne l'envoie plus",
         "coach_email: selectedOffer.coach_id" not in io.open(
             os.path.join(RACINE, "frontend", "src", "App.js"), encoding="utf-8").read())

print("\n7. LES ROUTES AUTHENTIFIEES NE SONT PAS TOUCHEES")
_arbre = ast.parse(SRC)
_fn = next((n for n in ast.walk(_arbre)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_offers"), None)
_corps = ast.get_source_segment(SRC, _fn) if _fn else ""
verifier("7a. `scope=mine` rend toujours les offres SANS filtre public",
         "return await _enrich_offers_with_next_date(_enrich_offers_with_active_price(scoped))" in _corps)
verifier("7b. un coach lisant SES offres voit donc son propre e-mail",
         "r2b_offre_publique" not in _corps.split("if scope == \"mine\":")[1].split("offers = await")[0])
verifier("7c. aucune route authentifiee n'est modifiee par ce lot",
         "_v309_require_coach_or_admin" not in
         SRC[SRC.index("def r2b_offre_publique"):SRC.index("@api_router.get(\"/offers\"")])

print("\n8. AUCUNE MIGRATION, AUCUN CHAMP NOUVEAU, AUCUNE FINANCE")
_bloc_brut = SRC[SRC.index("# R2b — UNE ROUTE PUBLIQUE"):SRC.index('@api_router.get("/offers"')]
# Un commentaire qui NOMME `stripe_account` pour expliquer le danger n'est pas
# du code qui touche a Stripe. On ne juge donc que le code execute.
_bloc = "\n".join(re.sub(r"#.*$", "", l) for l in _bloc_brut.splitlines())
_bloc = re.sub(r'"""[\s\S]*?"""', "", _bloc)
for interdit in ("update_one", "update_many", "insert_one", "insert_many",
                 "delete_one", "owner_type", "offer_type", "subscription",
                 "boost", "stripe", "price ="):
    verifier("8a. le socle R2b ne fait pas « %s »" % interdit, interdit not in _bloc)
verifier("8b. AUCUNE sortie reseau pendant le banc", not _TENTATIVES, str(_TENTATIVES[:3]))

_ok = sum(1 for _i, _c, _d in RESULTATS if _c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("R2b : %d / %d verifications" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s%s" % (_i, (" -> " + _d) if _d else ""))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)

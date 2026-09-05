#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R2c — DE QUI EST CETTE OFFRE, ET QU'EST-CE QUE C'EST ?

CE BANC N'APPELLE NI LA PRODUCTION NI AUCUN RESEAU. Il monte une base en
MEMOIRE et appelle les VRAIES fonctions de route : ce ne sont donc pas des
`grep` sur du texte, mais le comportement reel qui est mesure.

CE QU'IL PROUVE
==============================================================================
PROPRIETAIRE
  A. l'administrateur cree     -> owner_type = admin
  B. le partenaire cree        -> owner_type = partner + son UUID reel
  C. le partenaire REVENDIQUE  -> ignore, il reste partner
  D. le visiteur anonyme       -> ne cree ni ne modifie rien
  E. l'offre historique        -> reste unknown, aucune attribution inventee
  F. l'administrateur classe   -> la reponse humaine est enregistree
  G. le partenaire vole        -> 403, l'offre d'un autre lui resiste
TYPE
  les huit valeurs, la validation stricte a la creation, la tolerance a la
  mise a jour, et le refus d'une valeur inventee.
CONFIDENTIALITE
  aucun e-mail ne revient par la porte de derriere : `owner_id` est un UUID.
"""
import asyncio
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


_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    raise RuntimeError("sortie reseau interdite : %s" % hote)


socket.getaddrinfo = _dns

os.environ["JWT_SECRET"] = "secret-de-test-r2c"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-r2c-inexistant:27017")
import api.server as S  # noqa: E402
from fastapi import HTTPException  # noqa: E402

ADMIN = S.SUPER_ADMIN_EMAILS[0]
PARTENAIRE = "partenaire.un@exemple.test"
AUTRE = "partenaire.deux@exemple.test"
UUID_UN = "11111111-2222-3333-4444-555555555555"
UUID_DEUX = "99999999-8888-7777-6666-555555555555"


# --------------------------------------------------------------------------
# UNE BASE EN MEMOIRE. Juste assez de MongoDB pour les routes testees.
# --------------------------------------------------------------------------
def _correspond(doc, requete):
    for cle, attendu in (requete or {}).items():
        if cle == "$or":
            if not any(_correspond(doc, sous) for sous in attendu):
                return False
            continue
        valeur = doc.get(cle)
        if isinstance(attendu, dict):
            for op, arg in attendu.items():
                if op == "$in" and valeur not in arg:
                    return False
                if op == "$exists" and (cle in doc) != bool(arg):
                    return False
                if op == "$ne" and valeur == arg:
                    return False
        elif valeur != attendu:
            return False
    return True


def _projeter(doc, proj):
    if not proj:
        return dict(doc)
    gardees = [k for k, v in proj.items() if v and k != "_id"]
    if not gardees:
        return {k: v for k, v in doc.items() if k != "_id"}
    return {k: doc[k] for k in gardees if k in doc}


class _Curseur:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, n=None):
        return list(self._docs)[:n] if n else list(self._docs)

    def sort(self, *a, **k):
        return self


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def find(self, requete=None, proj=None):
        return _Curseur([_projeter(d, proj) for d in self.docs
                         if _correspond(d, requete)])

    async def find_one(self, requete=None, proj=None):
        for d in self.docs:
            if _correspond(d, requete):
                return _projeter(d, proj)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": doc.get("id")})()

    async def insert_many(self, docs):
        self.docs += [dict(d) for d in docs]

    async def update_one(self, requete, maj):
        for d in self.docs:
            if _correspond(d, requete):
                d.update(maj.get("$set", {}))
                return type("R", (), {"modified_count": 1})()
        return type("R", (), {"modified_count": 0})()

    async def update_many(self, requete, maj):
        return type("R", (), {"modified_count": 0})()

    async def delete_one(self, requete):
        return type("R", (), {"deleted_count": 0})()


class _Base:
    def __init__(self):
        self.offers = _Collection()
        self.courses = _Collection()
        self.coaches = _Collection([
            {"id": UUID_UN, "email": PARTENAIRE, "name": "Partenaire Un", "is_active": True},
            {"id": UUID_DEUX, "email": AUTRE, "name": "Partenaire Deux", "is_active": True},
        ])
        self.discount_codes = _Collection()

    def __getitem__(self, nom):
        return getattr(self, nom)


class _Requete:
    """Le strict minimum d'un `fastapi.Request` pour ces routes."""
    def __init__(self, email=None):
        self.headers = {} if email is None else {"X-User-Email": email}
        self.headers = _Entetes(self.headers)


class _Entetes(dict):
    def get(self, cle, defaut=""):
        for k, v in self.items():
            if k.lower() == str(cle).lower():
                return v
        return defaut


BASE = _Base()
S.db = BASE


def _offre(**kw):
    corps = {"name": "Offre", "price": 30.0, "offer_type": "single_class"}
    corps.update(kw)
    return S.OfferCreate(**corps)


async def _creer(email, **kw):
    return await S.create_offer(_offre(**kw), _Requete(email))


def _attrape(coro):
    """Execute et renvoie (resultat, code_http_ou_None)."""
    try:
        return asyncio.run(coro), None
    except HTTPException as e:
        return None, e.status_code


# ==========================================================================
print("\nPROPRIETAIRE — QUI A CREE CETTE OFFRE")

o_admin, _ = _attrape(_creer(ADMIN, name="Cours du samedi"))
verifier("A. l'administrateur cree -> owner_type = admin",
         o_admin and o_admin.owner_type == "admin", o_admin and o_admin.owner_type)
verifier("A-bis. l'administrateur n'a pas d'identifiant partenaire",
         o_admin and o_admin.owner_id is None, o_admin and o_admin.owner_id)

o_part, _ = _attrape(_creer(PARTENAIRE, name="Cours du partenaire"))
verifier("B. le partenaire cree -> owner_type = partner",
         o_part and o_part.owner_type == "partner", o_part and o_part.owner_type)
verifier("B-bis. owner_id = l'UUID REEL de sa fiche",
         o_part and o_part.owner_id == UUID_UN, o_part and o_part.owner_id)

# C. LA REVENDICATION. Le corps de la requete ment sur deux plans a la fois.
o_menteur, _ = _attrape(_creer(PARTENAIRE, name="Je suis admin", coach_id=ADMIN))
verifier("C. le partenaire qui envoie coach_id=admin reste PARTNER",
         o_menteur and o_menteur.owner_type == "partner",
         o_menteur and o_menteur.owner_type)
verifier("C-bis. et l'offre lui reste attribuee, pas a l'administrateur",
         o_menteur and o_menteur.coach_id == PARTENAIRE,
         o_menteur and o_menteur.coach_id)
verifier("C-ter. `owner_type` n'existe MEME PAS dans le modele d'entree",
         "owner_type" not in S.OfferCreate.model_fields,
         sorted(S.OfferCreate.model_fields)[:5])
verifier("C-quater. ni `owner_id`", "owner_id" not in S.OfferCreate.model_fields)

# D. L'ANONYME.
_r, _code = _attrape(_creer(None, name="Offre pirate"))
verifier("D. le visiteur anonyme ne peut pas CREER (401)", _code == 401, _code)
_r, _code = _attrape(S.update_offer(o_part.id, _offre(name="Detourne"), _Requete(None)))
verifier("D-bis. ni MODIFIER (401)", _code == 401, _code)

# E. L'OFFRE HISTORIQUE. Telle qu'elle vit en production : aucun des 3 champs.
BASE.offers.docs.append({"id": "legacy-1", "name": "PULSE x10 cours", "price": 250.0,
                         "coach_id": None, "visible": False, "pack_sessions": 10})
_lue = asyncio.run(BASE.offers.find_one({"id": "legacy-1"}))
verifier("E. une offre historique n'a AUCUN des trois champs",
         not any(c in _lue for c in ("owner_type", "owner_id", "offer_type")))
verifier("E-bis. relue par le modele, elle est `unknown` — pas « admin »",
         S.Offer(**_lue).owner_type == "unknown", S.Offer(**_lue).owner_type)
verifier("E-ter. et son type est `unknown` — pas « pack » devine de `pack_sessions`",
         S.Offer(**_lue).offer_type == "unknown", S.Offer(**_lue).offer_type)

# G. LE VOL. Le partenaire DEUX s'attaque a l'offre du partenaire UN.
_r, _code = _attrape(S.update_offer(o_part.id, _offre(name="Volee"), _Requete(AUTRE)))
verifier("G. un partenaire ne modifie pas l'offre d'un autre (403)", _code == 403, _code)
_r, _code = _attrape(S.update_offer(o_part.id, _offre(name="Renommee"), _Requete(PARTENAIRE)))
verifier("G-bis. mais il modifie TOUJOURS la sienne", _code is None, _code)
_apres = asyncio.run(BASE.offers.find_one({"id": o_part.id}))
verifier("G-ter. et sa sauvegarde n'a pas change son proprietaire",
         _apres.get("owner_id") == UUID_UN and _apres.get("coach_id") == PARTENAIRE,
         (_apres.get("owner_id"), _apres.get("coach_id")))

# Le super-admin garde la main sur tout — regle V310c : on PROUVE le chemin
# legitime avant de se feliciter du durcissement.
_r, _code = _attrape(S.update_offer(o_part.id, _offre(name="Corrigee par admin"), _Requete(ADMIN)))
verifier("G-quater. l'administrateur modifie n'importe quelle offre",
         _code is None, _code)
_apres = asyncio.run(BASE.offers.find_one({"id": o_part.id}))
verifier("G-quinquies. ... SANS se l'attribuer au passage",
         _apres.get("owner_id") == UUID_UN and _apres.get("owner_type") == "partner",
         (_apres.get("owner_type"), _apres.get("owner_id")))

# ==========================================================================
print("\nTYPE — CE QUE L'OFFRE EST")

for valeur in ("single_class", "event", "subscription", "pack",
               "membership", "product", "other"):
    _o, _c = _attrape(_creer(ADMIN, name="X", offer_type=valeur))
    verifier("le type « %s » est accepte et conserve" % valeur,
             _o and _o.offer_type == valeur, _c or (_o and _o.offer_type))

_o, _c = _attrape(_creer(ADMIN, name="X", offer_type="abonnement_annuel"))
verifier("un type invente est REFUSE a la creation (400)", _c == 400, _c)
_o, _c = _attrape(_creer(ADMIN, name="X", offer_type="unknown"))
verifier("`unknown` est REFUSE a la creation (400)", _c == 400, _c)
_o, _c = _attrape(S.create_offer(
    S.OfferCreate(name="Sans type", price=30.0), _Requete(ADMIN)))
verifier("... et l'absence totale de type aussi : le defaut est `unknown` (400)",
         _c == 400, _c)

_r, _c = _attrape(S.update_offer("legacy-1", _offre(name="PULSE x10 cours",
                                                   offer_type="unknown"), _Requete(ADMIN)))
verifier("`unknown` est TOLERE a la mise a jour — sinon les 9 offres seraient "
         "immodifiables", _c is None, _c)
_r, _c = _attrape(S.update_offer("legacy-1", _offre(name="X", offer_type="carte"),
                                 _Requete(ADMIN)))
verifier("mais un type invente reste refuse a la mise a jour (400)", _c == 400, _c)

# ==========================================================================
print("\nAUCUNE HEURISTIQUE — LE TYPE NE SE DEVINE NULLE PART")

_src = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
_bloc = _src[_src.index("# R2c — DE QUI EST CETTE OFFRE"):
             _src.index("class Offer(BaseModel):")]
_code_seul = "\n".join(re.sub(r"#.*$", "", l) for l in _bloc.splitlines())
_code_seul = re.sub(r'"""[\s\S]*?"""', "", _code_seul)
# L'invariant n'est PAS « ce mot n'apparait nulle part » — « abonnement »
# figure legitimement dans le message d'erreur que lit Bassi. C'est « ce champ
# n'est jamais LU » : on cherche donc les formes d'acces reelles.
for indice in ("name", "price", "duration_value", "duration_unit",
               "linked_course_ids", "pack_sessions", "category", "description"):
    _acces = ['get("%s"' % indice, "get('%s'" % indice,
              '["%s"]' % indice, "['%s']" % indice, "." + indice]
    verifier("le socle R2c ne LIT jamais le champ « %s »" % indice,
             not any(a in _code_seul for a in _acces),
             [a for a in _acces if a in _code_seul])

# La preuve par le contre-exemple : deux offres que TOUTE heuristique
# classerait, et que le serveur laisse a `unknown` faute de declaration.
for nom, extra in (("Abonnement 1 mois", {"duration_value": 1, "duration_unit": "months"}),
                   ("Carte 10 cours", {"pack_sessions": 10})):
    _d = dict({"id": "h-" + nom[:3], "name": nom, "price": 109.0}, **extra)
    verifier("« %s » reste `unknown` malgre son nom et ses champs" % nom,
             S.Offer(**_d).offer_type == "unknown")

# ==========================================================================
print("\nCLASSIFICATION DES OFFRES HISTORIQUES")

_r, _c = _attrape(S.r2c_lister_a_classifier(_Requete(PARTENAIRE)))
verifier("un partenaire ne voit PAS l'ecran de classification (403)", _c == 403, _c)
_r, _c = _attrape(S.r2c_lister_a_classifier(_Requete(None)))
verifier("un anonyme non plus (401)", _c == 401, _c)
_liste, _c = _attrape(S.r2c_lister_a_classifier(_Requete(ADMIN)))
verifier("F. l'administrateur, lui, obtient la liste", _liste is not None, _c)
verifier("F-bis. l'offre historique y est marquee a classifier",
         any(l["id"] == "legacy-1" and l["a_classifier"] for l in _liste["offres"]))
verifier("F-ter. la liste porte les libelles FRANCAIS, pas du jargon",
         {"Cours à l'unité", "Événement", "Carte membre"}
         <= {t["libelle"] for t in _liste["types"]},
         [t["libelle"] for t in _liste["types"]])
verifier("F-quater. `unknown` n'est PAS proposable comme choix",
         "unknown" not in {t["valeur"] for t in _liste["types"]})

_avant = dict(asyncio.run(BASE.offers.find_one({"id": "legacy-1"})))
_res, _c = _attrape(S.r2c_classifier(
    "legacy-1", S.R2CClassification(owner_type="partner", partner_id=UUID_UN,
                                    offer_type="pack"), _Requete(ADMIN)))
verifier("F-5. l'administrateur classe l'offre historique", _c is None, _c)
_apres = asyncio.run(BASE.offers.find_one({"id": "legacy-1"}))
verifier("F-6. le proprietaire declare est enregistre",
         _apres.get("owner_type") == "partner" and _apres.get("owner_id") == UUID_UN)
verifier("F-7. le type declare aussi", _apres.get("offer_type") == "pack")
verifier("F-8. `coach_id` est relu depuis la FICHE, jamais saisi",
         _apres.get("coach_id") == PARTENAIRE, _apres.get("coach_id"))
verifier("F-9. RIEN D'AUTRE n'a bouge (prix, visibilite, seances, nom)",
         all(_apres.get(k) == _avant.get(k)
             for k in ("name", "price", "visible", "pack_sessions")),
         {k: (_avant.get(k), _apres.get(k))
          for k in ("name", "price", "visible", "pack_sessions")})

_r, _c = _attrape(S.r2c_classifier("legacy-1", S.R2CClassification(
    owner_type="partner", partner_id="inexistant-9999", offer_type="pack"), _Requete(ADMIN)))
verifier("on ne classe pas une offre chez un partenaire INEXISTANT (404)", _c == 404, _c)
_r, _c = _attrape(S.r2c_classifier("legacy-1", S.R2CClassification(
    owner_type="partner", partner_id=PARTENAIRE, offer_type="pack"), _Requete(ADMIN)))
verifier("... ni en le designant par son ADRESSE E-MAIL (400)", _c == 400, _c)
_r, _c = _attrape(S.r2c_classifier("legacy-1", S.R2CClassification(
    owner_type="admin", offer_type="autre_chose"), _Requete(ADMIN)))
verifier("... ni avec un type invente (400)", _c == 400, _c)
_r, _c = _attrape(S.r2c_classifier("legacy-1", S.R2CClassification(
    owner_type="partner", offer_type="pack"), _Requete(ADMIN)))
verifier("... ni « partenaire » sans dire LEQUEL (400)", _c == 400, _c)
_r, _c = _attrape(S.r2c_classifier("inconnue-xyz", S.R2CClassification(
    owner_type="admin", offer_type="event"), _Requete(ADMIN)))
verifier("... ni une offre qui n'existe pas (404)", _c == 404, _c)
_r, _c = _attrape(S.r2c_classifier("legacy-1", S.R2CClassification(
    owner_type="admin", offer_type="event"), _Requete(PARTENAIRE)))
verifier("un partenaire ne classe RIEN (403)", _c == 403, _c)

# ==========================================================================
print("\nADMINISTRATEUR CREANT POUR UN PARTENAIRE (capacite preexistante)")

_o, _c = _attrape(_creer(ADMIN, name="Pour le partenaire", coach_id=PARTENAIRE))
verifier("l'administrateur PEUT creer au nom d'un partenaire REEL", _c is None, _c)
verifier("... et l'offre porte le bon proprietaire",
         _o and _o.owner_type == "partner" and _o.owner_id == UUID_UN,
         _o and (_o.owner_type, _o.owner_id))
_o, _c = _attrape(_creer(ADMIN, name="Pour un fantome", coach_id="fantome@exemple.test"))
verifier("... mais JAMAIS au nom d'un compte sans fiche partenaire (400)", _c == 400, _c)

# ==========================================================================
print("\nCONFIDENTIALITE — R2b N'EST PAS ROUVERT")

_toutes = asyncio.run(BASE.offers.find({}, {"_id": 0}).to_list(500))
_mail = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _emails(v):
    if isinstance(v, dict):
        return [e for x in v.values() for e in _emails(x)]
    if isinstance(v, (list, tuple)):
        return [e for x in v for e in _emails(x)]
    return _mail.findall(v) if isinstance(v, str) else []


_publiques = [S.r2b_offre_publique(o) for o in _toutes]
verifier("aucune offre publique ne contient d'adresse e-mail (%d offres)" % len(_publiques),
         _emails(_publiques) == [], _emails(_publiques)[:2] and "trouve")
verifier("aucun `owner_id` n'est une adresse e-mail",
         all("@" not in str(o.get("owner_id") or "") for o in _publiques))
verifier("`coach_id` reste hors de la liste blanche",
         "coach_id" not in S.R2B_CLES_OFFRE_PUBLIQUE)
verifier("mais il vit TOUJOURS en base — aucune donnee perdue",
         any(o.get("coach_id") for o in _toutes))
verifier("les trois champs R2c, eux, sont bien publics",
         {"owner_type", "owner_id", "offer_type"} <= set(S.R2B_CLES_OFFRE_PUBLIQUE))

# ==========================================================================
print("\nAUCUN DEBORDEMENT DE LOT")

_bloc_total = _src[_src.index("# R2c — DE QUI EST CETTE OFFRE"):
                   _src.index("class Offer(BaseModel):")]
_r2c_routes = _src[_src.index("# R2c — CLASSIFIER LES OFFRES HISTORIQUES"):
                   _src.index("# --- Product Categories ---")]
_tout_r2c = _bloc_total + _r2c_routes
_tout_r2c = "\n".join(re.sub(r"#.*$", "", l) for l in _tout_r2c.splitlines())
_tout_r2c = re.sub(r'"""[\s\S]*?"""', "", _tout_r2c)
# « Afroboost » contient « boost » : sans la frontiere de mot, ce garde
# accuserait le libelle « Afroboost / Administrateur ». Meme piege qu'en R2.
_minuscule = _tout_r2c.lower().replace("afroboost", "")
for hors_sujet in ("city", "ville", "latitude", "longitude", "address",
                   "boost", "stripe", "wallet", "commission", "reservation",
                   "discovery", "ou_pratiquer", "credit"):
    verifier("R2c ne touche pas a « %s »" % hors_sujet,
             not re.search(r"\b%s" % hors_sujet, _minuscule),
             hors_sujet)

_ok = sum(1 for _i, _c, _d in RESULTATS if _c)
_total = len(RESULTATS)
print("\n" + "=" * 78)
print("R2c : %d / %d verifications" % (_ok, _total))
if _ok != _total:
    print("\nECHECS :")
    for _i, _c, _d in RESULTATS:
        if not _c:
            print("  - %s%s" % (_i, (" -> " + _d) if _d else ""))
print("=" * 78)
sys.exit(0 if _ok == _total else 1)

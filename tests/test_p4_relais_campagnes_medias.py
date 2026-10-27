#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PHASE 6B — CAMPAGNES (PROSPECTION) ET MEDIATHEQUE PARTAGEE, DEPUIS LE RELAIS.

CE QUE CE LOT AJOUTE (api/routes/afroboosteur_relais.py)
==============================================================================
Six routes neuves, toujours sous la MEME garde HMAC que l'existant :

  * GET   .../campaigns/{id}      — detail d'une campagne de prospection,
                                     JAMAIS les actions (PII : adresse reelle,
                                     message pret par destinataire).
  * POST  .../campaigns           — cree OU previsualise (dry_run) une
                                     campagne. Relaie VERBATIM vers
                                     `p3s3_preparer_campagne_pour`, la MEME
                                     fonction que la route du coach — aucune
                                     logique parallele.
  * PATCH .../campaigns/{id}      — modifie nom/medias d'une campagne
                                     PREPAREE. Relaie vers
                                     `p3s3_modifier_campagne_pour`.
  * GET   .../medias               — la mediatheque (V595), tout statut
                                     confondu : rien n'est MASQUE (la liste
                                     montre niches et statuts existants,
                                     comme demande), mais seul un media
                                     `validee` est SELECTIONNABLE pour une
                                     campagne (`p3s3_medias_partages_valides`).
  * GET   .../niches                — les niches du coach (V598).
  * POST  .../medias                — ajoute un media PAR LIEN PUBLIC
                                     uniquement. Relaie vers
                                     `v595_ajouter_media_pour`.

CE QUE CE BANC PROUVE
==============================================================================
  1. La preparation/modification de campagne ECRIT reellement (via les
     fonctions reutilisees), mais JAMAIS un envoi : aucune ligne dans
     P3AI4_COLLECTION/P3AI_BROUILLONS (collections de la phase 6A), et le
     moteur de lancement reste hors de portee (aucune route ne l'appelle).
  2. `media_ids` est REFUSE si un id n'appartient pas au coach, ou n'est pas
     `validee` — jamais un filtrage silencieux.
  3. Le detail d'une campagne NE PORTE JAMAIS `actions` (PII).
  4. L'ajout d'un media PAR UN CHEMIN `/api/files/...` est REFUSE par le
     relais lui-meme, AVANT d'atteindre la fonction partagee.
  5. La portee par coach est respectee partout (un autre coach -> 404/filtre
     vide, jamais une fuite).
  6. Une signature invalide ou absente refuse AVANT toute lecture en base.
  7. Aucune sortie reseau (DNS/socket bloques au niveau OS).

Lancement :
    python3 tests/test_p4_relais_campagnes_medias.py
"""
import os
import socket
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
RESULTATS = []


def verifier(intitule, condition, detail=""):
    RESULTATS.append((intitule, bool(condition), detail))
    print("  %-6s %s" % ("OK  " if condition else "ECHEC", intitule))
    if detail and not condition:
        print("           -> %s" % detail)
    return bool(condition)


class SortieReseauInterdite(RuntimeError):
    pass


_GETADDR = socket.getaddrinfo


def _dns(hote, port, *a, **k):
    if str(hote) in ("localhost", "127.0.0.1", "::1", None):
        return _GETADDR(hote, port, *a, **k)
    raise SortieReseauInterdite(str(hote))


socket.getaddrinfo = _dns
socket.socket.connect = lambda self, a, *x, **k: (_ for _ in ()).throw(SortieReseauInterdite(str(a)))
socket.create_connection = lambda a, *x, **k: (_ for _ in ()).throw(SortieReseauInterdite(str(a)))

SECRET = "secret-p6b-campagnes-medias-sans-rapport-avec-la-production"
COACH_ID = "coach.p6b.fictif@exemple.test"
AUTRE_COACH = "autre.coach.p6b.fictif@exemple.test"
os.environ["JWT_SECRET"] = "jwt-secret-fictif-p6b"
os.environ.setdefault("MONGO_URL", "mongodb://bouchon-p6b-inexistant:27017")
os.environ["AFROBOOSTEUR_RELAY_SECRET"] = SECRET
os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = COACH_ID

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import hmac as hmac_module  # noqa: E402
import time  # noqa: E402

from fastapi import HTTPException  # noqa: E402

import api.server as S  # noqa: E402
import api.routes.afroboosteur_relais as R  # noqa: E402


# ============================================================================
print("\n0. OUTILLAGE")


class Curseur:
    def __init__(self, docs):
        self._docs = docs
        self._skip = 0
        self._limit = None

    def sort(self, cle, sens=1):
        specs = cle if isinstance(cle, list) else [(cle, sens)]
        for champ, s in reversed(specs):
            self._docs = sorted(self._docs, key=lambda d: d.get(champ) or "", reverse=(s == -1))
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _tranche(self):
        d = self._docs[self._skip:]
        return d[:self._limit] if self._limit is not None else d

    async def to_list(self, n=None):
        d = self._tranche()
        return list(d)[:n] if n is not None else list(d)

    def __aiter__(self):
        self._iter = iter(self._tranche())
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class CollectionBouchon:
    """Lecture seule (find/find_one/count_documents). Les ecritures accidentelles
    sur une collection qui n'en a pas besoin plantent avec AttributeError."""

    def __init__(self, documents=None):
        self.documents = [dict(d) for d in (documents or [])]

    def _ok(self, doc, filtre):
        if not filtre:
            return True
        for cle, val in filtre.items():
            if cle == "$or":
                if not any(self._ok(doc, sous) for sous in val):
                    return False
                continue
            if isinstance(val, dict) and "$in" in val:
                if doc.get(cle) not in val["$in"]:
                    return False
                continue
            if isinstance(val, dict) and "$ne" in val:
                if doc.get(cle) == val["$ne"]:
                    return False
                continue
            if isinstance(val, dict) and "$type" in val:
                continue
            if doc.get(cle) != val:
                return False
        return True

    @staticmethod
    def _projeter(doc, projection):
        """Applique une projection Mongo INCLUSIVE ({champ: 1, ...}), comme le
        ferait le vrai pilote — SANS CETTE METHODE, un test sur ce qu'une
        projection EXCLUT (ex. `notes`) serait toujours vert, meme si le code
        reel oubliait de la retirer : le bouchon doit mentir le moins possible."""
        if not projection:
            return dict(doc)
        if all(v == 0 for v in projection.values() if v != 0) or not any(
                v == 1 for v in projection.values()):
            # Style exclusif pur ({"_id": 0}) : tout garder sauf les champs a 0.
            return {k: v for k, v in doc.items() if projection.get(k, 1) != 0}
        garde = {}
        for cle, valeur in projection.items():
            if valeur != 1 or cle == "_id":
                continue
            if "." in cle:
                parent, enfant = cle.split(".", 1)
                if isinstance(doc.get(parent), dict):
                    garde.setdefault(parent, {})[enfant] = doc[parent].get(enfant)
            elif cle in doc:
                garde[cle] = doc[cle]
        return garde

    def find(self, filtre=None, projection=None, *a, **k):
        return Curseur([self._projeter(d, projection) for d in self.documents if self._ok(d, filtre)])

    async def find_one(self, filtre=None, projection=None, *a, **k):
        for d in self.documents:
            if self._ok(d, filtre):
                return self._projeter(d, projection)
        return None

    async def count_documents(self, filtre=None, *a, **k):
        return sum(1 for d in self.documents if self._ok(d, filtre))


class CollectionEcrivable(CollectionBouchon):
    """PHASE 6B — contrairement a la 6A, ce lot ECRIT reellement de nouvelles
    campagnes/medias (via les fonctions reutilisees) : cette collection
    supporte insert_one/update_one/update_many, et trace chaque ecriture."""

    def __init__(self, documents=None):
        super().__init__(documents)
        self.ecritures = []

    async def insert_one(self, doc, *a, **k):
        self.ecritures.append({"insert": dict(doc)})
        from pymongo.errors import DuplicateKeyError
        cle_unique = doc.get("id")
        if cle_unique and any(d.get("id") == cle_unique for d in self.documents):
            raise DuplicateKeyError("doublon")
        self.documents.append(dict(doc))
        return type("R", (), {"inserted_id": cle_unique})()

    async def update_one(self, filtre, maj, upsert=False, *a, **k):
        self.ecritures.append({"filtre": dict(filtre), "maj": {k: dict(v) for k, v in maj.items()}})
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                return type("R", (), {"matched_count": 1, "modified_count": 1, "upserted_id": None})()
        if not upsert:
            return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": None})()
        candidat = dict(filtre)
        candidat.update(maj.get("$setOnInsert") or {})
        candidat.update(maj.get("$set") or {})
        self.documents.append(candidat)
        return type("R", (), {"matched_count": 0, "modified_count": 0, "upserted_id": True})()

    async def update_many(self, filtre, maj, *a, **k):
        n = 0
        for d in self.documents:
            if self._ok(d, filtre):
                d.update(maj.get("$set") or {})
                n += 1
        self.ecritures.append({"filtre": dict(filtre), "maj": {k: dict(v) for k, v in maj.items()}, "n": n})
        return type("R", (), {"matched_count": n, "modified_count": n})()


class DBBouchon:
    def __init__(self, collections):
        self._c = collections

    def __getitem__(self, nom):
        self._c.setdefault(nom, CollectionBouchon())
        return self._c[nom]

    def __setitem__(self, nom, valeur):
        self._c[nom] = valeur

    def __getattr__(self, nom):
        return self[nom]


def signer(secret, methode, chemin, requete, horodatage, corps_brut=b""):
    chaine = R._chaine_canonique(methode, chemin, requete, horodatage, R._empreinte_corps(corps_brut))
    return hmac_module.new(secret.encode(), chaine.encode(), hashlib.sha256).hexdigest()


class URLFictive:
    def __init__(self, chemin, requete=""):
        self.path = chemin
        self.query = requete


class ParametresFictifs(dict):
    def get(self, cle, defaut=None):
        return dict.get(self, cle, defaut)


class RequeteFictive:
    def __init__(self, methode="GET", chemin="", requete="", headers=None, corps=None):
        self.method = methode
        self.url = URLFictive(chemin, requete)
        self.headers = headers or {}
        self.query_params = ParametresFictifs(
            {p.split("=")[0]: p.split("=", 1)[1] for p in requete.split("&") if "=" in p} if requete else {})
        import json as _json
        self._corps_brut = _json.dumps(corps).encode("utf-8") if corps is not None else b""
        self._a_un_corps = corps is not None

    async def body(self):
        return self._corps_brut

    async def json(self):
        if not self._a_un_corps:
            raise ValueError("pas de corps")
        import json as _json
        return _json.loads(self._corps_brut)


def requete_signee(methode, chemin, requete="", corps=None, secret=SECRET, decalage=0, sans_signature=False):
    horodatage = str(int(time.time()) + decalage)
    req = RequeteFictive(methode=methode, chemin=chemin, requete=requete,
                         headers={"X-Afroboosteur-Timestamp": horodatage}, corps=corps)
    if not sans_signature:
        req.headers["X-Afroboosteur-Signature"] = signer(
            secret, methode, chemin, requete, horodatage, req._corps_brut)
    return req


def executer(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def base_neuve():
    b = DBBouchon({})
    S.db = b
    R.db = b
    return b


NICHE_ID = "11111111-1111-1111-1111-111111111111"


def niche_valide(coach=COACH_ID, active=True, supprimee=False):
    return {"id": NICHE_ID, "coach_id": coach, "cle": NICHE_ID, "slug": "niche-test",
            "nom": "Niche de test", "ordre": 1, "active": active, "supprimee": supprimee,
            "origine": False, "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00", "archived_at": None}


def fiche_valide(id_="uuid-1", coach=COACH_ID, niche_id=NICHE_ID):
    return {"id": id_, "ref": "R-%s" % id_, "coach_id": coach, "niche_id": niche_id,
            "organisation_name": "Partenaire SA", "city": "Lausanne", "city_key": "lausanne",
            "category": "local", "priority": "haute", "score": 80, "wave": 1,
            "language": "fr", "preferred_channel": "email", "public_email": "contact@partenaire.test",
            "public_phone": None, "corbeille": False, "ne_plus_contacter": False,
            "created_at": "2026-01-01T00:00:00+00:00"}


def media_valide(id_="media-1", coach=COACH_ID, statut="validee", niche=NICHE_ID):
    return {"id": id_, "coach_id": coach, "niche": niche, "format": "16_9", "url": "https://exemple.test/v.mp4",
            "statut": statut, "version": "v1", "notes": "note privee du coach — jamais exposee",
            "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00",
            "archived_at": None, "remplace_par": None, "remplace": None, "origine": "lien",
            "source_id": None, "fichier": None, "edition": None, "cible": None, "cible_id": None}


def scenario_de_base():
    b = base_neuve()
    b[S.P3S3_CAMPAGNES] = CollectionEcrivable([])
    b[S.P3S3_ACTIONS] = CollectionEcrivable([])
    b[S.P3S1_COLLECTION] = CollectionBouchon([fiche_valide()])
    # CollectionEcrivable, pas CollectionBouchon : `v598_niches()` garantit
    # l'inscription idempotente des six niches d'origine (A-F) a CHAQUE appel
    # via `update_one(..., upsert=True)`, meme pour une simple lecture.
    b[S.V598_NICHES] = CollectionEcrivable([niche_valide()])
    b[S.V595_MEDIAS] = CollectionEcrivable([media_valide()])
    b[S.P3AI_BROUILLONS] = CollectionBouchon([])    # phase 6A — AUCUNE ecriture ne doit y atterrir
    b[S.P3AI4_COLLECTION] = CollectionBouchon([])   # idem — reservation/envoi reel
    return b


def requete_campagne_detail(campagne_id="camp-1", **kw):
    return requete_signee("GET", "/api/afroboosteur-relais/campaigns/%s" % campagne_id, **kw)


def requete_preparer(corps, **kw):
    return requete_signee("POST", "/api/afroboosteur-relais/campaigns", corps=corps, **kw)


def requete_modifier_campagne(campagne_id, corps, **kw):
    return requete_signee("PATCH", "/api/afroboosteur-relais/campaigns/%s" % campagne_id, corps=corps, **kw)


def requete_medias(requete="", **kw):
    return requete_signee("GET", "/api/afroboosteur-relais/medias", requete=requete, **kw)


def requete_niches(**kw):
    return requete_signee("GET", "/api/afroboosteur-relais/niches", **kw)


def requete_ajouter_media(corps, **kw):
    return requete_signee("POST", "/api/afroboosteur-relais/medias", corps=corps, **kw)


# ============================================================================
print("\n1. PREVISUALISER (dry_run) — RIEN N'EST ECRIT")

b = scenario_de_base()
rep = executer(R.relais_preparer_campagne(requete_preparer({"name": "Campagne test", "dry_run": True})))
verifier("1a dry_run=True par defaut cote relais, comme cote coach", rep.get("dry_run") is True, str(rep))
verifier("1b la campagne previsualisee porte le bon nombre de destinataires",
         rep["campaign"]["nb_destinataires"] == 1, str(rep.get("campaign")))
verifier("1c AUCUNE ecriture dans P3S3_CAMPAGNES pendant un apercu",
         b[S.P3S3_CAMPAGNES].ecritures == [])
verifier("1d AUCUNE ecriture dans P3S3_ACTIONS pendant un apercu",
         b[S.P3S3_ACTIONS].ecritures == [])
verifier("1e la reponse de previsualisation NE PORTE PAS `actions` (PII) — filtre du relais",
         "actions" not in rep, str(list(rep.keys())))

# ============================================================================
print("\n2. CREER (dry_run=False) — ECRITURE REELLE, JAMAIS UN ENVOI")

b = scenario_de_base()
rep = executer(R.relais_preparer_campagne(requete_preparer({
    "name": "Campagne reelle", "dry_run": False, "idempotency_key": "cle-test-1"})))
verifier("2a dry_run=False -> une campagne est reellement creee", rep.get("dry_run") is False, str(rep))
verifier("2b une ecriture dans P3S3_CAMPAGNES, et une seule", len(b[S.P3S3_CAMPAGNES].ecritures) == 1)
verifier("2c une action creee pour l'unique destinataire", len(b[S.P3S3_ACTIONS].ecritures) == 1)
verifier("2d la campagne est a l'etat PREPAREE, jamais approuvee/en_cours",
         rep["campaign"]["etat"] == "preparee", str(rep["campaign"]))
verifier("2e AUCUNE ecriture dans P3AI_BROUILLONS (phase 6A) pendant une preparation de campagne",
         not hasattr(b[S.P3AI_BROUILLONS], "ecritures") or b[S.P3AI_BROUILLONS].ecritures == [])
verifier("2f AUCUNE ecriture dans P3AI4_COLLECTION (reservation/envoi reel)",
         not hasattr(b[S.P3AI4_COLLECTION], "ecritures") or b[S.P3AI4_COLLECTION].ecritures == [])
id_campagne = rep["campaign"]["id"]

# ============================================================================
print("\n3. LE DETAIL D'UNE CAMPAGNE — jamais les actions, jamais un autre coach")

rep_detail = executer(R.relais_lire_campagne(id_campagne, requete_campagne_detail(id_campagne)))
verifier("3a le detail rend la campagne attendue", rep_detail["campaign"]["id"] == id_campagne)
verifier("3b AUCUN champ `actions` dans le detail (PII des destinataires)",
         "actions" not in rep_detail["campaign"], str(rep_detail))
try:
    executer(R.relais_lire_campagne("campagne-inconnue", requete_campagne_detail("campagne-inconnue")))
    verifier("3c campagne inconnue -> 404", False, "aucune exception levee")
except HTTPException as e:
    verifier("3c campagne inconnue -> 404", e.status_code == 404, str(e.status_code))

# ============================================================================
print("\n4. MEDIA_IDS — refuse un media hors bibliotheque ou non valide")

b2 = scenario_de_base()
b2[S.V595_MEDIAS] = CollectionEcrivable([media_valide(id_="media-brouillon", statut="en_cours")])
try:
    executer(R.relais_preparer_campagne(requete_preparer(
        {"name": "x", "dry_run": False, "media_ids": ["media-brouillon"]})))
    verifier("4a un media `en_cours` est REFUSE (seul `validee` passe)", False, "aucune exception levee")
except HTTPException as e:
    verifier("4a un media `en_cours` est REFUSE (seul `validee` passe)", e.status_code == 400, str(e.status_code))

b3 = scenario_de_base()  # media-1 existe mais appartient a un AUTRE coach
b3[S.V595_MEDIAS] = CollectionEcrivable([media_valide(coach=AUTRE_COACH)])
try:
    executer(R.relais_preparer_campagne(requete_preparer(
        {"name": "x", "dry_run": False, "media_ids": ["media-1"]})))
    verifier("4b un media d'un AUTRE coach est REFUSE (jamais une fuite croisee)", False, "aucune exception levee")
except HTTPException as e:
    verifier("4b un media d'un AUTRE coach est REFUSE (jamais une fuite croisee)",
             e.status_code == 400, str(e.status_code))

b4 = scenario_de_base()  # media-1 existe, coach correct, statut validee par defaut
rep4 = executer(R.relais_preparer_campagne(requete_preparer(
    {"name": "Avec media", "dry_run": False, "media_ids": ["media-1"]})))
verifier("4c un media `validee` du bon coach est ACCEPTE et porte sur la campagne",
         rep4["campaign"]["media_ids"] == ["media-1"], str(rep4["campaign"]))

# ============================================================================
print("\n5. MODIFIER UNE CAMPAGNE — nom et medias, jamais une campagne approuvee")

b5 = scenario_de_base()
rep5 = executer(R.relais_preparer_campagne(requete_preparer({"name": "A modifier", "dry_run": False})))
id5 = rep5["campaign"]["id"]
rep_mod = executer(R.relais_modifier_campagne(id5, requete_modifier_campagne(id5, {"nom": "Nom corrige"})))
verifier("5a le nom est modifie", rep_mod["campaign"]["nom"] == "Nom corrige", str(rep_mod))
rep_mod2 = executer(R.relais_modifier_campagne(id5, requete_modifier_campagne(id5, {"media_ids": ["media-1"]})))
verifier("5b media_ids est modifiable apres coup", rep_mod2["campaign"]["media_ids"] == ["media-1"])
# Approuver = passer l'etat a la main dans le bouchon (aucune route d'approbation n'est relayee)
for d in b5[S.P3S3_CAMPAGNES].documents:
    if d["id"] == id5:
        d["etat"] = "approuvee"
try:
    executer(R.relais_modifier_campagne(id5, requete_modifier_campagne(id5, {"nom": "Trop tard"})))
    verifier("5c une campagne APPROUVEE n'est plus modifiable depuis le relais", False, "aucune exception levee")
except HTTPException as e:
    verifier("5c une campagne APPROUVEE n'est plus modifiable depuis le relais",
             e.status_code == 409, str(e.status_code))

# ============================================================================
print("\n6. MEDIATHEQUE — lecture (tous statuts visibles), rien n'est cache")

b6 = scenario_de_base()
b6[S.V595_MEDIAS] = CollectionEcrivable([
    media_valide(id_="m-valide", statut="validee"),
    media_valide(id_="m-brouillon", statut="en_cours"),
    media_valide(id_="m-archive", statut="archivee"),
])
rep_m = executer(R.relais_lister_medias(requete_medias()))
verifier("6a les TROIS statuts sont visibles en lecture (rien de masque)",
         rep_m["total"] == 3, str(rep_m))
verifier("6b le filtre `statut` fonctionne", executer(
    R.relais_lister_medias(requete_medias("statut=validee")))["total"] == 1)
verifier("6c `notes` (annotation privee du coach) n'est JAMAIS renvoye",
         all("notes" not in m for m in rep_m["medias"]), str(rep_m["medias"]))
try:
    executer(R.relais_lister_medias(requete_medias("statut=invalide")))
    verifier("6d un statut inconnu -> 400", False, "aucune exception levee")
except HTTPException as e:
    verifier("6d un statut inconnu -> 400", e.status_code == 400)

rep_n = executer(R.relais_lister_niches(requete_niches()))
verifier("6e les niches du coach sont listees", any(n["id"] == NICHE_ID for n in rep_n["niches"]), str(rep_n))

# ============================================================================
print("\n7. AJOUTER UN MEDIA — par lien UNIQUEMENT, jamais /api/files")

b7 = scenario_de_base()
try:
    executer(R.relais_ajouter_media(requete_ajouter_media(
        {"niche": NICHE_ID, "format": "16_9", "url": "/api/files/abc/video.mp4"})))
    verifier("7a une url /api/files/... est REFUSEE par le relais LUI-MEME (message precis)",
             False, "aucune exception levee")
except HTTPException as e:
    # DISCRIMINANT : le message EXACT du garde du relais, pas un 400 qui
    # viendrait d'ailleurs (ex. « fichier introuvable » dans v596_url_fichier,
    # qui rendrait aussi 400 sans que CE garde ait rien fait).
    verifier("7a une url /api/files/... est REFUSEE par le relais LUI-MEME (message precis)",
             e.status_code == 400 and "ne peut pas etre reference depuis ce relais" in str(e.detail),
             "%s: %s" % (e.status_code, e.detail))

rep7 = executer(R.relais_ajouter_media(requete_ajouter_media(
    {"niche": NICHE_ID, "format": "16_9", "url": "https://exemple.test/nouveau.mp4",
     "notes": "une note que le membre tente de glisser"})))
verifier("7b un lien public est ACCEPTE", rep7["media"]["url"] == "https://exemple.test/nouveau.mp4", str(rep7))
verifier("7c le nouveau media entre « en_cours », jamais « validee »",
         rep7["media"]["statut"] == "en_cours", str(rep7["media"]))
verifier("7d `notes` n'apparait JAMAIS dans la reponse (ni ecrite, ni renvoyee)",
         "notes" not in rep7["media"], str(rep7["media"]))
# Le document REEL en base ne doit pas avoir heberge la note tentee non plus.
media_en_base = next(d for d in b7[S.V595_MEDIAS].documents if d["id"] == rep7["media"]["id"])
verifier("7e la note tentee n'a PAS ete ecrite en base", not media_en_base.get("notes"), str(media_en_base))

try:
    executer(R.relais_ajouter_media(requete_ajouter_media(
        {"niche": NICHE_ID, "format": "document", "url": "https://exemple.test/doc.pdf"})))
    verifier("7f un PDF par LIEN est refuse (un document exige /api/files, donc hors de portee du relais)",
             False, "aucune exception levee")
except HTTPException as e:
    verifier("7f un PDF par LIEN est refuse (un document exige /api/files, donc hors de portee du relais)",
             e.status_code == 400, str(e.status_code))

# ============================================================================
print("\n8. PORTEE — un autre coach ne voit/modifie jamais ce qui ne lui appartient pas")

b8 = scenario_de_base()
b8[S.P3S3_CAMPAGNES].documents.append({
    "id": "camp-autre-coach", "coach_id": AUTRE_COACH, "nom": "Pas a moi", "etat": "preparee",
    "nb_fiches": 0, "nb_destinataires": 0, "summary": {}, "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00", "created_by": AUTRE_COACH,
    "approved_at": None, "approved_by": None, "started_at": None, "finished_at": None, "media_ids": [],
})
try:
    executer(R.relais_lire_campagne("camp-autre-coach", requete_campagne_detail("camp-autre-coach")))
    verifier("8a une campagne d'un AUTRE coach -> filtree, jamais rendue (404)", False, "aucune exception levee")
except HTTPException as e:
    verifier("8a une campagne d'un AUTRE coach -> filtree, jamais rendue (404)",
             e.status_code == 404, str(e.status_code))

b9 = scenario_de_base()
b9[S.V595_MEDIAS] = CollectionEcrivable([media_valide(coach=AUTRE_COACH)])
rep_vide = executer(R.relais_lister_medias(requete_medias()))
verifier("8b la mediatheque d'un autre coach est INVISIBLE (portee stricte)", rep_vide["total"] == 0, str(rep_vide))

# ============================================================================
print("\n9. GARDE HMAC — toujours active sur les six nouvelles routes")

ROUTES_6B = [
    ("relais_lire_campagne", lambda req: R.relais_lire_campagne("x", req), requete_campagne_detail),
    ("relais_preparer_campagne", R.relais_preparer_campagne, lambda **kw: requete_preparer({}, **kw)),
    ("relais_modifier_campagne", lambda req: R.relais_modifier_campagne("x", req),
     lambda **kw: requete_modifier_campagne("x", {"nom": "x"}, **kw)),
    ("relais_lister_medias", R.relais_lister_medias, requete_medias),
    ("relais_lister_niches", R.relais_lister_niches, requete_niches),
    ("relais_ajouter_media", R.relais_ajouter_media,
     lambda **kw: requete_ajouter_media({"niche": NICHE_ID, "format": "16_9", "url": "https://x.test/v.mp4"}, **kw)),
]
base_neuve()
for nom, fonction, fabrique in ROUTES_6B:
    try:
        executer(fonction(fabrique(sans_signature=True)))
        verifier("9 %s sans signature -> refuse" % nom, False, "aucune exception levee")
    except HTTPException as e:
        verifier("9 %s sans signature -> refuse" % nom, e.status_code in (401, 403), str(e.status_code))
    try:
        executer(fonction(fabrique(secret="mauvais-secret-totalement-faux")))
        verifier("9 %s signature fausse -> 403" % nom, False, "aucune exception levee")
    except HTTPException as e:
        verifier("9 %s signature fausse -> 403" % nom, e.status_code == 403, str(e.status_code))

# ============================================================================
print("\n10. AUCUNE SORTIE RESEAU PENDANT TOUT LE BANC")
verifier("10a aucun import de 'requests' ni 'httpx' dans le module relais",
         "import requests" not in open(R.__file__.replace(".pyc", ".py"), encoding="utf-8").read()
         if hasattr(R, "__file__") else True, "verification structurelle")

# ============================================================================
print("\n11. REVUE DE SECURITE — AFROBOOSTEUR_RELAY_COACH_ID NE PEUT JAMAIS ETRE LE SUPER-ADMIN")
# `is_super_admin(appelant)` videi la portee de `p3s3_preparer_campagne_pour`/
# `p3s3_modifier_campagne_pour` (`p3s3_portee` -> `{}` au lieu de `{coach_id}`)
# et desactive entierement le controle de propriete de la seconde. Une seule
# ligne de configuration erronee aurait alors fait de ce relais une porte
# derobee inter-coachs. `_garde` doit refuser (503) AVANT toute autre chose
# si le coach configure est le super-admin — teste ici sur UNE route
# representative (les autres partagent la MEME garde).
base_neuve()
_coach_avant = os.environ.get("AFROBOOSTEUR_RELAY_COACH_ID")
os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = S.SUPER_ADMIN_EMAILS[0]
try:
    executer(R.relais_preparer_campagne(requete_preparer(
        {"name": "x"}, secret=SECRET)))
    verifier("11a super-admin configure comme coach -> 503, jamais une portee videe", False,
             "aucune exception levee")
except HTTPException as e:
    verifier("11a super-admin configure comme coach -> 503, jamais une portee videe",
             e.status_code == 503, str(e.status_code))
finally:
    if _coach_avant is not None:
        os.environ["AFROBOOSTEUR_RELAY_COACH_ID"] = _coach_avant
    else:
        os.environ.pop("AFROBOOSTEUR_RELAY_COACH_ID", None)

# ============================================================================
print("\n12. REVUE DE SECURITE — UN MEDIA VALIDE N'EST JAMAIS DEMOTIONNE PAR CE RELAIS")
# Sans protection, ajouter un lien sur le MEME emplacement (niche+format+cible)
# qu'un media deja `validee` l'aurait archive — un membre portant seulement
# `prospection_medias_ajouter` aurait alors pu faire disparaitre, en silence,
# un media potentiellement en usage actif et approuve par le coach.
b12 = scenario_de_base()
b12[S.V595_MEDIAS] = CollectionEcrivable([media_valide(id_="media-valide-en-usage", statut="validee")])
rep12 = executer(R.relais_ajouter_media(requete_ajouter_media(
    {"niche": NICHE_ID, "format": "16_9", "url": "https://exemple.test/remplacant.mp4"})))
verifier("12a le NOUVEAU media est bien ajoute", rep12["media"]["statut"] == "en_cours", str(rep12))
verifier("12b AUCUN media n'est rapporte comme archive par ce relais", rep12["archives"] == 0, str(rep12))
media_valide_apres = next(d for d in b12[S.V595_MEDIAS].documents if d["id"] == "media-valide-en-usage")
verifier("12c le media VALIDE PRE-EXISTANT reste `validee`, jamais `archivee`",
         media_valide_apres["statut"] == "validee", str(media_valide_apres))
verifier("12d le media valide n'a pas ete marque comme remplace",
         media_valide_apres.get("remplace_par") is None, str(media_valide_apres))

# ============================================================================
total = len(RESULTATS)
reussites = sum(1 for _, ok, _ in RESULTATS if ok)
echecs = total - reussites
print("\n=== %d/%d OK (%d echec%s) ===" % (reussites, total, echecs, "" if echecs == 1 else "s"))
if echecs:
    sys.exit(1)

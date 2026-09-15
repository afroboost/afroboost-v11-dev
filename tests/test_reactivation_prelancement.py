# -*- coding: utf-8 -*-
"""RÉACTIVATION 3B — L'INFRASTRUCTURE E-MAIL, PROUVÉE SANS AUCUN ENVOI.

Ce banc importe la VRAIE application (`api.server`, comme uvicorn), remplace la
base par un faux Mongo en mémoire et le fournisseur d'e-mail par un enregistreur :
AUCUN e-mail, WhatsApp ou push ne part. Il exécute ensuite les scénarios A–H du
GO du 15/09/2026, puis des contrôles structurels (front + routes).

  A. 3 personnes « essai_non_converti » -> aperçu = 3 -> lancement = 3 envois
     ENREGISTRÉS par le faux fournisseur, zéro réseau ;
  B. 1 personne opt-out -> exclue, journalisée `skipped/opt_out` ;
  C. 1 personne devenue abonnée active -> exclue, journalisée `skipped/actif` ;
  D. retry de la même campagne -> UN seul envoi (clé d'idempotence) ;
  E. `targetCategories` filtre réellement (segments -> destinataires) ;
  F. lien de désinscription : jeton reconnu -> `opted_out` -> campagne suivante
     l'exclut ;
  G. lien de réactivation : nomenclature UTM exacte ;
  H. first-touch Instagram conservé, la campagne se lit en `last`.

Lancement :  python3 tests/test_reactivation_prelancement.py
"""
import asyncio
import copy
import io
import os
import re
import sys
import uuid
from datetime import datetime, timezone, timedelta

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

# Environnement HERMÉTIQUE : aucune clé réelle, aucun réseau possible.
os.environ["MONGO_URL"] = "mongodb://127.0.0.1:27017/?serverSelectionTimeoutMS=1"
os.environ["DB_NAME"] = "r3_banc"
os.environ["JWT_SECRET"] = "r3-banc-secret-local"
os.environ["RESEND_API_KEY"] = "re_banc_factice_jamais_reel"
for _k in ("META_WHATSAPP_TOKEN", "META_WHATSAPP_PHONE_ID", "TWILIO_ACCOUNT_SID", "VAPID_PRIVATE_KEY"):
    os.environ.pop(_k, None)

import api.server as S                                     # noqa: E402
from api.routes import contact_segments_routes as SEG      # noqa: E402
from api.routes import campaign_routes as CR               # noqa: E402
from api.routes import reactivation as R                   # noqa: E402
from api.routes import shared as SH                        # noqa: E402
from api.routes import analytics_shared as A               # noqa: E402

OK = RATE = 0


def verifier(nom, cond, detail=""):
    global OK, RATE
    if cond:
        OK += 1; print("  OK  ", nom)
    else:
        RATE += 1; print("  RATE", nom, ("  [%s]" % (detail,)) if detail != "" else "")


def run(c):
    return asyncio.get_event_loop().run_until_complete(c)


# ═══ FAUX MONGO EN MÉMOIRE (asynchrone, comme Motor) ═══════════════════════════
MANQUANT = object()


def _val(doc, chemin):
    cur = doc
    for part in chemin.split("."):
        if isinstance(cur, list):
            # Traversée d'un tableau de sous-documents (« results.email_id »).
            vals = [_val(x, part) for x in cur if isinstance(x, dict)]
            vals = [v for v in vals if v is not MANQUANT]
            return vals if vals else MANQUANT
        if not isinstance(cur, dict) or part not in cur:
            return MANQUANT
        cur = cur[part]
    return cur


def _egal(obtenu, attendu):
    if obtenu is MANQUANT:
        return attendu is None
    if isinstance(obtenu, list) and not isinstance(attendu, list):
        return attendu in obtenu
    return obtenu == attendu


def _match(doc, q):
    for cle, attendu in (q or {}).items():
        if cle == "$or":
            if not any(_match(doc, s) for s in attendu):
                return False
            continue
        if cle == "$and":
            if not all(_match(doc, s) for s in attendu):
                return False
            continue
        obtenu = _val(doc, cle)
        if isinstance(attendu, dict) and any(k.startswith("$") for k in attendu):
            for op, v in attendu.items():
                if op == "$options":
                    continue
                if op == "$in":
                    if not any(_egal(obtenu, x) for x in v):
                        return False
                elif op == "$nin":
                    if any(_egal(obtenu, x) for x in v):
                        return False
                elif op == "$ne":
                    if _egal(obtenu, v):
                        return False
                elif op == "$exists":
                    if (obtenu is not MANQUANT) != bool(v):
                        return False
                elif op in ("$gte", "$gt", "$lte", "$lt"):
                    if obtenu is MANQUANT or type(obtenu) is not type(v):
                        return False
                    if op == "$gte" and not obtenu >= v: return False
                    if op == "$gt" and not obtenu > v: return False
                    if op == "$lte" and not obtenu <= v: return False
                    if op == "$lt" and not obtenu < v: return False
                elif op == "$regex":
                    if not isinstance(obtenu, str):
                        return False
                    flags = re.I if "i" in (attendu.get("$options") or "") else 0
                    if not re.search(v, obtenu, flags):
                        return False
                else:
                    raise AssertionError("opérateur non simulé : %s" % op)
        else:
            if not _egal(obtenu, attendu):
                return False
    return True


def _poser(doc, chemin, valeur):
    parts = chemin.split(".")
    cur = doc
    for i, part in enumerate(parts[:-1]):
        if part == "$":
            raise AssertionError("positionnel $ hors update_one positionnel")
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = valeur


def _appliquer(doc, m, insere=False, position=None):
    for op, champs in m.items():
        if op == "$set":
            for k, v in champs.items():
                if ".$." in k:
                    tab, sous = k.split(".$.", 1)
                    doc[tab][position][sous] = v
                else:
                    _poser(doc, k, v)
        elif op == "$setOnInsert":
            if insere:
                for k, v in champs.items():
                    _poser(doc, k, v)
        elif op == "$unset":
            for k in champs:
                doc.pop(k, None)
        elif op == "$push":
            for k, v in champs.items():
                doc.setdefault(k, []).append(v)
        elif op == "$inc":
            for k, v in champs.items():
                doc[k] = (doc.get(k) or 0) + v
        elif op == "$addToSet":
            for k, v in champs.items():
                if v not in doc.setdefault(k, []):
                    doc[k].append(v)
        else:
            raise AssertionError("mise à jour non simulée : %s" % op)


def _projeter(doc, p):
    if not p:
        return copy.deepcopy(doc)
    inclus = {k for k, v in p.items() if v and k != "_id"}
    exclus = {k for k, v in p.items() if not v}
    if inclus:
        return {k: copy.deepcopy(doc[k]) for k in inclus if k in doc}
    return {k: copy.deepcopy(v) for k, v in doc.items() if k not in exclus}


class _Res:
    def __init__(self, n, upserted=None):
        self.matched_count = n; self.modified_count = n; self.upserted_id = upserted
        self.deleted_count = n; self.inserted_id = upserted


class _Curseur:
    def __init__(self, docs, p=None):
        self.d = docs; self.p = p

    def sort(self, *a, **k):
        cle = a[0] if a and isinstance(a[0], str) else (a[0][0][0] if a and a[0] else None)
        sens = a[1] if len(a) > 1 else (a[0][0][1] if a and isinstance(a[0], list) else 1)
        if cle:
            self.d = sorted(self.d, key=lambda x: (x.get(cle) is None, x.get(cle) or ""), reverse=(sens == -1))
        return self

    def limit(self, n):
        self.d = self.d[:n]; return self

    def skip(self, n):
        self.d = self.d[n:]; return self

    async def to_list(self, n=None):
        await asyncio.sleep(0)
        return [_projeter(x, self.p) for x in (self.d if n is None else self.d[:n])]

    def __aiter__(self):
        self._i = 0; return self

    async def __anext__(self):
        await asyncio.sleep(0)
        if self._i >= len(self.d):
            raise StopAsyncIteration
        self._i += 1
        return _projeter(self.d[self._i - 1], self.p)


class _Coll:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.appels = []

    def find(self, q=None, p=None, **k):
        self.appels.append(("find", q))
        return _Curseur([d for d in self.docs if _match(d, q or {})], p)

    async def find_one(self, q, p=None, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q or {}):
                return _projeter(d, p)
        return None

    async def count_documents(self, q=None, **k):
        await asyncio.sleep(0)
        return sum(1 for d in self.docs if _match(d, q or {}))

    async def distinct(self, champ, q=None):
        await asyncio.sleep(0)
        return sorted({d.get(champ) for d in self.docs if _match(d, q or {}) and d.get(champ) is not None})

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        self.docs.append(dict(doc)); return _Res(1, "id")

    async def insert_many(self, docs, **k):
        await asyncio.sleep(0)
        self.docs.extend(dict(d) for d in docs); return _Res(len(docs))

    def _update(self, q, m, upsert=False, many=False):
        n = 0
        for d in self.docs:
            if _match(d, q or {}):
                pos = None
                if any(".$." in k for op in m.values() if isinstance(op, dict) for k in op):
                    tab = [k for op in m.values() for k in op if ".$." in k][0].split(".$.")[0]
                    sous = {k.split(".", 1)[1]: v for k, v in q.items() if k.startswith(tab + ".")}
                    for i, x in enumerate(d.get(tab) or []):
                        if all(_egal(_val(x, kk), vv) for kk, vv in sous.items()):
                            pos = i; break
                _appliquer(d, m, position=pos)
                n += 1
                if not many:
                    break
        if n == 0 and upsert:
            neuf = {k: v for k, v in (q or {}).items() if not isinstance(v, dict)}
            _appliquer(neuf, m, insere=True)
            self.docs.append(neuf)
            return _Res(0, "upserted")
        return _Res(n)

    async def update_one(self, q, m, upsert=False, **k):
        await asyncio.sleep(0)
        return self._update(q, m, upsert=upsert)

    async def update_many(self, q, m, upsert=False, **k):
        await asyncio.sleep(0)
        return self._update(q, m, upsert=upsert, many=True)

    async def find_one_and_update(self, q, m, return_document=False, **k):
        await asyncio.sleep(0)
        for d in self.docs:
            if _match(d, q or {}):
                avant = copy.deepcopy(d)
                _appliquer(d, m)
                return copy.deepcopy(d) if return_document else avant
        return None

    async def delete_one(self, q):
        await asyncio.sleep(0)
        for i, d in enumerate(self.docs):
            if _match(d, q or {}):
                del self.docs[i]; return _Res(1)
        return _Res(0)

    async def delete_many(self, q):
        await asyncio.sleep(0)
        avant = len(self.docs)
        self.docs = [d for d in self.docs if not _match(d, q or {})]
        return _Res(avant - len(self.docs))

    async def bulk_write(self, ops, ordered=True):
        await asyncio.sleep(0)
        for op in ops:
            d = op._doc if hasattr(op, "_doc") else None
            self._update(op._filter, d, upsert=getattr(op, "_upsert", False))
        return _Res(len(ops))

    async def create_index(self, *a, **k):
        return "idx"


class _Base:
    def __init__(self):
        self._c = {}

    def __getattr__(self, nom):
        if nom.startswith("_"):
            raise AttributeError(nom)
        return self._c.setdefault(nom, _Coll())

    def __getitem__(self, nom):
        return self._c.setdefault(nom, _Coll())


class _FauxEmails:
    envoyes = []

    @staticmethod
    def send(params):
        _FauxEmails.envoyes.append(copy.deepcopy(params))
        return {"id": "em_" + uuid.uuid4().hex[:12]}


def brancher(base):
    """Aiguille TOUTE l'application vers le faux Mongo et le faux fournisseur."""
    S.db = base; SEG.db = base; CR.db = base
    for mod in (SH,):
        if hasattr(mod, "db"):
            mod.db = base
    S.resend.Emails.send = _FauxEmails.send
    S.RESEND_AVAILABLE = True
    S.RESEND_API_KEY = "re_banc_factice_jamais_reel"

    async def _pas_de_whatsapp():
        return {}
    S._get_whatsapp_config = _pas_de_whatsapp
    _FauxEmails.envoyes.clear()


MAINTENANT = datetime.now(timezone.utc)
ADMIN = "contact.artboost@gmail.com"


def jeton(email=ADMIN, role="coach"):
    import jwt
    return jwt.encode({"email": email, "type": role, "exp": MAINTENANT + timedelta(hours=1)},
                      os.environ["JWT_SECRET"], algorithm="HS256")


def personne(idx, email, nom, essai_present=True, sub_extra=None, resa_extra=None):
    """Une personne « essai présent non converti » dans la forme exacte de la base."""
    uid = "u%d" % idx
    code = "AFR-ESSAI%d" % idx
    d0 = (MAINTENANT - timedelta(days=40)).isoformat()
    sub = {"id": "s%d" % idx, "email": email, "name": nom, "offer_name": "Cours d'essai GRATUIT", "code": code,
           "status": "active", "created_at": d0, "origine_paiement": "offert", "remaining_sessions": 0}
    sub.update(sub_extra or {})
    resa = {"id": "r%d" % idx, "userEmail": email, "userName": nom, "datetime": (MAINTENANT - timedelta(days=38)).isoformat(),
            "createdAt": d0, "validated": bool(essai_present), "discountCode": code, "courseName": "Afroboost Cardio"}
    resa.update(resa_extra or {})
    user = {"id": uid, "name": nom, "email": email, "whatsapp": ""}
    return user, sub, resa


def base_scenario():
    base = _Base()
    u1, s1, r1 = personne(1, "amina@exemple.ch", "Amina K")
    u2, s2, r2 = personne(2, "bruno@exemple.ch", "Bruno L")
    u3, s3, r3 = personne(3, "chloe@exemple.ch", "Chloé M")
    base.users.docs = [u1, u2, u3]
    base.subscriptions.docs = [s1, s2, s3]
    base.reservations.docs = [r1, r2, r3]
    return base


def campagne(cid="camp1", segments=("essai_non_converti",), **extra):
    doc = {"id": cid, "name": "Reprise hiver", "message": "Salut {prénom}, on reprend !", "mediaUrl": "",
           "targetType": "all", "selectedContacts": [], "channels": {"email": True, "whatsapp": False, "internal": False},
           "targetIds": [], "targetCategories": list(segments), "status": "draft", "coach_id": ADMIN, "results": [],
           "createdAt": MAINTENANT.isoformat()}
    doc.update(extra)
    return doc


class _Req:
    def __init__(self, token=None, corps=None):
        self.headers = {"Authorization": "Bearer " + token} if token else {}
        self._corps = corps or {}

    async def json(self):
        return self._corps


def _refus(coro_fn, *a):
    """Le code HTTP levé par une route (0 si elle n'a pas refusé)."""
    try:
        run(coro_fn(*a))
        return 0
    except S.HTTPException as e:
        return e.status_code


def lancer(cid):
    return run(S.launch_campaign(cid))


# ═══ A. 3 PERSONNES -> APERÇU 3 -> LANCEMENT 3, ZÉRO RÉSEAU ══════════════════
print("\n[A] 3 essais présents non convertis")
base = base_scenario(); brancher(base)
base.campaigns.docs = [campagne()]
apercu = run(S.r3_previsualiser_campagne("camp1", _Req(jeton())))
verifier("A1. aperçu : 3 destinataires, 0 exclu", apercu["compteurs"]["destinataires"] == 3 and apercu["compteurs"]["opt_out"] == 0, apercu["compteurs"])
verifier("A2. aperçu : segment lu, lien UTM prêt, message présent", apercu["segments"][0]["cle"] == "essai_non_converti"
         and "utm_content=essai_non_converti" in apercu["segments"][0]["lien"] and apercu["campagne"]["message"].startswith("Salut"))
verifier("A3. aperçu : e-mails MASQUÉS, jamais en clair", all("…@" in l["email"] and "amina@" not in l["email"] for l in apercu["liste"]), apercu["liste"])
verifier("A4. aperçu : AUCUN envoi, AUCUNE écriture au registre", len(_FauxEmails.envoyes) == 0 and len(base.subscribers.docs) == 0)
verifier("A5. aperçu sans jeton -> 403", _refus(S.r3_previsualiser_campagne, "camp1", _Req()) == 403)
verifier("A6. aperçu par un autre coach -> 403", _refus(S.r3_previsualiser_campagne, "camp1", _Req(jeton("autre@coach.ch"))) == 403)
verifier("A7. segments seuls ≠ « tous les utilisateurs » (targetType=all sans cible n'élargit pas)",
         sorted(l["segment"] for l in apercu["liste"]) == ["essai_non_converti"] * 3, apercu["liste"])

res = lancer("camp1")
envois = [r for r in res["results"] if r["channel"] == "email" and r["status"] == "sent"]
verifier("A8. lancement : 3 envois enregistrés par le FAUX fournisseur (aucun réseau)", len(_FauxEmails.envoyes) == 3 and len(envois) == 3, (len(_FauxEmails.envoyes), len(envois)))
verifier("A9. chaque e-mail porte List-Unsubscribe (un-clic RFC 8058) + reply_to réel + pied de désinscription",
         all(p.get("headers", {}).get("List-Unsubscribe-Post") == "List-Unsubscribe=One-Click"
             and "/api/subscribers/unsubscribe?token=" in p["headers"]["List-Unsubscribe"]
             and "mailto:contact@afroboosteur.com" in p["headers"]["List-Unsubscribe"]
             and p["reply_to"] == "contact@afroboosteur.com"
             and "Ne plus recevoir ces e-mails" in p["html"] for p in _FauxEmails.envoyes), _FauxEmails.envoyes[0].get("headers"))
verifier("A10. jamais de mailto vers notifications@afroboost.com (pas de MX)", all("afroboost.com?subject" not in p["headers"]["List-Unsubscribe"] for p in _FauxEmails.envoyes))
verifier("A11. registre : 3 lignes `customer` (relation client), source relation_client, JAMAIS confirmed/opt-in",
         len(base.subscribers.docs) == 3 and all(d["status"] == "customer" and d["source"] == "relation_client" and d["unsubscribe_token"] for d in base.subscribers.docs), base.subscribers.docs)
verifier("A12. journal `campaigns.results` : clé d'idempotence + segment sur chaque envoi",
         all(r["cle"] == R.cle_idempotence("camp1", "email", r["contactEmail"]) and r["segment"] == "essai_non_converti" for r in envois), envois)
verifier("A13. le jeton du lien = celui du registre pour la MÊME adresse",
         all(any(d["value"] == p["to"][0] and d["unsubscribe_token"] in p["headers"]["List-Unsubscribe"] for d in base.subscribers.docs) for p in _FauxEmails.envoyes))
verifier("A14. statut final `completed`", res["status"] == "completed", res.get("status"))

# ═══ B. OPT-OUT -> EXCLUE AUTOMATIQUEMENT ════════════════════════════════════
print("\n[B] un refus enregistré")
base = base_scenario(); brancher(base)
base.subscribers.docs = [{"channel": "email", "value": "bruno@exemple.ch", "status": "opted_out", "unsubscribe_token": "tok-b"}]
base.campaigns.docs = [campagne()]
apercu = run(S.r3_previsualiser_campagne("camp1", _Req(jeton())))
verifier("B1. aperçu : 2 destinataires, 1 opt-out", apercu["compteurs"]["destinataires"] == 2 and apercu["compteurs"]["opt_out"] == 1, apercu["compteurs"])
res = lancer("camp1")
verifier("B2. lancement : 2 envois, Bruno jamais transmis au fournisseur", len(_FauxEmails.envoyes) == 2 and all(p["to"][0] != "bruno@exemple.ch" for p in _FauxEmails.envoyes))
verifier("B3. journal : l'exclusion est ÉCRITE (skipped / opt_out), pas silencieuse",
         any(r["status"] == "skipped" and r["exclu"] == "opt_out" and r["contactEmail"] == "bruno@exemple.ch" for r in res["results"]), res["results"])
verifier("B4. le registre du refusant n'est PAS réécrit (reste opted_out, jeton intact)",
         next(d for d in base.subscribers.docs if d["value"] == "bruno@exemple.ch")["status"] == "opted_out")

# ═══ C. DEVENUE ABONNÉE ACTIVE -> EXCLUE AU LANCEMENT ════════════════════════
print("\n[C] un client redevenu actif entre la sélection et l'envoi")
base = base_scenario(); brancher(base)
base.campaigns.docs = [campagne()]
apercu = run(S.r3_previsualiser_campagne("camp1", _Req(jeton())))
verifier("C1. avant : 3 destinataires", apercu["compteurs"]["destinataires"] == 3)
base.subscriptions.docs.append({"id": "s-chloe-abo", "email": "chloe@exemple.ch", "offer_name": "Abonnement mensuel HIVER", "status": "active",
                                "billing_mode": "mensuel_auto", "created_at": MAINTENANT.isoformat(), "remaining_sessions": 8})
res = lancer("camp1")
verifier("C2. au lancement (ciblage par segment) : 2 envois, Chloé n'est plus dans le segment", len(_FauxEmails.envoyes) == 2
         and all(p["to"][0] != "chloe@exemple.ch" for p in _FauxEmails.envoyes), [p["to"] for p in _FauxEmails.envoyes])
# Sélection MANUELLE (panier) : Chloé est nommément visée -> la garde l'écarte ET l'écrit.
base.campaigns.docs.append(campagne("camp1b", (), targetType="selected", targetIds=["u1", "u2", "u3"]))
_FauxEmails.envoyes.clear()
apercu = run(S.r3_previsualiser_campagne("camp1b", _Req(jeton())))
res = lancer("camp1b")
verifier("C2b. sélection manuelle : aperçu compte 1 actif, lancement 2 envois, Chloé journalisée `skipped/actif`",
         apercu["compteurs"]["actif"] == 1 and len(_FauxEmails.envoyes) == 2
         and any(r["status"] == "skipped" and r["exclu"] == "actif" and r["contactEmail"] == "chloe@exemple.ch" for r in res["results"]), (apercu["compteurs"], res["results"]))
verifier("C3. un droit actif EXPIRÉ ne protège pas (redevient ciblable)",
         not R.est_droit_actif({"status": "active", "offer_name": "Pulse", "expires_at": (MAINTENANT - timedelta(days=1)).isoformat(), "remaining_sessions": 3}))
verifier("C4. un droit actif sans séance restante et sans cycle n'est pas actif",
         not R.est_droit_actif({"status": "active", "offer_name": "Pulse", "remaining_sessions": 0}))
verifier("C5. un essai « actif » n'est jamais un droit actif", not R.est_droit_actif({"status": "active", "offer_name": "Cours d'essai GRATUIT", "remaining_sessions": 1}))

# ═══ D. RETRY -> UN SEUL ENVOI ════════════════════════════════════════════════
print("\n[D] retry technique de la même campagne")
base = base_scenario(); brancher(base)
base.campaigns.docs = [campagne()]
res1 = lancer("camp1")
verifier("D1. premier passage : 3 envois", len(_FauxEmails.envoyes) == 3)
res2 = lancer("camp1")
verifier("D2. relance d'une campagne `completed` : verrou atomique, 0 envoi supplémentaire", len(_FauxEmails.envoyes) == 3 and res2["status"] == "completed")
# Retry « technique » : le statut est remis (crash, reprogrammation) mais le journal est conservé.
base.campaigns.docs[0]["status"] = "draft"
res3 = lancer("camp1")
verifier("D3. journal conservé + statut remis : la clé d'idempotence bloque -> toujours 3 envois au total", len(_FauxEmails.envoyes) == 3, len(_FauxEmails.envoyes))
verifier("D4. les 3 envois d'origine restent dans le journal, les 3 exclusions `deja_envoye` sont écrites",
         sum(1 for r in res3["results"] if r["status"] == "sent") == 3 and sum(1 for r in res3["results"] if r.get("exclu") == "deja_envoye") == 3, res3["results"])
verifier("D5. clé = campagne|canal|e-mail normalisé (casse/espaces neutralisés)",
         R.cle_idempotence("c", "EMAIL", " Amina@Exemple.CH ") == R.cle_idempotence("c", "email", "amina@exemple.ch") == "c|email|amina@exemple.ch")

# ═══ E. targetCategories FILTRE RÉELLEMENT ═══════════════════════════════════
print("\n[E] le ciblage par segment")
base = base_scenario(); brancher(base)
# Un ancien abonné (pack Pulse expiré) + un client actif + une donnée de test + un ancien participant sans essai.
base.users.docs += [{"id": "u4", "name": "Dario P", "email": "dario@exemple.ch"},
                    {"id": "u5", "name": "Eva Q", "email": "eva@exemple.ch"},
                    {"id": "u6", "name": "Test Sonde", "email": "sonde@example.com"},
                    {"id": "u7", "name": "Farid R", "email": "farid@exemple.ch"}]
base.subscriptions.docs += [{"id": "s4", "email": "dario@exemple.ch", "offer_name": "Pulse 10 séances", "status": "expired", "created_at": (MAINTENANT - timedelta(days=200)).isoformat(), "remaining_sessions": 0},
                            {"id": "s5", "email": "eva@exemple.ch", "offer_name": "Abonnement mensuel", "status": "active", "billing_mode": "mensuel_auto", "created_at": MAINTENANT.isoformat()},
                            {"id": "s6", "email": "sonde@example.com", "offer_name": "Cours d'essai GRATUIT", "status": "active", "created_at": MAINTENANT.isoformat(), "origine_paiement": "offert"}]
base.reservations.docs += [{"id": "r7", "userEmail": "farid@exemple.ch", "userName": "Farid R", "datetime": (MAINTENANT - timedelta(days=120)).isoformat(),
                            "validated": True, "discountCode": "BASSBOOSTX-99", "courseName": "Afroboost Cardio"},
                           {"id": "r6", "userEmail": "sonde@example.com", "userName": "Test Sonde", "datetime": MAINTENANT.isoformat(), "validated": True, "discountCode": "AFR-ESSAI6", "courseName": "Cardio"}]
personnes, _ = run(SEG._calcule_personnes())
par_id = {p["id"]: set(p["etiquettes"]) for p in personnes}
verifier("E1. essai présent non converti -> `essai_non_converti` (u1..u3)", all("essai_non_converti" in par_id.get(u, set()) for u in ("u1", "u2", "u3")), par_id)
verifier("E2. pack Pulse expiré -> `ancien_abonne`, pas `essai_*`", "ancien_abonne" in par_id.get("u4", set()) and not any(k.startswith("essai") for k in par_id.get("u4", set())), par_id.get("u4"))
verifier("E3. client actif -> AUCUN segment de réactivation", not (par_id.get("u5", set()) & set(R.SEGMENTS_REACTIVATION)), par_id.get("u5"))
verifier("E4. donnée de test (example.com / « sonde ») -> AUCUN segment, et elle N'EST PAS supprimée",
         not (par_id.get("u6", set()) & set(R.SEGMENTS_REACTIVATION)) and any(u["id"] == "u6" for u in base.users.docs), par_id.get("u6"))
verifier("E5. ancien participant (cours payé, sans droit actif) -> `ancien_participant`", "ancien_participant" in par_id.get("u7", set()), par_id.get("u7"))
verifier("E6. les 6 clés sont connues de V363 (/contacts/segments les compte)", all(k in SEG.SEGMENTS_CONNUS for k in R.SEGMENTS_REACTIVATION))
base.campaigns.docs = [campagne("camp-abo", ("ancien_abonne",))]
apercu = run(S.r3_previsualiser_campagne("camp-abo", _Req(jeton())))
verifier("E7. campagne `ancien_abonne` -> 1 seul destinataire (Dario), pas les essais", apercu["compteurs"]["destinataires"] == 1 and apercu["liste"][0]["segment"] == "ancien_abonne", apercu)
base.campaigns.docs = [campagne("camp-2", ("essai_non_converti", "ancien_participant"))]
apercu = run(S.r3_previsualiser_campagne("camp-2", _Req(jeton())))
verifier("E8. deux segments -> union (3 essais + Farid = 4), test et actif absents", apercu["compteurs"]["destinataires"] == 4 and apercu["compteurs"]["test"] == 0, apercu["compteurs"])
base.campaigns.docs = [campagne("camp-tous", ())]
apercu = run(S.r3_previsualiser_campagne("camp-tous", _Req(jeton())))
verifier("E9. sans segment ni cible, targetType=all garde l'ancien comportement (tous les users), garde appliquée : test + actif écartés",
         apercu["compteurs"]["test"] == 1 and apercu["compteurs"]["actif"] == 1 and apercu["compteurs"]["destinataires"] == 5, apercu["compteurs"])

# ═══ F. DÉSINSCRIPTION : JETON -> REFUS -> EXCLUSION ══════════════════════════
print("\n[F] le lien de désinscription")
base = base_scenario(); brancher(base)
base.campaigns.docs = [campagne("camp-f1")]
lancer("camp-f1")
tok = next(d["unsubscribe_token"] for d in base.subscribers.docs if d["value"] == "amina@exemple.ch")
lien = next(p["headers"]["List-Unsubscribe"] for p in _FauxEmails.envoyes if p["to"][0] == "amina@exemple.ch")
verifier("F1. le lien de l'e-mail porte exactement le jeton du registre", ("token=%s>" % tok) in lien, lien)
page = run(S.v332_unsubscribe(tok))
verifier("F2. GET/POST /api/subscribers/unsubscribe?token= -> reconnu (page « Désinscription effectuée »)", page.status_code == 200 and "Désinscription effectuée" in page.body.decode("utf-8"))
ligne = next(d for d in base.subscribers.docs if d["value"] == "amina@exemple.ch")
verifier("F3. refus ENREGISTRÉ : status opted_out + opted_out_at", ligne["status"] == "opted_out" and ligne.get("opted_out_at"), ligne)
base.campaigns.docs.append(campagne("camp-f2"))
_FauxEmails.envoyes.clear()
res = lancer("camp-f2")
verifier("F4. campagne suivante : Amina exclue (effet immédiat), 2 envois", len(_FauxEmails.envoyes) == 2
         and any(r["exclu"] == "opt_out" and r["contactEmail"] == "amina@exemple.ch" for r in res["results"] if r["status"] == "skipped"))
verifier("F5. jeton inconnu -> page « Lien invalide », rien n'est écrit", "Lien invalide" in run(S.v332_unsubscribe("n-existe-pas")).body.decode("utf-8")
         and sum(1 for d in base.subscribers.docs if d["status"] == "opted_out") == 1)
verifier("F6. un `opted_out` n'est jamais rétrogradé en `customer` par une campagne ($setOnInsert)", ligne["status"] == "opted_out" and ligne.get("source") == "relation_client")
verifier("F7. /campaigns/send-email (unitaire) refuse un opt-out (403)",
         _refus(S.send_campaign_email, _Req(jeton(), {"to_email": "amina@exemple.ch", "to_name": "Amina", "subject": "x", "message": "y"})) == 403)
verifier("F8. /campaigns/send-email sans jeton -> 403 (jamais un relais ouvert)",
         _refus(S.send_campaign_email, _Req(None, {"to_email": "zoe@exemple.ch", "subject": "x", "message": "y"})) == 403)

# ═══ G. LIEN DE RÉACTIVATION UTM ══════════════════════════════════════════════
print("\n[G] nomenclature UTM")
verifier("G1. lien exact", R.lien_reactivation("essai_non_converti") == "https://afroboost.com/?utm_source=email&utm_medium=reactivation&utm_campaign=hiver2026&utm_content=essai_non_converti")
verifier("G2. segment/campagne nettoyés (jamais d'injection dans l'URL)", R.lien_reactivation("anc ien/abo?x=1", "Hiver 2026!") == "https://afroboost.com/?utm_source=email&utm_medium=reactivation&utm_campaign=hiver2026&utm_content=ancienabox1")
verifier("G3. `email` est une source RECONNUE du tracking 2B (liste fermée partagée)", "email" in SH.M2A_SOURCES)
_att = SH.m2a_attribution_entrante({"utm_source": "email", "utm_medium": "reactivation", "utm_campaign": "hiver2026", "utm_content": "ancien_abonne"}, "", "/")
verifier("G4. l'URL est lue par le tracking : source=email, medium=reactivation, campaign=hiver2026, content=segment",
         _att and _att["source"] == "email" and _att["medium"] == "reactivation" and _att["campaign"] == "hiver2026" and _att["content"] == "ancien_abonne", _att)

# ═══ H. FIRST INSTAGRAM CONSERVÉ, CAMPAGNE EN LAST ════════════════════════════
print("\n[H] first-touch préservé")
class _BaseM2A:
    def __init__(self, docs): self._d = docs
    def __getattr__(self, n): return _Coll(self._d if n in ("subscriptions", "reservations", "users", "payment_transactions", "leads", "chat_participants") else [])
    __getitem__ = __getattr__
_ancien = {"email": "amina@exemple.ch", "attribution": {"first": {"source": "instagram", "medium": "reel", "campaign": "ete2026", "content": "", "term": "", "landing_path": "/", "touch_at": "2026-07-01T10:00:00+00:00"},
                                                          "last": {"source": "instagram", "medium": "reel", "campaign": "ete2026", "content": "", "term": "", "landing_path": "/", "touch_at": "2026-07-01T10:00:00+00:00"}}}
_camp = {"first": {"source": "email", "medium": "reactivation", "campaign": "hiver2026", "content": "essai_non_converti", "term": "", "landing_path": "/", "touch_at": "2026-09-20T10:00:00+00:00"},
         "last": {"source": "email", "medium": "reactivation", "campaign": "hiver2026", "content": "essai_non_converti", "term": "", "landing_path": "/", "touch_at": "2026-09-20T10:00:00+00:00"}}
_res = run(SH.m2a_resoudre(_BaseM2A([_ancien]), _camp, "amina@exemple.ch"))
verifier("H1. first reste Instagram / ete2026", _res["first"]["source"] == "instagram" and _res["first"]["campaign"] == "ete2026", _res)
verifier("H2. last = la campagne de réactivation (email / reactivation / hiver2026 / segment)",
         _res["last"]["source"] == "email" and _res["last"]["campaign"] == "hiver2026" and _res["last"]["content"] == "essai_non_converti", _res)
_achat = {"date_dt": datetime(2026, 9, 21, tzinfo=timezone.utc), "essai": False, "montant": 39.0, "montant_prouve": True, "participant_key": "amina@exemple.ch",
          "attribution_first": ("instagram", "reel", "ete2026", ""), "attribution_last": ("email", "reactivation", "hiver2026", "essai_non_converti")}
verifier("H3. analytics : `attribution_last` extrait la campagne d'un document", A.attribution_last({"attribution": _camp}) == ("email", "reactivation", "hiver2026", "essai_non_converti"), A.attribution_last({"attribution": _camp}))
verifier("H4. le cockpit expose un bloc `campagnes` (dernière touche) à côté des sources (first)",
         "campagnes" in A.calculer_kpi_sources.__code__.co_consts or "lignes_campagnes" in A.calculer_kpi_sources.__code__.co_varnames)

# ═══ I. SÉCURITÉ DES ROUTES (sans jeton -> refus ; coach -> OK ; autre -> refus) ═══
print("\n[I] PUT / DELETE / preview / launch")
base = base_scenario(); brancher(base)
base.campaigns.docs = [campagne()]
verifier("I1. PUT /campaigns/{id} SANS jeton -> 403 (route active = server.py)", _refus(S.update_campaign, "camp1", _Req(None, {"name": "pirate"})) == 403)
verifier("I2. PUT par un AUTRE coach -> 403", _refus(S.update_campaign, "camp1", _Req(jeton("autre@coach.ch"), {"name": "pirate"})) == 403)
maj = run(S.update_campaign("camp1", _Req(jeton(), {"name": "Reprise hiver 2", "targetCategories": ["ancien_abonne"], "coach_id": "pirate@x.ch"})))
verifier("I3. PUT par le propriétaire -> 200, targetCategories accepté, coach_id NON réécrit",
         maj["name"] == "Reprise hiver 2" and maj["targetCategories"] == ["ancien_abonne"] and maj["coach_id"] == ADMIN, maj)
verifier("I4. DELETE sans jeton -> 403", _refus(CR.delete_campaign, "camp1", _Req()) == 403)
verifier("I5. DELETE par un autre coach -> 403", _refus(CR.delete_campaign, "camp1", _Req(jeton("autre@coach.ch"))) == 403)
verifier("I6. DELETE par le propriétaire -> OK", run(CR.delete_campaign("camp1", _Req(jeton())))["success"] is True and len(base.campaigns.docs) == 0)
verifier("I7. purge/all sans jeton -> 403", _refus(CR.purge_all_campaigns, _Req()) == 403)
base.campaigns.docs = [campagne()]
verifier("I8. POST /launch sans jeton -> 403 (V451 inchangé)", _refus(S.v451_lancer_campagne_http, "camp1", _Req()) == 403)
verifier("I9. l'ordre des routeurs : api_router (server.py) est inclus AVANT campaign_router -> le PUT durci est bien celui de server.py",
         [r.path for r in S.fastapi_app.routes if getattr(r, "path", "") == "/api/campaigns/{campaign_id}" and "PUT" in getattr(r, "methods", set())][0] == "/api/campaigns/{campaign_id}"
         and S.update_campaign.__module__ == "api.server")
src_put = io.open(os.path.join(RACINE, "api", "server.py"), encoding="utf-8").read()
verifier("I10. POST /campaigns stocke targetCategories (modèle + création)", "targetCategories=[str(c or" in src_put and 'targetCategories: Optional[List[str]] = []  # RÉACTIVATION 3B' in src_put)

# ═══ J. STRUCTURE : FRONT ET AUTRES CANAUX ═══════════════════════════════════
print("\n[J] front + canaux")
dash = io.open(os.path.join(RACINE, "frontend", "src", "components", "CoachDashboard.js"), encoding="utf-8").read()
_lws = dash[dash.index("const launchCampaignWithSend = async"):dash.index("// Delete campaign")]
verifier("J1. le bouton « Lancer » n'appelle PLUS /campaigns/send-email par destinataire (fin du double envoi)", "send-email" not in _lws and "mark-sent" not in _lws)
verifier("J2. aperçu serveur AVANT le lancement, puis confirmation, puis /launch — dans cet ordre",
         _lws.index("r3ConfirmerAvantLancement") < _lws.index("/launch`") and "window.confirm(" in dash[dash.index("const r3ConfirmerAvantLancement"):dash.index("const launchCampaignWithSend")])
_conf = dash[dash.index("const r3TexteApercu"):dash.index("const r3ConfirmerAvantLancement")]
verifier("J3. la confirmation montre : segment, destinataires, exclus, canal, campagne UTM, aperçu du message",
         all(x in _conf for x in ("Segment(s)", "Destinataires e-mail", "Exclus automatiquement", "Canal", "Campagne (UTM)", "Aperçu du message")))
verifier("J4. mode immédiat : confirmation aussi avant l'auto-lancement e-mail/WhatsApp", "r3ConfirmerAvantLancement(res.data.id" in dash)
verifier("J5. targetCategories transmis à la création (immédiate + programmée), à la modification et à la duplication",
         dash.count("targetCategories: r3SegmentsChoisis()") == 3
         and "targetCategories: Array.isArray(campaign.targetCategories)" in io.open(os.path.join(RACINE, "frontend", "src", "components", "coach", "CampaignManager.js"), encoding="utf-8").read())
modal = io.open(os.path.join(RACINE, "frontend", "src", "components", "coach", "CampaignModal.js"), encoding="utf-8").read()
verifier("J6. la modale propose les 6 segments de réactivation (clés identiques au serveur)",
         all(("cle: '%s'" % k) in modal for k in R.SEGMENTS_REACTIVATION) and "targetCategories" in modal)
verifier("J7. « présence inconnue » documentée comme N'ÉTANT PAS un no-show (serveur + modale)", "PAS un no-show" in modal and "JAMAIS un no-show" in io.open(os.path.join(RACINE, "api", "routes", "reactivation.py"), encoding="utf-8").read())
_bc = src_put[src_put.index('@api_router.post("/push/broadcast")'):src_put.index('@api_router.post("/push/broadcast")') + 4000]
verifier("J8. push/broadcast lit le registre (c3_refus_exprimes) et saute les refus", "c3_refus_exprimes(\"email\"" in _bc and "_r3_exclus" in _bc)
_wh = src_put[src_put.index('@api_router.post("/webhooks/resend")'):src_put.index('@api_router.post("/webhooks/resend")') + 6000]
verifier("J9. le webhook Resend écrit delivered/bounced/complained dans le journal de campagne", "results.$.provider_status" in _wh and '"bounced", "complained"' in _wh)
# … et il le fait vraiment : un `email.bounced` sur un email_id du journal marque la ligne.
base = base_scenario(); brancher(base)
base.campaigns.docs = [campagne("camp-wh")]
lancer("camp-wh")
_eid = next(r["email_id"] for r in base.campaigns.docs[0]["results"] if r["status"] == "sent")
import json as _json
class _ReqBrute:
    headers = {}
    async def body(self): return _json.dumps({"type": "email.bounced", "data": {"email_id": _eid}}).encode()
_sig = S.p3u3_signature_valide
S.p3u3_signature_valide = lambda corps, entetes: {"ok": True, "motif": ""}   # la signature est testée par P3-U3, pas ici
try:
    run(S.p3u3_webhook_resend(_ReqBrute()))
finally:
    S.p3u3_signature_valide = _sig
verifier("J9b. `email.bounced` -> results[].provider_status = bounced sur la bonne ligne (les autres intactes)",
         [r.get("provider_status") for r in base.campaigns.docs[0]["results"]].count("bounced") == 1
         and next(r for r in base.campaigns.docs[0]["results"] if r.get("email_id") == _eid)["provider_status"] == "bounced", base.campaigns.docs[0]["results"])
cock = io.open(os.path.join(RACINE, "frontend", "src", "components", "analytics", "AnalyticsCockpit.js"), encoding="utf-8").read()
verifier("J10. le cockpit affiche le bloc « Campagnes — dernière touche »", "tableau-campagnes" in cock and "sources.campagnes" in cock)

# ═══ K. PUSH : le registre est HONORABLE (aucun envoi) ════════════════════════
print("\n[K] push")
base = _Base(); brancher(base)
base.push_subscriptions.docs = [{"participant_id": "p1", "email": "amina@exemple.ch", "active": True}, {"participant_id": "p2", "active": True}]
base.chat_participants.docs = [{"id": "p2", "email": "bruno@exemple.ch"}]
base.subscribers.docs = [{"channel": "email", "value": "bruno@exemple.ch", "status": "opted_out"}]
verifier("K1. broadcast sans identité super-admin -> 403 (rien n'est envoyé)",
         _refus(S.push_broadcast, _Req(None, {"title": "t", "body": "b"})) == 403)
# Le registre est HONORABLE : la résolution des refus (fiche push -> e-mail -> registre) donne le bon ensemble.
async def _resoudre_refus_push():
    subs = await base.push_subscriptions.find({"active": True}, {"_id": 0, "participant_id": 1, "email": 1}).to_list(2000)
    pids = [x.get("participant_id") for x in subs]
    fiches = await base.chat_participants.find({"id": {"$in": pids}}, {"_id": 0, "id": 1, "email": 1}).to_list(5000)
    par_pid = {f["id"]: S._v332_normaliser("email", f.get("email") or "") for f in fiches}
    for x in subs:
        if x.get("email"):
            par_pid[x["participant_id"]] = S._v332_normaliser("email", x["email"])
    refus = await S.c3_refus_exprimes("email", list(par_pid.values()))
    return {pid for pid, m in par_pid.items() if m in refus}
verifier("K2. registre honorable : p2 (bruno, opt-out via sa fiche CRM) exclu, p1 servi — aucun push émis", run(_resoudre_refus_push()) == {"p2"})

print("\n%d/%d au vert" % (OK, OK + RATE))
sys.exit(0 if RATE == 0 else 1)

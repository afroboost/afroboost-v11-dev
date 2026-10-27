# -*- coding: utf-8 -*-
"""V608 — LE POINT D'ENVOI RESEND UNIQUE DU PROJET.

Tous les modules envoient par ici (plus aucun `resend.Emails.send` ailleurs) :

    import api.resend_central as _rc
    await asyncio.to_thread(_rc.emails("module:fonction", critique=False).send, params)

`.send(params, options=None)` a EXACTEMENT l'interface et la valeur de retour du SDK
Resend : destinataires, objets, gabarits, pièces jointes, Reply-To et clés
d'idempotence passent tels quels. Ce module n'ajoute que trois choses :

1. QUOTA DU COMPTE RESEND (global, tous modules), réservé ATOMIQUEMENT AVANT l'appel :
   - fenêtre = JOUR UTC en cours (V608b : Resend remet sa limite journalière à zéro
     chaque jour civil, constaté le 12/10) ;
   - non critique : bloqué à RESEND_DAILY_SAFETY_LIMIT (95 par défaut) ;
   - critique (OTP, accès, paiement, réservation) : réserve jusqu'à RESEND_DAILY_LIMIT
     (100) ; au-delà, TOUT est bloqué ;
   - la réservation est UNE écriture conditionnelle MongoDB (`find_one_and_update` avec
     `$expr` sur la taille de la fenêtre) : deux demandes simultanées pour une seule
     place → une seule passe. Jamais « lire 94 puis écrire ».
   - une tentative SOUMISE au fournisseur reste comptée même si Resend échoue ensuite
     (on ne sait pas toujours si elle a consommé du quota) : la place n'est jamais
     rendue. Un blocage AVANT l'appel ne consomme rien.
   - le compte Resend peut être utilisé ailleurs : `reconcilier_avec_resend()` lit
     l'historique du compte et pose un PLANCHER (valable 30 min) ; le compteur
     effectif est max(local, plancher) — le fournisseur peut le faire monter, jamais
     baisser.
2. JOURNAL CENTRAL `resend_envois` : une ligne par tentative (source, type, destinataire,
   dates, provider_status, identifiant Resend, raison). Aucun contenu d'e-mail, aucune clé.
3. UNE ADRESSE DE REPONSE PAR DEFAUT (V632) : un e-mail transactionnel (reservation,
   bienvenue, code de verification...) qui n'en fixe pas recoit `Reply-To:
   contact@afroboosteur.com`. Sans elle, le client voyait `notifications@afroboost.com`
   — une adresse qui n'a longtemps eu AUCUN MX — et sa reponse etait perdue. Un
   `reply_to` fixe par l'appelant n'est JAMAIS modifie (c'est le cas de la prospection :
   `r-<jeton>@reply.afroboosteur.com`).
4. Rien d'autre : aucune nouvelle tentative automatique, aucun changement de contenu.
"""
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("api.resend_central")

COL_QUOTA = "resend_quota"
COL_JOURNAL = "resend_envois"
DOC_QUOTA = "compte"
PLANCHER_VALIDITE = timedelta(minutes=30)


def debut_fenetre(now: datetime) -> datetime:
    """V608b : la limite journalière Resend se remet à ZÉRO chaque jour civil (constaté au
    tableau de bord le 12/10 : « Daily 0 / 100 » à 05:23 UTC après 174 envois la veille).
    La fenêtre est donc le jour UTC en cours, PAS 24 h glissantes."""
    return now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _expiration_plancher(now: datetime) -> datetime:
    """Un plancher lu avant minuit ne survit jamais au changement de jour."""
    return min(now + PLANCHER_VALIDITE, debut_fenetre(now) + timedelta(days=1))


DOC_REGLAGES = "reglages"
LIMITE_MAX = 1000000


def _defauts() -> dict:
    """Valeurs INITIALES seulement (variables d'environnement, sinon 100 / 95).
    Le coach les remplace depuis le dashboard ; elles ne sont pas des règles métier."""
    def _int(nom, defaut):
        try:
            return max(0, int(os.environ.get(nom) or defaut))
        except (TypeError, ValueError):
            return defaut
    limite = _int("RESEND_DAILY_LIMIT", 100)
    return {"actif": True, "limite": limite, "seuil": min(_int("RESEND_DAILY_SAFETY_LIMIT", 95), limite)}


def reglages() -> dict:
    """LA source du réglage « Limiter les envois Resend » : en BASE (persistant après
    redémarrage / déploiement), modifiable sans code. Base illisible → valeurs initiales."""
    d = _defauts()
    try:
        doc = _db()[COL_QUOTA].find_one({"_id": DOC_REGLAGES}) or {}
    except Exception as e:  # noqa: BLE001
        logger.warning("[RESEND] réglages illisibles (%s) — valeurs initiales", type(e).__name__)
        return dict(d, source="defaut")
    if not doc:
        return dict(d, source="defaut")
    return {"actif": bool(doc.get("actif", True)), "limite": int(doc.get("limite", d["limite"])),
            "seuil": int(doc.get("seuil", d["seuil"])), "modifie_le": doc.get("modifie_le"),
            "modifie_par": doc.get("modifie_par"), "source": "base"}


def enregistrer_reglages(actif, limite, seuil, par: str = "") -> dict:
    """Valide et PERSISTE le réglage. Lève ValueError sur une valeur incohérente."""
    if not isinstance(actif, bool):
        raise ValueError("actif doit être vrai ou faux")
    try:
        limite, seuil = int(limite), int(seuil)
    except (TypeError, ValueError):
        raise ValueError("limite et seuil doivent être des nombres entiers")
    if not (1 <= limite <= LIMITE_MAX):
        raise ValueError("limite entre 1 et %d" % LIMITE_MAX)
    if not (0 <= seuil <= limite):
        raise ValueError("le seuil doit être compris entre 0 et la limite")
    _db()[COL_QUOTA].update_one({"_id": DOC_REGLAGES}, {"$set": {
        "actif": actif, "limite": limite, "seuil": seuil,
        "modifie_le": _maintenant().isoformat(), "modifie_par": (par or "")[:120]}}, upsert=True)
    return reglages()


def limites() -> dict:
    """Limite et seuil EN VIGUEUR (lus dans le réglage)."""
    r = reglages()
    return {"limite": r["limite"], "seuil": r["seuil"], "actif": r["actif"]}


class QuotaResendAtteint(Exception):
    """Envoi BLOQUÉ AVANT Resend : rien n'est parti, rien n'est consommé."""
    code = "QUOTA_RESEND"
    status_code = 429

    def __init__(self, compte: int, plafond: int, critique: bool):
        self.compte, self.plafond, self.critique = compte, plafond, critique
        self.message = "Non envoyé — quota Resend atteint (%d/%d aujourd'hui)" % (compte, plafond)
        super().__init__(self.message)


_base = None
_transport = None
_actif = False
_verrou = threading.Lock()


def activer() -> None:
    """Appelé au DÉMARRAGE du serveur (production) : quota + journal actifs.
    Tant que le serveur n'a pas démarré (bancs qui importent le module sans le lancer),
    le point d'envoi transmet tel quel — exactement le comportement d'avant V608."""
    global _actif
    _actif = True


def configurer(base=None, transport=None) -> None:
    """Bancs V608 : base MongoDB synchrone (pymongo) et faux fournisseur ; active le garde-fou."""
    global _base, _transport, _actif
    _base, _transport, _actif = base, transport, True


def _db():
    global _base
    if _base is None:
        with _verrou:
            if _base is None:
                from pymongo import MongoClient
                client = MongoClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=8000,
                                     maxPoolSize=3)
                _base = client[os.environ.get("DB_NAME", "afroboost_db")]
    return _base


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- quota
# COMPTE EFFECTIF = max( tentatives locales de la fenêtre ,
#                        plancher lu chez Resend + tentatives locales POSTÉRIEURES à sa lecture )
# Le plancher (tout le compte, tous services) AVANCE avec nos envois suivants ; il ne
# fait jamais baisser le compte local.
_EXPR_COMPTE = {"$max": [
    {"$size": "$tentatives"},
    {"$add": [{"$ifNull": ["$plancher", 0]},
              {"$size": {"$filter": {"input": "$tentatives", "as": "t",
                                     "cond": {"$gt": ["$$t", {"$ifNull": ["$plancher_lu_at", "9999"]}]}}}}]}]}


def compte_effectif(doc: dict) -> int:
    """Même calcul que `_EXPR_COMPTE`, côté Python (affichage, message d'erreur). PURE."""
    t = doc.get("tentatives") or []
    lu = doc.get("plancher_lu_at") or "9999"
    return max(len(t), int(doc.get("plancher") or 0) + len([x for x in t if x > lu]))


def reserver(critique: bool, maintenant: datetime = None) -> dict:
    """Réserve UNE place dans la fenêtre glissante. ATOMIQUE. Lève QuotaResendAtteint."""
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError
    now = maintenant or _maintenant()
    lim = limites()
    plafond = lim["limite"] if critique else lim["seuil"]
    col = _db()[COL_QUOTA]
    if not lim["actif"]:
        # GARDE-FOU AFROBOOST = OFF : on COMPTE (affichage, diagnostic), on ne bloque RIEN.
        # Les limites du compte Resend restent applicables : une erreur Resend reste une erreur.
        col.update_one({"_id": DOC_QUOTA}, {"$pull": {"tentatives": {"$lt": debut_fenetre(now).isoformat()}}})
        doc = col.find_one_and_update({"_id": DOC_QUOTA}, {"$push": {"tentatives": now.isoformat()},
                                                          "$setOnInsert": {"plancher": 0}},
                                      upsert=True, return_document=ReturnDocument.AFTER)
        return {"compte": compte_effectif(doc), "plafond": None, "limitation": False}
    try:
        col.update_one({"_id": DOC_QUOTA},
                       {"$setOnInsert": {"tentatives": [], "plancher": 0, "plancher_expire_at": ""}},
                       upsert=True)
    except DuplicateKeyError:
        pass
    # Ménage (idempotent) : les tentatives sorties de la fenêtre, le plancher périmé.
    col.update_one({"_id": DOC_QUOTA}, {"$pull": {"tentatives": {"$lt": debut_fenetre(now).isoformat()}}})
    col.update_one({"_id": DOC_QUOTA, "plancher_expire_at": {"$lt": now.isoformat()}},
                   {"$set": {"plancher": 0, "plancher_lu_at": None}})
    doc = col.find_one_and_update(
        {"_id": DOC_QUOTA, "$expr": {"$lt": [_EXPR_COMPTE, plafond]}},
        {"$push": {"tentatives": now.isoformat()}},
        return_document=ReturnDocument.AFTER)
    if doc is None:
        raise QuotaResendAtteint(compte_effectif(col.find_one({"_id": DOC_QUOTA}) or {}), plafond, critique)
    return {"compte": compte_effectif(doc), "plafond": plafond}


def etat(maintenant: datetime = None) -> dict:
    """Lecture seule : compteurs, plancher fournisseur, blocages et diagnostic de capacité."""
    now = maintenant or _maintenant()
    base = _db()
    doc = base[COL_QUOTA].find_one({"_id": DOC_QUOTA}) or {}
    debut = debut_fenetre(now).isoformat()
    fen = [t for t in (doc.get("tentatives") or []) if t >= debut]
    valide = (doc.get("plancher_expire_at") or "") >= now.isoformat()
    plancher = int(doc.get("plancher") or 0) if valide else 0
    effectif = compte_effectif({"tentatives": fen, "plancher": plancher,
                                "plancher_lu_at": doc.get("plancher_lu_at") if valide else None})
    bloques = base[COL_JOURNAL].count_documents({"provider_status": "bloque_quota", "prepare_at": {"$gte": debut}})
    lim = limites()
    demande = effectif + bloques
    reg = reglages()
    return {"reglages": reg, "restants_avant_seuil": max(0, lim["seuil"] - effectif),
            "restants_avant_limite": max(0, lim["limite"] - effectif),
            "fenetre": "jour UTC (remise à zéro à minuit UTC)", "local_24h": len(fen), "plancher_resend": plancher,
            "plancher_lu_at": doc.get("plancher_lu_at"), "compte_effectif": effectif,
            "bloques_24h": bloques, "demande_24h": demande, **lim,
            "plan_insuffisant": demande > lim["limite"]}


def reconcilier_avec_resend(maintenant: datetime = None, lister=None) -> dict:
    """Pose le PLANCHER = e-mails du COMPTE Resend depuis minuit UTC (tous
    services). Ne fait que relever le compteur effectif. `lister(after)` pour les tests."""
    import json
    import urllib.request
    now = maintenant or _maintenant()
    debut = debut_fenetre(now)

    def _lister(apres):
        url = "https://api.resend.com/emails?limit=100" + (("&after=" + apres) if apres else "")
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + os.environ.get("RESEND_API_KEY", ""),
            "User-Agent": "Afroboost/1.0"})
        return json.load(urllib.request.urlopen(req, timeout=15))

    lire = lister or _lister
    total, apres = 0, None
    for _ in range(20):                         # au plus 2 000 e-mails lus : borne explicite
        page = lire(apres) or {}
        lot = page.get("data") or []
        complet = False
        for e in lot:
            brut = str(e.get("created_at") or "").replace(" ", "T")
            if brut.endswith("+00"):
                brut += ":00"
            try:
                cree = datetime.fromisoformat(brut)
            except ValueError:
                continue
            if cree.tzinfo is None:
                cree = cree.replace(tzinfo=timezone.utc)
            if cree < debut:
                complet = True
                break
            total += 1
        if complet or not page.get("has_more") or not lot:
            break
        apres = lot[-1].get("id")
    _db()[COL_QUOTA].update_one(
        {"_id": DOC_QUOTA},
        {"$set": {"plancher": total, "plancher_lu_at": now.isoformat(),
                  "plancher_expire_at": _expiration_plancher(now).isoformat()},
         "$setOnInsert": {"tentatives": []}}, upsert=True)
    return {"plancher": total, "lu_at": now.isoformat()}


# --------------------------------------------------------------------------- journal
def _journal(op, *args, **kwargs):
    """Le journal ne doit JAMAIS empêcher un envoi : toute panne est seulement loguée."""
    try:
        return getattr(_db()[COL_JOURNAL], op)(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        logger.warning("[RESEND] journal indisponible (%s)", type(e).__name__)
        return None


def _destinataire(params) -> str:
    to = (params or {}).get("to")
    if isinstance(to, (list, tuple)):
        to = to[0] if to else ""
    return str(to or "")[:200]


# V632 — L'ADRESSE DE REPONSE PAR DEFAUT.
# MEME VALEUR QUE `AFROBOOST_REPLY_TO_CANONIQUE` (api/server.py) : ce module ne peut pas
# importer le serveur (import circulaire), la parite est donc VERIFIEE PAR UN BANC
# (tests/test_v632_reply_to_transactionnel.py) plutot que supposee.
REPLY_TO_DEFAUT = "contact@afroboosteur.com"
# Adresses mortes : domaine sans MX. Meme regle que cote serveur — une variable
# d'environnement ne peut pas les remettre.
REPLY_TO_MORTES = ("contact@afroboost.ch",)


def reply_to_defaut() -> str:
    """L'adresse de reponse des e-mails qui n'en fixent pas. Surchargeable (AFROBOOST_REPLY_TO),
    sauf pour une adresse morte, qui rend toujours la canonique."""
    valeur = (os.environ.get("AFROBOOST_REPLY_TO") or "").strip()
    if not valeur or valeur.lower() in REPLY_TO_MORTES:
        return REPLY_TO_DEFAUT
    return valeur


def _avec_reply_to(params):
    """`params` avec une adresse de reponse, SANS jamais ecraser celle de l'appelant.

    Un `reply_to` absent, nul, vide ou une liste vide recoit la valeur par defaut. Tout
    `reply_to` renseigne (chaine ou liste) passe tel quel. Le dictionnaire de l'appelant
    n'est pas modifie : on rend une copie.
    """
    if not isinstance(params, dict):
        return params
    actuel = params.get("reply_to")
    if isinstance(actuel, (list, tuple)):
        renseigne = any(str(x or "").strip() for x in actuel)
    else:
        renseigne = bool(str(actuel or "").strip())
    if renseigne:
        return params
    return dict(params, reply_to=reply_to_defaut())


class _Emails:
    def __init__(self, source: str, type_email: str, critique: bool, reference, sdk=None):
        self.source, self.type_email, self.critique, self.reference = source, type_email, critique, reference
        self.sdk = sdk   # l'objet `resend` QUE L'APPELANT UTILISAIT (résolution identique à avant V608)

    def _appeler(self, params, options):
        if self.sdk is None:
            import resend as _sdk
        else:
            _sdk = self.sdk
        return _sdk.Emails.send(params, options) if options is not None else _sdk.Emails.send(params)

    def send(self, params, options=None):
        """Même signature et même valeur de retour que `resend.Emails.send`."""
        params = _avec_reply_to(params)   # V632 : adresse de reponse par defaut, jamais imposee
        if not _actif:
            return self._appeler(params, options)
        jid = str(uuid.uuid4())
        now = _maintenant().isoformat()
        _journal("insert_one", {
            "id": jid, "resend_id": None, "source": self.source, "type_email": self.type_email,
            "critique": self.critique, "destinataire": _destinataire(params),
            "reference": self.reference, "prepare_at": now, "soumis_at": None,
            "provider_status": "prepare", "raison": None, "evenements": []})
        try:
            reserver(self.critique)
        except QuotaResendAtteint as q:
            _journal("update_one", {"id": jid}, {"$set": {
                "provider_status": "bloque_quota", "raison": q.message}})
            logger.warning("[RESEND] %s — %s (%s, critique=%s). Si cela se répète : PLAN RESEND INSUFFISANT.",
                           q.message, self.source, self.type_email, self.critique)
            raise
        except Exception as e:  # noqa: BLE001
            # Quota illisible (base injoignable) : un e-mail critique passe, le reste attend.
            logger.warning("[RESEND] quota illisible (%s) — critique=%s", type(e).__name__, self.critique)
            if not self.critique:
                _journal("update_one", {"id": jid}, {"$set": {
                    "provider_status": "bloque_quota", "raison": "quota illisible"}})
                raise QuotaResendAtteint(-1, -1, False)
        soumis = _maintenant().isoformat()
        try:
            if _transport is not None:
                brut = _transport(params, options)
            else:
                brut = self._appeler(params, options)
        except Exception as e:  # noqa: BLE001
            _journal("update_one", {"id": jid}, {"$set": {
                "provider_status": "erreur_envoi", "soumis_at": soumis,
                "raison": ("%s: %s" % (type(e).__name__, getattr(e, "message", None) or e))[:300]}})
            raise
        rid = brut.get("id") if isinstance(brut, dict) else getattr(brut, "id", None)
        _journal("update_one", {"id": jid}, {"$set": {
            "resend_id": rid, "soumis_at": soumis,
            "provider_status": "accepted" if rid else "sans_identifiant"}})
        return brut


def emails(source: str, critique: bool = False, type_email: str = None, reference=None, sdk=None) -> _Emails:
    """`emails("module:fonction", critique=…, sdk=resend).send(params[, options])` — remplace `resend.Emails`."""
    return _Emails(source, type_email or source, bool(critique), reference, sdk)

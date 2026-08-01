# contact_segments_routes.py — V363 : segments de contacts CALCULÉS
#
# POURQUOI CALCULÉS ET NON STOCKÉS
# --------------------------------
# Le groupe « Contacts WhatsApp » a été figé le 28 avril 2026 : il compte 210 membres
# alors que 301 personnes sont aujourd'hui joignables. Un groupe matérialisé vieillit
# dès le lendemain. Ici, RIEN n'est écrit sur les fiches : chaque appel recalcule les
# segments à partir des champs déjà présents (numéro, e-mail, abonnements, source).
# Un contact créé dans une minute est donc classé correctement à la lecture suivante,
# sans automate de fond — ce déploiement n'en a aucun de fiable (cf. V328).
#
# CE MODULE N'ÉCRIT JAMAIS EN BASE. Uniquement find / count_documents.
# Il ne touche ni au chemin d'envoi des campagnes, ni aux campagnes, ni aux groupes.
#
# Les règles sont lues dans le document `contact_segments_config` (V363) ; s'il est
# absent (rollback), on retombe sur LES MÊMES valeurs par défaut ci-dessous : supprimer
# le document ne casse donc rien, il sert à ajuster les règles sans redéployer.
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

segments_router = APIRouter(tags=["contact-segments"])

db = None


def init_segments_db(database):
    global db
    db = database


# --- Valeurs par défaut = copie conforme du document contact_segments_config ---
CONFIG_DEFAUT = {
    "numeros_internes": ["765203363"],
    "emails_internes": [],
    "regles": {
        "telephone": {"champs_lus": ["whatsapp", "phone"], "longueur_min": 9, "longueur_max": 15},
        "email": {"motif": r"^[^@\s]+@[^@\s.]+\.[a-z]{2,}$"},
        "deduplication": {
            "collections_lues": ["chat_participants", "users", "leads", "subscriber_infos"]
        },
        "abonnement": {
            "date_prime_sur_statut": True,
            "sans_date_expiration": "actif_a_verifier",
            "zero_seance_restante": "expire",
        },
        "essai_gratuit": {"sources": ["free_checkout"]},
    },
}

SEGMENTS_CONNUS = [
    "whatsapp", "email", "abonne_actif", "essai_gratuit", "abonnement_expire",
    "visiteur", "demarchable_whatsapp", "comptes_app", "a_completer", "interne_test",
]

# Ordre de préférence de l'identifiant renvoyé : le CRM d'abord, car c'est celui que
# `launch_campaign` résout en premier pour retrouver un numéro.
PRIORITE_COLLECTION = {"chat_participants": 0, "users": 1, "leads": 2, "subscriber_infos": 3}


def _coach_email_depuis_jwt(request: Request) -> str:
    """Email issu d'un JWT coach SIGNÉ uniquement — jamais X-User-Email (falsifiable).
    Rejette les jetons abonné. Même mécanisme que _v311_coach_email_from_jwt (V311h) ;
    dupliqué ici car un module de routes ne peut pas importer server.py (circularité)."""
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return ""
    auth = request.headers.get("Authorization", "") or ""
    if not auth.lower().startswith("bearer "):
        return ""
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return ""
    try:
        import jwt as _pyjwt
        payload = _pyjwt.decode(token, secret, algorithms=["HS256"])
    except Exception:
        return ""
    if (payload.get("type") or "") == "subscriber":
        return ""
    return (payload.get("email") or "").strip().lower()


async def _autorise(request: Request) -> str:
    """403 sauf coach/admin prouvé par jeton signé. Ces routes exposent des
    identifiants de contacts : la règle « aucune donnée personnelle sans
    authentification » s'applique intégralement."""
    email = _coach_email_depuis_jwt(request)
    if not email:
        logger.warning("[SEGMENTS] Refus — aucun jeton coach signé")
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    if not await _est_coach_ou_admin(email):
        logger.warning("[SEGMENTS] Refus — jeton valide mais ni coach ni admin")
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    return email


async def _est_coach_ou_admin(email: str) -> bool:
    email = (email or "").lower().strip()
    if not email:
        return False
    if email == "contact.artboost@gmail.com":
        return True
    if await db.coaches.find_one({"email": email}, {"_id": 1}):
        return True
    if await db.coach_auth.find_one({"email": email}, {"_id": 1}):
        return True
    return False


async def _config() -> dict:
    """Règles depuis la base, sinon valeurs par défaut identiques (rollback sans effet)."""
    try:
        doc = await db.contact_segments_config.find_one(
            {"id": "contact_segments_config"}, {"_id": 0})
    except Exception:
        doc = None
    return doc or CONFIG_DEFAUT


def _normalise_tel(brut, cfg):
    """Clé de déduplication d'un numéro : les 9 derniers chiffres du format E.164.
    Utilise format_phone_e164 du chemin d'envoi pour que « numéro exploitable » ici
    veuille dire exactement « numéro auquel une campagne saurait écrire »."""
    if not isinstance(brut, str) or not brut.strip():
        return None
    try:
        from api.server import format_phone_e164  # import différé : évite la circularité
        e164 = format_phone_e164(brut.strip())
    except Exception:
        e164 = brut.strip()
    chiffres = re.sub(r"\D", "", e164 or "")
    regle = cfg.get("regles", {}).get("telephone", {})
    mini = regle.get("longueur_min", 9)
    maxi = regle.get("longueur_max", 15)
    if mini <= len(chiffres) <= maxi and set(chiffres) != {"0"}:
        return chiffres[-9:]
    return None


def _normalise_email(brut, cfg):
    if not isinstance(brut, str):
        return None
    e = brut.strip().lower()
    motif = cfg.get("regles", {}).get("email", {}).get("motif", CONFIG_DEFAUT["regles"]["email"]["motif"])
    return e if re.match(motif, e, re.I) else None


def _etat_abonnement(abos, cfg):
    """-> ('actif' | 'expire' | None, sans_date_a_verifier). Trois arbitrages :
    la date prime sur le statut ; 0 séance restante = expiré ; pas de date = actif signalé."""
    regle = cfg.get("regles", {}).get("abonnement", {})
    maintenant = datetime.now(timezone.utc)
    resultat, sans_date = None, False
    for s in abos:
        exp = s.get("expires_at")
        passee = False
        if exp:
            try:
                dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                passee = dt <= maintenant
            except Exception:
                passee = False
        restantes = s.get("remaining_sessions")
        if s.get("status") != "active":
            resultat = resultat or "expire"
            continue
        if passee and regle.get("date_prime_sur_statut", True):
            resultat = resultat or "expire"
            continue
        if restantes is not None and restantes <= 0 and regle.get("zero_seance_restante") == "expire":
            resultat = resultat or "expire"
            continue
        if not exp:
            sans_date = True
        return "actif", sans_date
    return resultat, sans_date


async def _calcule_personnes():
    """Lit les collections de contacts, fusionne en personnes, étiquette. LECTURE SEULE.
    Renvoie (liste_de_personnes, config)."""
    cfg = await _config()
    internes = set(cfg.get("numeros_internes") or [])
    sources_essai = set(cfg.get("regles", {}).get("essai_gratuit", {}).get("sources") or [])
    collections = (cfg.get("regles", {}).get("deduplication", {}).get("collections_lues")
                   or CONFIG_DEFAUT["regles"]["deduplication"]["collections_lues"])

    enregistrements = []
    for nom in collections:
        projection = {"_id": 0, "id": 1, "name": 1, "email": 1, "whatsapp": 1,
                      "phone": 1, "source": 1, "code": 1, "subscriptionCode": 1}
        for d in await db[nom].find({}, projection).to_list(20000):
            brut = d.get("whatsapp") or d.get("phone") or ""
            enregistrements.append({
                "coll": nom,
                "id": d.get("id") or "",
                "tel": _normalise_tel(brut, cfg),
                "mail": _normalise_email(d.get("email"), cfg),
                "source": str(d.get("source") or ""),
                "code": str(d.get("subscriptionCode") or d.get("code") or "").strip().upper(),
            })

    # « Interne / test » : critère STRICT — la fiche porte réellement le numéro interne.
    # Retiré AVANT la fusion : les e-mails de test agrégeraient sinon, par transitivité,
    # des personnes qui n'en sont pas (3 cas constatés le 1er août 2026).
    internes_recs = [r for r in enregistrements if r["tel"] in internes]
    enregistrements = [r for r in enregistrements if r["tel"] not in internes]

    # Fusion par numéro puis e-mail (union-find)
    parent = {}

    def trouve(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def unis(a, b):
        ra, rb = trouve(a), trouve(b)
        if ra != rb:
            parent[ra] = rb

    for i, r in enumerate(enregistrements):
        trouve(f"r{i}")
        if r["tel"]:
            unis(f"r{i}", f"t:{r['tel']}")
        if r["mail"]:
            unis(f"r{i}", f"m:{r['mail']}")
    groupes = {}
    for i, r in enumerate(enregistrements):
        groupes.setdefault(trouve(f"r{i}"), []).append(r)

    # Abonnements, rattachés par e-mail et par code
    abo_mail, abo_code = {}, {}
    for s in await db.subscriptions.find({}, {"_id": 0}).to_list(20000):
        m = _normalise_email(s.get("email"), cfg)
        if m:
            abo_mail.setdefault(m, []).append(s)
        if s.get("code"):
            abo_code.setdefault(str(s["code"]).strip().upper(), []).append(s)

    personnes = []
    for _, recs in groupes.items():
        tel_ok = any(r["tel"] for r in recs)
        mail_ok = any(r["mail"] for r in recs)
        abos = []
        for r in recs:
            if r["mail"]:
                abos += abo_mail.get(r["mail"], [])
            if r["code"]:
                abos += abo_code.get(r["code"], [])
        etat, sans_date = _etat_abonnement(abos, cfg)
        essai = any(r["source"] in sources_essai for r in recs)

        etiquettes = set()
        if tel_ok:
            etiquettes.add("whatsapp")
            etiquettes.add("demarchable_whatsapp")
        if mail_ok:
            etiquettes.add("email")
        if etat == "actif":
            etiquettes.add("abonne_actif")
        if etat == "expire":
            etiquettes.add("abonnement_expire")
        if essai:
            etiquettes.add("essai_gratuit")
        if not etiquettes & {"abonne_actif", "abonnement_expire", "essai_gratuit"}:
            etiquettes.add("visiteur")
        if not tel_ok and mail_ok:
            etiquettes.add("comptes_app")
        if not tel_ok and not mail_ok:
            etiquettes.add("a_completer")

        principal = sorted(
            [r for r in recs if r["id"]],
            key=lambda r: PRIORITE_COLLECTION.get(r["coll"], 9))
        personnes.append({
            "id": principal[0]["id"] if principal else "",
            "collection": principal[0]["coll"] if principal else "",
            "etiquettes": sorted(etiquettes),
            "abonnement_sans_date": sans_date,
        })

    if internes_recs:
        principal = sorted(internes_recs, key=lambda r: PRIORITE_COLLECTION.get(r["coll"], 9))
        personnes.append({
            "id": principal[0]["id"],
            "collection": principal[0]["coll"],
            "etiquettes": ["interne_test"],
            "abonnement_sans_date": False,
            "fiches": len(internes_recs),
        })
    return personnes, cfg


@segments_router.get("/contacts/segments")
async def compter_segments(request: Request):
    """V363 — comptes par segment, recalculés à l'instant. LECTURE SEULE.
    Ne renvoie AUCUNE donnée personnelle : uniquement des nombres."""
    await _autorise(request)
    personnes, cfg = await _calcule_personnes()

    comptes = {cle: 0 for cle in SEGMENTS_CONNUS}
    for p in personnes:
        for e in p["etiquettes"]:
            if e in comptes:
                comptes[e] += 1

    # Groupes d'usage : exclusifs, ce sont eux qui pilotent les campagnes.
    groupes_usage = {
        "demarchable_whatsapp": comptes["demarchable_whatsapp"],
        "comptes_app": comptes["comptes_app"],
        "a_completer": comptes["a_completer"],
        "interne_test": comptes["interne_test"],
    }
    return {
        "success": True,
        "version": cfg.get("version", "V363 (valeurs par défaut)"),
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "personnes": len(personnes),
        "etiquettes": comptes,
        "groupes_usage": groupes_usage,
        "total_groupes_usage": sum(groupes_usage.values()),
        "abonnes_actifs_sans_date": sum(1 for p in personnes if p.get("abonnement_sans_date")),
    }


@segments_router.get("/contacts/segment/{cle}")
async def lister_segment(cle: str, request: Request, limite: int = 5000):
    """V363 — identifiants des personnes d'un segment, recalculés à l'instant.
    LECTURE SEULE. Renvoie des identifiants, jamais de numéros ni d'e-mails :
    l'appelant croise avec /contacts/all s'il a besoin des noms."""
    await _autorise(request)
    if cle not in SEGMENTS_CONNUS:
        raise HTTPException(status_code=404, detail=f"Segment inconnu : {cle}")
    personnes, cfg = await _calcule_personnes()
    retenues = [p for p in personnes if cle in p["etiquettes"] and p["id"]]
    tronque = len(retenues) > limite
    return {
        "success": True,
        "segment": cle,
        "total": len(retenues),
        "tronque": tronque,          # jamais de troncature silencieuse
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "contacts": [{"id": p["id"], "collection": p["collection"]} for p in retenues[:limite]],
    }

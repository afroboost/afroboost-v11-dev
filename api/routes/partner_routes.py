# api/routes/partner_routes.py — V633 Suivi partenaires
# Vue coach : rapport détaillé par code promo.
# Vue partenaire : page sécurisée en lecture seule.
# AUCUNE écriture sur payment_transactions, reservations, discount_codes.

import hashlib
import re
import secrets
import logging
import os
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.routes.shared import coach_jwt_email, is_super_admin

logger = logging.getLogger(__name__)

partner_router = APIRouter(prefix="/api/partner", tags=["Partner"])

_db = None

# ─── taux de rafraîchissement IP simple (mémoire locale) ─────────────────────
_RATE = {}  # ip -> (count, bucket_ts)
_RATE_LIMIT = 30   # requêtes / minute par IP


def init_partner_db(database):
    global _db
    _db = database


# ══════════════════════════════════════════════════════════════════════════════
# Utilitaires internes
# ══════════════════════════════════════════════════════════════════════════════

def _hash_token(tok: str) -> str:
    return hashlib.sha256(tok.encode("utf-8")).hexdigest()


def _ip(request: Request) -> str:
    return (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip() or "unknown"


def _rate_ok(ip: str) -> bool:
    """True si la requête est autorisée, False si le quota est dépassé."""
    import time
    now = int(time.time())
    bucket = now // 60
    c, b = _RATE.get(ip, (0, bucket))
    if b != bucket:
        c, b = 0, bucket
    c += 1
    _RATE[ip] = (c, b)
    return c <= _RATE_LIMIT


def _arrondir_chf(montant: float) -> float:
    """Arrondi au centime (règle déterministe : half-up)."""
    return round(montant * 100) / 100


def _masquer_nom(nom: str) -> str:
    """Prénom conservé, nom réduit à l'initiale. Ex : 'Alice Martin' -> 'Alice M.'"""
    parts = (nom or "").strip().split()
    if len(parts) >= 2:
        return " ".join(parts[:-1]) + " " + parts[-1][0].upper() + "."
    return nom or ""


def _sanitiser_str(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


# ══════════════════════════════════════════════════════════════════════════════
# Lecture combinée : transactions + réservations + espèces + attribution
# ══════════════════════════════════════════════════════════════════════════════

async def _lignes_pour_code(code_upper: str, coach_id: str, strict: bool = False) -> list:
    """Construit la liste unifiée des inscriptions pour un code promo.

    Sources croisées (lecture seule) :
      1. payment_transactions  — paiements Stripe confirmés ou en attente
      2. reservations           — réservations finalisées
      3. partner_cash_payments  — espèces déclarées par le coach

    Règle d'unicité : un session_id Stripe ne produit qu'une seule ligne.
    Un paiement sans réservation finalisée est affiché avec statut spécifique.

    strict=True : force le filtre coach_id même pour le super-admin (chemin jeton public).
    """
    lignes_par_session: dict = {}  # session_id -> ligne

    # 1 — transactions Stripe qui portent ce code
    filtre_tx = {"promo_code": code_upper}
    if strict or not is_super_admin(coach_id):
        filtre_tx["coach_id"] = coach_id
    async for tx in _db.payment_transactions.find(filtre_tx, {"_id": 0}):
        sid = _sanitiser_str(tx.get("session_id") or tx.get("id") or "")
        if not sid:
            continue
        if sid in lignes_par_session:
            continue
        qte = int(tx.get("quantity") or 1)
        montant = _arrondir_chf(float(tx.get("tarif_applique") or tx.get("amount") or 0) * qte)
        statut_raw = _sanitiser_str(tx.get("payment_status") or "")
        if statut_raw in ("paid", "completed"):
            statut = "paye"
        elif statut_raw == "refunded":
            statut = "rembourse"
        else:
            statut = "en_attente"
        lignes_par_session[sid] = {
            "session_id": sid,
            "nom": _sanitiser_str(tx.get("customer_name") or ""),
            "email": _sanitiser_str(tx.get("customer_email") or ""),
            "montant_chf": montant,
            "reduction_chf": _arrondir_chf(
                float(tx.get("tarif_public") or tx.get("server_unit_price") or 0) * qte - montant
            ),
            "statut": statut,
            "moyen": "en_ligne",
            "source": "code",
            "date_seance": None,
            "cours_nom": None,
            "reservation_id": None,
            "has_reservation": False,
            "created_at": _sanitiser_str(tx.get("created_at") or ""),
        }

    # 2 — réservations avec ce code (enrichit les lignes existantes ou crée les orphelines)
    filtre_r = {"$or": [
        {"promoCode": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}},
        {"discountCode": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}},
    ]}
    if not is_super_admin(coach_id):
        filtre_r["coach_id"] = coach_id
    async for r in _db.reservations.find(filtre_r, {"_id": 0}):
        sid = _sanitiser_str(r.get("stripeSessionId") or r.get("stripe_session_id") or "")
        nom_res = _sanitiser_str(r.get("userName") or r.get("user_name") or "")
        email_res = _sanitiser_str(r.get("userEmail") or r.get("user_email") or "")
        cours_nom = _sanitiser_str(r.get("courseName") or r.get("course_name") or r.get("courseId") or "")
        date_seance = _sanitiser_str(r.get("datetime") or r.get("date") or "")
        rid = _sanitiser_str(r.get("id") or r.get("_id") or "")
        if sid and sid in lignes_par_session:
            # Enrichit la ligne existante
            l = lignes_par_session[sid]
            l["has_reservation"] = True
            l["reservation_id"] = rid
            if not l["nom"]:
                l["nom"] = nom_res
            if not l["email"]:
                l["email"] = email_res
            if not l["cours_nom"]:
                l["cours_nom"] = cours_nom
            if not l["date_seance"]:
                l["date_seance"] = date_seance
        elif not sid:
            # Réservation sans session Stripe (paiement en espèces ou code gratuit)
            pseudo_id = f"resa:{rid}"
            if pseudo_id not in lignes_par_session:
                lignes_par_session[pseudo_id] = {
                    "session_id": None,
                    "nom": nom_res,
                    "email": email_res,
                    "montant_chf": 0.0,
                    "reduction_chf": 0.0,
                    "statut": "reservation_sans_paiement",
                    "moyen": "inconnu",
                    "source": "code",
                    "date_seance": date_seance,
                    "cours_nom": cours_nom,
                    "reservation_id": rid,
                    "has_reservation": True,
                    "created_at": _sanitiser_str(r.get("created_at") or ""),
                }

    # Paiements Stripe sans réservation finalisée
    for sid, l in lignes_par_session.items():
        if not l["has_reservation"] and l.get("session_id"):
            l["statut"] = "paiement_sans_reservation" if l["statut"] == "paye" else l["statut"]

    # 3 — espèces déclarées par le coach
    filtre_cash = {"code_upper": code_upper}
    if not is_super_admin(coach_id):
        filtre_cash["coach_id"] = coach_id
    async for c in _db.partner_cash_payments.find(filtre_cash, {"_id": 0}):
        cid = f"cash:{c.get('id','')}"
        lignes_par_session[cid] = {
            "session_id": None,
            "nom": f"{_sanitiser_str(c.get('prenom',''))} {_sanitiser_str(c.get('nom',''))}".strip(),
            "email": "",
            "montant_chf": _arrondir_chf(float(c.get("montant_chf") or 0)),
            "reduction_chf": 0.0,
            "statut": "paye",
            "moyen": "especes",
            "source": "code_especes",
            "date_seance": _sanitiser_str(c.get("date_seance") or ""),
            "cours_nom": None,
            "reservation_id": None,
            "has_reservation": False,
            "created_at": _sanitiser_str(c.get("created_at") or ""),
        }

    return list(lignes_par_session.values())


def _totaux(lignes: list, pct_partenaire: int) -> dict:
    """Calcule les totaux financiers depuis la liste des lignes."""
    total_inscriptions = len(lignes)
    payes = [l for l in lignes if l["statut"] in ("paye", "paiement_sans_reservation")]
    confirmes = [l for l in lignes if l["statut"] in ("paye", "paiement_sans_reservation")]
    rembourses = [l for l in lignes if l["statut"] == "rembourse"]

    total_net = _arrondir_chf(sum(l["montant_chf"] for l in confirmes))
    # Espèces font aussi partie du net
    especes_net = _arrondir_chf(sum(l["montant_chf"] for l in confirmes if l["moyen"] == "especes"))
    pct = max(0, min(100, pct_partenaire))
    part_partenaire = _arrondir_chf(total_net * pct / 100)
    part_afroboost = _arrondir_chf(total_net - part_partenaire)

    return {
        "nb_inscriptions": total_inscriptions,
        "nb_confirmes": len(confirmes),
        "nb_en_attente": len([l for l in lignes if l["statut"] == "en_attente"]),
        "nb_rembourses": len(rembourses),
        "nb_paiements_sans_reservation": len([l for l in lignes if l["statut"] == "paiement_sans_reservation"]),
        "total_net_chf": total_net,
        "part_partenaire_chf": part_partenaire,
        "part_afroboost_chf": part_afroboost,
        "pct_partenaire": pct,
        "especes_net_chf": especes_net,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Modèles Pydantic
# ══════════════════════════════════════════════════════════════════════════════

class ConfigPartenaire(BaseModel):
    partner_name: str = Field("", max_length=200)
    partner_pct: int = Field(40, ge=0, le=100)


class EspecesDeclaration(BaseModel):
    prenom: str = Field(..., min_length=1, max_length=100)
    nom: str = Field(..., min_length=1, max_length=100)
    date_seance: str = Field(..., min_length=6, max_length=20)
    montant_chf: float = Field(..., gt=0, le=10000)
    idempotence_key: str = Field(..., min_length=8, max_length=80)


# ══════════════════════════════════════════════════════════════════════════════
# Routes COACH (JWT obligatoire)
# ══════════════════════════════════════════════════════════════════════════════

@partner_router.get("/codes/{code}/details")
async def details_code(code: str, request: Request):
    """Vue coach : toutes les inscriptions liées à ce code promo, avec totaux."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    code_upper = code.upper()

    # Vérifier que le code appartient au coach (ou super-admin)
    filtre = {"code": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}, "active": True}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    fiche = await _db.discount_codes.find_one(filtre, {"_id": 0})
    if not fiche:
        raise HTTPException(404, "Code introuvable ou non autorisé")

    # Config partenaire pour ce code — filtrée par coach (IDOR fix V637b)
    filtre_cfg = {"code_upper": code_upper}
    if not is_super_admin(coach):
        filtre_cfg["coach_id"] = coach
    cfg = await _db.partner_configs.find_one(filtre_cfg, {"_id": 0}) or {}
    pct = int(cfg.get("partner_pct") or 40)
    partner_name = cfg.get("partner_name") or ""

    # Lien partenaire actif — filtrée par coach (IDOR fix V637b)
    filtre_tok = {"code_upper": code_upper, "revoked_at": None}
    if not is_super_admin(coach):
        filtre_tok["coach_id"] = coach
    tok_doc = await _db.partner_tokens.find_one(
        filtre_tok, {"_id": 0, "token_hash": 0}
    )
    lien_actif = tok_doc is not None
    token_id = tok_doc.get("id") if tok_doc else None

    lignes = await _lignes_pour_code(code_upper, coach)
    totaux = _totaux(lignes, pct)

    # Masquer les emails dans les lignes (la vue coach les garde, la vue partenaire les retire)
    return {
        "code": code_upper,
        "partner_name": partner_name,
        "pct_partenaire": pct,
        "lien_actif": lien_actif,
        "token_id": token_id,
        "lignes": lignes,
        "totaux": totaux,
    }


@partner_router.put("/codes/{code}/config")
async def config_partenaire(code: str, cfg: ConfigPartenaire, request: Request):
    """Met à jour la configuration partenaire (nom, pourcentage)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    code_upper = code.upper()

    filtre = {"code": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}}
    if not is_super_admin(coach):
        filtre["active"] = True
        filtre["coach_id"] = coach
    fiche = await _db.discount_codes.find_one(filtre, {"_id": 0})
    if not fiche:
        raise HTTPException(404, "Code introuvable ou non autorisé")

    now = datetime.now(timezone.utc).isoformat()
    # Filtre par (code_upper, coach_id) pour éviter les écrasements cross-tenant (IDOR fix V637b)
    filtre_upsert = {"code_upper": code_upper, "coach_id": coach}
    existing = await _db.partner_configs.find_one(filtre_upsert)
    if existing:
        await _db.partner_configs.update_one(
            filtre_upsert,
            {"$set": {"partner_name": cfg.partner_name, "partner_pct": cfg.partner_pct,
                      "updated_at": now}}
        )
    else:
        await _db.partner_configs.insert_one({
            "id": str(uuid.uuid4()),
            "code_upper": code_upper,
            "coach_id": coach,
            "partner_name": cfg.partner_name,
            "partner_pct": cfg.partner_pct,
            "created_at": now,
            "updated_at": now,
        })
    return {"ok": True, "code": code_upper, "partner_pct": cfg.partner_pct}


@partner_router.post("/codes/{code}/generate-token")
async def generer_token_partenaire(code: str, request: Request):
    """Génère un lien partenaire privé. Révoque l'ancien si présent."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    code_upper = code.upper()

    filtre = {"code": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}}
    if not is_super_admin(coach):
        filtre["active"] = True
        filtre["coach_id"] = coach
    fiche = await _db.discount_codes.find_one(filtre, {"_id": 0})
    if not fiche:
        raise HTTPException(404, "Code introuvable ou non autorisé")

    now = datetime.now(timezone.utc).isoformat()
    # Révoquer uniquement les jetons du même coach (IDOR fix V637b)
    await _db.partner_tokens.update_many(
        {"code_upper": code_upper, "coach_id": coach, "revoked_at": None},
        {"$set": {"revoked_at": now}}
    )
    # Nouveau jeton
    token = secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    await _db.partner_tokens.insert_one({
        "id": token_id,
        "code_upper": code_upper,
        "coach_id": coach,
        "token_hash": _hash_token(token),
        "created_at": now,
        "revoked_at": None,
    })
    return {"ok": True, "token": token, "token_id": token_id}


@partner_router.delete("/codes/{code}/revoke-token")
async def revoquer_token_partenaire(code: str, request: Request):
    """Révoque immédiatement tous les liens partenaires pour ce code."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    code_upper = code.upper()

    filtre = {"code": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}}
    if not is_super_admin(coach):
        filtre["active"] = True
        filtre["coach_id"] = coach
    fiche = await _db.discount_codes.find_one(filtre, {"_id": 0})
    if not fiche:
        raise HTTPException(404, "Code introuvable ou non autorisé")

    now = datetime.now(timezone.utc).isoformat()
    # Révoquer uniquement les jetons du même coach (IDOR fix V637b)
    await _db.partner_tokens.update_many(
        {"code_upper": code_upper, "coach_id": coach, "revoked_at": None},
        {"$set": {"revoked_at": now}}
    )
    return {"ok": True, "revoked_at": now}


@partner_router.post("/codes/{code}/cash")
async def declarer_especes(code: str, data: EspecesDeclaration, request: Request):
    """Le coach déclare un encaissement en espèces pour ce code."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    code_upper = code.upper()

    filtre = {"code": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}}
    if not is_super_admin(coach):
        filtre["active"] = True
        filtre["coach_id"] = coach
    fiche = await _db.discount_codes.find_one(filtre, {"_id": 0})
    if not fiche:
        raise HTTPException(404, "Code introuvable ou non autorisé")

    # Anti-doublon : idempotence_key unique par code
    ikey = f"{code_upper}:{data.idempotence_key}"
    existing = await _db.partner_cash_payments.find_one({"idempotence_key": ikey})
    if existing:
        return {"ok": True, "id": existing.get("id"), "doublon": True}

    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await _db.partner_cash_payments.insert_one({
        "id": pid,
        "code_upper": code_upper,
        "coach_id": coach,
        "prenom": data.prenom.strip(),
        "nom": data.nom.strip(),
        "date_seance": data.date_seance.strip(),
        "montant_chf": _arrondir_chf(data.montant_chf),
        "idempotence_key": ikey,
        "created_at": now,
        "created_by": coach,
    })
    return {"ok": True, "id": pid, "doublon": False}


@partner_router.get("/codes/{code}/export.csv")
async def export_csv(code: str, request: Request):
    """Export CSV de toutes les inscriptions pour ce code."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    code_upper = code.upper()

    filtre = {"code": {"$regex": f"^{re.escape(code_upper)}$", "$options": "i"}}
    if not is_super_admin(coach):
        filtre["active"] = True
        filtre["coach_id"] = coach
    fiche = await _db.discount_codes.find_one(filtre, {"_id": 0})
    if not fiche:
        raise HTTPException(404, "Code introuvable ou non autorisé")

    filtre_cfg_exp = {"code_upper": code_upper}
    if not is_super_admin(coach):
        filtre_cfg_exp["coach_id"] = coach
    cfg = await _db.partner_configs.find_one(filtre_cfg_exp, {"_id": 0}) or {}
    pct = int(cfg.get("partner_pct") or 40)

    lignes = await _lignes_pour_code(code_upper, coach)

    _FORMULA_CHARS = ('=', '-', '+', '@', '\t', '\r')

    def esc(v):
        """Échappe une valeur CSV + neutralise l'injection de formule (V637b)."""
        v = str(v or "")
        # Préfixe anti-injection : empêche Excel/LibreOffice d'interpréter la cellule
        if v and v[0] in _FORMULA_CHARS:
            v = "'" + v
        if any(c in v for c in (',', '"', '\n', '\r')):
            v = '"' + v.replace('"', '""') + '"'
        return v

    entete = "Nom,Date séance,Montant CHF,Réduction CHF,Moyen,Statut,Source\n"
    rows = "\n".join(
        f"{esc(l['nom'])},{esc(l['date_seance'])},{esc(l['montant_chf'])},"
        f"{esc(l['reduction_chf'])},{esc(l['moyen'])},{esc(l['statut'])},{esc(l['source'])}"
        for l in sorted(lignes, key=lambda x: x.get("created_at") or "")
    )
    totaux = _totaux(lignes, pct)
    summary = (
        f"\n\nTotal net CHF,{totaux['total_net_chf']}\n"
        f"Part partenaire {pct}%,{totaux['part_partenaire_chf']}\n"
        f"Part Afroboost {100-pct}%,{totaux['part_afroboost_chf']}\n"
    )
    contenu = entete + rows + summary
    return Response(
        content=contenu.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="partenaire_{code_upper}.csv"'},
    )


# ══════════════════════════════════════════════════════════════════════════════
# Route PARTENAIRE publique (jeton uniquement — aucune donnée personnelle)
# ══════════════════════════════════════════════════════════════════════════════

@partner_router.get("/view/{token}")
async def vue_partenaire(token: str, request: Request, response: Response):
    """Vue partenaire sécurisée : jeton dans l'URL, données anonymisées."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"

    ip = _ip(request)
    if not _rate_ok(ip):
        raise HTTPException(429, "Trop de requêtes")

    if not token or len(token) < 16 or len(token) > 200:
        raise HTTPException(404, "Lien invalide")

    h = _hash_token(token)
    tok_doc = await _db.partner_tokens.find_one({"token_hash": h, "revoked_at": None}, {"_id": 0})
    if not tok_doc:
        raise HTTPException(404, "Lien invalide ou révoqué")

    partner_id = tok_doc.get("partner_id")
    coach_id = tok_doc["coach_id"]

    if partner_id:
        # ── Chemin multi-partenaire (V638) ────────────────────────────────
        partner = await _db.partners.find_one(
            {"id": partner_id, "deleted": {"$ne": True}}, {"_id": 0}
        )
        if not partner:
            raise HTTPException(404, "Partenaire introuvable")
        pct = int(partner.get("pct") or 40)
        partner_name = partner.get("name") or ""
        code_display = ", ".join(partner.get("codes") or [])
        lignes = await _lignes_pour_partenaire(partner, coach_id, strict=True)
    else:
        # ── Chemin legacy par code (V637, backward compat) ────────────────
        code_upper = tok_doc.get("code_upper", "")
        cfg = await _db.partner_configs.find_one(
            {"code_upper": code_upper, "coach_id": coach_id}, {"_id": 0}
        ) or {}
        pct = int(cfg.get("partner_pct") or 40)
        partner_name = cfg.get("partner_name") or ""
        code_display = code_upper
        lignes = await _lignes_pour_code(code_upper, coach_id, strict=True)

    totaux = _totaux(lignes, pct)

    # Anonymiser : supprimer emails, masquer noms
    lignes_pub = []
    for l in lignes:
        lignes_pub.append({
            "nom_masque": _masquer_nom(l["nom"]),
            "date_seance": l["date_seance"],
            "montant_chf": l["montant_chf"],
            "statut": l["statut"],
            "moyen": l["moyen"],
            "source": l["source"],
        })

    return {
        "code": code_display,
        "codes": (partner.get("codes") if partner_id else None),
        "partner_name": partner_name,
        "pct_partenaire": pct,
        "lignes": lignes_pub,
        "totaux": totaux,
    }


# ══════════════════════════════════════════════════════════════════════════════
# V638 — SYSTÈME MULTI-PARTENAIRES
# ══════════════════════════════════════════════════════════════════════════════

# ─── Modèle Pydantic ─────────────────────────────────────────────────────────

class PartenaireData(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    pct: int = Field(40, ge=0, le=100)
    codes: list = Field(default_factory=list)          # list[str]
    invitation_ids: list = Field(default_factory=list)  # list[str]


# ─── Helpers V638 ─────────────────────────────────────────────────────────────

async def _lignes_pour_invitation(inv_id: str, coach_id: str, strict: bool = False) -> list:
    """Inscriptions liées à un identifiant d'invitation (Lien Intelligent)."""
    lignes_par_session: dict = {}
    filtre_r = {"$or": [
        {"invitation_id": inv_id},
        {"smart_link_id": inv_id},
        {"link_id": inv_id},
    ]}
    if strict or not is_super_admin(coach_id):
        filtre_r["coach_id"] = coach_id
    async for r in _db.reservations.find(filtre_r, {"_id": 0}):
        sid = _sanitiser_str(r.get("stripeSessionId") or r.get("stripe_session_id") or "")
        nom_res = _sanitiser_str(r.get("userName") or r.get("user_name") or "")
        email_res = _sanitiser_str(r.get("userEmail") or r.get("user_email") or "")
        cours_nom = _sanitiser_str(r.get("courseName") or r.get("course_name") or "")
        date_seance = _sanitiser_str(r.get("datetime") or r.get("date") or "")
        rid = _sanitiser_str(r.get("id") or str(r.get("_id", "")) or "")
        if sid:
            filtre_tx = {"session_id": sid}
            if strict or not is_super_admin(coach_id):
                filtre_tx["coach_id"] = coach_id
            tx = await _db.payment_transactions.find_one(filtre_tx, {"_id": 0})
            if tx and sid not in lignes_par_session:
                qte = int(tx.get("quantity") or 1)
                montant = _arrondir_chf(float(tx.get("tarif_applique") or tx.get("amount") or 0) * qte)
                statut_raw = _sanitiser_str(tx.get("payment_status") or "")
                statut = "paye" if statut_raw in ("paid", "completed") else ("rembourse" if statut_raw == "refunded" else "en_attente")
                lignes_par_session[sid] = {
                    "session_id": sid,
                    "nom": _sanitiser_str(tx.get("customer_name") or nom_res or ""),
                    "email": _sanitiser_str(tx.get("customer_email") or email_res or ""),
                    "montant_chf": montant,
                    "reduction_chf": 0.0,
                    "statut": statut,
                    "moyen": "en_ligne",
                    "source": "invitation",
                    "date_seance": date_seance,
                    "cours_nom": cours_nom,
                    "reservation_id": rid,
                    "has_reservation": True,
                    "created_at": _sanitiser_str(tx.get("created_at") or ""),
                }
        else:
            pseudo_id = f"inv_resa:{rid}"
            if pseudo_id not in lignes_par_session:
                lignes_par_session[pseudo_id] = {
                    "session_id": None,
                    "nom": nom_res,
                    "email": email_res,
                    "montant_chf": 0.0,
                    "reduction_chf": 0.0,
                    "statut": "reservation_sans_paiement",
                    "moyen": "inconnu",
                    "source": "invitation",
                    "date_seance": date_seance,
                    "cours_nom": cours_nom,
                    "reservation_id": rid,
                    "has_reservation": True,
                    "created_at": _sanitiser_str(r.get("created_at") or ""),
                }
    return list(lignes_par_session.values())


async def _lignes_pour_partenaire(partner_doc: dict, coach_id: str, strict: bool = False) -> list:
    """Agrège les inscriptions de tous les codes + invitations d'un partenaire.

    Déduplication par session_id : même Stripe session dans N codes = une seule ligne.
    """
    all_by_session: dict = {}

    # 1. Par codes promo
    for code in partner_doc.get("codes") or []:
        for l in await _lignes_pour_code(code.upper(), coach_id, strict=strict):
            key = l.get("session_id") or f"resa:{l.get('reservation_id', '')}"
            if key and key not in all_by_session:
                all_by_session[key] = l

    # 2. Par invitations (Liens Intelligents)
    for inv_id in partner_doc.get("invitation_ids") or []:
        for l in await _lignes_pour_invitation(inv_id, coach_id, strict=strict):
            key = l.get("session_id") or f"inv_resa:{l.get('reservation_id', '')}"
            if key and key not in all_by_session:
                all_by_session[key] = l

    # 3. Espèces déclarées au niveau du partenaire
    pid = partner_doc.get("id", "")
    if pid:
        filtre_cash = {"partner_id": pid}
        if strict or not is_super_admin(coach_id):
            filtre_cash["coach_id"] = coach_id
        async for c in _db.partner_cash_payments.find(filtre_cash, {"_id": 0}):
            cid = f"cash_p:{c.get('id', '')}"
            all_by_session[cid] = {
                "session_id": None,
                "nom": f"{_sanitiser_str(c.get('prenom', ''))} {_sanitiser_str(c.get('nom', ''))}".strip(),
                "email": "",
                "montant_chf": _arrondir_chf(float(c.get("montant_chf") or 0)),
                "reduction_chf": 0.0,
                "statut": "paye",
                "moyen": "especes",
                "source": "especes_partenaire",
                "date_seance": _sanitiser_str(c.get("date_seance") or ""),
                "cours_nom": None,
                "reservation_id": None,
                "has_reservation": False,
                "created_at": _sanitiser_str(c.get("created_at") or ""),
            }

    return list(all_by_session.values())


async def _detecter_conflits(coach_id: str) -> list:
    """Détecte les session_id revendiqués par plusieurs partenaires du même coach.

    Ne répartit jamais le montant — signale uniquement le conflit.
    """
    partners = await _db.partners.find(
        {"coach_id": coach_id, "deleted": {"$ne": True}}, {"_id": 0}
    ).to_list(200)

    sid_to_partners: dict = {}
    for p in partners:
        pinfo = {"id": p["id"], "name": p.get("name", "?")}
        for code in p.get("codes") or []:
            filtre = {"promo_code": code.upper(), "coach_id": coach_id}
            async for tx in _db.payment_transactions.find(filtre, {"session_id": 1, "_id": 0}):
                sid = tx.get("session_id")
                if sid:
                    if sid not in sid_to_partners:
                        sid_to_partners[sid] = []
                    if not any(x["id"] == pinfo["id"] for x in sid_to_partners[sid]):
                        sid_to_partners[sid].append(pinfo)

    return [
        {"session_id": sid, "partenaires": plist}
        for sid, plist in sid_to_partners.items()
        if len(plist) > 1
    ]


# ─── Routes CRUD partenaires ──────────────────────────────────────────────────

@partner_router.get("/partners")
async def lister_partenaires(request: Request):
    """Liste tous les partenaires du coach authentifié."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"coach_id": coach, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    docs = await _db.partners.find(filtre, {"_id": 0, "token_hash": 0}).to_list(200)
    return {"partenaires": docs}


@partner_router.post("/partners")
async def creer_partenaire(data: PartenaireData, request: Request):
    """Crée un nouveau partenaire pour le coach authentifié."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "coach_id": coach,
        "name": data.name.strip(),
        "pct": data.pct,
        "codes": [c.upper() for c in data.codes],
        "invitation_ids": list(data.invitation_ids),
        "created_at": now,
        "updated_at": now,
        "deleted": False,
    }
    await _db.partners.insert_one(doc)
    return_doc = {k: v for k, v in doc.items() if k != "_id"}
    return_doc.pop("deleted", None)
    from fastapi.responses import JSONResponse
    return JSONResponse(return_doc, status_code=201)


@partner_router.get("/partners/conflicts")
async def conflits_partenaires(request: Request):
    """Retourne les conflits (session_id revendiqués par plusieurs partenaires)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    conflits = await _detecter_conflits(coach)
    return {"conflits": conflits, "nb_conflits": len(conflits)}


@partner_router.get("/partners/{partner_id}")
async def obtenir_partenaire(partner_id: str, request: Request):
    """Retourne un partenaire par son id (coach authentifié uniquement)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    doc = await _db.partners.find_one(filtre, {"_id": 0, "deleted": 0})
    if not doc:
        raise HTTPException(404, "Partenaire introuvable")
    return doc


@partner_router.put("/partners/{partner_id}")
async def modifier_partenaire(partner_id: str, data: PartenaireData, request: Request):
    """Met à jour un partenaire (nom, pct, codes, invitations)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    doc = await _db.partners.find_one(filtre)
    if not doc:
        raise HTTPException(404, "Partenaire introuvable")
    now = datetime.now(timezone.utc).isoformat()
    await _db.partners.update_one(filtre, {"$set": {
        "name": data.name.strip(),
        "pct": data.pct,
        "codes": [c.upper() for c in data.codes],
        "invitation_ids": list(data.invitation_ids),
        "updated_at": now,
    }})
    updated = await _db.partners.find_one({"id": partner_id}, {"_id": 0, "deleted": 0})
    return updated


@partner_router.delete("/partners/{partner_id}")
async def supprimer_partenaire(partner_id: str, request: Request):
    """Suppression logique d'un partenaire (soft delete)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    doc = await _db.partners.find_one(filtre)
    if not doc:
        raise HTTPException(404, "Partenaire introuvable")
    now = datetime.now(timezone.utc).isoformat()
    await _db.partners.update_one(filtre, {"$set": {"deleted": True, "deleted_at": now}})
    # Révoquer les jetons actifs
    await _db.partner_tokens.update_many(
        {"partner_id": partner_id, "revoked_at": None},
        {"$set": {"revoked_at": now}}
    )
    return {"ok": True, "deleted_at": now}


@partner_router.get("/partners/{partner_id}/details")
async def details_partenaire(partner_id: str, request: Request):
    """Détails agrégés du partenaire : toutes les inscriptions (codes + invitations)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    partner = await _db.partners.find_one(filtre, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partenaire introuvable")

    # Lien partenaire actif
    tok_doc = await _db.partner_tokens.find_one(
        {"partner_id": partner_id, "coach_id": partner["coach_id"], "revoked_at": None},
        {"_id": 0, "token_hash": 0}
    )

    lignes = await _lignes_pour_partenaire(partner, coach)
    totaux = _totaux(lignes, partner.get("pct", 40))

    return {
        "id": partner_id,
        "name": partner.get("name", ""),
        "pct_partenaire": partner.get("pct", 40),
        "codes": partner.get("codes", []),
        "invitation_ids": partner.get("invitation_ids", []),
        "lien_actif": tok_doc is not None,
        "token_id": tok_doc.get("id") if tok_doc else None,
        "lignes": lignes,
        "totaux": totaux,
    }


@partner_router.post("/partners/{partner_id}/generate-token")
async def generer_token_partenaire_v2(partner_id: str, request: Request):
    """Génère un lien partenaire pour un partenaire (révoque l'ancien)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    partner = await _db.partners.find_one(filtre, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partenaire introuvable")

    now = datetime.now(timezone.utc).isoformat()
    owner_id = partner["coach_id"]  # V638b : source de vérité pour l'émission du jeton
    # Révoquer les anciens jetons de ce partenaire (filtre sur partner_id seul — accès déjà contrôlé)
    await _db.partner_tokens.update_many(
        {"partner_id": partner_id, "revoked_at": None},
        {"$set": {"revoked_at": now}}
    )
    token = secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    await _db.partner_tokens.insert_one({
        "id": token_id,
        "partner_id": partner_id,
        "code_upper": None,           # V638 : partenaire global, pas lié à un code
        "coach_id": owner_id,
        "token_hash": _hash_token(token),
        "created_at": now,
        "revoked_at": None,
    })
    return {"ok": True, "token": token, "token_id": token_id}


@partner_router.delete("/partners/{partner_id}/revoke-token")
async def revoquer_token_partenaire_v2(partner_id: str, request: Request):
    """Révoque tous les liens actifs d'un partenaire."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    partner = await _db.partners.find_one(filtre)
    if not partner:
        raise HTTPException(404, "Partenaire introuvable")
    now = datetime.now(timezone.utc).isoformat()
    # Révoquer tous les jetons de ce partenaire (accès déjà contrôlé par la recherche ci-dessus)
    res = await _db.partner_tokens.update_many(
        {"partner_id": partner_id, "revoked_at": None},
        {"$set": {"revoked_at": now}}
    )
    revoked_count = res.modified_count if hasattr(res, "modified_count") else 0
    return {"ok": True, "revoked_at": now, "revoked_count": revoked_count}


@partner_router.post("/partners/{partner_id}/cash")
async def declarer_especes_partenaire(partner_id: str, data: EspecesDeclaration, request: Request):
    """Déclare un encaissement en espèces pour un partenaire (avec anti-doublon)."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    partner = await _db.partners.find_one(filtre, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partenaire introuvable")

    # Anti-doublon
    ikey = f"{partner_id}:{data.idempotence_key}"
    existing = await _db.partner_cash_payments.find_one({"idempotence_key": ikey})
    if existing:
        return {"ok": True, "id": existing.get("id"), "doublon": True}

    pid_cash = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await _db.partner_cash_payments.insert_one({
        "id": pid_cash,
        "partner_id": partner_id,
        "coach_id": coach,
        "prenom": data.prenom.strip(),
        "nom": data.nom.strip(),
        "date_seance": data.date_seance.strip(),
        "montant_chf": _arrondir_chf(data.montant_chf),
        "idempotence_key": ikey,
        "created_at": now,
        "created_by": coach,
    })
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True, "id": pid_cash, "doublon": False}, status_code=201)


@partner_router.get("/partners/{partner_id}/export.csv")
async def export_csv_partenaire(partner_id: str, request: Request):
    """Export CSV agrégé pour un partenaire."""
    coach = coach_jwt_email(request)
    if not coach:
        raise HTTPException(403, "Authentification coach requise")
    filtre = {"id": partner_id, "deleted": {"$ne": True}}
    if not is_super_admin(coach):
        filtre["coach_id"] = coach
    partner = await _db.partners.find_one(filtre, {"_id": 0})
    if not partner:
        raise HTTPException(404, "Partenaire introuvable")

    pct = int(partner.get("pct") or 40)
    lignes = await _lignes_pour_partenaire(partner, coach)

    _FORMULA_CHARS = ('=', '-', '+', '@', '\t', '\r')

    def esc(v):
        v = str(v or "")
        if v and v[0] in _FORMULA_CHARS:
            v = "'" + v
        if any(c in v for c in (',', '"', '\n', '\r')):
            v = '"' + v.replace('"', '""') + '"'
        return v

    entete = "Nom,Date séance,Montant CHF,Réduction CHF,Moyen,Statut,Source\n"
    rows = "\n".join(
        f"{esc(l['nom'])},{esc(l['date_seance'])},{esc(l['montant_chf'])},"
        f"{esc(l['reduction_chf'])},{esc(l['moyen'])},{esc(l['statut'])},{esc(l['source'])}"
        for l in sorted(lignes, key=lambda x: x.get("created_at") or "")
    )
    totaux = _totaux(lignes, pct)
    summary = (
        f"\n\nTotal net CHF,{totaux['total_net_chf']}\n"
        f"Part partenaire {pct}%,{totaux['part_partenaire_chf']}\n"
        f"Part Afroboost {100-pct}%,{totaux['part_afroboost_chf']}\n"
    )
    contenu = entete + rows + summary
    nom_fichier = _sanitiser_str(partner.get("name", partner_id)).replace(" ", "_")[:30]
    return Response(
        content=contenu.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f'attachment; filename="partenaire_{nom_fichier}.csv"'},
    )

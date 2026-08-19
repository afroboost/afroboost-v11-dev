# -*- coding: utf-8 -*-
"""P1-bis-a — L'ADHESION : QUI EST MEMBRE, ET DEPUIS QUAND.

CE QUE CE LOT AJOUTE, ET RIEN D'AUTRE
=====================================
Une collection `memberships`, un formulaire de saisie a la main pour le coach,
et les deux lectures qui servent cette saisie. C'est tout.

CE QUE CE LOT NE FAIT PAS — et la liste est aussi importante que le reste :
aucun avantage tarifaire, aucun snapshot, aucun renouvellement, aucune regle
250/150, aucun moteur d'eligibilite au passage en caisse. Ce module n'est LU par
personne : ni le checkout, ni Stripe, ni les reservations, ni l'essai gratuit,
ni les promotions, ni la lecture financiere A/B, ni la conversion LOT A. Si
P1-bis-b n'arrivait jamais, la production resterait fonctionnellement identique
a ce qu'elle etait avant ce commit — c'est verifiable, et c'est verifie
(`tests/test_p1bisa_adhesions.py`, mesures 10 a 14).

POURQUOI UNE COLLECTION, ET PAS UN CHAMP SUR LE FORFAIT
=======================================================
Une adhesion et un forfait de seances ne vivent pas au meme rythme : le forfait
s'epuise (`remaining_sessions`), l'adhesion expire a une date. Les melanger
reproduirait exactement le defaut de `total_sessions`, incremente au
renouvellement, qui a oblige le lot B a figer `seances_a_l_achat` a cote
(`shared.py`). Deux cycles de vie, deux documents.

AUCUN BACKFILL. RIEN N'EST DEDUIT DU PASSE
==========================================
Aucune adhesion n'est creee a partir d'une offre a 250 ou a 150, d'un nom
d'offre, d'une ancienne transaction, d'un `subscription.offer_name` ni d'un code
promo. Les donnees historiques restent SANS adhesion, ce qui est la verite : le
depot n'a jamais enregistre qui etait membre. Un faux membre deduit d'un montant
coute plus cher qu'un membre manquant, qu'un humain peut saisir en dix secondes.

LE STATUT N'EST PAS STOCKE
==========================
Il n'existe pas de champ `is_member`, pas de `status: active`. Le statut est
DEDUIT des dates a chaque lecture (`p1a_statut`). C'est la lecon de V393 : un
`status: active` perime laissait reserver un forfait expire, parce que personne
ne repassait derriere pour le corriger. Une date, elle, ne ment jamais.
"""
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from api.routes.shared import (B_DEVISE_DEFAUT, B_ORIGINES_MANUELLES,
                               b_valider_encaissement)

logger = logging.getLogger(__name__)

membership_router = APIRouter(tags=["memberships"])

db = None


def init_membership_db(database):
    global db
    db = database


# Les trois formes REELLES de « sans proprietaire » constatees en production le
# 19/08/2026 : `coach_id` nul sur les 8 offres, chaine vide sur les forfaits
# d'essai, et champ absent sur le stock le plus ancien. La liste est enumerative
# et volontairement fermee — voir `p1a_filtre_proprietaire`.
P1A_SANS_PROPRIETAIRE = [{"coach_id": None}, {"coach_id": ""},
                         {"coach_id": {"$exists": False}}]

P1A_STATUTS = ("future", "active", "expiree", "invalide")

P1A_MSG_DATES = ("Dates d'adhésion requises : début et fin, au format "
                 "JJ/MM/AAAA ou AAAA-MM-JJ.")
P1A_MSG_ORDRE = "La date de fin ne peut pas précéder la date de début."
P1A_MSG_EMAIL = "Adresse e-mail du participant requise."

# Meme motif que la validation d'e-mail des segments (V363) : volontairement
# simple, il ecarte la saisie vide ou manifestement fausse sans pretendre
# valider une adresse — seul un envoi reel le peut.
_P1A_MOTIF_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[a-zA-Z]{2,}$")


def p1a_jour_suisse() -> str:
    """La date du jour a Zurich, en AAAA-MM-JJ.

    Zurich et non UTC : le coach est en Suisse, et une adhesion qui se termine
    « le 31 decembre » se termine a la fin de SA journee. En UTC, une lecture
    faite le 1er janvier a 00h30 heure suisse verrait encore le 31 decembre et
    prolongerait l'adhesion d'une demi-journee. L'ecart est petit, mais il porte
    sur la seule chose que ce module decide.
    """
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Zurich")).strftime("%Y-%m-%d")
    except Exception:
        # Une bibliotheque de fuseaux absente ne doit pas rendre le module
        # inutilisable : UTC est une approximation acceptable a l'heure pres.
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def p1a_date_iso(valeur) -> str:
    """La date normalisee en AAAA-MM-JJ, ou "" si elle n'est pas exploitable.

    Deux formats acceptes : AAAA-MM-JJ (ce qu'envoie un `<input type="date">`)
    et JJ/MM/AAAA (ce que le coach ecrit a la main). Tout le reste est refuse
    plutot que devine : une date mal lue decale une adhesion entiere.
    """
    _v = str(valeur or "").strip()
    if not _v:
        return ""
    for _format in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(_v[:10], _format).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def p1a_statut(date_debut, date_fin, aujourdhui=None) -> str:
    """« future » | « active » | « expiree » | « invalide » — DEDUIT des dates.

    Bornes INCLUSES aux deux extremites : une adhesion du 01/01/2026 au
    31/12/2026 est active le 01/01 comme le 31/12. C'est la lecture qu'attend
    quelqu'un qui lit « valable jusqu'au 31 decembre ».

    « invalide » n'est pas un cinquieme etat metier : c'est l'aveu qu'un
    document ne porte pas de dates lisibles. La creation l'interdit ; seul un
    document modifie a la main hors de cette route peut l'atteindre. On refuse
    alors de trancher — surtout pas de le declarer actif.

    Comparaison de chaines AAAA-MM-JJ : lexicographiquement equivalente a la
    comparaison de dates, sans conversion ni fuseau a chaque appel.
    """
    _d = p1a_date_iso(date_debut)
    _f = p1a_date_iso(date_fin)
    if not _d or not _f or _f < _d:
        return "invalide"
    _j = p1a_date_iso(aujourdhui) or p1a_jour_suisse()
    if _j < _d:
        return "future"
    if _j > _f:
        return "expiree"
    return "active"


def p1a_coach_id_contexte(appelant: str, est_super_admin: bool):
    """Le proprietaire a inscrire sur une adhesion creee par `appelant`.

    REGLE SYMETRIQUE, et le mot « symetrique » a coute une soiree le 19/08/2026.
    Le defaut alors corrige (`2c8a831`) : un repli injectait le compte
    super-admin comme proprietaire dans la REQUETE, alors que les 8 offres de
    production portent `coach_id` nul et les forfaits d'essai la chaine vide. La
    projection cherchait donc un proprietaire que RIEN ne porte, et sortait vide
    quoi que le coach fasse.

    Ici : un partenaire identifie est proprietaire de ce qu'il saisit ; le
    super-admin, lui, ecrit SANS proprietaire — exactement comme le stock qu'il
    possede deja. On n'injecte jamais son adresse artificiellement.
    """
    if est_super_admin:
        return None
    return (appelant or "").strip().lower() or None


def p1a_filtre_proprietaire(coach_id) -> dict:
    """Le filtre de lecture, miroir exact de `p1a_coach_id_contexte`.

    Proprietaire reel -> ses adhesions, et elles seules.
    Aucun proprietaire -> les adhesions sans proprietaire, et elles seules.

    Un partenaire ne voit JAMAIS le stock sans proprietaire, et le contexte sans
    proprietaire ne voit JAMAIS le catalogue d'un partenaire : une adhesion
    explicitement possedee n'est pas « sans proprietaire ». Meme raisonnement,
    meme forme que `conv_offres_premier_achat` (LOT A) — une seule idee de la
    propriete dans tout le depot. Fail closed en multi-coach.
    """
    _cid = (coach_id or "").strip().lower() if isinstance(coach_id, str) else coach_id
    if _cid:
        return {"coach_id": _cid}
    return {"$or": list(P1A_SANS_PROPRIETAIRE)}


def p1a_projeter(doc: dict, aujourdhui=None) -> dict:
    """Le document tel que l'ecran le recoit : ses champs, plus le statut CALCULE.

    `statut` n'est jamais lu depuis la base — il est recalcule ici a chaque
    lecture. Un document qui en porterait un (import, ecriture directe) le verra
    ecrase : la base ne fait pas foi sur ce point, les dates si.
    """
    _d = dict(doc or {})
    _d.pop("_id", None)
    _d["statut"] = p1a_statut(_d.get("date_debut"), _d.get("date_fin"), aujourdhui)
    return _d


async def _p1a_appelant(request: Request) -> tuple:
    """(email du coach, est-il super-admin) — ou 403.

    JWT SIGNE UNIQUEMENT, jamais `X-User-Email`. Cette route renvoie des
    adresses e-mail : la regle « aucune donnee personnelle sans
    authentification » s'applique sans amenagement.

    CE DURCISSEMENT EST PROUVE, au sens de la regle V310c : le tableau de bord
    du proprietaire porte deja un jeton signe. `/trash` et `/discount-codes`
    sont JWT-strict et figurent dans `ROUTES_SIGNATURE_REQUISE`
    (frontend/src/utils/authSession.js), liste dont chaque entree a ete mesuree
    en production le 18/08/2026 — 403 sans jeton, 200 avec. La corbeille et
    l'ecran des codes fonctionnent : le chemin legitime existe et est emprunte.

    ECHEC D'IMPORT -> REFUS. Un module d'authentification illisible ne doit
    jamais ouvrir la porte ; meme arbitrage que `conv_presence_reelle`.
    """
    try:
        from api.server import (_v311_coach_email_from_jwt as _jwt,
                                _v309_is_coach_or_admin as _est_coach,
                                is_super_admin as _est_admin)
    except Exception as _err:
        logger.error("[P1BIS-A] authentification indisponible: %s", _err)
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    _email = _jwt(request)
    if not _email or not await _est_coach(_email):
        logger.warning("[P1BIS-A] refus — aucun jeton coach signe")
        raise HTTPException(
            status_code=403,
            detail="Authentification coach requise — reconnectez-vous")
    return _email, bool(_est_admin(_email))


@membership_router.post("/memberships")
async def creer_adhesion(request: Request):
    """Le coach enregistre une adhesion a la main. Aucune deduction, aucun calcul.

    Le montant de la carte passe par `b_valider_encaissement` — le validateur du
    lot B, celui qui sert deja aux codes crees a la main. Reutilise et non
    recopie : une adhesion payee en especes doit se lire EXACTEMENT comme un
    forfait paye en especes (`montant_encaisse`, `devise`, `origine_paiement`),
    sinon la lecture financiere aurait deux vocabulaires a connaitre. Les regles
    du lot B s'appliquent donc telles quelles : « offert » interdit un montant
    non nul, un 0 non declare offert est refuse, un moyen inconnu est refuse.

    `exiger=False` : une adhesion peut etre enregistree sans montant (le coach
    saisit d'abord les dates, la carte est reglee plus tard). Mais tout ce qui
    est fourni est valide — jamais de declaration a moitie vraie.
    """
    appelant, est_admin = await _p1a_appelant(request)
    try:
        corps = await request.json()
    except Exception:
        corps = {}
    if not isinstance(corps, dict):
        corps = {}

    email = str(corps.get("email") or "").strip().lower()
    if not email or not _P1A_MOTIF_EMAIL.match(email):
        raise HTTPException(status_code=400, detail=P1A_MSG_EMAIL)

    date_debut = p1a_date_iso(corps.get("date_debut"))
    date_fin = p1a_date_iso(corps.get("date_fin"))
    if not date_debut or not date_fin:
        raise HTTPException(status_code=400, detail=P1A_MSG_DATES)
    if date_fin < date_debut:
        raise HTTPException(status_code=400, detail=P1A_MSG_ORDRE)

    # Lot B : leve un 400 explicite sur toute incoherence, ne corrige rien en
    # silence. `seances=None` — une adhesion n'ouvre aucune seance, c'est
    # precisement ce qui la distingue d'un forfait.
    champs_b = b_valider_encaissement(
        corps.get("montant"), corps.get("origine_paiement"),
        corps.get("devise") or B_DEVISE_DEFAUT, saisi_par=appelant,
        seances=None, exiger=False)

    maintenant = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        # Le nom sert l'affichage de la liste, rien d'autre. Il n'identifie pas :
        # `email` est la seule cle du participant.
        "name": str(corps.get("name") or "").strip()[:120],
        "coach_id": p1a_coach_id_contexte(appelant, est_admin),
        "date_debut": date_debut,
        "date_fin": date_fin,
        "devise": (champs_b.get("devise") or B_DEVISE_DEFAUT),
        "source": "saisie_manuelle",
        "created_by": appelant,
        "created_at": maintenant,
        "updated_at": maintenant,
    }
    doc.update(champs_b)
    # AUCUN `statut` en base. Il est calcule a la lecture, et lui seul fait foi.
    doc.pop("statut", None)

    await db["memberships"].insert_one(doc)
    logger.info("[P1BIS-A] adhesion %s -> %s (%s au %s) par %s",
                doc["id"][:8], email, date_debut, date_fin, appelant)
    return {"success": True, "membership": p1a_projeter(doc)}


@membership_router.get("/memberships")
async def lister_adhesions(request: Request, page: int = 1, limit: int = 50,
                           email: str = ""):
    """Les adhesions visibles par l'appelant, page par page.

    50 par page au maximum (regle du depot sur toute liste). Le filtre par
    e-mail est une EGALITE STRICTE sur une valeur mise en minuscules : aucune
    saisie utilisateur n'entre dans une regex MongoDB.
    """
    appelant, est_admin = await _p1a_appelant(request)
    limit = max(1, min(int(limit or 50), 50))
    page = max(1, int(page or 1))

    requete = p1a_filtre_proprietaire(p1a_coach_id_contexte(appelant, est_admin))
    _cible = str(email or "").strip().lower()
    if _cible:
        requete = dict(requete)
        requete["email"] = _cible

    lignes = await db["memberships"].find(requete, {"_id": 0}) \
        .sort("date_fin", -1).skip((page - 1) * limit).limit(limit).to_list(limit)
    total = await db["memberships"].count_documents(requete)
    jour = p1a_jour_suisse()
    return {
        "success": True,
        "memberships": [p1a_projeter(_l, jour) for _l in lignes],
        "total": total, "page": page, "limit": limit,
        "aujourdhui": jour,
        "moyens": list(B_ORIGINES_MANUELLES),
    }

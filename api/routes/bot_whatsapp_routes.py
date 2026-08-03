# bot_whatsapp_routes.py — V367 (ÉTAPE 1/5) : menu WhatsApp à boutons, LECTURE SEULE
#
# CE QUE FAIT CETTE ÉTAPE — ET CE QU'ELLE NE FAIT PAS
# ---------------------------------------------------
# Elle ne fait QUE construire et prévisualiser le menu. Elle n'écrit rien, n'envoie
# AUCUN message, et ne touche pas au webhook entrant : le comportement actuel de
# WhatsApp est strictement inchangé. La greffe sur le webhook viendra à l'étape
# suivante, une fois le rendu validé.
#
# TOUJOURS À JOUR, SANS SAISIE MANUELLE
# Le menu ne recopie rien : il relit `courses` et `offers` à CHAQUE affichage, avec
# les mêmes filtres que la vitrine (`archived != true` pour les cours, `visible` pour
# les offres). Un cours ajouté dans le dashboard apparaît donc dans WhatsApp à la
# question suivante — c'est tout l'intérêt par rapport à une liste figée, qui vieillit
# comme a vieilli le groupe « Contacts WhatsApp ».
#
# LIMITES DE LA PLATEFORME (WhatsApp Cloud API), respectées ici :
#   - boutons de réponse : 3 maximum, titre <= 20 caractères
#   - liste : 10 lignes maximum, titre de ligne <= 24, description <= 72
#   - corps du message <= 1024 caractères
# Quand il y a plus de 10 cours, on le DIT dans le message (« et N autres ») plutôt
# que de tronquer en silence.
import logging
import os
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

bot_router = APIRouter(tags=["bot-whatsapp"])

db = None


def init_bot_db(database):
    global db
    db = database


# Interrupteur général. Défaut FALSE : tant qu'il n'est pas basculé, le bot n'existe
# pas — même une fois la greffe posée sur le webhook.
DRAPEAU_BOT = "BOT_MENU_ENABLED"

MAX_LIGNES_LISTE = 10        # imposé par WhatsApp
MAX_TITRE_LIGNE = 24         # imposé par WhatsApp
MAX_DESCRIPTION_LIGNE = 72   # imposé par WhatsApp
MAX_TITRE_BOUTON = 20        # imposé par WhatsApp

JOURS = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]

SITE = "https://afroboost.com"

# Identifiants des boutons : ils reviennent tels quels dans le webhook quand la
# personne clique. Ils sont stables — ne pas les renommer sans mettre à jour le
# webhook, sinon un clic ne serait plus reconnu.
BOUTON_COURS = "menu_cours"
BOUTON_OFFRES = "menu_offres"
BOUTON_COACH = "menu_coach"


def _couper(texte, maximum):
    """Coupe proprement à la limite WhatsApp, avec un caractère de continuité."""
    t = re.sub(r"\s+", " ", str(texte or "")).strip()
    if len(t) <= maximum:
        return t
    return t[:maximum - 1].rstrip() + "…"


async def bot_actif() -> bool:
    """Le menu est-il activé ? Défaut FALSE = comportement actuel, à l'identique."""
    try:
        flags = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0}) or {}
        return bool(flags.get(DRAPEAU_BOT, False))
    except Exception as e:
        logger.warning(f"[BOT-WA] Drapeau {DRAPEAU_BOT} illisible ({e}) — bot considéré INACTIF")
        return False


# ---------------------------------------------------------------- lecture des données

# V367 : fiches d'horaire jamais renommées. L'assistant d'offre (V225) crée un cours
# DÈS le clic sur « ajouter un horaire », nommé « Nouveau cours » et invisible ; il ne
# devient visible qu'à l'enregistrement. Onze fiches sont restées avec ce nom par
# défaut. Le bot les masque — un menu qui propose « Nouveau cours » n'inspire rien.
# On ne SUPPRIME rien : c'est un filtre d'affichage, la base n'est pas touchée.
def _sans_vrai_nom(course):
    nom = (course.get("name") or "").strip().lower()
    return nom == "" or nom.startswith("nouveau cours")


async def lire_cours():
    """Les cours affichés par la vitrine : MÊME filtre que GET /api/courses."""
    cours = await db.courses.find(
        {"archived": {"$ne": True}},
        {"_id": 0, "id": 1, "name": 1, "weekday": 1, "time": 1,
         "locationName": 1, "location": 1, "date": 1, "visible": 1}
    ).to_list(100)
    # La vitrine masque en plus ce qui n'est pas `visible`.
    return [c for c in cours if c.get("visible") is not False and not _sans_vrai_nom(c)]


async def lire_offres():
    """Les offres et produits affichés par la boutique : MÊME filtre que GET /api/offers."""
    offres = await db.offers.find(
        {}, {"_id": 0, "id": 1, "name": 1, "price": 1, "description": 1,
             "category": 1, "isProduct": 1, "visible": 1, "stock": 1}
    ).to_list(100)
    return [o for o in offres if o.get("visible") is not False]


def _cle_tri_cours(c, aujourdhui=None):
    """Trie par PROCHAINE OCCURRENCE, pas par numéro de jour.

    Trier de dimanche à samedi remplissait les 10 places avec les seuls dimanches,
    et cachait les cours de mercredi — les plus proches. Quelqu'un qui écrit veut
    savoir ce qui vient ENSUITE.
    """
    if aujourdhui is None:
        aujourdhui = (datetime.now(timezone.utc).weekday() + 1) % 7  # dimanche = 0
    jour = c.get("weekday")
    jour = jour if isinstance(jour, int) else 9
    dans_combien = (jour - aujourdhui) % 7 if jour <= 6 else 9
    return (dans_combien, str(c.get("time") or "99:99"), str(c.get("name") or ""))


def _dedoublonner_cours(cours):
    """Même nom + même jour + même heure + même lieu = une seule ligne."""
    vus, uniques = set(), []
    for c in cours:
        cle = (re.sub(r"\s+", " ", (c.get("name") or "").strip().lower()),
               c.get("weekday"), c.get("time"),
               (c.get("locationName") or c.get("location") or "").strip().lower())
        if cle in vus:
            continue
        vus.add(cle)
        uniques.append(c)
    return uniques


# ---------------------------------------------------------------- construction du menu

def construire_menu_principal(prenom=None):
    """Message d'accueil + 3 boutons. Format `interactive / button` de WhatsApp."""
    bonjour = f"Bonjour {prenom} 👋" if prenom else "Bonjour 👋"
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": f"{bonjour}\n\nBienvenue chez Afroboost ! Que souhaites-tu ?"},
            "footer": {"text": "Tape « coach » à tout moment pour parler à un humain."},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": BOUTON_COURS,
                                                "title": _couper("📅 Nos cours", MAX_TITRE_BOUTON)}},
                    {"type": "reply", "reply": {"id": BOUTON_OFFRES,
                                                "title": _couper("🛍️ Nos offres", MAX_TITRE_BOUTON)}},
                    {"type": "reply", "reply": {"id": BOUTON_COACH,
                                                "title": _couper("💬 Parler à un coach", MAX_TITRE_BOUTON)}},
                ]
            }
        }
    }


def construire_liste_cours(cours):
    """Liste des cours, lue en direct. Renvoie aussi le nombre non affiché."""
    tries = sorted(_dedoublonner_cours(cours), key=_cle_tri_cours)
    retenus = tries[:MAX_LIGNES_LISTE]
    reste = len(tries) - len(retenus)

    lignes = []
    for c in retenus:
        jour = c.get("weekday")
        jour_txt = JOURS[jour] if isinstance(jour, int) and 0 <= jour <= 6 else ""
        heure = c.get("time") or ""
        lieu = c.get("locationName") or c.get("location") or ""
        quand = " ".join(x for x in (jour_txt, heure) if x)
        lignes.append({
            "id": f"cours_{c.get('id', '')}"[:200],
            "title": _couper(c.get("name") or "Cours", MAX_TITRE_LIGNE),
            "description": _couper(" · ".join(x for x in (quand, lieu) if x), MAX_DESCRIPTION_LIGNE)
        })

    corps = "Voici nos cours 📅"
    if reste > 0:
        # Jamais de troncature silencieuse : on annonce ce qui n'est pas montré.
        corps += f"\n\n(et {reste} autre{'s' if reste > 1 else ''} sur {SITE})"

    return {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": corps},
            "footer": {"text": "Réserve sur afroboost.com"},
            "action": {
                "button": _couper("Voir les cours", MAX_TITRE_BOUTON),
                "sections": [{"title": _couper("Nos cours", MAX_TITRE_LIGNE), "rows": lignes}]
            }
        }
    }, reste


def _prix(offre):
    p = offre.get("price")
    try:
        p = float(p)
    except (TypeError, ValueError):
        return ""
    return "Gratuit" if p == 0 else f"{p:.0f} CHF" if p == int(p) else f"{p:.2f} CHF"


def construire_liste_offres(offres):
    """Liste des offres et produits, lue en direct."""
    # Les prestations d'abord, les produits ensuite : c'est l'ordre de la boutique.
    tries = sorted(offres, key=lambda o: (bool(o.get("isProduct")), str(o.get("name") or "")))
    retenus = tries[:MAX_LIGNES_LISTE]
    reste = len(tries) - len(retenus)

    lignes = []
    for o in retenus:
        prix = _prix(o)
        desc = _couper(o.get("description") or "", MAX_DESCRIPTION_LIGNE - len(prix) - 3)
        lignes.append({
            "id": f"offre_{o.get('id', '')}"[:200],
            "title": _couper(o.get("name") or "Offre", MAX_TITRE_LIGNE),
            "description": _couper(f"{prix} · {desc}" if prix else desc, MAX_DESCRIPTION_LIGNE)
        })

    corps = "Voici nos offres 🛍️"
    if reste > 0:
        corps += f"\n\n(et {reste} autre{'s' if reste > 1 else ''} sur {SITE})"

    return {
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": corps},
            "footer": {"text": "Commande sur afroboost.com"},
            "action": {
                "button": _couper("Voir les offres", MAX_TITRE_BOUTON),
                "sections": [{"title": _couper("Nos offres", MAX_TITRE_LIGNE), "rows": lignes}]
            }
        }
    }, reste


# ---------------------------------------------------------------- rappel par un coach
#
# Déroulé : clic sur « Parler à un coach » -> on demande un créneau -> le message
# SUIVANT est pris tel quel comme créneau (texte brut, AUCUNE interprétation : on est
# en menu seul, pas en IA) -> confirmation + notification au coach + pause du bot.

ETAPE_ATTENTE_CRENEAU = "attente_creneau"


def construire_demande_creneau():
    """Question posée juste après le clic sur « Parler à un coach »."""
    return {
        "type": "text",
        "text": {"body": "Bien sûr 🙌\n\nQuel jour et quelle heure vous conviendraient "
                         "pour être rappelé(e) ?\nIndiquez par exemple : « mardi vers 18h »."}
    }


def construire_confirmation_creneau(creneau_brut):
    """Confirmation. Le créneau est repris TEL QUEL, sans reformulation."""
    creneau = _couper(creneau_brut, 200)
    return {
        "type": "text",
        "text": {"body": f"Merci ! Un coach vous rappellera {creneau} 🙌"}
    }


def construire_notification_coach(nom, telephone, creneau_brut):
    """Ce que le coach reçoit : WebPush + message dans sa messagerie."""
    creneau = _couper(creneau_brut, 200)
    qui = nom or "Contact WhatsApp"
    return {
        "push": {
            "titre": "📞 Demande de rappel WhatsApp",
            "corps": f"{qui} — {creneau}",
        },
        "message_messagerie": (
            f"📞 Demande de rappel\n\n"
            f"De : {qui}\n"
            f"WhatsApp : {telephone}\n"
            f"Créneau souhaité : {creneau}\n\n"
            f"Le bot est en pause pour cette personne jusqu'à ce que tu reprennes la main."
        ),
    }


def construire_repli():
    """Message quand rien ne correspond : on ramène au menu, sans IA."""
    return {
        "type": "text",
        "text": {"body": "Choisis une option ci-dessous, ou tape « coach » "
                         "pour parler à un humain."}
    }


# ---------------------------------------------------------------- aperçu (lecture seule)

def _coach_email_depuis_jwt(request: Request) -> str:
    """Identité coach par JWT signé uniquement (jamais X-User-Email, falsifiable)."""
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


@bot_router.get("/bot-whatsapp/apercu")
async def apercu_du_menu(request: Request):
    """
    V367 — APERÇU du menu, tel qu'il serait envoyé. LECTURE SEULE, AUCUN ENVOI.

    Renvoie les payloads WhatsApp exacts ET un rendu lisible, pour valider le menu
    sans écrire à personne. Réservé au coach (jeton signé) : la liste des cours et
    des offres est publique, mais l'état du bot ne l'est pas.
    """
    email = _coach_email_depuis_jwt(request)
    if not email:
        raise HTTPException(status_code=403, detail="Authentification coach requise")

    cours = await lire_cours()
    offres = await lire_offres()
    menu = construire_menu_principal()
    liste_c, reste_c = construire_liste_cours(cours)
    liste_o, reste_o = construire_liste_offres(offres)

    def lisible(charge):
        inter = charge.get("interactive") or {}
        if charge.get("type") == "text":
            return [charge["text"]["body"]]
        sortie = [inter.get("body", {}).get("text", "")]
        action = inter.get("action", {})
        for b in action.get("buttons", []):
            sortie.append(f"   [ {b['reply']['title']} ]")
        for section in action.get("sections", []):
            sortie.append(f"   — {section.get('title')} —")
            for r in section.get("rows", []):
                sortie.append(f"   • {r['title']}"
                              + (f"\n     {r['description']}" if r.get("description") else ""))
        if inter.get("footer"):
            sortie.append(f"   ({inter['footer']['text']})")
        return sortie

    return {
        "success": True,
        "bot_actif": await bot_actif(),          # False tant que le drapeau n'est pas posé
        "calcule_le": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "cours_visibles": len(cours),
            "cours_affiches": min(len(cours), MAX_LIGNES_LISTE),
            "cours_non_affiches": reste_c,
            "offres_visibles": len(offres),
            "offres_affichees": min(len(offres), MAX_LIGNES_LISTE),
            "offres_non_affichees": reste_o,
        },
        "rendu_lisible": {
            "menu": lisible(menu),
            "cours": lisible(liste_c),
            "offres": lisible(liste_o),
            "repli": lisible(construire_repli()),
        },
        "payloads_whatsapp": {"menu": menu, "cours": liste_c, "offres": liste_o},
        "aucun_envoi": True,
    }

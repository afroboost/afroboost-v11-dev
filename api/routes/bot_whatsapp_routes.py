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
from datetime import datetime, timedelta, timezone

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
# V372 : préfixe du bouton de paiement. L'identifiant de l'offre suit.
PREFIXE_PAYER = "payer_"
# Un lien Stripe déjà généré est REUTILISÉ pendant ce délai : sans cela, une
# personne indécise qui reclique trois fois crée trois lignes `payment_transactions`
# en « pending ». Décision du coach : 1 heure.
MINUTES_REUTILISATION_LIEN = 60


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


# ---------------------------------------------------------------- fiches détaillées
#
# POURQUOI CES FICHES
# Une ligne de liste WhatsApp est limitée à 24 caractères de titre et 72 de
# description : « Afroboost Silent avec B… Gratuit · Vivez une expérience uniq… ».
# Illisible pour décider. Quand la personne SÉLECTIONNE une ligne, on lui envoie
# donc un message texte COMPLET (limite : 4096 caractères, on est très en dessous).
# Tout est relu en direct : un prix modifié dans le dashboard est répercuté aussitôt.

LIEN_BOUTIQUE = f"{SITE}/#offers-slider"


def _lien_offre(offre):
    """V371 : lien qui ouvre DIRECTEMENT cette offre sur le site.

    Le site sait désormais lire `?offre=<id>` : il fait défiler jusqu'à la carte et
    la met en évidence. Il ne déclenche AUCUN paiement — un lien ne doit jamais
    ouvrir un checkout tout seul. Repli sur la boutique si l'offre n'a pas d'id.
    """
    identifiant = (offre or {}).get("id")
    return f"{SITE}/?offre={identifiant}" if identifiant else LIEN_BOUTIQUE

_LIBELLE_PALIER = {"early_bird": "prévente", "standard": "standard",
                   "last_minute": "dernière minute", "regular": "tarif normal"}


def _formater_prix(valeur):
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        return None
    if v == 0:
        return "Gratuit"
    return f"{v:.0f} CHF" if v == int(v) else f"{v:.2f} CHF"


def _bloc_tarifs(offre):
    """Un ou trois paliers, selon la configuration de l'offre.

    Le palier ACTIF est calculé par api.pricing.compute_active_price — la MÊME
    fonction que le site : le bot ne peut pas annoncer un prix différent de la
    boutique, ce qui serait le pire des bugs sur un canal de vente.
    """
    lignes = []
    progressif = bool(offre.get("progressive_pricing"))
    paliers = [("Prévente", offre.get("price_early_bird")),
               ("Standard", offre.get("price_standard")),
               ("Dernière minute", offre.get("price_last_minute"))]
    connus = [(nom, _formater_prix(v)) for nom, v in paliers if v is not None]

    # Les paliers ne sont annoncés QUE s'ils s'appliquent vraiment. Si la date de
    # référence (`countdown_date`) est absente, compute_active_price retombe sur le
    # tarif normal : afficher « Standard 33 / Dernière minute 50 » annoncerait alors
    # au client des prix qui ne seront jamais appliqués. On n'affiche donc que le
    # prix réellement pratiqué — le même que la boutique.
    palier_actif = None
    if progressif:
        try:
            from api.pricing import compute_active_price
            palier_actif = compute_active_price(offre)
        except Exception as e:
            logger.warning(f"[BOT-WA] prix actif indisponible : {e}")

    if progressif and connus and palier_actif and palier_actif.get("tier") != "regular":
        lignes.append("💰 Tarifs :")
        for nom, prix in connus:
            lignes.append(f"   • {nom} : {prix}")
        prix_actif = _formater_prix(palier_actif.get("price"))
        palier = _LIBELLE_PALIER.get(palier_actif.get("tier"), palier_actif.get("tier"))
        if prix_actif:
            lignes.append(f"   ➜ Tarif actuel : {prix_actif} ({palier})")
    elif palier_actif:
        prix = _formater_prix(palier_actif.get("price"))
        if prix:
            lignes.append(f"💰 {prix}")
    else:
        prix = _formater_prix(offre.get("price"))
        if prix:
            lignes.append(f"💰 {prix}")
    return lignes


def construire_fiche_offre(offre, cours_lies=None):
    """Message COMPLET d'une offre : nom, tarifs, description entière, lieu, date, lien."""
    lignes = [f"🛍️ *{(offre.get('name') or 'Offre').strip()}*", ""]
    lignes += _bloc_tarifs(offre)

    description = (offre.get("description") or "").strip()
    if description:
        lignes += ["", description[:1500]]

    # Lieu et prochaine séance : lus sur les cours RATTACHÉS à l'offre.
    for c in (cours_lies or []):
        lieu = (c.get("locationName") or c.get("location") or "").strip()
        if lieu:
            lignes += ["", f"📍 {lieu}"]
            break
    prochaine = _prochaine_seance(cours_lies or [])
    if prochaine:
        lignes.append(f"📅 Prochaine séance : {prochaine}")

    if offre.get("isProduct"):
        stock = offre.get("stock")
        if isinstance(stock, int) and stock >= 0:
            lignes.append(f"📦 Stock : {stock}")

    # V374 : PAS de lien « Réserver » dans le texte. La fiche est suivie d'un message
    # à boutons ; afficher en plus un lien vers le site donnait DEUX appels à
    # l'action contradictoires — l'un vers la boutique, l'autre vers Stripe. Une
    # offre, une seule action : le bouton.
    lignes += ["", "Tape « menu » pour revenir."]
    return {"type": "text", "text": {"body": "\n".join(lignes)[:4000], "preview_url": False}}


def _prochaine_seance(cours):
    """Libellé de la prochaine séance : date fixe si elle existe, sinon jour récurrent."""
    maintenant = datetime.now(timezone.utc)
    datees = []
    for c in cours:
        brut = c.get("date")
        if not brut:
            continue
        try:
            d = datetime.fromisoformat(str(brut)).replace(tzinfo=timezone.utc)
            if d.date() >= maintenant.date():
                datees.append((d, c))
        except Exception:
            continue
    if datees:
        d, c = sorted(datees)[0]
        jour = JOURS[(d.weekday() + 1) % 7]
        return f"{jour} {d.day:02d}/{d.month:02d} à {c.get('time') or ''}".strip()
    for c in cours:
        j = c.get("weekday")
        if isinstance(j, int) and 0 <= j <= 6:
            return f"tous les {JOURS[j]}s à {c.get('time') or ''}".strip()
    return None


def construire_fiche_cours(cours, offre=None):
    """Message COMPLET d'un cours : nom, quand, lieu, plan, description, lien.

    DESCRIPTION : un cours n'a AUCUN champ `description` en base (ses seuls champs
    sont name, weekday, time, date, locationName, mapsUrl, playlist, audio_tracks).
    On reprend donc celle de l'OFFRE à laquelle il est rattaché, en le disant
    (« Détail de l'offre … »). Un cours orphelin — il en reste — affiche simplement
    nom, date et lieu, sans erreur ni ligne vide.
    """
    lignes = [f"📅 *{(cours.get('name') or 'Cours').strip()}*", ""]
    quand = _prochaine_seance([cours])
    if quand:
        lignes.append(f"🗓️ {quand}")
    elif cours.get("time"):
        lignes.append(f"🗓️ {cours.get('time')}")
    lieu = (cours.get("locationName") or cours.get("location") or "").strip()
    if lieu:
        lignes.append(f"📍 {lieu}")
    plan = (cours.get("mapsUrl") or "").strip()
    if plan.startswith("http"):
        lignes.append(f"🗺️ {plan}")

    if offre:
        prix = _bloc_tarifs(offre)
        if prix:
            lignes += [""] + prix
        description = (offre.get("description") or "").strip()
        if description:
            lignes += ["", f"_Détail de l'offre « {(offre.get('name') or '').strip()[:60]} » :_",
                       description[:1500]]

    lien = _lien_offre(offre) if offre else SITE
    lignes += ["", f"👉 Réserver : {lien}", "", "Tape « menu » pour revenir."]
    return {"type": "text", "text": {"body": "\n".join(lignes)[:4000], "preview_url": True}}


def construire_boutons_offre(offre, payante):
    """Boutons envoyés JUSTE APRÈS la fiche.

    Pourquoi un second message : le corps d'un message à boutons est limité à 1024
    caractères par WhatsApp, alors qu'une description d'offre en fait couramment
    1500. Tronquer la fiche pour loger un bouton reviendrait à recréer le problème
    qu'on vient de corriger. On envoie donc la fiche entière, puis les boutons.

    `payante` décide du libellé : on n'écrit jamais « payer » là où le clic mène en
    réalité sur le site (offre gratuite, ou à variantes qu'on ne peut pas choisir ici).
    """
    titre = "💳 Réserver et payer" if payante else "🌐 Voir sur le site"
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": "Que souhaitez-vous faire ?"},
            "action": {"buttons": [
                {"type": "reply", "reply": {"id": f"{PREFIXE_PAYER}{offre.get('id','')}",
                                            "title": _couper(titre, MAX_TITRE_BOUTON)}},
                {"type": "reply", "reply": {"id": BOUTON_OFFRES,
                                            "title": _couper("🛍️ Autres offres", MAX_TITRE_BOUTON)}},
            ]}
        }
    }


def offre_payable_par_lien(offre):
    """Cette offre peut-elle être payée directement depuis WhatsApp ?

    NON dans deux cas, et le bouton le dit alors honnêtement :
      - prix nul : le parcours gratuit du site passe par des étapes (formulaire,
        preuve sociale Instagram) qu'on ne peut pas reproduire ici ;
      - offre à VARIANTES (taille, couleur) : payer sans choisir produirait une
        commande inexploitable.
    C'est la même règle que le site (`v225IsDirectCheckout` : prix > 0).
    """
    if offre.get("variants"):
        return False
    try:
        from api.pricing import compute_active_price
        return float(compute_active_price(offre).get("price") or 0) > 0
    except Exception:
        return float(offre.get("price") or 0) > 0


async def creer_lien_paiement(telephone, offre, etat):
    """Crée (ou RÉUTILISE) le lien Stripe de cette offre. Renvoie (payload, cree).

    APPELÉ UNIQUEMENT AU CLIC sur « Réserver et payer » — jamais à l'affichage
    d'une fiche. Consulter dix offres ne crée donc aucune session ni aucune ligne
    `payment_transactions`.

    Le montant vient de compute_active_price côté SERVEUR : le bot ne transmet
    jamais un prix venu du client.
    """
    identifiant = offre.get("id") or ""
    # Réutilisation : même offre, même personne, moins d'une heure.
    ancien = etat.get("dernier_lien_stripe")
    if ancien and etat.get("dernier_lien_offre") == identifiant:
        try:
            pose = datetime.fromisoformat(str(etat.get("dernier_lien_le")).replace("Z", "+00:00"))
            if pose.tzinfo is None:
                pose = pose.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - pose < timedelta(minutes=MINUTES_REUTILISATION_LIEN):
                logger.info(f"[BOT-WA] lien Stripe réutilisé pour …{telephone[-4:]}")
                return _message_lien(offre, ancien), False
        except Exception:
            pass

    from api.server import create_checkout_session, CreateCheckoutRequest
    from api.pricing import compute_active_price
    montant = float(compute_active_price(offre).get("price") or 0)
    requete = CreateCheckoutRequest(
        productName=(offre.get("name") or "Offre Afroboost").strip()[:120],
        amount=montant,
        originUrl=SITE,
        offerId=identifiant,
        quantity=1,
        reservationData={"source": "bot_whatsapp", "telephone": telephone},
    )
    resultat = await create_checkout_session(requete)
    url = (resultat or {}).get("url") or (resultat or {}).get("checkout_url") or ""
    if not url:
        logger.error(f"[BOT-WA] Stripe n'a pas renvoyé d'URL : {str(resultat)[:200]}")
        return {"type": "text", "text": {"body":
                "Le lien de paiement n'a pas pu être créé. Réessaie dans un instant, "
                f"ou passe par {_lien_offre(offre)}", "preview_url": True}}, False
    await ecrire_etat(telephone, {
        "dernier_lien_stripe": url,
        "dernier_lien_offre": identifiant,
        "dernier_lien_le": datetime.now(timezone.utc).isoformat(),
        # V433 : on garde AUSSI l'identifiant de session Stripe. C'est lui qui
        # permet plus tard de savoir si la personne a payé — sans quoi une
        # relance pourrait partir vers quelqu'un qui a déjà réglé. Champ
        # purement additif : rien de ce qui existait ne le lit.
        "dernier_lien_session": (resultat or {}).get("sessionId"),
    })
    return _message_lien(offre, url), True


def _message_lien(offre, url):
    """V374 : le lien de paiement derrière un BOUTON, jamais en texte brut.

    Une URL Stripe fait ~130 caractères d'apparence hostile ; collée dans la
    conversation, elle donne l'air d'un message frauduleux. Le format `cta_url`
    affiche un bouton propre qui ouvre l'URL — c'est EXACTEMENT le mécanisme déjà
    utilisé en production par les campagnes (« Voir sur Instagram », V163.6), avec
    ici un `body` seul, sans image d'en-tête.

    Contraintes de la plateforme, respectées : `display_text` <= 20 caractères,
    `body` <= 1024. Si Meta refusait ce format, `envoyer_payload` bascule
    automatiquement sur un message texte contenant l'URL — la personne ne se
    retrouve jamais sans moyen de payer.
    """
    from api.pricing import compute_active_price
    try:
        prix = _formater_prix(compute_active_price(offre).get("price"))
    except Exception:
        prix = _formater_prix(offre.get("price"))
    nom = (offre.get("name") or "").strip()[:70]
    corps = (f"🔒 Paiement sécurisé — *{nom}*" + (f", {prix}" if prix else "") + ".\n"
             "⏳ Valable 24 h et à usage unique.\n"
             "Un nouveau clic sur « Réserver » régénère un lien.")
    return {
        "type": "interactive",
        "interactive": {
            "type": "cta_url",
            "body": {"text": corps[:1024]},
            "action": {"name": "cta_url", "parameters": {
                "display_text": _couper("💳 Payer maintenant", MAX_TITRE_BOUTON),
                "url": url,
            }},
        },
        # Repli utilisé UNIQUEMENT si Meta refuse le format interactif.
        "_repli_texte": f"{corps}\n\n{url}",
    }


async def lire_offre_du_cours(identifiant_cours):
    """L'offre qui référence ce cours, s'il y en a une (sinon None)."""
    return await db.offers.find_one({"linked_course_ids": identifiant_cours}, {"_id": 0})


async def lire_offre(identifiant):
    return await db.offers.find_one({"id": identifiant}, {"_id": 0})


async def lire_un_cours(identifiant):
    return await db.courses.find_one({"id": identifiant}, {"_id": 0})


async def lire_cours_de_offre(offre):
    ids = offre.get("linked_course_ids") or []
    if not ids:
        return []
    return await db.courses.find({"id": {"$in": ids}}, {"_id": 0}).to_list(50)


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


# ================================================================ ÉTAT PAR PERSONNE
#
# Collection `bot_whatsapp_etat` : UN document par numéro, validé par le coach.
#   telephone (clé unique) · nom · etape · creneau_demande · pause_jusqu_a
#   derniere_interaction_le · mis_a_jour_le
# Aucune autre collection n'en dépend. Rollback : db.bot_whatsapp_etat.drop().

COLLECTION_ETAT = "bot_whatsapp_etat"

# V369b : dernière erreur rencontrée par la greffe du webhook, gardée EN MÉMOIRE
# (aucune écriture en base) et exposée par /api/bot-whatsapp/apercu. Sans accès aux
# logs du conteneur, une exception avalée est invisible : c'est exactement ce qui a
# masqué le NameError de V369 pendant un test complet.
DERNIERE_ERREUR = None
JOURS_DE_PAUSE = 7          # décision du coach : 7 jours, levée par un bouton

# GARDE-FOU DE TEST : tant que cette liste n'est PAS vide, le bot ne répond QU'À ces
# numéros. Elle protège même si le drapeau passait à ON par erreur. Comparaison sur
# les 9 derniers chiffres, comme la déduplication des campagnes (V162).
NUMEROS_AUTORISES = ["765203363"]     # le numéro du coach, et lui seul


def _cle_numero(telephone):
    chiffres = re.sub(r"\D", "", str(telephone or ""))
    return chiffres[-9:] if len(chiffres) >= 9 else chiffres


def numero_autorise(telephone) -> bool:
    """Liste blanche de test. Vide = tout le monde (ouverture réelle, plus tard)."""
    if not NUMEROS_AUTORISES:
        return True
    return _cle_numero(telephone) in {_cle_numero(n) for n in NUMEROS_AUTORISES}


async def lire_etat(telephone: str) -> dict:
    try:
        return await db[COLLECTION_ETAT].find_one({"telephone": telephone}, {"_id": 0}) or {}
    except Exception as e:
        logger.warning(f"[BOT-WA] état illisible pour {telephone[-4:]} : {e}")
        return {}


async def ecrire_etat(telephone: str, champs: dict):
    champs = dict(champs)
    champs["mis_a_jour_le"] = datetime.now(timezone.utc).isoformat()
    await db[COLLECTION_ETAT].update_one(
        {"telephone": telephone}, {"$set": champs}, upsert=True)


async def en_pause(etat: dict) -> bool:
    """La pause l'emporte sur tout (sauf STOP) : décision du coach."""
    jusqu_a = etat.get("pause_jusqu_a")
    if not jusqu_a:
        return False
    try:
        dt = datetime.fromisoformat(str(jusqu_a).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except Exception:
        return False


# ================================================================ DÉCISION DU BOT

async def decider_reponse(telephone: str, texte: str, bouton: str, nom: str = None):
    """Que répondre à ce message ? Fonction de DÉCISION : elle n'envoie rien.

    Renvoie (payload_a_envoyer | None, notification_coach | None).
    None = le bot se tait (personne en pause, ou message hors liste blanche).

    ORDRE DE PRIORITÉ (le STOP V332 est traité AVANT, dans le webhook) :
        1. pause coach  ->  silence total
        2. clic sur un bouton du menu
        3. attente d'un créneau  ->  le message est pris tel quel
        4. mot-clé « coach »
        5. tout le reste  ->  menu, jamais l'IA
    """
    etat = await lire_etat(telephone)
    await ecrire_etat(telephone, {
        "nom": nom or etat.get("nom"),
        "derniere_interaction_le": datetime.now(timezone.utc).isoformat(),
    })

    # 1. PAUSE : le bot se tait, y compris si la personne écrit « menu ».
    if await en_pause(etat):
        logger.info(f"[BOT-WA] silence (pause active) pour …{telephone[-4:]}")
        return None, None

    mot = (texte or "").strip().lower()

    # 2. CLIC SUR UN BOUTON
    if bouton == BOUTON_COURS:
        return construire_liste_cours(await lire_cours())[0], None
    if bouton == BOUTON_OFFRES:
        return construire_liste_offres(await lire_offres())[0], None
    if bouton == BOUTON_COACH or mot in ("coach", "humain", "parler a un coach", "parler à un coach"):
        await ecrire_etat(telephone, {"etape": ETAPE_ATTENTE_CRENEAU})
        return construire_demande_creneau(), None

    # 3. LE MESSAGE SUIVANT EST LE CRÉNEAU — pris TEL QUEL, aucune interprétation
    if etat.get("etape") == ETAPE_ATTENTE_CRENEAU and texte:
        fin_pause = datetime.now(timezone.utc) + timedelta(days=JOURS_DE_PAUSE)
        await ecrire_etat(telephone, {
            "etape": "",
            "creneau_demande": texte.strip()[:300],
            "pause_jusqu_a": fin_pause.isoformat(),
        })
        logger.info(f"[BOT-WA] demande de rappel pour …{telephone[-4:]}, bot en pause "
                    f"{JOURS_DE_PAUSE} jours")
        return (construire_confirmation_creneau(texte.strip()),
                construire_notification_coach(nom or etat.get("nom"), telephone, texte.strip()))

    # 4. SÉLECTION D'UNE LIGNE -> fiche détaillée. Les listes WhatsApp coupent à
    #    24/72 caractères ; la fiche donne le texte entier, les tarifs et le lien.
    #    Aucun tunnel d'achat dans WhatsApp : la réservation se fait sur le site.
    # V372 : CLIC SUR « Réserver et payer ». C'est LE seul endroit qui crée une
    # session Stripe — donc aucune ligne `payment_transactions` n'apparaît en
    # consultant une fiche, seulement en demandant explicitement à payer.
    if bouton and bouton.startswith(PREFIXE_PAYER):
        offre = await lire_offre(bouton[len(PREFIXE_PAYER):])
        if not offre:
            return construire_repli(), None
        if not offre_payable_par_lien(offre):
            # Gratuit ou à variantes : on renvoie vers le site, sans rien créer.
            return {"type": "text", "text": {"body":
                    f"Cette offre se réserve sur le site 👇\n\n{_lien_offre(offre)}\n\n"
                    "Tape « menu » pour revenir.", "preview_url": True}}, None
        message, _ = await creer_lien_paiement(telephone, offre, etat)
        return message, None

    if bouton and bouton.startswith("offre_"):
        offre = await lire_offre(bouton[len("offre_"):])
        if offre:
            # Deux messages : la fiche ENTIÈRE, puis les boutons (le corps d'un
            # message à boutons est plafonné à 1024 caractères par WhatsApp).
            return [construire_fiche_offre(offre, await lire_cours_de_offre(offre)),
                    construire_boutons_offre(offre, offre_payable_par_lien(offre))], None
        return construire_repli(), None
    if bouton and bouton.startswith("cours_"):
        identifiant = bouton[len("cours_"):]
        cours = await lire_un_cours(identifiant)
        if cours:
            return construire_fiche_cours(cours, await lire_offre_du_cours(identifiant)), None
        return construire_repli(), None

    # 5. TOUT LE RESTE : le menu. JAMAIS l'IA — décision du coach (menu seul).
    if mot in ("menu", "bonjour", "salut", "hello", "hi", "start", "démarrer", "demarrer"):
        return construire_menu_principal(nom or etat.get("nom")), None
    return construire_repli(), None


async def envoyer_payload(telephone: str, payload: dict) -> dict:
    """Envoie UN message construit par le bot. N'utilise NI le template des campagnes,
    NI launch_campaign : appel direct à l'API Meta, sur le chemin des réponses.

    La fenêtre des 24 h est respectée par construction : le bot ne parle QUE pour
    répondre à un message entrant.
    """
    import httpx
    from api.server import _get_whatsapp_config          # import différé (circularité)

    config = await _get_whatsapp_config()
    if not config or config.get("api_mode") != "meta":
        logger.warning("[BOT-WA] pas de config Meta — aucun envoi")
        return {"status": "error", "error": "config Meta absente"}

    numero = re.sub(r"\D", "", telephone or "")
    corps = {"messaging_product": "whatsapp", "to": numero}
    corps.update(payload)
    url = (f"https://graph.facebook.com/{config.get('api_version', 'v21.0')}"
           f"/{config['phone_number_id']}/messages")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers={
            "Authorization": f"Bearer {config['access_token']}",
            "Content-Type": "application/json"}, json=corps)
    ok = r.status_code < 400
    logger.info(f"[BOT-WA] envoi à …{numero[-4:]} : HTTP {r.status_code}")
    if not ok:
        logger.error(f"[BOT-WA] refus Meta : {r.text[:300]}")
        # V374 : REPLI. Si le bouton `cta_url` est refusé, on renvoie le lien en
        # texte : mieux vaut une URL brute qu'une personne sans moyen de payer.
        if repli:
            logger.warning("[BOT-WA] bouton refusé — repli sur le lien en texte")
            async with httpx.AsyncClient(timeout=30.0) as client2:
                r2 = await client2.post(url, headers={
                    "Authorization": f"Bearer {config['access_token']}",
                    "Content-Type": "application/json"}, json={
                        "messaging_product": "whatsapp", "to": numero,
                        "type": "text", "text": {"body": repli[:4000], "preview_url": True}})
            return {"status": "success" if r2.status_code < 400 else "error",
                    "http": r2.status_code, "repli": True}
    return {"status": "success" if ok else "error", "http": r.status_code}


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
        "derniere_erreur": DERNIERE_ERREUR,     # V369b : None = aucune erreur avalée
        "aucun_envoi": True,
    }


@bot_router.get("/bot-whatsapp/pauses")
async def lister_pauses(request: Request):
    """V369 — qui attend un rappel ? LECTURE SEULE, réservé au coach.

    Alimente le futur bouton « Réactiver le bot » du dashboard. Renvoie le numéro,
    le nom, le créneau demandé tel qu'écrit, et la fin de pause.
    """
    if not _coach_email_depuis_jwt(request):
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    maintenant = datetime.now(timezone.utc)
    sortie = []
    for e in await db[COLLECTION_ETAT].find({}, {"_id": 0}).to_list(500):
        actif = False
        try:
            if e.get("pause_jusqu_a"):
                dt = datetime.fromisoformat(str(e["pause_jusqu_a"]).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                actif = dt > maintenant
        except Exception:
            pass
        if actif:
            sortie.append({
                "telephone": e.get("telephone"),
                "nom": e.get("nom"),
                "creneau_demande": e.get("creneau_demande"),
                "pause_jusqu_a": e.get("pause_jusqu_a"),
            })
    return {"success": True, "en_pause": len(sortie), "personnes": sortie}


@bot_router.post("/bot-whatsapp/reactiver")
async def reactiver_le_bot(request: Request):
    """V369 — « Réactiver le bot » : lève la pause pour UNE personne.

    Écrit UNIQUEMENT dans bot_whatsapp_etat, et seulement le champ `pause_jusqu_a`.
    N'envoie AUCUN message : la personne ne reçoit rien ; le bot répondra simplement
    à son prochain message. Réservé au coach (jeton signé).
    """
    if not _coach_email_depuis_jwt(request):
        raise HTTPException(status_code=403, detail="Authentification coach requise")
    corps = await request.json()
    telephone = (corps.get("telephone") or "").strip()
    if not telephone:
        raise HTTPException(status_code=400, detail="telephone requis")
    r = await db[COLLECTION_ETAT].update_one(
        {"telephone": telephone},
        {"$set": {"pause_jusqu_a": None, "etape": "",
                  "mis_a_jour_le": datetime.now(timezone.utc).isoformat()}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Aucun état pour ce numéro")
    logger.info(f"[BOT-WA] pause levée pour …{telephone[-4:]}")
    return {"success": True, "telephone": telephone, "pause_levee": True,
            "aucun_message_envoye": True}

"""
V433 — WhatsApp : répondre à une intention d'ACHAT par un VRAI lien de paiement,
et ne plus jamais signer « [Votre Nom] ».

CE QUI S'EST PASSÉ (fil « Deborah Akaya », 10/08/2026, mesuré en base)
---------------------------------------------------------------------
La cliente demandait la prévente du casque Silent (21-22 août, Montbenon) et
« le lien pour faire le nécessaire ». La réponse partie automatiquement :

    « … je vous recommande de visiter le site officiel de l'événement ou de
      contacter directement l'organisateur … Cordialement, [Votre Nom] »

Vente perdue, et un placeholder de brouillon envoyé à une vraie cliente.

LA CAUSE, VÉRIFIÉE — ce n'est PAS le bot à menus
------------------------------------------------
Le bot à boutons (`bot_whatsapp_routes`) ne répond qu'aux numéros de sa liste
blanche (le coach seul) : il n'a jamais vu ce message. C'est le flux IA du
webhook Meta qui a répondu — et `ai_config.systemPrompt` est **VIDE** en base.
GPT-4o-mini recevait donc le message d'une cliente sans la moindre instruction :
il ignorait qu'il EST Afroboost, d'où « contactez l'organisateur » (Afroboost
est l'organisateur) et la signature de brouillon.

TROIS COUCHES, DE LA PLUS SÛRE À LA PLUS GÉNÉRALE
-------------------------------------------------
1. `intention_achat()` + `repondre_achat()` — DÉTERMINISTE, sans IA. Un message
   qui parle d'achat reçoit le lien de paiement réel de l'offre. Aucune
   formulation n'est laissée au hasard : c'est la couche qui rattrape la vente.
2. `PROMPT_BASE` — l'identité qui manquait, imposée en CODE et non en base.
   Posée en base, elle serait perdue au premier enregistrement du dashboard ;
   ici elle est versionnée et revient avec un `git revert`.
3. `assainir()` — dernier filet sur la sortie de l'IA : plus aucun placeholder
   ni « contactez l'organisateur » ne peut sortir, quoi qu'ait produit le modèle.

Aucune de ces couches n'envoie quoi que ce soit toute seule : elles CONSTRUISENT
des textes. L'envoi reste au webhook, exactement là où il était.
"""
import os
import re
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

db = None


def init_vente_db(database):
    global db
    db = database


# L'offre « Afroboost Silent avec Bassi » — casque Silent du Laff Festival.
OFFRE_SILENT = "76a78f31-614a-415a-876b-9d2d1a4b441c"

SITE = "https://afroboost.com"

SIGNATURE = "L'équipe Afroboost"

# Drapeau de la relance (point 3). ABSENT de la base = OFF : la relance ne peut
# pas s'allumer par accident, il faut un geste explicite du propriétaire.
DRAPEAU_RELANCE = "RELANCE_ACHAT_ENABLED"

COLLECTION_RELANCES = "relances_achat"

# Délai avant la relance, et fenêtre au-delà de laquelle on renonce : relancer
# quelqu'un une semaine après serait du démarchage, pas un rappel.
HEURES_AVANT_RELANCE = 24
HEURES_ABANDON = 96

# Un paiement peut être marqué de plusieurs façons selon le chemin (Stripe
# direct, pawaPay, boost). On les accepte toutes : se tromper ici enverrait une
# relance à quelqu'un qui a DÉJÀ payé — la faute la plus grave de ce module.
STATUTS_PAYES = {"paid", "completed", "complete", "succeeded", "success"}


# ---------------------------------------------------------------------------
# 1. DÉTECTION DE L'INTENTION D'ACHAT
# ---------------------------------------------------------------------------

# Mots qui, à eux seuls, disent l'intention d'acheter ou de réserver.
_MOTS_ACHAT = [
    "acheter", "achat", "acheté", "achete",
    "prévente", "prevente", "pré-vente", "pre-vente", "prévendre",
    "précommande", "precommande", "pré-commande",
    "réserver", "reserver", "réservation", "reservation", "réserve",
    "payer", "paiement", "paypal", "twint", "carte",
    "billet", "billets", "ticket", "tickets", "place", "places",
    "inscrire", "inscription", "commander", "commande",
    "casque", "silent", "prix", "combien", "tarif", "coûte", "coute",
]

# « lien » seul est ambigu (on peut demander le lien d'une vidéo). On ne le
# retient donc QUE s'il accompagne un mot de contexte — sauf « le lien pour »,
# tournure du message réel de Deborah, qui ne laisse aucun doute.
_MOTS_LIEN = ["lien", "link", "url"]
_CONTEXTE_LIEN = ["pour", "afin", "réserv", "reserv", "achat", "acheter", "payer",
                  "paiement", "inscri", "casque", "silent", "prévente", "prevente",
                  "commande", "billet", "place", "nécessaire", "necessaire"]


def _sans_accents_minuscule(texte):
    """Compare sans accents : « réserver » et « reserver » doivent matcher pareil."""
    t = (texte or "").lower()
    for avant, apres in (("à", "a"), ("â", "a"), ("ä", "a"), ("é", "e"), ("è", "e"),
                         ("ê", "e"), ("ë", "e"), ("î", "i"), ("ï", "i"), ("ô", "o"),
                         ("ö", "o"), ("ù", "u"), ("û", "u"), ("ü", "u"), ("ç", "c")):
        t = t.replace(avant, apres)
    return t


def intention_achat(texte) -> bool:
    """Ce message parle-t-il d'acheter, de réserver, ou demande-t-il « le lien » ?

    Volontairement LARGE : le coût d'un faux positif est d'envoyer poliment un
    lien de réservation à quelqu'un qui n'achetait pas. Le coût d'un faux
    négatif, lui, est une vente perdue — c'est exactement ce qui vient
    d'arriver. L'asymétrie commande de pencher du côté large.
    """
    if not texte:
        return False
    t = _sans_accents_minuscule(texte)

    # Un « STOP » ne doit JAMAIS être lu comme une intention d'achat : il est
    # traité en amont (V332), mais une garde ici coûte une ligne et évite une
    # catastrophe si l'ordre des blocs changeait un jour.
    if t.strip() in ("stop", "stop!", "arret", "arreter", "desabonnement"):
        return False

    for mot in _MOTS_ACHAT:
        if _sans_accents_minuscule(mot) in t:
            return True

    if any(m in t for m in _MOTS_LIEN):
        if any(_sans_accents_minuscule(c) in t for c in _CONTEXTE_LIEN):
            return True

    return False


# ---------------------------------------------------------------------------
# 2. L'IDENTITÉ QUI MANQUAIT À L'IA
# ---------------------------------------------------------------------------

PROMPT_BASE = f"""Tu es l'assistant WhatsApp officiel d'AFROBOOST (afroboost.com),
studio de fitness et de danse afrobeat basé en Suisse, à Lausanne.

RÈGLES ABSOLUES :
- Afroboost EST l'organisateur de ses événements. Ne dis JAMAIS « contactez
  l'organisateur », « le site officiel de l'événement » ou « renseignez-vous
  auprès des organisateurs » : c'est à TOI que la personne s'adresse.
- Ne renvoie jamais vers un site tiers. Le seul site est {SITE}.
- N'invente jamais un prix, une date ni un lieu. Si tu ne sais pas, dis-le
  simplement et propose de faire suivre au coach.
- Termine TOUJOURS par la signature exacte : « {SIGNATURE} ».
- N'écris JAMAIS de champ à compléter entre crochets ([Votre Nom], [Nom],
  [Signature]…). Tu écris un message envoyé tel quel à un vrai client.
- Réponds en français, chaleureusement, en 6 lignes maximum. WhatsApp, pas une
  lettre administrative : pas de « Cordialement », pas d'objet.
"""


# ---------------------------------------------------------------------------
# 3. ASSAINISSEMENT DE LA SORTIE
# ---------------------------------------------------------------------------

# Placeholders explicitement listés — on ne supprime PAS tout ce qui est entre
# crochets : « [Image reçue] » et consorts sont légitimes dans ce produit.
_PLACEHOLDERS = re.compile(
    r"\[\s*(?:votre|ton|mon|le|la)?\s*"
    r"(?:nom|pr[ée]nom|signature|poste|fonction|entreprise|soci[ée]t[ée]|"
    r"your\s+name|name|company|title)"
    r"[^\]]{0,30}\]",
    re.IGNORECASE)

# Formules de politesse épistolaires, avec ou sans placeholder derrière.
_FORMULES = re.compile(
    r"(?:^|\n)\s*(?:bien\s+)?(?:cordialement|sinc[èe]rement|amicalement|"
    r"salutations(?:\s+distingu[ée]es)?|bien\s+[àa]\s+vous|"
    r"respectueusement|best\s+regards|regards)\s*[,.!]?\s*",
    re.IGNORECASE)

# Le renvoi vers un tiers — le cœur de la vente perdue.
_RENVOIS_TIERS = [
    (re.compile(r"contact(?:er|ez)?\s+(?:directement\s+)?(?:l['’]|les?\s+)?organisateur[s]?", re.I),
     "nous écrire ici"),
    (re.compile(r"(?:le\s+)?site\s+officiel\s+de\s+l['’][ée]v[ée]nement", re.I),
     SITE),
    # Le « via » est avalé avec le groupe : sans lui, « nous écrire ici via ce
    # numéro WhatsApp » reste redondant une fois la première règle appliquée.
    (re.compile(r"\s*(?:via|par)\s+(?:leurs?|ses)\s+canaux\s+de\s+communication", re.I),
     ""),
]


def assainir(texte):
    """Dernier filet avant l'envoi : ni placeholder, ni renvoi vers un tiers.

    Ce filet existe parce qu'un `systemPrompt`, si bien écrit soit-il, reste une
    SUGGESTION faite à un modèle : rien ne garantit qu'il l'applique à chaque
    fois. Ce qui doit être impossible doit être rendu impossible par le code.
    """
    if not texte:
        return texte

    t = str(texte)

    for motif, remplacement in _RENVOIS_TIERS:
        t = motif.sub(remplacement, t)

    t = _PLACEHOLDERS.sub("", t)
    t = _FORMULES.sub("\n", t)

    # Nettoyage des blancs laissés par les suppressions.
    # Uniquement la virgule et le point : en français, l'espace AVANT « ! » « ? »
    # « : » « ; » est correcte, la retirer serait une faute de typographie.
    t = re.sub(r"[ \t]+([,.])", r"\1", t)      # « ici . » -> « ici. »
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    # La signature, une seule fois, à la fin.
    if SIGNATURE.lower() not in t.lower():
        t = f"{t}\n\n{SIGNATURE}" if t else SIGNATURE

    return t


# ---------------------------------------------------------------------------
# 4. LA RÉPONSE D'ACHAT : LE VRAI LIEN DE PAIEMENT
# ---------------------------------------------------------------------------

def _prenom(nom):
    """« Deborah Akaya » -> « Deborah ». Sert à ouvrir le message chaleureusement."""
    propre = re.sub(r"^\s*[\U0001F300-\U0001FAFF☀-➿]\s*", "", str(nom or "")).strip()
    return propre.split(" ")[0] if propre else ""


def _formater_prix(valeur):
    try:
        v = float(valeur)
    except (TypeError, ValueError):
        return ""
    return f"{v:.2f} CHF".replace(".00 ", ".– ")


_LIBELLE_PALIER = {"early_bird": "prévente", "standard": "tarif standard",
                   "last_minute": "dernière minute", "regular": "tarif normal"}


async def _seances_de_offre(offre):
    """Dates et lieu, lus des cours liés — jamais inventés (règle du PROMPT_BASE)."""
    lignes, lieu = [], (offre.get("location") or "").strip()
    for cid in (offre.get("linked_course_ids") or [])[:4]:
        try:
            c = await db.courses.find_one({"id": cid}, {"_id": 0, "date": 1, "time": 1, "location": 1})
        except Exception:
            c = None
        if not c:
            continue
        if not lieu:
            lieu = (c.get("location") or "").strip()
        d = str(c.get("date") or "")
        try:
            jour = datetime.strptime(d, "%Y-%m-%d")
            d = f"{jour.day} {['janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre'][jour.month - 1]}"
        except Exception:
            pass
        lignes.append(f"{d} à {c.get('time')}" if c.get("time") else d)
    return lignes, lieu


async def construire_texte_achat(offre, nom=None):
    """Le message qui accompagne le lien. Prix et dates viennent du SERVEUR."""
    from api.pricing import compute_active_price

    calcul = compute_active_price(offre) or {}
    prix = _formater_prix(calcul.get("price"))
    palier = _LIBELLE_PALIER.get(calcul.get("tier") or "", "")

    seances, lieu = await _seances_de_offre(offre)
    prenom = _prenom(nom)

    lignes = [f"Bonjour {prenom} 👋" if prenom else "Bonjour 👋", ""]
    lignes.append("Oui, la réservation est ouverte — c'est nous qui organisons, "
                  "tout se fait ici. 🎧")
    lignes.append("")
    if seances:
        lignes.append("📅 " + " et ".join(seances))
    if lieu:
        lignes.append("📍 " + lieu)
    if prix:
        lignes.append(f"🎟️ {prix}" + (f" ({palier})" if palier else ""))
    lignes.append("")
    lignes.append("Le cours est offert : la réservation couvre le casque Silent.")
    lignes.append("Le lien de paiement est juste en dessous 👇")
    lignes.append("")
    lignes.append(SIGNATURE)
    return "\n".join(lignes)


async def repondre_achat(telephone, nom=None, offre_id=OFFRE_SILENT):
    """Construit la réponse complète : le message + le LIEN DE PAIEMENT RÉEL.

    Renvoie `(payloads, texte_pour_la_messagerie, session_id)` ou `(None, ...)`
    si l'offre est introuvable — auquel cas l'appelant retombe sur l'IA plutôt
    que de laisser la personne sans réponse.

    N'ENVOIE RIEN : c'est l'appelant qui envoie. Cette séparation est ce qui
    rend le module testable hors ligne, sans jamais écrire à un vrai numéro.
    """
    offre = await db.offers.find_one({"id": offre_id}, {"_id": 0})
    if not offre:
        logger.warning(f"[V433] offre {offre_id[:8]} introuvable — repli sur l'IA")
        return None, None, None

    texte = await construire_texte_achat(offre, nom)

    from api.routes.bot_whatsapp_routes import (
        lire_etat, ecrire_etat, creer_lien_paiement, offre_payable_par_lien, _lien_offre)

    payloads = [{"type": "text", "text": {"body": texte[:4096], "preview_url": False}}]
    session_id = None

    if offre_payable_par_lien(offre):
        etat = await lire_etat(telephone)
        # `creer_lien_paiement` REUTILISE le lien de la dernière heure pour la même
        # personne et la même offre : deux messages d'affilée ne créent pas deux
        # sessions Stripe. C'est le comportement déjà en service pour le bouton du bot.
        payload_lien, _cree = await creer_lien_paiement(telephone, offre, etat)
        payloads.append(payload_lien)
        etat_apres = await lire_etat(telephone)
        session_id = etat_apres.get("dernier_lien_session")
    else:
        # Prix nul ou offre à variantes : pas de paiement direct possible. On
        # envoie alors le lien PROFOND vers la carte de l'offre (V371) — surtout
        # pas la page d'accueil, qui est précisément ce qu'il fallait éviter.
        payloads.append({"type": "text", "text": {
            "body": f"Pour réserver : {_lien_offre(offre)}", "preview_url": True}})

    return payloads, texte, session_id


# ---------------------------------------------------------------------------
# 5. RELANCE AUTOMATIQUE — CONSTRUITE, MAIS ÉTEINTE
# ---------------------------------------------------------------------------

async def relance_active() -> bool:
    """Drapeau ABSENT = OFF. La relance ne s'allume que par un geste explicite."""
    try:
        f = await db.feature_flags.find_one({"id": "feature_flags"}, {"_id": 0}) or {}
        return f.get(DRAPEAU_RELANCE) is True
    except Exception:
        return False


async def noter_intention(telephone, nom=None, offre_id=OFFRE_SILENT, session_id=None):
    """Mémorise « cette personne a demandé le lien » — pour une éventuelle relance.

    Écrit TOUJOURS, même drapeau éteint : la trace ne coûte rien et permet, le
    jour de l'activation, de savoir qui relancer. Ce qui est sous drapeau, c'est
    l'ENVOI, jamais la mémoire.

    `_id` = téléphone + offre : une personne ne peut pas accumuler dix relances
    en écrivant dix fois. C'est le verrou anti-spam, porté par la base plutôt
    que par du code qui pourrait oublier de vérifier.
    """
    cle = f"{telephone}|{offre_id}"
    maintenant = datetime.now(timezone.utc)
    try:
        await db[COLLECTION_RELANCES].update_one(
            {"_id": cle},
            {"$setOnInsert": {
                "telephone": telephone,
                "offre_id": offre_id,
                "nom": nom,
                "cree_le": maintenant.isoformat(),
                "cree_dt": maintenant,
                "relance_envoyee": False,
                "relance_le": None,
            },
             "$set": {"session_id": session_id or None,
                      "dernier_interet_le": maintenant.isoformat()}},
            upsert=True)
    except Exception as e:
        logger.warning(f"[V433] trace de relance non écrite : {e}")


async def _a_paye(ligne) -> bool:
    """Cette personne a-t-elle payé ? En cas de DOUTE, on répond OUI.

    Se tromper dans ce sens ne coûte qu'une relance non envoyée. Se tromper dans
    l'autre envoie « tu n'as pas payé » à quelqu'un qui a payé.
    """
    sid = ligne.get("session_id")
    if sid:
        try:
            t = await db.payment_transactions.find_one({"session_id": sid},
                                                       {"_id": 0, "payment_status": 1})
            if t and str(t.get("payment_status") or "").lower() in STATUTS_PAYES:
                return True
        except Exception:
            return True   # doute -> on s'abstient de relancer

    # Filet : un paiement passé par un AUTRE chemin (site, lien partagé) pour la
    # même offre, après la marque d'intérêt.
    try:
        depuis = ligne.get("cree_dt") or datetime.now(timezone.utc) - timedelta(days=30)
        recentes = await db.payment_transactions.find(
            {"metadata.offer_id": ligne.get("offre_id")},
            {"_id": 0, "payment_status": 1, "created_at": 1, "metadata": 1}
        ).sort("created_at", -1).to_list(200)
        tel = re.sub(r"\D", "", str(ligne.get("telephone") or ""))[-9:]
        for t in recentes:
            if str(t.get("payment_status") or "").lower() not in STATUTS_PAYES:
                continue
            brut = re.sub(r"\D", "", str(t.get("metadata") or ""))
            if tel and tel in brut:
                return True
    except Exception:
        return True

    return False


def construire_texte_relance(nom=None):
    """UNE relance, courte, sans culpabilisation, avec le lien juste après."""
    prenom = _prenom(nom)
    return "\n".join([
        f"Coucou {prenom} 👋" if prenom else "Coucou 👋",
        "",
        "Ta place n'est pas encore réservée — on garde le casque au chaud ! 🎧",
        "Si tu veux toujours venir, le lien est juste en dessous.",
        "",
        "Si ce n'est plus d'actualité, ignore simplement ce message : "
        "on ne te relancera pas une deuxième fois.",
        "",
        SIGNATURE,
    ])


async def relances_dues(maintenant=None):
    """Les personnes à relancer MAINTENANT. Lecture seule — n'envoie rien."""
    maintenant = maintenant or datetime.now(timezone.utc)
    debut = maintenant - timedelta(hours=HEURES_ABANDON)
    fin = maintenant - timedelta(hours=HEURES_AVANT_RELANCE)

    try:
        candidats = await db[COLLECTION_RELANCES].find(
            {"cree_dt": {"$gte": debut, "$lte": fin}}).limit(200).to_list(200)
    except Exception as e:
        logger.warning(f"[V433] lecture des relances impossible : {e}")
        return []

    dues = []
    for ligne in candidats:
        if ligne.get("relance_envoyee"):
            continue
        if await _a_paye(ligne):
            continue
        dues.append(ligne)
    return dues


async def envoyer_relances(apercu=True):
    """Relance ceux qui n'ont pas payé. `apercu=True` (DÉFAUT) n'envoie RIEN.

    Trois verrous avant qu'un message parte :
      1. `apercu=False` demandé explicitement par l'appelant ;
      2. le drapeau RELANCE_ACHAT_ENABLED, absent par défaut ;
      3. `relance_envoyee`, marqué AVANT l'envoi — une panne au milieu ne peut
         pas produire un second message au passage suivant.
    """
    dues = await relances_dues()
    resultat = {"apercu": apercu, "candidats": len(dues), "envoyees": 0, "lettres": []}

    if apercu:
        for l in dues[:20]:
            resultat["lettres"].append({
                "telephone": "…" + str(l.get("telephone") or "")[-4:],
                "texte": construire_texte_relance(l.get("nom")),
            })
        return resultat

    if not await relance_active():
        resultat["raison"] = f"{DRAPEAU_RELANCE} éteint — aucun envoi"
        return resultat

    from api.routes.bot_whatsapp_routes import (
        envoyer_payload, lire_etat, creer_lien_paiement, offre_payable_par_lien)

    for ligne in dues:
        tel = ligne.get("telephone")
        try:
            # Marqué AVANT l'envoi : au pire une relance est perdue, jamais doublée.
            await db[COLLECTION_RELANCES].update_one(
                {"_id": ligne["_id"]},
                {"$set": {"relance_envoyee": True,
                          "relance_le": datetime.now(timezone.utc).isoformat()}})

            await envoyer_payload(tel, {"type": "text", "text": {
                "body": construire_texte_relance(ligne.get("nom")), "preview_url": False}})

            offre = await db.offers.find_one({"id": ligne.get("offre_id")}, {"_id": 0})
            if offre and offre_payable_par_lien(offre):
                etat = await lire_etat(tel)
                payload_lien, _ = await creer_lien_paiement(tel, offre, etat)
                await envoyer_payload(tel, payload_lien)

            resultat["envoyees"] += 1
            logger.info(f"[V433] relance envoyée à …{str(tel)[-4:]}")
        except Exception as e:
            logger.error(f"[V433] relance échouée pour …{str(tel)[-4:]} : {e}")

    return resultat

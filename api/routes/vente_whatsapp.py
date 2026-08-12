"""
V434 — Assistant de RÉPONSE MANUELLE dans le viewer WhatsApp du dashboard.

CE MODULE N'ENVOIE RIEN ET NE RÉPOND À PERSONNE.
------------------------------------------------
Il ne fabrique que du TEXTE, à la demande de l'admin, pour qu'il le relise, le
corrige et décide lui-même de l'envoyer. Aucune de ces fonctions n'est appelée
par le webhook : le bot IA automatique garde EXACTEMENT le comportement qu'il
avait, mêmes réponses, même signature, même prompt.

    webhook Meta  ─── STOP (V332) ─── bot à menus (V369b) ─── flux IA
                                                               (inchangé)

    dashboard ─── « Proposer une réponse » / « Améliorer » ─── texte affiché
                                                               à l'admin
                                                                   │
                                                     l'admin relit et clique
                                                                   ▼
                                                              envoi manuel

POURQUOI CETTE SÉPARATION EST STRICTE
-------------------------------------
Une fonction qui sait rédiger un message ET qui est joignable depuis le webhook
finit tôt ou tard par répondre toute seule — au premier refactor, à la première
ligne ajoutée « pour bien faire ». Ici, aucun appelant automatique n'existe :
les deux seuls points d'entrée sont des routes du dashboard protégées par un
jeton super-admin signé, déclenchées par un clic.

CONNAISSANCE MÉTIER
-------------------
Le contexte donné au modèle (offres, dates, prix, lien) est LU EN BASE à chaque
appel : aucun prix ni aucune date n'est écrit en dur ici. Une modification faite
dans le dashboard se reflète immédiatement dans les brouillons.
"""
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

db = None


def init_vente_db(database):
    global db
    db = database


SITE = "https://afroboost.com"

SIGNATURE = "L'équipe Afroboost"

# L'offre « Afroboost Silent avec Bassi » — casque Silent du Laff Festival.
OFFRE_SILENT = "76a78f31-614a-415a-876b-9d2d1a4b441c"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def lien_offre(offre_id):
    """Lien de réservation STABLE vers une offre précise.

    Pourquoi ce lien plutôt qu'une URL de paiement Stripe : une session Stripe
    est à USAGE UNIQUE et expire en 24 h. Glissée dans un brouillon que l'admin
    relit, corrige, puis envoie une heure plus tard — ou renvoie le lendemain à
    quelqu'un d'autre — elle serait morte à l'arrivée. Ce lien-ci ouvre la carte
    de l'offre (V371 : le site lit `?offre=<id>`, y fait défiler et la met en
    évidence), d'où le bouton « Réserver » mène au paiement. Il reste valable
    indéfiniment et se partage sans risque.
    """
    return f"{SITE}/?offre={offre_id}" if offre_id else SITE


async def _seances(offre):
    """Dates et lieu, lus des cours liés — jamais inventés."""
    lignes, lieu = [], (offre.get("location") or "").strip()
    for cid in (offre.get("linked_course_ids") or [])[:4]:
        try:
            c = await db.courses.find_one({"id": cid},
                                          {"_id": 0, "date": 1, "time": 1, "location": 1})
        except Exception:
            c = None
        if not c:
            continue
        if not lieu:
            lieu = (c.get("location") or "").strip()
        d = str(c.get("date") or "")
        try:
            j = datetime.strptime(d, "%Y-%m-%d")
            d = f"{j.day} {MOIS[j.month - 1]}"
        except Exception:
            pass
        lignes.append(f"{d} à {c.get('time')}" if c.get("time") else d)
    return lignes, lieu


async def contexte_afroboost():
    """Ce que le modèle doit savoir pour rédiger. Lu en base, à chaque appel."""
    morceaux = []

    offre = await db.offers.find_one({"id": OFFRE_SILENT}, {"_id": 0})
    if offre:
        try:
            from api.pricing import compute_active_price
            calcul = compute_active_price(offre) or {}
            prix = calcul.get("price")
            palier = {"early_bird": "prévente", "standard": "tarif standard",
                      "last_minute": "dernière minute"}.get(calcul.get("tier") or "", "")
        except Exception:
            prix, palier = offre.get("price"), ""

        seances, lieu = await _seances(offre)
        morceaux.append(
            "OFFRE PHARE — « Afroboost Silent avec Bassi » (casque Silent) :\n"
            f"  · prix actuel : {prix} CHF" + (f" ({palier})" if palier else "") + "\n"
            + (f"  · dates : {' et '.join(seances)}\n" if seances else "")
            + (f"  · lieu : {lieu}\n" if lieu else "")
            + "  · le COURS EST OFFERT : la réservation couvre le casque Silent.\n"
            f"  · lien de réservation à donner : {lien_offre(OFFRE_SILENT)}"
        )

    # Les autres offres visibles, en une ligne chacune : de quoi répondre à
    # « vous avez quoi d'autre ? » sans inventer.
    try:
        autres = await db.offers.find(
            {"visible": True, "id": {"$ne": OFFRE_SILENT}},
            {"_id": 0, "id": 1, "name": 1, "price": 1}).to_list(12)
        if autres:
            lignes = [f"  · {(o.get('name') or '').strip()[:70]} — "
                      f"{o.get('price')} CHF — {lien_offre(o.get('id'))}"
                      for o in autres]
            morceaux.append("AUTRES OFFRES :\n" + "\n".join(lignes))
    except Exception as e:
        logger.warning(f"[V434] autres offres non lues : {e}")

    return "\n\n".join(morceaux)


PROMPT_ASSISTANT = f"""Tu aides l'équipe AFROBOOST (afroboost.com), studio de
fitness et de danse afrobeat à Lausanne, à répondre sur WhatsApp.

Tu n'écris PAS au client : tu proposes un brouillon que l'humain va relire,
corriger et envoyer lui-même.

RÈGLES :
- Afroboost EST l'organisateur de ses événements. Ne dis JAMAIS « contactez
  l'organisateur » ni « le site officiel de l'événement ».
- N'invente aucun prix, aucune date, aucun lieu : utilise UNIQUEMENT le contexte
  fourni. Si l'information manque, propose de vérifier plutôt que de deviner.
- Quand la personne veut acheter ou réserver, donne le lien de réservation tel
  quel, sans le raccourcir ni le modifier.
- Écris en français, chaleureusement, comme un message WhatsApp : 6 lignes
  maximum, pas d'objet, pas de « Cordialement ».
- N'écris JAMAIS de champ à compléter entre crochets ([Votre Nom], [Nom]…).
- Termine par la signature exacte : « {SIGNATURE} ».
- Réponds UNIQUEMENT par le texte du message, sans commentaire ni guillemets.
"""


# Placeholders explicitement listés — on ne supprime PAS tout ce qui est entre
# crochets : « [Image reçue] » et consorts sont légitimes dans ce produit.
_PLACEHOLDERS = re.compile(
    r"\[\s*(?:votre|ton|mon|le|la)?\s*"
    r"(?:nom|pr[ée]nom|signature|poste|fonction|entreprise|soci[ée]t[ée]|"
    r"your\s+name|name|company|title)"
    r"[^\]]{0,30}\]",
    re.IGNORECASE)

_FORMULES = re.compile(
    r"(?:^|\n)\s*(?:bien\s+)?(?:cordialement|sinc[èe]rement|amicalement|"
    r"salutations(?:\s+distingu[ée]es)?|bien\s+[àa]\s+vous|"
    r"respectueusement|best\s+regards|regards)\s*[,.!]?\s*",
    re.IGNORECASE)


def assainir(texte):
    """Nettoie le BROUILLON avant de l'afficher à l'admin.

    Ne s'applique qu'à ce que le modèle vient d'écrire, jamais à un message déjà
    parti ni à une réponse du bot automatique.
    """
    if not texte:
        return texte
    t = str(texte).strip()

    # Le modèle encadre parfois sa réponse de guillemets ou de ```.
    t = re.sub(r"^```[a-z]*\n?|```$", "", t).strip()
    if len(t) > 1 and t[0] in "«\"'" and t[-1] in "»\"'":
        t = t[1:-1].strip()

    t = _PLACEHOLDERS.sub("", t)
    t = _FORMULES.sub("\n", t)

    # En français l'espace avant « ! » « ? » « : » « ; » est correcte : on ne
    # recolle QUE la virgule et le point.
    t = re.sub(r"[ \t]+([,.])", r"\1", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    if SIGNATURE.lower() not in t.lower():
        t = f"{t}\n\n{SIGNATURE}" if t else SIGNATURE
    return t


async def _historique(conversation_id, limite=12):
    """Les derniers messages du fil, du plus ancien au plus récent."""
    try:
        msgs = await db.private_messages.find(
            {"conversation_id": conversation_id, "is_deleted": {"$ne": True}},
            {"_id": 0, "sender_id": 1, "content": 1, "created_at": 1}
        ).sort("created_at", -1).to_list(limite)
    except Exception as e:
        logger.warning(f"[V434] historique illisible : {e}")
        return []
    msgs.reverse()
    return msgs


async def rediger(conversation_id, mode="proposer", brouillon="", modele=None):
    """Produit un brouillon. `mode` = « proposer » ou « ameliorer ».

    Renvoie `(texte, erreur)`. N'ENVOIE RIEN, n'écrit rien en base : le résultat
    part vers l'écran de l'admin et nulle part ailleurs.
    """
    import os
    cle = os.environ.get("OPENAI_API_KEY")
    if not cle:
        return None, "Clé OpenAI absente sur le serveur."

    if mode == "ameliorer" and not (brouillon or "").strip():
        return None, "Écris d'abord un brouillon à améliorer."

    contexte = await contexte_afroboost()
    historique = await _historique(conversation_id)

    lignes = []
    for m in historique:
        qui = "AFROBOOST" if str(m.get("sender_id") or "").startswith("admin") else "CLIENT"
        lignes.append(f"{qui} : {(m.get('content') or '').strip()[:600]}")
    fil = "\n".join(lignes) or "(aucun message)"

    if mode == "ameliorer":
        consigne = (
            "Voici le brouillon écrit par l'équipe. Corrige l'orthographe et la "
            "grammaire, rends-le plus clair et plus chaleureux, SANS changer le "
            "sens ni ajouter d'information qui n'y est pas.\n\n"
            f"BROUILLON :\n{brouillon.strip()}")
    else:
        consigne = ("Propose la réponse à envoyer au CLIENT, en te fondant sur "
                    "le dernier message reçu et sur le contexte ci-dessus.")

    contenu = (f"CONTEXTE AFROBOOST\n{contexte}\n\n"
               f"CONVERSATION (du plus ancien au plus récent)\n{fil}\n\n"
               f"TÂCHE\n{consigne}")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=cle, timeout=25.0, max_retries=1)
        import asyncio
        reponse = await asyncio.to_thread(
            client.chat.completions.create,
            model=modele or "gpt-4o-mini",
            messages=[{"role": "system", "content": PROMPT_ASSISTANT},
                      {"role": "user", "content": contenu}],
            max_tokens=500,
            temperature=0.6)
        return assainir(reponse.choices[0].message.content), None
    except Exception as e:
        logger.error(f"[V434] rédaction impossible : {type(e).__name__}: {e}")
        return None, f"L'assistant n'a pas répondu ({type(e).__name__})."

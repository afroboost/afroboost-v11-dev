"""
V435 — Envoi de MODÈLES WhatsApp approuvés, depuis le viewer du dashboard.

À QUOI ÇA SERT
--------------
Meta n'autorise le texte libre que pendant 24 h après le dernier message du
client. Passé ce délai, la seule façon de le recontacter est un MODÈLE
(« template ») approuvé à l'avance par Meta. C'est le cas de tous les clients
de la campagne de Lausanne qui ont écrit il y a plusieurs jours.

CE QUE CE MODULE FAIT, ET NE FAIT PAS
-------------------------------------
Il CONSTRUIT l'appel et, sur demande explicite, l'exécute. Il n'est appelé par
aucun automate : ses deux seuls appelants sont des routes du dashboard
protégées par un jeton super-admin signé, déclenchées par un clic. Le bot IA
automatique n'y touche pas et n'est pas modifié.

`construire_appel()` est PURE — aucun réseau, aucune base. C'est ce qui permet
de prouver la forme exacte de la requête sans envoyer quoi que ce soit à un
vrai numéro, et c'est le mode par défaut (`simulation=True`).

LE PIÈGE À CONNAÎTRE
--------------------
Un `200` de Meta ne veut PAS dire « distribué » : Meta accepte, rend un
`wamid`, puis signale l'échec plus tard par le webhook de statuts (V378,
collection `whatsapp_statuts`). Mesuré le 12/08 : envoi vers un numéro fictif
-> `success` synchrone, puis `failed` code 131026. Le journal écrit ici garde
donc le `wamid`, seule clé permettant de rapprocher un envoi de son sort réel.
"""
import os
import re
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

db = None


def init_modeles_db(database):
    global db
    db = database


# Le compte WhatsApp Business. Déjà écrit en dur à deux endroits de server.py ;
# on le centralise ici, avec une variable d'environnement pour pouvoir en
# changer sans redéployer.
WABA_ID = os.environ.get("META_WHATSAPP_WABA_ID", "1615280896432370")

COLLECTION_JOURNAL = "whatsapp_modeles_envois"


# --- Traduction des refus de Meta -------------------------------------------
#
# Meta renvoie des codes numériques et des messages en anglais, souvent
# obscurs. Les laisser remonter tels quels à l'écran obligerait à les
# rechercher à chaque fois. On traduit les cas réellement rencontrés sur ce
# type de compte ; les autres passent avec leur message d'origine.
ERREURS = {
    132000: "Le nombre de variables envoyées ne correspond pas au modèle.",
    132001: ("Ce modèle n'existe pas (ou pas dans cette langue) sur le compte "
             "WhatsApp. Vérifiez son nom exact et sa langue."),
    132005: "Le texte d'une variable est trop long pour ce modèle.",
    132007: "Le contenu d'une variable est refusé par Meta (format inattendu).",
    132012: "Le format d'une variable ne correspond pas à ce qu'attend le modèle.",
    132015: "Ce modèle est SUSPENDU par Meta : il ne peut plus être envoyé.",
    132016: "Ce modèle est DÉSACTIVÉ par Meta (trop de signalements).",
    132068: "Ce modèle a été mis en pause par Meta pour cause de faible qualité.",
    132069: "Ce modèle a été désactivé définitivement par Meta.",
    131026: ("Message non distribuable : le numéro n'a pas WhatsApp, ou il ne "
             "peut pas recevoir ce type de message."),
    131047: "Fenêtre de 24 h fermée — c'est justement le cas où un modèle est requis.",
    131049: "Meta a limité l'envoi vers ce numéro pour préserver la qualité du compte.",
    130472: "Ce numéro fait partie d'une expérience Meta et n'est pas joignable.",
    100: ("Paramètre invalide. Le plus souvent : le modèle n'est pas approuvé, "
          "ou un composant (bouton, variable) ne correspond pas à sa définition."),
    190: "Le jeton Meta est expiré ou révoqué — à renouveler dans Coolify.",
    368: "Le compte WhatsApp est temporairement bloqué par Meta.",
    80007: "Limite de débit Meta atteinte : réessayez dans quelques minutes.",
}


def message_erreur(code, message_meta=""):
    """Une phrase compréhensible, sans perdre le code d'origine."""
    clair = ERREURS.get(code)
    if clair:
        return f"{clair} (code Meta {code})"
    return (f"WhatsApp a refusé l'envoi : {message_meta or 'raison non précisée'} "
            f"(code Meta {code}).")


# --- Lecture des modèles déclarés -------------------------------------------

async def lister_modeles(config):
    """Les modèles du compte, avec leur STATUT. Lecture seule chez Meta.

    On renvoie TOUT, y compris les refusés : cacher un modèle rejeté ferait
    croire qu'il n'a jamais été soumis, alors que le savoir est précisément ce
    qui explique pourquoi on ne peut pas l'envoyer. L'interface, elle, n'en rend
    sélectionnables que les approuvés.
    """
    import httpx
    version = (config or {}).get("api_version") or "v21.0"
    url = f"https://graph.facebook.com/{version}/{WABA_ID}/message_templates"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers={
                "Authorization": f"Bearer {config['access_token']}"},
                params={"limit": 100,
                        "fields": "name,status,language,category,components"})
        d = r.json()
    except Exception as e:
        logger.error(f"[V435] liste des modèles illisible : {e}")
        return None, f"Impossible de joindre Meta ({type(e).__name__})."

    if "error" in d:
        err = d["error"]
        return None, message_erreur(err.get("code"), err.get("message"))

    modeles = []
    for t in d.get("data", []):
        corps, entete, pied, boutons = "", "", "", []
        for c in t.get("components", []) or []:
            ty = c.get("type")
            if ty == "BODY":
                corps = c.get("text") or ""
            elif ty == "HEADER":
                entete = c.get("text") or ""
            elif ty == "FOOTER":
                pied = c.get("text") or ""
            elif ty == "BUTTONS":
                for b in c.get("buttons", []) or []:
                    boutons.append({"type": b.get("type"), "texte": b.get("text"),
                                    "url": b.get("url")})
        modeles.append({
            "nom": t.get("name"),
            "statut": t.get("status"),
            "langue": t.get("language"),
            "categorie": t.get("category"),
            "corps": corps,
            "entete": entete,
            "pied": pied,
            "boutons": boutons,
            # Combien de {{n}} le corps attend : l'interface s'en sert pour
            # afficher le bon nombre de champs, et le serveur pour refuser un
            # envoi mal formé AVANT de déranger Meta.
            "variables": len(set(re.findall(r"\{\{(\d+)\}\}", corps))),
        })
    return modeles, None


def apercu(corps, variables):
    """Le texte tel que le client le lira. Sert à la relecture avant envoi."""
    texte = corps or ""
    for i, v in enumerate(variables or [], start=1):
        texte = texte.replace("{{%d}}" % i, str(v))
    return texte


# --- Construction de l'appel (PURE : ni réseau, ni base) ---------------------

def normaliser_numero(telephone):
    """Format attendu par Meta : chiffres seuls, indicatif compris.

    L'ORDRE DES DEUX CAS COMPTE. « 00 » est le préfixe international : il faut
    le retirer AVANT de traiter le « 0 » national, sinon `0041795105694`
    devient `41041795105694` — un numéro inexistant, vers lequel le message
    part sans erreur visible. C'est le défaut qu'avait la première version de
    cette fonction, trouvé en imprimant les trois écritures côte à côte.
    """
    n = re.sub(r"\D", "", str(telephone or ""))
    if n.startswith("00"):
        return n[2:]              # 0041… -> 41…
    if n.startswith("0"):
        return "41" + n[1:]       # 079…  -> 4179…  (numéro suisse)
    return n


def construire_appel(config, telephone, modele, langue, variables=None,
                     suffixe_bouton=None, index_bouton=0):
    """Renvoie `(url, entetes, payload)` — exactement ce qui partirait chez Meta.

    Fonction PURE : aucun effet de bord. C'est elle qu'on inspecte en mode
    simulation, et c'est la MÊME qui sert à l'envoi réel — sans quoi la preuve
    porterait sur autre chose que ce qui part vraiment.

    `suffixe_bouton` ne concerne que les boutons URL DYNAMIQUES, où Meta colle
    la valeur à la fin de l'URL de base définie dans le modèle. Un bouton URL
    STATIQUE (URL complète figée à la création) ne prend AUCUN paramètre : lui
    en envoyer un fait échouer l'appel en code 100.
    """
    version = (config or {}).get("api_version") or "v21.0"
    url = f"https://graph.facebook.com/{version}/{config['phone_number_id']}/messages"
    entetes = {"Authorization": "Bearer ***",          # jamais le vrai jeton ici
               "Content-Type": "application/json"}

    payload = {
        "messaging_product": "whatsapp",
        "to": normaliser_numero(telephone),
        "type": "template",
        "template": {"name": modele, "language": {"code": langue or "fr"}},
    }

    composants = []
    if variables:
        composants.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)} for v in variables],
        })
    if suffixe_bouton:
        composants.append({
            "type": "button",
            "sub_type": "url",
            "index": str(index_bouton),
            "parameters": [{"type": "text", "text": str(suffixe_bouton)}],
        })
    if composants:
        payload["template"]["components"] = composants

    return url, entetes, payload


# --- Envoi ------------------------------------------------------------------

async def envoyer_modele(config, telephone, modele, langue, variables=None,
                         suffixe_bouton=None, index_bouton=0,
                         simulation=True, appelant="", conversation_id=""):
    """Envoie un modèle. `simulation=True` (DÉFAUT) n'appelle PAS Meta.

    Le défaut est volontaire : une fonction d'envoi dont le comportement par
    défaut est d'envoyer finira par envoyer par accident.
    """
    url, entetes, payload = construire_appel(
        config, telephone, modele, langue, variables, suffixe_bouton, index_bouton)

    if simulation:
        return {"simulation": True, "url": url, "entetes": entetes,
                "payload": payload,
                "note": "Aucun appel réseau n'a été effectué."}

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=payload, headers={
                "Authorization": f"Bearer {config['access_token']}",
                "Content-Type": "application/json"})
        reponse = r.json()
    except Exception as e:
        logger.error(f"[V435] appel Meta impossible : {e}")
        return {"success": False, "erreur": f"Meta injoignable ({type(e).__name__})."}

    erreur = reponse.get("error")
    if erreur:
        clair = message_erreur(erreur.get("code"), erreur.get("message"))
        logger.warning(f"[V435] modèle « {modele} » refusé pour "
                       f"…{str(telephone)[-4:]} : {clair}")
        await _journaliser(appelant, telephone, modele, langue, variables,
                           conversation_id, statut="refuse",
                           wamid=None, erreur=clair, code=erreur.get("code"))
        return {"success": False, "erreur": clair, "code": erreur.get("code")}

    wamid = ((reponse.get("messages") or [{}])[0]).get("id")
    logger.info(f"[V435] modèle « {modele} » accepté par Meta pour "
                f"…{str(telephone)[-4:]} (wamid {wamid}) — par {appelant}")
    await _journaliser(appelant, telephone, modele, langue, variables,
                       conversation_id, statut="accepte", wamid=wamid)
    return {"success": True, "wamid": wamid,
            "avertissement": ("Meta a ACCEPTÉ le message. La distribution réelle "
                              "est confirmée plus tard par le webhook de statuts.")}


async def _journaliser(appelant, telephone, modele, langue, variables,
                       conversation_id, statut, wamid=None, erreur=None, code=None):
    """Qui, quand, à qui, quel modèle, et ce que Meta a répondu."""
    if db is None:
        return
    try:
        await db[COLLECTION_JOURNAL].insert_one({
            "id": str(uuid.uuid4()),
            "quand": datetime.now(timezone.utc).isoformat(),
            "par": appelant,
            "telephone": telephone,
            "conversation_id": conversation_id or None,
            "modele": modele,
            "langue": langue,
            "variables": list(variables or []),
            "statut": statut,          # « accepte » ou « refuse »
            "wamid": wamid,            # clé de rapprochement avec whatsapp_statuts
            "erreur": erreur,
            "code_meta": code,
        })
    except Exception as e:
        logger.warning(f"[V435] journal non écrit : {e}")

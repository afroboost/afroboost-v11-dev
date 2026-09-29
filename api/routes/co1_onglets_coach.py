# -*- coding: utf-8 -*-
"""CO-1 — Onglets Contacts et Campagnes ouverts aux coachs partenaires.

Ce module ne porte que des règles PURES (aucun accès base, aucun réseau), pour
être prouvées sans serveur par tests/test_co1_onglets_coach.py.

1. WHATSAPP D'UNE CAMPAGNE = NUMÉRO OFFICIEL AFROBOOST.
   Le moteur de campagne (`launch_campaign`) n'a qu'UNE configuration WhatsApp :
   celle de la plateforme (`_get_whatsapp_config`, variables META_WHATSAPP_*).
   Le sélecteur « Mon numéro WhatsApp Business » de CampaignModal n'a jamais été
   transmis au serveur (`senderType` / `customFromNumber` n'existent dans aucun
   modèle) : une campagne WhatsApp de coach partenaire partirait donc DEPUIS le
   numéro officiel. On le refuse : seule une campagne dont le propriétaire est
   le super-admin (ou une campagne historique sans propriétaire, que seul le
   super-admin peut lancer — V451) peut utiliser le canal WhatsApp.

2. CONFIGURATION IA = RÉGLAGE PLATEFORME.
   `ai_config` est UN document global (prompt, activation, lien Twint…). Seul
   le super-admin signé le lit en entier ou l'écrit. La lecture publique ne
   garde que `enabled` (sonde de nonregression.py #12), sans prompt ni lien.
"""

from api.routes.shared import is_super_admin

MESSAGE_WHATSAPP_RESERVE = (
    "Le canal WhatsApp des campagnes passe par le numéro officiel Afroboost : "
    "il est réservé à la plateforme. Utilisez l'e-mail ou le chat interne, ou "
    "écrivez à vos contacts WhatsApp depuis votre propre téléphone."
)

MESSAGE_IA_RESERVEE = "Réservé au super-admin : reconnectez-vous avec votre mot de passe."

# Champs de `ai_config` lisibles sans être super-admin signé. Rien d'autre.
CHAMPS_IA_PUBLICS = ("enabled",)


def proprietaire_partenaire(proprietaire) -> bool:
    """Le propriétaire désigne-t-il un coach partenaire (ni vide, ni super-admin) ?"""
    p = (proprietaire or "").lower().strip()
    return bool(p) and not is_super_admin(p)


def whatsapp_demande(channels) -> bool:
    return isinstance(channels, dict) and bool(channels.get("whatsapp"))


def whatsapp_campagne_interdit(proprietaire, channels) -> bool:
    """Vrai si une campagne de coach partenaire veut le canal WhatsApp."""
    return whatsapp_demande(channels) and proprietaire_partenaire(proprietaire)


def ia_config_publique(config) -> dict:
    """Vue publique de `ai_config` : `enabled` seul (jamais prompt/lien/média)."""
    config = config or {}
    return {c: bool(config.get(c)) for c in CHAMPS_IA_PUBLICS}

"""
Activation après paiement — bloc PARTAGÉ entre prestataires (V325)

Pourquoi ce fichier : le webhook CinetPay contient le bloc « que faire une fois le
paiement confirmé » (inscription partenaire / achat de crédits / achat client).
PawaPay doit faire EXACTEMENT la même chose. Plutôt que de dupliquer ce bloc une
troisième fois, il est extrait ici, à l'identique.

⚠️ ÉTAT ACTUEL — lire avant de modifier :
`cinetpay_routes.py` n'a PAS été touché par V325 (consigne : zéro ligne modifiée sur
les prestataires en production). Ce module est donc pour l'instant appelé UNIQUEMENT
par le webhook PawaPay ; c'est une COPIE FIDÈLE du bloc CinetPay, pas encore son
remplacement. La migration de CinetPay vers cette fonction est un chantier séparé,
à faire quand PawaPay aura tourné en production — elle ne doit pas être glissée dans
la version qui introduit PawaPay.

Une seule différence VOLONTAIRE avec l'original CinetPay : dans la branche « achat
client », l'original utilise `primary_color` sans l'avoir défini dans cette branche
(la variable n'est calculée que dans la branche « inscription partenaire »). Le
`NameError` est avalé par le `except` qui entoure l'envoi — donc l'e-mail client
n'est jamais parti. Ici la couleur est relue au début de la branche.
"""
import os
import uuid
import logging
from datetime import datetime, timezone

from api.routes.shared import get_primary_color, hex_to_rgb_triplet

logger = logging.getLogger(__name__)


async def activate_after_payment(
    db,
    local_tx: dict,
    *,
    provider: str,
    amount,
    currency: str,
    payment_method: str,
    transaction_ref: str,
    log_prefix: str = "PAYMENT_ACTIVATION",
):
    """
    Applique les effets métier d'un paiement CONFIRMÉ.

    Cette fonction ne décide RIEN : l'appelant (le webhook du prestataire) a déjà
    vérifié auprès de l'API du prestataire que le paiement est bien final et réussi,
    et a déjà marqué sa transaction locale comme `completed` (garde anti-double
    traitement incluse). Ici on ne fait qu'accorder les droits achetés.

    Paramètres :
        db              : base Motor
        local_tx        : la transaction locale (dict) — porte `type`, emails, pack, crédits
        provider        : "pawapay" | "cinetpay" | … — écrit tel quel dans les enregistrements
        amount          : montant confirmé par le prestataire (unité majeure)
        currency        : devise confirmée
        payment_method  : libellé du moyen (opérateur mobile money, carte…)
        transaction_ref : référence de la transaction chez le prestataire
        log_prefix      : préfixe des logs, pour tracer quel webhook a appelé
    """
    tx_type = local_tx.get("type", "")

    # --- Inscription Partenaire ---
    if tx_type == "coach_registration":
        coach_email = (local_tx.get("customer_email", "") or "").lower()
        credits = local_tx.get("credits", 0)
        pack_id = local_tx.get("pack_id", "")
        customer_name = local_tx.get("customer_name", "")

        # Créer/Mettre à jour le profil coach
        existing_coach = await db.coaches.find_one({"email": coach_email})
        if existing_coach:
            await db.coaches.update_one(
                {"email": coach_email},
                {"$set": {
                    "credits": credits,
                    "pack_id": pack_id,
                    "is_active": True,
                    "payment_provider": provider,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        else:
            await db.coaches.insert_one({
                "id": str(uuid.uuid4()),
                "email": coach_email,
                "name": customer_name,
                "phone": local_tx.get("customer_phone", ""),
                "credits": credits,
                "pack_id": pack_id,
                "is_active": True,
                "payment_provider": provider,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

        logger.info(f"[{log_prefix}] Coach créé/mis à jour: {coach_email} avec {credits} crédits")

        # === NOTIFICATION EMAIL : Super Admin + Partenaire ===
        try:
            import resend
            import asyncio
            resend.api_key = os.environ.get('RESEND_API_KEY', '')

            # V259: couleur de marque relue en base pour ces emails
            primary_color = await get_primary_color(db)
            primary_rgb = hex_to_rgb_triplet(primary_color)

            # Email au Super Admin
            await asyncio.to_thread(resend.Emails.send, {
                "from": "Afroboost <notifications@afroboost.com>",
                "to": ["contact.artboost@gmail.com"],
                "subject": f"🎉 Nouveau Partenaire ! {customer_name} ({coach_email})",
                "html": f"""
                <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                    <h2 style="color:{primary_color};">🎉 Nouveau Partenaire Afroboost</h2>
                    <p><strong>Nom:</strong> {customer_name}</p>
                    <p><strong>Email:</strong> {coach_email}</p>
                    <p><strong>Pack:</strong> {local_tx.get('pack_name', 'N/A')}</p>
                    <p><strong>Crédits:</strong> {credits}</p>
                    <p><strong>Montant:</strong> {amount} {currency}</p>
                    <p><strong>Méthode:</strong> Mobile Money ({payment_method})</p>
                    <p><strong>Transaction:</strong> {transaction_ref}</p>
                    <p style="color:#4ade80;font-weight:bold;margin-top:20px;">Paiement confirmé ✅</p>
                </div>
                """
            })

            # Email au nouveau partenaire
            await asyncio.to_thread(resend.Emails.send, {
                "from": "Afroboost <notifications@afroboost.com>",
                "to": [coach_email],
                "subject": "🎊 Bienvenue Partenaire Afroboost !",
                "html": f"""
                <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                    <h2 style="color:{primary_color};">Bienvenue {customer_name} ! 🎊</h2>
                    <p>Votre inscription comme Partenaire Afroboost est confirmée.</p>
                    <p><strong>Pack:</strong> {local_tx.get('pack_name', '')}</p>
                    <p><strong>Crédits disponibles:</strong> {credits}</p>
                    <p style="margin-top:20px;">
                        <a href="https://afroboost.com/#partner-dashboard"
                           style="display:inline-block;padding:12px 24px;background:linear-gradient(135deg,{primary_color},#8b5cf6);color:white;text-decoration:none;border-radius:8px;font-weight:bold;">
                            Accéder à mon Dashboard →
                        </a>
                    </p>
                </div>
                """
            })

            logger.info(f"[{log_prefix}] Emails envoyés pour coach: {coach_email}")
        except Exception as email_err:
            logger.error(f"[{log_prefix}] Erreur envoi email: {email_err}")

    # --- Achat de crédits ---
    elif tx_type == "credit_purchase":
        coach_email = (local_tx.get("coach_email", "") or "").lower()
        credits_to_add = local_tx.get("credits", 0)
        pack_name = local_tx.get("pack_name", "")

        if coach_email and credits_to_add > 0:
            await db.coaches.update_one(
                {"email": coach_email},
                {"$inc": {"credits": credits_to_add}}
            )

            await db.credit_transactions.insert_one({
                "coach_email": coach_email,
                "credits_added": credits_to_add,
                "pack_name": pack_name,
                "amount": amount,
                "currency": currency,
                "payment_provider": provider,
                "transaction_id": transaction_ref,
                "payment_method": payment_method,
                "date": datetime.now(timezone.utc)
            })

            logger.info(f"[{log_prefix}] {credits_to_add} crédits ajoutés à {coach_email}")

    # --- V342 : Boost d'une publication ---
    # Le paiement vient d'être confirmé par le prestataire (l'appelant a déjà
    # re-vérifié auprès de son API). Il ne reste qu'à accorder l'apparition 48 h
    # sur la vitrine de destination et à créditer son propriétaire. L'import est
    # LAZY : `boost_routes` importe déjà `pawapay_routes`, un import en tête de
    # fichier créerait un cycle.
    elif tx_type == "publication_boost":
        boost_id = local_tx.get("boost_id", "")
        if boost_id:
            from api.routes.boost_routes import activer_boost
            await activer_boost(boost_id, provider=provider, reference=transaction_ref)
        else:
            logger.error(f"[{log_prefix}] Boost sans boost_id — rien à activer")

    # --- Achat client (séances) ---
    else:
        customer_email = (local_tx.get("customer_email", "") or "").lower()
        if customer_email:
            # Générer un code d'accès
            access_code = f"AFR-{uuid.uuid4().hex[:6].upper()}"
            sessions_count = (local_tx.get("metadata") or {}).get("sessions", 10)

            # V384 : les noms de champs sont ceux que lit RÉELLEMENT la page
            # « Code promo / partenaire » — `assignedEmail`, `used`, `active`.
            # Cette insertion écrivait `assignedTo`, `usedCount`, `isActive` :
            # aucun des 33 codes existants ne porte ces noms-là, donc le code
            # créé par un paiement Mobile Money serait bien en base mais
            # INVISIBLE (ou vide) dans la page. Le bug n'avait jamais été vu
            # parce qu'aucun paiement PawaPay n'avait encore abouti.
            await db.discount_codes.insert_one({
                "id": str(uuid.uuid4()),
                "code": access_code,
                "type": "100%",
                "value": 100,
                "assignedEmail": customer_email,
                "assignedName": local_tx.get("customer_name", ""),
                "maxUses": sessions_count,
                "used": 0,
                "active": True,
                "courses": [],
                "targetCategories": [],
                "multi_member": False,
                "shared_sessions": True,
                "coach_id": None,
                # Montant réellement payé, dans la devise locale du client.
                "stripe_amount": amount,
                "paid_currency": currency,
                "source": provider,
                "transaction_id": transaction_ref,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

            # Envoyer email avec QR Code
            try:
                import resend
                import asyncio
                resend.api_key = os.environ.get('RESEND_API_KEY', '')

                # V325 : la couleur est relue ICI (l'original ne la définissait que
                # dans la branche « partenaire » -> NameError silencieux, e-mail perdu).
                primary_color = await get_primary_color(db)

                qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://afroboost.com/?qr={access_code}"

                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboost.com>",
                    "to": [customer_email],
                    "subject": f"Votre accès Afroboost - {access_code}",
                    "html": f"""
                    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                        <h2 style="color:{primary_color};">Bienvenue chez Afroboost ! 🎉</h2>
                        <p>Merci pour votre achat ! Voici vos accès :</p>
                        <div style="background:rgba(139,92,246,0.2);padding:16px;border-radius:8px;text-align:center;margin:16px 0;">
                            <p style="font-size:12px;color:#c4b5fd;">Votre code d'identification</p>
                            <p style="font-size:28px;font-weight:bold;color:{primary_color};letter-spacing:4px;">{access_code}</p>
                            <p style="font-size:12px;color:rgba(255,255,255,0.5);">Séances : {sessions_count}</p>
                        </div>
                        <div style="text-align:center;margin:16px 0;">
                            <p style="font-size:12px;color:#c4b5fd;">Votre QR Code (à présenter à l'entrée)</p>
                            <img src="{qr_url}" alt="QR Code" style="width:200px;height:200px;border-radius:8px;"/>
                        </div>
                        <p style="font-size:12px;color:rgba(255,255,255,0.5);margin-top:16px;">
                            Utilisez ce code pour vous connecter sur afroboost.com et suivre votre consommation de séances.
                        </p>
                    </div>
                    """
                })

                # Notifier le Super Admin
                await asyncio.to_thread(resend.Emails.send, {
                    "from": "Afroboost <notifications@afroboost.com>",
                    "to": ["contact.artboost@gmail.com"],
                    "subject": f"💰 Nouvelle vente ! {local_tx.get('customer_name', '')} - {amount} {currency}",
                    "html": f"""
                    <div style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:20px;background:#1a1a2e;color:white;border-radius:12px;">
                        <h2 style="color:#4ade80;">💰 Nouvelle Vente</h2>
                        <p><strong>Client:</strong> {local_tx.get('customer_name', 'N/A')}</p>
                        <p><strong>Email:</strong> {customer_email}</p>
                        <p><strong>Montant:</strong> {amount} {currency}</p>
                        <p><strong>Méthode:</strong> Mobile Money ({payment_method})</p>
                        <p><strong>Code accès:</strong> {access_code}</p>
                        <p><strong>Séances:</strong> {sessions_count}</p>
                    </div>
                    """
                })
            except Exception as email_err:
                logger.error(f"[{log_prefix}] Erreur email client: {email_err}")

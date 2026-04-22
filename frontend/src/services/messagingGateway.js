// messagingGateway.js - Passerelles techniques pour l'envoi de messages
// Ces fonctions sont des canaux de sortie PURS - aucune logique de décision
// L'agent IA reste le déclencheur principal et utilise ces passerelles pour expédier

import emailjs from '@emailjs/browser';

// === CONSTANTES EMAILJS - NE PAS MODIFIER ===
const EMAILJS_SERVICE_ID = "service_8mrmxim";
const EMAILJS_TEMPLATE_ID = "template_3n1u86p";
const EMAILJS_PUBLIC_KEY = "5LfgQSIEQoqq_XSqt";

// === WEBHOOK WHATSAPP (backend Twilio) ===
const WHATSAPP_WEBHOOK_URL = "https://afroboost-audio-1.emergent.host/api/webhook/whatsapp";
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

// === INITIALISATION SDK AU CHARGEMENT DU MODULE ===
let emailjsInitialized = false;
try {
  emailjs.init(EMAILJS_PUBLIC_KEY);
  emailjsInitialized = true;
  console.log('✅ [Gateway] EmailJS SDK initialisé');
} catch (e) {
  console.error('❌ [Gateway] Erreur init EmailJS:', e);
}

/**
 * === LIAISON IA -> EMAILJS ===
 * Fonction de soudure entre l'agent IA et le canal EmailJS
 * Bypass du crash PostHog avec try/catch robuste
 * 
 * @param {string} aiMessage - Message généré par l'IA
 * @param {string} clientEmail - Email du destinataire
 * @param {string} clientName - Nom du destinataire (optionnel)
 * @param {string} subject - Sujet de l'email (optionnel)
 * @returns {Promise<{success: boolean, ...}>}
 */
export const sendAIResponseViaEmail = async (aiMessage, clientEmail, clientName = 'Client', subject = 'Afroboost - Réponse') => {
  // === BYPASS CRASH POSTHOG ===
  // L'autonomie de l'IA est prioritaire sur le tracking
  try {
    console.log('[IA->EmailJS] ========================================');
    console.log('[IA->EmailJS] Liaison IA -> EmailJS activée');
    console.log('[IA->EmailJS] Destinataire:', clientEmail);
    console.log('[IA->EmailJS] Message IA:', aiMessage?.substring(0, 100) + '...');
    console.log('[IA->EmailJS] ========================================');
    
    // Validation basique
    if (!clientEmail || !clientEmail.includes('@')) {
      console.error('[IA->EmailJS] ❌ Email invalide:', clientEmail);
      return { success: false, error: 'Email invalide', channel: 'email' };
    }
    
    if (!aiMessage || aiMessage.trim() === '') {
      console.error('[IA->EmailJS] ❌ Message IA vide');
      return { success: false, error: 'Message IA vide', channel: 'email' };
    }
    
    // Paramètres du template - format plat uniquement
    const templateParams = {
      message: String(aiMessage),
      to_email: String(clientEmail),
      to_name: String(clientName),
      subject: String(subject)
    };
    
    console.log('[IA->EmailJS] Template params:', JSON.stringify(templateParams));
    
    // === ENVOI VIA EMAILJS ===
    const response = await emailjs.send(
      EMAILJS_SERVICE_ID,
      EMAILJS_TEMPLATE_ID,
      templateParams,
      EMAILJS_PUBLIC_KEY
    );
    
    // === VALIDATION SUCCÈS ===
    console.log('IA : Message envoyé via EmailJS');
    console.log('[IA->EmailJS] ✅ Réponse:', response.status, response.text);
    
    return { 
      success: true, 
      response, 
      channel: 'email',
      aiMessageSent: aiMessage.substring(0, 50) + '...'
    };
    
  } catch (error) {
    // BYPASS: Ne pas laisser l'erreur bloquer l'IA
    console.error('[IA->EmailJS] ❌ Erreur (bypass PostHog):', error);
    
    // Vérifier si c'est une erreur PostHog/DataClone
    if (error.name === 'DataCloneError' || error.message?.includes('clone')) {
      console.warn('[IA->EmailJS] ⚠️ Erreur PostHog ignorée - tentative alternative');
      // L'erreur PostHog ne doit pas bloquer
      return { 
        success: false, 
        error: 'PostHog blocking - message may have been sent',
        postHogBlocked: true,
        channel: 'email'
      };
    }
    
    return { 
      success: false, 
      error: error?.text || error?.message || 'Erreur inconnue',
      channel: 'email'
    };
  }
};

/**
 * === LIAISON IA -> WHATSAPP — V161: Via backend unifié (Meta Cloud API ou Twilio) ===
 * Fonction de soudure entre l'agent IA et le canal WhatsApp
 *
 * @param {string} aiMessage - Message généré par l'IA
 * @param {string} phoneNumber - Numéro de téléphone du destinataire
 * @param {object} _legacyConfig - Ignoré (legacy Twilio, gardé pour rétrocompat)
 * @returns {Promise<{success: boolean, ...}>}
 */
export const sendAIResponseViaWhatsApp = async (aiMessage, phoneNumber, _legacyConfig = null) => {
  try {
    console.log('[IA->WhatsApp] Liaison IA -> WhatsApp (Meta Cloud API)');
    console.log('[IA->WhatsApp] Destinataire:', phoneNumber);

    if (!phoneNumber) {
      return { success: false, error: 'Numéro invalide', channel: 'whatsapp' };
    }

    if (!aiMessage || aiMessage.trim() === '') {
      return { success: false, error: 'Message IA vide', channel: 'whatsapp' };
    }

    // Formater le numéro au format E.164
    let formattedPhone = phoneNumber.replace(/[^\d+]/g, '');
    if (!formattedPhone.startsWith('+')) {
      formattedPhone = formattedPhone.startsWith('0')
        ? '+41' + formattedPhone.substring(1)
        : '+' + formattedPhone;
    }

    // V161: Toujours passer par le backend unifié (qui route Meta ou Twilio)
    const response = await fetch(`${BACKEND_URL}/api/send-whatsapp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        to: formattedPhone,
        message: String(aiMessage)
      })
    });

    const data = await response.json();

    if (data.status === 'success') {
      console.log('[IA->WhatsApp] ✅ Envoyé - ID:', data.sid);
      return { success: true, sid: data.sid, channel: 'whatsapp' };
    } else if (data.status === 'simulated') {
      console.warn('[IA->WhatsApp] ⚠️ Mode simulation');
      return { success: true, simulated: true, channel: 'whatsapp' };
    } else {
      console.error('[IA->WhatsApp] ❌ Erreur:', data.error);
      return { success: false, error: data.error, channel: 'whatsapp' };
    }

  } catch (error) {
    console.error('[IA->WhatsApp] ❌ Exception:', error);
    return { success: false, error: error.message, channel: 'whatsapp' };
  }
};

/**
 * === DISPATCH IA UNIFIÉ ===
 * Point d'entrée unique pour l'agent IA - route vers le bon canal
 * L'IA appelle cette fonction avec le message généré et la destination
 * 
 * @param {object} aiOutput - Sortie de l'agent IA
 * @param {string} aiOutput.message - Message généré par l'IA
 * @param {string} aiOutput.channel - 'email' ou 'whatsapp'
 * @param {string} aiOutput.destination - Email ou numéro de téléphone
 * @param {string} aiOutput.clientName - Nom du client (optionnel)
 * @param {object} aiOutput.twilioConfig - Config Twilio (optionnel)
 * @returns {Promise<{success: boolean, ...}>}
 */
export const dispatchAIResponse = async (aiOutput) => {
  const { message, channel, destination, clientName, twilioConfig } = aiOutput;
  
  console.log('[IA-Dispatch] ========================================');
  console.log('[IA-Dispatch] Agent IA demande envoi');
  console.log('[IA-Dispatch] Canal:', channel);
  console.log('[IA-Dispatch] Destination:', destination);
  console.log('[IA-Dispatch] ========================================');
  
  // === BYPASS CRASH POSTHOG - Encapsulation totale ===
  try {
    if (channel === 'email') {
      return await sendAIResponseViaEmail(message, destination, clientName);
    }
    
    if (channel === 'whatsapp') {
      return await sendAIResponseViaWhatsApp(message, destination, twilioConfig);
    }
    
    console.error('[IA-Dispatch] ❌ Canal inconnu:', channel);
    return { success: false, error: `Canal inconnu: ${channel}` };
    
  } catch (dispatchError) {
    console.error('[IA-Dispatch] ❌ Erreur dispatch (bypass):', dispatchError);
    
    // Ne jamais bloquer l'IA
    return { 
      success: false, 
      error: dispatchError.message,
      bypassed: true
    };
  }
};

/**
 * PASSERELLE EMAIL - Canal technique pur
 * Reçoit les paramètres de l'agent IA et les transmet à EmailJS
 * AUCUNE logique de décision - juste transmission
 * 
 * @param {string} to_email - Email du destinataire
 * @param {string} to_name - Nom du destinataire (défaut: 'Client')
 * @param {string} subject - Sujet (défaut: 'Afroboost')
 * @param {string} message - Corps du message généré par l'IA
 * @returns {Promise<{success: boolean, response?: any, error?: string}>}
 */
export const sendEmailGateway = async (to_email, to_name = 'Client', subject = 'Afroboost', message = '') => {
  // Payload plat - texte uniquement, aucun objet complexe
  const params = {
    to_email: String(to_email),
    to_name: String(to_name),
    subject: String(subject),
    message: String(message)
  };
  
  console.log('[Gateway] ========================================');
  console.log('[Gateway] DEMANDE EMAILJS - Canal de sortie IA');
  console.log('[Gateway] Destination:', to_email);
  console.log('[Gateway] Payload:', JSON.stringify(params));
  console.log('[Gateway] ========================================');
  
  try {
    const response = await emailjs.send(
      EMAILJS_SERVICE_ID,
      EMAILJS_TEMPLATE_ID,
      params,
      EMAILJS_PUBLIC_KEY
    );
    
    console.log('[Gateway] ✅ Email transmis:', response.status);
    return { success: true, response, channel: 'email' };
  } catch (error) {
    console.error('[Gateway] ❌ Erreur transmission email:', error);
    return { 
      success: false, 
      error: error?.text || error?.message || 'Erreur inconnue',
      channel: 'email'
    };
  }
};

/**
 * PASSERELLE WHATSAPP — V161: Via backend unifié (Meta Cloud API ou Twilio)
 * Canal technique pur - route vers /api/send-whatsapp
 *
 * @param {string} phoneNumber - Numéro de téléphone du destinataire
 * @param {string} message - Message généré par l'IA
 * @param {object} _legacyConfig - Ignoré (rétrocompat)
 * @returns {Promise<{success: boolean, sid?: string, error?: string}>}
 */
export const sendWhatsAppGateway = async (phoneNumber, message, _legacyConfig = {}) => {
  console.log('[Gateway] DEMANDE WHATSAPP (Meta Cloud API) - Destination:', phoneNumber);

  let formattedPhone = phoneNumber.replace(/[^\d+]/g, '');
  if (!formattedPhone.startsWith('+')) {
    formattedPhone = formattedPhone.startsWith('0')
      ? '+41' + formattedPhone.substring(1)
      : '+' + formattedPhone;
  }

  try {
    const response = await fetch(`${BACKEND_URL}/api/send-whatsapp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: formattedPhone, message: String(message) })
    });

    const data = await response.json();

    if (data.status === 'success') {
      console.log('[Gateway] ✅ WhatsApp envoyé - ID:', data.sid);
      return { success: true, sid: data.sid, channel: 'whatsapp' };
    } else if (data.status === 'simulated') {
      return { success: true, simulated: true, channel: 'whatsapp' };
    } else {
      console.error('[Gateway] ❌ Erreur WhatsApp:', data.error);
      return { success: false, error: data.error || 'Erreur envoi', channel: 'whatsapp' };
    }
  } catch (error) {
    console.error('[Gateway] ❌ Erreur transmission WhatsApp:', error);
    return { success: false, error: error.message, channel: 'whatsapp' };
  }
};

/**
 * PASSERELLE UNIFIÉE - Point d'entrée unique pour l'agent IA
 * L'IA choisit le canal (email ou whatsapp) et cette fonction route
 * 
 * @param {string} channel - 'email' ou 'whatsapp'
 * @param {object} params - Paramètres selon le canal
 * @returns {Promise<{success: boolean, ...}>}
 */
export const sendMessageGateway = async (channel, params) => {
  console.log('[Gateway] 🤖 Agent IA demande envoi via canal:', channel);
  
  if (channel === 'email') {
    return sendEmailGateway(
      params.to_email,
      params.to_name,
      params.subject,
      params.message
    );
  }
  
  if (channel === 'whatsapp') {
    return sendWhatsAppGateway(
      params.phoneNumber,
      params.message
    );
  }
  
  return { success: false, error: `Canal inconnu: ${channel}` };
};

// === EXPORTS ===
export default {
  sendEmailGateway,
  sendWhatsAppGateway,
  sendMessageGateway,
  EMAILJS_SERVICE_ID,
  EMAILJS_TEMPLATE_ID,
  EMAILJS_PUBLIC_KEY,
  isInitialized: () => emailjsInitialized
};

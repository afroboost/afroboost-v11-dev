// whatsappService.js - V161: Service d'envoi WhatsApp via Meta Cloud API (+ Twilio legacy)
// Compatible Vercel - Configuration stockée dans MongoDB

// API URL
const API = process.env.REACT_APP_BACKEND_URL || '';

// === CONFIGURATION CACHE ===
let cachedConfig = null;

/**
 * Récupère la configuration WhatsApp depuis MongoDB
 */
export const getWhatsAppConfig = async () => {
  try {
    const response = await fetch(`${API}/api/whatsapp-config`);
    if (response.ok) {
      cachedConfig = await response.json();
      return cachedConfig;
    }
  } catch (e) {
    console.error('Error fetching WhatsApp config:', e);
  }
  return { apiMode: 'meta', metaAccessToken: '', metaPhoneNumberId: '', accountSid: '', authToken: '', fromNumber: '' };
};

/**
 * Récupère la configuration WhatsApp synchrone (depuis cache)
 */
export const getWhatsAppConfigSync = () => {
  return cachedConfig || { apiMode: 'meta', metaAccessToken: '', metaPhoneNumberId: '', accountSid: '', authToken: '', fromNumber: '' };
};

/**
 * Sauvegarde la configuration WhatsApp dans MongoDB
 */
export const saveWhatsAppConfig = async (config) => {
  try {
    const response = await fetch(`${API}/api/whatsapp-config`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    if (response.ok) {
      cachedConfig = await response.json();
      return true;
    }
  } catch (e) {
    console.error('Error saving WhatsApp config:', e);
  }
  return false;
};

/**
 * Vérifie si WhatsApp API est configuré
 */
export const isWhatsAppConfigured = () => {
  const config = cachedConfig || {};
  const mode = config.apiMode || 'meta';
  if (mode === 'meta') {
    return !!(config.metaAccessToken && config.metaPhoneNumberId);
  }
  // Legacy Twilio
  return !!(config.accountSid && config.authToken && config.fromNumber);
};

/**
 * Formate un numéro de téléphone au format E.164
 */
export const formatPhoneE164 = (phone) => {
  if (!phone) return '';
  let cleaned = phone.replace(/[^\d+]/g, '');
  if (!cleaned.startsWith('+')) {
    if (cleaned.startsWith('0')) {
      cleaned = '+41' + cleaned.substring(1);
    } else if (cleaned.length > 10) {
      cleaned = '+' + cleaned;
    } else {
      cleaned = '+41' + cleaned;
    }
  }
  return cleaned;
};

/**
 * V161: Envoie un message WhatsApp via le backend (Meta ou Twilio, routé côté serveur)
 */
export const sendWhatsAppMessage = async (params) => {
  const toNumber = formatPhoneE164(params.to);
  if (!toNumber || toNumber.length < 10) {
    return { success: false, error: 'Numéro de téléphone invalide' };
  }

  let personalizedMessage = params.message;
  if (params.contactName) {
    const firstName = params.contactName.split(' ')[0];
    personalizedMessage = params.message.replace(/{prénom}/gi, firstName);
  }

  try {
    // V161: Envoi via backend unifié (Meta ou Twilio, routé côté serveur)
    const response = await fetch(`${API}/api/send-whatsapp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        to: toNumber,
        message: personalizedMessage,
        mediaUrl: params.mediaUrl || null
      })
    });

    const data = await response.json();

    if (data.status === 'success') {
      return { success: true, sid: data.sid, status: data.status };
    } else if (data.status === 'simulated') {
      return { success: true, simulated: true, status: 'simulated' };
    } else {
      return { success: false, error: data.error || 'Erreur envoi WhatsApp', code: data.error_code };
    }
  } catch (error) {
    return { success: false, error: error.message };
  }
};

/**
 * Envoie des messages WhatsApp en masse
 */
export const sendBulkWhatsApp = async (recipients, campaign, onProgress) => {
  const results = { sent: 0, failed: 0, errors: [], details: [] };
  const total = recipients.length;

  for (let i = 0; i < recipients.length; i++) {
    const recipient = recipients[i];

    if (onProgress) {
      onProgress(i + 1, total, 'sending', recipient.name || recipient.phone);
    }

    try {
      const result = await sendWhatsAppMessage({
        to: recipient.phone,
        message: campaign.message,
        mediaUrl: campaign.mediaUrl,
        contactName: recipient.name
      });

      if (result.success) {
        results.sent++;
        results.details.push({ phone: recipient.phone, name: recipient.name, status: 'sent', sid: result.sid });
      } else {
        results.failed++;
        results.errors.push(`${recipient.phone}: ${result.error}`);
        results.details.push({ phone: recipient.phone, name: recipient.name, status: 'failed', error: result.error });
      }
    } catch (error) {
      results.failed++;
      results.errors.push(`${recipient.phone}: ${error.message}`);
      results.details.push({ phone: recipient.phone, name: recipient.name, status: 'failed', error: error.message });
    }

    if (i < recipients.length - 1) {
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }

  if (onProgress) {
    onProgress(total, total, 'completed');
  }

  return results;
};

/**
 * Teste la configuration WhatsApp
 */
export const testWhatsAppConfig = async (testPhone) => {
  return sendWhatsAppMessage({
    to: testPhone,
    message: '🎉 Test Afroboost WhatsApp!\n\nVotre configuration Meta WhatsApp fonctionne correctement.',
    contactName: 'Test'
  });
};

export default {
  getWhatsAppConfig,
  getWhatsAppConfigSync,
  saveWhatsAppConfig,
  isWhatsAppConfigured,
  formatPhoneE164,
  sendWhatsAppMessage,
  sendBulkWhatsApp,
  testWhatsAppConfig
};

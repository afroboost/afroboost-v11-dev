// aiResponseService.js - Service IA pour réponses WhatsApp automatiques
// Compatible Vercel - Utilise OpenAI via Afroboost API
// Ce service est utilisé côté frontend pour la configuration

// === CONFIGURATION PAR DÉFAUT ===
const DEFAULT_AI_CONFIG = {
  enabled: false,
  systemPrompt: `Tu es l'assistant virtuel d'Afroboost, une expérience fitness unique combinant cardio, danse afrobeat et casques audio immersifs.

Ton rôle:
- Répondre aux questions sur les cours, les offres et les réservations
- Être chaleureux, dynamique et motivant comme un coach fitness
- Utiliser un ton amical et des emojis appropriés
- Personnaliser les réponses avec le prénom du client quand disponible

Informations clés:
- Les cours sont dispensés par des coachs professionnels
- Les participants portent des casques audio sans fil
- L'ambiance est énergique et fun
- Les réservations se font via l'application

Si tu ne connais pas la réponse, oriente vers le contact: contact.artboost@gmail.com`,
  model: 'gpt-4o-mini',
  provider: 'openai',
  lastMediaUrl: '', // Dernier média envoyé pour contexte
  logs: [] // Logs des réponses IA
};

// Clé localStorage pour la configuration
const AI_CONFIG_KEY = 'afroboost_ai_config';

/**
 * Récupère la configuration de l'IA
 */
export const getAIConfig = () => {
  try {
    const stored = localStorage.getItem(AI_CONFIG_KEY);
    if (stored) {
      return { ...DEFAULT_AI_CONFIG, ...JSON.parse(stored) };
    }
  } catch (e) {
    console.error('Error reading AI config:', e);
  }
  return DEFAULT_AI_CONFIG;
};

/**
 * Sauvegarde la configuration de l'IA
 */
export const saveAIConfig = (config) => {
  try {
    localStorage.setItem(AI_CONFIG_KEY, JSON.stringify(config));
    return true;
  } catch (e) {
    console.error('Error saving AI config:', e);
    return false;
  }
};

/**
 * Vérifie si l'IA est activée
 */
export const isAIEnabled = () => {
  const config = getAIConfig();
  return config.enabled === true;
};

/**
 * Met à jour le dernier média envoyé (pour contexte IA)
 */
export const setLastMediaUrl = (mediaUrl) => {
  const config = getAIConfig();
  config.lastMediaUrl = mediaUrl;
  saveAIConfig(config);
};

/**
 * Ajoute un log de réponse IA
 */
export const addAILog = (log) => {
  const config = getAIConfig();
  const newLog = {
    id: Date.now(),
    timestamp: new Date().toISOString(),
    ...log
  };
  // Garder les 50 derniers logs
  config.logs = [newLog, ...(config.logs || [])].slice(0, 50);
  saveAIConfig(config);
  return newLog;
};

/**
 * Récupère les logs de l'IA
 */
export const getAILogs = () => {
  const config = getAIConfig();
  return config.logs || [];
};

/**
 * Efface les logs de l'IA
 */
export const clearAILogs = () => {
  const config = getAIConfig();
  config.logs = [];
  saveAIConfig(config);
};

/**
 * Trouve un client par numéro de téléphone dans les réservations
 */
export const findClientByPhone = (phone, reservations = []) => {
  if (!phone) return null;
  
  // Normaliser le numéro de téléphone
  const normalizedPhone = phone.replace(/\D/g, '');
  
  for (const reservation of reservations) {
    const resPhone = (reservation.whatsapp || reservation.phone || '').replace(/\D/g, '');
    if (resPhone && normalizedPhone.includes(resPhone.slice(-9))) {
      return {
        name: reservation.userName || reservation.name,
        email: reservation.userEmail || reservation.email,
        phone: reservation.whatsapp || reservation.phone
      };
    }
  }
  return null;
};

/**
 * Construit le contexte pour l'IA avec les infos client
 */
export const buildAIContext = (clientInfo, lastMediaUrl, customContext = '') => {
  let context = '';
  
  if (clientInfo?.name) {
    context += `\n\nClient actuel: ${clientInfo.name}`;
    if (clientInfo.email) context += ` (${clientInfo.email})`;
  }
  
  if (lastMediaUrl) {
    context += `\n\nNote: Tu as récemment envoyé un média (image/vidéo) à ce client: ${lastMediaUrl}. Tu peux lui demander s'il l'a bien reçu ou faire référence au contenu.`;
  }
  
  if (customContext) {
    context += `\n\n${customContext}`;
  }
  
  return context;
};

export default {
  getAIConfig,
  saveAIConfig,
  isAIEnabled,
  setLastMediaUrl,
  addAILog,
  getAILogs,
  clearAILogs,
  findClientByPhone,
  buildAIContext
};

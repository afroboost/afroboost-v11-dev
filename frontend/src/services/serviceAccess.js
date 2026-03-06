/**
 * Service Access Control - Vérification des droits d'accès aux services
 * 
 * Architecture Business Model:
 * - Super Admin: Contrôle les feature flags globaux (AUDIO_SERVICE_ENABLED, etc.)
 * - Coach: Doit avoir l'abonnement correspondant (hasAudioService, etc.)
 * - Accès = Feature Flag ON + Coach Subscription OK
 * 
 * Usage:
 * ```js
 * import { checkServiceAccess, ServiceAccessGuard } from './services/serviceAccess';
 * 
 * // Vérification programmatique
 * const access = await checkServiceAccess('audio');
 * if (!access.hasAccess) {
 *   alert(access.reason);
 *   return;
 * }
 * 
 * // Composant garde
 * <ServiceAccessGuard service="audio" fallback={<UpgradePrompt />}>
 *   <AudioFeature />
 * </ServiceAccessGuard>
 * ```
 */

import axios from 'axios';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

/**
 * Cache local pour éviter les appels API répétés
 * TTL: 5 minutes
 */
const accessCache = {
  data: {},
  timestamps: {},
  TTL: 5 * 60 * 1000 // 5 minutes
};

/**
 * Vérifie si le cache est valide
 */
const isCacheValid = (service) => {
  if (!accessCache.data[service] || !accessCache.timestamps[service]) return false;
  return Date.now() - accessCache.timestamps[service] < accessCache.TTL;
};

/**
 * Invalide le cache (appeler après modification des droits)
 */
export const invalidateAccessCache = (service = null) => {
  if (service) {
    delete accessCache.data[service];
    delete accessCache.timestamps[service];
  } else {
    accessCache.data = {};
    accessCache.timestamps = {};
  }
};

/**
 * Vérifie l'accès à un service spécifique
 * 
 * @param {string} service - Nom du service: "audio", "video", "streaming"
 * @param {boolean} useCache - Utiliser le cache (défaut: true)
 * @returns {Promise<{
 *   hasAccess: boolean,
 *   reason: string,
 *   featureFlagEnabled: boolean,
 *   coachHasSubscription: boolean,
 *   service: string
 * }>}
 */
export const checkServiceAccess = async (service, useCache = true) => {
  // Vérifier le cache d'abord
  if (useCache && isCacheValid(service)) {
    console.log(`🔒 Service access (cached): ${service} = ${accessCache.data[service].hasAccess}`);
    return accessCache.data[service];
  }

  try {
    const response = await axios.get(`${API}/verify-service-access/${service}`);
    const accessData = response.data;
    
    // Mettre en cache
    accessCache.data[service] = accessData;
    accessCache.timestamps[service] = Date.now();
    
    console.log(`🔒 Service access (API): ${service} = ${accessData.hasAccess}`);
    return accessData;
    
  } catch (err) {
    console.error(`Error checking service access for ${service}:`, err);
    
    // En cas d'erreur, bloquer l'accès par sécurité
    return {
      hasAccess: false,
      reason: "Erreur de vérification des droits d'accès",
      featureFlagEnabled: false,
      coachHasSubscription: false,
      service
    };
  }
};

/**
 * Vérifie l'accès à plusieurs services en parallèle
 * 
 * @param {string[]} services - Liste des services à vérifier
 * @returns {Promise<Object>} - Map service -> accessData
 */
export const checkMultipleServicesAccess = async (services) => {
  const results = await Promise.all(
    services.map(service => checkServiceAccess(service))
  );
  
  return services.reduce((acc, service, idx) => {
    acc[service] = results[idx];
    return acc;
  }, {});
};

/**
 * Récupère les feature flags globaux
 * (Pour affichage admin uniquement)
 */
export const getFeatureFlags = async () => {
  try {
    const response = await axios.get(`${API}/feature-flags`);
    return response.data;
  } catch (err) {
    console.error('Error fetching feature flags:', err);
    return {
      AUDIO_SERVICE_ENABLED: false,
      VIDEO_SERVICE_ENABLED: false,
      STREAMING_SERVICE_ENABLED: false
    };
  }
};

/**
 * Met à jour les feature flags (Super Admin only)
 */
export const updateFeatureFlags = async (updates) => {
  try {
    const response = await axios.put(`${API}/feature-flags`, updates);
    invalidateAccessCache(); // Invalider le cache après modification
    return response.data;
  } catch (err) {
    console.error('Error updating feature flags:', err);
    throw err;
  }
};

/**
 * Récupère l'abonnement du coach actuel
 */
export const getCoachSubscription = async () => {
  try {
    const response = await axios.get(`${API}/coach-subscription`);
    return response.data;
  } catch (err) {
    console.error('Error fetching coach subscription:', err);
    return {
      hasAudioService: false,
      hasVideoService: false,
      hasStreamingService: false,
      subscriptionPlan: 'free'
    };
  }
};

/**
 * Met à jour l'abonnement du coach
 */
export const updateCoachSubscription = async (updates) => {
  try {
    const response = await axios.put(`${API}/coach-subscription`, updates);
    invalidateAccessCache(); // Invalider le cache après modification
    return response.data;
  } catch (err) {
    console.error('Error updating coach subscription:', err);
    throw err;
  }
};

/**
 * Fonction utilitaire: Bloque l'accès si le service n'est pas disponible
 * Affiche un message d'erreur approprié
 * 
 * @param {string} service - Nom du service
 * @param {function} onDenied - Callback si accès refusé (reçoit reason)
 * @returns {Promise<boolean>} - true si accès autorisé
 */
export const requireServiceAccess = async (service, onDenied = null) => {
  const access = await checkServiceAccess(service);
  
  if (!access.hasAccess) {
    if (onDenied) {
      onDenied(access.reason);
    } else {
      // Message par défaut
      console.warn(`🚫 Accès refusé au service ${service}: ${access.reason}`);
    }
    return false;
  }
  
  return true;
};

/**
 * Services disponibles
 */
export const SERVICES = {
  AUDIO: 'audio',
  VIDEO: 'video',
  STREAMING: 'streaming'
};

/**
 * Plans d'abonnement
 */
export const SUBSCRIPTION_PLANS = {
  FREE: 'free',
  BASIC: 'basic',
  PREMIUM: 'premium',
  ENTERPRISE: 'enterprise'
};

export default {
  checkServiceAccess,
  checkMultipleServicesAccess,
  requireServiceAccess,
  getFeatureFlags,
  updateFeatureFlags,
  getCoachSubscription,
  updateCoachSubscription,
  invalidateAccessCache,
  SERVICES,
  SUBSCRIPTION_PLANS
};

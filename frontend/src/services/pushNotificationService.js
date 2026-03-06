// /services/pushNotificationService.js - Gestion des notifications push
// Web Push API avec Service Worker pour Afroboost

import axios from 'axios';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

// Clé pour stocker l'état de souscription
const PUSH_SUBSCRIPTION_KEY = 'af_push_subscribed';
const PUSH_ASKED_KEY = 'af_push_asked';

/**
 * Vérifie si les notifications push sont supportées
 */
export const isPushSupported = () => {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
};

/**
 * Vérifie si l'utilisateur a déjà été sollicité pour les notifications
 */
export const hasAskedForPermission = () => {
  return localStorage.getItem(PUSH_ASKED_KEY) === 'true';
};

/**
 * Marque que l'utilisateur a été sollicité
 */
export const markAsAsked = () => {
  localStorage.setItem(PUSH_ASKED_KEY, 'true');
};

/**
 * Vérifie si l'utilisateur est déjà inscrit aux notifications
 */
export const isSubscribed = () => {
  return localStorage.getItem(PUSH_SUBSCRIPTION_KEY) === 'true';
};

/**
 * Convertit une clé base64 URL-safe en Uint8Array
 */
const urlBase64ToUint8Array = (base64String) => {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');
  
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
};

/**
 * Enregistre le Service Worker
 */
export const registerServiceWorker = async () => {
  if (!isPushSupported()) {
    console.log('Push notifications not supported');
    return null;
  }
  
  try {
    const registration = await navigator.serviceWorker.register('/sw.js');
    console.log('Service Worker registered:', registration.scope);
    return registration;
  } catch (error) {
    console.error('Service Worker registration failed:', error);
    return null;
  }
};

/**
 * Demande la permission pour les notifications (non intrusive)
 * À appeler après le premier message de l'utilisateur
 */
export const requestNotificationPermission = async () => {
  if (!isPushSupported()) {
    return 'unsupported';
  }
  
  // Vérifier l'état actuel
  if (Notification.permission === 'granted') {
    return 'granted';
  }
  
  if (Notification.permission === 'denied') {
    return 'denied';
  }
  
  // Demander la permission
  try {
    const permission = await Notification.requestPermission();
    return permission;
  } catch (error) {
    console.error('Permission request failed:', error);
    return 'error';
  }
};

/**
 * Souscrit aux notifications push pour un participant
 * @param {string} participantId - ID du participant
 * @returns {boolean} - Succès de la souscription
 */
export const subscribeToPush = async (participantId) => {
  if (!isPushSupported() || !participantId) {
    return false;
  }
  
  try {
    // 1. Enregistrer le Service Worker
    const registration = await registerServiceWorker();
    if (!registration) {
      return false;
    }
    
    // 2. Récupérer la clé VAPID du serveur
    const vapidResponse = await axios.get(`${API}/push/vapid-key`);
    const vapidPublicKey = vapidResponse.data.publicKey;
    
    if (!vapidPublicKey) {
      console.error('VAPID public key not available');
      return false;
    }
    
    // 3. S'abonner aux notifications push
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
    });
    
    // 4. Envoyer la souscription au serveur
    await axios.post(`${API}/push/subscribe`, {
      participant_id: participantId,
      subscription: subscription.toJSON()
    });
    
    // 5. Marquer comme souscrit
    localStorage.setItem(PUSH_SUBSCRIPTION_KEY, 'true');
    console.log('Successfully subscribed to push notifications');
    return true;
    
  } catch (error) {
    console.error('Push subscription failed:', error);
    return false;
  }
};

/**
 * Se désabonne des notifications push
 * @param {string} participantId - ID du participant
 */
export const unsubscribeFromPush = async (participantId) => {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    
    if (subscription) {
      await subscription.unsubscribe();
    }
    
    if (participantId) {
      await axios.delete(`${API}/push/subscribe/${participantId}`);
    }
    
    localStorage.removeItem(PUSH_SUBSCRIPTION_KEY);
    return true;
  } catch (error) {
    console.error('Unsubscribe failed:', error);
    return false;
  }
};

/**
 * Demande les notifications de manière non intrusive
 * À appeler après le premier message envoyé par l'utilisateur
 * @param {string} participantId - ID du participant
 */
export const promptForNotifications = async (participantId) => {
  // Ne pas demander si déjà souscrit ou déjà demandé
  if (isSubscribed() || hasAskedForPermission()) {
    return { prompted: false, reason: 'already_handled' };
  }
  
  // Ne pas demander si non supporté
  if (!isPushSupported()) {
    return { prompted: false, reason: 'not_supported' };
  }
  
  // Marquer comme demandé
  markAsAsked();
  
  // Demander la permission
  const permission = await requestNotificationPermission();
  
  if (permission === 'granted') {
    // S'abonner
    const subscribed = await subscribeToPush(participantId);
    return { prompted: true, permission, subscribed };
  }
  
  return { prompted: true, permission, subscribed: false };
};

/**
 * Affiche une notification locale (pour le son)
 * Utilisé quand l'app est ouverte
 */
export const showLocalNotification = async (title, body, options = {}) => {
  if (Notification.permission !== 'granted') {
    return false;
  }
  
  try {
    const registration = await navigator.serviceWorker.ready;
    await registration.showNotification(title, {
      body,
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      vibrate: [200, 100, 200],
      tag: 'afroboost-local',
      ...options
    });
    return true;
  } catch (error) {
    console.error('Local notification failed:', error);
    return false;
  }
};

export default {
  isPushSupported,
  hasAskedForPermission,
  isSubscribed,
  registerServiceWorker,
  requestNotificationPermission,
  subscribeToPush,
  unsubscribeFromPush,
  promptForNotifications,
  showLocalNotification
};

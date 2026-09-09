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

// ═══════════════════════════════════════════════════════════════════════════
// RENOUVELLEMENT DE L'ABONNEMENT PUSH — CE QUI MANQUAIT
// ═══════════════════════════════════════════════════════════════════════════
//
// LE DÉFAUT MESURÉ (09/09/2026). `isSubscribed()` ci-dessus lit un DRAPEAU
// LOCAL, jamais le navigateur. Une fois posé, il reste `true` à vie. Or le
// service de push révoque régulièrement un abonnement (réponse `410 Gone`) :
// le serveur le désactivait bien, mais le téléphone, lui, croyait toujours
// être inscrit et ne se réabonnait JAMAIS. Constat sur le compte du
// propriétaire : le seul abonnement Android a répondu 410 le 06/09, et aucun
// nouveau n'a été créé depuis — le téléphone était devenu injoignable en
// silence.
//
// LA SEULE QUESTION QUI VAILLE est `pushManager.getSubscription()` : elle
// interroge le navigateur, pas notre mémoire. C'est ce que font les fonctions
// ci-dessous.
//
// AUCUNE LOGIQUE NOUVELLE. Elles reprennent, à l'identique, la réconciliation
// déjà éprouvée du tableau de bord coach (P1-a..d) : état lu, abonnement
// courant réutilisé s'il existe, recréé sinon, endpoint remplacé DÉCLARÉ au
// serveur pour qu'il mette l'ancien au rebut. On la sort de l'écran coach pour
// que la PWA en bénéficie aussi, au lieu d'en écrire une deuxième version qui
// divergerait au premier correctif.

/** Clé locale : le dernier endpoint que CE navigateur a fait enregistrer. */
const CLE_DERNIER_ENDPOINT = 'af_push_last_endpoint';

/**
 * L'état des notifications, tel qu'on peut l'AFFICHER :
 * 'non_supporte' | 'denied' | 'default' | 'granted'.
 * Ne demande jamais rien, n'ouvre aucune popup.
 */
export const etatNotifications = () => {
  // `'Notification' in window` reste VRAI si la propriété existe avec la valeur
  // `undefined` — on ne s'en contente donc pas, sous peine de lire `.permission`
  // sur rien du tout et de casser l'écran au lieu de se taire.
  if (!isPushSupported() || typeof Notification === 'undefined' || !Notification) {
    return 'non_supporte';
  }
  return Notification.permission;   // 'granted' | 'denied' | 'default'
};

/** Convertit la clé VAPID. Identique à l'existant, factorisée ici. */
const enTableauOctets = (b64) => {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4);
  const base = (b64 + pad).replace(/-/g, '+').replace(/_/g, '/');
  const brut = window.atob(base);
  const out = new Uint8Array(brut.length);
  for (let i = 0; i < brut.length; ++i) out[i] = brut.charCodeAt(i);
  return out;
};

/**
 * Enregistre l'abonnement ET NOMME CELUI QU'IL REMPLACE.
 *
 * Le serveur ne peut pas deviner que deux endpoints viennent du même
 * navigateur — rien dans les données ne le dit. Le navigateur, lui, le sait :
 * il garde le dernier endpoint qu'il a fait enregistrer. C'est ce qui arrête
 * l'accumulation (184 endpoints pour un ou deux appareils réels).
 */
export const enregistrerAbonnement = async (sub, { participantId, role, email }) => {
  if (!sub || !participantId) return null;
  const endpoint = sub.endpoint;
  let precedent = null;
  try { precedent = localStorage.getItem(CLE_DERNIER_ENDPOINT) || null; } catch (e) { /* navigation privée */ }
  const reponse = await axios.post(`${API}/push/subscribe`, {
    participant_id: participantId,
    subscription: typeof sub.toJSON === 'function' ? sub.toJSON() : sub,
    role: role || undefined,
    email: email || undefined,
    // Jamais l'endpoint courant : le serveur refuse déjà ce cas, mais on ne lui
    // demande pas de nous protéger de nous-mêmes.
    previous_endpoint: precedent && precedent !== endpoint ? precedent : null,
  });
  if (!reponse || !reponse.data || reponse.data.success !== true) return null;
  try { localStorage.setItem(CLE_DERNIER_ENDPOINT, endpoint); } catch (e) { /* ignore */ }
  try { localStorage.setItem(PUSH_SUBSCRIPTION_KEY, 'true'); } catch (e) { /* ignore */ }
  // Relais pour le Service Worker : sans session, c'est son seul moyen de savoir
  // au nom de qui déclarer une rotation d'endpoint.
  try {
    const c = await caches.open('afroboost-push-owner');
    await c.put('owner', new Response(participantId));
  } catch (e) { /* le cache n'est qu'un relais */ }
  return endpoint;
};

/**
 * RÉCONCILIE l'abonnement de CET appareil. À appeler à l'ouverture de l'app.
 *
 * N'OUVRE JAMAIS DE POPUP : si la permission n'est pas déjà accordée, on se
 * contente de rendre l'état, et c'est l'interface qui proposera un bouton.
 * C'est ce que les navigateurs exigent, et cela évite de harceler quiconque.
 */
export const assurerAbonnementPush = async ({ participantId, role, email } = {}) => {
  const etat = etatNotifications();
  if (etat !== 'granted' || !participantId) return { etat, abonne: false };
  try {
    const registration = await navigator.serviceWorker.ready;
    let sub = await registration.pushManager.getSubscription();
    const existait = !!sub;
    if (!sub) {
      // La permission est DÉJÀ accordée : ce `subscribe` n'ouvre aucune popup.
      const cle = (await axios.get(`${API}/push/vapid-key`)).data.publicKey;
      if (!cle) return { etat, abonne: false, motif: 'vapid_absente' };
      sub = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: enTableauOctets(cle),
      });
    }
    const endpoint = await enregistrerAbonnement(sub, { participantId, role, email });
    return { etat, abonne: !!endpoint, recree: !existait, endpoint };
  } catch (e) {
    return { etat, abonne: false, motif: (e && e.message) || 'erreur' };
  }
};

/**
 * Le clic sur « Activer les notifications ». SEUL endroit qui demande la
 * permission — et uniquement sur un geste de l'utilisateur.
 * Ne boucle jamais : si c'est refusé, on rend l'état et on n'insiste pas.
 */
export const activerNotifications = async ({ participantId, role, email } = {}) => {
  if (!isPushSupported()) return { etat: 'non_supporte', abonne: false };
  if (Notification.permission === 'denied') return { etat: 'denied', abonne: false };
  const perm = await Notification.requestPermission();
  markAsAsked();
  if (perm !== 'granted') return { etat: perm, abonne: false };
  return assurerAbonnementPush({ participantId, role, email });
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
    
    // 4. Envoyer la souscription au serveur — V182: valider réponse
    const resp = await axios.post(`${API}/push/subscribe`, {
      participant_id: participantId,
      subscription: subscription.toJSON()
    });

    // V182: Valider la réponse backend (success: true requis)
    if (!resp || !resp.data || resp.data.success !== true) {
      console.error('[PUSH-V182] Backend subscribe response invalid:', resp && resp.data);
      return false;
    }

    // 5. Marquer comme souscrit
    localStorage.setItem(PUSH_SUBSCRIPTION_KEY, 'true');
    localStorage.setItem('af_push_pid', participantId); // V182: stocker pid pour diagnostic
    console.log('[PUSH-V182] Successfully subscribed for participant', participantId);
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

// V182: Diagnostic complet de l'état des notifications push
export const getPushDiagnostic = async () => {
  const result = {
    supported: isPushSupported(),
    permission: typeof Notification !== 'undefined' ? Notification.permission : 'unsupported',
    serviceWorkerActive: false,
    hasSubscription: false,
    backendKnowsSubscription: null,
    participantId: localStorage.getItem('af_push_pid') || null,
    localStorageSubscribed: localStorage.getItem(PUSH_SUBSCRIPTION_KEY) === 'true',
    error: null,
  };
  try {
    if ('serviceWorker' in navigator) {
      const reg = await navigator.serviceWorker.getRegistration();
      result.serviceWorkerActive = !!(reg && reg.active);
      if (reg) {
        const sub = await reg.pushManager.getSubscription();
        result.hasSubscription = !!sub;
        result.endpoint = sub ? sub.endpoint.substring(0, 60) + '...' : null;
      }
    }
  } catch (e) {
    result.error = String(e);
  }
  return result;
};

// V182: Envoyer une notification test pour vérifier de bout en bout
export const sendTestPushNotification = async (participantId) => {
  if (!participantId) return { success: false, error: 'No participantId' };
  try {
    const r = await axios.post(`${API}/push/send`, {
      participant_id: participantId,
      title: '🎉 Test Afroboost',
      body: 'Si tu vois ça, les notifications marchent !'
    });
    return { success: !!(r.data && r.data.push_sent), data: r.data };
  } catch (e) {
    return { success: false, error: String(e) };
  }
};

export default {
  isPushSupported,
  hasAskedForPermission,
  isSubscribed,
  etatNotifications,
  enregistrerAbonnement,
  assurerAbonnementPush,
  activerNotifications,
  registerServiceWorker,
  requestNotificationPermission,
  subscribeToPush,
  unsubscribeFromPush,
  promptForNotifications,
  showLocalNotification,
  getPushDiagnostic,
  sendTestPushNotification
};

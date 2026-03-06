// /services/notificationService.js - Service de notifications sonores et visuelles
// Pour le systeme de chat Afroboost - Optimise pour iOS et Android

/**
 * Sons de notification utilisant Audio HTML5 avec son Base64 de qualite
 * Optimise pour iOS (Safari) et Android
 * Son "soft" type Pop/Glass - se declenche uniquement si document.visibilityState === 'hidden'
 */

// Contexte Audio global avec gestion iOS
let audioContext = null;
let isAudioUnlocked = false;
let softPopAudio = null;

// === SON BASE64 "POP" DOUX ET DISCRET ===
// Son synthetique court (200ms) type "glass chime" - genere via Web Audio encode en WAV Base64
// Ce son est doux et non intrusif - ideal pour les notifications mobiles
const SOFT_POP_SOUND_BASE64 = 'data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YVoGAACBgYGBgYGBgYGBgYGBgYGBgYGBgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P3+/wABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fICEiIyQlJicoKSorLC0uLzAxMjM0NTY3ODk6Ozw9Pj9AQUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVpbXF1eX2BhYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ent8fX5/gIGCg4SFhoeIiYqLjI2Oj5CRkpOUlZaXmJmam5ydnp+goaKjpKWmp6ipqqusra6vsLGys7S1tre4ubq7vL2+v8DBwsPExcbHyMnKy8zNzs/Q0dLT1NXW19jZ2tvc3d7f4OHi4+Tl5ufo6err7O3u7/Dx8vP09fb3+Pn6+/z9/v8AAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyAhIiMkJSYnKCkqKywtLi8wMTIzNDU2Nzg5Ojs8PT4/QEFCQ0RFRkdISUpLTE1OT1BRUlNUVVZXWFlaW1xdXl9gYWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXp7fH1+f4CBgoOEhYaHiImKi4yNjo+QkZKTlJWWl5iZmpucnZ6foKGio6SlpqeoqaqrrK2ur7CxsrO0tba3uLm6u7y9vr/AwcLDxMXGx8jJysvMzc7P0NHS09TV1tfY2drb3N3e3+Dh4uPk5ebn6Onq6+zt7u/w8fLz9PX29/j5+vv8/f7/fn18e3p5eHd2dXRzcnFwb25tbGtqaWhnZmVkY2JhYF9eXVxbWllYV1ZVVFNSUVBPTk1MS0pJSEdGRURDQkFAPz49PDs6OTg3NjU0MzIxMC8uLSwrKikoJyYlJCMiISAfHh0cGxoZGBcWFRQTEhEQDw4NDAsKCQgHBgUEAwIBAP/+/fz7+vn49/b19PPy8fDv7u3s6+rp6Ofm5eTj4uHg397d3Nva2djX1tXU09LR0M/OzczLysnIx8bFxMPCwcC/vr28u7q5uLe2tbSzsrGwr66trKuqqainpqWko6KhoJ+enZybmpmYl5aVlJOSkZCPjo2Mi4qJiIeGhYSDgoGAgH9+fXx7enl4d3Z1dHNycXBvbm1sa2ppaGdmZWRjYmFgX15dXFtaWVhXVlVUU1JRUE9OTUxLSklIR0ZFRERDQkFAPz49PDs6OTg3NjU0MzIxMC8uLSwrKikoJyYlJCMiISAfHh0cGxoZGBcWFRQTEhEQDw4NDAsKCQgHBgUEAwIBAA==';

/**
 * Initialise l'objet Audio pour le son de notification
 * Utilise un son Base64 inline pour eviter les erreurs 404
 */
const initSoftPopAudio = () => {
  if (!softPopAudio) {
    try {
      softPopAudio = new Audio(SOFT_POP_SOUND_BASE64);
      softPopAudio.volume = 0.5; // Volume modere (50%)
      softPopAudio.preload = 'auto';
    } catch (e) {
      console.warn('[AUDIO] Impossible de creer Audio element:', e);
    }
  }
  return softPopAudio;
};

/**
 * Obtient le contexte audio, le creant si necessaire (pour sons synthetiques)
 */
const getAudioContext = () => {
  if (!audioContext) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) {
      audioContext = new AudioContext();
    }
  }
  return audioContext;
};

/**
 * Deverrouille l'audio sur iOS (necessite une interaction utilisateur)
 * A appeler lors du premier clic/tap de l'utilisateur
 */
export const unlockAudio = () => {
  if (isAudioUnlocked) return Promise.resolve();
  
  return new Promise((resolve) => {
    // Initialiser le son Base64
    const audio = initSoftPopAudio();
    if (audio) {
      audio.load();
    }
    
    const ctx = getAudioContext();
    if (!ctx) {
      isAudioUnlocked = true;
      resolve();
      return;
    }
    
    // Creer un son silencieux pour debloquer l'audio sur iOS
    const buffer = ctx.createBuffer(1, 1, 22050);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start(0);
    
    // Resumer le contexte si suspendu
    if (ctx.state === 'suspended') {
      ctx.resume().then(() => {
        isAudioUnlocked = true;
        resolve();
      });
    } else {
      isAudioUnlocked = true;
      resolve();
    }
  });
};

/**
 * Declenche une vibration sur mobile (si supporte)
 * Pattern: court-pause-court pour notification discrete
 */
export const triggerVibration = () => {
  if (navigator.vibrate) {
    navigator.vibrate([200, 100, 200]);
    console.log('[VIBRATION] Vibration declenchee');
    return true;
  }
  console.log('[VIBRATION] API non supportee');
  return false;
};

/**
 * Joue le son "soft pop" Base64 (son doux de qualite) + VIBRATION
 * Se declenche UNIQUEMENT si document.visibilityState === 'hidden'
 */
export const playSoftPopSound = async () => {
  // CONDITION OBLIGATOIRE: Ne jouer que si l'app est en arriere-plan
  if (document.visibilityState !== 'hidden') {
    console.log('[SOUND] App visible - son ignore');
    return false;
  }
  
  // VIBRATION: Meme si le telephone est en silencieux
  triggerVibration();
  
  try {
    const audio = initSoftPopAudio();
    if (audio) {
      audio.currentTime = 0;
      await audio.play();
      console.log('[SOUND] Son Pop joue (arriere-plan)');
      return true;
    }
  } catch (err) {
    console.warn('[SOUND] Lecture son Base64 echouee:', err);
  }
  return false;
};

/**
 * Joue un son de notification pour les messages entrants
 * Utilise le son Base64 "soft pop" si l'app est en arriere-plan
 * Sinon utilise Web Audio API pour un son synthetique discret
 * @param {string} type - 'message' | 'coach' | 'user' | 'private'
 */
export const playNotificationSound = async (type = 'message') => {
  // Si l'app est en arriere-plan, utiliser le son Base64 de qualite + vibration
  if (document.visibilityState === 'hidden') {
    const played = await playSoftPopSound();
    if (played) return;
  }
  
  // Vibration meme si son synthetique (mode silencieux)
  triggerVibration();
  
  // Fallback: son synthetique via Web Audio API (pour app au premier plan)
  try {
    const ctx = getAudioContext();
    if (!ctx) {
      console.warn('Web Audio API not supported');
      return;
    }
    
    // Resumer le contexte audio si suspendu (politique navigateur iOS/Chrome)
    if (ctx.state === 'suspended') {
      await ctx.resume();
    }

    const oscillator = ctx.createOscillator();
    const gainNode = ctx.createGain();
    
    // Ajouter un filtre pour un son plus doux sur mobile
    const filter = ctx.createBiquadFilter();
    filter.type = 'lowpass';
    filter.frequency.value = 2000;

    oscillator.connect(filter);
    filter.connect(gainNode);
    gainNode.connect(ctx.destination);
    
    oscillator.type = 'sine';
    
    const now = ctx.currentTime;

    // Differents sons selon le type
    switch (type) {
      case 'private':
        // Son URGENT pour message prive (triple bip ascendant)
        oscillator.frequency.setValueAtTime(440, now); // La4
        oscillator.frequency.setValueAtTime(554, now + 0.1); // Do#5
        oscillator.frequency.setValueAtTime(659, now + 0.2); // Mi5
        gainNode.gain.setValueAtTime(0.3, now);
        gainNode.gain.setValueAtTime(0.25, now + 0.1);
        gainNode.gain.setValueAtTime(0.2, now + 0.2);
        gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
        oscillator.start(now);
        oscillator.stop(now + 0.35);
        break;
        
      case 'coach':
        // Son distinctif pour reponse coach (double bip harmonieux)
        oscillator.frequency.setValueAtTime(523, now); // Do5
        oscillator.frequency.setValueAtTime(659, now + 0.12); // Mi5
        gainNode.gain.setValueAtTime(0.25, now);
        gainNode.gain.setValueAtTime(0.2, now + 0.1);
        gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
        oscillator.start(now);
        oscillator.stop(now + 0.25);
        break;
      
      case 'user':
        // Son aigu pour message utilisateur (notification subtile)
        oscillator.frequency.setValueAtTime(784, now); // Sol5
        gainNode.gain.setValueAtTime(0.15, now);
        gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
        oscillator.start(now);
        oscillator.stop(now + 0.15);
        break;
      
      default:
        // Son standard (bip agreable)
        oscillator.frequency.setValueAtTime(587, now); // Re5
        gainNode.gain.setValueAtTime(0.2, now);
        gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.12);
        oscillator.start(now);
        oscillator.stop(now + 0.12);
    }

  } catch (err) {
    console.warn('Notification sound failed:', err);
  }
};

/**
 * Joue un son de notification plus long et distinct (pour les notifications push)
 */
export const playPushNotificationSound = async () => {
  // Utiliser le son Base64 de qualite
  const played = await playSoftPopSound();
  if (played) return;
  
  // Fallback synthetique
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    
    if (ctx.state === 'suspended') {
      await ctx.resume();
    }

    const now = ctx.currentTime;
    
    // Creer un son de notification plus elabore
    const notes = [523, 659, 784]; // Do, Mi, Sol (accord majeur)
    
    notes.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      
      osc.type = 'sine';
      osc.frequency.value = freq;
      osc.connect(gain);
      gain.connect(ctx.destination);
      
      const startTime = now + i * 0.1;
      gain.gain.setValueAtTime(0.15, startTime);
      gain.gain.exponentialRampToValueAtTime(0.01, startTime + 0.3);
      
      osc.start(startTime);
      osc.stop(startTime + 0.3);
    });

  } catch (err) {
    console.warn('Push notification sound failed:', err);
  }
};

/**
 * Demande la permission pour les notifications browser
 * IMPORTANT: Doit etre appele suite a une action utilisateur (clic)
 * @returns {Promise<'granted'|'denied'|'default'|'unsupported'>} Status de la permission
 */
export const requestNotificationPermission = async () => {
  if (!('Notification' in window)) {
    console.log('[NOTIFICATIONS] Browser notifications not supported');
    return 'unsupported';
  }
  
  if (Notification.permission === 'granted') {
    return 'granted';
  }
  
  if (Notification.permission === 'denied') {
    console.log('[NOTIFICATIONS] Permission was denied previously');
    return 'denied';
  }
  
  // Permission is 'default' - ask user
  try {
    const permission = await Notification.requestPermission();
    console.log('[NOTIFICATIONS] Permission result:', permission);
    return permission;
  } catch (err) {
    console.error('[NOTIFICATIONS] Error requesting permission:', err);
    return 'denied';
  }
};

/**
 * Verifie l'etat actuel de la permission de notification
 * @returns {'granted'|'denied'|'default'|'unsupported'}
 */
export const getNotificationPermissionStatus = () => {
  if (!('Notification' in window)) {
    return 'unsupported';
  }
  return Notification.permission;
};

/**
 * Affiche une notification browser (si autorisee)
 * @param {string} title - Titre de la notification
 * @param {string} body - Corps du message
 * @param {object} options - Options supplementaires
 * @returns {Promise<{notification: Notification|null, fallbackNeeded: boolean}>}
 */
export const showBrowserNotification = async (title, body, options = {}) => {
  // Verifier le support et la permission
  if (!('Notification' in window)) {
    console.log('[NOTIFICATIONS] Browser not supported - fallback needed');
    return { notification: null, fallbackNeeded: true, reason: 'unsupported' };
  }
  
  if (Notification.permission !== 'granted') {
    console.log('[NOTIFICATIONS] Permission not granted - fallback needed');
    return { notification: null, fallbackNeeded: true, reason: 'permission_denied' };
  }

  try {
    const notification = new Notification(title, {
      body,
      icon: options.icon || '/favicon.ico',
      badge: options.badge || '/favicon.ico',
      tag: options.tag || 'afroboost-chat',
      requireInteraction: options.requireInteraction || false,
      silent: false,
      ...options
    });

    // Fermer automatiquement apres 8 secondes
    setTimeout(() => notification.close(), 8000);

    // Callback au clic - Focus la fenetre
    notification.onclick = (event) => {
      event.preventDefault();
      window.focus();
      notification.close();
      if (options.onClick) {
        options.onClick(event);
      }
    };

    console.log('[NOTIFICATIONS] Browser notification shown:', title);
    return { notification, fallbackNeeded: false };
    
  } catch (err) {
    console.error('[NOTIFICATIONS] Error showing notification:', err);
    return { notification: null, fallbackNeeded: true, reason: 'error' };
  }
};

/**
 * Affiche une notification systeme pour un nouveau message Afroboost
 * A utiliser quand l'onglet est en arriere-plan
 * @param {string} senderName - Nom de l'expediteur
 * @param {string} messageText - Texte du message (tronque si trop long)
 * @returns {Promise<boolean>} - true si la notification a ete affichee
 */
export const showNewMessageNotification = async (senderName, messageText) => {
  // Ne pas afficher si la fenetre a le focus
  if (document.hasFocus()) {
    console.log('[NOTIFICATIONS] Window has focus - skipping notification');
    return false;
  }
  
  // Tronquer le message si trop long (max 100 caracteres)
  const truncatedText = messageText && messageText.length > 100 
    ? messageText.substring(0, 97) + '...' 
    : messageText || '';
  
  const result = await showBrowserNotification(
    `Afroboost - ${senderName || 'Nouveau message'}`,
    truncatedText,
    {
      tag: 'afroboost-new-message',
      requireInteraction: false,
      onClick: () => {
        window.focus();
      }
    }
  );
  
  return !result.fallbackNeeded;
};

/**
 * Convertit une URL en lien cliquable
 * @param {string} text - Texte a analyser
 * @returns {string} - Texte avec liens HTML
 */
export const linkifyText = (text) => {
  if (!text) return '';
  
  // Si le texte contient deja du HTML (emojis img), le preserver
  const imgTags = [];
  let protectedText = text.replace(/<img[^>]+>/gi, (match) => {
    imgTags.push(match);
    return `__IMG_PLACEHOLDER_${imgTags.length - 1}__`;
  });
  
  // Regex pour detecter les URLs
  const urlRegex = /(https?:\/\/[^\s<]+[^<.,:;"')\]\s])/g;
  
  // Convertir les URLs en liens
  protectedText = protectedText.replace(urlRegex, (url) => {
    return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="chat-link">${url}</a>`;
  });
  
  // Restaurer les balises img
  imgTags.forEach((img, index) => {
    protectedText = protectedText.replace(`__IMG_PLACEHOLDER_${index}__`, img);
  });
  
  return protectedText;
};

/**
 * Mapping des emojis personnalises vers leurs equivalents natifs (fallback)
 */
const EMOJI_FALLBACK_MAP = {
  'fire': '🔥',
  'fire.svg': '🔥',
  'muscle': '💪',
  'muscle.svg': '💪',
  'heart': '❤️',
  'heart.svg': '❤️',
  'thumbsup': '👍',
  'thumbsup.svg': '👍',
  'star': '⭐',
  'star.svg': '⭐',
  'celebration': '🎉',
  'celebration.svg': '🎉'
};

/**
 * Parse les tags [emoji:filename.svg] et les convertit en balises <img>
 * @param {string} text - Texte avec potentiels tags emoji
 * @returns {string} - Texte avec balises img pour les emojis
 */
export const parseEmojis = (text) => {
  if (!text) return '';
  
  const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';
  
  // Regex pour detecter [emoji:filename.svg] ou [emoji:filename]
  const emojiRegex = /\[emoji:([^\]]+)\]/g;
  
  return text.replace(emojiRegex, (match, filename) => {
    const file = filename.includes('.') ? filename : `${filename}.svg`;
    const emojiName = filename.replace('.svg', '');
    const fallbackEmoji = EMOJI_FALLBACK_MAP[filename] || EMOJI_FALLBACK_MAP[file] || '😊';
    
    return `<img src="${API}/emojis/${file}" alt="${emojiName}" class="chat-emoji" style="width:20px;height:20px;vertical-align:middle;display:inline-block;margin:0 2px;" onerror="this.outerHTML='${fallbackEmoji}'" />`;
  });
};

/**
 * Combine le parsing d'emojis et la creation de liens
 * @param {string} text - Texte brut
 * @returns {string} - Texte HTML avec emojis et liens
 */
export const parseMessageContent = (text) => {
  if (!text) return '';
  
  let parsed = parseEmojis(text);
  parsed = linkifyText(parsed);
  
  return parsed;
};

/**
 * Verifie si le texte contient des URLs
 * @param {string} text - Texte a verifier
 * @returns {boolean}
 */
export const containsLinks = (text) => {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  return urlRegex.test(text);
};

// ==================== CLIGNOTEMENT TITRE ONGLET ====================
let originalTitle = document.title;
let titleInterval = null;
let isFlashing = false;

/**
 * Demarre le clignotement du titre de l'onglet pour attirer l'attention
 * @param {string} message - Message a afficher
 */
export const startTitleFlash = (message = 'Nouveau message !') => {
  if (isFlashing) return;
  
  originalTitle = document.title;
  isFlashing = true;
  let showMessage = true;
  
  titleInterval = setInterval(() => {
    document.title = showMessage ? message : originalTitle;
    showMessage = !showMessage;
  }, 1000);
  
  const handleFocus = () => {
    stopTitleFlash();
    window.removeEventListener('focus', handleFocus);
  };
  window.addEventListener('focus', handleFocus);
};

/**
 * Arrete le clignotement du titre et restaure le titre original
 */
export const stopTitleFlash = () => {
  if (titleInterval) {
    clearInterval(titleInterval);
    titleInterval = null;
  }
  document.title = originalTitle;
  isFlashing = false;
};

/**
 * Verifie si la fenetre/onglet a le focus
 * @returns {boolean}
 */
export const isWindowFocused = () => {
  return document.hasFocus();
};

/**
 * Notification complete pour MP: titre clignotant + badge
 */
export const notifyPrivateMessage = (senderName = 'Quelqu\'un') => {
  if (!isWindowFocused()) {
    startTitleFlash(`${senderName} vous a envoye un message !`);
  }
  
  showBrowserNotification(
    'Nouveau message prive',
    `${senderName} vous a envoye un message`,
    { tag: 'private' }
  );
};

export default {
  playNotificationSound,
  playPushNotificationSound,
  playSoftPopSound,
  triggerVibration,
  unlockAudio,
  requestNotificationPermission,
  getNotificationPermissionStatus,
  showBrowserNotification,
  showNewMessageNotification,
  linkifyText,
  parseEmojis,
  parseMessageContent,
  containsLinks,
  startTitleFlash,
  stopTitleFlash,
  isWindowFocused,
  notifyPrivateMessage
};

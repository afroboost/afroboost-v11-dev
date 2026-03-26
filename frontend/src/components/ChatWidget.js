// /components/ChatWidget.js - Widget IA flottant avec capture de leads et reconnaissance automatique
// Architecture modulaire Afroboost - Utilise l'API chat améliorée
// Fonctionnalités: Socket.IO temps réel, notifications push, sons, liens cliquables, suppression historique

import React, { useState, useEffect, useRef, useCallback, memo } from 'react';
import ReactDOM from 'react-dom';
import axios from 'axios';
import { io } from 'socket.io-client';
import { 
  parseMessageContent, 
  notifyPrivateMessage,
  stopTitleFlash,
  showNewMessageNotification,
  requestNotificationPermission,
  getNotificationPermissionStatus,
  unlockAudio
} from '../services/notificationService';
import {
  isPushSupported,
  promptForNotifications,
  registerServiceWorker,
  isSubscribed,
  subscribeToPush,
  unsubscribeFromPush
} from '../services/pushNotificationService';
import { 
  isInSilenceHours, 
  getSilenceHoursLabel,
  playSoundIfAllowed,
  SOUND_TYPES 
} from '../services/SoundManager';
import AfricanEmojiPicker from './chat/AfricanEmojiPicker';
import SubscriberForm from './chat/SubscriberForm';
import OnboardingTunnel from './chat/OnboardingTunnel';
import PrivateChatView from './chat/PrivateChatView';
import BookingPanel from './chat/BookingPanel';
import MessageSkeleton from './chat/MessageSkeleton';
import MediaMessage from './chat/MediaMessage';
import { parseMediaUrl, isMediaUrl } from '../services/MediaParser';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';
const SOCKET_URL = process.env.REACT_APP_BACKEND_URL || ''; // URL Socket.IO (même que backend)

// Clés localStorage pour la mémorisation client (persistance de session)
const CHAT_CLIENT_KEY = 'af_chat_client';
const CHAT_SESSION_KEY = 'af_chat_session';
const AFROBOOST_IDENTITY_KEY = 'afroboost_identity'; // Clé unifiée pour l'identité
const AFROBOOST_PROFILE_KEY = 'afroboost_profile'; // Profil abonné avec code promo validé
const MESSAGE_CACHE_KEY = 'afroboost_last_msgs'; // Cache hybride pour chargement instantané

// Icône Plein Écran
const FullscreenIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
    <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
  </svg>
);

// Icône Réduire Plein Écran
const ExitFullscreenIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
    <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>
  </svg>
);

// Icône Emoji
const EmojiIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-5-6c.78 2.34 2.72 4 5 4s4.22-1.66 5-4H7zm8.5-3c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11z"/>
  </svg>
);

// v9.4.2: Icône Bulle de Chat Afroboost (remplace WhatsApp)
const ChatBubbleIcon = () => (
  <svg viewBox="0 0 24 24" width="28" height="28" fill="white">
    <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/>
    <circle cx="8" cy="10" r="1.5"/>
    <circle cx="12" cy="10" r="1.5"/>
    <circle cx="16" cy="10" r="1.5"/>
  </svg>
);

// Alias pour compatibilité (remplace WhatsAppIcon)
const WhatsAppIcon = ChatBubbleIcon;

// Icône Fermer
const CloseIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="white">
    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
  </svg>
);

// Icône Envoyer
const SendIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="white">
    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
  </svg>
);

// Icône Corbeille
const TrashIcon = () => (
  <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
    <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
  </svg>
);

// Icône Groupe
const GroupIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
    <path d="M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z"/>
  </svg>
);

/**
 * Formate l'horodatage d'un message
 * - "À l'instant" si < 60 secondes
 * - "14:05" pour aujourd'hui
 * - "Hier, 09:15" pour hier
 * - "08/02, 18:30" pour les autres jours
 */
const formatMessageTime = (dateStr) => {
  if (!dateStr) return '';
  
  try {
    const date = new Date(dateStr);
    if (isNaN(date.getTime())) return '';
    
    const now = new Date();
    const diffSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);
    
    // Message envoyé il y a moins de 60 secondes
    if (diffSeconds < 60 && diffSeconds >= 0) {
      return 'À l\'instant';
    }
    
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const msgDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    
    // Format heure locale 24h (Europe/Paris)
    const timeStr = date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', hour12: false });
    
    if (msgDate.getTime() === today.getTime()) {
      return timeStr;
    } else if (msgDate.getTime() === yesterday.getTime()) {
      return `Hier, ${timeStr}`;
    } else {
      const day = String(date.getDate()).padStart(2, '0');
      const month = String(date.getMonth() + 1).padStart(2, '0');
      return `${day}/${month}, ${timeStr}`;
    }
  } catch (e) {
    return '';
  }
};

// === COMPOSANTS MÉDIA INLINE ===
// v16.4: Lecteur YouTube natif — youtube-nocookie.com + overlay anti-sortie
const InlineYouTubePlayer = ({ videoId, thumbnailUrl }) => {
  const [isPlaying, setIsPlaying] = useState(false);

  return (
    <div style={{ marginTop: '8px', borderRadius: '12px', overflow: 'hidden', maxWidth: '100%', position: 'relative', background: '#000' }} data-testid="inline-youtube">
      {!isPlaying ? (
        <button
          onClick={() => setIsPlaying(true)}
          style={{
            width: '100%',
            aspectRatio: '16/9',
            background: `url(${thumbnailUrl}) center/cover no-repeat`,
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative'
          }}
          data-testid="youtube-thumbnail-btn"
        >
          {/* v16.4: Play button Afroboost — fond noir + accent #D91CD2 */}
          <div style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: 'rgba(217, 28, 210, 0.85)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 20px rgba(217, 28, 210, 0.4)',
            transition: 'transform 0.2s'
          }}>
            <svg width="22" height="22" fill="#fff" viewBox="0 0 24 24">
              <polygon points="6 3 20 12 6 21 6 3"/>
            </svg>
          </div>
        </button>
      ) : (
        <div style={{ position: 'relative', width: '100%', aspectRatio: '16/9' }}>
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&mute=1&rel=0&playsinline=1&modestbranding=1&showinfo=0&iv_load_policy=3&disablekb=0&fs=1`}
            style={{ width: '100%', height: '100%', border: 'none', position: 'absolute', top: 0, left: 0 }}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
            allowFullScreen
            title="Afroboost Video"
          />
          {/* v16.4: Overlay transparent haut — bloque le logo YouTube cliquable */}
          <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '40px', zIndex: 2, cursor: 'default' }} />
          {/* v16.4: Overlay transparent bas-droite — bloque le bouton YouTube */}
          <div style={{ position: 'absolute', bottom: 0, right: 0, width: '120px', height: '30px', zIndex: 2, cursor: 'default' }} />
        </div>
      )}
    </div>
  );
};

const InlineDriveImage = ({ directUrl, previewUrl }) => {
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  
  // Timeout de 3 secondes pour les images Drive
  useEffect(() => {
    const timer = setTimeout(() => {
      if (loading) {
        setError(true);
        setLoading(false);
      }
    }, 3000);
    return () => clearTimeout(timer);
  }, [loading]);
  
  if (error) {
    return (
      <a 
        href={previewUrl || directUrl} 
        target="_blank" 
        rel="noopener noreferrer"
        style={{
          display: 'block',
          marginTop: '8px',
          padding: '12px',
          background: 'linear-gradient(135deg, #1a1a2e, #16213e)',
          borderRadius: '12px',
          textDecoration: 'none',
          color: '#fff',
          textAlign: 'center'
        }}
        data-testid="drive-fallback"
      >
        <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginBottom: '4px' }}>
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <div style={{ fontSize: '12px' }}>Voir l'image sur Drive</div>
      </a>
    );
  }
  
  return (
    <img
      src={directUrl}
      alt="Google Drive"
      onLoad={() => setLoading(false)}
      onError={() => { setError(true); setLoading(false); }}
      style={{
        marginTop: '8px',
        maxWidth: '100%',
        borderRadius: '12px',
        display: loading ? 'none' : 'block'
      }}
      data-testid="inline-drive-image"
    />
  );
};

const InlineImage = ({ src }) => (
  <img
    src={src}
    alt="Image"
    style={{
      marginTop: '8px',
      maxWidth: '100%',
      borderRadius: '12px',
      display: 'block'
    }}
    data-testid="inline-image"
  />
);

// v16.4: CTA in-app — pas de redirection externe, écosystème fermé
const InlineCtaButton = ({ label, url }) => {
  // Validation stricte : label ET url doivent être non-vides
  if (!label || !url || typeof label !== 'string' || typeof url !== 'string') return null;
  const trimmedLabel = label.trim();
  const trimmedUrl = url.trim();
  if (!trimmedLabel || !trimmedUrl) return null;

  // Auto-ajout de https:// si manquant
  const safeUrl = trimmedUrl.startsWith('http://') || trimmedUrl.startsWith('https://')
    ? trimmedUrl
    : `https://${trimmedUrl}`;

  // v16.4: Détecte si le lien pointe vers Afroboost (navigation in-app)
  const isInternalLink = safeUrl.includes('afroboost') || safeUrl.includes(window.location.host) || safeUrl.startsWith('/') || safeUrl.startsWith('/?');

  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isInternalLink) {
      // Navigation in-app — pas de nouvel onglet
      const urlObj = new URL(safeUrl, window.location.origin);
      window.location.href = urlObj.pathname + urlObj.search + urlObj.hash;
    } else {
      // Lien externe — ouvre dans un nouvel onglet (seul cas autorisé)
      window.open(safeUrl, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <button
      onClick={handleClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '8px',
        marginTop: '10px',
        padding: '12px 20px',
        background: 'linear-gradient(135deg, #9333ea, #d91cd2)',
        borderRadius: '12px',
        color: '#fff',
        fontWeight: '600',
        fontSize: '14px',
        border: 'none',
        cursor: 'pointer',
        width: '100%',
        transition: 'transform 0.2s, opacity 0.2s'
      }}
      onMouseEnter={(e) => { e.currentTarget.style.transform = 'scale(1.02)'; e.currentTarget.style.opacity = '0.9'; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.opacity = '1'; }}
      data-testid="inline-cta-button"
    >
      {trimmedLabel}
      {/* v16.4: Icône flèche in-app au lieu d'ExternalIcon */}
      <svg width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24">
        <path d="M5 12h14M12 5l7 7-7 7"/>
      </svg>
    </button>
  );
};

/**
 * Composant pour afficher un message avec liens cliquables et emojis
 * Affiche le nom de l'expéditeur au-dessus de chaque bulle
 * Couleurs: Violet (#8B5CF6) pour le Coach, Gris foncé pour les membres/IA
 */
const MessageBubble = ({ msg, isUser, onParticipantClick, isCommunity, currentUserId, profilePhotoUrl, onReservationClick, onZoomPhoto, onDelete }) => {
  // v10.4: Fallback robuste pour texte (content, text, body - jamais vide)
  const messageText = msg.content || msg.text || msg.body || '';
  const htmlContent = parseMessageContent(messageText);
  const isOtherUser = isCommunity && msg.type === 'user' && msg.senderId && msg.senderId !== currentUserId;

  // v153: État pour afficher le bouton supprimer (long press mobile + hover desktop)
  const [showDelete, setShowDelete] = React.useState(false);
  const longPressTimer = React.useRef(null);

  // v10.3: RÉCAPITULATIF DE RÉSERVATION PREMIUM
  // v10.4: État local pour fermer/minimiser la carte
  const [isMinimized, setIsMinimized] = React.useState(false);

  // v153: Message supprimé — afficher placeholder
  if (msg.is_deleted) {
    return (
      <div style={{ alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: '75%', opacity: 0.5 }}>
        <div style={{
          background: 'rgba(255,255,255,0.05)',
          color: 'rgba(255,255,255,0.4)',
          padding: '8px 14px',
          borderRadius: '16px',
          fontSize: '12px',
          fontStyle: 'italic',
          border: '1px dashed rgba(255,255,255,0.1)'
        }}>
          🗑️ Message supprimé
        </div>
      </div>
    );
  }
  
  if (msg.isReservationSummary && msg.reservationDetails) {
    const details = msg.reservationDetails;
    
    // v10.4: Version minimisée après fermeture
    if (isMinimized) {
      return (
        <div
          style={{
            alignSelf: 'flex-start',
            maxWidth: '320px'
          }}
        >
          <div style={{
            fontSize: '10px',
            fontWeight: '600',
            marginBottom: '3px',
            marginLeft: '4px',
            color: '#A78BFA'
          }}>
            Coach Bassi
          </div>
          <button
            onClick={() => setIsMinimized(false)}
            style={{
              background: 'rgba(217, 28, 210, 0.2)',
              border: '1px solid rgba(217, 28, 210, 0.4)',
              borderRadius: '12px',
              padding: '10px 16px',
              color: '#D91CD2',
              fontSize: '12px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }}
          >
            ✨ Réservation confirmée - Voir détails
          </button>
        </div>
      );
    }
    
    return (
      <div
        style={{
          alignSelf: 'flex-start',
          maxWidth: '320px',
          width: '100%',
          position: 'relative'
        }}
      >
        <div style={{
          fontSize: '10px',
          fontWeight: '600',
          marginBottom: '3px',
          marginLeft: '4px',
          color: '#A78BFA'
        }}>
          Coach Bassi
        </div>
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(20, 10, 30, 0.95) 0%, rgba(30, 15, 45, 0.95) 100%)',
            border: '1px solid rgba(217, 28, 210, 0.5)',
            borderRadius: '20px',
            padding: '16px',
            boxShadow: '0 0 15px rgba(217, 28, 210, 0.15)',
            position: 'relative'
          }}
        >
          {/* v10.4: Bouton fermeture (X) */}
          <button
            onClick={() => setIsMinimized(true)}
            style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              width: '24px',
              height: '24px',
              borderRadius: '50%',
              background: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.2)',
              color: 'rgba(255,255,255,0.6)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '14px',
              transition: 'all 0.2s'
            }}
            onMouseOver={(e) => {
              e.target.style.background = 'rgba(217, 28, 210, 0.3)';
              e.target.style.color = 'white';
            }}
            onMouseOut={(e) => {
              e.target.style.background = 'rgba(255,255,255,0.1)';
              e.target.style.color = 'rgba(255,255,255,0.6)';
            }}
            data-testid="close-reservation-summary"
          >
            ×
          </button>
          
          <div style={{ textAlign: 'center', marginBottom: '12px' }}>
            <span style={{ fontSize: '24px' }}>✨</span>
            <h4 style={{ 
              color: '#D91CD2', 
              fontSize: '14px', 
              fontWeight: 'bold',
              margin: '8px 0 4px 0',
              textShadow: '0 0 10px rgba(217, 28, 210, 0.5)'
            }}>
              RÉSERVATION CONFIRMÉE
            </h4>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* Offre / Cours */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ color: '#D91CD2', fontSize: '14px' }}>📅</span>
              <div>
                <div style={{ color: '#A78BFA', fontSize: '10px', fontWeight: '600' }}>SÉANCE</div>
                <div style={{ color: 'white', fontSize: '13px', fontWeight: '500' }}>{details.courseName}</div>
              </div>
            </div>
            
            {/* v11.5: Date et Heure de la réservation */}
            {details.reservationDate && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#D91CD2', fontSize: '14px' }}>🗓️</span>
                <div>
                  <div style={{ color: '#A78BFA', fontSize: '10px', fontWeight: '600' }}>DATE & HEURE</div>
                  <div style={{ color: 'white', fontSize: '13px', fontWeight: '700' }}>
                    {details.reservationDate}
                  </div>
                </div>
              </div>
            )}
            
            {/* Solde restant */}
            {details.remaining && details.remaining !== 'N/A' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#D91CD2', fontSize: '14px' }}>🎟️</span>
                <div>
                  <div style={{ color: '#A78BFA', fontSize: '10px', fontWeight: '600' }}>SOLDE</div>
                  <div style={{ color: 'white', fontSize: '13px', fontWeight: '500' }}>
                    {details.remaining === 'illimite' ? 'Illimité' : `${details.remaining} séance(s) restante(s)`}
                  </div>
                </div>
              </div>
            )}
            
            {/* Validité */}
            {details.expiry && details.expiry !== 'Non définie' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ color: '#D91CD2', fontSize: '14px' }}>⏰</span>
                <div>
                  <div style={{ color: '#A78BFA', fontSize: '10px', fontWeight: '600' }}>VALIDITÉ</div>
                  <div style={{ color: 'white', fontSize: '13px', fontWeight: '500' }}>
                    Jusqu'au {new Date(details.expiry).toLocaleDateString('fr-FR')}
                  </div>
                </div>
              </div>
            )}
            
            {/* Client */}
            <div style={{ 
              borderTop: '1px solid rgba(217, 28, 210, 0.3)', 
              paddingTop: '10px',
              marginTop: '4px'
            }}>
              <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '11px' }}>
                Réservé par: <span style={{ color: 'white', fontWeight: '500' }}>{details.clientName}</span>
              </div>
              {details.promoCode && details.promoCode !== 'N/A' && (
                <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '11px' }}>
                  Code: <span style={{ color: '#D91CD2', fontWeight: '500' }}>{details.promoCode}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }
  
  // v153: Handlers long press (mobile) + hover (desktop) pour bouton supprimer
  const handleTouchStart = () => {
    if (!onDelete) return;
    longPressTimer.current = setTimeout(() => setShowDelete(true), 600);
  };
  const handleTouchEnd = () => {
    if (longPressTimer.current) clearTimeout(longPressTimer.current);
  };
  const handleDeleteClick = (e) => {
    e.stopPropagation();
    if (window.confirm('Supprimer ce message ?')) {
      onDelete(msg.id);
      setShowDelete(false);
    }
  };

  // === DÉTECTION AUTOMATIQUE DES MÉDIAS DANS LE TEXTE ===
  const detectMediaInText = (text) => {
    if (!text) return null;
    const urlPattern = /https?:\/\/[^\s<>"{}|\\^`\[\]]+/g;
    const urls = text.match(urlPattern) || [];
    for (const url of urls) {
      if (isMediaUrl(url)) {
        return parseMediaUrl(url);
      }
    }
    return null;
  };
  
  const detectedMedia = detectMediaInText(messageText);
  
  // Déterminer si c'est un message du Coach HUMAIN (pas l'IA)
  const isCoachMessage = msg.type === 'coach' || msg.is_admin === true || msg.role === 'coach';
  
  // Message IA (assistant automatique - Coach Bassi)
  const isAIMessage = msg.type === 'ai';
  
  // Déterminer le nom à afficher
  const getDisplayName = () => {
    if (isCoachMessage) return 'Coach Bassi';
    if (isAIMessage) return 'Coach Bassi';
    return msg.sender || msg.senderName || 'Membre';
  };
  const displayName = getDisplayName();
  
  // Couleur du nom selon le type
  const getNameColor = () => {
    if (isCoachMessage) return '#FBBF24'; // Jaune/Or pour Coach
    if (isAIMessage) return '#A78BFA';    // Violet clair pour IA
    return '#22D3EE';                      // Cyan pour membres
  };
  
  // Couleur de la bulle selon le type
  const getBubbleBackground = () => {
    if (isUser) {
      // Messages envoyés par l'utilisateur actuel (à droite)
      return 'linear-gradient(135deg, #d91cd2, #8b5cf6)';
    }
    if (isCoachMessage) {
      // Messages du Coach HUMAIN: Violet solide
      return '#8B5CF6';
    }
    // Messages IA et autres membres: Gris foncé
    return '#2D2D2D';
  };
  
  // v76: Récupérer l'avatar — photos cliquables pour zoom plein écran
  const getAvatar = () => {
    // Déterminer l'URL photo à afficher
    const photoUrl = (isUser && profilePhotoUrl) ? profilePhotoUrl : (msg.senderPhotoUrl || null);

    if (photoUrl) {
      return (
        <div
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            console.log('[V76] Zoom photo cliqué:', photoUrl);
            if (onZoomPhoto) onZoomPhoto(photoUrl);
          }}
          style={{
            width: '32px',
            height: '32px',
            minWidth: '32px',
            borderRadius: '50%',
            overflow: 'hidden',
            border: '2px solid #D91CD2',
            cursor: 'pointer',
            flexShrink: 0,
            WebkitTapHighlightColor: 'transparent',
            position: 'relative',
            zIndex: 10,
            pointerEvents: 'auto'
          }}
        >
          <img
            src={photoUrl}
            alt="avatar"
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
              pointerEvents: 'none'
            }}
          />
        </div>
      );
    }
    // Pas de photo = pas de zoom (initiale sur fond violet reste statique)
    return null;
  };
  
  // === DÉTECTION MÉDIA AVEC CTA ===
  // Si le message contient un média (media_url) et/ou un CTA - BLINDAGE
  const hasMedia = msg?.media_url && typeof msg.media_url === 'string' && msg.media_url.startsWith('http');
  const hasCta = msg?.cta_type && msg?.cta_text;
  
  // Si c'est un message média avec CTA, utiliser MediaMessage
  if (hasMedia || hasCta) {
    const ctaConfig = hasCta ? {
      type: msg.cta_type === 'reserver' ? 'RESERVER' :
            msg.cta_type === 'offre' ? 'OFFRE' :
            msg.cta_type === 'conversation' ? 'CONVERSATION' : 'PERSONNALISE',
      text: msg.cta_text,
      url: msg.cta_link || '#'
    } : null;
    
    return (
      <div
        style={{
          alignSelf: isUser ? 'flex-end' : 'flex-start',
          maxWidth: '320px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
          position: 'relative'
        }}
        onMouseEnter={() => onDelete && setShowDelete(true)}
        onMouseLeave={() => setShowDelete(false)}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        {/* v153: Bouton supprimer sur média */}
        {showDelete && onDelete && (
          <button
            onClick={handleDeleteClick}
            style={{
              position: 'absolute', top: '-8px', right: '-8px', zIndex: 20,
              width: '28px', height: '28px', borderRadius: '50%',
              background: 'rgba(239, 68, 68, 0.9)', border: '2px solid rgba(0,0,0,0.3)',
              color: '#fff', fontSize: '14px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 2px 8px rgba(0,0,0,0.4)'
            }}
            title="Supprimer ce message"
          >✕</button>
        )}
        {/* Nom au-dessus si pas utilisateur */}
        {!isUser && (
          <div style={{
            fontSize: '10px',
            fontWeight: '600',
            marginLeft: '4px',
            color: getNameColor()
          }}>
            {displayName}
          </div>
        )}

        {/* Composant MediaMessage avec CTA */}
        <MediaMessage
          mediaUrl={hasMedia ? msg.media_url : null}
          description={messageText}
          cta={ctaConfig}
          onReservationClick={onReservationClick}
          isCompact={true}
        />
      </div>
    );
  }
  
  // === MESSAGE STANDARD (sans média) ===

  // v81: MESSAGE STANDARD ÉPURÉ — Bulles adaptatives style WhatsApp
  return (
    <div
      style={{
        alignSelf: isUser ? 'flex-end' : 'flex-start',
        maxWidth: '75%',
        width: 'fit-content',
        display: 'flex',
        flexDirection: isUser ? 'row-reverse' : 'row',
        gap: '8px',
        alignItems: 'flex-end',
        position: 'relative'
      }}
      onMouseEnter={() => onDelete && setShowDelete(true)}
      onMouseLeave={() => setShowDelete(false)}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* v153: Bouton supprimer — hover desktop / long press mobile */}
      {showDelete && onDelete && (
        <button
          onClick={handleDeleteClick}
          style={{
            position: 'absolute',
            top: '-8px',
            [isUser ? 'left' : 'right']: '-8px',
            width: '28px', height: '28px',
            borderRadius: '50%',
            background: 'rgba(239, 68, 68, 0.9)',
            border: '2px solid rgba(0,0,0,0.3)',
            color: '#fff',
            fontSize: '14px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 20,
            boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
            transition: 'transform 0.15s',
          }}
          title="Supprimer ce message"
        >
          ✕
        </button>
      )}

      {/* Avatar rond si disponible */}
      {getAvatar()}

      <div style={{ width: 'fit-content', maxWidth: '100%' }}>
        {/* NOM AU-DESSUS DE LA BULLE - Toujours visible pour les messages reçus */}
        {!isUser && (
          <div
            style={{
              fontSize: '10px',
              fontWeight: '600',
              marginBottom: '3px',
              marginLeft: '4px',
              color: getNameColor(),
              letterSpacing: '0.3px',
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
          >
            {isOtherUser && onParticipantClick ? (
              <button
                onClick={() => onParticipantClick(msg.senderId, msg.sender)}
                style={{
                  fontSize: '10px',
                  fontWeight: '600',
                  background: 'none',
                  border: 'none',
                  color: '#22D3EE',
                  cursor: 'pointer',
                  padding: 0,
                  textDecoration: 'underline',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}
                title="Cliquer pour envoyer un message privé"
              >
                {/* Icône DM */}
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
                {displayName}
              </button>
            ) : (
              displayName
            )}
          </div>
        )}
        
        <div
          style={{
            background: getBubbleBackground(),
            color: '#fff',
            padding: '10px 14px',
            borderRadius: isUser
              ? '20px 20px 6px 20px'
              : '20px 20px 20px 6px',
            fontSize: '13px',
            lineHeight: '1.5',
            border: 'none',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)'
          }}
        >
          {/* Rendu du texte avec liens cliquables */}
          <span 
            dangerouslySetInnerHTML={{ __html: htmlContent }}
            style={{ wordBreak: 'break-word' }}
          />
        </div>
        
        {/* === MÉDIA INLINE DÉTECTÉ AUTOMATIQUEMENT === */}
        {detectedMedia && detectedMedia.type === 'youtube' && (
          <InlineYouTubePlayer videoId={detectedMedia.videoId} thumbnailUrl={detectedMedia.thumbnailUrl} />
        )}
        {detectedMedia && detectedMedia.type === 'drive' && (
          <InlineDriveImage directUrl={detectedMedia.directUrl} previewUrl={detectedMedia.previewUrl} />
        )}
        {detectedMedia && detectedMedia.type === 'image' && (
          <InlineImage src={detectedMedia.directUrl} />
        )}
        
        {/* === BOUTON CTA SI PRÉSENT === */}
        {(msg.cta_text && msg.cta_link) && (
          <InlineCtaButton label={msg.cta_text} url={msg.cta_link} />
        )}
        
        {/* Horodatage sous la bulle - visible et clair */}
        {msg.created_at && (
          <div style={{
            fontSize: '10px',
            color: '#999',
            marginTop: '4px',
            textAlign: isUser ? 'right' : 'left',
            fontWeight: '400'
          }}>
            {formatMessageTime(msg.created_at)}
          </div>
        )}
      </div>
    </div>
  );
};

// === OPTIMISATION: memo pour éviter les re-rendus inutiles ===
// Compare uniquement les props critiques: ID du message et URLs d'avatar
const MemoizedMessageBubble = memo(MessageBubble, (prevProps, nextProps) => {
  // Si l'ID change, on doit re-rendre
  if (prevProps.msg.id !== nextProps.msg.id) return false;

  // v153: Si is_deleted change, on doit re-rendre
  if (prevProps.msg.is_deleted !== nextProps.msg.is_deleted) return false;

  // Si l'avatar change (utilisateur a uploadé une nouvelle photo), on doit re-rendre
  if (prevProps.msg.senderPhotoUrl !== nextProps.msg.senderPhotoUrl) return false;
  if (prevProps.profilePhotoUrl !== nextProps.profilePhotoUrl) return false;

  // Sinon, pas besoin de re-rendre (même message, même avatar)
  return true;
});

/**
 * Widget de chat IA flottant avec reconnaissance automatique et historique
 * Utilise l'API /api/chat/smart-entry pour identifier les utilisateurs
 */
export const ChatWidget = () => {
  // === VÉRIFICATION DU PROFIL ABONNÉ (afroboost_profile) ===
  const getStoredProfile = () => {
    try {
      const savedProfile = localStorage.getItem(AFROBOOST_PROFILE_KEY);
      if (savedProfile) {
        const profile = JSON.parse(savedProfile);
        if (profile && profile.code && profile.name) {
          return profile;
        }
      }
    } catch (e) {
      console.warn('[PROFILE] Erreur lecture profil:', e.message);
    }
    return null;
  };

  // === CACHE HYBRIDE v9.4.0: Chargement instantané via localStorage (persistant) + sessionStorage ===
  // Stocke les 20 derniers messages pour affichage immédiat (0ms)
  const getCachedMessages = () => {
    try {
      // Priorité 1: sessionStorage (session actuelle)
      const sessionCached = sessionStorage.getItem(MESSAGE_CACHE_KEY);
      if (sessionCached) {
        const messages = JSON.parse(sessionCached);
        if (Array.isArray(messages) && messages.length > 0) {
          console.log('[CACHE v9.4.0] Messages de session trouvés:', messages.length);
          return messages;
        }
      }
      
      // Priorité 2: localStorage (persistant entre sessions)
      const localCached = localStorage.getItem(MESSAGE_CACHE_KEY + '_persist');
      if (localCached) {
        const messages = JSON.parse(localCached);
        if (Array.isArray(messages) && messages.length > 0) {
          console.log('[CACHE v9.4.0] Messages persistants trouvés:', messages.length);
          // Restaurer aussi dans sessionStorage
          sessionStorage.setItem(MESSAGE_CACHE_KEY, JSON.stringify(messages));
          return messages;
        }
      }
    } catch (e) {
      console.warn('[CACHE v9.4.0] Erreur lecture cache:', e.message);
    }
    return [];
  };

  const saveCachedMessages = (messages) => {
    try {
      // Stocker les 20 derniers messages uniquement
      const toCache = messages.slice(-20);
      // Sauvegarder dans sessionStorage (session actuelle)
      sessionStorage.setItem(MESSAGE_CACHE_KEY, JSON.stringify(toCache));
      // Sauvegarder aussi dans localStorage (persistant)
      localStorage.setItem(MESSAGE_CACHE_KEY + '_persist', JSON.stringify(toCache));
      console.log('[CACHE v9.4.0] 💾 Messages mis en cache (session+persist):', toCache.length);
    } catch (e) {
      console.warn('[CACHE v9.4.0] Erreur écriture cache:', e.message);
    }
  };

  // === VÉRIFICATION PERSISTANCE AU MONTAGE (AVANT tout render) ===
  // Déterminer le step initial IMMÉDIATEMENT basé sur localStorage
  // AVEC FALLBACK ROBUSTE pour données corrompues
  // === ZERO-FLASH: Vérifie aussi ?group=ID pour adhésion instantanée ===
  const [pendingGroupJoin, setPendingGroupJoin] = useState(() => {
    // Détecter le paramètre ?group=ID AVANT le premier render
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const groupId = urlParams.get('group');
      if (groupId) {
        console.log('[ZERO-FLASH] 🚀 Paramètre group détecté:', groupId);
        return groupId;
      }
    } catch (e) {
      console.warn('[ZERO-FLASH] Erreur lecture URL:', e.message);
    }
    return null;
  });
  
  const getInitialStep = () => {
    try {
      // PRIORITÉ 1: Vérifier si c'est un abonné identifié (afroboost_profile)
      const profile = getStoredProfile();
      
      // ZERO-FLASH: Si profil existe ET ?group=ID -> direct au chat (pas de formulaire)
      const urlParams = new URLSearchParams(window.location.search);
      const groupId = urlParams.get('group');
      
      if (profile && groupId) {
        console.log('[ZERO-FLASH] Abonné reconnu + lien groupe -> DIRECT chat');
        return 'chat'; // Adhésion instantanée, formulaire JAMAIS affiché
      }
      
      if (profile) {
        console.log('[PERSISTENCE] Abonné reconnu:', profile.name, '- Code:', profile.code);
        return 'chat'; // Abonné -> DIRECT au chat en mode plein écran
      }
      
      const savedIdentity = localStorage.getItem(AFROBOOST_IDENTITY_KEY);
      const savedClient = localStorage.getItem(CHAT_CLIENT_KEY);
      
      if (savedIdentity || savedClient) {
        const rawData = savedIdentity || savedClient;
        
        // Vérification de la validité JSON
        if (!rawData || rawData === 'undefined' || rawData === 'null') {
          throw new Error('Données localStorage invalides');
        }
        
        const data = JSON.parse(rawData);
        
        // Vérification des données minimales requises
        if (data && typeof data === 'object' && data.firstName && typeof data.firstName === 'string' && data.firstName.trim()) {
          console.log('[PERSISTENCE] Utilisateur reconnu:', data.firstName);
          return 'chat'; // Utilisateur déjà identifié -> DIRECT au chat
        } else {
          throw new Error('Données utilisateur incomplètes');
        }
      }
    } catch (e) {
      // FALLBACK: Nettoyer les données corrompues et rediriger vers le formulaire
      console.warn('[PERSISTENCE] Données corrompues détectées, nettoyage...', e.message);
      try {
        localStorage.removeItem(AFROBOOST_IDENTITY_KEY);
        localStorage.removeItem(CHAT_CLIENT_KEY);
        localStorage.removeItem(CHAT_SESSION_KEY);
        localStorage.removeItem(AFROBOOST_PROFILE_KEY);
      } catch (cleanupError) {
        console.error('[PERSISTENCE] Erreur lors du nettoyage localStorage:', cleanupError);
      }
    }
    return 'form'; // Nouvel utilisateur ou données corrompues -> formulaire
  };
  
  // === DÉTERMINER SI MODE PLEIN ÉCRAN INITIAL (Abonné = plein écran OU lien groupe) ===
  const getInitialFullscreen = () => {
    const profile = getStoredProfile();
    // Si profil + lien groupe -> plein écran immédiat
    const urlParams = new URLSearchParams(window.location.search);
    const groupId = urlParams.get('group');
    return !!profile || (!!profile && !!groupId);
  };
  
  // === OUVRIR LE CHAT AUTOMATIQUEMENT SI LIEN GROUPE ===
  const getInitialOpen = () => {
    const urlParams = new URLSearchParams(window.location.search);
    const groupId = urlParams.get('group');
    const profile = getStoredProfile();
    // Si lien groupe + profil -> ouvrir immédiatement
    if (groupId && profile) {
      console.log('[ZERO-FLASH] 🚀 Chat ouvert automatiquement');
      return true;
    }
    return false;
  };

  const [isOpen, setIsOpen] = useState(getInitialOpen); // ZERO-FLASH: Ouvrir si lien groupe
  const [step, setStep] = useState(getInitialStep); // Initialisation DYNAMIQUE
  const [leadData, setLeadData] = useState(() => {
    // Charger les données du localStorage IMMÉDIATEMENT
    try {
      const savedIdentity = localStorage.getItem(AFROBOOST_IDENTITY_KEY);
      const savedClient = localStorage.getItem(CHAT_CLIENT_KEY);
      if (savedIdentity || savedClient) {
        const data = JSON.parse(savedIdentity || savedClient);
        if (data && data.firstName) {
          return {
            firstName: data.firstName || '',
            email: data.email || '',
            whatsapp: data.whatsapp || ''
          };
        }
      }
    } catch (e) {}
    return { firstName: '', whatsapp: '', email: '' };
  });
  
  // === CACHE HYBRIDE: Initialiser avec les messages cachés pour affichage instantané ===
  const [messages, setMessages] = useState(() => getCachedMessages());
  const [isLoadingHistory, setIsLoadingHistory] = useState(true); // État skeleton
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isReturningClient, setIsReturningClient] = useState(() => {
    // Déterminer si c'est un client de retour IMMÉDIATEMENT
    try {
      const savedIdentity = localStorage.getItem(AFROBOOST_IDENTITY_KEY);
      const savedClient = localStorage.getItem(CHAT_CLIENT_KEY);
      return !!(savedIdentity || savedClient);
    } catch (e) {}
    return false;
  });
  const [sessionData, setSessionData] = useState(() => {
    // Charger la session depuis localStorage IMMÉDIATEMENT
    try {
      const savedSession = localStorage.getItem(CHAT_SESSION_KEY);
      if (savedSession) {
        return JSON.parse(savedSession);
      }
    } catch (e) {}
    return null;
  });
  const [participantId, setParticipantId] = useState(() => {
    try {
      const savedIdentity = localStorage.getItem(AFROBOOST_IDENTITY_KEY);
      const savedClient = localStorage.getItem(CHAT_CLIENT_KEY);
      if (savedIdentity || savedClient) {
        const data = JSON.parse(savedIdentity || savedClient);
        return data?.participantId || null;
      }
    } catch (e) {}
    return null;
  });
  const [showMenu, setShowMenu] = useState(false);
  // V160: Birthday states
  var _bd160 = useState(false); var showBirthdayModal = _bd160[0]; var setShowBirthdayModal = _bd160[1];
  var _bd161 = useState(""); var birthdayMonth = _bd161[0]; var setBirthdayMonth = _bd161[1];
  var _bd162 = useState(""); var birthdayDay = _bd162[0]; var setBirthdayDay = _bd162[1];
  var _bd163 = useState(null); var todayBirthdays = _bd163[0]; var setTodayBirthdays = _bd163[1];
  var _bd164 = useState(false); var birthdaySaved = _bd164[0]; var setBirthdaySaved = _bd164[1];

  // V160: Check today's birthdays on mount
  useEffect(function() {
    var checkBirthdays = function() {
      fetch(API + '/birthdays/today')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.birthdays && data.birthdays.length > 0) {
            setTodayBirthdays(data.birthdays);
          }
        })
        .catch(function(err) { console.log('[V160] Birthday check error:', err); });
    };
    checkBirthdays();
    // Re-check every hour
    var interval = setInterval(checkBirthdays, 3600000);
    return function() { clearInterval(interval); };
  }, []);

  // V160: Save birthday
  var handleSaveBirthday = function() {
    if (!birthdayMonth || !birthdayDay || !participantId) return;
    var mm = birthdayMonth.padStart(2, '0');
    var dd = birthdayDay.padStart(2, '0');
    var birthday = mm + '-' + dd;
    fetch(API + '/chat/participants/' + participantId + '/birthday', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ birthday: birthday })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.success) {
        setBirthdaySaved(true);
        setTimeout(function() { setShowBirthdayModal(false); setBirthdaySaved(false); }, 2000);
      }
    })
    .catch(function(err) { console.error('[V160] Save birthday error:', err); });
  };
  const [isCommunityMode, setIsCommunityMode] = useState(false);
  const [chatMode, setChatMode] = useState('private'); // v8.6: 'private' ou 'group'
  const [groupMessages, setGroupMessages] = useState([]); // v8.6: Messages de groupe
  const [availableGroups, setAvailableGroups] = useState([]); // V107.12: Groupes disponibles
  const [selectedGroup, setSelectedGroup] = useState(null); // V107.12: Groupe sélectionné
  const [groupLoading, setGroupLoading] = useState(false); // V107.12: Chargement groupes
  const [lastMessageCount, setLastMessageCount] = useState(0);
  const [privateChatTarget, setPrivateChatTarget] = useState(null);
  const [messageCount, setMessageCount] = useState(0); // Compteur de messages pour prompt notif
  const [pushEnabled, setPushEnabled] = useState(() => isSubscribed()); // V120: init depuis localStorage
  const [unreadCount, setUnreadCount] = useState(0); // v9.4.0: Compteur de messages non lus pour badge
  const [hasNewMessage, setHasNewMessage] = useState(false); // v9.4.0: Indicateur de nouveau message
  const [isCoachMode, setIsCoachMode] = useState(() => {
    // v9.1.5: Vérifier si c'est un coach connecté (pas seulement Bassi)
    try {
      // 1. Vérifier d'abord le flag de session coach global
      const coachModeFlag = localStorage.getItem('afroboost_coach_mode');
      const coachUser = localStorage.getItem('afroboost_coach_user');
      if (coachModeFlag === 'true' && coachUser) {
        return true;
      }
      
      // 2. Fallback: vérifier l'identité du chat
      const savedIdentity = localStorage.getItem(AFROBOOST_IDENTITY_KEY);
      const savedClient = localStorage.getItem(CHAT_CLIENT_KEY);
      if (savedIdentity || savedClient) {
        const data = JSON.parse(savedIdentity || savedClient);
        const email = data?.email?.toLowerCase();
        // v9.5.6: Liste des Super Admins
        return email === 'contact.artboost@gmail.com' || email === 'afroboost.bassi@gmail.com';
      }
    } catch (e) {}
    return false;
  });
  const [coachSessions, setCoachSessions] = useState([]); // Liste des sessions pour le coach
  const [selectedCoachSession, setSelectedCoachSession] = useState(null); // Session sélectionnée par le coach
  // v162: Mini-dashboard tabs
  var _ctab = useState('conversations'); var coachDashTab = _ctab[0]; var setCoachDashTab = _ctab[1];
  var _cres = useState([]); var coachReservations = _cres[0]; var setCoachReservations = _cres[1];
  var _cqr = useState(''); var qrScanCode = _cqr[0]; var setQrScanCode = _cqr[1];
  var _cqrR = useState(null); var qrScanResult = _cqrR[0]; var setQrScanResult = _cqrR[1];
  // v162e: QR camera scanner
  var _cqrCam = useState(false); var qrCameraActive = _cqrCam[0]; var setQrCameraActive = _cqrCam[1];
  var _cqrErr = useState(''); var qrCameraError = _cqrErr[0]; var setQrCameraError = _cqrErr[1];
  var qrScannerRef = useRef(null);
  // v162f: Coach profile photo
  var _cpro = useState(null); var coachProfile = _cpro[0]; var setCoachProfile = _cpro[1];
  // v162f: Coach emoji picker toggle (separate from chat emoji picker)
  var _cep = useState(false); var showCoachEmojiPicker = _cep[0]; var setShowCoachEmojiPicker = _cep[1];
  // v162f: AI suggestion for coach response
  var _cai = useState(''); var aiSuggestion = _cai[0]; var setAiSuggestion = _cai[1];
  var _caiL = useState(false); var aiSuggestionLoading = _caiL[0]; var setAiSuggestionLoading = _caiL[1];
  const [isFullscreen, setIsFullscreen] = useState(getInitialFullscreen); // Mode plein écran (ABONNÉ = activé)
  const [showAfricanEmojiPicker, setShowAfricanEmojiPicker] = useState(false); // v154: Sélecteur d'emojis unifié
  const [coachCustomEmojis, setCoachCustomEmojis] = useState([]); // v154: Emojis personnalisés du coach

  // v154: Charger les emojis personnalisés du coach
  useEffect(() => {
    axios.get(`${API}/chat/emojis`).then(res => {
      if (Array.isArray(res.data)) setCoachCustomEmojis(res.data);
    }).catch(() => {});
  }, []);

  // === FORMULAIRE ABONNÉ (4 champs: Nom, WhatsApp, Email, Code Promo) ===
  const [showSubscriberForm, setShowSubscriberForm] = useState(false); // Afficher le formulaire abonné
  const [subscriberFormData, setSubscriberFormData] = useState({ name: '', whatsapp: '', email: '', code: '' });
  const [validatingCode, setValidatingCode] = useState(false); // Loading pendant validation du code

  // === v16.0: TUNNEL D'ONBOARDING (liens personnalisés) ===
  const [showOnboardingTunnel, setShowOnboardingTunnel] = useState(false); // Tunnel actif
  const [currentLinkToken, setCurrentLinkToken] = useState(null); // Token du lien actuel

  // === v11.6: RÉCUPÉRATION D'ACCÈS & MON PASS ===
  const [showRecoverForm, setShowRecoverForm] = useState(false); // Formulaire "Retrouver mes accès"
  const [recoverData, setRecoverData] = useState({ email: '', whatsapp: '' }); // Données de récupération
  const [recoverLoading, setRecoverLoading] = useState(false);
  const [recoverResult, setRecoverResult] = useState(null); // Résultat de la récupération {success, code, qr_code_url, ...}
  const [recoverError, setRecoverError] = useState('');
  const [showMonPass, setShowMonPass] = useState(false); // Affichage élargi du QR "Mon Pass"
  
  // === v11.0: AUTO-CONNEXION QR CODE ABONNÉ ===
  useEffect(() => {
    const qrCode = localStorage.getItem('afroboost_qr_subscriber');
    if (qrCode) {
      localStorage.removeItem('afroboost_qr_subscriber');
      console.log('[CHATWIDGET] 📱 QR Code abonné détecté:', qrCode);
      // Auto-remplir le code et ouvrir le formulaire abonné
      setSubscriberFormData(prev => ({ ...prev, code: qrCode }));
      setShowSubscriberForm(true);
      setIsFullscreen(true);
      setIsOpen(true);
    }
  }, []);

  // === v8.9.9: VÉRIFICATION COACH INSCRIT ===
  // v9.3.0: Initialiser depuis localStorage pour persistance après reconnexion
  // v9.3.1: Aussi vérifier côté serveur pour synchronisation
  const [isRegisteredCoach, setIsRegisteredCoach] = useState(() => {
    try {
      const coachModeFlag = localStorage.getItem('afroboost_coach_mode');
      const coachUser = localStorage.getItem('afroboost_coach_user');
      return coachModeFlag === 'true' || !!coachUser;
    } catch { return false; }
  });
  
  // v9.3.1: Vérification côté serveur si l'utilisateur est partenaire
  // v9.3.2: Ajout d'une vérification au changement du profil pour persistance
  useEffect(() => {
    const checkPartnerStatus = async () => {
      // Vérifier avec le profil abonné existant ou le profil coach
      const profile = getStoredProfile();
      const coachUserStr = localStorage.getItem('afroboost_coach_user');
      const email = profile?.email || (coachUserStr ? JSON.parse(coachUserStr)?.email : null);
      
      if (email) {
        try {
          const res = await axios.get(`${API}/check-partner/${encodeURIComponent(email)}`);
          if (res.data?.is_partner) {
            setIsRegisteredCoach(true);
            // Synchroniser le localStorage
            localStorage.setItem('afroboost_coach_mode', 'true');
            localStorage.setItem('afroboost_partner_verified', 'true');
            console.log('[CHAT] ✅ Partenaire vérifié côté serveur:', email);
          } else {
            // Nettoyer si pas partenaire
            localStorage.removeItem('afroboost_partner_verified');
          }
        } catch (e) {
          console.log('[CHAT] Vérification partenaire impossible:', e.message);
        }
      }
    };
    
    checkPartnerStatus();
    
    // v9.3.2: Re-vérifier lors du storage change (après login)
    const handleStorageChange = () => {
      checkPartnerStatus();
    };
    window.addEventListener('storage', handleStorageChange);
    
    // v9.3.2: Re-vérifier périodiquement pour persistance
    const interval = setInterval(checkPartnerStatus, 30000); // Toutes les 30 secondes
    
    return () => {
      window.removeEventListener('storage', handleStorageChange);
      clearInterval(interval);
    };
  }, []);
  
  // === PROFIL ABONNÉ VALIDÉ (afroboost_profile) ===
  const [afroboostProfile, setAfroboostProfile] = useState(getStoredProfile);
  const [profilePhoto, setProfilePhoto] = useState(() => {
    try {
      const profile = getStoredProfile();
      return profile?.photoUrl || null;
    } catch { return null; }
  });
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  
  // === v76: ZOOM PHOTO PROFIL (crop supprimé définitivement) ===
  const [zoomedChatPhoto, setZoomedChatPhoto] = useState(null);

  // === v88: FORMULAIRE AVIS POST-SESSION (fix erreur + masquage après pub) ===
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [reviewRating, setReviewRating] = useState(5);
  const [reviewText, setReviewText] = useState('');
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewSubmitted, setReviewSubmitted] = useState(() => {
    // v88: Restaurer l'état "déjà publié" depuis localStorage
    const key = `afroboost_review_done_${sessionStorage.getItem('afroboost_code') || ''}`;
    return localStorage.getItem(key) === 'true';
  });
  const [reviewSessionId, setReviewSessionId] = useState('');
  const [reviewRequestVisible, setReviewRequestVisible] = useState(false); // v86 fix: indépendant du state messages
  
  // === MENU UTILISATEUR (Partage + Mode Visiteur) ===
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showCoachMenu, setShowCoachMenu] = useState(false); // Menu coach minimaliste
  const [linkCopied, setLinkCopied] = useState(false);
  const [isVisitorMode, setIsVisitorMode] = useState(false); // Mode visiteur (chat réduit mais profil conservé)
  const [isVisitorPreview, setIsVisitorPreview] = useState(false); // Admin: aperçu mode visiteur
  const [showiOSPrompt, setShowiOSPrompt] = useState(false); // Message iOS pour PWA
  const [isLoggingOut, setIsLoggingOut] = useState(false); // Etat de deconnexion en cours
  
  // === PRÉFÉRENCES SONORES (persistées dans localStorage via SoundManager) ===
  const [soundEnabled, setSoundEnabledState] = useState(() => {
    try {
      const saved = localStorage.getItem('afroboost_sound_enabled');
      return saved !== null ? saved === 'true' : true;
    } catch { return true; }
  });
  
  const [silenceAutoEnabled, setSilenceAutoEnabledState] = useState(() => {
    try {
      const saved = localStorage.getItem('afroboost_silence_auto');
      return saved === 'true';
    } catch { return false; }
  });
  
  // === v9.2.8: PLATFORM SETTINGS - Charger pour conditionner l'affichage ===
  const [platformSettings, setPlatformSettings] = useState({
    partner_access_enabled: true,
    maintenance_mode: false
  });
  
  useEffect(() => {
    const loadPlatformSettings = async () => {
      try {
        const res = await axios.get(`${API}/platform-settings`);
        setPlatformSettings({
          partner_access_enabled: res.data?.partner_access_enabled ?? true,
          maintenance_mode: res.data?.maintenance_mode ?? false
        });
      } catch {
        // Valeurs par défaut si erreur
      }
    };
    loadPlatformSettings();
  }, []);
  
  // Toggle le mode Silence Auto (utilise SoundManager)
  const toggleSilenceAuto = () => {
    const newValue = !silenceAutoEnabled;
    setSilenceAutoEnabledState(newValue);
    localStorage.setItem('afroboost_silence_auto', String(newValue));
    console.log('[SILENCE AUTO] 🌙', newValue ? `Activé (${getSilenceHoursLabel()})` : 'Désactivé');
  };
  
  // Toggle les sons (utilise SoundManager)
  const toggleSound = () => {
    const newValue = !soundEnabled;
    setSoundEnabledState(newValue);
    localStorage.setItem('afroboost_sound_enabled', String(newValue));
    console.log('[SOUND] 🔊', newValue ? 'Activé' : 'Désactivé');
  };

  // V120: Toggle notifications push
  const togglePush = async () => {
    if (pushEnabled) {
      // Désactiver
      await unsubscribeFromPush(participantId);
      setPushEnabled(false);
      console.log('[PUSH] 🔕 Désactivé');
    } else {
      // Activer — demander permission + souscrire
      if (!participantId) return;
      const permission = await Notification.requestPermission();
      if (permission === 'granted') {
        const ok = await subscribeToPush(participantId);
        setPushEnabled(ok);
        console.log('[PUSH] 🔔', ok ? 'Activé' : 'Échec');
      }
    }
  };

  // V120: Clear badge quand le chat est ouvert/visible
  useEffect(() => {
    const clearBadge = () => {
      if (navigator.clearAppBadge) navigator.clearAppBadge().catch(() => {});
      // Signaler au SW de remettre le compteur à 0
      if (navigator.serviceWorker?.controller) {
        navigator.serviceWorker.controller.postMessage({ type: 'CLEAR_BADGE' });
      }
    };
    // Clear badge au montage et quand on revient sur l'onglet
    clearBadge();
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') clearBadge();
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, []);
  
  // === WRAPPER SIMPLIFIÉ (délègue à SoundManager) ===
  const playSoundIfEnabled = useCallback((type = SOUND_TYPES.MESSAGE) => {
    playSoundIfAllowed(type, soundEnabled, silenceAutoEnabled);
  }, [soundEnabled, silenceAutoEnabled]);
  
  // v8.6: Charger messages de groupe (legacy broadcast)
  const loadGroupMessages = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/chat/group/messages?limit=100`);
      setGroupMessages(res.data || []);
    } catch (err) {
      console.warn('[GROUP] Erreur chargement:', err);
    }
  }, []);

  // V107.12: Charger la liste des groupes disponibles
  const loadAvailableGroups = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/chat/groups/public`);
      setAvailableGroups(res.data || []);
    } catch (err) {
      console.warn('[V107.12] Erreur chargement groupes:', err);
    }
  }, []);

  // V108.4: Charger messages d'un groupe spécifique — avec formatage unifié
  const loadGroupSessionMessages = useCallback(async (sessionId) => {
    if (!sessionId) return;
    setGroupLoading(true);
    try {
      const res = await axios.get(`${API}/chat/sessions/${sessionId}/messages`);
      // V108.4: Formater les messages serveur → format client unifié
      const formatted = (res.data || []).map(m => ({
        id: m.id,
        type: m.type || (m.sender_type === 'user' ? 'user' : m.sender_type === 'coach' ? 'coach' : 'ai'),
        text: m.content || m.text || '',
        sender: m.sender_name || m.sender || '',
        senderId: m.sender_id || m.senderId || '',
        created_at: m.created_at,
        media_url: m.media_url || null,
        is_group: true
      }));
      setGroupMessages(formatted);
    } catch (err) {
      console.warn('[V108.4] Erreur chargement messages groupe:', err);
    }
    setGroupLoading(false);
  }, []);

  // V107.12: Sélectionner un groupe et rejoindre
  const handleSelectGroup = useCallback(async (group) => {
    setSelectedGroup(group);
    setGroupMessages([]); // Reset messages pendant le chargement
    // Rejoindre le groupe si on a un participantId
    if (participantId && group.id) {
      try {
        await axios.post(`${API}/chat/groups/${group.id}/join`, { participant_id: participantId });
      } catch (e) { /* déjà membre, pas grave */ }
    }
    // Charger les messages du groupe
    loadGroupSessionMessages(group.session_id);
  }, [participantId, loadGroupSessionMessages]);

  // V107.12: Polling messages du groupe sélectionné (toutes les 10s)
  useEffect(() => {
    if (chatMode !== 'group' || !selectedGroup?.session_id) return;
    const interval = setInterval(() => {
      loadGroupSessionMessages(selectedGroup.session_id);
    }, 10000);
    return () => clearInterval(interval);
  }, [chatMode, selectedGroup?.session_id, loadGroupSessionMessages]);
  
  // Fonction pour copier le lien du site
  const handleShareLink = async () => {
    try {
      const shareUrl = window.location.origin;
      await navigator.clipboard.writeText(shareUrl);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
      console.log('[SHARE] Lien copié:', shareUrl);
    } catch (err) {
      console.error('[SHARE] Erreur copie:', err);
      // Fallback pour navigateurs sans clipboard API
      const textArea = document.createElement('textarea');
      textArea.value = window.location.origin;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    }
    setShowUserMenu(false);
  };
  
  // Fonction pour passer en mode visiteur (réduit le chat sans effacer le profil)
  const handleVisitorMode = () => {
    setIsFullscreen(false);
    setIsVisitorMode(true);
    setShowUserMenu(false);
    setShowReservationPanel(false);
    console.log('[MODE] Mode visiteur activé (profil conservé)');
  };
  
  // Fonction pour réactiver le mode abonné
  const handleReactivateSubscriber = () => {
    if (afroboostProfile?.code) {
      setIsFullscreen(true);
      setIsVisitorMode(false);
      console.log('[MODE] Mode abonné réactivé');
    }
  };
  
  // === FONCTION DE DÉCONNEXION STRICTE (HARD RESET) ===
  const handleLogout = async () => {
    if (isLoggingOut) return; // Eviter double clic
    setIsLoggingOut(true);
    
    // Timeout de securite: force redirect apres 3s
    const forceRedirect = setTimeout(() => window.location.replace('/'), 3000);
    
    try {
      // 1. Desabonner des notifications push (garde la PWA installee)
      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();
        if (subscription) await subscription.unsubscribe();
      }
      
      // 2. Vider les caches
      if ('caches' in window) {
        const cacheNames = await caches.keys();
        await Promise.all(cacheNames.map(name => caches.delete(name)));
      }
      
      // 3. Nettoyer le stockage
      localStorage.clear();
      sessionStorage.clear();
      
      // 4. Reinitialiser les etats
      setSessionData(null);
      setParticipantId(null);
      setMessages([]);
      setAfroboostProfile(null);
      setStep('welcome');
      
      clearTimeout(forceRedirect);
    } catch (err) {
      console.error('[LOGOUT] Erreur:', err);
      localStorage.clear();
      sessionStorage.clear();
    }
    window.location.replace('/');
  };
  
  // === OUVRIR UN DM (Message Privé) ===
  const openDirectMessage = async (memberId, memberName) => {
    if (!participantId) return;
    
    try {
      console.log('[DM] 📩 Ouverture DM avec:', memberName);
      
      // Créer ou récupérer la conversation privée
      const res = await axios.post(`${API}/private/conversations`, {
        participant_1_id: participantId,
        participant_1_name: afroboostProfile?.name || leadData?.firstName || 'Moi',
        participant_2_id: memberId,
        participant_2_name: memberName
      });
      
      const conversation = res.data;
      setActivePrivateChat(conversation);
      
      // Charger les messages existants
      const messagesRes = await axios.get(`${API}/private/messages/${conversation.id}`);
      setPrivateMessages(messagesRes.data || []);
      
      // Rejoindre la room Socket.IO pour les mises à jour temps réel
      if (socketRef.current) {
        socketRef.current.emit('join_private_conversation', {
          conversation_id: conversation.id,
          participant_id: participantId
        });
      }
      
      // Marquer comme lu
      await axios.put(`${API}/private/messages/read/${conversation.id}?reader_id=${participantId}`);
      
      // Persister la conversation active pour F5
      localStorage.setItem('afroboost_active_dm', JSON.stringify(conversation));
      
      console.log('[DM] Conversation ouverte:', conversation.id);
    } catch (err) {
      console.error('[DM] Erreur ouverture DM:', err);
    }
  };
  
  // === FERMER LE DM ===
  const closeDirectMessage = () => {
    if (activePrivateChat && socketRef.current) {
      socketRef.current.emit('leave_private_conversation', {
        conversation_id: activePrivateChat.id
      });
    }
    setActivePrivateChat(null);
    setPrivateMessages([]);
    setPrivateInput('');
    localStorage.removeItem('afroboost_active_dm');
    console.log('[DM] 📭 DM fermé');
  };
  
  // === ENVOYER UN MESSAGE PRIVÉ ===
  const sendPrivateMessage = async () => {
    if (!privateInput.trim() || !activePrivateChat) return;
    
    try {
      const recipientId = activePrivateChat.participant_1_id === participantId 
        ? activePrivateChat.participant_2_id 
        : activePrivateChat.participant_1_id;
      const recipientName = activePrivateChat.participant_1_id === participantId
        ? activePrivateChat.participant_2_name
        : activePrivateChat.participant_1_name;
      
      const res = await axios.post(`${API}/private/messages`, {
        conversation_id: activePrivateChat.id,
        sender_id: participantId,
        sender_name: afroboostProfile?.name || leadData?.firstName || 'Moi',
        recipient_id: recipientId,
        recipient_name: recipientName,
        content: privateInput.trim()
      });
      
      // Ajouter le message localement
      setPrivateMessages(prev => [...prev, res.data]);
      setPrivateInput('');
      
      console.log('[DM] Message envoyé');
    } catch (err) {
      console.error('[DM] Erreur envoi message:', err);
    }
  };
  
  // === COMPRESSION IMAGE CÔTÉ CLIENT ===
  const compressImage = (file, maxWidth = 200, maxHeight = 200, quality = 0.8) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = new Image();
        img.onload = () => {
          // Calculer les nouvelles dimensions
          let { width, height } = img;
          if (width > maxWidth || height > maxHeight) {
            const ratio = Math.min(maxWidth / width, maxHeight / height);
            width = Math.round(width * ratio);
            height = Math.round(height * ratio);
          }
          
          // Créer le canvas pour la compression
          const canvas = document.createElement('canvas');
          canvas.width = width;
          canvas.height = height;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(img, 0, 0, width, height);
          
          // Convertir en blob compressé
          canvas.toBlob(
            (blob) => {
              if (blob) {
                resolve(new File([blob], file.name, { type: 'image/jpeg' }));
              } else {
                reject(new Error('Compression échouée'));
              }
            },
            'image/jpeg',
            quality
          );
        };
        img.onerror = reject;
        img.src = e.target.result;
      };
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  };
  
  // === v75: UPLOAD PHOTO SIMPLIFIÉ — Auto-centrage, pas de crop manuel ===
  const handlePhotoSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith('image/')) {
      alert('Veuillez sélectionner une image');
      return;
    }

    // v75: Upload direct sans crop modal — le backend auto-centre à 200x200
    handleDirectUpload(file);
  };

  // === v75: UPLOAD DIRECT SANS CROP — Auto-centrage côté backend ===
  const handleDirectUpload = async (file) => {
    setUploadingPhoto(true);

    try {
      // Créer canvas pour centrer automatiquement en carré
      const canvas = document.createElement('canvas');
      const size = 200;
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext('2d');

      // Charger l'image
      const img = new Image();
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = reject;
        img.src = URL.createObjectURL(file);
      });

      // Auto-centrage : crop carré au centre de l'image
      const minDim = Math.min(img.width, img.height);
      const offsetX = (img.width - minDim) / 2;
      const offsetY = (img.height - minDim) / 2;

      // Dessiner dans un cercle
      ctx.beginPath();
      ctx.arc(size/2, size/2, size/2, 0, Math.PI * 2);
      ctx.closePath();
      ctx.clip();

      ctx.drawImage(img, offsetX, offsetY, minDim, minDim, 0, 0, size, size);

      // Convertir en blob
      const blob = await new Promise((resolve) => {
        canvas.toBlob(resolve, 'image/jpeg', 0.85);
      });

      const compressedFile = new File([blob], 'profile.jpg', { type: 'image/jpeg' });
      console.log('[PHOTO] v75 Auto-centrage terminé:', Math.round(compressedFile.size / 1024), 'KB');

      // Upload vers l'endpoint MongoDB
      const formData = new FormData();
      formData.append('file', compressedFile);
      formData.append('participant_id', participantId || 'guest');

      const res = await axios.post(`${API}/users/upload-photo`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      if (res.data?.success && res.data?.url) {
        const photoUrl = res.data.url;
        setProfilePhoto(photoUrl);

        // === MISE À JOUR DU PROFIL LOCAL (sync avec DB) ===
        const profile = getStoredProfile() || {};
        profile.photoUrl = photoUrl;
        localStorage.setItem(AFROBOOST_PROFILE_KEY, JSON.stringify(profile));
        setAfroboostProfile(profile);

        // === ÉMETTRE LA MISE À JOUR D'AVATAR EN TEMPS RÉEL ===
        emitAvatarUpdate(photoUrl);

        console.log('[PHOTO] v75 Photo uploadée MongoDB:', photoUrl, res.data.db_updated);
      }
    } catch (err) {
      console.error('[PHOTO] Erreur:', err);
      alert('Erreur lors de l\'upload');
    } finally {
      setUploadingPhoto(false);
    }
  };

  // v76: Upload simplifié — alias pour compatibilité
  const handlePhotoUpload = (e) => handlePhotoSelect(e);
  
  // === RESTAURER DM ACTIVE APRÈS F5 ===
  useEffect(() => {
    const savedDM = localStorage.getItem('afroboost_active_dm');
    if (savedDM && participantId) {
      try {
        const conversation = JSON.parse(savedDM);
        openDirectMessage(
          conversation.participant_1_id === participantId 
            ? conversation.participant_2_id 
            : conversation.participant_1_id,
          conversation.participant_1_id === participantId
            ? conversation.participant_2_name
            : conversation.participant_1_name
        );
      } catch (e) {}
    }
  }, [participantId]);
  
  // === INDICATEUR DE SAISIE (Typing Indicator) ===
  const [typingUser, setTypingUser] = useState(null); // Qui est en train d'écrire
  const typingTimeoutRef = useRef(null); // Timer pour cacher l'indicateur après 3s
  const lastTypingEmitRef = useRef(0); // Éviter le spam d'événements typing
  
  // === MESSAGERIE PRIVÉE (MP) ===
  const [privateChats, setPrivateChats] = useState([]); // Liste des conversations MP actives
  const [activePrivateChat, setActivePrivateChat] = useState(null); // MP actuellement ouverte
  const [privateMessages, setPrivateMessages] = useState([]); // Messages de la MP active
  const [privateInput, setPrivateInput] = useState(''); // Input de la MP
  const [unreadPrivateCount, setUnreadPrivateCount] = useState(0); // Compteur MP non lus (pastille rouge)
  const [dmTypingUser, setDmTypingUser] = useState(null); // Indicateur "en train d'écrire" pour DM
  const dmTypingTimeoutRef = useRef(null); // Timer pour cacher l'indicateur DM après 3s
  const lastDmTypingEmitRef = useRef(0); // Éviter le spam d'événements DM typing
  const messagesEndRef = useRef(null);
  const socketRef = useRef(null); // Référence Socket.IO
  const chatContainerRef = useRef(null); // Ref pour le mode plein écran
  
  // === SUBSCRIBER DATA (Mémorisation code promo) ===
  const [subscriberData, setSubscriberData] = useState(() => {
    try {
      const saved = localStorage.getItem('subscriber_data');
      return saved ? JSON.parse(saved) : null;
    } catch { return null; }
  });
  const [showReservationPanel, setShowReservationPanel] = useState(false);
  const [availableCourses, setAvailableCourses] = useState([]); // Cours pour réservation
  const [loadingCourses, setLoadingCourses] = useState(false);
  const [selectedCourse, setSelectedCourse] = useState(null); // Cours sélectionné
  const [reservationLoading, setReservationLoading] = useState(false); // Chargement réservation
  const [reservationError, setReservationError] = useState(''); // Erreur réservation
  const [reservationEligibility, setReservationEligibility] = useState(null); // Éligibilité code
  // v95: Multi-abonnements
  const [userSubscriptions, setUserSubscriptions] = useState([]);
  const [selectedSubscription, setSelectedSubscription] = useState(null);

  // === VÉRIFICATION ÉLIGIBILITÉ RÉSERVATION ===
  const checkReservationEligibility = useCallback(async () => {
    if (!afroboostProfile?.code || !afroboostProfile?.email) {
      setReservationEligibility({ canReserve: false, reason: "Profil incomplet" });
      return false;
    }
    
    try {
      const response = await fetch(`${API}/check-reservation-eligibility`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: afroboostProfile.code,
          email: afroboostProfile.email
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        setReservationEligibility(data);
        return data.canReserve;
      }
      return false;
    } catch (err) {
      console.error('[ELIGIBILITY] Erreur:', err);
      setReservationEligibility({ canReserve: false, reason: "Erreur de vérification" });
      return false;
    }
  }, [afroboostProfile?.code, afroboostProfile?.email]);

  // v7.2: Charger l'eligibilite au montage pour afficher le compteur de cours
  useEffect(() => {
    if (afroboostProfile?.code && afroboostProfile?.email) {
      checkReservationEligibility();
    }
  }, [afroboostProfile?.code, afroboostProfile?.email, checkReservationEligibility]);

  // === v95: Rafraîchir TOUS les abonnements actifs depuis le serveur (par email, sans filtrer par code) ===
  useEffect(() => {
    const refreshSubscriptionStatus = async () => {
      if (!afroboostProfile?.email) return;

      try {
        // v95: Charger par email uniquement pour récupérer TOUS les abonnements
        const res = await axios.get(`${API}/discount-codes/subscriptions/status`, {
          params: { email: afroboostProfile.email }
        });

        if (res.data?.success) {
          const rawSubs = res.data?.subscriptions || (res.data?.subscription ? [res.data.subscription] : []);
          // v151: Déduplication par code (filet de sécurité côté frontend)
          const seen = new Set();
          const allSubs = rawSubs.filter(s => {
            const key = (s.code || '').toUpperCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          });
          // Mettre à jour le profil avec le premier abonnement (rétro-compatible) + liste complète
          const updatedProfile = {
            ...afroboostProfile,
            subscription: allSubs[0] || null,
            allSubscriptions: allSubs
          };
          localStorage.setItem(AFROBOOST_PROFILE_KEY, JSON.stringify(updatedProfile));
          setAfroboostProfile(updatedProfile);
          console.log('[SUBSCRIPTION v151] Abonnements vérifiés:', allSubs.length, 'actif(s)');
        }
      } catch (err) {
        console.log('[SUBSCRIPTION v95] Erreur chargement statut:', err.message);
      }
    };

    refreshSubscriptionStatus();
    // V156.2: Rafraîchir toutes les 30s pour refléter les scans QR du coach
    const interval = setInterval(refreshSubscriptionStatus, 30000);
    return () => clearInterval(interval);
  }, []); // Exécuté au montage + refresh périodique

  // === v8.9.9: Vérifier si l'utilisateur est un coach inscrit ===
  // v9.1.5: Amélioré pour détecter aussi les coachs via localStorage
  useEffect(() => {
    const checkCoachStatus = async () => {
      try {
        // v9.1.5: D'abord vérifier le localStorage de session coach
        const coachModeFlag = localStorage.getItem('afroboost_coach_mode');
        const coachUserStr = localStorage.getItem('afroboost_coach_user');
        if (coachModeFlag === 'true' && coachUserStr) {
          try {
            const coachUser = JSON.parse(coachUserStr);
            if (coachUser?.email) {
              setIsRegisteredCoach(true);
              setIsCoachMode(true);
              return;
            }
          } catch {}
        }
        
        // Récupérer l'email depuis le profil ou l'identité
        const savedIdentity = localStorage.getItem(AFROBOOST_IDENTITY_KEY);
        const savedClient = localStorage.getItem(CHAT_CLIENT_KEY);
        const profile = afroboostProfile;
        
        let userEmail = profile?.email;
        if (!userEmail && savedIdentity) {
          try { userEmail = JSON.parse(savedIdentity)?.email; } catch {}
        }
        if (!userEmail && savedClient) {
          try { userEmail = JSON.parse(savedClient)?.email; } catch {}
        }
        
        if (!userEmail) {
          setIsRegisteredCoach(false);
          return;
        }
        
        // Super Admin est toujours un coach - v9.5.6
        const email = userEmail.toLowerCase();
        if (email === 'contact.artboost@gmail.com' || email === 'afroboost.bassi@gmail.com') {
          setIsRegisteredCoach(true);
          return;
        }
        
        // Vérifier si l'email est dans la collection coaches
        const res = await fetch(`${BACKEND_URL}/api/coach/profile`, {
          headers: { 'X-User-Email': userEmail }
        });
        
        if (res.ok) {
          const data = await res.json();
          setIsRegisteredCoach(data?.role === 'coach' || data?.role === 'super_admin');
        } else {
          setIsRegisteredCoach(false);
        }
      } catch {
        setIsRegisteredCoach(false);
      }
    };
    
    checkCoachStatus();
  }, [afroboostProfile?.email]);

  // === HANDLER CLIC BOUTON RÉSERVATION ===
  // v9.3.7: Toujours ouvrir le panel, vérification à la confirmation
  const handleReservationClick = useCallback(async () => {
    // BLINDAGE: Bloquer en mode Vue Visiteur
    if (isVisitorPreview) {
      console.log('[ADMIN] Réservation bloquée en mode Vue Visiteur');
      return;
    }
    
    if (showReservationPanel) {
      // Fermer le panel
      setShowReservationPanel(false);
      setSelectedCourse(null);
      return;
    }
    
    // v16.3: Tunnel dynamique Réserver
    // Cas A: Contact NON-abonné → redirection vers formulaire d'inscription/paiement
    if (!afroboostProfile?.code) {
      // Chercher la section offres/paiement sur la page
      const offresSection = document.getElementById('devenir-coach') || document.getElementById('offres');
      if (offresSection) {
        offresSection.scrollIntoView({ behavior: 'smooth' });
      } else {
        // Fallback: ouvrir la page d'offres dans un nouvel onglet
        window.open(`${window.location.origin}/#devenir-coach`, '_blank');
      }
      // Ajouter un message IA pour guider le contact
      setMessages(prev => [...prev, {
        id: `sys_reserve_${Date.now()}`,
        type: 'ai',
        text: '📋 Pour réserver un cours, vous devez d\'abord souscrire à un pack. Consultez nos offres pour commencer !',
        timestamp: new Date().toISOString()
      }]);
      return;
    }

    // Cas B: Contact DÉJÀ abonné → ouvrir directement le sélecteur de sessions
    loadAvailableCourses();
    setShowReservationPanel(true);
    setSelectedCourse(null);
    setReservationError('');
    setSelectedSubscription(null);

    // v95/v151: Charger les abonnements actifs de l'utilisateur (filtrés par le backend)
    if (afroboostProfile?.email) {
      axios.get(`${API}/discount-codes/subscriptions/status`, {
        params: { email: afroboostProfile.email }
      }).then(res => {
        const rawSubs = res.data?.subscriptions || (res.data?.subscription ? [res.data.subscription] : []);
        // v151: Déduplication frontend par code (filet de sécurité)
        const seen = new Set();
        const subs = rawSubs.filter(s => {
          const key = (s.code || '').toUpperCase();
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        });
        setUserSubscriptions(subs);
        // Si un seul abonnement, le sélectionner automatiquement
        if (subs.length === 1) {
          setSelectedSubscription(subs[0]);
        }
        console.log('[SUBSCRIPTIONS] v151:', subs.length, 'abonnement(s) vérifié(s)');
      }).catch(err => {
        console.log('[SUBSCRIPTIONS] Erreur chargement:', err.message);
        setUserSubscriptions([]);
      });
    }
  }, [showReservationPanel, isVisitorPreview, afroboostProfile]);

  // === HANDLER CONFIRMATION RÉSERVATION (extrait pour BookingPanel) ===
  const handleConfirmReservation = useCallback(async () => {
    // v9.3.7: Vérifier si l'utilisateur a un code promo valide
    if (!afroboostProfile?.code) {
      setReservationError('Veuillez entrer un code promo valide dans le formulaire "Abonné" pour réserver.');
      return;
    }
    
    if (!selectedCourse) {
      setReservationError('Veuillez sélectionner un cours.');
      return;
    }
    
    // Reset error state
    setReservationError('');
    setReservationLoading(true);
    
    // Utiliser les données du profil abonné (afroboostProfile)
    const reservationData = {
      userName: afroboostProfile?.name?.trim() || leadData?.firstName?.trim() || 'Abonné',
      userEmail: (afroboostProfile?.email || leadData?.email || '').trim(),
      userWhatsapp: (afroboostProfile?.whatsapp || leadData?.whatsapp || '').trim(),
      userId: participantId || `guest-${Date.now()}`, // ID utilisateur requis
      courseId: selectedCourse.id,
      courseName: selectedCourse.name,
      courseTime: selectedCourse.time,
      datetime: new Date().toISOString(),
      promoCode: (selectedSubscription?.code || afroboostProfile?.code || '').trim().toUpperCase(),
      subscriptionId: selectedSubscription?.id || null,
      source: 'chat_widget_abonne',
      type: 'abonné',
      offerId: selectedCourse.id,
      offerName: selectedCourse.name,
      price: selectedCourse.price || 0,
      totalPrice: selectedCourse.price || 0
    };
    
    // LOG pour debug
    console.log('[RESERVATION] 📤 Envoi des données:', JSON.stringify(reservationData, null, 2));
    
    try {
      const res = await axios.post(`${API}/reservations`, reservationData);
      console.log('[RESERVATION] Réponse serveur:', res.data);
      
      if (res.data) {
        // Succès : fermer le panneau et afficher message
        setShowReservationPanel(false);
        setSelectedCourse(null);
        setReservationError('');
        
        // v11.4: Rafraîchir le solde d'abonnement après réservation
        if (afroboostProfile?.email && afroboostProfile?.code) {
          try {
            const statusRes = await axios.get(`${API}/discount-codes/subscriptions/status`, {
              params: { email: afroboostProfile.email, code: afroboostProfile.code }
            });
            if (statusRes.data?.success && statusRes.data?.subscription) {
              // Mettre à jour le profil local avec le nouveau solde
              const updatedProfile = {
                ...afroboostProfile,
                subscription: statusRes.data.subscription
              };
              localStorage.setItem(AFROBOOST_PROFILE_KEY, JSON.stringify(updatedProfile));
              setAfroboostProfile(updatedProfile);
              console.log('[SUBSCRIPTION] Solde mis à jour:', statusRes.data.subscription.remaining_sessions, 'séances restantes');
            }
          } catch (subErr) {
            console.log('[SUBSCRIPTION] Erreur rafraîchissement solde:', subErr.message);
          }
        }
        
        // v10.3: Message de confirmation PREMIUM avec récapitulatif
        // v11.5: Ajout de la date et heure précises
        // v14.8: FIX - Correction décalage +7 jours (permettre réservation le jour même)
        const formatReservationDate = (time, weekday) => {
          const today = new Date();
          const currentDay = today.getDay();
          let daysUntilCourse = weekday - currentDay;
          // v14.8: < 0 (pas <= 0) pour permettre réservation le jour même
          if (daysUntilCourse < 0) daysUntilCourse += 7;
          const courseDate = new Date(today);
          courseDate.setDate(today.getDate() + daysUntilCourse);
          if (time) {
            const [hours, minutes] = time.split(':');
            courseDate.setHours(parseInt(hours) || 18, parseInt(minutes) || 30, 0, 0);
          }
          return courseDate;
        };
        
        const reservationDate = formatReservationDate(selectedCourse.time, selectedCourse.weekday);
        // v14.8: Format Suisse (fr-CH) avec fuseau Europe/Zurich (Neuchâtel)
        const formattedDateTime = new Intl.DateTimeFormat('fr-CH', {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
          timeZone: 'Europe/Zurich'
        }).format(reservationDate);
        
        const confirmMsg = {
          type: 'ai',
          text: `✨ RÉSERVATION CONFIRMÉE ✨`,
          sender: 'Coach Bassi',
          isReservationSummary: true,
          reservationDetails: {
            courseName: selectedCourse.name,
            courseTime: selectedCourse.time,
            reservationDate: formattedDateTime.charAt(0).toUpperCase() + formattedDateTime.slice(1), // v11.5
            clientName: reservationData.userName,
            promoCode: afroboostProfile?.code || 'N/A',
            remaining: reservationEligibility?.remaining || 'N/A',
            expiry: reservationEligibility?.expiry_date || 'Non définie'
          }
        };
        setMessages(prev => [...prev, confirmMsg]);
      }
    } catch (err) {
      console.error('[RESERVATION] Erreur:', err.response?.data || err.message);
      // Afficher l'erreur dans l'UI (pas alert)
      const errorMsg = err.response?.data?.detail || err.response?.data?.message || 'Erreur serveur, réessayez.';
      setReservationError(errorMsg);
    } finally {
      // TOUJOURS réactiver le bouton
      setReservationLoading(false);
    }
  }, [selectedCourse, afroboostProfile, leadData, participantId, setMessages]);

  // v9.5.6: Liste des emails coach/admin autorisés
  const COACH_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
  
  // Sauvegarder subscriber_data quand un code promo est validé
  const saveSubscriberData = useCallback((code, name, type = 'abonné') => {
    const data = { code, name, type, savedAt: new Date().toISOString() };
    localStorage.setItem('subscriber_data', JSON.stringify(data));
    setSubscriberData(data);
    console.log('[SUBSCRIBER] Données abonné sauvegardées:', data);
  }, []);
  
  // === VALIDATION DU CODE PROMO ET ENREGISTREMENT PROFIL ABONNÉ ===
  const handleSubscriberFormSubmit = async (e) => {
    e.preventDefault();
    setError('');
    
    const { name, whatsapp, email, code } = subscriberFormData;
    
    // Validation des champs
    if (!name?.trim() || !whatsapp?.trim() || !email?.trim() || !code?.trim()) {
      setError('Tous les champs sont obligatoires');
      return;
    }
    
    setValidatingCode(true);
    
    try {
      // Valider le code promo via l'API
      const res = await axios.post(`${API}/discount-codes/validate`, {
        code: code.trim(),
        email: email.trim()
      });
      
      if (!res.data?.valid) {
        setError(res.data?.message || 'Code promo invalide');
        setValidatingCode(false);
        return;
      }
      
      // Code valide ! Sauvegarder le profil abonné avec infos d'abonnement v11.4
      const subscriptionInfo = res.data.subscription || {};
      const profile = {
        name: name.trim(),
        whatsapp: whatsapp.trim(),
        email: email.trim(),
        code: code.trim().toUpperCase(),
        codeDetails: res.data.code, // Détails du code (type, valeur, etc.)
        subscription: subscriptionInfo, // v11.4: Infos d'abonnement
        savedAt: new Date().toISOString()
      };
      
      localStorage.setItem(AFROBOOST_PROFILE_KEY, JSON.stringify(profile));
      setAfroboostProfile(profile);
      
      // Sauvegarder aussi dans subscriber_data pour compatibilité
      saveSubscriberData(profile.code, profile.name, 'abonné');
      
      // Mettre à jour leadData pour le chat
      setLeadData({ firstName: profile.name, whatsapp: profile.whatsapp, email: profile.email });
      
      console.log('[SUBSCRIBER] Profil abonné validé et sauvegardé:', profile.name);
      
      // Activer le mode plein écran et passer au chat
      setIsFullscreen(true);
      setShowSubscriberForm(false);
      
      // Démarrer le chat avec smart-entry
      await handleSmartEntry({ 
        firstName: profile.name, 
        whatsapp: profile.whatsapp, 
        email: profile.email 
      });
      
    } catch (err) {
      console.error('[SUBSCRIBER] Erreur validation:', err);
      setError(err.response?.data?.message || 'Erreur lors de la validation du code');
    } finally {
      setValidatingCode(false);
    }
  };
  
  // === v11.6: RÉCUPÉRATION D'ACCÈS ABONNÉ ===
  const handleRecoverAccess = async (e) => {
    e.preventDefault();
    setRecoverError('');
    setRecoverResult(null);

    const { email, whatsapp } = recoverData;
    if (!email?.trim() && !whatsapp?.trim()) {
      setRecoverError('Veuillez saisir votre email ou votre numéro WhatsApp');
      return;
    }

    setRecoverLoading(true);
    try {
      const res = await axios.post(`${API}/subscriber/recover`, {
        email: email.trim() || undefined,
        whatsapp: whatsapp.trim() || undefined
      });

      if (res.data?.code) {
        setRecoverResult({
          success: true,
          code: res.data.code,
          qr_code_url: res.data.qr_code_url,
          sessions_remaining: res.data.sessions_remaining,
          offer_name: res.data.offer_name,
          email_sent: res.data.email_sent
        });
        console.log('[RECOVER] Accès récupéré:', res.data.code);
      } else {
        setRecoverError('Aucun abonnement trouvé avec ces informations.');
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.message || 'Erreur lors de la recherche. Réessayez.';
      setRecoverError(msg);
    } finally {
      setRecoverLoading(false);
    }
  };

  // Charger les cours disponibles
  const loadAvailableCourses = useCallback(async () => {
    setLoadingCourses(true);
    try {
      const res = await axios.get(`${API}/courses`);
      const courses = res.data || [];
      setAvailableCourses(courses);
      console.log('[COURSES] Chargés:', courses.length);
    } catch (err) {
      console.error('[COURSES] Erreur:', err);
    }
    setLoadingCourses(false);
  }, []);

  // === CHARGER LA PHOTO DEPUIS LA DB (pas localStorage) ===
  // Se déclenche quand participantId est disponible
  useEffect(() => {
    const loadPhotoFromDB = async () => {
      if (!participantId) return;
      
      try {
        const res = await axios.get(`${API}/users/${participantId}/profile`);
        if (res.data?.success && res.data?.photo_url) {
          console.log('[PHOTO] Photo chargée depuis DB:', res.data.photo_url);
          setProfilePhoto(res.data.photo_url);
          
          // Synchroniser localStorage avec la DB
          const profile = getStoredProfile() || {};
          if (profile.photoUrl !== res.data.photo_url) {
            profile.photoUrl = res.data.photo_url;
            localStorage.setItem(AFROBOOST_PROFILE_KEY, JSON.stringify(profile));
            setAfroboostProfile(profile);
          }
        }
      } catch (err) {
        console.log('[PHOTO] ℹ️ Profil DB non trouvé, utilise localStorage');
      }
    };
    
    loadPhotoFromDB();
  }, [participantId]);

  // === FONCTIONS MODE PLEIN ÉCRAN (CSS - plus fiable) ===
  const toggleFullscreen = () => {
    setIsFullscreen(prev => !prev);
  };

  // Écouter les changements de fullscreen (touche Escape, etc.)
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  // === ECOUTEUR MODE VUE VISITEUR (Communication CoachDashboard -> ChatWidget) ===
  useEffect(() => {
    const handleVisitorPreviewToggle = (event) => {
      const newState = event.detail?.enabled;
      if (typeof newState === 'boolean') {
        setIsVisitorPreview(newState);
        console.log('[ADMIN] Vue Visiteur via Dashboard:', newState ? 'activee' : 'desactivee');
      }
    };
    
    window.addEventListener('afroboost:visitorPreview', handleVisitorPreviewToggle);
    return () => window.removeEventListener('afroboost:visitorPreview', handleVisitorPreviewToggle);
  }, []);

  // === v107: DÉCLENCHEUR AVIS POST-SESSION — uniquement après fin d'une séance réservée ===
  useEffect(() => {
    if (!afroboostProfile?.code || step !== 'chat' || reviewSubmitted || reviewRequestVisible) return;
    // Vérifier localStorage d'abord (avis déjà publié)
    const doneKey = `afroboost_review_done_${afroboostProfile.code}`;
    if (localStorage.getItem(doneKey) === 'true') {
      setReviewSubmitted(true);
      return;
    }
    const checkKey = `afroboost_review_shown_${afroboostProfile.code}`;
    const alreadyShown = sessionStorage.getItem(checkKey);
    if (alreadyShown) return;

    let intervalId = null;
    const checkEndedSession = async () => {
      try {
        const email = afroboostProfile?.email || '';
        const code = afroboostProfile?.code || '';
        if (!email && !code) return;

        // v107: Vérifier d'abord si l'abonné a déjà publié un avis
        const coachId = sessionData?.coach_id || 'contact.artboost@gmail.com';
        const reviewCheckRes = await fetch(`${API}/reviews/check?participant_code=${encodeURIComponent(code)}&coach_id=${encodeURIComponent(coachId)}`);
        if (reviewCheckRes.ok) {
          const reviewData = await reviewCheckRes.json();
          if (reviewData.has_reviewed) {
            setReviewSubmitted(true);
            localStorage.setItem(doneKey, 'true');
            if (intervalId) clearInterval(intervalId);
            console.log('[V107] Avis déjà publié — notification masquée');
            return;
          }
        }

        // v107: Vérifier si une séance vient de se terminer
        const endedRes = await fetch(`${API}/reservations/ended-for-review?email=${encodeURIComponent(email)}&code=${encodeURIComponent(code)}`);
        if (endedRes.ok) {
          const endedData = await endedRes.json();
          if (endedData.has_ended_session) {
            setReviewRequestVisible(true);
            sessionStorage.setItem(checkKey, 'true');
            if (intervalId) clearInterval(intervalId);
            console.log(`[V107] Séance terminée: ${endedData.session_name} — notification avis activée`);
          }
        }
      } catch (e) {
        console.warn('[V107] Check ended session failed:', e.message);
      }
    };

    // Vérifier immédiatement après 3s, puis toutes les 2 minutes
    const timer = setTimeout(() => {
      checkEndedSession();
      intervalId = setInterval(checkEndedSession, 120000); // 2 min
    }, 3000);

    return () => {
      clearTimeout(timer);
      if (intervalId) clearInterval(intervalId);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [afroboostProfile?.code, step, reviewSubmitted, reviewRequestVisible]);

  // === v86: Détecter les review_request du cron backend dans les messages API ===
  useEffect(() => {
    if (reviewRequestVisible || reviewSubmitted) return;
    const hasBackendReview = messages.some(m => m.type === 'review_request');
    if (hasBackendReview) {
      setReviewRequestVisible(true);
      console.log('[V86] Review request détecté depuis backend cron');
    }
  }, [messages.length, reviewRequestVisible, reviewSubmitted]);

  // Enregistrer le Service Worker au montage
  useEffect(() => {
    if (isPushSupported()) {
      registerServiceWorker().then(() => {
        setPushEnabled(isSubscribed());
      });
    }
  }, []);

  // === ADHESION AUTOMATIQUE VIA LIEN ?group=ID (ZERO-FLASH) ===
  // Utilise pendingGroupJoin détecté AVANT le premier render
  // L'adhésion se fait silencieusement, le formulaire n'est JAMAIS affiché
  useEffect(() => {
    const executeAutoJoin = async () => {
      // Utiliser pendingGroupJoin détecté au montage
      if (!pendingGroupJoin) return;
      
      try {
        // Vérifier si l'utilisateur est déjà connecté
        const storedProfile = getStoredProfile();
        if (!storedProfile || !storedProfile.email) {
          console.log('[ZERO-FLASH] Utilisateur non connecté, formulaire requis');
          setPendingGroupJoin(null); // Reset
          return;
        }
        
        console.log('[ZERO-FLASH] 🚀 Adhésion instantanée au groupe:', pendingGroupJoin);
        
        // Appeler l'API pour rejoindre le groupe silencieusement
        const response = await axios.post(`${API}/groups/join`, {
          group_id: pendingGroupJoin,
          email: storedProfile.email,
          name: storedProfile.name,
          user_id: participantId || storedProfile.id
        });
        
        if (response.data.success) {
          console.log('[ZERO-FLASH] Groupe rejoint:', response.data.group_name || pendingGroupJoin);
          
          // Charger l'historique du groupe
          if (response.data.conversation_id) {
            try {
              const historyRes = await axios.get(`${API}/chat/sessions/${response.data.conversation_id}/messages`);
              if (historyRes.data && historyRes.data.length > 0) {
                const restoredMessages = historyRes.data.map(msg => ({
                  id: msg.id,
                  type: msg.sender_type === 'user' ? 'user' : msg.sender_type === 'coach' ? 'coach' : 'ai',
                  // v10.4: Fallback robuste pour texte (content, text, body)
                  text: msg.content || msg.text || msg.body || '',
                  sender: msg.sender_name,
                  media_url: msg.media_url || null,
                  cta_type: msg.cta_type || null,
                  cta_text: msg.cta_text || null,
                  cta_link: msg.cta_link || null
                }));
                setMessages(restoredMessages);
              }
            } catch (histErr) {
              console.warn('[ZERO-FLASH] Historique non chargé:', histErr.message);
            }
          }
        }
        
        // Nettoyer l'URL (enlever ?group=ID) - fait une seule fois
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, '', cleanUrl);
        setPendingGroupJoin(null); // Reset après traitement
        
      } catch (err) {
        console.error('[ZERO-FLASH] Erreur adhésion:', err.response?.data?.detail || err.message);
        setPendingGroupJoin(null); // Reset même en cas d'erreur
      }
    };
    
    executeAutoJoin();
  }, [pendingGroupJoin, participantId]); // eslint-disable-line react-hooks/exhaustive-deps

  // === PERSISTANCE HISTORIQUE - Charger l'historique au montage si connecté ===
  useEffect(() => {
    const loadChatHistory = async () => {
      // Vérifier si l'utilisateur est connecté
      const storedProfile = getStoredProfile();
      const savedSession = sessionData || (() => {
        try {
          return JSON.parse(localStorage.getItem(CHAT_SESSION_KEY));
        } catch { return null; }
      })();
      
      if (!storedProfile && !savedSession?.id) {
        console.log('[HISTORY] Pas de session active, historique non chargé');
        setIsLoadingHistory(false); // Masquer skeleton
        return;
      }
      
      // Charger même si on a des messages en cache (pour mise à jour)
      if (step !== 'chat') {
        setIsLoadingHistory(false);
        return;
      }
      
      try {
        console.log('[HISTORY] 📜 Chargement de l\'historique depuis l\'API...');
        
        // Essayer de charger l'historique via smart-entry ou directement
        if (savedSession?.id) {
          const response = await axios.get(`${API}/chat/sessions/${savedSession.id}/messages`);
          if (response.data && response.data.length > 0) {
            const restoredMessages = response.data.map(msg => ({
              id: msg.id,
              type: msg.sender_type === 'user' ? 'user' : msg.sender_type === 'coach' ? 'coach' : 'ai',
              // v10.4: Fallback robuste pour texte
              text: msg.content || msg.text || msg.body || '',
              sender: msg.sender_name,
              media_url: msg.media_url || null,
              cta_type: msg.cta_type || null,
              cta_text: msg.cta_text || null,
              cta_link: msg.cta_link || null
            }));
            setMessages(restoredMessages);
            setLastMessageCount(restoredMessages.length);
            // === CACHE HYBRIDE: Sauvegarder dans sessionStorage ===
            saveCachedMessages(restoredMessages);
            console.log('[HISTORY]', restoredMessages.length, 'messages restaurés et mis en cache');
          }
        }
      } catch (err) {
        console.warn('[HISTORY] Historique non disponible:', err.message);
      } finally {
        // Masquer le skeleton après le chargement (succès ou échec)
        setIsLoadingHistory(false);
      }
    };
    
    loadChatHistory();
  }, [step, sessionData]); // eslint-disable-line react-hooks/exhaustive-deps

  // === CACHE HYBRIDE: Mettre à jour le cache à chaque nouveau message ===
  useEffect(() => {
    if (messages.length > 0) {
      saveCachedMessages(messages);
    }
  }, [messages]);
  
  // === v9.4.0: RECHARGEMENT HISTORIQUE À L'OUVERTURE DU WIDGET ===
  useEffect(() => {
    const reloadOnOpen = async () => {
      if (!isOpen) {
        // Widget fermé - reset le badge quand on ferme
        return;
      }
      
      // Widget ouvert - recharger l'historique et reset le badge
      setHasNewMessage(false);
      setUnreadCount(0);
      setUnreadPrivateCount(0); // v9.4.0: Reset le badge quand le widget est ouvert
      
      // Charger depuis cache d'abord pour affichage instantané
      const cachedMsgs = getCachedMessages();
      if (cachedMsgs.length > 0 && messages.length === 0) {
        setMessages(cachedMsgs);
        console.log('[v9.4.0] Messages restaurés depuis cache:', cachedMsgs.length);
      }
      
      // Puis charger depuis API en arrière-plan
      const savedSession = sessionData || (() => {
        try {
          return JSON.parse(localStorage.getItem(CHAT_SESSION_KEY));
        } catch { return null; }
      })();
      
      if (savedSession?.id) {
        try {
          const response = await axios.get(`${API}/chat/sessions/${savedSession.id}/messages`);
          if (response.data && response.data.length > 0) {
            const restoredMessages = response.data.map(msg => ({
              id: msg.id,
              type: msg.sender_type === 'user' ? 'user' : msg.sender_type === 'coach' ? 'coach' : 'ai',
              // v10.4: Fallback robuste pour texte
              text: msg.content || msg.text || msg.body || '',
              sender: msg.sender_name,
              media_url: msg.media_url || null,
              cta_type: msg.cta_type || null,
              cta_text: msg.cta_text || null,
              cta_link: msg.cta_link || null
            }));
            setMessages(restoredMessages);
            saveCachedMessages(restoredMessages);
            console.log('[v9.4.0] Historique rechargé à l\'ouverture:', restoredMessages.length, 'messages');
          }
        } catch (err) {
          console.warn('[v9.4.0] Rechargement historique échoué:', err.message);
        }
      }
    };
    
    reloadOnOpen();
  }, [isOpen]); // Se déclenche uniquement quand isOpen change

  // Extraire le token de lien depuis l'URL si présent
  // v16.0: Supporte /?link={token} (format shareable) ET /chat/{token} (ancien format)
  const getLinkTokenFromUrl = () => {
    // 1. Vérifier le query param ?link=
    const urlParams = new URLSearchParams(window.location.search);
    const linkParam = urlParams.get('link');
    if (linkParam) return linkParam;
    // 2. Fallback: ancien format /chat/{token}
    const path = window.location.pathname;
    const match = path.match(/\/chat\/([a-zA-Z0-9-]+)/);
    return match ? match[1] : null;
  };

  // === SOCKET.IO CONNEXION ET GESTION TEMPS RÉEL ===
  useEffect(() => {
    // Connexion Socket.IO quand on a une session active
    if (sessionData?.id && step === 'chat' && !socketRef.current) {
      console.log('[SOCKET.IO] 🔌 Connexion WebSocket à', SOCKET_URL);
      
      const socket = io(SOCKET_URL, {
        transports: ['websocket'], // WEBSOCKET UNIQUEMENT - Zéro polling
        reconnection: true,
        reconnectionAttempts: 3,
        reconnectionDelay: 500,
        timeout: 5000,
        upgrade: false // Pas de fallback
      });
      
      socketRef.current = socket;
      
      socket.on('connect', () => {
        console.log('[SOCKET.IO] WebSocket connecté! Session:', sessionData.id);
        // Rejoindre la room de la session
        socket.emit('join_session', {
          session_id: sessionData.id,
          participant_id: participantId
        });
      });
      
      socket.on('joined_session', (data) => {
        console.log('[SOCKET.IO] Session rejointe:', data);
      });
      
      // Gestion erreur WebSocket
      socket.on('connect_error', (error) => {
        console.error('[SOCKET.IO] Erreur WebSocket:', error.message);
        // Tenter une reconnexion avec polling en dernier recours
        if (socket.io.opts.transports[0] === 'websocket') {
          console.log('[SOCKET.IO] Tentative fallback polling...');
          socket.io.opts.transports = ['polling', 'websocket'];
          socket.connect();
        }
      });
      
      // === RECONNEXION: Récupérer les messages manqués ===
      socket.on('reconnect', async (attemptNumber) => {
        console.log(`[SOCKET.IO] Reconnexion réussie (tentative ${attemptNumber})`);
        // Rejoindre à nouveau la session
        socket.emit('join_session', {
          session_id: sessionData.id,
          participant_id: participantId
        });
        // Récupérer les messages manqués pendant la déconnexion
        try {
          const response = await fetch(`${API}/chat/sessions/${sessionData.id}/messages`);
          if (response.ok) {
            const data = await response.json();
            if (data.messages && data.messages.length > 0) {
              console.log(`[SOCKET.IO] 📥 ${data.messages.length} messages récupérés après reconnexion`);
              setMessages(prev => {
                // Fusionner sans doublons
                const newMsgs = data.messages.filter(m => !prev.some(p => p.id === m.id));
                if (newMsgs.length > 0) {
                  return [...prev, ...newMsgs].sort((a, b) => 
                    new Date(a.created_at || 0) - new Date(b.created_at || 0)
                  );
                }
                return prev;
              });
            }
          }
        } catch (err) {
          console.warn('[SOCKET.IO] Erreur récupération messages:', err);
        }
      });
      
      // Écouter les nouveaux messages en temps réel
      socket.on('message_received', (messageData) => {
        console.log('[SOCKET.IO] Message recu:', messageData);
        setTypingUser(null);
        
        // Ne pas dupliquer nos propres messages
        if (messageData.senderId === participantId && messageData.type === 'user') return;
        
        // ANTI-DOUBLONS: Verifier ID avant d'ajouter
        setMessages(prev => {
          const msgId = messageData.id || messageData._id;
          if (!msgId || prev.some(m => m.id === msgId || m._id === msgId)) {
            console.log('[SOCKET.IO] Doublon ignore:', msgId);
            return prev;
          }
          return [...prev, {
            id: msgId, type: messageData.type, text: messageData.text || '',
            sender: messageData.sender || '', senderId: messageData.senderId || '',
            created_at: messageData.created_at || new Date().toISOString(),
            media_url: messageData.media_url || null, media_type: messageData.media_type || null,
            cta_type: messageData.cta_type || null, cta_text: messageData.cta_text || null,
            cta_link: messageData.cta_link || null
          }];
        });
        
        // Notifications si pas en train de regarder le chat
        const isUserWatchingChat = isOpen && document.hasFocus();
        if (messageData.senderId !== participantId && !isUserWatchingChat) {
          playSoundIfEnabled(messageData.type === 'coach' ? 'coach' : 'message');
          const senderName = messageData.sender || (messageData.type === 'coach' ? 'Coach Bassi' : 'Afroboost');
          showNewMessageNotification(senderName, messageData.text);
          // v9.4.0: Incrémenter le badge de notification
          setUnreadPrivateCount(prev => prev + 1);
          setHasNewMessage(true);
        }
      });
      
      // v8.6: ÉCOUTER LES MESSAGES DE GROUPE
      socket.on('group_message', (messageData) => {
        console.log('[SOCKET.IO] Message groupe recu:', messageData);
        setGroupMessages(prev => {
          const msgId = messageData.id;
          if (prev.some(m => m.id === msgId)) return prev;
          return [...prev, {
            id: msgId, type: 'coach', text: messageData.text || '',
            sender: messageData.sender || 'Coach Bassi', is_group: true,
            created_at: messageData.created_at, media_url: messageData.media_url
          }];
        });
        // Notification si en mode groupe
        if (chatMode === 'group' && !document.hasFocus()) {
          playSoundIfEnabled('coach');
          // v9.4.0: Incrémenter le badge pour les messages de groupe aussi
          setUnreadPrivateCount(prev => prev + 1);
          setHasNewMessage(true);
        }
      });
      
      // === ÉCOUTER L'INDICATEUR DE SAISIE ===
      socket.on('user_typing', (data) => {
        console.log('[SOCKET.IO] ⌨️ Typing event:', data);
        
        if (data.is_typing) {
          // Afficher l'indicateur
          setTypingUser({
            name: data.user_name,
            type: data.user_type
          });
          
          // Cacher automatiquement après 3 secondes d'inactivité
          if (typingTimeoutRef.current) {
            clearTimeout(typingTimeoutRef.current);
          }
          typingTimeoutRef.current = setTimeout(() => {
            setTypingUser(null);
          }, 3000);
        } else {
          // Cacher l'indicateur
          setTypingUser(null);
        }
      });
      
      // === SYNCHRONISATION TEMPS RÉEL : Suppression de cours ===
      socket.on('course_deleted', (data) => {
        console.log('[SOCKET.IO] 🗑️ Cours supprimé:', data.courseId);
        
        // 1. Retirer le cours de la liste locale
        setAvailableCourses(prev => prev.filter(course => course.id !== data.courseId));
        
        // 2. HARD DELETE: Vider le cache local pour forcer un rafraîchissement
        if (data.hardDelete) {
          // Supprimer les caches liés aux cours du sessionStorage
          try {
            const keysToRemove = [];
            for (let i = 0; i < sessionStorage.length; i++) {
              const key = sessionStorage.key(i);
              if (key && (key.includes('courses') || key.includes('reservations') || key.includes('calendar'))) {
                keysToRemove.push(key);
              }
            }
            keysToRemove.forEach(key => sessionStorage.removeItem(key));
            console.log('[CACHE] 🧹 Cache cours/réservations vidé');
          } catch (e) {
            console.warn('[CACHE] Erreur nettoyage:', e);
          }
        }
        
        // 3. Notification pour l'utilisateur
        if (data.deletedReservations > 0) {
          console.log(`[SOCKET.IO] ${data.deletedReservations} réservation(s) annulée(s)`);
        }
      });
      
      // === SYNCHRONISATION TEMPS RÉEL : Purge des cours archivés ===
      socket.on('courses_purged', (data) => {
        console.log('[SOCKET.IO] 🧹 Purge cours archivés:', data.count, 'cours supprimés');
        // Retirer tous les cours purgés
        setAvailableCourses(prev => prev.filter(course => !data.purgedIds.includes(course.id)));
        // Vider tout le cache
        try {
          sessionStorage.clear();
          console.log('[CACHE] 🧹 Cache entièrement vidé après purge');
        } catch (e) {
          console.warn('[CACHE] Erreur:', e);
        }
      });
      
      socket.on('disconnect', () => {
        console.log('[SOCKET.IO] Déconnecté');
      });
      
      socket.on('connect_error', (error) => {
        console.warn('[SOCKET.IO] Erreur connexion:', error.message);
      });
    }
    
    // Cleanup - Nettoyage complet pour éviter les fuites de mémoire
    return () => {
      if (socketRef.current) {
        const socket = socketRef.current;
        console.log('[SOCKET.IO] 🔌 Nettoyage listeners et déconnexion...');
        
        // Supprimer explicitement tous les listeners avant déconnexion
        socket.off('connect');
        socket.off('joined_session');
        socket.off('connect_error');
        socket.off('disconnect');
        socket.off('message_received');
        socket.off('user_typing');
        socket.off('course_deleted');
        socket.off('courses_purged');
        socket.off('reconnect');
        
        socket.disconnect();
        socketRef.current = null;
      }
      
      // Nettoyer les timers typing
      if (typingTimeoutRef.current) {
        clearTimeout(typingTimeoutRef.current);
        typingTimeoutRef.current = null;
      }
    };
  }, [sessionData?.id, step, participantId]);

  // === ÉTAT DE SYNCHRONISATION (indicateur visuel) ===
  const [isSyncing, setIsSyncing] = useState(false);
  
  // === RÉCUPÉRATION MESSAGES AU RETOUR - ARCHITECTURE "RAMASSER" RÉSILIENTE ===
  // Garantit ZÉRO PERTE de message avec retry automatique et gestion hors-ligne
  useEffect(() => {
    if (!sessionData?.id || step !== 'chat') return;
    
    // Stocker la dernière date de sync dans localStorage (UTC ISO 8601)
    const LAST_SYNC_KEY = `afroboost_last_sync_${sessionData.id}`;
    let lastSyncTime = localStorage.getItem(LAST_SYNC_KEY) || null;
    
    // Constantes de configuration
    const MAX_RETRIES = 3;
    const RETRY_DELAY = 2000;
    const ONLINE_DELAY = 800; // Délai après retour réseau pour stabiliser la connexion
    const REQUEST_TIMEOUT = 10000;
    
    // Fonction de récupération RÉSILIENTE avec retry
    const fetchLatestMessages = async (retryCount = 0, source = 'manual') => {
      // Vérifier si on est en ligne
      if (!navigator.onLine) {
        console.log('[RAMASSER] 📵 Hors ligne - Attente connexion...');
        return; // On laisse le listener 'online' rappeler
      }
      
      setIsSyncing(true);
      
      try {
        // Construire l'URL avec timestamp UTC
        let url = `${API}/messages/sync?session_id=${sessionData.id}&limit=100`;
        if (lastSyncTime) {
          // S'assurer que le timestamp est en UTC
          url += `&since=${encodeURIComponent(lastSyncTime)}`;
        }
        
        console.log(`[RAMASSER] Sync depuis ${source} (since=${lastSyncTime ? lastSyncTime.substring(0, 19) : 'null'})`);
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);
        
        const response = await fetch(url, {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        
        const data = await response.json();
        
        // Mettre à jour lastSyncTime avec le timestamp UTC du serveur
        if (data.synced_at) {
          lastSyncTime = data.synced_at;
          localStorage.setItem(LAST_SYNC_KEY, lastSyncTime);
        }
        
        if (data.messages && data.messages.length > 0) {
          console.log(`[RAMASSER] ${data.count} message(s) recupere(s)`);
          setMessages(prev => {
            // V146: ANTI-DOUBLONS AMÉLIORÉ — vérifie ID + contenu pour détecter les messages optimistes
            const existingIds = new Set(prev.flatMap(m => [m.id, m._id].filter(Boolean)));
            // V146: Collecter le texte des messages optimistes (temp_user_*) pour éviter les doublons
            const pendingTexts = new Set(
              prev.filter(m => m.id && m.id.startsWith('temp_user_')).map(m => (m.text || '').trim().toLowerCase())
            );

            let updatedPrev = [...prev];
            const trulyNew = [];

            for (const m of data.messages) {
              const msgId = m.id || m._id;
              if (!msgId) continue;

              // Cas 1: ID déjà connu → skip
              if (existingIds.has(msgId)) continue;

              // V146: Cas 2: Message serveur correspondant à un message optimiste temp_user_*
              const msgText = (m.text || m.content || '').trim().toLowerCase();
              const isSameUser = m.sender_type === 'user' || m.type === 'user';
              if (isSameUser && pendingTexts.has(msgText)) {
                // Remplacer le temp_user_ par le vrai ID serveur (pas d'ajout = pas de doublon)
                const tempIdx = updatedPrev.findIndex(p =>
                  p.id && p.id.startsWith('temp_user_') && (p.text || '').trim().toLowerCase() === msgText
                );
                if (tempIdx !== -1) {
                  updatedPrev[tempIdx] = { ...updatedPrev[tempIdx], id: msgId, created_at: m.created_at };
                  pendingTexts.delete(msgText); // Ne matcher qu'une fois
                  existingIds.add(msgId);
                  console.log(`[V146] Remplacé temp_user → ${msgId}`);
                  continue;
                }
              }

              // Cas 3: Vraiment nouveau
              trulyNew.push(m);
              existingIds.add(msgId);
            }

            if (trulyNew.length > 0) {
              console.log(`[RAMASSER] ${trulyNew.length} NOUVEAUX messages ajoutes`);
              // v87: Son notification pour les nouveaux messages (campagne ou coach)
              const hasCampaignMsg = trulyNew.some(m =>
                (m.sender_id && m.sender_id.startsWith('coach-campaign')) || m.campaign_id
              );
              const hasCoachMsg = trulyNew.some(m => m.sender_type === 'coach');
              if (hasCampaignMsg || hasCoachMsg) {
                try { playSoundIfEnabled('coach'); } catch(e) {}
              } else {
                try { playSoundIfEnabled('message'); } catch(e) {}
              }
              return [...updatedPrev, ...trulyNew].sort((a, b) => (a.created_at || '0').localeCompare(b.created_at || '0'));
            }

            // V146: Même si pas de trulyNew, on peut avoir remplacé des temp → retourner updatedPrev
            if (updatedPrev !== prev) return updatedPrev;
            return prev;
          });
        }

        setIsSyncing(false);
        
      } catch (err) {
        console.warn(`[RAMASSER] Tentative ${retryCount + 1}/${MAX_RETRIES} échouée:`, err.message);
        
        // Retry si pas épuisé et toujours en ligne
        if (retryCount < MAX_RETRIES - 1 && navigator.onLine) {
          console.log(`[RAMASSER] Retry dans ${RETRY_DELAY/1000}s...`);
          await new Promise(r => setTimeout(r, RETRY_DELAY));
          return fetchLatestMessages(retryCount + 1, source);
        }
        
        // Fallback vers l'ancien endpoint
        console.log('[RAMASSER] Tentative fallback...');
        try {
          const fallback = await fetch(`${API}/chat/sessions/${sessionData.id}/messages`);
          if (fallback.ok) {
            const data = await fallback.json();
            if (Array.isArray(data) && data.length > 0) {
              setMessages(prev => {
                const existingIds = new Set(prev.flatMap(m => [m.id, m._id].filter(Boolean)));
                // V146: Aussi vérifier les messages optimistes par contenu
                const pendingTexts = new Set(
                  prev.filter(m => m.id && m.id.startsWith('temp_user_')).map(m => (m.text || '').trim().toLowerCase())
                );
                const newMsgs = data.filter(m => {
                  if (!m.id || existingIds.has(m.id)) return false;
                  // V146: Skip si c'est un doublon d'un message optimiste
                  const mText = (m.text || m.content || '').trim().toLowerCase();
                  if ((m.sender_type === 'user' || m.type === 'user') && pendingTexts.has(mText)) return false;
                  return true;
                });
                if (newMsgs.length > 0) {
                  console.log(`[RAMASSER-FALLBACK] ${newMsgs.length} messages récupérés`);
                  return [...prev, ...newMsgs].sort((a, b) =>
                    (a.created_at || '0').localeCompare(b.created_at || '0')
                  );
                }
                return prev;
              });
            }
          }
        } catch (fallbackErr) {
          console.warn('[RAMASSER] Fallback échoué:', fallbackErr.message);
        }
        
        setIsSyncing(false);
      }
    };
    
    // Listener visibilité (changement d'onglet ou retour de veille) - PRIORITÉ HAUTE
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        console.log('[VISIBILITY] 👀 App visible - Sync immédiate');
        // Sync immédiate sans délai pour visibilitychange (utilisateur actif)
        fetchLatestMessages(0, 'visibility');
      }
    };
    
    // Listener focus (clic sur la fenêtre)
    const handleFocus = () => {
      console.log('[FOCUS] App focus');
      fetchLatestMessages(0, 'focus');
    };
    
    // Listener online (retour réseau) - AVEC DÉLAI 800ms
    const handleOnline = () => {
      console.log('[ONLINE] 📶 Réseau rétabli - Attente stabilisation...');
      setTimeout(() => {
        console.log('[ONLINE] 📶 Sync après stabilisation');
        fetchLatestMessages(0, 'online');
      }, ONLINE_DELAY);
    };
    
    // Listener changement de connexion (4G <-> Wi-Fi) via Network Information API
    let connectionChangeTimeout = null;
    const handleConnectionChange = () => {
      // Éviter les appels multiples rapides
      if (connectionChangeTimeout) clearTimeout(connectionChangeTimeout);
      connectionChangeTimeout = setTimeout(() => {
        if (navigator.onLine) {
          console.log('[CONNECTION] Type réseau changé - Sync...');
          fetchLatestMessages(0, 'connection_change');
        }
      }, 1000); // 1s de délai pour stabiliser
    };
    
    // Ajouter les listeners
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleFocus);
    window.addEventListener('online', handleOnline);
    
    // Network Information API (si disponible)
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (connection) {
      connection.addEventListener('change', handleConnectionChange);
    }
    
    // Récupération initiale au montage
    fetchLatestMessages(0, 'mount');

    // === v87: POLLING TEMPS RÉEL — Toutes les 3s quand chat visible (plus réactif) ===
    const POLL_INTERVAL = 3000; // v87: 3 secondes pour chat "live"
    const pollRef = setInterval(() => {
      if (document.visibilityState === 'visible' && navigator.onLine) {
        fetchLatestMessages(0, 'poll');
      }
    }, POLL_INTERVAL);

    // Cleanup
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
      window.removeEventListener('online', handleOnline);
      clearInterval(pollRef);
      if (connection) {
        connection.removeEventListener('change', handleConnectionChange);
      }
      if (connectionChangeTimeout) clearTimeout(connectionChangeTimeout);
    };
  }, [sessionData?.id, step]);

  // === MESSAGERIE PRIVÉE (MP) - FENÊTRE FLOTTANTE ===
  const openPrivateChat = async (targetId, targetName) => {
    if (!participantId || !targetId || targetId === participantId) return;
    
    setIsLoading(true);
    try {
      // Créer ou récupérer la conversation privée
      const response = await axios.post(`${API}/private/conversations`, {
        participant_1_id: participantId,
        participant_1_name: leadData.firstName,
        participant_2_id: targetId,
        participant_2_name: targetName
      });
      
      const conversation = response.data;
      
      // Charger les messages existants
      const messagesRes = await axios.get(`${API}/private/messages/${conversation.id}`);
      
      // Ouvrir la fenêtre flottante MP
      setActivePrivateChat({
        id: conversation.id,
        recipientId: targetId,
        recipientName: targetName
      });
      setPrivateMessages(messagesRes.data.map(m => ({
        id: m.id,
        text: m.content,
        sender: m.sender_name,
        senderId: m.sender_id,
        isMine: m.sender_id === participantId,
        createdAt: m.created_at
      })));
      
      // === SOCKET.IO: Rejoindre la room de conversation privée ===
      if (socketRef.current) {
        socketRef.current.emit('join_private_conversation', {
          conversation_id: conversation.id,
          participant_id: participantId
        });
      }
      
      console.log(`💬 MP ouverte avec ${targetName}`);
      
    } catch (err) {
      console.error('Erreur ouverture MP:', err);
      alert('Erreur lors de l\'ouverture de la conversation privée');
    } finally {
      setIsLoading(false);
    }
  };

  // Fermer la fenêtre MP
  const closePrivateChat = () => {
    // === SOCKET.IO: Quitter la room de conversation privée ===
    if (socketRef.current && activePrivateChat?.id) {
      socketRef.current.emit('leave_private_conversation', {
        conversation_id: activePrivateChat.id
      });
    }
    setActivePrivateChat(null);
    setPrivateMessages([]);
    setPrivateInput('');
  };

  // === SOCKET.IO pour les MP - Remplace le polling ===
  useEffect(() => {
    if (!socketRef.current) return;
    
    const socket = socketRef.current;
    
    // Handler principal pour les messages privés
    const handlePrivateMessage = (data) => {
      console.log('[SOCKET.IO] 📩 Message privé reçu:', data);
      
      // Ne pas compter nos propres messages
      if (data.senderId === participantId) return;
      
      // Vérifier si c'est pour notre conversation active
      if (activePrivateChat && data.conversation_id === activePrivateChat.id) {
        // Message dans la conversation ouverte -> ajouter à la liste
        setPrivateMessages(prev => {
          const exists = prev.some(m => m.id === data.id);
          if (exists) return prev;
          
          return [...prev, {
            id: data.id,
            text: data.text,
            sender: data.sender,
            senderId: data.senderId,
            isMine: false,
            createdAt: data.created_at
          }];
        });
        
        // Son de notification DM (fenêtre déjà ouverte) - son "private" distinct
        playSoundIfEnabled('private');
        
        // Marquer comme lu
        axios.put(`${API}/private/messages/read/${activePrivateChat.id}?reader_id=${participantId}`).catch(() => {});
      } else {
        // Message pour une autre conversation ou pas de conversation ouverte
        // -> NOTIFICATION COMPLÈTE (badge + son si activé + titre clignotant)
        setUnreadPrivateCount(prev => prev + 1);
        playSoundIfEnabled('private'); // Son "ding" cristallin si activé
        notifyPrivateMessage(data.sender || 'Quelqu\'un');
      }
    };
    
    socket.on('private_message_received', handlePrivateMessage);
    
    return () => {
      socket.off('private_message_received', handlePrivateMessage);
    };
  }, [activePrivateChat, participantId, soundEnabled]);

  // === SOCKET.IO pour le TYPING INDICATOR dans les DM ===
  useEffect(() => {
    if (!socketRef.current) return;
    
    const socket = socketRef.current;
    
    const handleDmTyping = (data) => {
      // Ignorer nos propres événements de frappe
      if (data.user_id === participantId) return;
      
      // Vérifier si c'est pour notre conversation active
      if (activePrivateChat && data.conversation_id === activePrivateChat.id) {
        if (data.is_typing) {
          setDmTypingUser({ name: data.user_name });
          
          // Auto-hide après 3 secondes
          if (dmTypingTimeoutRef.current) {
            clearTimeout(dmTypingTimeoutRef.current);
          }
          dmTypingTimeoutRef.current = setTimeout(() => {
            setDmTypingUser(null);
          }, 3000);
        } else {
          setDmTypingUser(null);
        }
      }
    };
    
    socket.on('dm_typing', handleDmTyping);
    
    return () => {
      socket.off('dm_typing', handleDmTyping);
      if (dmTypingTimeoutRef.current) {
        clearTimeout(dmTypingTimeoutRef.current);
      }
    };
  }, [activePrivateChat, participantId]);

  // === SOCKET.IO pour la mise à jour d'AVATAR en temps réel ===
  useEffect(() => {
    if (!socketRef.current) return;
    
    const socket = socketRef.current;
    
    const handleAvatarChanged = (data) => {
      console.log('[SOCKET.IO] 📷 Avatar mis à jour:', data);
      
      // Mettre à jour les messages privés si l'avatar de l'interlocuteur change
      if (activePrivateChat && data.user_id !== participantId) {
        setPrivateMessages(prev => prev.map(msg => {
          if (msg.senderId === data.user_id) {
            return { ...msg, senderPhotoUrl: data.photo_url };
          }
          return msg;
        }));
      }
      
      // Mettre à jour les messages du chat principal (communautaire)
      setMessages(prev => prev.map(msg => {
        if (msg.senderId === data.user_id) {
          return { ...msg, senderPhotoUrl: data.photo_url };
        }
        return msg;
      }));
    };
    
    socket.on('user_avatar_changed', handleAvatarChanged);
    
    return () => {
      socket.off('user_avatar_changed', handleAvatarChanged);
    };
  }, [activePrivateChat, participantId]);

  // === DÉMARRER UNE DISCUSSION PRIVÉE (COMPAT ANCIEN CODE) ===
  const startPrivateChat = async (targetId, targetName) => {
    // Utilise la nouvelle fonction openPrivateChat avec fenêtre flottante
    // Réinitialiser le compteur et arrêter le clignotement quand on ouvre une conversation
    setUnreadPrivateCount(0);
    stopTitleFlash();
    openPrivateChat(targetId, targetName);
  };

  // Insérer un emoji dans l'input (utilisé par EmojiPicker)
  const insertEmoji = (emojiName) => {
    // Si c'est un emoji natif (🔥), l'ajouter directement
    if (emojiName.length <= 2 && /[\u{1F300}-\u{1F9FF}]/u.test(emojiName)) {
      setInputMessage(prev => prev + emojiName);
    } else {
      // Sinon c'est un emoji personnalisé -> tag
      const emojiTag = `[emoji:${emojiName}]`;
      setInputMessage(prev => prev + emojiTag);
    }
    setShowEmojiPicker(false);
  };

  // === MÉMORISATION CLIENT: Charger la session et configurer le chat ===
  useEffect(() => {
    const savedSession = localStorage.getItem(CHAT_SESSION_KEY);

    if (savedSession) {
      try {
        const session = JSON.parse(savedSession);
        setSessionData(session);
        setIsCommunityMode(session.mode === 'community');
      } catch (err) {
        localStorage.removeItem(CHAT_SESSION_KEY);
      }
    }

    // Si on arrive via un lien partagé, ouvrir automatiquement le widget
    // v16.0: Vérifier si onboarding déjà fait, sinon afficher le tunnel
    const linkToken = getLinkTokenFromUrl();
    if (linkToken) {
      setCurrentLinkToken(linkToken);
      setIsOpen(true);
      setIsFullscreen(true);

      // Vérifier si le visiteur a déjà complété l'onboarding pour ce lien
      const storedParticipant = localStorage.getItem(`af_participant_${linkToken}`);
      if (storedParticipant) {
        try {
          const parsed = JSON.parse(storedParticipant);
          console.log('[CHATWIDGET] 🔄 Visiteur reconnu via onboarding:', parsed.name);
          // Lancer smart-entry avec les données sauvegardées
          handleSmartEntry({
            firstName: parsed.name,
            email: parsed.email,
            whatsapp: parsed.whatsapp
          }, linkToken);
        } catch (e) {
          localStorage.removeItem(`af_participant_${linkToken}`);
          setShowOnboardingTunnel(true);
        }
      } else {
        // Nouveau visiteur → afficher le tunnel d'onboarding
        console.log('[CHATWIDGET] 🆕 Nouveau visiteur, affichage tunnel onboarding');
        setShowOnboardingTunnel(true);
      }
    }
  }, []);

  // v14.5: Mettre à jour le titre de la page quand une session avec titre est active
  useEffect(() => {
    if (sessionData?.title) {
      document.title = `Afroboost | Chat ${sessionData.title}`;
    } else if (isOpen) {
      document.title = 'Afroboost | Chat';
    }
    // Cleanup: remettre le titre original à la fermeture
    return () => {
      if (!isOpen) {
        document.title = 'Afroboost';
      }
    };
  }, [sessionData?.title, isOpen]);
  
  // === FERMER LE MENU UTILISATEUR AU CLIC EXTÉRIEUR ===
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (showUserMenu && !e.target.closest('.afro-share-menu')) {
        setShowUserMenu(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [showUserMenu]);

  // === MODE COACH: Charger les sessions actives ===
  const loadCoachSessions = async () => {
    try {
      const res = await axios.get(`${API}/chat/sessions`);
      // Filtrer les sessions non supprimées avec des messages récents
      const activeSessions = res.data.filter(s => !s.is_deleted);
      setCoachSessions(activeSessions);
    } catch (err) {
      console.error('Error loading coach sessions:', err);
    }
  };

  // v162: Charger les réservations pour le dashboard coach
  var loadCoachReservations = function() {
    axios.get(API + '/reservations').then(function(res) {
      var d = res.data;
      setCoachReservations(Array.isArray(d) ? d : (d && Array.isArray(d.data) ? d.data : []));
    }).catch(function(err) { console.error('[v162] Reservations load error:', err); });
  };

  // v162: Valider un QR code réservation
  var handleQrValidation = function() {
    if (!qrScanCode.trim()) return;
    setQrScanResult(null);
    axios.post(API + '/reservations/staff/validate', { code: qrScanCode.trim() })
      .then(function(res) {
        setQrScanResult(res.data);
        if (res.data.success) setQrScanCode('');
      })
      .catch(function(err) {
        var msg = (err.response && err.response.data && err.response.data.detail) || 'Erreur de validation';
        setQrScanResult({ success: false, message: msg });
      });
  };

  // v162e: QR Camera Scanner functions
  var loadQrScannerLib = function(callback) {
    if (window.Html5Qrcode) { callback(); return; }
    var s = document.createElement('script');
    s.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
    s.onload = callback;
    s.onerror = function() { setQrCameraError('Impossible de charger le scanner'); };
    document.head.appendChild(s);
  };

  var startQrCamera = function() {
    setQrCameraError('');
    setQrScanResult(null);
    // Clear the container first (html5-qrcode needs it empty)
    var container = document.getElementById('qr-reader-container');
    if (container) container.innerHTML = '';
    setQrCameraActive(true); // Show container as active BEFORE starting
    loadQrScannerLib(function() {
      try {
        if (qrScannerRef.current) {
          try { qrScannerRef.current.stop(); } catch(e) {}
        }
        // Small delay to ensure React has rendered the container visible
        setTimeout(function() {
          var scanner = new window.Html5Qrcode('qr-reader-container');
          qrScannerRef.current = scanner;
          scanner.start(
            { facingMode: 'environment' },
            { fps: 10, qrbox: { width: 180, height: 180 }, aspectRatio: 1.0 },
            function(decodedText) {
              // QR code scanned successfully
              setQrScanCode(decodedText.toUpperCase());
              try { scanner.stop(); } catch(e) {}
              setQrCameraActive(false);
              // Auto-validate
              axios.post(API + '/reservations/staff/validate', { code: decodedText.trim() })
                .then(function(res) {
                  setQrScanResult(res.data);
                  if (res.data.success) setQrScanCode('');
                })
                .catch(function(err) {
                  var msg = (err.response && err.response.data && err.response.data.detail) || 'Erreur de validation';
                  setQrScanResult({ success: false, message: msg });
                });
            },
            function() {} // ignore scan errors (no QR found in frame)
          ).catch(function(err) {
            var errMsg = err && err.message ? err.message : String(err);
            if (errMsg.indexOf('Permission') >= 0 || errMsg.indexOf('NotAllowed') >= 0) {
              setQrCameraError('Autorisez l\'accès à la caméra dans les paramètres de votre navigateur');
            } else if (errMsg.indexOf('NotFound') >= 0 || errMsg.indexOf('device') >= 0) {
              setQrCameraError('Aucune caméra détectée sur cet appareil');
            } else {
              setQrCameraError('Caméra: ' + errMsg);
            }
            setQrCameraActive(false);
          });
        }, 300);
      } catch(e) {
        setQrCameraError('Erreur scanner: ' + e.message);
        setQrCameraActive(false);
      }
    });
  };

  var stopQrCamera = function() {
    if (qrScannerRef.current) {
      try { qrScannerRef.current.stop(); } catch(e) {}
      qrScannerRef.current = null;
    }
    setQrCameraActive(false);
  };

  // v162f: Load coach profile on mount (for photo)
  var loadCoachProfile = function() {
    axios.get(API + '/coach-profile').then(function(res) {
      setCoachProfile(res.data || null);
    }).catch(function() {});
  };

  // v162f: AI suggestion for coach — ask backend AI for a response suggestion
  var getAiSuggestion = function() {
    if (!selectedCoachSession || aiSuggestionLoading) return;
    setAiSuggestionLoading(true);
    setAiSuggestion('');
    // Collect last messages from the conversation
    var msgs = (messages || []).slice(-6).map(function(m) {
      return (m.type === 'user' ? 'Client' : 'Coach') + ': ' + (m.text || '').substring(0, 200);
    }).join('\n');
    axios.post(API + '/chat', {
      message: 'Tu es le coach Afroboost. Suggère une réponse courte et chaleureuse au dernier message du client. Voici la conversation récente:\n' + msgs + '\n\nSuggère une réponse de coach (2-3 phrases max, en français):',
      session_id: 'ai-suggestion-' + Date.now(),
      mode: 'ai'
    }).then(function(res) {
      var reply = res.data && res.data.reply ? res.data.reply : '';
      setAiSuggestion(reply);
      setAiSuggestionLoading(false);
    }).catch(function() {
      setAiSuggestion('Erreur lors de la génération de suggestion.');
      setAiSuggestionLoading(false);
    });
  };

  // === MODE COACH: Charger les messages d'une session ===
  const loadCoachSessionMessages = async (session) => {
    setSelectedCoachSession(session);
    try {
      const res = await axios.get(`${API}/chat/sessions/${session.id}/messages`);
      const formattedMessages = res.data.map(m => ({
        id: m.id,
        type: m.sender_type === 'user' ? 'user' : m.sender_type === 'coach' ? 'coach' : 'ai',
        text: m.content || m.text || '',
        sender: m.sender_name,
        senderId: m.sender_id,
        media_url: m.media_url || null,
        cta_type: m.cta_type || null,
        cta_text: m.cta_text || null,
        cta_link: m.cta_link || null
      }));
      setMessages(formattedMessages);
      setLastMessageCount(formattedMessages.length);
    } catch (err) {
      console.error('Error loading session messages:', err);
    }
  };

  // === MODE COACH: Envoyer une réponse ===
  const sendCoachResponse = async () => {
    if (!selectedCoachSession || !inputMessage.trim()) return;
    
    setIsLoading(true);
    try {
      await axios.post(`${API}/chat/coach-response`, {
        session_id: selectedCoachSession.id,
        message: inputMessage.trim(),
        coach_name: 'Coach'
      });
      setInputMessage('');
      // Recharger les messages
      await loadCoachSessionMessages(selectedCoachSession);
      playSoundIfEnabled('coach');
    } catch (err) {
      console.error('Error sending coach response:', err);
      alert('Erreur lors de l\'envoi du message');
    } finally {
      setIsLoading(false);
    }
  };

  // Charger les sessions quand le mode coach est activé
  useEffect(() => {
    if (isCoachMode && isOpen) {
      loadCoachSessions();
      loadCoachProfile();
      setStep('coach');
    }
  }, [isCoachMode, isOpen]);
  
  // === FERMER LES MENUS AU CLIC EXTÉRIEUR ===
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (showCoachMenu && !e.target.closest('.coach-icons-menu')) {
        setShowCoachMenu(false);
      }
    };
    document.addEventListener('click', handleClickOutside);
    return () => document.removeEventListener('click', handleClickOutside);
  }, [showCoachMenu]);

  // Scroll vers le bas des messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // === TIMER DYNAMIQUE: Rafraîchit les timestamps toutes les 60s ===
  const [, setTimestampTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      setTimestampTick(t => t + 1);
    }, 60000); // 60 secondes
    return () => clearInterval(timer);
  }, []);

  // === SMART ENTRY: Point d'entrée intelligent avec reconnaissance ===
  const handleSmartEntry = async (clientData, linkToken = null) => {
    try {
      const response = await axios.post(`${API}/chat/smart-entry`, {
        name: clientData.firstName,
        email: clientData.email,
        whatsapp: clientData.whatsapp,
        link_token: linkToken,
        tunnel_answers: clientData.tunnelAnswers || null
      });

      const { participant, session, is_returning, chat_history, message } = response.data;

      // Sauvegarder les données
      const fullClientData = {
        ...clientData,
        participantId: participant.id
      };
      // Sauvegarder avec les deux clés pour compatibilité
      localStorage.setItem(CHAT_CLIENT_KEY, JSON.stringify(fullClientData));
      localStorage.setItem(AFROBOOST_IDENTITY_KEY, JSON.stringify({
        ...fullClientData,
        savedAt: new Date().toISOString()
      }));
      localStorage.setItem(CHAT_SESSION_KEY, JSON.stringify(session));

      setParticipantId(participant.id);
      setSessionData(session);
      setIsReturningClient(is_returning);
      setIsCommunityMode(session.mode === 'community');
      
      // === MISE À JOUR DU MODE COACH APRÈS CONNEXION ===
      const isCoach = COACH_EMAILS.includes(clientData.email?.toLowerCase());
      setIsCoachMode(isCoach);
      console.log(`[AUTH] Email: ${clientData.email}, isCoach: ${isCoach}`);

      // Restaurer l'historique si utilisateur reconnu
      if (is_returning && chat_history && chat_history.length > 0) {
        const restoredMessages = chat_history.map(msg => ({
          id: msg.id,
          type: msg.sender_type === 'user' ? 'user' : msg.sender_type === 'coach' ? 'coach' : 'ai',
          text: msg.content,
          sender: msg.sender_name
        }));
        setMessages([
          { id: `welcome_${Date.now()}`, type: 'ai', text: message },
          ...restoredMessages
        ]);
        setLastMessageCount(chat_history.length + 1);
      } else {
        setMessages([{
          id: `welcome_${Date.now()}`,
          type: 'ai',
          text: message
        }]);
        setLastMessageCount(1);
      }

      setStep('chat');
      
      // === DEMANDE AUTORISATION NOTIFICATIONS SUR CLIC CONNEXION ===
      // Anti-blocage mobile: demande liee a une action utilisateur (clic)
      const currentPermission = getNotificationPermissionStatus();
      if (currentPermission !== 'granted' && currentPermission !== 'denied') {
        console.log('[NOTIFICATIONS] Demande autorisation sur clic connexion...');
        const permission = await requestNotificationPermission();
        if (permission === 'granted') {
          setPushEnabled(true);
          // S'abonner aux notifications push avec l'ID du participant
          const subscribed = await subscribeToPush(participant.id);
          console.log('[PUSH] Abonnement:', subscribed ? 'OK' : 'Echec');
        }
      } else if (currentPermission === 'granted' && !isSubscribed()) {
        // Permission deja accordee mais pas encore abonne -> s'abonner
        const subscribed = await subscribeToPush(participant.id);
        if (subscribed) setPushEnabled(true);
      }
      
      // Debloquer l'audio pour iOS (necessite action utilisateur)
      unlockAudio();
      
      // === MESSAGE iOS PWA ===
      // Detecter iOS et afficher message pour ajout ecran d'accueil
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
      const isStandalone = window.navigator.standalone === true;
      const alreadyShown = localStorage.getItem('af_ios_prompt_shown');
      
      if (isIOS && !isStandalone && !alreadyShown) {
        setShowiOSPrompt(true);
        localStorage.setItem('af_ios_prompt_shown', 'true');
        // Auto-fermeture apres 5 secondes
        setTimeout(() => setShowiOSPrompt(false), 5000);
      }
      
      return { success: true, session, participant };

    } catch (err) {
      console.error('Smart entry error:', err);
      // Fallback: continuer sans le backend amélioré
      setMessages([{
        type: 'ai',
        text: `Enchanté ${clientData.firstName} ! Comment puis-je t'aider ?`
      }]);
      setStep('chat');
      return { success: false };
    }
  };

  // Valider et enregistrer le lead
  const handleSubmitLead = async (e) => {
    e.preventDefault();
    setError('');
    
    // Validation
    if (!leadData.firstName.trim()) {
      setError('Le prénom est requis');
      return;
    }
    if (!leadData.whatsapp.trim()) {
      setError('Le numéro WhatsApp est requis');
      return;
    }
    if (!leadData.email.trim() || !leadData.email.includes('@')) {
      setError('Un email valide est requis');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const clientData = {
        firstName: leadData.firstName.trim(),
        whatsapp: leadData.whatsapp.trim(),
        email: leadData.email.trim().toLowerCase()
      };

      // Utiliser le smart entry pour la reconnaissance automatique
      const linkToken = getLinkTokenFromUrl();
      await handleSmartEntry(clientData, linkToken);

      // Backup: créer aussi un lead (ancien système)
      try {
        await axios.post(`${API}/leads`, {
          firstName: clientData.firstName,
          whatsapp: clientData.whatsapp,
          email: clientData.email,
          source: linkToken ? `link_${linkToken}` : 'widget_ia'
        });
      } catch (leadErr) {
        console.warn('Lead creation failed, continuing anyway:', leadErr);
      }
      
    } catch (err) {
      console.error('Error:', err);
      // Fallback
      localStorage.setItem(CHAT_CLIENT_KEY, JSON.stringify({
        firstName: leadData.firstName.trim(),
        whatsapp: leadData.whatsapp.trim(),
        email: leadData.email.trim().toLowerCase()
      }));
      
      setStep('chat');
      setMessages([{
        type: 'ai',
        text: `Enchanté ${leadData.firstName} ! Comment puis-je t'aider ?`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // === CLIENT RECONNU: Ouvrir directement le chat ===
  const handleReturningClientStart = async () => {
    setIsLoading(true);
    
    try {
      const linkToken = getLinkTokenFromUrl();
      await handleSmartEntry(leadData, linkToken);
    } catch (err) {
      console.error('Error:', err);
      setStep('chat');
      setMessages([{
        type: 'ai',
        text: `Bonjour ${leadData.firstName} ! 😊 Comment puis-je t'aider ?`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // === Ouvrir le widget ===
  const handleOpenWidget = () => {
    setIsOpen(true);
    
    // Si client reconnu et pas encore en mode chat, ouvrir directement le chat
    if (isReturningClient && step === 'form') {
      handleReturningClientStart();
    }
  };

  // === v88: Soumettre un avis post-session (fix erreur + masquage permanent) ===
  const handleSubmitReview = async () => {
    if (!reviewText.trim() || reviewSubmitting) return;
    setReviewSubmitting(true);
    try {
      const res = await fetch(`${API}/reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          participant_code: afroboostProfile?.code || '',
          participant_name: afroboostProfile?.name || leadData?.firstName || 'Abonné',
          text: reviewText.trim(),
          rating: reviewRating,
          profile_photo: profilePhoto || '',
          coach_id: sessionData?.coach_id || 'contact.artboost@gmail.com',
          session_id: reviewSessionId
        })
      });
      if (res.ok) {
        setReviewSubmitted(true);
        setShowReviewForm(false);
        setReviewRequestVisible(false);
        setReviewText('');
        setReviewRating(5);
        // v88: Persister pour ne plus jamais montrer le formulaire à cet utilisateur
        if (afroboostProfile?.code) {
          localStorage.setItem(`afroboost_review_done_${afroboostProfile.code}`, 'true');
        }
        setMessages(prev => [...prev, {
          id: `review_confirm_${Date.now()}`,
          type: 'bot',
          text: '✅ Merci pour ton avis ! Il est maintenant visible sur la page Afroboost 💜',
          timestamp: new Date().toISOString()
        }]);
        console.log('[V88] Avis soumis avec succès');
      } else {
        const err = await res.json().catch(() => ({}));
        const isDuplicate = err.detail && err.detail.includes('déjà');
        if (isDuplicate) {
          // v88: Si déjà publié, masquer le formulaire définitivement
          setReviewSubmitted(true);
          setShowReviewForm(false);
          setReviewRequestVisible(false);
          if (afroboostProfile?.code) {
            localStorage.setItem(`afroboost_review_done_${afroboostProfile.code}`, 'true');
          }
        }
        setMessages(prev => [...prev, {
          id: `review_error_${Date.now()}`,
          type: 'bot',
          text: isDuplicate
            ? '⭐ Tu as déjà laissé un avis — merci pour ton retour !'
            : `⚠️ Erreur lors de l'envoi (${res.status}). Réessaie dans quelques secondes.`,
          timestamp: new Date().toISOString()
        }]);
      }
    } catch (e) {
      console.error('[V88] Erreur soumission avis:', e);
      setMessages(prev => [...prev, {
        id: `review_error_${Date.now()}`,
        type: 'bot',
        text: '⚠️ Problème de connexion. Vérifie ta connexion internet et réessaie.',
        timestamp: new Date().toISOString()
      }]);
    }
    setReviewSubmitting(false);
  };

  // Envoyer un message au chat avec contexte de session
  const handleDeleteMessage = async (messageId) => {
    try {
      await axios.put(`${API}/chat/messages/${messageId}/delete`);
      // Remove from local state or mark as deleted
      setMessages(prev => prev.map(m => m.id === messageId ? {...m, is_deleted: true, text: 'Message supprimé'} : m));
      setGroupMessages(prev => prev.map(m => m.id === messageId ? {...m, is_deleted: true, text: 'Message supprimé'} : m));
    } catch (err) {
      console.error('Delete message error:', err);
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage = inputMessage.trim();
    setInputMessage('');
    // Ajouter le senderId + un ID temporaire pour identifier les messages de l'utilisateur actuel
    const tempUserMsgId = `temp_user_${Date.now()}`;

    // V108.5: Déterminer la cible (groupe ou privé) — détection robuste
    const isGroupMode = !!(selectedGroup && selectedGroup.session_id && (chatMode === 'group' || selectedGroup.id));
    const targetMessages = isGroupMode ? setGroupMessages : setMessages;

    // V108.5: Log systématique pour debug (toujours, pas seulement en mode groupe)
    console.log('[V108.5] handleSendMessage:', {
      chatMode, isGroupMode,
      selectedGroup: selectedGroup?.name || null,
      session_id: selectedGroup?.session_id || null,
      participantId: participantId || 'NULL!',
      hasSessionData: !!sessionData,
      message: userMessage.substring(0, 20)
    });

    // V108.5: Si mode groupe mais participantId manquant, tenter récupération
    let effectiveParticipantId = participantId;
    if (isGroupMode && !effectiveParticipantId) {
      console.warn('[V108.5] participantId NULL en mode groupe — tentative récupération...');
      try {
        const savedIdentity = localStorage.getItem('afroboost_identity');
        const savedClient = localStorage.getItem('af_chat_client');
        if (savedIdentity || savedClient) {
          const data = JSON.parse(savedIdentity || savedClient);
          effectiveParticipantId = data?.participantId || null;
          console.log('[V108.5] Récupéré participantId depuis localStorage:', effectiveParticipantId);
        }
      } catch (e) { console.error('[V108.5] Erreur récup localStorage:', e); }

      // Si toujours null, tenter smart-entry auto avec le profil
      if (!effectiveParticipantId && afroboostProfile?.email) {
        console.log('[V108.5] Tentative auto-registration via smart-entry...');
        try {
          const regRes = await axios.post(`${API}/chat/smart-entry`, {
            name: afroboostProfile.name || 'Abonné',
            email: afroboostProfile.email,
            whatsapp: afroboostProfile.whatsapp || ''
          });
          if (regRes.data?.participant?.id) {
            effectiveParticipantId = regRes.data.participant.id;
            setParticipantId(effectiveParticipantId);
            // Sauvegarder pour les prochaines fois
            localStorage.setItem('afroboost_identity', JSON.stringify({
              firstName: afroboostProfile.name,
              email: afroboostProfile.email,
              participantId: effectiveParticipantId,
              savedAt: new Date().toISOString()
            }));
            console.log('[V108.5] Auto-registration OK! participantId:', effectiveParticipantId);
          }
        } catch (regErr) {
          console.error('[V108.5] Auto-registration FAILED:', regErr);
        }
      }

      if (!effectiveParticipantId) {
        console.error('[V108.5] IMPOSSIBLE de récupérer participantId!');
        targetMessages(prev => [...prev, {
          id: `err_nopid_${Date.now()}`,
          type: 'ai',
          text: "Erreur: votre session n'est pas initialisée. Essayez de recharger la page ou de vous reconnecter."
        }]);
        setIsLoading(false);
        return;
      }
    }

    targetMessages(prev => [...prev, { id: tempUserMsgId, type: 'user', text: userMessage, senderId: participantId }]);
    setLastMessageCount(prev => prev + 1);
    setMessageCount(prev => prev + 1);
    setIsLoading(true);

    try {
      // V108.5: Si mode groupe avec un groupe sélectionné, envoyer au session du groupe
      if (isGroupMode && effectiveParticipantId) {
        console.log('[V108.5] Envoi message groupe:', { session_id: selectedGroup.session_id, participant_id: effectiveParticipantId, group_name: selectedGroup.name });
        try {
          const response = await axios.post(`${API}/chat/ai-response`, {
            session_id: selectedGroup.session_id,
            participant_id: effectiveParticipantId,
            message: userMessage
          });

          console.log('[V108.3] Réponse groupe:', response.data);

          // Mettre à jour l'ID temporaire
          if (response.data.user_message_id) {
            targetMessages(prev => prev.map(m =>
              m.id === tempUserMsgId ? { ...m, id: response.data.user_message_id } : m
            ));
          }

          if (response.data.response) {
            playSoundIfEnabled('message');
            targetMessages(prev => [...prev, {
              id: response.data.ai_message_id || `ai_${Date.now()}`,
              type: 'ai',
              text: response.data.response
            }]);
          } else if (!response.data.ai_active) {
            targetMessages(prev => [...prev, {
              id: `wait_${Date.now()}`,
              type: 'ai',
              text: "Message envoyé au groupe ! Le coach et les autres membres le verront."
            }]);
          }
        } catch (groupErr) {
          console.error('[V108.3] ERREUR envoi groupe:', groupErr?.response?.status, groupErr?.response?.data, groupErr);
          // V108.3: Afficher l'erreur dans les messages du GROUPE (pas privé)
          targetMessages(prev => prev.map(m =>
            m.id === tempUserMsgId
              ? { ...m, text: `${userMessage} (erreur envoi)`, error: true }
              : m
          ));
          targetMessages(prev => [...prev, {
            id: `grp_error_${Date.now()}`,
            type: 'ai',
            text: `Erreur d'envoi: ${groupErr?.response?.data?.detail || 'Vérifie ta connexion et réessaie.'}`,
          }]);
        }

        setIsLoading(false);
        return;
      }

      // Si on a une session active, utiliser l'API améliorée
      if (sessionData && participantId) {
        // Transmettre le link_token de l'URL pour initialiser le bon contexte IA
        const currentLinkToken = getLinkTokenFromUrl();
        const response = await axios.post(`${API}/chat/ai-response`, {
          session_id: sessionData.id,
          participant_id: participantId,
          message: userMessage,
          link_token: currentLinkToken || undefined
        });
        
        // v16.1: Mettre à jour l'ID temporaire du message user avec le vrai ID du serveur
        if (response.data.user_message_id) {
          setMessages(prev => prev.map(m =>
            m.id === tempUserMsgId ? { ...m, id: response.data.user_message_id } : m
          ));
        }

        if (response.data.response) {
          // Jouer un son pour la réponse
          playSoundIfEnabled('message');

          setMessages(prev => [...prev, {
            id: response.data.ai_message_id || `ai_${Date.now()}`,
            type: 'ai',
            text: response.data.response
          }]);
          setLastMessageCount(prev => prev + 1);
        } else if (!response.data.ai_active) {
          // IA désactivée - message en attente
          setMessages(prev => [...prev, {
            id: response.data.user_message_id ? `wait_${response.data.user_message_id}` : `wait_${Date.now()}`,
            type: 'ai',
            text: isCommunityMode
              ? "Message envoyé au groupe ! Les autres participants verront votre message."
              : "Message reçu ! Le coach vous répondra bientôt. 💬"
          }]);
        }
      } else {
        // Fallback: ancien système - maintenant avec CRM auto-save
        const response = await axios.post(`${API}/chat`, {
          message: userMessage,
          firstName: leadData.firstName,
          email: leadData.email || '',       // Pour CRM auto-save
          whatsapp: leadData.whatsapp || '', // Pour CRM auto-save
          source: 'chat_ia',                 // Source pour tracking
          leadId: ''
        });
        
        playSoundIfEnabled('message');
        
        setMessages(prev => [...prev, {
          id: `fallback_${Date.now()}`,
          type: 'ai',
          text: response.data.response || "Désolé, je n'ai pas pu traiter votre message."
        }]);
      }

      // === PROMPT NOTIFICATIONS PUSH après le premier message ===
      if (messageCount === 1 && participantId && !pushEnabled) {
        // Attendre un peu avant de demander (non intrusif)
        setTimeout(async () => {
          const result = await promptForNotifications(participantId);
          if (result.subscribed) {
            setPushEnabled(true);
            console.log('Push notifications enabled');
          }
        }, 2000);
      }

    } catch (err) {
      console.error('Chat error:', err);
      setMessages(prev => [...prev, {
        id: `error_${Date.now()}`,
        type: 'ai',
        text: "Désolé, une erreur s'est produite. Veuillez réessayer."
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  // === SUPPRIMER L'HISTORIQUE - ROUTE SÉCURISÉE ADMIN ===
  const handleDeleteHistory = async () => {
    if (!sessionData?.id) return;
    
    const confirm = window.confirm('Êtes-vous sûr de vouloir supprimer votre historique de conversation ?');
    if (!confirm) return;
    
    try {
      // Utiliser la route sécurisée qui vérifie l'email
      const response = await axios.post(`${API}/admin/delete-history`, {
        session_id: sessionData.id,
        email: leadData.email || ''
      });
      
      if (response.data.success) {
        // Vider l'affichage local
        setMessages([{
          type: 'ai',
          text: '🗑️ Historique supprimé. Comment puis-je vous aider ?'
        }]);
        setLastMessageCount(1);
        setShowMenu(false);
        console.log('[ADMIN] Historique supprimé:', response.data.deleted_count, 'messages');
      }
      
    } catch (err) {
      console.error('[SECURITY] Delete history error:', err.response?.data?.detail || err.message);
      if (err.response?.status === 403) {
        alert('⛔ Accès refusé. Seul le coach peut supprimer l\'historique.');
      } else {
        alert('Erreur lors de la suppression de l\'historique');
      }
    }
  };

  // Réinitialiser le widget
  const handleClose = () => {
    setIsOpen(false);
    setShowMenu(false);
  };

  // === CHANGER D'IDENTITÉ - ROUTE SÉCURISÉE ADMIN ===
  const handleChangeIdentity = async () => {
    try {
      // Vérifier côté serveur (optionnel mais recommandé)
      await axios.post(`${API}/admin/change-identity`, {
        participant_id: participantId,
        email: leadData.email || ''
      });
      
      // Réinitialiser localement (y compris le profil abonné)
      localStorage.removeItem(CHAT_CLIENT_KEY);
      localStorage.removeItem(CHAT_SESSION_KEY);
      localStorage.removeItem(AFROBOOST_IDENTITY_KEY);
      localStorage.removeItem(AFROBOOST_PROFILE_KEY);
      localStorage.removeItem('subscriber_data');
      setLeadData({ firstName: '', whatsapp: '', email: '' });
      setIsReturningClient(false);
      setStep('form');
      setMessages([]);
      setSessionData(null);
      setParticipantId(null);
      setShowMenu(false);
      setLastMessageCount(0);
      setIsCoachMode(false);
      setAfroboostProfile(null);
      setSubscriberData(null);
      setIsFullscreen(false);
      setShowSubscriberForm(false);
      setSubscriberFormData({ name: '', whatsapp: '', email: '', code: '' });
      console.log('[ADMIN] Identité et profil abonné réinitialisés');
      
    } catch (err) {
      console.error('[SECURITY] Change identity error:', err.response?.data?.detail || err.message);
      if (err.response?.status === 403) {
        alert('⛔ Accès refusé. Seul le coach peut changer l\'identité.');
      } else {
        // En cas d'erreur réseau, on fait quand même le reset local (coach mode)
        localStorage.removeItem(CHAT_CLIENT_KEY);
        localStorage.removeItem(CHAT_SESSION_KEY);
        localStorage.removeItem(AFROBOOST_IDENTITY_KEY);
        localStorage.removeItem(AFROBOOST_PROFILE_KEY);
        localStorage.removeItem('subscriber_data');
        setLeadData({ firstName: '', whatsapp: '', email: '' });
        setStep('form');
        setMessages([]);
        setSessionData(null);
        setParticipantId(null);
        setShowMenu(false);
        setIsCoachMode(false);
        setAfroboostProfile(null);
        setSubscriberData(null);
        setIsFullscreen(false);
      }
    }
  };

  // === FONCTION POUR ÉMETTRE L'ÉVÉNEMENT TYPING ===
  const emitTyping = (isTyping) => {
    if (!socketRef.current || !sessionData?.id) return;
    
    const now = Date.now();
    // Éviter le spam (max 1 événement par seconde)
    if (isTyping && now - lastTypingEmitRef.current < 1000) return;
    lastTypingEmitRef.current = now;
    
    const eventName = isTyping ? 'typing_start' : 'typing_stop';
    socketRef.current.emit(eventName, {
      session_id: sessionData.id,
      user_name: isCoachMode ? 'Coach Bassi' : leadData.firstName || 'Utilisateur',
      user_type: isCoachMode ? 'coach' : 'user'
    });
  };

  // === FONCTION POUR ÉMETTRE L'ÉVÉNEMENT TYPING DANS LES DM ===
  const emitDmTyping = (isTyping) => {
    if (!socketRef.current || !activePrivateChat?.id) return;
    
    const now = Date.now();
    // Éviter le spam (max 1 événement par seconde)
    if (isTyping && now - lastDmTypingEmitRef.current < 1000) return;
    lastDmTypingEmitRef.current = now;
    
    try {
      const eventName = isTyping ? 'dm_typing_start' : 'dm_typing_stop';
      socketRef.current.emit(eventName, {
        conversation_id: activePrivateChat.id,
        user_id: participantId,
        user_name: afroboostProfile?.name || leadData?.firstName || 'Utilisateur'
      });
    } catch (e) {
      // NULL-SAFE: Ne pas bloquer le chat si l'événement échoue
      console.warn('[DM-TYPING] Erreur émission:', e.message);
    }
  };

  // === FONCTION POUR ÉMETTRE LA MISE À JOUR D'AVATAR ===
  const emitAvatarUpdate = (photoUrl) => {
    if (!socketRef.current || !participantId) return;
    
    try {
      socketRef.current.emit('avatar_updated', {
        user_id: participantId,
        user_name: afroboostProfile?.name || leadData?.firstName || 'Utilisateur',
        photo_url: photoUrl
      });
      console.log('[AVATAR] 📷 Diffusion mise à jour avatar');
    } catch (e) {
      console.warn('[AVATAR] Erreur diffusion avatar:', e.message);
    }
  };

  // Handler pour l'input avec émission typing
  const handleInputChangeWithTyping = (e) => {
    const value = e.target.value;
    setInputMessage(value);
    
    // Émettre l'événement typing
    if (value.length > 0) {
      emitTyping(true);
    }
  };

  // Arrêter l'indicateur typing quand on perd le focus ou envoie
  const handleInputBlur = () => {
    emitTyping(false);
  };

  return (
    <>
      {/* Style pour les liens dans les messages et responsive mobile */}
      <style>{`
        .chat-link {
          color: #a78bfa;
          text-decoration: underline;
          word-break: break-all;
        }
        .chat-link:hover {
          color: #c4b5fd;
        }
        
        /* Emoji inline dans les messages */
        .chat-emoji {
          width: 20px;
          height: 20px;
          vertical-align: middle;
          display: inline-block;
          margin: 0 2px;
        }
        
        /* Animation pastille notification MP */
        @keyframes pulse {
          0%, 100% {
            transform: scale(1);
            box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
          }
          50% {
            transform: scale(1.1);
            box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);
          }
        }
        
        /* Animation points typing DM (minimaliste) */
        @keyframes dmTypingDot {
          0%, 80%, 100% {
            opacity: 0.3;
            transform: scale(0.8);
          }
          40% {
            opacity: 1;
            transform: scale(1);
          }
        }

        /* v16.4: Animation slide-in fluide pour les messages */
        @keyframes afroMsgSlideIn {
          from {
            opacity: 0;
            transform: translateY(12px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }

        /* Chat widget responsive - plus grand sur mobile */
        @media (max-width: 640px) {
          .chat-widget-window {
            bottom: 0 !important;
            right: 0 !important;
            left: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
            height: 85vh !important;
            max-height: 85vh !important;
            border-radius: 16px 16px 0 0 !important;
          }
          .chat-widget-button {
            bottom: 100px !important; /* Décalé vers le haut pour ne pas gêner la barre d'input */
            right: 16px !important;
            width: 60px !important;
            height: 60px !important;
          }
        }
        
        @media (min-width: 641px) and (max-width: 1024px) {
          .chat-widget-window {
            width: 400px !important;
            height: 70vh !important;
            max-height: 70vh !important;
          }
        }
      `}</style>

      {/* === MESSAGE iOS PWA (ajout ecran d'accueil) === */}
      {showiOSPrompt && (
        <div
          style={{
            position: 'fixed',
            bottom: '170px',
            right: '20px',
            maxWidth: '280px',
            background: 'linear-gradient(135deg, #1a1a2e, #16213e)',
            borderRadius: '12px',
            padding: '12px 16px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            zIndex: 60,
            border: '1px solid rgba(255,255,255,0.1)',
            animation: 'fadeIn 0.3s ease-out'
          }}
          data-testid="ios-pwa-prompt"
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
            {/* Icone Share SVG minimaliste */}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#a78bfa" strokeWidth="2" style={{ flexShrink: 0, marginTop: '2px' }}>
              <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/>
              <polyline points="16 6 12 2 8 6"/>
              <line x1="12" y1="2" x2="12" y2="15"/>
            </svg>
            <div>
              <div style={{ fontSize: '12px', color: '#fff', lineHeight: '1.4' }}>
                Pour recevoir les alertes, ajoutez cette application a votre ecran d'accueil.
              </div>
              <div style={{ fontSize: '10px', color: '#888', marginTop: '4px' }}>
                Partager &gt; Sur l'ecran d'accueil
              </div>
            </div>
            {/* Bouton fermer */}
            <button
              onClick={() => setShowiOSPrompt(false)}
              style={{
                background: 'none',
                border: 'none',
                color: '#666',
                cursor: 'pointer',
                padding: '0',
                marginLeft: 'auto',
                flexShrink: 0
              }}
              aria-label="Fermer"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* v9.4.2: Bouton flottant Chat Afroboost (violet) - Positionné à DROITE, au-dessus de la barre */}
      {!isOpen && (
        <button
          onClick={handleOpenWidget}
          className="chat-widget-button fixed z-50 shadow-lg transition-all duration-300 hover:scale-110"
          style={{
            bottom: '100px', /* Décalé vers le haut pour ne pas gêner le bouton Envoyer */
            right: '20px',
            left: 'auto', /* Force le positionnement à droite */
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: '#D91CD2', /* v9.4.2: Violet Afroboost au lieu de vert WhatsApp */
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 15px rgba(217, 28, 210, 0.4)', /* Ombre violette */
            position: 'fixed', /* Assurer position fixe */
            zIndex: 50 /* Inférieur à la barre de saisie */
          }}
          data-testid="chat-widget-button"
        >
          <ChatBubbleIcon /> {/* v9.4.2: Icône bulle de chat */}
          
          {/* Badge MP non lus (pastille rouge) */}
          {unreadPrivateCount > 0 && (
            <span 
              style={{
                position: 'absolute',
                top: '-6px',
                right: '-6px',
                minWidth: '22px',
                height: '22px',
                borderRadius: '11px',
                background: '#ef4444',
                border: '2px solid #0a0a0a',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '11px',
                fontWeight: 'bold',
                color: '#fff',
                padding: '0 4px',
                animation: 'pulse 1.5s infinite'
              }}
              data-testid="unread-mp-badge"
            >
              {unreadPrivateCount > 99 ? '99+' : unreadPrivateCount}
            </span>
          )}
          
          {/* Badge si client reconnu (affiché seulement si pas de MP non lus) */}
          {isReturningClient && unreadPrivateCount === 0 && (
            <span 
              style={{
                position: 'absolute',
                top: '-4px',
                right: '-4px',
                width: '18px',
                height: '18px',
                borderRadius: '50%',
                background: '#d91cd2',
                border: '2px solid #0a0a0a',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '10px',
                color: '#fff'
              }}
            >
              ✓
            </span>
          )}
        </button>
      )}

      {/* Fenêtre de chat - Responsive avec dvh pour compatibilité clavier mobile */}
      {isOpen && (
        <div
          ref={chatContainerRef}
          className="chat-widget-window fixed z-50 shadow-2xl"
          style={{
            bottom: isFullscreen ? '0' : '80px',
            right: isFullscreen ? '0' : '20px',
            left: isFullscreen ? '0' : 'auto',
            top: isFullscreen ? '0' : 'auto',
            width: isFullscreen ? '100vw' : '380px',
            maxWidth: isFullscreen ? '100vw' : 'calc(100vw - 40px)',
            height: isFullscreen ? '100dvh' : '70vh', /* dvh pour compatibilité clavier mobile */
            maxHeight: isFullscreen ? '100dvh' : '85vh',
            minHeight: isFullscreen ? '100dvh' : '400px',
            borderRadius: isFullscreen ? '0' : '16px',
            background: '#0a0a0a',
            border: isFullscreen ? 'none' : '1px solid rgba(217, 28, 210, 0.3)',
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden'
          }}
          data-testid="chat-widget-window"
        >
          {/* Header v9.4.2: Gradient violet Afroboost */}
          <div 
            style={{
              background: isCommunityMode 
                ? 'linear-gradient(135deg, #8b5cf6, #6366f1)' 
                : 'linear-gradient(135deg, #D91CD2, #9333ea)', /* v9.4.2: Violet Afroboost */
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0
            }}
          >
            <div className="flex items-center gap-3">
              <div 
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '50%',
                  background: 'rgba(255,255,255,0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                {isCommunityMode ? <GroupIcon /> : <ChatBubbleIcon />} {/* v9.4.2 */}
              </div>
              <div>
                <div className="text-white font-semibold text-sm">
                  {isCommunityMode ? 'Communauté Afroboost' : 'Afroboost'}
                </div>
                <div className="text-white text-xs" style={{ opacity: 0.8 }}>
                  {/* Indicateur de synchronisation */}
                  {isSyncing ? (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ 
                        width: '8px', 
                        height: '8px', 
                        borderRadius: '50%', 
                        background: '#fbbf24',
                        animation: 'pulse 1s infinite'
                      }}></span>
                      Synchronisation...
                    </span>
                  ) : (
                    /* v14.5: Afficher badge "Session Active : [Nom du Lien]" si disponible */
                    sessionData?.title ? (
                      <div className="flex flex-col">
                        <span className="flex items-center gap-1">
                          <span style={{ fontSize: '12px' }}>🤖</span>
                          <span className="font-bold" style={{ color: '#D91CD2' }}>{sessionData.title}</span>
                        </span>
                        <span className="text-xs opacity-70" style={{ fontSize: '9px' }}>
                          ✓ Session Active
                        </span>
                      </div>
                    ) :
                    /* Afficher le statut abonné si profil validé + cours restants */
                    afroboostProfile?.code && step === 'chat'
                      ? `Abonne - ${afroboostProfile.name}${reservationEligibility?.remaining !== undefined && reservationEligibility?.remaining !== 'illimite' ? ` (${reservationEligibility.remaining} cours)` : ''}`
                      : isReturningClient && step === 'chat' 
                        ? leadData.firstName 
                        : isCommunityMode 
                          ? 'Chat Groupe'
                          : sessionData?.is_ai_active === false 
                            ? 'Mode Coach'
                            : 'Coach Bassi'
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {/* Bouton Plein Écran - TOUJOURS visible en mode abonné */}
              {step === 'chat' && (
                <button
                  onClick={toggleFullscreen}
                  title={isFullscreen ? "Quitter le plein écran" : "Mode plein écran"}
                  style={{
                    background: afroboostProfile?.code 
                      ? 'linear-gradient(135deg, rgba(147, 51, 234, 0.4), rgba(99, 102, 241, 0.4))'
                      : 'rgba(255,255,255,0.2)',
                    border: afroboostProfile?.code ? '1px solid rgba(147, 51, 234, 0.5)' : 'none',
                    borderRadius: '8px',
                    width: '32px',
                    height: '32px',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: '#fff'
                  }}
                  data-testid="fullscreen-btn"
                >
                  {isFullscreen ? <ExitFullscreenIcon /> : <FullscreenIcon />}
                </button>
              )}
              
              {/* === ICÔNES MINIMALISTES (Partage + Menu) === */}
              {step === 'chat' && (
                <div className="relative afro-share-menu" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  {/* Icône Partager (filaire fine) */}
                  <button
                    onClick={handleShareLink}
                    title={linkCopied ? "Lien copié !" : "Partager"}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: '4px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      opacity: linkCopied ? 1 : 0.6,
                      transition: 'opacity 0.2s ease'
                    }}
                    data-testid="share-link-btn"
                  >
                    {linkCopied ? (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="1.5">
                        <polyline points="20 6 9 17 4 12"></polyline>
                      </svg>
                    ) : (
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.5">
                        <circle cx="18" cy="5" r="3"></circle>
                        <circle cx="6" cy="12" r="3"></circle>
                        <circle cx="18" cy="19" r="3"></circle>
                        <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                        <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                      </svg>
                    )}
                  </button>
                  
                  {/* Icône Menu (⋮) filaire fine */}
                  <button
                    onClick={() => setShowUserMenu(!showUserMenu)}
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: '4px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      opacity: 0.6,
                      transition: 'opacity 0.2s ease'
                    }}
                    data-testid="user-menu-btn"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="#fff">
                      <circle cx="12" cy="5" r="1.5"></circle>
                      <circle cx="12" cy="12" r="1.5"></circle>
                      <circle cx="12" cy="19" r="1.5"></circle>
                    </svg>
                  </button>
                  
                  {/* Menu déroulant utilisateur */}
                  {showUserMenu && (
                    <div
                      style={{
                        position: 'absolute',
                        top: '35px',
                        right: '0',
                        background: '#1a1a1a',
                        borderRadius: '8px',
                        border: 'none',
                        overflow: 'hidden',
                        minWidth: '180px',
                        zIndex: 100,
                        boxShadow: '0 4px 24px rgba(0,0,0,0.6)',
                        borderRadius: '12px'
                      }}
                    >
                      {/* Upload Photo de profil */}
                      <label
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          padding: '10px 14px',
                          color: '#fff',
                          fontSize: '12px',
                          cursor: 'pointer'
                        }}
                        className="hover:bg-white/10"
                      >
                        <input
                          type="file"
                          accept="image/*"
                          onChange={(e) => {
                            handlePhotoUpload(e);
                            setShowUserMenu(false);
                          }}
                          style={{ display: 'none' }}
                        />
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                          <circle cx="8.5" cy="8.5" r="1.5"></circle>
                          <polyline points="21 15 16 10 5 21"></polyline>
                        </svg>
                        {uploadingPhoto ? 'Upload...' : 'Photo de profil'}
                        {profilePhoto && (
                          <img
                            id="profile-avatar-zoom"
                            src={profilePhoto}
                            alt=""
                            onClick={(e) => { e.stopPropagation(); e.preventDefault(); setZoomedChatPhoto(profilePhoto); }}
                            style={{ width: '20px', height: '20px', borderRadius: '50%', marginLeft: 'auto', cursor: 'pointer', padding: '10px', margin: '-10px', marginLeft: 'auto', boxSizing: 'content-box' }}
                          />
                        )}
                      </label>

                      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', margin: '2px 0' }} />

                      {/* v84: Dashboard uniquement en Mode Coach, sinon Devenir Partenaire pour tous (abonnés + visiteurs) */}
                      {isCoachMode ? (
                        <button
                          onClick={() => {
                            window.location.hash = '#partner-dashboard';
                            setShowUserMenu(false);
                          }}
                          style={{
                            width: '100%',
                            padding: '10px 14px',
                            textAlign: 'left',
                            fontSize: '12px',
                            color: '#D91CD2',
                            background: 'linear-gradient(135deg, rgba(217, 28, 210, 0.15), rgba(139, 92, 246, 0.15))',
                            border: 'none',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            fontWeight: '600'
                          }}
                          className="hover:bg-white/10"
                          data-testid="access-dashboard-btn"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="3" y="3" width="7" height="7"></rect>
                            <rect x="14" y="3" width="7" height="7"></rect>
                            <rect x="14" y="14" width="7" height="7"></rect>
                            <rect x="3" y="14" width="7" height="7"></rect>
                          </svg>
                          Mon Dashboard
                        </button>
                      ) : (
                        <button
                          onClick={() => {
                            window.dispatchEvent(new CustomEvent('openBecomeCoach'));
                            setShowUserMenu(false);
                          }}
                          style={{
                            width: '100%',
                            padding: '10px 14px',
                            textAlign: 'left',
                            fontSize: '12px',
                            color: '#D91CD2',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            fontWeight: '600'
                          }}
                          className="hover:bg-white/10"
                          data-testid="become-partner-user-menu-btn"
                        >
                          <span>✨</span>
                          Devenir Partenaire
                        </button>
                      )}
                      
                      {/* Mode Visiteur - seulement si abonné */}
                      {afroboostProfile?.code && (
                        <button
                          onClick={() => { handleVisitorMode(); setShowUserMenu(false); }}
                          style={{
                            width: '100%',
                            padding: '10px 14px',
                            textAlign: 'left',
                            fontSize: '12px',
                            color: '#fff',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px'
                          }}
                          className="hover:bg-white/10"
                          data-testid="visitor-mode-btn"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                            <circle cx="12" cy="12" r="3"></circle>
                          </svg>
                          Mode Visiteur
                        </button>
                      )}

                      
                      {/* V160: Date de naissance */}
                      <button
                        onClick={function() { setShowBirthdayModal(true); setShowMenu(false); }}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '8px',
                          width: '100%', padding: '8px 12px',
                          background: 'none', border: 'none', color: '#fff',
                          cursor: 'pointer', fontSize: '13px', textAlign: 'left',
                          borderRadius: '6px'
                        }}
                        onMouseOver={function(e) { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; }}
                        onMouseOut={function(e) { e.currentTarget.style.background = 'none'; }}
                      >
                        <span role="img" aria-label="birthday">&#x1F382;</span> Date de naissance
                      </button>

<div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', margin: '2px 0' }} />
                      
                      {/* Toggle Son (icône haut-parleur filaire) */}
                      <button
                        onClick={() => { toggleSound(); setShowUserMenu(false); }}
                        style={{
                          width: '100%',
                          padding: '10px 14px',
                          textAlign: 'left',
                          fontSize: '12px',
                          color: '#fff',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px'
                        }}
                        className="hover:bg-white/10"
                        data-testid="toggle-sound-btn"
                      >
                        {soundEnabled ? (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                            <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                            <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
                          </svg>
                        ) : (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                            <line x1="23" y1="9" x2="17" y2="15"></line>
                            <line x1="17" y1="9" x2="23" y2="15"></line>
                          </svg>
                        )}
                        {soundEnabled ? 'Son activé' : 'Son désactivé'}
                      </button>
                      
                      {/* Silence Auto (22h-08h) - Mode Ne Pas Déranger */}
                      <button
                        onClick={() => { toggleSilenceAuto(); setShowUserMenu(false); }}
                        style={{
                          width: '100%',
                          padding: '10px 14px',
                          textAlign: 'left',
                          fontSize: '12px',
                          color: silenceAutoEnabled ? '#FBBF24' : '#fff',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px'
                        }}
                        className="hover:bg-white/10"
                        data-testid="toggle-silence-auto-btn"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
                        </svg>
                        {silenceAutoEnabled ? 'Silence Auto (actif)' : `Silence Auto (${getSilenceHoursLabel()})`}
                      </button>

                      {/* V120: Toggle Notifications Push */}
                      {isPushSupported() && (
                        <button
                          onClick={async () => { await togglePush(); setShowUserMenu(false); }}
                          style={{
                            width: '100%',
                            padding: '10px 14px',
                            textAlign: 'left',
                            fontSize: '12px',
                            color: pushEnabled ? '#22c55e' : '#fff',
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px'
                          }}
                          className="hover:bg-white/10"
                          data-testid="toggle-push-btn"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
                            <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
                          </svg>
                          {pushEnabled ? 'Notifications activées' : 'Activer les notifications'}
                        </button>
                      )}

                      {/* Rafraîchir */}
                      <button
                        onClick={() => { window.location.reload(); }}
                        style={{
                          width: '100%',
                          padding: '10px 14px',
                          textAlign: 'left',
                          fontSize: '12px',
                          color: 'rgba(255,255,255,0.5)',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px'
                        }}
                        className="hover:bg-white/10"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="23 4 23 10 17 10"></polyline>
                          <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                        </svg>
                        Rafraîchir
                      </button>

                      <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', margin: '2px 0' }} />

                      {/* Bouton Déconnexion */}
                      <button
                        onClick={() => { handleLogout(); }}
                        disabled={isLoggingOut}
                        style={{
                          width: '100%',
                          padding: '10px 14px',
                          textAlign: 'left',
                          fontSize: '12px',
                          color: isLoggingOut ? '#888' : '#ef4444',
                          background: 'none',
                          border: 'none',
                          cursor: isLoggingOut ? 'wait' : 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          opacity: isLoggingOut ? 0.6 : 1
                        }}
                        className="hover:bg-white/10"
                        data-testid="logout-btn"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                          <polyline points="16 17 21 12 16 7"></polyline>
                          <line x1="21" y1="12" x2="9" y2="12"></line>
                        </svg>
                        {isLoggingOut ? 'Deconnexion...' : 'Se deconnecter'}
                      </button>
                    </div>
                  )}
                </div>
              )}
              
              {/* Menu burger - VISIBLE UNIQUEMENT EN MODE CHAT (le panel coach a son propre menu) */}
              {step === 'chat' && isCoachMode && !isVisitorPreview && (
                <div className="relative">
                  <button
                    onClick={() => setShowMenu(!showMenu)}
                    style={{
                      background: 'rgba(255,255,255,0.2)',
                      border: 'none',
                      borderRadius: '8px',
                      width: '32px',
                      height: '32px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      color: '#fff',
                      fontSize: '16px'
                    }}
                    data-testid="chat-menu-btn"
                  >
                    ⋮
                  </button>
                  
                  {/* Menu déroulant - ADMIN ONLY */}
                  {showMenu && (
                    <div
                      style={{
                        position: 'absolute',
                        top: '40px',
                        right: '0',
                        background: '#1a1a1a',
                        borderRadius: '8px',
                        border: '1px solid rgba(255,255,255,0.1)',
                        overflow: 'hidden',
                        minWidth: '180px',
                        zIndex: 100
                      }}
                    >
                      <button
                        onClick={handleDeleteHistory}
                        className="w-full px-4 py-3 text-left text-sm hover:bg-white/10 flex items-center gap-2"
                        style={{ color: '#ef4444', border: 'none', background: 'none' }}
                        data-testid="delete-history-btn"
                      >
                        <TrashIcon /> Supprimer l'historique
                      </button>
                      <button
                        onClick={handleChangeIdentity}
                        className="w-full px-4 py-3 text-left text-sm hover:bg-white/10 flex items-center gap-2"
                        style={{ color: '#fff', border: 'none', background: 'none' }}
                        data-testid="change-identity-btn"
                      >
                        Changer d'identité
                      </button>
                    </div>
                  )}
                </div>
              )}
              
              <button
                onClick={handleClose}
                style={{
                  background: 'rgba(255,255,255,0.2)',
                  border: 'none',
                  borderRadius: '50%',
                  width: '32px',
                  height: '32px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
                data-testid="chat-close-btn"
              >
                <CloseIcon />
              </button>
            </div>
          </div>
          
          {/* Badge Mode Aperçu (Admin) - Sous la barre de navigation */}
          {isVisitorPreview && isCoachMode && (
            <div
              style={{
                height: '2px',
                background: 'linear-gradient(90deg, #9333ea, #ec4899)',
                position: 'relative',
                flexShrink: 0,
                zIndex: 50,
                boxShadow: '0 1px 4px rgba(0, 0, 0, 0.15)'
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  top: '2px',
                  left: '50%',
                  transform: 'translateX(-50%)',
                  background: '#0a0a0a',
                  padding: '2px 8px',
                  borderRadius: '0 0 4px 4px',
                  fontSize: '9px',
                  color: '#9333ea',
                  fontWeight: '500',
                  letterSpacing: '0.5px',
                  textTransform: 'uppercase',
                  boxShadow: '0 1px 3px rgba(0, 0, 0, 0.2)'
                }}
                data-testid="visitor-preview-badge"
              >
                Aperçu
              </span>
            </div>
          )}

          {/* Contenu avec scroll */}
          <div style={{ 
            flex: 1, 
            overflow: 'hidden', 
            display: 'flex', 
            flexDirection: 'column',
            minHeight: 0
          }}>
            
            {/* Formulaire de capture avec scroll */}
            {step === 'form' && (
              <div 
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  padding: '20px',
                  display: 'flex',
                  flexDirection: 'column'
                }}
              >
                {/* === v16.0: TUNNEL D'ONBOARDING (liens personnalisés) === */}
                {showOnboardingTunnel && currentLinkToken ? (
                  <OnboardingTunnel
                    linkToken={currentLinkToken}
                    onComplete={async (participantId, sessionId, clientData) => {
                      console.log('[CHATWIDGET] ✅ Onboarding terminé:', { participantId, sessionId });
                      setShowOnboardingTunnel(false);
                      // Lancer le chat via smart-entry (réutilise le flux existant)
                      try {
                        await handleSmartEntry(clientData, currentLinkToken);
                      } catch (err) {
                        console.error('[CHATWIDGET] Erreur post-onboarding:', err);
                        setMessages([{
                          type: 'ai',
                          text: `Bienvenue ${clientData.firstName} ! 😊 Comment puis-je vous aider ?`
                        }]);
                      }
                    }}
                  />
                ) : showSubscriberForm ? (
                  /* === FORMULAIRE ABONNÉ (4 champs avec code promo) === */
                  <SubscriberForm
                    formData={subscriberFormData}
                    setFormData={setSubscriberFormData}
                    onSubmit={handleSubscriberFormSubmit}
                    onCancel={() => { setShowSubscriberForm(false); setError(''); }}
                    error={error}
                    isLoading={validatingCode}
                  />
                ) : showRecoverForm ? (
                  /* === v11.6: FORMULAIRE RÉCUPÉRATION D'ACCÈS === */
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', minHeight: 'min-content' }}>
                    <div style={{ textAlign: 'center', marginBottom: '8px' }}>
                      <span style={{ fontSize: '28px' }}>🔑</span>
                      <p style={{ color: '#fff', fontSize: '14px', marginTop: '8px', fontWeight: '600' }}>
                        Retrouver mes accès
                      </p>
                      <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', marginTop: '4px' }}>
                        Entrez votre email ou WhatsApp pour récupérer votre code et QR Code
                      </p>
                    </div>

                    {/* Résultat de récupération réussie */}
                    {recoverResult?.success && (
                      <div style={{
                        background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.15), rgba(16, 185, 129, 0.1))',
                        border: '1px solid rgba(34, 197, 94, 0.4)',
                        borderRadius: '12px',
                        padding: '16px',
                        textAlign: 'center'
                      }}>
                        <span style={{ fontSize: '24px' }}>✅</span>
                        <p style={{ color: '#22c55e', fontWeight: '700', fontSize: '14px', marginTop: '8px' }}>
                          Accès retrouvé !
                        </p>

                        {/* Code abonné */}
                        <div style={{
                          background: 'rgba(147, 51, 234, 0.2)',
                          border: '1px solid rgba(147, 51, 234, 0.4)',
                          borderRadius: '8px',
                          padding: '12px',
                          marginTop: '12px'
                        }}>
                          <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '1px' }}>
                            Votre code abonné
                          </p>
                          <p style={{ color: '#D91CD2', fontSize: '22px', fontWeight: '800', letterSpacing: '3px', marginTop: '4px' }}>
                            {recoverResult.code}
                          </p>
                          {recoverResult.offer_name && (
                            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', marginTop: '4px' }}>
                              {recoverResult.offer_name} — {recoverResult.sessions_remaining ?? '∞'} séance(s) restante(s)
                            </p>
                          )}
                        </div>

                        {/* QR Code */}
                        {recoverResult.qr_code_url && (
                          <div style={{ marginTop: '12px' }}>
                            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '11px', marginBottom: '8px' }}>
                              Votre QR Code d'accès :
                            </p>
                            <img
                              src={recoverResult.qr_code_url}
                              alt="QR Code abonné"
                              style={{
                                width: '180px',
                                height: '180px',
                                borderRadius: '12px',
                                background: '#fff',
                                padding: '8px',
                                margin: '0 auto',
                                display: 'block'
                              }}
                            />
                            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '10px', marginTop: '8px' }}>
                              Faites une capture d'écran pour le garder sur votre téléphone
                            </p>
                          </div>
                        )}

                        {recoverResult.email_sent && (
                          <p style={{ color: '#22c55e', fontSize: '11px', marginTop: '8px' }}>
                            Un email de rappel a aussi été envoyé
                          </p>
                        )}

                        {/* Bouton pour s'identifier directement */}
                        <button
                          type="button"
                          onClick={() => {
                            setSubscriberFormData(prev => ({ ...prev, code: recoverResult.code }));
                            setShowRecoverForm(false);
                            setShowSubscriberForm(true);
                            setRecoverResult(null);
                          }}
                          style={{
                            width: '100%',
                            padding: '12px',
                            marginTop: '12px',
                            borderRadius: '8px',
                            background: 'linear-gradient(135deg, #9333ea, #6366f1)',
                            color: '#fff',
                            border: 'none',
                            cursor: 'pointer',
                            fontWeight: '600',
                            fontSize: '13px'
                          }}
                        >
                          S'identifier avec ce code
                        </button>
                      </div>
                    )}

                    {/* Erreur de récupération */}
                    {recoverError && (
                      <div style={{
                        background: 'rgba(239, 68, 68, 0.2)',
                        color: '#ef4444',
                        padding: '8px 12px',
                        borderRadius: '8px',
                        fontSize: '12px'
                      }}>
                        {recoverError}
                      </div>
                    )}

                    {/* Formulaire de récupération */}
                    {!recoverResult?.success && (
                      <form onSubmit={handleRecoverAccess} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        <div>
                          <label style={{ display: 'block', color: '#fff', fontSize: '12px', marginBottom: '4px', opacity: 0.7 }}>Email</label>
                          <input
                            type="email"
                            value={recoverData.email}
                            onChange={(e) => setRecoverData(prev => ({ ...prev, email: e.target.value }))}
                            placeholder="votre@email.com"
                            style={{
                              width: '100%',
                              padding: '10px 12px',
                              borderRadius: '8px',
                              background: 'rgba(255,255,255,0.1)',
                              border: '1px solid rgba(255,255,255,0.2)',
                              color: '#fff',
                              fontSize: '14px',
                              outline: 'none',
                              boxSizing: 'border-box'
                            }}
                            data-testid="recover-email"
                          />
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', margin: '0' }}>
                          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.2)' }} />
                          <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px' }}>ou</span>
                          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.2)' }} />
                        </div>

                        <div>
                          <label style={{ display: 'block', color: '#fff', fontSize: '12px', marginBottom: '4px', opacity: 0.7 }}>Numéro WhatsApp</label>
                          <input
                            type="tel"
                            value={recoverData.whatsapp}
                            onChange={(e) => setRecoverData(prev => ({ ...prev, whatsapp: e.target.value }))}
                            placeholder="+41 79 123 45 67"
                            style={{
                              width: '100%',
                              padding: '10px 12px',
                              borderRadius: '8px',
                              background: 'rgba(255,255,255,0.1)',
                              border: '1px solid rgba(255,255,255,0.2)',
                              color: '#fff',
                              fontSize: '14px',
                              outline: 'none',
                              boxSizing: 'border-box'
                            }}
                            data-testid="recover-whatsapp"
                          />
                        </div>

                        <button
                          type="submit"
                          disabled={recoverLoading}
                          style={{
                            width: '100%',
                            padding: '12px',
                            borderRadius: '8px',
                            background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                            color: '#fff',
                            border: 'none',
                            cursor: recoverLoading ? 'wait' : 'pointer',
                            fontWeight: '600',
                            fontSize: '14px',
                            opacity: recoverLoading ? 0.7 : 1,
                            marginTop: '4px'
                          }}
                          data-testid="recover-submit"
                        >
                          {recoverLoading ? '⏳ Recherche...' : '🔍 Retrouver mes accès'}
                        </button>
                      </form>
                    )}

                    {/* Bouton retour */}
                    <button
                      type="button"
                      onClick={() => { setShowRecoverForm(false); setRecoverError(''); setRecoverResult(null); }}
                      style={{
                        background: 'none',
                        color: 'rgba(255,255,255,0.6)',
                        border: 'none',
                        cursor: 'pointer',
                        textDecoration: 'underline',
                        fontSize: '12px',
                        padding: '4px'
                      }}
                      data-testid="recover-back"
                    >
                      ← Retour
                    </button>
                  </div>
                ) : (
                  /* === FORMULAIRE VISITEUR CLASSIQUE (3 champs) === */
                  <form 
                    onSubmit={handleSubmitLead}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                      minHeight: 'min-content'
                    }}
                  >
                    <p className="text-white text-sm text-center mb-2">
                      Avant de commencer, présentez-vous !
                    </p>
                    
                    {error && (
                      <div style={{ 
                        background: 'rgba(239, 68, 68, 0.2)', 
                        color: '#ef4444', 
                        padding: '8px 12px', 
                        borderRadius: '8px',
                        fontSize: '12px'
                      }}>
                        {error}
                      </div>
                    )}
                    
                    <div>
                      <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Prénom *</label>
                      <input
                        type="text"
                        value={leadData.firstName}
                        onChange={(e) => setLeadData({ ...leadData, firstName: e.target.value })}
                        placeholder="Votre prénom"
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{
                          background: 'rgba(255,255,255,0.1)',
                          border: '1px solid rgba(255,255,255,0.2)',
                          color: '#fff',
                          outline: 'none'
                        }}
                        data-testid="lead-firstname"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Numéro WhatsApp *</label>
                      <input
                        type="tel"
                        value={leadData.whatsapp}
                        onChange={(e) => setLeadData({ ...leadData, whatsapp: e.target.value })}
                        placeholder="+41 79 123 45 67"
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{
                          background: 'rgba(255,255,255,0.1)',
                          border: '1px solid rgba(255,255,255,0.2)',
                          color: '#fff',
                          outline: 'none'
                        }}
                        data-testid="lead-whatsapp"
                      />
                    </div>
                    
                    <div>
                      <label className="block text-white text-xs mb-1" style={{ opacity: 0.7 }}>Email *</label>
                      <input
                        type="email"
                        value={leadData.email}
                        onChange={(e) => setLeadData({ ...leadData, email: e.target.value })}
                        placeholder="votre@email.com"
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{
                          background: 'rgba(255,255,255,0.1)',
                          border: '1px solid rgba(255,255,255,0.2)',
                          color: '#fff',
                          outline: 'none'
                        }}
                        data-testid="lead-email"
                      />
                    </div>
                    
                    <button
                      type="submit"
                      disabled={isLoading}
                      className="py-3 rounded-lg font-semibold text-sm transition-all"
                      style={{
                        background: '#D91CD2', /* v9.4.2: Violet Afroboost */
                        color: '#fff',
                        border: 'none',
                        cursor: isLoading ? 'wait' : 'pointer',
                        opacity: isLoading ? 0.7 : 1,
                        marginTop: '8px'
                      }}
                      data-testid="lead-submit"
                    >
                      {isLoading ? 'Chargement...' : 'Commencer le chat 💬'}
                    </button>
                    
                    {/* === SÉPARATEUR === */}
                    <div style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: '12px',
                      margin: '8px 0'
                    }}>
                      <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.2)' }} />
                      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px' }}>ou</span>
                      <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.2)' }} />
                    </div>
                    
                    {/* === BOUTON ABONNÉ === */}
                    <button
                      type="button"
                      onClick={() => { setShowSubscriberForm(true); setError(''); }}
                      className="py-3 rounded-lg font-semibold text-sm transition-all"
                      style={{
                        background: 'linear-gradient(135deg, rgba(147, 51, 234, 0.3), rgba(99, 102, 241, 0.3))',
                        color: '#a855f7',
                        border: '1px solid rgba(147, 51, 234, 0.4)',
                        cursor: 'pointer'
                      }}
                      data-testid="subscriber-btn"
                    >
                      S'identifier comme abonné
                    </button>

                    {/* === v11.6: LIEN RETROUVER MES ACCÈS === */}
                    <button
                      type="button"
                      onClick={() => { setShowRecoverForm(true); setRecoverError(''); setRecoverResult(null); setError(''); }}
                      style={{
                        background: 'none',
                        color: '#f59e0b',
                        border: 'none',
                        cursor: 'pointer',
                        fontSize: '12px',
                        textDecoration: 'underline',
                        padding: '2px 0',
                        textAlign: 'center'
                      }}
                      data-testid="recover-access-link"
                    >
                      🔑 Code perdu ? Retrouver mes accès
                    </button>

                    {/* v84: Bouton Devenir Partenaire — Dashboard si Mode Coach actif, sinon Devenir Partenaire */}
                    {(platformSettings.partner_access_enabled || isCoachMode) && (
                    <button
                      type="button"
                      onClick={() => {
                        if (isCoachMode) {
                          window.location.hash = '#coach-dashboard';
                        } else {
                          window.dispatchEvent(new CustomEvent('openBecomeCoach'));
                        }
                      }}
                      className="text-xs font-medium transition-all hover:scale-105"
                      style={{
                        width: '100%',
                        padding: '10px',
                        marginTop: '8px',
                        borderRadius: '8px',
                        background: isCoachMode
                          ? 'linear-gradient(135deg, rgba(217, 28, 210, 0.3), rgba(139, 92, 246, 0.3))'
                          : 'transparent',
                        color: '#D91CD2',
                        border: '1px solid rgba(217, 28, 210, 0.4)',
                        cursor: 'pointer'
                      }}
                      data-testid={isCoachMode ? "partner-dashboard-btn" : "become-partner-chat-btn"}
                    >
                      {isCoachMode ? '🏠 Mon Espace Partenaire' : '✨ Devenir Partenaire'}
                    </button>
                    )}
                    
                    <p className="text-center text-xs" style={{ color: 'rgba(255,255,255,0.4)', marginTop: '8px' }}>
                      Vos données sont protégées et utilisées uniquement pour vous contacter.
                    </p>
                  </form>
                )}
              </div>
            )}

            {/* === MODE COACH: Interface de gestion des conversations === */}
            {step === 'coach' && isCoachMode && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
                {/* Header Coach MINIMALISTE - Masque en mode Vue Visiteur */}
                {!isVisitorPreview && (
                <div style={{ 
                  background: 'rgba(217, 28, 210, 0.2)', 
                  padding: '8px 16px', 
                  borderBottom: '1px solid rgba(217, 28, 210, 0.3)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {/* Coach avatar — click to upload, long-press/right-click to zoom */}
                    <label style={{ cursor: 'pointer', position: 'relative' }}>
                      {coachProfile && coachProfile.photo_url ? (
                        <img src={coachProfile.photo_url} alt="Coach"
                          onClick={function(e) { e.preventDefault(); setZoomedChatPhoto(coachProfile.photo_url); }}
                          style={{
                            width: '30px', height: '30px', borderRadius: '50%', objectFit: 'cover',
                            border: '2px solid #d91cd2', cursor: 'pointer'
                          }} />
                      ) : (
                        <div style={{
                          width: '30px', height: '30px', borderRadius: '50%',
                          background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: '13px', color: '#fff'
                        }}>📷</div>
                      )}
                      <input type="file" accept="image/*" style={{ display: 'none' }}
                        onChange={function(e) {
                          var file = e.target.files && e.target.files[0];
                          if (!file || file.size > 2 * 1024 * 1024) {
                            if (file) alert('Image trop grande (max 2 Mo)');
                            return;
                          }
                          var reader = new FileReader();
                          reader.onload = function(ev) {
                            var base64 = ev.target.result;
                            // Resize to max 200x200 for storage
                            var img = new Image();
                            img.onload = function() {
                              var canvas = document.createElement('canvas');
                              var size = Math.min(img.width, img.height, 200);
                              canvas.width = size; canvas.height = size;
                              var ctx = canvas.getContext('2d');
                              var sx = (img.width - size) / 2, sy = (img.height - size) / 2;
                              ctx.drawImage(img, sx, sy, size, size, 0, 0, size, size);
                              var resized = canvas.toDataURL('image/jpeg', 0.8);
                              // Save to backend
                              axios.put(API + '/coach-profile', { photo_url: resized }, {
                                headers: { 'X-User-Email': localStorage.getItem('coach_email') || '' }
                              }).then(function() {
                                setCoachProfile(function(prev) { return Object.assign({}, prev, { photo_url: resized }); });
                              }).catch(function() { alert('Erreur upload photo'); });
                            };
                            img.src = base64;
                          };
                          reader.readAsDataURL(file);
                          e.target.value = '';
                        }}
                      />
                    </label>
                    <span style={{ color: '#d91cd2', fontSize: '12px', fontWeight: 'bold' }}>
                      Mode Coach
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }} className="coach-icons-menu">
                    {/* Icône Partage (SVG minimaliste) */}
                    <button
                      onClick={handleShareLink}
                      title={linkCopied ? "Lien copié !" : "Partager"}
                      style={{ 
                        background: 'none', 
                        border: 'none', 
                        padding: '4px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        opacity: linkCopied ? 1 : 0.7,
                        transition: 'opacity 0.2s ease'
                      }}
                      data-testid="coach-chat-share"
                    >
                      {linkCopied ? (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
                          <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                      ) : (
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="1.5">
                          <circle cx="18" cy="5" r="3"></circle>
                          <circle cx="6" cy="12" r="3"></circle>
                          <circle cx="18" cy="19" r="3"></circle>
                          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                        </svg>
                      )}
                    </button>
                    
                    {/* Icône Menu (⋮) avec badge notifications */}
                    <div style={{ position: 'relative' }}>
                      <button
                        onClick={() => setShowCoachMenu(!showCoachMenu)}
                        style={{ 
                          background: 'none', 
                          border: 'none', 
                          padding: '4px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          opacity: 0.7,
                          transition: 'opacity 0.2s ease'
                        }}
                        data-testid="coach-chat-menu"
                      >
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="#fff">
                          <circle cx="12" cy="5" r="2"></circle>
                          <circle cx="12" cy="12" r="2"></circle>
                          <circle cx="12" cy="19" r="2"></circle>
                        </svg>
                      </button>
                      
                      {/* Badge notification (point rouge) */}
                      {coachSessions.length > 0 && (
                        <span style={{
                          position: 'absolute',
                          top: '0',
                          right: '0',
                          width: '8px',
                          height: '8px',
                          borderRadius: '50%',
                          background: '#ef4444',
                          border: '1px solid rgba(0,0,0,0.3)'
                        }} />
                      )}
                      
                      {/* Menu déroulant coach */}
                      {showCoachMenu && (
                        <div
                          style={{
                            position: 'absolute',
                            top: '30px',
                            right: '0',
                            background: '#1a1a1a',
                            borderRadius: '8px',
                            border: '1px solid rgba(255,255,255,0.1)',
                            overflow: 'hidden',
                            minWidth: '160px',
                            zIndex: 100,
                            boxShadow: '0 4px 20px rgba(0,0,0,0.5)'
                          }}
                        >
                          {/* Toggle Vue Visiteur (Admin) */}
                          <button
                            onClick={() => {
                              setIsVisitorPreview(!isVisitorPreview);
                              setShowCoachMenu(false);
                              console.log('[ADMIN] Vue Visiteur:', !isVisitorPreview ? 'activée' : 'désactivée');
                            }}
                            style={{
                              width: '100%',
                              padding: '10px 14px',
                              textAlign: 'left',
                              fontSize: '12px',
                              color: isVisitorPreview ? '#9333ea' : '#fff',
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px'
                            }}
                            className="hover:bg-white/10"
                            data-testid="visitor-preview-toggle"
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                              <circle cx="12" cy="12" r="3"></circle>
                            </svg>
                            {isVisitorPreview ? 'Vue Visiteur (actif)' : 'Vue Visiteur'}
                          </button>
                          <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }} />
                          <button
                            onClick={async () => {
                              setShowCoachMenu(false);
                              console.log('[COACH] Rafraîchissement...');
                              await loadCoachSessions();
                            }}
                            style={{
                              width: '100%',
                              padding: '10px 14px',
                              textAlign: 'left',
                              fontSize: '12px',
                              color: '#fff',
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px'
                            }}
                            className="hover:bg-white/10"
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="23 4 23 10 17 10"></polyline>
                              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                            </svg>
                            Rafraîchir
                          </button>
                          <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }} />
                          <button
                            onClick={() => {
                              setShowCoachMenu(false);
                              localStorage.clear();
                              sessionStorage.clear();
                              
                              setIsCoachMode(false);
                              setStep('form');
                              setMessages([]);
                              setSessionData(null);
                              setLeadData({ firstName: '', whatsapp: '', email: '' });
                              setSelectedCoachSession(null);
                              setCoachSessions([]);
                              
                              console.log('[COACH] Déconnexion');
                              window.history.replaceState(null, '', window.location.pathname);
                              window.location.reload();
                            }}
                            style={{
                              width: '100%',
                              padding: '10px 14px',
                              textAlign: 'left',
                              fontSize: '12px',
                              color: '#ef4444',
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px'
                            }}
                            className="hover:bg-white/10"
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                              <polyline points="16 17 21 12 16 7"></polyline>
                              <line x1="21" y1="12" x2="9" y2="12"></line>
                            </svg>
                            Déconnexion
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                )}

                {/* v162: Mini-dashboard tabs */}
                {!selectedCoachSession ? (
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                    {/* Tab bar */}
                    <div style={{ display: 'flex', borderBottom: '1px solid rgba(255,255,255,0.1)', flexShrink: 0 }}>
                      {[
                        { key: 'conversations', label: 'Conversations', icon: '💬' },
                        { key: 'reservations', label: 'Réservations', icon: '📅' },
                        { key: 'scanner', label: 'Scanner QR', icon: '📷' }
                      ].map(function(tab) {
                        return React.createElement('button', {
                          key: tab.key,
                          onClick: function() {
                            if (tab.key !== 'scanner') stopQrCamera();
                            setCoachDashTab(tab.key);
                            if (tab.key === 'reservations') loadCoachReservations();
                          },
                          style: {
                            flex: 1,
                            padding: '8px 4px',
                            fontSize: '11px',
                            color: coachDashTab === tab.key ? '#d91cd2' : '#888',
                            background: 'none',
                            border: 'none',
                            borderBottom: coachDashTab === tab.key ? '2px solid #d91cd2' : '2px solid transparent',
                            cursor: 'pointer',
                            transition: 'all 0.2s'
                          }
                        }, tab.icon + ' ' + tab.label);
                      })}
                    </div>

                    {/* Tab: Conversations */}
                    {coachDashTab === 'conversations' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
                    <div style={{ color: '#fff', fontSize: '12px', marginBottom: '12px', opacity: 0.7 }}>
                      Conversations actives ({coachSessions.length})
                    </div>
                    {coachSessions.length === 0 ? (
                      <div style={{ color: '#fff', opacity: 0.5, textAlign: 'center', padding: '20px', fontSize: '13px' }}>
                        Aucune conversation active
                      </div>
                    ) : (
                      coachSessions.map(function(session) { return (
                        <div
                          key={session.id}
                          onClick={function() { loadCoachSessionMessages(session); }}
                          onTouchStart={function(e) {
                            var t = setTimeout(function() {
                              // Long press detected
                              if (window.confirm('Supprimer cette conversation avec ' + (session.participantName || 'Visiteur anonyme') + ' ?')) {
                                axios.delete(API + '/chat/sessions/' + session.id, {
                                  headers: { 'X-User-Email': localStorage.getItem('coach_email') || '' }
                                }).then(function() { loadCoachSessions(); })
                                  .catch(function() { alert('Erreur de suppression'); });
                              }
                            }, 800);
                            e.target._lpTimer = t;
                          }}
                          onTouchEnd={function(e) { if (e.target._lpTimer) clearTimeout(e.target._lpTimer); }}
                          onTouchMove={function(e) { if (e.target._lpTimer) clearTimeout(e.target._lpTimer); }}
                          onContextMenu={function(e) {
                            e.preventDefault();
                            if (window.confirm('Supprimer cette conversation avec ' + (session.participantName || 'Visiteur anonyme') + ' ?')) {
                              axios.delete(API + '/chat/sessions/' + session.id, {
                                headers: { 'X-User-Email': localStorage.getItem('coach_email') || '' }
                              }).then(function() { loadCoachSessions(); })
                                .catch(function() { alert('Erreur de suppression'); });
                            }
                          }}
                          style={{
                            background: 'rgba(255,255,255,0.05)',
                            border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: '8px',
                            padding: '10px',
                            marginBottom: '8px',
                            cursor: 'pointer',
                            WebkitUserSelect: 'none',
                            userSelect: 'none'
                          }}
                        >
                          <div style={{ color: '#fff', fontSize: '13px', fontWeight: '500' }}>
                            {session.participantName || session.title || 'Visiteur anonyme'}
                          </div>
                          <div style={{ color: '#888', fontSize: '11px', marginTop: '4px' }}>
                            {session.participantEmail ? session.participantEmail : (session.mode === 'human' ? 'Mode Humain' : session.mode === 'community' ? 'Communauté' : 'IA')}
                            {' • '}
                            {new Date(session.created_at).toLocaleDateString('fr-FR')}
                          </div>
                          {session.lastMessage && (
                            <div style={{ color: '#aaa', fontSize: '11px', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '260px' }}>
                              {session.lastMessage}
                            </div>
                          )}
                        </div>
                      ); })
                    )}
                  </div>
                    )}

                    {/* Tab: Réservations */}
                    {coachDashTab === 'reservations' && (
                    <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
                      <div style={{ color: '#fff', fontSize: '12px', marginBottom: '12px', opacity: 0.7 }}>
                        Réservations récentes ({coachReservations.length})
                      </div>
                      {coachReservations.length === 0 ? (
                        <div style={{ color: '#fff', opacity: 0.5, textAlign: 'center', padding: '20px', fontSize: '13px' }}>
                          Aucune réservation
                        </div>
                      ) : (
                        coachReservations.slice(0, 30).map(function(r, idx) {
                          return React.createElement('div', {
                            key: r.reservationCode || idx,
                            style: {
                              background: r.validated ? 'rgba(34,197,94,0.1)' : 'rgba(255,255,255,0.05)',
                              border: '1px solid ' + (r.validated ? 'rgba(34,197,94,0.3)' : 'rgba(255,255,255,0.1)'),
                              borderRadius: '8px',
                              padding: '10px',
                              marginBottom: '8px'
                            }
                          },
                            React.createElement('div', { style: { color: '#fff', fontSize: '13px', fontWeight: '500' } },
                              (r.userName || 'Inconnu') + (r.validated ? ' ✅' : ' ⏳')
                            ),
                            React.createElement('div', { style: { color: '#888', fontSize: '11px', marginTop: '4px' } },
                              (r.courseName || r.offerName || '') + ' • ' + (r.selectedDatesText || '')
                            ),
                            React.createElement('div', { style: { color: '#666', fontSize: '10px', marginTop: '2px' } },
                              'Code: ' + (r.reservationCode || '') + (r.validatedAt ? ' • Validé le ' + new Date(r.validatedAt).toLocaleDateString('fr-FR') : '')
                            )
                          );
                        })
                      )}
                    </div>
                    )}

                    {/* Tab: Scanner QR */}
                    {coachDashTab === 'scanner' && (
                    <div style={{ flex: 1, padding: '16px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px', overflowY: 'auto' }}>
                      {/* Camera scanner zone — always in DOM for html5-qrcode */}
                      <div id="qr-reader-container" style={{
                        width: '100%', maxWidth: '280px', minHeight: qrCameraActive ? '220px' : '0',
                        borderRadius: '12px', overflow: 'hidden',
                        background: '#000'
                      }}></div>
                      {!qrCameraActive && (
                        <div style={{ display: 'flex', gap: '8px', width: '100%', maxWidth: '280px' }}>
                          <button onClick={startQrCamera} style={{
                            flex: 1, padding: '14px 8px', borderRadius: '10px',
                            border: '2px dashed rgba(217,28,210,0.4)',
                            background: 'rgba(217,28,210,0.06)', color: '#d91cd2',
                            fontSize: '13px', cursor: 'pointer', textAlign: 'center'
                          }}>📷 Caméra</button>
                          <label style={{
                            flex: 1, padding: '14px 8px', borderRadius: '10px',
                            border: '2px dashed rgba(139,92,246,0.4)',
                            background: 'rgba(139,92,246,0.06)', color: '#8b5cf6',
                            fontSize: '13px', cursor: 'pointer', textAlign: 'center'
                          }}>
                            🖼️ Image
                            <input type="file" accept="image/*" style={{ display: 'none' }}
                              onChange={function(e) {
                                var file = e.target.files && e.target.files[0];
                                if (!file) return;
                                setQrCameraError('');
                                setQrScanResult(null);
                                loadQrScannerLib(function() {
                                  var scanner = new window.Html5Qrcode('qr-reader-container');
                                  scanner.scanFile(file, true).then(function(decodedText) {
                                    setQrScanCode(decodedText.toUpperCase());
                                    // Auto-validate
                                    axios.post(API + '/reservations/staff/validate', { code: decodedText.trim() })
                                      .then(function(res) {
                                        setQrScanResult(res.data);
                                        if (res.data.success) setQrScanCode('');
                                      })
                                      .catch(function(err) {
                                        var msg = (err.response && err.response.data && err.response.data.detail) || 'Erreur';
                                        setQrScanResult({ success: false, message: msg });
                                      });
                                  }).catch(function() {
                                    setQrCameraError('Aucun QR code trouvé dans cette image');
                                  });
                                });
                                e.target.value = '';
                              }}
                            />
                          </label>
                        </div>
                      )}
                      {qrCameraActive && (
                        <button onClick={stopQrCamera} style={{
                          padding: '8px 16px', borderRadius: '8px', border: 'none',
                          background: 'rgba(239,68,68,0.2)', color: '#ef4444', fontSize: '12px',
                          cursor: 'pointer'
                        }}>
                          Fermer la caméra
                        </button>
                      )}
                      {qrCameraError && (
                        <div style={{ color: '#ef4444', fontSize: '12px', textAlign: 'center' }}>{qrCameraError}</div>
                      )}
                      <div style={{ width: '100%', maxWidth: '280px', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '10px', textAlign: 'center' }}>
                        <div style={{ color: '#888', fontSize: '11px', marginBottom: '8px' }}>ou entrez le code manuellement</div>
                      </div>
                      <input
                        type="text"
                        value={qrScanCode}
                        onChange={function(e) { setQrScanCode(e.target.value.toUpperCase()); }}
                        onKeyDown={function(e) { if (e.key === 'Enter') handleQrValidation(); }}
                        placeholder="CODE RÉSERVATION"
                        style={{
                          width: '100%',
                          maxWidth: '250px',
                          padding: '12px 16px',
                          borderRadius: '8px',
                          border: '1px solid rgba(255,255,255,0.2)',
                          background: 'rgba(255,255,255,0.05)',
                          color: '#fff',
                          fontSize: '16px',
                          textAlign: 'center',
                          letterSpacing: '2px',
                          outline: 'none'
                        }}
                      />
                      <button
                        onClick={handleQrValidation}
                        disabled={!qrScanCode.trim()}
                        style={{
                          padding: '10px 24px',
                          borderRadius: '8px',
                          border: 'none',
                          background: qrScanCode.trim() ? '#d91cd2' : 'rgba(255,255,255,0.1)',
                          color: '#fff',
                          fontSize: '14px',
                          cursor: qrScanCode.trim() ? 'pointer' : 'default',
                          fontWeight: '500'
                        }}
                      >
                        Valider la présence
                      </button>
                      {qrScanResult && (
                        <div style={{
                          padding: '12px 16px',
                          borderRadius: '8px',
                          background: qrScanResult.success ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                          border: '1px solid ' + (qrScanResult.success ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'),
                          color: qrScanResult.success ? '#22c55e' : '#ef4444',
                          fontSize: '13px',
                          textAlign: 'center',
                          width: '100%',
                          maxWidth: '250px'
                        }}>
                          {qrScanResult.success ? '✅ ' : '❌ '}
                          {qrScanResult.message}
                          {qrScanResult.userName && (
                            <div style={{ color: '#fff', marginTop: '4px', fontSize: '12px' }}>
                              {qrScanResult.userName} {qrScanResult.courseName ? '— ' + qrScanResult.courseName : ''}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    )}

                  </div>
                ) : (
                  <>
                    {/* Header session sélectionnée */}
                    <div style={{ 
                      padding: '8px 12px', 
                      borderBottom: '1px solid rgba(255,255,255,0.1)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px'
                    }}>
                      <button
                        onClick={() => setSelectedCoachSession(null)}
                        style={{ 
                          background: 'none', 
                          border: 'none', 
                          color: '#d91cd2', 
                          cursor: 'pointer',
                          fontSize: '14px'
                        }}
                      >
                        ← Retour
                      </button>
                      <span style={{ color: '#fff', fontSize: '12px' }}>
                        {selectedCoachSession.participantName || selectedCoachSession.title || 'Visiteur anonyme'}
                      </span>
                    </div>

                    {/* Messages - SMOOTH SCROLL: overflow-anchor none pour stabilité mobile */}
                    <div style={{ 
                      flex: 1, 
                      overflowY: 'auto', 
                      overflowAnchor: 'none', /* Fix sauts visuels mobile */
                      padding: '12px', 
                      display: 'flex', 
                      flexDirection: 'column', 
                      gap: '8px' 
                    }}>
                      {messages.map(function(msg, idx) { return (
                        <MemoizedMessageBubble
                          key={msg.id || idx}
                          msg={msg}
                          isUser={msg.type === 'coach'}
                          profilePhotoUrl={msg.type === 'coach' && coachProfile ? coachProfile.photo_url : null}
                          onReservationClick={function() {}}
                          onZoomPhoto={function(url) { setZoomedChatPhoto(url); }}
                          onDelete={function(messageId) { handleDeleteMessage(messageId); }}
                        />
                      ); })}
                      <div ref={messagesEndRef} />
                    </div>

                    {/* v162f: AI suggestion zone */}
                    {(aiSuggestion || aiSuggestionLoading) && (
                      <div style={{ padding: '8px 12px', borderTop: '1px solid rgba(217,28,210,0.2)', background: 'rgba(217,28,210,0.05)' }}>
                        {aiSuggestionLoading ? (
                          <div style={{ color: '#d91cd2', fontSize: '12px', textAlign: 'center' }}>
                            ✨ Génération de suggestion...
                          </div>
                        ) : (
                          <div>
                            <div style={{ color: '#888', fontSize: '10px', marginBottom: '4px' }}>💡 Suggestion IA :</div>
                            <div style={{ color: '#ddd', fontSize: '12px', lineHeight: '1.4', marginBottom: '6px' }}>{aiSuggestion}</div>
                            <div style={{ display: 'flex', gap: '6px' }}>
                              <button onClick={function() { setInputMessage(aiSuggestion); setAiSuggestion(''); }}
                                style={{ padding: '4px 10px', borderRadius: '12px', border: 'none', background: '#d91cd2', color: '#fff', fontSize: '11px', cursor: 'pointer' }}>
                                Utiliser
                              </button>
                              <button onClick={function() { setAiSuggestion(''); }}
                                style={{ padding: '4px 10px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.2)', background: 'none', color: '#888', fontSize: '11px', cursor: 'pointer' }}>
                                Ignorer
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {/* v162f: Coach emoji picker */}
                    {showCoachEmojiPicker && (
                      <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                        <AfricanEmojiPicker
                          isOpen={showCoachEmojiPicker}
                          onSelect={function(emoji) {
                            setInputMessage(function(prev) { return prev + emoji; });
                            setShowCoachEmojiPicker(false);
                          }}
                          onClose={function() { setShowCoachEmojiPicker(false); }}
                          customEmojis={coachCustomEmojis}
                        />
                      </div>
                    )}

                    {/* Input coach with emoji + AI buttons */}
                    <div style={{ padding: '8px 12px', borderTop: '1px solid rgba(255,255,255,0.1)', display: 'flex', gap: '6px', alignItems: 'center' }}>
                      {/* Emoji button */}
                      <button
                        type="button"
                        onClick={function() { setShowCoachEmojiPicker(!showCoachEmojiPicker); }}
                        title="Émojis"
                        style={{
                          width: '32px', height: '32px', borderRadius: '50%', border: 'none',
                          background: showCoachEmojiPicker ? '#d91cd2' : 'transparent',
                          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                          flexShrink: 0, fontSize: '16px'
                        }}
                      >😊</button>
                      {/* AI suggestion button */}
                      <button
                        type="button"
                        onClick={getAiSuggestion}
                        disabled={aiSuggestionLoading}
                        title="Suggestion IA"
                        style={{
                          width: '32px', height: '32px', borderRadius: '50%', border: 'none',
                          background: aiSuggestionLoading ? 'rgba(217,28,210,0.3)' : 'transparent',
                          cursor: aiSuggestionLoading ? 'wait' : 'pointer', display: 'flex',
                          alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: '16px'
                        }}
                      >✨</button>
                      {/* Text input */}
                      <input
                        type="text"
                        value={inputMessage}
                        onChange={function(e) { setInputMessage(e.target.value); }}
                        onKeyPress={function(e) { if (e.key === 'Enter') sendCoachResponse(); }}
                        placeholder="Votre réponse..."
                        style={{
                          flex: 1,
                          background: 'rgba(255,255,255,0.1)',
                          border: '1px solid rgba(255,255,255,0.2)',
                          borderRadius: '20px',
                          padding: '8px 16px',
                          color: '#fff',
                          fontSize: '13px',
                          outline: 'none'
                        }}
                      />
                      {/* Send button */}
                      <button
                        type="button"
                        onClick={function(e) {
                          e.preventDefault();
                          e.stopPropagation();
                          sendCoachResponse();
                        }}
                        disabled={isLoading || !inputMessage.trim()}
                        style={{
                          background: inputMessage.trim() ? 'linear-gradient(135deg, #d91cd2, #8b5cf6)' : 'rgba(255,255,255,0.1)',
                          border: 'none',
                          borderRadius: '50%',
                          width: '36px',
                          height: '36px',
                          cursor: inputMessage.trim() ? 'pointer' : 'not-allowed',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          opacity: inputMessage.trim() ? 1 : 0.5,
                          flexShrink: 0
                        }}
                        data-testid="coach-widget-send-btn"
                      >
                        <span style={{ pointerEvents: 'none' }}><SendIcon /></span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
            
            {/* Zone de chat */}
            {step === 'chat' && (
              <>
                {/* v85: Indicateur mode non-IA — sans bordure */}
                {sessionData && !sessionData.is_ai_active && (
                  <div
                    style={{
                      background: isCommunityMode ? 'rgba(139, 92, 246, 0.2)' : 'rgba(234, 179, 8, 0.2)',
                      padding: '8px 16px',
                      textAlign: 'center',
                      fontSize: '11px',
                      color: isCommunityMode ? '#a78bfa' : '#fbbf24'
                    }}
                  >
                    {isCommunityMode 
                      ? 'Mode Communauté - Plusieurs participants' 
                      : privateChatTarget
                      ? `💬 Discussion privée avec ${privateChatTarget.name}`
                      : 'Mode Humain - Le coach vous répondra'}
                  </div>
                )}

                {/* v85: CTA "Devenir Partenaire" — compact */}
                {!isCoachMode && (
                  <button
                    onClick={() => window.dispatchEvent(new CustomEvent('openBecomeCoach'))}
                    style={{
                      width: '100%',
                      padding: '8px 16px',
                      background: 'linear-gradient(135deg, rgba(217, 28, 210, 0.15), rgba(139, 92, 246, 0.1))',
                      border: 'none',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      flexShrink: 0
                    }}
                    data-testid="become-partner-banner"
                  >
                    <span style={{ fontSize: '12px' }}>✨</span>
                    <span style={{ color: '#D91CD2', fontSize: '12px', fontWeight: '700', letterSpacing: '0.3px' }}>Devenir Partenaire</span>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#D91CD2" strokeWidth="2.5" strokeLinecap="round">
                      <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                  </button>
                )}

                {/* === v97: BOUTON ABONNEMENTS — compact & moderne === */}
                {(afroboostProfile?.allSubscriptions?.length > 0 || afroboostProfile?.subscription) && (
                  <div data-testid="subscription-section" style={{ background: '#0a0a0a' }}>
                    {/* Bouton principal — dégradé violet Afroboost */}
                    <button
                      onClick={() => setShowMonPass(prev => !prev)}
                      style={{
                        width: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '10px 16px',
                        background: 'linear-gradient(135deg, rgba(217, 28, 210, 0.12), rgba(147, 51, 234, 0.08))',
                        border: 'none',
                        borderBottom: '1px solid rgba(217, 28, 210, 0.15)',
                        cursor: 'pointer',
                        transition: 'background 0.2s'
                      }}
                      data-testid="abonnements-toggle"
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        {/* Icône abonnement SVG */}
                        <div style={{
                          width: '28px', height: '28px', borderRadius: '8px',
                          background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          boxShadow: '0 2px 8px rgba(217, 28, 210, 0.3)'
                        }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
                            <line x1="1" y1="10" x2="23" y2="10"></line>
                          </svg>
                        </div>
                        <div style={{ textAlign: 'left' }}>
                          <div style={{ fontSize: '12px', fontWeight: '700', color: '#fff', letterSpacing: '0.3px' }}>
                            Mes Abonnements
                          </div>
                          <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)', marginTop: '1px' }}>
                            {(() => {
                              const subs = afroboostProfile.allSubscriptions || [afroboostProfile.subscription];
                              const totalRemaining = subs.reduce((acc, s) => {
                                if (s?.remaining_sessions === -1) return Infinity;
                                return acc + (s?.remaining_sessions || 0);
                              }, 0);
                              return totalRemaining === Infinity
                                ? `${subs.length} offre${subs.length > 1 ? 's' : ''} • Illimité`
                                : `${subs.length} offre${subs.length > 1 ? 's' : ''} • ${totalRemaining} séance${totalRemaining > 1 ? 's' : ''} restante${totalRemaining > 1 ? 's' : ''}`;
                            })()}
                          </div>
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {/* Mini compteur total */}
                        <div style={{
                          background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
                          padding: '3px 10px',
                          borderRadius: '12px',
                          fontSize: '11px',
                          fontWeight: '700',
                          color: '#fff'
                        }}>
                          {(() => {
                            const subs = afroboostProfile.allSubscriptions || [afroboostProfile.subscription];
                            const totalRemaining = subs.reduce((acc, s) => {
                              if (s?.remaining_sessions === -1) return Infinity;
                              return acc + (s?.remaining_sessions || 0);
                            }, 0);
                            return totalRemaining === Infinity ? '∞' : totalRemaining;
                          })()}
                        </div>
                        <svg
                          width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="2"
                          style={{ transform: showMonPass ? 'rotate(180deg)' : 'rotate(0)', transition: 'transform 0.25s ease' }}
                        >
                          <polyline points="6 9 12 15 18 9"></polyline>
                        </svg>
                      </div>
                    </button>

                    {/* Section dépliable — détails de chaque abonnement */}
                    {showMonPass && (
                      <div style={{
                        padding: '12px 16px',
                        background: 'rgba(0,0,0,0.3)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '12px',
                        animation: 'fadeIn 0.3s ease'
                      }}>
                        {(afroboostProfile.allSubscriptions || [afroboostProfile.subscription]).map((sub, idx) => {
                          /* v97: Nom lisible — si offer_name = code brut, on le formate */
                          const rawName = sub?.offer_name || sub?.code || 'Abonnement';
                          const displayName = rawName
                            .replace(/[-_]/g, ' ')
                            .replace(/\b\w/g, c => c.toUpperCase())
                            .replace(/^Bass$/, 'Pack Afroboost')
                            .replace(/Bassboostx/i, 'Pack Boost Xtrem');
                          const remaining = sub?.remaining_sessions === -1 ? '∞' : (sub?.remaining_sessions ?? '∞');
                          const total = sub?.total_sessions === -1 ? '∞' : (sub?.total_sessions ?? '∞');
                          const pct = (sub?.remaining_sessions > 0 && sub?.total_sessions > 0)
                            ? Math.round((sub.remaining_sessions / sub.total_sessions) * 100)
                            : sub?.remaining_sessions === -1 ? 100 : 0;

                          return (
                            <div key={sub?.id || idx} style={{
                              background: 'linear-gradient(135deg, rgba(217, 28, 210, 0.08), rgba(147, 51, 234, 0.05))',
                              borderRadius: '12px',
                              padding: '14px',
                              border: '1px solid rgba(217, 28, 210, 0.15)'
                            }}>
                              {/* En-tête : nom + compteur */}
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                  <div style={{
                                    width: '32px', height: '32px', borderRadius: '8px',
                                    background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center'
                                  }}>
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
                                    </svg>
                                  </div>
                                  <div>
                                    <div style={{ fontSize: '13px', fontWeight: '700', color: '#fff' }}>{displayName}</div>
                                    {sub?.offer_price != null && (
                                      <div style={{ fontSize: '10px', color: '#a78bfa', marginTop: '1px', fontWeight: '600' }}>
                                        {sub.offer_price > 0 ? `${sub.offer_price.toFixed(2)} CHF` : 'Offert'}
                                      </div>
                                    )}
                                    <div style={{ fontSize: '10px', color: 'rgba(255,255,255,0.4)', marginTop: '1px' }}>
                                      {sub?.expires_at
                                        ? `Expire le ${new Date(sub.expires_at).toLocaleDateString('fr-FR')}`
                                        : 'Sans expiration'}
                                      {' • '}{remaining === '∞' ? 'Illimité' : `${remaining}/${total} séance${total > 1 ? 's' : ''}`}
                                    </div>
                                  </div>
                                </div>
                                <div style={{
                                  background: 'linear-gradient(135deg, #D91CD2, #9333ea)',
                                  padding: '4px 12px',
                                  borderRadius: '12px',
                                  fontSize: '12px',
                                  fontWeight: '700',
                                  color: '#fff',
                                  boxShadow: '0 2px 8px rgba(217, 28, 210, 0.3)'
                                }}>
                                  {remaining}/{total}
                                </div>
                              </div>

                              {/* Barre de progression */}
                              <div style={{
                                height: '4px',
                                background: 'rgba(255,255,255,0.1)',
                                borderRadius: '2px',
                                overflow: 'hidden',
                                marginBottom: '10px'
                              }}>
                                <div style={{
                                  height: '100%',
                                  width: `${pct}%`,
                                  background: 'linear-gradient(90deg, #D91CD2, #9333ea)',
                                  borderRadius: '2px',
                                  transition: 'width 0.5s ease'
                                }}></div>
                              </div>

                              {/* Code + QR */}
                              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <img
                                  src={`https://api.qrserver.com/v1/create-qr-code/?size=80x80&data=${encodeURIComponent('https://afroboost.com/?qr=' + (sub?.code || afroboostProfile.code))}`}
                                  alt="QR"
                                  style={{
                                    width: '56px', height: '56px',
                                    borderRadius: '8px',
                                    background: '#fff',
                                    padding: '4px'
                                  }}
                                />
                                <div style={{ flex: 1 }}>
                                  <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.4)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '2px' }}>
                                    Code
                                  </div>
                                  <div style={{
                                    fontSize: '15px', fontWeight: '800', color: '#D91CD2',
                                    letterSpacing: '1.5px', fontFamily: 'monospace'
                                  }}>
                                    {sub?.code || afroboostProfile.code}
                                  </div>
                                  <div style={{ fontSize: '9px', color: 'rgba(255,255,255,0.35)', marginTop: '2px' }}>
                                    Présentez ce QR à l'entrée
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}


                {/* v97.1: Onglets Privé / Groupe — avec icônes SVG, positionnés sous les abonnements */}
                {afroboostProfile?.code && (
                  <div style={{
                    display: 'flex',
                    padding: '0',
                    background: '#0a0a0a',
                    gap: '0'
                  }}>
                    <button
                      onClick={() => { setChatMode('private'); }}
                      style={{
                        flex: 1,
                        padding: '10px 12px',
                        background: chatMode === 'private' ? 'rgba(217, 28, 210, 0.1)' : 'transparent',
                        border: 'none',
                        borderBottom: chatMode === 'private' ? '2px solid #d91cd2' : '2px solid rgba(255,255,255,0.08)',
                        color: chatMode === 'private' ? '#d91cd2' : 'rgba(255,255,255,0.4)',
                        fontSize: '11px',
                        fontWeight: '600',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      {/* Icône discussion individuelle */}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                      </svg>
                      Privé Coach
                    </button>
                    <button
                      onClick={() => { setChatMode('group'); loadAvailableGroups(); if (selectedGroup) loadGroupSessionMessages(selectedGroup.session_id); else loadGroupMessages(); }}
                      style={{
                        flex: 1,
                        padding: '10px 12px',
                        background: chatMode === 'group' ? 'rgba(139, 92, 246, 0.1)' : 'transparent',
                        border: 'none',
                        borderBottom: chatMode === 'group' ? '2px solid #8b5cf6' : '2px solid rgba(255,255,255,0.08)',
                        color: chatMode === 'group' ? '#8b5cf6' : 'rgba(255,255,255,0.4)',
                        fontSize: '11px',
                        fontWeight: '600',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        transition: 'all 0.2s ease'
                      }}
                    >
                      {/* Icône groupe */}
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="9" cy="7" r="4"></circle>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                      </svg>
                      Groupes
                    </button>
                  </div>
                )}
                
                {/* v97: Mon Pass fusionné dans le bouton Abonnements ci-dessus */}

                {/* v85: Banner supprimé ici — déplacé tout en haut (avant les onglets) */}

                {/* V107.12: Sélecteur de groupes thématiques */}
                {chatMode === 'group' && (
                  <div style={{
                    padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)',
                    display: 'flex', gap: '6px', overflowX: 'auto', flexShrink: 0,
                    WebkitOverflowScrolling: 'touch',
                  }}>
                    {availableGroups.length === 0 ? (
                      <span style={{ color: 'rgba(255,255,255,0.3)', fontSize: '11px', padding: '6px 0' }}>Chargement des groupes...</span>
                    ) : availableGroups.map(g => (
                      <button
                        key={g.id}
                        onClick={() => handleSelectGroup(g)}
                        style={{
                          padding: '6px 14px', borderRadius: '16px', border: 'none', cursor: 'pointer',
                          background: selectedGroup?.id === g.id
                            ? 'linear-gradient(135deg, #8b5cf6, #D91CD2)'
                            : 'rgba(255,255,255,0.06)',
                          color: selectedGroup?.id === g.id ? '#fff' : 'rgba(255,255,255,0.5)',
                          fontSize: '11px', fontWeight: '600', whiteSpace: 'nowrap',
                          transition: 'all 0.2s',
                          boxShadow: selectedGroup?.id === g.id ? '0 0 10px rgba(139,92,246,0.3)' : 'none',
                        }}
                      >
                        {g.name} {g.is_ai_active ? '🤖' : ''}
                      </button>
                    ))}
                  </div>
                )}

                <div
                  style={{
                    flex: 1,
                    overflowY: 'auto',
                    overflowAnchor: 'none', /* Fix sauts visuels mobile clavier */
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    minHeight: 0
                  }}
                >
                  {/* === SKELETON LOADING: Animation pendant le chargement initial === */}
                  {isLoadingHistory && messages.length === 0 && (
                    <MessageSkeleton count={4} />
                  )}

                  {/* V107.12: Message d'accueil quand aucun groupe sélectionné */}
                  {chatMode === 'group' && !selectedGroup && availableGroups.length > 0 && groupMessages.length === 0 && (
                    <div style={{ textAlign: 'center', padding: '30px 16px' }}>
                      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="rgba(139,92,246,0.3)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto 12px' }}>
                        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                        <circle cx="9" cy="7" r="4"></circle>
                        <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                        <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                      </svg>
                      <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '13px', margin: '0 0 6px' }}>
                        Choisissez un groupe ci-dessus
                      </p>
                      <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px', margin: 0 }}>
                        Posez vos questions et discutez avec les autres membres
                      </p>
                    </div>
                  )}

                  {/* === MESSAGES: Affichés selon mode (privé ou groupe) === */}
                  {/* v16.4: Animation slide-in + fade pour chaque message */}
                  {(chatMode === 'group' ? groupMessages : messages).filter(m => m.type !== 'review_request').map((msg, idx) => (
                    <div
                      key={msg.id || idx}
                      style={{
                        animation: 'afroMsgSlideIn 0.35s ease-out both',
                        animationDelay: `${Math.min(idx * 0.03, 0.3)}s`
                      }}
                    >
                      <MemoizedMessageBubble
                        msg={msg}
                        isUser={(msg.type === 'user' || msg.sender_type === 'user') && (msg.senderId === participantId || msg.sender_id === participantId)}
                        onParticipantClick={startPrivateChat}
                        isCommunity={chatMode === 'group'}
                        currentUserId={participantId}
                        profilePhotoUrl={profilePhoto}
                        onReservationClick={() => setShowReservationPanel(true)}
                        onZoomPhoto={(url) => setZoomedChatPhoto(url)}
                        onDelete={(messageId) => handleDeleteMessage(messageId)}
                      />
                    </div>
                  ))}
                  
                  {/* === INDICATEUR DE SAISIE (Typing Indicator) === */}
                  {typingUser && (
                    <div style={{ alignSelf: 'flex-start', marginTop: '4px' }}>
                      <div
                        style={{
                          background: 'rgba(167, 139, 250, 0.2)',
                          color: '#a78bfa',
                          padding: '8px 14px',
                          borderRadius: '16px 16px 16px 4px',
                          fontSize: '12px',
                          fontStyle: 'italic',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px'
                        }}
                      >
                        <span className="animate-pulse">...</span>
                        <span>{typingUser.type === 'coach' ? 'Coach Bassi' : typingUser.name} est en train d'écrire...</span>
                        <span className="animate-bounce" style={{ animationDelay: '0.1s' }}>.</span>
                        <span className="animate-bounce" style={{ animationDelay: '0.2s' }}>.</span>
                        <span className="animate-bounce" style={{ animationDelay: '0.3s' }}>.</span>
                      </div>
                    </div>
                  )}
                  
                  {isLoading && (
                    <div style={{ alignSelf: 'flex-start' }}>
                      <div
                        style={{
                          background: 'rgba(255,255,255,0.1)',
                          color: '#fff',
                          padding: '10px 14px',
                          borderRadius: '16px 16px 16px 4px',
                          fontSize: '13px'
                        }}
                      >
                        <span className="animate-pulse">...</span>
                      </div>
                    </div>
                  )}
                  
                  {/* === v86 fix: CARTE REVIEW_REQUEST — rendue hors du messages.map pour éviter écrasement par polling === */}
                  {reviewRequestVisible && !reviewSubmitted && !showReviewForm && (
                    <div style={{
                      alignSelf: 'flex-start',
                      maxWidth: '320px',
                      background: 'rgba(217, 28, 210, 0.1)',
                      borderRadius: '16px',
                      padding: '16px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '10px',
                      animation: 'afroMsgSlideIn 0.3s ease-out'
                    }}>
                      <div style={{ fontSize: '11px', fontWeight: 600, color: '#D91CD2', marginBottom: '2px' }}>
                        Afroboost
                      </div>
                      <p style={{ color: '#fff', fontSize: '13px', lineHeight: 1.5, margin: 0 }}>
                        {'🔥 Bravo pour ta session Afroboost ' + (afroboostProfile?.name || '') + ' ! Comment as-tu trouvé le cours ?'}
                      </p>
                      <button
                        onClick={() => {
                          setReviewSessionId('');
                          setShowReviewForm(true);
                        }}
                        style={{
                          background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                          border: 'none',
                          borderRadius: '20px',
                          padding: '10px 20px',
                          color: '#fff',
                          fontSize: '13px',
                          fontWeight: 700,
                          cursor: 'pointer',
                          alignSelf: 'flex-start',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px'
                        }}
                        data-testid="leave-review-btn"
                      >
                        ⭐ Laisser un avis
                      </button>
                    </div>
                  )}

                  {/* === v86: FORMULAIRE AVIS INLINE — Stars + Texte === */}
                  {showReviewForm && !reviewSubmitted && (
                    <div style={{
                      background: 'rgba(217, 28, 210, 0.08)',
                      borderRadius: '16px',
                      padding: '16px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                      animation: 'afroMsgSlideIn 0.3s ease-out'
                    }}
                    data-testid="review-form-inline"
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ color: '#D91CD2', fontSize: '13px', fontWeight: 700 }}>⭐ Ton avis</span>
                        <button
                          onClick={() => setShowReviewForm(false)}
                          style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', fontSize: '16px' }}
                        >✕</button>
                      </div>

                      {/* Étoiles */}
                      <div style={{ display: 'flex', gap: '4px', justifyContent: 'center' }}>
                        {[1,2,3,4,5].map(star => (
                          <button
                            key={star}
                            onClick={() => setReviewRating(star)}
                            style={{
                              background: 'none', border: 'none', cursor: 'pointer', padding: '4px',
                              transform: star <= reviewRating ? 'scale(1.2)' : 'scale(1)',
                              transition: 'transform 0.15s ease'
                            }}
                          >
                            <svg width="28" height="28" viewBox="0 0 24 24"
                              fill={star <= reviewRating ? '#D91CD2' : 'rgba(255,255,255,0.15)'}
                              stroke="none"
                            >
                              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                            </svg>
                          </button>
                        ))}
                      </div>

                      {/* Zone de texte */}
                      <textarea
                        value={reviewText}
                        onChange={(e) => setReviewText(e.target.value)}
                        placeholder="Qu'as-tu pensé du cours ? (ex: Super ambiance, j'ai adoré !)"
                        maxLength={500}
                        style={{
                          width: '100%',
                          minHeight: '60px',
                          background: 'rgba(255,255,255,0.05)',
                          border: 'none',
                          borderRadius: '12px',
                          padding: '10px 12px',
                          color: '#fff',
                          fontSize: '13px',
                          resize: 'vertical',
                          outline: 'none',
                          fontFamily: 'inherit'
                        }}
                      />

                      {/* Bouton envoyer */}
                      <button
                        onClick={handleSubmitReview}
                        disabled={!reviewText.trim() || reviewSubmitting}
                        style={{
                          background: reviewText.trim()
                            ? 'linear-gradient(135deg, #D91CD2, #8b5cf6)'
                            : 'rgba(255,255,255,0.1)',
                          border: 'none',
                          borderRadius: '20px',
                          padding: '10px 20px',
                          color: '#fff',
                          fontSize: '13px',
                          fontWeight: 700,
                          cursor: reviewText.trim() ? 'pointer' : 'not-allowed',
                          opacity: reviewText.trim() ? 1 : 0.5,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: '6px',
                          alignSelf: 'center'
                        }}
                        data-testid="submit-review-btn"
                      >
                        {reviewSubmitting ? '⏳ Envoi...' : '💜 Publier mon avis'}
                      </button>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>

                {/* === v9.3.7: PANNEAU DE RÉSERVATION - Visible pour TOUS, par-dessus le chat === */}
                {showReservationPanel && (
                  <div 
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      zIndex: 10000, /* Par-dessus tout dans le chat */
                      background: 'rgba(0,0,0,0.95)',
                      display: 'flex',
                      flexDirection: 'column',
                      overflow: 'hidden'
                    }}
                    data-testid="booking-panel-overlay"
                  >
                    {/* Header avec bouton fermer */}
                    <div style={{
                      padding: '16px',
                      borderBottom: '1px solid rgba(147, 51, 234, 0.3)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      background: 'linear-gradient(135deg, rgba(147, 51, 234, 0.2), rgba(99, 102, 241, 0.2))'
                    }}>
                      <h3 style={{ color: '#fff', fontSize: '16px', fontWeight: '600', margin: 0 }}>
                        📅 Réserver un cours
                      </h3>
                      <button
                        onClick={() => { setShowReservationPanel(false); setSelectedCourse(null); setReservationError(''); }}
                        style={{
                          background: 'rgba(255,255,255,0.1)',
                          border: 'none',
                          borderRadius: '50%',
                          width: '32px',
                          height: '32px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          color: '#fff'
                        }}
                        data-testid="close-booking-panel"
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <line x1="18" y1="6" x2="6" y2="18"></line>
                          <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                      </button>
                    </div>
                    
                    {/* Contenu du panel */}
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
                      <BookingPanel
                        afroboostProfile={afroboostProfile || {}}
                        availableCourses={availableCourses}
                        selectedCourse={selectedCourse}
                        setSelectedCourse={setSelectedCourse}
                        loadingCourses={loadingCourses}
                        reservationLoading={reservationLoading}
                        reservationError={reservationError}
                        onConfirmReservation={handleConfirmReservation}
                        onClose={() => { setShowReservationPanel(false); setSelectedCourse(null); setReservationError(''); }}
                        subscriptions={userSubscriptions}
                        selectedSubscription={selectedSubscription}
                        onSelectSubscription={setSelectedSubscription}
                      />
                    </div>
                  </div>
                )}
                
                {/* === BOUTON RÉACTIVATION MODE ABONNÉ (Visible en mode visiteur avec profil) === */}
                {!isFullscreen && isVisitorMode && afroboostProfile?.code && step === 'chat' && (
                  <div 
                    style={{
                      padding: '8px 12px',
                      borderTop: '1px solid rgba(147, 51, 234, 0.3)',
                      background: 'linear-gradient(135deg, rgba(147, 51, 234, 0.15), rgba(99, 102, 241, 0.15))',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px'
                    }}
                  >
                    <button
                      onClick={handleReactivateSubscriber}
                      style={{
                        background: 'linear-gradient(135deg, #9333ea, #6366f1)',
                        border: 'none',
                        borderRadius: '20px',
                        padding: '8px 16px',
                        color: '#fff',
                        fontSize: '12px',
                        fontWeight: '600',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        boxShadow: '0 2px 10px rgba(147, 51, 234, 0.3)'
                      }}
                      data-testid="reactivate-subscriber-btn"
                    >
                      Repasser en mode Réservation
                    </button>
                    <span style={{ fontSize: '10px', color: 'rgba(255,255,255,0.5)' }}>
                      ({afroboostProfile.name})
                    </span>
                  </div>
                )}
                
                {/* v81: Input message - Borderless moderne, Mobile optimized */}
                <div
                  style={{
                    padding: '10px 12px',
                    paddingBottom: 'max(10px, env(safe-area-inset-bottom, 10px))',
                    borderTop: 'none',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    flexShrink: 0,
                    position: 'sticky',
                    bottom: 0,
                    zIndex: 9999,
                    background: 'rgba(15,10,20,0.95)',
                    backdropFilter: 'blur(10px)',
                    WebkitBackdropFilter: 'blur(10px)'
                  }}
                  data-testid="chat-input-bar"
                >
                  {/* === GAUCHE: Emoji + Réservations === */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', flexShrink: 0 }}>
                    {/* v154: Sélecteur d'emojis unifié (Africain + Coach custom) */}
                    <AfricanEmojiPicker
                      isOpen={showAfricanEmojiPicker}
                      onSelect={(emoji) => {
                        // Si c'est un tag [emoji:...], l'insérer tel quel
                        if (typeof emoji === 'string' && emoji.startsWith('[emoji:')) {
                          setInputMessage(prev => prev + emoji);
                        } else {
                          setInputMessage(prev => prev + emoji);
                        }
                        setShowAfricanEmojiPicker(false);
                      }}
                      onClose={() => setShowAfricanEmojiPicker(false)}
                      customEmojis={coachCustomEmojis}
                    />

                    {/* v154: Un seul bouton emoji — personnage noir souriant */}
                    <button
                      type="button"
                      onClick={() => setShowAfricanEmojiPicker(!showAfricanEmojiPicker)}
                      style={{
                        width: '36px',
                        height: '36px',
                        borderRadius: '50%',
                        background: showAfricanEmojiPicker ? '#D91CD2' : 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        padding: 0
                      }}
                      data-testid="emoji-btn"
                      title="Émojis"
                    >
                      <svg width="28" height="28" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="18" cy="18" r="16" fill="#6D4C41"/>
                        <circle cx="12" cy="15" r="2" fill="#1a1a1a"/>
                        <circle cx="24" cy="15" r="2" fill="#1a1a1a"/>
                        <path d="M11 22 C14 27, 22 27, 25 22" stroke="#1a1a1a" strokeWidth="2" strokeLinecap="round" fill="none"/>
                      </svg>
                    </button>

                    {/* v9.3.7: Icône Calendrier (Réservation) - TOUJOURS VISIBLE pour tous les utilisateurs */}
                    <button
                      type="button"
                      onClick={handleReservationClick}
                      style={{
                        width: '40px',
                        height: '40px',
                        borderRadius: '50%',
                        background: showReservationPanel ? '#9333ea' : 'rgba(147, 51, 234, 0.3)',
                        border: '1px solid rgba(147, 51, 234, 0.5)',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0
                      }}
                      title="Réserver un cours"
                      data-testid="calendar-btn"
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={showReservationPanel ? '#fff' : '#a855f7'} strokeWidth="2">
                        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>
                        <line x1="16" y1="2" x2="16" y2="6"></line>
                        <line x1="8" y1="2" x2="8" y2="6"></line>
                        <line x1="3" y1="10" x2="21" y2="10"></line>
                      </svg>
                    </button>
                  </div>
                  
                  {/* === MILIEU: Input texte (flex-grow: 1) === */}
                  <input
                    type="text"
                    value={inputMessage}
                    onChange={handleInputChangeWithTyping}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        emitTyping(false);
                        handleSendMessage();
                      }
                    }}
                    onBlur={handleInputBlur}
                    placeholder="Écrivez votre message..."
                    style={{
                      flex: 1,
                      minWidth: 0,
                      background: 'rgba(255,255,255,0.08)',
                      border: 'none',
                      borderRadius: '24px',
                      color: '#fff',
                      outline: 'none',
                      fontSize: '16px',
                      padding: '10px 16px',
                      lineHeight: '1.2'
                    }}
                    data-testid="chat-input"
                  />
                  
                  {/* === DROITE: Bouton Envoyer (toujours à l'extrême droite) === */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleSendMessage();
                    }}
                    disabled={isLoading || !inputMessage.trim()}
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '50%',
                      background: '#D91CD2', /* v9.4.2: Violet Afroboost */
                      border: 'none',
                      cursor: isLoading || !inputMessage.trim() ? 'not-allowed' : 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      opacity: isLoading || !inputMessage.trim() ? 0.5 : 1,
                      flexShrink: 0,
                      marginLeft: 'auto' /* Force à droite */
                    }}
                    data-testid="chat-send-btn"
                  >
                    <span style={{ pointerEvents: 'none' }}><SendIcon /></span>
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* === FENÊTRE FLOTTANTE MP (Composant extrait) === */}
      <PrivateChatView
        activeChat={activePrivateChat ? {
          ...activePrivateChat,
          recipientName: activePrivateChat.recipientName || 
            (activePrivateChat.participant_1_id === participantId 
              ? activePrivateChat.participant_2_name 
              : activePrivateChat.participant_1_name)
        } : null}
        messages={privateMessages}
        inputValue={privateInput}
        setInputValue={setPrivateInput}
        onSend={sendPrivateMessage}
        onClose={closePrivateChat}
        onInputChange={emitDmTyping}
        onInputBlur={() => emitDmTyping(false)}
        typingUser={dmTypingUser}
        isMainChatOpen={isOpen}
      />
      
      {/* === v85: MODAL ZOOM PHOTO — Portal sur document.body + z-index 10000000 === */}
      {zoomedChatPhoto && ReactDOM.createPortal(
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            background: 'rgba(0,0,0,0.88)',
            backdropFilter: 'blur(5px)',
            WebkitBackdropFilter: 'blur(5px)',
            zIndex: 10000000,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            pointerEvents: 'auto'
          }}
          onClick={() => setZoomedChatPhoto(null)}
          data-testid="zoom-photo-modal"
        >
          {/* v82: Bouton Fermer (X) visible en haut à droite */}
          <button
            onClick={(e) => { e.stopPropagation(); setZoomedChatPhoto(null); }}
            style={{
              position: 'absolute',
              top: '20px',
              right: '20px',
              width: '44px',
              height: '44px',
              borderRadius: '50%',
              background: 'rgba(255,255,255,0.15)',
              border: '2px solid rgba(255,255,255,0.3)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10000001
            }}
          >
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
          {/* v82: Photo circulaire avec bordure violet néon */}
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: 'min(70vw, 280px)',
              height: 'min(70vw, 280px)',
              borderRadius: '50%',
              overflow: 'hidden',
              border: '5px solid #D91CD2',
              boxShadow: '0 0 40px rgba(217,28,210,0.6), 0 0 80px rgba(217,28,210,0.3), 0 0 120px rgba(217,28,210,0.1)',
              animation: 'v76ZoomIn 0.25s ease-out'
            }}
          >
            <img
              src={zoomedChatPhoto}
              alt="Photo profil"
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
          </div>
        </div>,
        document.body
      )}

      {/* v76: CSS animation pour zoom photo */}
      <style>{`
        @keyframes v76ZoomIn {
          from { transform: scale(0.5); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }
      
        @keyframes birthdaySlide {
          from { transform: translateX(-50%) translateY(-20px); opacity: 0; }
          to { transform: translateX(-50%) translateY(0); opacity: 1; }
        }
      `}</style>

      {/* V160: Birthday Announcement Banner */}
      {todayBirthdays && todayBirthdays.length > 0 && (
        <div style={{
          position: 'fixed', top: '60px', left: '50%', transform: 'translateX(-50%)',
          background: 'linear-gradient(135deg, #7c3aed, #a855f7)',
          color: '#fff', padding: '12px 24px', borderRadius: '16px',
          boxShadow: '0 4px 20px rgba(124,58,237,0.4)',
          zIndex: 10000, display: 'flex', alignItems: 'center', gap: '10px',
          maxWidth: '90vw', animation: 'birthdaySlide 0.5s ease-out'
        }}>
          <span style={{ fontSize: '28px' }}>&#x1F389;</span>
          <div>
            <div style={{ fontWeight: 'bold', fontSize: '14px' }}>
              {"C'est l'anniversaire de " + todayBirthdays.map(function(b) { return b.name; }).join(', ') + " !"}
            </div>
            <div style={{ fontSize: '12px', opacity: 0.9 }}>
              Souhaitez-lui un joyeux anniversaire !
            </div>
          </div>
          <button onClick={function() { setTodayBirthdays(null); }} style={{
            background: 'rgba(255,255,255,0.2)', border: 'none', color: '#fff',
            borderRadius: '50%', width: '24px', height: '24px', cursor: 'pointer',
            fontSize: '14px', marginLeft: '8px'
          }}>&#x2715;</button>
        </div>
      )}

      {/* V160: Birthday Date Picker Modal */}
      {showBirthdayModal && ReactDOM.createPortal(
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.6)', zIndex: 99999,
          display: 'flex', alignItems: 'center', justifyContent: 'center'
        }} onClick={function() { setShowBirthdayModal(false); }}>
          <div style={{
            background: 'linear-gradient(135deg, #1a1a2e, #2d1b4e)',
            borderRadius: '20px', padding: '28px', width: '320px',
            boxShadow: '0 8px 32px rgba(124,58,237,0.3)',
            border: '1px solid rgba(124,58,237,0.3)'
          }} onClick={function(e) { e.stopPropagation(); }}>
            <div style={{ textAlign: 'center', marginBottom: '20px' }}>
              <span style={{ fontSize: '40px' }}>&#x1F382;</span>
              <h3 style={{ color: '#fff', margin: '10px 0 5px', fontSize: '18px' }}>Date de naissance</h3>
              <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', margin: 0 }}>
                Pour recevoir un message le jour J !
              </p>
            </div>
            <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
              <div style={{ flex: 1 }}>
                <label style={{ color: 'rgba(255,255,255,0.7)', fontSize: '12px', marginBottom: '6px', display: 'block' }}>Mois</label>
                <select
                  value={birthdayMonth}
                  onChange={function(e) { setBirthdayMonth(e.target.value); }}
                  style={{
                    width: '100%', padding: '10px', borderRadius: '10px',
                    background: 'rgba(124,58,237,0.2)', border: '1px solid rgba(124,58,237,0.4)',
                    color: '#fff', fontSize: '14px', outline: 'none'
                  }}
                >
                  <option value="" style={{background:'#1a1a2e'}}>--</option>
                  <option value="1" style={{background:'#1a1a2e'}}>Janvier</option>
                  <option value="2" style={{background:'#1a1a2e'}}>F\u00e9vrier</option>
                  <option value="3" style={{background:'#1a1a2e'}}>Mars</option>
                  <option value="4" style={{background:'#1a1a2e'}}>Avril</option>
                  <option value="5" style={{background:'#1a1a2e'}}>Mai</option>
                  <option value="6" style={{background:'#1a1a2e'}}>Juin</option>
                  <option value="7" style={{background:'#1a1a2e'}}>Juillet</option>
                  <option value="8" style={{background:'#1a1a2e'}}>Ao\u00fbt</option>
                  <option value="9" style={{background:'#1a1a2e'}}>Septembre</option>
                  <option value="10" style={{background:'#1a1a2e'}}>Octobre</option>
                  <option value="11" style={{background:'#1a1a2e'}}>Novembre</option>
                  <option value="12" style={{background:'#1a1a2e'}}>D\u00e9cembre</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ color: 'rgba(255,255,255,0.7)', fontSize: '12px', marginBottom: '6px', display: 'block' }}>Jour</label>
                <select
                  value={birthdayDay}
                  onChange={function(e) { setBirthdayDay(e.target.value); }}
                  style={{
                    width: '100%', padding: '10px', borderRadius: '10px',
                    background: 'rgba(124,58,237,0.2)', border: '1px solid rgba(124,58,237,0.4)',
                    color: '#fff', fontSize: '14px', outline: 'none'
                  }}
                >
                  <option value="" style={{background:'#1a1a2e'}}>--</option>
                  {Array.from({length: 31}, function(_, i) { return i + 1; }).map(function(d) {
                    return React.createElement('option', {key: d, value: String(d), style:{background:'#1a1a2e'}}, d);
                  })}
                </select>
              </div>
            </div>
            {birthdaySaved ? (
              <div style={{
                background: 'rgba(34,197,94,0.2)', border: '1px solid rgba(34,197,94,0.4)',
                borderRadius: '12px', padding: '12px', textAlign: 'center',
                color: '#22c55e', fontSize: '14px'
              }}>
                &#x2705; Date enregistr\u00e9e !
              </div>
            ) : (
              <button
                onClick={handleSaveBirthday}
                disabled={!birthdayMonth || !birthdayDay}
                style={{
                  width: '100%', padding: '12px', borderRadius: '12px',
                  background: birthdayMonth && birthdayDay ? 'linear-gradient(135deg, #7c3aed, #a855f7)' : 'rgba(124,58,237,0.3)',
                  border: 'none', color: '#fff', fontSize: '15px',
                  fontWeight: 'bold', cursor: birthdayMonth && birthdayDay ? 'pointer' : 'not-allowed',
                  transition: 'all 0.3s'
                }}
              >
                Enregistrer
              </button>
            )}
          </div>
        </div>,
        document.body
      )}

    </>
  );
};

export default ChatWidget;

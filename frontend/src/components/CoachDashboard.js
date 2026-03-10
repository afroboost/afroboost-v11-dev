/**
 * CoachDashboard Component
 * Admin panel for managing the Afroboost application
 * Extracted from App.js for better maintainability
 */
import React, { useState, useEffect, useRef, useMemo, useCallback, Component } from "react";
import axios from "axios";
import { QRCodeSVG } from "qrcode.react";
import {
  getWhatsAppConfig,
  saveWhatsAppConfig,
  isWhatsAppConfigured,
  sendBulkWhatsApp,
  testWhatsAppConfig
} from "../services/whatsappService";
import {
  setLastMediaUrl as setLastMediaUrlService
} from "../services/aiResponseService";
import { sendBulkEmails } from "../services/emailService";
import { LandingSectionSelector } from "./SearchBar";
import { playNotificationSound, linkifyText } from "../services/notificationService";
import { QRScannerModal } from "./QRScanner";
// ArticleManager supprimÃ© - v8.9 Nettoyage SAAS
import ReservationTab from "./coach/ReservationTab"; // Import Reservation Tab
import CampaignManager from "./coach/CampaignManager"; // Import Campaign Manager
import CRMSection from "./coach/CRMSection"; // v9.2.0 Import CRM Section
import { parseMediaUrl, getMediaThumbnail } from "../services/MediaParser"; // Media Parser
import SuperAdminPanel from "./SuperAdminPanel"; // v8.9 Super Admin Panel
// v13.5: Composants extraits pour allÃ©ger CoachDashboard
import { CreditsGate, CreditBoutique, StripeConnectTab, CoursesManager, OffersManager, ConceptEditor, PageVenteTab, PromoCodesTab, PaymentConfigTab, BrandingManager, SEOManager, FAQManager, ContactsManager } from "./dashboard";
import { copyToClipboard } from "../utils/clipboard"; // Utilitaire copier avec fallback mobile

// v9.2.1: ErrorBoundary pour isoler les erreurs de composants
class SectionErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, info) {
    console.error('[SectionErrorBoundary]', this.props.sectionName, error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="p-6 rounded-xl bg-red-500/20 border border-red-500/50 text-white">
          <h3 className="text-lg font-bold mb-2">â ï¸ Erreur dans la section {this.props.sectionName}</h3>
          <p className="text-white/70 text-sm mb-3">{this.state.error?.message || 'Une erreur est survenue'}</p>
          <button 
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-4 py-2 bg-violet-500 rounded-lg text-white text-sm"
          >
            ð RÃ©essayer
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// === API BACKEND URL (UNIQUE) ===
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

// ============================================================
// === FONCTIONS AUTONOMES - ENVOI EMAIL VIA RESEND (BACKEND)
// ============================================================

/**
 * FONCTION D'ENVOI EMAIL VIA RESEND (API BACKEND)
 * Remplace EmailJS pour un contrÃ´le total cÃ´tÃ© serveur
 * @param {string} destination - Email du destinataire
 * @param {string} recipientName - Nom du destinataire
 * @param {string} subject - Sujet de l'email
 * @param {string} text - Corps du message
 * @param {string} mediaUrl - URL du visuel (optionnel, peut Ãªtre un lien interne /v/slug)
 * @returns {Promise<{success: boolean, response?: any, error?: string}>}
 */
const performEmailSend = async (destination, recipientName = 'Client', subject = 'Afroboost', text = '', mediaUrl = null) => {
  try {
    // Validation des paramÃ¨tres
    if (!destination || !destination.includes('@')) {
      console.error('RESEND_DEBUG: Email invalide -', destination);
      return { success: false, error: 'Email invalide' };
    }
    
    if (!text || text.trim() === '') {
      console.error('RESEND_DEBUG: Message vide');
      return { success: false, error: 'Message vide' };
    }
    
    console.log('========================================');
    console.log('RESEND_DEBUG: Envoi campagne via API');
    console.log('RESEND_DEBUG: Destination =', destination);
    console.log('RESEND_DEBUG: Sujet =', subject);
    console.log('RESEND_DEBUG: Media URL =', mediaUrl || 'Aucun');
    console.log('========================================');
    
    // Appel API backend Resend
    const response = await fetch(`${BACKEND_URL}/api/campaigns/send-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        to_email: String(destination).trim(),
        to_name: String(recipientName || 'Client').trim(),
        subject: String(subject || 'Afroboost').trim(),
        message: String(text).trim(),
        media_url: mediaUrl ? String(mediaUrl).trim() : null
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      console.log('RESEND_DEBUG: SUCCÃS - Email ID =', result.email_id);
      return { success: true, response: result };
    } else {
      console.error('RESEND_DEBUG: ÃCHEC -', result.error);
      return { success: false, error: result.error };
    }
    
  } catch (error) {
    console.error('RESEND_DEBUG: Exception -', error);
    return { success: false, error: error.message };
  }
};

/**
 * FONCTION AUTONOME D'ENVOI WHATSAPP VIA TWILIO
 * Si pas de backend, affiche une alerte de simulation
 * @param {string} phoneNumber - NumÃ©ro de tÃ©lÃ©phone
 * @param {string} message - Message Ã  envoyer
 * @param {object} twilioConfig - {accountSid, authToken, fromNumber}
 * @returns {Promise<{success: boolean, sid?: string, error?: string}>}
 */
const performWhatsAppSend = async (phoneNumber, message, twilioConfig) => {
  const { accountSid, authToken, fromNumber } = twilioConfig || {};
  
  console.log('========================================');
  console.log('DEMANDE WHATSAPP/TWILIO ENVOYÃE');
  console.log('NumÃ©ro:', phoneNumber);
  console.log('Message:', message?.substring(0, 50) + '...');
  console.log('Account SID:', accountSid || 'NON CONFIGURÃ');
  console.log('From Number:', fromNumber || 'NON CONFIGURÃ');
  console.log('========================================');
  
  // Si pas de config Twilio, simulation avec alerte
  if (!accountSid || !authToken || !fromNumber) {
    console.warn('â ï¸ Twilio non configurÃ© - Mode simulation');
    alert(`WhatsApp prÃªt pour : ${phoneNumber}\n\nMessage: ${message?.substring(0, 100)}...`);
    return { success: true, simulated: true };
  }
  
  // Formater le numÃ©ro au format E.164
  let formattedPhone = phoneNumber.replace(/[^\d+]/g, '');
  if (!formattedPhone.startsWith('+')) {
    formattedPhone = formattedPhone.startsWith('0') 
      ? '+41' + formattedPhone.substring(1) 
      : '+' + formattedPhone;
  }
  
  // Construire les donnÃ©es pour Twilio
  const formData = new URLSearchParams();
  formData.append('From', `whatsapp:${fromNumber.startsWith('+') ? fromNumber : '+' + fromNumber}`);
  formData.append('To', `whatsapp:${formattedPhone}`);
  formData.append('Body', message);
  
  try {
    const response = await fetch(
      `https://api.twilio.com/2010-04-01/Accounts/${accountSid}/Messages.json`,
      {
        method: 'POST',
        headers: {
          'Authorization': 'Basic ' + btoa(`${accountSid}:${authToken}`),
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: formData
      }
    );
    
    const data = await response.json();
    console.log('ð± TWILIO RÃPONSE:', data);
    
    if (!response.ok) {
      return { success: false, error: data.message || `HTTP ${response.status}` };
    }
    
    return { success: true, sid: data.sid };
  } catch (error) {
    console.error('â TWILIO ERREUR:', error);
    return { success: false, error: error.message };
  }
};

// API avec prÃ©fixe /api
const API = `${BACKEND_URL}/api`;

// Weekdays mapping for multi-language support
const WEEKDAYS_MAP = {
  fr: ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"],
  en: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  de: ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"]
};

// SVG Icons
const CalendarIcon = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>;
const ClockIcon = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>;
const TrashIcon = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>;
const FolderIcon = () => <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/></svg>;

// MediaDisplay component - Utilise parseMediaUrl importÃ© de MediaParser.js
const MediaDisplay = ({ url, className }) => {
  const media = parseMediaUrl(url);
  if (!media || media.type === 'unknown' || !url || url.trim() === '') return null;

  const containerStyle = {
    position: 'relative',
    width: '100%',
    paddingBottom: '56.25%',
    overflow: 'hidden',
    borderRadius: '16px',
    border: '1px solid rgba(217, 28, 210, 0.3)',
    background: '#0a0a0a'
  };

  const contentStyle = {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%'
  };

  // YouTube - utilise embedUrl du parser
  if (media.type === 'youtube') {
    return (
      <div className={className} style={containerStyle}>
        <iframe 
          src={media.embedUrl || `https://www.youtube.com/embed/${media.videoId}?autoplay=0&mute=1`}
          frameBorder="0" 
          allow="encrypted-media" 
          style={{ ...contentStyle }}
          title="YouTube video"
        />
      </div>
    );
  }
  
  // Google Drive - utilise embedUrl du parser
  if (media.type === 'drive') {
    return (
      <div className={className} style={containerStyle}>
        <iframe 
          src={media.embedUrl}
          frameBorder="0" 
          allow="autoplay" 
          style={{ ...contentStyle }}
          title="Google Drive media"
        />
      </div>
    );
  }
  
  // VidÃ©o directe
  if (media.type === 'video') {
    return (
      <div className={className} style={containerStyle}>
        <video 
          src={media.directUrl} 
          muted
          playsInline 
          style={{ ...contentStyle, objectFit: 'cover' }}
        />
      </div>
    );
  }
  
  // Image ou lien inconnu - affiche directUrl ou thumbnailUrl avec fallback SVG
  return (
    <div className={className} style={containerStyle}>
      <img 
        src={media.thumbnailUrl || media.directUrl} 
        alt="Media" 
        style={{ ...contentStyle, objectFit: 'cover' }}
        onError={(e) => { 
          // Fallback: affiche une icone video SVG
          e.target.style.display = 'none';
          const fallback = e.target.nextSibling;
          if (fallback) fallback.style.display = 'flex';
        }}
      />
      {/* Fallback SVG quand image ne charge pas */}
      <div 
        style={{ 
          ...contentStyle, 
          display: 'none', 
          alignItems: 'center', 
          justifyContent: 'center',
          background: 'rgba(0,0,0,0.5)'
        }}
      >
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="1.5">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
      </div>
    </div>
  );
};

// ClÃ© localStorage pour persistance coach
const COACH_TAB_KEY = 'afroboost_coach_tab';
const COACH_SESSION_KEY = 'afroboost_coach_session';

// === v79: Composant Social Boost â liste commentaires + formulaire ajout + toast + feedback UX ===
const SocialBoostCommentsList = ({ API, coachEmail, axios }) => {
  const [comments, setComments] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [refreshing, setRefreshing] = React.useState(false);
  const [likedIds, setLikedIds] = React.useState({});
  const [toast, setToast] = React.useState('');
  // v79: Formulaire ajout manuel
  const [showAddForm, setShowAddForm] = React.useState(false);
  const [newName, setNewName] = React.useState('');
  const [newText, setNewText] = React.useState('');
  const [newPhotoUrl, setNewPhotoUrl] = React.useState('');
  const [adding, setAdding] = React.useState(false);

  const showToast = (msg) => { setToast(msg); setTimeout(() => setToast(''), 2500); };

  const fetchComments = React.useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/comments?coach_id=${encodeURIComponent(coachEmail || '')}`);
      setComments((res.data?.comments || []).slice(0, 5));
    } catch (e) { console.error('[V79] Fetch comments error:', e); }
    finally { setLoading(false); }
  }, [API, coachEmail, axios]);

  React.useEffect(() => { fetchComments(); }, [fetchComments]);

  React.useEffect(() => {
    const el = document.getElementById('social-boost-comments-list');
    if (!el) return;
    const handler = () => fetchComments();
    el.addEventListener('refresh', handler);
    return () => el.removeEventListener('refresh', handler);
  }, [fetchComments]);

  // v79: Like avec disable + spinner + toast
  const handleLike = async (commentId) => {
    setComments(prev => prev.map(c => c.id === commentId ? { ...c, likes: (c.likes || 0) + 1 } : c));
    setLikedIds(prev => ({ ...prev, [commentId]: 'loading' }));
    try {
      await axios.post(`${API}/comments/${commentId}/like`);
      setLikedIds(prev => ({ ...prev, [commentId]: 'done' }));
      showToast('â Like +1 enregistrÃ©');
      console.log('[V79] Like +1 OK:', commentId);
    } catch (e) {
      setComments(prev => prev.map(c => c.id === commentId ? { ...c, likes: (c.likes || 0) - 1 } : c));
      showToast('â Erreur like');
    }
    setTimeout(() => setLikedIds(prev => ({ ...prev, [commentId]: false })), 1200);
  };

  // v79: Refresh avec toast
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const res = await axios.get(`${API}/comments?coach_id=${encodeURIComponent(coachEmail || '')}`);
      setComments((res.data?.comments || []).slice(0, 5));
      showToast('â Commentaires mis Ã  jour');
    } catch (e) { showToast('â Erreur rafraÃ®chissement'); }
    finally { setRefreshing(false); }
  };

  const handleDelete = async (commentId) => {
    if (!window.confirm('Supprimer ce commentaire ?')) return;
    try {
      await axios.delete(`${API}/admin/comments/${commentId}`, {
        headers: { 'X-User-Email': coachEmail }
      });
      setComments(prev => prev.filter(c => c.id !== commentId));
      showToast('â Commentaire supprimÃ©');
    } catch (e) { showToast('â Erreur suppression'); }
  };

  const handlePhoto = async (commentId) => {
    const url = prompt('URL de la photo de profil (ex: /api/files/xxx/photo.jpg) :');
    if (!url) return;
    try {
      await axios.post(`${API}/admin/comments/${commentId}/photo`, { photo_url: url }, {
        headers: { 'X-User-Email': coachEmail, 'Content-Type': 'application/json' }
      });
      setComments(prev => prev.map(c => c.id === commentId ? { ...c, profile_photo: url } : c));
      showToast('â Photo mise Ã  jour');
    } catch (e) { showToast('â Erreur photo'); }
  };

  // v79: Ajout manuel de commentaire
  const handleAddComment = async () => {
    if (!newName.trim() || !newText.trim()) return;
    setAdding(true);
    try {
      const res = await axios.post(`${API}/admin/comments/add`, {
        user_name: newName.trim(),
        text: newText.trim(),
        profile_photo: newPhotoUrl.trim() || '',
        coach_id: coachEmail
      }, { headers: { 'X-User-Email': coachEmail, 'Content-Type': 'application/json' } });
      if (res.data?.comment) {
        setComments(prev => [res.data.comment, ...prev].slice(0, 5));
      }
      setNewName(''); setNewText(''); setNewPhotoUrl('');
      setShowAddForm(false);
      showToast('â Commentaire ajoutÃ©');
      console.log('[V79] Commentaire manuel ajoutÃ©');
    } catch (e) {
      const msg = e.response?.data?.detail || 'Erreur ajout';
      showToast('â ' + msg);
    }
    finally { setAdding(false); }
  };

  if (loading && comments.length === 0) return (
    <div id="social-boost-comments-list" style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', marginTop: '12px' }}>
      â³ Chargement des commentaires...
    </div>
  );

  return (
    <div id="social-boost-comments-list" style={{ marginTop: '14px' }}>
      <style>{`
        @keyframes v79LikePulse {
          0% { transform: scale(1); }
          30% { transform: scale(1.5); }
          60% { transform: scale(0.9); }
          100% { transform: scale(1); }
        }
        @keyframes v79RefreshSpin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
        @keyframes v79LikeFlash {
          0% { color: #D91CD2; }
          50% { color: #00ff88; font-size: 14px; }
          100% { color: #D91CD2; }
        }
        @keyframes v79ToastIn {
          from { transform: translateY(20px); opacity: 0; }
          to { transform: translateY(0); opacity: 1; }
        }
        @keyframes v79Spin {
          0% { transform: rotate(0deg); }
          100% { transform: rotate(360deg); }
        }
      `}</style>

      {/* v79: Toast notification */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: '80px', left: '50%', transform: 'translateX(-50%)',
          background: toast.startsWith('â') ? 'rgba(0,200,100,0.95)' : 'rgba(220,40,40,0.95)',
          color: '#fff', padding: '10px 22px', borderRadius: '20px', fontSize: '13px',
          fontWeight: 600, zIndex: 999999, boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
          animation: 'v79ToastIn 0.3s ease', whiteSpace: 'nowrap'
        }}>{toast}</div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <div style={{ color: '#D91CD2', fontSize: '12px', fontWeight: 600 }}>
          5 derniers commentaires :
        </div>
        {/* v79: Bouton + Ajouter commentaire */}
        <button onClick={() => setShowAddForm(!showAddForm)}
          style={{
            background: showAddForm ? 'rgba(217,28,210,0.3)' : 'rgba(217,28,210,0.1)',
            border: '1px solid rgba(217,28,210,0.4)', borderRadius: '6px',
            color: '#D91CD2', fontSize: '11px', fontWeight: 600, cursor: 'pointer',
            padding: '4px 10px'
          }}>
          {showAddForm ? 'â Fermer' : 'ï¼ Ajouter'}
        </button>
      </div>

      {/* v79: Formulaire d'ajout manuel */}
      {showAddForm && (
        <div style={{
          background: 'rgba(217,28,210,0.06)', border: '1px solid rgba(217,28,210,0.2)',
          borderRadius: '10px', padding: '12px', marginBottom: '10px'
        }}>
          <div style={{ fontSize: '12px', color: '#D91CD2', fontWeight: 600, marginBottom: '8px' }}>
            Nouveau commentaire manuel
          </div>
          <input value={newName} onChange={e => setNewName(e.target.value)}
            placeholder="Nom de l'utilisateur (ex: Marie D.)"
            style={{
              width: '100%', padding: '8px 10px', marginBottom: '6px', borderRadius: '6px',
              border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)',
              color: '#fff', fontSize: '12px', outline: 'none', boxSizing: 'border-box'
            }} />
          <textarea value={newText} onChange={e => setNewText(e.target.value)}
            placeholder="Texte du commentaire..."
            rows={2}
            style={{
              width: '100%', padding: '8px 10px', marginBottom: '6px', borderRadius: '6px',
              border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)',
              color: '#fff', fontSize: '12px', outline: 'none', resize: 'vertical',
              boxSizing: 'border-box', fontFamily: 'inherit'
            }} />
          <input value={newPhotoUrl} onChange={e => setNewPhotoUrl(e.target.value)}
            placeholder="URL photo de profil (optionnel â DiceBear si vide)"
            style={{
              width: '100%', padding: '8px 10px', marginBottom: '8px', borderRadius: '6px',
              border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)',
              color: '#fff', fontSize: '11px', outline: 'none', boxSizing: 'border-box'
            }} />
          <button onClick={handleAddComment}
            disabled={adding || !newName.trim() || !newText.trim()}
            style={{
              background: adding ? 'rgba(150,150,150,0.3)' : 'linear-gradient(135deg, #D91CD2, #8B5CF6)',
              border: 'none', borderRadius: '8px', color: '#fff', fontSize: '13px',
              fontWeight: 600, padding: '10px 20px', cursor: adding ? 'wait' : 'pointer',
              opacity: (!newName.trim() || !newText.trim()) ? 0.5 : 1,
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px'
            }}>
            {adding ? (
              <>
                <span style={{ display: 'inline-block', width: '14px', height: '14px', border: '2px solid rgba(255,255,255,0.3)', borderTop: '2px solid #fff', borderRadius: '50%', animation: 'v79Spin 0.8s linear infinite' }}></span>
                Ajout en cours...
              </>
            ) : 'â Ajouter ce commentaire'}
          </button>
        </div>
      )}

      {comments.length === 0 && !showAddForm ? (
        <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>
          Aucun commentaire. Cliquez sur "Booster" ou "ï¼ Ajouter" pour en crÃ©er.
        </div>
      ) : comments.map((c) => {
        const likeState = likedIds[c.id]; // false | 'loading' | 'done'
        const justLiked = likeState === 'done';
        const isLiking = likeState === 'loading';
        return (
        <div key={c.id} style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '8px 10px', marginBottom: '6px',
          background: 'rgba(255,255,255,0.04)', borderRadius: '10px',
          border: '1px solid rgba(255,255,255,0.06)'
        }}>
          {/* Avatar */}
          {c.profile_photo ? (
            <img src={c.profile_photo} alt="" style={{
              width: '32px', height: '32px', borderRadius: '50%', objectFit: 'cover',
              border: '2px solid #D91CD2', flexShrink: 0
            }} />
          ) : (
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%', flexShrink: 0,
              background: '#D91CD2', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '13px', fontWeight: 700, color: '#fff'
            }}>{(c.user_name || '?')[0].toUpperCase()}</div>
          )}
          {/* Content */}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: '#fff', fontSize: '12px', fontWeight: 600 }}>{c.user_name}</div>
            <div style={{ color: 'rgba(255,255,255,0.6)', fontSize: '11px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {c.text}
            </div>
          </div>
          {/* Likes count */}
          <span style={{
            color: justLiked ? '#00ff88' : '#D91CD2',
            fontSize: justLiked ? '14px' : '12px',
            fontWeight: 700, minWidth: '35px', textAlign: 'center',
            transition: 'all 0.3s ease',
            animation: justLiked ? 'v79LikeFlash 0.6s ease' : 'none'
          }}>
            {c.likes || 0}
          </span>
          {/* v79: Like button â disabled pendant loading + spinner */}
          <button onClick={() => handleLike(c.id)} title="+1 Like"
            disabled={!!isLiking}
            style={{
              background: (justLiked || isLiking) ? 'rgba(217,28,210,0.2)' : 'none',
              border: (justLiked || isLiking) ? '1px solid #D91CD2' : '1px solid transparent',
              borderRadius: '8px', cursor: isLiking ? 'wait' : 'pointer', fontSize: '18px',
              padding: '6px 10px', minWidth: '44px', minHeight: '36px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              animation: justLiked ? 'v79LikePulse 0.5s ease' : 'none',
              transition: 'all 0.2s ease', opacity: isLiking ? 0.6 : 1
            }}>
            {isLiking ? (
              <span style={{ display: 'inline-block', width: '16px', height: '16px', border: '2px solid rgba(217,28,210,0.3)', borderTop: '2px solid #D91CD2', borderRadius: '50%', animation: 'v79Spin 0.7s linear infinite' }}></span>
            ) : 'â¤ï¸'}
          </button>
          {/* Photo button */}
          <button onClick={() => handlePhoto(c.id)} title="Ajouter photo"
            style={{
              background: 'none', border: '1px solid transparent', borderRadius: '8px',
              cursor: 'pointer', fontSize: '18px', padding: '6px 10px',
              minWidth: '44px', minHeight: '36px',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
            ð¸
          </button>
          {/* Delete button */}
          <button onClick={() => handleDelete(c.id)} title="Supprimer"
            style={{
              background: 'none', border: '1px solid transparent', borderRadius: '8px',
              cursor: 'pointer', fontSize: '18px', padding: '6px 10px',
              minWidth: '44px', minHeight: '36px',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
            ðï¸
          </button>
        </div>
        );
      })}
      {/* v79: Refresh button */}
      <button onClick={handleRefresh} disabled={refreshing}
        style={{
          background: refreshing ? 'rgba(217,28,210,0.15)' : 'rgba(217,28,210,0.08)',
          border: '1px solid rgba(217,28,210,0.3)', borderRadius: '8px',
          color: '#D91CD2', fontSize: '13px', fontWeight: 600,
          cursor: refreshing ? 'wait' : 'pointer',
          padding: '8px 16px', marginTop: '8px',
          display: 'flex', alignItems: 'center', gap: '6px',
          opacity: refreshing ? 0.7 : 1,
          transition: 'all 0.2s ease', width: '100%', justifyContent: 'center'
        }}>
        <span style={{
          display: 'inline-block',
          animation: refreshing ? 'v79RefreshSpin 1s linear infinite' : 'none'
        }}>ð</span>
        {refreshing ? 'RafraÃ®chissement...' : 'RafraÃ®chir les commentaires'}
      </button>
    </div>
  );
};

const CoachDashboard = ({ t, lang, onBack, onLogout, coachUser }) => {
  // v9.2.5: Protection ABSOLUE contre les erreurs - Valeurs par dÃ©faut GARANTIES
  const safeCoachUser = coachUser || {};
  
  // v9.2.5: Ãtat de chargement initial
  const [dashboardReady, setDashboardReady] = useState(false);
  const [loadError, setLoadError] = useState(null);
  
  // Email Super Admin
  // v9.5.6: Liste des Super Admins autorisÃ©s
  const SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
  const isSuperAdmin = SUPER_ADMIN_EMAILS.some(email => 
    (safeCoachUser?.email || '').toLowerCase() === email.toLowerCase()
  );
  
  // v9.2.5: Valeurs par dÃ©faut TOUJOURS prÃ©sentes pour Ã©viter page blanche
  const displayEmail = safeCoachUser?.email || 'Partenaire';
  const displayName = safeCoachUser?.name || 'Partenaire';
  
  // v8.9.5: Helper pour crÃ©er les headers avec l'email coach (isolation des donnÃ©es)
  const getCoachHeaders = () => ({
    headers: { 'X-User-Email': safeCoachUser?.email || '' }
  });
  
  // v9.2.5: Marquer le dashboard comme prÃªt aprÃ¨s le premier rendu
  useEffect(() => {
    const timer = setTimeout(() => {
      setDashboardReady(true);
      console.log('[DASHBOARD] v9.2.5 Dashboard prÃªt');
    }, 100);
    return () => clearTimeout(timer);
  }, []);
  
  // === PANNEAU SUPER ADMIN ===
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  
  // === v9.2.7: QUICK CONTROL - Interrupteurs minimalistes Super Admin ===
  const [showQuickControl, setShowQuickControl] = useState(false);
  const [platformSettings, setPlatformSettings] = useState({
    partner_access_enabled: true,
    maintenance_mode: false
  });
  const quickControlRef = useRef(null);
  
  // v9.2.7: Charger les settings plateforme au dÃ©marrage
  useEffect(() => {
    if (isSuperAdmin && safeCoachUser?.email) {
      axios.get(`${API}/platform-settings`, { headers: { 'X-User-Email': safeCoachUser.email } })
        .then(res => setPlatformSettings(res.data))
        .catch(err => console.log('[SETTINGS] Error loading:', err));
    }
  }, [isSuperAdmin, safeCoachUser?.email]);
  
  // v9.2.7: Toggle setting avec feedback visuel
  const togglePlatformSetting = async (key) => {
    const newValue = !platformSettings[key];
    setPlatformSettings(prev => ({ ...prev, [key]: newValue }));
    
    try {
      await axios.put(`${API}/platform-settings`, 
        { [key]: newValue },
        { headers: { 'X-User-Email': safeCoachUser?.email } }
      );
      console.log(`[SETTINGS] ${key} toggled to ${newValue}`);
    } catch (err) {
      // Rollback on error
      setPlatformSettings(prev => ({ ...prev, [key]: !newValue }));
      console.error('[SETTINGS] Toggle error:', err);
    }
  };
  
  // v9.2.7: Fermer Quick Control si clic extÃ©rieur
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (quickControlRef.current && !quickControlRef.current.contains(e.target)) {
        setShowQuickControl(false);
      }
    };
    if (showQuickControl) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showQuickControl]);
  
  // === STRIPE CONNECT v8.9.3 (uniquement pour les coachs, pas Bassi) ===
  const [stripeConnectStatus, setStripeConnectStatus] = useState(null);
  const [stripeConnectLoading, setStripeConnectLoading] = useState(false);
  
  // === v13.0: BOUTIQUE CRÃDITS ===
  const [creditPacks, setCreditPacks] = useState([]);
  const [loadingPacks, setLoadingPacks] = useState(false);
  const [purchasingPack, setPurchasingPack] = useState(null);
  
  // === v13.1: PRIX DES SERVICES (configurÃ©s par Super Admin) ===
  const [servicePrices, setServicePrices] = useState({
    campaign: 1,
    ai_conversation: 1,
    promo_code: 1
  });
  
  // === CRÃDITS COACH v8.9.7 ===
  // v9.2.3: Initialiser selon le rÃ´le immÃ©diatement pour Ã©viter page blanche
  const [coachCredits, setCoachCredits] = useState(isSuperAdmin ? -1 : 0); // -1=illimitÃ© (Super Admin), 0=dÃ©faut
  
  // === v8.9.9: VITRINE COACH ===
  // v67: Super Admin vitrine = homepage publique, JAMAIS /coach/bassi
  const [coachUsername, setCoachUsername] = useState(null);
  const coachVitrineUrl = isSuperAdmin
    ? `${window.location.origin}/?visitor=true`
    : coachUsername ? `${window.location.origin}/coach/${coachUsername}` : null;
  
  // === v9.1.3: MARQUE BLANCHE - platform_name ===
  const [coachPlatformName, setCoachPlatformName] = useState(null);
  const dashboardTitle = coachPlatformName || (isSuperAdmin ? 'Afroboost' : 'Mon Espace Partenaire');
  
  // v13.1: Helper - vÃ©rifier si assez de crÃ©dits pour un service
  const hasCreditsFor = (serviceType) => {
    if (isSuperAdmin) return true; // Super Admin = accÃ¨s illimitÃ©
    if (coachCredits === -1) return true; // CrÃ©dits illimitÃ©s
    const requiredCredits = servicePrices[serviceType] || 1;
    return coachCredits >= requiredCredits;
  };
  
  // Helper: crÃ©dits insuffisants (pour info, mais plus de grisage v9.1.3)
  const hasInsufficientCredits = !isSuperAdmin && coachCredits !== null && coachCredits !== -1 && coachCredits <= 0;

  // v9.2.4: Charger profil coach avec protection try-catch complÃ¨te
  useEffect(() => {
    const loadProfile = async () => {
      try {
        if (safeCoachUser?.email) {
          const res = await axios.get(`${BACKEND_URL}/api/coach/profile`, {
            headers: { 'X-User-Email': safeCoachUser.email }
          });
          setCoachCredits(res.data?.credits ?? 0);
          // v8.9.9: RÃ©cupÃ©rer username pour vitrine
          const username = res.data?.name?.toLowerCase().replace(/\s+/g, '-') || res.data?.id || safeCoachUser.email.split('@')[0];
          setCoachUsername(isSuperAdmin ? 'bassi' : username);
          // v9.1.3: RÃ©cupÃ©rer platform_name pour marque blanche
          setCoachPlatformName(res.data?.platform_name || null);
        }
      } catch (err) {
        // v9.2.4: FORCE AFFICHAGE - Dashboard s'affiche TOUJOURS mÃªme si profil inexistant
        console.warn('[COACH] v9.2.4 Profil non trouvÃ©, utilisation des valeurs par dÃ©faut:', err?.response?.status || err?.message);
        // Pour Super Admin: crÃ©dits illimitÃ©s
        if (isSuperAdmin) {
          setCoachCredits(-1);
          setCoachUsername('bassi');
          setCoachPlatformName('Afroboost');
        } else {
          // Pour les partenaires: valeurs par dÃ©faut (pas de blocage)
          setCoachCredits(0);
          setCoachUsername(safeCoachUser?.name?.toLowerCase().replace(/\s+/g, '-') || safeCoachUser?.email?.split('@')[0] || 'partenaire');
          setCoachPlatformName(null);
        }
      }
    };
    loadProfile();
  }, [safeCoachUser?.email, safeCoachUser?.name, isSuperAdmin]);

  // === v9.5.8: FONCTION DÃDUCTION CRÃDITS ===
  // DÃ©duit 1 crÃ©dit et affiche message si solde Ã©puisÃ©
  const consumeCredit = async (action = "action") => {
    // Super Admin ne consomme jamais de crÃ©dits
    if (isSuperAdmin) {
      console.log('[CREDITS] Super Admin - action gratuite');
      return { success: true, bypassed: true };
    }
    
    // VÃ©rifier le solde local d'abord
    if (coachCredits <= 0) {
      setValidationMessage('â ï¸ Solde Ã©puisÃ©. Achetez un pack pour continuer.');
      setTimeout(() => setValidationMessage(''), 5000);
      return { success: false, error: "CrÃ©dits insuffisants" };
    }
    
    try {
      const res = await axios.post(`${BACKEND_URL}/api/credits/deduct`, 
        { action },
        { headers: { 'X-User-Email': safeCoachUser?.email } }
      );
      
      // Mettre Ã  jour le solde local
      setCoachCredits(res.data?.credits_remaining ?? coachCredits - 1);
      console.log(`[CREDITS] ${action} - 1 crÃ©dit dÃ©duit, reste: ${res.data?.credits_remaining}`);
      
      return { success: true, credits_remaining: res.data?.credits_remaining };
    } catch (err) {
      console.error('[CREDITS] Erreur dÃ©duction:', err);
      if (err?.response?.status === 402) {
        setValidationMessage('â ï¸ Solde Ã©puisÃ©. Achetez un pack pour continuer.');
        setTimeout(() => setValidationMessage(''), 5000);
        setCoachCredits(0);
      }
      return { success: false, error: err?.response?.data?.detail || "Erreur" };
    }
  };

  // === v9.5.8: BLOQUEUR D'ACTION SI CRÃDITS ÃPUISÃS ===
  const checkCreditsBeforeAction = () => {
    if (isSuperAdmin) return true;
    if (coachCredits <= 0) {
      setValidationMessage('â ï¸ Solde Ã©puisÃ©. Achetez un pack pour continuer.');
      setTimeout(() => setValidationMessage(''), 5000);
      return false;
    }
    return true;
  };

  // VÃ©rifier le statut Stripe Connect au chargement (pour les coachs seulement)
  useEffect(() => {
    if (coachUser?.email && !isSuperAdmin) {
      axios.get(`${API}/coach/stripe-connect/status`, {
        headers: { 'X-User-Email': coachUser.email }
      }).then(res => {
        setStripeConnectStatus(res.data);
      }).catch(() => {
        setStripeConnectStatus({ connected: false, status: 'error' });
      });
    }
  }, [coachUser?.email, isSuperAdmin]);

  // Fonction pour lancer l'onboarding Stripe Connect
  const handleStripeConnect = async () => {
    if (!coachUser?.email || stripeConnectLoading) return;
    setStripeConnectLoading(true);
    try {
      const res = await axios.post(`${API}/coach/stripe-connect/onboard`, {
        email: coachUser.email
      });
      if (res.data?.url) {
        window.open(res.data.url, '_blank');
      }
    } catch (err) {
      console.error('[STRIPE-CONNECT] Erreur:', err);
      alert('Erreur lors de la connexion Stripe');
    } finally {
      setStripeConnectLoading(false);
    }
  };
  
  // === v13.0: BOUTIQUE CRÃDITS - Charger les packs disponibles ===
  useEffect(() => {
    const loadCreditPacks = async () => {
      setLoadingPacks(true);
      try {
        const res = await axios.get(`${API}/credit-packs`);
        setCreditPacks(res.data || []);
      } catch (err) {
        console.error('[BOUTIQUE] Erreur chargement packs:', err);
      } finally {
        setLoadingPacks(false);
      }
    };
    if (!isSuperAdmin) {
      loadCreditPacks();
    }
  }, [isSuperAdmin]);

  // v13.0: Fonction pour acheter un pack de crÃ©dits
  const handleBuyPack = async (pack) => {
    if (!coachUser?.email || purchasingPack) return;
    setPurchasingPack(pack.id);
    try {
      const res = await axios.post(`${API}/stripe/create-credit-checkout`, 
        { pack_id: pack.id },
        { headers: { 'X-User-Email': coachUser.email } }
      );
      if (res.data?.checkout_url) {
        window.location.href = res.data.checkout_url;
      }
    } catch (err) {
      console.error('[BOUTIQUE] Erreur achat:', err);
      alert(err.response?.data?.detail || 'Erreur lors de l\'achat');
    } finally {
      setPurchasingPack(null);
    }
  };

  // === v13.1: Charger les prix des services depuis platform-settings ===
  useEffect(() => {
    const loadServicePrices = async () => {
      try {
        const res = await axios.get(`${API}/platform-settings`, {
          headers: { 'X-User-Email': coachUser?.email || '' }
        });
        if (res.data?.service_prices) {
          setServicePrices(res.data.service_prices);
          console.log('[SERVICE-PRICES] ChargÃ©s:', res.data.service_prices);
        }
      } catch (err) {
        console.log('[SERVICE-PRICES] Erreur (utilisation prix par dÃ©faut):', err.message);
      }
    };
    loadServicePrices();
  }, [coachUser?.email]);
  
  // === PERSISTANCE ONGLET : Restaurer l'onglet depuis localStorage ===
  const [tab, setTab] = useState(() => {
    try {
      const savedTab = localStorage.getItem(COACH_TAB_KEY);
      // v36: Migration â "concept" et "courses" redirigent vers "offers"
      if (savedTab && ['reservations', 'concept', 'courses', 'offers', 'payments', 'page-vente', 'codes', 'campaigns', 'articles', 'media', 'conversations'].includes(savedTab)) {
        const migratedTab = savedTab === 'payments' ? 'page-vente'
          : (savedTab === 'concept' || savedTab === 'courses') ? 'offers'
          : savedTab;
        console.log('[COACH] â Onglet restaurÃ©:', migratedTab);
        return migratedTab;
      }
    } catch (e) {}
    return "reservations";
  });

  // v37.2: Sous-onglet du HUB "Gestion" â 4 sections centralisÃ©es
  const [offersSubTab, setOffersSubTab] = useState('contenus');

  // v37.2: Auto-scroll + auto-load audio course on sub-tab change
  const handleSubTabChange = (subTabId) => {
    setOffersSubTab(subTabId);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    // v44: Plus besoin d'auto-select cours â Studio Audio est autonome
  };

  // === PARTAGE COACH ===
  const [linkCopied, setLinkCopied] = useState(false);
  
  // === MODE VUE VISITEUR (communique avec ChatWidget via evenement) ===
  const [isVisitorPreviewActive, setIsVisitorPreviewActive] = useState(false);
  
  const toggleVisitorPreview = () => {
    const newState = !isVisitorPreviewActive;
    setIsVisitorPreviewActive(newState);
    // Emettre l'evenement pour ChatWidget
    window.dispatchEvent(new CustomEvent('afroboost:visitorPreview', { 
      detail: { enabled: newState } 
    }));
    console.log('[COACH] Vue Visiteur:', newState ? 'activee' : 'desactivee');
  };

  const [reservations, setReservations] = useState([]);
  const [reservationsSearch, setReservationsSearch] = useState(''); // Recherche locale rÃ©servations
  const [reservationPagination, setReservationPagination] = useState({ page: 1, limit: 20, total: 0, pages: 0 });
  const [loadingReservations, setLoadingReservations] = useState(false);
  const [courses, setCourses] = useState([]);
  const [offers, setOffers] = useState([]);
  const [offersSearch, setOffersSearch] = useState(''); // Recherche locale offres
  const [nextExpiration, setNextExpiration] = useState(null); // v69: prochaine expiration
  const [users, setUsers] = useState([]);
  const [paymentLinks, setPaymentLinks] = useState({ stripe: "", paypal: "", twint: "", coachWhatsapp: "", coachNotificationEmail: "", coachNotificationPhone: "" });
  // v15.0: Config paiement multi-vendeurs
  const [vendorPaymentConfig, setVendorPaymentConfig] = useState({});
  const [concept, setConcept] = useState({ appName: "Afroboost", description: "", heroImageUrl: "", logoUrl: "", faviconUrl: "", termsText: "", googleReviewsUrl: "", defaultLandingSection: "sessions", externalLink1Title: "", externalLink1Url: "", externalLink2Title: "", externalLink2Url: "", paymentTwint: false, paymentPaypal: false, paymentCreditCard: false, eventPosterEnabled: false, eventPosterMediaUrl: "" });
  const [discountCodes, setDiscountCodes] = useState([]);
  const [codesSearch, setCodesSearch] = useState(''); // Recherche locale codes promo
  const [newCode, setNewCode] = useState({ code: "", type: "", value: "", assignedEmails: [], courses: [], maxUses: "", expiresAt: "", batchCount: 1, prefix: "" });
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [selectedBeneficiaries, setSelectedBeneficiaries] = useState([]); // Multi-select pour bÃ©nÃ©ficiaires
  const [editingCode, setEditingCode] = useState(null); // Pour l'Ã©dition individuelle des codes
  const [newCourse, setNewCourse] = useState({ name: "", weekday: 0, time: "18:30", locationName: "", mapsUrl: "" });
  const [newOffer, setNewOffer] = useState({
    name: "", price: 0, visible: true, description: "", keywords: "",
    images: ["", "", "", "", ""], // 5 champs d'images
    category: "service", isProduct: false, variants: null, tva: 0, shippingCost: 0, stock: -1,
    duration_value: '', duration_unit: '', is_auto_prolong: true
  });
  const [editingOfferId, setEditingOfferId] = useState(null); // Pour mode Ã©dition
  const fileInputRef = useRef(null);
  
  // Scanner state
  const [showScanner, setShowScanner] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [scanError, setScanError] = useState(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  
  // Manual contact form state
  const [showManualContactForm, setShowManualContactForm] = useState(false);
  const [manualContact, setManualContact] = useState({ name: "", email: "", whatsapp: "" });

  // Custom Emojis state
  const [customEmojis, setCustomEmojis] = useState([]);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [newEmojiName, setNewEmojiName] = useState("");
  const emojiInputRef = useRef(null);

  // ========== v44: STUDIO AUDIO AUTONOME â indÃ©pendant des cours ==========
  const [showAudioModal, setShowAudioModal] = useState(false);
  const [selectedCourseForAudio, setSelectedCourseForAudio] = useState(null); // legacy compat
  const [audioTracks, setAudioTracks] = useState([]);
  const [savingPlaylist, setSavingPlaylist] = useState(false);
  const [uploadingAudio, setUploadingAudio] = useState(false);
  const [editingTrackId, setEditingTrackId] = useState(null);
  const [dragOverIndex, setDragOverIndex] = useState(null);
  const [draggedTrackId, setDraggedTrackId] = useState(null);
  const audioFileInputRef = useRef(null);
  const audioCoverInputRef = useRef(null);
  const [coverUploadTrackId, setCoverUploadTrackId] = useState(null);
  const [audioLoaded, setAudioLoaded] = useState(false);

  // v44: Chargement automatique des pistes audio depuis l'API autonome
  const authHeaders = { 'X-User-Email': coachUser?.email || '' };
  const loadAudioTracks = async () => {
    try {
      const res = await axios.get(`${API}/audio-tracks`, { headers: authHeaders });
      const apiTracks = res.data.tracks || [];

      // v44: Migration automatique â si l'API est vide mais des cours ont des audio_tracks legacy, migrer
      if (apiTracks.length === 0 && courses.length > 0) {
        const legacyTracks = [];
        courses.forEach(course => {
          if (course.audio_tracks && course.audio_tracks.length > 0) {
            course.audio_tracks.forEach(t => legacyTracks.push(t));
          }
        });
        if (legacyTracks.length > 0) {
          console.log(`[AUDIO] ð Migration de ${legacyTracks.length} pistes legacy...`);
          const migrated = [];
          for (const t of legacyTracks) {
            try {
              const createRes = await axios.post(`${API}/audio-tracks`, {
                url: t.url || '', title: t.title || 'Sans titre',
                cover_url: t.cover_url || null, description: t.description || '',
                price: parseFloat(t.price) || 0, preview_duration: parseInt(t.preview_duration) || 30,
                duration: t.duration || null, visible: t.visible !== false,
                order: migrated.length
              }, { headers: { 'Content-Type': 'application/json', ...authHeaders } });
              migrated.push(createRes.data.track);
              console.log(`[AUDIO] â MigrÃ©: ${t.title}`);
            } catch (migErr) {
              console.error(`[AUDIO] â Erreur migration ${t.title}:`, migErr);
            }
          }
          setAudioTracks(migrated);
          setAudioLoaded(true);
          console.log(`[AUDIO] ð Migration terminÃ©e: ${migrated.length}/${legacyTracks.length}`);
          return;
        }
      }

      setAudioTracks(apiTracks);
      setAudioLoaded(true);
      console.log(`[AUDIO] â ${res.data.count} pistes chargÃ©es`);
    } catch (err) {
      console.error("[AUDIO] Erreur chargement:", err);
      setAudioLoaded(true);
    }
  };

  useEffect(() => {
    if (coachUser?.email && !audioLoaded && courses.length >= 0) {
      loadAudioTracks();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coachUser?.email, courses.length]);

  // Legacy compat â openAudioModal kept for modal version
  const openAudioModal = (course) => {
    setSelectedCourseForAudio(course);
    setShowAudioModal(true);
  };

  // v58: Upload en chunks pour gros fichiers (contourne limite Vercel 4.5MB)
  const uploadFileInChunks = async (file) => {
    const CHUNK_SIZE = 3 * 1024 * 1024; // 3MB par chunk
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
    const uploadId = Date.now().toString(36) + Math.random().toString(36).substr(2, 5);

    console.log(`[AUDIO] ð¦ Upload en ${totalChunks} chunks pour "${file.name}" (${(file.size / 1024 / 1024).toFixed(1)}MB)`);

    let finalUrl = null;
    for (let i = 0; i < totalChunks; i++) {
      const start = i * CHUNK_SIZE;
      const end = Math.min(start + CHUNK_SIZE, file.size);
      const chunk = file.slice(start, end);

      const formData = new FormData();
      formData.append('file', chunk, `chunk_${i}`);
      formData.append('upload_id', uploadId);
      formData.append('chunk_index', i.toString());
      formData.append('total_chunks', totalChunks.toString());
      formData.append('original_name', file.name);
      formData.append('content_type', file.type || 'audio/mpeg');
      formData.append('asset_type', 'audio');

      console.log(`[AUDIO] â¬ï¸ Chunk ${i + 1}/${totalChunks} (${((end - start) / 1024 / 1024).toFixed(1)}MB)`);
      const res = await axios.post(`${API}/coach/upload-chunk`, formData, {
        headers: { 'Content-Type': 'multipart/form-data', ...authHeaders }
      });

      if (res.data.url) {
        finalUrl = res.data.url;
        console.log(`[AUDIO] â Fichier assemblÃ©: ${finalUrl}`);
      }
    }
    return finalUrl;
  };

  // v58: Upload audio â chunked pour gros fichiers
  const handleAudioFileUpload = async (files) => {
    if (!files || files.length === 0) return;
    setUploadingAudio(true);

    const MAX_AUDIO_SIZE = 15 * 1024 * 1024; // 15MB max
    const CHUNK_THRESHOLD = 3.5 * 1024 * 1024; // Chunked au-delÃ  de 3.5MB
    for (const file of files) {
      try {
        if (file.size > MAX_AUDIO_SIZE) {
          alert(`â ï¸ Le fichier "${file.name}" fait ${(file.size / 1024 / 1024).toFixed(1)}MB.\nMaximum : 15MB.`);
          continue;
        }

        let uploadUrl;
        if (file.size > CHUNK_THRESHOLD) {
          // v58: Upload en chunks pour les gros fichiers
          console.log(`[AUDIO] Fichier > 3.5MB, upload en chunks...`);
          uploadUrl = await uploadFileInChunks(file);
          if (!uploadUrl) {
            alert(`â ï¸ Erreur lors de l'upload de "${file.name}". RÃ©essayez.`);
            continue;
          }
        } else {
          // Upload normal pour les petits fichiers
          const formData = new FormData();
          formData.append('file', file);
          formData.append('asset_type', 'audio');
          const uploadRes = await axios.post(`${API}/coach/upload-asset`, formData, {
            headers: { 'Content-Type': 'multipart/form-data', ...authHeaders }
          });
          uploadUrl = uploadRes.data.url;
        }

        // 2. CrÃ©er la piste dans la collection audio_tracks
        const trackRes = await axios.post(`${API}/audio-tracks`, {
          url: uploadUrl,
          title: file.name.replace(/\.[^.]+$/, ''),
          price: 0,
          preview_duration: 30,
          visible: true
        }, { headers: authHeaders });

        setAudioTracks(prev => [...prev, trackRes.data.track]);
        console.log(`[AUDIO] â Piste crÃ©Ã©e: ${trackRes.data.track.title}`);
      } catch (err) {
        console.error("Erreur upload audio:", err);
        alert(`Erreur upload "${file.name}": ${err.response?.data?.detail || err.message}`);
      }
    }
    setUploadingAudio(false);
  };

  // Upload cover image pour une piste
  const handleCoverUpload = async (file, trackId) => {
    if (!file) return;
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('asset_type', 'image');
      const res = await axios.post(`${API}/coach/upload-asset`, formData, {
        headers: { 'Content-Type': 'multipart/form-data', ...authHeaders }
      });
      // Mettre Ã  jour localement ET dans l'API
      await axios.put(`${API}/audio-tracks/${trackId}`, { cover_url: res.data.url }, { headers: authHeaders });
      setAudioTracks(prev => prev.map(t => t.id === trackId ? { ...t, cover_url: res.data.url } : t));
    } catch (err) {
      console.error("Erreur upload cover:", err);
      alert("Erreur upload de la pochette");
    }
  };

  // v44: Mettre Ã  jour un champ â sauvegarde immÃ©diate dans l'API
  const updateTrackField = async (trackId, field, value) => {
    setAudioTracks(prev => prev.map(t => t.id === trackId ? { ...t, [field]: value } : t));
    try {
      await axios.put(`${API}/audio-tracks/${trackId}`, { [field]: value }, { headers: authHeaders });
    } catch (err) {
      console.error(`[AUDIO] Erreur maj ${field}:`, err);
    }
  };

  // v44: Supprimer une piste â suppression immÃ©diate dans l'API
  const removeTrack = async (trackId) => {
    setAudioTracks(prev => prev.filter(t => t.id !== trackId).map((t, i) => ({ ...t, order: i })));
    try {
      await axios.delete(`${API}/audio-tracks/${trackId}`, { headers: authHeaders });
      console.log(`[AUDIO] ðï¸ Piste supprimÃ©e: ${trackId}`);
    } catch (err) {
      console.error("[AUDIO] Erreur suppression:", err);
    }
  };

  // Drag & Drop rÃ©ordonnement (Desktop)
  const handleTrackDragStart = (e, trackId) => {
    setDraggedTrackId(trackId);
    e.dataTransfer.effectAllowed = 'move';
  };
  const handleTrackDragOver = (e, index) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverIndex(index);
  };
  const handleTrackDrop = (e, targetIndex) => {
    e.preventDefault();
    if (!draggedTrackId) return;
    const fromIndex = audioTracks.findIndex(t => t.id === draggedTrackId);
    if (fromIndex === targetIndex) { setDragOverIndex(null); setDraggedTrackId(null); return; }
    const updated = [...audioTracks];
    const [moved] = updated.splice(fromIndex, 1);
    updated.splice(targetIndex, 0, moved);
    setAudioTracks(updated.map((t, i) => ({ ...t, order: i })));
    setDragOverIndex(null);
    setDraggedTrackId(null);
  };

  // v46: Touch Drag & Drop (Mobile/Tablette)
  const touchStartRef = useRef(null);
  const touchTrackIdRef = useRef(null);
  const handleTrackTouchStart = (e, trackId) => {
    touchTrackIdRef.current = trackId;
    touchStartRef.current = { y: e.touches[0].clientY };
    setDraggedTrackId(trackId);
  };
  const handleTrackTouchMove = (e, trackListEl) => {
    if (!touchTrackIdRef.current || !trackListEl) return;
    e.preventDefault(); // empÃªche le scroll pendant le drag
    const touchY = e.touches[0].clientY;
    const children = Array.from(trackListEl.children);
    for (let i = 0; i < children.length; i++) {
      const rect = children[i].getBoundingClientRect();
      if (touchY >= rect.top && touchY <= rect.bottom) {
        setDragOverIndex(i);
        break;
      }
    }
  };
  const handleTrackTouchEnd = () => {
    if (!touchTrackIdRef.current || dragOverIndex === null) {
      setDragOverIndex(null); setDraggedTrackId(null); touchTrackIdRef.current = null;
      return;
    }
    const sorted = [...audioTracks].sort((a, b) => a.order - b.order);
    const fromIndex = sorted.findIndex(t => t.id === touchTrackIdRef.current);
    if (fromIndex !== -1 && fromIndex !== dragOverIndex) {
      const updated = [...sorted];
      const [moved] = updated.splice(fromIndex, 1);
      updated.splice(dragOverIndex, 0, moved);
      setAudioTracks(updated.map((t, i) => ({ ...t, order: i })));
    }
    setDragOverIndex(null); setDraggedTrackId(null); touchTrackIdRef.current = null;
  };

  // v44: Sauvegarder = rÃ©-ordonner toutes les pistes dans l'API
  const saveAudioStudio = async () => {
    setSavingPlaylist(true);
    try {
      const sortedTracks = [...audioTracks].sort((a, b) => a.order - b.order);
      await axios.put(`${API}/audio-tracks/reorder`, {
        track_ids: sortedTracks.map(t => t.id)
      }, { headers: authHeaders });
      alert(`â Studio Audio sauvegardÃ© (${sortedTracks.length} pistes)`);
    } catch (err) {
      console.error("Erreur sauvegarde studio:", err);
      alert("Erreur lors de la sauvegarde du Studio Audio");
    } finally {
      setSavingPlaylist(false);
    }
  };

  // === PERSISTANCE ONGLET : Sauvegarder l'onglet actif ===
  useEffect(() => {
    if (tab) {
      localStorage.setItem(COACH_TAB_KEY, tab);
      console.log('[COACH] ð¾ Onglet sauvegardÃ©:', tab);
    }
  }, [tab]);
  
  // === v9.3.7: MÃMOIRE TOTALE - Auto-save Concept avec debounce ===
  const conceptSaveTimeoutRef = useRef(null);
  const [conceptSaveStatus, setConceptSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
  const isConceptLoaded = useRef(false); // Ãviter save au premier chargement
  
  useEffect(() => {
    // Ne pas sauvegarder au premier chargement
    if (!isConceptLoaded.current) {
      isConceptLoaded.current = true;
      return;
    }
    
    // Debounce: attendre 1 seconde d'inactivitÃ© avant de sauvegarder
    if (conceptSaveTimeoutRef.current) {
      clearTimeout(conceptSaveTimeoutRef.current);
    }
    
    conceptSaveTimeoutRef.current = setTimeout(async () => {
      try {
        setConceptSaveStatus('saving');
        await axios.put(`${API}/concept`, concept, getCoachHeaders());
        setConceptSaveStatus('saved');
        console.log('[COACH] v9.3.7 Concept auto-sauvegardÃ©');
        // Cacher le statut aprÃ¨s 2 secondes
        setTimeout(() => setConceptSaveStatus(null), 2000);
      } catch (err) {
        console.error('[COACH] Erreur auto-save concept:', err);
        setConceptSaveStatus('error');
      }
    }, 1000);
    
    return () => {
      if (conceptSaveTimeoutRef.current) {
        clearTimeout(conceptSaveTimeoutRef.current);
      }
    };
  }, [concept]);
  
  // === v9.3.7: MÃMOIRE TOTALE - Auto-save PaymentLinks avec debounce ===
  const paymentSaveTimeoutRef = useRef(null);
  const [paymentSaveStatus, setPaymentSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
  const isPaymentLoaded = useRef(false); // Ãviter save au premier chargement
  
  useEffect(() => {
    // Ne pas sauvegarder au premier chargement
    if (!isPaymentLoaded.current) {
      isPaymentLoaded.current = true;
      return;
    }
    
    // Debounce: attendre 1 seconde d'inactivitÃ© avant de sauvegarder
    if (paymentSaveTimeoutRef.current) {
      clearTimeout(paymentSaveTimeoutRef.current);
    }
    
    paymentSaveTimeoutRef.current = setTimeout(async () => {
      try {
        setPaymentSaveStatus('saving');
        await axios.put(`${API}/payment-links`, paymentLinks, getCoachHeaders());
        setPaymentSaveStatus('saved');
        console.log('[COACH] v9.3.7 Payment Links auto-sauvegardÃ©s');
        // Cacher le statut aprÃ¨s 2 secondes
        setTimeout(() => setPaymentSaveStatus(null), 2000);
      } catch (err) {
        console.error('[COACH] Erreur auto-save payment links:', err);
        setPaymentSaveStatus('error');
      }
    }, 1000);
    
    return () => {
      if (paymentSaveTimeoutRef.current) {
        clearTimeout(paymentSaveTimeoutRef.current);
      }
    };
  }, [paymentLinks]);
  
  // === FONCTION PARTAGE COACH ===
  // v8.9.9: Partager le lien de la vitrine coach
  const handleCoachShareLink = async () => {
    const shareUrl = coachVitrineUrl || window.location.origin;
    const result = await copyToClipboard(shareUrl);
    if (result.success) {
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
      console.log('[COACH] Lien vitrine copiÃ©:', shareUrl);
    }
  };
  
  // === DÃCONNEXION SÃCURISÃE ===
  const handleSecureLogout = () => {
    try {
      // Vider localStorage (sauf les clÃ©s critiques)
      const keysToRemove = [
        COACH_TAB_KEY,
        COACH_SESSION_KEY,
        'afroboost_coach_user',
        'afroboost_identity',
        'af_chat_client',
        'af_chat_session'
      ];
      keysToRemove.forEach(key => localStorage.removeItem(key));
      
      // Vider sessionStorage
      sessionStorage.clear();
      
      console.log('[COACH] ðª DÃ©connexion sÃ©curisÃ©e effectuÃ©e');
      
      // Appeler la fonction onLogout du parent
      if (onLogout) onLogout();
    } catch (err) {
      console.error('[COACH] â Erreur dÃ©connexion:', err);
      // Forcer la dÃ©connexion mÃªme en cas d'erreur
      if (onLogout) onLogout();
    }
  };

  // Fonction pour charger les rÃ©servations avec pagination
  const loadReservations = async (page = 1, limit = 20) => {
    setLoadingReservations(true);
    try {
      const res = await axios.get(`${API}/reservations?page=${page}&limit=${limit}`, getCoachHeaders());
      setReservations(res.data.data);
      setReservationPagination(res.data.pagination);
    } catch (err) {
      console.error("Error loading reservations:", err);
    } finally {
      setLoadingReservations(false);
    }
  };

  useEffect(() => {
    const loadData = async () => {
      try {
        // v8.9.5: Charger les rÃ©servations avec isolation coach_id
        // Toutes les requÃªtes passent le header X-User-Email pour filtrage par coach_id
        const headers = getCoachHeaders();
        const resPromise = axios.get(`${API}/reservations?page=1&limit=20`, headers);
        const [res, crs, off, usr, lnk, cpt, cds] = await Promise.all([
          resPromise, axios.get(`${API}/courses`, headers), axios.get(`${API}/offers`, headers),
          axios.get(`${API}/users`, headers), axios.get(`${API}/payment-links`, headers),
          axios.get(`${API}/concept`, headers), axios.get(`${API}/discount-codes`, headers)
        ]);
        // RÃ©servations avec pagination
        setReservations(res.data.data);
        setReservationPagination(res.data.pagination);
        
        setCourses(crs.data); setOffers(off.data); setUsers(usr.data);
        setPaymentLinks(lnk.data); setConcept(cpt.data); setDiscountCodes(cds.data);

        // v69: Charger prochaine expiration d'offre
        try {
          const expRes = await axios.get(`${API}/offers/next-expiration`, headers);
          setNextExpiration(expRes.data);
        } catch (expErr) { console.warn('[V69] Next expiration:', expErr); }

        // v15.0: Charger la config paiement multi-vendeurs
        try {
          const pcRes = await axios.get(`${API}/api/payment-config`, headers);
          setVendorPaymentConfig(pcRes.data || {});
        } catch (pcErr) { console.warn('[PAYMENT-CONFIG] Load:', pcErr); }

        // === SANITIZE DATA: Nettoyer automatiquement les donnÃ©es fantÃ´mes ===
        try {
          const sanitizeResult = await axios.post(`${API}/sanitize-data`);
          if (sanitizeResult.data.stats?.codes_cleaned > 0) {
            console.log(`ð§¹ Nettoyage: ${sanitizeResult.data.stats.codes_cleaned} codes promo nettoyÃ©s`);
            // Recharger les codes promo aprÃ¨s nettoyage
            const updatedCodes = await axios.get(`${API}/discount-codes`);
            setDiscountCodes(updatedCodes.data);
          }
        } catch (sanitizeErr) {
          console.warn("Sanitize warning:", sanitizeErr);
        }
      } catch (err) { console.error("Error:", err); }
    };
    loadData();
  }, []);

  // Fonction de nettoyage manuel (peut Ãªtre appelÃ©e depuis l'interface)
  const manualSanitize = async () => {
    try {
      const result = await axios.post(`${API}/sanitize-data`);
      const stats = result.data.stats;
      alert(`ð§¹ Nettoyage terminÃ©!\n\nâ¢ ${stats.codes_cleaned} codes promo nettoyÃ©s\nâ¢ ${stats.valid_offers} offres valides\nâ¢ ${stats.valid_courses} cours valides\nâ¢ ${stats.valid_users} contacts valides`);
      // Recharger les codes promo
      const updatedCodes = await axios.get(`${API}/discount-codes`);
      setDiscountCodes(updatedCodes.data);
    } catch (err) {
      console.error("Erreur nettoyage:", err);
      alert("Erreur lors du nettoyage");
    }
  };

  // Get unique customers for beneficiary dropdown (filtrage local supplÃ©mentaire)
  const uniqueCustomers = Array.from(new Map(
    [...reservations.map(r => ({ name: r.userName, email: r.userEmail })), ...users.map(u => ({ name: u.name, email: u.email }))]
    .filter(c => c.email && c.name) // Exclure les entrÃ©es sans email ou nom
    .map(c => [c.email, c])
  ).values());

  const exportCSV = async () => {
    try {
      // RÃ©cupÃ©rer TOUTES les rÃ©servations pour l'export (sans pagination)
      const response = await axios.get(`${API}/reservations?all_data=true`);
      const allReservations = response.data.data;
      
      const rows = [
        [t('code'), t('name'), t('email'), "WhatsApp", t('courses'), t('date'), t('time'), t('offer'), t('qty'), t('total'), "Dates multiples"],
        ...allReservations.map(r => {
          const dt = new Date(r.datetime);
          return [r.reservationCode || '', r.userName, r.userEmail, r.userWhatsapp || '', r.courseName, 
            dt.toLocaleDateString('fr-CH'), dt.toLocaleTimeString('fr-CH', { hour: '2-digit', minute: '2-digit' }),
            r.offerName, r.quantity || 1, r.totalPrice || r.price, r.selectedDatesText || ''];
        })
      ];
      const csv = rows.map(r => r.map(c => `"${c}"`).join(",")).join("\n");
      const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" }); // UTF-8 BOM
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; 
      a.download = `afroboost_reservations_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
    } catch (err) {
      console.error("Export error:", err);
      alert("Erreur lors de l'export CSV");
    }
  };

  // Validate reservation by code (for QR scanner)
  const validateReservation = async (code) => {
    try {
      const response = await axios.post(`${API}/reservations/${code}/validate`);
      if (response.data.success) {
        setScanResult({ success: true, reservation: response.data.reservation });
        // Update local state
        setReservations(reservations.map(r => 
          r.reservationCode === code ? { ...r, validated: true } : r
        ));
        // Auto-close after 3 seconds
        setTimeout(() => {
          setShowScanner(false);
          setScanResult(null);
        }, 3000);
      }
    } catch (err) {
      setScanError(err.response?.data?.detail || 'Code non trouvÃ©');
      setTimeout(() => setScanError(null), 3000);
    }
  };

  // Manual code input for validation
  const handleManualValidation = (e) => {
    e.preventDefault();
    const code = e.target.code.value.trim().toUpperCase();
    if (code) {
      validateReservation(code);
      e.target.reset();
    }
  };

  const saveConcept = async () => { 
    try {
      console.log("Saving concept:", concept);
      const response = await axios.put(`${API}/concept`, concept); 
      console.log("Concept saved successfully:", response.data);
      alert("â Concept sauvegardÃ© avec succÃ¨s !");
    } catch (err) {
      console.error("Error saving concept:", err);
      console.error("Error details:", err.response?.data || err.message);
      const errorMessage = err.response?.data?.detail || err.message || "Erreur inconnue";
      alert(`â Erreur lors de la sauvegarde: ${errorMessage}`);
    }
  };
  const savePayments = async () => { await axios.put(`${API}/payment-links`, paymentLinks); alert("Saved!"); };

  // v9.5.8: addCode avec vÃ©rification crÃ©dits
  const addCode = async (e) => {
    e.preventDefault();
    if (!newCode.type || !newCode.value) return;
    
    // v9.5.8: VÃ©rifier les crÃ©dits avant l'action (sauf Super Admin)
    if (!checkCreditsBeforeAction()) return;
    
    // Si mode sÃ©rie activÃ©, utiliser la fonction batch
    if (isBatchMode && newCode.batchCount > 1) {
      await addBatchCodes(e);
      return;
    }
    
    // v9.5.8: Consommer un crÃ©dit pour cette action
    const creditResult = await consumeCredit("creation_code_promo");
    if (!creditResult.success && !creditResult.bypassed) return;
    
    // Mode normal - un seul code
    const beneficiaryEmail = selectedBeneficiaries.length > 0 ? selectedBeneficiaries[0] : null;
    
    const response = await axios.post(`${API}/discount-codes`, {
      code: newCode.code || `CODE-${Date.now().toString().slice(-4)}`,
      type: newCode.type, value: parseFloat(newCode.value),
      assignedEmail: beneficiaryEmail,
      courses: newCode.courses, maxUses: newCode.maxUses ? parseInt(newCode.maxUses) : null,
      expiresAt: newCode.expiresAt || null
    });
    setDiscountCodes([...discountCodes, response.data]);
    setNewCode({ code: "", type: "", value: "", assignedEmails: [], courses: [], maxUses: "", expiresAt: "", batchCount: 1, prefix: "" });
    setSelectedBeneficiaries([]);
  };

  // GÃ©nÃ©ration en sÃ©rie de codes promo - CrÃ©e rÃ©ellement N entrÃ©es distinctes en base
  const addBatchCodes = async (e) => {
    e.preventDefault();
    if (!newCode.type || !newCode.value) return;
    
    const count = Math.min(Math.max(1, parseInt(newCode.batchCount) || 1), 50); // Entre 1 et 50
    const prefix = newCode.prefix?.trim().toUpperCase() || "CODE";
    
    setBatchLoading(true);
    const createdCodes = [];
    
    try {
      // Si plusieurs bÃ©nÃ©ficiaires sÃ©lectionnÃ©s, attribuer un code Ã  chacun
      const beneficiaries = selectedBeneficiaries.length > 0 ? selectedBeneficiaries : [null];
      let codeIndex = 1;
      
      for (let i = 0; i < count; i++) {
        // Attribuer les bÃ©nÃ©ficiaires de maniÃ¨re circulaire si moins de bÃ©nÃ©ficiaires que de codes
        const beneficiaryEmail = beneficiaries[i % beneficiaries.length];
        const codeValue = `${prefix}-${String(codeIndex).padStart(2, '0')}`;
        codeIndex++;
        
        const response = await axios.post(`${API}/discount-codes`, {
          code: codeValue,
          type: newCode.type, 
          value: parseFloat(newCode.value),
          assignedEmail: beneficiaryEmail,
          courses: newCode.courses, // Cours ET produits autorisÃ©s
          maxUses: newCode.maxUses ? parseInt(newCode.maxUses) : null,
          expiresAt: newCode.expiresAt || null
        });
        createdCodes.push(response.data);
      }
      
      setDiscountCodes(prev => [...prev, ...createdCodes]);
      setNewCode({ code: "", type: "", value: "", assignedEmails: [], courses: [], maxUses: "", expiresAt: "", batchCount: 1, prefix: "" });
      setSelectedBeneficiaries([]);
      setIsBatchMode(false);
      alert(`â ${count} codes crÃ©Ã©s avec succÃ¨s !`);
    } catch (error) {
      console.error("Erreur gÃ©nÃ©ration en sÃ©rie:", error);
      // Ajouter les codes dÃ©jÃ  crÃ©Ã©s mÃªme si erreur partielle
      if (createdCodes.length > 0) {
        setDiscountCodes(prev => [...prev, ...createdCodes]);
        alert(`â ï¸ ${createdCodes.length}/${count} codes crÃ©Ã©s. Erreur partielle.`);
      } else {
        alert("â Erreur lors de la crÃ©ation des codes.");
      }
    } finally {
      setBatchLoading(false);
    }
  };
  
  // Toggle sÃ©lection d'un bÃ©nÃ©ficiaire (multi-select)
  const toggleBeneficiarySelection = (email) => {
    setSelectedBeneficiaries(prev => 
      prev.includes(email) 
        ? prev.filter(e => e !== email)
        : [...prev, email]
    );
  };
  
  // Supprimer un article (cours/produit) de la liste des autorisÃ©s (formulaire de crÃ©ation)
  const removeAllowedArticle = (articleId) => {
    setNewCode(prev => ({
      ...prev,
      courses: prev.courses.filter(id => id !== articleId)
    }));
  };
  
  // Supprimer un article d'un code promo EXISTANT (mise Ã  jour immÃ©diate en base)
  const removeArticleFromExistingCode = async (codeId, articleId) => {
    const code = discountCodes.find(c => c.id === codeId);
    if (!code) return;
    
    const updatedCourses = (code.courses || []).filter(id => id !== articleId);
    
    try {
      await axios.put(`${API}/discount-codes/${codeId}`, { courses: updatedCourses });
      setDiscountCodes(prev => prev.map(c => 
        c.id === codeId ? { ...c, courses: updatedCourses } : c
      ));
      console.log(`â Article ${articleId} retirÃ© du code ${code.code}`);
    } catch (error) {
      console.error("Erreur suppression article:", error);
      alert("â Erreur lors de la mise Ã  jour");
    }
  };
  
  // Supprimer un bÃ©nÃ©ficiaire d'un code promo EXISTANT (mise Ã  jour immÃ©diate en base)
  const removeBeneficiaryFromExistingCode = async (codeId) => {
    try {
      await axios.put(`${API}/discount-codes/${codeId}`, { assignedEmail: null });
      setDiscountCodes(prev => prev.map(c => 
        c.id === codeId ? { ...c, assignedEmail: null } : c
      ));
      console.log(`â BÃ©nÃ©ficiaire retirÃ© du code`);
    } catch (error) {
      console.error("Erreur suppression bÃ©nÃ©ficiaire:", error);
      alert("â Erreur lors de la mise Ã  jour");
    }
  };
  
  // Mettre Ã  jour un code promo individuellement
  const updateCodeIndividual = async (codeId, updates) => {
    try {
      const response = await axios.put(`${API}/discount-codes/${codeId}`, updates);
      setDiscountCodes(prev => prev.map(c => c.id === codeId ? { ...c, ...updates } : c));
      setEditingCode(null);
      return true;
    } catch (error) {
      console.error("Erreur mise Ã  jour code:", error);
      alert("â Erreur lors de la mise Ã  jour");
      return false;
    }
  };

  const toggleCode = async (code) => {
    await axios.put(`${API}/discount-codes/${code.id}`, { active: !code.active });
    setDiscountCodes(discountCodes.map(c => c.id === code.id ? { ...c, active: !c.active } : c));
  };

  // v13.8: Ãditer un code promo existant - Charge les donnÃ©es dans le formulaire
  const editCode = (code) => {
    setNewCode({
      code: code.code || "",
      type: code.type || "",
      value: code.value || "",
      assignedEmails: code.assignedEmails || [],
      courses: code.courses || [],
      maxUses: code.maxUses || "",
      expiresAt: code.expiresAt || "",
      batchCount: 1,
      prefix: ""
    });
    setSelectedBeneficiaries(code.assignedEmails || []);
    setEditingCode(code.id); // Marque le code en cours d'Ã©dition
    setIsBatchMode(false); // DÃ©sactive le mode sÃ©rie pour l'Ã©dition
    // Scroll vers le formulaire
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // v13.8: Dupliquer un code promo - Copie les donnÃ©es avec un nouveau nom
  const duplicateCode = (code) => {
    setNewCode({
      code: `${code.code}_COPY`,
      type: code.type || "",
      value: code.value || "",
      assignedEmails: [],
      courses: code.courses || [],
      maxUses: code.maxUses || "",
      expiresAt: code.expiresAt || "",
      batchCount: 1,
      prefix: ""
    });
    setSelectedBeneficiaries([]);
    setEditingCode(null); // Nouveau code, pas d'Ã©dition
    setIsBatchMode(false);
    // Scroll vers le formulaire
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Delete discount code - SUPPRESSION DÃFINITIVE EN BASE + VÃRIFICATION
  const deleteCode = async (codeId) => {
    if (window.confirm("â ï¸ SUPPRESSION DÃFINITIVE\n\nCe code promo sera supprimÃ© de la base de donnÃ©es.\nCette action est irrÃ©versible.\n\nConfirmer la suppression ?")) {
      try {
        await axios.delete(`${API}/discount-codes/${codeId}`);
        setDiscountCodes(prev => prev.filter(c => c.id !== codeId));
        console.log(`â Code ${codeId} supprimÃ© dÃ©finitivement`);
      } catch (error) {
        console.error("Erreur suppression code:", error);
        alert("â Erreur lors de la suppression");
      }
    }
  };
  
  // Delete reservation - SUPPRESSION DÃFINITIVE EN BASE
  const deleteReservation = async (reservationId) => {
    if (window.confirm("â ï¸ SUPPRESSION DÃFINITIVE\n\nCette rÃ©servation sera supprimÃ©e de la base de donnÃ©es.\n\nConfirmer la suppression ?")) {
      try {
        console.log('DELETE_UI: DÃ©but suppression rÃ©servation:', reservationId);
        await axios.delete(`${API}/reservations/${reservationId}`);
        
        // Mise Ã  jour immÃ©diate de l'Ã©tat - supporte id ET _id
        setReservations(prev => {
          const filtered = prev.filter(r => r.id !== reservationId && r._id !== reservationId);
          console.log(`DELETE_UI: RÃ©servations filtrÃ©es: ${prev.length} -> ${filtered.length}`);
          return filtered;
        });
        
        // Mettre Ã  jour le compteur de pagination
        setReservationPagination(prev => ({ ...prev, total: prev.total - 1 }));
        console.log(`DELETE_UI: â RÃ©servation ${reservationId} supprimÃ©e - UI mise Ã  jour instantanÃ©ment`);
      } catch (err) {
        console.error("DELETE_UI: â ERREUR:", err);
        alert("â Erreur lors de la suppression");
      }
    }
  };
  
  // Add manual contact to users list (for beneficiary dropdown)
  // SYNCHRONISATION CRM: Ajoute aussi dans chat_participants
  const addManualContact = async (e) => {
    e.preventDefault();
    if (!manualContact.name || !manualContact.email) return;
    try {
      // 1. CrÃ©er dans la collection users (pour les codes promo)
      const response = await axios.post(`${API}/users`, {
        name: manualContact.name,
        email: manualContact.email,
        whatsapp: manualContact.whatsapp || ""
      });
      setUsers([...users, response.data]);
      
      // 2. SYNCHRONISATION: CrÃ©er aussi dans chat_participants (CRM global)
      try {
        await addManualChatParticipant(
          manualContact.name,
          manualContact.email,
          manualContact.whatsapp || "",
          "manual_promo"
        );
      } catch (crmErr) {
        console.warn("CRM sync warning:", crmErr);
      }
      
      setManualContact({ name: "", email: "", whatsapp: "" });
      setShowManualContactForm(false);
    } catch (err) {
      console.error("Erreur ajout contact:", err);
    }
  };
  
  // Supprimer un contact (Hard Delete avec nettoyage des rÃ©fÃ©rences)
  // Supprimer un contact - SUPPRESSION DÃFINITIVE + NETTOYAGE CODES PROMO
  const deleteContact = async (userId) => {
    if (!window.confirm("â ï¸ SUPPRESSION DÃFINITIVE\n\nCe contact sera supprimÃ© de la base de donnÃ©es.\nSon email sera retirÃ© de tous les codes promo.\n\nConfirmer la suppression ?")) return;
    try {
      // RÃ©cupÃ©rer l'email AVANT suppression du state
      const userToDelete = users.find(u => u.id === userId || u._id === userId);
      const userEmail = userToDelete?.email;
      
      // 1. Supprimer en base de donnÃ©es
      await axios.delete(`${API}/users/${userId}`);
      
      // 2. Mettre Ã  jour TOUS les states locaux - supporte id ET _id
      setUsers(prev => {
        const filtered = prev.filter(u => u.id !== userId && u._id !== userId);
        console.log(`DELETE_UI: users filtrÃ©: ${prev.length} -> ${filtered.length}`);
        return filtered;
      });
      
      // 3. AUSSI mettre Ã  jour chatParticipants au cas oÃ¹
      setChatParticipants(prev => {
        const filtered = prev.filter(p => p.id !== userId && p._id !== userId);
        console.log(`DELETE_UI: chatParticipants filtrÃ©: ${prev.length} -> ${filtered.length}`);
        return filtered;
      });
      
      // 4. Nettoyer les codes promo localement
      if (userEmail) {
        setDiscountCodes(prev => prev.map(c => 
          c.assignedEmail === userEmail ? { ...c, assignedEmail: null } : c
        ));
      }
      
      // 5. Appeler sanitizeData pour s'assurer que la base est propre
      try {
        await axios.post(`${API}/sanitize-data`);
      } catch (sanitizeErr) {
        console.warn("Sanitize warning:", sanitizeErr);
      }
      
      console.log(`DELETE_UI: â Contact ${userId} supprimÃ© dÃ©finitivement`);
    } catch (err) {
      console.error("DELETE_UI: â Erreur suppression contact:", err);
      alert("â Erreur lors de la suppression");
    }
  };

  const handleImportCSV = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (event) => {
      try {
        const text = event.target.result;
        const lines = text.split('\n').filter(line => line.trim());
        for (let i = 1; i < lines.length; i++) {
          const parts = lines[i].split(',').map(s => s.trim().replace(/^["']|["']$/g, ''));
          const [email, name, value, type, expiration] = parts;
          if (value && type) {
            const response = await axios.post(`${API}/discount-codes`, {
              code: name || `CODE-${Date.now() + i}`.slice(-6), type, value: parseFloat(value),
              assignedEmail: email || null, expiresAt: expiration || null, courses: [], maxUses: null
            });
            setDiscountCodes(prev => [...prev, response.data]);
          }
        }
      } catch (error) { console.error('Import error:', error); }
    };
    reader.readAsText(file); e.target.value = '';
  };

  // Export promo codes to CSV
  const exportPromoCodesCSV = () => {
    if (discountCodes.length === 0) {
      alert("Aucun code promo Ã  exporter.");
      return;
    }
    
    // CSV headers
    const headers = ["Code", "Type", "Valeur", "BÃ©nÃ©ficiaire", "Utilisations Max", "UtilisÃ©", "Date Expiration", "Actif", "Cours AutorisÃ©s"];
    
    // CSV rows
    const rows = discountCodes.map(code => {
      const coursesNames = code.courses?.length > 0 
        ? code.courses.map(cId => courses.find(c => c.id === cId)?.name || cId).join("; ")
        : "Tous";
      
      return [
        code.code || "",
        code.type || "",
        code.value || "",
        code.assignedEmail || "",
        code.maxUses || "",
        code.used || 0,
        code.expiresAt ? new Date(code.expiresAt).toLocaleDateString() : "",
        code.active ? "Oui" : "Non",
        coursesNames
      ];
    });
    
    // Build CSV content
    const csvContent = [
      headers.join(","),
      ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(","))
    ].join("\n");
    
    // Create and trigger download
    const blob = new Blob(["\uFEFF" + csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `codes_promo_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const updateCourse = async (course) => { await axios.put(`${API}/courses/${course.id}`, course); };
  const addCourse = async (e) => {
    e.preventDefault();
    if (!newCourse.name) return;
    const response = await axios.post(`${API}/courses`, newCourse);
    setCourses([...courses, response.data]);
    setNewCourse({ name: "", weekday: 0, time: "18:30", locationName: "", mapsUrl: "" });
  };

  const updateOffer = async (offer) => { 
    try {
      await axios.put(`${API}/offers/${offer.id}`, offer); 
    } catch (err) {
      console.error("Erreur mise Ã  jour offre:", err);
    }
  };

  // Supprimer une offre - SUPPRESSION DÃFINITIVE + NETTOYAGE CODES PROMO
  const deleteOffer = async (offerId) => {
    if (!window.confirm("â ï¸ SUPPRESSION DÃFINITIVE\n\nCette offre sera supprimÃ©e de la base de donnÃ©es.\nElle sera retirÃ©e de tous les codes promo.\n\nConfirmer la suppression ?")) return;
    try {
      // 1. Supprimer en base de donnÃ©es (le backend nettoie aussi les codes promo)
      await axios.delete(`${API}/offers/${offerId}`, getCoachHeaders());
      
      // 2. Mettre Ã  jour le state local
      setOffers(prev => prev.filter(o => o.id !== offerId));
      
      // 3. Nettoyer localement les rÃ©fÃ©rences dans les codes promo
      setDiscountCodes(prev => prev.map(c => ({
        ...c,
        courses: c.courses ? c.courses.filter(id => id !== offerId) : []
      })));
      
      // 4. Appeler sanitizeData pour s'assurer que la base est propre
      try {
        await axios.post(`${API}/sanitize-data`, {}, getCoachHeaders());
      } catch (sanitizeErr) {
        console.warn("Sanitize warning:", sanitizeErr);
      }

      alert(`Offre supprimÃ©e avec succÃ¨s`);
      console.log(`Offre ${offerId} supprimÃ©e dÃ©finitivement`);
    } catch (err) {
      console.error("Erreur suppression offre:", err);
      alert("â Erreur lors de la suppression");
    }
  };

  // Charger une offre dans le formulaire pour modification
  const startEditOffer = (offer) => {
    const images = offer.images || [];
    // Remplir les 5 champs avec les images existantes
    const paddedImages = [...images, "", "", "", "", ""].slice(0, 5);
    setNewOffer({
      name: offer.name || "",
      price: offer.price || 0,
      visible: offer.visible !== false,
      description: offer.description || "",
      keywords: offer.keywords || "", // FIX: Charger les mots-clÃ©s existants
      images: paddedImages,
      category: offer.category || "service",
      isProduct: offer.isProduct || false,
      variants: offer.variants || null,
      tva: offer.tva || 0,
      shippingCost: offer.shippingCost || 0,
      stock: offer.stock ?? -1
    });
    setEditingOfferId(offer.id);
    // Scroll vers le formulaire
    document.getElementById('offer-form')?.scrollIntoView({ behavior: 'smooth' });
  };

  // Annuler l'Ã©dition
  const cancelEditOffer = () => {
    setNewOffer({ 
      name: "", price: 0, visible: true, description: "", keywords: "",
      images: ["", "", "", "", ""],
      category: "service", isProduct: false, variants: null, tva: 0, shippingCost: 0, stock: -1
    });
    setEditingOfferId(null);
  };

  // Ajouter ou mettre Ã  jour une offre
  const addOffer = async (e) => {
    e.preventDefault();
    if (!newOffer.name) return;
    console.log("[V61] addOffer called, raw newOffer:", JSON.stringify({duration_value: newOffer.duration_value, duration_unit: newOffer.duration_unit, is_auto_prolong: newOffer.is_auto_prolong}));
    try {
      // Filtrer les images non vides
      const filteredImages = (newOffer.images || []).filter(url => url && url.trim());
      // v61: Blindage total â conversion explicite, jamais de string vide
      const dv = newOffer.duration_value;
      const cleanDurationValue = (dv !== null && dv !== undefined && dv !== '' && !isNaN(parseInt(dv, 10))) ? parseInt(dv, 10) : null;
      const cleanDurationUnit = (newOffer.duration_unit && newOffer.duration_unit !== '') ? newOffer.duration_unit : null;
      const offerData = {
        name: newOffer.name,
        price: parseFloat(newOffer.price) || 0,
        visible: newOffer.visible !== false,
        description: newOffer.description || "",
        keywords: newOffer.keywords || "",
        images: filteredImages,
        thumbnail: filteredImages[0] || "",
        category: newOffer.category || "service",
        isProduct: newOffer.isProduct || false,
        variants: newOffer.variants || null,
        tva: parseFloat(newOffer.tva) || 0,
        shippingCost: parseFloat(newOffer.shippingCost) || 0,
        stock: parseInt(newOffer.stock) || -1,
        duration_value: cleanDurationValue,
        duration_unit: cleanDurationUnit,
        is_auto_prolong: newOffer.is_auto_prolong !== false
      };
      console.log("[V61] Sending offerData:", JSON.stringify(offerData));

      let resultMsg = '';
      const headers = { 'X-User-Email': coachUser?.email || '' };
      if (editingOfferId) {
        await axios.put(`${API}/offers/${editingOfferId}`, offerData, { headers });
        setOffers(prevOffers => prevOffers.map(o => o.id === editingOfferId ? { ...o, ...offerData } : o));
        setEditingOfferId(null);
        resultMsg = `â Offre "${offerData.name}" modifiÃ©e`;
      } else {
        const response = await axios.post(`${API}/offers`, offerData, { headers });
        setOffers(prevOffers => [...prevOffers, response.data]);
        resultMsg = `â Offre "${offerData.name}" crÃ©Ã©e`;
      }
      // v61: Feedback durÃ©e
      if (cleanDurationValue && cleanDurationUnit) {
        const unitLabel = cleanDurationUnit === 'days' ? 'jour(s)' : cleanDurationUnit === 'weeks' ? 'semaine(s)' : 'mois';
        resultMsg += ` avec durÃ©e : ${cleanDurationValue} ${unitLabel}`;
      }
      alert(resultMsg);

      // Reset formulaire
      setNewOffer({
        name: "", price: 0, visible: true, description: "",
        images: ["", "", "", "", ""],
        category: "service", isProduct: false, variants: null, tva: 0, shippingCost: 0, stock: -1,
        duration_value: '', duration_unit: '', is_auto_prolong: true
      });
    } catch (err) {
      console.error("[V61] Erreur offre:", err);
      // v61: Afficher l'erreur RÃELLE du serveur
      const serverMsg = err?.response?.data?.detail || err?.response?.data?.message || err?.message || "Erreur inconnue";
      alert(`â Erreur: ${typeof serverMsg === 'string' ? serverMsg : JSON.stringify(serverMsg)}`);
    }
  };

  const toggleCourseSelection = (courseId) => {
    setNewCode(prev => ({
      ...prev, courses: prev.courses.includes(courseId) ? prev.courses.filter(id => id !== courseId) : [...prev.courses, courseId]
    }));
  };

  // === CAMPAIGNS STATE & FUNCTIONS ===
  const [campaigns, setCampaigns] = useState([]);
  const [newCampaign, setNewCampaign] = useState({
    name: "", message: "", mediaUrl: "", mediaFormat: "16:9",
    targetType: "all", selectedContacts: [],
    channels: { whatsapp: false, email: false, instagram: false, group: false, internal: true },
    targetGroupId: 'community',
    targetConversationId: '', // ID de la conversation interne sÃ©lectionnÃ©e (legacy)
    targetConversationName: '', // Nom pour affichage (legacy)
    scheduleSlots: [], // Multi-date scheduling
    // === CHAMPS CTA ===
    ctaType: 'none', // 'none', 'reserver', 'offre', 'personnalise'
    ctaText: '',     // Texte personnalisÃ© du bouton
    ctaLink: '',     // URL du bouton (pour offre et personnalise)
    // === v11: PROMPTS INDÃPENDANTS PAR CAMPAGNE ===
    systemPrompt: '',        // Instructions systÃ¨me IA pour cette campagne
    descriptionPrompt: ''    // Prompt de description/objectif spÃ©cifique
  });
  const [selectedContactsForCampaign, setSelectedContactsForCampaign] = useState([]);
  const [contactSearchQuery, setContactSearchQuery] = useState("");
  const [campaignLogs, setCampaignLogs] = useState([]); // Error logs
  const [editingCampaignId, setEditingCampaignId] = useState(null); // ID de la campagne en Ã©dition
  
  // === PANIER DE DESTINATAIRES (TAGS) ===
  const [selectedRecipients, setSelectedRecipients] = useState([]); // [{id, name, type: 'group'|'user'}]
  
  // === CONVERSATIONS ACTIVES POUR MESSAGERIE INTERNE ===
  const [activeConversations, setActiveConversations] = useState([]);
  const [showConversationDropdown, setShowConversationDropdown] = useState(false); // Dropdown ouvert/fermÃ©
  
  // === FILTRES HISTORIQUE CAMPAGNES ===
  const [campaignHistoryFilter, setCampaignHistoryFilter] = useState('all'); // 'all', 'groups', 'individuals'
  
  // === SECTION CANAUX EXTERNES REPLIABLE ===
  const [externalChannelsExpanded, setExternalChannelsExpanded] = useState(false);
  
  // === SCHEDULER HEALTH STATE ===
  const [schedulerHealth, setSchedulerHealth] = useState({ status: "unknown", last_run: null });
  
  // === ENVOI DIRECT STATE ===
  const [directSendMode, setDirectSendMode] = useState(false);
  const [currentWhatsAppIndex, setCurrentWhatsAppIndex] = useState(0);
  const [instagramProfile, setInstagramProfile] = useState("afroboost"); // Profil Instagram par dÃ©faut
  const [messageCopied, setMessageCopied] = useState(false);
  
  // v8.6: Envoi message de groupe
  const sendGroupMessage = async (messageText, mediaUrl = null) => {
    if (!messageText.trim()) return;
    try {
      const response = await axios.post(`${API}/chat/group-message`, {
        message: messageText,
        coach_name: "Coach Bassi",
        media_url: mediaUrl
      });
      console.log('[GROUP] Message envoye:', response.data);
      return response.data;
    } catch (err) {
      console.error('[GROUP] Erreur:', err);
      throw err;
    }
  };
  
  // === EMAIL RESEND STATE (remplace EmailJS) ===
  const [emailSendingProgress, setEmailSendingProgress] = useState(null);
  const [emailSendingResults, setEmailSendingResults] = useState(null);
  const [testEmailAddress, setTestEmailAddress] = useState('');
  
  // === RESOLVED THUMBNAIL FOR PREVIEW ===
  const [resolvedThumbnail, setResolvedThumbnail] = useState(null);
  const [testEmailStatus, setTestEmailStatus] = useState(null);

  // === WHATSAPP API STATE ===
  const [whatsAppConfig, setWhatsAppConfig] = useState(() => getWhatsAppConfig());
  const [showWhatsAppConfig, setShowWhatsAppConfig] = useState(false);
  const [whatsAppSendingProgress, setWhatsAppSendingProgress] = useState(null);
  const [whatsAppSendingResults, setWhatsAppSendingResults] = useState(null);
  const [testWhatsAppNumber, setTestWhatsAppNumber] = useState('');
  const [testWhatsAppStatus, setTestWhatsAppStatus] = useState(null);

  // === ENVOI GROUPÃ STATE ===
  const [bulkSendingInProgress, setBulkSendingInProgress] = useState(false);
  const [bulkSendingProgress, setBulkSendingProgress] = useState(null);
  const [bulkSendingResults, setBulkSendingResults] = useState(null);

  // === IA WHATSAPP STATE ===
  const [aiConfig, setAiConfig] = useState({ enabled: false, systemPrompt: '', model: 'gpt-4o-mini', provider: 'openai', lastMediaUrl: '', twintPaymentUrl: '', campaignPrompt: '' });
  const [showAIConfig, setShowAIConfig] = useState(false);
  const [aiLogs, setAiLogs] = useState([]);
  const [aiTestMessage, setAiTestMessage] = useState('');
  const [aiTestResponse, setAiTestResponse] = useState(null);
  const [aiTestLoading, setAiTestLoading] = useState(false);
  
  // === v9.4.3 FIX: Auto-save AIConfig APRÃS dÃ©claration (corrige "Cannot access before initialization") ===
  const aiConfigSaveTimeoutRef = useRef(null);
  const [aiConfigSaveStatus, setAiConfigSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
  const isAiConfigLoaded = useRef(false); // Ãviter save au premier chargement
  
  useEffect(() => {
    // Ne pas sauvegarder au premier chargement
    if (!isAiConfigLoaded.current) {
      isAiConfigLoaded.current = true;
      return;
    }
    
    // Debounce: attendre 1 seconde d'inactivitÃ© avant de sauvegarder
    if (aiConfigSaveTimeoutRef.current) {
      clearTimeout(aiConfigSaveTimeoutRef.current);
    }
    
    aiConfigSaveTimeoutRef.current = setTimeout(async () => {
      try {
        setAiConfigSaveStatus('saving');
        await axios.put(`${API}/ai-config`, aiConfig);
        setAiConfigSaveStatus('saved');
        console.log('[COACH] v9.4.3 AIConfig auto-sauvegardÃ©');
        setTimeout(() => setAiConfigSaveStatus(null), 2000);
      } catch (err) {
        console.error('[COACH] Erreur auto-save aiConfig:', err);
        setAiConfigSaveStatus('error');
      }
    }, 1000);
    
    return () => {
      if (aiConfigSaveTimeoutRef.current) {
        clearTimeout(aiConfigSaveTimeoutRef.current);
      }
    };
  }, [aiConfig]);

  // === CONVERSATIONS STATE (CRM AVANCÃ) ===
  const [chatSessions, setChatSessions] = useState([]);
  const [chatParticipants, setChatParticipants] = useState([]);
  const [chatLinks, setChatLinks] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [sessionMessages, setSessionMessages] = useState([]);
  const [coachMessage, setCoachMessage] = useState('');
  const [newLinkTitle, setNewLinkTitle] = useState('');
  const [newLinkCustomPrompt, setNewLinkCustomPrompt] = useState('');  // Prompt spÃ©cifique au lien
  const [newCommunityName, setNewCommunityName] = useState('');  // Nom pour le chat communautaire
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [copiedLinkId, setCopiedLinkId] = useState(null);
  const [conversationSearch, setConversationSearch] = useState(''); // Recherche globale conversations
  
  // === CRM AVANCÃ - Pagination et Infinite Scroll ===
  const [conversationsPage, setConversationsPage] = useState(1);
  const [conversationsTotal, setConversationsTotal] = useState(0);
  const [conversationsHasMore, setConversationsHasMore] = useState(false);
  const [conversationsLoading, setConversationsLoading] = useState(false);
  const [enrichedConversations, setEnrichedConversations] = useState([]);
  const conversationsListRef = useRef(null);
  const searchTimeoutRef = useRef(null);

  // Add schedule slot
  const addScheduleSlot = () => {
    const now = new Date();
    const defaultDate = now.toISOString().split('T')[0];
    const defaultTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    setNewCampaign(prev => ({
      ...prev,
      scheduleSlots: [...prev.scheduleSlots, { date: defaultDate, time: defaultTime }]
    }));
  };

  // Remove schedule slot
  const removeScheduleSlot = (index) => {
    setNewCampaign(prev => ({
      ...prev,
      scheduleSlots: prev.scheduleSlots.filter((_, i) => i !== index)
    }));
  };

  // Update schedule slot
  const updateScheduleSlot = (index, field, value) => {
    setNewCampaign(prev => ({
      ...prev,
      scheduleSlots: prev.scheduleSlots.map((slot, i) => i === index ? { ...slot, [field]: value } : slot)
    }));
  };

  // Add log entry
  const addCampaignLog = (campaignId, message, type = 'info') => {
    const logEntry = {
      id: Date.now(),
      campaignId,
      message,
      type, // 'info', 'success', 'error', 'warning'
      timestamp: new Date().toISOString()
    };
    setCampaignLogs(prev => [logEntry, ...prev].slice(0, 100)); // Keep last 100 logs
  };

  // === SCHEDULER HEALTH CHECK (toutes les 30 secondes) ===
  useEffect(() => {
    const checkSchedulerHealth = async () => {
      try {
        const res = await axios.get(`${API}/scheduler/health`);
        setSchedulerHealth(res.data);
      } catch (err) {
        setSchedulerHealth({ status: "stopped", last_run: null });
      }
    };
    
    // VÃ©rifier immÃ©diatement puis toutes les 30 secondes
    if (tab === "campaigns") {
      checkSchedulerHealth();
      const interval = setInterval(checkSchedulerHealth, 30000);
      return () => clearInterval(interval);
    }
  }, [tab]);

  // Load campaigns
  useEffect(() => {
    const loadCampaigns = async () => {
      try {
        // v8.9.5: Isolation coach_id
        const res = await axios.get(`${API}/campaigns`, getCoachHeaders());
        setCampaigns(res.data);
      } catch (err) { console.error("Error loading campaigns:", err); }
    };
    
    const loadActiveConversations = async () => {
      try {
        const res = await axios.get(`${API}/conversations/active`);
        if (res.data.success) {
          setActiveConversations(res.data.conversations || []);
        }
      } catch (err) { console.error("Error loading active conversations:", err); }
    };
    
    if (tab === "campaigns") {
      loadCampaigns();
      loadActiveConversations();
      loadAIConfig();
      loadAILogs();
      // v87: DÃ©clenche le check des campagnes programmÃ©es puis toutes les 60s
      // (Vercel Hobby = cron limitÃ©, donc on compense avec polling frontend)
      const triggerCheck = () => {
        fetch(`${API}/cron/check-campaigns`).then(() => loadCampaigns()).catch(() => {});
      };
      triggerCheck();
      const campaignCheckInterval = setInterval(triggerCheck, 60000); // 60s
      return () => clearInterval(campaignCheckInterval);
    }
  }, [tab]);

  // === RÃSOUDRE LA THUMBNAIL POUR L'APERÃU ===
  // Si mediaUrl est un lien interne /v/slug, on rÃ©cupÃ¨re la vraie thumbnail
  useEffect(() => {
    const resolveMediaThumbnail = async () => {
      const url = newCampaign.mediaUrl;
      
      if (!url) {
        setResolvedThumbnail(null);
        return;
      }
      
      // VÃ©rifier si c'est un lien interne
      // Formats supportÃ©s: /v/slug, /api/share/slug
      let slug = null;
      if (url.includes('/api/share/')) {
        slug = url.split('/api/share/').pop().split('?')[0].split('#')[0].trim();
      } else if (url.includes('/v/')) {
        slug = url.split('/v/').pop().split('?')[0].split('#')[0].trim();
      }
      
      if (slug) {
        // RÃ©cupÃ©rer la thumbnail depuis l'API
        try {
          const res = await axios.get(`${API}/media/${slug}/thumbnail`);
          if (res.data?.thumbnail) {
            setResolvedThumbnail(res.data.thumbnail);
          } else {
            setResolvedThumbnail(null);
          }
        } catch (err) {
          setResolvedThumbnail(null);
        }
      } else {
        // URL externe - parser pour YouTube/Drive/Image
        const parsed = parseMediaUrl(url);
        if (parsed.thumbnailUrl) {
          setResolvedThumbnail(parsed.thumbnailUrl);
        } else if (parsed.type === 'image') {
          setResolvedThumbnail(url);
        } else {
          setResolvedThumbnail(null);
        }
      }
    };
    
    resolveMediaThumbnail();
  }, [newCampaign.mediaUrl]);

  // === CONVERSATIONS FUNCTIONS ===
  // === CRM AVANCÃ - Chargement des conversations avec pagination ===
  const loadConversations = async (reset = true) => {
    if (conversationsLoading) return;
    
    setLoadingConversations(true);
    setConversationsLoading(true);
    
    try {
      const page = reset ? 1 : conversationsPage;
      const searchQuery = conversationSearch.trim();
      
      const [conversationsRes, participantsRes, linksRes] = await Promise.all([
        axios.get(`${API}/conversations`, {
          params: { page, limit: 20, query: searchQuery }
        }),
        axios.get(`${API}/chat/participants`, getCoachHeaders()),
        axios.get(`${API}/chat/links`)
      ]);
      
      const { conversations, total, has_more } = conversationsRes.data;
      
      if (reset) {
        setEnrichedConversations(conversations);
        setChatSessions(conversations); // CompatibilitÃ© avec l'ancien code
        setConversationsPage(1);
      } else {
        setEnrichedConversations(prev => [...prev, ...conversations]);
        setChatSessions(prev => [...prev, ...conversations]);
      }
      
      setConversationsTotal(total);
      setConversationsHasMore(has_more);
      setChatParticipants(participantsRes.data);
      setChatLinks(linksRes.data);
      
    } catch (err) {
      console.error("Error loading conversations:", err);
      // Fallback vers l'ancien endpoint
      try {
        const [sessionsRes, participantsRes, linksRes] = await Promise.all([
          axios.get(`${API}/chat/sessions`),
          axios.get(`${API}/chat/participants`, getCoachHeaders()),
          axios.get(`${API}/chat/links`)
        ]);
        setChatSessions(sessionsRes.data);
        setEnrichedConversations(sessionsRes.data);
        setChatParticipants(participantsRes.data);
        setChatLinks(linksRes.data);
      } catch (fallbackErr) {
        console.error("Fallback error:", fallbackErr);
      }
    } finally {
      setLoadingConversations(false);
      setConversationsLoading(false);
    }
  };
  
  // === CRM AVANCÃ - Charger plus de conversations (Infinite Scroll) ===
  const loadMoreConversations = async () => {
    if (!conversationsHasMore || conversationsLoading) return;
    
    setConversationsLoading(true);
    try {
      const nextPage = conversationsPage + 1;
      const searchQuery = conversationSearch.trim();
      
      const res = await axios.get(`${API}/conversations`, {
        params: { page: nextPage, limit: 20, query: searchQuery }
      });
      
      const { conversations, has_more } = res.data;
      
      setEnrichedConversations(prev => [...prev, ...conversations]);
      setChatSessions(prev => [...prev, ...conversations]);
      setConversationsPage(nextPage);
      setConversationsHasMore(has_more);
      
    } catch (err) {
      console.error("Error loading more conversations:", err);
    } finally {
      setConversationsLoading(false);
    }
  };
  
  // === CRM AVANCÃ - Gestionnaire de scroll pour infinite scroll ===
  const handleConversationsScroll = useCallback((e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target;
    // Charger plus quand on arrive Ã  80% du scroll
    if (scrollTop + clientHeight >= scrollHeight * 0.8) {
      loadMoreConversations();
    }
  }, [conversationsHasMore, conversationsLoading, conversationsPage, conversationSearch]);
  
  // === CRM AVANCÃ - Recherche avec debounce ===
  const handleSearchChange = (value) => {
    setConversationSearch(value);
    
    // Debounce de 300ms pour la recherche
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    
    searchTimeoutRef.current = setTimeout(() => {
      setConversationsPage(1);
      loadConversations(true);
    }, 300);
  };
  
  // === CRM AVANCÃ - Formatage des dates ===
  const formatConversationDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const conversationDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    
    if (conversationDate.getTime() === today.getTime()) {
      return 'Aujourd\'hui';
    } else if (conversationDate.getTime() === yesterday.getTime()) {
      return 'Hier';
    } else {
      return date.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
    }
  };
  
  // === CRM AVANCÃ - Grouper les conversations par date ===
  const groupedConversations = useMemo(() => {
    const groups = {};
    
    enrichedConversations.forEach(conv => {
      const dateKey = formatConversationDate(conv.created_at);
      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      groups[dateKey].push(conv);
    });
    
    return groups;
  }, [enrichedConversations]);

  // === RÃSERVATIONS - Filtrage optimisÃ© avec useMemo ===
  const filteredReservations = useMemo(() => {
    if (!reservationsSearch) return reservations;
    const q = reservationsSearch.toLowerCase();
    return reservations.filter(r => {
      const dateStr = new Date(r.datetime).toLocaleDateString('fr-FR');
      return r.userName?.toLowerCase().includes(q) ||
             r.userEmail?.toLowerCase().includes(q) ||
             r.userWhatsapp?.includes(q) ||
             r.reservationCode?.toLowerCase().includes(q) ||
             dateStr.includes(q) ||
             r.courseName?.toLowerCase().includes(q);
    });
  }, [reservations, reservationsSearch]);

  const loadSessionMessages = async (sessionId) => {
    try {
      const res = await axios.get(`${API}/chat/sessions/${sessionId}/messages`);
      setSessionMessages(res.data);
    } catch (err) {
      console.error("Error loading messages:", err);
    }
  };

  const generateShareableLink = async () => {
    try {
      const title = newLinkTitle.trim() || 'Lien Chat Afroboost';
      const customPrompt = newLinkCustomPrompt.trim() || null;  // Null si vide
      const res = await axios.post(`${API}/chat/generate-link`, { 
        title, 
        custom_prompt: customPrompt 
      });
      setChatLinks(prev => [res.data, ...prev]);
      setNewLinkTitle('');
      setNewLinkCustomPrompt('');  // Reset le prompt
      // Recharger les sessions
      const sessionsRes = await axios.get(`${API}/chat/sessions`);
      setChatSessions(sessionsRes.data);
      // Copier automatiquement le lien
      if (res.data.link_token) {
        copyLinkToClipboard(res.data.link_token);
      }
      return res.data;
    } catch (err) {
      console.error("Error generating link:", err);
      return null;
    }
  };

  // v14.3: AmÃ©liorer un prompt avec l'IA
  const enhancePromptWithAI = async (rawPrompt) => {
    try {
      const response = await axios.post(`${API}/chat/enhance-prompt`, {
        raw_prompt: rawPrompt
      });
      return response.data.enhanced_prompt;
    } catch (err) {
      console.error("Error enhancing prompt:", err);
      return null;
    }
  };

  // CrÃ©er un chat communautaire (sans IA)
  const createCommunityChat = async () => {
    try {
      const title = newCommunityName.trim() || 'Chat CommunautÃ© Afroboost';
      // CrÃ©er une session avec mode communautÃ©
      const sessionRes = await axios.post(`${API}/chat/sessions`, {
        mode: 'community',
        is_ai_active: false,
        title: title
      });
      
      // Mettre Ã  jour les listes
      setChatSessions(prev => [sessionRes.data, ...prev]);
      setNewCommunityName('');  // Reset le nom du groupe
      
      // Copier automatiquement le lien
      if (sessionRes.data.link_token) {
        copyLinkToClipboard(sessionRes.data.link_token);
      }
      
      return sessionRes.data;
    } catch (err) {
      console.error("Error creating community chat:", err);
      return null;
    }
  };

  // === CUSTOM EMOJIS FUNCTIONS ===
  const loadCustomEmojis = async () => {
    try {
      const res = await axios.get(`${API}/chat/emojis`);
      setCustomEmojis(res.data);
    } catch (err) {
      console.error("Error loading emojis:", err);
    }
  };

  const uploadCustomEmoji = async (file) => {
    if (!file || !newEmojiName.trim()) {
      alert("Veuillez donner un nom Ã  l'emoji");
      return;
    }
    
    // Valider le type de fichier
    if (!file.type.startsWith('image/')) {
      alert("Format non supportÃ©. Utilisez PNG, JPG ou GIF.");
      return;
    }
    
    // Convertir en base64
    const reader = new FileReader();
    reader.onload = async (e) => {
      try {
        const imageData = e.target.result;
        const res = await axios.post(`${API}/chat/emojis`, {
          name: newEmojiName.trim(),
          image_data: imageData,
          category: "custom"
        });
        setCustomEmojis(prev => [res.data, ...prev]);
        setNewEmojiName("");
        if (emojiInputRef.current) emojiInputRef.current.value = "";
      } catch (err) {
        console.error("Error uploading emoji:", err);
        alert("Erreur lors de l'upload de l'emoji");
      }
    };
    reader.readAsDataURL(file);
  };

  const deleteCustomEmoji = async (emojiId) => {
    if (!window.confirm("Supprimer cet emoji ?")) return;
    try {
      await axios.delete(`${API}/chat/emojis/${emojiId}`);
      setCustomEmojis(prev => prev.filter(e => e.id !== emojiId));
    } catch (err) {
      console.error("Error deleting emoji:", err);
    }
  };

  const insertEmoji = (emoji) => {
    // InsÃ©rer l'emoji sous forme de balise image dans le message
    const emojiTag = `[emoji:${emoji.id}]`;
    setCoachMessage(prev => prev + ` ${emojiTag} `);
    setShowEmojiPicker(false);
  };

  // Charger les emojis au montage
  useEffect(() => {
    if (tab === "conversations") {
      loadCustomEmojis();
    }
  }, [tab]);

  const toggleSessionAI = async (sessionId) => {
    try {
      const res = await axios.post(`${API}/chat/sessions/${sessionId}/toggle-ai`);
      setChatSessions(prev => prev.map(s => s.id === sessionId ? res.data : s));
      if (selectedSession?.id === sessionId) {
        setSelectedSession(res.data);
      }
    } catch (err) {
      console.error("Error toggling AI:", err);
    }
  };

  // Changer le mode de la session (ai, human, community)
  const setSessionMode = async (sessionId, mode) => {
    try {
      const isAiActive = mode === 'ai';
      const res = await axios.put(`${API}/chat/sessions/${sessionId}`, {
        mode: mode,
        is_ai_active: isAiActive
      });
      setChatSessions(prev => prev.map(s => s.id === sessionId ? res.data : s));
      if (selectedSession?.id === sessionId) {
        setSelectedSession(res.data);
      }
    } catch (err) {
      console.error("Error changing session mode:", err);
    }
  };

  // === FONCTION D'ENVOI MESSAGE COACH ===
  const handleSendMessage = async () => {
    try {
      const msg = coachMessage?.trim();
      if (!msg) return;
      
      const sid = selectedSession?.id || (chatSessions.length > 0 ? chatSessions[0].id : null);
      if (!sid) return;
      
      // PrÃ©parer le message (emojis)
      let messageContent = msg;
      if (customEmojis && customEmojis.length > 0) {
        for (const emoji of customEmojis) {
          const tag = `[emoji:${emoji.id}]`;
          if (messageContent.includes(tag)) {
            messageContent = messageContent.replace(tag, `<img src="${emoji.image_data}" alt="${emoji.name}" style="width:24px;height:24px;display:inline;vertical-align:middle" />`);
          }
        }
      }
      
      // Envoi HTTP
      const response = await axios.post(`${API}/chat/coach-response`, {
        session_id: sid,
        message: messageContent,
        coach_name: coachUser?.name || 'Coach'
      });
      
      // Si succÃ¨s, vider le champ et recharger
      if (response.data && response.data.success) {
        setCoachMessage('');
        loadSessionMessages(sid);
        
        if (!selectedSession) {
          const session = chatSessions.find(s => s.id === sid);
          if (session) setSelectedSession(session);
        }
      }
      
    } catch (err) {
      console.error('Erreur envoi:', err);
    }
  };

  const copyLinkToClipboard = async (linkToken) => {
    const baseUrl = window.location.origin;
    const fullUrl = `${baseUrl}/chat/${linkToken}`;
    // Utiliser l'utilitaire avec fallback mobile robuste (clipboard â textarea â feedback)
    const result = await copyToClipboard(fullUrl);
    if (result.success) {
      setCopiedLinkId(linkToken);
      setTimeout(() => setCopiedLinkId(null), 2000);
    } else {
      console.warn('[COPY] Ãchec copie lien:', linkToken);
    }
  };

  const getParticipantName = (participantId) => {
    const participant = chatParticipants.find(p => p.id === participantId);
    return participant?.name || 'Inconnu';
  };

  const getSourceLabel = (source) => {
    if (!source) return 'Direct';
    if (source.startsWith('link_')) {
      const token = source.replace('link_', '');
      const link = chatLinks.find(l => l.link_token === token);
      return link?.title || `Lien ${token.slice(0, 6)}`;
    }
    return source === 'chat_afroboost' ? 'Widget Chat' : source;
  };

  // === SUPPRESSION CONTACT CRM ===
  const deleteChatParticipant = async (participantId) => {
    if (!window.confirm("Supprimer ce contact definitivement ?\n\nSes messages et conversations seront aussi supprimes.")) return;
    
    try {
      console.log('[DELETE] Suppression participant:', participantId);
      const response = await axios.delete(`${API}/chat/participants/${participantId}`);
      console.log('[DELETE] API OK:', response.data);
      
      // Mise a jour immediate de l'UI - supprime le participant de la liste
      setChatParticipants(prev => {
        const filtered = prev.filter(p => p.id !== participantId && p._id !== participantId);
        console.log('[DELETE] chatParticipants:', prev.length, '->', filtered.length);
        return filtered;
      });
      
      // Nettoyer aussi les conversations enrichies qui contenaient ce participant
      setEnrichedConversations(prev => {
        const filtered = prev.filter(c => {
          const pids = c.participant_ids || [];
          return !pids.includes(participantId);
        });
        return filtered;
      });
      
      console.log('[DELETE] Contact supprime avec succes');
    } catch (err) {
      console.error("[DELETE] ERREUR:", err);
      alert("Erreur lors de la suppression: " + (err.response?.data?.detail || err.message));
    }
  };

  // === SUPPRESSION SESSION (Soft Delete) ===
  const deleteChatSession = async (sessionId) => {
    if (!window.confirm("â ï¸ Supprimer cette conversation ?\n\nLa conversation sera archivÃ©e (suppression logique).")) return;
    
    try {
      console.log('DELETE_DEBUG: Suppression session:', sessionId);
      await axios.put(`${API}/chat/sessions/${sessionId}`, { is_deleted: true });
      console.log('DELETE_DEBUG: API OK, mise Ã  jour du state...');
      
      // Mettre Ã  jour TOUS les states - supporte id ET _id
      setChatSessions(prev => {
        const filtered = prev.filter(s => s.id !== sessionId && s._id !== sessionId);
        console.log('DELETE_DEBUG: chatSessions filtrÃ©:', prev.length, '->', filtered.length);
        return filtered;
      });
      setEnrichedConversations(prev => {
        const filtered = prev.filter(c => c.id !== sessionId && c._id !== sessionId);
        console.log('DELETE_DEBUG: enrichedConversations filtrÃ©:', prev.length, '->', filtered.length);
        return filtered;
      });
      setChatLinks(prev => {
        const filtered = prev.filter(l => l.id !== sessionId && l._id !== sessionId);
        console.log('DELETE_DEBUG: chatLinks filtrÃ©:', prev.length, '->', filtered.length);
        return filtered;
      });
      
      // Si c'Ã©tait la session sÃ©lectionnÃ©e, la dÃ©sÃ©lectionner
      if (selectedSession?.id === sessionId || selectedSession?._id === sessionId) {
        setSelectedSession(null);
        setSessionMessages([]);
      }
      
      console.log('DELETE_DEBUG: Suppression terminÃ©e â');
    } catch (err) {
      console.error("DELETE_DEBUG: ERREUR:", err);
      alert("Erreur lors de la suppression de la conversation: " + (err.response?.data?.detail || err.message));
    }
  };

  // === v38: SUPPRESSION GROUPÃE DE SESSIONS ===
  const bulkDeleteChatSessions = async (sessionIds) => {
    try {
      console.log('BULK_DELETE: Suppression de', sessionIds.length, 'conversations...');
      // ExÃ©cuter toutes les suppressions en parallÃ¨le
      await Promise.all(sessionIds.map(id => axios.put(`${API}/chat/sessions/${id}`, { is_deleted: true })));

      // Mettre Ã  jour tous les states
      const idsSet = new Set(sessionIds);
      setChatSessions(prev => prev.filter(s => !idsSet.has(s.id) && !idsSet.has(s._id)));
      setEnrichedConversations(prev => prev.filter(c => !idsSet.has(c.id) && !idsSet.has(c._id)));
      setChatLinks(prev => prev.filter(l => !idsSet.has(l.id) && !idsSet.has(l._id)));

      // DÃ©sÃ©lectionner si la session sÃ©lectionnÃ©e est dans la liste
      if (selectedSession && (idsSet.has(selectedSession.id) || idsSet.has(selectedSession._id))) {
        setSelectedSession(null);
        setSessionMessages([]);
      }

      console.log('BULK_DELETE: Suppression groupÃ©e terminÃ©e â', sessionIds.length, 'conversations supprimÃ©es');
    } catch (err) {
      console.error('BULK_DELETE: ERREUR:', err);
      alert("Erreur lors de la suppression groupÃ©e: " + (err.message || 'Erreur inconnue'));
      throw err;
    }
  };

  // === SUPPRESSION LIEN DE CHAT ===
  const deleteChatLink = async (linkId) => {
    if (!window.confirm("â ï¸ Supprimer ce lien de partage ?\n\nLe lien ne sera plus accessible. Cette action est irrÃ©versible.")) return;
    
    try {
      console.log('DELETE_DEBUG: Suppression lien:', linkId);
      await axios.delete(`${API}/chat/links/${linkId}`);
      console.log('DELETE_DEBUG: API OK pour lien, mise Ã  jour du state...');
      
      setChatLinks(prev => {
        const filtered = prev.filter(l => l.id !== linkId && l._id !== linkId && l.link_token !== linkId);
        console.log('DELETE_DEBUG: chatLinks filtrÃ©:', prev.length, '->', filtered.length);
        return filtered;
      });
      setEnrichedConversations(prev => {
        const filtered = prev.filter(c => c.id !== linkId && c._id !== linkId && c.link_token !== linkId);
        console.log('DELETE_DEBUG: enrichedConversations filtrÃ©:', prev.length, '->', filtered.length);
        return filtered;
      });
      setChatSessions(prev => {
        const filtered = prev.filter(s => s.id !== linkId && s._id !== linkId && s.link_token !== linkId);
        console.log('DELETE_DEBUG: chatSessions filtrÃ©:', prev.length, '->', filtered.length);
        return filtered;
      });
      
      console.log('DELETE_DEBUG: Suppression lien terminÃ©e â');
    } catch (err) {
      console.error("DELETE_DEBUG: ERREUR lien:", err);
      alert("Erreur lors de la suppression du lien: " + (err.response?.data?.detail || err.message));
    }
  };

  // === v16.1: MODIFIER UN LIEN DE CHAT (titre + prompt) ===
  const updateChatLink = async (linkId, data) => {
    try {
      const res = await axios.put(`${API}/chat/links/${linkId}`, data);
      if (res.data.success) {
        // Mettre Ã  jour le state local
        setChatLinks(prev => prev.map(l => {
          if (l.id === linkId) {
            return {
              ...l,
              title: data.title !== undefined ? data.title : l.title,
              customPrompt: data.custom_prompt !== undefined ? data.custom_prompt : l.customPrompt,
              custom_prompt: data.custom_prompt !== undefined ? data.custom_prompt : l.custom_prompt
            };
          }
          return l;
        }));
        // RafraÃ®chir aussi les sessions
        const sessionsRes = await axios.get(`${API}/chat/sessions`);
        setChatSessions(sessionsRes.data);
      }
      return res.data;
    } catch (err) {
      console.error("Error updating chat link:", err);
      alert("Erreur: " + (err.response?.data?.detail || err.message));
      throw err;
    }
  };

  // === AJOUTER CONTACT MANUEL AU CRM (synchronisÃ© avec codes promo) ===
  const addManualChatParticipant = async (name, email, whatsapp, source = 'manual_promo') => {
    try {
      const response = await axios.post(`${API}/chat/participants`, {
        name,
        email,
        whatsapp,
        source
      });
      setChatParticipants(prev => [response.data, ...prev]);
      return response.data;
    } catch (err) {
      console.error("Error adding manual participant:", err);
      return null;
    }
  };

  // === FILTRAGE GLOBAL CONVERSATIONS ===
  const filteredChatLinks = useMemo(() => {
    if (!conversationSearch) return chatLinks;
    const q = conversationSearch.toLowerCase();
    return chatLinks.filter(l => 
      l.title?.toLowerCase().includes(q) ||
      l.link_token?.toLowerCase().includes(q)
    );
  }, [chatLinks, conversationSearch]);

  const filteredChatSessions = useMemo(() => {
    if (!conversationSearch) return chatSessions;
    const q = conversationSearch.toLowerCase();
    return chatSessions.filter(s => {
      // Rechercher dans les noms des participants
      const participantNames = s.participant_ids?.map(id => getParticipantName(id)).join(' ').toLowerCase() || '';
      return participantNames.includes(q) || s.title?.toLowerCase().includes(q);
    });
  }, [chatSessions, conversationSearch, chatParticipants]);

  const filteredChatParticipants = useMemo(() => {
    if (!conversationSearch) return chatParticipants;
    const q = conversationSearch.toLowerCase();
    return chatParticipants.filter(p => 
      p.name?.toLowerCase().includes(q) ||
      p.email?.toLowerCase().includes(q) ||
      p.whatsapp?.includes(q) ||
      p.source?.toLowerCase().includes(q)
    );
  }, [chatParticipants, conversationSearch]);

  // === NOTIFICATIONS SONORES ET VISUELLES (Coach) ===
  const [notificationPermission, setNotificationPermission] = useState('default'); // 'granted' | 'denied' | 'default' | 'unsupported'
  const [showPermissionBanner, setShowPermissionBanner] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [toastNotifications, setToastNotifications] = useState([]); // Fallback toasts
  const lastNotifiedIdsRef = useRef(new Set());
  
  // Ajouter un toast de notification (fallback quand les notifications browser sont bloquÃ©es)
  const addToastNotification = useCallback((message) => {
    const id = Date.now();
    const toast = {
      id,
      senderName: message.sender_name,
      content: message.content,
      sessionId: message.session_id,
      createdAt: new Date().toISOString()
    };
    
    setToastNotifications(prev => [...prev.slice(-4), toast]); // Garder max 5 toasts
    
    // Auto-dismiss aprÃ¨s 10 secondes
    setTimeout(() => {
      setToastNotifications(prev => prev.filter(t => t.id !== id));
    }, 10000);
  }, []);
  
  // Supprimer un toast
  const dismissToast = useCallback((toastId) => {
    setToastNotifications(prev => prev.filter(t => t.id !== toastId));
  }, []);
  
  // === TOAST GÃNÃRIQUE POUR CAMPAGNES ===
  const showCampaignToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    const icons = { success: 'â', error: 'â', info: 'â¹ï¸', warning: 'â ï¸' };
    const colors = { 
      success: 'bg-green-600/90 border-green-500', 
      error: 'bg-red-600/90 border-red-500', 
      info: 'bg-blue-600/90 border-blue-500',
      warning: 'bg-yellow-600/90 border-yellow-500'
    };
    
    const toast = {
      id,
      message: `${icons[type] || 'â¹ï¸'} ${message}`,
      type,
      color: colors[type] || colors.info,
      createdAt: new Date().toISOString()
    };
    
    setToastNotifications(prev => [...prev.slice(-4), toast]);
    
    // Auto-dismiss aprÃ¨s 5 secondes (plus rapide pour les notifications de campagne)
    setTimeout(() => {
      setToastNotifications(prev => prev.filter(t => t.id !== id));
    }, 5000);
  }, []);
  
  // Cliquer sur un toast pour aller Ã  la conversation
  const handleToastClick = useCallback((toast) => {
    const session = chatSessions.find(s => s.id === toast.sessionId);
    if (session) {
      setSelectedSession(session);
      loadSessionMessages(session.id);
    }
    dismissToast(toast.id);
  }, [chatSessions, dismissToast]);
  
  // === ÃTAT POUR NOTIFICATION IA ===
  const [notifyOnAiResponse, setNotifyOnAiResponse] = useState(
    localStorage.getItem('afroboost_notify_ai') === 'true'
  );
  
  // Sauvegarder la prÃ©fÃ©rence
  const toggleNotifyOnAiResponse = useCallback(() => {
    const newValue = !notifyOnAiResponse;
    setNotifyOnAiResponse(newValue);
    localStorage.setItem('afroboost_notify_ai', newValue.toString());
  }, [notifyOnAiResponse]);
  
  // v9.2.1: Fonction de test des notifications
  const handleTestNotification = useCallback(async () => {
    try {
      const { playNotificationSound, showBrowserNotification, getNotificationPermissionStatus } = await import('../services/notificationService');
      
      // Jouer le son
      await playNotificationSound();
      
      // Afficher une notification de test
      const permission = getNotificationPermissionStatus();
      if (permission === 'granted') {
        await showBrowserNotification('ð Test Notification', {
          body: 'Les notifications fonctionnent correctement !',
          icon: '/favicon.ico'
        });
      } else {
        // Fallback: ajouter un toast
        addToastNotification({
          id: Date.now(),
          senderName: 'Test',
          content: 'ð Les notifications fonctionnent (mode fallback)',
          sessionId: null
        });
      }
    } catch (error) {
      console.error('[NOTIFICATION] Test error:', error);
      // Fallback toast mÃªme en cas d'erreur
      addToastNotification({
        id: Date.now(),
        senderName: 'Test',
        content: 'ð Notification test (fallback)',
        sessionId: null
      });
    }
  }, [addToastNotification]);
  
  // VÃ©rifier le statut de permission au chargement ET activer le polling si dÃ©jÃ  autorisÃ©
  useEffect(() => {
    const initNotifications = async () => {
      const { getNotificationPermissionStatus, unlockAudio } = await import('../services/notificationService');
      const status = getNotificationPermissionStatus();
      setNotificationPermission(status);
      
      console.log('[NOTIFICATIONS] Statut initial:', status);
      
      // Afficher le banner si permission pas encore demandÃ©e
      if (status === 'default') {
        setShowPermissionBanner(true);
      } else if (status === 'granted') {
        // Permission dÃ©jÃ  accordÃ©e - dÃ©verrouiller l'audio silencieusement
        console.log('[NOTIFICATIONS] Permission dÃ©jÃ  accordÃ©e, polling actif automatiquement');
        try {
          await unlockAudio();
        } catch (e) {
          // Silencieux - l'audio sera dÃ©bloquÃ© au premier clic
        }
      }
    };
    initNotifications();
  }, []);
  
  // Demander la permission de notification explicitement (appelÃ© par le bouton)
  const requestNotificationAccess = useCallback(async () => {
    try {
      // DÃ©verrouiller l'audio (nÃ©cessaire sur iOS)
      const { unlockAudio, requestNotificationPermission } = await import('../services/notificationService');
      await unlockAudio();
      
      // Demander la permission des notifications browser
      const permission = await requestNotificationPermission();
      setNotificationPermission(permission);
      setShowPermissionBanner(false);
      
      if (permission === 'granted') {
        console.log('[NOTIFICATIONS] Permission accordÃ©e!');
        // Afficher une notification de test
        const { showBrowserNotification } = await import('../services/notificationService');
        await showBrowserNotification(
          'â Notifications activÃ©es',
          'Vous recevrez dÃ©sormais les alertes de nouveaux messages.',
          { tag: 'afroboost-permission-granted' }
        );
      } else if (permission === 'denied') {
        console.log('[NOTIFICATIONS] Permission refusÃ©e - utilisation du fallback toast');
      }
    } catch (err) {
      console.warn('[NOTIFICATIONS] Erreur permission:', err);
    }
  }, []);
  
  // VÃ©rifier les nouveaux messages non notifiÃ©s (endpoint optimisÃ©)
  const checkUnreadNotifications = useCallback(async () => {
    if (tab !== 'conversations') return;
    
    console.log('NOTIF_DEBUG: Polling dÃ©marrÃ©...');
    
    try {
      const res = await axios.get(`${API}/notifications/unread`, {
        params: { 
          target: 'coach',
          include_ai: notifyOnAiResponse  // Inclure les rÃ©ponses IA si option activÃ©e
        }
      });
      
      const { count, messages } = res.data;
      console.log(`NOTIF_DEBUG: ${count} messages non lus, ${messages?.length || 0} Ã  traiter`);
      setUnreadCount(count);
      
      if (messages && messages.length > 0) {
        // Filtrer les messages dÃ©jÃ  notifiÃ©s localement
        const newMessages = messages.filter(m => !lastNotifiedIdsRef.current.has(m.id));
        console.log(`NOTIF_DEBUG: ${newMessages.length} NOUVEAUX messages dÃ©tectÃ©s`);
        
        if (newMessages.length > 0) {
          console.log('NOTIF_DEBUG: â¡ Nouveaux messages! Tentative notification...');
          
          // Importer les fonctions de notification
          const { playNotificationSound, showBrowserNotification, getNotificationPermissionStatus } = await import('../services/notificationService');
          
          // Jouer le son (avec protection contre les erreurs)
          try {
            console.log('NOTIF_DEBUG: Jouer son...');
            await playNotificationSound('user');
            console.log('NOTIF_DEBUG: Son jouÃ© â');
          } catch (soundErr) {
            console.warn('NOTIF_DEBUG: Erreur son (ignorÃ©e):', soundErr.message);
            // Continuer mÃªme si le son Ã©choue
          }
          
          // VÃ©rifier la permission actuelle
          const currentPermission = getNotificationPermissionStatus();
          console.log('NOTIF_DEBUG: Permission actuelle:', currentPermission);
          
          // Afficher une notification pour chaque nouveau message (max 3)
          for (const msg of newMessages.slice(0, 3)) {
            console.log(`NOTIF_DEBUG: Traitement message de ${msg.sender_name}...`);
            
            // Essayer d'afficher une notification browser
            try {
              const result = await showBrowserNotification(
                'ð¬ Nouveau message - Afroboost',
                `${msg.sender_name}: ${msg.content.substring(0, 80)}${msg.content.length > 80 ? '...' : ''}`,
                {
                  tag: `afroboost-msg-${msg.id}`,
                  onClick: () => {
                    // SÃ©lectionner la session correspondante
                    const session = chatSessions.find(s => s.id === msg.session_id);
                    if (session) {
                      setSelectedSession(session);
                      loadSessionMessages(session.id);
                    }
                  }
                }
              );
              
              console.log('NOTIF_DEBUG: RÃ©sultat notification:', result);
              
              // Si la notification browser a Ã©chouÃ©, utiliser le fallback toast
              if (result.fallbackNeeded) {
                console.log('NOTIF_DEBUG: Fallback TOAST activÃ©!');
                addToastNotification(msg);
              } else {
                console.log('NOTIF_DEBUG: Notification browser envoyÃ©e â');
              }
            } catch (notifErr) {
              console.warn('NOTIF_DEBUG: Erreur notification (fallback toast):', notifErr.message);
              addToastNotification(msg);
            }
            
            // Ajouter Ã  la liste des messages notifiÃ©s localement (TOUJOURS, mÃªme en cas d'erreur)
            lastNotifiedIdsRef.current.add(msg.id);
          }
          
          // Marquer les messages comme notifiÃ©s cÃ´tÃ© serveur
          const messageIds = newMessages.map(m => m.id);
          await axios.put(`${API}/notifications/mark-read`, {
            message_ids: messageIds
          }).catch(() => {}); // Ignorer les erreurs silencieusement
          
          // RafraÃ®chir les conversations
          loadConversations(true);
        }
      }
    } catch (err) {
      // Fallback vers l'ancienne mÃ©thode si le nouvel endpoint n'est pas disponible
      console.warn('[NOTIFICATIONS] Erreur polling:', err);
    }
  }, [tab, chatSessions, addToastNotification, notifyOnAiResponse]);
  
  // Polling des notifications toutes les 10 secondes
  useEffect(() => {
    if (tab !== 'conversations') return;
    
    console.log('[NOTIFICATIONS] Polling activÃ© (interval 10s)');
    
    // VÃ©rifier immÃ©diatement
    checkUnreadNotifications();
    
    // Puis toutes les 10 secondes
    const interval = setInterval(() => {
      checkUnreadNotifications();
    }, 10000);
    
    // Cleanup important pour Ã©viter les fuites mÃ©moire
    return () => {
      console.log('[NOTIFICATIONS] Polling dÃ©sactivÃ©');
      clearInterval(interval);
    };
  }, [tab, checkUnreadNotifications]);

  // === POLLING LEGACY pour les sessions en mode humain ===
  const lastMessageCountRef = useRef({});
  
  const checkNewMessages = useCallback(async () => {
    if (tab !== 'conversations') return;
    
    // VÃ©rifier les sessions en mode humain pour les nouveaux messages
    const humanSessions = chatSessions.filter(s => !s.is_ai_active);
    
    for (const session of humanSessions) {
      try {
        const res = await axios.get(`${API}/chat/sessions/${session.id}/messages`);
        const messages = res.data;
        const prevCount = lastMessageCountRef.current[session.id] || 0;
        
        if (messages.length > prevCount) {
          const latestMessage = messages[messages.length - 1];
          
          // Si le message vient d'un utilisateur (pas du coach)
          if (latestMessage.sender_type === 'user') {
            // Note: Le son est maintenant gÃ©rÃ© par checkUnreadNotifications
            
            // Mettre Ã  jour les messages si c'est la session sÃ©lectionnÃ©e
            if (selectedSession?.id === session.id) {
              setSessionMessages(messages);
            }
          }
        }
        
        lastMessageCountRef.current[session.id] = messages.length;
      } catch (err) {
        // Ignorer les erreurs silencieusement
      }
    }
  }, [tab, chatSessions, selectedSession]);

  // Polling toutes les 5 secondes quand sur l'onglet conversations
  useEffect(() => {
    if (tab !== 'conversations') return;
    
    const interval = setInterval(() => {
      checkNewMessages();
      // RafraÃ®chir aussi la liste des sessions
      axios.get(`${API}/chat/sessions`).then(res => {
        setChatSessions(res.data);
      }).catch(() => {});
    }, 5000);
    return () => clearInterval(interval);
  }, [tab, checkNewMessages]);

  // Load conversations when tab changes
  useEffect(() => {
    if (tab === "conversations") {
      loadConversations();
    }
  }, [tab]);

  // === CONTACTS COMBINÃS: Users + Reservations + Chat Participants ===
  const allContacts = useMemo(() => {
    const contactMap = new Map();
    
    // 1. Users existants
    users.forEach(u => contactMap.set(u.email, { 
      id: u.id, 
      name: u.name, 
      email: u.email, 
      phone: u.whatsapp || "",
      source: 'users'
    }));
    
    // 2. RÃ©servations
    reservations.forEach(r => {
      if (r.userEmail && !contactMap.has(r.userEmail)) {
        contactMap.set(r.userEmail, { 
          id: r.userId, 
          name: r.userName, 
          email: r.userEmail, 
          phone: r.userWhatsapp || "",
          source: 'reservations'
        });
      }
    });
    
    // 3. Chat Participants (CRM) - SYNCHRONISATION
    chatParticipants.forEach(p => {
      if (p.email && !contactMap.has(p.email)) {
        contactMap.set(p.email, {
          id: p.id,
          name: p.name,
          email: p.email,
          phone: p.whatsapp || "",
          source: p.source || 'chat_crm'
        });
      }
    });
    
    return Array.from(contactMap.values());
  }, [users, reservations, chatParticipants]);

  // Filter contacts by search
  const filteredContacts = useMemo(() => {
    if (!contactSearchQuery) return allContacts;
    const q = contactSearchQuery.toLowerCase();
    return allContacts.filter(c => 
      c.name?.toLowerCase().includes(q) || c.email?.toLowerCase().includes(q)
    );
  }, [allContacts, contactSearchQuery]);

  // Toggle contact selection
  const toggleContactForCampaign = (contactId) => {
    setSelectedContactsForCampaign(prev => 
      prev.includes(contactId) ? prev.filter(id => id !== contactId) : [...prev, contactId]
    );
  };

  // Select/Deselect all contacts
  const toggleAllContacts = () => {
    if (selectedContactsForCampaign.length === allContacts.length) {
      setSelectedContactsForCampaign([]);
    } else {
      setSelectedContactsForCampaign(allContacts.map(c => c.id));
    }
  };

  // === ÃDITION CAMPAGNE ===
  // PrÃ©-remplir le formulaire avec les donnÃ©es d'une campagne existante
  const handleEditCampaign = (campaign) => {
    setEditingCampaignId(campaign.id);
    setNewCampaign({
      name: campaign.name || "",
      message: campaign.message || "",
      mediaUrl: campaign.mediaUrl || "",
      mediaFormat: campaign.mediaFormat || "16:9",
      targetType: campaign.targetType || "all",
      selectedContacts: campaign.selectedContacts || [],
      channels: campaign.channels || { whatsapp: false, email: false, instagram: false, internal: true },
      targetGroupId: campaign.targetGroupId || 'community',
      targetConversationId: campaign.targetConversationId || '',
      targetConversationName: campaign.targetConversationName || '',
      scheduleSlots: campaign.scheduledAt ? [{
        date: new Date(campaign.scheduledAt).toISOString().split('T')[0],
        time: new Date(campaign.scheduledAt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', hour12: false })
      }] : [],
      // v11: Charger les prompts de la campagne
      systemPrompt: campaign.systemPrompt || '',
      descriptionPrompt: campaign.descriptionPrompt || ''
    });
    // PrÃ©-sÃ©lectionner les contacts CRM si mode "selected"
    if (campaign.targetType === "selected" && campaign.selectedContacts) {
      setSelectedContactsForCampaign(campaign.selectedContacts);
    }
    // Recharger le panier de destinataires (targetIds)
    if (campaign.targetIds && campaign.targetIds.length > 0) {
      // Retrouver les infos de chaque destinataire depuis activeConversations
      const recipients = campaign.targetIds.map(id => {
        const conv = activeConversations.find(c => c.conversation_id === id);
        return conv 
          ? { id: conv.conversation_id, name: conv.name || 'Sans nom', type: conv.type }
          : { id, name: campaign.targetConversationName || 'Destinataire', type: 'user' };
      });
      setSelectedRecipients(recipients);
    } else if (campaign.targetConversationId) {
      // Legacy: single target
      const conv = activeConversations.find(c => c.conversation_id === campaign.targetConversationId);
      setSelectedRecipients([{
        id: campaign.targetConversationId,
        name: conv?.name || campaign.targetConversationName || 'Destinataire',
        type: conv?.type || 'user'
      }]);
    } else {
      setSelectedRecipients([]);
    }
    // Scroll vers le formulaire
    window.scrollTo({ top: 0, behavior: 'smooth' });
    showCampaignToast(`ð Mode Ã©dition: "${campaign.name}"`, 'info');
  };

  // Annuler l'Ã©dition et rÃ©initialiser le formulaire
  const cancelEditCampaign = () => {
    setEditingCampaignId(null);
    setNewCampaign({ 
      name: "", message: "", mediaUrl: "", mediaFormat: "16:9", 
      targetType: "all", selectedContacts: [], 
      channels: { whatsapp: false, email: false, instagram: false, group: false, internal: true },
      targetGroupId: 'community',
      targetConversationId: '',
      targetConversationName: '',
      scheduleSlots: [],
      systemPrompt: '',
      descriptionPrompt: ''
    });
    setSelectedContactsForCampaign([]);
    setSelectedRecipients([]); // Vider aussi le panier
  };

  // Create OR Update campaign (supports multiple schedule slots)
  const createCampaign = async (e) => {
    e.preventDefault();
    if (!newCampaign.name || !newCampaign.message) return;

    // v13: Blocage crÃ©dits cÃ´tÃ© frontend (double sÃ©curitÃ© avec backend)
    if (!isSuperAdmin && coachCredits !== null && coachCredits !== -1 && coachCredits <= 0) {
      showCampaignToast('ð CrÃ©dits insuffisants. Rechargez votre pack pour crÃ©er des campagnes.', 'error');
      return;
    }

    // Valider qu'il y a au moins un destinataire
    const hasRecipients = selectedRecipients.length > 0 || newCampaign.channels.whatsapp || newCampaign.channels.email || newCampaign.channels.group;
    if (!hasRecipients) {
      showCampaignToast('â ï¸ Ajoutez au moins un destinataire', 'error');
      return;
    }
    
    // PrÃ©parer les targetIds depuis le panier
    const targetIds = selectedRecipients.map(r => r.id);
    
    // === MODE ÃDITION : Mise Ã  jour d'une campagne existante ===
    if (editingCampaignId) {
      try {
        // Calculer scheduledAt depuis les scheduleSlots (si modifiÃ©)
        const editSlots = newCampaign.scheduleSlots || [];
        let editScheduledAt = null;
        if (editSlots.length > 0 && editSlots[0].date && editSlots[0].time) {
          const localDate = new Date(`${editSlots[0].date}T${editSlots[0].time}:00`);
          editScheduledAt = localDate.toISOString();
        }

        const updateData = {
          name: newCampaign.name,
          message: newCampaign.message,
          mediaUrl: newCampaign.mediaUrl,
          mediaFormat: newCampaign.mediaFormat,
          targetType: newCampaign.targetType,
          selectedContacts: newCampaign.targetType === "selected" ? selectedContactsForCampaign : [],
          channels: { ...newCampaign.channels, internal: selectedRecipients.length > 0 },
          targetGroupId: newCampaign.targetGroupId || 'community',
          targetIds: targetIds, // Tableau des IDs du panier
          targetConversationId: targetIds[0] || '', // Premier ID pour compatibilitÃ©
          targetConversationName: selectedRecipients[0]?.name || '',
          scheduledAt: editScheduledAt, // Mise Ã  jour de l'horaire
          // v11: Prompts indÃ©pendants
          systemPrompt: newCampaign.systemPrompt || null,
          descriptionPrompt: newCampaign.descriptionPrompt || null
        };
        const res = await axios.put(`${API}/campaigns/${editingCampaignId}`, updateData);
        setCampaigns(campaigns.map(c => c.id === editingCampaignId ? res.data : c));
        addCampaignLog(editingCampaignId, `Campagne "${newCampaign.name}" modifiÃ©e avec succÃ¨s`, 'success');
        
        // Reset form et mode Ã©dition
        cancelEditCampaign();
        setSelectedRecipients([]); // Vider le panier
        alert(`â Campagne "${newCampaign.name}" modifiÃ©e avec succÃ¨s !`);
        return;
      } catch (err) {
        console.error("Error updating campaign:", err);
        addCampaignLog(editingCampaignId, `Erreur modification: ${err.message}`, 'error');
        alert(`â Erreur lors de la modification: ${err.message}`);
        return;
      }
    }
    
    // === MODE CRÃATION : Nouvelle campagne ===
    const scheduleSlots = newCampaign.scheduleSlots;
    const isImmediate = scheduleSlots.length === 0;
    
    // PrÃ©parer les champs CTA (seulement si un type est sÃ©lectionnÃ©)
    const ctaFields = newCampaign.ctaType !== 'none' ? {
      ctaType: newCampaign.ctaType,
      ctaText: newCampaign.ctaText || (newCampaign.ctaType === 'reserver' ? 'RÃSERVER' : newCampaign.ctaType === 'offre' ? 'VOIR L\'OFFRE' : 'EN SAVOIR PLUS'),
      ctaLink: newCampaign.ctaLink || (newCampaign.ctaType === 'reserver' ? '#courses' : '')
    } : {};
    
    try {
      if (isImmediate) {
        // Create single immediate campaign
        const campaignData = {
          name: newCampaign.name,
          message: newCampaign.message,
          mediaUrl: newCampaign.mediaUrl,
          mediaFormat: newCampaign.mediaFormat,
          targetType: newCampaign.targetType,
          selectedContacts: newCampaign.targetType === "selected" ? selectedContactsForCampaign : [],
          channels: { ...newCampaign.channels, internal: selectedRecipients.length > 0 },
          targetGroupId: newCampaign.targetGroupId || 'community',
          targetIds: targetIds, // Tableau des IDs du panier
          targetConversationId: targetIds[0] || '',
          targetConversationName: selectedRecipients[0]?.name || '',
          scheduledAt: null,
          // v11: Prompts indÃ©pendants
          systemPrompt: newCampaign.systemPrompt || null,
          descriptionPrompt: newCampaign.descriptionPrompt || null,
          ...ctaFields  // Ajouter les champs CTA
        };
        const res = await axios.post(`${API}/campaigns`, campaignData);
        setCampaigns([res.data, ...campaigns]);
        addCampaignLog(res.data.id, `Campagne "${newCampaign.name}" crÃ©Ã©e (${targetIds.length} destinataire(s))`, 'success');

        // v13: Auto-launch immediate campaigns
        if (targetIds.length > 0) {
          try {
            addCampaignLog(res.data.id, 'ð Lancement automatique en cours...', 'info');
            const launchRes = await axios.post(`${API}/campaigns/${res.data.id}/launch`);
            setCampaigns(prev => prev.map(c => c.id === res.data.id ? launchRes.data : c));
            addCampaignLog(res.data.id, `â Campagne envoyÃ©e ! (${launchRes.data.results?.length || 0} envoi(s))`, 'success');
          } catch (launchErr) {
            console.error('Auto-launch error:', launchErr);
            addCampaignLog(res.data.id, `â ï¸ CrÃ©Ã©e mais envoi Ã©chouÃ©: ${launchErr.response?.data?.detail || launchErr.message}`, 'error');
          }
        }
      } else {
        // Create one campaign per schedule slot (multi-date)
        for (let i = 0; i < scheduleSlots.length; i++) {
          const slot = scheduleSlots[i];
          // Build ISO string with user's local timezone offset
          const localDate = new Date(`${slot.date}T${slot.time}:00`);
          const scheduledAt = localDate.toISOString();
          const campaignData = {
            name: scheduleSlots.length > 1 ? `${newCampaign.name} (${i + 1}/${scheduleSlots.length})` : newCampaign.name,
            message: newCampaign.message,
            mediaUrl: newCampaign.mediaUrl,
            mediaFormat: newCampaign.mediaFormat,
            targetType: newCampaign.targetType,
            selectedContacts: newCampaign.targetType === "selected" ? selectedContactsForCampaign : [],
            channels: { ...newCampaign.channels, internal: selectedRecipients.length > 0 },
            targetGroupId: newCampaign.targetGroupId || 'community',
            targetIds: targetIds, // Tableau des IDs du panier
            targetConversationId: targetIds[0] || '',
            targetConversationName: selectedRecipients[0]?.name || '',
            scheduledAt,
            // v11: Prompts indÃ©pendants
            systemPrompt: newCampaign.systemPrompt || null,
            descriptionPrompt: newCampaign.descriptionPrompt || null,
            ...ctaFields  // Ajouter les champs CTA
          };
          const res = await axios.post(`${API}/campaigns`, campaignData);
          setCampaigns(prev => [res.data, ...prev]);
          addCampaignLog(res.data.id, `Campagne "${campaignData.name}" programmÃ©e pour ${new Date(scheduledAt).toLocaleString('fr-FR')}`, 'info');
        }
      }
      
      // Reset form
      setNewCampaign({ 
        name: "", message: "", mediaUrl: "", mediaFormat: "16:9", 
        targetType: "all", selectedContacts: [], 
        channels: { whatsapp: false, email: false, instagram: false, group: false, internal: true }, 
        targetGroupId: 'community',
        targetConversationId: '',
        targetConversationName: '',
        scheduleSlots: [] 
      });
      setSelectedContactsForCampaign([]);
      setSelectedRecipients([]); // Vider le panier
      showCampaignToast(`${isImmediate ? 'Campagne crÃ©Ã©e' : `${scheduleSlots.length} campagne(s) programmÃ©e(s)`} avec succÃ¨s !`, 'success');
    } catch (err) { 
      console.error("Error creating campaign:", err);
      addCampaignLog('new', `Erreur crÃ©ation campagne: ${err.message}`, 'error');
      showCampaignToast(`Erreur: ${err.message}`, 'error');
    }
  };

  // Launch campaign (generate links)
  const launchCampaign = async (campaignId) => {
    try {
      addCampaignLog(campaignId, 'Lancement de la campagne...', 'info');
      const res = await axios.post(`${API}/campaigns/${campaignId}/launch`);
      setCampaigns(campaigns.map(c => c.id === campaignId ? res.data : c));
      addCampaignLog(campaignId, `Campagne lancÃ©e avec ${res.data.results?.length || 0} destinataire(s)`, 'success');
      showCampaignToast(`Campagne lancÃ©e ! ${res.data.results?.length || 0} destinataire(s)`, 'success');
    } catch (err) { 
      console.error("Error launching campaign:", err);
      addCampaignLog(campaignId, `Erreur lancement: ${err.message}`, 'error');
      showCampaignToast(`Erreur lancement: ${err.message}`, 'error');
    }
  };

  // Launch campaign WITH REAL SENDING via Resend and Twilio
  // === BOUTON LANCER - ISOLATION COMPLÃTE ===
  const launchCampaignWithSend = async (e, campaignId) => {
    // === BLOCAGE CRASH POSTHOG ===
    // Ces lignes DOIVENT Ãªtre en premier, avant toute autre logique
    e.preventDefault();
    e.stopPropagation();
    
    try {
      // 1. RÃ©cupÃ©rer la campagne
      const campaign = campaigns.find(c => c.id === campaignId);
      if (!campaign) {
        alert('â Campagne non trouvÃ©e');
        return;
      }

      // Log isolÃ© (peut Ãªtre ignorÃ© si PostHog crash)
      try {
        addCampaignLog(campaignId, 'PrÃ©paration de l\'envoi...', 'info');
      } catch (logErr) {
        console.warn('PostHog bloquÃ© sur log mais envoi maintenu:', logErr);
      }

      // 2. PrÃ©parer d'abord la campagne cÃ´tÃ© backend
      const launchRes = await axios.post(`${API}/campaigns/${campaignId}/launch`);
      const launchedCampaign = launchRes.data;
      
      try {
        setCampaigns(campaigns.map(c => c.id === campaignId ? launchedCampaign : c));
      } catch (stateErr) {
        console.warn('PostHog bloquÃ© sur setState mais envoi maintenu:', stateErr);
      }

      // 3. RÃ©cupÃ©rer les contacts Ã  envoyer
      const results = launchedCampaign.results || [];
      if (results.length === 0) {
        alert('â ï¸ Aucun contact Ã  envoyer');
        return;
      }

      // 4. SÃ©parer par canal
      const emailResults = results.filter(r => r.channel === 'email' && r.contactEmail);
      const whatsAppResults = results.filter(r => r.channel === 'whatsapp' && r.contactPhone);

      // Confirmation
      const confirmMsg = `ð Lancer la campagne "${campaign.name}" ?\n\n` +
        `ð§ ${emailResults.length} email(s)\n` +
        `ð± ${whatsAppResults.length} WhatsApp\n\n` +
        `â ï¸ Cette action est irrÃ©versible.`;
      
      if (!window.confirm(confirmMsg)) {
        return;
      }

      let totalSent = 0;
      let totalFailed = 0;

      // 5. === ENVOI EMAILS VIA RESEND (BACKEND) ===
      if (emailResults.length > 0) {
        try {
          addCampaignLog(campaignId, `ð§ Envoi de ${emailResults.length} email(s) via Resend...`, 'info');
        } catch (e) { console.warn('Log bloquÃ©:', e); }
        
        console.log(`RESEND_DEBUG: === LANCEMENT CAMPAGNE: ${emailResults.length} destinataires ===`);
        
        for (let i = 0; i < emailResults.length; i++) {
          const contact = emailResults[i];
          
          console.log(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] Envoi Ã : ${contact.contactEmail}`);
          console.log(`RESEND_DEBUG: mediaUrl = ${campaign.mediaUrl || 'AUCUN'}`);
          
          try {
            // Appel API Resend via backend
            const response = await fetch(`${BACKEND_URL}/api/campaigns/send-email`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                to_email: contact.contactEmail,
                to_name: contact.contactName || 'Client',
                subject: campaign.name || 'Afroboost - Message',
                message: campaign.message,
                media_url: campaign.mediaUrl || null
              })
            });
            
            const result = await response.json();
            
            if (result.success) {
              console.log(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] SUCCÃS - ID = ${result.email_id}`);
              totalSent++;
              
              // Marquer comme envoyÃ©
              try {
                await axios.post(`${API}/campaigns/${campaignId}/mark-sent`, {
                  contactId: contact.contactId,
                  channel: 'email'
                });
              } catch (markErr) {
                console.warn('RESEND_DEBUG: Mark-sent bloquÃ© mais email envoyÃ©');
              }
            } else {
              console.error(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] ÃCHEC - ${result.error}`);
              totalFailed++;
            }
            
          } catch (error) {
            console.error(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] EXCEPTION - ${error.message}`);
            totalFailed++;
          }
          
          // DÃ©lai entre les envois
          if (i < emailResults.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 300));
          }
        }
      }

      // 6. === ENVOI WHATSAPP VIA FONCTION AUTONOME ===
      if (whatsAppResults.length > 0) {
        try {
          addCampaignLog(campaignId, `ð± Envoi de ${whatsAppResults.length} WhatsApp...`, 'info');
        } catch (e) { console.warn('Log bloquÃ©:', e); }
        
        console.log(`ð± === LANCEMENT CAMPAGNE WHATSAPP: ${whatsAppResults.length} destinataires ===`);
        
        for (let i = 0; i < whatsAppResults.length; i++) {
          const contact = whatsAppResults[i];
          
          console.log(`ð± [${i + 1}/${whatsAppResults.length}] Envoi Ã : ${contact.contactPhone}`);
          
          // === APPEL FONCTION AUTONOME ISOLÃE ===
          const result = await performWhatsAppSend(
            contact.contactPhone,
            campaign.message,
            whatsAppConfig
          );

          if (result.success) {
            totalSent++;
            console.log(`â WhatsApp envoyÃ©${result.simulated ? ' (simulation)' : ''}`);
            // Marquer comme envoyÃ©
            try {
              await axios.post(`${API}/campaigns/${campaignId}/mark-sent`, {
                contactId: contact.contactId,
                channel: 'whatsapp'
              });
            } catch (markErr) {
              console.warn('â ï¸ Mark-sent bloquÃ© mais WhatsApp envoyÃ©:', markErr);
            }
          } else {
            totalFailed++;
            console.error(`â WhatsApp failed: ${result.error}`);
          }
          
          // DÃ©lai entre les envois
          if (i < whatsAppResults.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 500));
          }
        }
      }

      // 7. Recharger la campagne (peut Ãªtre ignorÃ©)
      try {
        const updatedRes = await axios.get(`${API}/campaigns/${campaignId}`);
        setCampaigns(campaigns.map(c => c.id === campaignId ? updatedRes.data : c));
      } catch (reloadErr) {
        console.warn('Reload bloquÃ© mais envois effectuÃ©s:', reloadErr);
      }

      // 8. Notification finale
      try {
        addCampaignLog(campaignId, `â TerminÃ©: ${totalSent} envoyÃ©s, ${totalFailed} Ã©chouÃ©s`, 'success');
      } catch (e) { console.warn('Log final bloquÃ©:', e); }
      
      alert(`â Campagne "${campaign.name}" terminÃ©e !\n\nâ EnvoyÃ©s: ${totalSent}\nâ ÃchouÃ©s: ${totalFailed}`);

    } catch (err) {
      console.error("Error launching campaign with send:", err);
      try {
        addCampaignLog(campaignId, `â Erreur: ${err.message}`, 'error');
      } catch (e) { console.warn('Log erreur bloquÃ©:', e); }
      alert(`â Erreur lors de l'envoi: ${err.message}`);
    }
  };

  // Delete campaign
  const deleteCampaign = async (campaignId) => {
    if (!window.confirm("Supprimer cette campagne ?")) return;
    try {
      await axios.delete(`${API}/campaigns/${campaignId}`);
      setCampaigns(campaigns.filter(c => c.id !== campaignId));
      addCampaignLog(campaignId, 'Campagne supprimÃ©e', 'info');
    } catch (err) { 
      console.error("Error deleting campaign:", err);
      addCampaignLog(campaignId, `Erreur suppression: ${err.message}`, 'error');
    }
  };

  // Format phone number for WhatsApp (ensure country code)
  const formatPhoneForWhatsApp = (phone) => {
    if (!phone) return '';
    
    // 1. Remove ALL non-numeric characters first (spaces, dashes, dots, parentheses)
    let cleaned = phone.replace(/[\s\-\.\(\)]/g, '');
    
    // 2. Handle + prefix separately
    const hasPlus = cleaned.startsWith('+');
    cleaned = cleaned.replace(/[^\d]/g, ''); // Keep only digits
    
    // 3. Detect and normalize Swiss numbers
    if (cleaned.startsWith('0041')) {
      // Format: 0041XXXXXXXXX -> 41XXXXXXXXX
      cleaned = cleaned.substring(2);
    } else if (cleaned.startsWith('41') && cleaned.length >= 11) {
      // Already has country code 41
      // Keep as is
    } else if (cleaned.startsWith('0') && (cleaned.length === 10 || cleaned.length === 9)) {
      // Swiss local format: 079XXXXXXX or 79XXXXXXX -> 4179XXXXXXX
      cleaned = '41' + cleaned.substring(1);
    } else if (!hasPlus && cleaned.length >= 9 && cleaned.length <= 10 && !cleaned.startsWith('41')) {
      // Assume Swiss number without country code
      cleaned = '41' + cleaned;
    }
    
    // 4. Final validation - must have at least 10 digits for international
    if (cleaned.length < 10) {
      return '';
    }
    
    return cleaned;
  };

  // Generate WhatsApp link with message and media URL at the end for link preview
  // NOTE: Do NOT call addCampaignLog here - this function is called during render!
  // Error handling is done visually in the JSX with red indicators
  const generateWhatsAppLink = (phone, message, mediaUrl, contactName) => {
    const firstName = contactName?.split(' ')[0] || contactName || 'ami(e)';
    const personalizedMessage = message
      .replace(/{prÃ©nom}/gi, firstName)
      .replace(/{prenom}/gi, firstName)
      .replace(/{nom}/gi, contactName || '');
    
    // CRITICAL: Add media URL at the very end WITHOUT any emoji/text before it
    // This allows WhatsApp to generate a link preview with thumbnail
    const fullMessage = mediaUrl 
      ? `${personalizedMessage}\n\n${mediaUrl}` 
      : personalizedMessage;
    
    const formattedPhone = formatPhoneForWhatsApp(phone);
    
    if (!formattedPhone) {
      // Don't call setState here (addCampaignLog) - it causes infinite re-render!
      // The error is handled visually in the JSX
      return null;
    }
    
    const encodedMessage = encodeURIComponent(fullMessage);
    // Use api.whatsapp.com/send which works better on mobile and desktop
    return `https://api.whatsapp.com/send?phone=${formattedPhone}&text=${encodedMessage}`;
  };

  // Generate mailto link for email
  // NOTE: Do NOT call addCampaignLog here - this function is called during render!
  const generateEmailLink = (email, subject, message, mediaUrl, contactName) => {
    const firstName = contactName?.split(' ')[0] || contactName || 'ami(e)';
    const personalizedMessage = message
      .replace(/{prÃ©nom}/gi, firstName)
      .replace(/{prenom}/gi, firstName)
      .replace(/{nom}/gi, contactName || '');
    
    const fullMessage = mediaUrl 
      ? `${personalizedMessage}\n\nð Voir le visuel: ${mediaUrl}` 
      : personalizedMessage;
    
    if (!email) {
      // Don't call setState here - it causes infinite re-render!
      return null;
    }
    
    return `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(fullMessage)}`;
  };

  // Generate Instagram DM link
  const generateInstagramLink = (username) => {
    // Instagram doesn't have a direct DM API, open profile instead
    return `https://instagram.com/${username || 'afroboost'}`;
  };

  // === ENVOI DIRECT PAR CANAL ===
  
  // Obtenir les contacts pour l'envoi direct
  const getContactsForDirectSend = () => {
    if (newCampaign.targetType === "selected") {
      return allContacts.filter(c => selectedContactsForCampaign.includes(c.id));
    }
    return allContacts;
  };

  // GÃ©nÃ©rer mailto: groupÃ© avec BCC pour tous les emails
  const generateGroupedEmailLink = () => {
    const contacts = getContactsForDirectSend();
    const emails = contacts.map(c => c.email).filter(e => e && e.includes('@'));
    
    if (emails.length === 0) return null;
    
    const subject = newCampaign.name || "Afroboost - Message";
    const body = newCampaign.mediaUrl 
      ? `${newCampaign.message}\n\nð Voir le visuel: ${newCampaign.mediaUrl}`
      : newCampaign.message;
    
    // Premier email en "to", reste en BCC pour confidentialitÃ©
    const firstEmail = emails[0];
    const bccEmails = emails.slice(1).join(',');
    
    return `mailto:${firstEmail}?${bccEmails ? `bcc=${bccEmails}&` : ''}subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  };

  // Obtenir le contact WhatsApp actuel
  const getCurrentWhatsAppContact = () => {
    const contacts = getContactsForDirectSend().filter(c => c.phone);
    return contacts[currentWhatsAppIndex] || null;
  };

  // Passer au contact WhatsApp suivant
  const nextWhatsAppContact = () => {
    const contacts = getContactsForDirectSend().filter(c => c.phone);
    if (currentWhatsAppIndex < contacts.length - 1) {
      setCurrentWhatsAppIndex(currentWhatsAppIndex + 1);
    }
  };

  // Passer au contact WhatsApp prÃ©cÃ©dent
  const prevWhatsAppContact = () => {
    if (currentWhatsAppIndex > 0) {
      setCurrentWhatsAppIndex(currentWhatsAppIndex - 1);
    }
  };

  // Copier le message pour Instagram (avec fallback mobile robuste)
  const copyMessageForInstagram = async () => {
    const message = newCampaign.mediaUrl
      ? `${newCampaign.message}\n\n${newCampaign.mediaUrl}`
      : newCampaign.message;

    const result = await copyToClipboard(message);
    if (result.success) {
      setMessageCopied(true);
      setTimeout(() => setMessageCopied(false), 3000);
    }
  };

  // === FONCTIONS EMAIL RESEND (remplacent EmailJS) ===
  
  // Tester l'envoi email via Resend
  const handleTestEmail = async (e) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    if (!testEmailAddress || !testEmailAddress.includes('@')) {
      alert('Veuillez entrer une adresse email valide');
      return;
    }
    
    setTestEmailStatus('sending');
    
    try {
      const result = await performEmailSend(
        testEmailAddress,
        'Client Test',
        'Test Afroboost - Resend',
        'Ceci est un test d\'envoi via Resend. Si vous recevez ce message, tout fonctionne !'
      );
      
      if (result.success) {
        setTestEmailStatus('success');
        alert('â Email de test envoyÃ© avec succÃ¨s via Resend !');
      } else {
        setTestEmailStatus('error');
        alert(`â Erreur: ${result.error}`);
      }
    } catch (error) {
      setTestEmailStatus('error');
      alert(`â Erreur: ${error.message}`);
    }
    
    setTimeout(() => setTestEmailStatus(null), 3000);
  };

  // Envoyer la campagne email via Resend
  const handleSendEmailCampaign = async (e) => {
    // === BYPASS CRASH POSTHOG ===
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    console.log('EMAILJS_DEBUG: Campagne email dÃ©marrÃ©e');

    const contacts = getContactsForDirectSend();
    const emailContacts = contacts
      .filter(c => c.email && c.email.includes('@'))
      .map(c => ({ email: c.email, name: c.name }));

    if (emailContacts.length === 0) {
      alert('Aucun contact avec email valide');
      return;
    }

    if (!newCampaign.message.trim()) {
      alert('Veuillez saisir un message');
      return;
    }

    // Confirmation
    if (!window.confirm(`Envoyer ${emailContacts.length} email(s) automatiquement ?\n\nSujet: ${newCampaign.name || 'Afroboost - Message'}\n\nCette action est irrÃ©versible.`)) {
      return;
    }

    console.log('CAMPAGNE: Contacts =', emailContacts.length);

    setEmailSendingResults(null);
    setEmailSendingProgress({ current: 0, total: emailContacts.length, status: 'starting' });

    const results = { sent: 0, failed: 0, errors: [] };

    // === BOUCLE ENVOI BRUT ===
    for (let i = 0; i < emailContacts.length; i++) {
      const contact = emailContacts[i];
      
      if (!contact.email) {
        results.failed++;
        continue;
      }
      
      console.log("ENVOI A:", contact.email);
      console.log("MEDIA_URL_DEBUG: newCampaign.mediaUrl =", newCampaign.mediaUrl);
      
      // === ENVOI VIA BACKEND RESEND ===
      const result = await performEmailSend(
        contact.email, 
        contact.name || 'Client', 
        newCampaign.name || 'Afroboost - Message',
        newCampaign.message,
        newCampaign.mediaUrl || null
      );
      
      if (result.success) {
        results.sent++;
      } else {
        results.failed++;
        results.errors.push(contact.email);
      }
      
      // DÃ©lai
      await new Promise(r => setTimeout(r, 300));
    }

    console.log('CAMPAGNE TERMINÃE - EnvoyÃ©s:', results.sent, '- ÃchouÃ©s:', results.failed);

    setEmailSendingResults(results);
    setEmailSendingProgress(null);

    if (results.sent > 0) {
      alert(`â EnvoyÃ©s: ${results.sent} / ÃchouÃ©s: ${results.failed}`);
    } else {
      alert(`â Ãchec total. Erreurs: ${results.errors.join(', ')}`);
    }
  };

  // === WHATSAPP API FUNCTIONS ===
  
  // === FONCTION ENVOI WHATSAPP DIRECT AVEC LOG ===
  // Log clair pour vÃ©rifier que les donnÃ©es circulent
  const sendWhatsAppMessageDirect = async (phoneNumber, message, mediaUrl = null) => {
    const config = whatsAppConfig;
    
    // LOG CLAIR: Afficher toutes les donnÃ©es envoyÃ©es
    console.log('ð± === ENVOI WHATSAPP ===');
    console.log('ð± Envoi WhatsApp vers:', phoneNumber);
    console.log('ð± Message:', message);
    console.log('ð± Media URL:', mediaUrl || 'Aucun');
    console.log('ð± Avec SID:', config.accountSid || 'NON CONFIGURÃ');
    console.log('ð± Auth Token:', config.authToken ? '***' + config.authToken.slice(-4) : 'NON CONFIGURÃ');
    console.log('ð± From Number:', config.fromNumber || 'NON CONFIGURÃ');
    
    // VÃ©rifier la configuration
    if (!config.accountSid || !config.authToken || !config.fromNumber) {
      console.error('â Configuration WhatsApp/Twilio incomplÃ¨te');
      return { 
        success: false, 
        error: 'Configuration Twilio incomplÃ¨te. VÃ©rifiez Account SID, Auth Token et From Number.' 
      };
    }
    
    // Formater le numÃ©ro au format E.164
    let formattedPhone = phoneNumber.replace(/[^\d+]/g, '');
    if (!formattedPhone.startsWith('+')) {
      if (formattedPhone.startsWith('0')) {
        formattedPhone = '+41' + formattedPhone.substring(1);
      } else {
        formattedPhone = '+' + formattedPhone;
      }
    }
    
    console.log('ð± NumÃ©ro formatÃ©:', formattedPhone);
    
    // Construire les donnÃ©es pour Twilio
    const formData = new URLSearchParams();
    formData.append('From', `whatsapp:${config.fromNumber.startsWith('+') ? config.fromNumber : '+' + config.fromNumber}`);
    formData.append('To', `whatsapp:${formattedPhone}`);
    formData.append('Body', message);
    
    if (mediaUrl) {
      formData.append('MediaUrl', mediaUrl);
    }
    
    console.log('ð± DonnÃ©es Twilio:', Object.fromEntries(formData));
    
    try {
      // Appel DIRECT Ã  l'API Twilio
      const response = await fetch(
        `https://api.twilio.com/2010-04-01/Accounts/${config.accountSid}/Messages.json`,
        {
          method: 'POST',
          headers: {
            'Authorization': 'Basic ' + btoa(`${config.accountSid}:${config.authToken}`),
            'Content-Type': 'application/x-www-form-urlencoded'
          },
          body: formData
        }
      );
      
      const data = await response.json();
      console.log('ð± RÃ©ponse Twilio:', data);
      
      if (!response.ok) {
        return { success: false, error: data.message || `HTTP ${response.status}`, code: data.code };
      }
      
      return { success: true, sid: data.sid, status: data.status };
    } catch (error) {
      console.error('â Erreur Twilio:', error);
      return { success: false, error: error.message };
    }
  };
  
  // Sauvegarder la configuration WhatsApp
  const handleSaveWhatsAppConfig = async () => {
    const success = await saveWhatsAppConfig(whatsAppConfig);
    if (success) {
      setShowWhatsAppConfig(false);
      alert('â Configuration WhatsApp API sauvegardÃ©e !');
    } else {
      alert('â Erreur lors de la sauvegarde');
    }
  };

  // === FONCTION TEST WHATSAPP - ISOLATION COMPLÃTE ===
  // Utilise la fonction autonome performWhatsAppSend pour Ã©viter les conflits PostHog
  const handleTestWhatsApp = async (e) => {
    // === BLOCAGE CRASH POSTHOG ===
    // Ces lignes DOIVENT Ãªtre en premier, avant toute autre logique
    e.preventDefault();
    e.stopPropagation();
    
    // Validation basique
    if (!testWhatsAppNumber) {
      alert('Veuillez entrer un numÃ©ro de tÃ©lÃ©phone pour le test');
      return;
    }
    
    // Sauvegarder la config (peut Ãªtre ignorÃ© si PostHog crash)
    try {
      await handleSaveWhatsAppConfig();
    } catch (saveError) {
      console.warn('PostHog bloquÃ© sur sauvegarde mais envoi maintenu:', saveError);
    }
    
    // Mise Ã  jour UI - dans un try/catch sÃ©parÃ© pour isoler PostHog
    try {
      setTestWhatsAppStatus('sending');
    } catch (stateError) {
      console.warn('PostHog bloquÃ© sur setState mais envoi maintenu:', stateError);
    }
    
    // === ENVOI TECHNIQUE - ISOLÃ DE LA GESTION D'ÃTAT ===
    try {
      // Appel de la fonction autonome (hors composant React)
      const result = await performWhatsAppSend(
        testWhatsAppNumber,
        'ð Test Afroboost WhatsApp API!\n\nVotre configuration Twilio fonctionne correctement.',
        whatsAppConfig
      );
      
      // Gestion du rÃ©sultat - Ã©galement isolÃ©e
      try {
        if (result.success) {
          setTestWhatsAppStatus('success');
          if (result.simulated) {
            // Mode simulation
            setTimeout(() => setTestWhatsAppStatus(null), 3000);
          } else {
            alert(`â WhatsApp de test envoyÃ© avec succÃ¨s !\n\nSID: ${result.sid}`);
            setTimeout(() => setTestWhatsAppStatus(null), 5000);
          }
        } else {
          setTestWhatsAppStatus('error');
          alert(`â Erreur Twilio: ${result.error}`);
          setTimeout(() => setTestWhatsAppStatus(null), 3000);
        }
      } catch (uiError) {
        console.warn('PostHog bloquÃ© sur UI update mais envoi rÃ©ussi:', uiError);
        if (result.success) {
          alert('â WhatsApp envoyÃ© (UI bloquÃ©e par PostHog)');
        }
      }
    } catch (sendError) {
      console.error('â Erreur envoi WhatsApp:', sendError);
      try {
        setTestWhatsAppStatus('error');
        alert(`â Erreur technique: ${sendError.message}`);
        setTimeout(() => setTestWhatsAppStatus(null), 3000);
      } catch (e) {
        console.warn('PostHog bloquÃ© mais erreur signalÃ©e:', e);
        alert(`â Erreur: ${sendError.message}`);
      }
    }
  };

  // Envoyer la campagne WhatsApp automatiquement - avec isolation PostHog
  const handleSendWhatsAppCampaign = async (e) => {
    // EmpÃªcher le rafraÃ®chissement et la propagation (isolation PostHog)
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    if (!isWhatsAppConfigured()) {
      alert('â ï¸ WhatsApp API non configurÃ©. Cliquez sur "âï¸ Config" pour ajouter vos clÃ©s Twilio.');
      return;
    }

    const contacts = getContactsForDirectSend();
    const phoneContacts = contacts
      .filter(c => c.phone)
      .map(c => ({ phone: c.phone, name: c.name }));

    if (phoneContacts.length === 0) {
      alert('Aucun contact avec numÃ©ro de tÃ©lÃ©phone');
      return;
    }

    if (!newCampaign.message.trim()) {
      alert('Veuillez saisir un message');
      return;
    }

    if (!window.confirm(`Envoyer ${phoneContacts.length} WhatsApp automatiquement ?\n\nâ ï¸ Cette action utilise votre quota Twilio et est irrÃ©versible.`)) {
      return;
    }

    setWhatsAppSendingResults(null);
    setWhatsAppSendingProgress({ current: 0, total: phoneContacts.length, status: 'starting' });

    try {
      const results = await sendBulkWhatsApp(
        phoneContacts,
        {
          message: newCampaign.message,
          mediaUrl: newCampaign.mediaUrl
        },
        (current, total, status, name) => {
          setWhatsAppSendingProgress({ current, total, status, name });
        }
      );

      setWhatsAppSendingResults(results);
      setWhatsAppSendingProgress(null);
      
      // Notification de succÃ¨s
      if (results.sent > 0) {
        alert(`â Campagne WhatsApp terminÃ©e !\n\nâ EnvoyÃ©s: ${results.sent}\nâ ÃchouÃ©s: ${results.failed}`);
      } else {
        alert(`â Ãchec de la campagne WhatsApp.\n\nErreurs: ${results.errors.join('\n')}`);
      }
    } catch (error) {
      console.error('â WhatsApp campaign error:', error);
      setWhatsAppSendingProgress(null);
      alert(`â Erreur lors de l'envoi: ${error.message}`);
    }
  };

  // === ENVOI GROUPÃ (EMAIL + WHATSAPP) ===
  const handleBulkSendCampaign = async (e) => {
    // Protection PostHog - EmpÃªcher la propagation d'Ã©vÃ©nements
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    const contacts = getContactsForDirectSend();
    const emailContacts = contacts
      .filter(c => c.email && c.email.includes('@'))
      .map(c => ({ email: c.email, name: c.name }));
    const phoneContacts = contacts
      .filter(c => c.phone)
      .map(c => ({ phone: c.phone, name: c.name }));

    // Resend est toujours configurÃ© cÃ´tÃ© serveur
    const hasEmail = emailContacts.length > 0;
    const hasWhatsApp = isWhatsAppConfigured() && phoneContacts.length > 0;

    if (!hasEmail && !hasWhatsApp) {
      alert('â ï¸ Aucun contact avec email ou tÃ©lÃ©phone disponible.');
      return;
    }

    if (!newCampaign.message.trim()) {
      alert('Veuillez saisir un message');
      return;
    }

    const channels = [];
    if (hasEmail) channels.push(`${emailContacts.length} emails`);
    if (hasWhatsApp) channels.push(`${phoneContacts.length} WhatsApp`);

    if (!window.confirm(`Envoi automatique :\nâ¢ ${channels.join('\nâ¢ ')}\n\nâ ï¸ Cette action est irrÃ©versible.`)) {
      return;
    }

    setBulkSendingInProgress(true);
    setBulkSendingResults(null);
    
    const results = { email: null, whatsapp: null };

    try {
      // Envoyer les emails d'abord
      if (hasEmail) {
        setBulkSendingProgress({ channel: 'email', current: 0, total: emailContacts.length, name: '' });
        results.email = await sendBulkEmails(
          emailContacts,
          {
            name: newCampaign.name || 'Afroboost - Message',
            message: newCampaign.message,
            mediaUrl: newCampaign.mediaUrl
          },
          (current, total, status, name) => {
            setBulkSendingProgress({ channel: 'email', current, total, name });
          }
        );
      }

      // Puis les WhatsApp
      if (hasWhatsApp) {
        setBulkSendingProgress({ channel: 'whatsapp', current: 0, total: phoneContacts.length, name: '' });
        results.whatsapp = await sendBulkWhatsApp(
          phoneContacts,
          {
            message: newCampaign.message,
            mediaUrl: newCampaign.mediaUrl
          },
          (current, total, status, name) => {
            setBulkSendingProgress({ channel: 'whatsapp', current, total, name });
          }
        );
      }

      // Notification de succÃ¨s
      const emailSent = results.email?.sent || 0;
      const emailFailed = results.email?.failed || 0;
      const waSent = results.whatsapp?.sent || 0;
      const waFailed = results.whatsapp?.failed || 0;
      
      alert(`â Campagne terminÃ©e !\n\nð§ Emails: ${emailSent} envoyÃ©s, ${emailFailed} Ã©chouÃ©s\nð± WhatsApp: ${waSent} envoyÃ©s, ${waFailed} Ã©chouÃ©s`);
    } catch (error) {
      console.error('â Bulk campaign error:', error);
      alert(`â Erreur lors de l'envoi: ${error.message}`);
    } finally {
      setBulkSendingProgress(null);
      setBulkSendingInProgress(false);
      setBulkSendingResults(results);
    }
    
    // Mettre Ã  jour le dernier mÃ©dia envoyÃ© pour l'IA
    if (newCampaign.mediaUrl) {
      setLastMediaUrlService(newCampaign.mediaUrl);
      // Aussi mettre Ã  jour cÃ´tÃ© backend
      axios.put(`${API}/ai-config`, { lastMediaUrl: newCampaign.mediaUrl }).catch(() => {});
    }
  };

  // === IA WHATSAPP FUNCTIONS ===
  
  // Charger la config IA depuis le backend
  const loadAIConfig = async () => {
    try {
      const res = await axios.get(`${API}/ai-config`);
      setAiConfig(res.data);
    } catch (err) {
      console.error("Error loading AI config:", err);
    }
  };

  // Charger les logs IA
  const loadAILogs = async () => {
    try {
      const res = await axios.get(`${API}/ai-logs`);
      setAiLogs(res.data || []);
    } catch (err) {
      console.error("Error loading AI logs:", err);
    }
  };

  // Sauvegarder la config IA
  const handleSaveAIConfig = async () => {
    try {
      await axios.put(`${API}/ai-config`, aiConfig);
      alert('â Configuration IA sauvegardÃ©e !');
    } catch (err) {
      alert('â Erreur lors de la sauvegarde');
    }
  };

  // Tester l'IA
  const handleTestAI = async () => {
    if (!aiTestMessage.trim()) {
      alert('Veuillez entrer un message de test');
      return;
    }
    
    setAiTestLoading(true);
    setAiTestResponse(null);
    
    try {
      const res = await axios.post(`${API}/ai-test`, {
        message: aiTestMessage,
        clientName: 'Test User'
      });
      setAiTestResponse(res.data);
    } catch (err) {
      setAiTestResponse({ success: false, error: err.response?.data?.detail || err.message });
    }
    
    setAiTestLoading(false);
  };

  // Effacer les logs IA
  const handleClearAILogs = async () => {
    if (!window.confirm('Effacer tous les logs IA ?')) return;
    try {
      await axios.delete(`${API}/ai-logs`);
      setAiLogs([]);
    } catch (err) {
      console.error("Error clearing AI logs:", err);
    }
  };

  // Stats des contacts pour envoi - calcul direct sans fonction
  const contactStats = useMemo(() => {
    const contacts = newCampaign.targetType === "selected" 
      ? allContacts.filter(c => selectedContactsForCampaign.includes(c.id))
      : allContacts;
    return {
      total: contacts.length,
      withEmail: contacts.filter(c => c.email && c.email.includes('@')).length,
      withPhone: contacts.filter(c => c.phone).length,
    };
  }, [allContacts, selectedContactsForCampaign, newCampaign.targetType]);

  // Mark result as sent
  const markResultSent = async (campaignId, contactId, channel) => {
    try {
      await axios.post(`${API}/campaigns/${campaignId}/mark-sent`, { contactId, channel });
      const res = await axios.get(`${API}/campaigns/${campaignId}`);
      setCampaigns(campaigns.map(c => c.id === campaignId ? res.data : c));
    } catch (err) { console.error("Error marking sent:", err); }
  };

  // Update shipping tracking for a reservation
  const updateTracking = async (reservationId, trackingNumber, shippingStatus) => {
    try {
      await axios.put(`${API}/reservations/${reservationId}/tracking`, { trackingNumber, shippingStatus });
      const res = await axios.get(`${API}/reservations`);
      setReservations(res.data);
    } catch (err) { console.error("Error updating tracking:", err); }
  };

  // v37.2: "Ma Page" et "Paiements" supprimÃ©s â centralisÃ©s dans le HUB Gestion
  const baseTabs = [
    { id: "reservations", label: t('reservations') },
    { id: "offers", label: "ðï¸ Gestion" },
    { id: "codes", label: t('promoCodes') },
    { id: "contacts", label: "ð Contacts" },
    { id: "campaigns", label: "ð¢ Campagnes" },
    { id: "conversations", label: unreadCount > 0 ? `ð¬ Conversations (${unreadCount})` : "ð¬ Conversations" }
  ];

  // v37.2: Boutique et Stripe pour coachs partenaires uniquement
  const tabs = !isSuperAdmin
    ? [...baseTabs, { id: "boutique", label: "ð Boutique" }, { id: "stripe", label: "ð Mon Stripe" }]
    : [...baseTabs];

  // v9.2.5: COMPOSANT DE SECOURS - Affiche le squelette du dashboard pendant le chargement
  // Garantit qu'on ne voit JAMAIS une page blanche
  const LoadingFallback = () => (
    <div className="w-full min-h-screen p-6 section-gradient" data-testid="dashboard-loading">
      <div className="max-w-6xl mx-auto">
        {/* Header avec logo Afroboost */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="font-bold text-white" style={{ fontSize: '28px' }}>
              {isSuperAdmin ? 'Afroboost' : 'Mon Espace Partenaire'}
            </h1>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-white/60 text-sm">
                ConnectÃ© en tant que <span className="text-purple-400">{displayEmail}</span>
              </span>
              {/* v68: Badge MODE SUPER ADMIN / COMPTE PARTENAIRE */}
              <span
                className="ml-2 px-3 py-1 rounded-full text-xs font-bold tracking-wide"
                style={{
                  background: isSuperAdmin
                    ? 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.3))'
                    : 'rgba(255,255,255,0.08)',
                  color: isSuperAdmin ? '#D91CD2' : '#a78bfa',
                  border: `1px solid ${isSuperAdmin ? 'rgba(217,28,210,0.6)' : 'rgba(167,139,250,0.3)'}`
                }}
              >
                {isSuperAdmin ? 'ð SUPER ADMIN : ACCÃS ILLIMITÃ' : 'COMPTE PARTENAIRE'}
              </span>
              {!isSuperAdmin && (
                <span
                  className="px-2 py-1 rounded-full text-xs font-bold"
                  style={{
                    background: coachCredits > 0 ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.2)',
                    color: coachCredits > 0 ? '#22c55e' : '#ef4444',
                    border: `1px solid ${coachCredits > 0 ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)'}`
                  }}
                >
                  CrÃ©dits : {coachCredits}
                </span>
              )}
            </div>
          </div>
        </div>
        
        {/* Onglets squelette */}
        <div className="flex flex-wrap gap-2 mb-6">
          {['RÃ©servations', 'ðï¸ Gestion', 'ðª Ma Page', 'Codes promo', 'Contacts', 'Campagnes', 'Conversations'].map((tabName, i) => (
            <div 
              key={i}
              className="px-4 py-2 rounded-lg text-white/60 text-sm"
              style={{ background: i === 0 ? 'rgba(217,28,210,0.3)' : 'rgba(255,255,255,0.1)' }}
            >
              {tabName}
            </div>
          ))}
        </div>
        
        {/* Message de chargement */}
        <div 
          className="p-8 rounded-xl text-center"
          style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(217,28,210,0.3)' }}
        >
          <div className="text-4xl mb-4 animate-pulse">â³</div>
          <h2 className="text-xl font-bold text-white mb-2">Initialisation de votre espace...</h2>
          <p className="text-white/60">Chargement de vos donnÃ©es en cours</p>
        </div>
      </div>
    </div>
  );

  // v9.2.5: Si le dashboard n'est pas prÃªt aprÃ¨s 2 secondes, afficher le fallback
  // (Mais normalement dashboardReady passe Ã  true aprÃ¨s 100ms)
  
  return (
    <div className="w-full min-h-screen p-6 section-gradient">
      {/* QR Scanner Modal with Camera Support */}
      {showScanner && (
        <QRScannerModal 
          onClose={() => { setShowScanner(false); setScanResult(null); setScanError(null); }}
          onValidate={validateReservation}
          scanResult={scanResult}
          scanError={scanError}
          onManualValidation={handleManualValidation}
        />
      )}

      {/* ========== v17.5: STUDIO AUDIO MODAL ========== */}
      {showAudioModal && selectedCourseForAudio && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.9)' }}>
          <div
            style={{
              width: '100%',
              maxWidth: '700px',
              maxHeight: '90vh',
              overflowY: 'auto',
              borderRadius: '20px',
              padding: '28px',
              background: 'linear-gradient(180deg, rgba(15,5,25,0.95) 0%, rgba(5,0,15,0.98) 100%)',
              border: '1px solid rgba(217,28,210,0.3)',
              boxShadow: '0 0 60px rgba(217,28,210,0.15), 0 0 120px rgba(139,92,246,0.08)',
              backdropFilter: 'blur(20px)',
              position: 'relative',
              overflow: 'hidden'
            }}
            className="custom-scrollbar"
          >
            {/* Background glow */}
            <div style={{
              position: 'absolute', top: '-80px', right: '-80px', width: '250px', height: '250px',
              borderRadius: '50%', background: 'radial-gradient(circle, rgba(217,28,210,0.12), transparent 70%)',
              filter: 'blur(40px)', pointerEvents: 'none'
            }} />
            <div style={{
              position: 'absolute', bottom: '-60px', left: '-60px', width: '200px', height: '200px',
              borderRadius: '50%', background: 'radial-gradient(circle, rgba(139,92,246,0.1), transparent 70%)',
              filter: 'blur(30px)', pointerEvents: 'none'
            }} />

            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px', position: 'relative', zIndex: 1 }}>
              <div>
                <h2 style={{ fontSize: '22px', fontWeight: 800, color: '#fff', display: 'flex', alignItems: 'center', gap: '10px', margin: 0 }}>
                  <span style={{ fontSize: '28px' }}>ðµ</span> Studio Audio
                </h2>
                <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '13px', margin: '4px 0 0 0' }}>
                  Cours : <span style={{ color: '#d91cd2' }}>{selectedCourseForAudio.name}</span>
                  {audioTracks.length > 0 && <span style={{ marginLeft: '8px', color: 'rgba(255,255,255,0.3)' }}>â¢ {audioTracks.length} piste{audioTracks.length > 1 ? 's' : ''}</span>}
                </p>
              </div>
              <button
                onClick={() => setShowAudioModal(false)}
                style={{ background: 'rgba(255,255,255,0.1)', border: 'none', borderRadius: '10px', padding: '8px', cursor: 'pointer', color: '#fff' }}
              >
                <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>

            {/* Drag & Drop Zone */}
            <div
              style={{
                position: 'relative', zIndex: 1,
                border: '2px dashed rgba(217,28,210,0.4)',
                borderRadius: '16px',
                padding: '28px',
                textAlign: 'center',
                marginBottom: '24px',
                background: 'rgba(217,28,210,0.04)',
                cursor: 'pointer',
                transition: 'all 0.3s ease'
              }}
              onClick={() => audioFileInputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); e.currentTarget.style.borderColor = 'rgba(217,28,210,0.8)'; e.currentTarget.style.background = 'rgba(217,28,210,0.1)'; }}
              onDragLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(217,28,210,0.4)'; e.currentTarget.style.background = 'rgba(217,28,210,0.04)'; }}
              onDrop={(e) => { e.preventDefault(); e.currentTarget.style.borderColor = 'rgba(217,28,210,0.4)'; e.currentTarget.style.background = 'rgba(217,28,210,0.04)'; handleAudioFileUpload(e.dataTransfer.files); }}
            >
              <input
                ref={audioFileInputRef}
                type="file"
                accept="audio/mpeg,audio/mp3,audio/wav,audio/ogg,audio/aac,.mp3,.wav,.ogg,.aac"
                multiple
                style={{ display: 'none' }}
                onChange={(e) => handleAudioFileUpload(e.target.files)}
              />
              <input
                ref={audioCoverInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                style={{ display: 'none' }}
                onChange={(e) => { if (e.target.files[0] && coverUploadTrackId) { handleCoverUpload(e.target.files[0], coverUploadTrackId); } }}
              />
              {uploadingAudio ? (
                <div>
                  <div style={{ fontSize: '36px', marginBottom: '8px' }}>â³</div>
                  <p style={{ color: '#d91cd2', fontWeight: 600, fontSize: '14px' }}>Upload en cours...</p>
                </div>
              ) : (
                <div>
                  <div style={{ fontSize: '42px', marginBottom: '8px', filter: 'drop-shadow(0 0 12px rgba(217,28,210,0.5))' }}>ð¶</div>
                  <p style={{ color: '#fff', fontWeight: 700, fontSize: '15px', marginBottom: '4px' }}>Glissez vos fichiers audio ici</p>
                  <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px' }}>ou cliquez pour sÃ©lectionner â¢ MP3, WAV, OGG, AAC (max 15MB)</p>
                </div>
              )}
            </div>

            {/* Tracks List */}
            <div style={{ position: 'relative', zIndex: 1 }}>
              {audioTracks.length === 0 ? (
                <div style={{ padding: '24px', borderRadius: '14px', textAlign: 'center', background: 'rgba(255,255,255,0.03)' }}>
                  <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '13px' }}>Aucune piste audio</p>
                  <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px', marginTop: '4px' }}>Glissez des fichiers MP3/WAV ci-dessus pour commencer</p>
                </div>
              ) : (
                <div ref={el => window._audioListRef1 = el} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {audioTracks.sort((a, b) => a.order - b.order).map((track, index) => (
                    <div
                      key={track.id}
                      draggable
                      onDragStart={(e) => handleTrackDragStart(e, track.id)}
                      onDragOver={(e) => handleTrackDragOver(e, index)}
                      onDrop={(e) => handleTrackDrop(e, index)}
                      onTouchStart={(e) => handleTrackTouchStart(e, track.id)}
                      onTouchMove={(e) => handleTrackTouchMove(e, window._audioListRef1)}
                      onTouchEnd={handleTrackTouchEnd}
                      onDragEnd={() => { setDragOverIndex(null); setDraggedTrackId(null); }}
                      style={{
                        borderRadius: '14px',
                        padding: editingTrackId === track.id ? '16px' : '12px',
                        background: dragOverIndex === index
                          ? 'rgba(217,28,210,0.15)'
                          : 'rgba(255,255,255,0.04)',
                        border: dragOverIndex === index
                          ? '1px solid rgba(217,28,210,0.5)'
                          : '1px solid rgba(255,255,255,0.06)',
                        transition: 'all 0.2s ease',
                        cursor: 'grab',
                        opacity: draggedTrackId === track.id ? 0.5 : 1
                      }}
                    >
                      {/* Track compact view */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        {/* Reorder buttons (touch-friendly) + drag handle */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', flexShrink: 0 }}>
                          <button onClick={(e) => { e.stopPropagation(); if (index === 0) return; const sorted = [...audioTracks].sort((a,b) => a.order - b.order); const updated = [...sorted]; const [moved] = updated.splice(index, 1); updated.splice(index - 1, 0, moved); setAudioTracks(updated.map((t, i) => ({ ...t, order: i }))); }}
                            style={{ width: '24px', height: '20px', border: 'none', borderRadius: '4px', background: index === 0 ? 'transparent' : 'rgba(255,255,255,0.08)', color: index === 0 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.5)', cursor: index === 0 ? 'default' : 'pointer', fontSize: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>â²</button>
                          <button onClick={(e) => { e.stopPropagation(); const sorted = [...audioTracks].sort((a,b) => a.order - b.order); if (index >= sorted.length - 1) return; const updated = [...sorted]; const [moved] = updated.splice(index, 1); updated.splice(index + 1, 0, moved); setAudioTracks(updated.map((t, i) => ({ ...t, order: i }))); }}
                            style={{ width: '24px', height: '20px', border: 'none', borderRadius: '4px', background: index >= audioTracks.length - 1 ? 'transparent' : 'rgba(255,255,255,0.08)', color: index >= audioTracks.length - 1 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.5)', cursor: index >= audioTracks.length - 1 ? 'default' : 'pointer', fontSize: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>â¼</button>
                        </div>

                        {/* Cover thumbnail */}
                        <div
                          onClick={(e) => { e.stopPropagation(); setCoverUploadTrackId(track.id); audioCoverInputRef.current?.click(); }}
                          style={{
                            width: '52px', height: '52px', borderRadius: '10px', flexShrink: 0,
                            background: track.cover_url ? `url(${track.cover_url}) center/cover` : 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.2))',
                            border: '2px solid rgba(217,28,210,0.3)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            cursor: 'pointer', position: 'relative', overflow: 'hidden',
                            boxShadow: '0 0 15px rgba(217,28,210,0.2)'
                          }}
                        >
                          {!track.cover_url && <span style={{ fontSize: '20px' }}>ðµ</span>}
                          <div style={{
                            position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.5)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            opacity: 0, transition: 'opacity 0.2s'
                          }}
                            onMouseEnter={(e) => { e.currentTarget.style.opacity = '1'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.opacity = '0'; }}
                          >
                            <span style={{ fontSize: '14px' }}>ð·</span>
                          </div>
                        </div>

                        {/* Track info */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <p style={{ color: '#fff', fontSize: '14px', fontWeight: 600, margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {track.title}
                          </p>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px', flexWrap: 'wrap' }}>
                            {track.price > 0 ? (
                              <span style={{ fontSize: '11px', color: '#22c55e', fontWeight: 600 }}>{track.price} CHF</span>
                            ) : (
                              <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)' }}>Gratuit</span>
                            )}
                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.2)' }}>â¢</span>
                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)' }}>Preview {track.preview_duration}s</span>
                            <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.2)' }}>â¢</span>
                            <span style={{
                              fontSize: '10px', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                              background: track.visible !== false ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                              color: track.visible !== false ? '#22c55e' : '#ef4444',
                              border: track.visible !== false ? '1px solid rgba(34,197,94,0.3)' : '1px solid rgba(239,68,68,0.3)'
                            }}>
                              {track.visible !== false ? 'En vente' : 'MasquÃ©'}
                            </span>
                          </div>
                        </div>

                        {/* Actions */}
                        <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                          <button
                            onClick={(e) => { e.stopPropagation(); setEditingTrackId(editingTrackId === track.id ? null : track.id); }}
                            style={{
                              width: '32px', height: '32px', borderRadius: '8px', border: 'none',
                              background: editingTrackId === track.id ? 'rgba(217,28,210,0.3)' : 'rgba(255,255,255,0.08)',
                              color: editingTrackId === track.id ? '#d91cd2' : 'rgba(255,255,255,0.5)',
                              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px'
                            }}
                            title="Ãditer"
                          >âï¸</button>
                          <button
                            onClick={(e) => { e.stopPropagation(); removeTrack(track.id); }}
                            style={{
                              width: '32px', height: '32px', borderRadius: '8px', border: 'none',
                              background: 'rgba(239,68,68,0.1)', color: '#ef4444',
                              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px'
                            }}
                            title="Supprimer"
                          >ðï¸</button>
                        </div>
                      </div>

                      {/* Expanded edit form */}
                      {editingTrackId === track.id && (
                        <div style={{ marginTop: '14px', paddingTop: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                          <div style={{ gridColumn: '1 / -1' }}>
                            <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Titre</label>
                            <input
                              type="text"
                              value={track.title}
                              onChange={(e) => updateTrackField(track.id, 'title', e.target.value)}
                              style={{
                                width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                                background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                                color: '#fff', outline: 'none'
                              }}
                            />
                          </div>
                          <div style={{ gridColumn: '1 / -1' }}>
                            <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Description</label>
                            <textarea
                              value={track.description || ''}
                              onChange={(e) => updateTrackField(track.id, 'description', e.target.value)}
                              rows={2}
                              style={{
                                width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                                background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                                color: '#fff', outline: 'none', resize: 'vertical'
                              }}
                              placeholder="Description de la piste..."
                            />
                          </div>
                          {/* Cover URL input */}
                          <div style={{ gridColumn: '1 / -1' }}>
                            <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>
                              Lien image de couverture (ou cliquez la miniature pour uploader)
                            </label>
                            <input
                              type="url"
                              value={track.cover_url || ''}
                              onChange={(e) => updateTrackField(track.id, 'cover_url', e.target.value || null)}
                              style={{
                                width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                                background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                                color: '#fff', outline: 'none'
                              }}
                              placeholder="https://exemple.com/cover.jpg"
                            />
                          </div>
                          <div>
                            <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Prix (CHF) â 0 = gratuit</label>
                            <input
                              type="number"
                              min="0"
                              step="0.5"
                              value={track.price}
                              onChange={(e) => updateTrackField(track.id, 'price', parseFloat(e.target.value) || 0)}
                              style={{
                                width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                                background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                                color: '#fff', outline: 'none'
                              }}
                            />
                          </div>
                          <div>
                            <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Preview (secondes)</label>
                            <input
                              type="number"
                              min="5"
                              max="120"
                              value={track.preview_duration}
                              onChange={(e) => updateTrackField(track.id, 'preview_duration', parseInt(e.target.value) || 30)}
                              style={{
                                width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px',
                                background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                                color: '#fff', outline: 'none'
                              }}
                            />
                          </div>
                          {/* Toggle "En vente" */}
                          <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: '12px', paddingTop: '6px' }}>
                            <div
                              onClick={() => updateTrackField(track.id, 'visible', track.visible === false ? true : false)}
                              style={{
                                width: '44px', height: '24px', borderRadius: '12px', cursor: 'pointer',
                                background: track.visible !== false
                                  ? 'linear-gradient(135deg, #22c55e, #16a34a)'
                                  : 'rgba(255,255,255,0.15)',
                                position: 'relative', transition: 'all 0.3s ease',
                                boxShadow: track.visible !== false ? '0 0 10px rgba(34,197,94,0.3)' : 'none'
                              }}
                            >
                              <div style={{
                                width: '18px', height: '18px', borderRadius: '50%', background: '#fff',
                                position: 'absolute', top: '3px',
                                left: track.visible !== false ? '23px' : '3px',
                                transition: 'left 0.3s ease',
                                boxShadow: '0 1px 3px rgba(0,0,0,0.3)'
                              }} />
                            </div>
                            <span style={{ color: track.visible !== false ? '#22c55e' : 'rgba(255,255,255,0.4)', fontSize: '13px', fontWeight: 600 }}>
                              {track.visible !== false ? 'En vente sur la vitrine' : 'MasquÃ© (non visible)'}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: '12px', marginTop: '24px', position: 'relative', zIndex: 1 }}>
              <button
                onClick={() => setShowAudioModal(false)}
                style={{
                  flex: 1, padding: '14px', borderRadius: '12px', fontSize: '14px',
                  background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)',
                  color: '#fff', cursor: 'pointer'
                }}
              >
                Annuler
              </button>
              <button
                onClick={saveAudioStudio}
                disabled={savingPlaylist}
                style={{
                  flex: 1, padding: '14px', borderRadius: '12px', fontSize: '14px', fontWeight: 700,
                  background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                  border: 'none', color: '#fff', cursor: 'pointer',
                  opacity: savingPlaylist ? 0.7 : 1,
                  boxShadow: '0 0 20px rgba(217,28,210,0.3)'
                }}
                data-testid="save-playlist-btn"
              >
                {savingPlaylist ? 'â³ Sauvegarde...' : 'ð¾ Sauvegarder le Studio'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* === PANNEAU SUPER ADMIN v8.9 === */}
      {showAdminPanel && (
        <SuperAdminPanel 
          userEmail={coachUser?.email}
          onClose={() => setShowAdminPanel(false)}
        />
      )}

      {/* v9.5.7: BOUTON DÃCONNEXION FIXED - Toujours visible en haut Ã  droite */}
      <button 
        onClick={handleSecureLogout} 
        className="flex items-center gap-1 px-3 py-2 rounded-lg text-white text-xs font-medium shadow-lg"
        style={{ 
          position: 'fixed',
          top: '12px',
          right: '12px',
          zIndex: 9999,
          background: 'rgba(239, 68, 68, 0.9)', 
          border: '1px solid rgba(239, 68, 68, 0.8)',
          backdropFilter: 'blur(8px)'
        }}
        data-testid="coach-logout-fixed"
      >
        ðª DÃ©connexion
      </button>
      
      {/* v10.6: BOUTON RETOUR - IcÃ´ne flÃ¨che en haut Ã  gauche */}
      <button 
        onClick={onBack}
        className="flex items-center justify-center w-10 h-10 rounded-full transition-all hover:scale-110"
        style={{ 
          position: 'fixed',
          top: '12px',
          left: '12px',
          zIndex: 9999,
          background: 'rgba(139, 92, 246, 0.3)', 
          border: '1px solid rgba(217, 28, 210, 0.4)',
          backdropFilter: 'blur(8px)',
          boxShadow: '0 0 10px rgba(217, 28, 210, 0.2)'
        }}
        data-testid="coach-back"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
      </button>

      {/* v10.6: Container principal avec scroll */}
      <div className="max-w-6xl mx-auto px-4" style={{ paddingTop: '60px', paddingBottom: '100px', overflowY: 'auto', minHeight: '100vh' }}>
        <div className="flex justify-between items-start mb-6 flex-wrap gap-4">
          <div className="flex-1 min-w-0">
            {/* v9.1.3: Marque blanche - Affiche platform_name ou "Mon Espace Afroboost" */}
            <h1 className="font-bold text-white text-2xl" data-testid="dashboard-title">
              {dashboardTitle}
            </h1>
            {/* Affichage de l'utilisateur connectÃ© via Google OAuth */}
            {coachUser && (
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                {coachUser.picture && (
                  <img 
                    src={coachUser.picture} 
                    alt={coachUser.name} 
                    className="w-6 h-6 rounded-full"
                    style={{ border: '2px solid #d91cd2' }}
                  />
                )}
                <span className="text-white/60 text-sm">
                  ConnectÃ© en tant que <span className="text-purple-400">{coachUser.email}</span>
                </span>
                {/* === v9.5.9: JAUGE DE CRÃDITS VISUELLE - Barre de progression Ã©lÃ©gante === */}
                {!isSuperAdmin && (
                  <div className="flex items-center gap-2 flex-wrap">
                    {/* Badge avec nombre de crÃ©dits */}
                    <div 
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                      style={{
                        background: coachCredits <= 0 ? 'rgba(239,68,68,0.15)' : 'rgba(217,28,210,0.15)',
                        border: coachCredits <= 0 ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(217,28,210,0.4)'
                      }}
                      data-testid="coach-credits-badge"
                    >
                      <span style={{ color: coachCredits <= 0 ? '#ef4444' : '#D91CD2' }}>ð°</span>
                      <div className="flex flex-col">
                        <span 
                          className="text-xs font-bold"
                          style={{ color: coachCredits <= 0 ? '#ef4444' : '#D91CD2' }}
                        >
                          {coachCredits <= 0 ? '0' : coachCredits} CrÃ©dit{coachCredits !== 1 ? 's' : ''}
                        </span>
                        {/* Barre de progression visuelle */}
                        <div 
                          className="w-20 h-1.5 rounded-full overflow-hidden"
                          style={{ background: 'rgba(255,255,255,0.1)' }}
                        >
                          <div 
                            className="h-full rounded-full transition-all duration-500"
                            style={{ 
                              width: Math.min(100, (coachCredits / 50) * 100) + '%',
                              background: coachCredits <= 0 
                                ? '#ef4444' 
                                : coachCredits < 5 
                                  ? 'linear-gradient(90deg, #ef4444, #f97316)' 
                                  : 'linear-gradient(90deg, #D91CD2, #8b5cf6)'
                            }}
                          />
                        </div>
                      </div>
                    </div>
                    {/* Bouton Acheter si solde = 0 */}
                    {coachCredits <= 0 && (
                      <button
                        onClick={() => window.location.hash = '#become-coach'}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:scale-105"
                        style={{
                          background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                          color: 'white',
                          boxShadow: '0 0 10px rgba(217,28,210,0.4)'
                        }}
                        data-testid="buy-credits-btn"
                      >
                        ð Acheter
                      </button>
                    )}
                  </div>
                )}
                {/* v9.5.9: Super Admin - Badge IllimitÃ© â¾ï¸ */}
                {isSuperAdmin && (
                  <span 
                    className="ml-2 px-3 py-1.5 rounded-lg text-sm font-bold flex items-center gap-1"
                    style={{ 
                      background: 'linear-gradient(135deg, rgba(217,28,210,0.2), rgba(139,92,246,0.2))', 
                      color: '#D91CD2', 
                      border: '1px solid rgba(217,28,210,0.4)',
                      boxShadow: '0 0 15px rgba(217,28,210,0.3)'
                    }}
                    data-testid="super-admin-badge"
                  >
                    <span>ð</span> CrÃ©dits : IllimitÃ©s â¾ï¸
                  </span>
                )}
              </div>
            )}
          </div>
          {/* v10.6: GRILLE D'ACTIONS MINIMALISTE - 2 colonnes sur mobile */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 w-full sm:w-auto">
            {/* === QUICK CONTROL - Super Admin === */}
            {isSuperAdmin && (
              <div className="relative" ref={quickControlRef}>
                <button 
                  onClick={() => setShowQuickControl(!showQuickControl)}
                  title="Quick Control"
                  className="w-full h-20 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all duration-200 hover:scale-105"
                  style={{ 
                    background: showQuickControl 
                      ? 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.3))' 
                      : 'rgba(255,255,255,0.05)',
                    border: showQuickControl ? '1px solid rgba(217,28,210,0.5)' : '1px solid rgba(255,255,255,0.1)',
                    boxShadow: showQuickControl ? '0 0 20px rgba(217,28,210,0.3)' : 'none'
                  }}
                  data-testid="quick-control-btn"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <circle cx="12" cy="5" r="1.5" fill="white" />
                    <circle cx="12" cy="12" r="1.5" fill="white" />
                    <circle cx="12" cy="19" r="1.5" fill="white" />
                  </svg>
                  <span className="text-white/80 text-xs">Quick</span>
                </button>
                
                {/* Menu Quick Control - FIXÃ pour mobile */}
                {showQuickControl && (
                  <div 
                    className="absolute left-1/2 transform -translate-x-1/2 mt-2 w-64 rounded-xl overflow-hidden z-50"
                    style={{ 
                      background: 'linear-gradient(180deg, rgba(20,10,30,0.98) 0%, rgba(10,5,20,0.99) 100%)',
                      border: '1px solid rgba(217,28,210,0.3)',
                      boxShadow: '0 8px 32px rgba(0,0,0,0.5), 0 0 20px rgba(217,28,210,0.2)'
                    }}
                    data-testid="quick-control-menu"
                  >
                    <div className="px-4 py-3 border-b" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
                      <span className="text-xs font-semibold text-white/60 uppercase tracking-wider">Quick Control</span>
                    </div>
                    
                    {/* Toggle: AccÃ¨s Partenaires */}
                    <div className="px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <span className="text-lg">{platformSettings.partner_access_enabled ? 'ð¢' : 'ð´'}</span>
                        <div>
                          <p className="text-sm text-white font-medium">AccÃ¨s Partenaires</p>
                          <p className="text-xs text-white/40">Inscription & connexion</p>
                        </div>
                      </div>
                      <button
                        onClick={() => togglePlatformSetting('partner_access_enabled')}
                        className="w-11 h-6 rounded-full relative transition-all duration-300"
                        style={{ 
                          background: platformSettings.partner_access_enabled 
                            ? 'linear-gradient(90deg, #22c55e, #16a34a)' 
                            : 'rgba(255,255,255,0.15)'
                        }}
                        data-testid="toggle-partner-access"
                      >
                        <span 
                          className="absolute top-1 w-4 h-4 rounded-full bg-white shadow-md transition-all duration-300"
                          style={{ left: platformSettings.partner_access_enabled ? '24px' : '4px' }}
                        />
                      </button>
                    </div>
                    
                    {/* Toggle: Mode Maintenance */}
                    <div className="px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <span className="text-lg">{platformSettings.maintenance_mode ? 'ð´' : 'ð¢'}</span>
                        <div>
                          <p className="text-sm text-white font-medium">Mode Maintenance</p>
                          <p className="text-xs text-white/40">Bloquer tout accÃ¨s</p>
                        </div>
                      </div>
                      <button
                        onClick={() => togglePlatformSetting('maintenance_mode')}
                        className="w-11 h-6 rounded-full relative transition-all duration-300"
                        style={{ 
                          background: platformSettings.maintenance_mode 
                            ? 'linear-gradient(90deg, #D91CD2, #8b5cf6)' 
                            : 'rgba(255,255,255,0.15)',
                          boxShadow: platformSettings.maintenance_mode 
                            ? '0 0 15px rgba(217, 28, 210, 0.6)' 
                            : 'none'
                        }}
                        data-testid="toggle-maintenance"
                      >
                        <span 
                          className="absolute top-1 w-4 h-4 rounded-full bg-white shadow-md transition-all duration-300"
                          style={{ left: platformSettings.maintenance_mode ? '24px' : '4px' }}
                        />
                      </button>
                    </div>
                    
                    {/* Info */}
                    <div className="px-4 py-2 border-t" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
                      <p className="text-[10px] text-white/30 text-center">Super Admin</p>
                    </div>
                  </div>
                )}
              </div>
            )}
            
            {/* === CARTE ADMIN (Super Admin uniquement) === */}
            {isSuperAdmin && (
              <button 
                onClick={() => setShowAdminPanel(true)}
                title="Panneau Super Admin"
                className="h-20 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all duration-200 hover:scale-105"
                style={{ 
                  background: 'linear-gradient(135deg, rgba(217,28,210,0.2), rgba(139,92,246,0.2))',
                  border: '1px solid rgba(217, 28, 210, 0.3)',
                  boxShadow: '0 0 15px rgba(217, 28, 210, 0.2)'
                }}
                data-testid="super-admin-btn"
              >
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 2L9 9l-7 2 5 5-1 7 6-3 6 3-1-7 5-5-7-2-3-7z" />
                </svg>
                <span className="text-white/80 text-xs">Admin</span>
              </button>
            )}
            
            {/* === CARTE STRIPE (Coachs uniquement) === */}
            {!isSuperAdmin && (
              <button 
                onClick={handleStripeConnect}
                disabled={stripeConnectLoading}
                title={stripeConnectStatus?.connected ? "Compte Stripe connectÃ©" : "Connecter votre Stripe"}
                className="h-20 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all duration-200 hover:scale-105"
                style={{ 
                  background: stripeConnectStatus?.connected 
                    ? 'rgba(34, 197, 94, 0.2)' 
                    : 'linear-gradient(135deg, rgba(99,91,255,0.2), rgba(139,92,246,0.2))',
                  border: stripeConnectStatus?.connected 
                    ? '1px solid rgba(34, 197, 94, 0.4)' 
                    : '1px solid rgba(99,91,255,0.3)',
                  opacity: stripeConnectLoading ? 0.7 : 1
                }}
                data-testid="stripe-connect-btn"
              >
                <span className="text-lg">{stripeConnectStatus?.connected ? 'â' : 'ð³'}</span>
                <span className="text-white/80 text-xs">{stripeConnectLoading ? '...' : 'Stripe'}</span>
              </button>
            )}
            
            {/* === CARTE PARTAGER === */}
            <button 
              onClick={handleCoachShareLink}
              title={linkCopied ? "Lien copiÃ© !" : "Partager le site"}
              className="h-20 rounded-2xl flex flex-col items-center justify-center gap-2 transition-all duration-200 hover:scale-105"
              style={{ 
                background: linkCopied 
                  ? 'rgba(34, 197, 94, 0.2)' 
                  : 'rgba(255,255,255,0.05)',
                border: linkCopied 
                  ? '1px solid rgba(34, 197, 94, 0.4)' 
                  : '1px solid rgba(255,255,255,0.1)',
                boxShadow: linkCopied ? '0 0 15px rgba(34, 197, 94, 0.3)' : 'none'
              }}
              data-testid="coach-share"
            >
              {linkCopied ? (
                <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
                </svg>
              )}
              <span className="text-white/80 text-xs">{linkCopied ? 'CopiÃ©!' : 'Partager'}</span>
            </button>
          </div>
        </div>

        {/* v9.3.6: Menu tabs mobile scrollable horizontalement */}
        <div 
          className="flex gap-2 mb-6 items-center pb-2"
          style={{
            overflowX: 'auto',
            overflowY: 'hidden',
            whiteSpace: 'nowrap',
            WebkitOverflowScrolling: 'touch',
            scrollbarWidth: 'none',
            msOverflowStyle: 'none'
          }}
        >
          {tabs.map(tb => (
            <button 
              key={tb.id} 
              onClick={() => setTab(tb.id)} 
              className={`coach-tab px-3 py-2 rounded-lg text-xs sm:text-sm flex-shrink-0 ${tab === tb.id ? 'active' : ''}`}
              style={{ color: 'white' }} 
              data-testid={`coach-tab-${tb.id}`}
            >
              {tb.label}
            </button>
          ))}
          
          {/* Bouton Vue Visiteur - Ouvre la vitrine publique dans un nouvel onglet */}
          <button
            onClick={() => {
              // v67: Super Admin â homepage publique, Partenaires â /coach/{username}
              // VERROUILLÃ: aucun chemin ne gÃ©nÃ¨re /coach/bassi pour le Super Admin
              const SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
              const isSA = SUPER_ADMIN_EMAILS.includes(safeCoachUser?.email?.toLowerCase());
              const finalUrl = isSA
                ? `${window.location.origin}/?visitor=true&t=${Date.now()}`
                : `${coachVitrineUrl || window.location.origin}?t=${Date.now()}`;
              console.log('[V67] Vue Visiteur â ', finalUrl);
              window.open(finalUrl, '_blank');
            }}
            className="ml-auto px-3 py-2 rounded-lg text-xs sm:text-sm flex items-center gap-2 flex-shrink-0"
            style={{
              background: 'rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.2)',
              color: 'white'
            }}
            title="Voir ma vitrine publique"
            data-testid="coach-visitor-preview-toggle"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"></path>
              <polyline points="15 3 21 3 21 9"></polyline>
              <line x1="10" y1="14" x2="21" y2="3"></line>
            </svg>
            Vue Visiteur
          </button>
        </div>

        {/* Reservations Tab - Utilise le composant extrait ReservationTab */}
        {tab === "reservations" && (
          <ReservationTab
            reservations={filteredReservations}
            pagination={reservationPagination}
            search={reservationsSearch}
            loading={loadingReservations}
            handlers={{
              onSearchChange: setReservationsSearch,
              onClearSearch: () => setReservationsSearch(''),
              onScanClick: () => setShowScanner(true),
              onExportCSV: exportCSV,
              onPageChange: (page) => loadReservations(page, reservationPagination.limit),
              onValidateReservation: validateReservation,
              onDeleteReservation: deleteReservation,
              formatDateTime: (date) => {
                if (!date) return '-';
                try {
                  return new Intl.DateTimeFormat('fr-FR', {
                    day: '2-digit', month: '2-digit', year: 'numeric',
                    hour: '2-digit', minute: '2-digit'
                  }).format(new Date(date));
                } catch { return date; }
              }
            }}
            t={t}
          />
        )}

        {/* v36: HUB GESTION â Centre de commande unifiÃ© avec sous-onglets 2x2 */}
        {tab === "offers" && (
          <>
            {/* v37: Grille 2x2 de navigation avec badges */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: '10px',
              marginBottom: '16px'
            }}>
              {(() => {
                const totalAudioTracks = courses.reduce((acc, c) => acc + (c.audio_tracks?.length || c.playlist?.length || 0), 0);
                const totalVideos = (concept?.heroVideos || []).filter(v => v && (v.url || v.file_id)).length;
                return [
                  { id: 'contenus', icon: 'ð', label: 'Contenus', badge: courses.length + (offers?.length || 0) + totalAudioTracks },
                  { id: 'video-hero', icon: 'ð¬', label: 'VidÃ©o Hero', badge: totalVideos },
                  { id: 'vitrine', icon: 'ð¼ï¸', label: 'Ma Vitrine', badge: 0 },
                  { id: 'boutique-hub', icon: 'ð³', label: 'Boutique & Paiements', badge: 0 }
                ];
              })().map(sub => (
                <button
                  key={sub.id}
                  onClick={() => handleSubTabChange(sub.id)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    padding: '14px 8px',
                    borderRadius: '14px',
                    border: offersSubTab === sub.id
                      ? '2px solid rgba(217,28,210,0.7)'
                      : '1px solid rgba(255,255,255,0.1)',
                    background: offersSubTab === sub.id
                      ? 'linear-gradient(135deg, rgba(217,28,210,0.18), rgba(139,92,246,0.12))'
                      : 'rgba(255,255,255,0.04)',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                    transform: offersSubTab === sub.id ? 'scale(1.02)' : 'scale(1)',
                    minHeight: '72px',
                    position: 'relative'
                  }}
                >
                  <span style={{ fontSize: '24px' }}>{sub.icon}</span>
                  <span style={{
                    color: offersSubTab === sub.id ? '#D91CD2' : 'rgba(255,255,255,0.7)',
                    fontSize: '12px',
                    fontWeight: offersSubTab === sub.id ? 700 : 500,
                    textAlign: 'center',
                    lineHeight: '1.2'
                  }}>{sub.label}</span>
                  {sub.badge > 0 && (
                    <span style={{
                      position: 'absolute', top: '6px', right: '8px',
                      background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                      color: '#fff', fontSize: '10px', fontWeight: 800,
                      minWidth: '18px', height: '18px', borderRadius: '9px',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      padding: '0 5px',
                      boxShadow: '0 0 8px rgba(217,28,210,0.4)'
                    }}>{sub.badge}</span>
                  )}
                </button>
              ))}
            </div>

            {/* v37.2: Sous-onglet: ð Contenus â Cours + Offres + Audio Upload + Master Control Audio */}
            {offersSubTab === 'contenus' && (
              <>
                <CoursesManager
                  courses={courses}
                  setCourses={setCourses}
                  newCourse={newCourse}
                  setNewCourse={setNewCourse}
                  updateCourse={updateCourse}
                  openAudioModal={openAudioModal}
                  hideAudioButton={true}
                  lang={lang}
                  t={t}
                  coachEmail={safeCoachUser?.email}
                />
                {/* v69: Indicateur prochaine expiration automatique */}
                {nextExpiration?.next && (
                  <div style={{
                    margin: '16px 0 0 0',
                    padding: '12px 16px',
                    borderRadius: '12px',
                    background: nextExpiration.next.days_left <= 3
                      ? 'rgba(239,68,68,0.12)'
                      : nextExpiration.next.days_left <= 7
                        ? 'rgba(245,158,11,0.12)'
                        : 'rgba(34,197,94,0.08)',
                    border: `1px solid ${
                      nextExpiration.next.days_left <= 3
                        ? 'rgba(239,68,68,0.4)'
                        : nextExpiration.next.days_left <= 7
                          ? 'rgba(245,158,11,0.4)'
                          : 'rgba(34,197,94,0.3)'
                    }`,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    flexWrap: 'wrap'
                  }}>
                    <span style={{ fontSize: '18px' }}>
                      {nextExpiration.next.days_left <= 3 ? 'ð´' : nextExpiration.next.days_left <= 7 ? 'ð¡' : 'ð¢'}
                    </span>
                    <div style={{ flex: 1, minWidth: '200px' }}>
                      <div style={{ color: '#fff', fontSize: '13px', fontWeight: 600 }}>
                        Prochaine expiration : <span style={{ color: '#D91CD2' }}>{nextExpiration.next.name}</span>
                      </div>
                      <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', marginTop: '2px' }}>
                        {nextExpiration.next.days_left === 0
                          ? "Expire aujourd'hui"
                          : `Dans ${nextExpiration.next.days_left} jour${nextExpiration.next.days_left > 1 ? 's' : ''}`}
                        {' â¢ '}
                        {new Date(nextExpiration.next.expiration_date).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}
                        {nextExpiration.next.is_auto_prolong ? ' â¢ â»ï¸ Auto-renouvellement' : ' â¢ â¹ï¸ Pas de renouvellement'}
                      </div>
                    </div>
                    <div style={{
                      padding: '4px 10px',
                      borderRadius: '8px',
                      background: 'rgba(217,28,210,0.15)',
                      border: '1px solid rgba(217,28,210,0.3)',
                      color: '#D91CD2',
                      fontSize: '11px',
                      fontWeight: 700
                    }}>
                      {nextExpiration.total_with_expiration} offre{nextExpiration.total_with_expiration > 1 ? 's' : ''} avec validitÃ©
                    </div>
                  </div>
                )}

                {/* v71: SOCIAL BOOST â Panneau Admin (Super Admin uniquement) */}
                {isSuperAdmin && (
                  <div style={{
                    marginTop: '16px', marginBottom: '16px',
                    borderRadius: '16px', padding: '20px',
                    background: 'linear-gradient(135deg, rgba(217,28,210,0.08) 0%, rgba(139,92,246,0.08) 100%)',
                    border: '1px solid rgba(217,28,210,0.2)'
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                      <span style={{ fontSize: '20px' }}>ð¬</span>
                      <h3 style={{ color: '#fff', fontSize: '15px', fontWeight: 700, margin: 0 }}>Social Boost</h3>
                      <span style={{
                        background: 'rgba(217,28,210,0.2)', color: '#D91CD2',
                        fontSize: '10px', padding: '2px 8px', borderRadius: '10px', fontWeight: 600
                      }}>ADMIN</span>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                      {/* v77: Bouton Boost avec feedback visuel */}
                      <button
                        id="boost-social-btn"
                        onClick={async (e) => {
                          const btn = e.currentTarget;
                          btn.disabled = true;
                          btn.textContent = 'â³ GÃ©nÃ©ration en cours... (Patientez)';
                          btn.style.opacity = '0.6';
                          btn.style.cursor = 'not-allowed';
                          try {
                            const res = await axios.post(`${API}/admin/generate-social-proof`, { count: 50 }, {
                              headers: { 'X-User-Email': coachUser?.email }
                            });
                            alert(`â 50 avis gÃ©nÃ©rÃ©s avec succÃ¨s !`);
                            // Refresh la liste des derniers commentaires
                            try {
                              const commRes = await axios.get(`${API}/comments?coach_id=${encodeURIComponent(coachUser?.email || '')}`);
                              const el = document.getElementById('social-boost-comments-list');
                              if (el && commRes.data?.comments) {
                                el.dataset.comments = JSON.stringify(commRes.data.comments.slice(0, 5));
                                el.dispatchEvent(new Event('refresh'));
                              }
                            } catch(er) {}
                          } catch (e2) {
                            alert('â Erreur: ' + (e2.response?.data?.detail || e2.message));
                          } finally {
                            btn.disabled = false;
                            btn.textContent = 'ð Booster la Preuve Sociale (50 avis IA)';
                            btn.style.opacity = '1';
                            btn.style.cursor = 'pointer';
                          }
                        }}
                        style={{
                          background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                          color: '#fff', border: 'none', padding: '10px 18px',
                          borderRadius: '12px', fontSize: '13px', fontWeight: 600,
                          cursor: 'pointer', boxShadow: '0 0 15px rgba(217,28,210,0.3)',
                          transition: 'opacity 0.2s'
                        }}
                      >
                        ð Booster la Preuve Sociale (50 avis IA)
                      </button>
                      <button
                        onClick={async () => {
                          try {
                            const res = await axios.post(`${API}/admin/boost-likes`, { amount: 100 }, {
                              headers: { 'X-User-Email': coachUser?.email }
                            });
                            alert(`â +100 likes ajoutÃ©s sur ${res.data.boosted_comments} commentaires !`);
                          } catch (e) {
                            alert('â Erreur: ' + (e.response?.data?.detail || e.message));
                          }
                        }}
                        style={{
                          background: 'rgba(255,255,255,0.08)',
                          color: '#fff', border: '1px solid rgba(217,28,210,0.3)',
                          padding: '10px 18px', borderRadius: '12px',
                          fontSize: '13px', fontWeight: 600, cursor: 'pointer'
                        }}
                      >
                        â¤ï¸ +100 Likes
                      </button>
                      <button
                        onClick={async () => {
                          if (!window.confirm('Supprimer tous les commentaires IA ?')) return;
                          try {
                            const res = await axios.delete(`${API}/admin/comments`, {
                              headers: { 'X-User-Email': coachUser?.email }
                            });
                            alert(`ðï¸ ${res.data.deleted} commentaires IA supprimÃ©s`);
                          } catch (e) {
                            alert('â Erreur: ' + (e.response?.data?.detail || e.message));
                          }
                        }}
                        style={{
                          background: 'rgba(239,68,68,0.1)',
                          color: '#ef4444', border: '1px solid rgba(239,68,68,0.3)',
                          padding: '10px 18px', borderRadius: '12px',
                          fontSize: '13px', fontWeight: 600, cursor: 'pointer'
                        }}
                      >
                        ðï¸ Reset
                      </button>
                    </div>

                    {/* v77: Liste des 5 derniers commentaires avec contrÃ´les individuels */}
                    <SocialBoostCommentsList API={API} coachEmail={coachUser?.email} axios={axios} />

                    <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '11px', marginTop: '10px', margin: '10px 0 0 0' }}>
                      Les commentaires gÃ©nÃ©rÃ©s s'affichent sur le Hero et la section Avis de votre vitrine.
                    </p>
                  </div>
                )}

                <div style={{ marginTop: '16px' }}>
                  <OffersManager
                    offers={offers}
                    setOffers={setOffers}
                    newOffer={newOffer}
                    setNewOffer={setNewOffer}
                    offersSearch={offersSearch}
                    setOffersSearch={setOffersSearch}
                    editingOfferId={editingOfferId}
                    addOffer={addOffer}
                    updateOffer={updateOffer}
                    deleteOffer={deleteOffer}
                    startEditOffer={startEditOffer}
                    cancelEditOffer={cancelEditOffer}
                    API={API}
                    t={t}
                  />
                </div>

                {/* v37.2: Audio Studio inline dans Contenus */}
                <div style={{
                  borderRadius: '16px',
                  padding: '20px',
                  background: 'linear-gradient(180deg, rgba(15,5,25,0.6) 0%, rgba(5,0,15,0.8) 100%)',
                  border: '1px solid rgba(217,28,210,0.2)',
                  marginBottom: '20px',
                  position: 'relative',
                  overflow: 'hidden'
                }}>
                  {/* Background glow */}
                  <div style={{
                    position: 'absolute', top: '-60px', right: '-60px', width: '180px', height: '180px',
                    borderRadius: '50%', background: 'radial-gradient(circle, rgba(217,28,210,0.1), transparent 70%)',
                    filter: 'blur(30px)', pointerEvents: 'none'
                  }} />

                  {/* v44: Header autonome â plus de sÃ©lecteur de cours */}
                  <div style={{ position: 'relative', zIndex: 1, marginBottom: '16px' }}>
                    <h2 style={{ fontSize: '20px', fontWeight: 800, color: '#fff', display: 'flex', alignItems: 'center', gap: '10px', margin: '0 0 4px 0' }}>
                      <span style={{ fontSize: '26px' }}>ðµ</span> Studio Audio
                      <span style={{ fontSize: '12px', fontWeight: 600, color: 'rgba(217,28,210,0.7)', background: 'rgba(217,28,210,0.1)', padding: '2px 8px', borderRadius: '8px' }}>
                        {audioTracks.length} piste{audioTracks.length !== 1 ? 's' : ''}
                      </span>
                    </h2>
                    <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: 0 }}>GÃ©rez vos pistes audio indÃ©pendamment â¢ Vente & tÃ©lÃ©chargement sur votre vitrine</p>
                  </div>

                  {/* Upload Zone â v44: toujours visible */}
                  <div style={{ position: 'relative', zIndex: 1 }}>
                      <div
                        style={{
                          border: '2px dashed rgba(217,28,210,0.4)',
                          borderRadius: '16px',
                          padding: '28px',
                          textAlign: 'center',
                          marginBottom: '20px',
                          background: 'rgba(217,28,210,0.04)',
                          cursor: 'pointer',
                          transition: 'all 0.3s ease'
                        }}
                        onClick={() => audioFileInputRef.current?.click()}
                        onDragOver={(e) => { e.preventDefault(); e.currentTarget.style.borderColor = 'rgba(217,28,210,0.8)'; e.currentTarget.style.background = 'rgba(217,28,210,0.1)'; }}
                        onDragLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(217,28,210,0.4)'; e.currentTarget.style.background = 'rgba(217,28,210,0.04)'; }}
                        onDrop={(e) => { e.preventDefault(); e.currentTarget.style.borderColor = 'rgba(217,28,210,0.4)'; e.currentTarget.style.background = 'rgba(217,28,210,0.04)'; handleAudioFileUpload(e.dataTransfer.files); }}
                      >
                        <input
                          ref={audioFileInputRef}
                          type="file"
                          accept="audio/mpeg,audio/mp3,audio/wav,audio/ogg,audio/aac,.mp3,.wav,.ogg,.aac"
                          multiple
                          style={{ display: 'none' }}
                          onChange={(e) => handleAudioFileUpload(e.target.files)}
                        />
                        <input
                          ref={audioCoverInputRef}
                          type="file"
                          accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                          style={{ display: 'none' }}
                          onChange={(e) => { if (e.target.files[0] && coverUploadTrackId) { handleCoverUpload(e.target.files[0], coverUploadTrackId); } }}
                        />
                        {uploadingAudio ? (
                          <div>
                            <div style={{ fontSize: '36px', marginBottom: '8px' }}>â³</div>
                            <p style={{ color: '#d91cd2', fontWeight: 600, fontSize: '14px', margin: 0 }}>Upload en cours...</p>
                          </div>
                        ) : (
                          <div>
                            <div style={{ fontSize: '42px', marginBottom: '8px', filter: 'drop-shadow(0 0 12px rgba(217,28,210,0.5))' }}>ð¶</div>
                            <p style={{ color: '#fff', fontWeight: 700, fontSize: '15px', marginBottom: '4px' }}>Glissez vos fichiers audio ici</p>
                            <p style={{ color: 'rgba(255,255,255,0.4)', fontSize: '12px', margin: 0 }}>ou cliquez pour sÃ©lectionner â¢ MP3, WAV, OGG, AAC (max 15MB)</p>
                          </div>
                        )}
                      </div>

                      {/* Track List */}
                      <div>
                        {audioTracks.length === 0 ? (
                          <div style={{ padding: '24px', borderRadius: '14px', textAlign: 'center', background: 'rgba(255,255,255,0.03)' }}>
                            <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '13px', margin: 0 }}>Aucune piste audio</p>
                            <p style={{ color: 'rgba(255,255,255,0.2)', fontSize: '11px', marginTop: '4px' }}>Glissez des fichiers MP3/WAV ci-dessus pour commencer</p>
                          </div>
                        ) : (
                          <div ref={el => window._audioListRef2 = el} style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {audioTracks.sort((a, b) => a.order - b.order).map((track, index) => (
                              <div
                                key={track.id}
                                draggable
                                onDragStart={(e) => handleTrackDragStart(e, track.id)}
                                onDragOver={(e) => handleTrackDragOver(e, index)}
                                onDrop={(e) => handleTrackDrop(e, index)}
                                onTouchStart={(e) => handleTrackTouchStart(e, track.id)}
                                onTouchMove={(e) => handleTrackTouchMove(e, window._audioListRef2)}
                                onTouchEnd={handleTrackTouchEnd}
                                onDragEnd={() => { setDragOverIndex(null); setDraggedTrackId(null); }}
                                style={{
                                  borderRadius: '14px',
                                  padding: editingTrackId === track.id ? '16px' : '12px',
                                  background: dragOverIndex === index ? 'rgba(217,28,210,0.15)' : 'rgba(255,255,255,0.04)',
                                  border: dragOverIndex === index ? '1px solid rgba(217,28,210,0.5)' : '1px solid rgba(255,255,255,0.06)',
                                  transition: 'all 0.2s ease',
                                  cursor: 'grab',
                                  opacity: draggedTrackId === track.id ? 0.5 : 1
                                }}
                              >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                  {/* v46: Reorder buttons (touch-friendly) */}
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', flexShrink: 0 }}>
                                    <button onClick={(e) => { e.stopPropagation(); if (index === 0) return; const sorted = [...audioTracks].sort((a,b) => a.order - b.order); const updated = [...sorted]; const [moved] = updated.splice(index, 1); updated.splice(index - 1, 0, moved); setAudioTracks(updated.map((t, i) => ({ ...t, order: i }))); }}
                                      style={{ width: '24px', height: '20px', border: 'none', borderRadius: '4px', background: index === 0 ? 'transparent' : 'rgba(255,255,255,0.08)', color: index === 0 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.5)', cursor: index === 0 ? 'default' : 'pointer', fontSize: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>â²</button>
                                    <button onClick={(e) => { e.stopPropagation(); const sorted = [...audioTracks].sort((a,b) => a.order - b.order); if (index >= sorted.length - 1) return; const updated = [...sorted]; const [moved] = updated.splice(index, 1); updated.splice(index + 1, 0, moved); setAudioTracks(updated.map((t, i) => ({ ...t, order: i }))); }}
                                      style={{ width: '24px', height: '20px', border: 'none', borderRadius: '4px', background: index >= audioTracks.length - 1 ? 'transparent' : 'rgba(255,255,255,0.08)', color: index >= audioTracks.length - 1 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.5)', cursor: index >= audioTracks.length - 1 ? 'default' : 'pointer', fontSize: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>â¼</button>
                                  </div>
                                  <div
                                    onClick={(e) => { e.stopPropagation(); setCoverUploadTrackId(track.id); audioCoverInputRef.current?.click(); }}
                                    style={{
                                      width: '52px', height: '52px', borderRadius: '10px', flexShrink: 0,
                                      background: track.cover_url ? `url(${track.cover_url}) center/cover` : 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.2))',
                                      border: '2px solid rgba(217,28,210,0.3)',
                                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                                      cursor: 'pointer', position: 'relative', overflow: 'hidden',
                                      boxShadow: '0 0 15px rgba(217,28,210,0.2)'
                                    }}
                                  >
                                    {!track.cover_url && <span style={{ fontSize: '20px' }}>ðµ</span>}
                                  </div>
                                  <div style={{ flex: 1, minWidth: 0 }}>
                                    <p style={{ color: '#fff', fontSize: '14px', fontWeight: 600, margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{track.title}</p>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '2px', flexWrap: 'wrap' }}>
                                      {track.price > 0 ? (
                                        <span style={{ fontSize: '11px', color: '#22c55e', fontWeight: 600 }}>{track.price} CHF</span>
                                      ) : (
                                        <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)' }}>Gratuit</span>
                                      )}
                                      <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.2)' }}>â¢</span>
                                      <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.3)' }}>Preview {track.preview_duration}s</span>
                                      <span style={{ fontSize: '11px', color: 'rgba(255,255,255,0.2)' }}>â¢</span>
                                      <span style={{
                                        fontSize: '10px', fontWeight: 700, padding: '1px 6px', borderRadius: '6px',
                                        background: track.visible !== false ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                                        color: track.visible !== false ? '#22c55e' : '#ef4444',
                                        border: track.visible !== false ? '1px solid rgba(34,197,94,0.3)' : '1px solid rgba(239,68,68,0.3)'
                                      }}>
                                        {track.visible !== false ? 'En vente' : 'MasquÃ©'}
                                      </span>
                                    </div>
                                  </div>
                                  <div style={{ display: 'flex', gap: '4px', flexShrink: 0 }}>
                                    <button onClick={(e) => { e.stopPropagation(); setEditingTrackId(editingTrackId === track.id ? null : track.id); }}
                                      style={{ width: '32px', height: '32px', borderRadius: '8px', border: 'none', background: editingTrackId === track.id ? 'rgba(217,28,210,0.3)' : 'rgba(255,255,255,0.08)', color: editingTrackId === track.id ? '#d91cd2' : 'rgba(255,255,255,0.5)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px' }}
                                      title="Ãditer">âï¸</button>
                                    <button onClick={(e) => { e.stopPropagation(); removeTrack(track.id); }}
                                      style={{ width: '32px', height: '32px', borderRadius: '8px', border: 'none', background: 'rgba(239,68,68,0.1)', color: '#ef4444', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '14px' }}
                                      title="Supprimer">ðï¸</button>
                                  </div>
                                </div>

                                {/* Expanded edit form */}
                                {editingTrackId === track.id && (
                                  <div style={{ marginTop: '14px', paddingTop: '14px', borderTop: '1px solid rgba(255,255,255,0.08)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                      <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Titre</label>
                                      <input type="text" value={track.title} onChange={(e) => updateTrackField(track.id, 'title', e.target.value)}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', outline: 'none' }} />
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                      <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Description</label>
                                      <textarea value={track.description || ''} onChange={(e) => updateTrackField(track.id, 'description', e.target.value)} rows={2}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', outline: 'none', resize: 'vertical' }} placeholder="Description de la piste..." />
                                    </div>
                                    <div style={{ gridColumn: '1 / -1' }}>
                                      <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Lien image de couverture</label>
                                      <input type="url" value={track.cover_url || ''} onChange={(e) => updateTrackField(track.id, 'cover_url', e.target.value || null)}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', outline: 'none' }} placeholder="https://exemple.com/cover.jpg" />
                                    </div>
                                    <div>
                                      <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Prix (CHF) â 0 = gratuit</label>
                                      <input type="number" min="0" step="0.5" value={track.price} onChange={(e) => updateTrackField(track.id, 'price', parseFloat(e.target.value) || 0)}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', outline: 'none' }} />
                                    </div>
                                    <div>
                                      <label style={{ color: 'rgba(255,255,255,0.5)', fontSize: '11px', display: 'block', marginBottom: '4px' }}>Preview (secondes)</label>
                                      <input type="number" min="5" max="120" value={track.preview_duration} onChange={(e) => updateTrackField(track.id, 'preview_duration', parseInt(e.target.value) || 30)}
                                        style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', fontSize: '13px', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', outline: 'none' }} />
                                    </div>
                                    <div style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', gap: '12px', paddingTop: '6px' }}>
                                      <div onClick={() => updateTrackField(track.id, 'visible', track.visible === false ? true : false)}
                                        style={{ width: '44px', height: '24px', borderRadius: '12px', cursor: 'pointer', background: track.visible !== false ? 'linear-gradient(135deg, #22c55e, #16a34a)' : 'rgba(255,255,255,0.15)', position: 'relative', transition: 'all 0.3s ease', boxShadow: track.visible !== false ? '0 0 10px rgba(34,197,94,0.3)' : 'none' }}>
                                        <div style={{ width: '18px', height: '18px', borderRadius: '50%', background: '#fff', position: 'absolute', top: '3px', left: track.visible !== false ? '23px' : '3px', transition: 'left 0.3s ease', boxShadow: '0 1px 3px rgba(0,0,0,0.3)' }} />
                                      </div>
                                      <span style={{ color: track.visible !== false ? '#22c55e' : 'rgba(255,255,255,0.4)', fontSize: '13px', fontWeight: 600 }}>
                                        {track.visible !== false ? 'En vente sur la vitrine' : 'MasquÃ© (non visible)'}
                                      </span>
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Save Button */}
                      <div style={{ marginTop: '16px' }}>
                        <button
                          onClick={saveAudioStudio}
                          disabled={savingPlaylist}
                          style={{
                            width: '100%', padding: '14px', borderRadius: '12px', fontSize: '14px', fontWeight: 700,
                            background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                            border: 'none', color: '#fff', cursor: 'pointer',
                            opacity: savingPlaylist ? 0.7 : 1,
                            boxShadow: '0 0 20px rgba(217,28,210,0.3)',
                            transition: 'all 0.3s ease'
                          }}
                          data-testid="save-audio-inline"
                        >
                          {savingPlaylist ? 'â³ Sauvegarde...' : 'ð¾ Sauvegarder le Studio Audio'}
                        </button>
                      </div>
                    </div>
                </div>

                {/* Master Control Audio (SuperAdmin) */}
                <ConceptEditor
                  concept={concept}
                  setConcept={setConcept}
                  conceptSaveStatus={conceptSaveStatus}
                  saveConcept={saveConcept}
                  API={API}
                  t={t}
                  isSuperAdmin={isSuperAdmin}
                  coachEmail={safeCoachUser?.email || ''}
                  courses={courses}
                  setCourses={setCourses}
                  section="audio"
                />
              </>
            )}

            {/* v37.2: Sous-onglet: ð¬ VidÃ©o Hero */}
            {offersSubTab === 'video-hero' && (
              <ConceptEditor
                concept={concept}
                setConcept={setConcept}
                conceptSaveStatus={conceptSaveStatus}
                saveConcept={saveConcept}
                API={API}
                t={t}
                isSuperAdmin={isSuperAdmin}
                coachEmail={safeCoachUser?.email || ''}
                courses={courses}
                setCourses={setCourses}
                section="video-hero"
              />
            )}

            {/* v37.2: Sous-onglet: ð¼ï¸ Ma Vitrine */}
            {offersSubTab === 'vitrine' && (
              <>
                <ConceptEditor
                  concept={concept}
                  setConcept={setConcept}
                  conceptSaveStatus={conceptSaveStatus}
                  saveConcept={saveConcept}
                  API={API}
                  t={t}
                  isSuperAdmin={isSuperAdmin}
                  coachEmail={safeCoachUser?.email || ''}
                  courses={courses}
                  setCourses={setCourses}
                  section="vitrine"
                />
                <BrandingManager
                  API={API}
                  coachEmail={safeCoachUser?.email}
                  t={t}
                />
                <PageVenteTab
                  coachVitrineUrl={coachVitrineUrl}
                  linkCopied={linkCopied}
                  onCopyLink={handleCoachShareLink}
                  paymentLinks={paymentLinks}
                  setPaymentLinks={setPaymentLinks}
                  paymentSaveStatus={paymentSaveStatus}
                  t={t}
                />
                <SEOManager
                  API={API}
                  coachEmail={safeCoachUser?.email}
                  coachUsername={coachUsername}
                  t={t}
                />
                <FAQManager
                  API={API}
                  coachEmail={safeCoachUser?.email}
                  t={t}
                />
              </>
            )}

            {/* v37.2: Sous-onglet: ð³ Boutique & Paiements */}
            {offersSubTab === 'boutique-hub' && (
              <>
                <ConceptEditor
                  concept={concept}
                  setConcept={setConcept}
                  conceptSaveStatus={conceptSaveStatus}
                  saveConcept={saveConcept}
                  API={API}
                  t={t}
                  isSuperAdmin={isSuperAdmin}
                  coachEmail={safeCoachUser?.email || ''}
                  courses={courses}
                  setCourses={setCourses}
                  section="boutique"
                />
                <PaymentConfigTab
                  paymentConfig={vendorPaymentConfig}
                  setPaymentConfig={setVendorPaymentConfig}
                  coachEmail={coachUser?.email}
                />
              </>
            )}
          </>
        )}

        {/* v37.2: "Ma Page" supprimÃ© â centralisÃ© dans HUB > Ma Vitrine */}

        {/* v13.8: Promo Codes Tab - RESTAURATION COMPLÃTE */}
        {tab === "codes" && (
          <PromoCodesTab
            // === Credits Gate ===
            hasCreditsFor={hasCreditsFor}
            servicePrices={servicePrices}
            coachCredits={coachCredits}
            setTab={setTab}
            // === Search ===
            codesSearch={codesSearch}
            setCodesSearch={setCodesSearch}
            // === Promo codes data ===
            discountCodes={discountCodes}
            newCode={newCode}
            setNewCode={setNewCode}
            // === Batch mode ===
            isBatchMode={isBatchMode}
            setIsBatchMode={setIsBatchMode}
            batchLoading={batchLoading}
            // === Manual contact ===
            showManualContactForm={showManualContactForm}
            setShowManualContactForm={setShowManualContactForm}
            manualContact={manualContact}
            setManualContact={setManualContact}
            // === Beneficiaries selection (v13.8: RESTAURÃ) ===
            uniqueCustomers={uniqueCustomers}
            selectedBeneficiaries={selectedBeneficiaries}
            toggleBeneficiarySelection={toggleBeneficiarySelection}
            // === Articles/Courses selection ===
            courses={courses}
            offers={offers}
            toggleCourseSelection={toggleCourseSelection}
            removeAllowedArticle={removeAllowedArticle}
            // === Actions ===
            addCode={addCode}
            deleteCode={deleteCode}
            toggleCode={toggleCode}
            duplicateCode={duplicateCode}
            editCode={editCode}
            addManualContact={addManualContact}
            handleImportCSV={handleImportCSV}
            exportPromoCodesCSV={exportPromoCodesCSV}
            manualSanitize={manualSanitize}
            // === Translations ===
            t={t}
          />
        )}

        {/* === CONTACTS TAB v18 === */}
        {tab === "contacts" && (
          <div className="card-gradient rounded-xl p-4 sm:p-6">
            <h2 style={{ color: '#fff', fontSize: '18px', fontWeight: 700, marginBottom: '16px' }}>ð Mes Contacts</h2>
            <ContactsManager API={API} coachEmail={coachUser?.email} />
          </div>
        )}

        {/* === CAMPAIGNS TAB === */}
        {/* [CAMPAGNE_START] - Section extraite vers CampaignManager.js */}
        {/* v13.2: Verrouillage crÃ©dits avec composant CreditsGate */}
        {tab === "campaigns" && !hasCreditsFor('campaign') ? (
          <div className="card-gradient rounded-xl p-4 sm:p-6">
            <CreditsGate 
              serviceName="campaigns"
              requiredCredits={servicePrices.campaign}
              currentCredits={coachCredits}
              onGoToBoutique={() => setTab('boutique')}
              testId="credits-lock-campaigns"
            />
          </div>
        ) : tab === "campaigns" && (
          <CampaignManager
            // === ÃTATS PRINCIPAUX ===
            campaigns={campaigns}
            newCampaign={newCampaign}
            setNewCampaign={setNewCampaign}
            editingCampaignId={editingCampaignId}
            schedulerHealth={schedulerHealth}
            
            // === ÃTATS ENVOI DIRECT ===
            directSendMode={directSendMode}
            setDirectSendMode={setDirectSendMode}
            externalChannelsExpanded={externalChannelsExpanded}
            setExternalChannelsExpanded={setExternalChannelsExpanded}
            currentWhatsAppIndex={currentWhatsAppIndex}
            instagramProfile={instagramProfile}
            setInstagramProfile={setInstagramProfile}
            messageCopied={messageCopied}
            
            // === CONTACT STATS ===
            contactStats={contactStats}
            allContacts={allContacts}
            filteredContacts={filteredContacts}
            selectedContactsForCampaign={selectedContactsForCampaign}
            contactSearchQuery={contactSearchQuery}
            setContactSearchQuery={setContactSearchQuery}
            
            // === DESTINATAIRES (PANIER) ===
            selectedRecipients={selectedRecipients}
            setSelectedRecipients={setSelectedRecipients}
            activeConversations={activeConversations}
            setActiveConversations={setActiveConversations}
            showConversationDropdown={showConversationDropdown}
            setShowConversationDropdown={setShowConversationDropdown}
            conversationSearch={conversationSearch}
            setConversationSearch={setConversationSearch}
            
            // === HISTORIQUE FILTRES ===
            campaignHistoryFilter={campaignHistoryFilter}
            setCampaignHistoryFilter={setCampaignHistoryFilter}
            campaignLogs={campaignLogs}
            
            // === EMAIL RESEND ===
            emailSendingProgress={emailSendingProgress}
            emailSendingResults={emailSendingResults}
            setEmailSendingResults={setEmailSendingResults}
            testEmailAddress={testEmailAddress}
            setTestEmailAddress={setTestEmailAddress}
            testEmailStatus={testEmailStatus}
            
            // === WHATSAPP ===
            whatsAppConfig={whatsAppConfig}
            setWhatsAppConfig={setWhatsAppConfig}
            showWhatsAppConfig={showWhatsAppConfig}
            setShowWhatsAppConfig={setShowWhatsAppConfig}
            whatsAppSendingProgress={whatsAppSendingProgress}
            whatsAppSendingResults={whatsAppSendingResults}
            setWhatsAppSendingResults={setWhatsAppSendingResults}
            testWhatsAppNumber={testWhatsAppNumber}
            setTestWhatsAppNumber={setTestWhatsAppNumber}
            testWhatsAppStatus={testWhatsAppStatus}
            
            // === ENVOI GROUPÃ ===
            bulkSendingInProgress={bulkSendingInProgress}
            bulkSendingProgress={bulkSendingProgress}
            bulkSendingResults={bulkSendingResults}
            setBulkSendingResults={setBulkSendingResults}
            
            // === IA WHATSAPP ===
            aiConfig={aiConfig}
            setAiConfig={setAiConfig}
            showAIConfig={showAIConfig}
            setShowAIConfig={setShowAIConfig}
            aiLogs={aiLogs}
            aiTestMessage={aiTestMessage}
            setAiTestMessage={setAiTestMessage}
            aiTestResponse={aiTestResponse}
            aiTestLoading={aiTestLoading}
            aiConfigSaveStatus={aiConfigSaveStatus} // v9.3.8: Indicateur auto-save
            
            // === PREVIEW MÃDIA ===
            resolvedThumbnail={resolvedThumbnail}
            
            // === HANDLERS ===
            handleTestEmail={handleTestEmail}
            handleSendEmailCampaign={handleSendEmailCampaign}
            handleTestWhatsApp={handleTestWhatsApp}
            handleSendWhatsAppCampaign={handleSendWhatsAppCampaign}
            handleBulkSendCampaign={handleBulkSendCampaign}
            handleSaveWhatsAppConfig={handleSaveWhatsAppConfig}
            handleSaveAIConfig={handleSaveAIConfig}
            handleTestAI={handleTestAI}
            handleClearAILogs={handleClearAILogs}
            handleEditCampaign={handleEditCampaign}
            
            // === FONCTIONS CAMPAGNES ===
            createCampaign={createCampaign}
            cancelEditCampaign={cancelEditCampaign}
            launchCampaignWithSend={launchCampaignWithSend}
            deleteCampaign={deleteCampaign}
            addScheduleSlot={addScheduleSlot}
            removeScheduleSlot={removeScheduleSlot}
            updateScheduleSlot={updateScheduleSlot}
            
            // === FONCTIONS CONTACTS ===
            toggleContactForCampaign={toggleContactForCampaign}
            toggleAllContacts={toggleAllContacts}
            getContactsForDirectSend={getContactsForDirectSend}
            getCurrentWhatsAppContact={getCurrentWhatsAppContact}
            nextWhatsAppContact={nextWhatsAppContact}
            prevWhatsAppContact={prevWhatsAppContact}
            
            // === FONCTIONS LIENS ===
            formatPhoneForWhatsApp={formatPhoneForWhatsApp}
            generateWhatsAppLink={generateWhatsAppLink}
            generateGroupedEmailLink={generateGroupedEmailLink}
            generateEmailLink={generateEmailLink}
            copyMessageForInstagram={copyMessageForInstagram}
            markResultSent={markResultSent}
            
            // === UTILS ===
            showCampaignToast={showCampaignToast}
            API={API}
            
            // === v9.0.2: CRÃDITS ===
            hasInsufficientCredits={hasInsufficientCredits}
            coachCredits={coachCredits}
            // v11: Super Admin + coÃ»t campagne
            isSuperAdmin={isSuperAdmin}
            campaignCreditCost={servicePrices?.campaign || 1}
            chatLinks={chatLinks}
            coachEmail={coachUser?.email}
          />
        )}
        {/* [CAMPAGNE_END] - Section extraite vers CampaignManager.js (~1490 lignes Ã©conomisÃ©es) */}


        {/* ========== ONGLET CONVERSATIONS v9.2.0 - Extrait vers CRMSection.js ========== */}
        {/* v13.2: Verrouillage crÃ©dits avec composant CreditsGate */}
        {tab === "conversations" && !hasCreditsFor('ai_conversation') ? (
          <div className="card-gradient rounded-xl p-4 sm:p-6">
            <CreditsGate 
              serviceName="conversations"
              requiredCredits={servicePrices.ai_conversation}
              currentCredits={coachCredits}
              onGoToBoutique={() => setTab('boutique')}
              testId="credits-lock-conversations"
            />
          </div>
        ) : tab === "conversations" && (
          <SectionErrorBoundary sectionName="Conversations">
            <CRMSection
              // Notification state
              showPermissionBanner={showPermissionBanner}
              setShowPermissionBanner={setShowPermissionBanner}
              notificationPermission={notificationPermission}
              requestNotificationAccess={requestNotificationAccess}
              toastNotifications={toastNotifications}
              handleToastClick={handleToastClick}
              dismissToast={dismissToast}
              handleTestNotification={handleTestNotification}
              notifyOnAiResponse={notifyOnAiResponse}
              toggleNotifyOnAiResponse={toggleNotifyOnAiResponse}
              // Link generation
              newLinkTitle={newLinkTitle}
              setNewLinkTitle={setNewLinkTitle}
              newLinkCustomPrompt={newLinkCustomPrompt}
              setNewLinkCustomPrompt={setNewLinkCustomPrompt}
              generateShareableLink={generateShareableLink}
              enhancePromptWithAI={enhancePromptWithAI}
              // Community
              newCommunityName={newCommunityName}
              setNewCommunityName={setNewCommunityName}
              createCommunityChat={createCommunityChat}
              // Chat links
              chatLinks={chatLinks}
              copiedLinkId={copiedLinkId}
              copyLinkToClipboard={copyLinkToClipboard}
            deleteChatLink={deleteChatLink}
            updateChatLink={updateChatLink}
            // Conversations
            enrichedConversations={enrichedConversations}
            selectedSession={selectedSession}
            setSelectedSession={setSelectedSession}
            loadSessionMessages={loadSessionMessages}
            setSessionMode={setSessionMode}
            deleteChatSession={deleteChatSession}
            bulkDeleteChatSessions={bulkDeleteChatSessions}
            conversationsLoading={conversationsLoading}
            conversationsHasMore={conversationsHasMore}
            handleConversationsScroll={handleConversationsScroll}
            conversationsListRef={conversationsListRef}
            conversationSearch={conversationSearch}
            setConversationSearch={setConversationSearch}
            loadConversations={loadConversations}
            // Messages
            sessionMessages={sessionMessages}
            coachMessage={coachMessage}
            setCoachMessage={setCoachMessage}
            handleSendMessage={handleSendMessage}
            // General
            loadingConversations={loadingConversations}
            isSuperAdmin={isSuperAdmin}
            API_URL={API}
          />
          </SectionErrorBoundary>
        )}
        {/* [CONVERSATIONS_END] - Section extraite vers CRMSection.js (~940 lignes Ã©conomisÃ©es) */}

        {/* ========== v13.2: ONGLET BOUTIQUE CRÃDITS - Composant extrait ========== */}
        {tab === "boutique" && !isSuperAdmin && (
          <CreditBoutique
            coachCredits={coachCredits}
            creditPacks={creditPacks}
            loadingPacks={loadingPacks}
            purchasingPack={purchasingPack}
            onBuyPack={handleBuyPack}
          />
        )}

        {/* v37.2: Onglet "Paiements" supprimÃ© â centralisÃ© dans HUB > Boutique & Paiements */}

        {/* ========== v13.2: ONGLET STRIPE - Composant extrait ========== */}
        {tab === "stripe" && !isSuperAdmin && (
          <StripeConnectTab
            stripeConnectStatus={stripeConnectStatus}
            stripeConnectLoading={stripeConnectLoading}
            onStripeConnect={handleStripeConnect}
            coachPlatformName={coachPlatformName}
            setCoachPlatformName={setCoachPlatformName}
            coachEmail={coachUser?.email}
          />
        )}
      </div>
    </div>
  );
};

export { CoachDashboard };

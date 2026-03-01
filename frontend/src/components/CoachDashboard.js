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
// ArticleManager supprimé - v8.9 Nettoyage SAAS
import ReservationTab from "./coach/ReservationTab"; // Import Reservation Tab
import CampaignManager from "./coach/CampaignManager"; // Import Campaign Manager
import CRMSection from "./coach/CRMSection"; // v9.2.0 Import CRM Section
import { parseMediaUrl, getMediaThumbnail } from "../services/MediaParser"; // Media Parser
import SuperAdminPanel from "./SuperAdminPanel"; // v8.9 Super Admin Panel

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
          <h3 className="text-lg font-bold mb-2">⚠️ Erreur dans la section {this.props.sectionName}</h3>
          <p className="text-white/70 text-sm mb-3">{this.state.error?.message || 'Une erreur est survenue'}</p>
          <button 
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-4 py-2 bg-violet-500 rounded-lg text-white text-sm"
          >
            🔄 Réessayer
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
 * Remplace EmailJS pour un contrôle total côté serveur
 * @param {string} destination - Email du destinataire
 * @param {string} recipientName - Nom du destinataire
 * @param {string} subject - Sujet de l'email
 * @param {string} text - Corps du message
 * @param {string} mediaUrl - URL du visuel (optionnel, peut être un lien interne /v/slug)
 * @returns {Promise<{success: boolean, response?: any, error?: string}>}
 */
const performEmailSend = async (destination, recipientName = 'Client', subject = 'Afroboost', text = '', mediaUrl = null) => {
  try {
    // Validation des paramètres
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
      console.log('RESEND_DEBUG: SUCCÈS - Email ID =', result.email_id);
      return { success: true, response: result };
    } else {
      console.error('RESEND_DEBUG: ÉCHEC -', result.error);
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
 * @param {string} phoneNumber - Numéro de téléphone
 * @param {string} message - Message à envoyer
 * @param {object} twilioConfig - {accountSid, authToken, fromNumber}
 * @returns {Promise<{success: boolean, sid?: string, error?: string}>}
 */
const performWhatsAppSend = async (phoneNumber, message, twilioConfig) => {
  const { accountSid, authToken, fromNumber } = twilioConfig || {};
  
  console.log('========================================');
  console.log('DEMANDE WHATSAPP/TWILIO ENVOYÉE');
  console.log('Numéro:', phoneNumber);
  console.log('Message:', message?.substring(0, 50) + '...');
  console.log('Account SID:', accountSid || 'NON CONFIGURÉ');
  console.log('From Number:', fromNumber || 'NON CONFIGURÉ');
  console.log('========================================');
  
  // Si pas de config Twilio, simulation avec alerte
  if (!accountSid || !authToken || !fromNumber) {
    console.warn('⚠️ Twilio non configuré - Mode simulation');
    alert(`WhatsApp prêt pour : ${phoneNumber}\n\nMessage: ${message?.substring(0, 100)}...`);
    return { success: true, simulated: true };
  }
  
  // Formater le numéro au format E.164
  let formattedPhone = phoneNumber.replace(/[^\d+]/g, '');
  if (!formattedPhone.startsWith('+')) {
    formattedPhone = formattedPhone.startsWith('0') 
      ? '+41' + formattedPhone.substring(1) 
      : '+' + formattedPhone;
  }
  
  // Construire les données pour Twilio
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
    console.log('📱 TWILIO RÉPONSE:', data);
    
    if (!response.ok) {
      return { success: false, error: data.message || `HTTP ${response.status}` };
    }
    
    return { success: true, sid: data.sid };
  } catch (error) {
    console.error('❌ TWILIO ERREUR:', error);
    return { success: false, error: error.message };
  }
};

// API avec préfixe /api
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

// MediaDisplay component - Utilise parseMediaUrl importé de MediaParser.js
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
  
  // Vidéo directe
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

// Clé localStorage pour persistance coach
const COACH_TAB_KEY = 'afroboost_coach_tab';
const COACH_SESSION_KEY = 'afroboost_coach_session';

const CoachDashboard = ({ t, lang, onBack, onLogout, coachUser }) => {
  // v9.2.5: Protection ABSOLUE contre les erreurs - Valeurs par défaut GARANTIES
  const safeCoachUser = coachUser || {};
  
  // v9.2.5: État de chargement initial
  const [dashboardReady, setDashboardReady] = useState(false);
  const [loadError, setLoadError] = useState(null);
  
  // Email Super Admin
  // v9.5.6: Liste des Super Admins autorisés
  const SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
  const isSuperAdmin = SUPER_ADMIN_EMAILS.some(email => 
    (safeCoachUser?.email || '').toLowerCase() === email.toLowerCase()
  );
  
  // v9.2.5: Valeurs par défaut TOUJOURS présentes pour éviter page blanche
  const displayEmail = safeCoachUser?.email || 'Partenaire';
  const displayName = safeCoachUser?.name || 'Partenaire';
  
  // v8.9.5: Helper pour créer les headers avec l'email coach (isolation des données)
  const getCoachHeaders = () => ({
    headers: { 'X-User-Email': safeCoachUser?.email || '' }
  });
  
  // v9.2.5: Marquer le dashboard comme prêt après le premier rendu
  useEffect(() => {
    const timer = setTimeout(() => {
      setDashboardReady(true);
      console.log('[DASHBOARD] v9.2.5 Dashboard prêt');
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
  
  // v9.2.7: Charger les settings plateforme au démarrage
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
  
  // v9.2.7: Fermer Quick Control si clic extérieur
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
  
  // === CRÉDITS COACH v8.9.7 ===
  // v9.2.3: Initialiser selon le rôle immédiatement pour éviter page blanche
  const [coachCredits, setCoachCredits] = useState(isSuperAdmin ? -1 : 0); // -1=illimité (Super Admin), 0=défaut
  
  // === v8.9.9: VITRINE COACH ===
  const [coachUsername, setCoachUsername] = useState(null);
  const coachVitrineUrl = coachUsername 
    ? `${window.location.origin}/coach/${coachUsername}`
    : isSuperAdmin ? `${window.location.origin}/coach/bassi` : null;
  
  // === v9.1.3: MARQUE BLANCHE - platform_name ===
  const [coachPlatformName, setCoachPlatformName] = useState(null);
  const dashboardTitle = coachPlatformName || (isSuperAdmin ? 'Afroboost' : 'Mon Espace Partenaire');
  
  // Helper: crédits insuffisants (pour info, mais plus de grisage v9.1.3)
  const hasInsufficientCredits = !isSuperAdmin && coachCredits !== null && coachCredits !== -1 && coachCredits <= 0;

  // v9.2.4: Charger profil coach avec protection try-catch complète
  useEffect(() => {
    const loadProfile = async () => {
      try {
        if (safeCoachUser?.email) {
          const res = await axios.get(`${BACKEND_URL}/api/coach/profile`, {
            headers: { 'X-User-Email': safeCoachUser.email }
          });
          setCoachCredits(res.data?.credits ?? 0);
          // v8.9.9: Récupérer username pour vitrine
          const username = res.data?.name?.toLowerCase().replace(/\s+/g, '-') || res.data?.id || safeCoachUser.email.split('@')[0];
          setCoachUsername(isSuperAdmin ? 'bassi' : username);
          // v9.1.3: Récupérer platform_name pour marque blanche
          setCoachPlatformName(res.data?.platform_name || null);
        }
      } catch (err) {
        // v9.2.4: FORCE AFFICHAGE - Dashboard s'affiche TOUJOURS même si profil inexistant
        console.warn('[COACH] v9.2.4 Profil non trouvé, utilisation des valeurs par défaut:', err?.response?.status || err?.message);
        // Pour Super Admin: crédits illimités
        if (isSuperAdmin) {
          setCoachCredits(-1);
          setCoachUsername('bassi');
          setCoachPlatformName('Afroboost');
        } else {
          // Pour les partenaires: valeurs par défaut (pas de blocage)
          setCoachCredits(0);
          setCoachUsername(safeCoachUser?.name?.toLowerCase().replace(/\s+/g, '-') || safeCoachUser?.email?.split('@')[0] || 'partenaire');
          setCoachPlatformName(null);
        }
      }
    };
    loadProfile();
  }, [safeCoachUser?.email, safeCoachUser?.name, isSuperAdmin]);

  // === v9.5.8: FONCTION DÉDUCTION CRÉDITS ===
  // Déduit 1 crédit et affiche message si solde épuisé
  const consumeCredit = async (action = "action") => {
    // Super Admin ne consomme jamais de crédits
    if (isSuperAdmin) {
      console.log('[CREDITS] Super Admin - action gratuite');
      return { success: true, bypassed: true };
    }
    
    // Vérifier le solde local d'abord
    if (coachCredits <= 0) {
      setValidationMessage('⚠️ Solde épuisé. Achetez un pack pour continuer.');
      setTimeout(() => setValidationMessage(''), 5000);
      return { success: false, error: "Crédits insuffisants" };
    }
    
    try {
      const res = await axios.post(`${BACKEND_URL}/api/credits/deduct`, 
        { action },
        { headers: { 'X-User-Email': safeCoachUser?.email } }
      );
      
      // Mettre à jour le solde local
      setCoachCredits(res.data?.credits_remaining ?? coachCredits - 1);
      console.log(`[CREDITS] ${action} - 1 crédit déduit, reste: ${res.data?.credits_remaining}`);
      
      return { success: true, credits_remaining: res.data?.credits_remaining };
    } catch (err) {
      console.error('[CREDITS] Erreur déduction:', err);
      if (err?.response?.status === 402) {
        setValidationMessage('⚠️ Solde épuisé. Achetez un pack pour continuer.');
        setTimeout(() => setValidationMessage(''), 5000);
        setCoachCredits(0);
      }
      return { success: false, error: err?.response?.data?.detail || "Erreur" };
    }
  };

  // === v9.5.8: BLOQUEUR D'ACTION SI CRÉDITS ÉPUISÉS ===
  const checkCreditsBeforeAction = () => {
    if (isSuperAdmin) return true;
    if (coachCredits <= 0) {
      setValidationMessage('⚠️ Solde épuisé. Achetez un pack pour continuer.');
      setTimeout(() => setValidationMessage(''), 5000);
      return false;
    }
    return true;
  };

  // Vérifier le statut Stripe Connect au chargement (pour les coachs seulement)
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
  
  // === PERSISTANCE ONGLET : Restaurer l'onglet depuis localStorage ===
  const [tab, setTab] = useState(() => {
    try {
      const savedTab = localStorage.getItem(COACH_TAB_KEY);
      // v9.2.9: Migration "payments" → "page-vente" et ajout du nouvel onglet
      if (savedTab && ['reservations', 'concept', 'courses', 'offers', 'payments', 'page-vente', 'codes', 'campaigns', 'articles', 'media', 'conversations'].includes(savedTab)) {
        const migratedTab = savedTab === 'payments' ? 'page-vente' : savedTab;
        console.log('[COACH] ✅ Onglet restauré:', migratedTab);
        return migratedTab;
      }
    } catch (e) {}
    return "reservations";
  });
  
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
  const [reservationsSearch, setReservationsSearch] = useState(''); // Recherche locale réservations
  const [reservationPagination, setReservationPagination] = useState({ page: 1, limit: 20, total: 0, pages: 0 });
  const [loadingReservations, setLoadingReservations] = useState(false);
  const [courses, setCourses] = useState([]);
  const [offers, setOffers] = useState([]);
  const [offersSearch, setOffersSearch] = useState(''); // Recherche locale offres
  const [users, setUsers] = useState([]);
  const [paymentLinks, setPaymentLinks] = useState({ stripe: "", paypal: "", twint: "", coachWhatsapp: "", coachNotificationEmail: "", coachNotificationPhone: "" });
  const [concept, setConcept] = useState({ appName: "Afroboost", description: "", heroImageUrl: "", logoUrl: "", faviconUrl: "", termsText: "", googleReviewsUrl: "", defaultLandingSection: "sessions", externalLink1Title: "", externalLink1Url: "", externalLink2Title: "", externalLink2Url: "", paymentTwint: false, paymentPaypal: false, paymentCreditCard: false, eventPosterEnabled: false, eventPosterMediaUrl: "" });
  const [discountCodes, setDiscountCodes] = useState([]);
  const [codesSearch, setCodesSearch] = useState(''); // Recherche locale codes promo
  const [newCode, setNewCode] = useState({ code: "", type: "", value: "", assignedEmails: [], courses: [], maxUses: "", expiresAt: "", batchCount: 1, prefix: "" });
  const [isBatchMode, setIsBatchMode] = useState(false);
  const [batchLoading, setBatchLoading] = useState(false);
  const [selectedBeneficiaries, setSelectedBeneficiaries] = useState([]); // Multi-select pour bénéficiaires
  const [editingCode, setEditingCode] = useState(null); // Pour l'édition individuelle des codes
  const [newCourse, setNewCourse] = useState({ name: "", weekday: 0, time: "18:30", locationName: "", mapsUrl: "" });
  const [newOffer, setNewOffer] = useState({ 
    name: "", price: 0, visible: true, description: "", keywords: "",
    images: ["", "", "", "", ""], // 5 champs d'images
    category: "service", isProduct: false, variants: null, tva: 0, shippingCost: 0, stock: -1
  });
  const [editingOfferId, setEditingOfferId] = useState(null); // Pour mode édition
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

  // ========== AUDIO PLAYLIST STATE ==========
  const [showAudioModal, setShowAudioModal] = useState(false);
  const [selectedCourseForAudio, setSelectedCourseForAudio] = useState(null);
  const [playlistUrls, setPlaylistUrls] = useState([]);
  const [newAudioUrl, setNewAudioUrl] = useState("");
  const [savingPlaylist, setSavingPlaylist] = useState(false);

  // Ouvrir le modal de gestion audio pour un cours
  const openAudioModal = (course) => {
    setSelectedCourseForAudio(course);
    setPlaylistUrls(course.playlist || []);
    setNewAudioUrl("");
    setShowAudioModal(true);
  };

  // Ajouter une URL à la playlist
  const addAudioUrl = () => {
    const url = newAudioUrl.trim();
    if (!url) return;
    
    // Validation basique de l'URL
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      alert("Veuillez entrer une URL valide commençant par http:// ou https://");
      return;
    }
    
    // Vérifier si c'est un MP3 ou stream audio
    const isAudioUrl = url.includes('.mp3') || url.includes('.wav') || url.includes('.ogg') || 
                       url.includes('.m3u') || url.includes('.m3u8') || url.includes('stream') ||
                       url.includes('audio') || url.includes('soundcloud') || url.includes('spotify');
    
    if (!isAudioUrl) {
      if (!window.confirm("Cette URL ne semble pas être un fichier audio (MP3, WAV, etc.) ou un stream. Voulez-vous l'ajouter quand même ?")) {
        return;
      }
    }
    
    if (playlistUrls.includes(url)) {
      alert("Cette URL est déjà dans la playlist.");
      return;
    }
    
    setPlaylistUrls([...playlistUrls, url]);
    setNewAudioUrl("");
  };

  // Supprimer une URL de la playlist
  const removeAudioUrl = (urlToRemove) => {
    setPlaylistUrls(playlistUrls.filter(url => url !== urlToRemove));
  };

  // Sauvegarder la playlist dans la base de données
  const savePlaylist = async () => {
    if (!selectedCourseForAudio) return;
    
    setSavingPlaylist(true);
    try {
      // Mettre à jour le cours avec la nouvelle playlist
      const updatedCourse = { ...selectedCourseForAudio, playlist: playlistUrls };
      await axios.put(`${API}/courses/${selectedCourseForAudio.id}`, updatedCourse);
      
      // Mettre à jour l'état local
      setCourses(courses.map(c => 
        c.id === selectedCourseForAudio.id 
          ? { ...c, playlist: playlistUrls } 
          : c
      ));
      
      alert(`✅ Playlist sauvegardée pour "${selectedCourseForAudio.name}" (${playlistUrls.length} morceaux)`);
      setShowAudioModal(false);
    } catch (err) {
      console.error("Erreur sauvegarde playlist:", err);
      alert("❌ Erreur lors de la sauvegarde de la playlist");
    } finally {
      setSavingPlaylist(false);
    }
  };

  // === PERSISTANCE ONGLET : Sauvegarder l'onglet actif ===
  useEffect(() => {
    if (tab) {
      localStorage.setItem(COACH_TAB_KEY, tab);
      console.log('[COACH] 💾 Onglet sauvegardé:', tab);
    }
  }, [tab]);
  
  // === v9.3.7: MÉMOIRE TOTALE - Auto-save Concept avec debounce ===
  const conceptSaveTimeoutRef = useRef(null);
  const [conceptSaveStatus, setConceptSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
  const isConceptLoaded = useRef(false); // Éviter save au premier chargement
  
  useEffect(() => {
    // Ne pas sauvegarder au premier chargement
    if (!isConceptLoaded.current) {
      isConceptLoaded.current = true;
      return;
    }
    
    // Debounce: attendre 1 seconde d'inactivité avant de sauvegarder
    if (conceptSaveTimeoutRef.current) {
      clearTimeout(conceptSaveTimeoutRef.current);
    }
    
    conceptSaveTimeoutRef.current = setTimeout(async () => {
      try {
        setConceptSaveStatus('saving');
        await axios.put(`${API}/concept`, concept, getCoachHeaders());
        setConceptSaveStatus('saved');
        console.log('[COACH] v9.3.7 Concept auto-sauvegardé');
        // Cacher le statut après 2 secondes
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
  
  // === v9.3.7: MÉMOIRE TOTALE - Auto-save PaymentLinks avec debounce ===
  const paymentSaveTimeoutRef = useRef(null);
  const [paymentSaveStatus, setPaymentSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
  const isPaymentLoaded = useRef(false); // Éviter save au premier chargement
  
  useEffect(() => {
    // Ne pas sauvegarder au premier chargement
    if (!isPaymentLoaded.current) {
      isPaymentLoaded.current = true;
      return;
    }
    
    // Debounce: attendre 1 seconde d'inactivité avant de sauvegarder
    if (paymentSaveTimeoutRef.current) {
      clearTimeout(paymentSaveTimeoutRef.current);
    }
    
    paymentSaveTimeoutRef.current = setTimeout(async () => {
      try {
        setPaymentSaveStatus('saving');
        await axios.put(`${API}/payment-links`, paymentLinks, getCoachHeaders());
        setPaymentSaveStatus('saved');
        console.log('[COACH] v9.3.7 Payment Links auto-sauvegardés');
        // Cacher le statut après 2 secondes
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
    try {
      const shareUrl = coachVitrineUrl || window.location.origin;
      await navigator.clipboard.writeText(shareUrl);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
      console.log('[COACH] ✅ Lien vitrine copié:', shareUrl);
    } catch (err) {
      // Fallback
      const textArea = document.createElement('textarea');
      textArea.value = coachVitrineUrl || window.location.origin;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand('copy');
      document.body.removeChild(textArea);
      setLinkCopied(true);
      setTimeout(() => setLinkCopied(false), 2000);
    }
  };
  
  // === DÉCONNEXION SÉCURISÉE ===
  const handleSecureLogout = () => {
    try {
      // Vider localStorage (sauf les clés critiques)
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
      
      console.log('[COACH] 🚪 Déconnexion sécurisée effectuée');
      
      // Appeler la fonction onLogout du parent
      if (onLogout) onLogout();
    } catch (err) {
      console.error('[COACH] ❌ Erreur déconnexion:', err);
      // Forcer la déconnexion même en cas d'erreur
      if (onLogout) onLogout();
    }
  };

  // Fonction pour charger les réservations avec pagination
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
        // v8.9.5: Charger les réservations avec isolation coach_id
        const resPromise = axios.get(`${API}/reservations?page=1&limit=20`, getCoachHeaders());
        const [res, crs, off, usr, lnk, cpt, cds] = await Promise.all([
          resPromise, axios.get(`${API}/courses`), axios.get(`${API}/offers`),
          axios.get(`${API}/users`), axios.get(`${API}/payment-links`), axios.get(`${API}/concept`), 
          axios.get(`${API}/discount-codes`)
        ]);
        // Réservations avec pagination
        setReservations(res.data.data);
        setReservationPagination(res.data.pagination);
        
        setCourses(crs.data); setOffers(off.data); setUsers(usr.data);
        setPaymentLinks(lnk.data); setConcept(cpt.data); setDiscountCodes(cds.data);
        
        // === SANITIZE DATA: Nettoyer automatiquement les données fantômes ===
        try {
          const sanitizeResult = await axios.post(`${API}/sanitize-data`);
          if (sanitizeResult.data.stats?.codes_cleaned > 0) {
            console.log(`🧹 Nettoyage: ${sanitizeResult.data.stats.codes_cleaned} codes promo nettoyés`);
            // Recharger les codes promo après nettoyage
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

  // Fonction de nettoyage manuel (peut être appelée depuis l'interface)
  const manualSanitize = async () => {
    try {
      const result = await axios.post(`${API}/sanitize-data`);
      const stats = result.data.stats;
      alert(`🧹 Nettoyage terminé!\n\n• ${stats.codes_cleaned} codes promo nettoyés\n• ${stats.valid_offers} offres valides\n• ${stats.valid_courses} cours valides\n• ${stats.valid_users} contacts valides`);
      // Recharger les codes promo
      const updatedCodes = await axios.get(`${API}/discount-codes`);
      setDiscountCodes(updatedCodes.data);
    } catch (err) {
      console.error("Erreur nettoyage:", err);
      alert("Erreur lors du nettoyage");
    }
  };

  // Get unique customers for beneficiary dropdown (filtrage local supplémentaire)
  const uniqueCustomers = Array.from(new Map(
    [...reservations.map(r => ({ name: r.userName, email: r.userEmail })), ...users.map(u => ({ name: u.name, email: u.email }))]
    .filter(c => c.email && c.name) // Exclure les entrées sans email ou nom
    .map(c => [c.email, c])
  ).values());

  const exportCSV = async () => {
    try {
      // Récupérer TOUTES les réservations pour l'export (sans pagination)
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
      setScanError(err.response?.data?.detail || 'Code non trouvé');
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
      alert("✅ Concept sauvegardé avec succès !");
    } catch (err) {
      console.error("Error saving concept:", err);
      console.error("Error details:", err.response?.data || err.message);
      const errorMessage = err.response?.data?.detail || err.message || "Erreur inconnue";
      alert(`❌ Erreur lors de la sauvegarde: ${errorMessage}`);
    }
  };
  const savePayments = async () => { await axios.put(`${API}/payment-links`, paymentLinks); alert("Saved!"); };

  // v9.5.8: addCode avec vérification crédits
  const addCode = async (e) => {
    e.preventDefault();
    if (!newCode.type || !newCode.value) return;
    
    // v9.5.8: Vérifier les crédits avant l'action (sauf Super Admin)
    if (!checkCreditsBeforeAction()) return;
    
    // Si mode série activé, utiliser la fonction batch
    if (isBatchMode && newCode.batchCount > 1) {
      await addBatchCodes(e);
      return;
    }
    
    // v9.5.8: Consommer un crédit pour cette action
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

  // Génération en série de codes promo - Crée réellement N entrées distinctes en base
  const addBatchCodes = async (e) => {
    e.preventDefault();
    if (!newCode.type || !newCode.value) return;
    
    const count = Math.min(Math.max(1, parseInt(newCode.batchCount) || 1), 50); // Entre 1 et 50
    const prefix = newCode.prefix?.trim().toUpperCase() || "CODE";
    
    setBatchLoading(true);
    const createdCodes = [];
    
    try {
      // Si plusieurs bénéficiaires sélectionnés, attribuer un code à chacun
      const beneficiaries = selectedBeneficiaries.length > 0 ? selectedBeneficiaries : [null];
      let codeIndex = 1;
      
      for (let i = 0; i < count; i++) {
        // Attribuer les bénéficiaires de manière circulaire si moins de bénéficiaires que de codes
        const beneficiaryEmail = beneficiaries[i % beneficiaries.length];
        const codeValue = `${prefix}-${String(codeIndex).padStart(2, '0')}`;
        codeIndex++;
        
        const response = await axios.post(`${API}/discount-codes`, {
          code: codeValue,
          type: newCode.type, 
          value: parseFloat(newCode.value),
          assignedEmail: beneficiaryEmail,
          courses: newCode.courses, // Cours ET produits autorisés
          maxUses: newCode.maxUses ? parseInt(newCode.maxUses) : null,
          expiresAt: newCode.expiresAt || null
        });
        createdCodes.push(response.data);
      }
      
      setDiscountCodes(prev => [...prev, ...createdCodes]);
      setNewCode({ code: "", type: "", value: "", assignedEmails: [], courses: [], maxUses: "", expiresAt: "", batchCount: 1, prefix: "" });
      setSelectedBeneficiaries([]);
      setIsBatchMode(false);
      alert(`✅ ${count} codes créés avec succès !`);
    } catch (error) {
      console.error("Erreur génération en série:", error);
      // Ajouter les codes déjà créés même si erreur partielle
      if (createdCodes.length > 0) {
        setDiscountCodes(prev => [...prev, ...createdCodes]);
        alert(`⚠️ ${createdCodes.length}/${count} codes créés. Erreur partielle.`);
      } else {
        alert("❌ Erreur lors de la création des codes.");
      }
    } finally {
      setBatchLoading(false);
    }
  };
  
  // Toggle sélection d'un bénéficiaire (multi-select)
  const toggleBeneficiarySelection = (email) => {
    setSelectedBeneficiaries(prev => 
      prev.includes(email) 
        ? prev.filter(e => e !== email)
        : [...prev, email]
    );
  };
  
  // Supprimer un article (cours/produit) de la liste des autorisés (formulaire de création)
  const removeAllowedArticle = (articleId) => {
    setNewCode(prev => ({
      ...prev,
      courses: prev.courses.filter(id => id !== articleId)
    }));
  };
  
  // Supprimer un article d'un code promo EXISTANT (mise à jour immédiate en base)
  const removeArticleFromExistingCode = async (codeId, articleId) => {
    const code = discountCodes.find(c => c.id === codeId);
    if (!code) return;
    
    const updatedCourses = (code.courses || []).filter(id => id !== articleId);
    
    try {
      await axios.put(`${API}/discount-codes/${codeId}`, { courses: updatedCourses });
      setDiscountCodes(prev => prev.map(c => 
        c.id === codeId ? { ...c, courses: updatedCourses } : c
      ));
      console.log(`✅ Article ${articleId} retiré du code ${code.code}`);
    } catch (error) {
      console.error("Erreur suppression article:", error);
      alert("❌ Erreur lors de la mise à jour");
    }
  };
  
  // Supprimer un bénéficiaire d'un code promo EXISTANT (mise à jour immédiate en base)
  const removeBeneficiaryFromExistingCode = async (codeId) => {
    try {
      await axios.put(`${API}/discount-codes/${codeId}`, { assignedEmail: null });
      setDiscountCodes(prev => prev.map(c => 
        c.id === codeId ? { ...c, assignedEmail: null } : c
      ));
      console.log(`✅ Bénéficiaire retiré du code`);
    } catch (error) {
      console.error("Erreur suppression bénéficiaire:", error);
      alert("❌ Erreur lors de la mise à jour");
    }
  };
  
  // Mettre à jour un code promo individuellement
  const updateCodeIndividual = async (codeId, updates) => {
    try {
      const response = await axios.put(`${API}/discount-codes/${codeId}`, updates);
      setDiscountCodes(prev => prev.map(c => c.id === codeId ? { ...c, ...updates } : c));
      setEditingCode(null);
      return true;
    } catch (error) {
      console.error("Erreur mise à jour code:", error);
      alert("❌ Erreur lors de la mise à jour");
      return false;
    }
  };

  const toggleCode = async (code) => {
    await axios.put(`${API}/discount-codes/${code.id}`, { active: !code.active });
    setDiscountCodes(discountCodes.map(c => c.id === code.id ? { ...c, active: !c.active } : c));
  };

  // Delete discount code - SUPPRESSION DÉFINITIVE EN BASE + VÉRIFICATION
  const deleteCode = async (codeId) => {
    if (window.confirm("⚠️ SUPPRESSION DÉFINITIVE\n\nCe code promo sera supprimé de la base de données.\nCette action est irréversible.\n\nConfirmer la suppression ?")) {
      try {
        await axios.delete(`${API}/discount-codes/${codeId}`);
        setDiscountCodes(prev => prev.filter(c => c.id !== codeId));
        console.log(`✅ Code ${codeId} supprimé définitivement`);
      } catch (error) {
        console.error("Erreur suppression code:", error);
        alert("❌ Erreur lors de la suppression");
      }
    }
  };
  
  // Delete reservation - SUPPRESSION DÉFINITIVE EN BASE
  const deleteReservation = async (reservationId) => {
    if (window.confirm("⚠️ SUPPRESSION DÉFINITIVE\n\nCette réservation sera supprimée de la base de données.\n\nConfirmer la suppression ?")) {
      try {
        console.log('DELETE_UI: Début suppression réservation:', reservationId);
        await axios.delete(`${API}/reservations/${reservationId}`);
        
        // Mise à jour immédiate de l'état - supporte id ET _id
        setReservations(prev => {
          const filtered = prev.filter(r => r.id !== reservationId && r._id !== reservationId);
          console.log(`DELETE_UI: Réservations filtrées: ${prev.length} -> ${filtered.length}`);
          return filtered;
        });
        
        // Mettre à jour le compteur de pagination
        setReservationPagination(prev => ({ ...prev, total: prev.total - 1 }));
        console.log(`DELETE_UI: ✅ Réservation ${reservationId} supprimée - UI mise à jour instantanément`);
      } catch (err) {
        console.error("DELETE_UI: ❌ ERREUR:", err);
        alert("❌ Erreur lors de la suppression");
      }
    }
  };
  
  // Add manual contact to users list (for beneficiary dropdown)
  // SYNCHRONISATION CRM: Ajoute aussi dans chat_participants
  const addManualContact = async (e) => {
    e.preventDefault();
    if (!manualContact.name || !manualContact.email) return;
    try {
      // 1. Créer dans la collection users (pour les codes promo)
      const response = await axios.post(`${API}/users`, {
        name: manualContact.name,
        email: manualContact.email,
        whatsapp: manualContact.whatsapp || ""
      });
      setUsers([...users, response.data]);
      
      // 2. SYNCHRONISATION: Créer aussi dans chat_participants (CRM global)
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
  
  // Supprimer un contact (Hard Delete avec nettoyage des références)
  // Supprimer un contact - SUPPRESSION DÉFINITIVE + NETTOYAGE CODES PROMO
  const deleteContact = async (userId) => {
    if (!window.confirm("⚠️ SUPPRESSION DÉFINITIVE\n\nCe contact sera supprimé de la base de données.\nSon email sera retiré de tous les codes promo.\n\nConfirmer la suppression ?")) return;
    try {
      // Récupérer l'email AVANT suppression du state
      const userToDelete = users.find(u => u.id === userId || u._id === userId);
      const userEmail = userToDelete?.email;
      
      // 1. Supprimer en base de données
      await axios.delete(`${API}/users/${userId}`);
      
      // 2. Mettre à jour TOUS les states locaux - supporte id ET _id
      setUsers(prev => {
        const filtered = prev.filter(u => u.id !== userId && u._id !== userId);
        console.log(`DELETE_UI: users filtré: ${prev.length} -> ${filtered.length}`);
        return filtered;
      });
      
      // 3. AUSSI mettre à jour chatParticipants au cas où
      setChatParticipants(prev => {
        const filtered = prev.filter(p => p.id !== userId && p._id !== userId);
        console.log(`DELETE_UI: chatParticipants filtré: ${prev.length} -> ${filtered.length}`);
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
      
      console.log(`DELETE_UI: ✅ Contact ${userId} supprimé définitivement`);
    } catch (err) {
      console.error("DELETE_UI: ❌ Erreur suppression contact:", err);
      alert("❌ Erreur lors de la suppression");
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
      alert("Aucun code promo à exporter.");
      return;
    }
    
    // CSV headers
    const headers = ["Code", "Type", "Valeur", "Bénéficiaire", "Utilisations Max", "Utilisé", "Date Expiration", "Actif", "Cours Autorisés"];
    
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
      console.error("Erreur mise à jour offre:", err);
    }
  };

  // Supprimer une offre - SUPPRESSION DÉFINITIVE + NETTOYAGE CODES PROMO
  const deleteOffer = async (offerId) => {
    if (!window.confirm("⚠️ SUPPRESSION DÉFINITIVE\n\nCette offre sera supprimée de la base de données.\nElle sera retirée de tous les codes promo.\n\nConfirmer la suppression ?")) return;
    try {
      // 1. Supprimer en base de données (le backend nettoie aussi les codes promo)
      await axios.delete(`${API}/offers/${offerId}`);
      
      // 2. Mettre à jour le state local
      setOffers(prev => prev.filter(o => o.id !== offerId));
      
      // 3. Nettoyer localement les références dans les codes promo
      setDiscountCodes(prev => prev.map(c => ({
        ...c,
        courses: c.courses ? c.courses.filter(id => id !== offerId) : []
      })));
      
      // 4. Appeler sanitizeData pour s'assurer que la base est propre
      try {
        await axios.post(`${API}/sanitize-data`);
      } catch (sanitizeErr) {
        console.warn("Sanitize warning:", sanitizeErr);
      }
      
      console.log(`✅ Offre ${offerId} supprimée définitivement`);
    } catch (err) {
      console.error("Erreur suppression offre:", err);
      alert("❌ Erreur lors de la suppression");
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
      keywords: offer.keywords || "", // FIX: Charger les mots-clés existants
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

  // Annuler l'édition
  const cancelEditOffer = () => {
    setNewOffer({ 
      name: "", price: 0, visible: true, description: "", keywords: "",
      images: ["", "", "", "", ""],
      category: "service", isProduct: false, variants: null, tva: 0, shippingCost: 0, stock: -1
    });
    setEditingOfferId(null);
  };

  // Ajouter ou mettre à jour une offre
  const addOffer = async (e) => {
    e.preventDefault();
    if (!newOffer.name) return;
    try {
      // Filtrer les images non vides
      const filteredImages = newOffer.images.filter(url => url && url.trim());
      const offerData = {
        ...newOffer,
        images: filteredImages,
        thumbnail: filteredImages[0] || "" // Première image comme thumbnail
      };

      if (editingOfferId) {
        // Mode édition : mettre à jour
        await axios.put(`${API}/offers/${editingOfferId}`, offerData);
        setOffers(prevOffers => prevOffers.map(o => o.id === editingOfferId ? { ...o, ...offerData } : o));
        setEditingOfferId(null);
      } else {
        // Mode ajout : créer nouvelle offre
        const response = await axios.post(`${API}/offers`, offerData);
        setOffers(prevOffers => [...prevOffers, response.data]);
      }
      
      // Reset formulaire
      setNewOffer({ 
        name: "", price: 0, visible: true, description: "",
        images: ["", "", "", "", ""],
        category: "service", isProduct: false, variants: null, tva: 0, shippingCost: 0, stock: -1 
      });
    } catch (err) {
      console.error("Erreur offre:", err);
      alert("Erreur lors de l'opération");
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
    targetConversationId: '', // ID de la conversation interne sélectionnée (legacy)
    targetConversationName: '', // Nom pour affichage (legacy)
    scheduleSlots: [], // Multi-date scheduling
    // === CHAMPS CTA ===
    ctaType: 'none', // 'none', 'reserver', 'offre', 'personnalise'
    ctaText: '',     // Texte personnalisé du bouton
    ctaLink: ''      // URL du bouton (pour offre et personnalise)
  });
  const [selectedContactsForCampaign, setSelectedContactsForCampaign] = useState([]);
  const [contactSearchQuery, setContactSearchQuery] = useState("");
  const [campaignLogs, setCampaignLogs] = useState([]); // Error logs
  const [editingCampaignId, setEditingCampaignId] = useState(null); // ID de la campagne en édition
  
  // === PANIER DE DESTINATAIRES (TAGS) ===
  const [selectedRecipients, setSelectedRecipients] = useState([]); // [{id, name, type: 'group'|'user'}]
  
  // === CONVERSATIONS ACTIVES POUR MESSAGERIE INTERNE ===
  const [activeConversations, setActiveConversations] = useState([]);
  const [showConversationDropdown, setShowConversationDropdown] = useState(false); // Dropdown ouvert/fermé
  
  // === FILTRES HISTORIQUE CAMPAGNES ===
  const [campaignHistoryFilter, setCampaignHistoryFilter] = useState('all'); // 'all', 'groups', 'individuals'
  
  // === SECTION CANAUX EXTERNES REPLIABLE ===
  const [externalChannelsExpanded, setExternalChannelsExpanded] = useState(false);
  
  // === SCHEDULER HEALTH STATE ===
  const [schedulerHealth, setSchedulerHealth] = useState({ status: "unknown", last_run: null });
  
  // === ENVOI DIRECT STATE ===
  const [directSendMode, setDirectSendMode] = useState(false);
  const [currentWhatsAppIndex, setCurrentWhatsAppIndex] = useState(0);
  const [instagramProfile, setInstagramProfile] = useState("afroboost"); // Profil Instagram par défaut
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

  // === ENVOI GROUPÉ STATE ===
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
  
  // === v9.4.3 FIX: Auto-save AIConfig APRÈS déclaration (corrige "Cannot access before initialization") ===
  const aiConfigSaveTimeoutRef = useRef(null);
  const [aiConfigSaveStatus, setAiConfigSaveStatus] = useState(null); // 'saving' | 'saved' | 'error'
  const isAiConfigLoaded = useRef(false); // Éviter save au premier chargement
  
  useEffect(() => {
    // Ne pas sauvegarder au premier chargement
    if (!isAiConfigLoaded.current) {
      isAiConfigLoaded.current = true;
      return;
    }
    
    // Debounce: attendre 1 seconde d'inactivité avant de sauvegarder
    if (aiConfigSaveTimeoutRef.current) {
      clearTimeout(aiConfigSaveTimeoutRef.current);
    }
    
    aiConfigSaveTimeoutRef.current = setTimeout(async () => {
      try {
        setAiConfigSaveStatus('saving');
        await axios.put(`${API}/ai-config`, aiConfig);
        setAiConfigSaveStatus('saved');
        console.log('[COACH] v9.4.3 AIConfig auto-sauvegardé');
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

  // === CONVERSATIONS STATE (CRM AVANCÉ) ===
  const [chatSessions, setChatSessions] = useState([]);
  const [chatParticipants, setChatParticipants] = useState([]);
  const [chatLinks, setChatLinks] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [sessionMessages, setSessionMessages] = useState([]);
  const [coachMessage, setCoachMessage] = useState('');
  const [newLinkTitle, setNewLinkTitle] = useState('');
  const [newLinkCustomPrompt, setNewLinkCustomPrompt] = useState('');  // Prompt spécifique au lien
  const [newCommunityName, setNewCommunityName] = useState('');  // Nom pour le chat communautaire
  const [loadingConversations, setLoadingConversations] = useState(false);
  const [copiedLinkId, setCopiedLinkId] = useState(null);
  const [conversationSearch, setConversationSearch] = useState(''); // Recherche globale conversations
  
  // === CRM AVANCÉ - Pagination et Infinite Scroll ===
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
    
    // Vérifier immédiatement puis toutes les 30 secondes
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
    }
  }, [tab]);

  // === RÉSOUDRE LA THUMBNAIL POUR L'APERÇU ===
  // Si mediaUrl est un lien interne /v/slug, on récupère la vraie thumbnail
  useEffect(() => {
    const resolveMediaThumbnail = async () => {
      const url = newCampaign.mediaUrl;
      
      if (!url) {
        setResolvedThumbnail(null);
        return;
      }
      
      // Vérifier si c'est un lien interne
      // Formats supportés: /v/slug, /api/share/slug
      let slug = null;
      if (url.includes('/api/share/')) {
        slug = url.split('/api/share/').pop().split('?')[0].split('#')[0].trim();
      } else if (url.includes('/v/')) {
        slug = url.split('/v/').pop().split('?')[0].split('#')[0].trim();
      }
      
      if (slug) {
        // Récupérer la thumbnail depuis l'API
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
  // === CRM AVANCÉ - Chargement des conversations avec pagination ===
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
        setChatSessions(conversations); // Compatibilité avec l'ancien code
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
  
  // === CRM AVANCÉ - Charger plus de conversations (Infinite Scroll) ===
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
  
  // === CRM AVANCÉ - Gestionnaire de scroll pour infinite scroll ===
  const handleConversationsScroll = useCallback((e) => {
    const { scrollTop, scrollHeight, clientHeight } = e.target;
    // Charger plus quand on arrive à 80% du scroll
    if (scrollTop + clientHeight >= scrollHeight * 0.8) {
      loadMoreConversations();
    }
  }, [conversationsHasMore, conversationsLoading, conversationsPage, conversationSearch]);
  
  // === CRM AVANCÉ - Recherche avec debounce ===
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
  
  // === CRM AVANCÉ - Formatage des dates ===
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
  
  // === CRM AVANCÉ - Grouper les conversations par date ===
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

  // === RÉSERVATIONS - Filtrage optimisé avec useMemo ===
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

  // Créer un chat communautaire (sans IA)
  const createCommunityChat = async () => {
    try {
      const title = newCommunityName.trim() || 'Chat Communauté Afroboost';
      // Créer une session avec mode communauté
      const sessionRes = await axios.post(`${API}/chat/sessions`, {
        mode: 'community',
        is_ai_active: false,
        title: title
      });
      
      // Mettre à jour les listes
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
      alert("Veuillez donner un nom à l'emoji");
      return;
    }
    
    // Valider le type de fichier
    if (!file.type.startsWith('image/')) {
      alert("Format non supporté. Utilisez PNG, JPG ou GIF.");
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
    // Insérer l'emoji sous forme de balise image dans le message
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
      
      // Préparer le message (emojis)
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
      
      // Si succès, vider le champ et recharger
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
    try {
      await navigator.clipboard.writeText(fullUrl);
      setCopiedLinkId(linkToken);
      setTimeout(() => setCopiedLinkId(null), 2000);
    } catch (err) {
      // Fallback pour mobile
      const textarea = document.createElement('textarea');
      textarea.value = fullUrl;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopiedLinkId(linkToken);
      setTimeout(() => setCopiedLinkId(null), 2000);
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
    if (!window.confirm("⚠️ Supprimer cette conversation ?\n\nLa conversation sera archivée (suppression logique).")) return;
    
    try {
      console.log('DELETE_DEBUG: Suppression session:', sessionId);
      await axios.put(`${API}/chat/sessions/${sessionId}`, { is_deleted: true });
      console.log('DELETE_DEBUG: API OK, mise à jour du state...');
      
      // Mettre à jour TOUS les states - supporte id ET _id
      setChatSessions(prev => {
        const filtered = prev.filter(s => s.id !== sessionId && s._id !== sessionId);
        console.log('DELETE_DEBUG: chatSessions filtré:', prev.length, '->', filtered.length);
        return filtered;
      });
      setEnrichedConversations(prev => {
        const filtered = prev.filter(c => c.id !== sessionId && c._id !== sessionId);
        console.log('DELETE_DEBUG: enrichedConversations filtré:', prev.length, '->', filtered.length);
        return filtered;
      });
      setChatLinks(prev => {
        const filtered = prev.filter(l => l.id !== sessionId && l._id !== sessionId);
        console.log('DELETE_DEBUG: chatLinks filtré:', prev.length, '->', filtered.length);
        return filtered;
      });
      
      // Si c'était la session sélectionnée, la désélectionner
      if (selectedSession?.id === sessionId || selectedSession?._id === sessionId) {
        setSelectedSession(null);
        setSessionMessages([]);
      }
      
      console.log('DELETE_DEBUG: Suppression terminée ✅');
    } catch (err) {
      console.error("DELETE_DEBUG: ERREUR:", err);
      alert("Erreur lors de la suppression de la conversation: " + (err.response?.data?.detail || err.message));
    }
  };

  // === SUPPRESSION LIEN DE CHAT ===
  const deleteChatLink = async (linkId) => {
    if (!window.confirm("⚠️ Supprimer ce lien de partage ?\n\nLe lien ne sera plus accessible. Cette action est irréversible.")) return;
    
    try {
      console.log('DELETE_DEBUG: Suppression lien:', linkId);
      await axios.delete(`${API}/chat/links/${linkId}`);
      console.log('DELETE_DEBUG: API OK pour lien, mise à jour du state...');
      
      setChatLinks(prev => {
        const filtered = prev.filter(l => l.id !== linkId && l._id !== linkId && l.link_token !== linkId);
        console.log('DELETE_DEBUG: chatLinks filtré:', prev.length, '->', filtered.length);
        return filtered;
      });
      setEnrichedConversations(prev => {
        const filtered = prev.filter(c => c.id !== linkId && c._id !== linkId && c.link_token !== linkId);
        console.log('DELETE_DEBUG: enrichedConversations filtré:', prev.length, '->', filtered.length);
        return filtered;
      });
      setChatSessions(prev => {
        const filtered = prev.filter(s => s.id !== linkId && s._id !== linkId && s.link_token !== linkId);
        console.log('DELETE_DEBUG: chatSessions filtré:', prev.length, '->', filtered.length);
        return filtered;
      });
      
      console.log('DELETE_DEBUG: Suppression lien terminée ✅');
    } catch (err) {
      console.error("DELETE_DEBUG: ERREUR lien:", err);
      alert("Erreur lors de la suppression du lien: " + (err.response?.data?.detail || err.message));
    }
  };

  // === AJOUTER CONTACT MANUEL AU CRM (synchronisé avec codes promo) ===
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
  
  // Ajouter un toast de notification (fallback quand les notifications browser sont bloquées)
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
    
    // Auto-dismiss après 10 secondes
    setTimeout(() => {
      setToastNotifications(prev => prev.filter(t => t.id !== id));
    }, 10000);
  }, []);
  
  // Supprimer un toast
  const dismissToast = useCallback((toastId) => {
    setToastNotifications(prev => prev.filter(t => t.id !== toastId));
  }, []);
  
  // === TOAST GÉNÉRIQUE POUR CAMPAGNES ===
  const showCampaignToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
    const colors = { 
      success: 'bg-green-600/90 border-green-500', 
      error: 'bg-red-600/90 border-red-500', 
      info: 'bg-blue-600/90 border-blue-500',
      warning: 'bg-yellow-600/90 border-yellow-500'
    };
    
    const toast = {
      id,
      message: `${icons[type] || 'ℹ️'} ${message}`,
      type,
      color: colors[type] || colors.info,
      createdAt: new Date().toISOString()
    };
    
    setToastNotifications(prev => [...prev.slice(-4), toast]);
    
    // Auto-dismiss après 5 secondes (plus rapide pour les notifications de campagne)
    setTimeout(() => {
      setToastNotifications(prev => prev.filter(t => t.id !== id));
    }, 5000);
  }, []);
  
  // Cliquer sur un toast pour aller à la conversation
  const handleToastClick = useCallback((toast) => {
    const session = chatSessions.find(s => s.id === toast.sessionId);
    if (session) {
      setSelectedSession(session);
      loadSessionMessages(session.id);
    }
    dismissToast(toast.id);
  }, [chatSessions, dismissToast]);
  
  // === ÉTAT POUR NOTIFICATION IA ===
  const [notifyOnAiResponse, setNotifyOnAiResponse] = useState(
    localStorage.getItem('afroboost_notify_ai') === 'true'
  );
  
  // Sauvegarder la préférence
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
        await showBrowserNotification('🔔 Test Notification', {
          body: 'Les notifications fonctionnent correctement !',
          icon: '/favicon.ico'
        });
      } else {
        // Fallback: ajouter un toast
        addToastNotification({
          id: Date.now(),
          senderName: 'Test',
          content: '🔔 Les notifications fonctionnent (mode fallback)',
          sessionId: null
        });
      }
    } catch (error) {
      console.error('[NOTIFICATION] Test error:', error);
      // Fallback toast même en cas d'erreur
      addToastNotification({
        id: Date.now(),
        senderName: 'Test',
        content: '🔔 Notification test (fallback)',
        sessionId: null
      });
    }
  }, [addToastNotification]);
  
  // Vérifier le statut de permission au chargement ET activer le polling si déjà autorisé
  useEffect(() => {
    const initNotifications = async () => {
      const { getNotificationPermissionStatus, unlockAudio } = await import('../services/notificationService');
      const status = getNotificationPermissionStatus();
      setNotificationPermission(status);
      
      console.log('[NOTIFICATIONS] Statut initial:', status);
      
      // Afficher le banner si permission pas encore demandée
      if (status === 'default') {
        setShowPermissionBanner(true);
      } else if (status === 'granted') {
        // Permission déjà accordée - déverrouiller l'audio silencieusement
        console.log('[NOTIFICATIONS] Permission déjà accordée, polling actif automatiquement');
        try {
          await unlockAudio();
        } catch (e) {
          // Silencieux - l'audio sera débloqué au premier clic
        }
      }
    };
    initNotifications();
  }, []);
  
  // Demander la permission de notification explicitement (appelé par le bouton)
  const requestNotificationAccess = useCallback(async () => {
    try {
      // Déverrouiller l'audio (nécessaire sur iOS)
      const { unlockAudio, requestNotificationPermission } = await import('../services/notificationService');
      await unlockAudio();
      
      // Demander la permission des notifications browser
      const permission = await requestNotificationPermission();
      setNotificationPermission(permission);
      setShowPermissionBanner(false);
      
      if (permission === 'granted') {
        console.log('[NOTIFICATIONS] Permission accordée!');
        // Afficher une notification de test
        const { showBrowserNotification } = await import('../services/notificationService');
        await showBrowserNotification(
          '✅ Notifications activées',
          'Vous recevrez désormais les alertes de nouveaux messages.',
          { tag: 'afroboost-permission-granted' }
        );
      } else if (permission === 'denied') {
        console.log('[NOTIFICATIONS] Permission refusée - utilisation du fallback toast');
      }
    } catch (err) {
      console.warn('[NOTIFICATIONS] Erreur permission:', err);
    }
  }, []);
  
  // Vérifier les nouveaux messages non notifiés (endpoint optimisé)
  const checkUnreadNotifications = useCallback(async () => {
    if (tab !== 'conversations') return;
    
    console.log('NOTIF_DEBUG: Polling démarré...');
    
    try {
      const res = await axios.get(`${API}/notifications/unread`, {
        params: { 
          target: 'coach',
          include_ai: notifyOnAiResponse  // Inclure les réponses IA si option activée
        }
      });
      
      const { count, messages } = res.data;
      console.log(`NOTIF_DEBUG: ${count} messages non lus, ${messages?.length || 0} à traiter`);
      setUnreadCount(count);
      
      if (messages && messages.length > 0) {
        // Filtrer les messages déjà notifiés localement
        const newMessages = messages.filter(m => !lastNotifiedIdsRef.current.has(m.id));
        console.log(`NOTIF_DEBUG: ${newMessages.length} NOUVEAUX messages détectés`);
        
        if (newMessages.length > 0) {
          console.log('NOTIF_DEBUG: ⚡ Nouveaux messages! Tentative notification...');
          
          // Importer les fonctions de notification
          const { playNotificationSound, showBrowserNotification, getNotificationPermissionStatus } = await import('../services/notificationService');
          
          // Jouer le son (avec protection contre les erreurs)
          try {
            console.log('NOTIF_DEBUG: Jouer son...');
            await playNotificationSound('user');
            console.log('NOTIF_DEBUG: Son joué ✅');
          } catch (soundErr) {
            console.warn('NOTIF_DEBUG: Erreur son (ignorée):', soundErr.message);
            // Continuer même si le son échoue
          }
          
          // Vérifier la permission actuelle
          const currentPermission = getNotificationPermissionStatus();
          console.log('NOTIF_DEBUG: Permission actuelle:', currentPermission);
          
          // Afficher une notification pour chaque nouveau message (max 3)
          for (const msg of newMessages.slice(0, 3)) {
            console.log(`NOTIF_DEBUG: Traitement message de ${msg.sender_name}...`);
            
            // Essayer d'afficher une notification browser
            try {
              const result = await showBrowserNotification(
                '💬 Nouveau message - Afroboost',
                `${msg.sender_name}: ${msg.content.substring(0, 80)}${msg.content.length > 80 ? '...' : ''}`,
                {
                  tag: `afroboost-msg-${msg.id}`,
                  onClick: () => {
                    // Sélectionner la session correspondante
                    const session = chatSessions.find(s => s.id === msg.session_id);
                    if (session) {
                      setSelectedSession(session);
                      loadSessionMessages(session.id);
                    }
                  }
                }
              );
              
              console.log('NOTIF_DEBUG: Résultat notification:', result);
              
              // Si la notification browser a échoué, utiliser le fallback toast
              if (result.fallbackNeeded) {
                console.log('NOTIF_DEBUG: Fallback TOAST activé!');
                addToastNotification(msg);
              } else {
                console.log('NOTIF_DEBUG: Notification browser envoyée ✅');
              }
            } catch (notifErr) {
              console.warn('NOTIF_DEBUG: Erreur notification (fallback toast):', notifErr.message);
              addToastNotification(msg);
            }
            
            // Ajouter à la liste des messages notifiés localement (TOUJOURS, même en cas d'erreur)
            lastNotifiedIdsRef.current.add(msg.id);
          }
          
          // Marquer les messages comme notifiés côté serveur
          const messageIds = newMessages.map(m => m.id);
          await axios.put(`${API}/notifications/mark-read`, {
            message_ids: messageIds
          }).catch(() => {}); // Ignorer les erreurs silencieusement
          
          // Rafraîchir les conversations
          loadConversations(true);
        }
      }
    } catch (err) {
      // Fallback vers l'ancienne méthode si le nouvel endpoint n'est pas disponible
      console.warn('[NOTIFICATIONS] Erreur polling:', err);
    }
  }, [tab, chatSessions, addToastNotification, notifyOnAiResponse]);
  
  // Polling des notifications toutes les 10 secondes
  useEffect(() => {
    if (tab !== 'conversations') return;
    
    console.log('[NOTIFICATIONS] Polling activé (interval 10s)');
    
    // Vérifier immédiatement
    checkUnreadNotifications();
    
    // Puis toutes les 10 secondes
    const interval = setInterval(() => {
      checkUnreadNotifications();
    }, 10000);
    
    // Cleanup important pour éviter les fuites mémoire
    return () => {
      console.log('[NOTIFICATIONS] Polling désactivé');
      clearInterval(interval);
    };
  }, [tab, checkUnreadNotifications]);

  // === POLLING LEGACY pour les sessions en mode humain ===
  const lastMessageCountRef = useRef({});
  
  const checkNewMessages = useCallback(async () => {
    if (tab !== 'conversations') return;
    
    // Vérifier les sessions en mode humain pour les nouveaux messages
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
            // Note: Le son est maintenant géré par checkUnreadNotifications
            
            // Mettre à jour les messages si c'est la session sélectionnée
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
      // Rafraîchir aussi la liste des sessions
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

  // === CONTACTS COMBINÉS: Users + Reservations + Chat Participants ===
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
    
    // 2. Réservations
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

  // === ÉDITION CAMPAGNE ===
  // Pré-remplir le formulaire avec les données d'une campagne existante
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
      scheduleSlots: [] // On ne peut pas modifier les schedules existants
    });
    // Pré-sélectionner les contacts CRM si mode "selected"
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
    showCampaignToast(`📝 Mode édition: "${campaign.name}"`, 'info');
  };

  // Annuler l'édition et réinitialiser le formulaire
  const cancelEditCampaign = () => {
    setEditingCampaignId(null);
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
    setSelectedRecipients([]); // Vider aussi le panier
  };

  // Create OR Update campaign (supports multiple schedule slots)
  const createCampaign = async (e) => {
    e.preventDefault();
    if (!newCampaign.name || !newCampaign.message) return;
    
    // Valider qu'il y a au moins un destinataire
    const hasRecipients = selectedRecipients.length > 0 || newCampaign.channels.whatsapp || newCampaign.channels.email || newCampaign.channels.group;
    if (!hasRecipients) {
      showCampaignToast('⚠️ Ajoutez au moins un destinataire', 'error');
      return;
    }
    
    // Préparer les targetIds depuis le panier
    const targetIds = selectedRecipients.map(r => r.id);
    
    // === MODE ÉDITION : Mise à jour d'une campagne existante ===
    if (editingCampaignId) {
      try {
        const updateData = {
          name: newCampaign.name,
          message: newCampaign.message,
          mediaUrl: newCampaign.mediaUrl,
          mediaFormat: newCampaign.mediaFormat,
          targetType: newCampaign.targetType,
          selectedContacts: newCampaign.targetType === "selected" ? selectedContactsForCampaign : [],
          channels: newCampaign.channels,
          targetGroupId: newCampaign.targetGroupId || 'community',
          targetIds: targetIds, // Tableau des IDs du panier
          targetConversationId: targetIds[0] || '', // Premier ID pour compatibilité
          targetConversationName: selectedRecipients[0]?.name || ''
        };
        const res = await axios.put(`${API}/campaigns/${editingCampaignId}`, updateData);
        setCampaigns(campaigns.map(c => c.id === editingCampaignId ? res.data : c));
        addCampaignLog(editingCampaignId, `Campagne "${newCampaign.name}" modifiée avec succès`, 'success');
        
        // Reset form et mode édition
        cancelEditCampaign();
        setSelectedRecipients([]); // Vider le panier
        alert(`✅ Campagne "${newCampaign.name}" modifiée avec succès !`);
        return;
      } catch (err) {
        console.error("Error updating campaign:", err);
        addCampaignLog(editingCampaignId, `Erreur modification: ${err.message}`, 'error');
        alert(`❌ Erreur lors de la modification: ${err.message}`);
        return;
      }
    }
    
    // === MODE CRÉATION : Nouvelle campagne ===
    const scheduleSlots = newCampaign.scheduleSlots;
    const isImmediate = scheduleSlots.length === 0;
    
    // Préparer les champs CTA (seulement si un type est sélectionné)
    const ctaFields = newCampaign.ctaType !== 'none' ? {
      ctaType: newCampaign.ctaType,
      ctaText: newCampaign.ctaText || (newCampaign.ctaType === 'reserver' ? 'RÉSERVER' : newCampaign.ctaType === 'offre' ? 'VOIR L\'OFFRE' : 'EN SAVOIR PLUS'),
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
          ...ctaFields  // Ajouter les champs CTA
        };
        const res = await axios.post(`${API}/campaigns`, campaignData);
        setCampaigns([res.data, ...campaigns]);
        addCampaignLog(res.data.id, `Campagne "${newCampaign.name}" créée (${targetIds.length} destinataire(s))`, 'success');
      } else {
        // Create one campaign per schedule slot (multi-date)
        for (let i = 0; i < scheduleSlots.length; i++) {
          const slot = scheduleSlots[i];
          const scheduledAt = `${slot.date}T${slot.time}:00`;
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
            ...ctaFields  // Ajouter les champs CTA
          };
          const res = await axios.post(`${API}/campaigns`, campaignData);
          setCampaigns(prev => [res.data, ...prev]);
          addCampaignLog(res.data.id, `Campagne "${campaignData.name}" programmée pour ${new Date(scheduledAt).toLocaleString('fr-FR')}`, 'info');
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
      showCampaignToast(`${isImmediate ? 'Campagne créée' : `${scheduleSlots.length} campagne(s) programmée(s)`} avec succès !`, 'success');
    } catch (err) { 
      console.error("Error creating campaign:", err);
      addCampaignLog('new', `Erreur création campagne: ${err.message}`, 'error');
      showCampaignToast(`Erreur: ${err.message}`, 'error');
    }
  };

  // Launch campaign (generate links)
  const launchCampaign = async (campaignId) => {
    try {
      addCampaignLog(campaignId, 'Lancement de la campagne...', 'info');
      const res = await axios.post(`${API}/campaigns/${campaignId}/launch`);
      setCampaigns(campaigns.map(c => c.id === campaignId ? res.data : c));
      addCampaignLog(campaignId, `Campagne lancée avec ${res.data.results?.length || 0} destinataire(s)`, 'success');
      showCampaignToast(`Campagne lancée ! ${res.data.results?.length || 0} destinataire(s)`, 'success');
    } catch (err) { 
      console.error("Error launching campaign:", err);
      addCampaignLog(campaignId, `Erreur lancement: ${err.message}`, 'error');
      showCampaignToast(`Erreur lancement: ${err.message}`, 'error');
    }
  };

  // Launch campaign WITH REAL SENDING via Resend and Twilio
  // === BOUTON LANCER - ISOLATION COMPLÈTE ===
  const launchCampaignWithSend = async (e, campaignId) => {
    // === BLOCAGE CRASH POSTHOG ===
    // Ces lignes DOIVENT être en premier, avant toute autre logique
    e.preventDefault();
    e.stopPropagation();
    
    try {
      // 1. Récupérer la campagne
      const campaign = campaigns.find(c => c.id === campaignId);
      if (!campaign) {
        alert('❌ Campagne non trouvée');
        return;
      }

      // Log isolé (peut être ignoré si PostHog crash)
      try {
        addCampaignLog(campaignId, 'Préparation de l\'envoi...', 'info');
      } catch (logErr) {
        console.warn('PostHog bloqué sur log mais envoi maintenu:', logErr);
      }

      // 2. Préparer d'abord la campagne côté backend
      const launchRes = await axios.post(`${API}/campaigns/${campaignId}/launch`);
      const launchedCampaign = launchRes.data;
      
      try {
        setCampaigns(campaigns.map(c => c.id === campaignId ? launchedCampaign : c));
      } catch (stateErr) {
        console.warn('PostHog bloqué sur setState mais envoi maintenu:', stateErr);
      }

      // 3. Récupérer les contacts à envoyer
      const results = launchedCampaign.results || [];
      if (results.length === 0) {
        alert('⚠️ Aucun contact à envoyer');
        return;
      }

      // 4. Séparer par canal
      const emailResults = results.filter(r => r.channel === 'email' && r.contactEmail);
      const whatsAppResults = results.filter(r => r.channel === 'whatsapp' && r.contactPhone);

      // Confirmation
      const confirmMsg = `🚀 Lancer la campagne "${campaign.name}" ?\n\n` +
        `📧 ${emailResults.length} email(s)\n` +
        `📱 ${whatsAppResults.length} WhatsApp\n\n` +
        `⚠️ Cette action est irréversible.`;
      
      if (!window.confirm(confirmMsg)) {
        return;
      }

      let totalSent = 0;
      let totalFailed = 0;

      // 5. === ENVOI EMAILS VIA RESEND (BACKEND) ===
      if (emailResults.length > 0) {
        try {
          addCampaignLog(campaignId, `📧 Envoi de ${emailResults.length} email(s) via Resend...`, 'info');
        } catch (e) { console.warn('Log bloqué:', e); }
        
        console.log(`RESEND_DEBUG: === LANCEMENT CAMPAGNE: ${emailResults.length} destinataires ===`);
        
        for (let i = 0; i < emailResults.length; i++) {
          const contact = emailResults[i];
          
          console.log(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] Envoi à: ${contact.contactEmail}`);
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
              console.log(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] SUCCÈS - ID = ${result.email_id}`);
              totalSent++;
              
              // Marquer comme envoyé
              try {
                await axios.post(`${API}/campaigns/${campaignId}/mark-sent`, {
                  contactId: contact.contactId,
                  channel: 'email'
                });
              } catch (markErr) {
                console.warn('RESEND_DEBUG: Mark-sent bloqué mais email envoyé');
              }
            } else {
              console.error(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] ÉCHEC - ${result.error}`);
              totalFailed++;
            }
            
          } catch (error) {
            console.error(`RESEND_DEBUG: [${i + 1}/${emailResults.length}] EXCEPTION - ${error.message}`);
            totalFailed++;
          }
          
          // Délai entre les envois
          if (i < emailResults.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 300));
          }
        }
      }

      // 6. === ENVOI WHATSAPP VIA FONCTION AUTONOME ===
      if (whatsAppResults.length > 0) {
        try {
          addCampaignLog(campaignId, `📱 Envoi de ${whatsAppResults.length} WhatsApp...`, 'info');
        } catch (e) { console.warn('Log bloqué:', e); }
        
        console.log(`📱 === LANCEMENT CAMPAGNE WHATSAPP: ${whatsAppResults.length} destinataires ===`);
        
        for (let i = 0; i < whatsAppResults.length; i++) {
          const contact = whatsAppResults[i];
          
          console.log(`📱 [${i + 1}/${whatsAppResults.length}] Envoi à: ${contact.contactPhone}`);
          
          // === APPEL FONCTION AUTONOME ISOLÉE ===
          const result = await performWhatsAppSend(
            contact.contactPhone,
            campaign.message,
            whatsAppConfig
          );

          if (result.success) {
            totalSent++;
            console.log(`✅ WhatsApp envoyé${result.simulated ? ' (simulation)' : ''}`);
            // Marquer comme envoyé
            try {
              await axios.post(`${API}/campaigns/${campaignId}/mark-sent`, {
                contactId: contact.contactId,
                channel: 'whatsapp'
              });
            } catch (markErr) {
              console.warn('⚠️ Mark-sent bloqué mais WhatsApp envoyé:', markErr);
            }
          } else {
            totalFailed++;
            console.error(`❌ WhatsApp failed: ${result.error}`);
          }
          
          // Délai entre les envois
          if (i < whatsAppResults.length - 1) {
            await new Promise(resolve => setTimeout(resolve, 500));
          }
        }
      }

      // 7. Recharger la campagne (peut être ignoré)
      try {
        const updatedRes = await axios.get(`${API}/campaigns/${campaignId}`);
        setCampaigns(campaigns.map(c => c.id === campaignId ? updatedRes.data : c));
      } catch (reloadErr) {
        console.warn('Reload bloqué mais envois effectués:', reloadErr);
      }

      // 8. Notification finale
      try {
        addCampaignLog(campaignId, `✅ Terminé: ${totalSent} envoyés, ${totalFailed} échoués`, 'success');
      } catch (e) { console.warn('Log final bloqué:', e); }
      
      alert(`✅ Campagne "${campaign.name}" terminée !\n\n✓ Envoyés: ${totalSent}\n✗ Échoués: ${totalFailed}`);

    } catch (err) {
      console.error("Error launching campaign with send:", err);
      try {
        addCampaignLog(campaignId, `❌ Erreur: ${err.message}`, 'error');
      } catch (e) { console.warn('Log erreur bloqué:', e); }
      alert(`❌ Erreur lors de l'envoi: ${err.message}`);
    }
  };

  // Delete campaign
  const deleteCampaign = async (campaignId) => {
    if (!window.confirm("Supprimer cette campagne ?")) return;
    try {
      await axios.delete(`${API}/campaigns/${campaignId}`);
      setCampaigns(campaigns.filter(c => c.id !== campaignId));
      addCampaignLog(campaignId, 'Campagne supprimée', 'info');
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
      .replace(/{prénom}/gi, firstName)
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
      .replace(/{prénom}/gi, firstName)
      .replace(/{prenom}/gi, firstName)
      .replace(/{nom}/gi, contactName || '');
    
    const fullMessage = mediaUrl 
      ? `${personalizedMessage}\n\n🔗 Voir le visuel: ${mediaUrl}` 
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

  // Générer mailto: groupé avec BCC pour tous les emails
  const generateGroupedEmailLink = () => {
    const contacts = getContactsForDirectSend();
    const emails = contacts.map(c => c.email).filter(e => e && e.includes('@'));
    
    if (emails.length === 0) return null;
    
    const subject = newCampaign.name || "Afroboost - Message";
    const body = newCampaign.mediaUrl 
      ? `${newCampaign.message}\n\n🔗 Voir le visuel: ${newCampaign.mediaUrl}`
      : newCampaign.message;
    
    // Premier email en "to", reste en BCC pour confidentialité
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

  // Passer au contact WhatsApp précédent
  const prevWhatsAppContact = () => {
    if (currentWhatsAppIndex > 0) {
      setCurrentWhatsAppIndex(currentWhatsAppIndex - 1);
    }
  };

  // Copier le message pour Instagram
  const copyMessageForInstagram = async () => {
    const message = newCampaign.mediaUrl 
      ? `${newCampaign.message}\n\n🔗 ${newCampaign.mediaUrl}`
      : newCampaign.message;
    
    try {
      await navigator.clipboard.writeText(message);
      setMessageCopied(true);
      setTimeout(() => setMessageCopied(false), 3000);
    } catch (err) {
      // Fallback pour navigateurs plus anciens
      const textarea = document.createElement('textarea');
      textarea.value = message;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
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
        alert('✅ Email de test envoyé avec succès via Resend !');
      } else {
        setTestEmailStatus('error');
        alert(`❌ Erreur: ${result.error}`);
      }
    } catch (error) {
      setTestEmailStatus('error');
      alert(`❌ Erreur: ${error.message}`);
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
    
    console.log('EMAILJS_DEBUG: Campagne email démarrée');

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
    if (!window.confirm(`Envoyer ${emailContacts.length} email(s) automatiquement ?\n\nSujet: ${newCampaign.name || 'Afroboost - Message'}\n\nCette action est irréversible.`)) {
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
      
      // Délai
      await new Promise(r => setTimeout(r, 300));
    }

    console.log('CAMPAGNE TERMINÉE - Envoyés:', results.sent, '- Échoués:', results.failed);

    setEmailSendingResults(results);
    setEmailSendingProgress(null);

    if (results.sent > 0) {
      alert(`✅ Envoyés: ${results.sent} / Échoués: ${results.failed}`);
    } else {
      alert(`❌ Échec total. Erreurs: ${results.errors.join(', ')}`);
    }
  };

  // === WHATSAPP API FUNCTIONS ===
  
  // === FONCTION ENVOI WHATSAPP DIRECT AVEC LOG ===
  // Log clair pour vérifier que les données circulent
  const sendWhatsAppMessageDirect = async (phoneNumber, message, mediaUrl = null) => {
    const config = whatsAppConfig;
    
    // LOG CLAIR: Afficher toutes les données envoyées
    console.log('📱 === ENVOI WHATSAPP ===');
    console.log('📱 Envoi WhatsApp vers:', phoneNumber);
    console.log('📱 Message:', message);
    console.log('📱 Media URL:', mediaUrl || 'Aucun');
    console.log('📱 Avec SID:', config.accountSid || 'NON CONFIGURÉ');
    console.log('📱 Auth Token:', config.authToken ? '***' + config.authToken.slice(-4) : 'NON CONFIGURÉ');
    console.log('📱 From Number:', config.fromNumber || 'NON CONFIGURÉ');
    
    // Vérifier la configuration
    if (!config.accountSid || !config.authToken || !config.fromNumber) {
      console.error('❌ Configuration WhatsApp/Twilio incomplète');
      return { 
        success: false, 
        error: 'Configuration Twilio incomplète. Vérifiez Account SID, Auth Token et From Number.' 
      };
    }
    
    // Formater le numéro au format E.164
    let formattedPhone = phoneNumber.replace(/[^\d+]/g, '');
    if (!formattedPhone.startsWith('+')) {
      if (formattedPhone.startsWith('0')) {
        formattedPhone = '+41' + formattedPhone.substring(1);
      } else {
        formattedPhone = '+' + formattedPhone;
      }
    }
    
    console.log('📱 Numéro formaté:', formattedPhone);
    
    // Construire les données pour Twilio
    const formData = new URLSearchParams();
    formData.append('From', `whatsapp:${config.fromNumber.startsWith('+') ? config.fromNumber : '+' + config.fromNumber}`);
    formData.append('To', `whatsapp:${formattedPhone}`);
    formData.append('Body', message);
    
    if (mediaUrl) {
      formData.append('MediaUrl', mediaUrl);
    }
    
    console.log('📱 Données Twilio:', Object.fromEntries(formData));
    
    try {
      // Appel DIRECT à l'API Twilio
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
      console.log('📱 Réponse Twilio:', data);
      
      if (!response.ok) {
        return { success: false, error: data.message || `HTTP ${response.status}`, code: data.code };
      }
      
      return { success: true, sid: data.sid, status: data.status };
    } catch (error) {
      console.error('❌ Erreur Twilio:', error);
      return { success: false, error: error.message };
    }
  };
  
  // Sauvegarder la configuration WhatsApp
  const handleSaveWhatsAppConfig = async () => {
    const success = await saveWhatsAppConfig(whatsAppConfig);
    if (success) {
      setShowWhatsAppConfig(false);
      alert('✅ Configuration WhatsApp API sauvegardée !');
    } else {
      alert('❌ Erreur lors de la sauvegarde');
    }
  };

  // === FONCTION TEST WHATSAPP - ISOLATION COMPLÈTE ===
  // Utilise la fonction autonome performWhatsAppSend pour éviter les conflits PostHog
  const handleTestWhatsApp = async (e) => {
    // === BLOCAGE CRASH POSTHOG ===
    // Ces lignes DOIVENT être en premier, avant toute autre logique
    e.preventDefault();
    e.stopPropagation();
    
    // Validation basique
    if (!testWhatsAppNumber) {
      alert('Veuillez entrer un numéro de téléphone pour le test');
      return;
    }
    
    // Sauvegarder la config (peut être ignoré si PostHog crash)
    try {
      await handleSaveWhatsAppConfig();
    } catch (saveError) {
      console.warn('PostHog bloqué sur sauvegarde mais envoi maintenu:', saveError);
    }
    
    // Mise à jour UI - dans un try/catch séparé pour isoler PostHog
    try {
      setTestWhatsAppStatus('sending');
    } catch (stateError) {
      console.warn('PostHog bloqué sur setState mais envoi maintenu:', stateError);
    }
    
    // === ENVOI TECHNIQUE - ISOLÉ DE LA GESTION D'ÉTAT ===
    try {
      // Appel de la fonction autonome (hors composant React)
      const result = await performWhatsAppSend(
        testWhatsAppNumber,
        '🎉 Test Afroboost WhatsApp API!\n\nVotre configuration Twilio fonctionne correctement.',
        whatsAppConfig
      );
      
      // Gestion du résultat - également isolée
      try {
        if (result.success) {
          setTestWhatsAppStatus('success');
          if (result.simulated) {
            // Mode simulation
            setTimeout(() => setTestWhatsAppStatus(null), 3000);
          } else {
            alert(`✅ WhatsApp de test envoyé avec succès !\n\nSID: ${result.sid}`);
            setTimeout(() => setTestWhatsAppStatus(null), 5000);
          }
        } else {
          setTestWhatsAppStatus('error');
          alert(`❌ Erreur Twilio: ${result.error}`);
          setTimeout(() => setTestWhatsAppStatus(null), 3000);
        }
      } catch (uiError) {
        console.warn('PostHog bloqué sur UI update mais envoi réussi:', uiError);
        if (result.success) {
          alert('✅ WhatsApp envoyé (UI bloquée par PostHog)');
        }
      }
    } catch (sendError) {
      console.error('❌ Erreur envoi WhatsApp:', sendError);
      try {
        setTestWhatsAppStatus('error');
        alert(`❌ Erreur technique: ${sendError.message}`);
        setTimeout(() => setTestWhatsAppStatus(null), 3000);
      } catch (e) {
        console.warn('PostHog bloqué mais erreur signalée:', e);
        alert(`❌ Erreur: ${sendError.message}`);
      }
    }
  };

  // Envoyer la campagne WhatsApp automatiquement - avec isolation PostHog
  const handleSendWhatsAppCampaign = async (e) => {
    // Empêcher le rafraîchissement et la propagation (isolation PostHog)
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    
    if (!isWhatsAppConfigured()) {
      alert('⚠️ WhatsApp API non configuré. Cliquez sur "⚙️ Config" pour ajouter vos clés Twilio.');
      return;
    }

    const contacts = getContactsForDirectSend();
    const phoneContacts = contacts
      .filter(c => c.phone)
      .map(c => ({ phone: c.phone, name: c.name }));

    if (phoneContacts.length === 0) {
      alert('Aucun contact avec numéro de téléphone');
      return;
    }

    if (!newCampaign.message.trim()) {
      alert('Veuillez saisir un message');
      return;
    }

    if (!window.confirm(`Envoyer ${phoneContacts.length} WhatsApp automatiquement ?\n\n⚠️ Cette action utilise votre quota Twilio et est irréversible.`)) {
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
      
      // Notification de succès
      if (results.sent > 0) {
        alert(`✅ Campagne WhatsApp terminée !\n\n✓ Envoyés: ${results.sent}\n✗ Échoués: ${results.failed}`);
      } else {
        alert(`❌ Échec de la campagne WhatsApp.\n\nErreurs: ${results.errors.join('\n')}`);
      }
    } catch (error) {
      console.error('❌ WhatsApp campaign error:', error);
      setWhatsAppSendingProgress(null);
      alert(`❌ Erreur lors de l'envoi: ${error.message}`);
    }
  };

  // === ENVOI GROUPÉ (EMAIL + WHATSAPP) ===
  const handleBulkSendCampaign = async (e) => {
    // Protection PostHog - Empêcher la propagation d'événements
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

    // Resend est toujours configuré côté serveur
    const hasEmail = emailContacts.length > 0;
    const hasWhatsApp = isWhatsAppConfigured() && phoneContacts.length > 0;

    if (!hasEmail && !hasWhatsApp) {
      alert('⚠️ Aucun contact avec email ou téléphone disponible.');
      return;
    }

    if (!newCampaign.message.trim()) {
      alert('Veuillez saisir un message');
      return;
    }

    const channels = [];
    if (hasEmail) channels.push(`${emailContacts.length} emails`);
    if (hasWhatsApp) channels.push(`${phoneContacts.length} WhatsApp`);

    if (!window.confirm(`Envoi automatique :\n• ${channels.join('\n• ')}\n\n⚠️ Cette action est irréversible.`)) {
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

      // Notification de succès
      const emailSent = results.email?.sent || 0;
      const emailFailed = results.email?.failed || 0;
      const waSent = results.whatsapp?.sent || 0;
      const waFailed = results.whatsapp?.failed || 0;
      
      alert(`✅ Campagne terminée !\n\n📧 Emails: ${emailSent} envoyés, ${emailFailed} échoués\n📱 WhatsApp: ${waSent} envoyés, ${waFailed} échoués`);
    } catch (error) {
      console.error('❌ Bulk campaign error:', error);
      alert(`❌ Erreur lors de l'envoi: ${error.message}`);
    } finally {
      setBulkSendingProgress(null);
      setBulkSendingInProgress(false);
      setBulkSendingResults(results);
    }
    
    // Mettre à jour le dernier média envoyé pour l'IA
    if (newCampaign.mediaUrl) {
      setLastMediaUrlService(newCampaign.mediaUrl);
      // Aussi mettre à jour côté backend
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
      alert('✅ Configuration IA sauvegardée !');
    } catch (err) {
      alert('❌ Erreur lors de la sauvegarde');
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

  // v8.9.5: Tabs dynamiques avec "Mon Stripe" pour les coachs (pas Bassi)
  // v9.1.3: DASHBOARD JUMEAU - Tous les coaches ont FULL ACCESS (même interface que Bassi)
  // L'indicateur requiresCredits est supprimé - seul le filtrage coach_id sépare les données
  // v9.5.8: Masquer "Campagnes" pour les partenaires - réservé au Super Admin
  const baseTabs = [
    { id: "reservations", label: t('reservations') }, 
    { id: "concept", label: t('conceptVisual') },
    { id: "courses", label: t('courses') }, 
    { id: "offers", label: t('offers') },
    { id: "page-vente", label: "🏪 Ma Page" }, 
    { id: "codes", label: t('promoCodes') },
    // v9.5.8: Campagnes masqué pour les partenaires
    ...(isSuperAdmin ? [{ id: "campaigns", label: "📢 Campagnes" }] : []),
    { id: "conversations", label: unreadCount > 0 ? `💬 Conversations (${unreadCount})` : "💬 Conversations" }
  ];
  
  // Ajouter "Mon Stripe" pour les coachs partenaires (pas Bassi)
  const tabs = !isSuperAdmin 
    ? [...baseTabs, { id: "stripe", label: "💳 Mon Stripe" }]
    : baseTabs;

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
                Connecté en tant que <span className="text-purple-400">{displayEmail}</span>
              </span>
              {/* Badge par défaut */}
              <span 
                className="ml-2 px-3 py-1 rounded-full text-sm font-bold"
                style={{
                  background: isSuperAdmin 
                    ? 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.3))' 
                    : 'rgba(239,68,68,0.25)',
                  color: isSuperAdmin ? '#D91CD2' : '#ef4444',
                  border: `2px solid ${isSuperAdmin ? 'rgba(217,28,210,0.6)' : 'rgba(239,68,68,0.6)'}`
                }}
              >
                {isSuperAdmin ? '👑 Crédits Illimités' : '💰 Solde : 0 Crédit'}
              </span>
            </div>
          </div>
        </div>
        
        {/* Onglets squelette */}
        <div className="flex flex-wrap gap-2 mb-6">
          {['Réservations', 'Concept & Visuel', 'Cours', 'Offres', 'Paiements', 'Codes promo', 'Campagnes', 'Conversations'].map((tabName, i) => (
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
          <div className="text-4xl mb-4 animate-pulse">⏳</div>
          <h2 className="text-xl font-bold text-white mb-2">Initialisation de votre espace...</h2>
          <p className="text-white/60">Chargement de vos données en cours</p>
        </div>
      </div>
    </div>
  );

  // v9.2.5: Si le dashboard n'est pas prêt après 2 secondes, afficher le fallback
  // (Mais normalement dashboardReady passe à true après 100ms)
  
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

      {/* ========== MODAL GESTION AUDIO / PLAYLIST ========== */}
      {showAudioModal && selectedCourseForAudio && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.8)' }}>
          <div 
            className="glass rounded-xl p-6 w-full max-w-lg max-h-[80vh] overflow-y-auto"
            style={{ border: '1px solid rgba(217, 28, 210, 0.3)' }}
          >
            {/* Header */}
            <div className="flex justify-between items-start mb-6">
              <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  🎵 Gérer la Playlist
                </h2>
                <p className="text-white/60 text-sm mt-1">
                  Cours : <span className="text-purple-400">{selectedCourseForAudio.name}</span>
                </p>
              </div>
              <button 
                onClick={() => setShowAudioModal(false)}
                className="p-2 rounded-lg hover:bg-white/10 transition-colors"
                style={{ color: '#fff' }}
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                </svg>
              </button>
            </div>

            {/* Ajouter une URL */}
            <div className="mb-6">
              <label className="block text-white text-sm mb-2">Ajouter un morceau (URL MP3/Stream)</label>
              <div className="flex gap-2">
                <input
                  type="url"
                  value={newAudioUrl}
                  onChange={(e) => setNewAudioUrl(e.target.value)}
                  placeholder="https://example.com/music.mp3"
                  className="flex-1 px-3 py-2 rounded-lg neon-input text-sm"
                  onKeyPress={(e) => e.key === 'Enter' && addAudioUrl()}
                  data-testid="audio-url-input"
                />
                <button
                  onClick={addAudioUrl}
                  className="px-4 py-2 rounded-lg font-semibold text-sm transition-all"
                  style={{ 
                    background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                    color: '#fff'
                  }}
                  data-testid="add-audio-btn"
                >
                  + Ajouter
                </button>
              </div>
              <p className="text-white/40 text-xs mt-2">
                Formats supportés : MP3, WAV, OGG, streams M3U/M3U8, Soundcloud, Spotify
              </p>
            </div>

            {/* Liste de la playlist */}
            <div className="mb-6">
              <h3 className="text-white text-sm font-semibold mb-3">
                Playlist ({playlistUrls.length} morceaux)
              </h3>
              
              {playlistUrls.length === 0 ? (
                <div className="p-4 rounded-lg text-center" style={{ background: 'rgba(255,255,255,0.05)' }}>
                  <p className="text-white/40 text-sm">Aucun morceau dans la playlist</p>
                  <p className="text-white/30 text-xs mt-1">Ajoutez des URLs ci-dessus</p>
                </div>
              ) : (
                <div className="space-y-2 max-h-48 overflow-y-auto custom-scrollbar">
                  {playlistUrls.map((url, index) => (
                    <div 
                      key={index}
                      className="flex items-center gap-3 p-3 rounded-lg group"
                      style={{ background: 'rgba(255,255,255,0.05)' }}
                    >
                      <span className="text-purple-400 text-sm font-mono">#{index + 1}</span>
                      <span className="flex-1 text-white text-sm truncate" title={url}>
                        {url.length > 40 ? url.substring(0, 40) + '...' : url}
                      </span>
                      <button
                        onClick={() => removeAudioUrl(url)}
                        className="p-1 rounded hover:bg-red-500/30 transition-colors opacity-0 group-hover:opacity-100"
                        style={{ color: '#ef4444' }}
                        title="Supprimer ce morceau"
                        data-testid={`remove-audio-${index}`}
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Boutons d'action */}
            <div className="flex gap-3">
              <button
                onClick={() => setShowAudioModal(false)}
                className="flex-1 py-3 rounded-lg glass text-white text-sm"
              >
                Annuler
              </button>
              <button
                onClick={savePlaylist}
                disabled={savingPlaylist}
                className="flex-1 py-3 rounded-lg font-semibold text-sm transition-all"
                style={{ 
                  background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                  color: '#fff',
                  opacity: savingPlaylist ? 0.7 : 1
                }}
                data-testid="save-playlist-btn"
              >
                {savingPlaylist ? '⏳ Sauvegarde...' : '💾 Sauvegarder'}
              </button>
            </div>

            {/* Info */}
            <p className="text-white/30 text-xs text-center mt-4">
              Les morceaux seront liés au cours "{selectedCourseForAudio.name}" (ID: {selectedCourseForAudio.id})
            </p>
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

      {/* v9.5.7: BOUTON DÉCONNEXION FIXED - Toujours visible en haut à droite */}
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
        🚪 Déconnexion
      </button>

      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-8 flex-wrap gap-4">
          <div>
            {/* v9.1.3: Marque blanche - Affiche platform_name ou "Mon Espace Afroboost" */}
            <h1 className="font-bold text-white" style={{ fontSize: '28px' }} data-testid="dashboard-title">
              {dashboardTitle}
            </h1>
            {/* Affichage de l'utilisateur connecté via Google OAuth */}
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
                  Connecté en tant que <span className="text-purple-400">{coachUser.email}</span>
                </span>
                {/* === v9.5.9: JAUGE DE CRÉDITS VISUELLE - Barre de progression élégante === */}
                {!isSuperAdmin && (
                  <div className="flex items-center gap-2 flex-wrap">
                    {/* Badge avec nombre de crédits */}
                    <div 
                      className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                      style={{
                        background: coachCredits <= 0 ? 'rgba(239,68,68,0.15)' : 'rgba(217,28,210,0.15)',
                        border: coachCredits <= 0 ? '1px solid rgba(239,68,68,0.4)' : '1px solid rgba(217,28,210,0.4)'
                      }}
                      data-testid="coach-credits-badge"
                    >
                      <span style={{ color: coachCredits <= 0 ? '#ef4444' : '#D91CD2' }}>💰</span>
                      <div className="flex flex-col">
                        <span 
                          className="text-xs font-bold"
                          style={{ color: coachCredits <= 0 ? '#ef4444' : '#D91CD2' }}
                        >
                          {coachCredits <= 0 ? '0' : coachCredits} Crédit{coachCredits !== 1 ? 's' : ''}
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
                        🛒 Acheter
                      </button>
                    )}
                  </div>
                )}
                {/* v9.5.9: Super Admin - Badge Illimité ♾️ */}
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
                    <span>👑</span> Crédits : Illimités ♾️
                  </span>
                )}
              </div>
            )}
          </div>
          {/* v10.5: Conteneur boutons harmonisé - Flexbox avec gap uniforme */}
          <div className="flex flex-wrap gap-3 items-center justify-center sm:justify-end">
            {/* === v9.2.7: QUICK CONTROL - Icône minimaliste Super Admin === */}
            {isSuperAdmin && (
              <div className="relative" ref={quickControlRef}>
                <button 
                  onClick={() => setShowQuickControl(!showQuickControl)}
                  title="Quick Control"
                  className="w-10 h-10 rounded-full flex items-center justify-center transition-all duration-200"
                  style={{ 
                    background: showQuickControl 
                      ? 'linear-gradient(135deg, rgba(217,28,210,0.4), rgba(139,92,246,0.4))' 
                      : 'rgba(255,255,255,0.08)',
                    border: showQuickControl ? '1px solid rgba(217,28,210,0.6)' : '1px solid rgba(255,255,255,0.1)'
                  }}
                  data-testid="quick-control-btn"
                >
                  {/* Icône 3 points verticaux style premium */}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <circle cx="12" cy="5" r="1.5" fill="currentColor" />
                    <circle cx="12" cy="12" r="1.5" fill="currentColor" />
                    <circle cx="12" cy="19" r="1.5" fill="currentColor" />
                  </svg>
                </button>
                
                {/* Menu Quick Control */}
                {showQuickControl && (
                  <div 
                    className="absolute right-0 mt-2 w-64 rounded-xl overflow-hidden z-50"
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
                    
                    {/* Toggle: Accès Partenaires */}
                    <div className="px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors">
                      <div className="flex items-center gap-3">
                        <span className="text-lg">{platformSettings.partner_access_enabled ? '🟢' : '🔴'}</span>
                        <div>
                          <p className="text-sm text-white font-medium">Accès Partenaires</p>
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
                    <div 
                      className="px-4 py-3 flex items-center justify-between hover:bg-white/5 transition-colors"
                      style={{ maxWidth: '100%' }}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-lg">{platformSettings.maintenance_mode ? '🔴' : '🟢'}</span>
                        <div>
                          <p className="text-sm text-white font-medium">Mode Maintenance</p>
                          <p className="text-xs text-white/40">Bloquer tout accès</p>
                        </div>
                      </div>
                      <button
                        onClick={() => togglePlatformSetting('maintenance_mode')}
                        className="w-12 h-7 rounded-full relative transition-all duration-300"
                        style={{ 
                          background: platformSettings.maintenance_mode 
                            ? 'linear-gradient(90deg, #D91CD2, #8b5cf6)' 
                            : 'rgba(255,255,255,0.15)',
                          boxShadow: platformSettings.maintenance_mode 
                            ? '0 0 15px rgba(217, 28, 210, 0.6), 0 0 30px rgba(217, 28, 210, 0.3)' 
                            : 'none'
                        }}
                        data-testid="toggle-maintenance"
                      >
                        <span 
                          className="absolute top-1 w-5 h-5 rounded-full bg-white shadow-md transition-all duration-300"
                          style={{ left: platformSettings.maintenance_mode ? '26px' : '4px' }}
                        />
                      </button>
                    </div>
                    
                    {/* Separator */}
                    <div className="border-t mx-3" style={{ borderColor: 'rgba(255,255,255,0.1)' }} />
                    
                    {/* Info */}
                    <div className="px-4 py-2">
                      <p className="text-[10px] text-white/30 text-center">
                        Contrôles instantanés • Super Admin
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}
            
            {/* === BOUTON SUPER ADMIN (visible uniquement pour Bassi) === */}
            {isSuperAdmin && (
              <button 
                onClick={() => setShowAdminPanel(true)}
                title="Panneau Super Admin"
                className="h-10 px-4 rounded-lg text-white text-sm font-medium flex items-center gap-2 transition-all hover:scale-105"
                style={{ 
                  background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                  border: '1px solid rgba(217, 28, 210, 0.4)',
                  boxShadow: '0 0 10px rgba(217, 28, 210, 0.3)'
                }}
                data-testid="super-admin-btn"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 2L9 9l-7 2 5 5-1 7 6-3 6 3-1-7 5-5-7-2-3-7z" />
                </svg>
                Admin
              </button>
            )}
            {/* === BOUTON STRIPE CONNECT (visible uniquement pour les coachs, pas Bassi) v8.9.3 === */}
            {!isSuperAdmin && (
              <button 
                onClick={handleStripeConnect}
                disabled={stripeConnectLoading}
                title={stripeConnectStatus?.connected ? "Compte Stripe connecté" : "Connecter votre Stripe"}
                className="h-10 px-4 rounded-lg text-white text-sm font-medium flex items-center gap-2 transition-all hover:scale-105"
                style={{ 
                  background: stripeConnectStatus?.connected 
                    ? 'rgba(34, 197, 94, 0.3)' 
                    : 'linear-gradient(135deg, #635BFF, #8b5cf6)',
                  border: stripeConnectStatus?.connected ? '1px solid rgba(34, 197, 94, 0.5)' : 'none',
                  opacity: stripeConnectLoading ? 0.7 : 1
                }}
                data-testid="stripe-connect-btn"
              >
                {stripeConnectLoading ? (
                  <span className="animate-pulse">...</span>
                ) : stripeConnectStatus?.connected ? (
                  <>
                    <span style={{ color: '#22c55e' }}>✓</span>
                    Stripe OK
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 8.25h19.5M2.25 9h19.5m-16.5 5.25h6m-6 2.25h3m-3.75 3h15a2.25 2.25 0 002.25-2.25V6.75A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25v10.5A2.25 2.25 0 004.5 19.5z" />
                    </svg>
                    Connecter Stripe
                  </>
                )}
              </button>
            )}
            {/* === ICÔNE PARTAGE COACH === */}
            <button 
              onClick={handleCoachShareLink}
              title={linkCopied ? "Lien copié !" : "Partager le site"}
              className="h-10 px-4 rounded-lg text-white text-sm font-medium flex items-center gap-2 transition-all hover:scale-105"
              style={{ 
                background: linkCopied 
                  ? 'rgba(34, 197, 94, 0.4)' 
                  : 'rgba(255,255,255,0.1)',
                border: linkCopied 
                  ? '1px solid rgba(34, 197, 94, 0.5)' 
                  : '1px solid rgba(255,255,255,0.2)',
                boxShadow: linkCopied ? '0 0 10px rgba(34, 197, 94, 0.3)' : 'none'
              }}
              data-testid="coach-share"
            >
              {linkCopied ? (
                <span style={{ color: '#22c55e' }}>✓ Copié</span>
              ) : (
                <>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="18" cy="5" r="3"></circle>
                    <circle cx="6" cy="12" r="3"></circle>
                    <circle cx="18" cy="19" r="3"></circle>
                    <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
                    <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
                  </svg>
                  Partager
                </>
              )}
            </button>
            <button 
              onClick={onBack} 
              className="h-10 px-4 rounded-lg text-white text-sm font-medium flex items-center gap-2 transition-all hover:scale-105"
              style={{ 
                background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.6), rgba(217, 28, 210, 0.4))',
                border: '1px solid rgba(217, 28, 210, 0.3)',
                boxShadow: '0 0 10px rgba(217, 28, 210, 0.2)'
              }}
              data-testid="coach-back"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7"/>
              </svg>
              {t('back')}
            </button>
            {/* v9.5.8: Bouton déconnexion supprimé ici - existe en position fixed en haut à droite */}
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
          
          {/* Bouton Vue Visiteur - Toggle mode apercu */}
          <button
            onClick={toggleVisitorPreview}
            className="ml-auto px-3 py-2 rounded-lg text-xs sm:text-sm flex items-center gap-2 flex-shrink-0"
            style={{
              background: isVisitorPreviewActive ? 'rgba(147, 51, 234, 0.3)' : 'rgba(255,255,255,0.1)',
              border: isVisitorPreviewActive ? '1px solid rgba(147, 51, 234, 0.5)' : '1px solid rgba(255,255,255,0.2)',
              color: isVisitorPreviewActive ? '#a855f7' : 'white'
            }}
            data-testid="coach-visitor-preview-toggle"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
              <circle cx="12" cy="12" r="3"></circle>
            </svg>
            {isVisitorPreviewActive ? 'Apercu actif' : 'Vue Visiteur'}
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

        {/* Concept Tab */}
        {tab === "concept" && (
          <div className="card-gradient rounded-xl p-6">
            {/* v9.3.7: Indicateur de sauvegarde automatique */}
            <div className="flex items-center justify-between mb-6">
              <h2 className="font-semibold text-white" style={{ fontSize: '20px' }}>{t('conceptVisual')}</h2>
              {conceptSaveStatus && (
                <span 
                  className="px-3 py-1 rounded-full text-xs font-medium flex items-center gap-2"
                  style={{
                    background: conceptSaveStatus === 'saved' ? 'rgba(34, 197, 94, 0.2)' : 
                               conceptSaveStatus === 'error' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(147, 51, 234, 0.2)',
                    color: conceptSaveStatus === 'saved' ? '#22c55e' : 
                           conceptSaveStatus === 'error' ? '#ef4444' : '#a855f7',
                    border: `1px solid ${conceptSaveStatus === 'saved' ? 'rgba(34, 197, 94, 0.3)' : 
                            conceptSaveStatus === 'error' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(147, 51, 234, 0.3)'}`
                  }}
                  data-testid="concept-save-status"
                >
                  {conceptSaveStatus === 'saving' && <><span className="animate-spin">⏳</span> Sauvegarde...</>}
                  {conceptSaveStatus === 'saved' && <>✓ Sauvegardé</>}
                  {conceptSaveStatus === 'error' && <>⚠️ Erreur</>}
                </span>
              )}
            </div>
            <div className="space-y-4">
              
              {/* ========================= PERSONNALISATION DES COULEURS ========================= */}
              <div className="border border-purple-500/30 rounded-lg p-4 bg-purple-900/10">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-purple-400 font-semibold">🎨 Personnalisation des couleurs</h3>
                  {/* v9.5.1: Bouton de sauvegarde manuelle */}
                  <button
                    onClick={saveConcept}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:scale-105"
                    style={{
                      background: 'linear-gradient(135deg, var(--primary-color, #D91CD2), var(--secondary-color, #8b5cf6))',
                      color: 'white'
                    }}
                    data-testid="save-colors-btn"
                  >
                    💾 Sauvegarder
                  </button>
                </div>
                <p className="text-white/60 text-xs mb-4">Les modifications s'appliquent en temps réel et sont auto-sauvegardées après 1 seconde.</p>
                
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {/* Couleur principale */}
                  <div>
                    <label className="block mb-2 text-white text-sm">✨ Couleur principale (Boutons/Titres)</label>
                    <div className="flex items-center gap-3">
                      <input 
                        type="color" 
                        value={concept.primaryColor || '#D91CD2'} 
                        onChange={(e) => {
                          const newColor = e.target.value;
                          setConcept({ ...concept, primaryColor: newColor });
                          document.documentElement.style.setProperty('--primary-color', newColor);
                          // Auto-glow si pas de glowColor défini
                          if (!concept.glowColor) {
                            document.documentElement.style.setProperty('--glow-color', `${newColor}66`);
                            document.documentElement.style.setProperty('--glow-color-strong', `${newColor}99`);
                          }
                        }}
                        className="w-12 h-12 rounded-lg cursor-pointer border-2 border-white/20"
                        style={{ background: 'transparent' }}
                        data-testid="color-picker-primary"
                      />
                      <div>
                        <input 
                          type="text" 
                          value={concept.primaryColor || '#D91CD2'} 
                          onChange={(e) => {
                            const newColor = e.target.value;
                            if (/^#[0-9A-Fa-f]{6}$/.test(newColor)) {
                              setConcept({ ...concept, primaryColor: newColor });
                              document.documentElement.style.setProperty('--primary-color', newColor);
                              if (!concept.glowColor) {
                                document.documentElement.style.setProperty('--glow-color', `${newColor}66`);
                              }
                            }
                          }}
                          className="px-3 py-2 rounded-lg neon-input text-sm uppercase w-28"
                          placeholder="#D91CD2"
                        />
                        <p className="text-xs mt-1 text-white/40">Rose par défaut</p>
                      </div>
                    </div>
                  </div>
                  
                  {/* Couleur secondaire */}
                  <div>
                    <label className="block mb-2 text-white text-sm">💜 Couleur secondaire (Accents)</label>
                    <div className="flex items-center gap-3">
                      <input 
                        type="color" 
                        value={concept.secondaryColor || '#8b5cf6'} 
                        onChange={(e) => {
                          const newColor = e.target.value;
                          setConcept({ ...concept, secondaryColor: newColor });
                          document.documentElement.style.setProperty('--secondary-color', newColor);
                        }}
                        className="w-12 h-12 rounded-lg cursor-pointer border-2 border-white/20"
                        style={{ background: 'transparent' }}
                        data-testid="color-picker-secondary"
                      />
                      <div>
                        <input 
                          type="text" 
                          value={concept.secondaryColor || '#8b5cf6'} 
                          onChange={(e) => {
                            const newColor = e.target.value;
                            if (/^#[0-9A-Fa-f]{6}$/.test(newColor)) {
                              setConcept({ ...concept, secondaryColor: newColor });
                              document.documentElement.style.setProperty('--secondary-color', newColor);
                            }
                          }}
                          className="px-3 py-2 rounded-lg neon-input text-sm uppercase w-28"
                          placeholder="#8b5cf6"
                        />
                        <p className="text-xs mt-1 text-white/40">Violet par défaut</p>
                      </div>
                    </div>
                  </div>
                  
                  {/* v9.4.4: Couleur de fond */}
                  <div>
                    <label className="block mb-2 text-white text-sm">🌑 Couleur de fond (Background)</label>
                    <div className="flex items-center gap-3">
                      <input 
                        type="color" 
                        value={concept.backgroundColor || '#000000'} 
                        onChange={(e) => {
                          const newColor = e.target.value;
                          setConcept({ ...concept, backgroundColor: newColor });
                          document.documentElement.style.setProperty('--background-color', newColor);
                          document.body.style.backgroundColor = newColor;
                        }}
                        className="w-12 h-12 rounded-lg cursor-pointer border-2 border-white/20"
                        style={{ background: 'transparent' }}
                        data-testid="color-picker-background"
                      />
                      <div>
                        <input 
                          type="text" 
                          value={concept.backgroundColor || '#000000'} 
                          onChange={(e) => {
                            const newColor = e.target.value;
                            if (/^#[0-9A-Fa-f]{6}$/.test(newColor)) {
                              setConcept({ ...concept, backgroundColor: newColor });
                              document.documentElement.style.setProperty('--background-color', newColor);
                              document.body.style.backgroundColor = newColor;
                            }
                          }}
                          className="px-3 py-2 rounded-lg neon-input text-sm uppercase w-28"
                          placeholder="#000000"
                        />
                        <p className="text-xs mt-1 text-white/40">Noir par défaut</p>
                      </div>
                    </div>
                  </div>
                  
                  {/* v9.4.4: Couleur du Glow */}
                  <div>
                    <label className="block mb-2 text-white text-sm">✨ Couleur du Glow (Lueurs)</label>
                    <div className="flex items-center gap-3">
                      <input 
                        type="color" 
                        value={concept.glowColor || concept.primaryColor || '#D91CD2'} 
                        onChange={(e) => {
                          const newColor = e.target.value;
                          setConcept({ ...concept, glowColor: newColor });
                          document.documentElement.style.setProperty('--glow-color', `${newColor}66`);
                          document.documentElement.style.setProperty('--glow-color-strong', `${newColor}99`);
                        }}
                        className="w-12 h-12 rounded-lg cursor-pointer border-2 border-white/20"
                        style={{ background: 'transparent' }}
                        data-testid="color-picker-glow"
                      />
                      <div>
                        <input 
                          type="text" 
                          value={concept.glowColor || concept.primaryColor || '#D91CD2'} 
                          onChange={(e) => {
                            const newColor = e.target.value;
                            if (/^#[0-9A-Fa-f]{6}$/.test(newColor)) {
                              setConcept({ ...concept, glowColor: newColor });
                              document.documentElement.style.setProperty('--glow-color', `${newColor}66`);
                              document.documentElement.style.setProperty('--glow-color-strong', `${newColor}99`);
                            }
                          }}
                          className="px-3 py-2 rounded-lg neon-input text-sm uppercase w-28"
                          placeholder="#D91CD2"
                        />
                        <p className="text-xs mt-1 text-white/40">Auto si vide</p>
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Présets de couleurs - v9.4.4: Incluant fond et glow */}
                <div className="mt-4">
                  <label className="block mb-2 text-white text-sm">🎯 Préréglages rapides</label>
                  <div className="flex flex-wrap gap-2">
                    {[
                      { name: 'Afroboost Classic', primary: '#D91CD2', secondary: '#8b5cf6', bg: '#000000', glow: '#D91CD2' },
                      { name: 'Blanc Élégant', primary: '#9333ea', secondary: '#6366f1', bg: '#ffffff', glow: '#9333ea' },
                      { name: 'Bleu Ocean', primary: '#0ea5e9', secondary: '#6366f1', bg: '#0a1628', glow: '#0ea5e9' },
                      { name: 'Or Luxe', primary: '#d4af37', secondary: '#b8860b', bg: '#1a1a0a', glow: '#d4af37' },
                      { name: 'Vert Nature', primary: '#10b981', secondary: '#14b8a6', bg: '#0a1a0f', glow: '#10b981' },
                      { name: 'Rouge Passion', primary: '#ef4444', secondary: '#ec4899', bg: '#1a0a0a', glow: '#ef4444' },
                    ].map((preset) => (
                      <button
                        key={preset.name}
                        onClick={() => {
                          setConcept({ 
                            ...concept, 
                            primaryColor: preset.primary, 
                            secondaryColor: preset.secondary,
                            backgroundColor: preset.bg,
                            glowColor: preset.glow
                          });
                          document.documentElement.style.setProperty('--primary-color', preset.primary);
                          document.documentElement.style.setProperty('--secondary-color', preset.secondary);
                          document.documentElement.style.setProperty('--background-color', preset.bg);
                          document.documentElement.style.setProperty('--glow-color', `${preset.glow}66`);
                          document.documentElement.style.setProperty('--glow-color-strong', `${preset.glow}99`);
                          document.body.style.backgroundColor = preset.bg;
                        }}
                        className="px-3 py-2 rounded-full text-xs font-medium transition-all hover:scale-105"
                        style={{ 
                          background: `linear-gradient(135deg, ${preset.primary}, ${preset.secondary})`,
                          boxShadow: `0 2px 10px ${preset.primary}40`,
                          color: preset.bg === '#ffffff' ? '#000' : '#fff'
                        }}
                        data-testid={`preset-${preset.name.toLowerCase().replace(/\s/g, '-')}`}
                      >
                        {preset.name}
                      </button>
                    ))}
                  </div>
                </div>
                
                {/* Bouton reset */}
                <button
                  onClick={() => {
                    setConcept({ 
                      ...concept, 
                      primaryColor: '#D91CD2', 
                      secondaryColor: '#8b5cf6',
                      backgroundColor: '#000000',
                      glowColor: ''
                    });
                    document.documentElement.style.setProperty('--primary-color', '#D91CD2');
                    document.documentElement.style.setProperty('--secondary-color', '#8b5cf6');
                    document.documentElement.style.setProperty('--background-color', '#000000');
                    document.documentElement.style.setProperty('--glow-color', 'rgba(217, 28, 210, 0.4)');
                    document.documentElement.style.setProperty('--glow-color-strong', 'rgba(217, 28, 210, 0.6)');
                    document.body.style.backgroundColor = '#000000';
                  }}
                  className="mt-4 px-4 py-2 rounded-lg text-sm text-white/70 hover:text-white border border-white/20 hover:border-white/40 transition-all"
                  data-testid="reset-colors-btn"
                >
                  🔄 Réinitialiser les couleurs par défaut
                </button>
              </div>
              
              {/* ========================= IDENTITÉ DE L'APPLICATION ========================= */}
              <div className="border border-pink-500/30 rounded-lg p-4 bg-pink-900/10">
                <h3 className="text-pink-400 font-semibold mb-4">🎨 Identité de l'application</h3>
                
                {/* Nom de l'application */}
                <div className="mb-4">
                  <label className="block mb-2 text-white text-sm">📝 Nom de l'application</label>
                  <input 
                    type="text" 
                    value={concept.appName || 'Afroboost'} 
                    onChange={(e) => setConcept({ ...concept, appName: e.target.value })}
                    className="w-full px-4 py-3 rounded-lg neon-input" 
                    placeholder="Afroboost" 
                    data-testid="concept-app-name" 
                  />
                  <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    Ce nom apparaît comme titre principal en haut du site
                  </p>
                </div>
                
                {/* Logo URL for Splash Screen & PWA */}
                <div>
                  <label className="block mb-2 text-white text-sm">🖼️ URL du Logo (Splash Screen & PWA)</label>
                  <input 
                    type="url" 
                    value={concept.logoUrl || ''} 
                    onChange={(e) => setConcept({ ...concept, logoUrl: e.target.value })}
                    className="w-full px-4 py-3 rounded-lg neon-input" 
                    placeholder="https://... (logo PNG/SVG)" 
                    data-testid="concept-logo-url" 
                  />
                  <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>
                    Ce logo apparaît sur le Splash Screen et comme icône d'installation mobile (PWA)
                  </p>
                </div>
                {concept.logoUrl && (
                  <div className="mt-3">
                    <p className="text-white text-sm mb-2" style={{ opacity: 0.7 }}>Aperçu logo:</p>
                    <div className="flex justify-center p-4 rounded-lg" style={{ background: '#000' }}>
                      <img src={concept.logoUrl} alt="Logo" style={{ maxHeight: '80px', maxWidth: '200px' }} />
                    </div>
                  </div>
                )}
              </div>
              
              {/* ========================= DESCRIPTION DU CONCEPT ========================= */}
              <div>
                <label className="block mb-2 text-white text-sm">{t('conceptDescription')}</label>
                <textarea value={concept.description} onChange={(e) => setConcept({ ...concept, description: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg neon-input" rows={4} data-testid="concept-description" 
                  placeholder="Décrivez votre concept..." />
              </div>
              
              {/* ========================= v9.5.0: LIEN VIDÉO SIMPLIFIÉ ========================= */}
              <div className="border border-pink-500/30 rounded-lg p-4 bg-pink-900/10">
                <h3 className="text-pink-400 font-semibold mb-2 flex items-center gap-2">
                  🎬 Lien de votre vidéo (YouTube ou MP4 direct)
                </h3>
                <p className="text-white/60 text-xs mb-3">
                  Cette vidéo s'affichera dans le flux vertical pour tous les membres. Copiez simplement le lien YouTube ou l'URL de votre fichier vidéo.
                </p>
                <div className="relative">
                  <input 
                    type="url" 
                    value={concept.heroImageUrl} 
                    onChange={(e) => setConcept({ ...concept, heroImageUrl: e.target.value })}
                    className="w-full px-4 py-3 rounded-lg neon-input pr-24" 
                    placeholder="https://youtube.com/watch?v=... ou https://mon-site.com/video.mp4" 
                    data-testid="concept-video-url" 
                  />
                  {/* Badge de validation d'URL */}
                  {concept.heroImageUrl && concept.heroImageUrl.trim() !== '' && (
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs px-2 py-1 rounded" style={{
                      background: (() => {
                        const url = concept.heroImageUrl.toLowerCase();
                        const isValid = url.includes('youtube.com') || url.includes('youtu.be') || 
                                        url.includes('vimeo.com') || 
                                        url.match(/\.(mp4|webm|mov|avi|m4v)(\?|$)/i) ||
                                        url.endsWith('.jpg') || url.endsWith('.jpeg') || 
                                        url.endsWith('.png') || url.endsWith('.webp') || url.endsWith('.gif') ||
                                        url.includes('unsplash.com') || url.includes('pexels.com');
                        return isValid ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)';
                      })(),
                      color: (() => {
                        const url = concept.heroImageUrl.toLowerCase();
                        const isValid = url.includes('youtube.com') || url.includes('youtu.be') || 
                                        url.includes('vimeo.com') || 
                                        url.match(/\.(mp4|webm|mov|avi|m4v)(\?|$)/i) ||
                                        url.endsWith('.jpg') || url.endsWith('.jpeg') || 
                                        url.endsWith('.png') || url.endsWith('.webp') || url.endsWith('.gif') ||
                                        url.includes('unsplash.com') || url.includes('pexels.com');
                        return isValid ? '#22c55e' : '#ef4444';
                      })()
                    }}>
                      {(() => {
                        const url = concept.heroImageUrl.toLowerCase();
                        if (url.includes('youtube.com') || url.includes('youtu.be')) return '✓ YouTube';
                        if (url.includes('vimeo.com')) return '✓ Vimeo';
                        if (url.match(/\.(mp4|webm|mov|avi|m4v)(\?|$)/i)) return '✓ Vidéo';
                        if (url.match(/\.(jpg|jpeg|png|webp|gif)(\?|$)/i)) return '✓ Image';
                        return '✗ Format inconnu';
                      })()}
                    </span>
                  )}
                </div>
                <p className="text-xs mt-2" style={{ color: 'rgba(255,255,255,0.5)' }}>
                  💡 <strong>Astuce:</strong> YouTube Shorts fonctionne aussi ! Copiez simplement le lien.
                </p>
              </div>
              
              {concept.heroImageUrl && (
                <div className="mt-4">
                  <p className="text-white text-sm mb-2" style={{ opacity: 0.7 }}>Aperçu média (format 16:9):</p>
                  <MediaDisplay url={concept.heroImageUrl} className="rounded-lg overflow-hidden" />
                </div>
              )}
              {/* Favicon URL - Icône de l'onglet navigateur */}
              <div>
                <label className="block mb-2 text-white text-sm">URL du Favicon (icône onglet navigateur)</label>
                <input type="url" value={concept.faviconUrl || ''} onChange={(e) => setConcept({ ...concept, faviconUrl: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg neon-input" placeholder="https://... (favicon .ico/.png)" data-testid="concept-favicon-url" />
                <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>Cette icône apparaît dans l'onglet du navigateur</p>
              </div>
              {concept.faviconUrl && (
                <div className="mt-2">
                  <p className="text-white text-sm mb-2" style={{ opacity: 0.7 }}>Aperçu favicon:</p>
                  <div className="flex items-center gap-3 p-3 rounded-lg" style={{ background: '#1a1a2e' }}>
                    <img src={concept.faviconUrl} alt="Favicon" style={{ width: '32px', height: '32px' }} onError={(e) => { e.target.style.display = 'none'; }} />
                    <span className="text-white text-sm opacity-70">{concept.appName || 'Afroboost'}</span>
                  </div>
                </div>
              )}

              {/* CGV - Conditions Générales de Vente */}
              <div className="mt-6 pt-6 border-t border-purple-500/30">
                <label className="block mb-2 text-white text-sm">{t('termsText') || 'Texte des Conditions Générales'}</label>
                <textarea 
                  value={concept.termsText || ''} 
                  onChange={(e) => setConcept({ ...concept, termsText: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg neon-input" 
                  rows={8}
                  placeholder={t('termsPlaceholder') || 'Entrez le texte de vos conditions générales de vente...'}
                  data-testid="concept-terms-text"
                />
                <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Ce texte s'affichera dans la fenêtre modale "Conditions générales" accessible depuis le formulaire de réservation.
                </p>
              </div>

              {/* Lien Avis Google */}
              <div className="mt-6 pt-6 border-t border-purple-500/30">
                <label className="block mb-2 text-white text-sm">⭐ Lien des avis Google</label>
                <input 
                  type="url" 
                  value={concept.googleReviewsUrl || ''} 
                  onChange={(e) => setConcept({ ...concept, googleReviewsUrl: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg neon-input" 
                  placeholder="https://g.page/r/..."
                  data-testid="concept-google-reviews-url"
                />
                <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Ce lien s'affichera comme bouton "Voir les avis" côté client, entre les offres et le formulaire.
                </p>
                {concept.googleReviewsUrl && (
                  <div className="mt-2 flex items-center gap-2">
                    <span className="text-green-400 text-xs">✓ Lien configuré</span>
                    <a 
                      href={concept.googleReviewsUrl} 
                      target="_blank" 
                      rel="noopener noreferrer" 
                      className="text-xs text-pink-400 hover:text-pink-300 underline"
                    >
                      Tester le lien
                    </a>
                  </div>
                )}
              </div>

              {/* Section d'atterrissage par défaut */}
              <div className="mt-6 pt-6 border-t border-purple-500/30">
                <LandingSectionSelector 
                  value={concept.defaultLandingSection || 'sessions'}
                  onChange={(value) => setConcept({ ...concept, defaultLandingSection: value })}
                />
              </div>

              {/* Liens Externes */}
              <div className="mt-6 pt-6 border-t border-purple-500/30">
                <h3 className="text-white text-sm font-semibold mb-4">🔗 Liens Externes (affichés en bas de page)</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                  <div>
                    <label className="block mb-1 text-white text-xs opacity-70">Titre du lien 1</label>
                    <input 
                      type="text" 
                      value={concept.externalLink1Title || ''} 
                      onChange={(e) => setConcept({ ...concept, externalLink1Title: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                      placeholder="Ex: Instagram"
                      data-testid="external-link1-title"
                    />
                  </div>
                  <div>
                    <label className="block mb-1 text-white text-xs opacity-70">URL du lien 1</label>
                    <input 
                      type="url" 
                      value={concept.externalLink1Url || ''} 
                      onChange={(e) => setConcept({ ...concept, externalLink1Url: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                      placeholder="https://..."
                      data-testid="external-link1-url"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block mb-1 text-white text-xs opacity-70">Titre du lien 2</label>
                    <input 
                      type="text" 
                      value={concept.externalLink2Title || ''} 
                      onChange={(e) => setConcept({ ...concept, externalLink2Title: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                      placeholder="Ex: Facebook"
                      data-testid="external-link2-title"
                    />
                  </div>
                  <div>
                    <label className="block mb-1 text-white text-xs opacity-70">URL du lien 2</label>
                    <input 
                      type="url" 
                      value={concept.externalLink2Url || ''} 
                      onChange={(e) => setConcept({ ...concept, externalLink2Url: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                      placeholder="https://..."
                      data-testid="external-link2-url"
                    />
                  </div>
                </div>
              </div>

              {/* Modes de paiement acceptés - Toggles */}
              <div className="mt-6 pt-6 border-t border-purple-500/30">
                <h3 className="text-white text-sm font-semibold mb-4">💳 Logos de paiement</h3>
                <p className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Activez les logos qui s'afficheront dans le pied de page.
                </p>
                <div className="space-y-3">
                  {/* Toggle Twint */}
                  <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
                    <div className="flex items-center gap-3">
                      <div style={{ 
                        background: '#00A9E0', 
                        borderRadius: '4px', 
                        padding: '2px 6px',
                        display: 'flex',
                        alignItems: 'center'
                      }}>
                        <span style={{ color: 'white', fontWeight: 'bold', fontSize: '12px' }}>TWINT</span>
                      </div>
                      <span className="text-white text-sm">Twint</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setConcept({ ...concept, paymentTwint: !concept.paymentTwint })}
                      className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.paymentTwint ? 'bg-pink-500' : 'bg-gray-600'}`}
                      data-testid="toggle-twint"
                    >
                      <span 
                        className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.paymentTwint ? 'left-7' : 'left-1'}`}
                      />
                    </button>
                  </div>
                  
                  {/* Toggle PayPal */}
                  <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
                    <div className="flex items-center gap-3">
                      <img 
                        src="https://upload.wikimedia.org/wikipedia/commons/b/b5/PayPal.svg" 
                        alt="PayPal" 
                        style={{ height: '18px' }}
                        onError={(e) => { e.target.src = ''; e.target.alt = 'PayPal'; }}
                      />
                      <span className="text-white text-sm">PayPal</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setConcept({ ...concept, paymentPaypal: !concept.paymentPaypal })}
                      className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.paymentPaypal ? 'bg-pink-500' : 'bg-gray-600'}`}
                      data-testid="toggle-paypal"
                    >
                      <span 
                        className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.paymentPaypal ? 'left-7' : 'left-1'}`}
                      />
                    </button>
                  </div>
                  
                  {/* Toggle Carte de Crédit */}
                  <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1">
                        <img 
                          src="https://upload.wikimedia.org/wikipedia/commons/5/5e/Visa_Inc._logo.svg" 
                          alt="Visa" 
                          style={{ height: '14px' }}
                          onError={(e) => { e.target.style.display = 'none'; }}
                        />
                        <img 
                          src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Mastercard-logo.svg" 
                          alt="Mastercard" 
                          style={{ height: '16px' }}
                          onError={(e) => { e.target.style.display = 'none'; }}
                        />
                      </div>
                      <span className="text-white text-sm">Carte de Crédit</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setConcept({ ...concept, paymentCreditCard: !concept.paymentCreditCard })}
                      className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.paymentCreditCard ? 'bg-pink-500' : 'bg-gray-600'}`}
                      data-testid="toggle-creditcard"
                    >
                      <span 
                        className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.paymentCreditCard ? 'left-7' : 'left-1'}`}
                      />
                    </button>
                  </div>
                </div>
              </div>

              {/* Affiche Événement (Popup) */}
              <div className="mt-6 pt-6 border-t border-purple-500/30">
                <h3 className="text-white text-sm font-semibold mb-4">🎉 Affiche Événement (Popup d'accueil)</h3>
                <p className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.4)' }}>
                  Affichez une image ou vidéo en popup dès l'arrivée des visiteurs.
                </p>
                
                {/* Toggle Activer/Désactiver */}
                <div className="flex items-center justify-between p-3 rounded-lg mb-4" style={{ background: 'rgba(139, 92, 246, 0.1)' }}>
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">📢</span>
                    <span className="text-white text-sm">Activer l'affiche événement</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setConcept({ ...concept, eventPosterEnabled: !concept.eventPosterEnabled })}
                    className={`relative w-12 h-6 rounded-full transition-all duration-300 ${concept.eventPosterEnabled ? 'bg-pink-500' : 'bg-gray-600'}`}
                    data-testid="toggle-event-poster"
                  >
                    <span 
                      className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-all duration-300 ${concept.eventPosterEnabled ? 'left-7' : 'left-1'}`}
                    />
                  </button>
                </div>
                
                {/* URL du média (visible seulement si activé) */}
                {concept.eventPosterEnabled && (
                  <div className="space-y-3">
                    <div>
                      <label className="block mb-1 text-white text-xs opacity-70">URL de l'image ou vidéo</label>
                      <input 
                        type="url" 
                        value={concept.eventPosterMediaUrl || ''} 
                        onChange={(e) => setConcept({ ...concept, eventPosterMediaUrl: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                        placeholder="https://... (image ou vidéo YouTube/Vimeo)"
                        data-testid="event-poster-url"
                      />
                    </div>
                    
                    {/* Aperçu du média */}
                    {concept.eventPosterMediaUrl && (
                      <div className="mt-3">
                        <label className="block mb-2 text-white text-xs opacity-70">Aperçu :</label>
                        <div className="rounded-lg overflow-hidden border border-purple-500/30" style={{ maxWidth: '300px' }}>
                          {concept.eventPosterMediaUrl.includes('youtube.com') || concept.eventPosterMediaUrl.includes('youtu.be') ? (
                            <div className="aspect-video">
                              <iframe 
                                src={`https://www.youtube.com/embed/${concept.eventPosterMediaUrl.includes('youtu.be') 
                                  ? concept.eventPosterMediaUrl.split('/').pop() 
                                  : new URLSearchParams(new URL(concept.eventPosterMediaUrl).search).get('v')}`}
                                className="w-full h-full"
                                frameBorder="0"
                                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                                allowFullScreen
                                title="Event poster preview"
                              />
                            </div>
                          ) : concept.eventPosterMediaUrl.includes('vimeo.com') ? (
                            <div className="aspect-video">
                              <iframe 
                                src={`https://player.vimeo.com/video/${concept.eventPosterMediaUrl.split('/').pop()}`}
                                className="w-full h-full"
                                frameBorder="0"
                                allow="autoplay; fullscreen; picture-in-picture"
                                allowFullScreen
                                title="Event poster preview"
                              />
                            </div>
                          ) : (
                            <img 
                              src={concept.eventPosterMediaUrl} 
                              alt="Aperçu affiche événement" 
                              className="w-full"
                              onError={(e) => { e.target.src = ''; e.target.alt = 'Image non valide'; }}
                            />
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* v9.3.7: Bouton remplacé par auto-save - Indication visuelle */}
              <div className="mt-6 p-3 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.2)' }}>
                <p className="text-green-400 text-sm flex items-center gap-2">
                  <span>✓</span> Sauvegarde automatique activée - Vos modifications sont enregistrées instantanément
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Courses Tab */}
        {tab === "courses" && (
          <div className="card-gradient rounded-xl p-6">
            <h2 className="font-semibold text-white mb-6" style={{ fontSize: '20px' }}>{t('courses')}</h2>
            {/* Liste des cours avec scroll */}
            <div style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '8px' }} className="custom-scrollbar">
              {courses.filter(c => !c.archived).map((course, idx) => (
                <div key={course.id} className="glass rounded-lg p-4 mb-4 relative">
                  {/* Actions: Audio + Dupliquer + Archiver */}
                  <div className="absolute top-2 right-2 flex gap-1">
                    {/* Bouton Gérer l'Audio */}
                    <button 
                      onClick={() => openAudioModal(course)}
                      className="p-2 rounded-lg hover:bg-pink-500/30 transition-colors"
                      style={{ color: '#d91cd2' }}
                      title="Gérer l'Audio / Playlist"
                      data-testid={`audio-course-${course.id}`}
                    >
                      <span className="text-sm">🎵</span>
                    </button>
                    {/* Bouton dupliquer */}
                    <button 
                      onClick={async () => {
                        try {
                          const duplicatedCourse = {
                            name: `${course.name} (copie)`,
                            weekday: course.weekday,
                            time: course.time,
                            locationName: course.locationName,
                            mapsUrl: course.mapsUrl || '',
                            visible: true,
                            archived: false
                          };
                          const res = await axios.post(`${API}/courses`, duplicatedCourse);
                          setCourses([...courses, res.data]);
                        } catch (err) {
                          console.error("Erreur duplication cours:", err);
                        }
                      }}
                      className="p-2 rounded-lg hover:bg-purple-500/30 transition-colors"
                      style={{ color: 'rgba(139, 92, 246, 0.8)' }}
                      title="Dupliquer ce cours"
                      data-testid={`duplicate-course-${course.id}`}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                      </svg>
                    </button>
                    {/* Bouton archiver (au lieu de supprimer) */}
                    <button 
                      onClick={async () => {
                        if (window.confirm(`Archiver le cours "${course.name}" ? Il sera masqué mais récupérable.`)) {
                          try {
                            await axios.put(`${API}/courses/${course.id}/archive`);
                            setCourses(courses.map(c => c.id === course.id ? { ...c, archived: true } : c));
                          } catch (err) {
                            console.error("Erreur archivage cours:", err);
                          }
                        }
                      }}
                      className="p-2 rounded-lg hover:bg-orange-500/30 transition-colors"
                      style={{ color: 'rgba(249, 115, 22, 0.8)' }}
                      title="Archiver ce cours"
                      data-testid={`archive-course-${course.id}`}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"/>
                      </svg>
                    </button>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pr-16">
                    <div>
                      <label className="block mb-1 text-white text-xs opacity-70">{t('courseName')}</label>
                      <input type="text" value={course.name} onChange={(e) => { const n = [...courses]; const realIdx = courses.findIndex(c => c.id === course.id); n[realIdx].name = e.target.value; setCourses(n); }}
                        onBlur={() => updateCourse(course)} className="w-full px-3 py-2 rounded-lg neon-input text-sm" />
                    </div>
                    <div>
                      <label className="block mb-1 text-white text-xs opacity-70">{t('location')}</label>
                      <input type="text" value={course.locationName} onChange={(e) => { const n = [...courses]; const realIdx = courses.findIndex(c => c.id === course.id); n[realIdx].locationName = e.target.value; setCourses(n); }}
                        onBlur={() => updateCourse(course)} className="w-full px-3 py-2 rounded-lg neon-input text-sm" />
                    </div>
                    <div>
                      <label className="block mb-1 text-white text-xs opacity-70">{t('weekday')}</label>
                      <select value={course.weekday} onChange={(e) => { const n = [...courses]; const realIdx = courses.findIndex(c => c.id === course.id); n[realIdx].weekday = parseInt(e.target.value); setCourses(n); updateCourse({ ...course, weekday: parseInt(e.target.value) }); }}
                        className="w-full px-3 py-2 rounded-lg neon-input text-sm">
                        {WEEKDAYS_MAP[lang].map((d, i) => <option key={i} value={i}>{d}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block mb-1 text-white text-xs opacity-70">{t('time')}</label>
                      <input type="time" value={course.time} onChange={(e) => { const n = [...courses]; n[idx].time = e.target.value; setCourses(n); }}
                        onBlur={() => updateCourse(course)} className="w-full px-3 py-2 rounded-lg neon-input text-sm" />
                    </div>
                    <div className="md:col-span-2">
                      <label className="block mb-1 text-white text-xs opacity-70">{t('mapsLink')}</label>
                      <input type="url" value={course.mapsUrl || ''} onChange={(e) => { const n = [...courses]; n[idx].mapsUrl = e.target.value; setCourses(n); }}
                        onBlur={() => updateCourse(course)} className="w-full px-3 py-2 rounded-lg neon-input text-sm" placeholder="https://maps.google.com/..." />
                    </div>
                    {/* Toggle visibilité du cours */}
                    <div className="flex items-center gap-3 mt-2">
                      <label className="text-white text-xs opacity-70">{t('visible')}</label>
                      <div className={`switch ${course.visible !== false ? 'active' : ''}`} 
                        onClick={() => { 
                          const n = [...courses]; 
                          const realIdx = courses.findIndex(c => c.id === course.id);
                          n[realIdx].visible = course.visible === false ? true : false; 
                          setCourses(n); 
                          updateCourse({ ...course, visible: n[realIdx].visible }); 
                        }} 
                        data-testid={`course-visible-${course.id}`}
                      />
                      <span className="text-white text-xs opacity-50">
                        {course.visible !== false ? '👁️ Visible' : '🚫 Masqué'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            
            {/* Section Cours Archivés */}
            {courses.filter(c => c.archived).length > 0 && (
              <div className="mt-6 pt-6 border-t border-purple-500/30">
                <h3 className="text-white text-sm font-semibold mb-3 flex items-center gap-2">
                  <span>📁</span> Cours archivés ({courses.filter(c => c.archived).length})
                </h3>
                <div className="space-y-2">
                  {courses.filter(c => c.archived).map(course => (
                    <div key={course.id} className="flex items-center justify-between p-3 rounded-lg" style={{ background: 'rgba(249, 115, 22, 0.1)', border: '1px solid rgba(249, 115, 22, 0.3)' }}>
                      <span className="text-white text-sm opacity-70">{course.name}</span>
                      <button 
                        onClick={async () => {
                          try {
                            await axios.put(`${API}/courses/${course.id}`, { ...course, archived: false });
                            setCourses(courses.map(c => c.id === course.id ? { ...c, archived: false } : c));
                          } catch (err) {
                            console.error("Erreur restauration cours:", err);
                          }
                        }}
                        className="px-3 py-1 rounded text-xs"
                        style={{ background: 'rgba(34, 197, 94, 0.3)', color: '#22c55e' }}
                        data-testid={`restore-course-${course.id}`}
                      >
                        ↩️ Restaurer
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            <form onSubmit={addCourse} className="glass rounded-lg p-4 mt-4">
              <h3 className="text-white mb-4 font-semibold text-sm">{t('addCourse')}</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <input type="text" placeholder={t('courseName')} value={newCourse.name} onChange={e => setNewCourse({ ...newCourse, name: e.target.value })} className="px-3 py-2 rounded-lg neon-input text-sm" required />
                <input type="text" placeholder={t('location')} value={newCourse.locationName} onChange={e => setNewCourse({ ...newCourse, locationName: e.target.value })} className="px-3 py-2 rounded-lg neon-input text-sm" />
                <select value={newCourse.weekday} onChange={e => setNewCourse({ ...newCourse, weekday: parseInt(e.target.value) })} className="px-3 py-2 rounded-lg neon-input text-sm">
                  {WEEKDAYS_MAP[lang].map((d, i) => <option key={i} value={i}>{d}</option>)}
                </select>
                <input type="time" value={newCourse.time} onChange={e => setNewCourse({ ...newCourse, time: e.target.value })} className="px-3 py-2 rounded-lg neon-input text-sm" />
              </div>
              <button type="submit" className="btn-primary px-4 py-2 rounded-lg mt-4 text-sm">{t('add')}</button>
            </form>
          </div>
        )}

        {/* Offers Tab */}
        {tab === "offers" && (
          <div className="card-gradient rounded-xl p-4 sm:p-6">
            {/* En-tête fixe avec titre et recherche */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4 sticky top-0 z-10 pb-3" style={{ background: 'inherit' }}>
              <h2 className="font-semibold text-white text-lg sm:text-xl">{t('offers')}</h2>
              <div className="relative w-full sm:w-64">
                <input
                  type="text"
                  placeholder="🔍 Rechercher une offre..."
                  value={offersSearch || ''}
                  onChange={(e) => setOffersSearch(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#fff' }}
                  data-testid="offers-search-input"
                />
                {offersSearch && (
                  <button
                    onClick={() => setOffersSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
                  >✕</button>
                )}
              </div>
            </div>
            
            {/* Conteneur scrollable pour les offres */}
            <div style={{ maxHeight: '500px', overflowY: 'auto', overflowX: 'hidden' }}>
              {/* === MOBILE VIEW: Cartes verticales === */}
              <div className="block md:hidden space-y-4">
                {(offersSearch ? offers.filter(o => 
                  o.name?.toLowerCase().includes(offersSearch.toLowerCase()) ||
                  o.description?.toLowerCase().includes(offersSearch.toLowerCase())
                ) : offers).map((offer, idx) => (
                  <div key={offer.id} className="glass rounded-lg p-4">
                    {/* Image et nom */}
                    <div className="flex items-center gap-3 mb-3">
                      {offer.images?.[0] || offer.thumbnail ? (
                        <img src={offer.images?.[0] || offer.thumbnail} alt="" className="w-16 h-16 rounded-lg object-cover flex-shrink-0" />
                      ) : (
                        <div className="w-16 h-16 rounded-lg bg-purple-900/30 flex items-center justify-center text-2xl flex-shrink-0">🎧</div>
                      )}
                      <div className="flex-1 min-w-0">
                        <h4 className="text-white font-semibold text-sm truncate">{offer.name}</h4>
                        <p className="text-purple-400 text-xs">{offer.price} CHF</p>
                        <p className="text-white/50 text-xs">{offer.images?.filter(i => i).length || 0} images</p>
                      </div>
                      {/* Toggle visible */}
                      <div className="flex flex-col items-center gap-1">
                        <div className={`switch ${offer.visible ? 'active' : ''}`} onClick={() => { const n = [...offers]; n[idx].visible = !offer.visible; setOffers(n); updateOffer({ ...offer, visible: !offer.visible }); }} />
                        <span className="text-xs text-white/40">{offer.visible ? 'ON' : 'OFF'}</span>
                      </div>
                    </div>
                    
                    {/* Description */}
                    {offer.description && (
                      <p className="text-white/60 text-xs mb-3 italic truncate">"{offer.description}"</p>
                    )}
                    
                    {/* Boutons action - largeur 100% sur mobile */}
                    <div className="flex gap-2">
                      <button 
                        onClick={() => startEditOffer(offer)}
                        className="flex-1 py-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium"
                        data-testid={`edit-offer-${offer.id}`}
                      >
                        ✏️ Modifier
                      </button>
                      <button 
                        onClick={() => deleteOffer(offer.id)}
                        className="flex-1 py-3 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-medium"
                        data-testid={`delete-offer-${offer.id}`}
                      >
                        🗑️ Supprimer
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              
              {/* === DESKTOP VIEW: Layout horizontal === */}
              <div className="hidden md:block">
              {(offersSearch ? offers.filter(o => 
                o.name?.toLowerCase().includes(offersSearch.toLowerCase()) ||
                o.description?.toLowerCase().includes(offersSearch.toLowerCase())
              ) : offers).map((offer, idx) => (
                <div key={offer.id} className="glass rounded-lg p-4 mb-4">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-3">
                      {offer.images?.[0] || offer.thumbnail ? (
                        <img src={offer.images?.[0] || offer.thumbnail} alt="" className="w-12 h-12 rounded-lg object-cover" />
                      ) : (
                        <div className="w-12 h-12 rounded-lg bg-purple-900/30 flex items-center justify-center text-2xl">🎧</div>
                      )}
                      <div>
                        <h4 className="text-white font-semibold">{offer.name}</h4>
                        <p className="text-purple-400 text-sm">{offer.price} CHF • {offer.images?.filter(i => i).length || 0} images</p>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button 
                        onClick={() => startEditOffer(offer)}
                        className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs"
                        data-testid={`edit-offer-${offer.id}`}
                      >
                        ✏️ Modifier
                      </button>
                      <button 
                        onClick={() => deleteOffer(offer.id)}
                        className="px-3 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs"
                        data-testid={`delete-offer-${offer.id}`}
                      >
                        🗑️ Supprimer
                      </button>
                      <div className="flex items-center gap-2 ml-2">
                        <span className="text-xs text-white opacity-60">{t('visible')}</span>
                        <div className={`switch ${offer.visible ? 'active' : ''}`} onClick={() => { const n = [...offers]; n[idx].visible = !offer.visible; setOffers(n); updateOffer({ ...offer, visible: !offer.visible }); }} />
                      </div>
                    </div>
                  </div>
                  {offer.description && (
                    <p className="text-white/60 text-xs mt-2 italic">"{offer.description}"</p>
                  )}
                </div>
              ))}
            </div>
            </div>
            
            {/* Formulaire Ajout/Modification - RESPONSIVE */}
            <form id="offer-form" onSubmit={addOffer} className="glass rounded-lg p-4 mt-4 border-2 border-purple-500/50">
              <h3 className="text-white mb-4 font-semibold text-sm flex items-center gap-2">
                {editingOfferId ? '✏️ Modifier l\'offre' : '➕ Ajouter une offre'}
                {editingOfferId && (
                  <button type="button" onClick={cancelEditOffer} className="ml-auto text-xs text-red-400 hover:text-red-300">
                    ✕ Annuler
                  </button>
                )}
              </h3>
              
              {/* Basic Info - Stack on mobile */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
                <div>
                  <label className="text-xs text-white opacity-60 mb-1 block">Nom de l'offre *</label>
                  <input type="text" placeholder="Ex: Cours à l'unité" value={newOffer.name} onChange={e => setNewOffer({ ...newOffer, name: e.target.value })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" required />
                </div>
                <div>
                  <label className="text-xs text-white opacity-60 mb-1 block">Prix (CHF)</label>
                  <input type="number" placeholder="30" value={newOffer.price} onChange={e => setNewOffer({ ...newOffer, price: parseFloat(e.target.value) || 0 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" />
                </div>
              </div>
              
              {/* 5 Champs d'images - 1 colonne mobile, 5 desktop */}
              <div className="mt-4">
                <label className="text-xs text-white opacity-60 mb-2 block">📷 Images (max 5 URLs)</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2">
                  {[0, 1, 2, 3, 4].map(i => (
                    <input 
                      key={i}
                      type="url" 
                      placeholder={`Image ${i + 1}`}
                      value={newOffer.images?.[i] || ''} 
                      onChange={e => {
                        const newImages = [...(newOffer.images || ["", "", "", "", ""])];
                        newImages[i] = e.target.value;
                        setNewOffer({ ...newOffer, images: newImages });
                      }}
                      className="w-full px-3 py-3 rounded-lg neon-input text-xs"
                    />
                  ))}
                </div>
              </div>
              
              {/* Description */}
              <div className="mt-4">
                <label className="text-xs text-white opacity-60 mb-1 block">Description (icône "i")</label>
                <textarea 
                  value={newOffer.description || ''} 
                  onChange={e => setNewOffer({ ...newOffer, description: e.target.value })}
                  className="w-full px-3 py-3 rounded-lg neon-input text-sm" 
                  rows={2}
                  maxLength={150}
                  placeholder="Description visible au clic sur l'icône i (max 150 car.)"
                />
                <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>{(newOffer.description || '').length}/150</p>
              </div>
              
              {/* Mots-clés pour la recherche */}
              <div className="mt-3">
                <label className="text-xs text-white opacity-60 mb-1 block">🔍 Mots-clés (pour la recherche)</label>
                <input 
                  type="text"
                  value={newOffer.keywords || ''} 
                  onChange={e => setNewOffer({ ...newOffer, keywords: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                  placeholder="session, séance, cardio, danse, afro... (séparés par virgules)"
                  data-testid="offer-keywords"
                />
                <p className="text-xs mt-1" style={{ color: 'rgba(139, 92, 246, 0.6)' }}>💡 Aide les clients à trouver cette offre avec des termes alternatifs</p>
              </div>
              
              {/* Category & Type - Stack on mobile */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">
                <select 
                  value={newOffer.category} 
                  onChange={e => setNewOffer({ ...newOffer, category: e.target.value })}
                  className="px-3 py-3 rounded-lg neon-input text-sm w-full"
                >
                  <option value="service">🎧 Service / Cours</option>
                  <option value="tshirt">👕 T-shirt</option>
                  <option value="shoes">👟 Chaussures</option>
                  <option value="supplement">💊 Complément</option>
                  <option value="accessory">🎒 Accessoire</option>
                </select>
                <label className="flex items-center gap-2 text-white text-sm py-2">
                  <input 
                    type="checkbox" 
                    checked={newOffer.isProduct} 
                    onChange={e => setNewOffer({ ...newOffer, isProduct: e.target.checked })} 
                    className="w-5 h-5"
                  />
                  Produit physique
                </label>
                <label className="flex items-center gap-2 text-white text-sm py-2">
                  <input 
                    type="checkbox" 
                    checked={newOffer.visible} 
                    onChange={e => setNewOffer({ ...newOffer, visible: e.target.checked })} 
                    className="w-5 h-5"
                  />
                  Visible
                </label>
              </div>
              
              {/* E-Commerce Fields (shown when isProduct) */}
              {newOffer.isProduct && (
                <div className="mt-3 p-3 rounded-lg border border-purple-500/30">
                  <p className="text-xs text-purple-400 mb-3">📦 Paramètres produit</p>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs text-white opacity-60">TVA (%)</label>
                      <input type="number" placeholder="7.7" value={newOffer.tva || ''} onChange={e => setNewOffer({ ...newOffer, tva: parseFloat(e.target.value) || 0 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" step="0.1" />
                    </div>
                    <div>
                      <label className="text-xs text-white opacity-60">Frais port</label>
                      <input type="number" placeholder="9.90" value={newOffer.shippingCost || ''} onChange={e => setNewOffer({ ...newOffer, shippingCost: parseFloat(e.target.value) || 0 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" step="0.1" />
                    </div>
                    <div>
                      <label className="text-xs text-white opacity-60">Stock</label>
                      <input type="number" placeholder="-1" value={newOffer.stock} onChange={e => setNewOffer({ ...newOffer, stock: parseInt(e.target.value) || -1 })} className="w-full px-3 py-3 rounded-lg neon-input text-sm" />
                    </div>
                  </div>
                  
                  {/* Variants */}
                  <div className="mt-3">
                    <label className="text-xs text-white opacity-60">Variantes (séparées par virgule)</label>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
                      <input 
                        type="text" 
                        placeholder="Tailles: S, M, L, XL"
                        onChange={e => setNewOffer({ 
                          ...newOffer, 
                          variants: { ...newOffer.variants, sizes: e.target.value.split(',').map(s => s.trim()).filter(s => s) }
                        })}
                        className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                      />
                      <input 
                        type="text" 
                        placeholder="Couleurs: Noir, Blanc"
                        onChange={e => setNewOffer({ 
                          ...newOffer, 
                          variants: { ...newOffer.variants, colors: e.target.value.split(',').map(s => s.trim()).filter(s => s) }
                        })}
                        className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                      />
                      <input 
                        type="text" 
                        placeholder="Poids: 0.5kg, 1kg"
                        onChange={e => setNewOffer({ 
                          ...newOffer, 
                          variants: { ...newOffer.variants, weights: e.target.value.split(',').map(s => s.trim()).filter(s => s) }
                        })}
                        className="w-full px-3 py-3 rounded-lg neon-input text-sm"
                      />
                    </div>
                  </div>
                </div>
              )}
              
              <button type="submit" className="btn-primary px-6 py-3 rounded-lg mt-4 text-sm w-full">
                {editingOfferId ? '💾 Enregistrer les modifications' : '➕ Ajouter l\'offre'}
              </button>
            </form>
          </div>
        )}

        {/* v9.2.9: Ma Page de Vente - Simplifié et unifié */}
        {tab === "page-vente" && (
          <div className="space-y-6">
            {/* Bloc principal - Ma Page de Vente */}
            <div className="card-gradient rounded-xl p-6">
              <h2 className="font-semibold text-white mb-2" style={{ fontSize: '20px' }}>🏪 Ma Page de Vente</h2>
              <p className="text-white/60 text-sm mb-6">
                Partagez votre page personnalisée avec vos clients pour qu'ils puissent réserver et payer.
              </p>
              
              {/* URL de la page de vente (vitrine) */}
              <div 
                className="rounded-lg p-4 mb-6"
                style={{ background: 'rgba(217, 28, 210, 0.1)', border: '1px solid rgba(217, 28, 210, 0.3)' }}
              >
                <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
                  <div className="flex-1">
                    <h4 className="text-white font-medium mb-1">🔗 Votre lien unique</h4>
                    <p className="text-purple-400 text-sm break-all" data-testid="page-vente-url">
                      {coachVitrineUrl || 'Chargement...'}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleCoachShareLink}
                      className="px-4 py-2 rounded-lg text-white text-sm font-semibold transition-all hover:scale-105"
                      style={{ background: linkCopied ? 'rgba(34, 197, 94, 0.3)' : 'linear-gradient(135deg, #d91cd2, #8b5cf6)' }}
                      data-testid="copy-page-vente-link"
                    >
                      {linkCopied ? '✓ Copié' : '📋 Copier'}
                    </button>
                    <button
                      onClick={() => coachVitrineUrl && window.open(coachVitrineUrl, '_blank')}
                      className="px-4 py-2 rounded-lg text-white text-sm font-semibold"
                      style={{ background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)' }}
                      data-testid="preview-page-vente"
                    >
                      👁️ Voir
                    </button>
                  </div>
                </div>
              </div>
              
              {/* QR Code */}
              {coachVitrineUrl && (
                <div className="flex justify-center mb-6">
                  <div className="bg-white rounded-lg p-4" data-testid="page-vente-qr">
                    <QRCodeSVG 
                      value={coachVitrineUrl}
                      size={150}
                      bgColor="#FFFFFF"
                      fgColor="#1a1a2e"
                      level="H"
                      includeMargin={true}
                    />
                  </div>
                </div>
              )}
              
              <p className="text-white/40 text-xs text-center">
                💡 Imprimez le QR Code pour vos flyers ou affichez-le dans votre salle !
              </p>
            </div>
            
            {/* Bloc secondaire - Liens de paiement (collapsible) */}
            <details className="card-gradient rounded-xl overflow-hidden">
              <summary 
                className="p-4 cursor-pointer text-white font-medium flex justify-between items-center"
                style={{ background: 'rgba(255,255,255,0.03)' }}
              >
                <div className="flex items-center gap-3">
                  <span>⚙️ Configuration des liens de paiement (optionnel)</span>
                  {/* v9.3.7: Indicateur de sauvegarde automatique */}
                  {paymentSaveStatus && (
                    <span 
                      className="px-2 py-0.5 rounded-full text-xs"
                      style={{
                        background: paymentSaveStatus === 'saved' ? 'rgba(34, 197, 94, 0.2)' : 
                                   paymentSaveStatus === 'error' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(147, 51, 234, 0.2)',
                        color: paymentSaveStatus === 'saved' ? '#22c55e' : 
                               paymentSaveStatus === 'error' ? '#ef4444' : '#a855f7'
                      }}
                      data-testid="payment-save-status"
                    >
                      {paymentSaveStatus === 'saving' && '⏳'}
                      {paymentSaveStatus === 'saved' && '✓'}
                      {paymentSaveStatus === 'error' && '⚠️'}
                    </span>
                  )}
                </div>
                <span className="text-white/40">▼</span>
              </summary>
              <div className="p-6 space-y-4">
                <div><label className="block mb-2 text-white text-sm">{t('stripeLink')}</label>
                  <input type="url" value={paymentLinks.stripe} onChange={e => setPaymentLinks({ ...paymentLinks, stripe: e.target.value })} className="w-full px-4 py-3 rounded-lg neon-input" placeholder="https://buy.stripe.com/..." data-testid="payment-stripe-input" /></div>
                <div><label className="block mb-2 text-white text-sm">{t('paypalLink')}</label>
                  <input type="url" value={paymentLinks.paypal} onChange={e => setPaymentLinks({ ...paymentLinks, paypal: e.target.value })} className="w-full px-4 py-3 rounded-lg neon-input" placeholder="https://paypal.me/..." data-testid="payment-paypal-input" /></div>
                <div><label className="block mb-2 text-white text-sm">{t('twintLink')}</label>
                  <input type="url" value={paymentLinks.twint} onChange={e => setPaymentLinks({ ...paymentLinks, twint: e.target.value })} className="w-full px-4 py-3 rounded-lg neon-input" placeholder="https://..." data-testid="payment-twint-input" /></div>
                <div><label className="block mb-2 text-white text-sm">{t('coachWhatsapp')}</label>
                  <input type="tel" value={paymentLinks.coachWhatsapp} onChange={e => setPaymentLinks({ ...paymentLinks, coachWhatsapp: e.target.value })} className="w-full px-4 py-3 rounded-lg neon-input" placeholder="+41791234567" data-testid="payment-whatsapp-input" /></div>
                
                {/* Section Notifications automatiques */}
                <div className="mt-6 pt-6 border-t border-purple-500/30">
                  <h3 className="text-white text-sm font-semibold mb-4">🔔 Notifications automatiques</h3>
                  <p className="text-xs mb-4" style={{ color: 'rgba(255,255,255,0.5)' }}>
                    Recevez une notification par email et/ou WhatsApp à chaque nouvelle réservation.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block mb-2 text-white text-xs opacity-70">📧 Email pour les alertes</label>
                      <input 
                        type="email" 
                        value={paymentLinks.coachNotificationEmail || ''} 
                        onChange={e => setPaymentLinks({ ...paymentLinks, coachNotificationEmail: e.target.value })} 
                        className="w-full px-4 py-3 rounded-lg neon-input text-sm" 
                        placeholder="coach@exemple.com"
                        data-testid="coach-notification-email"
                      />
                    </div>
                    <div>
                      <label className="block mb-2 text-white text-xs opacity-70">📱 WhatsApp pour les alertes</label>
                      <input 
                        type="tel" 
                        value={paymentLinks.coachNotificationPhone || ''} 
                        onChange={e => setPaymentLinks({ ...paymentLinks, coachNotificationPhone: e.target.value })} 
                        className="w-full px-4 py-3 rounded-lg neon-input text-sm" 
                        placeholder="+41791234567"
                        data-testid="coach-notification-phone"
                      />
                    </div>
                  </div>
                </div>

                {/* v9.3.7: Indication auto-save */}
                <div className="mt-4 p-3 rounded-lg" style={{ background: 'rgba(34, 197, 94, 0.1)', border: '1px solid rgba(34, 197, 94, 0.2)' }}>
                  <p className="text-green-400 text-xs flex items-center gap-2">
                    <span>✓</span> Sauvegarde automatique - Vos liens sont enregistrés à chaque modification
                  </p>
                </div>
              </div>
            </details>
          </div>
        )}

        {/* Promo Codes Tab with Beneficiary Dropdown */}
        {tab === "codes" && (
          <div className="card-gradient rounded-xl p-4 sm:p-6">
            {/* En-tête avec recherche */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 gap-3">
              <h2 className="font-semibold text-white text-lg sm:text-xl">{t('promoCodes')}</h2>
              <div className="relative w-full sm:w-64">
                <input
                  type="text"
                  placeholder="🔍 Rechercher un code..."
                  value={codesSearch}
                  onChange={(e) => setCodesSearch(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)', color: '#fff' }}
                  data-testid="codes-search-input"
                />
                {codesSearch && (
                  <button
                    onClick={() => setCodesSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
                  >✕</button>
                )}
              </div>
            </div>
            
            {/* Boutons d'action */}
            <div className="flex justify-end mb-4 flex-wrap gap-2">
              {/* Add Manual Contact Button */}
              <button 
                type="button"
                onClick={() => setShowManualContactForm(!showManualContactForm)} 
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-white text-xs sm:text-sm transition-all"
                style={{ 
                  background: showManualContactForm ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)',
                  border: showManualContactForm ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(34, 197, 94, 0.4)'
                }}
                data-testid="add-manual-contact-btn"
              >
                {showManualContactForm ? '✕ Fermer' : t('addManualContact')}
              </button>
              <input type="file" accept=".csv" ref={fileInputRef} onChange={handleImportCSV} style={{ display: 'none' }} />
              <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 px-3 py-2 rounded-lg glass text-white text-xs sm:text-sm" data-testid="import-csv-btn">
                <FolderIcon /> {t('importCSV')}
              </button>
              <button 
                onClick={exportPromoCodesCSV} 
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-white text-xs sm:text-sm"
                style={{ background: 'rgba(139, 92, 246, 0.3)', border: '1px solid rgba(139, 92, 246, 0.5)' }}
                data-testid="export-csv-btn"
              >
                📥 {t('exportCSV')}
              </button>
            </div>
            
            {/* Manual Contact Form */}
            {showManualContactForm && (
              <form onSubmit={addManualContact} className="mb-6 p-4 rounded-lg border border-green-500/30" style={{ background: 'rgba(34, 197, 94, 0.1)' }}>
                <h3 className="text-white font-semibold mb-3 text-sm">👤 Ajouter un nouveau contact</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                  <input 
                    type="text" 
                    placeholder={t('manualContactName')} 
                    value={manualContact.name} 
                    onChange={e => setManualContact({ ...manualContact, name: e.target.value })}
                    className="px-3 py-2 rounded-lg neon-input text-sm" 
                    required
                    data-testid="manual-contact-name"
                  />
                  <input 
                    type="email" 
                    placeholder={t('manualContactEmail')} 
                    value={manualContact.email} 
                    onChange={e => setManualContact({ ...manualContact, email: e.target.value })}
                    className="px-3 py-2 rounded-lg neon-input text-sm" 
                    required
                    data-testid="manual-contact-email"
                  />
                  <input 
                    type="tel" 
                    placeholder={t('manualContactWhatsapp')} 
                    value={manualContact.whatsapp} 
                    onChange={e => setManualContact({ ...manualContact, whatsapp: e.target.value })}
                    className="px-3 py-2 rounded-lg neon-input text-sm"
                    data-testid="manual-contact-whatsapp"
                  />
                </div>
                <button type="submit" className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ background: 'rgba(34, 197, 94, 0.6)' }} data-testid="submit-manual-contact">
                  ✓ Ajouter le contact
                </button>
              </form>
            )}
            
            <form onSubmit={addCode} className="mb-6 p-4 rounded-lg glass">
              {/* Toggle Mode Série + Bouton Nettoyage */}
              <div className="flex items-center justify-between mb-4">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={isBatchMode} 
                    onChange={(e) => setIsBatchMode(e.target.checked)}
                    className="w-5 h-5 rounded accent-purple-500"
                    data-testid="batch-mode-toggle"
                  />
                  <span className="text-white font-medium">{t('batchGeneration')}</span>
                </label>
                <div className="flex items-center gap-2">
                  {isBatchMode && (
                    <span className="text-xs text-purple-300 opacity-70">{t('batchMax')}</span>
                  )}
                  {/* Bouton nettoyage des données fantômes */}
                  <button 
                    type="button"
                    onClick={manualSanitize}
                    className="px-3 py-1 rounded-lg text-xs"
                    style={{ background: 'rgba(251, 191, 36, 0.2)', color: '#fbbf24', border: '1px solid rgba(251, 191, 36, 0.4)' }}
                    title="Nettoyer les données fantômes (articles/contacts supprimés)"
                    data-testid="sanitize-btn"
                  >
                    🧹 Nettoyer
                  </button>
                </div>
              </div>
              
              {/* Champs de génération en série (visibles uniquement si mode série activé) */}
              {isBatchMode && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4 p-3 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
                  <div>
                    <label className="block text-white text-xs mb-1 opacity-70">{t('codePrefix')}</label>
                    <input 
                      type="text" 
                      placeholder="VIP, PROMO, COACH..." 
                      value={newCode.prefix} 
                      onChange={e => setNewCode({ ...newCode, prefix: e.target.value.toUpperCase() })}
                      className="w-full px-3 py-2 rounded-lg neon-input text-sm uppercase" 
                      data-testid="batch-prefix"
                      maxLength={15}
                    />
                    <span className="text-xs text-purple-300 opacity-50 mt-1 block">Ex: VIP → VIP-1, VIP-2...</span>
                  </div>
                  <div>
                    <label className="block text-white text-xs mb-1 opacity-70">{t('batchCount')}</label>
                    <input 
                      type="number" 
                      min="1" 
                      max="20" 
                      placeholder="1-20" 
                      value={newCode.batchCount} 
                      onChange={e => setNewCode({ ...newCode, batchCount: Math.min(20, Math.max(1, parseInt(e.target.value) || 1)) })}
                      className="w-full px-3 py-2 rounded-lg neon-input text-sm" 
                      data-testid="batch-count"
                    />
                  </div>
                </div>
              )}
              
              {/* Champ code unique (visible uniquement si mode série désactivé) */}
              {!isBatchMode && (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                  <input type="text" placeholder={t('codePromo')} value={newCode.code} onChange={e => setNewCode({ ...newCode, code: e.target.value })}
                    className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="new-code-name" />
                  <select value={newCode.type} onChange={e => setNewCode({ ...newCode, type: e.target.value })} className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="new-code-type">
                    <option value="">{t('type')}</option>
                    <option value="100%">100% (Gratuit)</option>
                    <option value="%">%</option>
                    <option value="CHF">CHF</option>
                  </select>
                  <input type="number" placeholder={t('value')} value={newCode.value} onChange={e => setNewCode({ ...newCode, value: e.target.value })}
                    className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="new-code-value" />
                </div>
              )}
              
              {/* Paramètres communs (Type, Valeur pour le mode série) */}
              {isBatchMode && (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 mb-4">
                  <select value={newCode.type} onChange={e => setNewCode({ ...newCode, type: e.target.value })} className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="batch-code-type">
                    <option value="">{t('type')}</option>
                    <option value="100%">100% (Gratuit)</option>
                    <option value="%">%</option>
                    <option value="CHF">CHF</option>
                  </select>
                  <input type="number" placeholder={t('value')} value={newCode.value} onChange={e => setNewCode({ ...newCode, value: e.target.value })}
                    className="px-3 py-2 rounded-lg neon-input text-sm" data-testid="batch-code-value" />
                </div>
              )}
              
              {/* ============ SÉLECTION MULTIPLE DES BÉNÉFICIAIRES ============ */}
              <div className="mb-4">
                <label className="block text-white text-xs mb-2 opacity-70">
                  👥 Sélectionner les bénéficiaires ({selectedBeneficiaries.length} sélectionné{selectedBeneficiaries.length > 1 ? 's' : ''})
                </label>
                <div className="border border-purple-500/30 rounded-lg p-3 bg-purple-900/10" style={{ maxHeight: '120px', overflowY: 'auto' }}>
                  <div className="flex flex-wrap gap-2">
                    {uniqueCustomers.length > 0 ? uniqueCustomers.map((c, i) => (
                      <button
                        key={i}
                        type="button"
                        onClick={() => toggleBeneficiarySelection(c.email)}
                        className={`px-2 py-1 rounded text-xs transition-all flex items-center gap-1 ${
                          selectedBeneficiaries.includes(c.email) 
                            ? 'bg-pink-600 text-white' 
                            : 'bg-gray-700 text-white hover:bg-gray-600'
                        }`}
                        data-testid={`beneficiary-${i}`}
                      >
                        {selectedBeneficiaries.includes(c.email) && <span>✓</span>}
                        {c.name ? c.name.split(' ')[0] : 'Contact'}
                      </button>
                    )) : (
                      <span className="text-white text-xs opacity-50">Aucun contact disponible</span>
                    )}
                  </div>
                </div>
                {/* Affichage des bénéficiaires sélectionnés avec croix de suppression */}
                {selectedBeneficiaries.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {selectedBeneficiaries.map((email, i) => {
                      const customer = uniqueCustomers.find(c => c.email === email);
                      return (
                        <span key={i} className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs bg-pink-600/30 text-pink-300">
                          {customer?.name || email}
                          <button
                            type="button"
                            onClick={() => toggleBeneficiarySelection(email)}
                            className="hover:text-white ml-1"
                          >×</button>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                <input type="number" placeholder={t('maxUses')} value={newCode.maxUses} onChange={e => setNewCode({ ...newCode, maxUses: e.target.value })}
                  className="px-3 py-2 rounded-lg neon-input text-sm" />
                <input type="date" value={newCode.expiresAt} onChange={e => setNewCode({ ...newCode, expiresAt: e.target.value })}
                  className="px-3 py-2 rounded-lg neon-input text-sm" />
                <div>
                  <label className="block text-white text-xs mb-1 opacity-70">📦 Articles autorisés (Cours + Produits)</label>
                  {/* Scrollable list - Courses AND Products */}
                  <div className="courses-scroll-container" style={{ maxHeight: '150px', overflowY: 'auto', padding: '4px' }} data-testid="articles-scroll-container">
                    {/* Section Cours */}
                    {courses.length > 0 && (
                      <div className="mb-2">
                        <p className="text-white text-xs opacity-40 mb-1">📅 Cours</p>
                        <div className="flex flex-wrap gap-2">
                          {courses.map(c => (
                            <button key={c.id} type="button" onClick={() => toggleCourseSelection(c.id)}
                              className={`px-2 py-1 rounded text-xs transition-all ${newCode.courses.includes(c.id) ? 'bg-purple-600' : 'bg-gray-700 hover:bg-gray-600'}`}
                              style={{ color: 'white' }} data-testid={`course-select-${c.id}`}>{c.name ? c.name.split(' – ')[0] : 'Cours'}</button>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Section Produits */}
                    {offers.filter(o => o.isProduct).length > 0 && (
                      <div className="mt-2">
                        <p className="text-white text-xs opacity-40 mb-1">🛒 Produits</p>
                        <div className="flex flex-wrap gap-2">
                          {offers.filter(o => o.isProduct).map(p => (
                            <button key={p.id} type="button" onClick={() => toggleCourseSelection(p.id)}
                              className={`px-2 py-1 rounded text-xs transition-all ${newCode.courses.includes(p.id) ? 'bg-pink-600' : 'bg-gray-700 hover:bg-gray-600'}`}
                              style={{ color: 'white' }} data-testid={`product-select-${p.id}`}>{p.name}</button>
                          ))}
                        </div>
                      </div>
                    )}
                    {/* Section Offres/Services */}
                    {offers.filter(o => !o.isProduct).length > 0 && (
                      <div className="mt-2">
                        <p className="text-white text-xs opacity-40 mb-1">🎫 Offres</p>
                        <div className="flex flex-wrap gap-2">
                          {offers.filter(o => !o.isProduct).map(o => (
                            <button key={o.id} type="button" onClick={() => toggleCourseSelection(o.id)}
                              className={`px-2 py-1 rounded text-xs transition-all ${newCode.courses.includes(o.id) ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'}`}
                              style={{ color: 'white' }} data-testid={`offer-select-${o.id}`}>{o.name}</button>
                          ))}
                        </div>
                      </div>
                    )}
                    {courses.length === 0 && offers.length === 0 && (
                      <span className="text-white text-xs opacity-50">Tous les articles</span>
                    )}
                  </div>
                  {/* Articles sélectionnés avec croix de suppression */}
                  {newCode.courses.length > 0 && (
                    <div className="mt-2">
                      <p className="text-white text-xs opacity-40 mb-1">Sélectionnés:</p>
                      <div className="flex flex-wrap gap-1">
                        {newCode.courses.map(articleId => {
                          const course = courses.find(c => c.id === articleId);
                          const offer = offers.find(o => o.id === articleId);
                          const name = course?.name?.split(' – ')[0] || offer?.name || articleId;
                          const bgColor = course ? 'bg-purple-600/30' : offer?.isProduct ? 'bg-pink-600/30' : 'bg-blue-600/30';
                          const textColor = course ? 'text-purple-300' : offer?.isProduct ? 'text-pink-300' : 'text-blue-300';
                          return (
                            <span key={articleId} className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${bgColor} ${textColor}`}>
                              {name}
                              <button
                                type="button"
                                onClick={() => removeAllowedArticle(articleId)}
                                className="hover:text-white ml-1 font-bold"
                                title="Supprimer"
                              >×</button>
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              </div>
              
              {/* Bouton d'action */}
              <button 
                type="submit" 
                className="btn-primary px-6 py-2 rounded-lg text-sm flex items-center gap-2" 
                data-testid={isBatchMode ? "generate-batch" : "add-code"}
                disabled={batchLoading}
              >
                {batchLoading ? (
                  <>
                    <span className="animate-spin">⏳</span> Création en cours...
                  </>
                ) : isBatchMode ? (
                  <>{t('generateBatch')} ({newCode.batchCount || 1} codes)</>
                ) : (
                  t('add')
                )}
              </button>
            </form>

            {/* Liste des codes promo avec scroll */}
            <div style={{ maxHeight: '400px', overflowY: 'auto', overflowX: 'hidden' }}>
              <div className="space-y-2">
                {(codesSearch ? discountCodes.filter(c => 
                  c.code?.toLowerCase().includes(codesSearch.toLowerCase()) ||
                  c.assignedEmails?.some(e => e.toLowerCase().includes(codesSearch.toLowerCase()))
                ) : discountCodes).map(code => (
                <div key={code.id} className="p-4 rounded-lg glass">
                  {/* Mode édition pour ce code */}
                  {editingCode?.id === code.id ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-white font-bold">✏️ Modification de {code.code}</span>
                        <button onClick={() => setEditingCode(null)} className="text-white/50 hover:text-white">×</button>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        <div>
                          <label className="block text-white text-xs mb-1 opacity-50">Valeur</label>
                          <input 
                            type="number" 
                            value={editingCode.value} 
                            onChange={e => setEditingCode({...editingCode, value: parseFloat(e.target.value)})}
                            className="w-full px-2 py-1 rounded neon-input text-sm"
                          />
                        </div>
                        <div>
                          <label className="block text-white text-xs mb-1 opacity-50">Max utilisations</label>
                          <input 
                            type="number" 
                            value={editingCode.maxUses || ''} 
                            onChange={e => setEditingCode({...editingCode, maxUses: e.target.value ? parseInt(e.target.value) : null})}
                            className="w-full px-2 py-1 rounded neon-input text-sm"
                            placeholder="Illimité"
                          />
                        </div>
                        <div>
                          <label className="block text-white text-xs mb-1 opacity-50">Expiration</label>
                          <input 
                            type="date" 
                            value={editingCode.expiresAt ? editingCode.expiresAt.split('T')[0] : ''} 
                            onChange={e => setEditingCode({...editingCode, expiresAt: e.target.value || null})}
                            className="w-full px-2 py-1 rounded neon-input text-sm"
                          />
                        </div>
                        <div>
                          <label className="block text-white text-xs mb-1 opacity-50">Bénéficiaire</label>
                          <select 
                            value={editingCode.assignedEmail || ''} 
                            onChange={e => setEditingCode({...editingCode, assignedEmail: e.target.value || null})}
                            className="w-full px-2 py-1 rounded neon-input text-sm"
                          >
                            <option value="">Tous</option>
                            {uniqueCustomers.map((c, i) => (
                              <option key={i} value={c.email}>{c.name || 'Contact sans nom'}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div className="flex gap-2 justify-end mt-2">
                        <button 
                          onClick={() => setEditingCode(null)}
                          className="px-3 py-1 rounded text-sm bg-gray-600 text-white"
                        >
                          Annuler
                        </button>
                        <button 
                          onClick={() => updateCodeIndividual(code.id, {
                            value: editingCode.value,
                            maxUses: editingCode.maxUses,
                            expiresAt: editingCode.expiresAt,
                            assignedEmail: editingCode.assignedEmail
                          })}
                          className="px-3 py-1 rounded text-sm bg-pink-600 text-white"
                        >
                          ✓ Sauvegarder
                        </button>
                      </div>
                    </div>
                  ) : (
                    /* Mode affichage normal */
                    <div className="flex justify-between items-center flex-wrap gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-1">
                          <span className="text-white font-bold">{code.code}</span>
                          <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(139, 92, 246, 0.3)', color: '#d8b4fe' }}>
                            {code.type === '100%' ? '100%' : `${code.value}${code.type}`}
                          </span>
                        </div>
                        <div className="text-white text-xs opacity-50 flex flex-wrap items-center gap-2">
                          {/* Bénéficiaire avec croix de suppression */}
                          {code.assignedEmail && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-600/20 text-blue-300">
                              📧 {code.assignedEmail}
                              <button
                                onClick={() => removeBeneficiaryFromExistingCode(code.id)}
                                className="hover:text-white ml-1 font-bold"
                                title="Retirer ce bénéficiaire"
                              >×</button>
                            </span>
                          )}
                          {code.maxUses && <span className="mr-2">🔢 Max: {code.maxUses}</span>}
                          {code.expiresAt && <span className="mr-2">📅 {new Date(code.expiresAt).toLocaleDateString()}</span>}
                          <span>✓ {t('used')}: {code.used || 0}x</span>
                        </div>
                        {/* Articles autorisés avec croix de suppression (mise à jour immédiate en DB) */}
                        {code.courses && code.courses.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            <span className="text-white text-xs opacity-40 mr-1">Articles:</span>
                            {code.courses.map(articleId => {
                              const course = courses.find(c => c.id === articleId);
                              const offer = offers.find(o => o.id === articleId);
                              const name = course?.name?.split(' – ')[0] || offer?.name || articleId;
                              const bgColor = course ? 'bg-purple-600/20' : offer?.isProduct ? 'bg-pink-600/20' : 'bg-blue-600/20';
                              const textColor = course ? 'text-purple-300' : offer?.isProduct ? 'text-pink-300' : 'text-blue-300';
                              return (
                                <span key={articleId} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs ${bgColor} ${textColor}`}>
                                  {name}
                                  <button
                                    onClick={() => removeArticleFromExistingCode(code.id, articleId)}
                                    className="hover:text-white ml-1 font-bold"
                                    title="Retirer cet article (mise à jour immédiate)"
                                  >×</button>
                                </span>
                              );
                            })}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* NOUVEAU: Boutons Copier et Partager WhatsApp */}
                        <button 
                          onClick={() => {
                            navigator.clipboard.writeText(code.code);
                            alert(`✅ Code "${code.code}" copié !`);
                          }}
                          className="px-3 py-2 rounded-lg text-xs font-medium transition-all hover:scale-105"
                          style={{ background: 'rgba(34, 197, 94, 0.2)', color: '#22c55e', border: '1px solid rgba(34, 197, 94, 0.4)' }}
                          data-testid={`copy-code-${code.id}`}
                          title="Copier le code"
                        >
                          📋 Copier
                        </button>
                        <button 
                          onClick={() => {
                            const message = `🎁 Voici ton code promo Afroboost !\n\n💎 Code: *${code.code}*\n💰 Réduction: ${code.type === '100%' ? '100%' : `${code.value}${code.type}`}\n\n👉 Utilise-le sur afroboost.com`;
                            window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, '_blank');
                          }}
                          className="px-3 py-2 rounded-lg text-xs font-medium transition-all hover:scale-105"
                          style={{ background: 'rgba(37, 211, 102, 0.2)', color: '#25D366', border: '1px solid rgba(37, 211, 102, 0.4)' }}
                          data-testid={`share-whatsapp-${code.id}`}
                          title="Partager sur WhatsApp"
                        >
                          📤 WhatsApp
                        </button>
                        {/* Edit button */}
                        <button 
                          onClick={() => setEditingCode({...code})}
                          className="px-3 py-2 rounded-lg text-xs font-medium"
                          style={{ background: 'rgba(59, 130, 246, 0.2)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.4)' }}
                          data-testid={`edit-code-${code.id}`}
                          title="Modifier"
                        >
                          ✏️
                        </button>
                        <button onClick={() => toggleCode(code)} className={`px-4 py-2 rounded-lg text-xs font-medium ${code.active ? 'bg-green-600' : 'bg-gray-600'}`} style={{ color: 'white' }}>
                          {code.active ? `✅ ${t('active')}` : `❌ ${t('inactive')}`}
                        </button>
                        {/* Delete button - red trash icon */}
                        <button 
                          onClick={() => deleteCode(code.id)} 
                          className="delete-code-btn px-3 py-2 rounded-lg text-xs font-medium"
                          style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.4)' }}
                          data-testid={`delete-code-${code.id}`}
                          title={t('delete') || 'Supprimer'}
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
              {(codesSearch ? discountCodes.filter(c => 
                c.code?.toLowerCase().includes(codesSearch.toLowerCase()) ||
                c.assignedEmails?.some(e => e.toLowerCase().includes(codesSearch.toLowerCase()))
              ) : discountCodes).length === 0 && <p className="text-center py-8 text-white opacity-50">{codesSearch ? 'Aucun code trouvé' : t('noPromoCode')}</p>}
              </div>
            </div>
          </div>
        )}

        {/* === CAMPAIGNS TAB === */}
        {/* [CAMPAGNE_START] - Section extraite vers CampaignManager.js */}
        {tab === "campaigns" && (
          <CampaignManager
            // === ÉTATS PRINCIPAUX ===
            campaigns={campaigns}
            newCampaign={newCampaign}
            setNewCampaign={setNewCampaign}
            editingCampaignId={editingCampaignId}
            schedulerHealth={schedulerHealth}
            
            // === ÉTATS ENVOI DIRECT ===
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
            
            // === ENVOI GROUPÉ ===
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
            
            // === PREVIEW MÉDIA ===
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
            
            // === v9.0.2: CRÉDITS ===
            hasInsufficientCredits={hasInsufficientCredits}
            coachCredits={coachCredits}
          />
        )}
        {/* [CAMPAGNE_END] - Section extraite vers CampaignManager.js (~1490 lignes économisées) */}


        {/* ========== ONGLET CONVERSATIONS v9.2.0 - Extrait vers CRMSection.js ========== */}
        {tab === "conversations" && (
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
              // Community
              newCommunityName={newCommunityName}
              setNewCommunityName={setNewCommunityName}
              createCommunityChat={createCommunityChat}
              // Chat links
              chatLinks={chatLinks}
              copiedLinkId={copiedLinkId}
              copyLinkToClipboard={copyLinkToClipboard}
            deleteChatLink={deleteChatLink}
            // Conversations
            enrichedConversations={enrichedConversations}
            selectedSession={selectedSession}
            setSelectedSession={setSelectedSession}
            loadSessionMessages={loadSessionMessages}
            setSessionMode={setSessionMode}
            deleteChatSession={deleteChatSession}
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
        {/* [CONVERSATIONS_END] - Section extraite vers CRMSection.js (~940 lignes économisées) */}

        {/* ========== ONGLET MON STRIPE v8.9.5 (Coachs uniquement) ========== */}
        {tab === "stripe" && !isSuperAdmin && (
          <div className="space-y-6" data-testid="stripe-tab">
            <div className="glass rounded-xl p-6" style={{ border: '1px solid rgba(217, 28, 210, 0.3)' }}>
              <h2 className="text-xl font-bold text-white mb-4">💳 Stripe Connect</h2>
              <p className="text-white/70 mb-6">
                Connectez votre compte Stripe pour recevoir directement les paiements de vos clients.
              </p>
              
              {/* Statut actuel */}
              <div className="glass rounded-lg p-4 mb-6" style={{ background: 'rgba(255,255,255,0.05)' }}>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-white font-medium">Statut du compte</h3>
                    <p className="text-white/50 text-sm mt-1">
                      {stripeConnectStatus?.connected 
                        ? stripeConnectStatus?.charges_enabled 
                          ? 'Compte vérifié et prêt à recevoir des paiements' 
                          : 'Compte en cours de vérification'
                        : 'Non connecté'}
                    </p>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                    stripeConnectStatus?.connected 
                      ? stripeConnectStatus?.charges_enabled 
                        ? 'bg-green-500/20 text-green-400' 
                        : 'bg-yellow-500/20 text-yellow-400'
                      : 'bg-red-500/20 text-red-400'
                  }`}>
                    {stripeConnectStatus?.connected 
                      ? stripeConnectStatus?.charges_enabled ? '✓ Actif' : '⏳ En attente'
                      : '✗ Déconnecté'}
                  </span>
                </div>
              </div>
              
              {/* Bouton de connexion */}
              <button
                onClick={handleStripeConnect}
                disabled={stripeConnectLoading}
                className="w-full py-3 rounded-lg text-white font-semibold transition-all hover:scale-105 disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg, #635BFF, #8b5cf6)' }}
                data-testid="stripe-connect-tab-btn"
              >
                {stripeConnectLoading 
                  ? 'Chargement...' 
                  : stripeConnectStatus?.connected 
                    ? 'Gérer mon compte Stripe' 
                    : 'Connecter mon compte Stripe'}
              </button>
              
              {/* Info */}
              <div className="mt-6 p-4 rounded-lg" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
                <h4 className="text-white font-medium mb-2">💡 Comment ça marche ?</h4>
                <ul className="text-white/70 text-sm space-y-1 list-disc pl-5">
                  <li>Les paiements de vos clients seront versés sur votre compte</li>
                  <li>Une commission plateforme s'applique sur chaque transaction</li>
                  <li>Les virements sont automatiques sous 2-7 jours</li>
                </ul>
              </div>
            </div>
            
            {/* === v9.1.4: PERSONNALISATION MARQUE BLANCHE === */}
            <div className="glass rounded-xl p-6" style={{ border: '1px solid rgba(217, 28, 210, 0.3)' }}>
              <h2 className="text-xl font-bold text-white mb-4">🎨 Personnalisation</h2>
              <p className="text-white/70 mb-4">
                Personnalisez votre espace avec votre propre marque.
              </p>
              
              <div className="space-y-4">
                <div>
                  <label className="block text-white/70 text-sm mb-2">Nom de ma plateforme</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={coachPlatformName || ''}
                      onChange={(e) => setCoachPlatformName(e.target.value)}
                      placeholder="Ex: Mon Studio Fitness"
                      className="flex-1 px-4 py-2 rounded-lg bg-white/5 text-white border border-white/20 focus:border-purple-500 focus:outline-none"
                      data-testid="platform-name-input"
                    />
                    <button
                      onClick={async () => {
                        try {
                          await axios.put(`${BACKEND_URL}/api/coach/update-profile`, {
                            platform_name: coachPlatformName
                          }, { headers: { 'X-User-Email': coachUser?.email } });
                          alert('✓ Nom de plateforme enregistré !');
                        } catch (err) {
                          alert('Erreur lors de la sauvegarde');
                        }
                      }}
                      className="px-4 py-2 rounded-lg text-white font-medium"
                      style={{ background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)' }}
                      data-testid="save-platform-name-btn"
                    >
                      Enregistrer
                    </button>
                  </div>
                  <p className="text-white/50 text-xs mt-1">Ce nom s'affichera en haut de votre dashboard</p>
                </div>
              </div>
            </div>
            
            {/* v9.2.9: Suppression de la section "Ma Vitrine Publique" redondante - déplacée vers l'onglet "Ma Page" */}
          </div>
        )}
      </div>
    </div>
  );
};

export { CoachDashboard };

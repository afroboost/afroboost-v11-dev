import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import "@/App.css";
import axios from "axios";

// v62: Intercepteur global — injecte X-User-Email sur TOUTES les requêtes axios
axios.interceptors.request.use((config) => {
  if (!config.headers['X-User-Email']) {
    try {
      const saved = localStorage.getItem('afroboost_coach_user');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed?.email) {
          config.headers['X-User-Email'] = parsed.email;
        }
      }
    } catch (e) { /* ignore */ }
  }
  return config;
});
console.log("🚀 V71 : Social Boost — Commentaires IA & Social Proof activé");
import { QRCodeSVG } from "qrcode.react";
import { Html5Qrcode } from "html5-qrcode";
import html2canvas from "html2canvas";
import {
  getWhatsAppConfig,
  saveWhatsAppConfig,
  isWhatsAppConfigured,
  sendWhatsAppMessage,
  sendBulkWhatsApp,
  testWhatsAppConfig
} from "./services/whatsappService";
import {
  setLastMediaUrl as setLastMediaUrlService
} from "./services/aiResponseService";
import { 
  NavigationBar, 
  LandingSectionSelector,
  ScrollIndicator,
  useScrollIndicator
} from "./components/SearchBar";
import { ChatWidget } from "./components/ChatWidget";
import { CoachDashboard } from "./components/CoachDashboard";
import CoachLoginModal from "./components/CoachLoginModal";
import PaymentSuccessPage from "./components/PaymentSuccessPage";
import MediaViewer from "./components/MediaViewer";
import BecomeCoachPage from "./components/BecomeCoachPage";
import SuperAdminPanel from "./components/SuperAdminPanel";
import { CoachSearchModal } from "./components/CoachSearch";
import CoachVitrine from "./components/CoachVitrine";
import PartnersCarousel from "./components/PartnersCarousel";
import AudioPlayer from "./components/AudioPlayer";
import { useDataCache, invalidateCache } from "./hooks/useDataCache";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Configuration Admin - Vercel Compatible
// v9.5.6: Liste des Super Admins autorisés
const SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
const ADMIN_EMAIL = 'contact.artboost@gmail.com'; // Legacy
const APP_VERSION = '2.0.0';

// v9.5.6 + v41: Helper pour vérifier si un email est Super Admin
// Inclut les emails @afroboost.com + la whitelist
const isSuperAdminEmail = (email) => {
  if (!email) return false;
  const e = email.toLowerCase().trim();
  return SUPER_ADMIN_EMAILS.some(a => e === a.toLowerCase()) || e.endsWith('@afroboost.com');
};

// v42: Clé de persistance admin — ne jamais supprimer lors du logout
const ADMIN_AUTH_TOKEN_KEY = 'afroboost_admin_persist';

// v9.2.4: DÉTECTION IMMÉDIATE PROPULSION STRIPE (avant tout rendu) - MÉMOIRE MORTE
// Cette logique s'exécute AVANT React pour capturer l'intention de redirection
const detectStripeSuccess = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const hash = window.location.hash;
  
  const isSuccess = urlParams.get('success') === 'true' ||
                    urlParams.get('status') === 'success' ||
                    urlParams.get('payment') === 'success' ||
                    hash.includes('success=true') ||
                    hash.includes('welcome=true');
  
  if (isSuccess) {
    console.log('[APP] 🚀 v9.2.4 PROPULSION MÉMOIRE MORTE: Intent détecté AVANT rendu');
    // v9.2.4: MÉMOIRE MORTE - Flag persistant pour redirection post-login
    localStorage.setItem('redirect_to_dash', 'true');
    localStorage.setItem('afroboost_redirect_intent', 'dashboard');
    localStorage.setItem('afroboost_redirect_message', '🎉 Paiement validé ! Bienvenue Partenaire');

    // v11.6: Auto-session partenaire après paiement (évite reconnexion)
    try {
      const pendingStr = localStorage.getItem('afroboost_pending_partner');
      if (pendingStr) {
        const pending = JSON.parse(pendingStr);
        if (pending.email && pending.name) {
          localStorage.setItem('afroboost_coach_user', JSON.stringify({
            email: pending.email,
            name: pending.name,
            role: 'coach',
            is_coach: true
          }));
          localStorage.setItem('afroboost_coach_mode', 'true');
          console.log('[APP] 🔑 Session partenaire auto-créée:', pending.email);
        }
        localStorage.removeItem('afroboost_pending_partner');
      }
    } catch (e) {
      console.error('[APP] Erreur auto-session:', e);
    }

    // Nettoyer l'URL immédiatement
    const url = new URL(window.location.href);
    url.searchParams.delete('success');
    url.searchParams.delete('status');
    url.searchParams.delete('payment');
    url.searchParams.delete('provider');
    url.searchParams.delete('tid');
    url.searchParams.delete('session_id');
    url.searchParams.delete('welcome');
    url.hash = '#partner-dashboard';
    window.history.replaceState({}, '', url.pathname + url.hash);

    return true;
  }
  return false;
};

// v11.0: Détecter le scan QR (?qr=AFR-XXXXXX) pour auto-connecter l'abonné
const detectQRSubscriber = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const qrCode = urlParams.get('qr');
  if (qrCode && qrCode.startsWith('AFR-')) {
    console.log('[APP] 📱 QR Code détecté:', qrCode);
    localStorage.setItem('afroboost_qr_subscriber', qrCode);
    // Nettoyer l'URL
    const url = new URL(window.location.href);
    url.searchParams.delete('qr');
    window.history.replaceState({}, '', url.pathname + (url.hash || ''));
    return qrCode;
  }
  return null;
};

// Exécuter la détection immédiatement
const INITIAL_REDIRECT_INTENT = detectStripeSuccess();
const INITIAL_QR_CODE = detectQRSubscriber();

// Translations
const translations = {
  fr: {
    appTitle: "Afroboost",
    conceptDefault: "Le concept Afroboost : cardio + danse afrobeat + casques audio immersifs. Un entraînement fun, énergétique et accessible à tous.",
    chooseSession: "Choisissez votre session",
    chooseOffer: "Choisissez votre offre",
    yourInfo: "Vos informations",
    fullName: "Nom complet",
    emailRequired: "Email (obligatoire)",
    whatsappRequired: "WhatsApp (obligatoire)",
    promoCode: "Code promo",
    total: "Total",
    alreadySubscribed: "Je suis déjà abonné",
    selectProfile: "Sélectionnez votre profil...",
    acceptTerms: "J'accepte les",
    termsLink: "conditions générales",
    termsTitle: "Conditions Générales",
    quantity: "Quantité",
    payAndReserve: "💳 Payer et réserver",
    reserveFree: "Réserver gratuitement",
    loading: "Chargement...",
    copyright: "© Afroboost 2026",
    coachLogin: "Connexion Partenaire",
    email: "Email",
    password: "Mot de passe",
    login: "Se connecter",
    forgotPassword: "Mot de passe oublié ?",
    cancel: "Annuler",
    coachMode: "Mode Coach",
    back: "← Retour",
    logout: "🚪 Déconnexion",
    reservations: "Réservations",
    conceptVisual: "Concept & Visuel",
    courses: "Cours",
    offers: "Offres",
    payments: "Paiements",
    promoCodes: "Codes promo",
    reservationsList: "Liste des réservations",
    downloadCSV: "📥 Télécharger CSV",
    code: "Code",
    name: "Nom",
    date: "Date",
    time: "Heure",
    offer: "Offre",
    qty: "Qté",
    noReservations: "Aucune réservation pour le moment",
    deleteReservation: "Supprimer cette réservation",
    confirmDeleteReservation: "Êtes-vous sûr de vouloir supprimer cette réservation ?",
    addManualContact: "➕ Ajouter un contact",
    manualContactName: "Nom",
    manualContactEmail: "Email",
    manualContactWhatsapp: "WhatsApp",
    conceptDescription: "Description du concept",
    mediaUrl: "URL Média Accueil (YouTube, Vimeo, Image)",
    save: "Sauvegarder",
    courseName: "Nom du cours",
    location: "Lieu",
    mapsLink: "Lien Google Maps",
    weekday: "Jour",
    addCourse: "Ajouter un cours",
    offerName: "Nom de l'offre",
    price: "Prix (CHF)",
    visible: "Visible",
    thumbnail: "URL miniature",
    addOffer: "Ajouter une offre",
    stripeLink: "Lien Stripe",
    paypalLink: "Lien PayPal",
    twintLink: "Lien Twint",
    coachWhatsapp: "WhatsApp Coach",
    codePromo: "Code (ex: GRATUIT)",
    type: "Type",
    value: "Valeur",
    beneficiary: "Bénéficiaire",
    selectBeneficiary: "Sélectionner un client...",
    assignedEmail: "Email assigné",
    allowedCourses: "Cours autorisés",
    allCourses: "Tous les cours",
    maxUses: "Utilisations max",
    expiresAt: "Date d'expiration",
    importCSV: "Importer CSV",
    exportCSV: "Exporter CSV",
    add: "Ajouter",
    noPromoCode: "Aucun code promo",
    active: "Actif",
    inactive: "Inactif",
    used: "Utilisé",
    paymentDone: "Paiement effectué ?",
    paymentConfirmText: "Si vous avez terminé le paiement, cliquez ci-dessous pour valider.",
    confirmPayment: "✅ Confirmer mon paiement",
    reservationConfirmed: "Réservation confirmée !",
    reservationCode: "Code",
    print: "🖨️ Imprimer",
    share: "📱 Partager",
    saveTicket: "📥 Enregistrer mon ticket",
    shareWithImage: "📤 Partager avec QR",
    generatingImage: "Génération en cours...",
    emailWhatsappRequired: "L'email et le numéro WhatsApp sont obligatoires.",
    invalidPromoCode: "Code promo invalide.",
    noPaymentConfigured: "Paiement requis – réservation impossible.",
    subscriberOnlyCode: "Seuls les abonnés peuvent utiliser ce code.",
    wrongCredentials: "Email ou mot de passe incorrect",
    discount: "Réduction",
    sunday: "Dimanche", monday: "Lundi", tuesday: "Mardi", wednesday: "Mercredi",
    thursday: "Jeudi", friday: "Vendredi", saturday: "Samedi",
    logoUrl: "URL du Logo (Splash Screen & PWA)",
    offerDescription: "Description (icône \"i\")",
    confirmDelete: "Supprimer ce code ?",
    delete: "Supprimer",
    termsText: "Texte des Conditions Générales",
    termsPlaceholder: "Entrez le texte de vos conditions générales de vente...",
    scanToValidate: "Scannez pour valider",
    batchGeneration: "Génération en série",
    batchCount: "Nombre de codes",
    codePrefix: "Préfixe du code",
    generateBatch: "🚀 Générer la série",
    batchSuccess: "codes créés avec succès !",
    batchMax: "Maximum 20 codes par série",
  },
  en: {
    appTitle: "Afroboost",
    conceptDefault: "The Afroboost concept: cardio + afrobeat dance + immersive audio headsets. A fun, energetic workout for everyone.",
    chooseSession: "Choose your session",
    chooseOffer: "Choose your offer",
    yourInfo: "Your information",
    fullName: "Full name",
    emailRequired: "Email (required)",
    whatsappRequired: "WhatsApp (required)",
    promoCode: "Promo code",
    total: "Total",
    alreadySubscribed: "I'm already subscribed",
    selectProfile: "Select your profile...",
    acceptTerms: "I accept the",
    termsLink: "terms and conditions",
    termsTitle: "Terms and Conditions",
    quantity: "Quantity",
    payAndReserve: "💳 Pay and reserve",
    reserveFree: "Reserve for free",
    loading: "Loading...",
    copyright: "© Afroboost 2026",
    coachLogin: "Partner Login",
    email: "Email",
    password: "Password",
    login: "Log in",
    forgotPassword: "Forgot password?",
    cancel: "Cancel",
    coachMode: "Coach Mode",
    back: "← Back",
    logout: "🚪 Logout",
    reservations: "Reservations",
    conceptVisual: "Concept & Visual",
    courses: "Courses",
    offers: "Offers",
    payments: "Payments",
    promoCodes: "Promo codes",
    reservationsList: "Reservations list",
    downloadCSV: "📥 Download CSV",
    code: "Code",
    name: "Name",
    date: "Date",
    time: "Time",
    offer: "Offer",
    qty: "Qty",
    noReservations: "No reservations yet",
    deleteReservation: "Delete this reservation",
    confirmDeleteReservation: "Are you sure you want to delete this reservation?",
    addManualContact: "➕ Add contact",
    manualContactName: "Name",
    manualContactEmail: "Email",
    manualContactWhatsapp: "WhatsApp",
    conceptDescription: "Concept description",
    mediaUrl: "Media URL (YouTube, Vimeo, Image)",
    save: "Save",
    courseName: "Course name",
    location: "Location",
    mapsLink: "Google Maps link",
    weekday: "Day",
    addCourse: "Add course",
    offerName: "Offer name",
    price: "Price (CHF)",
    visible: "Visible",
    thumbnail: "Thumbnail URL",
    addOffer: "Add offer",
    stripeLink: "Stripe link",
    paypalLink: "PayPal link",
    twintLink: "Twint link",
    coachWhatsapp: "Coach WhatsApp",
    codePromo: "Code (e.g. FREE)",
    type: "Type",
    value: "Value",
    beneficiary: "Beneficiary",
    selectBeneficiary: "Select a customer...",
    assignedEmail: "Assigned email",
    allowedCourses: "Allowed courses",
    allCourses: "All courses",
    maxUses: "Max uses",
    expiresAt: "Expiration date",
    importCSV: "Import CSV",
    exportCSV: "Export CSV",
    add: "Add",
    noPromoCode: "No promo code",
    active: "Active",
    inactive: "Inactive",
    used: "Used",
    paymentDone: "Payment done?",
    paymentConfirmText: "If you completed the payment, click below to validate.",
    confirmPayment: "✅ Confirm my payment",
    reservationConfirmed: "Reservation confirmed!",
    reservationCode: "Code",
    print: "🖨️ Print",
    share: "📱 Share",
    saveTicket: "📥 Save my ticket",
    shareWithImage: "📤 Share with QR",
    generatingImage: "Generating...",
    emailWhatsappRequired: "Email and WhatsApp are required.",
    invalidPromoCode: "Invalid promo code.",
    noPaymentConfigured: "Payment required – reservation impossible.",
    subscriberOnlyCode: "Only subscribers can use this code.",
    wrongCredentials: "Wrong email or password",
    discount: "Discount",
    sunday: "Sunday", monday: "Monday", tuesday: "Tuesday", wednesday: "Wednesday",
    thursday: "Thursday", friday: "Friday", saturday: "Saturday",
    logoUrl: "Logo URL (Splash Screen & PWA)",
    offerDescription: "Description (\"i\" icon)",
    confirmDelete: "Delete this code?",
    delete: "Delete",
    termsText: "Terms and Conditions Text",
    termsPlaceholder: "Enter your terms and conditions text...",
    scanToValidate: "Scan to validate",
    batchGeneration: "Batch Generation",
    batchCount: "Number of codes",
    codePrefix: "Code prefix",
    generateBatch: "🚀 Generate batch",
    batchSuccess: "codes created successfully!",
    batchMax: "Maximum 20 codes per batch",
  },
  de: {
    appTitle: "Afroboost",
    conceptDefault: "Das Afroboost-Konzept: Cardio + Afrobeat-Tanz + immersive Audio-Kopfhörer. Ein spaßiges Training für alle.",
    chooseSession: "Wählen Sie Ihre Sitzung",
    chooseOffer: "Wählen Sie Ihr Angebot",
    yourInfo: "Ihre Informationen",
    fullName: "Vollständiger Name",
    emailRequired: "E-Mail (erforderlich)",
    whatsappRequired: "WhatsApp (erforderlich)",
    promoCode: "Promo-Code",
    total: "Gesamt",
    alreadySubscribed: "Ich bin bereits abonniert",
    selectProfile: "Wählen Sie Ihr Profil...",
    acceptTerms: "Ich akzeptiere die",
    termsLink: "Allgemeinen Geschäftsbedingungen",
    termsTitle: "Allgemeine Geschäftsbedingungen",
    quantity: "Menge",
    payAndReserve: "💳 Zahlen und reservieren",
    reserveFree: "Kostenlos reservieren",
    loading: "Laden...",
    copyright: "© Afroboost 2026",
    coachLogin: "Partner-Anmeldung",
    email: "E-Mail",
    password: "Passwort",
    login: "Anmelden",
    forgotPassword: "Passwort vergessen?",
    cancel: "Abbrechen",
    coachMode: "Coach-Modus",
    back: "← Zurück",
    logout: "🚪 Abmelden",
    reservations: "Reservierungen",
    conceptVisual: "Konzept & Visuell",
    courses: "Kurse",
    offers: "Angebote",
    payments: "Zahlungen",
    promoCodes: "Promo-Codes",
    reservationsList: "Reservierungsliste",
    downloadCSV: "📥 CSV herunterladen",
    code: "Code",
    name: "Name",
    date: "Datum",
    time: "Zeit",
    offer: "Angebot",
    qty: "Menge",
    noReservations: "Noch keine Reservierungen",
    deleteReservation: "Reservierung löschen",
    confirmDeleteReservation: "Möchten Sie diese Reservierung wirklich löschen?",
    addManualContact: "➕ Kontakt hinzufügen",
    manualContactName: "Name",
    manualContactEmail: "E-Mail",
    manualContactWhatsapp: "WhatsApp",
    conceptDescription: "Konzeptbeschreibung",
    mediaUrl: "Medien-URL (YouTube, Vimeo, Bild)",
    save: "Speichern",
    courseName: "Kursname",
    location: "Ort",
    mapsLink: "Google Maps Link",
    weekday: "Tag",
    addCourse: "Kurs hinzufügen",
    offerName: "Angebotsname",
    price: "Preis (CHF)",
    visible: "Sichtbar",
    thumbnail: "Miniatur-URL",
    addOffer: "Angebot hinzufügen",
    stripeLink: "Stripe-Link",
    paypalLink: "PayPal-Link",
    twintLink: "Twint-Link",
    coachWhatsapp: "Coach WhatsApp",
    codePromo: "Code (z.B. GRATIS)",
    type: "Typ",
    value: "Wert",
    beneficiary: "Begünstigter",
    selectBeneficiary: "Kunden auswählen...",
    assignedEmail: "Zugewiesene E-Mail",
    allowedCourses: "Erlaubte Kurse",
    allCourses: "Alle Kurse",
    maxUses: "Max. Nutzungen",
    expiresAt: "Ablaufdatum",
    importCSV: "CSV importieren",
    exportCSV: "CSV exportieren",
    add: "Hinzufügen",
    noPromoCode: "Kein Promo-Code",
    active: "Aktiv",
    inactive: "Inaktiv",
    used: "Verwendet",
    paymentDone: "Zahlung abgeschlossen?",
    paymentConfirmText: "Wenn Sie die Zahlung abgeschlossen haben, klicken Sie unten.",
    confirmPayment: "✅ Zahlung bestätigen",
    reservationConfirmed: "Reservierung bestätigt!",
    reservationCode: "Code",
    print: "🖨️ Drucken",
    share: "📱 Teilen",
    saveTicket: "📥 Ticket speichern",
    shareWithImage: "📤 Mit QR teilen",
    generatingImage: "Wird generiert...",
    emailWhatsappRequired: "E-Mail und WhatsApp sind erforderlich.",
    invalidPromoCode: "Ungültiger Promo-Code.",
    noPaymentConfigured: "Zahlung erforderlich.",
    subscriberOnlyCode: "Nur Abonnenten können diesen Code verwenden.",
    wrongCredentials: "Falsche E-Mail oder Passwort",
    discount: "Rabatt",
    sunday: "Sonntag", monday: "Montag", tuesday: "Dienstag", wednesday: "Mittwoch",
    thursday: "Donnerstag", friday: "Freitag", saturday: "Samstag",
    logoUrl: "Logo-URL (Splash Screen & PWA)",
    offerDescription: "Beschreibung (\"i\" Symbol)",
    confirmDelete: "Diesen Code löschen?",
    delete: "Löschen",
    termsText: "AGB-Text",
    termsPlaceholder: "Geben Sie Ihren AGB-Text ein...",
    scanToValidate: "Zum Validieren scannen",
    batchGeneration: "Serien-Generierung",
    batchCount: "Anzahl der Codes",
    codePrefix: "Code-Präfix",
    generateBatch: "🚀 Serie generieren",
    batchSuccess: "Codes erfolgreich erstellt!",
    batchMax: "Maximal 20 Codes pro Serie",
  }
};

const WEEKDAYS_MAP = {
  fr: ["Dimanche", "Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi"],
  en: ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
  de: ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"]
};

// Helper functions
function getNextOccurrences(weekday, count = 4) {
  const now = new Date();
  const results = [];
  const day = now.getDay();
  let diff = weekday - day;
  if (diff < 0) diff += 7;
  let current = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diff);
  for (let i = 0; i < count; i++) {
    results.push(new Date(current));
    current.setDate(current.getDate() + 7);
  }
  return results;
}

function formatDate(d, time, lang) {
  const formatted = d.toLocaleDateString(lang === 'de' ? 'de-CH' : lang === 'en' ? 'en-GB' : 'fr-CH', {
    weekday: "short", day: "2-digit", month: "2-digit"
  });
  return `${formatted} • ${time}`;
}

// Parse media URL (YouTube, Vimeo, Image)
function parseMediaUrl(url) {
  if (!url || typeof url !== 'string') return null;
  
  const trimmedUrl = url.trim();
  if (!trimmedUrl) return null;
  
  // YouTube - Support multiple formats
  // youtube.com/watch?v=ID, youtu.be/ID, youtube.com/embed/ID, youtube.com/v/ID
  const ytMatch = trimmedUrl.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  if (ytMatch) return { type: 'youtube', id: ytMatch[1] };
  
  // Vimeo - Support multiple formats
  const vimeoMatch = trimmedUrl.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  if (vimeoMatch) return { type: 'vimeo', id: vimeoMatch[1] };
  
  // Video files - MP4, WebM, MOV, AVI
  const videoExtensions = ['.mp4', '.webm', '.mov', '.avi', '.m4v', '.ogv'];
  const lowerUrl = trimmedUrl.toLowerCase();
  if (videoExtensions.some(ext => lowerUrl.includes(ext))) {
    return { type: 'video', url: trimmedUrl };
  }
  
  // Image - Accept all common formats and CDN URLs
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp', '.ico'];
  const imageCDNs = ['imgbb.com', 'cloudinary.com', 'imgur.com', 'unsplash.com', 'pexels.com', 'i.ibb.co'];
  
  if (imageExtensions.some(ext => lowerUrl.includes(ext)) || imageCDNs.some(cdn => lowerUrl.includes(cdn))) {
    return { type: 'image', url: trimmedUrl };
  }
  
  // Default: treat as image (many CDNs don't have extensions in URLs)
  return { type: 'image', url: trimmedUrl };
}

// Globe Icon - Clean, no background
const GlobeIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <line x1="2" y1="12" x2="22" y2="12"/>
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
  </svg>
);

// Location Icon
const LocationIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
    <circle cx="12" cy="10" r="3"/>
  </svg>
);

// Folder Icon for CSV Import
const FolderIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
  </svg>
);

// Splash Screen - Pure Black with configurable logo and PWA fallback
const SplashScreen = ({ logoUrl }) => {
  const [imgError, setImgError] = useState(false);
  // v9.3.8: Use Afroboost default logo as fallback
  const DEFAULT_LOGO = 'https://i.ibb.co/4Z7q3Tvw/file-000000005c1471f4bc77c9174753b16b.png';
  const fallbackLogo = DEFAULT_LOGO;
  const showLogo = logoUrl && !imgError;
  const showFallback = !logoUrl || imgError;
  
  return (
    <div className="splash-screen" style={{ background: '#000000' }}>
      {showLogo && (
        <img 
          src={logoUrl} 
          alt="Afroboost" 
          className="splash-logo" 
          onError={() => setImgError(true)}
        />
      )}
      {showFallback && (
        <img 
          src={fallbackLogo} 
          alt="Afroboost" 
          className="splash-logo" 
          style={{ maxWidth: '150px', maxHeight: '150px' }}
          onError={(e) => { 
            // Ultimate fallback: show emoji if PWA logo also fails
            e.target.style.display = 'none';
            e.target.parentNode.querySelector('.splash-headset-fallback').style.display = 'block';
          }}
        />
      )}
      <div className="splash-headset-fallback" style={{ display: 'none', fontSize: '80px' }}>🎧</div>
      <div className="splash-text">Afroboost</div>
    </div>
  );
};

// Language Selector - Clean without background
const LanguageSelector = ({ lang, setLang }) => {
  const [open, setOpen] = useState(false);
  const languages = [{ code: 'fr', label: 'FR' }, { code: 'en', label: 'EN' }, { code: 'de', label: 'DE' }];

  return (
    <div className="lang-selector" onClick={() => setOpen(!open)} data-testid="lang-selector">
      <GlobeIcon />
      <span style={{ color: '#FFFFFF', fontWeight: '500', fontSize: '14px' }}>{lang.toUpperCase()}</span>
      {open && (
        <div style={{
          position: 'absolute', top: '100%', right: 0, marginTop: '8px',
          background: 'rgba(0, 0, 0, 0.95)', border: '1px solid rgba(139, 92, 246, 0.4)',
          borderRadius: '8px', overflow: 'hidden', minWidth: '70px'
        }}>
          {languages.map(l => (
            <div key={l.code} onClick={(e) => { e.stopPropagation(); setLang(l.code); setOpen(false); }}
              style={{ padding: '10px 16px', color: '#FFFFFF', cursor: 'pointer', fontSize: '14px',
                background: lang === l.code ? 'rgba(139, 92, 246, 0.3)' : 'transparent' }}
              data-testid={`lang-${l.code}`}>{l.label}</div>
          ))}
        </div>
      )}
    </div>
  );
};

// Media Display Component (YouTube, Vimeo, Image, Video) - Clean display without dark overlays
// Media Display Component with Discreet Sound Control
const MediaDisplay = ({ url, className }) => {
  const [hasError, setHasError] = useState(false);
  const [isMuted, setIsMuted] = useState(true); // Muted par défaut pour garantir l'autoplay et la boucle
  const videoRef = useRef(null);
  const iframeRef = useRef(null);
  const media = parseMediaUrl(url);
  
  // Placeholder Afroboost par défaut
  const placeholderUrl = "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&h=450&fit=crop";
  
  // Return null if no valid media URL
  if (!media || !url || url.trim() === '') return null;

  // Toggle mute
  const toggleMute = (e) => {
    e.stopPropagation();
    e.preventDefault();
    const newMuted = !isMuted;
    setIsMuted(newMuted);
    
    if (videoRef.current) {
      videoRef.current.muted = newMuted;
    }
    
    // Pour YouTube, recharger l'iframe avec le nouveau paramètre mute
    if (iframeRef.current && media.type === 'youtube') {
      const currentSrc = iframeRef.current.src;
      const newSrc = currentSrc.replace(/mute=[01]/, `mute=${newMuted ? '1' : '0'}`);
      iframeRef.current.src = newSrc;
    }
  };

  // 16:9 container wrapper
  const containerStyle = {
    position: 'relative',
    width: '100%',
    paddingBottom: '56.25%',
    overflow: 'hidden',
    borderRadius: '16px',
    border: '1px solid rgba(217, 28, 210, 0.3)',
    boxShadow: '0 0 30px rgba(217, 28, 210, 0.2)',
    background: '#0a0a0a'
  };

  const contentStyle = {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%'
  };

  // Petite icône discrète en bas à droite - VISIBLE quand muted
  // z-index réduit pour ne pas passer au-dessus du widget chat (z-50)
  const smallMuteStyle = {
    position: 'absolute',
    bottom: '12px',
    right: '12px',
    zIndex: 40, // Réduit de 100 à 40 pour rester SOUS le widget chat
    padding: isMuted ? '8px 16px' : '8px',
    minWidth: isMuted ? 'auto' : '32px',
    height: '32px',
    borderRadius: isMuted ? '16px' : '50%',
    background: isMuted ? 'linear-gradient(135deg, #d91cd2 0%, #8b5cf6 100%)' : 'rgba(0, 0, 0, 0.7)',
    border: '1px solid rgba(255, 255, 255, 0.3)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    cursor: 'pointer',
    color: '#fff',
    fontSize: '14px',
    opacity: 1,
    transition: 'all 0.2s ease',
    boxShadow: isMuted ? '0 0 15px rgba(217, 28, 210, 0.5)' : '0 2px 8px rgba(0,0,0,0.3)',
    animation: isMuted ? 'pulse 2s infinite' : 'none'
  };

  // Couche transparente COMPLÈTE pour bloquer TOUS les clics vers YouTube
  const fullBlockerStyle = {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
    zIndex: 50,
    cursor: 'default',
    background: 'transparent',
    pointerEvents: 'auto'  // IMPORTANT: Capture tous les clics
  };

  if (hasError) {
    return (
      <div className={className} style={containerStyle} data-testid="media-container-placeholder">
        <img src={placeholderUrl} alt="Afroboost" style={{ ...contentStyle, objectFit: 'cover' }}/>
        <div style={{
          position: 'absolute',
          bottom: '10px',
          left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(0,0,0,0.7)',
          padding: '6px 12px',
          borderRadius: '8px',
          fontSize: '12px',
          color: 'rgba(255,255,255,0.8)'
        }}>
          ⚠️ Média non disponible
        </div>
      </div>
    );
  }

  if (media.type === 'youtube') {
    const muteParam = isMuted ? '1' : '0';
    // URL YouTube avec TOUS les paramètres pour masquer les contrôles et empêcher la sortie
    // Note: Les navigateurs bloquent autoplay+son, YouTube affiche son bouton Play
    const youtubeUrl = `https://www.youtube.com/embed/${media.id}?autoplay=1&mute=${muteParam}&loop=1&playlist=${media.id}&playsinline=1&modestbranding=1&rel=0&showinfo=0&controls=0&disablekb=1&fs=0&iv_load_policy=3&cc_load_policy=0&enablejsapi=1&origin=${encodeURIComponent(window.location.origin)}`;
    
    return (
      <div className={className} style={containerStyle} data-testid="media-container-16-9">
        <iframe 
          ref={iframeRef}
          src={youtubeUrl}
          frameBorder="0" 
          allow="autoplay; encrypted-media; accelerometer; gyroscope" 
          style={{ ...contentStyle, pointerEvents: 'none' }}
          title="YouTube video"
          onError={() => setHasError(true)}
        />
        {/* Couche transparente TOTALE pour bloquer tous les clics */}
        <div 
          style={fullBlockerStyle} 
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onTouchStart={(e) => { e.preventDefault(); e.stopPropagation(); }}
        />
        {/* Bouton mute discret au-dessus de la couche bloquante */}
        <button 
          onClick={toggleMute}
          onTouchStart={toggleMute}
          style={smallMuteStyle}
          data-testid="mute-btn"
        >
          {isMuted ? '🔇 Son' : '🔊'}
        </button>
      </div>
    );
  }
  
  if (media.type === 'vimeo') {
    const mutedParam = isMuted ? '1' : '0';
    const vimeoUrl = `https://player.vimeo.com/video/${media.id}?autoplay=1&muted=${mutedParam}&loop=1&background=1&playsinline=1&title=0&byline=0&portrait=0`;
    
    return (
      <div className={className} style={containerStyle} data-testid="media-container-16-9">
        <iframe 
          src={vimeoUrl}
          frameBorder="0" 
          allow="autoplay" 
          style={{ ...contentStyle, pointerEvents: 'none' }}
          title="Vimeo video"
          onError={() => setHasError(true)}
        />
        {/* Couche transparente TOTALE pour bloquer tous les clics */}
        <div 
          style={fullBlockerStyle} 
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onTouchStart={(e) => { e.preventDefault(); e.stopPropagation(); }}
        />
        {/* Bouton mute */}
        <button 
          onClick={toggleMute}
          onTouchStart={toggleMute}
          style={smallMuteStyle}
          data-testid="mute-btn"
        >
          {isMuted ? '🔇 Son' : '🔊'}
        </button>
      </div>
    );
  }
  
  if (media.type === 'video') {
    return (
      <div className={className} style={containerStyle} data-testid="media-container-16-9">
        <video 
          ref={videoRef}
          src={media.url} 
          autoPlay 
          loop 
          muted={isMuted}
          playsInline 
          style={{ ...contentStyle, objectFit: 'cover' }}
          onError={() => setHasError(true)}
        />
        <button 
          onClick={toggleMute}
          style={smallMuteStyle}
          data-testid="mute-btn"
        >
          {isMuted ? '🔇 Son' : '🔊'}
        </button>
      </div>
    );
  }
  
  // Image type
  return (
    <div className={className} style={containerStyle} data-testid="media-container-16-9">
      <img 
        src={media.url} 
        alt="Media" 
        style={{ ...contentStyle, objectFit: 'cover' }}
        onError={() => setHasError(true)}
      />
    </div>
  );
};

// Info Icon Component
const InfoIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/>
    <line x1="12" y1="16" x2="12" y2="12"/>
    <line x1="12" y1="8" x2="12.01" y2="8"/>
  </svg>
);

// Close Icon Component
const CloseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18"/>
    <line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
);

// Offer Card - Clean Design with Full Image + Info icon + Discrete dots navigation
const OfferCard = ({ offer, selected, onClick }) => {
  const [showDescription, setShowDescription] = useState(false);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const defaultImage = "https://picsum.photos/seed/default/400/200";
  
  // PRIORITÉ: offer.images[0] > offer.thumbnail > defaultImage
  const images = (offer.images && Array.isArray(offer.images) && offer.images.length > 0) 
    ? offer.images.filter(img => img && typeof img === 'string' && img.trim()) 
    : (offer.thumbnail && typeof offer.thumbnail === 'string' ? [offer.thumbnail] : [defaultImage]);
  
  const currentImage = images[currentImageIndex] || images[0] || defaultImage;
  const hasMultipleImages = images.length > 1;
  
  const toggleDescription = (e) => {
    e.stopPropagation();
    setShowDescription(!showDescription);
  };
  
  return (
    <div onClick={onClick} className={`offer-card rounded-xl overflow-hidden ${selected ? 'selected' : ''}`} data-testid={`offer-card-${offer.id}`}>
      <div style={{ position: 'relative', height: '140px' }}>
        {!showDescription ? (
          <>
            <img 
              src={currentImage} 
              alt={offer.name} 
              className="offer-card-image"
              onError={(e) => { e.target.src = defaultImage; }}
            />
            
            {/* Points discrets cliquables si plusieurs images */}
            {hasMultipleImages && (
              <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5" style={{ zIndex: 10 }}>
                {images.map((_, idx) => (
                  <div 
                    key={idx}
                    onClick={(e) => { e.stopPropagation(); setCurrentImageIndex(idx); }}
                    className={`w-1.5 h-1.5 rounded-full cursor-pointer transition-all ${idx === currentImageIndex ? 'bg-pink-500 scale-125' : 'bg-white/40'}`}
                  />
                ))}
              </div>
            )}
            
            {/* Info Icon (i) - Only if description exists */}
            {offer.description && (
              <div 
                className="offer-info-btn"
                onClick={toggleDescription}
                data-testid={`offer-info-${offer.id}`}
                title="Voir la description"
              >
                <InfoIcon />
              </div>
            )}
          </>
        ) : (
          <div 
            className="offer-description-panel"
            data-testid={`offer-description-panel-${offer.id}`}
          >
            <p className="offer-description-text">{offer.description}</p>
            <button 
              className="offer-close-btn"
              onClick={toggleDescription}
              data-testid={`offer-close-${offer.id}`}
              title="Fermer"
            >
              <CloseIcon />
            </button>
          </div>
        )}
      </div>
      <div className="offer-card-content">
        <h3 className="font-semibold text-white text-sm">{offer.name}</h3>
        <span className="font-bold" style={{ color: '#d91cd2', fontSize: '18px' }}>CHF {offer.price}.-</span>
      </div>
    </div>
  );
};

// Offer Card for Horizontal Slider - With LED effect, Loupe, Info icon + Discrete dots
const OfferCardSlider = ({ offer, selected, onClick }) => {
  const [showDescription, setShowDescription] = useState(false);
  const [showZoom, setShowZoom] = useState(false);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const defaultImage = "https://picsum.photos/seed/default/400/300";
  
  // PRIORITÉ: offer.images[0] > offer.thumbnail > defaultImage
  const images = (offer.images && Array.isArray(offer.images) && offer.images.length > 0) 
    ? offer.images.filter(img => img && typeof img === 'string' && img.trim()) 
    : (offer.thumbnail && typeof offer.thumbnail === 'string' ? [offer.thumbnail] : [defaultImage]);
  
  const currentImage = images[currentImageIndex] || images[0] || defaultImage;
  const hasMultipleImages = images.length > 1;
  
  const toggleDescription = (e) => {
    e.stopPropagation();
    setShowDescription(!showDescription);
  };
  
  const toggleZoom = (e) => {
    e.stopPropagation();
    setShowZoom(!showZoom);
  };
  
  const prevImage = (e) => {
    e.stopPropagation();
    setCurrentImageIndex(prev => prev > 0 ? prev - 1 : images.length - 1);
  };
  
  const nextImage = (e) => {
    e.stopPropagation();
    setCurrentImageIndex(prev => prev < images.length - 1 ? prev + 1 : 0);
  };
  
  return (
    <>
      {/* Zoom Modal - flèches uniquement dans le zoom */}
      {showZoom && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/90"
          onClick={toggleZoom}
        >
          <div className="relative max-w-4xl max-h-[90vh] p-4" onClick={e => e.stopPropagation()}>
            <img 
              src={currentImage} 
              alt={offer.name} 
              className="max-w-full max-h-[80vh] object-contain rounded-xl"
              style={{ boxShadow: '0 0 40px rgba(217, 28, 210, 0.5)' }}
            />
            
            {/* Flèches UNIQUEMENT dans le zoom */}
            {hasMultipleImages && (
              <>
                <button 
                  onClick={prevImage}
                  className="absolute left-6 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-pink-600 text-xl"
                >
                  ‹
                </button>
                <button 
                  onClick={nextImage}
                  className="absolute right-6 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full bg-black/70 text-white flex items-center justify-center hover:bg-pink-600 text-xl"
                >
                  ›
                </button>
              </>
            )}
            
            <button 
              className="absolute top-2 right-2 w-10 h-10 rounded-full bg-black/50 text-white text-2xl hover:bg-black/80 flex items-center justify-center"
              onClick={toggleZoom}
            >
              ×
            </button>
            <p className="text-center text-white mt-4 text-lg font-semibold">{offer.name}</p>
            
            {hasMultipleImages && (
              <p className="text-center text-pink-400 text-sm mt-2">{currentImageIndex + 1} / {images.length}</p>
            )}
          </div>
        </div>
      )}
      
      <div 
        className="flex-shrink-0 snap-start"
        style={{ width: '300px', minWidth: '300px', padding: '4px' }}
      >
        <div 
          onClick={onClick}
          className={`offer-card-slider rounded-xl overflow-visible cursor-pointer transition-all duration-300`}
          style={{
            boxShadow: selected 
              ? '0 0 0 3px #d91cd2, 0 0 10px rgba(217, 28, 210, 0.4)' 
              : '0 4px 20px rgba(0,0,0,0.4)',
            border: 'none',
            transform: selected ? 'scale(1.02)' : 'scale(1)',
            background: 'linear-gradient(180deg, rgba(20,10,30,0.98) 0%, rgba(5,0,15,0.99) 100%)',
            borderRadius: '16px',
            overflow: 'hidden'
          }}
          data-testid={`offer-card-${offer.id}`}
        >
          {/* Image Section - 250px HEIGHT */}
          <div style={{ position: 'relative', height: '250px', overflow: 'hidden' }}>
            {!showDescription ? (
              <>
                <img 
                  src={currentImage} 
                  alt={offer.name} 
                  className="w-full h-full"
                  style={{ objectFit: 'cover', objectPosition: 'center', height: '250px' }}
                  onError={(e) => { e.target.src = defaultImage; }}
                />
                
                {/* Points discrets cliquables - PAS de flèches */}
                {hasMultipleImages && (
                  <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5" style={{ zIndex: 15 }}>
                    {images.map((_, idx) => (
                      <div 
                        key={idx} 
                        onClick={(e) => { e.stopPropagation(); setCurrentImageIndex(idx); }}
                        className={`w-1.5 h-1.5 rounded-full cursor-pointer transition-all ${idx === currentImageIndex ? 'bg-pink-500 scale-150' : 'bg-white/40'}`}
                      />
                    ))}
                  </div>
                )}
                
                {/* Zoom Button (Loupe) - Top Left */}
                <div 
                  className="absolute top-3 left-3 w-8 h-8 rounded-full flex items-center justify-center cursor-pointer transition-all hover:scale-110"
                  style={{ 
                    background: 'rgba(0, 0, 0, 0.6)',
                    backdropFilter: 'blur(4px)'
                  }}
                  onClick={toggleZoom}
                  title="Agrandir l'image"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                    <circle cx="11" cy="11" r="8"/>
                    <path d="M21 21l-4.35-4.35"/>
                    <path d="M11 8v6M8 11h6"/>
                  </svg>
                </div>
                
                {/* Info Icon "i" - Top Right */}
                {offer.description && (
                  <div 
                    className="absolute top-3 right-3 w-7 h-7 rounded-full flex items-center justify-center cursor-pointer transition-all hover:scale-110"
                    style={{ 
                      background: 'rgba(217, 28, 210, 0.85)',
                      boxShadow: '0 0 8px rgba(217, 28, 210, 0.5)'
                    }}
                    onClick={toggleDescription}
                    data-testid={`offer-info-${offer.id}`}
                    title="Voir la description"
                  >
                    <span className="text-white text-sm font-bold">i</span>
                  </div>
                )}
                
                {/* Selected indicator */}
                {selected && (
                  <div 
                    className="absolute bottom-3 left-3 px-3 py-1 rounded-full text-xs font-bold text-white flex items-center gap-1"
                    style={{ 
                      background: 'linear-gradient(135deg, #d91cd2 0%, #8b5cf6 100%)', 
                      boxShadow: '0 0 15px rgba(217, 28, 210, 0.7)' 
                    }}
                  >
                    <span>✓</span> Sélectionné
                  </div>
                )}
              </>
            ) : (
              /* Description Panel */
              <div 
                className="w-full h-full flex flex-col justify-center p-4"
                style={{ background: 'linear-gradient(180deg, rgba(139, 92, 246, 0.95) 0%, rgba(217, 28, 210, 0.9) 100%)' }}
              >
                <p className="text-white text-sm leading-relaxed">{offer.description}</p>
                <button 
                  className="absolute top-3 right-3 w-7 h-7 rounded-full flex items-center justify-center bg-white/20 hover:bg-white/30 transition-all text-white"
                  onClick={toggleDescription}
                  title="Fermer"
                >
                  ×
                </button>
              </div>
            )}
          </div>
          
          {/* Content Section */}
          <div className="p-4">
            <p className="font-semibold text-white mb-2" style={{ fontSize: '17px' }}>{offer.name}</p>
            <div className="flex items-baseline gap-2">
              <span 
                className="text-2xl font-bold" 
                style={{ 
                  color: '#d91cd2', 
                  textShadow: selected ? '0 0 15px rgba(217, 28, 210, 0.6)' : 'none' 
                }}
              >
                CHF {offer.price}.-
              </span>
              {offer.tva > 0 && (
                <span className="text-xs text-white opacity-50">TVA {offer.tva}%</span>
              )}
            </div>
            {offer.isProduct && offer.shippingCost > 0 && (
              <p className="text-xs text-white opacity-50 mt-1">+ CHF {offer.shippingCost} frais de port</p>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

// === OFFERS SLIDER WITH AUTO-PLAY ===
// Carrousel horizontal avec défilement automatique pour montrer qu'il y a plusieurs offres
const OffersSliderAutoPlay = ({ offers, selectedOffer, onSelectOffer }) => {
  const sliderRef = useRef(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  
  // Largeur d'une carte + padding
  const CARD_WIDTH = 308; // 300px + 8px padding
  const AUTO_PLAY_INTERVAL = 3500; // 3.5 secondes entre chaque slide
  
  // Auto-play effect
  useEffect(() => {
    if (!offers || offers.length <= 1 || isPaused || selectedOffer) return;
    
    const interval = setInterval(() => {
      setCurrentIndex(prev => {
        const nextIndex = (prev + 1) % offers.length;
        // Scroll to the next card
        if (sliderRef.current) {
          sliderRef.current.scrollTo({
            left: nextIndex * CARD_WIDTH,
            behavior: 'smooth'
          });
        }
        return nextIndex;
      });
    }, AUTO_PLAY_INTERVAL);
    
    return () => clearInterval(interval);
  }, [offers, isPaused, selectedOffer]);
  
  // Reset auto-play when offers change
  useEffect(() => {
    setCurrentIndex(0);
    if (sliderRef.current) {
      sliderRef.current.scrollTo({ left: 0, behavior: 'smooth' });
    }
  }, [offers]);
  
  // Pause auto-play on user interaction
  const handleMouseEnter = () => setIsPaused(true);
  const handleMouseLeave = () => setIsPaused(false);
  const handleTouchStart = () => setIsPaused(true);
  const handleTouchEnd = () => {
    // Resume after a delay to allow swipe navigation
    setTimeout(() => setIsPaused(false), 5000);
  };
  
  // Handle manual scroll - update current index based on scroll position
  const handleScroll = () => {
    if (sliderRef.current) {
      const scrollLeft = sliderRef.current.scrollLeft;
      const newIndex = Math.round(scrollLeft / CARD_WIDTH);
      if (newIndex !== currentIndex && newIndex >= 0 && newIndex < offers.length) {
        setCurrentIndex(newIndex);
      }
    }
  };
  
  if (!offers || offers.length === 0) {
    return <p className="text-white/60 text-center py-4">Aucune offre disponible</p>;
  }
  
  return (
    <div 
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      {/* Slider Container */}
      <div 
        ref={sliderRef}
        onScroll={handleScroll}
        className="flex gap-2 overflow-x-auto snap-x snap-mandatory pb-4 hide-scrollbar"
        style={{ 
          scrollBehavior: 'smooth',
          WebkitOverflowScrolling: 'touch',
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          paddingTop: '30px',  /* Espace pour que le glow ne soit pas coupé - 30px */
          marginTop: '-10px'   /* Compense partiellement le padding pour l'alignement */
        }}
        data-testid="offers-slider"
      >
        {offers.map((offer) => (
          <OfferCardSlider
            key={offer.id}
            offer={offer}
            selected={selectedOffer?.id === offer.id}
            onClick={() => onSelectOffer(offer)}
          />
        ))}
      </div>
      
      {/* Indicateurs de pagination (points) - Visibles uniquement s'il y a plusieurs offres */}
      {offers.length > 1 && (
        <div className="flex justify-center gap-2 mt-2">
          {offers.map((_, idx) => (
            <button
              key={idx}
              onClick={() => {
                setCurrentIndex(idx);
                setIsPaused(true);
                if (sliderRef.current) {
                  sliderRef.current.scrollTo({
                    left: idx * CARD_WIDTH,
                    behavior: 'smooth'
                  });
                }
                // Resume after delay
                setTimeout(() => setIsPaused(false), 5000);
              }}
              className={`transition-all duration-300 rounded-full ${
                idx === currentIndex 
                  ? 'w-6 h-2 bg-pink-500' 
                  : 'w-2 h-2 bg-white/30 hover:bg-white/50'
              }`}
              aria-label={`Aller à l'offre ${idx + 1}`}
              data-testid={`offer-dot-${idx}`}
            />
          ))}
        </div>
      )}
      
      {/* Indicateur visuel d'auto-play actif */}
      {offers.length > 1 && !selectedOffer && !isPaused && (
        <div className="absolute top-2 right-2 flex items-center gap-1 px-2 py-1 rounded-full bg-black/50 text-xs text-white/70">
          <span className="w-1.5 h-1.5 rounded-full bg-pink-500 animate-pulse"></span>
          Auto
        </div>
      )}
    </div>
  );
};

// QR Scanner Modal with Camera Support - Enhanced Version
const QRScannerModal = ({ onClose, onValidate, scanResult, scanError, onManualValidation }) => {
  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [manualMode, setManualMode] = useState(false);
  const [permissionStatus, setPermissionStatus] = useState('unknown'); // unknown, granted, denied
  const [initializingCamera, setInitializingCamera] = useState(false);
  const scannerRef = useRef(null);
  const html5QrCodeRef = useRef(null);

  // Check camera permissions - Enhanced with direct getUserMedia test
  const checkCameraPermission = async () => {
    try {
      // Check if we're on HTTPS (required for camera access)
      const isLocalhost = window.location.hostname === 'localhost' || 
                          window.location.hostname === '127.0.0.1' ||
                          window.location.hostname.includes('.local');
      const isSecure = window.location.protocol === 'https:' || isLocalhost;
      
      if (!isSecure) {
        setCameraError("Le scan caméra nécessite une connexion HTTPS sécurisée.");
        setManualMode(true);
        return false;
      }

      // Check if mediaDevices is available
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setCameraError("Votre navigateur ne supporte pas l'accès à la caméra.");
        setManualMode(true);
        return false;
      }

      // Try to get permission status via Permissions API first
      if (navigator.permissions && navigator.permissions.query) {
        try {
          const result = await navigator.permissions.query({ name: 'camera' });
          setPermissionStatus(result.state);
          if (result.state === 'denied') {
            setCameraError("L'accès à la caméra a été refusé. Autorisez l'accès dans les paramètres de votre navigateur, puis réessayez.");
            return false;
          }
        } catch (e) {
          // Permission query not supported (e.g., Safari), continue anyway
          console.log("Permissions API not supported, continuing...");
        }
      }
      return true;
    } catch (err) {
      console.error("Permission check error:", err);
      return true; // Try anyway
    }
  };

  // Direct camera test before using html5-qrcode
  const testCameraAccess = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: { facingMode: 'environment' } 
      });
      // Successfully got access, stop the stream immediately
      stream.getTracks().forEach(track => track.stop());
      return true;
    } catch (err) {
      console.error("Direct camera test failed:", err);
      return false;
    }
  };

  // Start camera scanning with enhanced error handling
  const startScanning = async () => {
    setCameraError(null);
    setInitializingCamera(true);
    
    // Check permissions first
    const canProceed = await checkCameraPermission();
    if (!canProceed) {
      setInitializingCamera(false);
      return;
    }

    // Direct camera access test
    const cameraWorks = await testCameraAccess();
    if (!cameraWorks) {
      setCameraError("Impossible d'accéder à la caméra. Vérifiez les permissions et réessayez.");
      setInitializingCamera(false);
      return;
    }

    setScanning(true);
    setInitializingCamera(false);
    
    try {
      // Wait for the DOM element to be ready
      await new Promise(resolve => setTimeout(resolve, 100));
      
      const readerElement = document.getElementById("qr-reader");
      if (!readerElement) {
        throw new Error("Scanner container not found");
      }

      // IMPORTANT: Stop any previous session first using getState()
      if (html5QrCodeRef.current) {
        try {
          // getState(): 0 = NOT_STARTED, 1 = SCANNING, 2 = PAUSED
          if (html5QrCodeRef.current.getState && html5QrCodeRef.current.getState() !== 0) {
            await html5QrCodeRef.current.stop();
          }
          html5QrCodeRef.current = null;
        } catch (e) {
          console.log("Clearing previous session:", e);
          html5QrCodeRef.current = null;
        }
      }

      const html5QrCode = new Html5Qrcode("qr-reader");
      html5QrCodeRef.current = html5QrCode;
      
      // Get available cameras
      let cameras = [];
      try {
        cameras = await Html5Qrcode.getCameras();
      } catch (camErr) {
        console.error("Camera enumeration error:", camErr);
        // Fallback: try with facingMode constraint
        await html5QrCode.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 200, height: 200 }, aspectRatio: 1.0 },
          handleQrCodeSuccess,
          () => {}
        );
        setPermissionStatus('granted');
        return;
      }
      
      if (!cameras || cameras.length === 0) {
        // Try facingMode fallback
        await html5QrCode.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 200, height: 200 }, aspectRatio: 1.0 },
          handleQrCodeSuccess,
          () => {}
        );
        setPermissionStatus('granted');
        return;
      }
      
      // Prefer back camera on mobile (usually last in list)
      const backCamera = cameras.find(c => c.label?.toLowerCase().includes('back') || c.label?.toLowerCase().includes('arrière'));
      const cameraId = backCamera?.id || (cameras.length > 1 ? cameras[cameras.length - 1].id : cameras[0].id);
      
      await html5QrCode.start(
        cameraId,
        {
          fps: 10,
          qrbox: { width: 200, height: 200 },
          aspectRatio: 1.0
        },
        handleQrCodeSuccess,
        () => {} // Ignore scan errors (expected when no QR visible)
      );
      
      setPermissionStatus('granted');
    } catch (err) {
      console.error("Camera error:", err);
      handleCameraError(err);
      setScanning(false);
    }
  };

  // Handle QR code detection
  const handleQrCodeSuccess = (decodedText) => {
    // QR code detected - extract reservation code from URL
    let code = decodedText;
    if (decodedText.includes('/validate/')) {
      code = decodedText.split('/validate/').pop().toUpperCase();
    } else if (decodedText.includes('AFR-')) {
      // Extract AFR-XXXXXX pattern
      const match = decodedText.match(/AFR-[A-Z0-9]+/i);
      if (match) code = match[0].toUpperCase();
    }
    
    // Stop scanning and validate
    stopScanning();
    if (code) {
      onValidate(code);
    }
  };

  // Handle camera errors with user-friendly messages
  const handleCameraError = (err) => {
    const errString = err?.message || err?.toString() || '';
    let errorMessage = "Impossible d'accéder à la caméra.";
    
    if (errString.includes('Permission') || errString.includes('NotAllowed')) {
      errorMessage = "Permission caméra refusée. Autorisez l'accès dans les paramètres de votre navigateur, puis réessayez.";
      setPermissionStatus('denied');
    } else if (errString.includes('NotFound') || errString.includes('détectée') || errString.includes('No video')) {
      errorMessage = "Aucune caméra détectée sur cet appareil.";
    } else if (errString.includes('NotReadable') || errString.includes('already in use') || errString.includes('AbortError')) {
      errorMessage = "La caméra est déjà utilisée. Fermez les autres applications utilisant la caméra et réessayez.";
    } else if (errString.includes('OverconstrainedError')) {
      errorMessage = "Votre caméra ne supporte pas les paramètres requis. Essayez un autre appareil.";
    }
    
    setCameraError(errorMessage);
  };

  // Retry camera access
  const retryCamera = async () => {
    setCameraError(null);
    setManualMode(false);
    // Small delay before retry
    setTimeout(() => startScanning(), 300);
  };

  // Stop camera scanning
  const stopScanning = () => {
    if (html5QrCodeRef.current) {
      html5QrCodeRef.current.stop().catch(() => {});
      html5QrCodeRef.current = null;
    }
    setScanning(false);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (html5QrCodeRef.current) {
        html5QrCodeRef.current.stop().catch(() => {});
      }
    };
  }, []);

  // Handle close
  const handleClose = () => {
    stopScanning();
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content glass rounded-xl p-6 max-w-md w-full neon-border" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-xl font-bold text-white">📷 Scanner un ticket</h3>
          <button onClick={handleClose} className="text-2xl text-white hover:text-purple-400">×</button>
        </div>
        
        {/* Success Result */}
        {scanResult?.success && (
          <div className="p-4 rounded-lg bg-green-600/30 border border-green-500 mb-4 animate-pulse">
            <div className="flex items-center gap-3">
              <span className="text-5xl">✅</span>
              <div>
                <p className="text-white font-bold text-xl">Ticket validé !</p>
                <p className="text-green-300 text-lg">{scanResult.reservation?.userName}</p>
                <p className="text-green-300 text-sm">{scanResult.reservation?.reservationCode}</p>
              </div>
            </div>
          </div>
        )}
        
        {/* Error */}
        {scanError && (
          <div className="p-4 rounded-lg bg-red-600/30 border border-red-500 mb-4">
            <p className="text-red-300">❌ {scanError}</p>
          </div>
        )}
        
        {/* Camera Error with Retry Button */}
        {cameraError && (
          <div className="p-4 rounded-lg bg-yellow-600/30 border border-yellow-500 mb-4">
            <p className="text-yellow-300 text-sm mb-3">⚠️ {cameraError}</p>
            <button 
              onClick={retryCamera}
              className="w-full py-2 rounded-lg bg-yellow-600 hover:bg-yellow-700 text-white text-sm flex items-center justify-center gap-2"
            >
              🔄 Réessayer l'accès caméra
            </button>
          </div>
        )}
        
        {/* Camera Scanner */}
        {!scanResult?.success && !manualMode && (
          <div className="mb-4">
            {/* Initializing Camera Indicator */}
            {initializingCamera && (
              <div className="flex flex-col items-center justify-center py-8 mb-4">
                <div className="animate-spin rounded-full h-12 w-12 border-4 border-purple-500 border-t-transparent mb-4"></div>
                <p className="text-white text-sm">Initialisation de la caméra...</p>
              </div>
            )}
            
            <div 
              id="qr-reader" 
              ref={scannerRef}
              className="rounded-lg overflow-hidden mb-4"
              style={{ 
                width: '300px', 
                height: scanning ? '300px' : '0px',
                minHeight: scanning ? '300px' : '0px',
                background: scanning ? '#000' : 'transparent',
                display: initializingCamera ? 'none' : 'block',
                margin: '0 auto'
              }}
            />
            
            {!scanning && !initializingCamera ? (
              <button 
                onClick={startScanning}
                className="w-full py-4 rounded-lg btn-primary flex items-center justify-center gap-2 text-lg"
                data-testid="start-camera-btn"
              >
                📷 Activer la caméra
              </button>
            ) : (
              <button 
                onClick={stopScanning}
                className="w-full py-3 rounded-lg bg-red-600 hover:bg-red-700 text-white"
              >
                ⏹ Arrêter le scan
              </button>
            )}
            
            <button 
              onClick={() => { stopScanning(); setManualMode(true); }}
              className="w-full mt-3 py-2 rounded-lg glass text-white text-sm opacity-70 hover:opacity-100"
            >
              ⌨️ Saisie manuelle
            </button>
          </div>
        )}
        
        {/* Manual code input (fallback) */}
        {!scanResult?.success && manualMode && (
          <div>
            <form onSubmit={onManualValidation} className="space-y-4">
              <p className="text-white text-sm opacity-70">Entrez le code de réservation :</p>
              <input 
                type="text" 
                name="code"
                placeholder="AFR-XXXXXX"
                className="w-full px-4 py-3 rounded-lg neon-input uppercase text-center text-xl tracking-widest"
                autoFocus
                data-testid="manual-code-input"
              />
              <button type="submit" className="w-full py-3 rounded-lg btn-primary" data-testid="validate-code-btn">
                ✓ Valider le ticket
              </button>
            </form>
            <button 
              onClick={() => setManualMode(false)}
              className="w-full mt-3 py-2 rounded-lg glass text-white text-sm opacity-70 hover:opacity-100"
            >
              📷 Retour au scan caméra
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

// CoachLoginModal is now imported from ./components/CoachLoginModal

// Event Poster Modal (Popup d'accueil)
const EventPosterModal = ({ mediaUrl, onClose }) => {
  const [mediaType, setMediaType] = useState('image');
  
  useEffect(() => {
    if (!mediaUrl) return;
    const url = mediaUrl.toLowerCase();
    if (url.includes('youtube.com') || url.includes('youtu.be') || url.includes('vimeo.com')) {
      setMediaType('video');
    } else {
      setMediaType('image');
    }
  }, [mediaUrl]);
  
  // Parse video URL
  const getVideoEmbed = () => {
    if (!mediaUrl) return null;
    
    if (mediaUrl.includes('youtu.be')) {
      const id = mediaUrl.split('/').pop().split('?')[0];
      return `https://www.youtube.com/embed/${id}?autoplay=1&mute=1`;
    }
    if (mediaUrl.includes('youtube.com')) {
      const urlParams = new URLSearchParams(new URL(mediaUrl).search);
      const id = urlParams.get('v');
      return `https://www.youtube.com/embed/${id}?autoplay=1&mute=1`;
    }
    if (mediaUrl.includes('vimeo.com')) {
      const id = mediaUrl.split('/').pop();
      return `https://player.vimeo.com/video/${id}?autoplay=1&muted=1`;
    }
    return null;
  };
  
  if (!mediaUrl) return null;
  
  return (
    <div 
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4"
      style={{ background: 'rgba(0, 0, 0, 0.85)' }}
      onClick={onClose}
    >
      <div 
        className="relative max-w-2xl w-full rounded-xl overflow-hidden"
        style={{ 
          background: 'linear-gradient(180deg, #0a0a0f 0%, #1a0a1f 100%)',
          border: '2px solid rgba(217, 28, 210, 0.5)',
          boxShadow: '0 0 30px rgba(217, 28, 210, 0.3)'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button 
          onClick={onClose}
          className="absolute top-3 right-3 z-10 w-10 h-10 rounded-full flex items-center justify-center transition-all hover:scale-110"
          style={{ 
            background: 'rgba(0, 0, 0, 0.7)',
            border: '1px solid rgba(255, 255, 255, 0.3)'
          }}
          data-testid="close-event-poster"
        >
          <span className="text-white text-2xl font-light">×</span>
        </button>
        
        {/* Media Content */}
        <div className="w-full">
          {mediaType === 'video' ? (
            <div className="aspect-video">
              <iframe 
                src={getVideoEmbed()}
                className="w-full h-full"
                frameBorder="0"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                title="Event poster"
              />
            </div>
          ) : (
            <img 
              src={mediaUrl} 
              alt="Événement Afroboost"
              className="w-full h-auto max-h-[80vh] object-contain"
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          )}
        </div>
      </div>
    </div>
  );
};

// Success Overlay with Image Share Functionality
const SuccessOverlay = ({ t, data, onClose, onClearTicket }) => {
  const ticketRef = useRef(null);
  const [isGenerating, setIsGenerating] = useState(false);
  
  // URL officielle du site
  const AFROBOOST_URL = 'https://afroboost.com';
  
  const handlePrint = () => window.print();
  
  // Generate ticket image using html2canvas
  const generateTicketImage = async () => {
    if (!ticketRef.current) return null;
    setIsGenerating(true);
    try {
      const canvas = await html2canvas(ticketRef.current, {
        backgroundColor: '#1a0a1f',
        scale: 2,
        useCORS: true,
        logging: false
      });
      return canvas;
    } catch (err) {
      console.error('Error generating image:', err);
      return null;
    } finally {
      setIsGenerating(false);
    }
  };
  
  // Download ticket as image
  const handleSaveTicket = async () => {
    const canvas = await generateTicketImage();
    if (canvas) {
      const link = document.createElement('a');
      link.download = `ticket-afroboost-${data.reservationCode}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
    }
  };
  
  // Text message for WhatsApp with site URL
  const getShareMessage = () => {
    return `🎧 ${t('reservationConfirmed')}\n\n👤 ${t('name')}: ${data.userName}\n📧 ${t('email')}: ${data.userEmail}\n💰 ${t('offer')}: ${data.offerName}\n💵 ${t('total')}: CHF ${data.totalPrice}\n📅 ${t('courses')}: ${data.courseName}\n🎫 ${t('code')}: ${data.reservationCode}\n\n🔗 ${AFROBOOST_URL}`;
  };
  
  // Share with image - uses Web Share API if available, otherwise fallback
  const handleShareWithImage = async () => {
    const canvas = await generateTicketImage();
    if (!canvas) {
      handleTextShare();
      return;
    }
    
    // Convert canvas to blob
    canvas.toBlob(async (blob) => {
      if (!blob) {
        handleTextShare();
        return;
      }
      
      const file = new File([blob], `ticket-afroboost-${data.reservationCode}.png`, { type: 'image/png' });
      const shareData = {
        title: `🎧 ${t('reservationConfirmed')}`,
        text: `${t('reservationCode')}: ${data.reservationCode}\n${AFROBOOST_URL}`,
        files: [file]
      };
      
      // Check if Web Share API with files is supported (mobile mainly)
      if (navigator.canShare && navigator.canShare(shareData)) {
        try {
          await navigator.share(shareData);
          return; // Success, exit
        } catch (err) {
          if (err.name === 'AbortError') return; // User cancelled
        }
      }
      
      // Fallback for PC/browsers without file share support:
      // 1. Save the image
      // 2. Open WhatsApp Web with text + URL
      const link = document.createElement('a');
      link.download = `ticket-afroboost-${data.reservationCode}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
      
      // v9.4.3: Ne plus ouvrir WhatsApp automatiquement après téléchargement
      // Le client reste sur Afroboost.com
    }, 'image/png');
  };
  
  // NEW: Share on WhatsApp with image + specific text
  const handleShareWhatsApp = async () => {
    const canvas = await generateTicketImage();
    if (!canvas) {
      // Fallback to text-only if image fails
      window.open(`https://wa.me/?text=${encodeURIComponent('Voici ma réservation Afroboost : https://afroboost.com')}`, '_blank');
      return;
    }
    
    canvas.toBlob(async (blob) => {
      if (!blob) {
        window.open(`https://wa.me/?text=${encodeURIComponent('Voici ma réservation Afroboost : https://afroboost.com')}`, '_blank');
        return;
      }
      
      const file = new File([blob], `ticket-afroboost-${data.reservationCode}.png`, { type: 'image/png' });
      const shareData = {
        title: 'Ma réservation Afroboost',
        text: 'Voici ma réservation Afroboost : https://afroboost.com',
        files: [file]
      };
      
      // Use Web Share API if available (mobile)
      if (navigator.canShare && navigator.canShare(shareData)) {
        try {
          await navigator.share(shareData);
          return;
        } catch (err) {
          if (err.name === 'AbortError') return;
        }
      }
      
      // Fallback for PC: download image ONLY (v9.4.3: no auto WhatsApp)
      const link = document.createElement('a');
      link.download = `ticket-afroboost-${data.reservationCode}.png`;
      link.href = canvas.toDataURL('image/png');
      link.click();
      
      // v9.4.3: Le bouton WhatsApp est disponible mais NON automatique
    }, 'image/png');
  };
  
  // Text-only share (fallback) - includes afroboost.com URL
  const handleTextShare = () => {
    window.open(`https://wa.me/?text=${encodeURIComponent(getShareMessage())}`, '_blank');
  };

  // QR Code contains the validation URL for coach scanning
  const validationUrl = `${window.location.origin}/validate/${data.reservationCode}`;

  return (
    <div className="success-overlay">
      <div className="success-message glass rounded-xl p-6 max-w-md w-full text-center neon-border relative print-proof">
        <button onClick={onClose} className="absolute top-3 right-4 text-2xl text-white" data-testid="close-success">×</button>
        
        {/* Ticket content - captured for image */}
        <div ref={ticketRef} className="ticket-capture-zone" style={{ padding: '16px', background: 'linear-gradient(180deg, #1a0a1f 0%, #0d0510 100%)', borderRadius: '12px' }}>
          <div style={{ fontSize: '48px' }}>🎧</div>
          <p className="font-bold text-white my-2" style={{ fontSize: '20px' }}>{t('reservationConfirmed')}</p>
          
          {/* QR Code for coach validation - contains validation URL */}
          <div className="my-4 p-4 rounded-lg bg-white flex flex-col items-center">
            <QRCodeSVG 
              value={validationUrl} 
              size={150} 
              level="H"
              includeMargin={true}
              bgColor="#ffffff"
              fgColor="#000000"
            />
            <p className="text-xs text-gray-600 mt-2">{t('scanToValidate') || 'Scannez pour valider'}</p>
          </div>
          
          <div className="my-3 p-3 rounded-lg bg-white/10 border-2 border-dashed" style={{ borderColor: '#d91cd2' }}>
            <p className="text-xs text-white opacity-60">{t('reservationCode')}:</p>
            <p className="text-2xl font-bold tracking-widest text-white" data-testid="reservation-code">{data.reservationCode}</p>
          </div>
          <div className="text-sm text-left space-y-1 text-white opacity-80">
            <p><strong>{t('name')}:</strong> {data.userName}</p>
            <p><strong>{t('courses')}:</strong> {data.courseName}</p>
            {/* Afficher les variantes si présentes */}
            {data.variantsText && (
              <p><strong>Options:</strong> {data.variantsText}</p>
            )}
            <p><strong>{t('total')}:</strong> CHF {data.totalPrice}{data.quantity > 1 ? ` (x${data.quantity})` : ''}</p>
          </div>
          
          {/* Afroboost branding in ticket */}
          <p className="text-xs text-white/40 mt-4">afroboost.com</p>
        </div>
        
        {/* Action buttons - outside capture zone */}
        <div className="mt-4 space-y-3">
          {/* v9.4.3: Primary action - Enregistrer le ticket (priorité) */}
          <div className="flex gap-2">
            <button 
              onClick={handleSaveTicket} 
              disabled={isGenerating}
              className="flex-1 p-3 rounded-lg font-semibold text-white transition-all"
              style={{ 
                background: 'linear-gradient(135deg, #d91cd2 0%, #8b5cf6 100%)',
                boxShadow: '0 0 15px rgba(217, 28, 210, 0.4)'
              }}
              data-testid="save-ticket-btn"
            >
              {isGenerating ? t('generatingImage') : '📥 ' + t('saveTicket')}
            </button>
          </div>
          
          {/* v9.4.3: Secondary actions - Optionnelles (sans auto-redirect WhatsApp) */}
          <div className="flex gap-2">
            <button 
              onClick={handleShareWhatsApp} 
              disabled={isGenerating}
              className="flex-1 p-2 rounded-lg text-sm text-white/70 hover:text-white transition-all glass"
              data-testid="share-whatsapp-btn"
            >
              📤 Partager
            </button>
            <button onClick={handlePrint} className="flex-1 p-2 glass rounded-lg text-white/70 hover:text-white text-sm">
              🖨️ {t('print')}
            </button>
          </div>
          
          {/* Bouton Fermer et effacer - supprime le ticket du localStorage */}
          {onClearTicket && (
            <button 
              onClick={onClearTicket}
              className="w-full p-2 rounded-lg text-white/60 text-sm hover:text-white hover:bg-white/10 transition-all flex items-center justify-center gap-2"
              data-testid="clear-ticket-btn"
            >
              <span>🗑️</span>
              <span>Fermer et effacer le ticket</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

// Confirm Payment Overlay
const ConfirmPaymentOverlay = ({ t, onConfirm, onCancel }) => (
  <div className="modal-overlay">
    <div className="modal-content glass rounded-xl p-6 max-w-md w-full text-center neon-border">
      <div style={{ fontSize: '48px' }}>💳</div>
      <p className="font-bold text-white my-4" style={{ fontSize: '20px' }}>{t('paymentDone')}</p>
      <p className="mb-6 text-white opacity-80 text-sm">{t('paymentConfirmText')}</p>
      <button onClick={onConfirm} className="w-full btn-primary py-3 rounded-lg font-bold mb-3">{t('confirmPayment')}</button>
      <button onClick={onCancel} className="w-full py-2 glass rounded-lg text-white opacity-60">{t('cancel')}</button>
    </div>
  </div>
);

// Main App
function App() {
  const [lang, setLang] = useState(localStorage.getItem("af_lang") || "fr");
  const [showSplash, setShowSplash] = useState(true);
  const [showCoachLogin, setShowCoachLogin] = useState(false);
  
  // === PERSISTANCE SESSION COACH ===
  const [coachMode, setCoachMode] = useState(() => {
    try {
      const savedCoachMode = localStorage.getItem('afroboost_coach_mode');
      const savedCoachUser = localStorage.getItem('afroboost_coach_user');
      if (savedCoachMode === 'true' && savedCoachUser) {
        console.log('[APP] ✅ Session coach restaurée');
        return true;
      }
      // v41: Fallback — restauration automatique via token admin persistant
      const adminToken = localStorage.getItem(ADMIN_AUTH_TOKEN_KEY);
      if (adminToken) {
        const parsed = JSON.parse(adminToken);
        if (parsed?.email && isSuperAdminEmail(parsed.email)) {
          localStorage.setItem('afroboost_coach_mode', 'true');
          localStorage.setItem('afroboost_coach_user', JSON.stringify(parsed));
          console.log('[APP] 🔑 Session admin auto-restaurée via token persistant:', parsed.email);
          return true;
        }
      }
    } catch (e) {}
    return false;
  });
  const [coachUser, setCoachUser] = useState(() => {
    try {
      const savedCoachUser = localStorage.getItem('afroboost_coach_user');
      if (savedCoachUser) {
        const user = JSON.parse(savedCoachUser);
        console.log('[APP] ✅ Utilisateur coach restauré:', user?.email);
        return user;
      }
      // v41: Fallback — restauration via token admin
      const adminToken = localStorage.getItem(ADMIN_AUTH_TOKEN_KEY);
      if (adminToken) {
        const parsed = JSON.parse(adminToken);
        if (parsed?.email && isSuperAdminEmail(parsed.email)) {
          return parsed;
        }
      }
    } catch (e) {}
    return null;
  });
  const [validationCode, setValidationCode] = useState(null); // For /validate/:code URL
  const [loginWelcomeMessage, setLoginWelcomeMessage] = useState(null); // v9.1.8: Message de bienvenue après paiement
  
  // === SYSTÈME MULTI-COACH v8.9 ===
  const [showBecomeCoach, setShowBecomeCoach] = useState(false);
  const [showSuperAdminPanel, setShowSuperAdminPanel] = useState(false);
  const [userRole, setUserRole] = useState(null); // 'super_admin', 'coach', 'user'
  const [showCoachSearch, setShowCoachSearch] = useState(false); // v8.9.4: Modal recherche coach
  const [showCoachVitrine, setShowCoachVitrine] = useState(null); // v8.9.6: Username du coach pour vitrine
  
  // === v9.2.8: PLATFORM SETTINGS - Contrôles globaux ===
  const [platformSettings, setPlatformSettings] = useState({
    partner_access_enabled: true,
    maintenance_mode: false
  });
  
  // v9.2.8: Charger les settings au démarrage
  useEffect(() => {
    const loadPlatformSettings = async () => {
      try {
        const res = await axios.get(`${API}/platform-settings`);
        setPlatformSettings({
          partner_access_enabled: res.data?.partner_access_enabled ?? true,
          maintenance_mode: res.data?.maintenance_mode ?? false
        });
        console.log('[PLATFORM] Settings chargés:', res.data);
      } catch (err) {
        console.log('[PLATFORM] Settings par défaut utilisés');
      }
    };
    loadPlatformSettings();
  }, []);

  const [courses, setCourses] = useState([]);
  const [offers, setOffers] = useState([]);
  const [users, setUsers] = useState([]);
  const [studioAudioTracks, setStudioAudioTracks] = useState([]); // v53: pistes audio autonomes (Studio Audio)
  const [selectedAudioTracks, setSelectedAudioTracks] = useState([]); // v57: sélection multiple audio
  const [audioLightbox, setAudioLightbox] = useState(null); // v57: modale miniature audio {track}
  const [paymentLinks, setPaymentLinks] = useState({ stripe: "", paypal: "", twint: "", coachWhatsapp: "" });
  const [concept, setConcept] = useState({ appName: "Afroboost", description: "", heroImageUrl: "", logoUrl: "", faviconUrl: "", termsText: "", googleReviewsUrl: "", defaultLandingSection: "sessions", externalLink1Title: "", externalLink1Url: "", externalLink2Title: "", externalLink2Url: "", paymentTwint: false, paymentPaypal: false, paymentCreditCard: false, eventPosterEnabled: false, eventPosterMediaUrl: "" });
  const [showEventPoster, setShowEventPoster] = useState(false);
  const [discountCodes, setDiscountCodes] = useState([]);

  // ========== AUDIO PLAYER STATE ==========
  const [showAudioPlayer, setShowAudioPlayer] = useState(false);
  const [audioFeatureEnabled, setAudioFeatureEnabled] = useState(false);
  const [currentTrackIndex, setCurrentTrackIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioVolume, setAudioVolume] = useState(0.7);
  const audioRef = useRef(null);

  // Vérifier si le feature flag Audio est activé
  useEffect(() => {
    const checkAudioFeature = async () => {
      try {
        const response = await axios.get(`${API}/feature-flags`);
        setAudioFeatureEnabled(response.data?.AUDIO_SERVICE_ENABLED || false);
      } catch (err) {
        console.log('Feature flags not available');
        setAudioFeatureEnabled(false);
      }
    };
    checkAudioFeature();
  }, []);

  const [selectedCourse, setSelectedCourse] = useState(null);
  const [selectedDates, setSelectedDates] = useState([]); // MULTI-SELECT: Array de dates sélectionnées
  const [selectedOffer, setSelectedOffer] = useState(null);
  const [selectedSession, setSelectedSession] = useState(null);
  const [quantity, setQuantity] = useState(1); // Quantité pour achats multiples
  const [showTermsModal, setShowTermsModal] = useState(false); // Modal CGV
  const [selectedVariants, setSelectedVariants] = useState({}); // Variantes sélectionnées { size: "M", color: "Noir" }

  const [userName, setUserName] = useState("");
  const [userEmail, setUserEmail] = useState("");
  const [userWhatsapp, setUserWhatsapp] = useState("");
  const [shippingAddress, setShippingAddress] = useState(""); // Adresse de livraison pour produits physiques
  const [discountCode, setDiscountCode] = useState("");
  const [hasAcceptedTerms, setHasAcceptedTerms] = useState(false);
  const [promoMessage, setPromoMessage] = useState({ type: '', text: '' }); // New: dedicated promo message

  // Toggle une date dans la sélection multiple
  const toggleDateSelection = (date) => {
    setSelectedDates(prev => {
      if (prev.includes(date)) {
        return prev.filter(d => d !== date); // Enlever si déjà sélectionnée
      } else {
        return [...prev, date]; // Ajouter sinon
      }
    });
  };

  const [showSuccess, setShowSuccess] = useState(false);
  const [showConfirmPayment, setShowConfirmPayment] = useState(false);
  const [showPaymentSuccessPage, setShowPaymentSuccessPage] = useState(false); // Page de succès Stripe
  const [validationMessage, setValidationMessage] = useState("");
  const [pendingReservation, setPendingReservation] = useState(null);
  const [lastReservation, setLastReservation] = useState(null);
  const [loading, setLoading] = useState(false);
  const [appliedDiscount, setAppliedDiscount] = useState(null);
  const [hasSavedTicket, setHasSavedTicket] = useState(false); // Bouton flottant "Voir mon ticket"

  // Navigation et filtrage
  const [activeFilter, setActiveFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  
  // Indicateur de scroll pour les nouveaux utilisateurs
  const showScrollIndicator = useScrollIndicator();

  // PERSISTANCE TICKET: Vérifier s'il existe un ticket sauvegardé au chargement
  useEffect(() => {
    const savedTicket = localStorage.getItem('af_last_ticket');
    if (savedTicket) {
      try {
        const ticketData = JSON.parse(savedTicket);
        // Vérifier que le ticket n'est pas trop vieux (7 jours max)
        const ticketDate = new Date(ticketData.savedAt);
        const now = new Date();
        const daysDiff = (now - ticketDate) / (1000 * 60 * 60 * 24);
        
        if (daysDiff <= 7) {
          setHasSavedTicket(true);
        } else {
          // Ticket expiré, le supprimer
          localStorage.removeItem('af_last_ticket');
        }
      } catch (e) {
        console.error("Error parsing saved ticket:", e);
        localStorage.removeItem('af_last_ticket');
      }
    }
  }, []);

  // Fonction pour afficher le ticket sauvegardé
  const showSavedTicket = () => {
    const savedTicket = localStorage.getItem('af_last_ticket');
    if (savedTicket) {
      try {
        const ticketData = JSON.parse(savedTicket);
        setLastReservation(ticketData);
        setShowSuccess(true);
      } catch (e) {
        console.error("Error showing saved ticket:", e);
        setValidationMessage("Erreur lors de la récupération du ticket.");
        setTimeout(() => setValidationMessage(""), 3000);
      }
    }
  };

  // Fonction pour sauvegarder le ticket dans localStorage
  const saveTicketToStorage = (ticketData) => {
    const dataToSave = {
      ...ticketData,
      savedAt: new Date().toISOString()
    };
    localStorage.setItem('af_last_ticket', JSON.stringify(dataToSave));
    setHasSavedTicket(true);
  };

  // Fonction pour effacer le ticket sauvegardé
  const clearSavedTicket = () => {
    localStorage.removeItem('af_last_ticket');
    setHasSavedTicket(false);
    setShowSuccess(false);
    setLastReservation(null);
  };

  const [mediaSlug, setMediaSlug] = useState(null);
  const [clickCount, setClickCount] = useState(0);
  const [lastClickTime, setLastClickTime] = useState(0);

  // Check for /validate/:code URL and /v/:slug URL on mount
  // SUPPORTE AUSSI LE HASH ROUTING: /#/v/{slug} (fonctionne sans config serveur)
  useEffect(() => {
    const path = window.location.pathname;
    const hash = window.location.hash;
    const searchParams = new URLSearchParams(window.location.search);
    // Aussi parser les params dans le hash (ex: #coach-dashboard?session_id=xxx)
    const hashParams = new URLSearchParams(hash.split('?')[1] || '');
    
    // v11.0: Détection #reset-password pour afficher le modal de réinitialisation
    if (hash.includes('reset-password') && hash.includes('token=')) {
      console.log('[APP] 🔑 v11.0 - Lien de réinitialisation mot de passe détecté');
      setShowCoachLogin(true);
      return;
    }

    // v9.4.7: Détection #become-coach pour afficher la page d'inscription partenaire
    if (hash.includes('become-coach') || window.location.href.includes('become-coach')) {
      console.log('[APP] 🚀 v9.4.7 - Page Devenir Partenaire via hash');
      setShowBecomeCoach(true);
      return;
    }
    
    // === v9.2.5: PROPULSION AUTOMATIQUE #coach-dashboard ou #partner-dashboard ===
    // Force l'état dashboard sans AUCUNE autre condition
    if (hash.includes('coach-dashboard') || hash.includes('partner-dashboard') || window.location.href.includes('coach-dashboard') || window.location.href.includes('partner-dashboard')) {
      console.log('[APP] 🚀 v9.2.5 - Propulsion automatique dashboard FORCÉE');
      
      // v9.2.5: Détecter auth=success pour propulsion garantie
      const authSuccess = searchParams.get('auth') === 'success' || hash.includes('auth=success');
      const sessionId = searchParams.get('session_id') || hashParams.get('session_id');
      const isSuccess = searchParams.get('success') === 'true' || hash.includes('success=true');
      
      if (authSuccess || sessionId || isSuccess) {
        console.log('[APP] 💳 Retour Stripe détecté - auth:', authSuccess, 'session:', sessionId);
        // Mémoriser pour propulsion post-login
        localStorage.setItem('redirect_to_dash', 'true');
        localStorage.setItem('afroboost_redirect_message', '🎉 Paiement validé ! Bienvenue Partenaire');
      }
      
      const savedCoachUser = localStorage.getItem('afroboost_coach_user');
      
      if (savedCoachUser) {
        // Coach déjà connecté → PROPULSION IMMÉDIATE vers le dashboard
        try {
          const user = JSON.parse(savedCoachUser);
          setCoachUser(user);
          setCoachMode(true);
          // Nettoyer l'URL pour éviter les boucles (garder juste le hash)
          window.history.replaceState({}, '', window.location.pathname + '#partner-dashboard');
          console.log('[APP] ✅ v9.2.5 PROPULSION FORCÉE: Dashboard activé pour:', user?.email);
          
          // Afficher message de bienvenue si retour Stripe
          if (authSuccess || isSuccess) {
            setValidationMessage('🎉 Paiement validé ! Bienvenue Partenaire');
            setTimeout(() => setValidationMessage(''), 5000);
          }
        } catch (e) {
          console.error('[APP] Erreur parsing user:', e);
          setShowCoachLogin(true);
        }
      } else {
        // Pas connecté → Ouvrir modal de connexion (sera propulsé après login)
        console.log('[APP] 🔐 v9.2.5 Non connecté - Modal connexion avec message bienvenue');
        if (authSuccess || isSuccess) {
          setLoginWelcomeMessage('🎉 Paiement validé ! Connectez-vous pour accéder à votre espace Partenaire');
        }
        setShowCoachLogin(true);
      }
      return;
    }
    
    // === HASH ROUTING pour Media Viewer ===
    // Format: https://afroboost.com/#/v/{slug}
    if (hash.startsWith('#/v/')) {
      const slug = hash.replace('#/v/', '').split('/')[0].split('?')[0].trim();
      console.log('App.js - Hash routing - Media slug detected:', slug);
      if (slug && slug.length > 0) {
        setMediaSlug(slug.toLowerCase());
        return;
      }
    }
    
    // === PATH ROUTING (backup si serveur configuré) ===
    if (path.startsWith('/validate/')) {
      const code = path.replace('/validate/', '').toUpperCase();
      if (code) {
        setValidationCode(code);
        setShowCoachLogin(true);
      }
    }
    // Check for /v/:slug URL (Media Viewer)
    if (path.startsWith('/v/')) {
      const slug = path.replace('/v/', '').split('/')[0].split('?')[0].split('#')[0].trim();
      console.log('App.js - Path routing - Media slug detected:', slug);
      if (slug && slug.length > 0) {
        setMediaSlug(slug.toLowerCase());
        return;
      }
    }
  }, []);

  // Écouter les changements de hash pour le routing dynamique
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash;
      console.log('App.js - Hash changed:', hash);
      
      // v9.2.4: Détection #coach-dashboard ou #partner-dashboard
      if (hash.includes('#coach-dashboard') || hash.includes('coach-dashboard') || hash.includes('#partner-dashboard') || hash.includes('partner-dashboard')) {
        const savedCoachUser = localStorage.getItem('afroboost_coach_user');
        if (!savedCoachUser) {
          setShowCoachLogin(true);
        } else {
          setCoachMode(true);
        }
        return;
      }
      
      // v9.4.7: Détection #become-coach pour afficher la page d'inscription partenaire
      if (hash.includes('#become-coach') || hash.includes('become-coach')) {
        setShowBecomeCoach(true);
        return;
      }
      
      if (hash.startsWith('#/v/')) {
        const slug = hash.replace('#/v/', '').split('/')[0].split('?')[0].trim();
        if (slug && slug.length > 0) {
          setMediaSlug(slug.toLowerCase());
        }
      }
    };
    
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  // === v9.2.3: PROPULSION ZÉRO CLIC - Vérifie l'intention de redirection ===
  useEffect(() => {
    // Vérifier si une intention de redirection existe (définie AVANT le rendu React)
    const redirectIntent = localStorage.getItem('afroboost_redirect_intent');
    const redirectMessage = localStorage.getItem('afroboost_redirect_message');
    
    if (redirectIntent === 'dashboard') {
      console.log('[APP] 🚀 v9.2.3 PROPULSION: Intent trouvé, activation dashboard');
      
      // Nettoyer l'intention pour éviter boucle
      localStorage.removeItem('afroboost_redirect_intent');
      localStorage.removeItem('afroboost_redirect_message');
      
      const savedCoachUser = localStorage.getItem('afroboost_coach_user');
      
      if (savedCoachUser) {
        // Partenaire déjà connecté → PROPULSION IMMÉDIATE
        try {
          const user = JSON.parse(savedCoachUser);
          setCoachUser(user);
          setCoachMode(true);
          if (redirectMessage) {
            setValidationMessage(redirectMessage);
            setTimeout(() => setValidationMessage(""), 5000);
          }
          console.log('[APP] ✅ v9.2.3 PROPULSION: Dashboard activé pour:', user?.email);
          return;
        } catch (e) {
          console.error('[APP] Erreur parsing user:', e);
        }
      }
      
      // Pas connecté → Ouvrir modal avec message de bienvenue
      console.log('[APP] 🔐 v9.2.3 Intent dashboard mais non connecté - Affichage modal');
      setLoginWelcomeMessage(redirectMessage || "🎉 Bienvenue ! Connectez-vous pour accéder à votre espace.");
      setShowCoachLogin(true);
    }
    
    // Fallback: Détection classique (si jamais l'intent n'a pas été capturé)
    const urlParams = new URLSearchParams(window.location.search);
    const hash = window.location.hash;
    
    const isSuccess = urlParams.get('success') === 'true' || 
                      urlParams.get('status') === 'success' ||
                      hash.includes('success=true') ||
                      hash.includes('welcome=true');
    
    const isPartnerPayment = isSuccess && !localStorage.getItem('pendingReservation');
    
    if (isPartnerPayment && !redirectIntent) {
      console.log('[APP] 🚀 v9.2.3 PROPULSION FALLBACK: Détection dans useEffect');
      
      // Nettoyer l'URL
      const url = new URL(window.location.href);
      url.searchParams.delete('success');
      url.searchParams.delete('status');
      url.searchParams.delete('session_id');
      url.searchParams.delete('welcome');
      url.hash = '#coach-dashboard';
      window.history.replaceState({}, '', url.pathname + url.hash);
      
      const savedCoachUser = localStorage.getItem('afroboost_coach_user');
      
      if (savedCoachUser) {
        try {
          const user = JSON.parse(savedCoachUser);
          setCoachUser(user);
          setCoachMode(true);
          setValidationMessage("🎉 Paiement validé ! Bienvenue dans votre espace Partenaire");
          setTimeout(() => setValidationMessage(""), 5000);
          console.log('[APP] ✅ v9.2.3 PROPULSION FALLBACK: Dashboard activé pour:', user?.email);
          return;
        } catch (e) {
          console.error('[APP] Erreur parsing user:', e);
        }
      }
      
      setLoginWelcomeMessage("🎉 Paiement validé ! Bienvenue Partenaire. Connectez-vous pour accéder à votre espace.");
      setShowCoachLogin(true);
    }
  }, []);

  // PWA Install Prompt State
  const [installPrompt, setInstallPrompt] = useState(null);
  const [showInstallBanner, setShowInstallBanner] = useState(false);
  const [isIOS, setIsIOS] = useState(false);

  // v8.9.3: Écouter l'événement "openBecomeCoach" depuis le ChatWidget
  useEffect(() => {
    const handleOpenBecomeCoach = () => {
      setShowBecomeCoach(true);
    };
    window.addEventListener('openBecomeCoach', handleOpenBecomeCoach);
    return () => window.removeEventListener('openBecomeCoach', handleOpenBecomeCoach);
  }, []);

  // v67: SLUGS DU SUPER ADMIN — tout accès à ces slugs = homepage publique, jamais CoachVitrine
  const SUPER_ADMIN_SLUGS = ['bassi', 'artboost', 'afroboost'];

  // v8.9.6: Détecter l'URL /coach/[username] ou /partner/[username] pour afficher la vitrine
  // v9.1.8: Support route /partner/:username (alias de /coach/:username)
  // v67: Verrouillage — /coach/bassi redirige vers /?visitor=true (1 Super Admin = 1 seule vitrine = homepage)
  useEffect(() => {
    const checkCoachVitrine = () => {
      const path = window.location.pathname;
      // Supporter /coach/xxx ET /partner/xxx
      const match = path.match(/^\/(coach|partner)\/(.+)$/);
      if (match && match[2]) {
        const slug = decodeURIComponent(match[2]).toLowerCase().trim();
        // v67: Si c'est un slug du Super Admin → rediriger vers la homepage publique
        if (SUPER_ADMIN_SLUGS.includes(slug)) {
          console.log('[V67] VERROUILLAGE: /coach/' + slug + ' → homepage publique /?visitor=true');
          window.history.replaceState({}, '', '/?visitor=true');
          return; // Ne PAS charger CoachVitrine
        }
        setShowCoachVitrine(match[2]);
      }
    };
    checkCoachVitrine();

    // Écouter les changements d'URL
    const handlePopState = () => checkCoachVitrine();
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const t = useCallback((key) => translations[lang][key] || key, [lang]);

  useEffect(() => { localStorage.setItem("af_lang", lang); }, [lang]);

  // PWA Install Prompt - Capture beforeinstallprompt event
  useEffect(() => {
    // Detect iOS
    const iOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    setIsIOS(iOS);

    const handleBeforeInstallPrompt = (e) => {
      // Prevent Chrome 67+ from automatically showing the prompt
      e.preventDefault();
      // Store the event for later use
      setInstallPrompt(e);
      // Check if user hasn't dismissed the banner before
      const dismissed = localStorage.getItem('af_pwa_dismissed');
      if (!dismissed) {
        setShowInstallBanner(true);
      }
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    // Check if already installed (standalone mode)
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || 
                         window.navigator.standalone === true;
    
    if (isStandalone) {
      setShowInstallBanner(false);
    } else if (iOS) {
      // Show banner for iOS with manual instructions
      const dismissed = localStorage.getItem('af_pwa_dismissed');
      if (!dismissed) {
        setShowInstallBanner(true);
      }
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    };
  }, []);

  // Handle PWA install button click
  const handleInstallClick = async () => {
    if (isIOS) {
      // For iOS, show instructions (can't auto-prompt)
      alert('Pour installer Afroboost sur iOS:\n\n1. Appuyez sur le bouton Partager (📤)\n2. Sélectionnez "Sur l\'écran d\'accueil"\n3. Appuyez sur "Ajouter"');
      return;
    }
    
    if (!installPrompt) return;
    
    // Show the install prompt
    installPrompt.prompt();
    
    // Wait for user response
    const { outcome } = await installPrompt.userChoice;
    
    if (outcome === 'accepted') {
      console.log('PWA installed');
    }
    
    // Clear the prompt
    setInstallPrompt(null);
    setShowInstallBanner(false);
  };

  // Dismiss install banner
  const dismissInstallBanner = () => {
    setShowInstallBanner(false);
    localStorage.setItem('af_pwa_dismissed', 'true');
  };

  // MÉMORISATION CLIENT: Load saved client info from localStorage on mount
  useEffect(() => {
    const savedClient = localStorage.getItem("af_client_info");
    if (savedClient) {
      try {
        const client = JSON.parse(savedClient);
        // Pre-fill if data exists
        if (client.name) setUserName(client.name);
        if (client.email) setUserEmail(client.email);
        if (client.whatsapp) setUserWhatsapp(client.whatsapp);
      } catch (e) { console.error("Error loading client info:", e); }
    }
  }, []);

  // STRIPE CHECKOUT: Gestion du retour de paiement - Ticket persistant
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    // Détecter status=success ou les anciens formats (compatibilité)
    const statusParam = urlParams.get('status');
    const paymentParam = urlParams.get('payment');
    const isPaymentSuccess = statusParam === 'success' || paymentParam === 'success' || urlParams.get('payment_success') === 'true';
    const isPaymentCanceled = statusParam === 'canceled' || paymentParam === 'canceled' || urlParams.get('payment_canceled') === 'true';
    const sessionId = urlParams.get('session_id');
    
    // Nettoyer l'URL après affichage du ticket
    const cleanUrl = () => {
      const url = new URL(window.location.href);
      url.searchParams.delete('status');
      url.searchParams.delete('payment');
      url.searchParams.delete('payment_success');
      url.searchParams.delete('payment_canceled');
      url.searchParams.delete('session_id');
      window.history.replaceState({}, document.title, url.pathname);
    };
    
    if (isPaymentSuccess && sessionId) {
      // Paiement réussi - Afficher le ticket IMMÉDIATEMENT
      const pendingReservationData = localStorage.getItem('pendingReservation');
      
      if (pendingReservationData) {
        const reservation = JSON.parse(pendingReservationData);
        
        // AFFICHER LE TICKET IMMÉDIATEMENT avec les données locales
        const tempTicketData = {
          ...reservation,
          reservationCode: `AF-${Date.now().toString(36).toUpperCase()}`,
          stripeSessionId: sessionId,
          paymentStatus: 'processing'
        };
        setLastReservation(tempTicketData);
        setShowSuccess(true); // TICKET VISIBLE IMMÉDIATEMENT
        
        // SAUVEGARDER LE TICKET dans localStorage pour persistance
        saveTicketToStorage(tempTicketData);
        
        // Ensuite, finaliser en arrière-plan
        const finalizeReservation = async () => {
          try {
            // Créer la réservation dans la base de données
            const res = await axios.post(`${API}/reservations`, {
              ...reservation,
              stripeSessionId: sessionId,
              paymentStatus: 'paid'
            });
            
            // Utiliser le code promo si présent
            if (reservation.appliedDiscount) {
              try {
                await axios.post(`${API}/discount-codes/${reservation.appliedDiscount.id}/use`);
              } catch (e) { console.log("Discount code already used"); }
            }
            
            // Sauvegarder les infos client
            localStorage.setItem("af_client_info", JSON.stringify({
              name: reservation.userName,
              email: reservation.userEmail,
              whatsapp: reservation.userWhatsapp
            }));
            
            // Mettre à jour le ticket avec le vrai code de réservation
            setLastReservation(res.data);
            
            // METTRE À JOUR le ticket sauvegardé avec les vraies données
            saveTicketToStorage(res.data);
            
            // Nettoyer localStorage après succès
            localStorage.removeItem('pendingReservation');
            
          } catch (err) {
            console.error("Error saving reservation to database:", err);
            // Le ticket est déjà affiché et sauvegardé
            localStorage.setItem("failedReservation", JSON.stringify({
              ...reservation,
              stripeSessionId: sessionId,
              error: err.message
            }));
          }
        };
        
        finalizeReservation();
        
      } else {
        // Pas de réservation en attente - peut-être un refresh
        // Créer un ticket minimal avec le session_id
        console.log("No pending reservation, creating minimal ticket for session:", sessionId);
        const minimalTicket = {
          reservationCode: `AF-${sessionId.slice(-8).toUpperCase()}`,
          stripeSessionId: sessionId,
          paymentStatus: 'paid',
          courseName: 'Réservation Afroboost',
          totalPrice: '-'
        };
        setLastReservation(minimalTicket);
        setShowSuccess(true);
        
        // Sauvegarder même le ticket minimal
        saveTicketToStorage(minimalTicket);
      }
      
      // Nettoyer l'URL APRÈS affichage du ticket
      setTimeout(cleanUrl, 100);
      
    } else if (isPaymentCanceled) {
      // Paiement annulé - afficher un message
      localStorage.removeItem('pendingReservation');
      setValidationMessage("Paiement annulé. Vous pouvez réessayer.");
      setTimeout(() => setValidationMessage(""), 4000);
      cleanUrl();
    }
  }, []);

  // MÉMORISATION CLIENT: Auto-fill when email matches saved client
  const handleEmailChange = (email) => {
    setUserEmail(email);
    // Check if email matches a saved client
    const savedClient = localStorage.getItem("af_client_info");
    if (savedClient && email.length > 3) {
      try {
        const client = JSON.parse(savedClient);
        if (client.email && client.email.toLowerCase() === email.toLowerCase()) {
          // Auto-fill name and whatsapp
          if (client.name && !userName) setUserName(client.name);
          if (client.whatsapp && !userWhatsapp) setUserWhatsapp(client.whatsapp);
        }
      } catch (e) { /* ignore */ }
    }
  };

  // MÉMORISATION CLIENT: Save client info after successful reservation
  const saveClientInfo = (name, email, whatsapp) => {
    localStorage.setItem("af_client_info", JSON.stringify({ name, email, whatsapp }));
  };

  // === SYSTÈME DE CACHE OPTIMISÉ ===
  // Cache en mémoire avec TTL pour éviter les re-téléchargements inutiles
  const cacheRef = useRef({
    courses: { data: null, timestamp: 0 },
    offers: { data: null, timestamp: 0 },
    concept: { data: null, timestamp: 0 },
    paymentLinks: { data: null, timestamp: 0 }
  });

  // Vérifier si le cache est valide (TTL: 5 minutes)
  const isCacheValid = useCallback((key) => {
    const cached = cacheRef.current[key];
    const cacheTTL = 5 * 60 * 1000; // 5 minutes
    return cached.data && (Date.now() - cached.timestamp < cacheTTL);
  }, []);

  // Fonction pour charger les données avec cache
  const fetchData = useCallback(async (forceRefresh = false) => {
    try {
      // Utiliser le cache si disponible et pas de force refresh
      const cachedCourses = !forceRefresh && isCacheValid('courses') ? cacheRef.current.courses.data : null;
      const cachedOffers = !forceRefresh && isCacheValid('offers') ? cacheRef.current.offers.data : null;
      const cachedConcept = !forceRefresh && isCacheValid('concept') ? cacheRef.current.concept.data : null;
      const cachedLinks = !forceRefresh && isCacheValid('paymentLinks') ? cacheRef.current.paymentLinks.data : null;

      // Construire les requêtes uniquement pour les données non cachées
      const requests = [];
      const requestMap = {};

      if (!cachedCourses) {
        requestMap.courses = requests.length;
        requests.push(axios.get(`${API}/courses`));
      }
      if (!cachedOffers) {
        requestMap.offers = requests.length;
        requests.push(axios.get(`${API}/offers`));
      }
      if (!cachedLinks) {
        requestMap.links = requests.length;
        requests.push(axios.get(`${API}/payment-links`));
      }
      if (!cachedConcept) {
        requestMap.concept = requests.length;
        requests.push(axios.get(`${API}/concept`));
      }

      // Toujours récupérer users et discount codes (données dynamiques)
      requestMap.users = requests.length;
      requests.push(axios.get(`${API}/users`));
      requestMap.codes = requests.length;
      requests.push(axios.get(`${API}/discount-codes`));

      const responses = await Promise.all(requests);

      // Mettre à jour le cache et les états
      const now = Date.now();

      if (cachedCourses) {
        setCourses(cachedCourses);
      } else if (requestMap.courses !== undefined) {
        const coursesData = responses[requestMap.courses].data;
        cacheRef.current.courses = { data: coursesData, timestamp: now };
        setCourses(coursesData);
      }

      if (cachedOffers) {
        setOffers(cachedOffers);
      } else if (requestMap.offers !== undefined) {
        const offersData = responses[requestMap.offers].data;
        cacheRef.current.offers = { data: offersData, timestamp: now };
        setOffers(offersData);
      }

      if (cachedLinks) {
        setPaymentLinks(cachedLinks);
      } else if (requestMap.links !== undefined) {
        const linksData = responses[requestMap.links].data;
        cacheRef.current.paymentLinks = { data: linksData, timestamp: now };
        setPaymentLinks(linksData);
      }

      if (cachedConcept) {
        setConcept(cachedConcept);
        // Appliquer les couleurs personnalisées
        if (cachedConcept.primaryColor) {
          document.documentElement.style.setProperty('--primary-color', cachedConcept.primaryColor);
          // Glow: utiliser glowColor si défini, sinon primaryColor
          const glowBase = cachedConcept.glowColor || cachedConcept.primaryColor;
          document.documentElement.style.setProperty('--glow-color', `${glowBase}66`);
          document.documentElement.style.setProperty('--glow-color-strong', `${glowBase}99`);
        }
        if (cachedConcept.secondaryColor) {
          document.documentElement.style.setProperty('--secondary-color', cachedConcept.secondaryColor);
        }
        // v9.4.4: Appliquer la couleur de fond
        if (cachedConcept.backgroundColor) {
          document.documentElement.style.setProperty('--background-color', cachedConcept.backgroundColor);
          document.body.style.backgroundColor = cachedConcept.backgroundColor;
        }
      } else if (requestMap.concept !== undefined) {
        const conceptData = responses[requestMap.concept].data;
        cacheRef.current.concept = { data: conceptData, timestamp: now };
        setConcept(conceptData);
        // Appliquer les couleurs personnalisées
        if (conceptData.primaryColor) {
          document.documentElement.style.setProperty('--primary-color', conceptData.primaryColor);
          // Glow: utiliser glowColor si défini, sinon primaryColor
          const glowBase = conceptData.glowColor || conceptData.primaryColor;
          document.documentElement.style.setProperty('--glow-color', `${glowBase}66`);
          document.documentElement.style.setProperty('--glow-color-strong', `${glowBase}99`);
        }
        if (conceptData.secondaryColor) {
          document.documentElement.style.setProperty('--secondary-color', conceptData.secondaryColor);
        }
        // v9.4.4: Appliquer la couleur de fond
        if (conceptData.backgroundColor) {
          document.documentElement.style.setProperty('--background-color', conceptData.backgroundColor);
          document.body.style.backgroundColor = conceptData.backgroundColor;
        }
      }

      // Données dynamiques (toujours rafraîchies)
      if (requestMap.users !== undefined) {
        setUsers(responses[requestMap.users].data);
      }
      if (requestMap.codes !== undefined) {
        setDiscountCodes(responses[requestMap.codes].data);
      }

      console.log(`📦 Cache: ${cachedCourses ? '✓' : '↓'}courses ${cachedOffers ? '✓' : '↓'}offers ${cachedConcept ? '✓' : '↓'}concept`);

      // v53: Charger les pistes audio autonomes (Studio Audio) du super admin
      try {
        const ownerEmail = SUPER_ADMIN_EMAILS[0]; // contact.artboost@gmail.com
        const audioRes = await axios.get(`${API}/public/audio-tracks/${encodeURIComponent(ownerEmail)}`);
        const tracks = audioRes.data?.tracks || [];
        setStudioAudioTracks(tracks);
        console.log('[V53] Studio audio tracks loaded:', tracks.length);
      } catch (audioErr) {
        console.warn('[V53] Studio audio tracks fetch failed:', audioErr.message);
      }

    } catch (err) { console.error("Error:", err); }
  }, [isCacheValid]);

  // Invalider le cache (appelé après modifications dans CoachDashboard)
  const invalidateDataCache = useCallback((key) => {
    if (key) {
      cacheRef.current[key] = { data: null, timestamp: 0 };
    } else {
      // Invalider tout le cache
      Object.keys(cacheRef.current).forEach(k => {
        cacheRef.current[k] = { data: null, timestamp: 0 };
      });
    }
  }, []);

  // Charger les données au démarrage
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Vérification de session coach au démarrage : éviter redirect/logout cassant
  // Si le coach est désactivé ou supprimé côté backend, on le déconnecte proprement
  useEffect(() => {
    if (!coachMode || !coachUser?.email) return;
    const validateCoachSession = async () => {
      try {
        const res = await axios.get(`${API}/auth/role`, {
          headers: { 'X-User-Email': coachUser.email }
        });
        const role = res.data?.role;
        setUserRole(role);
        // Si l'utilisateur n'est plus coach ni super_admin → déconnexion propre
        if (role === 'user' || (!res.data?.is_coach && !res.data?.is_super_admin)) {
          console.log('[APP] Session coach invalide, déconnexion propre');
          localStorage.removeItem('afroboost_coach_mode');
          localStorage.removeItem('afroboost_coach_user');
          setCoachMode(false);
          setCoachUser(null);
        }
      } catch (err) {
        // En cas d'erreur réseau, on garde la session pour éviter un logout intempestif
        console.warn('[APP] Vérification session coach échouée (réseau?):', err.message);
      }
    };
    validateCoachSession();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Recharger les données quand on sort du Mode Coach (avec force refresh)
  useEffect(() => {
    if (!coachMode) {
      // Invalider le cache quand on sort du mode coach car des modifications ont pu être faites
      invalidateDataCache();
      fetchData(true);
    }
  }, [coachMode, fetchData, invalidateDataCache]);

  // Afficher le popup Affiche Événement si activé
  useEffect(() => {
    // Ne pas afficher si on est en mode Coach ou pendant le splash
    if (coachMode || showSplash || showCoachLogin) return;
    
    // Vérifier si le popup a déjà été fermé dans cette session
    const posterDismissed = sessionStorage.getItem('eventPosterDismissed');
    
    if (concept.eventPosterEnabled && concept.eventPosterMediaUrl && !posterDismissed) {
      // Petit délai pour laisser le temps au site de se charger
      const timer = setTimeout(() => {
        setShowEventPoster(true);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [concept.eventPosterEnabled, concept.eventPosterMediaUrl, coachMode, showSplash, showCoachLogin]);

  // Fonction pour fermer le popup et mémoriser
  const closeEventPoster = () => {
    setShowEventPoster(false);
    sessionStorage.setItem('eventPosterDismissed', 'true');
  };

  // =====================================================
  // FAVICON & PWA: Fonction centralisée pour mettre à jour le favicon
  // Supprime TOUS les favicons existants avant d'en injecter un seul
  // =====================================================
  
  const updateAllFavicons = useCallback((newFaviconUrl) => {
    if (!newFaviconUrl || newFaviconUrl.trim() === '') return;
    
    // 1. SUPPRIMER tous les liens favicon existants
    const existingIcons = document.querySelectorAll('link[rel="icon"], link[rel="shortcut icon"], link[rel~="icon"]');
    existingIcons.forEach(icon => icon.remove());
    
    // 2. SUPPRIMER tous les apple-touch-icon existants
    const existingAppleIcons = document.querySelectorAll('link[rel="apple-touch-icon"], link[rel="apple-touch-icon-precomposed"]');
    existingAppleIcons.forEach(icon => icon.remove());
    
    // 3. CRÉER un seul nouveau favicon
    const newFavicon = document.createElement('link');
    newFavicon.rel = 'icon';
    newFavicon.type = 'image/png';
    newFavicon.href = newFaviconUrl;
    document.head.appendChild(newFavicon);
    
    // 4. CRÉER un seul apple-touch-icon pour PWA
    const newAppleIcon = document.createElement('link');
    newAppleIcon.rel = 'apple-touch-icon';
    newAppleIcon.href = newFaviconUrl;
    document.head.appendChild(newAppleIcon);
    
    // 5. Mettre à jour le manifest pour PWA
    let manifestLink = document.querySelector("link[rel='manifest']");
    if (manifestLink) {
      const apiUrl = process.env.REACT_APP_BACKEND_URL || '';
      manifestLink.href = `${apiUrl}/api/manifest.json?v=${Date.now()}`;
    }
    
    console.log("✅ Favicon unique mis à jour:", newFaviconUrl);
  }, []);

  // v9.3.8: Favicon par défaut Afroboost
  const DEFAULT_FAVICON_URL = 'https://i.ibb.co/4Z7q3Tvw/file-000000005c1471f4bc77c9174753b16b.png';

  // Update favicon when faviconUrl changes (priority)
  useEffect(() => {
    if (concept.faviconUrl && concept.faviconUrl.trim() !== '') {
      updateAllFavicons(concept.faviconUrl);
    } else if (concept.logoUrl && concept.logoUrl.trim() !== '') {
      // Fallback vers logoUrl si pas de faviconUrl
      updateAllFavicons(concept.logoUrl);
    } else {
      // Fallback vers le favicon Afroboost par défaut
      updateAllFavicons(DEFAULT_FAVICON_URL);
    }
  }, [concept.faviconUrl, concept.logoUrl, updateAllFavicons]);

  // Scroll vers la section par défaut au chargement (si configuré par le coach)
  useEffect(() => {
    // Ne pas scroller si en mode coach ou pendant le splash
    if (coachMode || showSplash) return;
    
    // Attendre que les données soient chargées et le splash terminé
    if (concept.defaultLandingSection && concept.defaultLandingSection !== 'all' && concept.defaultLandingSection !== 'sessions') {
      // Délai plus long pour s'assurer que tout est prêt
      const timer = setTimeout(() => {
        let sectionId = null;
        if (concept.defaultLandingSection === 'offers' || concept.defaultLandingSection === 'shop') {
          sectionId = 'offers-section';
        }
        
        if (sectionId) {
          const element = document.getElementById(sectionId);
          if (element) {
            console.log(`Auto-scrolling to: ${sectionId}`);
            element.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }
        
        // Mettre à jour le filtre actif
        setActiveFilter(concept.defaultLandingSection);
      }, 800); // Délai augmenté pour attendre le splash
      return () => clearTimeout(timer);
    }
  }, [concept.defaultLandingSection, coachMode, showSplash]);

  useEffect(() => { const timer = setTimeout(() => setShowSplash(false), 1500); return () => clearTimeout(timer); }, []);

  // LOGIQUE CODE PROMO: Validation en temps réel - Case Insensitive avec trim
  useEffect(() => {
    const validateCode = async () => {
      // Normalize input: trim spaces
      const normalizedCode = discountCode?.trim() || '';
      
      // Reset if no code entered
      if (!normalizedCode) { 
        setAppliedDiscount(null); 
        setPromoMessage({ type: '', text: '' });
        return; 
      }
      
      // Need to select a course first
      if (!selectedCourse) { 
        setAppliedDiscount(null);
        setPromoMessage({ type: 'warning', text: '⚠️ Sélectionnez d\'abord un cours' });
        return; 
      }
      
      try {
        // Send normalized code to backend (backend will also normalize)
        const res = await axios.post(`${API}/discount-codes/validate`, { 
          code: normalizedCode,
          email: userEmail?.trim() || '', 
          courseId: selectedCourse.id 
        });
        
        if (res.data.valid) { 
          const code = res.data.code;
          setAppliedDiscount(code);
          
          // Calculate the actual discount amount for display
          let discountAmount = 0;
          let discountText = '';
          
          if (code.type === '100%' || (code.type === '%' && parseFloat(code.value) >= 100)) {
            discountAmount = selectedOffer ? selectedOffer.price : 0;
            discountText = `Code validé : -${discountAmount.toFixed(2)} CHF (GRATUIT)`;
          } else if (code.type === '%') {
            discountAmount = selectedOffer ? (selectedOffer.price * parseFloat(code.value) / 100) : 0;
            discountText = `Code validé : -${discountAmount.toFixed(2)} CHF (-${code.value}%)`;
          } else if (code.type === 'CHF') {
            discountAmount = parseFloat(code.value);
            discountText = `Code validé : -${discountAmount.toFixed(2)} CHF`;
          }
          
          setPromoMessage({ type: 'success', text: `✅ ${discountText}` });
        } else { 
          setAppliedDiscount(null);
          // Display specific error message from backend
          const errorMsg = res.data.message || 'Code inconnu ou non applicable à ce cours';
          setPromoMessage({ type: 'error', text: `❌ ${errorMsg}` });
        }
      } catch (err) { 
        console.error("Promo validation error:", err);
        setAppliedDiscount(null); 
        setPromoMessage({ type: 'error', text: '❌ Code inconnu ou non applicable à ce cours' });
      }
    };
    
    // Debounce to avoid too many API calls
    const debounce = setTimeout(validateCode, 400);
    return () => clearTimeout(debounce);
  }, [discountCode, selectedCourse, selectedOffer, userEmail]);

  // Secret coach access: 3 rapid clicks
  const handleCopyrightClick = () => {
    const now = Date.now();
    if (now - lastClickTime < 500) {
      const newCount = clickCount + 1;
      setClickCount(newCount);
      if (newCount >= 3) { setShowCoachLogin(true); setClickCount(0); }
    } else { setClickCount(1); }
    setLastClickTime(now);
  };

  const isDiscountFree = (code) => code && (code.type === "100%" || (code.type === "%" && parseFloat(code.value) >= 100));

  const calculateTotal = () => {
    if (!selectedOffer) return 0;
    // Pour les produits physiques: utiliser quantity
    // Pour les services/cours: utiliser le nombre de dates sélectionnées
    const isPhysicalProduct = selectedOffer?.isProduct || selectedOffer?.isPhysicalProduct;
    const multiplier = isPhysicalProduct ? quantity : Math.max(1, selectedDates.length);
    let total = selectedOffer.price * multiplier;
    if (appliedDiscount) {
      if (appliedDiscount.type === "100%" || (appliedDiscount.type === "%" && parseFloat(appliedDiscount.value) >= 100)) total = 0;
      else if (appliedDiscount.type === "%") total = total * (1 - parseFloat(appliedDiscount.value) / 100);
      else if (appliedDiscount.type === "CHF") total = Math.max(0, total - parseFloat(appliedDiscount.value));
    }
    return total.toFixed(2);
  };

  const resetForm = () => {
    setPendingReservation(null); setSelectedCourse(null); setSelectedDates([]);
    setSelectedOffer(null); setSelectedSession(null); setUserName(""); 
    setUserEmail(""); setUserWhatsapp(""); setDiscountCode(""); 
    setHasAcceptedTerms(false); setAppliedDiscount(null); setPromoMessage({ type: '', text: '' });
    setQuantity(1); // Reset quantité
  };

  // Reset form but keep client info (for repeat purchases)
  const resetFormKeepClient = () => {
    setPendingReservation(null); setSelectedCourse(null); setSelectedDates([]);
    setSelectedOffer(null); setSelectedSession(null); setDiscountCode(""); 
    setHasAcceptedTerms(false); setAppliedDiscount(null); setPromoMessage({ type: '', text: '' });
    setQuantity(1); setShippingAddress(""); // Reset quantité et adresse
    // Keep userName, userEmail, userWhatsapp for convenience
  };

  // Sélection d'offre avec smooth scroll vers le formulaire "Vos informations"
  const handleSelectOffer = (offer) => {
    // v56: Toggle — si la même offre est déjà sélectionnée, on la désélectionne (ferme le formulaire)
    if (selectedOffer && offer && selectedOffer.id === offer.id && selectedOffer.name === offer.name) {
      setSelectedOffer(null);
      setSelectedVariants({});
      return;
    }

    setSelectedOffer(offer);
    // Réinitialiser les variantes quand une nouvelle offre est sélectionnée
    setSelectedVariants({});

    // Smooth scroll vers la section "Vos informations" après un court délai
    // pour laisser le temps au DOM de se mettre à jour
    setTimeout(() => {
      const formSection = document.getElementById('user-info-section');
      if (formSection) {
        formSection.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    }, 150);
  };

  const sendWhatsAppNotification = (reservation, isCoach) => {
    const phone = isCoach ? paymentLinks.coachWhatsapp : reservation.userWhatsapp;
    if (!phone?.trim()) return;
    const dateStr = new Date(reservation.datetime).toLocaleDateString('fr-CH');
    const msg = `🎧 ${isCoach ? 'Nouvelle réservation' : 'Confirmation'} Afroboost\n\n👤 ${reservation.userName}\n📧 ${reservation.userEmail}\n💰 ${reservation.offerName} - CHF ${reservation.totalPrice}\n📅 ${reservation.courseName} - ${dateStr}\n🎫 ${reservation.reservationCode}`;
    window.open(`https://wa.me/${phone.replace(/\D/g, '')}?text=${encodeURIComponent(msg)}`, '_blank');
  };

  // Notification automatique au coach (email + WhatsApp via API)
  const notifyCoachAutomatic = async (reservation) => {
    try {
      // Appeler l'endpoint backend pour obtenir les configs de notification
      const dateStr = new Date(reservation.datetime).toLocaleDateString('fr-CH', {
        weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit'
      });
      
      const notifyResponse = await axios.post(`${API}/notify-coach`, {
        clientName: reservation.userName,
        clientEmail: reservation.userEmail,
        clientWhatsapp: reservation.userWhatsapp,
        offerName: reservation.offerName,
        courseName: reservation.courseName,
        sessionDate: dateStr,
        amount: reservation.totalPrice,
        reservationCode: reservation.reservationCode
      });

      if (!notifyResponse.data.success) {
        console.log("Coach notification not configured:", notifyResponse.data.message);
        return;
      }

      const { coachEmail, coachPhone, message, subject } = notifyResponse.data;

      // Envoyer notification email via Resend (backend)
      if (coachEmail) {
        try {
          await axios.post(`${API}/campaigns/send-email`, {
            to_email: coachEmail,
            to_name: "Coach Afroboost",
            subject: subject,
            message: message
          });
          console.log("✅ Email notification sent to coach via Resend");
        } catch (emailErr) {
          console.error("Email notification failed:", emailErr);
        }
      }

      // Envoyer notification WhatsApp si configuré et Twilio est actif
      if (coachPhone && isWhatsAppConfigured()) {
        try {
          await sendWhatsAppMessage({
            to: coachPhone,
            message: message,
            contactName: "Coach"
          });
          console.log("✅ WhatsApp notification sent to coach");
        } catch (waErr) {
          console.error("WhatsApp notification failed:", waErr);
        }
      }
    } catch (err) {
      console.error("Coach notification error:", err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Pour les produits physiques et audios, pas besoin de cours/dates
    const isPhysicalProduct = selectedOffer?.isProduct || selectedOffer?.isPhysicalProduct;
    const isAudioPurchase = selectedOffer?.type === 'audio'; // v54: achat audio autonome
    if (!isPhysicalProduct && !isAudioPurchase && (!selectedCourse || selectedDates.length === 0)) return;
    if (!selectedOffer || !hasAcceptedTerms) return;

    // Direct validation - private fields only
    if (!userEmail?.trim() || !userWhatsapp?.trim()) {
      setValidationMessage(t('emailWhatsappRequired'));
      setTimeout(() => setValidationMessage(""), 4000);
      return;
    }
    
    // Validation des variantes si le produit en a
    if (selectedOffer?.variants && Object.keys(selectedOffer.variants).length > 0) {
      const missingVariants = [];
      if (selectedOffer.variants.sizes?.length > 0 && !selectedVariants.size) {
        missingVariants.push('taille');
      }
      if (selectedOffer.variants.colors?.length > 0 && !selectedVariants.color) {
        missingVariants.push('couleur');
      }
      if (selectedOffer.variants.weights?.length > 0 && !selectedVariants.weight) {
        missingVariants.push('poids');
      }
      
      if (missingVariants.length > 0) {
        setValidationMessage(`Veuillez sélectionner: ${missingVariants.join(', ')}`);
        setTimeout(() => setValidationMessage(""), 4000);
        return;
      }
    }

    // Calcul de la date pour les services (cours) - utilise la première date sélectionnée
    let dt = new Date();
    const selectedDate = selectedDates[0]; // Première date pour la réservation principale
    if (selectedCourse && selectedDate) {
      const [h, m] = selectedCourse.time.split(':');
      dt = new Date(selectedDate);
      dt.setHours(parseInt(h), parseInt(m), 0, 0);
    }
    
    // Nombre de dates sélectionnées (pour le calcul du prix)
    const dateCount = selectedDates.length || 1;

    const totalPrice = parseFloat(calculateTotal());
    
    // Formatter les variantes sélectionnées pour l'affichage
    const variantsText = Object.entries(selectedVariants)
      .filter(([_, v]) => v)
      .map(([k, v]) => `${k === 'size' ? 'Taille' : k === 'color' ? 'Couleur' : 'Poids'}: ${v}`)
      .join(', ');
    
    // Formatter les dates sélectionnées
    const selectedDatesText = selectedDates.map(d => new Date(d).toLocaleDateString('fr-FR')).join(', ');

    const reservation = {
      userId: `user-${Date.now()}`,
      userName: userName,
      userEmail: userEmail, 
      userWhatsapp: userWhatsapp,
      shippingAddress: isPhysicalProduct ? shippingAddress : null, // Adresse si produit physique
      selectedVariants: Object.keys(selectedVariants).length > 0 ? selectedVariants : null, // Variantes choisies
      variantsText: variantsText || null, // Texte formaté des variantes
      selectedDates: selectedDates, // Toutes les dates sélectionnées
      selectedDatesText: selectedDatesText || null, // Texte formaté des dates
      courseId: selectedCourse?.id || 'N/A',
      courseName: selectedCourse?.name || (isAudioPurchase ? 'Achat Audio' : 'Produit physique'),
      courseTime: selectedCourse?.time || '', 
      datetime: dt.toISOString(),
      offerId: selectedOffer.id, 
      offerName: selectedOffer.name,
      price: selectedOffer.price, 
      quantity: dateCount, // Nombre de dates sélectionnées comme quantité
      totalPrice,
      discountCode: appliedDiscount?.code || null,
      discountType: appliedDiscount?.type || null,
      discountValue: appliedDiscount?.value || null,
      appliedDiscount,
      isProduct: isPhysicalProduct,
      isAudio: isAudioPurchase
    };

    // DYNAMISME DU BOUTON: Si total = 0 (100% gratuit), réservation directe sans paiement
    if (totalPrice === 0) {
      setLoading(true);
      try {
        // Create user
        try { await axios.post(`${API}/users`, { name: userName, email: userEmail, whatsapp: userWhatsapp }); }
        catch (err) { console.error("User creation error:", err); }
        
        // Create reservation directly (no payment needed)
        const res = await axios.post(`${API}/reservations`, reservation);
        
        // Mark discount code as used
        if (appliedDiscount) {
          await axios.post(`${API}/discount-codes/${appliedDiscount.id}/use`);
        }
        
        // MÉMORISATION CLIENT: Save client info for next visit
        saveClientInfo(userName, userEmail, userWhatsapp);
        
        setLastReservation(res.data);
        sendWhatsAppNotification(res.data, true);
        sendWhatsAppNotification(res.data, false);
        
        // NOTIFICATION AUTOMATIQUE AU COACH (email + WhatsApp API)
        notifyCoachAutomatic(res.data);
        
        setShowSuccess(true);
        resetFormKeepClient();
      } catch (err) { console.error(err); }
      setLoading(false);
      return;
    }

    // PAID RESERVATION: Check if payment is configured
    const hasStripeCheckout = concept.paymentCreditCard || concept.paymentTwint;
    const hasExternalLinks = paymentLinks.stripe?.trim() || paymentLinks.paypal?.trim() || paymentLinks.twint?.trim();
    
    if (!hasStripeCheckout && !hasExternalLinks) {
      setValidationMessage(t('noPaymentConfigured'));
      setTimeout(() => setValidationMessage(""), 4000);
      return;
    }

    // Create user first
    try { await axios.post(`${API}/users`, { name: userName, email: userEmail, whatsapp: userWhatsapp }); }
    catch (err) { console.error("User creation error:", err); }

    // STRIPE CHECKOUT (card + twint) si activé dans le concept
    if (hasStripeCheckout) {
      setLoading(true);
      try {
        const checkoutResponse = await axios.post(`${API}/create-checkout-session`, {
          productName: `${reservation.offerName} - ${reservation.courseName}`,
          amount: totalPrice,
          customerEmail: userEmail,
          originUrl: window.location.origin,
          reservationData: {
            id: reservation.userId,
            courseName: reservation.courseName,
            offerName: reservation.offerName
          }
        });
        
        // Sauvegarder la réservation en attente pour la finaliser après paiement
        localStorage.setItem('pendingReservation', JSON.stringify(reservation));
        
        // Rediriger vers Stripe Checkout
        if (checkoutResponse.data.url) {
          window.location.href = checkoutResponse.data.url;
        } else {
          throw new Error('No checkout URL received');
        }
      } catch (err) {
        console.error("Stripe checkout error:", err);
        setValidationMessage(err.response?.data?.detail || 'Erreur lors de la création du paiement');
        setTimeout(() => setValidationMessage(""), 4000);
        setLoading(false);
      }
      return;
    }

    // FALLBACK: Liens de paiement externes (ancienne méthode)
    setPendingReservation(reservation);

    // Open payment link
    if (paymentLinks.twint?.trim()) window.open(paymentLinks.twint, '_blank');
    else if (paymentLinks.stripe?.trim()) window.open(paymentLinks.stripe, '_blank');
    else if (paymentLinks.paypal?.trim()) window.open(paymentLinks.paypal, '_blank');

    setTimeout(() => setShowConfirmPayment(true), 800);
  };

  const confirmPayment = async () => {
    if (!pendingReservation) return;
    setLoading(true);
    try {
      const res = await axios.post(`${API}/reservations`, pendingReservation);
      if (pendingReservation.appliedDiscount) await axios.post(`${API}/discount-codes/${pendingReservation.appliedDiscount.id}/use`);
      
      // MÉMORISATION CLIENT: Save client info after successful payment
      saveClientInfo(pendingReservation.userName, pendingReservation.userEmail, pendingReservation.userWhatsapp);
      
      setLastReservation(res.data);
      sendWhatsAppNotification(res.data, true);
      sendWhatsAppNotification(res.data, false);
      
      // NOTIFICATION AUTOMATIQUE AU COACH (email + WhatsApp API)
      notifyCoachAutomatic(res.data);
      
      setShowSuccess(true);
      setShowConfirmPayment(false);
      resetFormKeepClient();
    } catch (err) { console.error(err); }
    setLoading(false);
  };

  const renderDates = (course) => {
    const dates = getNextOccurrences(course.weekday);
    return (
      <div className="grid grid-cols-2 gap-2 mt-3">
        {dates.map((date, idx) => {
          const dateISO = date.toISOString();
          const isSelected = selectedCourse?.id === course.id && selectedDates.includes(dateISO);
          return (
            <button key={idx} type="button"
              onClick={() => { 
                // Sélectionner le cours si différent
                if (selectedCourse?.id !== course.id) {
                  setSelectedCourse(course);
                  setSelectedDates([dateISO]); // Reset et ajouter la première date
                } else {
                  // Toggle la date (ajouter/retirer)
                  toggleDateSelection(dateISO);
                }
              }}
              className={`session-btn px-3 py-2 rounded-lg text-sm font-medium ${isSelected ? 'selected' : ''}`}
              style={{ color: 'white' }} data-testid={`date-btn-${course.id}-${idx}`}>
              <span>{formatDate(date, course.time, lang)} {isSelected && '✔'}</span>
              {course.maxCapacity && (
                <span className="text-xs opacity-60 ml-1">
                  · {course.maxCapacity - (course.reservations || 0)} places
                </span>
              )}
            </button>
          );
        })}
      </div>
    );
  };

  // Fonction de déconnexion Google OAuth
  const handleLogout = async () => {
    try {
      await axios.post(`${API}/auth/logout`, {}, { withCredentials: true });
    } catch (err) {
      console.error('Erreur déconnexion:', err);
    }
    // Nettoyer le localStorage coach
    localStorage.removeItem('afroboost_coach_mode');
    localStorage.removeItem('afroboost_coach_user');
    localStorage.removeItem('afroboost_coach_tab');
    localStorage.removeItem('afroboost_coach_session');
    sessionStorage.clear();
    
    setCoachMode(false);
    setCoachUser(null);
    console.log('[APP] 🚪 Déconnexion coach effectuée');
  };

  // Fonction de connexion Google OAuth - v9.2.4: PROPULSION FORCÉE avec mémoire morte
  const handleGoogleLogin = async (userData) => {
    // Persister la session coach
    localStorage.setItem('afroboost_coach_mode', 'true');
    localStorage.setItem('afroboost_coach_user', JSON.stringify(userData));

    // v41: Mémorisation persistante Super Admin / @afroboost.com
    if (userData?.email && isSuperAdminEmail(userData.email)) {
      localStorage.setItem(ADMIN_AUTH_TOKEN_KEY, JSON.stringify({
        email: userData.email,
        name: userData.name,
        user_id: userData.user_id,
        savedAt: new Date().toISOString()
      }));
      console.log('[APP] 🔑 Token admin persistant sauvegardé pour', userData.email);
    }
    
    setCoachUser(userData);
    setCoachMode(true);
    setShowCoachLogin(false);
    // v9.5.4: Fermer la page "Devenir Partenaire" après connexion
    setShowBecomeCoach(false);
    console.log('[APP] ✅ Connexion coach réussie:', userData?.email);
    
    // v9.2.4: MÉMOIRE MORTE - Vérifier si redirection post-paiement était demandée
    const shouldRedirectToDash = localStorage.getItem('redirect_to_dash');
    const redirectMessage = localStorage.getItem('afroboost_redirect_message');
    
    // Nettoyer les flags de redirection
    localStorage.removeItem('redirect_to_dash');
    localStorage.removeItem('afroboost_redirect_intent');
    localStorage.removeItem('afroboost_redirect_message');
    
    // Afficher le message de bienvenue si présent
    if (redirectMessage) {
      setValidationMessage(redirectMessage);
      setTimeout(() => setValidationMessage(""), 5000);
    }
    
    // v9.6.0: ROUTAGE INTELLIGENT - UN SEUL CLIC (FLASH LOGIN)
    try {
      // CAS C: Super Admin LOCAL CHECK FIRST - Accès illimité au Dashboard
      if (isSuperAdminEmail(userData?.email)) {
        console.log('[APP] 🔑 Super Admin détecté (local) - Redirection Dashboard FLASH');
        setUserRole('super_admin');
        // v9.6.0: FORCE RELOAD pour état propre du dashboard
        window.location.assign(window.location.origin + '/#coach-dashboard');
        return;
      }
      
      // Vérifier le rôle de l'utilisateur via API (fallback)
      const roleRes = await axios.get(`${API}/auth/role`, {
        headers: { 'X-User-Email': userData?.email || '' }
      });
      setUserRole(roleRes.data?.role || 'user');
      console.log('[APP] Rôle utilisateur:', roleRes.data?.role);
      
      // CAS C bis: Super Admin via API - Accès illimité au Dashboard
      if (roleRes.data?.is_super_admin) {
        console.log('[APP] 🔑 Super Admin détecté (API) - Redirection Dashboard FLASH');
        // v9.6.0: FORCE RELOAD
        window.location.assign(window.location.origin + '/#coach-dashboard');
        return;
      }
      
      // Vérifier le statut partenaire et les crédits
      const partnerRes = await axios.get(`${API}/check-partner/${encodeURIComponent(userData?.email || '')}`);
      console.log('[APP] 📊 Statut partenaire:', partnerRes.data);
      
      // v9.6.8: CAS A - Partenaire EXISTANT (inscrit dans coaches) - Redirection IMMÉDIATE
      // RÈGLE: Tout partenaire inscrit va au Dashboard, même sans crédits
      if (partnerRes.data?.is_partner) {
        console.log('[APP] 🚀 Partenaire existant - Redirection Dashboard FLASH (crédits:', partnerRes.data?.credits || 0, ')');
        // v9.6.8: FORCE RELOAD - Le partenaire verra son solde dans le dashboard
        window.location.assign(window.location.origin + '/#coach-dashboard');
        return;
      }
      
      // CAS B: NON-partenaire (pas inscrit) - Afficher la page Packs
      console.log('[APP] ⚠️ Non-partenaire - Affichage page d\'inscription');
      setValidationMessage('✨ Bienvenue ! Choisissez un pack pour devenir partenaire.');
      setTimeout(() => setValidationMessage(""), 6000);
      
      // Ouvrir la page "Devenir Partenaire" avec les packs
      setShowBecomeCoach(true);
      return;
      
    } catch (err) {
      console.error('[APP] Erreur vérification statut:', err);
      // En cas d'erreur API, on essaie quand même le dashboard
      // (l'accès sera refusé côté backend si nécessaire)
      window.location.hash = '#coach-dashboard';
    }
  };
  
  // Fonction pour quitter le mode coach sans déconnexion
  const handleBackFromCoach = () => {
    localStorage.removeItem('afroboost_coach_mode');
    setCoachMode(false);
    console.log('[APP] ↩️ Retour au site (session conservée)');
  };

  if (showSplash) return <SplashScreen logoUrl={concept.logoUrl} />;
  if (showCoachLogin) return <CoachLoginModal t={t} onLogin={handleGoogleLogin} onCancel={() => { setShowCoachLogin(false); setLoginWelcomeMessage(null); }} welcomeMessage={loginWelcomeMessage} />;
  
  // Page "Devenir Coach"
  if (showBecomeCoach) return (
    <BecomeCoachPage 
      onClose={() => setShowBecomeCoach(false)} 
      onSuccess={(coach) => {
        console.log('[APP] Coach inscrit:', coach);
        setShowBecomeCoach(false);
      }}
    />
  );
  
  // Panneau Super Admin
  if (showSuperAdminPanel && coachUser?.email) return (
    <SuperAdminPanel 
      userEmail={coachUser.email}
      onClose={() => setShowSuperAdminPanel(false)}
    />
  );
  
  // v12: Vitrine Coach publique - rendu en overlay (plus d'early return)
  // La vitrine s'affiche PAR-DESSUS le carrousel pour une transition fluide
  // (Déplacé dans le JSX principal au lieu d'un early return)
  
  // === v9.2.8: PAGE DE MAINTENANCE - Blocage total sauf Super Admin ===
  const isSuperAdmin = isSuperAdminEmail(coachUser?.email);
  if (platformSettings.maintenance_mode && !isSuperAdmin && !coachMode) {
    return (
      <div 
        className="fixed inset-0 flex flex-col items-center justify-center p-6"
        style={{
          background: 'linear-gradient(180deg, #0a0510 0%, #1a0520 50%, #0a0510 100%)',
          color: 'white'
        }}
      >
        {/* Logo animé */}
        <div 
          className="mb-8"
          style={{
            animation: 'pulse 2s ease-in-out infinite',
            filter: 'drop-shadow(0 0 20px rgba(217, 28, 210, 0.5))'
          }}
        >
          <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="#D91CD2" strokeWidth="1.5">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        
        {/* Titre */}
        <h1 
          className="text-3xl md:text-4xl font-bold mb-4 text-center"
          style={{
            background: 'linear-gradient(135deg, #D91CD2, #8B5CF6)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent'
          }}
        >
          Maintenance en cours
        </h1>
        
        {/* Message */}
        <p className="text-white/70 text-center max-w-md mb-8">
          Nous améliorons votre expérience Afroboost.
          <br />
          Revenez dans quelques instants !
        </p>
        
        {/* Barre de progression animée */}
        <div 
          className="w-64 h-1 rounded-full overflow-hidden"
          style={{ background: 'rgba(255,255,255,0.1)' }}
        >
          <div 
            className="h-full rounded-full"
            style={{
              background: 'linear-gradient(90deg, #D91CD2, #8B5CF6)',
              width: '30%',
              animation: 'loading 1.5s ease-in-out infinite'
            }}
          />
        </div>
        
        {/* Contact */}
        <p className="mt-8 text-sm text-white/40">
          Questions ? <a href="mailto:contact.artboost@gmail.com" className="underline hover:text-white/60">contact.artboost@gmail.com</a>
        </p>
        
        {/* Animation CSS */}
        <style>{`
          @keyframes loading {
            0% { transform: translateX(-100%); }
            50% { transform: translateX(200%); }
            100% { transform: translateX(-100%); }
          }
        `}</style>
      </div>
    );
  }
  
  // v66: ?visitor=true bypass — le Super Admin voit la homepage publique telle que les visiteurs la voient
  // v67: Détection synchrone — si l'URL est /coach/{slugSuperAdmin}, c'est aussi du visitor mode
  const urlParams = new URLSearchParams(window.location.search);
  const pathSlugMatch = window.location.pathname.match(/^\/(coach|partner)\/(.+)$/);
  const urlSlug = pathSlugMatch ? decodeURIComponent(pathSlugMatch[2]).toLowerCase().trim() : null;
  const isSuperAdminSlugInUrl = urlSlug && SUPER_ADMIN_SLUGS.includes(urlSlug);
  const isVisitorMode = urlParams.get('visitor') === 'true' || isSuperAdminSlugInUrl;

  // v18.2: Si l'URL est /coach/xxx, afficher la vitrine MÊME si le coach est connecté
  // v67: JAMAIS CoachVitrine pour le Super Admin — sa vitrine = homepage
  if (coachMode && !isVisitorMode) {
    if (showCoachVitrine) {
      // v67: Dernier verrou — si showCoachVitrine est un slug Super Admin, forcer homepage
      const vitrineSlug = (showCoachVitrine || '').toLowerCase().trim();
      if (SUPER_ADMIN_SLUGS.includes(vitrineSlug) || SUPER_ADMIN_EMAILS.some(e => e.toLowerCase() === vitrineSlug)) {
        // Ne pas rendre CoachVitrine, fall through vers la homepage
        console.log('[V67] VERROU FINAL: CoachVitrine bloquée pour slug Super Admin →', vitrineSlug);
      } else {
        return (
          <div className="fixed inset-0 z-50" style={{ background: '#000' }}>
            <CoachVitrine
              username={showCoachVitrine}
              onClose={() => { setShowCoachVitrine(null); window.history.pushState({}, '', '/'); }}
              onBack={() => { setShowCoachVitrine(null); window.history.pushState({}, '', '/'); }}
            />
          </div>
        );
      }
    }
    if (!showCoachVitrine || !SUPER_ADMIN_SLUGS.includes((showCoachVitrine || '').toLowerCase().trim())) {
      return <CoachDashboard t={t} lang={lang} onBack={handleBackFromCoach} onLogout={handleLogout} coachUser={coachUser} />;
    }
    // v67: Si on arrive ici, c'est un slug Super Admin en coachMode → on continue vers la homepage publique
  }

  // Filtrer les offres et cours selon visibilité, filtre actif et recherche
  // =====================================================
  // SÉPARATION TOTALE : PRODUITS vs COURS/SESSIONS
  // Les produits physiques sont COMPLÈTEMENT INDÉPENDANTS des cours
  // =====================================================
  // FILTRAGE PAR VISIBILITÉ - Une offre invisible NE DOIT JAMAIS apparaître
  // Utilise 'visible !== false' pour inclure les offres sans champ visible défini
  // =====================================================
  
  // 1. PRODUITS PHYSIQUES (isProduct: true) - Filtrés par visibilité
  const visibleProducts = offers.filter(o => 
    o.isProduct === true && o.visible !== false
  );
  
  // 2. OFFRES/SERVICES (isProduct: false ou undefined) - Filtrés par visibilité
  const visibleServices = offers.filter(o => 
    !o.isProduct && o.visible !== false
  );
  
  // 3. COURS avec leur propre visibilité (exclure les archivés et invisibles)
  // v12: DÉDUPLICATION par nom - garder uniquement le premier de chaque nom
  const baseCourses = (() => {
    const filtered = courses.filter(c => c.visible !== false && c.archived !== true);
    const seen = new Set();
    return filtered.filter(c => {
      const key = (c.name || '').toLowerCase().trim();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  })();
  
  // Fonction de recherche floue (fuzzy search)
  const fuzzyMatch = (text, query) => {
    if (!text || !query) return false;
    const normalizedText = text.toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9\s]/g, "");
    const normalizedQuery = query.toLowerCase()
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9\s]/g, "");
    
    if (normalizedText.includes(normalizedQuery)) return true;
    const queryWords = normalizedQuery.split(/\s+/).filter(w => w.length > 1);
    return queryWords.every(word => normalizedText.includes(word));
  };
  
  // Synonymes courants pour la recherche
  const synonyms = {
    'session': ['séance', 'cours', 'class'],
    'seance': ['session', 'cours', 'class'],
    'abonnement': ['abo', 'forfait', 'pack'],
    'abo': ['abonnement', 'forfait', 'pack'],
    'cardio': ['fitness', 'sport', 'entrainement'],
    'afrobeat': ['afro', 'danse', 'dance'],
    'produit': ['article', 'shop', 'boutique'],
    'tshirt': ['t-shirt', 'tee', 'haut'],
    't-shirt': ['tshirt', 'tee', 'haut']
  };
  
  const searchWithSynonyms = (text, query) => {
    if (fuzzyMatch(text, query)) return true;
    const queryNorm = query.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    for (const [key, values] of Object.entries(synonyms)) {
      if (queryNorm.includes(key)) {
        for (const syn of values) {
          if (fuzzyMatch(text, query.replace(new RegExp(key, 'gi'), syn))) return true;
        }
      }
    }
    return false;
  };
  
  // =====================================================
  // FILTRAGE SÉPARÉ : Sessions/Offres vs Produits vs Cours
  // =====================================================
  
  // Filtrer les SERVICES (sessions, abonnements) selon la recherche
  let filteredServices = visibleServices;
  if (searchQuery.trim()) {
    const query = searchQuery.trim();
    filteredServices = visibleServices.filter(offer => 
      searchWithSynonyms(offer.name || '', query) ||
      searchWithSynonyms(offer.description || '', query) ||
      searchWithSynonyms(offer.keywords || '', query)
    );
  }
  
  // Filtrer les PRODUITS selon la recherche
  let filteredProducts = visibleProducts;
  if (searchQuery.trim()) {
    const query = searchQuery.trim();
    filteredProducts = visibleProducts.filter(product => 
      searchWithSynonyms(product.name || '', query) ||
      searchWithSynonyms(product.description || '', query) ||
      searchWithSynonyms(product.keywords || '', query)
    );
  }
  
  // Filtrer les COURS selon la recherche
  let visibleCourses = baseCourses;
  if (activeFilter === 'shop') {
    visibleCourses = []; // Masquer les cours sur la page Shop
  } else if (searchQuery.trim()) {
    const query = searchQuery.trim();
    visibleCourses = baseCourses.filter(course => 
      searchWithSynonyms(course.name || '', query) ||
      searchWithSynonyms(course.locationName || '', query)
    );
  }
  
  // =====================================================
  // VARIABLE COMBINÉE pour l'affichage selon le filtre actif
  // =====================================================
  let visibleOffers;
  if (activeFilter === 'shop') {
    visibleOffers = filteredProducts; // Uniquement produits
  } else if (activeFilter === 'sessions' || activeFilter === 'offers') {
    visibleOffers = filteredServices; // Uniquement services
  } else {
    visibleOffers = [...filteredServices, ...filteredProducts]; // Tout
  }
  
  const totalPrice = calculateTotal();

  // Si on est sur /v/:slug, afficher le MediaViewer
  if (mediaSlug) {
    return <MediaViewer slug={mediaSlug} />;
  }

  return (
    <div className="w-full min-h-screen relative section-gradient" style={{ fontFamily: 'system-ui, sans-serif' }}>
      <LanguageSelector lang={lang} setLang={setLang} />

      {/* Event Poster Modal (Popup d'accueil) */}
      {showEventPoster && concept.eventPosterMediaUrl && (
        <EventPosterModal 
          mediaUrl={concept.eventPosterMediaUrl} 
          onClose={closeEventPoster} 
        />
      )}

      {/* PWA Install Banner */}
      {/* v15: Bannière install compacte - barre fine en bas au lieu du gros bandeau en haut */}
      {showInstallBanner && (
        <div
          className="fixed bottom-0 left-0 right-0 z-50 px-3 py-2"
          style={{
            background: 'rgba(10, 10, 20, 0.95)',
            borderTop: '1px solid rgba(217, 28, 210, 0.3)',
            backdropFilter: 'blur(12px)'
          }}
          data-testid="pwa-install-banner"
        >
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm">{isIOS ? '📤' : '📲'}</span>
              <p className="text-white text-xs opacity-80">
                {isIOS ? 'Ajoutez Afroboost à votre écran' : 'Installer l\'app Afroboost'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleInstallClick}
                className="px-3 py-1.5 rounded-full text-xs font-medium"
                style={{ background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)', color: '#fff' }}
                data-testid="pwa-install-btn"
              >
                {isIOS ? 'Comment ?' : 'Installer'}
              </button>
              <button
                onClick={dismissInstallBanner}
                className="text-white opacity-50 hover:opacity-100 text-xs p-1"
                data-testid="pwa-dismiss-btn"
              >
                ✕
              </button>
            </div>
          </div>
        </div>
      )}

      {showConfirmPayment && <ConfirmPaymentOverlay t={t} onConfirm={confirmPayment} onCancel={() => { setShowConfirmPayment(false); setPendingReservation(null); }} />}
      {showSuccess && lastReservation && (
        <SuccessOverlay 
          t={t} 
          data={lastReservation} 
          onClose={() => setShowSuccess(false)} 
          onClearTicket={clearSavedTicket}
        />
      )}
      
      {/* Page de succès paiement Stripe (plein écran) */}
      {showPaymentSuccessPage && lastReservation && (
        <PaymentSuccessPage 
          reservation={lastReservation} 
          t={t}
          onClose={() => {
            setShowPaymentSuccessPage(false);
            // Optionnel: Afficher aussi l'overlay ticket pour permettre le téléchargement
            setShowSuccess(true);
          }} 
        />
      )}

      {/* v9.7.2: Flux Reels - IMMERSIF 85vh pour Samsung Ultra 24 */}
      <div 
        className="relative w-full" 
        style={{ 
          height: '85vh',  // v9.7.2: 85vh pour Samsung Ultra 24
          maxHeight: '85vh',
          background: '#000000' 
        }}
      >
        <PartnersCarousel
          onPartnerClick={(partner) => {
            const username = partner.email || partner.id || partner.name?.toLowerCase().replace(/\s+/g, '-');
            // v67: Si clic sur le Super Admin dans le carousel → NE PAS ouvrir CoachVitrine
            // La homepage EST sa vitrine, pas besoin d'overlay
            const slugCheck = (username || '').toLowerCase().trim();
            if (SUPER_ADMIN_SLUGS.includes(slugCheck) || SUPER_ADMIN_EMAILS.some(e => e.toLowerCase() === slugCheck)) {
              console.log('[V67] Clic carousel Super Admin → scroll vers contenu homepage');
              const sessionsEl = document.getElementById('sessions-section');
              if (sessionsEl) sessionsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
              return; // Ne PAS ouvrir CoachVitrine overlay
            }
            // v12: Transition fluide sans rechargement page (partenaires seulement)
            window.history.pushState({}, '', `/coach/${username}`);
            setShowCoachVitrine(username);
          }}
          onSearch={() => setShowCoachSearch(true)}
          maintenanceMode={platformSettings.maintenance_mode}
          isSuperAdmin={isSuperAdminEmail(coachUser?.email)}
          lang={lang}
          onLangChange={setLang}
          currentVitrineEmail={null}
          onBuyVideo={(videoOffer) => {
            console.log('[V34-BUY] Achat vidéo depuis carousel:', videoOffer);
            handleSelectOffer(videoOffer);
          }}
        />
      </div>

      {/* v14: VITRINE COACH OVERLAY - Transition instantanée, pas d'écran de chargement violet */}
      {showCoachVitrine && (
        <div
          className="fixed inset-0 z-50"
          style={{
            background: '#000'
          }}
        >
          <CoachVitrine
            username={showCoachVitrine}
            onClose={() => {
              setShowCoachVitrine(null);
              window.history.pushState({}, '', '/');
            }}
            onBack={() => {
              setShowCoachVitrine(null);
              window.history.pushState({}, '', '/');
            }}
          />
        </div>
      )}

      {/* v35: SECTION AUDIO déplacée vers le Shop — voir plus bas */}

      {/* v15: BARRE DE NAVIGATION STICKY - Sections claires */}
      <div
        className="w-full"
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 40,
          background: 'rgba(10, 10, 20, 0.95)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          backdropFilter: 'blur(12px)',
          WebkitBackdropFilter: 'blur(12px)'
        }}
      >
        <div className="max-w-4xl mx-auto flex items-center gap-1 px-4 py-2 overflow-x-auto hide-scrollbar">
          {[
            { key: 'all', label: 'Tout', icon: '✨' },
            { key: 'sessions', label: 'Sessions', icon: '📅' },
            { key: 'offers', label: 'Offres', icon: '🎁' },
            { key: 'shop', label: 'Shop', icon: '🛒' }
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => {
                setActiveFilter(tab.key);
                const sectionMap = { sessions: 'sessions-section', offers: 'offers-section', shop: 'products-section' };
                if (sectionMap[tab.key]) {
                  const el = document.getElementById(sectionMap[tab.key]);
                  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
              }}
              className="flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all"
              style={{
                background: activeFilter === tab.key
                  ? 'linear-gradient(135deg, rgba(217, 28, 210, 0.3), rgba(139, 92, 246, 0.3))'
                  : 'rgba(255, 255, 255, 0.06)',
                border: activeFilter === tab.key
                  ? '1px solid rgba(217, 28, 210, 0.5)'
                  : '1px solid rgba(255, 255, 255, 0.1)',
                color: activeFilter === tab.key ? '#fff' : 'rgba(255, 255, 255, 0.6)'
              }}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* v9.5.8: Contenu scrollable SOUS le flux Reels */}
      <div
        className="max-w-4xl mx-auto px-6 pt-4"
        style={{
          background: 'transparent',
          border: 'none',
          boxShadow: 'none'
        }}
      >

        {/* Message si aucun résultat */}
        {filteredServices.length === 0 && filteredProducts.length === 0 && visibleCourses.length === 0 && searchQuery.trim() && (
          <div className="text-center py-8 mb-8 rounded-xl" style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
            <p className="text-white opacity-70">🔍 Aucun résultat pour "{searchQuery}"</p>
            <button 
              onClick={() => { setSearchQuery(''); setActiveFilter('all'); }}
              className="mt-3 px-4 py-2 rounded-lg text-sm"
              style={{ background: 'rgba(217, 28, 210, 0.3)', color: '#fff' }}
            >
              Réinitialiser les filtres
            </button>
          </div>
        )}

        {/* v16: DESCRIPTION PARTENAIRE — entre nav et sessions */}
        {concept.description && activeFilter !== 'shop' && (
          <div className="mb-6 fade-in-section" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '16px' }}>
            <p className="text-white/70 text-sm leading-relaxed" style={{ fontWeight: 300 }}>
              {concept.description}
            </p>
          </div>
        )}

        {/* Section Sessions - Masquée si filtre Shop actif */}
        {activeFilter !== 'shop' && visibleCourses.length > 0 && (
          <div id="sessions-section" className="mb-8 fade-in-section" style={{ background: 'transparent', border: 'none', boxShadow: 'none' }}>
            <h2 className="font-semibold mb-4 text-white" style={{ fontSize: '18px' }}>{t('chooseSession')}</h2>
            {/* Container avec scroll pour mobile - scrollbar rose fine 4px */}
            <div 
              className="space-y-4 sessions-scrollbar" 
              style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '8px', background: 'transparent' }}
            >
              {visibleCourses.map(course => (
                <div 
                  key={course.id} 
                  className={`course-card rounded-xl p-5 ${selectedCourse?.id === course.id ? 'selected' : ''}`} 
                  data-testid={`course-card-${course.id}`}
                  style={{ 
                    background: selectedCourse?.id === course.id ? 'rgba(217, 28, 210, 0.08)' : 'transparent',
                    border: 'none',
                    borderLeft: selectedCourse?.id === course.id ? '2px solid #d91cd2' : 'none',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                    boxShadow: 'none'
                  }}
                >
                  <h3 className="font-semibold text-white">{course.name}</h3>
                  <div className="flex items-center gap-2 text-xs text-white opacity-60 mb-1">
                    <LocationIcon />
                    <span>{course.locationName}</span>
                    {course.mapsUrl && (
                      <a href={course.mapsUrl} target="_blank" rel="noopener noreferrer" className="ml-2 flex items-center gap-1" style={{ color: '#8b5cf6' }}
                        onClick={(e) => e.stopPropagation()}>
                        <LocationIcon /> Maps
                      </a>
                    )}
                  </div>
                  {renderDates(course)}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* =====================================================
            SECTION OFFRES/SERVICES - Affichée si cours + dates sélectionnées
            ===================================================== */}
        {selectedCourse && selectedDates.length > 0 && filteredServices.length > 0 && (
          <div id="offers-section" className="mb-8 fade-in-section">
            <h2 className="font-semibold mb-2 text-white" style={{ fontSize: '18px' }}>{t('chooseOffer')}</h2>
            
            <p className="text-sm mb-4" style={{ color: '#d91cd2' }}>
              👉 Sélectionnez une offre pour continuer
            </p>
            
            <OffersSliderAutoPlay 
              offers={filteredServices}
              selectedOffer={selectedOffer}
              onSelectOffer={handleSelectOffer}
            />
          </div>
        )}

        {/* =====================================================
            BOUTON EXPERIENCE AUDIO IMMERSIVE
            Visible si: cours sélectionné + playlist existe + feature flag activé
            ===================================================== */}
        {selectedCourse && 
         selectedCourse.playlist && 
         selectedCourse.playlist.length > 0 && 
         audioFeatureEnabled && (
          <div className="mb-6">
            <button
              onClick={() => setShowAudioPlayer(true)}
              className="w-full py-4 rounded-xl font-semibold text-white transition-all duration-300 hover:scale-[1.02] flex items-center justify-center gap-3"
              style={{
                background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.3), rgba(217, 28, 210, 0.3))',
                border: '1px solid rgba(217, 28, 210, 0.5)',
                boxShadow: '0 0 20px rgba(217, 28, 210, 0.2)'
              }}
              data-testid="join-audio-experience-btn"
            >
              <span style={{ fontSize: '24px' }}>🎧</span>
              <span>Rejoindre l'expérience immersive</span>
            </button>
            <p className="text-center text-white/40 text-xs mt-2">
              Ambiance musicale pendant votre session
            </p>
          </div>
        )}

        {/* =====================================================
            LECTEUR AUDIO IMMERSIF (Mini Player)
            Design sobre sur fond noir, contrôle du volume
            ===================================================== */}
        {showAudioPlayer && selectedCourse?.playlist?.length > 0 && (
          <div 
            className="fixed bottom-0 left-0 right-0 z-50 p-4"
            style={{
              background: 'linear-gradient(to top, #000000, rgba(0,0,0,0.95))',
              borderTop: '1px solid rgba(217, 28, 210, 0.3)',
              boxShadow: '0 -10px 30px rgba(0,0,0,0.8)'
            }}
          >
            <div className="max-w-lg mx-auto">
              {/* Header avec fermeture */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xl">🎧</span>
                  <div>
                    <p className="text-white text-sm font-medium">Expérience immersive</p>
                    <p className="text-white/50 text-xs truncate max-w-[200px]">
                      {selectedCourse.name}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => {
                    setShowAudioPlayer(false);
                    setIsPlaying(false);
                    if (audioRef.current) {
                      audioRef.current.pause();
                    }
                  }}
                  className="p-2 rounded-full hover:bg-white/10 transition-colors"
                  style={{ color: '#fff' }}
                  data-testid="close-audio-player"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                  </svg>
                </button>
              </div>

              {/* Contrôles audio */}
              <div className="flex items-center gap-4">
                {/* Bouton Play/Pause */}
                <button
                  onClick={() => {
                    if (audioRef.current) {
                      if (isPlaying) {
                        audioRef.current.pause();
                      } else {
                        audioRef.current.play().catch(console.error);
                      }
                      setIsPlaying(!isPlaying);
                    }
                  }}
                  className="w-12 h-12 rounded-full flex items-center justify-center transition-all hover:scale-110"
                  style={{
                    background: 'linear-gradient(135deg, #d91cd2, #8b5cf6)',
                    boxShadow: isPlaying ? '0 0 20px rgba(217, 28, 210, 0.5)' : 'none'
                  }}
                  data-testid="audio-play-pause"
                >
                  {isPlaying ? (
                    <svg className="w-5 h-5 text-white" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/>
                    </svg>
                  ) : (
                    <svg className="w-5 h-5 text-white ml-1" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M8 5v14l11-7z"/>
                    </svg>
                  )}
                </button>

                {/* Piste suivante/précédente (si plusieurs pistes) */}
                {selectedCourse.playlist.length > 1 && (
                  <>
                    <button
                      onClick={() => {
                        const newIndex = (currentTrackIndex - 1 + selectedCourse.playlist.length) % selectedCourse.playlist.length;
                        setCurrentTrackIndex(newIndex);
                        if (audioRef.current && isPlaying) {
                          audioRef.current.load();
                          audioRef.current.play().catch(console.error);
                        }
                      }}
                      className="p-2 rounded-full hover:bg-white/10"
                      style={{ color: '#fff' }}
                      data-testid="audio-prev"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M6 6h2v12H6V6zm3.5 6l8.5 6V6l-8.5 6z"/>
                      </svg>
                    </button>
                    <button
                      onClick={() => {
                        const newIndex = (currentTrackIndex + 1) % selectedCourse.playlist.length;
                        setCurrentTrackIndex(newIndex);
                        if (audioRef.current && isPlaying) {
                          audioRef.current.load();
                          audioRef.current.play().catch(console.error);
                        }
                      }}
                      className="p-2 rounded-full hover:bg-white/10"
                      style={{ color: '#fff' }}
                      data-testid="audio-next"
                    >
                      <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M6 18l8.5-6L6 6v12zm2 0V6l6.5 6L8 18zm8-12h2v12h-2V6z"/>
                      </svg>
                    </button>
                  </>
                )}

                {/* Contrôle du volume */}
                <div className="flex items-center gap-2 flex-1">
                  <svg className="w-4 h-4 text-white/60" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02z"/>
                  </svg>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={audioVolume}
                    onChange={(e) => {
                      const vol = parseFloat(e.target.value);
                      setAudioVolume(vol);
                      if (audioRef.current) {
                        audioRef.current.volume = vol;
                      }
                    }}
                    className="flex-1 h-1 rounded-full appearance-none cursor-pointer"
                    style={{
                      background: `linear-gradient(to right, #d91cd2 0%, #d91cd2 ${audioVolume * 100}%, rgba(255,255,255,0.2) ${audioVolume * 100}%, rgba(255,255,255,0.2) 100%)`
                    }}
                    data-testid="audio-volume"
                  />
                  <svg className="w-5 h-5 text-white/60" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
                  </svg>
                </div>
              </div>

              {/* Info piste actuelle */}
              <div className="mt-3 text-center">
                <p className="text-white/40 text-xs">
                  Piste {currentTrackIndex + 1} / {selectedCourse.playlist.length}
                </p>
              </div>

              {/* Élément audio caché (autoplay=false pour respecter les règles) */}
              <audio
                ref={audioRef}
                src={selectedCourse.playlist[currentTrackIndex]}
                onEnded={() => {
                  // Passer à la piste suivante automatiquement
                  const nextIndex = (currentTrackIndex + 1) % selectedCourse.playlist.length;
                  setCurrentTrackIndex(nextIndex);
                  if (audioRef.current) {
                    audioRef.current.load();
                    audioRef.current.play().catch(console.error);
                  }
                }}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
              />
            </div>
          </div>
        )}

        {/* =====================================================
            SECTION PRODUITS PHYSIQUES - TOUJOURS VISIBLE si produits disponibles
            Complètement indépendante des cours
            ===================================================== */}
        {filteredProducts.length > 0 && (activeFilter === 'shop' || activeFilter === 'all') && (
          <div id="products-section" className="mb-8 fade-in-section" style={{ paddingTop: '10px' }}>
            {/* v15: Header Shop amélioré avec badge livraison */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="font-semibold text-white" style={{ fontSize: '18px' }}>
                  {t('shop') || 'Boutique'}
                </h2>
                <p className="text-xs mt-0.5" style={{ color: 'rgba(255,255,255,0.5)', fontWeight: '300' }}>
                  Produits exclusifs Afroboost
                </p>
              </div>
              <span
                className="text-xs px-3 py-1 rounded-full"
                style={{
                  background: 'rgba(34, 197, 94, 0.15)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                  color: 'rgba(34, 197, 94, 0.9)'
                }}
              >
                📦 Livraison dispo
              </span>
            </div>
            
            <OffersSliderAutoPlay 
              offers={filteredProducts}
              selectedOffer={selectedOffer}
              onSelectOffer={(product) => {
                // Pour les produits, pas besoin de cours/dates
                setSelectedCourse(null);
                setSelectedDates([]);
                handleSelectOffer(product);
              }}
            />
          </div>
        )}

        {/* v57: SECTION AUDIO SHOP — Sélection multiple, prix dégressif, scroll, modale */}
        {(() => {
          const allAudioTracks = [];
          courses.forEach(course => {
            if (course.audio_tracks && course.audio_tracks.length > 0) {
              course.audio_tracks
                .filter(track => track.visible !== false && track.url)
                .forEach(track => {
                  allAudioTracks.push({ ...track, courseName: course.name, courseId: course.id });
                });
            }
          });
          if (studioAudioTracks && studioAudioTracks.length > 0) {
            studioAudioTracks.forEach(track => {
              if (!allAudioTracks.find(t => t.id === track.id)) {
                allAudioTracks.push(track);
              }
            });
          }
          if (allAudioTracks.length === 0) return null;

          // v57: Prix dégressif — plus on achète, plus c'est avantageux
          const paidTracks = allAudioTracks.filter(t => t.price && t.price > 0);
          const selectedPaidTracks = selectedAudioTracks.filter(id => paidTracks.find(t => (t.id || t.courseId) === id));
          const selectedCount = selectedPaidTracks.length;

          const calcBundlePrice = (ids) => {
            let total = 0;
            ids.forEach(id => {
              const t = paidTracks.find(tr => (tr.id || tr.courseId) === id);
              if (t) total += t.price;
            });
            // Réduction: 2 titres = -25%, 3+ titres = -40%
            if (ids.length >= 3) return Math.round(total * 0.6 * 100) / 100;
            if (ids.length === 2) return Math.round(total * 0.75 * 100) / 100;
            return total;
          };

          const bundlePrice = calcBundlePrice(selectedPaidTracks);
          const fullPrice = selectedPaidTracks.reduce((sum, id) => {
            const t = paidTracks.find(tr => (tr.id || tr.courseId) === id);
            return sum + (t ? t.price : 0);
          }, 0);

          const toggleTrackSelect = (trackId) => {
            setSelectedAudioTracks(prev =>
              prev.includes(trackId) ? prev.filter(id => id !== trackId) : [...prev, trackId]
            );
          };

          const handleBuyBundle = () => {
            const names = selectedPaidTracks.map(id => {
              const t = paidTracks.find(tr => (tr.id || tr.courseId) === id);
              return t ? t.title : '';
            }).filter(Boolean).join(' + ');
            console.log('[V57-AUDIO] Achat groupé:', selectedCount, 'titres,', bundlePrice, 'CHF');
            handleSelectOffer({
              name: selectedCount === 1 ? names : `Playlist (${selectedCount} titres)`,
              price: bundlePrice,
              id: selectedPaidTracks.join('_'),
              type: 'audio',
              audioTrackIds: selectedPaidTracks,
              thumbnail: null
            });
          };

          const useScroll = allAudioTracks.length > 3;

          return (
            <div id="audio-shop-section" className="mb-8 fade-in-section" style={{ paddingTop: '10px' }}>
              {/* Header Audio Shop */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div>
                  <h2 style={{ color: '#fff', fontSize: '18px', fontWeight: 600, margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '22px' }}>🎧</span> Audio Shop
                  </h2>
                  <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', fontWeight: 300, marginTop: '2px' }}>
                    Musiques & contenus audio exclusifs
                  </p>
                </div>
                <span style={{
                  fontSize: '11px', padding: '4px 10px', borderRadius: '20px',
                  background: 'rgba(217,28,210,0.12)', border: '1px solid rgba(217,28,210,0.25)',
                  color: 'rgba(217,28,210,0.9)'
                }}>
                  🎵 {allAudioTracks.length} titre{allAudioTracks.length > 1 ? 's' : ''}
                </span>
              </div>

              {/* v57: Info prix dégressif */}
              {paidTracks.length >= 2 && (
                <div style={{
                  padding: '8px 14px', borderRadius: '10px', marginBottom: '12px',
                  background: 'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(217,28,210,0.08))',
                  border: '1px solid rgba(34,197,94,0.2)',
                  display: 'flex', alignItems: 'center', gap: '8px'
                }}>
                  <span style={{ fontSize: '16px' }}>💰</span>
                  <span style={{ color: 'rgba(255,255,255,0.7)', fontSize: '11px' }}>
                    Sélectionnez plusieurs titres pour un prix réduit : <strong style={{ color: '#22c55e' }}>-25% dès 2 titres, -40% dès 3 titres</strong>
                  </span>
                </div>
              )}

              {/* Audio Cards — scroll si +3 tracks */}
              <div style={{
                display: 'flex', flexDirection: 'column', gap: '12px',
                ...(useScroll ? {
                  maxHeight: '380px', overflowY: 'auto',
                  paddingRight: '4px',
                  scrollbarWidth: 'thin',
                  scrollbarColor: 'rgba(217,28,210,0.3) transparent'
                } : {})
              }}>
                {allAudioTracks.map((track, idx) => {
                  const trackId = track.id || track.courseId;
                  return (
                    <AudioPlayer
                      key={trackId || `audio-shop-${idx}`}
                      audioUrl={track.url?.startsWith('/api/') ? `${API.replace('/api', '')}${track.url}` : track.url}
                      title={track.title || 'Audio'}
                      thumbnail={track.cover_url}
                      description={track.description}
                      price={track.price}
                      isPreview={!!track.price && track.price > 0}
                      previewDuration={track.preview_duration || 30}
                      selectable={paidTracks.length >= 2}
                      isSelected={selectedAudioTracks.includes(trackId)}
                      onToggleSelect={() => toggleTrackSelect(trackId)}
                      onThumbnailClick={(track.cover_url || track.description) ? () => setAudioLightbox(track) : undefined}
                      onBuyClick={track.price > 0 ? () => {
                        console.log('[V57-AUDIO] Achat audio:', track.title, track.price, 'CHF');
                        handleSelectOffer({
                          name: track.title,
                          price: track.price,
                          id: trackId,
                          type: 'audio',
                          thumbnail: track.cover_url
                        });
                      } : undefined}
                    />
                  );
                })}
              </div>

              {/* v57: Bouton achat groupé — visible si au moins 2 sélectionnés */}
              {selectedCount >= 2 && (
                <div style={{
                  marginTop: '16px', padding: '16px', borderRadius: '14px',
                  background: 'linear-gradient(135deg, rgba(217,28,210,0.12), rgba(139,92,246,0.1))',
                  border: '1px solid rgba(217,28,210,0.3)',
                  textAlign: 'center'
                }}>
                  <div style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                    <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', textDecoration: 'line-through' }}>
                      {fullPrice} CHF
                    </span>
                    <span style={{ color: '#22c55e', fontSize: '16px', fontWeight: 700 }}>
                      {bundlePrice} CHF
                    </span>
                    <span style={{
                      fontSize: '10px', padding: '2px 8px', borderRadius: '10px',
                      background: 'rgba(34,197,94,0.2)', color: '#22c55e', fontWeight: 600
                    }}>
                      -{Math.round((1 - bundlePrice / fullPrice) * 100)}%
                    </span>
                  </div>
                  <button
                    onClick={handleBuyBundle}
                    style={{
                      width: '100%', padding: '12px 20px', borderRadius: '12px',
                      background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                      color: '#fff', fontWeight: 700, fontSize: '14px',
                      border: 'none', cursor: 'pointer',
                      boxShadow: '0 0 20px rgba(217,28,210,0.3)',
                      transition: 'transform 0.2s'
                    }}
                    onMouseEnter={(e) => { e.currentTarget.style.transform = 'scale(1.02)'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
                  >
                    🛒 Acheter la sélection ({selectedCount} titres) — {bundlePrice} CHF
                  </button>
                </div>
              )}
            </div>
          );
        })()}

        {/* v57: MODALE LIGHTBOX AUDIO — miniature + description complète */}
        {audioLightbox && (
          <div
            onClick={() => setAudioLightbox(null)}
            style={{
              position: 'fixed', inset: 0, zIndex: 9999,
              background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(8px)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: '20px', cursor: 'pointer'
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                maxWidth: '400px', width: '100%', borderRadius: '20px',
                background: 'rgba(20,10,30,0.95)', border: '1px solid rgba(217,28,210,0.3)',
                padding: '24px', cursor: 'default', position: 'relative',
                boxShadow: '0 0 40px rgba(217,28,210,0.2)'
              }}
            >
              {/* Bouton fermer */}
              <button
                onClick={() => setAudioLightbox(null)}
                style={{
                  position: 'absolute', top: '12px', right: '12px',
                  width: '32px', height: '32px', borderRadius: '50%',
                  background: 'rgba(255,255,255,0.1)', border: 'none',
                  color: '#fff', fontSize: '16px', cursor: 'pointer',
                  display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}
              >✕</button>
              {/* Image grande */}
              {audioLightbox.cover_url ? (
                <img
                  src={audioLightbox.cover_url}
                  alt={audioLightbox.title}
                  style={{
                    width: '100%', borderRadius: '14px', marginBottom: '16px',
                    boxShadow: '0 0 30px rgba(217,28,210,0.3)'
                  }}
                />
              ) : (
                <div style={{
                  width: '100%', height: '200px', borderRadius: '14px', marginBottom: '16px',
                  background: 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.2))',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '60px'
                }}>🎵</div>
              )}
              <h3 style={{ color: '#fff', fontSize: '18px', fontWeight: 700, margin: '0 0 8px 0' }}>
                {audioLightbox.title}
              </h3>
              {audioLightbox.price > 0 && (
                <span style={{
                  display: 'inline-block', padding: '4px 12px', borderRadius: '8px',
                  background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                  color: '#fff', fontWeight: 700, fontSize: '13px', marginBottom: '12px'
                }}>
                  {audioLightbox.price} CHF
                </span>
              )}
              {audioLightbox.description && (
                <p style={{
                  color: 'rgba(255,255,255,0.7)', fontSize: '13px', lineHeight: '1.5',
                  margin: '12px 0 0 0', whiteSpace: 'pre-wrap'
                }}>
                  {audioLightbox.description}
                </p>
              )}
              <p style={{ color: 'rgba(255,255,255,0.3)', fontSize: '10px', marginTop: '12px' }}>
                Aperçu limité à 30 secondes
              </p>
            </div>
          </div>
        )}

        {/* Bouton Voir les avis Google - affiché si configuré par le coach */}
        {selectedOffer && concept.googleReviewsUrl && (
          <div className="mb-6 flex justify-center">
            <a 
              href={concept.googleReviewsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full transition-all duration-300 hover:scale-105"
              style={{
                background: 'transparent',
                border: '2px solid rgba(217, 28, 210, 0.7)',
                boxShadow: '0 0 15px rgba(217, 28, 210, 0.4), inset 0 0 10px rgba(139, 92, 246, 0.1)',
                color: '#fff'
              }}
              data-testid="google-reviews-btn"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
              </svg>
              <span className="font-medium">Voir les avis</span>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                <polyline points="15 3 21 3 21 9"/>
                <line x1="10" y1="14" x2="21" y2="3"/>
              </svg>
            </a>
          </div>
        )}

        {selectedOffer && (
          <form onSubmit={handleSubmit}>
            <div id="user-info-section" className="form-section rounded-xl p-6 mb-6" data-testid="user-info-section">
              <h2 className="font-semibold mb-4 text-white" style={{ fontSize: '18px' }}>{t('yourInfo')}</h2>
              <div className="space-y-4">
                {/* Private input fields with auto-fill support */}
                <input type="text" required placeholder={t('fullName')} value={userName} onChange={e => setUserName(e.target.value)} className="w-full p-3 rounded-lg neon-input" data-testid="user-name-input" autoComplete="name" />
                <input type="email" required placeholder={t('emailRequired')} value={userEmail} onChange={e => handleEmailChange(e.target.value)} className="w-full p-3 rounded-lg neon-input" data-testid="user-email-input" autoComplete="email" />
                <input type="tel" required placeholder={t('whatsappRequired')} value={userWhatsapp} onChange={e => setUserWhatsapp(e.target.value)} className="w-full p-3 rounded-lg neon-input" data-testid="user-whatsapp-input" autoComplete="tel" />
                
                {/* Champ Adresse - Affiché uniquement pour les produits physiques */}
                {(selectedOffer?.isProduct || selectedOffer?.isPhysicalProduct) && (
                  <div className="border border-purple-500/30 rounded-lg p-3 bg-purple-900/20">
                    <p className="text-xs text-purple-400 mb-2">📦 Produit physique - Adresse de livraison requise</p>
                    <input 
                      type="text" 
                      required 
                      placeholder="Adresse complète (rue, numéro, code postal, ville)" 
                      value={shippingAddress} 
                      onChange={e => setShippingAddress(e.target.value)} 
                      className="w-full p-3 rounded-lg neon-input" 
                      data-testid="shipping-address-input" 
                      autoComplete="street-address" 
                    />
                  </div>
                )}
                
                {/* Sélecteur de variantes interactif - Affiché si le produit a des variantes */}
                {selectedOffer?.variants && Object.keys(selectedOffer.variants).length > 0 && (
                  <div className="border border-pink-500/30 rounded-lg p-4 bg-pink-900/10" data-testid="variants-selector">
                    <p className="text-xs text-pink-400 mb-3 font-medium">🎨 Sélectionnez vos options</p>
                    
                    {/* Tailles */}
                    {selectedOffer.variants.sizes && selectedOffer.variants.sizes.length > 0 && (
                      <div className="mb-4">
                        <p className="variant-label">Taille</p>
                        <div className="flex flex-wrap gap-2">
                          {selectedOffer.variants.sizes.map((size) => (
                            <button
                              key={size}
                              type="button"
                              onClick={() => setSelectedVariants(prev => ({ ...prev, size }))}
                              className={`variant-chip ${selectedVariants.size === size ? 'selected' : ''}`}
                              data-testid={`variant-size-${size}`}
                            >
                              {size}
                            </button>
                          ))}
                        </div>
                        {!selectedVariants.size && (
                          <p className="text-xs text-red-400 mt-1">* Veuillez sélectionner une taille</p>
                        )}
                      </div>
                    )}
                    
                    {/* Couleurs */}
                    {selectedOffer.variants.colors && selectedOffer.variants.colors.length > 0 && (
                      <div className="mb-4">
                        <p className="variant-label">Couleur</p>
                        <div className="flex flex-wrap gap-2">
                          {selectedOffer.variants.colors.map((color) => (
                            <button
                              key={color}
                              type="button"
                              onClick={() => setSelectedVariants(prev => ({ ...prev, color }))}
                              className={`variant-chip ${selectedVariants.color === color ? 'selected' : ''}`}
                              data-testid={`variant-color-${color}`}
                            >
                              {color}
                            </button>
                          ))}
                        </div>
                        {!selectedVariants.color && (
                          <p className="text-xs text-red-400 mt-1">* Veuillez sélectionner une couleur</p>
                        )}
                      </div>
                    )}
                    
                    {/* Autres variantes (poids, etc.) */}
                    {selectedOffer.variants.weights && selectedOffer.variants.weights.length > 0 && (
                      <div className="mb-2">
                        <p className="variant-label">Poids</p>
                        <div className="flex flex-wrap gap-2">
                          {selectedOffer.variants.weights.map((weight) => (
                            <button
                              key={weight}
                              type="button"
                              onClick={() => setSelectedVariants(prev => ({ ...prev, weight }))}
                              className={`variant-chip ${selectedVariants.weight === weight ? 'selected' : ''}`}
                              data-testid={`variant-weight-${weight}`}
                            >
                              {weight}
                            </button>
                          ))}
                        </div>
                        {!selectedVariants.weight && (
                          <p className="text-xs text-red-400 mt-1">* Veuillez sélectionner un poids</p>
                        )}
                      </div>
                    )}
                  </div>
                )}
                
                {/* Promo code input - Accept any case (minuscules/majuscules) */}
                <div>
                  <input type="text" placeholder={t('promoCode')} value={discountCode} onChange={e => setDiscountCode(e.target.value)}
                    className={`w-full p-3 rounded-lg ${appliedDiscount ? 'valid-code' : 'neon-input'}`} data-testid="discount-code-input" autoComplete="off" />
                  
                  {/* FEEDBACK VISUEL: Message clair sous le champ code promo */}
                  {promoMessage.text && (
                    <p className={`mt-2 text-sm font-medium ${promoMessage.type === 'success' ? 'text-green-400' : promoMessage.type === 'error' ? 'text-red-400' : 'text-yellow-400'}`} data-testid="promo-message">
                      {promoMessage.text}
                    </p>
                  )}
                </div>
                
                {/* Other validation messages */}
                {validationMessage && (
                  <p className="text-red-400 text-sm font-medium" data-testid="validation-message">{validationMessage}</p>
                )}
                
                {/* Price summary with quantity selector and discount */}
                <div className="p-4 rounded-lg card-gradient">
                  {selectedOffer && (
                    <>
                      <div className="flex justify-between items-center text-white text-sm mb-2">
                        <span>{selectedOffer.name}</span>
                        <span>CHF {selectedOffer.price.toFixed(2)}</span>
                      </div>
                      
                      {/* Pour les services/cours: Afficher les dates sélectionnées */}
                      {!selectedOffer?.isProduct && !selectedOffer?.isPhysicalProduct && selectedDates.length > 0 && (
                        <div className="mb-3 p-3 rounded-lg" style={{ 
                          background: 'rgba(217, 28, 210, 0.1)', 
                          border: '1px solid rgba(217, 28, 210, 0.3)' 
                        }}>
                          <p className="text-xs text-pink-400 mb-2 font-medium">📅 Dates sélectionnées ({selectedDates.length})</p>
                          <div className="flex flex-wrap gap-2">
                            {selectedDates.map((dateISO, idx) => (
                              <span 
                                key={idx}
                                className="px-2 py-1 rounded-full text-xs text-white"
                                style={{ 
                                  background: 'rgba(217, 28, 210, 0.3)',
                                  border: '1px solid #D91CD2'
                                }}
                              >
                                {new Date(dateISO).toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })}
                              </span>
                            ))}
                          </div>
                          {selectedDates.length > 1 && (
                            <p className="text-xs text-white opacity-70 mt-2">
                              💡 Cliquez sur les dates ci-dessus pour en ajouter ou retirer
                            </p>
                          )}
                        </div>
                      )}
                      
                      {/* Quantity selector - Visible uniquement pour les produits physiques */}
                      {(selectedOffer?.isProduct || selectedOffer?.isPhysicalProduct) && (
                        <div className="flex justify-between items-center text-white text-sm mb-2">
                          <span>{t('quantity') || 'Quantité'}:</span>
                          <div className="flex items-center gap-2">
                            <button 
                              type="button"
                              onClick={() => setQuantity(Math.max(1, quantity - 1))}
                              className="w-8 h-8 rounded-full bg-purple-600 hover:bg-purple-700 text-white font-bold"
                              data-testid="quantity-minus"
                            >-</button>
                            <span className="w-8 text-center font-bold" data-testid="quantity-value">{quantity}</span>
                            <button 
                              type="button"
                              onClick={() => setQuantity(quantity + 1)}
                              className="w-8 h-8 rounded-full bg-purple-600 hover:bg-purple-700 text-white font-bold"
                              data-testid="quantity-plus"
                            >+</button>
                          </div>
                        </div>
                      )}
                      
                      {/* Sous-total pour produits physiques */}
                      {(selectedOffer?.isProduct || selectedOffer?.isPhysicalProduct) && quantity > 1 && (
                        <div className="flex justify-between text-white text-xs opacity-60 mb-1">
                          <span>Sous-total ({quantity} x CHF {selectedOffer.price.toFixed(2)})</span>
                          <span>CHF {(selectedOffer.price * quantity).toFixed(2)}</span>
                        </div>
                      )}
                      
                      {/* Sous-total pour services/cours avec multi-dates */}
                      {!selectedOffer?.isProduct && !selectedOffer?.isPhysicalProduct && selectedDates.length > 1 && (
                        <div className="flex justify-between text-white text-xs opacity-60 mb-1">
                          <span>Sous-total ({selectedDates.length} dates x CHF {selectedOffer.price.toFixed(2)})</span>
                          <span>CHF {(selectedOffer.price * selectedDates.length).toFixed(2)}</span>
                        </div>
                      )}
                      
                      {appliedDiscount && (
                        <div className="flex justify-between text-green-400 text-sm mb-1">
                          <span>Réduction ({appliedDiscount.code})</span>
                          <span>
                            {appliedDiscount.type === '100%' ? '-100%' : 
                             appliedDiscount.type === '%' ? `-${appliedDiscount.value}%` : 
                             `-${appliedDiscount.value} CHF`}
                          </span>
                        </div>
                      )}
                      <hr className="border-gray-600 my-2" />
                    </>
                  )}
                  <p className="font-bold text-white text-lg flex justify-between" data-testid="total-price">
                    <span>{t('total')}:</span>
                    <span style={{ color: parseFloat(totalPrice) === 0 ? '#4ade80' : '#d91cd2' }}>
                      CHF {totalPrice}
                      {parseFloat(totalPrice) === 0 && <span className="ml-2 text-sm">(GRATUIT)</span>}
                    </span>
                  </p>
                </div>
                
                {/* CGV checkbox with clickable link */}
                <label className="flex items-start gap-2 cursor-pointer text-xs text-white opacity-70">
                  <input type="checkbox" required checked={hasAcceptedTerms} onChange={e => setHasAcceptedTerms(e.target.checked)} data-testid="terms-checkbox" />
                  <span>
                    {t('acceptTerms')}{' '}
                    <button 
                      type="button"
                      onClick={(e) => { e.preventDefault(); setShowTermsModal(true); }}
                      className="underline hover:text-purple-400"
                      style={{ color: '#d91cd2' }}
                      data-testid="terms-link"
                    >
                      {t('termsLink') || 'conditions générales'}
                    </button>
                    {' '}et confirme ma réservation.
                  </span>
                </label>
              </div>
            </div>
            
            {/* DYNAMISME DU BOUTON: Change selon le montant total */}
            <button type="submit" disabled={!hasAcceptedTerms || loading} 
              className={`w-full py-4 rounded-xl font-bold uppercase tracking-wide ${parseFloat(totalPrice) === 0 ? 'btn-free' : 'btn-primary'}`} 
              data-testid="submit-reservation-btn">
              {loading ? t('loading') : parseFloat(totalPrice) === 0 ? '🎁 Réserver gratuitement' : t('payAndReserve')}
            </button>
          </form>
        )}

        {/* CGV Modal */}
        {showTermsModal && (
          <div className="modal-overlay" onClick={() => setShowTermsModal(false)}>
            <div className="modal-content glass rounded-xl p-6 max-w-lg w-full neon-border" onClick={e => e.stopPropagation()}>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-xl font-bold text-white">{t('termsTitle') || 'Conditions Générales'}</h3>
                <button onClick={() => setShowTermsModal(false)} className="text-2xl text-white hover:text-purple-400">×</button>
              </div>
              <div className="max-h-[60vh] overflow-y-auto text-white text-sm opacity-80 whitespace-pre-wrap">
                {concept.termsText || 'Les conditions générales ne sont pas encore définies. Veuillez contacter l\'administrateur.'}
              </div>
              <button 
                onClick={() => setShowTermsModal(false)} 
                className="mt-4 w-full py-3 rounded-lg btn-primary"
              >
                Fermer
              </button>
            </div>
          </div>
        )}

        {/* v16: Section Témoignages / Avis clients */}
        <div className="mb-8 fade-in-section" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '24px' }}>
          <h2 className="font-semibold text-white text-center mb-6" style={{ fontSize: '18px' }}>
            Ce que disent nos clients
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Témoignage 1 */}
            <div className="rounded-xl p-5"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="flex items-center gap-1 mb-2">
                {[1,2,3,4,5].map(i => (
                  <svg key={i} width="14" height="14" viewBox="0 0 24 24" fill="#D91CD2" stroke="none">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                  </svg>
                ))}
              </div>
              <p className="text-white/70 text-sm leading-relaxed italic mb-3">
                "L'ambiance est incroyable ! Le concept casques audio rend la session unique. Je reviens chaque semaine."
              </p>
              <p className="text-white/40 text-xs">— Sarah M.</p>
            </div>
            {/* Témoignage 2 */}
            <div className="rounded-xl p-5"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="flex items-center gap-1 mb-2">
                {[1,2,3,4,5].map(i => (
                  <svg key={i} width="14" height="14" viewBox="0 0 24 24" fill="#D91CD2" stroke="none">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                  </svg>
                ))}
              </div>
              <p className="text-white/70 text-sm leading-relaxed italic mb-3">
                "Cours de danse top ! Le coach est super motivant. Parfait pour se défouler après le travail."
              </p>
              <p className="text-white/40 text-xs">— Kevin L.</p>
            </div>
          </div>
          {/* Lien avis Google si configuré */}
          {concept.googleReviewsUrl && (
            <div className="text-center mt-4">
              <a href={concept.googleReviewsUrl} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 text-sm transition-colors hover:text-pink-400"
                style={{ color: 'rgba(217, 28, 210, 0.8)' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
                Voir tous les avis Google
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
              </a>
            </div>
          )}
        </div>

        {/* v15: Footer amélioré avec réseaux sociaux + infos utiles */}
        <footer className="mt-12 mb-8 text-center" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '24px' }}>
          {/* Branding */}
          <p className="text-white font-semibold text-sm mb-1">Afroboost</p>
          <p className="text-white/40 text-xs mb-4">La plateforme des coachs</p>
          
          {/* Logos de paiement - Sans rectangle, juste les logos */}
          {(concept.paymentTwint || concept.paymentPaypal || concept.paymentCreditCard) && (
            <div className="flex justify-center items-center gap-6 mb-6" data-testid="payment-logos-footer">
              {concept.paymentTwint && (
                <div 
                  style={{ 
                    height: '24px', 
                    display: 'flex', 
                    alignItems: 'center',
                    opacity: 0.8 
                  }}
                  title="Twint"
                >
                  <svg width="60" height="24" viewBox="0 0 120 40" fill="white">
                    <text x="0" y="28" fontFamily="Arial, sans-serif" fontSize="24" fontWeight="bold" fill="white">TWINT</text>
                  </svg>
                </div>
              )}
              {concept.paymentPaypal && (
                <img 
                  src="https://upload.wikimedia.org/wikipedia/commons/b/b5/PayPal.svg" 
                  alt="PayPal" 
                  style={{ height: '22px', filter: 'brightness(0) invert(1)', opacity: 0.7 }}
                  title="PayPal"
                  onError={(e) => { e.target.style.display = 'none'; }}
                />
              )}
              {concept.paymentCreditCard && (
                <div className="flex items-center gap-2">
                  <img 
                    src="https://upload.wikimedia.org/wikipedia/commons/5/5e/Visa_Inc._logo.svg" 
                    alt="Visa" 
                    style={{ height: '18px', filter: 'brightness(0) invert(1)', opacity: 0.7 }}
                    title="Visa"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                  <img 
                    src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Mastercard-logo.svg" 
                    alt="Mastercard" 
                    style={{ height: '20px', filter: 'brightness(0) invert(1)', opacity: 0.7 }}
                    title="Mastercard"
                    onError={(e) => { e.target.style.display = 'none'; }}
                  />
                </div>
              )}
            </div>
          )}
          
          {/* Navigation textuelle horizontale - Police fine, sans icônes */}
          <div 
            className="flex justify-center items-center flex-wrap gap-x-2 gap-y-1"
            style={{ 
              fontFamily: "'Inter', -apple-system, sans-serif",
              fontWeight: 300,
              fontSize: '12px',
              letterSpacing: '0.5px'
            }}
          >
            {concept.externalLink1Url && concept.externalLink1Title && (
              <>
                <a 
                  href={concept.externalLink1Url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-white hover:text-pink-400 transition-colors"
                  style={{ opacity: 0.6 }}
                  data-testid="external-link-1"
                >
                  {concept.externalLink1Title}
                </a>
                <span className="text-white" style={{ opacity: 0.3 }}>|</span>
              </>
            )}
            {concept.externalLink2Url && concept.externalLink2Title && (
              <>
                <a 
                  href={concept.externalLink2Url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-white hover:text-pink-400 transition-colors"
                  style={{ opacity: 0.6 }}
                  data-testid="external-link-2"
                >
                  {concept.externalLink2Title}
                </a>
                <span className="text-white" style={{ opacity: 0.3 }}>|</span>
              </>
            )}
            {(installPrompt || isIOS) && !window.matchMedia('(display-mode: standalone)').matches && (
              <>
                <button 
                  onClick={handleInstallClick}
                  className="text-white hover:text-pink-400 transition-colors"
                  style={{ opacity: 0.6, background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit', fontWeight: 'inherit', fontSize: 'inherit', letterSpacing: 'inherit' }}
                  data-testid="footer-install-link"
                >
                  Installer Afroboost
                </button>
                <span className="text-white" style={{ opacity: 0.3 }}>|</span>
              </>
            )}
            <span 
              onClick={handleCopyrightClick} 
              className="copyright-secret text-white cursor-pointer" 
              style={{ opacity: 0.4 }}
              data-testid="copyright-secret"
            >
              {t('copyright')}
            </span>
          </div>
        </footer>
        
        {/* v9.5.6: ScrollIndicator supprimé - le flux Reels gère le scroll */}
        
        {/* Bouton flottant "Voir mon dernier ticket" */}
        {hasSavedTicket && !showSuccess && !coachMode && (
          <button
            onClick={showSavedTicket}
            className="fixed z-50 flex items-center gap-2 px-4 py-3 rounded-full shadow-lg transition-all duration-300 hover:scale-105"
            style={{
              bottom: '100px',
              right: '20px',
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
              boxShadow: '0 4px 20px rgba(16, 185, 129, 0.4)',
              border: '2px solid rgba(255, 255, 255, 0.2)'
            }}
            data-testid="view-saved-ticket-btn"
          >
            <span className="text-lg">🎫</span>
            <span className="text-white font-semibold text-sm">Mon ticket</span>
          </button>
        )}
        
        {/* Widget Chat IA flottant */}
        <ChatWidget />
        
        {/* v8.9.4: Modal recherche coach (déclenchée par l'icône dans NavigationBar) */}
        <CoachSearchModal
          isOpen={showCoachSearch}
          onClose={() => setShowCoachSearch(false)}
          onSelectCoach={(coach) => {
            console.log('[APP] Coach sélectionné:', coach);
            setShowCoachSearch(false);
            // v8.9.6: Rediriger vers la vitrine du coach
            if (coach?.id) {
              setShowCoachVitrine(coach.id);
              window.history.pushState({}, '', `/coach/${coach.id}`);
            }
          }}
        />
      </div>
    </div>
  );
}

export default App;

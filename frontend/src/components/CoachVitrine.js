/**
 * CoachVitrine - Vitrine publique d'un coach v29.3 STABLE CACHE-BUSTER
 * Route: /coach/[username]
 * Layout IDENTIQUE à la page d'accueil :
 *   - Hero 85vh avec YouTube Lite Facade (thumbnail + play)
 *   - Nom coach + actions overlays (style Instagram Reels)
 *   - Sous le hero : Cours/Sessions → Offres → Formulaire INLINE (pas de pop-up)
 *   - QR + Partage en haut à droite sur toutes les pages
 */
import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { QRCodeSVG } from "qrcode.react";
import { copyToClipboard } from "../utils/clipboard";
import VitrineCheckout from "./VitrineCheckout"; // v15.0
import AudioPlayer from "./AudioPlayer"; // v17.4

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// === UTILITAIRES VIDEO ===
const getYoutubeId = (url) => {
  if (!url) return null;
  const match = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  return match ? match[1] : null;
};

// Offres par défaut Afroboost si le coach n'a pas créé les siennes
const DEFAULT_STARTER_OFFERS = [
  {
    id: 'default-1',
    name: 'Séance découverte',
    description: 'Première séance offerte pour découvrir le concept',
    price: 0,
    imageUrl: 'https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=400&h=300&fit=crop'
  },
  {
    id: 'default-2',
    name: 'Pack 5 séances',
    description: 'Idéal pour commencer votre transformation',
    price: 99,
    imageUrl: 'https://images.unsplash.com/photo-1518611012118-696072aa579a?w=400&h=300&fit=crop'
  },
  {
    id: 'default-3',
    name: 'Abonnement mensuel',
    description: 'Accès illimité à toutes les séances du mois',
    price: 149,
    imageUrl: 'https://images.unsplash.com/photo-1549060279-7e168fcee0c2?w=400&h=300&fit=crop'
  }
];

// Icône de localisation
const LocationIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
    <circle cx="12" cy="10" r="3"/>
  </svg>
);

const CoachVitrine = ({ username, onClose, onBack }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [coach, setCoach] = useState(null);
  const [offers, setOffers] = useState([]);
  const [courses, setCourses] = useState([]);
  const [showQR, setShowQR] = useState(false);
  const [ytPlaying, setYtPlaying] = useState(false);
  const sliderRef = useRef(null);
  const formRef = useRef(null);

  // Recherche offres
  const [offerSearch, setOfferSearch] = useState('');

  // Config paiement
  const [paymentConfig, setPaymentConfig] = useState({
    stripe: '', paypal: '', twint: '', coachWhatsapp: ''
  });

  // Concept du coach (vidéo header)
  const [coachConcept, setCoachConcept] = useState(null);

  // v29.2: Timestamp STABLE pour cache-busting — fixé au montage, ne change plus entre les rotations
  const [cacheBusterTs] = useState(() => Date.now());

  // v17.0: Branding dynamique
  const [brandAccent, setBrandAccent] = useState('#D91CD2');

  // v44: Pistes audio autonomes (indépendantes des cours)
  const [audioTracks, setAudioTracks] = useState([]);

  // v17.2: FAQ
  const [faqs, setFaqs] = useState([]);
  const [openFaqId, setOpenFaqId] = useState(null);
  const [faqSectionOpen, setFaqSectionOpen] = useState(false);

  // v18: Multi-vidéos héro
  const [activeVideoIndex, setActiveVideoIndex] = useState(0);

  // v34: Preview 30s pour vidéos premium
  const [showVideoPreviewOverlay, setShowVideoPreviewOverlay] = useState(false);
  const ytPreviewTimerRef = useRef(null);
  const PREVIEW_LIMIT = 30; // secondes

  // v72: Social Proof — Icône interactive + panneau commentaires
  const [socialComments, setSocialComments] = useState([]);
  const [showCommentsPanel, setShowCommentsPanel] = useState(false);
  const [zoomedPhoto, setZoomedPhoto] = useState(null); // v74: Zoom photo profil

  // v17: INLINE booking multi-séances (tableau de { course, date })
  const [selectedBookings, setSelectedBookings] = useState([]); // [{ course, date }, ...]
  const selectedBooking = selectedBookings.length > 0 ? selectedBookings[0] : null; // compat
  const [selectedOffer, setSelectedOffer] = useState(null);
  const [bookingForm, setBookingForm] = useState({ name: '', email: '', whatsapp: '', promoCode: '' });
  const [bookingLoading, setBookingLoading] = useState(false);
  const [bookingSuccess, setBookingSuccess] = useState(false);

  // Promo
  const [promoMessage, setPromoMessage] = useState({ type: '', text: '' });
  const [appliedDiscount, setAppliedDiscount] = useState(null);

  // Retour au flux
  const [cameFromFlux, setCameFromFlux] = useState(false);

  useEffect(() => {
    const fluxIndex = sessionStorage.getItem('afroboost_flux_index');
    if (fluxIndex !== null) setCameFromFlux(true);
  }, []);

  const handleReturnToFlux = () => {
    if (onBack) onBack();
    else window.history.pushState({}, '', '/');
  };

  // v17: Clic sur date → toggle sélection multi-séances (max 3)
  const handleBookClick = (course, date) => {
    const dateStr = date.toISOString();
    const exists = selectedBookings.findIndex(b => b.course.id === course.id && b.date.toISOString() === dateStr);
    if (exists >= 0) {
      // Déselection
      setSelectedBookings(prev => prev.filter((_, i) => i !== exists));
    } else if (selectedBookings.length >= 3) {
      // Max 3 séances
      alert('Maximum 3 séances à la fois');
    } else {
      // Ajout
      setSelectedBookings(prev => [...prev, { course, date }]);
    }
    setBookingSuccess(false);
    setPromoMessage({ type: '', text: '' });
    setAppliedDiscount(null);
    // Scroll vers le formulaire après rendu
    setTimeout(() => {
      const el = document.getElementById('vitrine-booking-form');
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  // Valider code promo
  const validatePromoCode = async (code) => {
    if (!code || code.length < 2) {
      setPromoMessage({ type: '', text: '' });
      setAppliedDiscount(null);
      return;
    }
    try {
      const res = await axios.post(`${API}/discount-codes/validate`, {
        code: code.trim(),
        coach_id: coach?.email || username
      });
      if (res.data && res.data.valid) {
        const discountCode = res.data.code;
        let discountText = '';
        if (discountCode.type === '100%') discountText = `Code validé : GRATUIT`;
        else if (discountCode.type === '%') discountText = `Code validé : -${discountCode.value}%`;
        else discountText = `Code validé : -${discountCode.value} CHF`;
        setPromoMessage({ type: 'success', text: `✅ ${discountText}` });
        setAppliedDiscount(discountCode);
      } else {
        setPromoMessage({ type: 'error', text: '❌ Code invalide' });
        setAppliedDiscount(null);
      }
    } catch (err) {
      setPromoMessage({ type: 'error', text: '❌ Code invalide ou expiré' });
      setAppliedDiscount(null);
    }
  };

  // v17: Calculer prix final × nombre de séances
  const calculateFinalPrice = () => {
    if (!selectedOffer) return 0;
    const qty = Math.max(1, selectedBookings.length);
    let total = (selectedOffer.price || 0) * qty;
    if (appliedDiscount) {
      if (appliedDiscount.type === '100%') return 0;
      if (appliedDiscount.type === '%') return total * (1 - parseFloat(appliedDiscount.value) / 100);
      if (appliedDiscount.type === 'CHF') return Math.max(0, total - parseFloat(appliedDiscount.value));
    }
    return total;
  };

  // Soumettre réservation
  const handleBookingSubmit = async (e) => {
    e.preventDefault();
    if (selectedBookings.length === 0 || bookingLoading) return;
    setBookingLoading(true);
    try {
      // Envoyer une réservation par séance sélectionnée
      const finalPrice = calculateFinalPrice();
      const qty = selectedBookings.length;
      for (const booking of selectedBookings) {
        await axios.post(`${API}/reservations`, {
          userName: bookingForm.name,
          userEmail: bookingForm.email,
          userWhatsapp: bookingForm.whatsapp,
          courseName: booking.course.name || booking.course.title,
          courseTime: booking.course.time,
          datetime: booking.date.toISOString(),
          offerName: selectedOffer?.name || 'Séance',
          totalPrice: finalPrice / qty,
          quantity: 1,
          coach_id: coach?.email || username,
          source: 'vitrine_partenaire',
          promoCode: appliedDiscount?.code || null
        });
      }
      if (appliedDiscount) {
        try { await axios.post(`${API}/discount-codes/${appliedDiscount.id}/use`); } catch (e) {}
      }
      setBookingSuccess(true);
      setBookingForm({ name: '', email: '', whatsapp: '', promoCode: '' });
      setSelectedBookings([]);
    } catch (err) {
      console.error('[BOOKING] Erreur:', err);
      const detail = err.response?.data?.detail;
      const message = typeof detail === 'string' ? detail :
        Array.isArray(detail) ? detail.map(d => d.msg || JSON.stringify(d)).join(', ') :
        'Erreur lors de la réservation';
      alert(message);
    } finally {
      setBookingLoading(false);
    }
  };

  // URL de la vitrine pour le QR code
  const vitrineUrl = typeof window !== 'undefined'
    ? `${window.location.origin}/coach/${username}`
    : '';

  useEffect(() => {
    const fetchVitrine = async () => {
      if (!username) { setError('Aucun coach spécifié'); setLoading(false); return; }
      try {
        const res = await axios.get(`${API}/coach/vitrine/${encodeURIComponent(username)}`);
        setCoach(res.data.coach);
        const coachOffers = res.data.offers || [];
        setOffers(coachOffers.length === 0 ? DEFAULT_STARTER_OFFERS : coachOffers);
        setCourses(res.data.courses || []);

        // v29: Le concept (heroVideos, couleurs, etc.) est maintenant inclus directement dans la réponse vitrine
        if (res.data.concept) {
          setCoachConcept(res.data.concept);
          console.warn('[VITRINE-V29] ✅ Concept chargé depuis vitrine API — heroVideos:', res.data.concept.heroVideos?.length || 0,
            'URLs:', (res.data.concept.heroVideos || []).map(v => v?.url).filter(Boolean));
        } else {
          console.warn('[VITRINE-V29] ⚠️ Pas de concept dans la réponse vitrine, tentative fallback...');
          // Fallback: charger le concept séparément (compatibilité)
          const coachEmail = res.data.coach.email || username;
          try {
            const conceptRes = await axios.get(`${API}/concept`, {
              headers: { 'X-User-Email': coachEmail }
            });
            if (conceptRes.data) {
              setCoachConcept(conceptRes.data);
              console.warn('[VITRINE-V29] ✅ Concept fallback chargé:', conceptRes.data.heroVideos?.length || 0);
            }
          } catch (e) {
            console.warn('[VITRINE-V29] ❌ Fallback concept échoué:', e.message);
          }
        }

        // Charger paiement
        try {
          const paymentRes = await axios.get(`${API}/payment-links/${encodeURIComponent(res.data.coach.email || username)}`);
          setPaymentConfig(paymentRes.data);
        } catch (e) {}

        // v17.0: Charger branding
        try {
          const brandRes = await axios.get(`${API}/coach/branding/${encodeURIComponent(res.data.coach.email || username)}`);
          if (brandRes.data?.accent_color) setBrandAccent(brandRes.data.accent_color);
        } catch (e) {}

        // v17.2: Charger FAQ
        try {
          const faqRes = await axios.get(`${API}/coach/faqs/${encodeURIComponent(res.data.coach.email || username)}`);
          setFaqs(Array.isArray(faqRes.data) ? faqRes.data : []);
        } catch (e) {}

        // v52: Charger pistes audio — timeout 15s + retry + fallback cache
        const audioEmail = encodeURIComponent(res.data.coach.email || username);
        const audioUrl = `${API}/public/audio-tracks/${audioEmail}`;
        let audioLoaded = false;
        for (let attempt = 1; attempt <= 2 && !audioLoaded; attempt++) {
          try {
            const audioController = new AbortController();
            const audioTimeout = setTimeout(() => audioController.abort(), 15000); // 15s (Vercel cold start)
            console.log('[VITRINE-V52] Audio fetch attempt', attempt, audioUrl);
            const audioRes = await axios.get(audioUrl, { signal: audioController.signal });
            clearTimeout(audioTimeout);
            const tracks = audioRes.data.tracks || [];
            console.log('[VITRINE-V52] Audio loaded:', tracks.length, 'tracks');
            setAudioTracks(tracks);
            audioLoaded = true;
            if (tracks.length > 0) {
              try { localStorage.setItem('afroboost_audio_cache_' + username, JSON.stringify(tracks)); } catch(ce) {}
            }
          } catch (e) {
            console.warn('[VITRINE-V52] Audio attempt', attempt, 'failed:', e.message);
            if (attempt < 2) {
              await new Promise(r => setTimeout(r, 1000)); // Wait 1s before retry
            }
          }
        }
        if (!audioLoaded) {
          // Fallback — charger depuis le cache local
          try {
            const cached = localStorage.getItem('afroboost_audio_cache_' + username);
            if (cached) {
              const cachedTracks = JSON.parse(cached);
              setAudioTracks(cachedTracks);
              console.log('[VITRINE-V52] Loaded', cachedTracks.length, 'tracks from cache fallback');
            }
          } catch (ce) {}
        }
        // v71: Charger commentaires Social Proof
        try {
          const commentsRes = await axios.get(`${API}/comments?coach_id=${encodeURIComponent(res.data.coach.email || username)}`);
          if (commentsRes.data?.comments) setSocialComments(commentsRes.data.comments);
        } catch (e) {}

      } catch (err) {
        console.error('[VITRINE] Erreur:', err);
        setError(err.response?.data?.detail || 'Coach non trouvé');
      } finally {
        setLoading(false);
      }
    };
    fetchVitrine();
  }, [username]);

  // v17.1: SEO Dynamique — meta tags + OpenGraph pour chaque vitrine
  useEffect(() => {
    if (!coach) return;
    const coachName = coach.platform_name || coach.name || username;
    const coachEmail = coach.email || username;

    // Fetch SEO data
    fetch(`${API}/coach/seo/${encodeURIComponent(coachEmail)}`)
      .then(r => r.json())
      .then(seo => {
        const title = seo.meta_title || `${coachName} | Afroboost`;
        const desc = seo.meta_description || `Découvrez les cours et services de ${coachName} sur Afroboost`;
        const keywords = seo.seo_keywords || `${coachName}, fitness, coaching, Afroboost`;
        const image = seo.logo_url || `${window.location.origin}/logo192.png`;
        const url = `${window.location.origin}/coach/${username}`;

        // Title
        document.title = title;

        // Helper to set/create meta
        const setMeta = (attr, key, content) => {
          let el = document.querySelector(`meta[${attr}="${key}"]`);
          if (!el) { el = document.createElement('meta'); el.setAttribute(attr, key); document.head.appendChild(el); }
          el.setAttribute('content', content);
        };

        // Standard meta
        setMeta('name', 'description', desc);
        setMeta('name', 'keywords', keywords);
        setMeta('name', 'theme-color', brandAccent);

        // OpenGraph
        setMeta('property', 'og:type', 'website');
        setMeta('property', 'og:title', title);
        setMeta('property', 'og:description', desc);
        setMeta('property', 'og:image', image);
        setMeta('property', 'og:url', url);
        setMeta('property', 'og:site_name', 'Afroboost');

        // Twitter Card
        setMeta('name', 'twitter:card', 'summary_large_image');
        setMeta('name', 'twitter:title', title);
        setMeta('name', 'twitter:description', desc);
        setMeta('name', 'twitter:image', image);
      })
      .catch(() => {
        // Fallback: minimal title
        document.title = `${coachName} | Afroboost`;
      });

    // Cleanup on unmount
    return () => {
      document.title = 'Afroboost';
      ['description', 'keywords'].forEach(name => {
        const el = document.querySelector(`meta[name="${name}"]`);
        if (el) el.setAttribute('content', '');
      });
    };
  }, [coach, username, brandAccent]);

  // Partager
  const handleShare = async () => {
    const shareData = {
      title: `${coach?.platform_name || coach?.name} - Coach`,
      text: `Découvrez ${coach?.platform_name || coach?.name} sur Afroboost!`,
      url: vitrineUrl
    };
    if (navigator.share) {
      try { await navigator.share(shareData); } catch (err) {}
    } else {
      const result = await copyToClipboard(vitrineUrl);
      alert(result.success ? 'Lien copié!' : 'Impossible de copier. URL: ' + vitrineUrl);
    }
  };

  // Générer prochaines dates
  const getNextOccurrences = (weekday, count = 4) => {
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
  };

  const formatDateShort = (d) => {
    return d.toLocaleDateString('fr-CH', { weekday: 'short', day: '2-digit', month: '2-digit' });
  };

  // v18.4: Auto-rotation du carousel héro (8s par slide)
  const heroSlidesCount = (coachConcept?.heroVideos || []).filter(v => v && v.url).length;
  useEffect(() => {
    if (heroSlidesCount <= 1) return;
    const timer = setInterval(() => {
      setActiveVideoIndex(prev => (prev + 1) % heroSlidesCount);
    }, 8000);
    return () => clearInterval(timer);
  }, [heroSlidesCount]);

  // v29.4: PRELOAD vidéos en arrière-plan pour chargement instantané au switch
  useEffect(() => {
    if (!coachConcept?.heroVideos) return;
    const base = BACKEND_URL || (typeof window !== 'undefined' ? window.location.origin : '');
    const links = [];
    coachConcept.heroVideos.forEach(v => {
      if (!v || !v.url) return;
      const url = v.url.toLowerCase();
      const isVideo = url.match(/\.(mp4|webm|mov)(\?|$)/i) || v.type === 'upload' || url.includes('/video_');
      if (isVideo && v.url.startsWith('/api/files/')) {
        const fullUrl = `${base}${v.url}?v=${cacheBusterTs}`;
        const link = document.createElement('link');
        link.rel = 'preload';
        link.as = 'video';
        link.href = fullUrl;
        document.head.appendChild(link);
        links.push(link);
        console.log('[V29.4] Preload vidéo:', fullUrl);
      }
    });
    return () => links.forEach(l => { try { document.head.removeChild(l); } catch(e) {} });
  }, [coachConcept, cacheBusterTs]);

  // v34: Preview 30s hooks (MUST be before early returns)
  const previewCurrentVideo = coachConcept?.heroVideos?.[activeVideoIndex] || null;
  const previewPrice = previewCurrentVideo?.price || 0;
  const previewIsPremium = previewPrice > 0;

  const handleHeroTimeUpdate = useCallback((e) => {
    if (!previewIsPremium) return;
    if (e.target.currentTime >= PREVIEW_LIMIT) {
      e.target.pause();
      e.target.currentTime = 0;
      setShowVideoPreviewOverlay(true);
      console.log('[V34-VITRINE] ⏱️ Limite 30s atteinte');
    }
  }, [previewIsPremium]);

  useEffect(() => {
    setShowVideoPreviewOverlay(false);
    if (ytPreviewTimerRef.current) { clearTimeout(ytPreviewTimerRef.current); ytPreviewTimerRef.current = null; }
  }, [activeVideoIndex]);

  // === LOADING — v14: fond noir simple, pas de violet ===
  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: '#000' }}>
        <div className="animate-spin w-10 h-10 border-3 border-white/30 border-t-white rounded-full"></div>
      </div>
    );
  }

  // === ERREUR ===
  if (error || !coach) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center flex-col gap-6 p-6" style={{ background: '#0a0a0f' }}>
        <p className="text-red-400 text-xl font-semibold">{error || 'Coach non trouvé'}</p>
        <button onClick={onBack || onClose}
          className="px-6 py-3 rounded-xl text-white font-medium"
          style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #d91cd2 100%)' }}>
          ← Retour
        </button>
      </div>
    );
  }

  const displayName = coach.platform_name || coach.name || 'Coach';
  const initial = displayName.charAt(0).toUpperCase();

  // v29.4: Résolution URL COMPLÈTE — cache-buster STABLE (fixé au montage)
  const resolveMediaUrl = (url) => {
    if (!url) return '';
    if (url.startsWith('/api/files/')) {
      const base = BACKEND_URL || (typeof window !== 'undefined' ? window.location.origin : '');
      return `${base}${url}?v=${cacheBusterTs}`;
    }
    return url;
  };
  console.log('[VITRINE-V29.4] resolveMediaUrl stable — cacheBusterTs:', cacheBusterTs);

  // v20.1: Détection STRICTE du type réel de média — image TOUJOURS avant vidéo
  const detectMediaType = (video) => {
    if (!video || !video.url) return 'unknown';
    const url = video.url.toLowerCase();
    // YouTube — priorité 1
    if (url.includes('youtube.com') || url.includes('youtu.be')) return 'youtube';
    // Vimeo
    if (url.includes('vimeo.com')) return 'vimeo';
    // v20.1: IMAGE — vérifier extension ET nom de fichier contenant /image_
    // IMPORTANT: cette vérification DOIT être AVANT la vérification vidéo
    if (url.match(/\.(jpg|jpeg|png|webp|gif|svg|bmp)(\?|$)/i) || video.type === 'image' || url.includes('/image_')) return 'image';
    // VIDÉO — par extension OU par nom de fichier contenant /video_
    if (url.match(/\.(mp4|webm|mov|avi|mkv)(\?|$)/i) || video.type === 'upload' || video.type === 'video' || url.includes('/video_')) return 'video';
    // Fallback: si c'est un /api/files/ sans extension reconnue, traiter comme vidéo
    if (url.includes('/api/files/')) return 'video';
    return 'unknown';
  };

  // v20: Multi-vidéos héro — PRIORITÉ ABSOLUE aux médias uploadés
  // v32: Respecter l'ordre MANUEL défini dans le Dashboard (plus de tri automatique)
  const heroVideos = (() => {
    if (coachConcept?.heroVideos && coachConcept.heroVideos.length > 0) {
      // v34: Filtrer les vidéos masquées (is_visible: false)
      const filtered = coachConcept.heroVideos.filter(v => v && v.url && v.is_visible !== false);
      console.log('[V32-HERO] Carousel ordre manuel:', filtered.map((v, i) => `[${i}] ${detectMediaType(v)} → ${resolveMediaUrl(v.url)}`));
      return filtered;
    }
    if (coachConcept?.heroImageUrl) {
      return [{ url: coachConcept.heroImageUrl, type: 'youtube' }];
    }
    return [];
  })();

  // v29.4: Pré-résolution STABLE des URLs — calculée une seule fois par changement de concept
  const heroResolvedUrls = heroVideos.map(v => resolveMediaUrl(v.url));

  const currentHeroVideo = heroVideos[activeVideoIndex] || heroVideos[0] || null;
  const heroVideoUrl = heroResolvedUrls[activeVideoIndex] || heroResolvedUrls[0] || '';
  const heroMediaType = detectMediaType(currentHeroVideo);
  const youtubeId = getYoutubeId(heroVideoUrl);

  // v34: Déterminer si la vidéo courante est premium (uses pre-computed values from before early returns)
  const currentVideoPrice = currentHeroVideo?.price || 0;
  const isVideoPremium = currentVideoPrice > 0;

  // Déduplication des cours par nom
  const uniqueCourses = (() => {
    const seen = new Set();
    return courses.filter(c => {
      if (c.visible === false || c.archived === true) return false;
      const key = (c.name || '').toLowerCase().trim();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  })();

  // Déduplication des offres par nom
  const uniqueOffers = (() => {
    const seen = new Set();
    return offers.filter(o => {
      if (o.visible === false) return false;
      const key = (o.name || '').toLowerCase().trim();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  })();

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto" style={{ background: 'var(--background-color, #0a0a0f)' }}>

      {/* ============================================= */}
      {/* QR Code Modal */}
      {/* ============================================= */}
      {showQR && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.9)' }} onClick={() => setShowQR(false)}>
          <div className="bg-white rounded-2xl p-8 max-w-sm w-full text-center" onClick={e => e.stopPropagation()}>
            <h3 className="text-gray-900 font-bold text-xl mb-4">Partagez cette vitrine</h3>
            <div className="bg-white p-4 rounded-xl inline-block mb-4">
              <QRCodeSVG value={vitrineUrl} size={200} bgColor="#ffffff" fgColor="#1a0a1f" level="M" />
            </div>
            <p className="text-gray-600 text-sm mb-4 break-all">{vitrineUrl}</p>
            <button onClick={() => { navigator.clipboard.writeText(vitrineUrl); alert('Lien copié!'); }}
              className="w-full py-3 rounded-xl text-white font-medium"
              style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #d91cd2 100%)' }}>
              Copier le lien
            </button>
          </div>
        </div>
      )}

      {/* ============================================= */}
      {/* HERO 85vh — MIROIR EXACT du PartnersCarousel */}
      {/* ============================================= */}
      <div className="relative w-full" style={{ height: '85vh', maxHeight: '85vh', background: '#000000' }}>

        {/* v18.3: Loading spinner médias uploadés — auto-hide après 5s */}
        {heroVideoUrl && (heroMediaType === 'video' || heroMediaType === 'image') && heroVideoUrl.includes('/api/files') && (
          <div id="hero-media-loader" className="absolute inset-0 z-10 flex items-center justify-center"
            style={{ background: 'rgba(0,0,0,0.85)' }}
            ref={(el) => {
              if (el) {
                // v18.3: Auto-hide après 5s pour éviter spinner infini
                const timer = setTimeout(() => {
                  if (el) { el.style.opacity = '0'; el.style.pointerEvents = 'none'; }
                  setTimeout(() => { if (el) el.style.display = 'none'; }, 500);
                }, 5000);
                el._loaderTimer = timer;
              }
            }}>
            <div style={{
              width: '48px', height: '48px', borderRadius: '50%',
              border: '3px solid rgba(217,28,210,0.2)', borderTopColor: '#D91CD2',
              animation: 'spin 0.8s linear infinite'
            }} />
            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          </div>
        )}

        {/* v18.2: Fond média plein écran — autoplay total, switch dynamique img/video */}
        <div className="absolute inset-0 overflow-hidden">
          {(() => {
            // Log de validation finale
            if (heroVideoUrl) {
              console.log(`✅ Rendu Média Vitrine OK - Type: ${heroMediaType}, URL: ${heroVideoUrl}`);
            }

            // === YOUTUBE ===
            if (heroMediaType === 'youtube' && youtubeId) {
              // v19: YouTube thumbnail fallback — iframe embed ne fonctionne pas pour les Shorts
              // et certains vidéos ont l'embedding désactivé (Erreur 153)
              // Solution: afficher la thumbnail YouTube en fond avec bouton play cliquable
              const ytThumb = `https://img.youtube.com/vi/${youtubeId}/maxresdefault.jpg`;
              const ytThumbHQ = `https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg`;
              const ytLink = `https://www.youtube.com/watch?v=${youtubeId}`;
              return (
                <div className="absolute inset-0" key={`yt-wrap-${youtubeId}`}>
                  {/* Thumbnail YouTube en fond — fonctionne toujours, même pour Shorts */}
                  <img
                    key={`yt-thumb-${youtubeId}`}
                    src={ytThumb}
                    alt={displayName}
                    className="absolute inset-0 w-full h-full object-cover"
                    style={{ filter: 'brightness(0.65)' }}
                    onLoad={() => {
                      console.log('[VITRINE-MEDIA] ✅ YouTube thumbnail chargée:', youtubeId);
                      const loader = document.getElementById('hero-media-loader');
                      if (loader) loader.style.display = 'none';
                    }}
                    onError={(e) => {
                      // Fallback vers HQ si maxres n'existe pas
                      console.log('[VITRINE-MEDIA] maxresdefault indisponible, fallback hqdefault');
                      e.target.src = ytThumbHQ;
                    }}
                  />
                  {/* Bouton play centré — ouvre YouTube dans un nouvel onglet */}
                  <a
                    href={ytLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="absolute inset-0 flex items-center justify-center"
                    style={{ zIndex: 5 }}
                  >
                    <div style={{
                      width: '72px', height: '72px', borderRadius: '50%',
                      background: 'rgba(217, 28, 210, 0.85)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      boxShadow: '0 0 30px rgba(217, 28, 210, 0.5)',
                      transition: 'transform 0.2s ease'
                    }}>
                      <svg width="28" height="32" viewBox="0 0 28 32" fill="none">
                        <path d="M28 16L0 32V0L28 16Z" fill="white"/>
                      </svg>
                    </div>
                  </a>
                  {/* Gradient overlay */}
                  <div className="absolute inset-0" style={{
                    background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.15) 0%, rgba(217, 28, 210, 0.1) 50%, rgba(30, 0, 50, 0.4) 100%)',
                    zIndex: 1, pointerEvents: 'none'
                  }} />
                </div>
              );
            }

            // === VIMEO ===
            if (heroMediaType === 'vimeo') {
              return (
                <iframe
                  key={`vimeo-${heroVideoUrl}`}
                  className="absolute"
                  src={`https://player.vimeo.com/video/${heroVideoUrl.split('/').pop()}?autoplay=1&muted=1&loop=1&background=1`}
                  title={displayName}
                  frameBorder="0"
                  allow="autoplay; fullscreen"
                  style={{
                    pointerEvents: 'none', position: 'absolute',
                    top: '50%', left: '50%',
                    width: '177.78vh', height: '100vh',
                    minWidth: '100%', minHeight: '56.25vw',
                    transform: 'translate(-50%, -50%)'
                  }}
                />
              );
            }

            // === IMAGE (uploadée ou externe) — v20.1 ===
            if (heroMediaType === 'image') {
              return (
                <img
                  key={`img-${heroVideoUrl}`}
                  src={heroVideoUrl}
                  alt={displayName}
                  className="absolute inset-0 w-full h-full object-cover"
                  style={{ filter: 'brightness(0.75)' }}
                  onLoad={() => {
                    console.log('[VITRINE-MEDIA] ✅ Image chargée:', heroVideoUrl);
                    const loader = document.getElementById('hero-media-loader');
                    if (loader) loader.style.display = 'none';
                  }}
                  onError={(e) => {
                    console.error('[VITRINE-MEDIA] ❌ Erreur chargement image:', heroVideoUrl);
                    console.error('[V29.4] Image load error:', heroVideoUrl);
                    const loader = document.getElementById('hero-media-loader');
                    if (loader) loader.style.display = 'none';
                    e.target.style.display = 'none';
                  }}
                />
              );
            }

            // === VIDEO (uploadée ou externe) — v29.5 AUTOPLAY + FALLBACK VISUEL ===
            if (heroMediaType === 'video') {
              return (
                <div className="absolute inset-0" key={`vid-wrap-${activeVideoIndex}`}>
                  {/* v29.5: Gradient VISIBLE par défaut — se cache quand la vidéo charge */}
                  <div id={`vid-fallback-${activeVideoIndex}`} className="absolute inset-0" style={{
                    background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.7) 0%, rgba(217, 28, 210, 0.5) 50%, rgba(30, 0, 50, 0.95) 100%)',
                    zIndex: 2, transition: 'opacity 0.5s ease'
                  }}>
                    <div className="absolute inset-0 flex items-center justify-center flex-col gap-3">
                      <div style={{
                        width: '64px', height: '64px', borderRadius: '50%',
                        background: 'rgba(217, 28, 210, 0.7)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        boxShadow: '0 0 25px rgba(217, 28, 210, 0.4)'
                      }}>
                        <svg width="22" height="26" viewBox="0 0 28 32" fill="none">
                          <path d="M28 16L0 32V0L28 16Z" fill="white"/>
                        </svg>
                      </div>
                      <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.85rem' }}>Chargement vidéo...</span>
                    </div>
                  </div>
                  <video
                    key={`vid-${activeVideoIndex}`}
                    autoPlay
                    muted
                    loop={!isVideoPremium}
                    playsInline
                    preload="auto"
                    className="absolute inset-0 w-full h-full object-cover"
                    style={{ filter: 'brightness(0.7)', zIndex: 1 }}
                    onTimeUpdate={handleHeroTimeUpdate}
                    ref={(el) => {
                      if (el) {
                        el.setAttribute('webkit-playsinline', 'true');
                        el.setAttribute('x5-video-player-type', 'h5');
                        if (el.src !== heroVideoUrl) {
                          el.src = heroVideoUrl;
                          el.load();
                        }
                        const tryPlay = (attempt) => {
                          if (attempt > 8) return;
                          setTimeout(() => {
                            if (el.paused && el.readyState >= 2) {
                              el.muted = true;
                              el.play().then(() => {
                                const fb = document.getElementById(`vid-fallback-${activeVideoIndex}`);
                                if (fb) { fb.style.opacity = '0'; fb.style.pointerEvents = 'none'; }
                              }).catch(() => tryPlay(attempt + 1));
                            } else if (el.paused) {
                              tryPlay(attempt + 1);
                            }
                          }, attempt * 300);
                        };
                        tryPlay(0);
                      }
                    }}
                    onCanPlay={(e) => {
                      console.log('[V29.5] Video canplay');
                      const loader = document.getElementById('hero-media-loader');
                      if (loader) loader.style.display = 'none';
                      if (e.target.paused) { e.target.muted = true; e.target.play().catch(() => {}); }
                      const fb = document.getElementById(`vid-fallback-${activeVideoIndex}`);
                      if (fb) { fb.style.opacity = '0'; fb.style.pointerEvents = 'none'; }
                    }}
                    onError={(e) => {
                      console.error('[V29.5] Video error:', e.target.error);
                      const loader = document.getElementById('hero-media-loader');
                      if (loader) loader.style.display = 'none';
                    }}
                  />
                </div>
              );
            }

            // === FALLBACK — gradient décoratif ===
            return (
              <div className="absolute inset-0"
                style={{ background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.5) 0%, rgba(217, 28, 210, 0.4) 100%)' }}>
                <div className="absolute inset-0 flex items-center justify-center"
                  style={{ background: 'radial-gradient(circle at 50% 50%, rgba(217, 28, 210, 0.3) 0%, transparent 70%)' }}>
                  <span className="text-5xl opacity-70">🎬</span>
                </div>
              </div>
            );
          })()}
        </div>

        {/* Navigation dots multi-vidéos */}
        {heroVideos.length > 1 && (
          <div className="absolute z-20" style={{ bottom: '120px', left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: '8px' }}>
            {heroVideos.map((_, idx) => (
              <button
                key={idx}
                onClick={() => setActiveVideoIndex(idx)}
                style={{
                  width: activeVideoIndex === idx ? '24px' : '10px', height: '10px',
                  borderRadius: '5px', border: 'none', cursor: 'pointer',
                  background: activeVideoIndex === idx ? '#D91CD2' : 'rgba(255,255,255,0.4)',
                  boxShadow: activeVideoIndex === idx ? '0 0 10px rgba(217,28,210,0.6)' : 'none',
                  transition: 'all 0.3s ease'
                }}
              />
            ))}
          </div>
        )}

        {/* v34: Badge prix si vidéo premium */}
        {isVideoPremium && !showVideoPreviewOverlay && (
          <div className="absolute z-20" style={{
            top: '60px', right: '16px',
            background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
            padding: '4px 12px', borderRadius: '20px',
            boxShadow: '0 0 15px rgba(217,28,210,0.4)',
            fontSize: '12px', fontWeight: 700, color: '#fff'
          }}>
            💎 {currentVideoPrice} CHF
          </div>
        )}

        {/* v34: Overlay achat vidéo premium — après 30s */}
        {showVideoPreviewOverlay && isVideoPremium && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center"
            style={{
              background: 'rgba(0,0,0,0.85)',
              backdropFilter: 'blur(12px)',
              WebkitBackdropFilter: 'blur(12px)'
            }}
          >
            <div style={{
              width: '80px', height: '80px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 40px rgba(217,28,210,0.5)',
              marginBottom: '20px'
            }}>
              <svg width="36" height="36" viewBox="0 0 24 24" fill="white">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
              </svg>
            </div>
            <h3 style={{ color: '#fff', fontSize: '20px', fontWeight: 700, marginBottom: '8px' }}>Aperçu terminé</h3>
            <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '14px', marginBottom: '20px', textAlign: 'center', maxWidth: '280px' }}>
              {currentHeroVideo?.description || 'Achetez la version complète pour continuer'}
            </p>
            <button
              onClick={() => {
                console.log('[V34-VITRINE] Achat vidéo:', currentHeroVideo?.title, currentVideoPrice, 'CHF');
                setSelectedOffer({
                  name: currentHeroVideo?.title || `Vidéo ${displayName}`,
                  price: currentVideoPrice,
                  id: currentHeroVideo?.id || `hero-${activeVideoIndex}`,
                  type: 'video',
                  thumbnail: currentHeroVideo?.thumbnail || ''
                });
              }}
              style={{
                background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                color: '#fff', border: 'none', padding: '14px 32px',
                borderRadius: '30px', fontSize: '16px', fontWeight: 700,
                cursor: 'pointer', boxShadow: '0 0 25px rgba(217,28,210,0.5)'
              }}
            >
              Acheter — {currentVideoPrice} CHF
            </button>
            <button
              onClick={() => setShowVideoPreviewOverlay(false)}
              style={{
                background: 'transparent', color: 'rgba(255,255,255,0.4)',
                border: 'none', padding: '10px 20px', marginTop: '12px',
                fontSize: '13px', cursor: 'pointer'
              }}
            >
              Revoir l'aperçu
            </button>
          </div>
        )}

        {/* v75: Icône AVIS intégrée dans la barre d'actions ci-dessous */}

        {/* Gradient overlay bas */}
        <div className="absolute inset-0 pointer-events-none"
          style={{ background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 25%, transparent 50%)' }} />

        {/* === HEADER OVERLAY — Retour + Logo + QR + Partage (FIXES en haut à droite) === */}
        <div className="absolute top-0 left-0 right-0 z-20 flex justify-between items-center px-4 pt-4">
          {/* Bouton Retour */}
          <button onClick={cameFromFlux ? handleReturnToFlux : (onBack || onClose)}
            className="w-10 h-10 rounded-full flex items-center justify-center transition-all hover:scale-110"
            style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(8px)' }}>
            <svg className="w-5 h-5" fill="none" stroke="white" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>

          {/* Logo Afroboost centre */}
          <div className="flex items-center gap-2">
            <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
              <defs>
                <linearGradient id="vitrineLogo" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#D91CD2" />
                  <stop offset="100%" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
              <circle cx="20" cy="20" r="18" stroke="url(#vitrineLogo)" strokeWidth="2.5" fill="none" />
              <path d="M20 10 L26 28 H14 L20 10Z" fill="url(#vitrineLogo)" />
              <circle cx="20" cy="18" r="4" fill="url(#vitrineLogo)" />
            </svg>
          </div>

          {/* v17: QR + Partage uniquement dans la barre latérale (pas de doublon) */}
          <div className="flex items-center gap-2" />
        </div>

        {/* === BARRE D'ACTIONS DROITE — Style Instagram Reels === */}
        <div className="absolute right-3 bottom-32 z-20 flex flex-col items-center gap-5">
          {/* Avatar coach */}
          <div className="flex flex-col items-center gap-1">
            {coach.logo_url || coach.photo_url ? (
              <img src={coach.logo_url || coach.photo_url} alt={displayName}
                className="w-10 h-10 rounded-full object-cover"
                style={{ border: '2px solid #D91CD2' }} />
            ) : (
              <div className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold"
                style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #d91cd2 100%)', color: 'white', border: '2px solid #D91CD2' }}>
                {initial}
              </div>
            )}
          </div>

          {/* v88: Bouton Avis/Commentaires — glow réduit pour meilleure lisibilité */}
          {socialComments.length > 0 && (
            <button onClick={() => setShowCommentsPanel(true)} className="flex flex-col items-center gap-1">
              <div className="w-10 h-10 rounded-full flex items-center justify-center"
                style={{
                  background: 'rgba(217, 28, 210, 0.3)',
                  backdropFilter: 'blur(6px)',
                  border: '1.5px solid rgba(217, 28, 210, 0.5)',
                  boxShadow: '0 0 6px rgba(217, 28, 210, 0.25)'
                }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
              </div>
              <span className="text-[10px] font-bold" style={{ color: '#fff', textShadow: '0 1px 3px rgba(0,0,0,0.8)' }}>
                {socialComments.length} Avis
              </span>
            </button>
          )}

          {/* QR Code */}
          <button onClick={() => setShowQR(true)} className="flex flex-col items-center gap-1">
            <div className="w-10 h-10 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(255,255,255,0.15)', backdropFilter: 'blur(8px)' }}>
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h2M4 12h2m14 0h2M6 20h2m-2-8h2" />
              </svg>
            </div>
            <span className="text-white text-[10px]">QR</span>
          </button>

          {/* Partager */}
          <button onClick={handleShare} className="flex flex-col items-center gap-1">
            <div className="w-10 h-10 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(255,255,255,0.15)', backdropFilter: 'blur(8px)' }}>
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
              </svg>
            </div>
            <span className="text-white text-[10px]">Partager</span>
          </button>

          {/* Réserver (scroll) */}
          <button onClick={() => {
            const target = document.getElementById('vitrine-content-section');
            if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }} className="flex flex-col items-center gap-1">
            <div className="w-10 h-10 rounded-full flex items-center justify-center"
              style={{ background: 'rgba(217, 28, 210, 0.6)', boxShadow: '0 0 6px rgba(217, 28, 210, 0.3)' }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <span className="text-white text-[10px]">Réserver</span>
          </button>
        </div>

        {/* === NOM DU COACH EN BAS === */}
        <div className="absolute bottom-4 left-4 right-16 z-20">
          <h2 className="text-white font-bold text-xl mb-1" style={{ textShadow: '0 2px 8px rgba(0,0,0,0.8)' }}>
            {displayName}
          </h2>
          {coach.bio && (
            <p className="text-white/70 text-sm line-clamp-2" style={{ textShadow: '0 1px 4px rgba(0,0,0,0.8)' }}>
              {coach.bio}
            </p>
          )}
        </div>
      </div>

      {/* ============================================= */}
      {/* CONTENU SOUS LE HERO — FLOW INLINE */}
      {/* Étape 1: Choisir session → Étape 2: Choisir offre → Étape 3: Formulaire */}
      {/* ============================================= */}
      <div id="vitrine-content-section" className="max-w-4xl mx-auto px-6 pt-2"
        style={{ background: 'transparent' }}>

        {/* v16: DESCRIPTION PARTENAIRE — entre Hero et Sessions */}
        {coach.bio && (
          <div className="mb-8 pt-4 vitrine-fade-in" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '20px' }}>
            <div className="flex items-start gap-4">
              {/* Avatar */}
              <div className="flex-shrink-0">
                {coach.photo_url || coach.logo_url ? (
                  <img src={coach.photo_url || coach.logo_url} alt={displayName}
                    className="w-14 h-14 rounded-full object-cover"
                    style={{ border: '2px solid rgba(217, 28, 210, 0.4)' }} />
                ) : (
                  <div className="w-14 h-14 rounded-full flex items-center justify-center text-lg font-bold"
                    style={{ background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)', color: '#fff' }}>
                    {(displayName || 'P').charAt(0).toUpperCase()}
                  </div>
                )}
              </div>
              {/* Texte */}
              <div className="flex-1 min-w-0">
                <h3 className="text-white font-semibold text-base mb-1">{displayName}</h3>
                <p className="text-white/70 text-sm leading-relaxed">{coach.bio}</p>
              </div>
            </div>
          </div>
        )}

        {/* === ÉTAPE 1: Cours/Sessions === */}
        {uniqueCourses.length > 0 && (
          <div id="vitrine-courses-section" className="mb-8">
            <h2 className="font-semibold mb-4 text-white flex items-center gap-2" style={{ fontSize: '18px' }}>
              Choisissez vos sessions
              {selectedBookings.length > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(217, 28, 210, 0.3)', color: '#d91cd2' }}>
                  {selectedBookings.length} sélectionnée{selectedBookings.length > 1 ? 's' : ''}
                </span>
              )}
            </h2>
            <div className="space-y-4 sessions-scrollbar"
              style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '8px' }}>
              {uniqueCourses.map(course => {
                const upcomingDates = course.weekday !== undefined ? getNextOccurrences(course.weekday, 4) : [];
                const isSelected = selectedBookings.some(b => b.course.id === course.id);
                return (
                  <div key={course.id}
                    className="rounded-xl p-5 transition-all duration-200"
                    style={{
                      background: isSelected ? 'rgba(217, 28, 210, 0.08)' : 'transparent',
                      borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                      borderLeft: isSelected ? '2px solid #d91cd2' : 'none'
                    }}>
                    <h3 className="font-semibold text-white">{course.name || course.title}</h3>

                    {(course.locationName || course.location) && (
                      <div className="flex items-center gap-2 text-xs text-white opacity-60 mb-1">
                        <LocationIcon />
                        <span>{course.locationName || course.location}</span>
                      </div>
                    )}

                    {course.time && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-sm">⏰</span>
                        <span className="text-purple-400 font-medium text-sm">{course.time}</span>
                      </div>
                    )}

                    {upcomingDates.length > 0 && (
                      <div className="mt-3">
                        <div className="flex flex-wrap gap-2">
                          {upcomingDates.map((date, idx) => {
                            const isDateSelected = selectedBookings.some(b => b.course.id === course.id && b.date.toISOString() === date.toISOString());
                            return (
                              <button key={idx}
                                onClick={() => handleBookClick(course, date)}
                                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:scale-105"
                                style={{
                                  background: isDateSelected ? 'rgba(217, 28, 210, 0.5)' : 'rgba(217, 28, 210, 0.2)',
                                  border: isDateSelected ? '2px solid #d91cd2' : '1px solid rgba(217, 28, 210, 0.4)',
                                  color: isDateSelected ? '#fff' : '#d91cd2',
                                  cursor: 'pointer'
                                }}>
                                {formatDateShort(date)} • {course.time}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    {course.weekday !== undefined && upcomingDates.length === 0 && (
                      <div className="mt-2 px-3 py-1 inline-block rounded-full text-xs font-medium"
                        style={{ background: 'rgba(217, 28, 210, 0.2)', color: '#d91cd2' }}>
                        {['Dimanche', 'Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi'][course.weekday]}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* === ÉTAPE 2: Offres — Apparaît après sélection d'une session === */}
        {selectedBooking && uniqueOffers.length > 0 && (
          <div className="mb-8">
            <h2 className="font-semibold mb-2 text-white" style={{ fontSize: '18px' }}>
              {offers === DEFAULT_STARTER_OFFERS ? 'Offres de démarrage' : 'Choisissez votre offre'}
            </h2>
            <p className="text-sm mb-4" style={{ color: '#d91cd2' }}>
              Sélectionnez une offre pour continuer
            </p>

            <div ref={sliderRef}
              className="flex gap-4 overflow-x-auto snap-x snap-mandatory pb-4"
              style={{ scrollBehavior: 'smooth', WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none' }}>
              {uniqueOffers.map((offer) => {
                const defaultImage = "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=400&h=300&fit=crop";
                const imageUrl = offer.imageUrl || offer.thumbnail || offer.images?.[0] || defaultImage;
                const isOfferSelected = selectedOffer?.id === offer.id;
                return (
                  <div key={offer.id} className="flex-shrink-0 snap-start" style={{ width: '280px', minWidth: '280px', padding: '4px' }}>
                    <div className="rounded-xl overflow-hidden cursor-pointer transition-all duration-300 hover:scale-[1.02]"
                      style={{
                        boxShadow: isOfferSelected ? '0 0 20px rgba(217, 28, 210, 0.6)' : '0 4px 20px rgba(0,0,0,0.4)',
                        background: 'linear-gradient(180deg, rgba(20,10,30,0.98) 0%, rgba(5,0,15,0.99) 100%)',
                        border: isOfferSelected ? '2px solid #d91cd2' : '1px solid rgba(217, 28, 210, 0.3)'
                      }}
                      onClick={() => {
                        setSelectedOffer(offer);
                        setTimeout(() => {
                          const el = document.getElementById('vitrine-booking-form');
                          if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }, 100);
                      }}>
                      <div style={{ position: 'relative', height: '180px', overflow: 'hidden' }}>
                        <img src={imageUrl} alt={offer.name} className="w-full h-full object-cover"
                          onError={(e) => { e.target.src = defaultImage; }} />
                        {offer.price === 0 && (
                          <div className="absolute top-3 left-3 px-3 py-1 rounded-full text-xs font-bold text-white"
                            style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}>
                            GRATUIT
                          </div>
                        )}
                        {isOfferSelected && (
                          <div className="absolute top-3 right-3 w-7 h-7 rounded-full flex items-center justify-center"
                            style={{ background: '#d91cd2' }}>
                            <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                            </svg>
                          </div>
                        )}
                      </div>
                      <div className="p-4">
                        <p className="font-semibold text-white mb-2" style={{ fontSize: '16px' }}>{offer.name}</p>
                        <span className="text-xl font-bold" style={{ color: '#d91cd2' }}>
                          {offer.price === 0 ? 'Offert' : `CHF ${offer.price}.-`}
                        </span>
                        {offer.duration_value && offer.duration_unit && (
                          <div style={{ marginTop: '6px', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '20px', background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139, 92, 246, 0.4)', fontSize: '11px', color: '#a78bfa' }}>
                            <span>⏱</span>
                            <span>Valable {offer.duration_value} {offer.duration_unit === 'days' ? 'jour(s)' : offer.duration_unit === 'weeks' ? 'semaine(s)' : 'mois'}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Offres visibles TOUJOURS si pas de session sélectionnée (browsing) */}
        {!selectedBooking && uniqueOffers.length > 0 && (
          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-semibold text-white" style={{ fontSize: '18px' }}>
                {offers === DEFAULT_STARTER_OFFERS ? 'Offres de démarrage' : 'Offres disponibles'}
              </h2>
              {uniqueOffers.length > 1 && (
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-white/50 text-sm">🔍</span>
                  <input type="text" value={offerSearch} onChange={(e) => setOfferSearch(e.target.value)}
                    placeholder="Rechercher..."
                    className="pl-9 pr-4 py-2 rounded-full bg-black/40 text-white text-sm border border-white/20 focus:outline-none focus:ring-2 focus:ring-violet-500 w-40" />
                </div>
              )}
            </div>
            {(() => {
              const searchTerm = offerSearch.toLowerCase().trim();
              const filtered = searchTerm
                ? uniqueOffers.filter(o => (o.name || '').toLowerCase().includes(searchTerm) || (o.description || '').toLowerCase().includes(searchTerm))
                : uniqueOffers;
              return filtered.length > 0 ? (
                <div className="flex gap-4 overflow-x-auto snap-x snap-mandatory pb-4"
                  style={{ scrollBehavior: 'smooth', WebkitOverflowScrolling: 'touch', scrollbarWidth: 'none' }}>
                  {filtered.map((offer) => {
                    const defaultImage = "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=400&h=300&fit=crop";
                    const imageUrl = offer.imageUrl || offer.thumbnail || offer.images?.[0] || defaultImage;
                    return (
                      <div key={offer.id} className="flex-shrink-0 snap-start" style={{ width: '280px', minWidth: '280px', padding: '4px' }}>
                        <div className="rounded-xl overflow-hidden transition-all duration-300 hover:scale-[1.02]"
                          style={{
                            boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
                            background: 'linear-gradient(180deg, rgba(20,10,30,0.98) 0%, rgba(5,0,15,0.99) 100%)',
                            border: '1px solid rgba(217, 28, 210, 0.3)'
                          }}>
                          <div style={{ position: 'relative', height: '180px', overflow: 'hidden' }}>
                            <img src={imageUrl} alt={offer.name} className="w-full h-full object-cover"
                              onError={(e) => { e.target.src = defaultImage; }} />
                            {offer.price === 0 && (
                              <div className="absolute top-3 left-3 px-3 py-1 rounded-full text-xs font-bold text-white"
                                style={{ background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)' }}>
                                GRATUIT
                              </div>
                            )}
                          </div>
                          <div className="p-4">
                            <p className="font-semibold text-white mb-2" style={{ fontSize: '16px' }}>{offer.name}</p>
                            <span className="text-xl font-bold" style={{ color: '#d91cd2' }}>
                              {offer.price === 0 ? 'Offert' : `CHF ${offer.price}.-`}
                            </span>
                            {offer.duration_value && offer.duration_unit && (
                              <div style={{ marginTop: '6px', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '2px 8px', borderRadius: '20px', background: 'rgba(139, 92, 246, 0.15)', border: '1px solid rgba(139, 92, 246, 0.4)', fontSize: '11px', color: '#a78bfa' }}>
                                <span>⏱</span>
                                <span>Valable {offer.duration_value} {offer.duration_unit === 'days' ? 'jour(s)' : offer.duration_unit === 'weeks' ? 'semaine(s)' : 'mois'}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-white/50 text-center py-8">Aucune offre ne correspond à "{offerSearch}"</p>
              );
            })()}
          </div>
        )}

        {/* ============================================= */}
        {/* v44: Section Contenus Audio — pistes autonomes depuis /api/public/audio-tracks */}
        {audioTracks.length > 0 && (
          <div className="mb-8 vitrine-fade-in" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '24px' }}>
            <h2 className="font-semibold text-white text-center mb-4" style={{ fontSize: '16px' }}>
              🎵 Contenus Audio
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {audioTracks.map(track => (
                <AudioPlayer
                  key={track.id}
                  audioUrl={track.url}
                  title={track.title}
                  thumbnail={track.cover_url}
                  duration={track.duration}
                  price={track.price}
                  description={track.description}
                  accentColor={brandAccent}
                  isPreview={!!track.price && track.price > 0}
                  previewDuration={track.preview_duration || 30}
                  onBuyClick={track.price > 0 ? () => {
                    setSelectedOffer({ name: track.title, price: track.price, id: track.id, type: 'audio', thumbnail: track.cover_url });
                    const el = document.getElementById('vitrine-booking-form');
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  } : undefined}
                />
              ))}
            </div>
          </div>
        )}

        {/* ÉTAPE 3: FORMULAIRE INLINE (pas de pop-up) */}
        {/* Apparaît quand session + offre sélectionnées */}
        {/* ============================================= */}
        {selectedBooking && selectedOffer && (
          <div id="vitrine-booking-form" ref={formRef} className="mb-8 rounded-xl p-6"
            style={{
              background: 'linear-gradient(180deg, rgba(20,10,30,0.6) 0%, rgba(10,5,20,0.8) 100%)',
              border: '1px solid rgba(217, 28, 210, 0.3)',
              boxShadow: '0 0 30px rgba(217, 28, 210, 0.15)'
            }}>

            {bookingSuccess ? (
              <div className="text-center py-8">
                <div className="text-5xl mb-4">✅</div>
                <h4 className="text-xl font-bold text-white mb-2">Réservation confirmée !</h4>
                <p className="text-white/60 mb-4">Vous recevrez une confirmation par email.</p>
                <button onClick={() => {
                  setBookingSuccess(false);
                  setSelectedBookings([]);
                  setSelectedOffer(null);
                }}
                  className="px-6 py-3 rounded-xl text-white font-medium transition-all hover:scale-105"
                  style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #d91cd2 100%)' }}>
                  Nouvelle réservation
                </button>
              </div>
            ) : (
              <>
                <h3 className="text-lg font-bold text-white mb-4">
                  Finaliser votre réservation {selectedBookings.length > 1 && <span className="text-sm font-normal text-purple-400">({selectedBookings.length} séances)</span>}
                </h3>

                {/* Récapitulatif multi-séances */}
                <div className="rounded-lg p-4 mb-6"
                  style={{ background: 'rgba(217, 28, 210, 0.1)', border: '1px solid rgba(217, 28, 210, 0.2)' }}>
                  {selectedBookings.map((booking, idx) => (
                    <div key={idx} className={idx > 0 ? 'mt-3 pt-3' : ''} style={idx > 0 ? { borderTop: '1px solid rgba(255,255,255,0.1)' } : {}}>
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-white font-semibold text-sm">{booking.course.name || booking.course.title}</p>
                          <p className="text-purple-400 text-xs mt-0.5">
                            {booking.date.toLocaleDateString('fr-CH', { weekday: 'long', day: '2-digit', month: 'long' })}
                            {' • '}{booking.course.time}
                          </p>
                        </div>
                        <button type="button" onClick={() => setSelectedBookings(prev => prev.filter((_, i) => i !== idx))}
                          className="text-white/40 hover:text-red-400 text-xs ml-2 transition-colors">✕</button>
                      </div>
                    </div>
                  ))}
                  {selectedOffer && (
                    <p className="text-white/60 text-sm mt-3 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                      Offre : <span className="text-white">{selectedOffer.name}</span> — <span style={{ color: '#d91cd2' }}>{selectedOffer.price === 0 ? 'Offert' : `CHF ${selectedOffer.price}.-`}</span>
                    </p>
                  )}
                </div>

                {/* Formulaire */}
                <form onSubmit={handleBookingSubmit} className="space-y-4">
                  <div>
                    <label className="text-white/60 text-xs mb-1 block">Nom complet</label>
                    <input type="text" required value={bookingForm.name}
                      onChange={e => setBookingForm(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full px-4 py-3 rounded-lg text-white"
                      style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)' }}
                      placeholder="Votre nom" />
                  </div>
                  <div>
                    <label className="text-white/60 text-xs mb-1 block">Email</label>
                    <input type="email" required value={bookingForm.email}
                      onChange={e => setBookingForm(prev => ({ ...prev, email: e.target.value }))}
                      className="w-full px-4 py-3 rounded-lg text-white"
                      style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)' }}
                      placeholder="email@example.com" />
                  </div>
                  <div>
                    <label className="text-white/60 text-xs mb-1 block">WhatsApp</label>
                    <input type="tel" required value={bookingForm.whatsapp}
                      onChange={e => setBookingForm(prev => ({ ...prev, whatsapp: e.target.value }))}
                      className="w-full px-4 py-3 rounded-lg text-white"
                      style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.15)' }}
                      placeholder="+41 79 XXX XX XX" />
                  </div>

                  {/* Code Promo — v17: layout mobile-safe */}
                  <div>
                    <label className="text-white/60 text-xs mb-1 block">Code Promo (optionnel)</label>
                    <div className="flex gap-2" style={{ flexWrap: 'nowrap', maxWidth: '100%' }}>
                      <input type="text" value={bookingForm.promoCode}
                        onChange={e => setBookingForm(prev => ({ ...prev, promoCode: e.target.value.toUpperCase() }))}
                        className="px-3 py-3 rounded-lg text-white text-sm"
                        style={{
                          flex: '1 1 0%',
                          minWidth: 0,
                          background: appliedDiscount ? 'rgba(34, 197, 94, 0.15)' : 'rgba(255,255,255,0.08)',
                          border: appliedDiscount ? '1px solid rgba(34, 197, 94, 0.5)' : '1px solid rgba(255,255,255,0.15)'
                        }}
                        placeholder="CODE123" />
                      <button type="button" onClick={() => validatePromoCode(bookingForm.promoCode)}
                        className="rounded-lg font-medium transition-all hover:scale-105 text-sm"
                        style={{ flexShrink: 0, padding: '12px 14px', background: 'rgba(217, 28, 210, 0.3)', border: '1px solid rgba(217, 28, 210, 0.5)', color: '#D91CD2', whiteSpace: 'nowrap' }}>
                        Valider
                      </button>
                    </div>
                    {promoMessage.text && (
                      <p className={`mt-2 text-sm font-medium ${promoMessage.type === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                        {promoMessage.text}
                      </p>
                    )}
                  </div>

                  {/* Résumé prix — v17: × nombre de séances */}
                  <div className="rounded-lg p-3"
                    style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
                    <div className="flex justify-between text-sm text-white/70">
                      <span>{selectedOffer.name} {selectedBookings.length > 1 ? `× ${selectedBookings.length} séances` : ''}</span>
                      <span>{((selectedOffer.price || 0) * Math.max(1, selectedBookings.length)).toFixed(2)} CHF</span>
                    </div>
                    {appliedDiscount && (
                      <div className="flex justify-between text-sm text-green-400 mt-1">
                        <span>Réduction ({appliedDiscount.code})</span>
                        <span>-{appliedDiscount.type === '100%' ? '100%' : appliedDiscount.type === '%' ? `${appliedDiscount.value}%` : `${appliedDiscount.value} CHF`}</span>
                      </div>
                    )}
                    <div className="flex justify-between text-white font-bold mt-2 pt-2 border-t border-white/10">
                      <span>Total</span>
                      <span>{calculateFinalPrice().toFixed(2)} CHF</span>
                    </div>
                  </div>

                  {/* v15.0: Checkout intégré multi-vendeurs (remplace les liens de paiement externes) */}
                  {(selectedBookings.length > 0 || selectedOffer) && (
                    <VitrineCheckout
                      coachEmail={coach?.email || username}
                      coachName={coach?.name || username}
                      selectedBookings={selectedBookings}
                      selectedOffer={selectedOffer}
                      customerName={bookingForm.name}
                      customerEmail={bookingForm.email}
                      customerPhone={bookingForm.whatsapp}
                      appliedDiscount={appliedDiscount}
                      onSuccess={(data) => {
                        setBookingSuccess(true);
                        setSelectedBookings([]);
                        setSelectedOffer(null);
                      }}
                    />
                  )}

                  {/* Bouton Confirmer */}
                  <button type="submit" disabled={bookingLoading}
                    className="w-full py-4 rounded-xl text-white font-semibold transition-all hover:scale-[1.02]"
                    style={{
                      background: bookingLoading ? 'rgba(139, 92, 246, 0.5)' : 'linear-gradient(135deg, #D91CD2 0%, #8b5cf6 100%)',
                      boxShadow: bookingLoading ? 'none' : '0 0 25px rgba(217, 28, 210, 0.4)'
                    }}>
                    {bookingLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                        </svg>
                        Réservation en cours...
                      </span>
                    ) : 'Confirmer la réservation'}
                  </button>
                </form>
              </>
            )}
          </div>
        )}

        {/* v73: Section "Ce que disent nos clients" SUPPRIMÉE — tout passe par l'icône Glow du Hero */}

        {/* v72.1: Panneau commentaires style YouTube — slide-up depuis le bas */}
        {showCommentsPanel && (
          <div
            className="fixed inset-0 z-50"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={() => setShowCommentsPanel(false)}
          >
            <div
              style={{
                position: 'absolute', left: 0, right: 0, bottom: 0,
                maxHeight: '75vh',
                background: '#fff',
                borderRadius: '16px 16px 0 0',
                overflowY: 'auto', WebkitOverflowScrolling: 'touch',
                animation: 'v72slideUp 0.3s ease-out'
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header YouTube-style */}
              <div style={{
                position: 'sticky', top: 0, zIndex: 10,
                background: '#fff',
                borderBottom: '1px solid #e5e5e5',
                borderRadius: '16px 16px 0 0'
              }}>
                <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 4px' }}>
                  <div style={{ width: '40px', height: '4px', borderRadius: '2px', background: '#ccc' }}></div>
                </div>
                <div style={{
                  padding: '4px 16px 12px',
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between'
                }}>
                  <span style={{ color: '#0f0f0f', fontSize: '16px', fontWeight: 700 }}>
                    Commentaires {socialComments.length}
                  </span>
                  <button
                    onClick={() => setShowCommentsPanel(false)}
                    style={{
                      width: '32px', height: '32px', borderRadius: '50%',
                      background: 'transparent', border: 'none', cursor: 'pointer',
                      display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#606060" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </div>
              </div>

              {/* Liste des commentaires */}
              <div style={{ padding: '0 16px 100px' }}>
                {socialComments.map((comment) => (
                  <div key={comment.id} style={{
                    padding: '12px 0',
                    borderBottom: '1px solid #f0f0f0'
                  }}>
                    <div style={{ display: 'flex', gap: '12px' }}>
                      {/* v74: Avatar — cliquable si photo réelle */}
                      {comment.profile_photo ? (
                        <div
                          onClick={() => setZoomedPhoto(comment.profile_photo)}
                          style={{
                            width: '36px', height: '36px', borderRadius: '50%',
                            overflow: 'hidden', cursor: 'pointer', flexShrink: 0,
                            border: '2px solid #D91CD2'
                          }}
                        >
                          <img
                            src={comment.profile_photo}
                            alt={comment.user_name}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                          />
                        </div>
                      ) : (
                        <div style={{
                          width: '36px', height: '36px', borderRadius: '50%',
                          background: '#D91CD2',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: '14px', fontWeight: 700, color: '#fff', flexShrink: 0
                        }}>
                          {(comment.user_name || '?')[0].toUpperCase()}
                        </div>
                      )}
                      <div style={{ flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                          <span style={{ color: '#0f0f0f', fontSize: '13px', fontWeight: 600 }}>
                            {comment.user_name}
                          </span>
                          {/* v86: Badge "Vérifié" pour les avis réels post-session */}
                          {comment.is_verified && (
                            <span style={{
                              background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                              color: '#fff',
                              fontSize: '9px',
                              fontWeight: 700,
                              padding: '2px 6px',
                              borderRadius: '8px',
                              letterSpacing: '0.3px'
                            }}>✓ Vérifié</span>
                          )}
                          <div style={{ display: 'flex', gap: '1px' }}>
                            {[1,2,3,4,5].map(i => (
                              <svg key={i} width="10" height="10" viewBox="0 0 24 24"
                                fill={i <= (comment.rating || 5) ? '#D91CD2' : '#ddd'}
                                stroke="none"
                              >
                                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                              </svg>
                            ))}
                          </div>
                        </div>
                        <p style={{ color: '#303030', fontSize: '13px', lineHeight: 1.5, margin: '4px 0 6px' }}>
                          {comment.text}
                        </p>
                        <button
                          onClick={async () => {
                            try {
                              await axios.post(`${API}/comments/${comment.id}/like`);
                              setSocialComments(prev => prev.map(c =>
                                c.id === comment.id ? { ...c, likes: (c.likes || 0) + 1 } : c
                              ));
                            } catch (e) {}
                          }}
                          style={{
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: '#606060', fontSize: '12px',
                            display: 'flex', alignItems: 'center', gap: '4px', padding: '2px 0'
                          }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#606060" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
                            <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
                          </svg>
                          {comment.likes || 0}
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* v74: Modal zoom photo profil */}
        {zoomedPhoto && (
          <div
            className="fixed inset-0 z-50"
            style={{
              background: 'rgba(0,0,0,0.85)',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}
            onClick={() => setZoomedPhoto(null)}
          >
            <div style={{
              width: '260px', height: '260px', borderRadius: '50%',
              overflow: 'hidden',
              border: '3px solid #D91CD2',
              boxShadow: '0 0 30px rgba(217,28,210,0.5)',
              animation: 'v74ZoomIn 0.25s ease-out'
            }}>
              <img
                src={zoomedPhoto}
                alt="Photo profil"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </div>
          </div>
        )}

        {/* v74: CSS Animations — slide-up + Glow Pulse + Zoom */}
        <style>{`
          @keyframes v72slideUp {
            from { transform: translateY(100%); }
            to { transform: translateY(0); }
          }
          @keyframes v73GlowPulse {
            0%, 100% { transform: scale(1); box-shadow: 0 0 6px rgba(217,28,210,0.2); }
            50% { transform: scale(1.03); box-shadow: 0 0 10px rgba(217,28,210,0.3); }
          }
          @keyframes v74ZoomIn {
            from { transform: scale(0.5); opacity: 0; }
            to { transform: scale(1); opacity: 1; }
          }
        `}</style>

        {/* v104: Section FAQ Accordéon — titre cliquable pour ouvrir/fermer */}
        {faqs.length > 0 && (
          <div className="mb-8 vitrine-fade-in" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '24px' }}>
            <button
              onClick={() => setFaqSectionOpen(!faqSectionOpen)}
              style={{
                width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px',
                marginBottom: faqSectionOpen ? '16px' : '0', padding: '8px 0',
              }}
            >
              <h2 className="font-semibold text-white" style={{ fontSize: '16px', margin: 0 }}>
                Questions fréquentes
              </h2>
              <span style={{
                color: brandAccent, fontSize: '18px', fontWeight: '300',
                transform: faqSectionOpen ? 'rotate(45deg)' : 'none',
                transition: 'transform 0.2s ease',
              }}>+</span>
            </button>
            {faqSectionOpen && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {faqs.map(faq => (
                  <div key={faq.id} style={{
                    borderRadius: '10px',
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    overflow: 'hidden'
                  }}>
                    <button
                      onClick={() => setOpenFaqId(openFaqId === faq.id ? null : faq.id)}
                      style={{
                        width: '100%', padding: '12px 16px',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left'
                      }}
                    >
                      <span style={{ color: '#fff', fontSize: '13px', fontWeight: 500 }}>{faq.question}</span>
                      <span style={{
                        color: brandAccent, fontSize: '16px', fontWeight: 700,
                        transform: openFaqId === faq.id ? 'rotate(45deg)' : 'none',
                        transition: 'transform 0.2s ease'
                      }}>+</span>
                    </button>
                    {openFaqId === faq.id && faq.answer && (
                      <div style={{
                        padding: '0 16px 12px',
                        color: 'rgba(255,255,255,0.6)',
                        fontSize: '12px',
                        lineHeight: '1.5',
                        animation: 'afroMsgSlideIn 0.2s ease-out'
                      }}>
                        {faq.answer}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* === Footer === */}
        <div className="text-center mt-4 pb-8">
          <p className="text-white/30 text-xs">
            Propulsé par <span style={{ color: '#d91cd2' }}>Afroboost</span> - La plateforme des coachs
          </p>
        </div>
      </div>
    </div>
  );
};

export default CoachVitrine;

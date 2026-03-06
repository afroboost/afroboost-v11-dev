/**
 * CoachVitrine - Vitrine publique d'un coach v14.0 INLINE BOOKING
 * Route: /coach/[username]
 * Layout IDENTIQUE à la page d'accueil :
 *   - Hero 85vh avec YouTube Lite Facade (thumbnail + play)
 *   - Nom coach + actions overlays (style Instagram Reels)
 *   - Sous le hero : Cours/Sessions → Offres → Formulaire INLINE (pas de pop-up)
 *   - QR + Partage en haut à droite sur toutes les pages
 */
import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { QRCodeSVG } from "qrcode.react";
import { copyToClipboard } from "../utils/clipboard";

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

  // v14: INLINE booking (plus de modal)
  const [selectedBooking, setSelectedBooking] = useState(null); // { course, date }
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

  // v14: Clic sur date → sélection inline (pas de modal)
  const handleBookClick = (course, date) => {
    setSelectedBooking({ course, date });
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

  // Calculer prix final
  const calculateFinalPrice = () => {
    if (!selectedOffer) return 0;
    let total = selectedOffer.price || 0;
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
    if (!selectedBooking || bookingLoading) return;
    setBookingLoading(true);
    try {
      const res = await axios.post(`${API}/reservations`, {
        userName: bookingForm.name,
        userEmail: bookingForm.email,
        userWhatsapp: bookingForm.whatsapp,
        courseId: selectedBooking.course.id,
        courseName: selectedBooking.course.name || selectedBooking.course.title,
        courseTime: selectedBooking.course.time,
        datetime: selectedBooking.date.toISOString(),
        coach_id: coach?.email || username,
        source: 'vitrine_partenaire',
        selectedOffer: selectedOffer ? { id: selectedOffer.id, name: selectedOffer.name, price: selectedOffer.price } : null,
        appliedDiscount: appliedDiscount ? {
          id: appliedDiscount.id, code: appliedDiscount.code,
          type: appliedDiscount.type, value: appliedDiscount.value
        } : null
      });
      if (res.data) {
        if (appliedDiscount) {
          try { await axios.post(`${API}/discount-codes/${appliedDiscount.id}/use`); } catch (e) {}
        }
        setBookingSuccess(true);
        setBookingForm({ name: '', email: '', whatsapp: '', promoCode: '' });
      }
    } catch (err) {
      console.error('[BOOKING] Erreur:', err);
      alert(err.response?.data?.detail || 'Erreur lors de la réservation');
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

        // Charger paiement
        try {
          const paymentRes = await axios.get(`${API}/payment-links/${encodeURIComponent(res.data.coach.email || username)}`);
          setPaymentConfig(paymentRes.data);
        } catch (e) {}

        // Charger la vidéo du coach depuis /partners/active (source fiable)
        try {
          const partnersRes = await axios.get(`${API}/partners/active`);
          const coachEmail = (res.data.coach.email || username).toLowerCase();
          const partnerData = partnersRes.data.find(p =>
            p.email?.toLowerCase() === coachEmail ||
            p.name?.toLowerCase() === username.toLowerCase() ||
            p.platform_name?.toLowerCase() === username.toLowerCase()
          );
          if (partnerData) {
            setCoachConcept({
              heroImageUrl: partnerData.heroImageUrl || partnerData.video_url,
              heroVideoUrl: partnerData.video_url
            });
          }
        } catch (e) {
          // Fallback: essayer le concept direct
          try {
            const conceptRes = await axios.get(`${API}/concept`, {
              headers: { 'X-User-Email': res.data.coach.email || username }
            });
            setCoachConcept(conceptRes.data);
          } catch (e2) {}
        }
      } catch (err) {
        console.error('[VITRINE] Erreur:', err);
        setError(err.response?.data?.detail || 'Coach non trouvé');
      } finally {
        setLoading(false);
      }
    };
    fetchVitrine();
  }, [username]);

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

  // Extraire YouTube ID du concept
  const heroVideoUrl = coachConcept?.heroImageUrl || coachConcept?.heroVideoUrl || coach.video_url;
  const youtubeId = getYoutubeId(heroVideoUrl);

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

        {/* Fond vidéo/thumbnail plein écran */}
        <div className="absolute inset-0 overflow-hidden">
          {youtubeId ? (
            <>
              {!ytPlaying ? (
                <>
                  <img
                    src={`https://img.youtube.com/vi/${youtubeId}/0.jpg`}
                    alt={displayName}
                    className="absolute inset-0 w-full h-full object-cover"
                    style={{ filter: 'brightness(0.85)' }}
                    onError={(e) => { e.target.src = `https://img.youtube.com/vi/${youtubeId}/hqdefault.jpg`; }}
                  />
                  <div className="absolute inset-0 flex items-center justify-center cursor-pointer"
                    onClick={() => setYtPlaying(true)}>
                    <div className="w-20 h-20 rounded-full flex items-center justify-center transition-transform hover:scale-110"
                      style={{
                        background: 'rgba(217, 28, 210, 0.85)',
                        boxShadow: '0 0 30px rgba(217, 28, 210, 0.6), 0 0 60px rgba(217, 28, 210, 0.3)',
                        backdropFilter: 'blur(4px)'
                      }}>
                      <svg width="36" height="36" viewBox="0 0 24 24" fill="white">
                        <polygon points="6 3 20 12 6 21 6 3" />
                      </svg>
                    </div>
                  </div>
                  <div className="absolute top-4 left-4 px-3 py-1 rounded-full text-xs font-bold text-white"
                    style={{ background: 'rgba(255, 0, 0, 0.8)' }}>
                    Shorts
                  </div>
                </>
              ) : (
                <iframe
                  className="absolute"
                  src={`https://www.youtube.com/embed/${youtubeId}?autoplay=1&mute=1&loop=1&playlist=${youtubeId}&controls=1&showinfo=0&rel=0&modestbranding=1&playsinline=1`}
                  title={displayName}
                  frameBorder="0"
                  allow="autoplay; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                  style={{
                    pointerEvents: 'auto', position: 'absolute',
                    top: '50%', left: '50%',
                    width: '56.25vh', height: '100vh',
                    minWidth: '100%', minHeight: '177.78vw',
                    transform: 'translate(-50%, -50%)'
                  }}
                  onError={() => setYtPlaying(false)}
                />
              )}
            </>
          ) : heroVideoUrl && heroVideoUrl.match(/\.(mp4|webm|mov)$/i) ? (
            <video autoPlay muted loop playsInline className="absolute inset-0 w-full h-full object-cover"
              style={{ filter: 'brightness(0.7)' }}>
              <source src={heroVideoUrl} type="video/mp4" />
            </video>
          ) : (
            <div className="absolute inset-0"
              style={{ background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.5) 0%, rgba(217, 28, 210, 0.4) 100%)' }}>
              <div className="absolute inset-0 flex items-center justify-center"
                style={{ background: 'radial-gradient(circle at 50% 50%, rgba(217, 28, 210, 0.3) 0%, transparent 70%)' }}>
                <span className="text-5xl opacity-70">🎬</span>
              </div>
            </div>
          )}
        </div>

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

          {/* v14: QR + Partage FIXES en haut à droite */}
          <div className="flex items-center gap-2">
            <button onClick={() => setShowQR(true)}
              className="w-10 h-10 rounded-full flex items-center justify-center transition-all hover:scale-110"
              style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(8px)' }}>
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h2M4 12h2m14 0h2M6 20h2m-2-8h2" />
              </svg>
            </button>
            <button onClick={handleShare}
              className="w-10 h-10 rounded-full flex items-center justify-center transition-all hover:scale-110"
              style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(8px)' }}>
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
              </svg>
            </button>
          </div>
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
              style={{ background: 'rgba(217, 28, 210, 0.7)', boxShadow: '0 0 15px rgba(217, 28, 210, 0.5)' }}>
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
            <h2 className="font-semibold mb-4 text-white" style={{ fontSize: '18px' }}>
              Choisissez votre session
            </h2>
            <div className="space-y-4 sessions-scrollbar"
              style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '8px' }}>
              {uniqueCourses.map(course => {
                const upcomingDates = course.weekday !== undefined ? getNextOccurrences(course.weekday, 4) : [];
                const isSelected = selectedBooking?.course?.id === course.id;
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
                            const isDateSelected = selectedBooking?.course?.id === course.id &&
                              selectedBooking?.date?.toISOString() === date.toISOString();
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
                  setSelectedBooking(null);
                  setSelectedOffer(null);
                }}
                  className="px-6 py-3 rounded-xl text-white font-medium transition-all hover:scale-105"
                  style={{ background: 'linear-gradient(135deg, #8b5cf6 0%, #d91cd2 100%)' }}>
                  Nouvelle réservation
                </button>
              </div>
            ) : (
              <>
                <h3 className="text-lg font-bold text-white mb-4">Finaliser votre réservation</h3>

                {/* Récapitulatif */}
                <div className="rounded-lg p-4 mb-6"
                  style={{ background: 'rgba(217, 28, 210, 0.1)', border: '1px solid rgba(217, 28, 210, 0.2)' }}>
                  <p className="text-white font-semibold">{selectedBooking.course.name || selectedBooking.course.title}</p>
                  <p className="text-purple-400 text-sm mt-1">
                    {selectedBooking.date.toLocaleDateString('fr-CH', { weekday: 'long', day: '2-digit', month: 'long' })}
                    {' • '}{selectedBooking.course.time}
                  </p>
                  <p className="text-white/60 text-sm mt-2">
                    Offre : <span className="text-white">{selectedOffer.name}</span> — <span style={{ color: '#d91cd2' }}>{selectedOffer.price === 0 ? 'Offert' : `CHF ${selectedOffer.price}.-`}</span>
                  </p>
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

                  {/* Code Promo */}
                  <div>
                    <label className="text-white/60 text-xs mb-1 block">Code Promo (optionnel)</label>
                    <div className="flex gap-2">
                      <input type="text" value={bookingForm.promoCode}
                        onChange={e => setBookingForm(prev => ({ ...prev, promoCode: e.target.value.toUpperCase() }))}
                        className="flex-1 px-4 py-3 rounded-lg text-white"
                        style={{
                          background: appliedDiscount ? 'rgba(34, 197, 94, 0.15)' : 'rgba(255,255,255,0.08)',
                          border: appliedDiscount ? '1px solid rgba(34, 197, 94, 0.5)' : '1px solid rgba(255,255,255,0.15)'
                        }}
                        placeholder="CODE123" />
                      <button type="button" onClick={() => validatePromoCode(bookingForm.promoCode)}
                        className="px-4 py-3 rounded-lg font-medium transition-all hover:scale-105"
                        style={{ background: 'rgba(217, 28, 210, 0.3)', border: '1px solid rgba(217, 28, 210, 0.5)', color: '#D91CD2' }}>
                        Valider
                      </button>
                    </div>
                    {promoMessage.text && (
                      <p className={`mt-2 text-sm font-medium ${promoMessage.type === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                        {promoMessage.text}
                      </p>
                    )}
                  </div>

                  {/* Résumé prix */}
                  <div className="rounded-lg p-3"
                    style={{ background: 'rgba(139, 92, 246, 0.1)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
                    <div className="flex justify-between text-sm text-white/70">
                      <span>{selectedOffer.name}</span>
                      <span>{selectedOffer.price?.toFixed(2) || '0.00'} CHF</span>
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

                  {/* Liens paiement */}
                  {(paymentConfig.stripe || paymentConfig.twint || paymentConfig.paypal) && (
                    <div className="py-2">
                      <div className="flex flex-wrap gap-2 justify-center">
                        {paymentConfig.stripe && (
                          <a href={paymentConfig.stripe} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs"
                            style={{ background: 'rgba(99, 91, 255, 0.2)', color: '#A5B4FC', border: '1px solid rgba(99, 91, 255, 0.3)' }}>
                            Stripe
                          </a>
                        )}
                        {paymentConfig.twint && (
                          <a href={paymentConfig.twint} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs"
                            style={{ background: 'rgba(255,255,255,0.1)', color: '#E5E7EB', border: '1px solid rgba(255,255,255,0.2)' }}>
                            TWINT
                          </a>
                        )}
                        {paymentConfig.paypal && (
                          <a href={paymentConfig.paypal} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs"
                            style={{ background: 'rgba(0, 112, 186, 0.2)', color: '#93C5FD', border: '1px solid rgba(0, 112, 186, 0.3)' }}>
                            PayPal
                          </a>
                        )}
                      </div>
                    </div>
                  )}

                  {!paymentConfig.stripe && !paymentConfig.twint && !paymentConfig.paypal && (
                    <div className="text-center text-white/40 text-xs py-2">
                      Réservez d'abord, le paiement sera confirmé par le coach
                    </div>
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

        {/* v16: Section Témoignages dans vitrine */}
        <div className="mb-8 vitrine-fade-in" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '24px' }}>
          <h2 className="font-semibold text-white text-center mb-4" style={{ fontSize: '16px' }}>
            Avis clients
          </h2>
          <div className="space-y-3">
            <div className="rounded-xl p-4" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="flex items-center gap-1 mb-1.5">
                {[1,2,3,4,5].map(i => (
                  <svg key={i} width="12" height="12" viewBox="0 0 24 24" fill="#D91CD2" stroke="none">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                  </svg>
                ))}
              </div>
              <p className="text-white/70 text-xs leading-relaxed italic">"Super expérience, le coach est top !"</p>
              <p className="text-white/40 text-xs mt-1">— Client vérifié</p>
            </div>
          </div>
        </div>

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

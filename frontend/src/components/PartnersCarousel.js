/**
 * PartnersCarousel - Flux vertical Reels v31 FUSION ACCUEIL = VITRINE
 * - Logo Afroboost en haut au centre (position absolue)
 * - Icône recherche en haut à droite
 * - 1 Clic = Play/Pause, Double-clic = Vitrine
 * - v31: Carousel multi-slots heroVideos avec auto-rotation (miroir CoachVitrine)
 * - Lazy loading optimisé (vidéos chargent quand visibles)
 * - Event listeners nettoyés pour éviter conflits
 */
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// v9.5.3: Vidéo par défaut Afroboost - Afrobeat Dance Workout (vidéo populaire 2025)
const DEFAULT_VIDEO_URL = "https://www.youtube.com/watch?v=9ZvW8wnWcxE";

// Logo Afroboost SVG compact
const AfroboostLogo = () => (
  <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
    <defs>
      <linearGradient id="logoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="var(--primary-color, #D91CD2)" />
        <stop offset="100%" stopColor="var(--secondary-color, #8b5cf6)" />
      </linearGradient>
    </defs>
    <circle cx="20" cy="20" r="18" stroke="url(#logoGrad)" strokeWidth="2.5" fill="none" />
    <path d="M20 10 L26 28 H14 L20 10Z" fill="url(#logoGrad)" />
    <circle cx="20" cy="18" r="4" fill="url(#logoGrad)" />
  </svg>
);

// Icône Recherche
const SearchIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" />
    <path d="m21 21-4.35-4.35" />
  </svg>
);

// Icône Coeur pour Like
const HeartIcon = ({ filled }) => (
  <svg 
    width="20" 
    height="20" 
    viewBox="0 0 24 24" 
    fill={filled ? "currentColor" : "none"} 
    stroke="currentColor" 
    strokeWidth="2" 
    strokeLinecap="round" 
    strokeLinejoin="round"
  >
    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
  </svg>
);

// Icône Son discrète
const SoundIcon = ({ muted }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {muted ? (
      <>
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <line x1="23" y1="9" x2="17" y2="15" />
        <line x1="17" y1="9" x2="23" y2="15" />
      </>
    ) : (
      <>
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
        <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
      </>
    )}
  </svg>
);

// Icône Calendrier compact
const CalendarIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </svg>
);

// === UTILITAIRES VIDEO ===
const getYoutubeId = (url) => {
  if (!url) return null;
  const match = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|v\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  return match ? match[1] : null;
};

const getVimeoId = (url) => {
  if (!url) return null;
  const match = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
  return match ? match[1] : null;
};

const isDirectVideoFile = (url) => {
  if (!url) return false;
  return /\.(mp4|webm|mov|avi|m4v)(\?|$)/i.test(url) || (url.includes('/api/files/') && url.includes('/video_'));
};

// v29: Détection images uploadées via /api/files/
const isDirectImageFile = (url) => {
  if (!url) return false;
  return /\.(jpg|jpeg|png|webp|gif|svg|bmp)(\?|$)/i.test(url) || (url.includes('/api/files/') && url.includes('/image_'));
};

// v31: Détection STRICTE du type de média (copié de CoachVitrine)
const detectHeroMediaType = (video) => {
  if (!video || !video.url) return 'unknown';
  const url = video.url.toLowerCase();
  if (url.includes('youtube.com') || url.includes('youtu.be')) return 'youtube';
  if (url.includes('vimeo.com')) return 'vimeo';
  if (url.match(/\.(jpg|jpeg|png|webp|gif|svg|bmp)(\?|$)/i) || video.type === 'image' || url.includes('/image_')) return 'image';
  if (url.match(/\.(mp4|webm|mov|avi|mkv)(\?|$)/i) || video.type === 'upload' || video.type === 'video' || url.includes('/video_')) return 'video';
  if (url.includes('/api/files/')) return 'video';
  return 'unknown';
};

// v31: Résoudre URL complète pour /api/files/
const resolveHeroUrl = (url, cacheBuster) => {
  if (!url) return '';
  if (url.startsWith('/api/files/')) {
    const base = BACKEND_URL || (typeof window !== 'undefined' ? window.location.origin : '');
    return `${base}${url}?v=${cacheBuster}`;
  }
  return url;
};

// v32: Respecter l'ordre MANUEL défini dans le Dashboard (plus de tri automatique)
// v34: Filtrer les vidéos marquées is_visible: false
const getHeroVideosOrdered = (heroVideos) => {
  if (!heroVideos || heroVideos.length === 0) return [];
  return heroVideos.filter(v => v && v.url && v.is_visible !== false);
};

const getMediaInfo = (videoUrl) => {
  const url = videoUrl || DEFAULT_VIDEO_URL;
  const youtubeId = getYoutubeId(url);
  const vimeoId = getVimeoId(url);
  const isDirectVideo = isDirectVideoFile(url);
  const isDirectImage = isDirectImageFile(url);
  // v29: /api/files/ sans extension reconnue → traiter comme vidéo par défaut
  const isApiFile = url.includes('/api/files/') && !isDirectImage;

  return {
    url,
    youtubeId,
    vimeoId,
    isDirectVideo: isDirectVideo || isApiFile,
    isDirectImage,
    hasValidMedia: !!(youtubeId || vimeoId || isDirectVideo || isDirectImage || isApiFile),
    isFallback: !videoUrl || (!youtubeId && !vimeoId && !isDirectVideo && !isDirectImage && !isApiFile)
  };
};

// === COMPOSANT VIDEO CARD v9.5.7 avec mode maintenance ===
// v11.7: Ajout isSuperAdminVideo pour désactiver double-clic
// v34: Ajout preview 30s + overlay achat pour vidéos premium
const PartnerVideoCard = ({ partner, onToggleMute, isMuted, onLike, isLiked, onNavigate, isPaused, onTogglePause, isVisible, maintenanceMode = false, isSuperAdmin = false, onBuyVideo, socialCommentsCount = 0, onShowComments, pageLikesCount = 0, likeAnimating = false }) => {
  const videoRef = useRef(null);
  const [hasError, setHasError] = useState(false);
  const [ytPlaying, setYtPlaying] = useState(false);
  const lastClickTime = useRef(0);
  const clickCount = useRef(0);
  const clickTimer = useRef(null);

  // v31: Carousel multi-slots — utiliser TOUS les heroVideos (pas juste [0])
  const [activeHeroIdx, setActiveHeroIdx] = useState(0);
  const [cacheBusterTs] = useState(() => Date.now());

  // v34: Preview 30s — overlay achat pour vidéos premium
  const [showPreviewOverlay, setShowPreviewOverlay] = useState(false);
  const ytTimerRef = useRef(null);
  const PREVIEW_DURATION = 30; // secondes

  // v32: Utiliser l'ordre de la BDD tel quel (pas de tri automatique)
  const heroVideosSorted = useMemo(() => getHeroVideosOrdered(partner.heroVideos || []), [partner.heroVideos]);
  const heroSlidesCount = heroVideosSorted.length;

  // v31: Auto-rotation toutes les 8s quand il y a plusieurs slots
  useEffect(() => {
    if (heroSlidesCount <= 1 || !isVisible) return;
    const timer = setInterval(() => {
      setActiveHeroIdx(prev => (prev + 1) % heroSlidesCount);
    }, 8000);
    return () => clearInterval(timer);
  }, [heroSlidesCount, isVisible]);

  // v31: Résoudre le média courant du carousel
  const currentHero = heroVideosSorted[activeHeroIdx] || heroVideosSorted[0] || null;
  const currentHeroType = detectHeroMediaType(currentHero);
  const currentHeroUrl = resolveHeroUrl(currentHero?.url || '', cacheBusterTs);
  const currentYoutubeId = getYoutubeId(currentHeroUrl);

  // v34: Vérifier si la vidéo courante est premium (a un prix > 0)
  const currentHeroPrice = currentHero?.price || 0;
  const isCurrentHeroPremium = currentHeroPrice > 0;

  // v34: Handler timeupdate pour vidéos <video> — bloque à 30s si premium
  const handleVideoTimeUpdate = useCallback((e) => {
    if (!isCurrentHeroPremium) return;
    if (e.target.currentTime >= PREVIEW_DURATION) {
      e.target.pause();
      e.target.currentTime = 0;
      setShowPreviewOverlay(true);
      console.log('[V34-PREVIEW] ⏱️ Limite 30s atteinte, overlay affiché');
    }
  }, [isCurrentHeroPremium]);

  // v34: Timer YouTube — bloque après 30s si premium
  useEffect(() => {
    if (ytTimerRef.current) { clearTimeout(ytTimerRef.current); ytTimerRef.current = null; }
    if (ytPlaying && isCurrentHeroPremium) {
      ytTimerRef.current = setTimeout(() => {
        setYtPlaying(false);
        setShowPreviewOverlay(true);
        console.log('[V34-PREVIEW] ⏱️ YouTube: limite 30s atteinte');
      }, PREVIEW_DURATION * 1000);
    }
    return () => { if (ytTimerRef.current) clearTimeout(ytTimerRef.current); };
  }, [ytPlaying, isCurrentHeroPremium]);

  // v34: Reset overlay quand on change de slot
  useEffect(() => {
    setShowPreviewOverlay(false);
  }, [activeHeroIdx]);

  // Fallback: si pas de heroVideos, utiliser l'ancien système mono-média
  const heroVideosArr = partner.heroVideos || [];
  const firstHeroUrl = heroVideosArr.length > 0 && heroVideosArr[0]?.url ? heroVideosArr[0].url : '';
  const videoUrl = firstHeroUrl || partner.video_url || partner.heroImageUrl;
  const mediaInfo = useMemo(() => getMediaInfo(videoUrl), [videoUrl]);
  const activeMedia = hasError ? getMediaInfo(DEFAULT_VIDEO_URL) : mediaInfo;

  // v31: Décider quel système de rendu utiliser
  const useMultiSlotCarousel = heroSlidesCount > 0;
  
  const initial = (partner.name || partner.platform_name || 'P').charAt(0).toUpperCase();
  const displayName = partner.platform_name || partner.name || 'Partenaire';
  const bio = partner.bio || partner.description || '';
  
  // v9.5.7: QUICK CONTROL - Bloquer actions si maintenance ON (sauf Super Admin)
  const isBlocked = maintenanceMode && !isSuperAdmin;
  
  // v11.7: Identifier si cette vidéo appartient au Super Admin (pas de double-clic)
  const SUPER_ADMIN_EMAILS = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
  const partnerEmail = (partner.email || '').toLowerCase().trim();
  const isSuperAdminVideo = SUPER_ADMIN_EMAILS.some(email => email.toLowerCase() === partnerEmail);

  // v9.5.2: Nettoyage des event listeners
  useEffect(() => {
    return () => {
      if (clickTimer.current) {
        clearTimeout(clickTimer.current);
      }
    };
  }, []);

  // v9.5.7: Gestion améliorée clic simple vs double-clic (avec blocage maintenance)
  // v11.7: Double-clic DÉSACTIVÉ sur vidéos Super Admin
  const handleVideoClick = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    
    // v9.5.7: QUICK CONTROL - Bloquer double-clic si maintenance
    if (isBlocked) {
      console.log('[MAINTENANCE] Interaction bloquée');
      return;
    }
    
    clickCount.current += 1;
    
    if (clickTimer.current) {
      clearTimeout(clickTimer.current);
    }
    
    clickTimer.current = setTimeout(() => {
      if (clickCount.current === 1) {
        // Simple clic -> Play/Pause
        onTogglePause();
      } else if (clickCount.current >= 2) {
        // v11.7: Double-clic -> Navigation vitrine UNIQUEMENT si PAS Super Admin
        if (isSuperAdminVideo) {
          console.log('[SUPER-ADMIN] Double-clic désactivé sur vidéo Super Admin');
          onTogglePause(); // Juste play/pause à la place
        } else {
          onNavigate(partner);
        }
      }
      clickCount.current = 0;
    }, 250);
  }, [onNavigate, onTogglePause, partner, isSuperAdminVideo, isBlocked]);

  // v9.5.7: handleReserve avec blocage maintenance
  // v11.8: Pour SA, scroll vers offres au lieu de naviguer
  const handleReserve = (e) => {
    e.stopPropagation();
    if (isBlocked) {
      console.log('[MAINTENANCE] Réservation bloquée');
      return;
    }
    
    // v11.8: Si vidéo Super Admin, scroll vers les offres de la page actuelle
    if (isSuperAdminVideo) {
      console.log('[SUPER-ADMIN] Scroll vers section offres (pas de navigation)');
      // Chercher les sections offres/sessions dans la page actuelle
      const offersSection = document.getElementById('sessions-section') || 
                           document.getElementById('offers-section') ||
                           document.getElementById('courses-section');
      if (offersSection) {
        offersSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        console.log('[SUPER-ADMIN] ✅ Scroll effectué vers', offersSection.id);
      } else {
        console.log('[SUPER-ADMIN] ❌ Aucune section offres trouvée');
        // Fallback: appeler onNavigate qui ne fera rien pour SA (grâce au check v11.7)
        onNavigate(partner);
      }
      return;
    }
    
    // Pour les autres partenaires, navigation normale vers leur vitrine
    onNavigate(partner);
  };

  // v9.5.2: LAZY LOADING - Ne charger la vidéo que si visible
  const shouldLoadVideo = isVisible;

  return (
    <div 
      className="snap-start snap-always w-full flex-shrink-0 relative"
      style={{ 
        height: '100%',
        background: '#000000'
      }}
      data-testid={`partner-card-${partner.id || partner.email}`}
    >
      {/* v10.0: STYLE INSTAGRAM REELS - ZÉRO VIDE - Vidéo plein écran */}
      <div 
        className="absolute inset-0"
        style={{ paddingTop: '0px' }}
      >
        {/* === v10.2: VIDÉO PLEIN ÉCRAN - ZÉRO VIDE - object-fit: cover === */}
        <div 
          className="absolute inset-0 overflow-hidden cursor-pointer"
          style={{ borderRadius: '0px' }}
          onClick={handleVideoClick}
        >
          {shouldLoadVideo ? (
            <>
              {/* === v31: MULTI-SLOT HERO CAROUSEL === */}
              {useMultiSlotCarousel ? (
                <div className="absolute inset-0">
                  {/* Rendu du média courant */}
                  {currentHeroType === 'image' ? (
                    <img
                      key={`hero-img-${activeHeroIdx}`}
                      src={currentHeroUrl}
                      alt={displayName}
                      className="absolute inset-0 w-full h-full object-cover"
                      style={{ filter: 'brightness(0.75)' }}
                      onError={() => setActiveHeroIdx(prev => (prev + 1) % heroSlidesCount)}
                    />
                  ) : currentHeroType === 'video' ? (
                    <div className="absolute inset-0" key={`hero-vid-wrap-${activeHeroIdx}`}>
                      {/* v31: Gradient fallback visible par défaut */}
                      <div id={`hero-fb-${activeHeroIdx}`} className="absolute inset-0" style={{
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
                        key={`hero-vid-${activeHeroIdx}`}
                        autoPlay muted loop={!isCurrentHeroPremium} playsInline preload="auto"
                        className="absolute inset-0 w-full h-full object-cover"
                        style={{ filter: 'brightness(0.7)', zIndex: 1 }}
                        onTimeUpdate={handleVideoTimeUpdate}
                        ref={(el) => {
                          if (el) {
                            el.setAttribute('webkit-playsinline', 'true');
                            el.setAttribute('x5-video-player-type', 'h5');
                            if (el.src !== currentHeroUrl) { el.src = currentHeroUrl; el.load(); }
                            const tryPlay = (attempt) => {
                              if (attempt > 8) return;
                              setTimeout(() => {
                                if (el.paused && el.readyState >= 2) {
                                  el.muted = true;
                                  el.play().then(() => {
                                    const fb = document.getElementById(`hero-fb-${activeHeroIdx}`);
                                    if (fb) { fb.style.opacity = '0'; fb.style.pointerEvents = 'none'; }
                                  }).catch(() => tryPlay(attempt + 1));
                                } else if (el.paused) { tryPlay(attempt + 1); }
                              }, attempt * 300);
                            };
                            tryPlay(0);
                          }
                        }}
                        onCanPlay={(e) => {
                          if (e.target.paused) { e.target.muted = true; e.target.play().catch(() => {}); }
                          const fb = document.getElementById(`hero-fb-${activeHeroIdx}`);
                          if (fb) { fb.style.opacity = '0'; fb.style.pointerEvents = 'none'; }
                        }}
                        onError={() => console.error('[V31] Video error slot', activeHeroIdx)}
                      />
                    </div>
                  ) : currentHeroType === 'youtube' && currentYoutubeId ? (
                    <div className="absolute inset-0 overflow-hidden">
                      {!ytPlaying ? (
                        <>
                          <img
                            src={`https://img.youtube.com/vi/${currentYoutubeId}/0.jpg`}
                            alt={displayName}
                            className="absolute inset-0 w-full h-full object-cover"
                            style={{ filter: 'brightness(0.85)' }}
                            onError={(e) => { e.target.src = `https://img.youtube.com/vi/${currentYoutubeId}/hqdefault.jpg`; }}
                          />
                          <div
                            className="absolute inset-0 flex items-center justify-center cursor-pointer"
                            onClick={(e) => { e.stopPropagation(); setYtPlaying(true); }}
                          >
                            <div
                              className="w-20 h-20 rounded-full flex items-center justify-center transition-transform hover:scale-110"
                              style={{
                                background: 'rgba(217, 28, 210, 0.85)',
                                boxShadow: '0 0 30px rgba(217, 28, 210, 0.6), 0 0 60px rgba(217, 28, 210, 0.3)',
                                backdropFilter: 'blur(4px)'
                              }}
                            >
                              <svg width="36" height="36" viewBox="0 0 24 24" fill="white">
                                <polygon points="6 3 20 12 6 21 6 3" />
                              </svg>
                            </div>
                          </div>
                        </>
                      ) : (
                        <iframe
                          className="absolute"
                          src={`https://www.youtube.com/embed/${currentYoutubeId}?autoplay=1&mute=1&loop=1&playlist=${currentYoutubeId}&controls=1&showinfo=0&rel=0&modestbranding=1&playsinline=1`}
                          title={displayName}
                          frameBorder="0"
                          allow="autoplay; encrypted-media; gyroscope; picture-in-picture"
                          allowFullScreen
                          style={{
                            pointerEvents: 'auto',
                            position: 'absolute', top: '50%', left: '50%',
                            width: '56.25vh', height: '100vh',
                            minWidth: '100%', minHeight: '177.78vw',
                            transform: 'translate(-50%, -50%)'
                          }}
                          onError={() => setYtPlaying(false)}
                        />
                      )}
                    </div>
                  ) : (
                    /* Fallback: gradient avec nom du coach */
                    <div className="absolute inset-0" style={{
                      background: 'linear-gradient(180deg, #0a0a1a 0%, #1a0a2e 50%, #0a0a1a 100%)'
                    }}>
                      <div className="absolute inset-0 flex flex-col items-center justify-center px-8 text-center">
                        <div className="w-24 h-24 rounded-full flex items-center justify-center text-3xl font-bold mb-4"
                          style={{ background: 'linear-gradient(135deg, #D91CD2 0%, #8b5cf6 100%)', color: 'white' }}
                        >{initial}</div>
                        <h2 className="text-white text-2xl font-bold mb-2">{displayName}</h2>
                      </div>
                    </div>
                  )}

                  {/* v31: Dots navigation */}
                  {heroSlidesCount > 1 && (
                    <div className="absolute bottom-20 left-0 right-0 flex justify-center items-center gap-2 z-10">
                      {heroVideosSorted.map((_, idx) => (
                        <div
                          key={idx}
                          onClick={(e) => { e.stopPropagation(); setActiveHeroIdx(idx); setYtPlaying(false); }}
                          style={{
                            width: activeHeroIdx === idx ? '24px' : '10px', height: '10px',
                            borderRadius: '5px', cursor: 'pointer',
                            background: activeHeroIdx === idx ? '#D91CD2' : 'rgba(255,255,255,0.4)',
                            boxShadow: activeHeroIdx === idx ? '0 0 10px rgba(217,28,210,0.6)' : 'none',
                            transition: 'all 0.3s ease'
                          }}
                        />
                      ))}
                    </div>
                  )}

                  {/* v34: Badge prix si vidéo premium */}
                  {isCurrentHeroPremium && !showPreviewOverlay && (
                    <div className="absolute top-16 right-3 z-10" style={{
                      background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                      padding: '4px 12px', borderRadius: '20px',
                      boxShadow: '0 0 15px rgba(217,28,210,0.4)',
                      fontSize: '12px', fontWeight: 700, color: '#fff'
                    }}>
                      💎 {currentHeroPrice} CHF
                    </div>
                  )}

                  {/* v34: Overlay achat — affiché après 30s de preview */}
                  {showPreviewOverlay && isCurrentHeroPremium && (
                    <div className="absolute inset-0 z-20 flex flex-col items-center justify-center"
                      onClick={(e) => e.stopPropagation()}
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
                      <h3 style={{ color: '#fff', fontSize: '20px', fontWeight: 700, marginBottom: '8px', textAlign: 'center' }}>
                        Aperçu terminé
                      </h3>
                      <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '14px', marginBottom: '20px', textAlign: 'center', maxWidth: '280px' }}>
                        {currentHero?.description || 'Achetez la version complète pour continuer la lecture'}
                      </p>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          console.log('[V34-PREVIEW] Clic achat vidéo:', currentHero?.title || 'Vidéo', currentHeroPrice, 'CHF');
                          if (onBuyVideo) onBuyVideo({
                            name: currentHero?.title || `Vidéo ${displayName}`,
                            price: currentHeroPrice,
                            id: currentHero?.id || `hero-${activeHeroIdx}`,
                            type: 'video',
                            thumbnail: currentHero?.thumbnail || ''
                          });
                        }}
                        style={{
                          background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                          color: '#fff', border: 'none', padding: '14px 32px',
                          borderRadius: '30px', fontSize: '16px', fontWeight: 700,
                          cursor: 'pointer', boxShadow: '0 0 25px rgba(217,28,210,0.5)',
                          transition: 'transform 0.2s ease'
                        }}
                        onMouseOver={(e) => e.target.style.transform = 'scale(1.05)'}
                        onMouseOut={(e) => e.target.style.transform = 'scale(1)'}
                      >
                        Acheter — {currentHeroPrice} CHF
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setShowPreviewOverlay(false); }}
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
                </div>
              ) : activeMedia.youtubeId ? (
                <div className="absolute inset-0 overflow-hidden">
                  {/* v12: YouTube Lite Facade - Thumbnail d'abord, iframe au clic */}
                  {!ytPlaying ? (
                    <>
                      {/* Thumbnail YouTube haute qualité */}
                      <img
                        src={`https://img.youtube.com/vi/${activeMedia.youtubeId}/0.jpg`}
                        alt={displayName}
                        className="absolute inset-0 w-full h-full object-cover"
                        style={{ filter: 'brightness(0.85)' }}
                        onError={(e) => {
                          e.target.src = `https://img.youtube.com/vi/${activeMedia.youtubeId}/hqdefault.jpg`;
                        }}
                      />
                      {/* Bouton Play central */}
                      <div
                        className="absolute inset-0 flex items-center justify-center cursor-pointer"
                        onClick={(e) => {
                          e.stopPropagation();
                          setYtPlaying(true);
                        }}
                      >
                        <div
                          className="w-20 h-20 rounded-full flex items-center justify-center transition-transform hover:scale-110"
                          style={{
                            background: 'rgba(217, 28, 210, 0.85)',
                            boxShadow: '0 0 30px rgba(217, 28, 210, 0.6), 0 0 60px rgba(217, 28, 210, 0.3)',
                            backdropFilter: 'blur(4px)'
                          }}
                        >
                          <svg width="36" height="36" viewBox="0 0 24 24" fill="white">
                            <polygon points="6 3 20 12 6 21 6 3" />
                          </svg>
                        </div>
                      </div>
                      {/* Badge "Shorts" */}
                      <div
                        className="absolute top-4 left-4 px-3 py-1 rounded-full text-xs font-bold text-white"
                        style={{ background: 'rgba(255, 0, 0, 0.8)' }}
                      >
                        Shorts
                      </div>
                    </>
                  ) : (
                    <iframe
                      className="absolute"
                      src={`https://www.youtube.com/embed/${activeMedia.youtubeId}?autoplay=1&mute=1&loop=1&playlist=${activeMedia.youtubeId}&controls=1&showinfo=0&rel=0&modestbranding=1&playsinline=1`}
                      title={displayName}
                      frameBorder="0"
                      allow="autoplay; encrypted-media; gyroscope; picture-in-picture"
                      allowFullScreen
                      style={{
                        pointerEvents: 'auto',
                        position: 'absolute',
                        top: '50%',
                        left: '50%',
                        width: '56.25vh',
                        height: '100vh',
                        minWidth: '100%',
                        minHeight: '177.78vw',
                        transform: 'translate(-50%, -50%)'
                      }}
                      onError={() => { setHasError(true); setYtPlaying(false); }}
                    />
                  )}
                </div>
              ) : activeMedia.vimeoId ? (
                <div className="absolute inset-0 overflow-hidden">
                  <iframe
                    className="absolute"
                    src={`https://player.vimeo.com/video/${activeMedia.vimeoId}?autoplay=${isPaused ? 0 : 1}&muted=${isMuted ? 1 : 0}&loop=1&background=1`}
                    title={displayName}
                    frameBorder="0"
                    allow="autoplay"
                    style={{
                      pointerEvents: 'none',
                      position: 'absolute',
                      top: '50%',
                      left: '50%',
                      width: '56.25vh',
                      height: '100vh',
                      minWidth: '100%',
                      minHeight: '177.78vw',
                      transform: 'translate(-50%, -50%)'
                    }}
                    onError={() => setHasError(true)}
                  />
                </div>
              ) : activeMedia.isDirectImage ? (
                /* v29: IMAGE uploadée — afficher en plein écran */
                <img
                  src={activeMedia.url.startsWith('/api/') ? `${BACKEND_URL || (typeof window !== 'undefined' ? window.location.origin : '')}${activeMedia.url}` : activeMedia.url}
                  alt={displayName}
                  className="absolute inset-0 w-full h-full object-cover"
                  style={{ filter: 'brightness(0.75)' }}
                  onError={() => setHasError(true)}
                />
              ) : activeMedia.isDirectVideo ? (
                <video
                  ref={(el) => {
                    videoRef.current = el;
                    if (el) {
                      el.setAttribute('webkit-playsinline', 'true');
                      el.setAttribute('x5-video-player-type', 'h5');
                      el.setAttribute('x5-video-player-fullscreen', 'false');
                      // v29.2: Force autoplay après montage DOM (Samsung Ultra 24 fix)
                      setTimeout(() => {
                        if (el.paused && !isPaused) {
                          el.muted = true;
                          el.play().catch(() => {});
                        }
                      }, 150);
                    }
                  }}
                  autoPlay={true}
                  loop
                  muted={true}
                  playsInline
                  className="absolute inset-0 w-full h-full object-cover"
                  onError={() => setHasError(true)}
                  preload="auto"
                  style={{ filter: 'brightness(0.8)' }}
                  src={activeMedia.url.startsWith('/api/') ? `${BACKEND_URL || (typeof window !== 'undefined' ? window.location.origin : '')}${activeMedia.url}` : activeMedia.url}
                  onCanPlay={(e) => {
                    if (e.target.paused && !isPaused) {
                      e.target.muted = true;
                      e.target.play().catch(() => {});
                    }
                  }}
                  onLoadedData={(e) => {
                    console.log('[CAROUSEL-MEDIA] ✅ Vidéo chargée:', activeMedia.url);
                    if (e.target.paused && !isPaused) {
                      e.target.muted = true;
                      e.target.play().catch(() => {});
                    }
                  }}
                />
              ) : (
                <div
                  className="absolute inset-0"
                  style={{
                    background: 'linear-gradient(180deg, #0a0a1a 0%, #1a0a2e 50%, #0a0a1a 100%)'
                  }}
                >
                  {/* Fallback hero: Avatar + Nom + Accroche */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center px-8 text-center">
                    {/* Avatar large */}
                    <div
                      className="w-24 h-24 rounded-full flex items-center justify-center text-3xl font-bold mb-4"
                      style={{
                        background: 'linear-gradient(135deg, #D91CD2 0%, #8b5cf6 100%)',
                        color: 'white',
                        boxShadow: '0 0 40px rgba(217, 28, 210, 0.5)'
                      }}
                    >
                      {initial}
                    </div>
                    {/* Nom du coach */}
                    <h2 className="text-white text-2xl font-bold mb-2" style={{ textShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>
                      {displayName}
                    </h2>
                    {/* Bio ou accroche */}
                    <p className="text-white/70 text-sm max-w-xs">
                      {bio || 'Découvrez nos cours et réservez votre prochaine session'}
                    </p>
                    {/* Bouton CTA */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isBlocked) onNavigate(partner);
                      }}
                      className="mt-6 px-6 py-2.5 rounded-full text-white text-sm font-medium transition-all hover:scale-105"
                      style={{
                        background: 'linear-gradient(135deg, #D91CD2, #8b5cf6)',
                        boxShadow: '0 4px 20px rgba(217, 28, 210, 0.4)'
                      }}
                    >
                      Voir le profil
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* Placeholder pendant que non visible (lazy loading) */
            <div 
              className="absolute inset-0 flex items-center justify-center"
              style={{ background: 'rgba(20, 10, 30, 0.8)' }}
            >
              <div className="animate-pulse w-16 h-16 rounded-full" style={{ background: 'rgba(217, 28, 210, 0.3)' }}></div>
            </div>
          )}
          
          {/* Indicateur Pause au centre */}
          {isPaused && shouldLoadVideo && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/30 transition-opacity">
              <div 
                className="w-16 h-16 rounded-full flex items-center justify-center"
                style={{ background: 'rgba(255,255,255,0.2)', backdropFilter: 'blur(8px)' }}
              >
                <svg width="32" height="32" viewBox="0 0 24 24" fill="white">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              </div>
            </div>
          )}
        </div>
        
        {/* v10.0: Gradient overlay bas pour lisibilité */}
        <div 
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 25%, transparent 50%)'
          }}
        />
        
        {/* === v10.0: BARRE D'ACTIONS STYLE INSTAGRAM - DROITE === */}
        {/* v94.1: z-10 ajouté — les icônes restent toujours au-dessus de la vidéo et du gradient */}
        <div
          className="absolute right-3 bottom-28 flex flex-col items-center gap-5 z-10"
          data-testid="reels-action-bar"
        >
          {/* v75: Bouton Avis/Commentaires — même taille que Like et Réserver */}
          {socialCommentsCount > 0 && onShowComments && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onShowComments();
              }}
              className="flex flex-col items-center transition-all hover:scale-110 active:scale-95"
              data-testid="comments-btn"
            >
              <div
                style={{
                  width: '44px', height: '44px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: '#D91CD2',
                  border: 'none',
                  boxShadow: '0 0 14px rgba(217, 28, 210, 0.6), 0 0 30px rgba(217, 28, 210, 0.3), 0 4px 15px rgba(217, 28, 210, 0.4)'
                }}
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="rgba(255,255,255,0.95)" stroke="white" strokeWidth="0.5">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
              </div>
              <span
                className="text-xs mt-1 font-medium"
                style={{
                  color: '#fff',
                  textShadow: '0 1px 3px rgba(0,0,0,0.8)'
                }}
              >
                {socialCommentsCount}
              </span>
            </button>
          )}

          {/* v80: Bouton Like avec compteur réel + animation */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              onLike();
            }}
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', background: 'none', border: 'none', cursor: 'pointer', padding: 0, transition: 'transform 0.2s ease' }}
            data-testid={`like-btn-${partner.id || partner.email}`}
          >
            <div
              style={{
                width: '44px', height: '44px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: '#D91CD2',
                border: 'none',
                boxShadow: isLiked ? '0 0 20px rgba(217, 28, 210, 0.8), 0 0 40px rgba(217, 28, 210, 0.4), 0 4px 15px rgba(217, 28, 210, 0.4)' : '0 0 14px rgba(217, 28, 210, 0.6), 0 0 30px rgba(217, 28, 210, 0.3), 0 4px 15px rgba(217, 28, 210, 0.4)',
                transform: likeAnimating ? 'scale(1.3)' : 'scale(1)',
                transition: 'all 0.3s ease'
              }}
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill={isLiked ? 'white' : 'none'}
                stroke="white"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{
                  filter: isLiked ? 'drop-shadow(0 0 8px rgba(255,255,255,0.8))' : 'none',
                  transition: 'all 0.3s ease'
                }}
              >
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
            </div>
            <span
              style={{
                fontSize: '12px', fontWeight: 600, marginTop: '4px',
                color: 'white',
                textShadow: '0 1px 3px rgba(0,0,0,0.9)',
                transition: 'all 0.3s ease',
                transform: likeAnimating ? 'scale(1.2)' : 'scale(1)'
              }}
            >
              {pageLikesCount}
            </span>
          </button>
          
          {/* Bouton Réserver */}
          {!isBlocked && (
            <button
              onClick={handleReserve}
              className="flex flex-col items-center transition-all hover:scale-110"
              data-testid={`reserve-btn-${partner.id || partner.email}`}
            >
              <div
                style={{
                  width: '44px', height: '44px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: '#D91CD2',
                  border: 'none',
                  boxShadow: '0 0 14px rgba(217, 28, 210, 0.6), 0 0 30px rgba(217, 28, 210, 0.3), 0 4px 15px rgba(217, 28, 210, 0.4)'
                }}
              >
                <CalendarIcon />
              </div>
              <span className="text-white text-xs mt-1" style={{ textShadow: '0 1px 3px rgba(0,0,0,0.9)' }}>
                Réserver
              </span>
            </button>
          )}
        </div>
        
        {/* === v10.0: BLOC BAS GAUCHE - Photo + Nom + Légende (Style Instagram) === */}
        <div 
          className="absolute bottom-6 left-3 right-20"
          data-testid={`profile-overlay-${partner.id || partner.email}`}
        >
          {/* Photo + Nom */}
          <div className="flex items-center gap-2.5 mb-2">
            <div 
              className="cursor-pointer flex-shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                if (!isBlocked) onNavigate(partner);
              }}
            >
              {partner.photo_url || partner.logo_url ? (
                <img 
                  src={partner.photo_url || partner.logo_url} 
                  alt={displayName}
                  className="w-10 h-10 rounded-full object-cover"
                  style={{ 
                    border: '2px solid white',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
                  }}
                  loading="lazy"
                />
              ) : (
                <div 
                  className="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold"
                  style={{ 
                    background: 'linear-gradient(135deg, var(--primary-color, #D91CD2) 0%, var(--secondary-color, #8b5cf6) 100%)',
                    color: 'white',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
                  }}
                >
                  {initial}
                </div>
              )}
            </div>
            
            <span 
              className="text-white text-sm font-bold cursor-pointer hover:underline"
              style={{ textShadow: '0 1px 3px rgba(0,0,0,0.9)' }}
              onClick={(e) => {
                e.stopPropagation();
                if (!isBlocked) onNavigate(partner);
              }}
            >
              {displayName}
            </span>
          </div>
          
          {/* v15: Bio + Tags spécialité + Lieu */}
          {bio && (
            <p
              className="text-white/90 text-sm leading-snug mb-1.5"
              style={{
                textShadow: '0 1px 2px rgba(0,0,0,0.8)',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden'
              }}
            >
              {bio}
            </p>
          )}
          {/* Lieu du coach */}
          {partner.location && (
            <div className="flex items-center gap-1 mt-1">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="rgba(255,255,255,0.5)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                <circle cx="12" cy="10" r="3" />
              </svg>
              <span className="text-white/50 text-xs" style={{ textShadow: '0 1px 2px rgba(0,0,0,0.8)' }}>
                {partner.location}
              </span>
            </div>
          )}
          {/* Tags spécialités */}
          {partner.specialties && partner.specialties.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {partner.specialties.slice(0, 3).map((tag, i) => (
                <span
                  key={i}
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{
                    background: 'rgba(217, 28, 210, 0.2)',
                    border: '1px solid rgba(217, 28, 210, 0.3)',
                    color: 'rgba(255, 255, 255, 0.8)',
                    textShadow: '0 1px 2px rgba(0,0,0,0.5)'
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// Icône Globe pour sélecteur de langue
const GlobeIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </svg>
);

// === COMPOSANT PRINCIPAL v9.7.2 - Vitrine Unique + Son global unique ===
const PartnersCarousel = ({ onPartnerClick, onSearch, maintenanceMode = false, isSuperAdmin = false, lang = 'fr', onLangChange, currentVitrineEmail = null, onBuyVideo, socialCommentsCount = 0, onShowComments }) => {
  // v9.6.8: État pour sélecteur de langue
  const [showLangMenu, setShowLangMenu] = useState(false);
  const [globalMuted, setGlobalMuted] = useState(true); // Son global muté par défaut
  const [partners, setPartners] = useState([]);
  const [filteredPartners, setFilteredPartners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [mutedStates, setMutedStates] = useState({});
  const [likedStates, setLikedStates] = useState({});
  const [pausedStates, setPausedStates] = useState({});
  // v80: Compteur de likes réel via API
  const [pageLikesCount, setPageLikesCount] = useState(0);
  const [likeAnimating, setLikeAnimating] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showSearch, setShowSearch] = useState(false);
  const sliderRef = useRef(null);
  const scrollTimeout = useRef(null);
  const searchInputRef = useRef(null);
  
  // v9.5.3: Filtrer les partenaires par nom
  useEffect(() => {
    if (searchQuery.trim() === '') {
      setFilteredPartners(partners);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = partners.filter(p => {
        const name = (p.platform_name || p.name || '').toLowerCase();
        const bio = (p.bio || p.description || '').toLowerCase();
        return name.includes(query) || bio.includes(query);
      });
      setFilteredPartners(filtered);
    }
    setActiveIndex(0);
  }, [searchQuery, partners]);
  
  // Restaurer la position de scroll
  useEffect(() => {
    const savedIndex = sessionStorage.getItem('afroboost_flux_index');
    if (savedIndex && partners.length > 0) {
      const idx = parseInt(savedIndex, 10);
      setActiveIndex(idx);
      setTimeout(() => {
        if (sliderRef.current) {
          sliderRef.current.scrollTo({
            top: idx * sliderRef.current.clientHeight,
            behavior: 'auto'
          });
        }
      }, 100);
      sessionStorage.removeItem('afroboost_flux_index');
    }
  }, [partners]);
  
  // Charger les partenaires
  useEffect(() => {
    const fetchPartners = async () => {
      try {
        const res = await axios.get(`${API}/partners/active`);
        const rawData = res.data || [];
        
        // v9.6.6: Déduplication par email (double sécurité)
        const seen = new Set();
        const data = rawData.filter(p => {
          const key = (p.email || p.id || '').toLowerCase();
          if (seen.has(key)) {
            console.warn(`[FLUX-REELS] ⚠️ DOUBLON DÉTECTÉ ET FILTRÉ: ${key}`);
            return false;
          }
          seen.add(key);
          return true;
        });
        
        // v9.6.9: Log détaillé pour debug
        console.log(`[FLUX-REELS] ${rawData.length} partenaires reçus, ${data.length} uniques`);
        if (rawData.length !== data.length) {
          console.warn(`[FLUX-REELS] ❌ ${rawData.length - data.length} doublons supprimés`);
        } else {
          console.log('[FLUX-REELS] ✅ Aucun doublon détecté');
        }
        
        setPartners(data);
        setFilteredPartners(data); // v9.5.3: Initialiser filteredPartners
        
        const initialMuted = {};
        const initialPaused = {};
        data.forEach(p => {
          const pKey = p.id || p.email;
          initialMuted[pKey] = true;
          initialPaused[pKey] = false;
        });
        setMutedStates(initialMuted);
        setPausedStates(initialPaused);
        
        const savedLikes = localStorage.getItem('afroboost_partner_likes');
        if (savedLikes) {
          setLikedStates(JSON.parse(savedLikes));
        }
      } catch (err) {
        console.error('[FLUX-REELS] Erreur:', err);
        setError('Impossible de charger les partenaires');
      } finally {
        setLoading(false);
      }
    };
    fetchPartners();
  }, []);

  // v80: Charger le compteur de likes depuis l'API
  useEffect(() => {
    const fetchPageLikes = async () => {
      try {
        const res = await axios.get(`${API}/page-likes?coach_email=contact.artboost@gmail.com`);
        setPageLikesCount(res.data?.count || 0);
      } catch (e) { console.error('[V80] Fetch page likes error:', e); }
    };
    fetchPageLikes();
  }, []);

  // v9.5.2: Nettoyage des timeouts
  useEffect(() => {
    return () => {
      if (scrollTimeout.current) {
        clearTimeout(scrollTimeout.current);
      }
    };
  }, []);
  
  const handleToggleMute = useCallback((partnerId) => {
    setMutedStates(prev => ({ ...prev, [partnerId]: !prev[partnerId] }));
  }, []);
  
  const handleToggleLike = useCallback((partnerId) => {
    // v80: Incrémenter le compteur via API + animation
    setPageLikesCount(prev => prev + 1);
    setLikeAnimating(true);
    setTimeout(() => setLikeAnimating(false), 600);
    // Marquer comme liké localement
    setLikedStates(prev => {
      const newState = { ...prev, [partnerId]: true };
      localStorage.setItem('afroboost_partner_likes', JSON.stringify(newState));
      return newState;
    });
    // Appel API async (fire & forget)
    const partnerEmail = partners.find(p => (p.id || p.email) === partnerId)?.email || 'contact.artboost@gmail.com';
    axios.post(`${API}/page-like`, { coach_email: partnerEmail }).then(res => {
      if (res.data?.count) setPageLikesCount(res.data.count);
    }).catch(e => console.error('[V80] Page like error:', e));
  }, [partners]);
  
  const handleTogglePause = useCallback((partnerId) => {
    setPausedStates(prev => ({ ...prev, [partnerId]: !prev[partnerId] }));
  }, []);
  
  // v9.5.3: Scroll handler optimisé avec debounce
  const handleScroll = useCallback(() => {
    if (scrollTimeout.current) {
      clearTimeout(scrollTimeout.current);
    }
    
    scrollTimeout.current = setTimeout(() => {
      if (sliderRef.current) {
        const scrollTop = sliderRef.current.scrollTop;
        const cardHeight = sliderRef.current.clientHeight;
        const newIndex = Math.round(scrollTop / cardHeight);
        if (newIndex !== activeIndex && newIndex >= 0 && newIndex < filteredPartners.length) {
          setActiveIndex(newIndex);
        }
      }
    }, 50);
  }, [activeIndex, filteredPartners.length]);
  
  // Navigation vers vitrine - v9.7.2: VITRINE UNIQUE - Pas de redirection si même partenaire
  // v11.7: DÉSACTIVÉ pour Super Admin - Pas de redirection vers vitrine Super Admin
  const SUPER_ADMIN_EMAILS_NAV = ['contact.artboost@gmail.com', 'afroboost.bassi@gmail.com'];
  
  const handleNavigate = useCallback((partner) => {
    // v9.5.7: QUICK CONTROL - Bloquer navigation si maintenance ON (sauf Super Admin)
    if (maintenanceMode && !isSuperAdmin) {
      console.log('[MAINTENANCE] Navigation bloquée - mode maintenance actif');
      return; // Ne rien faire
    }
    
    // v11.7: Bloquer navigation vers vitrine Super Admin
    const partnerEmail = (partner.email || '').toLowerCase().trim();
    const isSuperAdminTarget = SUPER_ADMIN_EMAILS_NAV.some(email => email.toLowerCase() === partnerEmail);
    if (isSuperAdminTarget) {
      console.log('[SUPER-ADMIN] Navigation vers vitrine Super Admin désactivée');
      return; // Ne rien faire - pas de vitrine partenaire pour Super Admin
    }
    
    // v9.7.2: VITRINE UNIQUE - Si on est déjà sur la vitrine de ce partenaire, ne rien faire
    const currentVitrine = (currentVitrineEmail || '').toLowerCase().trim();
    
    if (currentVitrine && partnerEmail === currentVitrine) {
      console.log('[VITRINE-UNIQUE] Clic sur sa propre vidéo - Aucune redirection');
      return; // Ne rien faire - on est déjà sur cette vitrine
    }
    
    sessionStorage.setItem('afroboost_flux_index', activeIndex.toString());
    
    const username = partner.email || partner.id || partner.name?.toLowerCase().replace(/\s+/g, '-');
    const targetPath = `/coach/${username}`;
    
    if (window.location.pathname !== targetPath) {
      if (onPartnerClick) {
        onPartnerClick(partner);
      } else {
        window.history.pushState({}, '', targetPath); // v12: pas de rechargement page
      }
    }
  }, [activeIndex, onPartnerClick, maintenanceMode, isSuperAdmin, currentVitrineEmail]);
  
  if (loading) {
    return (
      <div className="flex items-center justify-center w-full h-full" style={{ background: '#000000' }}>
        <div className="text-center">
          <div className="animate-spin w-10 h-10 border-3 rounded-full mx-auto mb-3" style={{ borderColor: 'var(--primary-color, #D91CD2)', borderTopColor: 'transparent' }}></div>
          <p className="text-white/50 text-sm">Chargement...</p>
        </div>
      </div>
    );
  }
  
  if (error || partners.length === 0) {
    return null;
  }
  
  return (
    <div 
      className="relative w-full h-full"
      style={{ background: '#000000' }}
      data-testid="partners-reels-section"
    >
      {/* v9.6.6: HEADER avec icônes bien alignées (Loupe + Traduction) */}
      <div 
        className="absolute top-0 left-0 right-0 z-20"
        style={{ 
          background: 'linear-gradient(180deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.3) 70%, transparent 100%)',
          paddingTop: '0px',
          paddingBottom: '0px'
        }}
      >
        {/* Ligne principale: Logo (centre) + Icônes (droite) */}
        <div className="flex items-center justify-between px-2 py-1">
          {/* Espace gauche pour équilibrer */}
          <div className="w-8"></div>
          
          {/* Logo centré (ou barre de recherche si activée) */}
          {showSearch ? (
            <div className="flex-1 mx-1">
              <div className="relative">
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Rechercher..."
                  className="w-full px-2 py-1 rounded-full text-xs text-white placeholder-white/50"
                  style={{
                    background: 'rgba(255,255,255,0.15)',
                    border: '1px solid rgba(255,255,255,0.2)',
                    backdropFilter: 'blur(8px)'
                  }}
                  autoFocus
                  data-testid="search-input"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-white/50 hover:text-white text-xs"
                  >
                    ✕
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-1" data-testid="afroboost-logo">
              <AfroboostLogo />
              <span 
                className="text-white font-bold text-xs"
                style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}
              >
                Afroboost
              </span>
            </div>
          )}
          
          {/* v9.6.8: Container icônes avec gap de 15px (gap-4) - LANGUE + LOUPE + SON */}
          <div className="flex items-center gap-4">
            {/* v9.6.8: Sélecteur de langue */}
            <div className="relative">
              <button
                onClick={() => setShowLangMenu(!showLangMenu)}
                className="w-7 h-7 flex items-center justify-center rounded-full transition-all hover:scale-110"
                style={{ 
                  background: 'rgba(255,255,255,0.1)',
                  color: 'white'
                }}
                data-testid="lang-selector-btn"
              >
                <GlobeIcon />
              </button>
              {showLangMenu && (
                <div 
                  className="absolute top-full right-0 mt-1 py-1 rounded-lg overflow-hidden"
                  style={{
                    background: 'rgba(0,0,0,0.95)',
                    border: '1px solid rgba(139, 92, 246, 0.4)',
                    minWidth: '60px',
                    zIndex: 50
                  }}
                >
                  {['FR', 'EN', 'DE'].map(code => (
                    <button
                      key={code}
                      onClick={() => {
                        if (onLangChange) onLangChange(code.toLowerCase());
                        setShowLangMenu(false);
                      }}
                      className="w-full px-3 py-1.5 text-white text-xs text-center hover:bg-purple-500/30"
                      style={{ 
                        background: lang?.toUpperCase() === code ? 'rgba(139, 92, 246, 0.3)' : 'transparent' 
                      }}
                      data-testid={`lang-${code.toLowerCase()}`}
                    >
                      {code}
                    </button>
                  ))}
                </div>
              )}
            </div>
            
            {/* Bouton Recherche/Fermer */}
            <button
              onClick={() => {
                setShowSearch(!showSearch);
                if (!showSearch) {
                  setTimeout(() => searchInputRef.current?.focus(), 100);
                } else {
                  setSearchQuery('');
                }
              }}
              className="w-7 h-7 flex items-center justify-center rounded-full transition-all hover:scale-110"
              style={{ 
                background: showSearch ? 'var(--primary-color, #D91CD2)' : 'rgba(255,255,255,0.1)',
                color: 'white'
              }}
              data-testid="search-btn"
            >
              {showSearch ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              ) : (
                <SearchIcon />
              )}
            </button>
            
            {/* v9.6.8: Bouton Son global */}
            <button
              onClick={() => setGlobalMuted(!globalMuted)}
              className="w-7 h-7 flex items-center justify-center rounded-full transition-all hover:scale-110"
              style={{
                background: globalMuted ? 'rgba(255,255,255,0.1)' : 'var(--primary-color, #D91CD2)',
                color: 'white'
              }}
              data-testid="global-sound-btn"
            >
              <SoundIcon muted={globalMuted} />
            </button>

            {/* v14: Bouton QR Code - toujours visible */}
            <button
              onClick={() => {
                const url = window.location.href;
                const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&data=${encodeURIComponent(url)}`;
                window.open(qrUrl, '_blank');
              }}
              className="w-7 h-7 flex items-center justify-center rounded-full transition-all hover:scale-110"
              style={{ background: 'rgba(255,255,255,0.1)', color: 'white' }}
              data-testid="qr-btn-carousel"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="2" y="2" width="8" height="8" rx="1" />
                <rect x="14" y="2" width="8" height="8" rx="1" />
                <rect x="2" y="14" width="8" height="8" rx="1" />
                <rect x="14" y="14" width="4" height="4" />
                <line x1="22" y1="14" x2="22" y2="18" />
                <line x1="18" y1="22" x2="22" y2="22" />
              </svg>
            </button>

            {/* v12: Bouton Partage - toujours visible */}
            <button
              onClick={() => {
                const url = window.location.href;
                if (navigator.share) {
                  navigator.share({ title: 'Afroboost', url });
                } else {
                  navigator.clipboard.writeText(url);
                }
              }}
              className="w-7 h-7 flex items-center justify-center rounded-full transition-all hover:scale-110"
              style={{ background: 'rgba(255,255,255,0.1)', color: 'white' }}
              data-testid="share-btn-carousel"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="18" cy="5" r="3" />
                <circle cx="6" cy="12" r="3" />
                <circle cx="18" cy="19" r="3" />
                <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
                <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
              </svg>
            </button>
          </div>
        </div>
        
        {/* v9.5.3: Résultats de recherche */}
        {showSearch && searchQuery && (
          <div className="px-3 pb-1">
            <p className="text-white/60 text-xs">
              {filteredPartners.length} {lang === 'de' ? 'Ergebnis(se)' : lang === 'en' ? 'result(s)' : `résultat${filteredPartners.length > 1 ? 's' : ''}`}
            </p>
          </div>
        )}
      </div>
      
      {/* v9.5.4: Container scroll vertical - Pleine hauteur */}
      {/* v11.7: ZÉRO PAGE VIDE - Désactiver scroll si <= 1 partenaire */}
      <div 
        ref={sliderRef}
        onScroll={handleScroll}
        className={`snap-y snap-mandatory w-full h-full ${filteredPartners.length > 1 ? 'overflow-y-auto' : 'overflow-hidden'}`}
        style={{ 
          scrollBehavior: 'smooth',
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          WebkitOverflowScrolling: 'touch'
        }}
        data-testid="partners-vertical-slider"
      >
        {filteredPartners.length === 0 && searchQuery ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <p className="text-white/50 text-lg mb-2">{lang === 'de' ? 'Keine Ergebnisse' : lang === 'en' ? 'No results' : 'Aucun résultat'}</p>
              <p className="text-white/30 text-sm">{lang === 'de' ? 'Versuchen Sie einen anderen Suchbegriff' : lang === 'en' ? 'Try another search term' : 'Essayez un autre terme de recherche'}</p>
            </div>
          </div>
        ) : (
          filteredPartners.map((partner, index) => {
            // v9.6.9: Clé unique stable - Priorité: id > email > index
            const uniqueKey = partner.id || partner.email || `partner_${index}`;
            
            return (
              <div 
                key={uniqueKey}
                className="snap-start snap-always"
                style={{ height: '100%' }}
                data-partner-key={uniqueKey}
              >
                <PartnerVideoCard
                  partner={partner}
                  isMuted={globalMuted}
                  onToggleMute={() => setGlobalMuted(!globalMuted)}
                  isLiked={likedStates[partner.id || partner.email] || false}
                  onLike={() => handleToggleLike(partner.id || partner.email)}
                  pageLikesCount={pageLikesCount}
                  likeAnimating={likeAnimating}
                  isPaused={pausedStates[partner.id || partner.email] || false}
                  onTogglePause={() => handleTogglePause(partner.id || partner.email)}
                  onNavigate={handleNavigate}
                  isVisible={Math.abs(index - activeIndex) <= 1}
                  maintenanceMode={maintenanceMode}
                  isSuperAdmin={isSuperAdmin}
                  onBuyVideo={onBuyVideo}
                  socialCommentsCount={socialCommentsCount}
                  onShowComments={onShowComments}
                />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default PartnersCarousel;

/**
 * PartnersCarousel - Flux vertical Reels v9.5.2 LOGIQUE D'ACCÈS ET FLUX RÉPARÉ
 * - Logo Afroboost en haut au centre (position absolue)
 * - Icône recherche en haut à droite
 * - 1 Clic = Play/Pause, Double-clic = Vitrine
 * - Lazy loading optimisé (vidéos chargent quand visibles)
 * - Espace noir supprimé, vidéo 16:9 centrée optimalement
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
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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
  return /\.(mp4|webm|mov|avi|m4v)(\?|$)/i.test(url);
};

const getMediaInfo = (videoUrl) => {
  const url = videoUrl || DEFAULT_VIDEO_URL;
  const youtubeId = getYoutubeId(url);
  const vimeoId = getVimeoId(url);
  const isDirectVideo = isDirectVideoFile(url);
  
  return {
    url,
    youtubeId,
    vimeoId,
    isDirectVideo,
    hasValidMedia: !!(youtubeId || vimeoId || isDirectVideo),
    isFallback: !videoUrl || (!youtubeId && !vimeoId && !isDirectVideo)
  };
};

// === COMPOSANT VIDEO CARD v9.5.7 avec mode maintenance ===
const PartnerVideoCard = ({ partner, onToggleMute, isMuted, onLike, isLiked, onNavigate, isPaused, onTogglePause, isVisible, maintenanceMode = false, isSuperAdmin = false }) => {
  const videoRef = useRef(null);
  const [hasError, setHasError] = useState(false);
  const lastClickTime = useRef(0);
  const clickCount = useRef(0);
  const clickTimer = useRef(null);
  
  const videoUrl = partner.video_url || partner.heroImageUrl;
  const mediaInfo = useMemo(() => getMediaInfo(videoUrl), [videoUrl]);
  const activeMedia = hasError ? getMediaInfo(DEFAULT_VIDEO_URL) : mediaInfo;
  
  const initial = (partner.name || partner.platform_name || 'P').charAt(0).toUpperCase();
  const displayName = partner.platform_name || partner.name || 'Partenaire';
  const bio = partner.bio || partner.description || '';
  
  // v9.5.7: QUICK CONTROL - Bloquer actions si maintenance ON (sauf Super Admin)
  const isBlocked = maintenanceMode && !isSuperAdmin;

  // v9.5.2: Nettoyage des event listeners
  useEffect(() => {
    return () => {
      if (clickTimer.current) {
        clearTimeout(clickTimer.current);
      }
    };
  }, []);

  // v9.5.7: Gestion améliorée clic simple vs double-clic (avec blocage maintenance)
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
        // Double-clic -> Navigation vitrine
        onNavigate(partner);
      }
      clickCount.current = 0;
    }, 250);
  }, [onNavigate, onTogglePause, partner]);

  // v9.5.7: handleReserve avec blocage maintenance
  const handleReserve = (e) => {
    e.stopPropagation();
    if (isBlocked) {
      console.log('[MAINTENANCE] Réservation bloquée');
      return;
    }
    onNavigate(partner);
  };

  // v9.5.2: LAZY LOADING - Ne charger la vidéo que si visible
  const shouldLoadVideo = isVisible;

  return (
    <div 
      className="snap-start snap-always w-full flex-shrink-0 flex items-center justify-center"
      style={{ 
        height: '100%',
        background: '#000000'
      }}
      data-testid={`partner-card-${partner.id || partner.email}`}
    >
      {/* v9.6.4: ZÉRO VIDE NOIR - padding réduit à 5px */}
      <div 
        className="relative w-full h-full flex items-start justify-center"
        style={{ paddingTop: '5px', paddingLeft: '2px', paddingRight: '2px', paddingBottom: '0' }}
      >
        <div 
          className="relative w-full"
          style={{
            aspectRatio: '9/16',
            maxHeight: '98%',  // v9.5.7: Maximisé à 98%
            maxWidth: '100%'
          }}
        >
          {/* === VIDÉO/IMAGE - Format 9:16 avec LAZY LOADING === */}
          <div 
            className="absolute inset-0 overflow-hidden cursor-pointer"
            style={{ borderRadius: '12px' }}  // v9.5.7: Rayon réduit
            onClick={handleVideoClick}
          >
            {shouldLoadVideo ? (
              <>
                {activeMedia.youtubeId ? (
                  <iframe
                    className="absolute inset-0 w-full h-full"
                    src={`https://www.youtube.com/embed/${activeMedia.youtubeId}?autoplay=${isPaused ? 0 : 1}&mute=${isMuted ? 1 : 0}&loop=1&playlist=${activeMedia.youtubeId}&controls=0&showinfo=0&rel=0&modestbranding=1&playsinline=1`}
                    title={displayName}
                    frameBorder="0"
                    allow="autoplay; encrypted-media"
                    style={{ pointerEvents: 'none' }}
                    onError={() => setHasError(true)}
                    loading="lazy"
                  />
                ) : activeMedia.vimeoId ? (
                  <iframe
                    className="absolute inset-0 w-full h-full"
                    src={`https://player.vimeo.com/video/${activeMedia.vimeoId}?autoplay=${isPaused ? 0 : 1}&muted=${isMuted ? 1 : 0}&loop=1&background=1`}
                    title={displayName}
                    frameBorder="0"
                    allow="autoplay"
                    style={{ pointerEvents: 'none' }}
                    onError={() => setHasError(true)}
                    loading="lazy"
                  />
                ) : activeMedia.isDirectVideo ? (
                  <video
                    ref={videoRef}
                    autoPlay={!isPaused}
                    loop
                    muted={isMuted}
                    playsInline
                    className="absolute inset-0 w-full h-full object-cover"
                    onError={() => setHasError(true)}
                    preload="metadata"
                  >
                    <source src={activeMedia.url} type="video/mp4" />
                  </video>
                ) : (
                  <div 
                    className="absolute inset-0"
                    style={{
                      background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.5) 0%, rgba(217, 28, 210, 0.4) 100%)'
                    }}
                  >
                    <div 
                      className="absolute inset-0 flex items-center justify-center"
                      style={{
                        background: 'radial-gradient(circle at 50% 50%, rgba(217, 28, 210, 0.3) 0%, transparent 70%)'
                      }}
                    >
                      <span className="text-5xl opacity-70">🎬</span>
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
          
          {/* Overlay gradient discret en bas */}
          <div 
            className="absolute inset-0 pointer-events-none"
            style={{
              borderRadius: '16px',
              background: 'linear-gradient(0deg, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.15) 40%, transparent 60%)'
            }}
          />
          
          {/* === UI OVERLAY v9.7.2 === */}
          
          {/* v9.7.2: Bouton Son SUPPRIMÉ ICI - Un seul bouton Son global dans le header */}
          
          {/* Bouton Réserver COMPACT - Bas droite - v9.5.7: Masqué en maintenance */}
          {!isBlocked && (
            <button
              onClick={handleReserve}
              className="absolute bottom-3 right-3 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all hover:scale-105"
              style={{
                background: 'var(--primary-color, #D91CD2)',
                color: 'white',
                boxShadow: '0 2px 8px rgba(0,0,0,0.3)'
              }}
              data-testid={`reserve-btn-${partner.id || partner.email}`}
            >
              <CalendarIcon />
              <span>Réserver</span>
            </button>
          )}
          
          {/* === BLOC BAS GAUCHE: Photo + Like + Nom + Bio === */}
          <div 
            className="absolute bottom-3 left-3 right-24"
            data-testid={`profile-overlay-${partner.id || partner.email}`}
          >
            <div className="flex items-center gap-2 mb-0.5">
              <div 
                className="cursor-pointer flex-shrink-0"
                onClick={(e) => {
                  e.stopPropagation();
                  onNavigate(partner);
                }}
              >
                {partner.photo_url || partner.logo_url ? (
                  <img 
                    src={partner.photo_url || partner.logo_url} 
                    alt={displayName}
                    className="w-9 h-9 rounded-full object-cover"
                    style={{ 
                      border: '2px solid var(--primary-color, #D91CD2)',
                      boxShadow: '0 0 8px var(--glow-color, rgba(217, 28, 210, 0.4))'
                    }}
                    loading="lazy"
                  />
                ) : (
                  <div 
                    className="w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold"
                    style={{ 
                      background: 'linear-gradient(135deg, var(--primary-color, #D91CD2) 0%, var(--secondary-color, #8b5cf6) 100%)',
                      color: 'white',
                      boxShadow: '0 0 8px var(--glow-color, rgba(217, 28, 210, 0.4))'
                    }}
                  >
                    {initial}
                  </div>
                )}
              </div>
              
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onLike();
                }}
                className="p-0.5 transition-all hover:scale-125 active:scale-95 flex-shrink-0"
                style={{
                  color: isLiked ? 'var(--primary-color, #D91CD2)' : 'white',
                  filter: isLiked ? 'drop-shadow(0 0 6px var(--primary-color, #D91CD2))' : 'none'
                }}
                data-testid={`like-btn-${partner.id || partner.email}`}
              >
                <HeartIcon filled={isLiked} />
              </button>
              
              <span 
                className="text-white text-sm font-semibold truncate cursor-pointer"
                style={{ textShadow: '0 1px 3px rgba(0,0,0,0.9)' }}
                onClick={(e) => {
                  e.stopPropagation();
                  onNavigate(partner);
                }}
              >
                {displayName}
              </span>
            </div>
            
            {bio && (
              <p 
                className="text-white/60 text-xs leading-tight pl-11"
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
          </div>
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
const PartnersCarousel = ({ onPartnerClick, onSearch, maintenanceMode = false, isSuperAdmin = false, lang = 'fr', onLangChange, currentVitrineEmail = null }) => {
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
    setLikedStates(prev => {
      const newState = { ...prev, [partnerId]: !prev[partnerId] };
      localStorage.setItem('afroboost_partner_likes', JSON.stringify(newState));
      return newState;
    });
  }, []);
  
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
  
  // Navigation vers vitrine - v9.5.7: Bloquer en mode maintenance
  const handleNavigate = useCallback((partner) => {
    // v9.5.7: QUICK CONTROL - Bloquer navigation si maintenance ON (sauf Super Admin)
    if (maintenanceMode && !isSuperAdmin) {
      console.log('[MAINTENANCE] Navigation bloquée - mode maintenance actif');
      return; // Ne rien faire
    }
    
    sessionStorage.setItem('afroboost_flux_index', activeIndex.toString());
    
    const username = partner.email || partner.id || partner.name?.toLowerCase().replace(/\s+/g, '-');
    const targetPath = `/coach/${username}`;
    
    if (window.location.pathname !== targetPath) {
      if (onPartnerClick) {
        onPartnerClick(partner);
      } else {
        window.location.href = targetPath;
      }
    }
  }, [activeIndex, onPartnerClick, maintenanceMode, isSuperAdmin]);
  
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
          </div>
        </div>
        
        {/* v9.5.3: Résultats de recherche */}
        {showSearch && searchQuery && (
          <div className="px-3 pb-1">
            <p className="text-white/60 text-xs">
              {filteredPartners.length} résultat{filteredPartners.length > 1 ? 's' : ''}
            </p>
          </div>
        )}
      </div>
      
      {/* v9.5.4: Container scroll vertical - Pleine hauteur */}
      <div 
        ref={sliderRef}
        onScroll={handleScroll}
        className="snap-y snap-mandatory overflow-y-auto w-full h-full"
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
              <p className="text-white/50 text-lg mb-2">Aucun résultat</p>
              <p className="text-white/30 text-sm">Essayez un autre terme de recherche</p>
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
                  isPaused={pausedStates[partner.id || partner.email] || false}
                  onTogglePause={() => handleTogglePause(partner.id || partner.email)}
                  onNavigate={handleNavigate}
                  isVisible={Math.abs(index - activeIndex) <= 1}
                  maintenanceMode={maintenanceMode}
                  isSuperAdmin={isSuperAdmin}
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

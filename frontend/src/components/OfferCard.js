// OfferCard.js - Composants de rendu des offres avec multi-images
// Compatible Vercel - Extrait de App.js pour architecture modulaire
import { useState, useEffect } from 'react';

// === V159: COUNTDOWN TIMER COMPONENT (ES5-compatible logic) ===
var CountdownTimer = function CountdownTimer(props) {
  var offer = props.offer;
  var initialRemaining = function() {
    if (!offer.countdown_enabled || !offer.countdown_date) return 0;
    var endStr = offer.countdown_date + 'T' + (offer.countdown_time || '23:59') + ':00';
    var end = new Date(endStr).getTime();
    var now = Date.now();
    return Math.max(0, Math.floor((end - now) / 1000));
  };

  var remainingState = useState(initialRemaining);
  var remaining = remainingState[0];
  var setRemaining = remainingState[1];

  useEffect(function() {
    if (!offer.countdown_enabled || !offer.countdown_date) return;
    var endStr = offer.countdown_date + 'T' + (offer.countdown_time || '23:59') + ':00';
    var endTime = new Date(endStr).getTime();
    var interval = setInterval(function() {
      var now = Date.now();
      var diff = Math.max(0, Math.floor((endTime - now) / 1000));
      setRemaining(diff);
      if (diff <= 0) clearInterval(interval);
    }, 1000);
    return function() { clearInterval(interval); };
  }, [offer.countdown_date, offer.countdown_time, offer.countdown_enabled]);

  if (!offer.countdown_enabled || !offer.countdown_date || remaining <= 0) {
    if (offer.countdown_enabled && offer.countdown_date && remaining <= 0) {
      return (
        <div style={{
          marginTop: '8px', padding: '6px 12px', borderRadius: '8px',
          background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)',
          fontSize: '11px', color: '#f87171', textAlign: 'center', fontWeight: 600
        }}>
          Cette offre est terminée
        </div>
      );
    }
    return null;
  }

  var days = Math.floor(remaining / 86400);
  var hours = Math.floor((remaining % 86400) / 3600);
  var minutes = Math.floor((remaining % 3600) / 60);
  var seconds = remaining % 60;
  var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
  var text = offer.countdown_text || "L'OFFRE FINIT DANS :";

  return (
    <div style={{
      marginTop: '8px', padding: '8px 12px', borderRadius: '10px',
      background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(239, 68, 68, 0.1) 100%)',
      border: '1px solid rgba(245, 158, 11, 0.35)',
      textAlign: 'center'
    }}>
      <div style={{ fontSize: '10px', color: '#f59e0b', fontWeight: 700, letterSpacing: '0.5px', marginBottom: '4px', textTransform: 'uppercase' }}>
        {text}
      </div>
      <div style={{ fontSize: '15px', color: '#fff', fontWeight: 800, fontFamily: "'Courier New', monospace", letterSpacing: '1px' }}>
        {pad(days)}j {pad(hours)}h {pad(minutes)}m {pad(seconds)}s
      </div>
    </div>
  );
};

// === ICONS ===
const InfoIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <circle cx="12" cy="12" r="10"/>
    <path d="M12 16v-4"/>
    <path d="M12 8h.01"/>
  </svg>
);

const CloseIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
    <path d="M18 6L6 18M6 6l12 12"/>
  </svg>
);

// === OFFER CARD SIMPLE ===
// Pour grilles ou listes verticales
export const OfferCard = ({ offer, selected, onClick }) => {
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
              loading="lazy"
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
            
            {/* Photo Icon - Top Left */}
            <div
              className="offer-info-btn"
              style={{
                left: '8px',
                right: 'auto',
                background: 'rgba(217, 28, 210, 0.85)',
                boxShadow: '0 0 8px rgba(217, 28, 210, 0.5)',
                border: 'none'
              }}
              title="Photo"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                <circle cx="8.5" cy="8.5" r="1.5"/>
                <polyline points="21 15 16 10 5 21"/>
              </svg>
            </div>
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
        {offer.description && (
          <p className="text-xs text-white/60 mt-1" style={{
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical'
          }}>
            {offer.description}{' '}
            <span
              onClick={toggleDescription}
              className="cursor-pointer font-semibold"
              style={{ color: '#d91cd2' }}
            >
              Lire plus
            </span>
          </p>
        )}
        <span className="font-bold" style={{ color: '#d91cd2', fontSize: '18px' }}>CHF {offer.price}.-</span>
        {/* V159: Countdown Timer */}
        <CountdownTimer offer={offer} />
      </div>
    </div>
  );
};

// === OFFER CARD SLIDER ===
// Pour slider horizontal avec LED effect, Loupe, Info icon + Dots
export const OfferCardSlider = ({ offer, selected, onClick }) => {
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
              ? '0 0 0 3px #d91cd2, 0 0 30px #d91cd2, 0 0 60px rgba(217, 28, 210, 0.5)' 
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
                  loading="lazy"
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
                
                {/* Photo Icon - Top Left */}
                <div
                  className="absolute top-3 left-3 w-9 h-9 rounded-full flex items-center justify-center cursor-pointer transition-all hover:scale-110"
                  style={{
                    background: 'rgba(217, 28, 210, 0.85)',
                    boxShadow: '0 0 12px rgba(217, 28, 210, 0.5)',
                    border: '2px solid rgba(255, 255, 255, 0.3)'
                  }}
                  onClick={toggleZoom}
                  title="Voir la photo"
                >
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
                    <circle cx="8.5" cy="8.5" r="1.5"/>
                    <polyline points="21 15 16 10 5 21"/>
                  </svg>
                </div>
                
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
            <p className="font-semibold text-white mb-1" style={{ fontSize: '17px' }}>{offer.name}</p>
            {offer.description && (
              <p className="text-xs mb-2" style={{
                color: 'rgba(255,255,255,0.55)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                lineHeight: '1.4'
              }}>
                {offer.description}{' '}
                <span
                  onClick={(e) => { e.stopPropagation(); setShowDescription(true); }}
                  className="cursor-pointer font-semibold"
                  style={{ color: '#d91cd2' }}
                >
                  Lire plus
                </span>
              </p>
            )}
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
            {offer.duration_value && offer.duration_unit && (
              <div style={{
                marginTop: '8px',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '3px 10px',
                borderRadius: '20px',
                background: 'rgba(139, 92, 246, 0.15)',
                border: '1px solid rgba(139, 92, 246, 0.4)',
                fontSize: '11px',
                color: '#a78bfa'
              }}>
                <span>⏱</span>
                <span>Valable {offer.duration_value} {offer.duration_unit === 'days' ? 'jour(s)' : offer.duration_unit === 'weeks' ? 'semaine(s)' : 'mois'}</span>
              </div>
            )}
            {/* V159: Countdown Timer */}
            <CountdownTimer offer={offer} />
          </div>
        </div>
      </div>
    </>
  );
};

export default OfferCard;

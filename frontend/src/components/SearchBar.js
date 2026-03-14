// /components/SearchBar.js - Navigation Client avec filtres ultra-minimalistes
// Architecture modulaire Afroboost - Design minimaliste style globe

import { useState, useCallback, useEffect } from 'react';

// Icône de recherche SVG - fine
const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8"/>
    <line x1="21" y1="21" x2="16.65" y2="16.65"/>
  </svg>
);

// Icône de fermeture SVG - fine
const CloseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18"/>
    <line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
);

// Icônes minimalistes pour les filtres - style traits fins comme le globe (22px)
// Taille réduite à 12px pour correspondre au style micro/globe
const AllIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="7" height="7"/>
    <rect x="14" y="3" width="7" height="7"/>
    <rect x="14" y="14" width="7" height="7"/>
    <rect x="3" y="14" width="7" height="7"/>
  </svg>
);

const CoursesIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
    <line x1="16" y1="2" x2="16" y2="6"/>
    <line x1="8" y1="2" x2="8" y2="6"/>
    <line x1="3" y1="10" x2="21" y2="10"/>
  </svg>
);

const ShopIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/>
    <line x1="3" y1="6" x2="21" y2="6"/>
    <path d="M16 10a4 4 0 01-8 0"/>
  </svg>
);

// v8.9.4: Icône Coach - cercle fin avec silhouette minimaliste
const CoachIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="8" r="4"/>
    <path d="M6 21v-2a4 4 0 014-4h4a4 4 0 014 4v2"/>
  </svg>
);

// Configuration des filtres - Style ultra-minimaliste
const FILTER_OPTIONS = [
  { id: 'all', label: 'Tout', Icon: AllIcon },
  { id: 'sessions', label: 'Cours', Icon: CoursesIcon },
  { id: 'shop', label: 'Shop', Icon: ShopIcon }
];

/**
 * Barre de navigation avec filtres ultra-minimalistes style globe
 */
export const NavigationBar = ({ 
  activeFilter = 'all', 
  onFilterChange, 
  searchQuery = '', 
  onSearchChange,
  showSearch = true,
  showFilters = true,
  onCoachClick = null  // v8.9.4: Callback pour ouvrir la recherche coach
}) => {
  const [localSearch, setLocalSearch] = useState(searchQuery);
  
  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      if (onSearchChange) {
        onSearchChange(localSearch);
      }
    }, 150);
    return () => clearTimeout(timer);
  }, [localSearch, onSearchChange]);

  useEffect(() => {
    setLocalSearch(searchQuery);
  }, [searchQuery]);

  const handleFilterClick = useCallback((filterId) => {
    if (onFilterChange) {
      onFilterChange(filterId);
      
      setTimeout(() => {
        let sectionId = null;
        if (filterId === 'sessions') {
          sectionId = 'sessions-section';
        } else if (filterId === 'shop') {
          sectionId = 'products-section';
        }
        
        if (sectionId) {
          const element = document.getElementById(sectionId);
          if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }
      }, 100);
    }
  }, [onFilterChange]);

  const clearSearch = useCallback(() => {
    setLocalSearch('');
    if (onSearchChange) {
      onSearchChange('');
    }
  }, [onSearchChange]);

  return (
    <div className="navigation-bar mb-6" data-testid="navigation-bar">
      {/* Barre de recherche avec bordure rose fine */}
      {showSearch && (
        <div 
          className="search-bar-container"
          style={{
            position: 'relative',
            width: '100%',
            maxWidth: '400px',
            margin: '0 auto 16px auto'
          }}
        >
          <div 
            style={{
              position: 'absolute',
              left: '12px',
              top: '50%',
              transform: 'translateY(-50%)',
              color: 'rgba(217, 28, 210, 0.5)',
              pointerEvents: 'none'
            }}
          >
            <SearchIcon />
          </div>
          <input
            type="text"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            placeholder="Rechercher..."
            data-testid="search-input"
            className="search-input-minimal"
            style={{
              width: '100%',
              padding: '10px 36px 10px 36px',
              borderRadius: '20px',
              border: '1px solid rgba(217, 28, 210, 0.4)',
              background: 'rgba(0, 0, 0, 0.3)',
              color: '#fff',
              fontSize: '13px',
              fontWeight: '300',
              letterSpacing: '0.3px',
              outline: 'none',
              transition: 'all 0.3s ease'
            }}
          />
          {localSearch && (
            <button
              onClick={clearSearch}
              data-testid="clear-search"
              style={{
                position: 'absolute',
                right: '12px',
                top: '50%',
                transform: 'translateY(-50%)',
                background: 'none',
                border: 'none',
                color: 'rgba(217, 28, 210, 0.6)',
                cursor: 'pointer',
                padding: '2px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <CloseIcon />
            </button>
          )}
        </div>
      )}

      {/* Icônes de filtres - Ultra minimalistes, petites, style globe (26px) */}
      {showFilters && (
        <div 
          className="filter-icons-container"
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: '10px'
          }}
        >
          {FILTER_OPTIONS.map((filter) => {
            const isActive = activeFilter === filter.id;
            const Icon = filter.Icon;
            
            return (
              <button
                key={filter.id}
                onClick={() => handleFilterClick(filter.id)}
                data-testid={`filter-${filter.id}`}
                title={filter.label}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '26px',
                  height: '26px',
                  borderRadius: '50%',
                  border: `1px solid ${isActive ? '#D91CD2' : 'rgba(255, 255, 255, 0.2)'}`,
                  background: isActive ? 'rgba(217, 28, 210, 0.15)' : 'transparent',
                  color: isActive ? '#D91CD2' : 'rgba(255, 255, 255, 0.5)',
                  cursor: 'pointer',
                  transition: 'all 0.25s ease',
                  outline: 'none',
                  padding: 0
                }}
              >
                <Icon />
              </button>
            );
          })}
          
          {/* v8.9.4: Icône Coach séparée - alignée avec les filtres */}
          {onCoachClick && (
            <>
              <div style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }} />
              <button
                onClick={onCoachClick}
                data-testid="coach-search-nav-btn"
                title="Trouver un coach"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: '26px',
                  height: '26px',
                  borderRadius: '50%',
                  border: '2px solid #D91CD2',
                  background: 'transparent',
                  color: '#D91CD2',
                  cursor: 'pointer',
                  transition: 'all 0.25s ease',
                  outline: 'none',
                  padding: 0
                }}
              >
                <CoachIcon />
              </button>
            </>
          )}
        </div>
      )}

      {/* Styles pour hover et focus */}
      <style>{`
        .search-input-minimal:focus {
          border-color: #D91CD2 !important;
          box-shadow: 0 0 10px rgba(217, 28, 210, 0.25);
        }
        .search-input-minimal::placeholder {
          color: rgba(255, 255, 255, 0.35);
          font-weight: 300;
        }
        .filter-icons-container button:hover {
          border-color: rgba(217, 28, 210, 0.6) !important;
          color: #D91CD2 !important;
          background: rgba(217, 28, 210, 0.08) !important;
        }
      `}</style>
    </div>
  );
};

/**
 * Flèche animée pour indiquer du contenu en dessous
 */
export const ScrollIndicator = ({ show }) => {
  if (!show) return null;
  
  return (
    <div 
      className="scroll-indicator"
      style={{
        position: 'fixed',
        bottom: '30px',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 50,
        animation: 'bounce 2s infinite',
        opacity: 0.7,
        cursor: 'pointer'
      }}
      onClick={() => window.scrollBy({ top: 300, behavior: 'smooth' })}
      data-testid="scroll-indicator"
    >
      <svg 
        width="28" 
        height="28" 
        viewBox="0 0 24 24" 
        fill="none" 
        stroke="#d91cd2" 
        strokeWidth="1.5" 
        strokeLinecap="round" 
        strokeLinejoin="round"
      >
        <path d="M12 5v14M5 12l7 7 7-7"/>
      </svg>
      <style>{`
        @keyframes bounce {
          0%, 20%, 50%, 80%, 100% {
            transform: translateX(-50%) translateY(0);
          }
          40% {
            transform: translateX(-50%) translateY(-10px);
          }
          60% {
            transform: translateX(-50%) translateY(-5px);
          }
        }
      `}</style>
    </div>
  );
};

/**
 * Hook pour gérer l'indicateur de scroll
 */
export const useScrollIndicator = () => {
  const [showIndicator, setShowIndicator] = useState(false);
  
  useEffect(() => {
    let hasScrolled = false;
    let timer = null;
    
    const handleScroll = () => {
      hasScrolled = true;
      setShowIndicator(false);
      window.removeEventListener('scroll', handleScroll);
      if (timer) clearTimeout(timer);
    };
    
    timer = setTimeout(() => {
      if (!hasScrolled) {
        setShowIndicator(true);
      }
    }, 3000);
    
    window.addEventListener('scroll', handleScroll, { passive: true });
    
    return () => {
      window.removeEventListener('scroll', handleScroll);
      if (timer) clearTimeout(timer);
    };
  }, []);
  
  return showIndicator;
};

/**
 * Hook pour gérer la logique de filtrage et recherche
 */
export const useNavigation = (offers = [], courses = [], defaultSection = 'all') => {
  const [activeFilter, setActiveFilter] = useState(defaultSection);
  const [searchQuery, setSearchQuery] = useState('');

  // V106: Recherche universelle — scanne nom, description, ET mots-clés
  const filteredOffers = offers.filter(offer => {
    let categoryMatch = true;
    if (activeFilter === 'sessions') {
      categoryMatch = !offer.isProduct;
    } else if (activeFilter === 'shop') {
      categoryMatch = offer.isProduct === true;
    }

    let searchMatch = true;
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      const name = (offer.name || '').toLowerCase();
      const description = (offer.description || '').toLowerCase();
      const keywords = (offer.keywords || '').toLowerCase();
      const category = (offer.category || '').toLowerCase();
      searchMatch = name.includes(query) || description.includes(query) || keywords.includes(query) || category.includes(query);
    }

    return categoryMatch && searchMatch;
  });

  // V106: Recherche cours — scanne nom, lieu, description
  const filteredCourses = courses.filter(course => {
    if (activeFilter === 'shop') {
      return false;
    }

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      const name = (course.name || '').toLowerCase();
      const location = (course.locationName || course.location || '').toLowerCase();
      return name.includes(query) || location.includes(query);
    }

    return true;
  });

  const getSectionToScroll = useCallback(() => {
    switch (activeFilter) {
      case 'sessions':
        return 'sessions-section';
      case 'shop':
        return 'products-section';
      default:
        return null;
    }
  }, [activeFilter]);

  return {
    activeFilter,
    setActiveFilter,
    searchQuery,
    setSearchQuery,
    filteredOffers,
    filteredCourses,
    getSectionToScroll,
    hasResults: filteredOffers.length > 0 || filteredCourses.length > 0
  };
};

/**
 * Sélecteur de section d'atterrissage pour le Mode Coach
 */
export const LandingSectionSelector = ({ value = 'sessions', onChange }) => {
  const options = [
    { id: 'sessions', label: '📅 Sessions', description: 'Les cours disponibles' },
    { id: 'offers', label: '🎁 Offres', description: 'Les cartes et abonnements' },
    { id: 'shop', label: '🛍️ Shop', description: 'Les produits physiques' }
  ];

  return (
    <div className="landing-section-selector" data-testid="landing-section-selector">
      <label className="block mb-2 text-white text-sm">📍 Section d'atterrissage par défaut</label>
      <select
        value={value}
        onChange={(e) => onChange && onChange(e.target.value)}
        className="w-full px-4 py-3 rounded-lg neon-input"
        data-testid="landing-section-select"
        style={{
          background: 'rgba(0, 0, 0, 0.6)',
          border: '2px solid rgba(139, 92, 246, 0.4)',
          color: '#fff',
          cursor: 'pointer'
        }}
      >
        {options.map(option => (
          <option key={option.id} value={option.id}>
            {option.label} - {option.description}
          </option>
        ))}
      </select>
      <p className="text-xs mt-1" style={{ color: 'rgba(255,255,255,0.4)' }}>
        Cette section sera affichée en premier lors du chargement de l'application côté client.
      </p>
    </div>
  );
};

export default NavigationBar;

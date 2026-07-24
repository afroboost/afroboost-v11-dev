/**
 * CoachSearch - Composant de recherche de coach v8.9.2
 * Icône minimaliste cercle fin violet #D91CD2
 * Avec Error Boundary pour éviter les crashes
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';
const API = `${BACKEND_URL}/api`;

// Icône Coach cercle fin
const CoachIcon = ({ onClick, className = "" }) => (
  <button
    onClick={onClick}
    className={`p-2 rounded-full transition-all hover:scale-110 ${className}`}
    style={{ 
      border: '2px solid var(--primary-color, #D91CD2)',
      background: 'transparent'
    }}
    data-testid="coach-search-icon"
    title="Trouver un coach"
  >
    <svg 
      width="24" 
      height="24" 
      viewBox="0 0 24 24" 
      fill="none" 
      style={{ stroke: 'var(--primary-color, #D91CD2)' }} 
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
    </svg>
  </button>
);

// Icône QR Scan
const ScanIcon = ({ onClick, className = "" }) => (
  <button
    onClick={onClick}
    className={`p-2 rounded-full transition-all hover:scale-110 ${className}`}
    style={{ 
      border: '2px solid var(--primary-color, #D91CD2)',
      background: 'transparent'
    }}
    data-testid="coach-scan-icon"
    title="Scanner QR Coach"
  >
    <svg 
      width="24" 
      height="24" 
      viewBox="0 0 24 24" 
      fill="none" 
      style={{ stroke: 'var(--primary-color, #D91CD2)' }} 
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
  </button>
);

// Modal de recherche
const CoachSearchModal = ({ isOpen, onClose, onSelectCoach }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Debounced search
  const searchCoaches = useCallback(async (q) => {
    if (!q || q.length < 2) {
      setResults([]);
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      const res = await axios.get(`${API}/coaches/search?q=${encodeURIComponent(q)}`);
      setResults(res.data || []);
    } catch (err) {
      console.error('[SEARCH] Erreur:', err);
      setError('Recherche impossible');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      searchCoaches(query);
    }, 300);
    return () => clearTimeout(timer);
  }, [query, searchCoaches]);

  if (!isOpen) return null;

  return (
    <div 
      className="fixed inset-0 bg-black/80 z-50 flex items-start justify-center pt-20"
      onClick={onClose}
    >
      <div 
        className="glass rounded-2xl p-6 w-full max-w-md mx-4"
        style={{ border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.3)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-white">Trouver un Coach</h2>
          <button 
            onClick={onClose}
            className="text-white/60 hover:text-white text-xl"
          >
            ✕
          </button>
        </div>

        {/* Search input */}
        <div className="relative mb-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Nom ou email du coach..."
            className="w-full px-4 py-3 rounded-xl pr-10"
            style={{ 
              background: 'rgba(255,255,255,0.1)', 
              border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.3)', 
              color: '#fff' 
            }}
            autoFocus
            data-testid="coach-search-input"
          />
          {loading && (
            <div className="absolute right-3 top-1/2 -translate-y-1/2">
              <div className="w-5 h-5 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="text-red-400 text-sm mb-4 p-2 rounded bg-red-500/10">
            {error}
          </div>
        )}

        {/* Results */}
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {results.length === 0 && query.length >= 2 && !loading && (
            <p className="text-white/50 text-sm text-center py-4">
              Aucun coach trouvé
            </p>
          )}
          
          {results.map(coach => (
            <button
              key={coach.id}
              onClick={() => {
                onSelectCoach?.(coach);
                onClose();
              }}
              className="w-full flex items-center gap-3 p-3 rounded-lg transition-all hover:bg-white/10"
              style={{ border: '1px solid rgba(255,255,255,0.1)' }}
              data-testid={`coach-result-${coach.id}`}
            >
              {coach.photo_url ? (
                <img 
                  src={coach.photo_url} 
                  alt={coach.name}
                  className="w-10 h-10 rounded-full object-cover"
                  style={{ border: '2px solid var(--primary-color, #D91CD2)' }}
                />
              ) : (
                <div 
                  className="w-10 h-10 rounded-full flex items-center justify-center text-lg"
                  style={{ background: 'rgba(var(--primary-rgb, 217, 28, 210), 0.2)', border: '2px solid var(--primary-color, #D91CD2)' }}
                >
                  {coach.name?.charAt(0)?.toUpperCase() || '?'}
                </div>
              )}
              <div className="text-left">
                <div className="text-white font-medium">{coach.name}</div>
                {coach.bio && (
                  <div className="text-white/50 text-xs truncate max-w-[200px]">{coach.bio}</div>
                )}
              </div>
            </button>
          ))}
        </div>

        {/* Hint */}
        {query.length < 2 && (
          <p className="text-white/40 text-xs text-center mt-4">
            Tapez au moins 2 caractères pour rechercher
          </p>
        )}
      </div>
    </div>
  );
};

// Composant principal avec Error Boundary intégré
const CoachSearch = ({ onSelectCoach }) => {
  const [showSearch, setShowSearch] = useState(false);
  const [hasError, setHasError] = useState(false);

  // Error boundary simple
  if (hasError) {
    return null; // Silencieux en cas d'erreur
  }

  try {
    return (
      <>
        <div className="flex items-center gap-2">
          <CoachIcon onClick={() => setShowSearch(true)} />
        </div>
        
        <CoachSearchModal
          isOpen={showSearch}
          onClose={() => setShowSearch(false)}
          onSelectCoach={onSelectCoach}
        />
      </>
    );
  } catch (err) {
    console.error('[CoachSearch] Error:', err);
    setHasError(true);
    return null;
  }
};

export { CoachSearch, CoachIcon, ScanIcon, CoachSearchModal };
export default CoachSearch;

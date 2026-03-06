/**
 * CoachLoginModal Component - Google OAuth Authentication
 * 
 * Authentification Google exclusive pour le Coach/Super Admin
 * Seul l'email autorisé (coach@afroboost.com) peut accéder au dashboard
 * 
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';

// Icône Google officielle
const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
    <g fill="none" fillRule="evenodd">
      <path d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>
      <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </g>
  </svg>
);

const CoachLoginModal = ({ t, onLogin, onCancel, welcomeMessage }) => {
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const hasProcessedRef = useRef(false);

  // Vérifier si déjà authentifié au chargement
  useEffect(() => {
    const checkExistingAuth = async () => {
      try {
        const response = await axios.get(`${API}/auth/me`, {
          withCredentials: true
        });
        if (response.data && response.data.email) {
          console.log('✅ Déjà connecté:', response.data.email);
          onLogin(response.data);
        }
      } catch (err) {
        console.log('🔒 Non connecté, affichage du formulaire');
      } finally {
        setIsCheckingAuth(false);
      }
    };
    checkExistingAuth();
  }, [onLogin]);

  // Traiter le session_id dans l'URL (callback OAuth)
  useEffect(() => {
    const processOAuthCallback = async () => {
      // Éviter le double traitement (StrictMode)
      if (hasProcessedRef.current) return;
      
      const hash = window.location.hash;
      if (!hash.includes('session_id=')) return;
      
      hasProcessedRef.current = true;
      setIsLoading(true);
      setError("");
      
      const sessionId = hash.split('session_id=')[1]?.split('&')[0];
      if (!sessionId) {
        setError("Session invalide");
        setIsLoading(false);
        return;
      }
      
      // Nettoyer l'URL immédiatement
      window.history.replaceState(null, '', window.location.pathname);
      
      try {
        const response = await axios.post(`${API}/auth/google/session`, 
          { session_id: sessionId },
          { withCredentials: true }
        );
        
        if (response.data.success) {
          console.log('✅ Authentification Google réussie:', response.data.user.email);
          onLogin(response.data.user);
        } else {
          // Accès refusé (email non autorisé)
          setError(response.data.message || "Accès refusé");
        }
      } catch (err) {
        console.error('❌ Erreur OAuth:', err);
        setError(err.response?.data?.message || "Erreur d'authentification");
      } finally {
        setIsLoading(false);
      }
    };
    
    processOAuthCallback();
  }, [onLogin]);

  // Lancer l'authentification Google
  const handleGoogleLogin = () => {
    setIsLoading(true);
    setError("");
    
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + window.location.pathname;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  // Affichage pendant la vérification
  if (isCheckingAuth) {
    return (
      <div className="modal-overlay">
        <div className="modal-content glass rounded-xl p-8 max-w-md w-full neon-border">
          <div className="text-center">
            <div className="animate-spin w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full mx-auto mb-4"></div>
            <p className="text-white text-sm">Vérification de la session...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content glass rounded-xl p-6 max-w-md w-full neon-border">
        
        {/* v9.6.4: Header simplifié */}
        <div className="text-center mb-4">
          <div className="w-14 h-14 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 mx-auto mb-3 flex items-center justify-center">
            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h2 className="font-bold text-white text-lg mb-1">{t('coachLogin') || 'Espace Partenaire'}</h2>
        </div>

        {/* v9.1.8: Message de bienvenue après paiement */}
        {welcomeMessage && (
          <div 
            className="mb-4 p-3 rounded-lg text-center"
            style={{ 
              background: 'rgba(34, 197, 94, 0.2)', 
              border: '1px solid rgba(34, 197, 94, 0.5)' 
            }}
          >
            <p className="text-green-400 text-sm font-medium">{welcomeMessage}</p>
          </div>
        )}

        {/* Message d'erreur */}
        {error && (
          <div 
            className="mb-4 p-3 rounded-lg text-center"
            style={{ 
              background: 'rgba(239, 68, 68, 0.2)', 
              border: '1px solid rgba(239, 68, 68, 0.5)' 
            }}
          >
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* v9.6.4: BOUTON PRINCIPAL EN HAUT - Déjà Partenaire */}
        <div className="space-y-3">
          <p className="text-white/70 text-xs text-center mb-2">Déjà partenaire ?</p>
          <button
            onClick={handleGoogleLogin}
            disabled={isLoading}
            className="w-full flex items-center justify-center gap-3 py-3 px-4 rounded-lg font-medium transition-all duration-200 hover:scale-[1.02]"
            style={{
              background: '#ffffff',
              color: '#1f1f1f',
              border: 'none',
              cursor: isLoading ? 'wait' : 'pointer',
              opacity: isLoading ? 0.7 : 1,
              boxShadow: '0 4px 15px rgba(255,255,255,0.2)'
            }}
            data-testid="google-login-btn"
          >
            {isLoading ? (
              <div className="animate-spin w-5 h-5 border-2 border-gray-400 border-t-transparent rounded-full"></div>
            ) : (
              <GoogleIcon />
            )}
            <span className="font-semibold">{isLoading ? 'Connexion...' : 'Se connecter avec Google'}</span>
          </button>
        </div>

        {/* Séparateur */}
        <div className="flex items-center my-5">
          <div className="flex-1 h-px bg-white/20"></div>
          <span className="px-3 text-white/40 text-xs">ou</span>
          <div className="flex-1 h-px bg-white/20"></div>
        </div>

        {/* v9.6.4: BOUTON SECONDAIRE EN BAS - Devenir Partenaire */}
        <button 
          type="button" 
          onClick={() => {
            onCancel();
            window.location.hash = '#become-coach';
          }} 
          className="w-full py-3 rounded-lg font-medium text-sm transition-all hover:scale-[1.02]"
          style={{
            background: 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.3))',
            border: '1px solid rgba(217,28,210,0.5)',
            color: '#D91CD2'
          }}
          data-testid="become-partner-btn"
        >
          ✨ Devenir Partenaire
        </button>

        {/* Info sécurité compacte */}
        <p className="text-white/40 text-[10px] text-center mt-4">
          🔒 Connexion sécurisée via Google
        </p>

        {/* Bouton Fermer */}
        <button 
          type="button" 
          onClick={onCancel} 
          className="w-full py-2 mt-3 rounded-lg text-white/60 text-xs hover:text-white transition-colors"
          data-testid="coach-login-cancel"
        >
          Fermer
        </button>
      </div>
    </div>
  );
};

export default CoachLoginModal;

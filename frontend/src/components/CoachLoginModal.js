/**
 * CoachLoginModal Component v10.0 - Google OAuth + Email/Password
 *
 * Authentification multi-méthodes pour les Partenaires et Super Admin
 * - Google OAuth (existant, fiabilisé avec retry)
 * - Email/Password classique (nouveau)
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

// Icône Email
const EmailIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
    <polyline points="22,6 12,13 2,6"/>
  </svg>
);

// Icône œil (show/hide password)
const EyeIcon = ({ open }) => open ? (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
    <circle cx="12" cy="12" r="3"/>
  </svg>
) : (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24"/>
    <line x1="1" y1="1" x2="23" y2="23"/>
  </svg>
);

const CoachLoginModal = ({ t, onLogin, onCancel, welcomeMessage }) => {
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState(true);
  const hasProcessedRef = useRef(false);

  // Email/Password form state
  const [authMode, setAuthMode] = useState('choice'); // 'choice' | 'login' | 'register' | 'forgot' | 'reset'
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // v11: Détecter le token de reset dans l'URL au chargement
  useEffect(() => {
    const hash = window.location.hash;
    if (hash.includes('reset-password') && hash.includes('token=')) {
      const token = hash.split('token=')[1]?.split('&')[0];
      if (token) {
        setResetToken(token);
        setAuthMode('reset');
        window.history.replaceState(null, '', window.location.pathname);
      }
    }
  }, []);

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

      window.history.replaceState(null, '', window.location.pathname);

      // Retry logic for Google OAuth
      let lastError = null;
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          const response = await axios.post(`${API}/auth/google/session`,
            { session_id: sessionId },
            { withCredentials: true, timeout: 8000 }
          );

          if (response.data.success) {
            console.log('✅ Authentification Google réussie:', response.data.user.email);
            // V133: Stocker le JWT signé pour les requêtes sécurisées
            if (response.data.token) {
              localStorage.setItem('afroboost_jwt', response.data.token);
            }
            onLogin(response.data.user);
            return;
          } else {
            setError(response.data.message || "Accès refusé");
            setIsLoading(false);
            return;
          }
        } catch (err) {
          lastError = err;
          console.warn(`⚠️ Tentative ${attempt}/3 échouée:`, err.message);
          if (attempt < 3) await new Promise(r => setTimeout(r, 1000));
        }
      }

      console.error('❌ Erreur OAuth après 3 tentatives:', lastError);
      setError("La connexion Google a échoué. Réessayez ou utilisez votre email.");
      setIsLoading(false);
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

  // Connexion Email/Password
  const handleEmailLogin = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");

    try {
      const response = await axios.post(`${API}/auth/login`,
        { email, password },
        { withCredentials: true }
      );

      if (response.data.success) {
        console.log('✅ Connexion email réussie:', response.data.user.email);
        // V133: Stocker le JWT
        if (response.data.token) {
          localStorage.setItem('afroboost_jwt', response.data.token);
        }
        onLogin(response.data.user);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || "Erreur de connexion";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // Inscription Email/Password
  const handleEmailRegister = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");

    if (password.length < 6) {
      setError("Le mot de passe doit contenir au moins 6 caractères");
      setIsLoading(false);
      return;
    }

    try {
      const response = await axios.post(`${API}/auth/register`,
        { email, name, password },
        { withCredentials: true }
      );

      if (response.data.success) {
        console.log('✅ Inscription réussie:', response.data.user.email);
        // V133: Stocker le JWT
        if (response.data.token) {
          localStorage.setItem('afroboost_jwt', response.data.token);
        }
        onLogin(response.data.user);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || "Erreur d'inscription";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // Mot de passe oublié
  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    setSuccessMsg("");

    try {
      const response = await axios.post(`${API}/auth/forgot-password`,
        { email },
        { withCredentials: true }
      );

      if (response.data.success) {
        setSuccessMsg("Un email de réinitialisation a été envoyé si ce compte existe.");
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Erreur lors de l'envoi");
    } finally {
      setIsLoading(false);
    }
  };

  // Réinitialisation du mot de passe
  const handleResetPassword = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");
    setSuccessMsg("");

    if (newPassword.length < 6) {
      setError("Le mot de passe doit contenir au moins 6 caractères");
      setIsLoading(false);
      return;
    }

    try {
      const response = await axios.post(`${API}/auth/reset-password`,
        { token: resetToken, new_password: newPassword },
        { withCredentials: true }
      );

      if (response.data.success) {
        setSuccessMsg("Mot de passe modifié avec succès ! Vous pouvez vous connecter.");
        setTimeout(() => {
          resetForm();
          setAuthMode('login');
        }, 2000);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || "Lien expiré ou invalide";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  // Reset form
  const resetForm = () => {
    setEmail('');
    setName('');
    setPassword('');
    setNewPassword('');
    setError('');
    setSuccessMsg('');
    setShowPassword(false);
  };

  // Affichage pendant la vérification
  if (isCheckingAuth) {
    return (
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
        <div style={{ background: 'rgba(30,20,50,0.95)', borderRadius: '16px', padding: '32px', maxWidth: '400px', width: '90%', border: '1px solid rgba(139,92,246,0.3)' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: '32px', height: '32px', border: '2px solid #8b5cf6', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 16px' }}></div>
            <p style={{ color: 'white', fontSize: '14px' }}>Vérification de la session...</p>
          </div>
        </div>
      </div>
    );
  }

  // === STYLES COMMUNS ===
  const inputStyle = {
    width: '100%',
    padding: '10px 12px',
    borderRadius: '8px',
    background: 'rgba(255,255,255,0.08)',
    border: '1px solid rgba(255,255,255,0.15)',
    color: 'white',
    fontSize: '14px',
    outline: 'none',
    boxSizing: 'border-box'
  };

  const labelStyle = {
    display: 'block',
    color: 'rgba(255,255,255,0.6)',
    fontSize: '12px',
    marginBottom: '4px'
  };

  const primaryBtnStyle = {
    width: '100%',
    padding: '12px',
    borderRadius: '8px',
    fontWeight: '600',
    fontSize: '14px',
    cursor: isLoading ? 'wait' : 'pointer',
    opacity: isLoading ? 0.7 : 1,
    border: 'none',
    transition: 'all 0.2s'
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
      <div style={{ background: 'rgba(30,20,50,0.95)', borderRadius: '16px', padding: '24px', maxWidth: '420px', width: '90%', border: '1px solid rgba(139,92,246,0.3)', maxHeight: '90vh', overflowY: 'auto' }}>

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '16px' }}>
          <div style={{ width: '56px', height: '56px', borderRadius: '50%', background: 'linear-gradient(135deg, #8b5cf6, #ec4899)', margin: '0 auto 12px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <h2 style={{ fontWeight: 'bold', color: 'white', fontSize: '18px', marginBottom: '4px' }}>
            {t('coachLogin') || 'Espace Partenaire'}
          </h2>
        </div>

        {/* Message de bienvenue après paiement */}
        {welcomeMessage && (
          <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '8px', textAlign: 'center', background: 'rgba(34,197,94,0.2)', border: '1px solid rgba(34,197,94,0.5)' }}>
            <p style={{ color: '#4ade80', fontSize: '13px', fontWeight: '500' }}>{welcomeMessage}</p>
          </div>
        )}

        {/* Message d'erreur */}
        {error && (
          <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '8px', textAlign: 'center', background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.5)' }}>
            <p style={{ color: '#f87171', fontSize: '13px' }}>{error}</p>
          </div>
        )}

        {/* Message de succès */}
        {successMsg && (
          <div style={{ marginBottom: '16px', padding: '12px', borderRadius: '8px', textAlign: 'center', background: 'rgba(34,197,94,0.2)', border: '1px solid rgba(34,197,94,0.5)' }}>
            <p style={{ color: '#4ade80', fontSize: '13px' }}>{successMsg}</p>
          </div>
        )}

        {/* === MODE CHOIX (par défaut) === */}
        {authMode === 'choice' && (
          <>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', textAlign: 'center', marginBottom: '12px' }}>Déjà partenaire ?</p>

            {/* Bouton Google */}
            <button
              onClick={handleGoogleLogin}
              disabled={isLoading}
              style={{
                ...primaryBtnStyle,
                background: '#ffffff',
                color: '#1f1f1f',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '10px',
                boxShadow: '0 4px 15px rgba(255,255,255,0.15)',
                marginBottom: '10px'
              }}
              data-testid="google-login-btn"
            >
              {isLoading ? (
                <div style={{ width: '20px', height: '20px', border: '2px solid #999', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
              ) : (
                <GoogleIcon />
              )}
              <span>{isLoading ? 'Connexion...' : 'Se connecter avec Google'}</span>
            </button>

            {/* Bouton Email */}
            <button
              onClick={() => { resetForm(); setAuthMode('login'); }}
              disabled={isLoading}
              style={{
                ...primaryBtnStyle,
                background: 'rgba(139,92,246,0.2)',
                color: '#c4b5fd',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '10px',
                border: '1px solid rgba(139,92,246,0.4)',
                marginBottom: '0'
              }}
            >
              <EmailIcon />
              <span>Se connecter avec Email</span>
            </button>

            {/* Séparateur */}
            <div style={{ display: 'flex', alignItems: 'center', margin: '20px 0' }}>
              <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.15)' }}></div>
              <span style={{ padding: '0 12px', color: 'rgba(255,255,255,0.3)', fontSize: '12px' }}>ou</span>
              <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.15)' }}></div>
            </div>

            {/* Devenir Partenaire */}
            <button
              type="button"
              onClick={() => { onCancel(); window.location.hash = '#become-coach'; }}
              style={{
                ...primaryBtnStyle,
                background: 'linear-gradient(135deg, rgba(217,28,210,0.3), rgba(139,92,246,0.3))',
                border: '1px solid rgba(217,28,210,0.5)',
                color: '#D91CD2'
              }}
              data-testid="become-partner-btn"
            >
              ✨ Devenir Partenaire
            </button>
          </>
        )}

        {/* === MODE CONNEXION EMAIL === */}
        {authMode === 'login' && (
          <form onSubmit={handleEmailLogin}>
            <div style={{ marginBottom: '12px' }}>
              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="votre@email.com"
                required
                style={inputStyle}
              />
            </div>
            <div style={{ marginBottom: '16px', position: 'relative' }}>
              <label style={labelStyle}>Mot de passe</label>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••"
                required
                style={{ ...inputStyle, paddingRight: '40px' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{ position: 'absolute', right: '10px', top: '28px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: '4px' }}
              >
                <EyeIcon open={showPassword} />
              </button>
            </div>
            <button
              type="submit"
              disabled={isLoading}
              style={{
                ...primaryBtnStyle,
                background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
                color: 'white',
                marginBottom: '10px'
              }}
            >
              {isLoading ? 'Connexion...' : 'Se connecter'}
            </button>

            {/* Mot de passe oublié */}
            <div style={{ textAlign: 'center', marginTop: '8px', marginBottom: '4px' }}>
              <button
                type="button"
                onClick={() => { setError(''); setSuccessMsg(''); setAuthMode('forgot'); }}
                style={{ background: 'none', border: 'none', color: '#f59e0b', fontSize: '12px', cursor: 'pointer', textDecoration: 'underline' }}
              >
                Mot de passe oublié ?
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
              <button
                type="button"
                onClick={() => { resetForm(); setAuthMode('register'); }}
                style={{ background: 'none', border: 'none', color: '#c4b5fd', fontSize: '12px', cursor: 'pointer', textDecoration: 'underline' }}
              >
                Créer un compte
              </button>
              <button
                type="button"
                onClick={() => { resetForm(); setAuthMode('choice'); }}
                style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', fontSize: '12px', cursor: 'pointer' }}
              >
                ← Retour
              </button>
            </div>
          </form>
        )}

        {/* === MODE MOT DE PASSE OUBLIÉ === */}
        {authMode === 'forgot' && (
          <form onSubmit={handleForgotPassword}>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '13px', textAlign: 'center', marginBottom: '16px' }}>
              Entrez votre email pour recevoir un lien de réinitialisation
            </p>
            <div style={{ marginBottom: '16px' }}>
              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="votre@email.com"
                required
                autoFocus
                style={inputStyle}
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              style={{
                ...primaryBtnStyle,
                background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                color: 'white',
                marginBottom: '10px'
              }}
            >
              {isLoading ? 'Envoi...' : 'Envoyer le lien de réinitialisation'}
            </button>
            <div style={{ textAlign: 'center', marginTop: '8px' }}>
              <button
                type="button"
                onClick={() => { resetForm(); setAuthMode('login'); }}
                style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', fontSize: '12px', cursor: 'pointer' }}
              >
                ← Retour à la connexion
              </button>
            </div>
          </form>
        )}

        {/* === MODE RESET MOT DE PASSE === */}
        {authMode === 'reset' && (
          <form onSubmit={handleResetPassword}>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '13px', textAlign: 'center', marginBottom: '16px' }}>
              Choisissez votre nouveau mot de passe
            </p>
            <div style={{ marginBottom: '16px', position: 'relative' }}>
              <label style={labelStyle}>Nouveau mot de passe (min. 6 caractères)</label>
              <input
                type={showPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="••••••"
                required
                minLength={6}
                autoFocus
                style={{ ...inputStyle, paddingRight: '40px' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{ position: 'absolute', right: '10px', top: '28px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: '4px' }}
              >
                <EyeIcon open={showPassword} />
              </button>
            </div>
            <button
              type="submit"
              disabled={isLoading}
              style={{
                ...primaryBtnStyle,
                background: 'linear-gradient(135deg, #10b981, #059669)',
                color: 'white',
                marginBottom: '10px'
              }}
            >
              {isLoading ? 'Modification...' : 'Modifier mon mot de passe'}
            </button>
            <div style={{ textAlign: 'center', marginTop: '8px' }}>
              <button
                type="button"
                onClick={() => { resetForm(); setAuthMode('login'); }}
                style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', fontSize: '12px', cursor: 'pointer' }}
              >
                ← Retour à la connexion
              </button>
            </div>
          </form>
        )}

        {/* === MODE INSCRIPTION EMAIL === */}
        {authMode === 'register' && (
          <form onSubmit={handleEmailRegister}>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '13px', textAlign: 'center', marginBottom: '16px' }}>
              Créer votre compte Partenaire
            </p>
            <div style={{ marginBottom: '12px' }}>
              <label style={labelStyle}>Nom complet</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Votre nom"
                required
                style={inputStyle}
              />
            </div>
            <div style={{ marginBottom: '12px' }}>
              <label style={labelStyle}>Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="votre@email.com"
                required
                style={inputStyle}
              />
            </div>
            <div style={{ marginBottom: '16px', position: 'relative' }}>
              <label style={labelStyle}>Mot de passe (min. 6 caractères)</label>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••"
                required
                minLength={6}
                style={{ ...inputStyle, paddingRight: '40px' }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{ position: 'absolute', right: '10px', top: '28px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: '4px' }}
              >
                <EyeIcon open={showPassword} />
              </button>
            </div>
            <button
              type="submit"
              disabled={isLoading}
              style={{
                ...primaryBtnStyle,
                background: 'linear-gradient(135deg, #ec4899, #8b5cf6)',
                color: 'white',
                marginBottom: '10px'
              }}
            >
              {isLoading ? 'Inscription...' : 'Créer mon compte'}
            </button>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
              <button
                type="button"
                onClick={() => { resetForm(); setAuthMode('login'); }}
                style={{ background: 'none', border: 'none', color: '#c4b5fd', fontSize: '12px', cursor: 'pointer', textDecoration: 'underline' }}
              >
                Déjà un compte ? Se connecter
              </button>
              <button
                type="button"
                onClick={() => { resetForm(); setAuthMode('choice'); }}
                style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', fontSize: '12px', cursor: 'pointer' }}
              >
                ← Retour
              </button>
            </div>
          </form>
        )}

        {/* Info sécurité */}
        <p style={{ color: 'rgba(255,255,255,0.25)', fontSize: '10px', textAlign: 'center', marginTop: '16px' }}>
          🔒 Connexion sécurisée
        </p>

        {/* Bouton Fermer */}
        <button
          type="button"
          onClick={onCancel}
          style={{ width: '100%', padding: '8px', marginTop: '8px', borderRadius: '8px', background: 'none', border: 'none', color: 'rgba(255,255,255,0.4)', fontSize: '12px', cursor: 'pointer' }}
          data-testid="coach-login-cancel"
        >
          Fermer
        </button>
      </div>

      {/* CSS animation keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
};

export default CoachLoginModal;

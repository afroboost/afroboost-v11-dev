/**
 * CoachLoginModal Component v10.0 - Email/Password
 * V403 : l'authentification Google (via auth.emergentagent.com) a ete retiree.
 *
 * Authentification multi-méthodes pour les Partenaires et Super Admin
 * - Email/Password classique (nouveau)
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
import { useState, useEffect, useRef } from 'react';
import axios from 'axios';

const API = (process.env.REACT_APP_BACKEND_URL || '') + '/api';


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

  // V403 : le traitement du retour OAuth Emergent (`session_id` dans le
  // fragment d'URL) est retire avec le bouton qui le declenchait.

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

        {/* === MODE CHOIX — Email, puis « Devenir Partenaire » (V403 : plus de Google) === */}
        {authMode === 'choice' && (
          <>
            <p style={{ color: 'rgba(255,255,255,0.5)', fontSize: '12px', textAlign: 'center', marginBottom: '12px' }}>Connectez-vous à votre espace</p>

            {/* Bouton Email (principal) */}
            <button
              onClick={() => { resetForm(); setAuthMode('login'); }}
              disabled={isLoading}
              style={{
                ...primaryBtnStyle,
                background: 'linear-gradient(135deg, #8b5cf6, #7c3aed)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '10px',
                boxShadow: '0 4px 15px rgba(139,92,246,0.3)',
                marginBottom: '10px'
              }}
            >
              <EmailIcon />
              <span>Se connecter avec Email</span>
            </button>

            {/* V403 — LE BOUTON « GOOGLE » A ETE RETIRE.
                Il n'ouvrait pas Google mais `auth.emergentagent.com`, la
                plateforme sur laquelle ce projet a ete construit : l'utilisateur
                tombait sur un ecran de consentement d'une marque tierce, en
                plein parcours Afroboost. Verifie avant retrait : les 11 comptes
                de `users_auth` sont TOUS en `email_password` avec un mot de
                passe — personne ne s'y connectait. */}

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
                background: 'linear-gradient(135deg, rgba(var(--primary-rgb, 217, 28, 210), 0.3), rgba(139,92,246,0.3))',
                border: '1px solid rgba(var(--primary-rgb, 217, 28, 210), 0.5)',
                color: 'var(--primary-color, #D91CD2)'
              }}
              data-testid="become-partner-btn"
            >
              Devenir Partenaire
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
